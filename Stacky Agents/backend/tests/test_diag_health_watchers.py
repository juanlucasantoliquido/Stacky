import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # backend/ (C4: redundante con conftest.py, ver test_completion_preflight.py)

import app as app_module

def _client(monkeypatch):
    flask_app = app_module.create_app()
    flask_app.config.update(TESTING=True)
    return flask_app.test_client()

def test_health_reports_watchers_active_fields(monkeypatch):
    monkeypatch.setattr("project_manager.get_active_project", lambda: None)
    client = _client(monkeypatch)
    resp = client.get("/api/diag/health")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "watchers_active" in data
    assert data["watchers_active"] is False
    assert data["watchers_inactive_reason"] == "sin_proyecto_activo"
