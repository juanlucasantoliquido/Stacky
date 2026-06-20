"""Plan 57 F4 — Tests del claim hook en run_brief y flujo de speculative.claim()."""
import os
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta


# ---------------------------------------------------------------------------
# Tests sobre speculative.claim() directo
# ---------------------------------------------------------------------------

def _make_completed_row(agent_type="business", runtime="claude_code_cli",
                        output="<h1>Epic</h1>"):
    row = MagicMock()
    row.agent_type = agent_type
    row.input_hash = "abc123"
    row.status = "completed"
    row.output = output
    row.output_format = "html"
    row.id = 42
    row.ticket_id = 1
    row.created_at = datetime.utcnow()
    row.expires_at = datetime.utcnow() + timedelta(minutes=5)

    def to_dict(include_output=False):
        d = {
            "id": row.id,
            "agent_type": row.agent_type,
            "input_hash": row.input_hash,
            "status": row.status,
            "ticket_id": row.ticket_id,
            "created_at": row.created_at.isoformat(),
            "expires_at": row.expires_at.isoformat(),
        }
        if include_output:
            d["output"] = row.output
            d["output_format"] = row.output_format
        return d

    row.to_dict = to_dict
    return row


def test_claim_hit_returns_output():
    """Spec completado → claim retorna dict con output."""
    import contextlib
    import services.speculative as spec
    from services.output_cache import compute_key

    blocks = [{"kind": "story", "content": "test"}]
    h = compute_key(agent_type="business", blocks=blocks, runtime="claude_code_cli")

    row = _make_completed_row(runtime="claude_code_cli")
    row.input_hash = h

    mock_query = MagicMock()
    mock_query.filter_by.return_value.order_by.return_value.first.return_value = row
    mock_session = MagicMock()
    mock_session.query.return_value = mock_query

    @contextlib.contextmanager
    def fake_scope():
        yield mock_session

    with patch.dict(os.environ, {"STACKY_SPECULATIVE_ENABLED": "true"}, clear=False), \
         patch("services.speculative.session_scope", fake_scope):
        result = spec.claim(
            agent_type="business",
            context_blocks=blocks,
            runtime="claude_code_cli",
        )

    assert result is not None
    assert result["output"] == "<h1>Epic</h1>"
    assert result["status"] == "completed"


def test_claim_miss_when_no_spec():
    """Sin spec completado → claim retorna None."""
    import contextlib
    import services.speculative as spec

    mock_query = MagicMock()
    mock_query.filter_by.return_value.order_by.return_value.first.return_value = None
    mock_session = MagicMock()
    mock_session.query.return_value = mock_query

    @contextlib.contextmanager
    def fake_scope():
        yield mock_session

    with patch.dict(os.environ, {"STACKY_SPECULATIVE_ENABLED": "true"}, clear=False), \
         patch("services.speculative.session_scope", fake_scope):
        result = spec.claim(
            agent_type="business",
            context_blocks=[{"kind": "story", "content": "x"}],
            runtime="claude_code_cli",
        )

    assert result is None


def test_claim_different_runtime_miss():
    """Hash distinto por runtime diferente → claim automáticamente falla."""
    from services.output_cache import compute_key

    blocks = [{"kind": "story", "content": "x"}]
    h_cli = compute_key(agent_type="business", blocks=blocks, runtime="claude_code_cli")
    h_codex = compute_key(agent_type="business", blocks=blocks, runtime="codex_cli")
    assert h_cli != h_codex, "Hashes distintos garantizan que claim no cruza runtimes"


def test_claim_flag_off_always_miss():
    """claim() retorna None si STACKY_SPECULATIVE_ENABLED=false."""
    import services.speculative as spec
    with patch.dict(os.environ, {"STACKY_SPECULATIVE_ENABLED": "false"}, clear=False):
        result = spec.claim(
            agent_type="business",
            context_blocks=[{"kind": "story", "content": "x"}],
            runtime="claude_code_cli",
        )
    assert result is None


def test_spec_expired_ttl_misses():
    """Spec expirado (expires_at en el pasado) → claim retorna None."""
    import contextlib
    import services.speculative as spec

    row = _make_completed_row()
    row.expires_at = datetime.utcnow() - timedelta(minutes=1)  # expirado

    mock_query = MagicMock()
    mock_query.filter_by.return_value.order_by.return_value.first.return_value = row
    mock_session = MagicMock()
    mock_session.query.return_value = mock_query

    @contextlib.contextmanager
    def fake_scope():
        yield mock_session

    with patch.dict(os.environ, {"STACKY_SPECULATIVE_ENABLED": "true"}, clear=False), \
         patch("services.speculative.session_scope", fake_scope):
        result = spec.claim(
            agent_type="business",
            context_blocks=[{"kind": "story", "content": "x"}],
        )

    assert result is None
    assert row.status == "expired"


# ---------------------------------------------------------------------------
# Tests de la anotación from_speculative en run_brief
# ---------------------------------------------------------------------------

def test_spec_claim_code_is_present_in_run_brief():
    """run_brief contiene código que intenta el claim especulativo (F4)."""
    import pathlib
    src_path = pathlib.Path(__file__).parents[1] / "api" / "agents.py"
    src = src_path.read_text(encoding="utf-8")
    assert "from_speculative" in src, \
        "agents.py debe anotar from_speculative en metadata del execution (Plan 57 F4)"
    assert "_speculative.claim(" in src or "speculative.claim(" in src, \
        "run_brief debe llamar speculative.claim() como claim hook (Plan 57 F4)"


def test_claimed_epic_still_requires_confirmation():
    """Spec output de épica: el claim es informativo, autopublish ocurre en el runner.

    El operador sigue confirmando (click en Run). El claim solo anota from_speculative.
    El autopublish ocurre cuando claude_code_cli_runner finaliza, no antes.
    """
    # Verificamos que claim() no llama autopublish (estructuralmente)
    import pathlib
    src = (pathlib.Path(__file__).parents[1] / "services" / "speculative.py").read_text(
        encoding="utf-8"
    )
    assert "_maybe_autopublish_epic" not in src
    assert "publish_issue_from_run" not in src


def test_claim_miss_runs_normal_execution():
    """Con spec miss (flag OFF), run_brief llega a agent_runner.run_agent normalmente."""
    # Con flag OFF, _spec_claimed = None → se llama run_agent sin spec_output.
    # Verificamos que la firma de run_agent NO fue modificada para aceptar spec_output.
    import inspect
    from agent_runner import run_agent
    sig = inspect.signature(run_agent)
    assert "spec_output" not in sig.parameters, \
        "run_agent no debe recibir spec_output (el claim hook es solo metadata)"
