"""tests/test_plan218_parity_endpoint.py -- Plan 218 F8.

Rollout por capacidad + endpoint de solo lectura de la matriz de paridad.
Con la flag maestra apagada, TODA la superficie del 218 desaparece: ese es el
rollback completo del plan en un click.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import config as config_module  # noqa: E402

from services.provider_capabilities import CAPABILITY_KEYS  # noqa: E402


@pytest.fixture
def client():
    from app import create_app

    app = create_app()
    app.config.update(TESTING=True)
    with app.test_client() as c:
        yield c


class _Ctx:
    stacky_project_name = "RSPACIFICO"
    tracker_type = "gitlab"
    tracker_project = "grupo/repo"
    organization = None
    base_url = None
    tracker_group = None
    workspace_root = None
    auth_path = None
    vscode_port = None


def _con_proyecto(overrides=None):
    cfg = {"name": "RSPACIFICO", "issue_tracker": {"type": "gitlab", "project": "grupo/repo"}}
    if overrides is not None:
        cfg["issue_tracker"]["parity_overrides"] = overrides
    return (
        patch("services.project_context.resolve_project_context", return_value=_Ctx()),
        patch("services.project_context._config_for_project_name", return_value=cfg),
    )


def test_matrix_devuelve_todas_las_capacidades(client, monkeypatch):
    monkeypatch.setattr(config_module.config, "STACKY_PROVIDER_PARITY_ENABLED", True)
    p1, p2 = _con_proyecto()
    with p1, p2:
        resp = client.get("/api/parity/matrix?project=RSPACIFICO")

    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert len(body["capabilities"]) == len(CAPABILITY_KEYS)
    assert body["provider"] == "gitlab"
    claves = {c["key"] for c in body["capabilities"]}
    assert claves == set(CAPABILITY_KEYS)


def test_override_por_proyecto_apaga_una_capacidad(client, monkeypatch):
    monkeypatch.setattr(config_module.config, "STACKY_PROVIDER_PARITY_ENABLED", True)
    p1, p2 = _con_proyecto({"mr.approve": False})
    with p1, p2:
        resp = client.get("/api/parity/matrix?project=RSPACIFICO")

    body = resp.get_json()
    entrada = next(c for c in body["capabilities"] if c["key"] == "mr.approve")
    assert entrada["status"] == "full", "en GitLab mr.approve está implementado"
    assert entrada["enabled"] is False, "el override por proyecto debe poder apagarla"


def test_flag_maestra_off_capability_enabled_es_true_para_todo(monkeypatch):
    """Llama a parity_rollout.capability_enabled() DIRECTO, no al endpoint.

    Con la maestra apagada el comportamiento es el de antes del plan: nadie consulta
    la matriz, así que todo se considera disponible.
    """
    from services.parity_rollout import capability_enabled

    monkeypatch.setattr(config_module.config, "STACKY_PROVIDER_PARITY_ENABLED", False)
    for key in ("mr.approve", "tracker.sync.full", "ci.artifacts.list"):
        assert capability_enabled(key, project="RSPACIFICO") is True


def test_flag_maestra_off_el_endpoint_no_existe(client, monkeypatch):
    """Rollback completo del 218: la superficie desaparece."""
    monkeypatch.setattr(config_module.config, "STACKY_PROVIDER_PARITY_ENABLED", False)
    resp = client.get("/api/parity/matrix")
    assert resp.status_code == 404


def test_endpoint_es_solo_lectura(client, monkeypatch):
    monkeypatch.setattr(config_module.config, "STACKY_PROVIDER_PARITY_ENABLED", True)
    resp = client.post("/api/parity/matrix")
    assert resp.status_code == 405


def test_ruta_registrada_sin_doble_prefijo(client):
    """R6: los planes 72, 73 y 74 fueron rechazados por el doble prefijo /api/api/...

    El alcance es el blueprint de ESTE plan. (El barrido encontró UNA ruta con doble
    prefijo preexistente —`/api/api/projects/<project_name>/tasks`— ajena al 218:
    queda reportada como hallazgo, no se toca acá.)
    """
    from app import create_app

    reglas = {str(r) for r in create_app().url_map.iter_rules()}
    assert "/api/parity/matrix" in reglas
    dobles_de_paridad = [r for r in reglas if r.startswith("/api/api/") and "parity" in r]
    assert dobles_de_paridad == [], dobles_de_paridad


def test_no_filtra_secretos(client, monkeypatch):
    """La respuesta expone SOLO la forma declarada — ni credenciales ni campos extra.

    Un centinela por substring no sirve: la clave `identity.token.scopes` es una
    capacidad legítima del registro congelado. Lo que se verifica es (a) la forma
    exacta del payload y (b) que no aparezca material con pinta de credencial.
    """
    import re

    monkeypatch.setattr(config_module.config, "STACKY_PROVIDER_PARITY_ENABLED", True)
    p1, p2 = _con_proyecto()
    with p1, p2:
        resp = client.get("/api/parity/matrix?project=RSPACIFICO")

    body = resp.get_json()
    assert set(body) == {"provider", "project", "parity_enabled", "capabilities"}
    for entrada in body["capabilities"]:
        assert set(entrada) == {"key", "status", "enabled", "loss", "owner_plan"}

    crudo = resp.get_data(as_text=True)
    for cabecera in ("PRIVATE-TOKEN", "Authorization", "Basic ", "Bearer "):
        assert cabecera not in crudo, f"la respuesta filtra {cabecera!r}"
    sospechosos = [t for t in re.findall(r"\b[A-Za-z0-9_-]{24,}\b", crudo) if not t.isalpha()]
    assert sospechosos == [], f"la respuesta trae algo con pinta de credencial: {sospechosos}"
