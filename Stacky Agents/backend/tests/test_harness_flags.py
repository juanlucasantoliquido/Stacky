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


# ---------------------------------------------------------------------------
# Plan 59 — Flag de descomposición vertical épica→hijos
# ---------------------------------------------------------------------------

def test_epic_decomposition_flag_registered():
    """STACKY_EPIC_DECOMPOSITION_ENABLED debe aparecer en FLAG_REGISTRY."""
    from services.harness_flags import FLAG_REGISTRY
    keys = {f.key for f in FLAG_REGISTRY}
    assert "STACKY_EPIC_DECOMPOSITION_ENABLED" in keys


def test_epic_decomposition_flag_default_off():
    """El flag de descomposición debe tener default False (env_only, leído via os.getenv)."""
    from services.harness_flags import FLAG_REGISTRY
    spec = next(f for f in FLAG_REGISTRY if f.key == "STACKY_EPIC_DECOMPOSITION_ENABLED")
    assert spec.type == "bool"
    # env_only=True: leído con os.getenv en tickets.py, no atributo de Config.
    assert spec.env_only is True


def test_epic_decomposition_flag_group_global():
    """El flag de descomposición debe pertenecer al grupo 'global'."""
    from services.harness_flags import FLAG_REGISTRY
    spec = next(f for f in FLAG_REGISTRY if f.key == "STACKY_EPIC_DECOMPOSITION_ENABLED")
    assert spec.group == "global"


# ---------------------------------------------------------------------------
# Plan 60 — Flags de aprendizaje bidireccional ediciones ADO
# ---------------------------------------------------------------------------

def test_ado_edit_learning_flags_registered():
    """Los 3 keys del plan 60 deben aparecer en FLAG_REGISTRY."""
    from services.harness_flags import FLAG_REGISTRY
    keys = {f.key for f in FLAG_REGISTRY}
    assert "STACKY_ADO_EDIT_LEARNING_ENABLED" in keys
    assert "STACKY_ADO_EDIT_SWEEP_HOURS" in keys
    assert "STACKY_ADO_SERVICE_IDENTITY" in keys


def test_ado_edit_learning_enabled_is_env_only_bool():
    """STACKY_ADO_EDIT_LEARNING_ENABLED debe ser type=bool, env_only=True, group=global."""
    from services.harness_flags import FLAG_REGISTRY
    spec = next(f for f in FLAG_REGISTRY if f.key == "STACKY_ADO_EDIT_LEARNING_ENABLED")
    assert spec.type == "bool"
    assert spec.env_only is True
    assert spec.group == "global"


def test_ado_edit_sweep_hours_is_env_only_int():
    """STACKY_ADO_EDIT_SWEEP_HOURS debe ser type=int, env_only=True."""
    from services.harness_flags import FLAG_REGISTRY
    spec = next(f for f in FLAG_REGISTRY if f.key == "STACKY_ADO_EDIT_SWEEP_HOURS")
    assert spec.type == "int"
    assert spec.env_only is True


def test_ado_service_identity_is_env_only_csv():
    """STACKY_ADO_SERVICE_IDENTITY debe ser type=csv, env_only=True."""
    from services.harness_flags import FLAG_REGISTRY
    spec = next(f for f in FLAG_REGISTRY if f.key == "STACKY_ADO_SERVICE_IDENTITY")
    assert spec.type == "csv"
    assert spec.env_only is True


# ---------------------------------------------------------------------------
# Plan 63 — F0: taxonomía de categorías + helpers
# ---------------------------------------------------------------------------

# Keys con default=True curadas con confianza (ratchet Plan 63).
# El set ES la lista de defaults ON curados: toda flag con spec.default=True DEBE estar
# aquí (default_is_known == True ⇔ pertenencia a este set). Agregar/quitar una key acá
# es la vía canónica para promover/degradar un default; nunca se toca el meta-test.
_CURATED_DEFAULTS_ON = {
    # ── Plan 63 — 12 originales ──
    "STACKY_EPIC_SANITIZE_ENABLED",
    "STACKY_EPIC_STRUCTURE_WARNINGS_ENABLED",
    "STACKY_COMMENT_FULL_SCAN_ENABLED",
    "STACKY_ADO_PREVIEW_ENABLED",
    "STACKY_GROUNDING_OBSERVATORY_ENABLED",
    "STACKY_PROCESS_CATALOG_SUGGESTIONS_ENABLED",
    "STACKY_OPERATIONAL_HEALTH_ENABLED",
    "STACKY_EPIC_FROM_BRIEF_ENABLED",
    "STACKY_EXECUTION_TRACE_ENABLED",
    "STACKY_ORPHAN_REAPER_ENABLED",
    "STACKY_PENDING_TASK_STRICT_VALIDATION_ENABLED",
    "STACKY_RUNNER_REAP_ON_CLOSE_ENABLED",
    # ── Promoción de defaults a ON — Grupo A (bajo riesgo, costo de tokens nulo/negativo) ──
    "STACKY_PARALLEL_INJECTORS_ENABLED",
    "STACKY_CONTEXT_DEDUP_ENABLED",
    "STACKY_CONTEXT_BUDGET_ENABLED",
    "STACKY_CONTEXT_RERANK_ENABLED",
    "STACKY_COMPLEXITY_ESTIMATION_ENABLED",
    "STACKY_ARTIFACT_INTAKE_ENABLED",
    "STACKY_LOG_FLUSH_INCREMENTAL_ENABLED",
    "STACKY_PUBLISH_IDEMPOTENT_GUARD_ENABLED",
    "STACKY_RELIABILITY_KPIS_ENABLED",
    "STACKY_INTEGRITY_KPIS_ENABLED",
    "STACKY_EXEC_VERIFICATION_KPIS_ENABLED",
    "STACKY_ACCEPTANCE_KPIS_ENABLED",
    "STACKY_QUALITY_KPIS_ENABLED",
    "STACKY_EXECUTION_HISTORY_ENABLED",
    # ── Promoción de defaults a ON — Grupo B (valioso; algunas gastan tokens/CPU) ──
    "STACKY_DIFFICULTY_ROUTING_ENABLED",
    "STACKY_RUN_REPAIR_ENABLED",
    "STACKY_ACCEPTANCE_CRITERIA_INJECTION_ENABLED",
    "STACKY_SKILLS_ENABLED",
    "STACKY_ADAPTIVE_EFFORT_ENABLED",
    "STACKY_FAKE_GREEN_GUARD_ENABLED",   # soft-warn (HARD queda OFF)
    "STACKY_EXEC_VERIFICATION_ENABLED",  # modo annotate (NUNCA gate; EXEC_REPAIR OFF)
    "STACKY_PUSH_REJECTIONS_ENABLED",
    "STACKY_DB_READONLY_DIRECTIVE_ENABLED",
    # ── Activación operador 2026-07-05 — serie pipelines/DevOps (decisión explícita,
    # incluye flags de mayor riesgo: RDP+credenciales, disparo de pipelines CI reales,
    # commit de YAML a repo, y consumo de tokens del agente DevOps) ──
    "STACKY_NEGATIVE_GOLDEN_FROM_EDITS_ENABLED",
    "STACKY_PIPELINE_TRIGGER_ENABLED",
    "STACKY_PIPELINE_GENERATOR_ENABLED",
    "STACKY_DEVOPS_PANEL_ENABLED",
    "STACKY_DEVOPS_PUBLICATIONS_ENABLED",
    "STACKY_DEVOPS_ENVIRONMENTS_ENABLED",
    "STACKY_DEVOPS_AGENT_ENABLED",
    "STACKY_DEVOPS_SERVERS_ENABLED",
    # ── Activación operador 2026-07-09 — modelo local ON por default (decisión
    # explícita; rompe el default-OFF original de Plan 106 conscientemente) ──
    "LOCAL_LLM_ENABLED",
    # ── Activación operador 2026-07-09 — flags DevOps 93-108 promovidas a default
    # ON (decisión explícita; rompen el default-OFF original de cada plan
    # conscientemente) ──
    "STACKY_DEVOPS_PREFLIGHT_ENABLED",
    "STACKY_DEVOPS_VARIABLES_ENABLED",
    "STACKY_DEVOPS_PRODUCTION_ENABLED",
    "STACKY_DEVOPS_DOCTOR_ENABLED",
    "STACKY_DEVOPS_STACK_DETECT_ENABLED",
    "STACKY_DEVOPS_BOOTSTRAP_ENABLED",
    "STACKY_DEVOPS_SECTION_DOCTOR_ENABLED",
    "STACKY_DEVOPS_REMOTE_CONSOLE_ENABLED",
    "STACKY_DEVOPS_ENV_TREE_PREVIEW_ENABLED",
    "STACKY_DEVOPS_ENV_SANDBOX_ENABLED",
    "STACKY_DEVOPS_REMOTE_TARGET_ENABLED",
    # ── Plan 110 — Revisor de PRs: master default ON pedido por el operador ──
    "STACKY_PR_REVIEWER_ENABLED",
    # ── Activación operador 2026-07-10 — "Capacidades opt-in": features que el
    # operador invoca explícitamente (botón/tab/endpoint) y NO disparan trabajo
    # ni costo automático dentro de otro flujo. Promovidas a default ON para que
    # todas queden disponibles sin recordar cuál estaba prendida. Ver categoría
    # capacidades_optin. ADO_PREWARM queda INERTE hasta STACKY_ADO_READ_CACHE_TTL_SEC>0. ──
    "STACKY_DOCS_GRAPH_ENABLED",
    "STACKY_DOCS_STALENESS_ENABLED",
    "STACKY_DOCS_DOCUMENTER_ENABLED",
    "STACKY_DOCS_RAG_HYBRID_ENABLED",
    "STACKY_MIGRATOR_ADO_TO_GITLAB_ENABLED",
    "STACKY_CAPS_ADVISOR_ENABLED",
    "STACKY_EPIC_DECOMPOSITION_ENABLED",
    "STACKY_EPIC_PORTFOLIO_ENABLED",
    "STACKY_CODEBASE_MEMORY_MCP_ENABLED",
    "STACKY_GITLAB_DEEP_LINKS_ENABLED",
    "STACKY_ADO_PREWARM_ENABLED",
}


def test_every_registry_flag_is_categorized():
    """Cada key del registry debe estar en _CATEGORY_KEYS (bijección completa, sin huérfanas)."""
    from services.harness_flags import FLAG_REGISTRY, _KEY_CATEGORY

    registry_keys = {s.key for s in FLAG_REGISTRY}
    category_keys = set(_KEY_CATEGORY.keys())
    missing = registry_keys - category_keys
    stale = category_keys - registry_keys
    assert missing == set(), f"Keys del registry sin categoría: {sorted(missing)}"
    assert stale == set(), f"Keys en _CATEGORY_KEYS que ya no existen en el registry: {sorted(stale)}"


def test_category_keys_no_duplicates_across_categories():
    """Ninguna key aparece en más de una categoría."""
    from services.harness_flags import _CATEGORY_KEYS

    all_keys: list[str] = []
    for keys in _CATEGORY_KEYS.values():
        all_keys.extend(keys)
    assert len(all_keys) == len(set(all_keys)), "Hay keys duplicadas en _CATEGORY_KEYS"


def test_categorize_known_and_fallback():
    """categorize devuelve la categoría correcta para una key conocida y 'otros' para una inexistente."""
    from services.harness_flags import categorize

    assert categorize("STACKY_TASK_GATE_ENABLED") == "flujo_funcional"
    assert categorize("CLAVE_INEXISTENTE_XYZ") == "otros"


def test_list_categories_ids_unique_and_include_otros():
    """list_categories devuelve ids únicos, incluye 'otros', y toda categoría usada en
    _CATEGORY_KEYS existe en FLAG_CATEGORIES."""
    from services.harness_flags import list_categories, FLAG_CATEGORIES, _CATEGORY_KEYS

    cats = list_categories()
    ids = [c["id"] for c in cats]
    assert len(ids) == len(set(ids)), "ids de categorías duplicados"
    assert "otros" in ids, "'otros' debe estar en list_categories"
    # Toda categoría en _CATEGORY_KEYS debe aparecer en FLAG_CATEGORIES
    flag_cat_ids = {c.id for c in FLAG_CATEGORIES}
    for cat_id in _CATEGORY_KEYS:
        assert cat_id in flag_cat_ids, f"Categoría '{cat_id}' en _CATEGORY_KEYS pero no en FLAG_CATEGORIES"


def test_read_current_includes_category_and_default():
    """Cada dict de read_current() tiene 'category', 'default', 'default_known', 'active'
    y 'category' pertenece a los ids de FLAG_CATEGORIES."""
    from services.harness_flags import read_current, FLAG_CATEGORIES

    valid_cat_ids = {c.id for c in FLAG_CATEGORIES}
    for d in read_current():
        assert "category" in d, f"Falta 'category' en {d['key']}"
        assert "default" in d, f"Falta 'default' en {d['key']}"
        assert "default_known" in d, f"Falta 'default_known' en {d['key']}"
        assert "active" in d, f"Falta 'active' en {d['key']}"
        assert d["category"] in valid_cat_ids, (
            f"category '{d['category']}' de {d['key']} no está en FLAG_CATEGORIES"
        )


def test_declared_default_true_set():
    """Las 12 keys curadas tienen declared_default is True y default_is_known is True."""
    from services.harness_flags import FLAG_REGISTRY, declared_default, default_is_known

    by_key = {s.key: s for s in FLAG_REGISTRY}
    for key in _CURATED_DEFAULTS_ON:
        spec = by_key[key]
        assert declared_default(spec) is True, f"{key}: declared_default debe ser True"
        assert default_is_known(spec) is True, f"{key}: default_is_known debe ser True"


def test_default_known_only_for_curated():
    """default_is_known es True SOLO para las 12 keys curadas: ni más ni menos."""
    from services.harness_flags import FLAG_REGISTRY, default_is_known

    known_keys = {s.key for s in FLAG_REGISTRY if default_is_known(s)}
    assert known_keys == _CURATED_DEFAULTS_ON, (
        f"Drift detectado.\n"
        f"Extras (no curadas): {sorted(known_keys - _CURATED_DEFAULTS_ON)}\n"
        f"Faltantes (curadas pero default_known=False): {sorted(_CURATED_DEFAULTS_ON - known_keys)}"
    )


def test_declared_default_falls_back_to_type_zero():
    """Para flags sin default explícito, declared_default devuelve el type-zero y
    default_is_known devuelve False."""
    from services.harness_flags import FLAG_REGISTRY, declared_default, default_is_known

    by_key = {s.key: s for s in FLAG_REGISTRY}
    # bool sin default → False
    bool_spec = by_key["STACKY_TASK_GATE_ENABLED"]
    assert declared_default(bool_spec) is False
    assert default_is_known(bool_spec) is False
    # int sin default → 0
    int_spec = by_key["STACKY_RUNAWAY_MAX_TURNS"]
    assert declared_default(int_spec) == 0
    assert default_is_known(int_spec) is False


def test_is_active_semantics():
    """is_active: bool→True si True; int→True si !=0 (normalización numérica C4);
    float→True si !=0.0; csv→True si no vacío."""
    from dataclasses import dataclass
    from services.harness_flags import is_active, FlagSpec

    bool_spec = FlagSpec("K_B", "bool", "L", "D", "global")
    int_spec   = FlagSpec("K_I", "int",  "L", "D", "global")
    float_spec = FlagSpec("K_F", "float","L", "D", "global")
    csv_spec   = FlagSpec("K_C", "csv",  "L", "D", "global")

    # bool
    assert is_active(bool_spec, True) is True
    assert is_active(bool_spec, False) is False
    # int
    assert is_active(int_spec, 0) is False
    assert is_active(int_spec, 2) is True
    # float (normalización numérica C4: compara como float)
    assert is_active(float_spec, 0.0) is False
    assert is_active(float_spec, 1.0) is True
    assert is_active(float_spec, "1.0") is True   # string numérico
    assert is_active(float_spec, "0.0") is False
    # csv
    assert is_active(csv_spec, "") is False
    assert is_active(csv_spec, "proj-a") is True


def test_issue_phase_comments_flag_registered_default_false():
    """Plan 77 F1 — flag STACKY_ISSUE_PHASE_COMMENTS_ENABLED registrado, env_only=False, categorizado."""
    from services.harness_flags import FLAG_REGISTRY, _CATEGORY_KEYS, categorize

    spec = next(
        (s for s in FLAG_REGISTRY if s.key == "STACKY_ISSUE_PHASE_COMMENTS_ENABLED"),
        None,
    )
    assert spec is not None, "STACKY_ISSUE_PHASE_COMMENTS_ENABLED no está en FLAG_REGISTRY"
    assert spec.type == "bool"
    # env_only=False (default): el flag es atributo de Config, visible en la UI
    assert spec.env_only is False, "env_only debe ser False para que sea editable por UI"
    # [C2] debe estar categorizado (en epicas_ado)
    category = categorize("STACKY_ISSUE_PHASE_COMMENTS_ENABLED")
    assert category == "epicas_ado", f"Categoría inesperada: {category!r}"
    assert "STACKY_ISSUE_PHASE_COMMENTS_ENABLED" in _CATEGORY_KEYS["epicas_ado"]


def test_flagspec_backward_compatible():
    """FlagSpec con construcción legacy (sin default) no rompe; default es None."""
    from services.harness_flags import FlagSpec

    spec = FlagSpec("K", "bool", "L", "D", "global")
    assert spec.default is None


# ---------------------------------------------------------------------------
# Plan 63 — F1: endpoint expone categories
# ---------------------------------------------------------------------------

def test_get_harness_flags_includes_categories(client):
    """GET /api/harness-flags incluye campo 'categories' con lista de {id, label, description}
    y el primer elemento tiene id='runtimes_cli'."""
    c, _ = client
    resp = c.get("/api/harness-flags")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert "categories" in data, "Falta 'categories' en la respuesta"
    cats = data["categories"]
    assert isinstance(cats, list) and len(cats) > 0
    for cat in cats:
        assert "id" in cat and "label" in cat and "description" in cat
    assert cats[0]["id"] == "runtimes_cli", f"Primera categoría debe ser 'runtimes_cli', got: {cats[0]['id']}"


def test_get_harness_flags_flags_have_category(client):
    """GET /api/harness-flags: cada item de 'flags' tiene category, default, default_known y active."""
    c, _ = client
    resp = c.get("/api/harness-flags")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    # Verificar que los campos existentes siguen intactos
    assert data["ok"] is True
    assert "flags" in data
    assert "active_profile" in data
    for flag in data["flags"]:
        assert "category" in flag, f"Falta 'category' en flag {flag['key']}"
        assert "default" in flag, f"Falta 'default' en flag {flag['key']}"
        assert "default_known" in flag, f"Falta 'default_known' en flag {flag['key']}"
        assert "active" in flag, f"Falta 'active' en flag {flag['key']}"


# Plan 64 F1 — tests de flags RAG en FLAG_REGISTRY
def test_rag_catalog_enabled_in_registry():
    from services.harness_flags import FLAG_REGISTRY
    keys = {s.key for s in FLAG_REGISTRY}
    assert "STACKY_RAG_CATALOG_ENABLED" in keys
    assert "STACKY_RAG_CATALOG_TOP_K" in keys


def test_rag_catalog_enabled_is_bool_off_by_default():
    from services.harness_flags import FLAG_REGISTRY
    spec = next(s for s in FLAG_REGISTRY if s.key == "STACKY_RAG_CATALOG_ENABLED")
    assert spec.type == "bool"
    assert spec.default is None  # no tiene default declarado → OFF por type-zero


def test_rag_catalog_top_k_is_int():
    from services.harness_flags import FLAG_REGISTRY
    spec = next(s for s in FLAG_REGISTRY if s.key == "STACKY_RAG_CATALOG_TOP_K")
    assert spec.type == "int"


def test_rag_flags_pair_linkage():
    from services.harness_flags import FLAG_REGISTRY
    spec = next(s for s in FLAG_REGISTRY if s.key == "STACKY_RAG_CATALOG_ENABLED")
    assert spec.pair == "STACKY_RAG_CATALOG_TOP_K"


# ---------------------------------------------------------------------------
# Plan 78 F0 — metadata tier/intent en CategorySpec
# ---------------------------------------------------------------------------

def test_every_category_has_tier_and_intent():
    """Bidireccional: toda CategorySpec declara tier válido e intent no vacío.
    Impide drift — una categoría nueva sin tier/intent rompe CI a propósito."""
    from services.harness_flags import FLAG_CATEGORIES
    valid_tiers = {"simple", "advanced"}
    for c in FLAG_CATEGORIES:
        assert c.tier in valid_tiers, f"Categoría '{c.id}' tiene tier inválido: {c.tier!r}"
        assert isinstance(c.intent, str) and c.intent.strip(), \
            f"Categoría '{c.id}' tiene intent vacío"


def test_list_categories_exposes_tier_and_intent():
    """list_categories() expone tier e intent de forma ADITIVA (sin romper id/label/description)."""
    from services.harness_flags import list_categories
    for c in list_categories():
        assert {"id", "label", "description", "tier", "intent"} <= set(c.keys())
        assert c["tier"] in {"simple", "advanced"}


def test_at_least_one_simple_and_one_advanced_category():
    """Garantiza que el modo Simple no quede vacío ni absorba todo (sanidad del diseño de niveles)."""
    from services.harness_flags import FLAG_CATEGORIES
    tiers = {c.tier for c in FLAG_CATEGORIES}
    assert "simple" in tiers, "Ninguna categoría es 'simple' → modo Simple quedaría vacío"
    assert "advanced" in tiers, "Ninguna categoría es 'advanced' → no hay catch-all que poblar"


def test_partition_semantics_simple_vs_advanced():
    """[ADICIÓN ARQUITECTO — C2] Valida que el predicado tier=='simple' y su complemento
    tier!='simple' particionan el total sin solape ni pérdida."""
    from services.harness_flags import FLAG_CATEGORIES
    all_ids = [c.id for c in FLAG_CATEGORIES]
    simple_ids = [c.id for c in FLAG_CATEGORIES if c.tier == "simple"]
    rest_ids   = [c.id for c in FLAG_CATEGORIES if c.tier != "simple"]
    # Sin solape
    assert len(set(simple_ids) & set(rest_ids)) == 0, "Solapamiento entre simple y rest — imposible por definición"
    # Sin pérdida
    assert sorted(simple_ids + rest_ids) == sorted(all_ids), \
        "La unión simple+rest != FLAG_CATEGORIES — se perdió una categoría"
