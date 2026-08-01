"""Plan 57 F2 — Tests de paridad de runtime para _run_spec.

C22 está resuelto por decisión del operador: el auto-publish de épicas es
comportamiento correcto e intencional. Los tests aquí verifican:
1. Que el despacho por runtime funciona (dispatch structure).
2. Que _run_spec NUNCA llama directamente maybe_autopublish_epic ni
   publish_issue_from_run.

Plan 278 F3 — el autopublish YA NO ocurre en el runner confirmado: se mudó al
post-hook services/epic_autopublish.py, que corre en ticket_status.on_execution_end
para los 3 runtimes. Por eso el assert que de verdad blinda el riel pasa a ser
que speculative.py no llame on_execution_end: si lo llamara, dispararía el
post-hook publicador y la especulación crearía épicas en el tracker real.
"""
import sys
import pathlib
import pytest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers de fixtures
# ---------------------------------------------------------------------------

def _make_mock_agent(output="<h1>Epic</h1>", output_format="html"):
    mock_result = MagicMock()
    mock_result.output = output
    mock_result.output_format = output_format
    mock_agent = MagicMock()
    mock_agent.run.return_value = mock_result
    return mock_agent


def _run_spec_patched(runtime, mock_agent):
    """Ejecuta _run_spec con DB y agents mockeados. Retorna el mock_agent para assertions."""
    import services.speculative as spec

    mock_row = MagicMock()
    mock_row.status = "running"
    mock_row.output = None

    mock_session = MagicMock()
    mock_session.get.return_value = mock_row

    import contextlib

    @contextlib.contextmanager
    def fake_scope():
        yield mock_session

    mock_agents_mod = MagicMock()
    mock_agents_mod.get.return_value = mock_agent

    with patch("services.speculative.session_scope", fake_scope), \
         patch("services.speculative._cancelled", set()), \
         patch.dict(sys.modules, {"agents": mock_agents_mod}):
        # _run_spec hace `import agents as _agents` como lazy local
        # patch.dict garantiza que cuando se ejecute esa línea, resuelva nuestro mock
        spec._run_spec(1, "business", [{"kind": "story", "content": "x"}], runtime=runtime)

    return mock_agents_mod


# ---------------------------------------------------------------------------
# Tests de despacho por runtime
# ---------------------------------------------------------------------------

def test_copilot_fallback_uses_agents_run():
    """Runtime '' (copilot): _run_spec usa agents.get().run() directamente."""
    mock_agent = _make_mock_agent()
    mock_agents_mod = _run_spec_patched(runtime="", mock_agent=mock_agent)
    mock_agent.run.assert_called_once()


def test_claude_cli_runtime_falls_back_to_copilot_until_f2a():
    """Runtime claude_code_cli: en v1 sin F2a, usa fallback copilot (a.run())."""
    mock_agent = _make_mock_agent()
    mock_agents_mod = _run_spec_patched(runtime="claude_code_cli", mock_agent=mock_agent)
    # v1: fallback copilot → a.run() se llama
    mock_agent.run.assert_called_once()


def test_codex_cli_runtime_falls_back_to_copilot_until_f2a():
    """Runtime codex_cli: en v1 sin F2a, usa fallback copilot."""
    mock_agent = _make_mock_agent(output="output", output_format="markdown")
    mock_agents_mod = _run_spec_patched(runtime="codex_cli", mock_agent=mock_agent)
    mock_agent.run.assert_called_once()


def test_runtime_not_supported_falls_back_gracefully():
    """Runtime desconocido → fallback copilot, sin excepción."""
    mock_agent = _make_mock_agent()
    mock_agents_mod = _run_spec_patched(runtime="unknown_runtime_xyz", mock_agent=mock_agent)
    mock_agent.run.assert_called_once()


def test_spec_never_calls_autopublish():
    """_run_spec NUNCA importa ni llama maybe_autopublish_epic o publish_issue_from_run.

    Blinda el riel: el autopublish ocurre en el post-hook services/epic_autopublish.py
    (Plan 278 F3), nunca en la especulación.
    """
    import services.speculative as spec_module

    # 1. No en namespace del módulo
    assert not hasattr(spec_module, "maybe_autopublish_epic"), \
        "_run_spec NO debe exponer maybe_autopublish_epic en el scope del módulo"
    assert not hasattr(spec_module, "publish_issue_from_run"), \
        "_run_spec NO debe exponer publish_issue_from_run en el scope del módulo"

    # 2. No en el source text (llamadas directas)
    src = pathlib.Path(spec_module.__file__).read_text(encoding="utf-8")
    assert "maybe_autopublish_epic" not in src, \
        "speculative.py no debe contener llamadas a maybe_autopublish_epic"
    assert "publish_issue_from_run" not in src, \
        "speculative.py no debe contener llamadas a publish_issue_from_run"

    # 3. Plan 278 F3 — EL assert que de verdad blinda el riel ahora que el
    # publicador es un post-hook: llamar on_execution_end lo dispararía.
    assert "on_execution_end" not in src, \
        "speculative.py no debe llamar on_execution_end: eso dispararía el post-hook publicador"


def test_agent_not_found_marks_cancelled():
    """Si agents.get() retorna None, spec queda cancelled sin excepción."""
    import services.speculative as spec
    import contextlib

    mock_session = MagicMock()
    mock_session.get.return_value = MagicMock()

    @contextlib.contextmanager
    def fake_scope():
        yield mock_session

    mock_agents_mod = MagicMock()
    mock_agents_mod.get.return_value = None  # agente inexistente

    with patch("services.speculative.session_scope", fake_scope), \
         patch("services.speculative._cancelled", set()), \
         patch("services.speculative._mark") as mock_mark, \
         patch.dict(sys.modules, {"agents": mock_agents_mod}):
        spec._run_spec(1, "business", [{"kind": "story", "content": "x"}], runtime="")
        mock_mark.assert_called_once_with(1, "cancelled")
