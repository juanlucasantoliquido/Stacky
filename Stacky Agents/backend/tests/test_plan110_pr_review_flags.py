"""Plan 110 F0 — Flags del Revisor de PRs (Haiku solo-lectura + modelo local).

5 flags nuevas: 1 bool master default ON + 4 str/int de subconfig.
Verifica registro, categoría devops, editabilidad por UI, default ON del master,
ausencia de default explícito en las str/int, requires → master del panel, y el
cap del camino solo-local (0 = sin límite).
"""
import importlib

from services.harness_flags import FLAG_REGISTRY, _CATEGORY_KEYS

_MASTER = "STACKY_PR_REVIEWER_ENABLED"
_SUBCONFIG = (
    "STACKY_PR_REVIEW_HAIKU_MODEL",
    "STACKY_PR_REVIEW_DIFF_MAX_CHARS",
    "STACKY_PR_REVIEW_LOCAL_DIFF_MAX_CHARS",
    "STACKY_PR_REVIEW_TIMEOUT_SEC",
)
_ALL = (_MASTER,) + _SUBCONFIG


def _spec(key):
    return next((s for s in FLAG_REGISTRY if s.key == key), None)


def test_flags_registered_and_categorized():
    for key in _ALL:
        assert _spec(key) is not None, f"{key} no está en FLAG_REGISTRY"
        assert key in _CATEGORY_KEYS["devops"], f"{key} no está en categoría devops"


def test_flags_editable_by_ui():
    for key in _ALL:
        assert _spec(key).env_only is False, f"{key} debe ser editable por UI"


def test_reviewer_default_on(monkeypatch):
    """Default ON — candado del pedido del operador."""
    monkeypatch.delenv(_MASTER, raising=False)
    import config
    importlib.reload(config)
    try:
        assert config.config.STACKY_PR_REVIEWER_ENABLED is True
    finally:
        importlib.reload(config)
    assert _spec(_MASTER).default is True
    from tests.test_harness_flags import _CURATED_DEFAULTS_ON
    assert _MASTER in _CURATED_DEFAULTS_ON


def test_subconfig_flags_no_explicit_default():
    for key in _SUBCONFIG:
        assert _spec(key).default is None, f"{key} no debe tener default explícito"
    from tests.test_harness_flags import _CURATED_DEFAULTS_ON
    for key in _SUBCONFIG:
        assert key not in _CURATED_DEFAULTS_ON


def test_requires_all_point_to_panel_master():
    for key in _ALL:
        assert _spec(key).requires == "STACKY_DEVOPS_PANEL_ENABLED", (
            f"{key} debe requerir STACKY_DEVOPS_PANEL_ENABLED (R4 profundidad-1)"
        )


def test_local_diff_cap_allows_zero(monkeypatch):
    """El cap del camino solo-local permite 0 (=sin límite); default efectivo 200000."""
    spec = _spec("STACKY_PR_REVIEW_LOCAL_DIFF_MAX_CHARS")
    assert spec.min_value == 0
    assert spec.max_value == 2000000
    monkeypatch.delenv("STACKY_PR_REVIEW_LOCAL_DIFF_MAX_CHARS", raising=False)
    import config
    importlib.reload(config)
    try:
        assert config.config.STACKY_PR_REVIEW_LOCAL_DIFF_MAX_CHARS == 200000
    finally:
        importlib.reload(config)
