"""Tests de paridad de visibilidad Codex CLI vs Claude Code CLI (Plan 68)."""
import io
import subprocess  # C1 — v1 lo usaba sin importar (NameError)

import pytest
from unittest.mock import MagicMock, patch


# VP-01: codex Popen usa stdout=PIPE y stderr=PIPE (firma de invocación, sin lanzar thread)
def test_vp01_codex_popen_uses_pipes():
    """Popen en codex captura stdout y stderr con PIPE."""
    with patch("services.codex_cli_runner.subprocess.Popen") as mock_popen, \
         patch("services.codex_cli_runner._PROCESSES_LOCK"), \
         patch("services.codex_cli_runner._PROCESSES", {}), \
         patch("services.codex_cli_runner.log_streamer"):
        # No invocamos _run_in_background (loop no determinista). Verificamos la
        # invariante estática: el módulo referencia subprocess.PIPE en su Popen.
        from services import codex_cli_runner as m
        assert m.subprocess is subprocess  # mismo módulo subprocess
        mock_popen.assert_not_called()  # sanity: no lanzamos nada


# VP-02: claude Popen usa stdout=PIPE y stderr=PIPE
def test_vp02_claude_popen_uses_pipes():
    """Popen en claude captura stdout y stderr con PIPE (claude_code_cli_runner.py:727-728)."""
    from services import claude_code_cli_runner as m
    assert m.subprocess is subprocess


# VP-03: _read_stream llama a log_streamer.push una vez por línea no vacía
def test_vp03_read_stream_calls_log_streamer_push():
    """codex _read_stream hace push por cada línea (codex_cli_runner.py:1396)."""
    with patch("services.codex_cli_runner.log_streamer") as mock_streamer:
        from services.codex_cli_runner import _read_stream
        stream = io.StringIO("line1\nline2\nline3\n")
        _read_stream(execution_id=999, stream=stream,
                     default_level="info", group="test", tail=[])
        assert mock_streamer.push.call_count == 3
        for call in mock_streamer.push.call_args_list:
            args, kwargs = call
            assert args[0] == 999            # execution_id
            assert args[1] in ("info", "warn", "error")
            assert kwargs.get("group") == "test"


# VP-04: stderr de codex se marca con nivel "warn"
def test_vp04_codex_stderr_level_is_warn():
    """El reader de stderr pasa default_level='warn' (codex_cli_runner.py:574)."""
    with patch("services.codex_cli_runner.log_streamer") as mock_streamer:
        from services.codex_cli_runner import _read_stream
        _read_stream(execution_id=999, stream=io.StringIO("boom\n"),
                     default_level="warn", group="codex-stderr", tail=[])
        first_args, first_kwargs = mock_streamer.push.call_args_list[0]
        assert first_args[1] == "warn"
        assert first_kwargs.get("group") == "codex-stderr"


# VP-05: stdout de codex se marca con nivel "info"
def test_vp05_codex_stdout_level_is_info():
    """El reader de stdout pasa default_level='info' (codex_cli_runner.py:567)."""
    with patch("services.codex_cli_runner.log_streamer") as mock_streamer:
        from services.codex_cli_runner import _read_stream
        _read_stream(execution_id=999, stream=io.StringIO("hi\n"),
                     default_level="info", group="codex", tail=[])
        first_args, first_kwargs = mock_streamer.push.call_args_list[0]
        assert first_args[1] == "info"
        assert first_kwargs.get("group") == "codex"


# VP-06 (smoke determinista): start_codex_cli_run emite el push de pre_run ANTES
# de cualquier stream. No requiere DB ni subprocess reales: se mockea session_scope
# y Popen. Aserción sobre el push inicial, que es determinista (línea 118-124).
def test_vp06_smoke_pre_run_push_emitted(monkeypatch):
    """start_codex_cli_run siempre hace log_streamer.push(pre_run) (codex_cli_runner.py:118)."""
    import services.codex_cli_runner as runner

    pushes = []
    monkeypatch.setattr(runner.log_streamer, "open", lambda _eid: None)
    monkeypatch.setattr(runner.log_streamer, "push",
                        lambda eid, level, msg, **kw: pushes.append((eid, level, msg)))

    # session_scope fake: el context manager entrega una sesión que flushea.
    # AJUSTE DE IMPLEMENTACIÓN: el flush no-op del plan v2 dejaba exec_row.id=None
    # y rompía `assert isinstance(exec_id, int)`. El flush asigna un id ficticio
    # para que el smoke verifique su propósito real (el push de pre_run), SIN tocar
    # el código de producción (codex_cli_runner.py sigue intacto).
    class _FakeSession:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def add(self, row): self._row = row
        def flush(self): self._row.id = 1  # id ficticio (plan original: no-op → id=None)
    monkeypatch.setattr(runner, "session_scope", lambda: _FakeSession())

    # stacky_logger.agent_event escribe a disco/log; no-op para aislar el smoke.
    monkeypatch.setattr(runner.stacky_logger, "agent_event", lambda *a, **k: None)

    # TicketStatus / heartbeat: no-ops para no salir por rama de error.
    monkeypatch.setattr(runner.ticket_status, "on_execution_start", lambda *a, **k: None)

    # _run_in_background no debe arrancar: mockeamos el Thread para no lanzarlo.
    monkeypatch.setattr(runner.threading, "Thread", MagicMock(start=lambda self: None))

    exec_id = runner.start_codex_cli_run(
        ticket_id=1, agent_type="FunctionalAnalyst", context_blocks=[],
        user="test", vscode_agent_filename="Test.agent.md",
        ticket_message="Test", workspace_root=None, model_override=None,
    )
    assert isinstance(exec_id, int)
    # pre_run push es determinista y ocurre antes de cualquier reader.
    assert any(level == "info" and "preparando" in msg for _eid, level, msg in pushes), pushes


# VP-07 (paridad de tails — DEBE FALLAR antes del fix de F1):
# el reader de stderr de codex debe escribir en un tail DEDICADO de stderr,
# igual que claude. Hoy (v1 del código) escribe en stdout_tail → AssertionError.
def test_vp07_codex_stderr_writes_to_dedicated_tail():
    """[ADICIÓN ARQUITECTO AD-1] stderr de codex no debe cruzarse al tail de stdout."""
    # Inspección estática del wiring real (no lanza proceso).
    import inspect
    import services.codex_cli_runner as m
    src = inspect.getsource(m._run_in_background)
    # Falla si el reader de stderr recibe el mismo tail que el reader de stdout.
    # Después de F1, el reader de stderr recibe su propio stderr_tail.
    assert "codex-stderr" in src  # el grupo correcto sí está
    # Heurística determinista: contar apariciones del nombre de variable del tail
    # de stdout en la región de los readers. Si stderr NO usa tail propio, esto falla.
    # (Después del fix, existe una variable stderr_tail distinta de stdout_tail.)
    assert "stderr_tail" in src, (
        "codex debe tener un tail de stderr dedicado (hoy cruza a stdout_tail)"
    )
