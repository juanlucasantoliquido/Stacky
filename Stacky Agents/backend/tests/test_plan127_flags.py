"""
Plan 127 F0 — Flags STACKY_EXEC_ERROR_ANALYSIS_ENABLED y
STACKY_DEVOPS_LOCAL_DOCTOR_ENABLED, patrón triple de flag curada default ON
(directiva explícita del operador 2026-07-12).
"""

from pathlib import Path

from services.harness_flags import FLAG_REGISTRY, _CATEGORY_KEYS

_ERROR_ANALYSIS_KEY = "STACKY_EXEC_ERROR_ANALYSIS_ENABLED"
_LOCAL_DOCTOR_KEY = "STACKY_DEVOPS_LOCAL_DOCTOR_ENABLED"


def _spec(key: str):
    return next((s for s in FLAG_REGISTRY if s.key == key), None)


def test_flags_registradas_en_registry():
    assert _spec(_ERROR_ANALYSIS_KEY) is not None, f"{_ERROR_ANALYSIS_KEY} no está en FLAG_REGISTRY"
    assert _spec(_LOCAL_DOCTOR_KEY) is not None, f"{_LOCAL_DOCTOR_KEY} no está en FLAG_REGISTRY"


def test_flags_categorizadas():
    assert _ERROR_ANALYSIS_KEY in _CATEGORY_KEYS["avanzado"]
    assert _LOCAL_DOCTOR_KEY in _CATEGORY_KEYS["devops"]


def test_local_doctor_requires_panel():
    spec = _spec(_LOCAL_DOCTOR_KEY)
    assert spec.requires == "STACKY_DEVOPS_PANEL_ENABLED"


def test_error_analysis_sin_requires():
    spec = _spec(_ERROR_ANALYSIS_KEY)
    assert spec.requires is None


def test_config_defaults_on(monkeypatch):
    """Sin env vars, ambos atributos de config valen True (patrón invertido de
    test_plan96_doctor_flag.py:41-45)."""
    monkeypatch.delenv(_ERROR_ANALYSIS_KEY, raising=False)
    monkeypatch.delenv(_LOCAL_DOCTOR_KEY, raising=False)
    import importlib
    import config
    importlib.reload(config)
    assert config.config.STACKY_EXEC_ERROR_ANALYSIS_ENABLED is True
    assert config.config.STACKY_DEVOPS_LOCAL_DOCTOR_ENABLED is True


def test_flagspec_default_true():
    assert _spec(_ERROR_ANALYSIS_KEY).default is True
    assert _spec(_LOCAL_DOCTOR_KEY).default is True


def test_flags_en_set_curado():
    from tests.test_harness_flags import _CURATED_DEFAULTS_ON

    assert _ERROR_ANALYSIS_KEY in _CURATED_DEFAULTS_ON
    assert _LOCAL_DOCTOR_KEY in _CURATED_DEFAULTS_ON


def test_harness_defaults_sin_linea_off():
    """H3 — el archivo versionado harness_defaults.env NO debe traer una línea
    '=false' horneada para estas 2 keys (pisaría el default ON de código en
    cada deploy nuevo). Key ausente o '=true' son válidos."""
    backend_root = Path(__file__).parent.parent
    defaults_path = backend_root / "harness_defaults.env"
    assert defaults_path.exists()
    content = defaults_path.read_text(encoding="utf-8")
    assert f"{_ERROR_ANALYSIS_KEY}=false" not in content
    assert f"{_LOCAL_DOCTOR_KEY}=false" not in content
