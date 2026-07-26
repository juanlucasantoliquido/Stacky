"""Plan 171 F0 — Las 3 flags de telemetría operativa (patrón triple).

Master + 2 hijas con `requires` de profundidad 1, todas default ON (observabilidad
read-only: no bypasea revisión, no es destructiva, no depende de prerequisito
externo, no reduce seguridad).
"""
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

_MASTER = "STACKY_OPS_TELEMETRY_ENABLED"
_BASELINE = "STACKY_OPS_BASELINE_ENABLED"
_TRACE = "STACKY_OPS_TRACE_ENABLED"


def _spec(key: str):
    from services.harness_flags import FLAG_REGISTRY

    return next((s for s in FLAG_REGISTRY if s.key == key), None)


def test_master_flag_en_registry():
    spec = _spec(_MASTER)

    assert spec is not None, f"{_MASTER} no está en FLAG_REGISTRY"
    assert spec.type == "bool"
    assert spec.default is True
    assert not getattr(spec, "requires", None), "la master no declara requires (profundidad 1)"


def test_baseline_flag_requires_master():
    spec = _spec(_BASELINE)

    assert spec is not None
    assert spec.type == "bool"
    assert spec.default is True
    assert spec.requires == _MASTER


def test_trace_flag_requires_master():
    spec = _spec(_TRACE)

    assert spec is not None
    assert spec.type == "bool"
    assert spec.default is True
    assert spec.requires == _MASTER


def test_las_3_estan_categorizadas():
    from services.harness_flags import _CATEGORY_KEYS

    todas = {k for keys in _CATEGORY_KEYS.values() for k in keys}
    faltan = {_MASTER, _BASELINE, _TRACE} - todas
    assert faltan == set(), f"sin categorizar: {sorted(faltan)}"


def test_config_defaults_on(monkeypatch):
    for key in (_MASTER, _BASELINE, _TRACE):
        monkeypatch.delenv(key, raising=False)
    import config as config_mod

    reloaded = importlib.reload(config_mod)
    try:
        assert reloaded.Config.STACKY_OPS_TELEMETRY_ENABLED is True
        assert reloaded.Config.STACKY_OPS_BASELINE_ENABLED is True
        assert reloaded.Config.STACKY_OPS_TRACE_ENABLED is True
    finally:
        # El reload contamina la instancia global de la corrida: se restaura.
        importlib.reload(config_mod)


def test_aristas_requires_congeladas():
    from tests.test_harness_flags_requires import _REQUIRES_MAP_FROZEN

    assert _REQUIRES_MAP_FROZEN.get(_BASELINE) == _MASTER
    assert _REQUIRES_MAP_FROZEN.get(_TRACE) == _MASTER
    assert _MASTER not in _REQUIRES_MAP_FROZEN, "la master no puede tener arista (profundidad 1)"


def test_help_presente():
    from services.harness_flags_help import PLAIN_HELP

    for key in (_MASTER, _BASELINE, _TRACE):
        assert key in PLAIN_HELP, f"falta la ayuda en lenguaje llano de {key}"
        help_entry = PLAIN_HELP[key]
        assert help_entry.what and help_entry.on_effect
        assert help_entry.off_effect and help_entry.example


def test_flags_en_curated_defaults_on():
    from tests.test_harness_flags import _CURATED_DEFAULTS_ON

    for key in (_MASTER, _BASELINE, _TRACE):
        assert key in _CURATED_DEFAULTS_ON
