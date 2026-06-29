"""Plan 72 F2 — Tests del endpoint POST /api/ci/<project>/trigger.

10 casos según el plan:
  1. Flag OFF → 404 (guard per-request).
  2. Flag ON + sin confirm → 400 "confirm=True requerido" [RIEL ABSOLUTO — VP-01].
  3. Flag ON + confirm=True + ref="develop" + scopes válidos → llama trigger_pipeline → 200.
  4. Flag ON + scopes conocidos inválidos → 400 con "api" en mensaje.
  5. [C3'] Flag ON + _read_pat_scopes=None → no bloquea → llama trigger_pipeline.
  6. Flag ON + ref vacío → 400 (ValueError).
  7. Idempotencia: 2do trigger con mismo (ref, sha) en ventana → reused, no llama provider.
  8. [C4'] provider lanza TrackerApiError(403) → 403 con kind.
  9. [C5'] _record_trigger + _recent_triggers funcional.
  10. [C6] provider.name="gitlab" → ItemRef(tracker_type="gitlab") pasado al mock.
"""
from __future__ import annotations

import time
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
    """Limpia los stores in-process antes de cada test."""
    import api.ci as ci_mod
    ci_mod._RECENT_TRIGGERS.clear()
    ci_mod._ACTIVE_POLLS.clear()
    yield
    ci_mod._RECENT_TRIGGERS.clear()
    ci_mod._ACTIVE_POLLS.clear()


def _mock_provider(tracker_type: str = "gitlab") -> MagicMock:
    mock = MagicMock()
    mock.name = tracker_type
    mock.trigger_pipeline.return_value = {
        "id": "42",
        "status": "created",
        "ref": "develop",
        "sha": "abc123",
        "web_url": "http://gitlab/p/42",
    }
    return mock


# ---------------------------------------------------------------------------
# Caso 1 — Flag OFF → 404
# ---------------------------------------------------------------------------
def test_trigger_flag_off_returns_404(client, monkeypatch):
    monkeypatch.setattr(config.config, "STACKY_PIPELINE_TRIGGER_ENABLED", False)
    resp = client.post("/api/ci/myproject/trigger", json={"confirm": True, "ref": "main"})
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Caso 2 — Flag ON + sin confirm → 400 [RIEL ABSOLUTO VP-01]
# ---------------------------------------------------------------------------
def test_trigger_no_confirm_returns_400(client, monkeypatch):
    monkeypatch.setattr(config.config, "STACKY_PIPELINE_TRIGGER_ENABLED", True)
    resp = client.post("/api/ci/myproject/trigger", json={"ref": "develop"})
    assert resp.status_code == 400
    data = resp.get_json()
    assert "confirm" in data["error"].lower()


def test_trigger_confirm_false_returns_400(client, monkeypatch):
    monkeypatch.setattr(config.config, "STACKY_PIPELINE_TRIGGER_ENABLED", True)
    resp = client.post("/api/ci/myproject/trigger", json={"confirm": False, "ref": "develop"})
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Caso 3 — Flag ON + confirm=True + scopes OK → llama trigger_pipeline → 200
# ---------------------------------------------------------------------------
def test_trigger_valid_calls_provider(client, monkeypatch):
    monkeypatch.setattr(config.config, "STACKY_PIPELINE_TRIGGER_ENABLED", True)
    mock_provider = _mock_provider("gitlab")

    with patch("api.ci.get_ci_provider", return_value=mock_provider), \
         patch("api.ci._read_pat_scopes", return_value=None):
        resp = client.post("/api/ci/myproject/trigger", json={
            "confirm": True,
            "ref": "develop",
            "sha": "newsha",
        })

    assert resp.status_code == 200
    mock_provider.trigger_pipeline.assert_called_once()
    data = resp.get_json()
    assert data["id"] == "42"


# ---------------------------------------------------------------------------
# Caso 4 — scopes conocidos inválidos → 400 con "api"
# ---------------------------------------------------------------------------
def test_trigger_invalid_scopes_returns_400(client, monkeypatch):
    monkeypatch.setattr(config.config, "STACKY_PIPELINE_TRIGGER_ENABLED", True)
    mock_provider = _mock_provider("gitlab")

    with patch("api.ci.get_ci_provider", return_value=mock_provider), \
         patch("api.ci._read_pat_scopes", return_value={"read_api"}):
        resp = client.post("/api/ci/myproject/trigger", json={
            "confirm": True,
            "ref": "develop",
        })

    assert resp.status_code == 400
    data = resp.get_json()
    assert "api" in data["error"]


# ---------------------------------------------------------------------------
# Caso 5 — [C3'] scopes=None → no bloquea → llama trigger_pipeline
# ---------------------------------------------------------------------------
def test_trigger_none_scopes_not_blocking(client, monkeypatch):
    monkeypatch.setattr(config.config, "STACKY_PIPELINE_TRIGGER_ENABLED", True)
    mock_provider = _mock_provider("gitlab")

    with patch("api.ci.get_ci_provider", return_value=mock_provider), \
         patch("api.ci._read_pat_scopes", return_value=None):
        resp = client.post("/api/ci/myproject/trigger", json={
            "confirm": True,
            "ref": "develop",
            "sha": "sha-for-none-test",
        })

    assert resp.status_code == 200
    mock_provider.trigger_pipeline.assert_called_once()


# ---------------------------------------------------------------------------
# Caso 6 — ref vacío → 400 (ValueError)
# ---------------------------------------------------------------------------
def test_trigger_empty_ref_returns_400(client, monkeypatch):
    monkeypatch.setattr(config.config, "STACKY_PIPELINE_TRIGGER_ENABLED", True)
    mock_provider = _mock_provider()
    with patch("api.ci.get_ci_provider", return_value=mock_provider):
        resp = client.post("/api/ci/myproject/trigger", json={"confirm": True, "ref": ""})
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Caso 7 — Idempotencia: 2do trigger mismo (ref, sha) → reused, no llama provider
# ---------------------------------------------------------------------------
def test_trigger_idempotency_reuses_pipeline(client, monkeypatch):
    monkeypatch.setattr(config.config, "STACKY_PIPELINE_TRIGGER_ENABLED", True)
    mock_provider = _mock_provider("gitlab")

    with patch("api.ci.get_ci_provider", return_value=mock_provider), \
         patch("api.ci._read_pat_scopes", return_value=None):
        # 1er trigger — dispara
        r1 = client.post("/api/ci/myproject/trigger", json={
            "confirm": True, "ref": "develop", "sha": "idm-sha",
        })
        assert r1.status_code == 200
        assert r1.get_json().get("status") != "reused"
        mock_provider.trigger_pipeline.assert_called_once()

        mock_provider.trigger_pipeline.reset_mock()

        # 2do trigger con mismo (ref, sha) en ventana → reused
        r2 = client.post("/api/ci/myproject/trigger", json={
            "confirm": True, "ref": "develop", "sha": "idm-sha",
        })
        assert r2.status_code == 200
        data2 = r2.get_json()
        assert data2["status"] == "reused"
        mock_provider.trigger_pipeline.assert_not_called()


# ---------------------------------------------------------------------------
# Caso 8 — [C4'] TrackerApiError(403) → 403 con kind
# ---------------------------------------------------------------------------
def test_trigger_tracker_api_error_403(client, monkeypatch):
    from services.tracker_provider import TrackerApiError
    monkeypatch.setattr(config.config, "STACKY_PIPELINE_TRIGGER_ENABLED", True)
    mock_provider = _mock_provider("gitlab")
    mock_provider.trigger_pipeline.side_effect = TrackerApiError(403, "forbidden", kind="forbidden")

    with patch("api.ci.get_ci_provider", return_value=mock_provider), \
         patch("api.ci._read_pat_scopes", return_value=None):
        resp = client.post("/api/ci/myproject/trigger", json={
            "confirm": True, "ref": "main", "sha": "err-sha",
        })

    assert resp.status_code == 403
    data = resp.get_json()
    assert data["kind"] == "forbidden"


# ---------------------------------------------------------------------------
# Caso 9 — [C5'] _record_trigger + _recent_triggers funcional
# ---------------------------------------------------------------------------
def test_record_and_recent_triggers():
    import api.ci as ci_mod
    ci_mod._record_trigger("gitlab", "develop", "sha1", "42")
    entries = ci_mod._recent_triggers("gitlab", "develop")
    assert len(entries) == 1
    assert entries[0]["pipeline_id"] == "42"


# ---------------------------------------------------------------------------
# Caso 10 — [C6] provider.name="gitlab" → ItemRef(tracker_type="gitlab")
# ---------------------------------------------------------------------------
def test_trigger_uses_provider_name_for_item_ref(client, monkeypatch):
    from services.ci_provider import ItemRef
    monkeypatch.setattr(config.config, "STACKY_PIPELINE_TRIGGER_ENABLED", True)
    mock_provider = _mock_provider("gitlab")

    captured_item_ref = {}

    def capture_trigger(item_ref, ref):
        captured_item_ref["item_ref"] = item_ref
        return {"id": "7", "status": "created", "ref": ref, "sha": "x", "web_url": ""}

    mock_provider.trigger_pipeline.side_effect = capture_trigger

    with patch("api.ci.get_ci_provider", return_value=mock_provider), \
         patch("api.ci._read_pat_scopes", return_value=None):
        resp = client.post("/api/ci/myproject/trigger", json={
            "confirm": True, "ref": "develop", "sha": "sha-c6",
        })

    assert resp.status_code == 200
    assert captured_item_ref["item_ref"].tracker_type == "gitlab"
