"""Plan 247 F4 — POST /api/pipeline-profiler/profile: flag, degradación y contratos. 9 casos."""
from __future__ import annotations

import json
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
def _flag_on(monkeypatch):
    import config as cfg

    monkeypatch.setattr(cfg.config, "STACKY_PIPELINE_PROFILER_ENABLED", True, raising=False)
    yield


def _post(app, body):
    return app.test_client().post("/api/pipeline-profiler/profile", json=body)


def test_flag_off_devuelve_404(app, monkeypatch):
    import config as cfg

    monkeypatch.setattr(cfg.config, "STACKY_PIPELINE_PROFILER_ENABLED", False, raising=False)
    assert _post(app, {"yaml_text": "a: 1"}).status_code == 404


def test_yaml_text_perfila_ok(app):
    texto = (GOLDEN / "agendaweb-ci.yml").read_text(encoding="utf-8")
    resp = _post(app, {"yaml_text": texto})
    assert resp.status_code == 200
    assert resp.get_json()["stack"]["value"] == ["dotnet_framework"]


def test_sin_yaml_ni_id_devuelve_400(app):
    resp = _post(app, {})
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "yaml_text_requerido"


def test_yaml_vacio_devuelve_400(app):
    assert _post(app, {"yaml_text": "   "}).status_code == 400


def test_provider_gitlab_devuelve_400(app):
    resp = _post(app, {"yaml_text": "a: 1", "provider": "gitlab"})
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "provider_no_soportado"


def test_pipeline_id_sin_inventario_devuelve_501(app, monkeypatch):
    """Degradación explícita ante el plan 246: si el resolutor no existe, 501 accionable."""
    import builtins

    real_import = builtins.__import__

    def _fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "services.pipeline_inventory" and "get_pipeline_yaml" in (fromlist or ()):
            raise ImportError("get_pipeline_yaml no existe")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _fake_import)
    resp = _post(app, {"pipeline_id": "x"})
    assert resp.status_code == 501
    assert resp.get_json()["error"] == "inventory_unavailable"


def test_yaml_roto_devuelve_200_con_parse_error(app):
    resp = _post(app, {"yaml_text": "a: [\n"})
    assert resp.status_code == 200
    assert resp.get_json()["parse_error"]


def test_default_no_narra_con_llm(app):
    texto = (GOLDEN / "ci-batch.yml").read_text(encoding="utf-8")
    resp = _post(app, {"yaml_text": texto})
    assert resp.get_json()["purpose_source"] == "plantilla"


def test_respuesta_es_json_serializable(app):
    texto = (GOLDEN / "cd-deploy-test.yml").read_text(encoding="utf-8")
    body = _post(app, {"yaml_text": texto}).get_json()
    json.loads(json.dumps(body))
