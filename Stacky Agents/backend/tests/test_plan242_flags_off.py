"""Plan 242 F8 — Las 2 flags: cableado completo y NO-DEGRADACION.

Alcance recortado (§0.3): SOLO STACKY_COST_STATS_ENABLED y
STACKY_COST_SCORING_ENABLED. Las otras 6 del plan (forecast, ledger, autotrain,
autopromote y las 2 numericas) son del plan siguiente.

G16 — con las 2 en OFF, el Centro de Costos se comporta EXACTAMENTE como el
del Plan 142 + 158: mismos endpoints, mismo payload, cero archivos escritos.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

_LAS_2 = ("STACKY_COST_STATS_ENABLED", "STACKY_COST_SCORING_ENABLED")
_RUTAS = ("/api/metrics/cost-stats", "/api/metrics/cost-scores")


@pytest.fixture(scope="module")
def _app():
    os.environ["STACKY_COST_CENTER_ENABLED"] = "true"
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    return app


@pytest.fixture(scope="module")
def client(_app):
    with _app.test_client() as c:
        yield c


# ── Registro y categorizacion ───────────────────────────────────────────────

def test_las_2_flags_estan_en_el_registry():
    from services.harness_flags import FLAG_REGISTRY
    by_key = {s.key: s for s in FLAG_REGISTRY}
    for key in _LAS_2:
        assert key in by_key, key


def test_las_2_flags_estan_categorizadas():
    """G12 — sin categoria, test_every_registry_flag_is_categorized rompe."""
    from services.harness_flags import categorize
    for key in _LAS_2:
        assert categorize(key) == "observabilidad_notif", key


def test_las_2_flags_estan_en_curated_defaults_on():
    """G11 — declaran default= -> DEBEN estar en el set curado, o
    test_default_known_only_for_curated queda rojo."""
    from tests.test_harness_flags import _CURATED_DEFAULTS_ON
    for key in _LAS_2:
        assert key in _CURATED_DEFAULTS_ON, key


def test_las_2_flags_declaran_default_true():
    from services.harness_flags import FLAG_REGISTRY, default_is_known
    by_key = {s.key: s for s in FLAG_REGISTRY}
    for key in _LAS_2:
        assert by_key[key].default is True, key
        assert default_is_known(by_key[key]) is True, key
        assert by_key[key].type == "bool", key


def test_default_efectivo_es_on_para_las_2():
    """El default EFECTIVO vive en config.py, no en la FlagSpec. Se lee de la
    INSTANCIA config.config (G10), que es lo que consulta el endpoint."""
    from config import config as cfg
    for key in _LAS_2:
        assert hasattr(cfg, key), f"{key} no existe como atributo de Config"
        assert getattr(cfg, key) is True, key


def test_ninguna_flag_es_env_only():
    """Configurable desde la UI del Arnes: nada de env-only."""
    from services.harness_flags import FLAG_REGISTRY
    by_key = {s.key: s for s in FLAG_REGISTRY}
    for key in _LAS_2:
        assert by_key[key].env_only is False, key


def test_las_2_flags_tienen_label_y_description_en_espanol():
    from services.harness_flags import FLAG_REGISTRY
    by_key = {s.key: s for s in FLAG_REGISTRY}
    for key in _LAS_2:
        spec = by_key[key]
        assert spec.label.strip() and spec.description.strip(), key
        assert "Plan 242" in spec.description, key
        # rasgo de castellano: al menos un acento o enie en la descripcion
        assert any(ch in spec.description for ch in "áéíóúñÁÉÍÓÚÑ¿¡"), key


def test_las_2_flags_tienen_ayuda_llana():
    """Su entrada en la ayuda para mortales existe y respeta los limites."""
    from services.harness_flags_help import PLAIN_HELP
    for key in _LAS_2:
        assert key in PLAIN_HELP, key
        e = PLAIN_HELP[key]
        assert len(e.what) <= 200 and len(e.on_effect) <= 240
        assert len(e.off_effect) <= 240 and len(e.example) <= 300
        assert e.on_effect.startswith("Si ") and e.off_effect.startswith("Si ")


def test_las_2_flags_no_declaran_requires():
    """R4 — profundidad 1: estas 2 no cuelgan de ninguna otra, asi que no
    tocan el mapa congelado de aristas."""
    from services.harness_flags import FLAG_REGISTRY
    by_key = {s.key: s for s in FLAG_REGISTRY}
    for key in _LAS_2:
        assert by_key[key].requires is None, key


# ── No-degradacion (G16) ────────────────────────────────────────────────────

@pytest.mark.parametrize("ruta", _RUTAS)
def test_con_las_2_off_los_endpoints_devuelven_enabled_false(client, monkeypatch, ruta):
    import config as config_module
    for key in _LAS_2:
        monkeypatch.setattr(config_module.config, key, False)
    resp = client.get(ruta)
    assert resp.status_code == 200
    assert resp.get_json() == {"enabled": False}


def test_con_las_2_off_cost_summary_es_identico(client, monkeypatch):
    """G16 — el payload del 142 no cambia ni un byte por culpa del 242.

    Las fechas van FIJAS en el query: sin eso, `filters_echo.date_from/date_to`
    se derivan de utcnow() y dos llamadas consecutivas difieren en los
    microsegundos, que es ruido y no una regresion.
    """
    import config as config_module
    ruta = "/api/metrics/cost-summary?from=2026-01-01&to=2026-01-31"
    antes = client.get(ruta).get_json()
    for key in _LAS_2:
        monkeypatch.setattr(config_module.config, key, False)
    despues = client.get(ruta).get_json()
    antes.pop("generated_at", None)
    despues.pop("generated_at", None)
    assert json.dumps(antes, sort_keys=True) == json.dumps(despues, sort_keys=True)


def test_esta_mitad_no_escribe_ningun_archivo(client, monkeypatch):
    """El invariante central del recorte de §0.3: esta mitad es ESTRICTAMENTE
    read-only. Ni siquiera con las 2 flags en ON se abre un archivo para
    escribir. (El que escribe cost_model.json / el ledger es el plan siguiente.)"""
    import builtins

    real_open = builtins.open
    escrituras: list[str] = []

    def _espia(file, mode="r", *a, **k):
        if any(c in str(mode) for c in ("w", "a", "x", "+")):
            escrituras.append(f"{file!r} mode={mode!r}")
        return real_open(file, mode, *a, **k)

    monkeypatch.setattr(builtins, "open", _espia)
    for ruta in _RUTAS:
        assert client.get(ruta).status_code == 200
    assert escrituras == [], f"esta mitad escribio archivos: {escrituras}"


def test_flag_leida_del_modulo_daria_el_default(monkeypatch):
    """G10 documentado como test: `getattr(config_module, K)` NO ve el cambio
    en la instancia. Este es el bug clasico que mata el branch OFF."""
    import config as config_module

    key = "STACKY_COST_STATS_ENABLED"
    monkeypatch.setattr(config_module.config, key, False)
    assert getattr(config_module.config, key) is False        # instancia: OK
    assert getattr(config_module.Config, key) is True         # clase: el default
    assert getattr(config_module.config, key) != getattr(config_module.Config, key)


def test_los_helpers_del_endpoint_leen_la_instancia(monkeypatch):
    """El patron real de api/metrics.py: getattr(_cfg, ...) sobre la instancia."""
    import config as config_module
    from api import metrics

    monkeypatch.setattr(config_module.config, "STACKY_COST_STATS_ENABLED", False)
    monkeypatch.setattr(config_module.config, "STACKY_COST_SCORING_ENABLED", False)
    assert metrics._cost_stats_enabled() is False
    assert metrics._cost_scoring_enabled() is False
