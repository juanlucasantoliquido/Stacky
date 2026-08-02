"""Plan 82 F0/F1 — Campo `requires` en FlagSpec, `requires_met`, `validate_requires_graph`.

Metadata + presentación pura: ningún runner evalúa `requires`. Ver
Stacky Agents/docs/82_PLAN_CLARIDAD_CONFIGURACION_ARNES.md.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")


# ---------------------------------------------------------------------------
# F0 — FlagSpec.requires + requires_met + validate_requires_graph + read_current
# ---------------------------------------------------------------------------

def test_flagspec_requires_default_none():
    from services.harness_flags import FlagSpec

    spec = FlagSpec("K", "bool", "L", "D", "global")
    assert spec.requires is None


def test_requires_met_none_is_true():
    from services.harness_flags import FlagSpec, requires_met

    spec = FlagSpec("K", "bool", "L", "D", "global")
    assert requires_met(spec, {}) is True


def test_requires_met_master_on():
    from services.harness_flags import FlagSpec, requires_met

    spec = FlagSpec("HIJA", "int", "L", "D", "global", requires="MASTER")
    assert requires_met(spec, {"MASTER": True}) is True


def test_requires_met_master_off():
    from services.harness_flags import FlagSpec, requires_met

    spec = FlagSpec("HIJA", "int", "L", "D", "global", requires="MASTER")
    assert requires_met(spec, {"MASTER": False}) is False
    assert requires_met(spec, {"MASTER": ""}) is False


def test_requires_met_master_missing_fail_open():
    from services.harness_flags import FlagSpec, requires_met

    spec = FlagSpec("HIJA", "int", "L", "D", "global", requires="MASTER")
    assert requires_met(spec, {}) is True


def test_validate_requires_graph_empty_registry_ok():
    from services.harness_flags import validate_requires_graph

    assert validate_requires_graph() == []


def test_read_current_exposes_requires_fields():
    from services.harness_flags import read_current

    for d in read_current():
        assert "requires" in d, f"Falta 'requires' en {d['key']}"
        assert "requires_met" in d, f"Falta 'requires_met' en {d['key']}"


# ---------------------------------------------------------------------------
# F1 — Mapa curado de dependencias (CONGELADO) + grafo válido
#
# Procedimiento aplicado a CADA fila de la tabla del plan (grep del consumidor
# real en backend/ fuera de services/harness_flags.py y tests/, lectura del
# punto exacto donde se lee la hija, verificación de que está dentro de -o
# después de- un chequeo del master). 6 de las 26 filas de la tabla original
# NO superaron la verificación y se descartan aquí con evidencia:
#
# descartado Plan 82 F1: STACKY_RUN_ADVISOR_ENFORCE — el endpoint
#   GET /api/agents/advise (api/agents.py:318-333) llama run_advisor.advise()
#   sin leer STACKY_RUN_ADVISOR_ENABLED ni STACKY_RUN_ADVISOR_ENFORCE en
#   ningún punto del backend; services/run_advisor.py tampoco los referencia.
#   No hay gating verificable.
#
# descartado Plan 82 F1: STACKY_CRITERIA_REPAIR_MAX_RETRIES — el llamador
#   real (services/claude_code_cli_runner.py:908-914) pasa
#   retries_budget=config.CLAUDE_CODE_CLI_AUTOCORRECT_MAX_RETRIES a
#   attempt_criteria_repair(), NO STACKY_CRITERIA_REPAIR_MAX_RETRIES. Esa key
#   nunca se lee como valor en ningún módulo (solo existe en config.py/
#   harness_flags.py). Hija sin consumidor real.
#
# descartado Plan 82 F1: STACKY_TRANSIENT_RUN_RETRY_MAX — G2.2 está
#   explícitamente DIFERIDO (tests/test_transient_run_retry.py documenta
#   `test_no_retry_module_exists`: no existe services.transient_retry). No
#   hay ningún consumidor que leer.
#
# descartado Plan 82 F1: STACKY_FAKE_GREEN_GUARD_HARD — su master declarado,
#   STACKY_FAKE_GREEN_GUARD_ENABLED, NUNCA se lee en el código (grep sin
#   resultados fuera de config.py/harness_flags.py). FakeGreenGuard corre
#   incondicionalmente dentro de _VERIFIERS (services/exec_verification.py:495),
#   gateado únicamente por el STACKY_EXEC_VERIFICATION_ENABLED del pipeline
#   padre — no por el master que la tabla proponía. No se puede verificar la
#   relación hija→master declarada.
#
# descartado Plan 82 F1: STACKY_MIGRATOR_EPIC_POLICY — el valor de config
#   nunca se lee en services/migrator_core.py ni api/migrator.py (solo existe
#   un parámetro homónimo `epic_policy` en el body de POST /api/migrator/plan
#   que ni siquiera se extrae de `data`). Sin lectura real que verificar.
#
# descartado Plan 82 F1: STACKY_ACCEPTANCE_REPAIR_MAX_RETRIES —
#   attempt_acceptance_repair() (services/acceptance_gate.py:140-148) no
#   tiene parámetro de cap de reintentos: hace un único pase correctivo
#   hardcodeado. El caller (harness/post_run.py:271-279) pasa
#   budget_remaining=STACKY_EXEC_VERIFICATION_BUDGET_S, no esta key. Hija
#   sin consumidor real.
# ---------------------------------------------------------------------------

_REQUIRES_MAP_FROZEN = {
    # Plan 264: la paridad de effort en Codex, la preferencia por proyecto y el
    # selector unico solo tienen sentido si la matriz unica de capacidades esta
    # activa (es quien resuelve y clampea). Profundidad 1: la madre
    # STACKY_RUNTIME_CAPABILITIES_ENABLED no declara requires (R4).
    "STACKY_CODEX_EFFORT_PARITY_ENABLED": "STACKY_RUNTIME_CAPABILITIES_ENABLED",
    "STACKY_RUN_SELECTION_PREFS_ENABLED": "STACKY_RUNTIME_CAPABILITIES_ENABLED",
    "STACKY_MODEL_PICKER_EVERYWHERE_ENABLED": "STACKY_RUNTIME_CAPABILITIES_ENABLED",
    # Plan 258: la lista de nombres de prueba y la limpieza destructiva solo
    # tienen efecto por el camino que abre la inferencia de procedencia (sin
    # ella nada queda marcado como 'test', asi que no habria ni que filtrar ni
    # que borrar). Profundidad 1: la madre no declara requires (R4).
    "STACKY_LEDGER_TEST_MARKERS": "STACKY_LEDGER_LEGACY_INFERENCE_ENABLED",
    "STACKY_LEDGER_PURGE_ENABLED": "STACKY_LEDGER_LEGACY_INFERENCE_ENABLED",
    # Plan 257: los parametros del agrupado de mensajes repetidos solo se leen
    # desde el camino que abre su master, y los de rotacion por tamano desde el
    # suyo. Profundidad 1: ninguno de los dos masters declara requires (R4).
    "STACKY_LOG_THROTTLE_WINDOW_S": "STACKY_LOG_THROTTLE_ENABLED",
    "STACKY_LOG_THROTTLE_MAX_SIGNATURES": "STACKY_LOG_THROTTLE_ENABLED",
    "STACKY_LOG_THROTTLE_FLUSH_S": "STACKY_LOG_THROTTLE_ENABLED",
    "STACKY_LOG_MAX_BYTES": "STACKY_LOG_SIZE_ROTATION_ENABLED",
    "STACKY_LOG_MAX_PARTS_PER_DAY": "STACKY_LOG_SIZE_ROTATION_ENABLED",
    # Plan 202: el techo de gasto solo se lee desde el camino que abre el master de
    # la Fragua; sin la arista, tocarlo con la Fragua apagada no haría nada.
    "STACKY_NIGHT_FOUNDRY_TOKEN_BUDGET": "STACKY_NIGHT_FOUNDRY_ENABLED",
    # Plan 196: los botones del pipeline viven DENTRO del Tablero de Planes; sin
    # la arista, acciones ON + tablero OFF dejaria endpoints sin superficie.
    "STACKY_PLANS_PIPELINE_ACTIONS_ENABLED": "STACKY_PLANS_BOARD_ENABLED",
    # Plan 214: el autorun vive DENTRO del hook gateado por la otra flag; sin la
    # arista, autorun ON + encolado OFF sería un no-op mudo.
    "STACKY_QA_UAT_AUTORUN_ENABLED": "STACKY_QA_UAT_ON_DEV_COMPLETE_ENABLED",
    # Plan 213: la allowlist y el techo solo se leen desde el camino que abre la
    # flag madre; sin la arista, tocarlos con el modo OFF no haría nada.
    "STACKY_ASSUMPTION_MODE_AGENT_TYPES": "STACKY_ASSUMPTION_MODE_ENABLED",
    "STACKY_ASSUMPTION_MAX_PER_RUN": "STACKY_ASSUMPTION_MODE_ENABLED",
    # Plan 199: las 4 hijas de la cosecha cuelgan del master (profundidad 1).
    "STACKY_TELEMETRY_HARVEST_AUTOSCAN_ENABLED": "STACKY_TELEMETRY_HARVEST_ENABLED",
    "STACKY_TELEMETRY_HARVEST_ATTRIBUTED_ONLY": "STACKY_TELEMETRY_HARVEST_ENABLED",
    "STACKY_TELEMETRY_HARVEST_LOOKBACK_DAYS": "STACKY_TELEMETRY_HARVEST_ENABLED",
    "STACKY_TELEMETRY_HARVEST_ROOTS_JSON": "STACKY_TELEMETRY_HARVEST_ENABLED",
    # Plan 200: consola y detector cuelgan del resolutor de incidencias; bitácora
    # y ejecución, del master del comparador (que es quien tiene los ambientes).
    "STACKY_INCIDENT_CONSOLE_ENABLED": "STACKY_INCIDENT_RESOLVER_ENABLED",
    "STACKY_SQL_DEPLOY_DETECT_ENABLED": "STACKY_INCIDENT_RESOLVER_ENABLED",
    "STACKY_SQL_EXEC_LEDGER_ENABLED": "STACKY_DB_COMPARE_ENABLED",
    "STACKY_SQL_EXEC_ENABLED": "STACKY_DB_COMPARE_ENABLED",
    # Plan 176: las 4 capas nuevas del comparador cuelgan del master (profundidad 1).
    "STACKY_DB_COMPARE_TRIAGE_ENABLED": "STACKY_DB_COMPARE_ENABLED",
    "STACKY_DB_COMPARE_GATES_ENABLED": "STACKY_DB_COMPARE_ENABLED",
    "STACKY_DB_COMPARE_TABLE_PREFS_ENABLED": "STACKY_DB_COMPARE_ENABLED",
    "STACKY_DB_COMPARE_DIFF_UX_V2_ENABLED": "STACKY_DB_COMPARE_ENABLED",
    # Plan 171: las 2 hijas de telemetría operativa apuntan al ROOT (profundidad 1);
    # la master STACKY_OPS_TELEMETRY_ENABLED no declara arista.
    "STACKY_OPS_BASELINE_ENABLED": "STACKY_OPS_TELEMETRY_ENABLED",
    "STACKY_OPS_TRACE_ENABLED": "STACKY_OPS_TELEMETRY_ENABLED",
    "CLAUDE_CODE_CLI_AUTOCORRECT_MAX_RETRIES": "CLAUDE_CODE_CLI_AUTOCORRECT_ENABLED",
    "CODEX_CLI_AUTOCORRECT_MAX_RETRIES": "CODEX_CLI_AUTOCORRECT_ENABLED",
    "STACKY_CONTEXT_BUDGET_TOKENS": "STACKY_CONTEXT_BUDGET_ENABLED",
    "STACKY_CLI_FEWSHOT_K": "STACKY_CLI_FEWSHOT_ENABLED",
    # Plan 87: la master del panel NO declara requires (supervisión 2026-07-05 — la
    # arista PANEL→GENERATOR violaba R4/profundidad-1 al sumar las hijas de la serie
    # §3.12 y contradecía la degradación por FlagGateBanner del propio 87).
    # Serie DevOps §3.12 (87 v3): cada sección hija requiere la flag master del panel.
    "STACKY_DEVOPS_PUBLICATIONS_ENABLED": "STACKY_DEVOPS_PANEL_ENABLED",  # Plan 88
    "STACKY_DEVOPS_ENVIRONMENTS_ENABLED": "STACKY_DEVOPS_PANEL_ENABLED",  # Plan 89
    "STACKY_DEVOPS_AGENT_ENABLED": "STACKY_DEVOPS_PANEL_ENABLED",  # Plan 90
    "STACKY_DEVOPS_SERVERS_ENABLED": "STACKY_DEVOPS_PANEL_ENABLED",  # Plan 91
    "STACKY_DEVOPS_PREFLIGHT_ENABLED": "STACKY_DEVOPS_PANEL_ENABLED",  # Plan 93
    "STACKY_DEVOPS_VARIABLES_ENABLED": "STACKY_DEVOPS_PANEL_ENABLED",  # Plan 94
    "STACKY_DEVOPS_PRODUCTION_ENABLED": "STACKY_DEVOPS_PANEL_ENABLED",  # Plan 95
    "STACKY_DEVOPS_STACK_DETECT_ENABLED": "STACKY_DEVOPS_PANEL_ENABLED",  # Plan 97
    "STACKY_DEVOPS_DOCTOR_ENABLED": "STACKY_DEVOPS_PANEL_ENABLED",  # Plan 96
    # Plan 104: el doc pedía requires=AGENT_ENABLED pero esa flag ya tiene requires
    # propio (línea de arriba) -- encadenar rompe R4 (profundidad 1). Se usa el
    # mismo master que las hermanas; el guard funcional de AGENT_ENABLED vive en
    # el endpoint (api/devops_section_doctor.py), no en el grafo de flags.
    "STACKY_DEVOPS_SECTION_DOCTOR_ENABLED": "STACKY_DEVOPS_PANEL_ENABLED",  # Plan 104
    "STACKY_DEVOPS_BOOTSTRAP_ENABLED": "STACKY_DEVOPS_PANEL_ENABLED",  # Plan 98
    "STACKY_DEVOPS_PIPELINE_MONITOR_ENABLED": "STACKY_DEVOPS_PANEL_ENABLED",  # Plan 103
    "STACKY_DEVOPS_ONE_CLICK_PUBLISH_ENABLED": "STACKY_DEVOPS_PANEL_ENABLED",  # Plan 102 (R4: PANEL, no PUBLICATIONS)
    "STACKY_DEVOPS_REMOTE_CONSOLE_ENABLED": "STACKY_DEVOPS_PANEL_ENABLED",  # Plan 105
    "STACKY_DEVOPS_REMOTE_TARGET_ENABLED": "STACKY_DEVOPS_PANEL_ENABLED",  # Plan 108
    "STACKY_DEVOPS_ENV_TREE_PREVIEW_ENABLED": "STACKY_DEVOPS_PANEL_ENABLED",  # Plan 107
    "STACKY_DEVOPS_ENV_SANDBOX_ENABLED": "STACKY_DEVOPS_PANEL_ENABLED",  # Plan 107
    "STACKY_EXEC_VERIFICATION_MODE": "STACKY_EXEC_VERIFICATION_ENABLED",
    "STACKY_EXEC_VERIFICATION_TIMEOUT_S": "STACKY_EXEC_VERIFICATION_ENABLED",
    "STACKY_EXEC_VERIFICATION_BUDGET_S": "STACKY_EXEC_VERIFICATION_ENABLED",
    "STACKY_EXEC_REPAIR_MAX_RETRIES": "STACKY_EXEC_REPAIR_ENABLED",
    "STACKY_ACCEPTANCE_CONTRACT_MODE": "STACKY_ACCEPTANCE_CONTRACT_ENABLED",
    "STACKY_ACCEPTANCE_CONTRACT_MAX_CHECKS": "STACKY_ACCEPTANCE_CONTRACT_ENABLED",
    "STACKY_RAG_CATALOG_TOP_K": "STACKY_RAG_CATALOG_ENABLED",
    "STACKY_DOCS_RAG_HYBRID_ALPHA": "STACKY_DOCS_RAG_HYBRID_ENABLED",  # Plan 112
    "STACKY_DOCS_RAG_HYBRID_BETA": "STACKY_DOCS_RAG_HYBRID_ENABLED",  # Plan 112
    "STACKY_DOCS_RAG_HYBRID_MAX_NEIGHBORS": "STACKY_DOCS_RAG_HYBRID_ENABLED",  # Plan 112
    "STACKY_DOCS_DOCUMENTER_MAX_FILES": "STACKY_DOCS_DOCUMENTER_ENABLED",  # Plan 113
    "STACKY_DOCS_DOCUMENTER_V2_ENABLED": "STACKY_DOCS_DOCUMENTER_ENABLED",  # Plan 137
    "STACKY_DOCS_DOCUMENTER_EVIDENCE_MAX_CHARS": "STACKY_DOCS_DOCUMENTER_ENABLED",  # Plan 137
    "STACKY_DOCS_STALENESS_ENABLED": "STACKY_DOCS_GRAPH_ENABLED",  # Plan 114
    # Plan 285 F0.1 — saldo del rojo de fabrica que dejo el plan 284.
    # Estas 11 keys ya estaban en FLAG_REGISTRY con su `requires`, pero nadie
    # las agrego aca: el test comparaba por IGUALDAD y quedo `1 failed, 8 passed`
    # desde el 284. Un ratchet rojo no protege nada — cualquier dano nuevo se
    # esconde en el mismo mensaje de error. Se saldan ANTES de registrar las
    # flags del 285 para que su rojo vuelva a ser una senal util.
    # OJO: estas dos cuelgan del GRAFO, no del Documentador. El mensaje de
    # error del test lista keys pero NO valores, asi que copiar el `requires`
    # de las vecinas deja el test rojo con "Extras: [] / Faltantes: []" —
    # completamente indiagnostico. Los valores salen del FLAG_REGISTRY.
    "STACKY_DOCS_TAXONOMY_ENABLED": "STACKY_DOCS_GRAPH_ENABLED",  # Plan 284
    "STACKY_DOCS_RADIOGRAPHY_ENABLED": "STACKY_DOCS_GRAPH_ENABLED",  # Plan 284
    "STACKY_DOCS_TICKET_MINING_ENABLED": "STACKY_DOCS_DOCUMENTER_ENABLED",  # Plan 284
    "STACKY_DOCS_TICKET_MINING_MAX": "STACKY_DOCS_DOCUMENTER_ENABLED",  # Plan 284
    "STACKY_DOCS_CITATION_GATE_ENABLED": "STACKY_DOCS_DOCUMENTER_ENABLED",  # Plan 284
    "STACKY_DOCS_CITATION_GATE_MIN_RATIO": "STACKY_DOCS_DOCUMENTER_ENABLED",  # Plan 284
    "STACKY_DOCS_OPERATOR_NOTE_ENABLED": "STACKY_DOCS_DOCUMENTER_ENABLED",  # Plan 284
    "STACKY_DOCS_OPERATOR_NOTE_MAX_CHARS": "STACKY_DOCS_DOCUMENTER_ENABLED",  # Plan 284
    "STACKY_DOCS_PIPELINE_STAGES_ENABLED": "STACKY_DOCS_DOCUMENTER_ENABLED",  # Plan 284
    "STACKY_DOCS_PIPELINE_AUTOAPPLY": "STACKY_DOCS_DOCUMENTER_ENABLED",  # Plan 284
    "STACKY_DOCS_PIPELINE_MAX_LLM_CALLS": "STACKY_DOCS_DOCUMENTER_ENABLED",  # Plan 284
    # Plan 285 — las 9 flags del corpus vivo / rigor por afirmacion. El mapa
    # esta indexado por KEY DE FLAG: reusar un `requires` que ya existe NO exime
    # de agregar la key nueva. Registrado en los DOS ratchets => trampa de COMMIT.
    "STACKY_DOCS_CORPUS_AUTOINDEX_ENABLED": "STACKY_DOCS_DOCUMENTER_ENABLED",  # Plan 285
    "STACKY_DOCS_CORPUS_RETRIEVAL_ENABLED": "STACKY_DOCS_DOCUMENTER_ENABLED",  # Plan 285
    "STACKY_DOCS_CORPUS_ORPHANS_ENABLED": "STACKY_DOCS_DOCUMENTER_ENABLED",  # Plan 285
    "STACKY_DOCS_CORPUS_PURGE_ENABLED": "STACKY_DOCS_DOCUMENTER_ENABLED",  # Plan 285
    "STACKY_DOCS_RIGOR_PER_CLAIM_ENABLED": "STACKY_DOCS_DOCUMENTER_ENABLED",  # Plan 285
    "STACKY_DOCS_RIGOR_MIN_DENSITY": "STACKY_DOCS_DOCUMENTER_ENABLED",  # Plan 285
    "STACKY_DOCS_RIGOR_MIN_CITATIONS": "STACKY_DOCS_DOCUMENTER_ENABLED",  # Plan 285
    "STACKY_DOCS_TICKET_TRIAGE_VISIBLE_ENABLED": "STACKY_DOCS_DOCUMENTER_ENABLED",  # Plan 285
    "STACKY_DOCS_TREE_GROUP_BY_CLASS_ENABLED": "STACKY_DOCS_DOCUMENTER_ENABLED",  # Plan 285
    "STACKY_DEVOPS_CONNECTION_DOCTOR_ENABLED": "STACKY_DEVOPS_PANEL_ENABLED",  # Plan 116
    "STACKY_LOCAL_INSIGHTS_SWEEP_SEC": "STACKY_LOCAL_INSIGHTS_ENABLED",  # Plan 117
    "STACKY_LOCAL_INSIGHTS_MAX_PER_CYCLE": "STACKY_LOCAL_INSIGHTS_ENABLED",  # Plan 117
    "STACKY_LOCAL_INSIGHTS_LOOKBACK_DAYS": "STACKY_LOCAL_INSIGHTS_ENABLED",  # Plan 117
    "STACKY_LOCAL_INSIGHTS_DIGEST_NARRATIVE_ENABLED": "STACKY_LOCAL_INSIGHTS_ENABLED",  # Plan 117
    "INTENT_PREFLIGHT_AUTO_APPROVE": "INTENT_PREFLIGHT_ENABLED",
    "INTENT_PREFLIGHT_AUTO_APPROVE_MIN_CONF": "INTENT_PREFLIGHT_ENABLED",
    "STACKY_TASK_GATE_BLOCKING": "STACKY_TASK_GATE_ENABLED",
    "STACKY_QUALITY_CONVERGENCE_MAX_ITERATIONS": "STACKY_QUALITY_CONVERGENCE_ENABLED",
    "STACKY_ADO_EDIT_SWEEP_HOURS": "STACKY_ADO_EDIT_LEARNING_ENABLED",
    "STACKY_CODEBASE_MEMORY_MCP_BINARY_PATH": "STACKY_CODEBASE_MEMORY_MCP_ENABLED",
    "STACKY_CODEBASE_MEMORY_MCP_PROJECTS": "STACKY_CODEBASE_MEMORY_MCP_ENABLED",
    "STACKY_EPIC_CATALOG_GATE_ENABLED": "STACKY_EPIC_GATE_ENABLED",
    "LOCAL_LLM_ENDPOINT": "LOCAL_LLM_ENABLED",  # Plan 106
    "LOCAL_LLM_MODEL": "LOCAL_LLM_ENABLED",  # Plan 106
    "LOCAL_LLM_TIMEOUT_SEC": "LOCAL_LLM_ENABLED",  # Plan 106
    "STACKY_PR_REVIEWER_ENABLED": "STACKY_DEVOPS_PANEL_ENABLED",       # Plan 110
    "STACKY_PR_REVIEW_HAIKU_MODEL": "STACKY_DEVOPS_PANEL_ENABLED",     # Plan 110
    "STACKY_PR_REVIEW_DIFF_MAX_CHARS": "STACKY_DEVOPS_PANEL_ENABLED",  # Plan 110
    "STACKY_PR_REVIEW_LOCAL_DIFF_MAX_CHARS": "STACKY_DEVOPS_PANEL_ENABLED",  # Plan 110 v2.1
    "STACKY_PR_REVIEW_TIMEOUT_SEC": "STACKY_DEVOPS_PANEL_ENABLED",     # Plan 110
    "STACKY_DB_COMPARE_CONNECT_TIMEOUT_SEC": "STACKY_DB_COMPARE_ENABLED",  # Plan 122
    "STACKY_DB_COMPARE_DATA_DIFF_ENABLED": "STACKY_DB_COMPARE_ENABLED",  # Plan 126
    "STACKY_DB_COMPARE_DATA_MAX_ROWS": "STACKY_DB_COMPARE_ENABLED",  # Plan 126
    "STACKY_DB_COMPARE_CONFIG_IN_PLACE_ENABLED": "STACKY_DB_COMPARE_ENABLED",  # Plan 157
    "STACKY_DB_COMPARE_WEBCONFIG_IMPORT_ENABLED": "STACKY_DB_COMPARE_ENABLED",  # Plan 157
    "STACKY_DB_COMPARE_MIGRATION_PANEL_ENABLED": "STACKY_DB_COMPARE_ENABLED",  # Plan 157
    "STACKY_DB_COMPARE_DEMO_ENABLED": "STACKY_DB_COMPARE_ENABLED",  # Plan 183
    "STACKY_DB_COMPARE_SNAPSHOT_V2_ENABLED": "STACKY_DB_COMPARE_ENABLED",  # Plan 179
    "STACKY_DB_COMPARE_DATA_MERGE_ENABLED": "STACKY_DB_COMPARE_ENABLED",  # Plan 182
    "STACKY_DB_COMPARE_MASKING_ENABLED": "STACKY_DB_COMPARE_ENABLED",  # Plan 181
    "STACKY_DB_COMPARE_RADAR_ENABLED": "STACKY_DB_COMPARE_ENABLED",  # Plan 178
    "STACKY_DB_COMPARE_WATCH_INTERVAL_MIN": "STACKY_DB_COMPARE_ENABLED",  # Plan 178
    "STACKY_DB_COMPARE_WATCH_MAX_RUNS_PER_DAY": "STACKY_DB_COMPARE_ENABLED",  # Plan 178
    "STACKY_DB_COMPARE_REPO_BRIDGE_ENABLED": "STACKY_DB_COMPARE_ENABLED",  # Plan 180
    "STACKY_DB_COMPARE_REPO_BRIDGE_GLOBS": "STACKY_DB_COMPARE_ENABLED",  # Plan 180
    "STACKY_DB_COMPARE_REPO_BRIDGE_MAX_FILES": "STACKY_DB_COMPARE_ENABLED",  # Plan 180
    "CLAUDE_CODE_CLI_TRUST_AUTOSET_ENABLED": "CLAUDE_CODE_CLI_TRUST_PREFLIGHT_ENABLED",  # Plan 144 F3
    # Drift preexistente destrabado al implementar Plan 144 (ajeno a este plan):
    # Plan 142 F7 declaraba requires= pero nunca sumó la arista acá.
    "STACKY_COST_CODEBURN_IMPORT_PATH": "STACKY_COST_CODEBURN_IMPORT_ENABLED",  # Plan 142
    "STACKY_DEVOPS_UI_V2_ENABLED": "STACKY_DEVOPS_PANEL_ENABLED",  # Plan 119
    "STACKY_DEVOPS_COCKPIT_ENABLED": "STACKY_DEVOPS_PANEL_ENABLED",  # Plan 239
    "STACKY_DEPLOYMENTS_ENABLED": "STACKY_DEVOPS_PANEL_ENABLED",  # Plan 120
    "STACKY_DEPLOYMENTS_EXECUTE_ENABLED": "STACKY_DEVOPS_PANEL_ENABLED",  # Plan 120
    "STACKY_DEPLOYMENTS_AI_DIAGNOSIS_ENABLED": "STACKY_DEVOPS_PANEL_ENABLED",  # Plan 120
    "STACKY_DEPLOYMENTS_RETAIN_RELEASES": "STACKY_DEVOPS_PANEL_ENABLED",  # Plan 120
    "STACKY_DEPLOYMENTS_SMOKE_TIMEOUT_SEC": "STACKY_DEVOPS_PANEL_ENABLED",  # Plan 120
    "STACKY_EGRESS_SENTINEL_MAX_PER_CYCLE": "STACKY_EGRESS_SENTINEL_ENABLED",  # Plan 121
    "STACKY_EGRESS_SENTINEL_LOOKBACK_DAYS": "STACKY_EGRESS_SENTINEL_ENABLED",  # Plan 121
    "STACKY_EGRESS_SENTINEL_MAX_CHARS": "STACKY_EGRESS_SENTINEL_ENABLED",  # Plan 121
    "STACKY_DEVOPS_LOCAL_DOCTOR_ENABLED": "STACKY_DEVOPS_PANEL_ENABLED",  # Plan 127
    "STACKY_INCIDENT_TICKET_PERSIST_ENABLED": "STACKY_INCIDENT_RESOLVER_ENABLED",  # Plan 166
    "STACKY_INCIDENT_VISION_OCR_ENABLED": "STACKY_INCIDENT_RESOLVER_ENABLED",  # Plan 166
    # ENDPOINT/MODEL apuntan al ROOT (no a VISION_OCR_ENABLED): R4 prohíbe
    # cadenas de profundidad >1 y VISION_OCR_ENABLED ya tiene su propio requires.
    "STACKY_INCIDENT_VISION_ENDPOINT": "STACKY_INCIDENT_RESOLVER_ENABLED",  # Plan 166
    "STACKY_INCIDENT_VISION_MODEL": "STACKY_INCIDENT_RESOLVER_ENABLED",  # Plan 166
    "STACKY_INCIDENT_AUTO_PUBLISH_ENABLED": "STACKY_INCIDENT_RESOLVER_ENABLED",  # Plan 166
    "STACKY_INCIDENT_DEV_PR_ENABLED": "STACKY_INCIDENT_DEV_RESOLVER_ENABLED",  # Plan 177
    # Acciones de la bandeja: apuntan al ROOT del 238 (G8/R4 profundidad 1). Los
    # gates de agente/PR los sigue evaluando el propio /api/incidents/status.
    "STACKY_INCIDENT_INBOX_ACTIONS_ENABLED": "STACKY_INCIDENT_INBOX_ENABLED",
    # Plan 167 — Centro de Evolución: las 3 hijas apuntan al ROOT (G8/R4 profundidad 1).
    "STACKY_EVOLUTION_CYCLE_ENABLED": "STACKY_EVOLUTION_CENTER_ENABLED",  # Plan 167
    "STACKY_EVOLUTION_AUTO_APPLY_KNOWLEDGE_ENABLED": "STACKY_EVOLUTION_CENTER_ENABLED",  # Plan 167
    "STACKY_EVOLUTION_CYCLE_TOKEN_BUDGET": "STACKY_EVOLUTION_CENTER_ENABLED",  # Plan 167
    # Plan 168 — Arnés de fitness: las 3 hijas apuntan al ROOT del 167 (G8/R4 profundidad 1).
    "STACKY_EVAL_HARNESS_ENABLED": "STACKY_EVOLUTION_CENTER_ENABLED",  # Plan 168
    "STACKY_EVAL_JUDGE_ENABLED": "STACKY_EVOLUTION_CENTER_ENABLED",  # Plan 168
    "STACKY_EVAL_RUN_TOKEN_BUDGET": "STACKY_EVOLUTION_CENTER_ENABLED",  # Plan 168
    # Plan 169 — Optimizador evolutivo: las 5 hijas apuntan al ROOT del 167 (G8/R4 profundidad 1).
    "STACKY_EVOLUTION_OPTIMIZER_ENABLED": "STACKY_EVOLUTION_CENTER_ENABLED",  # Plan 169
    "STACKY_EVOLUTION_OPTIMIZER_GENERATOR": "STACKY_EVOLUTION_CENTER_ENABLED",  # Plan 169
    "STACKY_EVOLUTION_OPTIMIZER_VARIANTS": "STACKY_EVOLUTION_CENTER_ENABLED",  # Plan 169
    "STACKY_EVOLUTION_OPTIMIZER_TOKEN_BUDGET": "STACKY_EVOLUTION_CENTER_ENABLED",  # Plan 169
    "STACKY_EVOLUTION_OPTIMIZER_MIN_MARGIN_PCT": "STACKY_EVOLUTION_CENTER_ENABLED",  # Plan 169
    "STACKY_KNOWLEDGE_FLYWHEEL_ENABLED": "STACKY_EVOLUTION_CENTER_ENABLED",  # Plan 170
    "STACKY_KNOWLEDGE_INJECTION_ENABLED": "STACKY_EVOLUTION_CENTER_ENABLED",  # Plan 170
    "STACKY_KNOWLEDGE_INJECT_TOP_N": "STACKY_EVOLUTION_CENTER_ENABLED",  # Plan 170
    "STACKY_KNOWLEDGE_INJECT_MAX_CHARS": "STACKY_EVOLUTION_CENTER_ENABLED",  # Plan 170
    "STACKY_KNOWLEDGE_MAX_LESSONS": "STACKY_EVOLUTION_CENTER_ENABLED",  # Plan 170
    "STACKY_DEVOPS_PIPELINE_LINT_ENABLED": "STACKY_DEVOPS_PANEL_ENABLED",  # Plan 186
    "STACKY_DEVOPS_FAILURE_EVIDENCE_ENABLED": "STACKY_DEVOPS_PANEL_ENABLED",  # Plan 188
    "STACKY_DEVOPS_ROLLBACK_READINESS_ENABLED": "STACKY_DEVOPS_PANEL_ENABLED",  # Plan 189
    "STACKY_CI_RUN_LEDGER_ENABLED": "STACKY_PIPELINE_TRIGGER_ENABLED",  # Plan 191
    "STACKY_CI_FAILURE_TRIAGE_ENABLED": "STACKY_PIPELINE_TRIGGER_ENABLED",  # Plan 193
    "STACKY_DEVOPS_ENV_APPLY_LEDGER_ENABLED": "STACKY_DEVOPS_PANEL_ENABLED",  # Plan 198
    # Drift PREEXISTENTE detectado al implementar el plan 239 (ajeno a este plan):
    # el plan 237 declaró requires= en la FlagSpec pero nunca sumó la arista acá,
    # dejando test_requires_map_is_frozen en rojo desde su commit.
    "STACKY_EVOLUTION_PLANS_TRIAGE_ENABLED": "STACKY_EVOLUTION_CENTER_ENABLED",  # Plan 237
    # Plan 250: el commit al repo REAL cuelga del panel de edición (profundidad 1; la
    # madre no declara `requires`). La arista es INFORMATIVA para la UI — el candado 0
    # de api/pipeline_editor.py chequea las dos flags por su cuenta.
    "STACKY_PIPELINE_NL_EDIT_COMMIT_ENABLED": "STACKY_PIPELINE_NL_EDIT_ENABLED",
    # Plan 251: la matriz de entornos cuelga del master del panel DevOps (profundidad 1).
    "STACKY_PIPELINE_ENV_MATRIX_ENABLED": "STACKY_DEVOPS_PANEL_ENABLED",
    # ── Costura de flags de la OLA 1 (paquete P0, 2026-07-28) ───────────────
    # Las 3 UNICAS aristas `requires` de los 15 flags pre-declarados. Los planes
    # 259, 269 y 270 no declaran ninguna (el 269 de forma deliberada: resuelve la
    # dependencia EN CODIGO, no en el registro), asi que este mapa solo crece 3.
    # Profundidad 1 verificada (R4) en las dos madres: ni
    # STACKY_DEVOPS_ACTION_CATALOG_ENABLED ni STACKY_DOCS_GRAPH_ENABLED declaran
    # `requires`, asi que no se forma cadena.
    #
    # Plan 267: interpretar la frase y ejecutar la accion cuelgan del catalogo
    # (es una ESTRELLA, no una cadena: las dos apuntan a la misma madre).
    "STACKY_DEVOPS_ACTION_NL_ENABLED": "STACKY_DEVOPS_ACTION_CATALOG_ENABLED",
    "STACKY_DEVOPS_AGENT_ACTION_RUN_ENABLED": "STACKY_DEVOPS_ACTION_CATALOG_ENABLED",
    # Plan 279: el copiloto y su commit cuelgan del MISMO catalogo (estrella, no
    # cadena). Profundidad 1 verificada: STACKY_DEVOPS_ACTION_CATALOG_ENABLED no
    # declara `requires`.
    "STACKY_PIPELINE_COPILOT_ENABLED": "STACKY_DEVOPS_ACTION_CATALOG_ENABLED",
    "STACKY_PIPELINE_COPILOT_COMMIT_ENABLED": "STACKY_DEVOPS_ACTION_CATALOG_ENABLED",
    # Plan 268: el explorador solo tiene sentido si el grafo documental existe.
    "STACKY_DOCS_GRAPH_EXPLORER_ENABLED": "STACKY_DOCS_GRAPH_ENABLED",
    # Plan 266: la forma garantizada del summary cuelga del master del Comparador
    # (profundidad 1: STACKY_DB_COMPARE_ENABLED no declara `requires`, no hay cadena).
    "STACKY_DB_COMPARE_SUMMARY_SHAPE_ENABLED": "STACKY_DB_COMPARE_ENABLED",
    # Plan 260: las 3 cuelgan del master del panel DevOps o del disparo (profundidad 1).
    "STACKY_PIPELINE_ENV_DECLARE_ENABLED": "STACKY_DEVOPS_PANEL_ENABLED",
    "STACKY_PIPELINE_TRIGGER_ENV_GATE_ENABLED": "STACKY_PIPELINE_TRIGGER_ENABLED",
    "STACKY_PIPELINE_SECRET_COMMIT_GATE_ENABLED": "STACKY_DEVOPS_PANEL_ENABLED",
    # Plan 263: las tres capas del tablero de planes cuelgan del master del tablero
    # (profundidad 1; STACKY_PLANS_BOARD_ENABLED no declara `requires`). El candado
    # real "APPLY exige PREVIEW" lo chequea api/plans_board.py por su cuenta (patron
    # del Plan 250): la arista es INFORMATIVA para la UI.
    "STACKY_PLANS_ESTADO_FALLBACK_ENABLED": "STACKY_PLANS_BOARD_ENABLED",
    "STACKY_PLANS_NORMALIZE_PREVIEW_ENABLED": "STACKY_PLANS_BOARD_ENABLED",
    "STACKY_PLANS_NORMALIZE_APPLY_ENABLED": "STACKY_PLANS_BOARD_ENABLED",
    # Plan 265: las 3 hijas de la consola cuelgan del master de pantalla completa
    # (profundidad 1; el master NO declara requires).
    "STACKY_CONSOLE_RICH_RENDER_ENABLED": "STACKY_CONSOLE_FULLSCREEN_ENABLED",
    "STACKY_CONSOLE_REPO_PANEL_ENABLED": "STACKY_CONSOLE_FULLSCREEN_ENABLED",
    "STACKY_CONSOLE_AUDIT_LOG_ENABLED": "STACKY_CONSOLE_FULLSCREEN_ENABLED",
    # Plan 283: las 4 hijas del módulo de reuniones cuelgan del master
    # (profundidad 1; el master NO declara requires). R2 mira el tipo del
    # MASTER, no el de la hija, así que las 2 `str` son aristas legales.
    "STACKY_MEETINGS_GRAPH_ENABLED": "STACKY_MEETINGS_ENABLED",
    "STACKY_MEETINGS_PUBLISH_ENABLED": "STACKY_MEETINGS_ENABLED",
    "STACKY_MEETINGS_GRAPH_TENANT": "STACKY_MEETINGS_ENABLED",
    "STACKY_MEETINGS_GRAPH_CLIENT_ID": "STACKY_MEETINGS_ENABLED",
    # Plan 294: las 2 hijas de escritura del asistente guiado. Profundidad 1 en
    # los dos casos y ninguna madre declara `requires` (R4). La primera cuelga
    # del propio asistente; la segunda cuelga del disparo de pipelines, que es
    # quien de verdad la habilita (mandar variables sin poder disparar no
    # significa nada). Las aristas son INFORMATIVAS para la UI: cada guard
    # chequea sus flags por su cuenta.
    "STACKY_PIPELINE_WIZARD_COMMIT_ENABLED": "STACKY_PIPELINE_WIZARD_ENABLED",
    "STACKY_PIPELINE_TRIGGER_VARS_ENABLED": "STACKY_PIPELINE_TRIGGER_ENABLED",
}


def test_requires_map_is_frozen():
    from services.harness_flags import FLAG_REGISTRY

    actual = {s.key: s.requires for s in FLAG_REGISTRY if s.requires}
    assert actual == _REQUIRES_MAP_FROZEN, (
        f"Drift detectado en el mapa `requires`.\n"
        f"Extras: {sorted(set(actual) - set(_REQUIRES_MAP_FROZEN))}\n"
        f"Faltantes: {sorted(set(_REQUIRES_MAP_FROZEN) - set(actual))}"
    )


def test_validate_requires_graph_ok_after_population():
    from services.harness_flags import validate_requires_graph

    assert validate_requires_graph() == []
