"""Plan 248 F5 — blueprint, flag y cableado de health. 7 tests."""
from __future__ import annotations

from pathlib import Path

import pytest

GOLDEN = Path(__file__).resolve().parent / "fixtures" / "cicd_nl" / "golden"


@pytest.fixture
def app():
    from app import create_app

    application = create_app()
    application.config["TESTING"] = True
    return application


@pytest.fixture(autouse=True)
def _flag_on_y_data_dir_aislado(tmp_path, monkeypatch):
    import config as cfg
    import runtime_paths

    monkeypatch.setattr(cfg.config, "STACKY_PIPELINE_AUDIT_ENABLED", True, raising=False)
    monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)
    yield


def test_scan_devuelve_report(app):
    crudo = (GOLDEN / "cd-deploy-test.yml").read_text(encoding="utf-8")
    resp = app.test_client().post("/api/pipeline-audit/scan",
                                  json={"yaml": crudo, "provider": "ado"})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    codigos = sorted({f["code"] for f in body["findings"]})
    assert codigos == ["OPT003", "OPT004", "SEC005"]


def test_flag_off_da_404(app, monkeypatch):
    import config as cfg

    monkeypatch.setattr(cfg.config, "STACKY_PIPELINE_AUDIT_ENABLED", False, raising=False)
    client = app.test_client()
    assert client.post("/api/pipeline-audit/scan", json={"yaml": "a: 1"}).status_code == 404
    assert client.get("/api/pipeline-audit/suppressions").status_code == 404
    assert client.post("/api/pipeline-audit/suppress", json={}).status_code == 404
    assert client.delete("/api/pipeline-audit/suppress", json={}).status_code == 404


def test_suppress_sin_reason_da_400(app):
    resp = app.test_client().post("/api/pipeline-audit/suppress", json={
        "pipeline_key": "p1", "code": "SEC006", "location": "steps[1]", "reason": ""})
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "supresion_invalida"


def test_suppress_y_scan_devuelve_suprimido(app):
    crudo = (GOLDEN / "security-scan-online.yml").read_text(encoding="utf-8")
    client = app.test_client()
    primero = client.post("/api/pipeline-audit/scan",
                          json={"yaml": crudo, "provider": "ado", "pipeline_key": "p1"}).get_json()
    sec006 = [f for f in primero["findings"] if f["code"] == "SEC006"][0]

    creado = client.post("/api/pipeline-audit/suppress", json={
        "pipeline_key": "p1", "code": sec006["code"], "location": sec006["location"],
        "evidence_fingerprint": sec006["evidence_fingerprint"],
        "reason": "el script hace el gate por dentro"})
    assert creado.status_code == 201

    listado = client.get("/api/pipeline-audit/suppressions?pipeline_key=p1").get_json()
    assert len(listado["items"]) == 1

    segundo = client.post("/api/pipeline-audit/scan",
                          json={"yaml": crudo, "provider": "ado", "pipeline_key": "p1"}).get_json()
    assert "SEC006" not in {f["code"] for f in segundo["findings"]}
    assert "SEC006" in {f["code"] for f in segundo["suppressed"]}

    borrado = client.delete("/api/pipeline-audit/suppress", json={
        "pipeline_key": "p1", "code": "SEC006", "location": sec006["location"]})
    assert borrado.get_json()["removed"] is True


def test_yaml_faltante_da_400(app):
    resp = app.test_client().post("/api/pipeline-audit/scan", json={"provider": "ado"})
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "yaml_requerido"


def test_provider_invalido_da_400(app):
    resp = app.test_client().post("/api/pipeline-audit/scan",
                                  json={"yaml": "a: 1", "provider": "jenkins"})
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "provider_no_soportado"


def test_health_expone_la_flag(app, monkeypatch):
    import config as cfg

    body = app.test_client().get("/api/devops/health").get_json()
    assert body["pipeline_audit_enabled"] is True
    monkeypatch.setattr(cfg.config, "STACKY_PIPELINE_AUDIT_ENABLED", False, raising=False)
    body2 = app.test_client().get("/api/devops/health").get_json()
    assert body2["pipeline_audit_enabled"] is False
