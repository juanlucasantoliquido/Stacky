"""Plan 246 F4 — endpoint /api/pipeline-inventory/list, flag y health key. 10 tests."""
from __future__ import annotations

import ast
from pathlib import Path

import pytest


@pytest.fixture
def app():
    from app import create_app

    application = create_app()
    application.config["TESTING"] = True
    return application


@pytest.fixture(autouse=True)
def _flag_on(monkeypatch):
    import config as cfg

    monkeypatch.setattr(cfg.config, "STACKY_PIPELINE_INVENTORY_ENABLED", True, raising=False)
    yield


def _flag_off(monkeypatch):
    import config as cfg

    monkeypatch.setattr(cfg.config, "STACKY_PIPELINE_INVENTORY_ENABLED", False, raising=False)


def test_flag_off_da_404(app, monkeypatch):
    _flag_off(monkeypatch)
    assert app.test_client().get("/api/pipeline-inventory/list").status_code == 404


def test_flag_on_da_200_con_el_shape(app):
    resp = app.test_client().get("/api/pipeline-inventory/list")
    assert resp.status_code == 200
    body = resp.get_json()
    assert set(body) == {
        "ok", "generated_at", "cached", "cache_age_sec", "project",
        "counts", "sources", "pipelines",
    }


def test_endpoint_siempre_200_aunque_todo_falle(app, monkeypatch):
    import api.pipeline_inventory as mod

    degradado = {
        "ok": True, "generated_at": "2026-07-26T00:00:00+00:00", "cached": False,
        "cache_age_sec": 0, "project": "", "counts": {"total": 0},
        "sources": [], "pipelines": [],
    }
    monkeypatch.setattr(mod, "build_inventory", lambda project, refresh=False: degradado)
    resp = app.test_client().get("/api/pipeline-inventory/list")
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True


def test_endpoint_pasa_refresh(app, monkeypatch):
    import api.pipeline_inventory as mod

    visto: dict = {}

    def _spy(project, refresh=False):
        visto["project"] = project
        visto["refresh"] = refresh
        return {"ok": True}

    monkeypatch.setattr(mod, "build_inventory", _spy)
    app.test_client().get("/api/pipeline-inventory/list?refresh=1")
    assert visto["refresh"] is True
    app.test_client().get("/api/pipeline-inventory/list")
    assert visto["refresh"] is False


def test_endpoint_pasa_project(app, monkeypatch):
    import api.pipeline_inventory as mod

    visto: dict = {}

    def _spy(project, refresh=False):
        visto["project"] = project
        return {"ok": True}

    monkeypatch.setattr(mod, "build_inventory", _spy)
    app.test_client().get("/api/pipeline-inventory/list?project=RSPACIFICO")
    assert visto["project"] == "RSPACIFICO"
    app.test_client().get("/api/pipeline-inventory/list")
    assert visto["project"] is None


@pytest.mark.parametrize("verbo", ["post", "put", "patch", "delete"])
def test_endpoint_no_expone_verbos_de_escritura(app, verbo):
    client = app.test_client()
    resp = getattr(client, verbo)("/api/pipeline-inventory/list")
    assert resp.status_code == 405


def test_health_expone_pipeline_inventory_enabled(app):
    body = app.test_client().get("/api/devops/health").get_json()
    assert "pipeline_inventory_enabled" in body
    assert isinstance(body["pipeline_inventory_enabled"], bool)


def test_health_refleja_la_flag_off(app, monkeypatch):
    _flag_off(monkeypatch)
    body = app.test_client().get("/api/devops/health").get_json()
    assert body["pipeline_inventory_enabled"] is False


def test_bootstrap_y_health_siguen_en_paridad(app, monkeypatch):
    import config as cfg

    monkeypatch.setattr(cfg.config, "STACKY_DEVOPS_BOOTSTRAP_ENABLED", True, raising=False)
    client = app.test_client()
    health = client.get("/api/devops/health").get_json()
    # /bootstrap exige `project` (api/devops.py) y reusa el MISMO _health_payload.
    bootstrap = client.get("/api/devops/bootstrap?project=RSPACIFICO").get_json()
    plano = bootstrap.get("health", bootstrap)
    assert plano["pipeline_inventory_enabled"] == health["pipeline_inventory_enabled"]


def test_endpoint_no_lee_current_user():
    ruta = Path(__file__).resolve().parent.parent / "api" / "pipeline_inventory.py"
    fuente = ruta.read_text(encoding="utf-8")
    assert "current_user" not in fuente
    ast.parse(fuente)  # y sigue siendo Python valido
