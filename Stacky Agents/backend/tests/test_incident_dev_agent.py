"""tests/test_incident_dev_agent.py — Plan 166 F4.

Agente NUEVO "Dev Resolutor de Incidencias" (`incident_dev`) + endpoint
POST /api/agents/run-incident-dev. Espeja el patrón de
tests/test_plan131_run_incident.py: parchea db.session_scope +
agent_runner.run_agent para aislar el endpoint (CERO llamadas reales).
"""
from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _make_app():
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    return app


@contextmanager
def _flag(enabled: bool):
    import config as cfg
    original = getattr(cfg.config, "STACKY_INCIDENT_DEV_RESOLVER_ENABLED", False)
    cfg.config.STACKY_INCIDENT_DEV_RESOLVER_ENABLED = enabled
    try:
        yield
    finally:
        cfg.config.STACKY_INCIDENT_DEV_RESOLVER_ENABLED = original


@contextmanager
def _patch_run_incident_dev_deps(ticket, execution_id=77, run_agent_exc=None):
    @contextmanager
    def _fake_scope():
        sess = MagicMock()
        sess.get.return_value = ticket
        yield sess

    import agent_runner as ar

    if run_agent_exc:
        mock_run_agent = MagicMock(side_effect=run_agent_exc)
    else:
        mock_run_agent = MagicMock(return_value=execution_id)

    with patch("db.session_scope", _fake_scope), \
         patch.object(ar, "run_agent", mock_run_agent):
        yield mock_run_agent


def _fake_ticket(work_item_type="Issue", ado_id=555, title="[INC] Falla X", description="<p>desglose</p>"):
    t = MagicMock()
    t.id = 1
    t.work_item_type = work_item_type
    t.ado_id = ado_id
    t.title = title
    t.description = description
    return t


# ── 1-2. Registro + contrato del prompt ─────────────────────────────────────


def test_incident_dev_registered():
    from agents import registry
    assert "incident_dev" in registry


def test_incident_dev_system_prompt_has_contract():
    from agents.incident_dev import IncidentDevAgent
    prompt = IncidentDevAgent().system_prompt()
    assert "🚀" in prompt
    assert "⚠️ BLOQUEADO" in prompt
    assert "criterios de aceptación" in prompt.lower()


# ── 3-5. Endpoint run-incident-dev ──────────────────────────────────────────


def test_run_incident_dev_404_when_flag_off():
    app = _make_app()
    with _flag(False):
        with app.test_client() as client:
            resp = client.post("/api/agents/run-incident-dev", json={"ticket_id": 1})
    assert resp.status_code == 404
    assert resp.get_json()["error"] == "feature_disabled"


def test_run_incident_dev_400_when_not_issue():
    ticket = _fake_ticket(work_item_type="Task")
    app = _make_app()
    with _flag(True):
        with _patch_run_incident_dev_deps(ticket):
            with app.test_client() as client:
                resp = client.post("/api/agents/run-incident-dev", json={"ticket_id": 1})
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "not_an_issue"


def test_run_incident_dev_launches():
    ticket = _fake_ticket(work_item_type="Issue")
    app = _make_app()
    with _flag(True):
        with _patch_run_incident_dev_deps(ticket, execution_id=888) as mock_run_agent:
            with app.test_client() as client:
                resp = client.post(
                    "/api/agents/run-incident-dev",
                    json={"ticket_id": 1, "runtime": "github_copilot"},
                )
    assert resp.status_code == 202, resp.get_json()
    data = resp.get_json()
    assert data["execution_id"] == 888
    assert data["status"] == "running"
    mock_run_agent.assert_called_once()
    _, kwargs = mock_run_agent.call_args
    assert kwargs["agent_type"] == "incident_dev"
    assert kwargs["ticket_id"] == 1


# ── 6. ensure_incident_dev_agent_file ───────────────────────────────────────


def test_ensure_incident_dev_agent_file_writes(tmp_path, monkeypatch):
    from services import incident_dev_context

    monkeypatch.setattr(incident_dev_context, "stacky_agents_dir", lambda: tmp_path)
    dest = incident_dev_context.ensure_incident_dev_agent_file()
    assert dest.exists()
    assert dest.name == "IncidentDevResolver.agent.md"
    assert "stacky_agent_type: incident_dev" in dest.read_text(encoding="utf-8")


# ── 7-10. Plan 177 F3 — baseline + intent del auto-PR ───────────────────────


@contextmanager
def _pr_flags(resolver: bool, pr: bool):
    import config as cfg
    o1 = getattr(cfg.config, "STACKY_INCIDENT_DEV_RESOLVER_ENABLED", False)
    o2 = getattr(cfg.config, "STACKY_INCIDENT_DEV_PR_ENABLED", False)
    cfg.config.STACKY_INCIDENT_DEV_RESOLVER_ENABLED = resolver
    cfg.config.STACKY_INCIDENT_DEV_PR_ENABLED = pr
    try:
        yield
    finally:
        cfg.config.STACKY_INCIDENT_DEV_RESOLVER_ENABLED = o1
        cfg.config.STACKY_INCIDENT_DEV_PR_ENABLED = o2


@contextmanager
def _patch_pr_deps(repo_root="/repo", baseline=None):
    """Parchea las deps de F3 (project_context + incident_dev_pr) para no tocar git."""
    from services import incident_dev_pr, project_context
    if baseline is None:
        baseline = {"head": "abc", "entries": {}}
    ctx = MagicMock()
    ctx.workspace_root = "/ws" if repo_root else None
    record = MagicMock()
    with patch.object(project_context, "resolve_project_context", MagicMock(return_value=ctx)), \
         patch.object(incident_dev_pr, "resolve_repo_root", MagicMock(return_value=repo_root)), \
         patch.object(incident_dev_pr, "snapshot_worktree", MagicMock(return_value=baseline)), \
         patch.object(incident_dev_pr, "record_intent", record):
        yield record


def test_run_incident_dev_records_intent_when_open_pr_and_flag_on():
    ticket = _fake_ticket(work_item_type="Issue")
    app = _make_app()
    with _pr_flags(True, True):
        with _patch_run_incident_dev_deps(ticket, execution_id=321):
            with _patch_pr_deps(repo_root="/repo") as record:
                with app.test_client() as client:
                    resp = client.post(
                        "/api/agents/run-incident-dev",
                        json={"ticket_id": 1, "runtime": "github_copilot", "open_pr": True},
                    )
    assert resp.status_code == 202, resp.get_json()
    record.assert_called_once()
    args, _kwargs = record.call_args
    assert args[0] == 321  # execution_id
    assert args[1]["open_pr"] is True
    assert args[1]["repo_root"] == "/repo"


def test_run_incident_dev_no_intent_when_open_pr_false():
    ticket = _fake_ticket(work_item_type="Issue")
    app = _make_app()
    with _pr_flags(True, True):
        with _patch_run_incident_dev_deps(ticket, execution_id=322):
            with _patch_pr_deps() as record:
                with app.test_client() as client:
                    resp = client.post(
                        "/api/agents/run-incident-dev",
                        json={"ticket_id": 1, "runtime": "github_copilot"},
                    )
    assert resp.status_code == 202
    record.assert_not_called()


def test_run_incident_dev_no_intent_when_pr_flag_off():
    ticket = _fake_ticket(work_item_type="Issue")
    app = _make_app()
    with _pr_flags(True, False):  # flag de auto-PR OFF (el flag manda sobre el checkbox)
        with _patch_run_incident_dev_deps(ticket, execution_id=323):
            with _patch_pr_deps() as record:
                with app.test_client() as client:
                    resp = client.post(
                        "/api/agents/run-incident-dev",
                        json={"ticket_id": 1, "open_pr": True},
                    )
    assert resp.status_code == 202
    record.assert_not_called()


def test_run_incident_dev_no_intent_when_not_a_git_repo():
    ticket = _fake_ticket(work_item_type="Issue")
    app = _make_app()
    with _pr_flags(True, True):
        with _patch_run_incident_dev_deps(ticket, execution_id=324):
            with _patch_pr_deps(repo_root=None) as record:  # workspace no es repo git
                with app.test_client() as client:
                    resp = client.post(
                        "/api/agents/run-incident-dev",
                        json={"ticket_id": 1, "open_pr": True},
                    )
    assert resp.status_code == 202
    record.assert_not_called()
