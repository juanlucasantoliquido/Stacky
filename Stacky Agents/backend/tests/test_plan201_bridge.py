"""Plan 201 F8 — Bridge al Centro de Despliegues.

Cierra el lazo compilar → desplegar: la carpeta de BITS del build (no el zip) se
registra como app desplegable, reusando la validación y el store del Plan 120.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

import api.devops_build_workshop as bw  # noqa: E402


@pytest.fixture(scope="module")
def client():
    from app import create_app

    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture(autouse=True)
def _entorno(tmp_path, monkeypatch):
    from config import config as cfg
    from services import deploy_store, solution_store

    monkeypatch.setattr(cfg, "STACKY_DEVOPS_BUILD_WORKSHOP_ENABLED", True, raising=False)
    monkeypatch.setattr(deploy_store, "_apps_path", lambda: tmp_path / "deploy_apps.json",
                        raising=True)
    monkeypatch.setattr(solution_store, "store_path",
                        lambda: tmp_path / "build_solutions.json", raising=True)
    monkeypatch.setattr(bw, "_active_workspace_root", lambda: tmp_path / "ws", raising=True)


@pytest.fixture
def bits(tmp_path, monkeypatch):
    """Un build exitoso con su carpeta de bits reales."""
    carpeta = tmp_path / "build_artifacts" / "mi-app" / "ts1" / "mi-app"
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / "App.dll").write_bytes(b"bits")
    monkeypatch.setattr(bw.solution_builder, "get_status",
                        lambda bid: {"status": "success", "mode": "single",
                                     "slugs": ["mi-app"], "log": [], "error": None,
                                     "artifact_ready": True, "summary": {}},
                        raising=True)
    monkeypatch.setattr(bw.solution_builder, "artifact_dir_for",
                        lambda bid, slug: carpeta if slug == "mi-app" else None,
                        raising=True)
    return carpeta


_TARGETS = {"__local__": {"install_path": "C:\\inetpub\\mi-app",
                          "smoke": {"kind": "none"}}}


def _post(client, **body):
    return client.post("/api/devops/build/register-deploy-app", json=body)


def test_register_requires_confirm(client, bits):
    r = _post(client, build_id="b1", slug="mi-app")

    assert r.status_code == 400
    assert r.get_json()["error"] == "confirm requerido"


def test_register_rejects_unfinished_build(client, monkeypatch):
    monkeypatch.setattr(bw.solution_builder, "get_status",
                        lambda bid: {"status": "running"}, raising=True)

    r = _post(client, build_id="b1", slug="mi-app", confirm=True)

    assert r.status_code == 400
    assert "éxito" in r.get_json()["error"]


def test_register_rejects_missing_artifact(client, monkeypatch):
    monkeypatch.setattr(bw.solution_builder, "get_status",
                        lambda bid: {"status": "success"}, raising=True)
    monkeypatch.setattr(bw.solution_builder, "artifact_dir_for", lambda bid, slug: None,
                        raising=True)

    r = _post(client, build_id="b1", slug="mi-app", confirm=True)

    assert r.status_code == 400
    assert "Artefacto" in r.get_json()["error"]


def test_register_sin_targets_pide_destino(client, bits):
    """`validate_app` exige destino: inventar un install_path sería copiar archivos
    a un lugar que el operador no eligió."""
    r = _post(client, build_id="b1", slug="mi-app", confirm=True)

    assert r.status_code == 400
    body = r.get_json()
    assert body["needs_targets"] is True
    assert "install_path" in body["error"]


def test_register_conserva_destinos_de_una_app_ya_registrada(client, bits):
    from services import deploy_store

    _post(client, build_id="b1", slug="mi-app", confirm=True, targets=_TARGETS)
    r = _post(client, build_id="b2", slug="mi-app", confirm=True)  # sin targets

    assert r.status_code == 200
    assert deploy_store.get_app("mi-app")["targets"] == _TARGETS


def test_register_creates_deploy_app_with_folder_artifact(client, bits):
    from services import deploy_store

    r = _post(client, build_id="b1", slug="mi-app", confirm=True, targets=_TARGETS)

    assert r.status_code == 200, r.get_json()
    app = r.get_json()["app"]
    assert app["id"] == "mi-app"
    assert app["artifact"]["kind"] == "folder"
    assert Path(app["artifact"]["path"]) == bits.resolve() or \
        os.path.abspath(str(bits)) == app["artifact"]["path"]
    assert "App.dll" in os.listdir(app["artifact"]["path"]), "son los bits, no el zip"

    guardada = deploy_store.get_app("mi-app")
    assert guardada is not None
    assert guardada["artifact"]["kind"] == "folder"


def test_register_is_idempotent_on_same_slug(client, bits):
    from services import deploy_store

    _post(client, build_id="b1", slug="mi-app", confirm=True, targets=_TARGETS)
    _post(client, build_id="b2", slug="mi-app", confirm=True, targets=_TARGETS)

    apps = [a for a in deploy_store.list_apps() if a["id"] == "mi-app"]
    assert len(apps) == 1, "upsert por id: no duplica"


def test_register_usa_friendly_name_del_catalogo(client, bits, monkeypatch):
    from services import solution_store

    monkeypatch.setattr(
        solution_store, "load_catalog",
        lambda ws: {"scanned_at": None, "truncated": False,
                    "solutions": [{"slug": "mi-app", "friendly_name": "Mi App Linda"}]},
        raising=True,
    )

    app = _post(client, build_id="b1", slug="mi-app", confirm=True,
                targets=_TARGETS).get_json()["app"]

    assert app["name"] == "Mi App Linda"


def test_slug_id_passes_deploy_planner_validation(bits):
    from services.deploy_planner import validate_app

    payload = {"id": "mi-app", "name": "Mi App",
               "artifact": {"kind": "folder", "path": os.path.abspath(str(bits))},
               "targets": _TARGETS}

    assert validate_app(payload) == [], "el slug y el artefacto pasan la validación del 120"


def test_targets_vacio_es_invalido_para_el_120():
    """Ancla del desvío: el contrato del Plan 120 NO acepta una app sin destinos."""
    from services.deploy_planner import validate_app

    errores = validate_app({"id": "mi-app", "name": "x",
                            "artifact": {"kind": "folder", "path": "C:\\bits"},
                            "targets": {}})

    assert any("targets" in e for e in errores)


def test_register_off_devuelve_404(client, bits, monkeypatch):
    from config import config as cfg

    monkeypatch.setattr(cfg, "STACKY_DEVOPS_BUILD_WORKSHOP_ENABLED", False, raising=False)

    assert _post(client, build_id="b1", slug="mi-app", confirm=True).status_code == 404
