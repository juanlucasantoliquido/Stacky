"""Plan 128 F0 — flag STACKY_PLANS_BOARD_ENABLED (tests primero).

Espejo de tests/test_plan93_preflight_flag.py. **Plan 237**: la flag pasó de
opt-in (sin `default=`) a **default ON** — lectura local de docs/, sin egreso ni
escritura, así que ninguna de las 4 excepciones duras aplica. Sin `requires` (no
tiene master). Categoría `observabilidad_notif` (existente).
"""
from pathlib import Path

from services.harness_flags import FLAG_REGISTRY, _CATEGORY_KEYS
from services.harness_flags_help import PLAIN_HELP

_KEY = "STACKY_PLANS_BOARD_ENABLED"


def _spec():
    return next((s for s in FLAG_REGISTRY if s.key == _KEY), None)


def test_flag_declarada_en_registry():
    spec = _spec()
    assert spec is not None
    assert spec.type == "bool"
    assert spec.label  # no vacío


def test_flag_ui_editable():
    spec = _spec()
    assert spec.env_only is False


def test_flag_default_on_desde_plan237():
    spec = _spec()
    # Plan 237: promovida a default ON (lectura local, sin egreso). Curada en _CURATED_DEFAULTS_ON.
    assert spec.default is True


def test_config_default_on(monkeypatch):
    monkeypatch.delenv(_KEY, raising=False)
    import importlib
    import config
    importlib.reload(config)
    # Plan 237: sin variable de entorno, el tablero viene ENCENDIDO.
    assert config.config.STACKY_PLANS_BOARD_ENABLED is True


def test_categoria_observabilidad():
    assert _KEY in _CATEGORY_KEYS["observabilidad_notif"]


def test_defaults_env_y_help():
    backend_root = Path(__file__).parent.parent
    defaults_path = backend_root / "harness_defaults.env"
    assert defaults_path.exists()
    content = defaults_path.read_text(encoding="utf-8")
    # harness_defaults.env es un snapshot PARCIAL generado por
    # deployment/export_harness_defaults.py: esta key puede no estar. Lo que NO puede
    # pasar (Plan 237) es que esté con el valor viejo "false".
    assert "STACKY_PLANS_BOARD_ENABLED=false" not in content
    assert _KEY in PLAIN_HELP
