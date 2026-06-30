"""Plan 41 F3 — Orquestación pre-vuelo en run_brief (dos pasos)."""
from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.intent_preflight import IntentBrief  # noqa: E402


def _make_app():
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    return app


@contextmanager
def _patch_deps(execution_id=77):
    fake_ticket = MagicMock()
    fake_ticket.id = 1

    @contextmanager
    def _fake_scope():
        sess = MagicMock()
        sess.query.return_value.filter_by.return_value.first.return_value = fake_ticket
        yield sess

    import agent_runner as ar
    mock_run_agent = MagicMock(return_value=execution_id)
    with patch("db.session_scope", _fake_scope), \
         patch.object(ar, "run_agent", mock_run_agent):
        yield mock_run_agent


def _post(client, body):
    return client.post(
        "/api/agents/run-brief",
        json={"brief": "hacé la épica de facturación", "runtime": "claude_code_cli", **body},
        headers={"X-User-Email": "op@x"},
    )


_INTENT = IntentBrief(
    objective="Generar épica", deliverables=["épica"], assumptions=[],
    open_questions=[], areas=[], confidence=0.9,
)


def test_flag_off_is_byte_identical():
    from config import config
    app = _make_app()
    with patch.object(config, "INTENT_PREFLIGHT_ENABLED", False):
        with app.test_client() as c:
            with _patch_deps() as run_agent:
                r = _post(c, {"preflight": True})
            assert r.status_code == 202
            run_agent.assert_called_once()


def test_preflight_returns_intent_and_does_not_run():
    from config import config
    app = _make_app()
    with patch.object(config, "INTENT_PREFLIGHT_ENABLED", True), \
         patch("services.intent_preflight.generate_intent_brief", return_value=_INTENT):
        with app.test_client() as c:
            with _patch_deps() as run_agent:
                r = _post(c, {"preflight": True})
            assert r.status_code == 200
            d = r.get_json()
            assert d["stage"] == "preflight"
            assert d["intent"]["objective"] == "Generar épica"
            run_agent.assert_not_called()


def test_preflight_runtime_unavailable_falls_through():
    from config import config
    app = _make_app()
    with patch.object(config, "INTENT_PREFLIGHT_ENABLED", True), \
         patch("services.intent_preflight.generate_intent_brief", return_value=None):
        with app.test_client() as c:
            with _patch_deps() as run_agent:
                r = _post(c, {"preflight": True})
            assert r.status_code == 202
            run_agent.assert_called_once()


def test_approved_runs_with_corrections_block():
    from config import config
    app = _make_app()
    with patch.object(config, "INTENT_PREFLIGHT_ENABLED", True):
        with app.test_client() as c:
            with _patch_deps() as run_agent:
                r = _post(c, {"approved": True, "corrections": "el batch es FacturacionNocturna"})
            assert r.status_code == 202
            blocks = run_agent.call_args.kwargs["context_blocks"]
            assert blocks[0]["id"] == "operator-corrections"
            assert "FacturacionNocturna" in blocks[0]["content"]


def test_approved_without_corrections_runs_clean():
    from config import config
    app = _make_app()
    with patch.object(config, "INTENT_PREFLIGHT_ENABLED", True):
        with app.test_client() as c:
            with _patch_deps() as run_agent:
                r = _post(c, {"approved": True})
            assert r.status_code == 202
            blocks = run_agent.call_args.kwargs["context_blocks"]
            assert all(b["id"] != "operator-corrections" for b in blocks)


def test_missing_brief_returns_400():
    app = _make_app()
    with app.test_client() as c:
        r = c.post("/api/agents/run-brief", json={"runtime": "claude_code_cli"},
                   headers={"X-User-Email": "op@x"})
    assert r.status_code == 400


def test_preflight_marks_auto_approvable():
    from config import config
    app = _make_app()
    with patch.object(config, "INTENT_PREFLIGHT_ENABLED", True), \
         patch.object(config, "INTENT_PREFLIGHT_AUTO_APPROVE", True), \
         patch.object(config, "INTENT_PREFLIGHT_AUTO_APPROVE_MIN_CONF", 0.8), \
         patch("services.intent_preflight.generate_intent_brief", return_value=_INTENT):
        with app.test_client() as c:
            with _patch_deps():
                r = _post(c, {"preflight": True})
            assert r.get_json()["auto_approvable"] is True
