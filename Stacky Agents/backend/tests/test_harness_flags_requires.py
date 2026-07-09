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
    "INTENT_PREFLIGHT_AUTO_APPROVE": "INTENT_PREFLIGHT_ENABLED",
    "INTENT_PREFLIGHT_AUTO_APPROVE_MIN_CONF": "INTENT_PREFLIGHT_ENABLED",
    "STACKY_TASK_GATE_BLOCKING": "STACKY_TASK_GATE_ENABLED",
    "STACKY_QUALITY_CONVERGENCE_MAX_ITERATIONS": "STACKY_QUALITY_CONVERGENCE_ENABLED",
    "STACKY_ADO_EDIT_SWEEP_HOURS": "STACKY_ADO_EDIT_LEARNING_ENABLED",
    "STACKY_CODEBASE_MEMORY_MCP_BINARY_PATH": "STACKY_CODEBASE_MEMORY_MCP_ENABLED",
    "STACKY_CODEBASE_MEMORY_MCP_PROJECTS": "STACKY_CODEBASE_MEMORY_MCP_ENABLED",
    "STACKY_EPIC_CATALOG_GATE_ENABLED": "STACKY_EPIC_GATE_ENABLED",
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
