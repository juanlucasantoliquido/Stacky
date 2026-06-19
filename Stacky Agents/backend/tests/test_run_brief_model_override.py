"""Plan 40 F3 + Plan 42 F3 — Wiring de model_override, effort_override y clamp en run_brief.

Tests TDD que validan:
1. Sin 'model' en body → run_agent llamado con model_override=None.
2. Con 'model' válido → run_agent llamado con model_override="claude-sonnet-4-6".
3. effort_override="high" siempre pasado desde run_brief a run_agent.
4. clamp_model bloquea modelos opus.
5. Plan 42: opus se clampea al cap; haiku pasa sin elevar; sin model → None;
   effort del body se respeta; effort inválido defaultea a "high".
"""
from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, call, patch

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _make_app():
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    return app


@contextmanager
def _patch_run_brief_deps(execution_id=99, run_agent_exc=None):
    """Parchea session_scope + agent_runner.run_agent para aislar run_brief."""
    fake_ticket = MagicMock()
    fake_ticket.id = 1

    @contextmanager
    def _fake_scope():
        sess = MagicMock()
        sess.query.return_value.filter_by.return_value.first.return_value = fake_ticket
        yield sess

    import agent_runner as ar

    if run_agent_exc:
        mock_run_agent = MagicMock(side_effect=run_agent_exc)
    else:
        mock_run_agent = MagicMock(return_value=execution_id)

    with patch("db.session_scope", _fake_scope), \
         patch.object(ar, "run_agent", mock_run_agent):
        yield mock_run_agent


# ---------------------------------------------------------------------------
# 1. Sin 'model' en body → model_override=None
# ---------------------------------------------------------------------------

def test_run_brief_no_model_passes_none_override():
    app = _make_app()
    with app.test_client() as client:
        with _patch_run_brief_deps(execution_id=10) as mock_run_agent:
            resp = client.post(
                "/api/agents/run-brief",
                json={"brief": "texto del brief", "runtime": "claude_code_cli"},
                headers={"X-User-Email": "test@test.com"},
            )
        assert resp.status_code == 202
        args, kwargs = mock_run_agent.call_args
        assert kwargs.get("model_override") is None, (
            f"model_override debería ser None, es {kwargs.get('model_override')!r}"
        )


# ---------------------------------------------------------------------------
# 2. Con 'model' válido → model_override="claude-sonnet-4-6"
# ---------------------------------------------------------------------------

def test_run_brief_with_model_passes_override():
    app = _make_app()
    with app.test_client() as client:
        with _patch_run_brief_deps(execution_id=11) as mock_run_agent:
            resp = client.post(
                "/api/agents/run-brief",
                json={
                    "brief": "texto del brief",
                    "model": "claude-sonnet-4-6",
                    "runtime": "claude_code_cli",
                },
                headers={"X-User-Email": "test@test.com"},
            )
        assert resp.status_code == 202
        _, kwargs = mock_run_agent.call_args
        assert kwargs.get("model_override") == "claude-sonnet-4-6", (
            f"model_override debería ser 'claude-sonnet-4-6', es {kwargs.get('model_override')!r}"
        )


# ---------------------------------------------------------------------------
# 3. effort_override="high" siempre presente en la llamada a run_agent
# ---------------------------------------------------------------------------

def test_run_brief_always_passes_effort_high():
    app = _make_app()
    with app.test_client() as client:
        with _patch_run_brief_deps(execution_id=12) as mock_run_agent:
            resp = client.post(
                "/api/agents/run-brief",
                json={"brief": "texto del brief", "runtime": "claude_code_cli"},
                headers={"X-User-Email": "test@test.com"},
            )
        assert resp.status_code == 202
        _, kwargs = mock_run_agent.call_args
        assert kwargs.get("effort_override") == "high", (
            f"effort_override debería ser 'high', es {kwargs.get('effort_override')!r}"
        )


# ---------------------------------------------------------------------------
# 4. clamp_model bloquea modelos opus (test unitario sobre llm_router.clamp_model)
# ---------------------------------------------------------------------------

def test_clamp_model_blocks_opus():
    from services import llm_router
    clamped = llm_router.clamp_model("claude-opus-4-5")
    assert "opus" not in clamped.lower(), (
        f"clamp_model debe eliminar opus, devolvió: {clamped!r}"
    )
    assert clamped, "clamp_model no debe devolver cadena vacía"


# ---------------------------------------------------------------------------
# Plan 42 F3 — tests nuevos
# ---------------------------------------------------------------------------

def test_run_brief_clamps_opus_to_cap():
    """Opus en body → run_agent recibe model_override == CLAUDE_CAP_MODEL."""
    from services.llm_router import CLAUDE_CAP_MODEL
    app = _make_app()
    with app.test_client() as client:
        with _patch_run_brief_deps(execution_id=20) as mock_run_agent:
            resp = client.post(
                "/api/agents/run-brief",
                json={"brief": "x", "runtime": "claude_code_cli", "model": "claude-opus-4-7"},
                headers={"X-User-Email": "test@test.com"},
            )
    assert resp.status_code == 202
    _, kwargs = mock_run_agent.call_args
    assert kwargs.get("model_override") == CLAUDE_CAP_MODEL, (
        f"Opus debe clampearse a {CLAUDE_CAP_MODEL!r}, fue {kwargs.get('model_override')!r}"
    )


def test_run_brief_allows_haiku():
    """Haiku en body → pasa sin elevar (no se sube a sonnet)."""
    app = _make_app()
    with app.test_client() as client:
        with _patch_run_brief_deps(execution_id=21) as mock_run_agent:
            resp = client.post(
                "/api/agents/run-brief",
                json={"brief": "x", "runtime": "claude_code_cli", "model": "claude-haiku-3-5"},
                headers={"X-User-Email": "test@test.com"},
            )
    assert resp.status_code == 202
    _, kwargs = mock_run_agent.call_args
    assert kwargs.get("model_override") == "claude-haiku-3-5", (
        f"Haiku no debe elevarse, fue {kwargs.get('model_override')!r}"
    )


def test_run_brief_model_none_when_empty():
    """Body sin 'model' → model_override is None."""
    app = _make_app()
    with app.test_client() as client:
        with _patch_run_brief_deps(execution_id=22) as mock_run_agent:
            resp = client.post(
                "/api/agents/run-brief",
                json={"brief": "x", "runtime": "claude_code_cli"},
                headers={"X-User-Email": "test@test.com"},
            )
    assert resp.status_code == 202
    _, kwargs = mock_run_agent.call_args
    assert kwargs.get("model_override") is None, (
        f"Sin model → None, fue {kwargs.get('model_override')!r}"
    )


def test_run_brief_passes_effort_from_body():
    """Body con effort:'medium' → effort_override='medium'."""
    app = _make_app()
    with app.test_client() as client:
        with _patch_run_brief_deps(execution_id=23) as mock_run_agent:
            resp = client.post(
                "/api/agents/run-brief",
                json={"brief": "x", "runtime": "claude_code_cli", "effort": "medium"},
                headers={"X-User-Email": "test@test.com"},
            )
    assert resp.status_code == 202
    _, kwargs = mock_run_agent.call_args
    assert kwargs.get("effort_override") == "medium", (
        f"effort_override debería ser 'medium', es {kwargs.get('effort_override')!r}"
    )


def test_run_brief_effort_defaults_high():
    """Body sin effort → effort_override='high' por defecto."""
    app = _make_app()
    with app.test_client() as client:
        with _patch_run_brief_deps(execution_id=24) as mock_run_agent:
            resp = client.post(
                "/api/agents/run-brief",
                json={"brief": "x", "runtime": "claude_code_cli"},
                headers={"X-User-Email": "test@test.com"},
            )
    assert resp.status_code == 202
    _, kwargs = mock_run_agent.call_args
    assert kwargs.get("effort_override") == "high", (
        f"effort_override sin body → 'high', fue {kwargs.get('effort_override')!r}"
    )
