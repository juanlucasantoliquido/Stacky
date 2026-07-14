"""tests/test_plan131_incident_api.py — Plan 131 F1.

Endpoints multipart de intake: POST/GET /api/incidents, GET /<id>,
GET /<id>/files/<stored_name>. CERO llamadas reales a ADO (no aplica en F1:
estos endpoints son persistencia local pura).
"""
import io

import pytest

import runtime_paths


@pytest.fixture
def app_on(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)
    import config as cfg
    original = getattr(cfg.config, "STACKY_INCIDENT_RESOLVER_ENABLED", False)
    cfg.config.STACKY_INCIDENT_RESOLVER_ENABLED = True
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    yield app
    cfg.config.STACKY_INCIDENT_RESOLVER_ENABLED = original


@pytest.fixture
def app_off(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)
    import config as cfg
    original = getattr(cfg.config, "STACKY_INCIDENT_RESOLVER_ENABLED", False)
    cfg.config.STACKY_INCIDENT_RESOLVER_ENABLED = False
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    yield app
    cfg.config.STACKY_INCIDENT_RESOLVER_ENABLED = original


def test_post_multipart_happy(app_on):
    client = app_on.test_client()
    resp = client.post(
        "/api/incidents",
        data={
            "text": "la pantalla se rompe",
            "files": (io.BytesIO(b"fake png bytes"), "captura.png"),
        },
        content_type="multipart/form-data",
    )
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["ok"] is True
    assert body["incident"]["text"] == "la pantalla se rompe"
    assert len(body["incident"]["files"]) == 1


def test_post_flag_off_404(app_off):
    client = app_off.test_client()
    resp = client.post(
        "/api/incidents",
        data={"text": "x"},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 404
    assert resp.get_json()["ok"] is False


def test_post_ext_not_allowed_400(app_on):
    client = app_on.test_client()
    resp = client.post(
        "/api/incidents",
        data={
            "text": "x",
            "files": (io.BytesIO(b"MZ"), "virus.exe"),
        },
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["error"] == "validation_error"
    assert "ext_not_allowed" in body["message"]


def test_get_file_happy_and_traversal(app_on):
    client = app_on.test_client()
    create_resp = client.post(
        "/api/incidents",
        data={
            "text": "x",
            "files": (io.BytesIO(b"exact-bytes-here"), "captura.png"),
        },
        content_type="multipart/form-data",
    )
    incident_id = create_resp.get_json()["incident"]["id"]

    ok_resp = client.get(f"/api/incidents/{incident_id}/files/captura.png")
    assert ok_resp.status_code == 200
    assert ok_resp.data == b"exact-bytes-here"

    traversal_resp = client.get(f"/api/incidents/{incident_id}/files/..%5C..%5Cintake.json")
    assert traversal_resp.status_code == 404


def test_get_incident_not_found_404(app_on):
    client = app_on.test_client()
    resp = client.get("/api/incidents/inc_does_not_exist")
    assert resp.status_code == 404
    assert resp.get_json()["error"] == "not_found"


def test_list_incidents_endpoint(app_on):
    client = app_on.test_client()
    client.post(
        "/api/incidents",
        data={"text": "primera incidencia"},
        content_type="multipart/form-data",
    )
    resp = client.get("/api/incidents")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert len(body["incidents"]) == 1


def test_list_incidents_flag_off_404(app_off):
    client = app_off.test_client()
    resp = client.get("/api/incidents")
    assert resp.status_code == 404


def test_post_content_length_too_big_413_creates_nothing(app_on):
    client = app_on.test_client()
    resp = client.post(
        "/api/incidents",
        data={"text": "x"},
        content_type="multipart/form-data",
        environ_overrides={"CONTENT_LENGTH": str(26 * 1024 * 1024 + 2_000_000)},
    )
    assert resp.status_code == 413

    list_resp = client.get("/api/incidents")
    assert list_resp.get_json()["incidents"] == []
