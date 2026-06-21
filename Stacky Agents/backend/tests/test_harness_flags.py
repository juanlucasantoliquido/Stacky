"""H0.4 — Tests del registry de flags del arnés y el endpoint /api/harness-flags.

Casos:
  1. Integridad del registry: para cada FlagSpec con env_only=False, hasattr(config, key).
  2. apply_updates: cast por tipo, key desconocida→ValueError.
  3. API PUT y hot-apply: 200 + config actualizado + .env temporal + os.environ.
  4. API PUT con key desconocida → 400 y .env sin cambiar.
  5. Round-trip: GET refleja el valor tras el PUT.
  6. env_only: PUT STACKY_MEMORY_INJECTION_ENABLED → os.environ y memory_injection_enabled.
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


# ---------------------------------------------------------------------------
# 1. Integridad del registry
# ---------------------------------------------------------------------------

def test_registry_all_non_env_only_keys_exist_in_config():
    """Cada FlagSpec con env_only=False debe ser un atributo real de Config."""
    from services.harness_flags import FLAG_REGISTRY
    from config import config

    missing = [
        spec.key for spec in FLAG_REGISTRY
        if not spec.env_only and not hasattr(config, spec.key)
    ]
    assert missing == [], f"Keys no encontradas en config: {missing}"


def test_registry_no_duplicates():
    """No hay claves duplicadas en el registry."""
    from services.harness_flags import FLAG_REGISTRY

    keys = [s.key for s in FLAG_REGISTRY]
    assert len(keys) == len(set(keys)), "Claves duplicadas en FLAG_REGISTRY"


def test_operator_note_flag_registered():
    """Plan 47 F3 — flag STACKY_OPERATOR_NOTE_TO_MEMORY_ENABLED registrado."""
    from services.harness_flags import FLAG_REGISTRY

    spec = next(
        (s for s in FLAG_REGISTRY if s.key == "STACKY_OPERATOR_NOTE_TO_MEMORY_ENABLED"),
        None,
    )
    assert spec is not None
    assert spec.type == "bool"
    assert spec.env_only is True
    assert spec.group == "global"


def test_artifact_rescue_flag_registered():
    """Plan 47 F4 — flag STACKY_ARTIFACT_RESCUE_ENABLED registrado."""
    from services.harness_flags import FLAG_REGISTRY

    spec = next(
        (s for s in FLAG_REGISTRY if s.key == "STACKY_ARTIFACT_RESCUE_ENABLED"),
        None,
    )
    assert spec is not None
    assert spec.type == "bool"
    assert spec.group == "global"
    assert spec.env_only is True


def test_push_rejections_flag_registered():
    """Plan 48 F5 — flag STACKY_PUSH_REJECTIONS_ENABLED registrado."""
    from services.harness_flags import FLAG_REGISTRY

    spec = next(
        (s for s in FLAG_REGISTRY if s.key == "STACKY_PUSH_REJECTIONS_ENABLED"),
        None,
    )
    assert spec is not None
    assert spec.type == "bool"
    assert spec.group == "global"


def test_plan50_flags_registered():
    """Plan 50 F0 — las 3 flags de saneamiento/warnings registradas como bool."""
    from services.harness_flags import FLAG_REGISTRY

    by_key = {s.key: s for s in FLAG_REGISTRY}
    for key in (
        "STACKY_EPIC_SANITIZE_ENABLED",
        "STACKY_EPIC_STRUCTURE_WARNINGS_ENABLED",
        "STACKY_CATALOG_GROUNDING_WARNINGS_ENABLED",
    ):
        assert key in by_key, f"flag {key} no registrada"
        assert by_key[key].type == "bool"
        assert by_key[key].env_only is True


def test_plan51_52_flags_registered():
    """Plan 51 F3 + Plan 52 F1 — flags nuevas registradas como bool env_only."""
    from services.harness_flags import FLAG_REGISTRY

    by_key = {s.key: s for s in FLAG_REGISTRY}
    for key in (
        "STACKY_EPIC_GATE_ENABLED",
        "STACKY_EPIC_CATALOG_GATE_ENABLED",
        "STACKY_COMMENT_FULL_SCAN_ENABLED",
    ):
        assert key in by_key, f"flag {key} no registrada"
        assert by_key[key].type == "bool"
        assert by_key[key].env_only is True


def test_plan53_adaptive_selector_flag_registered():
    """Plan 53 — STACKY_ADAPTIVE_SELECTOR_ENABLED registrada, bool, no env_only (atributo de Config)."""
    from services.harness_flags import FLAG_REGISTRY

    by_key = {s.key: s for s in FLAG_REGISTRY}
    key = "STACKY_ADAPTIVE_SELECTOR_ENABLED"
    assert key in by_key, f"flag {key} no registrada en FLAG_REGISTRY"
    spec = by_key[key]
    assert spec.type == "bool"
    assert spec.env_only is False, "debe ser atributo de Config (no env_only)"
    assert spec.group == "agents"


def test_plan55_flags_registered():
    """Plan 55 — STACKY_ADO_PREVIEW_ENABLED y STACKY_EPIC_PORTFOLIO_ENABLED registradas como bool env_only."""
    from services.harness_flags import FLAG_REGISTRY

    by_key = {s.key: s for s in FLAG_REGISTRY}
    for key, expected_group in (
        ("STACKY_ADO_PREVIEW_ENABLED", "agents"),
        ("STACKY_EPIC_PORTFOLIO_ENABLED", "agents"),
    ):
        assert key in by_key, f"flag {key} no registrada en FLAG_REGISTRY"
        spec = by_key[key]
        assert spec.type == "bool", f"{key}: type debe ser bool"
        assert spec.env_only is True, f"{key}: debe ser env_only=True"
        assert spec.group == expected_group, f"{key}: group debe ser '{expected_group}'"


# ---------------------------------------------------------------------------
# 2. apply_updates — cast por tipo
# ---------------------------------------------------------------------------

def test_apply_updates_bool_true_string():
    from services.harness_flags import apply_updates

    result = apply_updates({"CLAUDE_CODE_CLI_MCP_ENABLED": "true"})
    assert result["CLAUDE_CODE_CLI_MCP_ENABLED"] is True


def test_apply_updates_bool_false_string():
    from services.harness_flags import apply_updates

    result = apply_updates({"CLAUDE_CODE_CLI_MCP_ENABLED": "false"})
    assert result["CLAUDE_CODE_CLI_MCP_ENABLED"] is False


def test_apply_updates_bool_native_true():
    from services.harness_flags import apply_updates

    result = apply_updates({"CLAUDE_CODE_CLI_CONTRACT_GATE_ENABLED": True})
    assert result["CLAUDE_CODE_CLI_CONTRACT_GATE_ENABLED"] is True


def test_apply_updates_bool_invalid_raises():
    from services.harness_flags import apply_updates

    with pytest.raises(ValueError, match="CLAUDE_CODE_CLI_MCP_ENABLED"):
        apply_updates({"CLAUDE_CODE_CLI_MCP_ENABLED": "maybe"})


def test_apply_updates_unknown_key_raises():
    from services.harness_flags import apply_updates

    with pytest.raises(ValueError, match="UNKNOWN_KEY_XYZ"):
        apply_updates({"UNKNOWN_KEY_XYZ": True})


def test_apply_updates_csv_normalizes_whitespace():
    from services.harness_flags import apply_updates

    result = apply_updates({"CLAUDE_CODE_CLI_MCP_PROJECTS": " A , b ,"})
    assert result["CLAUDE_CODE_CLI_MCP_PROJECTS"] == "A,b"


def test_apply_updates_int_valid():
    from services.harness_flags import apply_updates

    result = apply_updates({"CLAUDE_CODE_CLI_AUTOCORRECT_MAX_RETRIES": "3"})
    assert result["CLAUDE_CODE_CLI_AUTOCORRECT_MAX_RETRIES"] == 3


def test_apply_updates_int_invalid_raises():
    from services.harness_flags import apply_updates

    with pytest.raises(ValueError, match="CLAUDE_CODE_CLI_AUTOCORRECT_MAX_RETRIES"):
        apply_updates({"CLAUDE_CODE_CLI_AUTOCORRECT_MAX_RETRIES": "x"})


# ---------------------------------------------------------------------------
# 3. API PUT → hot-apply + .env + os.environ
# ---------------------------------------------------------------------------

@pytest.fixture
def client(tmp_path, monkeypatch):
    """Flask test client con _ENV_PATH apuntando a un tmp .env."""
    monkeypatch.setenv("STACKY_REAPER_ENABLED", "false")
    monkeypatch.setenv("STACKY_MANIFEST_WATCHER_ENABLED", "false")

    # Redirigir _ENV_PATH de global_config a un archivo temporal
    tmp_env = tmp_path / ".env"
    tmp_env.write_text("", encoding="utf-8")
    monkeypatch.setattr("api.global_config._ENV_PATH", tmp_env)
    # También redirigir en harness_flags si importa _ENV_PATH directamente
    monkeypatch.setattr("api.harness_flags._ENV_PATH", tmp_env, raising=False)

    from app import create_app
    from services.ticket_status import stop_stale_recovery
    from services.manifest_watcher import stop_manifest_watcher

    app = create_app()
    app.config.update(TESTING=True)
    stop_stale_recovery()
    stop_manifest_watcher()
    with app.test_client() as c:
        yield c, tmp_env
    stop_stale_recovery()
    stop_manifest_watcher()


def test_put_harness_flag_hot_apply(client, monkeypatch):
    """PUT actualiza config en caliente (setattr), .env y os.environ."""
    c, tmp_env = client
    from config import config

    # Asegurarse de estado inicial False
    monkeypatch.setattr(config, "CLAUDE_CODE_CLI_MCP_ENABLED", False)

    resp = c.put(
        "/api/harness-flags",
        json={"updates": {"CLAUDE_CODE_CLI_MCP_ENABLED": True}},
    )
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data["ok"] is True

    # hot-apply verificado: el atributo del config singleton fue seteado
    assert config.CLAUDE_CODE_CLI_MCP_ENABLED is True

    # .env temporal contiene la key
    env_content = tmp_env.read_text(encoding="utf-8")
    assert "CLAUDE_CODE_CLI_MCP_ENABLED=true" in env_content

    # os.environ actualizado
    assert os.environ.get("CLAUDE_CODE_CLI_MCP_ENABLED") == "true"


def test_put_unknown_key_returns_400_no_env_change(client):
    """PUT con key desconocida → 400 y el .env temporal NO cambia."""
    c, tmp_env = client
    original = tmp_env.read_text(encoding="utf-8")

    resp = c.put(
        "/api/harness-flags",
        json={"updates": {"NONEXISTENT_FLAG_XYZ": True}},
    )
    assert resp.status_code == 400
    assert tmp_env.read_text(encoding="utf-8") == original


# ---------------------------------------------------------------------------
# 4. Round-trip: GET refleja el valor tras el PUT
# ---------------------------------------------------------------------------

def test_get_after_put_reflects_value(client, monkeypatch):
    """GET /api/harness-flags muestra el valor actualizado tras un PUT."""
    c, _ = client
    from config import config

    monkeypatch.setattr(config, "CLAUDE_CODE_CLI_HOOKS_ENABLED", False)

    c.put(
        "/api/harness-flags",
        json={"updates": {"CLAUDE_CODE_CLI_HOOKS_ENABLED": True}},
    )

    resp = c.get("/api/harness-flags")
    assert resp.status_code == 200
    flags = {f["key"]: f["value"] for f in json.loads(resp.data)["flags"]}
    assert flags["CLAUDE_CODE_CLI_HOOKS_ENABLED"] is True


# ---------------------------------------------------------------------------
# 5. env_only: STACKY_MEMORY_INJECTION_ENABLED
# ---------------------------------------------------------------------------

def test_put_env_only_flag_updates_os_environ(client):
    """PUT STACKY_MEMORY_INJECTION_ENABLED (env_only) → os.environ y memory_injection_enabled."""
    c, _ = client

    # Limpiar estado previo
    os.environ.pop("STACKY_MEMORY_INJECTION_ENABLED", None)

    resp = c.put(
        "/api/harness-flags",
        json={"updates": {"STACKY_MEMORY_INJECTION_ENABLED": True}},
    )
    assert resp.status_code == 200
    assert os.environ.get("STACKY_MEMORY_INJECTION_ENABLED") == "true"

    # memory_injection_enabled lo ve sin reinicio (allowlist vacía → aplica a todos)
    from services.cli_feature_flags import memory_injection_enabled
    assert memory_injection_enabled(None) is True


# ---------------------------------------------------------------------------
# 6. Unificación writer/loader del .env (fix del split en deploy frozen)
# ---------------------------------------------------------------------------

def test_env_writers_target_the_same_file_config_loads():
    """harness_flags y global_config deben escribir el MISMO .env que carga
    config.py al arrancar: backend_root()/.env.

    En un deploy frozen, el patrón viejo Path(__file__).parent.parent resolvía a
    _internal/.env, que el loader (config.py) nunca lee → los cambios de la UI no
    sobrevivían al reinicio del deploy. Ambos endpoints deben coincidir entre sí
    y con el loader.
    """
    from runtime_paths import backend_root
    import api.harness_flags as hf
    import api.global_config as gc

    expected = backend_root() / ".env"
    assert hf._ENV_PATH == expected
    assert gc._ENV_PATH == expected


# ---------------------------------------------------------------------------
# Plan 58 — Flags del bucle de convergencia de calidad
# ---------------------------------------------------------------------------

def test_convergence_flags_registered():
    """Los dos keys del plan 58 deben aparecer en FLAG_REGISTRY."""
    from services.harness_flags import FLAG_REGISTRY
    keys = {f.key for f in FLAG_REGISTRY}
    assert "STACKY_QUALITY_CONVERGENCE_ENABLED" in keys
    assert "STACKY_QUALITY_CONVERGENCE_MAX_ITERATIONS" in keys


def test_convergence_enabled_default_off():
    """Con env limpio, STACKY_QUALITY_CONVERGENCE_ENABLED debe ser False."""
    env_backup = os.environ.pop("STACKY_QUALITY_CONVERGENCE_ENABLED", None)
    try:
        from importlib import reload
        import config as cfg_module
        reload(cfg_module)
        assert cfg_module.Config().STACKY_QUALITY_CONVERGENCE_ENABLED is False
    finally:
        if env_backup is not None:
            os.environ["STACKY_QUALITY_CONVERGENCE_ENABLED"] = env_backup
        from importlib import reload
        import config as cfg_module
        reload(cfg_module)


def test_convergence_cap_default_two():
    """Con env limpio, STACKY_QUALITY_CONVERGENCE_MAX_ITERATIONS debe ser 2."""
    env_backup = os.environ.pop("STACKY_QUALITY_CONVERGENCE_MAX_ITERATIONS", None)
    try:
        from importlib import reload
        import config as cfg_module
        reload(cfg_module)
        assert cfg_module.Config().STACKY_QUALITY_CONVERGENCE_MAX_ITERATIONS == 2
    finally:
        if env_backup is not None:
            os.environ["STACKY_QUALITY_CONVERGENCE_MAX_ITERATIONS"] = env_backup
        from importlib import reload
        import config as cfg_module
        reload(cfg_module)
