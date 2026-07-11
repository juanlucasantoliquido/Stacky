"""Plan 107 F0 — flags STACKY_DEVOPS_ENV_TREE_PREVIEW_ENABLED y
STACKY_DEVOPS_ENV_SANDBOX_ENABLED (tests primero).

Activación operador 2026-07-09: ambas keys fueron promovidas a default ON
(`default=True` explícito en el FlagSpec, curadas en _CURATED_DEFAULTS_ON;
config.py cae a "true" sin env var), rompiendo conscientemente el default-OFF
original documentado más abajo en el historial de este archivo.
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


def test_flags_default_on():
    """Default ON desde 2026-07-09 (activación explícita del operador)."""
    import importlib
    import config

    importlib.reload(config)
    assert config.config.STACKY_DEVOPS_ENV_TREE_PREVIEW_ENABLED is True
    assert config.config.STACKY_DEVOPS_ENV_SANDBOX_ENABLED is True


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
    """Con ambas flags ON (default desde 2026-07-09), ninguna key existente de
    _health_payload() desaparece -- solo se agregan las 2 keys nuevas (aditivo puro)."""
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
    # Con las flags nuevas ON por default (activación operador 2026-07-09), sus keys son True.
    assert payload["env_tree_preview_enabled"] is True
    assert payload["env_sandbox_enabled"] is True


def test_flags_have_plain_help():
    for key in _KEYS:
        assert key in PLAIN_HELP, f"{key} sin entrada en PLAIN_HELP (Plan 86)"
