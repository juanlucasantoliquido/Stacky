"""Plan 200 F0 — Las 4 flags: 3 read-only default ON y la de ejecución SQL OFF.

La asimetría es el punto: mirar la consola, detectar que hace falta desplegar y
llevar bitácora son read-only y vienen encendidas. Ejecutar DDL/DML contra una
base real es destructivo e irreversible ⇒ default OFF, y el operador la prende
a mano cuando quiere.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

_ON = (
    "STACKY_INCIDENT_CONSOLE_ENABLED",
    "STACKY_SQL_DEPLOY_DETECT_ENABLED",
    "STACKY_SQL_EXEC_LEDGER_ENABLED",
)
_OFF = "STACKY_SQL_EXEC_ENABLED"

_PADRES = {
    "STACKY_INCIDENT_CONSOLE_ENABLED": "STACKY_INCIDENT_RESOLVER_ENABLED",
    "STACKY_SQL_DEPLOY_DETECT_ENABLED": "STACKY_INCIDENT_RESOLVER_ENABLED",
    "STACKY_SQL_EXEC_LEDGER_ENABLED": "STACKY_DB_COMPARE_ENABLED",
    "STACKY_SQL_EXEC_ENABLED": "STACKY_DB_COMPARE_ENABLED",
}


def _spec(key: str):
    from services.harness_flags import FLAG_REGISTRY

    return next((s for s in FLAG_REGISTRY if s.key == key), None)


def test_r1_r2_r4_declaradas_default_on():
    from config import config as cfg

    for key in _ON:
        spec = _spec(key)
        assert spec is not None, key
        assert spec.type == "bool", key
        assert spec.default is True, key
        assert getattr(cfg, key) is True, key


def test_r3_declarada_default_off():
    """Ejecutar SQL real no puede venir encendido de fábrica."""
    from config import config as cfg

    spec = _spec(_OFF)
    assert spec is not None
    assert spec.type == "bool"
    assert getattr(cfg, _OFF) is False


def test_r1_r2_r4_en_curated_on():
    from tests.test_harness_flags import _CURATED_DEFAULTS_ON

    for key in _ON:
        assert key in _CURATED_DEFAULTS_ON, key


def test_r3_no_en_curated_on():
    from tests.test_harness_flags import _CURATED_DEFAULTS_ON

    assert _OFF not in _CURATED_DEFAULTS_ON


def test_r3_no_declara_default_en_el_spec():
    """Gotcha del arnés: declarar `default=` la vuelve 'conocida' y exige estar
    curada, pero el set curado es sólo para las bool ON. El default real vive
    en config.py."""
    from services.harness_flags import default_is_known

    assert default_is_known(_spec(_OFF)) is False


def test_cuatro_categorizadas():
    from services.harness_flags import _CATEGORY_KEYS

    todas = {k for keys in _CATEGORY_KEYS.values() for k in keys}
    for key in (*_ON, _OFF):
        assert key in todas, key


def test_cuatro_aristas_requires():
    for key, padre in _PADRES.items():
        assert _spec(key).requires == padre, key


def test_aristas_en_el_mapa_congelado():
    from tests.test_harness_flags_requires import _REQUIRES_MAP_FROZEN

    for key, padre in _PADRES.items():
        assert _REQUIRES_MAP_FROZEN.get(key) == padre, key
