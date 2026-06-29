"""Plan 72 F5 — Tests del endpoint GET /api/ci/<project>/pipeline/<id>.

6 casos:
  1. Flag ON → llama provider.monitor_pipeline; response con status, web_url, tracker_type.
  2. Flag OFF → 404.
  3. AdoCIProvider.monitor_pipeline lanza NotImplementedError → 501.
  4. provider.monitor_pipeline lanza TrackerApiError(404) → 404 con mensaje.
  5. [C4] Cap: _ACTIVE_POLLS["42"]=5 → 429; con 0 → 200.
  6. [C4] Tras request 200, _ACTIVE_POLLS["<id>"] vuelve a 0 (finally decrementa).
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import config


@pytest.fixture()
def app():
    from app import create_app
    _app = create_app()
    _app.config["TESTING"] = True
    return _app


@pytest.fixture()
def client(app):
    with app.test_client() as c:
        yield c


@pytest.fixture(autouse=True)
def _reset_stores():
    import api.ci as ci_mod
    ci_mod._RECENT_TRIGGERS.clear()
    ci_mod._ACTIVE_POLLS.clear()
    yield
    ci_mod._RECENT_TRIGGERS.clear()
    ci_mod._ACTIVE_POLLS.clear()


def _make_provider(tracker_type: str = "gitlab") -> MagicMock:
    mock = MagicMock()
    mock.name = tracker_type
    mock.monitor_pipeline.return_value = {
        "id": "99",
        "status": "running",
        "ref": "develop",
        "sha": "abc",
        "web_url": "http://gitlab/pipelines/99",
    }
    return mock


# ---------------------------------------------------------------------------
# Caso 1 — Flag ON → llama monitor_pipeline → response con tracker_type
# ---------------------------------------------------------------------------
def test_monitor_flag_on_returns_status(client, monkeypatch):
    monkeypatch.setattr(config.config, "STACKY_PIPELINE_TRIGGER_ENABLED", True)
    mock_provider = _make_provider("gitlab")

    with patch("api.ci.get_ci_provider", return_value=mock_provider):
        resp = client.get("/api/ci/myproject/pipeline/99")

    assert resp.status_code == 200
    mock_provider.monitor_pipeline.assert_called_once_with("99")
    data = resp.get_json()
    assert data["status"] == "running"
    assert data["web_url"] == "http://gitlab/pipelines/99"
    assert data["tracker_type"] == "gitlab"
    assert data["source"] == "ci"


# ---------------------------------------------------------------------------
# Caso 2 — Flag OFF → 404
# ---------------------------------------------------------------------------
def test_monitor_flag_off_returns_404(client, monkeypatch):
    monkeypatch.setattr(config.config, "STACKY_PIPELINE_TRIGGER_ENABLED", False)
    resp = client.get("/api/ci/myproject/pipeline/99")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Caso 3 — ADO monitor → NotImplementedError → 501
# ---------------------------------------------------------------------------
def test_monitor_ado_not_implemented_returns_501(client, monkeypatch):
    monkeypatch.setattr(config.config, "STACKY_PIPELINE_TRIGGER_ENABLED", True)
    mock_provider = _make_provider("azure_devops")
    mock_provider.monitor_pipeline.side_effect = NotImplementedError("ADO fuera de scope v1")

    with patch("api.ci.get_ci_provider", return_value=mock_provider):
        resp = client.get("/api/ci/adoproject/pipeline/55")

    assert resp.status_code == 501
    data = resp.get_json()
    assert "v1" in data["error"] or "ADO" in data["error"]


# ---------------------------------------------------------------------------
# Caso 4 — TrackerApiError(404) → 404
# ---------------------------------------------------------------------------
def test_monitor_tracker_error_returns_status(client, monkeypatch):
    from services.tracker_provider import TrackerApiError
    monkeypatch.setattr(config.config, "STACKY_PIPELINE_TRIGGER_ENABLED", True)
    mock_provider = _make_provider("gitlab")
    mock_provider.monitor_pipeline.side_effect = TrackerApiError(404, "no existe pipeline", kind="not_found")

    with patch("api.ci.get_ci_provider", return_value=mock_provider):
        resp = client.get("/api/ci/myproject/pipeline/999")

    assert resp.status_code == 404
    data = resp.get_json()
    assert "pipeline" in data["error"].lower() or data["error"]


# ---------------------------------------------------------------------------
# Caso 5 — [C4] Cap concurrencia: polls>=5 → 429; polls=0 → 200
# ---------------------------------------------------------------------------
def test_monitor_cap_returns_429_when_at_limit(client, monkeypatch):
    import api.ci as ci_mod
    monkeypatch.setattr(config.config, "STACKY_PIPELINE_TRIGGER_ENABLED", True)
    mock_provider = _make_provider("gitlab")

    # Pre-sembrar cap al máximo
    ci_mod._ACTIVE_POLLS["42"] = ci_mod._MAX_ACTIVE_POLLS_PER_PIPELINE

    with patch("api.ci.get_ci_provider", return_value=mock_provider):
        resp = client.get("/api/ci/myproject/pipeline/42")

    assert resp.status_code == 429
    mock_provider.monitor_pipeline.assert_not_called()


def test_monitor_cap_ok_when_below_limit(client, monkeypatch):
    import api.ci as ci_mod
    monkeypatch.setattr(config.config, "STACKY_PIPELINE_TRIGGER_ENABLED", True)
    mock_provider = _make_provider("gitlab")

    # Asegurar que no hay cap
    ci_mod._ACTIVE_POLLS.pop("43", None)

    with patch("api.ci.get_ci_provider", return_value=mock_provider):
        resp = client.get("/api/ci/myproject/pipeline/43")

    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Caso 6 — [C4] Tras request 200, _ACTIVE_POLLS vuelve a 0
# ---------------------------------------------------------------------------
def test_monitor_finally_decrements_active_polls(client, monkeypatch):
    import api.ci as ci_mod
    monkeypatch.setattr(config.config, "STACKY_PIPELINE_TRIGGER_ENABLED", True)
    mock_provider = _make_provider("gitlab")

    ci_mod._ACTIVE_POLLS.pop("44", None)

    with patch("api.ci.get_ci_provider", return_value=mock_provider):
        resp = client.get("/api/ci/myproject/pipeline/44")

    assert resp.status_code == 200
    assert ci_mod._ACTIVE_POLLS.get("44", 0) == 0
