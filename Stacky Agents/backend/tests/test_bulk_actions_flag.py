"""Plan 187 F0 — flag STACKY_BULK_ACTIONS_ENABLED (seleccion multiple y lote)."""
import re
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
_KEY = "STACKY_BULK_ACTIONS_ENABLED"


def test_flag_registrada_bool_global_default_on():
    from services.harness_flags import FLAG_REGISTRY
    by_key = {s.key: s for s in FLAG_REGISTRY}
    assert _KEY in by_key, f"{_KEY} no esta en FLAG_REGISTRY"
    spec = by_key[_KEY]
    assert spec.type == "bool"
    assert spec.group == "global"
    assert spec.default is True


def test_flag_categorizada_interfaz_ui():
    from services.harness_flags import categorize
    assert categorize(_KEY) == "interfaz_ui"


def test_flag_curada_default_on():
    # Patron real del repo: tests/test_context_contract_flags.py:68
    from tests.test_harness_flags import _CURATED_DEFAULTS_ON
    assert _KEY in _CURATED_DEFAULTS_ON


def test_config_default_efectivo_true():
    # Chequeo a nivel FUENTE para no importar config con side effects
    # (gotcha create_app/daemons; mismo patron que el plan 175 F0).
    src = (_BACKEND / "config.py").read_text(encoding="utf-8")
    m = re.search(rf'{_KEY}: bool = os\.getenv\(\s*"{_KEY}", "(\w+)"', src)
    assert m is not None, "config.py no define la flag con el patron canonico"
    assert m.group(1) == "true"
