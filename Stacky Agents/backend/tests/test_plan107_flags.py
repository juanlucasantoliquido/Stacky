"""Plan 107 F0 — flags STACKY_DEVOPS_ENV_TREE_PREVIEW_ENABLED y
STACKY_DEVOPS_ENV_SANDBOX_ENABLED (tests primero).

Nota (desvío documentado, gotcha _CURATED_DEFAULTS_ON): el doc del plan trae
`default=False` explícito en el pseudocódigo del FlagSpec (líneas 138/153),
pero `default_is_known(spec)` en services/harness_flags.py es
`spec.default is not None` -- CUALQUIER default explícito (True o False)
marca la key como "curada", y `test_default_known_only_for_curated` exige
que el set de keys curadas sea EXACTAMENTE `_CURATED_DEFAULTS_ON` (12 keys
de Plan 63). Como estas 2 keys no están en esa lista, se omite `default=`
del FlagSpec (mismo patrón que Planes 94/95/96/97/98/105). El default
EFECTIVO sigue siendo False vía config.py (test_flags_default_off) y vía
type-zero de `declared_default` (bool sin default -> False).
"""
from services.harness_flags import FLAG_REGISTRY, _CATEGORY_KEYS
from services.harness_flags_help import PLAIN_HELP

_TREE_KEY = "STACKY_DEVOPS_ENV_TREE_PREVIEW_ENABLED"
_SANDBOX_KEY = "STACKY_DEVOPS_ENV_SANDBOX_ENABLED"
_KEYS = (_TREE_KEY, _SANDBOX_KEY)


def _spec(key):
    return next((s for s in FLAG_REGISTRY if s.key == key), None)


def test_flags_registered_in_devops_category():
    for key in _KEYS:
        assert key in _CATEGORY_KEYS["devops"], f"{key} no está en _CATEGORY_KEYS['devops']"


def test_flags_default_off():
    import importlib
    import config

    importlib.reload(config)
    assert config.config.STACKY_DEVOPS_ENV_TREE_PREVIEW_ENABLED is False
    assert config.config.STACKY_DEVOPS_ENV_SANDBOX_ENABLED is False


def test_flags_require_panel_master():
    for key in _KEYS:
        spec = _spec(key)
        assert spec is not None, f"{key} no está en FLAG_REGISTRY"
        assert spec.requires == "STACKY_DEVOPS_PANEL_ENABLED", (
            f"{key}.requires debe apuntar al master del panel (gotcha R4 depth-1), "
            f"no a una flag hija -- valor actual: {spec.requires!r}"
        )
        assert spec.env_only is False
        assert spec.group == "global"
        assert spec.label


def test_health_exposes_new_keys():
    from api.devops import _health_payload

    payload = _health_payload()
    assert "env_tree_preview_enabled" in payload
    assert "env_sandbox_enabled" in payload
    assert isinstance(payload["env_tree_preview_enabled"], bool)
    assert isinstance(payload["env_sandbox_enabled"], bool)


def test_health_backcompat_without_sandbox_key():
    """Con ambas flags OFF (default), ninguna key existente de _health_payload()
    cambia de valor -- solo se agregan las 2 keys nuevas (aditivo puro)."""
    from api.devops import _health_payload

    payload = _health_payload()
    # Keys pre-existentes (Plan 87..105) deben seguir presentes con su tipo bool.
    preexisting = (
        "flag_enabled", "generator_enabled", "trigger_enabled",
        "publications_enabled", "environments_enabled", "agent_enabled",
        "servers_enabled", "rdp_available", "preflight_enabled",
        "variables_enabled", "stack_detect_enabled", "doctor_enabled",
        "production_enabled", "ado_commit_supported", "section_doctor_enabled",
        "bootstrap_enabled", "remote_console_enabled",
    )
    for key in preexisting:
        assert key in payload, f"regresión: {key} desapareció de _health_payload()"
    # Con las flags nuevas OFF por default, sus keys son False.
    assert payload["env_tree_preview_enabled"] is False
    assert payload["env_sandbox_enabled"] is False


def test_flags_have_plain_help():
    for key in _KEYS:
        assert key in PLAIN_HELP, f"{key} sin entrada en PLAIN_HELP (Plan 86)"
