"""tests/test_plan237_plans_triage_endpoint.py — Plan 237 F4: /api/evolution/plans."""
import pathlib
import re

import pytest


@pytest.fixture
def client():
    import config as cfg
    prev_center = getattr(cfg.config, "STACKY_EVOLUTION_CENTER_ENABLED", True)
    prev_triage = getattr(cfg.config, "STACKY_EVOLUTION_PLANS_TRIAGE_ENABLED", True)
    cfg.config.STACKY_EVOLUTION_CENTER_ENABLED = True
    cfg.config.STACKY_EVOLUTION_PLANS_TRIAGE_ENABLED = True
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    yield app.test_client()
    cfg.config.STACKY_EVOLUTION_CENTER_ENABLED = prev_center
    cfg.config.STACKY_EVOLUTION_PLANS_TRIAGE_ENABLED = prev_triage


def test_flag_de_la_seccion_default_on():
    from services.harness_flags import FLAG_REGISTRY
    spec = next(s for s in FLAG_REGISTRY if s.key == "STACKY_EVOLUTION_PLANS_TRIAGE_ENABLED")
    assert spec.default is True
    assert spec.requires == "STACKY_EVOLUTION_CENTER_ENABLED"


def test_flag_de_la_seccion_esta_categorizada():
    """C2: sin entrada en _CATEGORY_KEYS, dos meta-tests del arnés se ponen rojos."""
    from services.harness_flags import _CATEGORY_KEYS
    todas = {k for keys in _CATEGORY_KEYS.values() for k in keys}
    assert "STACKY_EVOLUTION_PLANS_TRIAGE_ENABLED" in todas


def test_plans_health_siempre_200_con_flag_on(client):
    r = client.get("/api/evolution/plans/health")
    assert r.status_code == 200
    assert r.get_json()["flag_enabled"] is True


def test_plans_devuelve_board_con_triage(client):
    r = client.get("/api/evolution/plans")
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True
    assert body["triage_order"] == ["SIN_IMPLEMENTAR", "SIN_CRITICAR", "SIN_DOCUMENTO",
                                    "SIN_SUPERVISAR", "COMPLETADO"]
    assert "triage_totals" in body and "census" in body and "numbering" in body
    assert all("triage_bucket" in p for p in body["plans"])


def test_plans_404_con_su_flag_off(client):
    from config import config as cfg
    cfg.STACKY_EVOLUTION_PLANS_TRIAGE_ENABLED = False
    try:
        r = client.get("/api/evolution/plans")
        assert r.status_code == 404
        # El 404 tiene que nombrar la flag que REALMENTE lo apagó. Si el Centro sigue
        # encendido y solo cayó el triage, culpar a la flag maestra manda al operador a
        # buscar la flag equivocada.
        body = r.get_json()
        assert body["error"] == "plans_triage_disabled"
        assert "STACKY_EVOLUTION_PLANS_TRIAGE_ENABLED" in body["message"]
        assert "STACKY_EVOLUTION_CENTER_ENABLED" not in body["message"]
        assert client.get("/api/evolution/plans/health").get_json()["flag_enabled"] is False
    finally:
        cfg.STACKY_EVOLUTION_PLANS_TRIAGE_ENABLED = True


def test_plans_404_con_la_flag_maestra_off(client):
    from config import config as cfg
    cfg.STACKY_EVOLUTION_CENTER_ENABLED = False
    try:
        r = client.get("/api/evolution/plans")
        assert r.status_code == 404
        # Con la maestra abajo, el diagnóstico correcto SÍ es el del Centro entero.
        body = r.get_json()
        assert body["error"] == "evolution_disabled"
        assert "STACKY_EVOLUTION_CENTER_ENABLED" in body["message"]
    finally:
        cfg.STACKY_EVOLUTION_CENTER_ENABLED = True


def test_plans_no_depende_del_flag_del_tab_planes(client):
    """La sección de Evolución vive aunque el tab 'Planes' esté apagado."""
    from config import config as cfg
    prev = cfg.STACKY_PLANS_BOARD_ENABLED
    cfg.STACKY_PLANS_BOARD_ENABLED = False
    try:
        assert client.get("/api/evolution/plans").status_code == 200
    finally:
        cfg.STACKY_PLANS_BOARD_ENABLED = prev


def test_plan237_seccion_no_expone_endpoints_de_escritura():
    """G2: debajo del centinela del Plan 237 no puede haber NINGUNA ruta de escritura."""
    src_path = pathlib.Path(__file__).resolve().parents[1] / "api" / "evolution.py"
    src = src_path.read_text(encoding="utf-8")
    centinela = "# ── Plan 237 — Triage de planes (bloque appendeado al FINAL del archivo) ──"
    assert centinela in src, "el bloque del Plan 237 debe ir al final de api/evolution.py"
    bloque = src[src.index(centinela):]
    assert not re.search(r"@bp\.(post|put|delete|patch)", bloque), (
        "el bloque del Plan 237 quedó ANTES de rutas de escritura: moverlo al final del archivo"
    )
