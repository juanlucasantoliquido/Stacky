"""tests/test_plan131_run_incident.py — Plan 131 F4.

POST /api/agents/run-incident. Espejo de test_run_brief_model_override.py:
parchea db.session_scope + agent_runner.run_agent para aislar el endpoint.
CERO llamadas reales a ADO/tracker (get_tracker_provider se deja fallar
naturalmente en el entorno de test sin credenciales, o se parchea explícito).
"""
from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import runtime_paths
from services import incident_store


def _make_app():
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    return app


@contextmanager
def _patch_run_incident_deps(execution_id=99, run_agent_exc=None):
    fake_ticket = MagicMock()
    fake_ticket.id = 1

    @contextmanager
    def _fake_scope():
        sess = MagicMock()
        sess.query.return_value.filter_by.return_value.first.return_value = fake_ticket
        sess.get.return_value = None
        yield sess

    import agent_runner as ar

    if run_agent_exc:
        mock_run_agent = MagicMock(side_effect=run_agent_exc)
    else:
        mock_run_agent = MagicMock(return_value=execution_id)

    with patch("db.session_scope", _fake_scope), \
         patch.object(ar, "run_agent", mock_run_agent):
        yield mock_run_agent


@contextmanager
def _flag_on():
    import config as cfg
    original = getattr(cfg.config, "STACKY_INCIDENT_RESOLVER_ENABLED", False)
    cfg.config.STACKY_INCIDENT_RESOLVER_ENABLED = True
    try:
        yield
    finally:
        cfg.config.STACKY_INCIDENT_RESOLVER_ENABLED = original


@contextmanager
def _flag_off():
    import config as cfg
    original = getattr(cfg.config, "STACKY_INCIDENT_RESOLVER_ENABLED", False)
    cfg.config.STACKY_INCIDENT_RESOLVER_ENABLED = False
    try:
        yield
    finally:
        cfg.config.STACKY_INCIDENT_RESOLVER_ENABLED = original


def _create_incident(tmp_path, monkeypatch, text="la pantalla se rompe"):
    monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)
    return incident_store.create_incident(text, [])


def test_flag_off_404(tmp_path, monkeypatch):
    incident = _create_incident(tmp_path, monkeypatch)
    app = _make_app()
    with _flag_off():
        with app.test_client() as client:
            resp = client.post(
                "/api/agents/run-incident",
                json={"incident_id": incident["id"], "runtime": "claude_code_cli"},
                headers={"X-User-Email": "test@test.com"},
            )
    assert resp.status_code == 404
    assert resp.get_json()["error"] == "feature_disabled"


def test_incident_not_found_400(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)
    app = _make_app()
    with _flag_on():
        with app.test_client() as client:
            resp = client.post(
                "/api/agents/run-incident",
                json={"incident_id": "inc_does_not_exist", "runtime": "claude_code_cli"},
                headers={"X-User-Email": "test@test.com"},
            )
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "incident_not_found"


def test_happy_path_prompt_contains_manifest_and_catalog(tmp_path, monkeypatch):
    incident = _create_incident(tmp_path, monkeypatch, text="la pantalla se rompe feo")
    app = _make_app()
    with _flag_on():
        with app.test_client() as client:
            with _patch_run_incident_deps(execution_id=555) as mock_run_agent:
                resp = client.post(
                    "/api/agents/run-incident",
                    json={"incident_id": incident["id"], "runtime": "claude_code_cli"},
                    headers={"X-User-Email": "test@test.com"},
                )
    assert resp.status_code == 202
    body = resp.get_json()
    assert body["execution_id"] == 555

    _, kwargs = mock_run_agent.call_args
    assert kwargs["agent_type"] == "incident"
    assert kwargs["vscode_agent_filename"] == "IncidentAnalyst.agent.md"
    prompt = kwargs["context_blocks"][0]["content"]
    assert "la pantalla se rompe feo" in prompt
    assert "<attachments-manifest>" in prompt
    assert "<epic-catalog>" in prompt


def test_status_transitions_to_analizando_with_execution_id(tmp_path, monkeypatch):
    incident = _create_incident(tmp_path, monkeypatch)
    app = _make_app()
    with _flag_on():
        with app.test_client() as client:
            with _patch_run_incident_deps(execution_id=777):
                client.post(
                    "/api/agents/run-incident",
                    json={"incident_id": incident["id"], "runtime": "claude_code_cli"},
                    headers={"X-User-Email": "test@test.com"},
                )
    updated = incident_store.get_incident(incident["id"])
    assert updated["status"] == "analizando"
    assert updated["execution_id"] == 777


def test_codex_and_github_copilot_not_rejected(tmp_path, monkeypatch):
    for runtime_name in ("codex_cli", "github_copilot"):
        incident = _create_incident(tmp_path, monkeypatch, text=f"incidencia {runtime_name}")
        app = _make_app()
        with _flag_on():
            with app.test_client() as client:
                with _patch_run_incident_deps(execution_id=888):
                    resp = client.post(
                        "/api/agents/run-incident",
                        json={"incident_id": incident["id"], "runtime": runtime_name},
                        headers={"X-User-Email": "test@test.com"},
                    )
        assert resp.status_code == 202, f"runtime {runtime_name} fue rechazado: {resp.get_json()}"


def test_broken_provider_still_launches_with_empty_catalog(tmp_path, monkeypatch):
    incident = _create_incident(tmp_path, monkeypatch)
    app = _make_app()

    def _raise_provider(*a, **kw):
        raise RuntimeError("tracker no configurado")

    with _flag_on():
        with app.test_client() as client:
            with patch("services.tracker_provider.get_tracker_provider", _raise_provider):
                with _patch_run_incident_deps(execution_id=999) as mock_run_agent:
                    resp = client.post(
                        "/api/agents/run-incident",
                        json={"incident_id": incident["id"], "runtime": "claude_code_cli"},
                        headers={"X-User-Email": "test@test.com"},
                    )
    assert resp.status_code == 202
    _, kwargs = mock_run_agent.call_args
    prompt = kwargs["context_blocks"][0]["content"]
    assert '(catálogo vacío → escribí exactamente "EPICA: ninguna")' in prompt


def test_c14_incident_pool_is_one_shot():
    from services.claude_code_cli_runner import _ONE_SHOT_ADO_IDS
    assert -8 in _ONE_SHOT_ADO_IDS
    assert -1 in _ONE_SHOT_ADO_IDS
