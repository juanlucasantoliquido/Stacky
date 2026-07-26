"""Plan 174 F0/F5 — Las 3 flags de rendimiento percibido, end-to-end.

Ver Stacky Agents/docs/174_PLAN_RENDIMIENTO_PERCIBIDO_VIRTUALIZACION_PREFETCH_Y_NAVEGACION_INSTANTANEA.md

Una flag que existe en el registro pero no llega al health es una flag que el
frontend nunca va a poder leer: el operador la apaga por UI y no pasa nada. Por
eso el test recorre las tres capas.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

_FLAGS = {
    "STACKY_UI_VIRTUALIZATION_ENABLED": "ui_virtualization_enabled",
    "STACKY_UI_PREFETCH_ENABLED": "ui_prefetch_enabled",
    "STACKY_UI_INSTANT_NAV_ENABLED": "ui_instant_nav_enabled",
}


def test_las_tres_estan_en_el_registro():
    from services import harness_flags

    conocidas = {f.key for f in harness_flags.FLAG_REGISTRY}

    assert set(_FLAGS).issubset(conocidas), sorted(set(_FLAGS) - conocidas)


def test_default_on():
    # Son solo UX y no queman tokens: ninguna de las 4 excepciones duras aplica.
    import config as config_mod

    for key in _FLAGS:
        assert getattr(config_mod.config, key) is True, key


def test_declaradas_bool_con_default_true():
    from services import harness_flags

    por_key = {f.key: f for f in harness_flags.FLAG_REGISTRY}
    for key in _FLAGS:
        assert por_key[key].type == "bool", key
        assert por_key[key].default is True, key


def test_el_health_de_la_ruta_trae_los_3_campos(monkeypatch):
    monkeypatch.setenv("STACKY_REAPER_ENABLED", "false")
    monkeypatch.setenv("STACKY_MANIFEST_WATCHER_ENABLED", "false")

    from app import create_app
    from services.manifest_watcher import stop_manifest_watcher
    from services.ticket_status import stop_stale_recovery

    app = create_app()
    app.config.update(TESTING=True)
    stop_stale_recovery()
    stop_manifest_watcher()
    try:
        with app.test_client() as c:
            cuerpo = c.get("/api/diag/health").get_json()
    finally:
        stop_stale_recovery()
        stop_manifest_watcher()

    for campo in _FLAGS.values():
        assert campo in cuerpo, campo
        assert cuerpo[campo] is True, campo
