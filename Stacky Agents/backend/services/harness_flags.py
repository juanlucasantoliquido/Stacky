"""H0.4 — Registry declarativo de flags del arnés.

Reglas de diseño:
- PURO: no toca disco ni Flask. Solo describe y valida.
- Todo flag nuevo que introduzca el plan (H2/H3.3/H4/H5/H7) debe agregarse a
  FLAG_REGISTRY en el mismo PR que lo crea, para que aparezca en la UI sin
  tocar el frontend.
- env_only=True → el flag NO es atributo de Config; vive solo en os.environ
  (leído en call time, no en import time).
- El hot-apply lo hace el endpoint (api/harness_flags.py), no este módulo.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class FlagSpec:
    key: str             # nombre EXACTO de la env var / atributo de Config
    type: str            # "bool" | "csv" | "int" | "float" | "json"
    label: str           # texto corto para la UI (español)
    description: str     # 1-2 líneas para tooltip
    group: str           # "claude_code_cli" | "global"
    pair: str | None = None    # key del *_PROJECTS asociado (UI los renderiza juntos)
    env_only: bool = False     # True = no existe como atributo de Config
    default: object | None = None  # NUEVO — default DECLARADO (hint de UI). None = usar type-zero.


@dataclass(frozen=True)
class CategorySpec:
    id: str          # slug estable (no cambia)
    label: str       # título humano para la UI (español)
    description: str # 1 línea: qué controla esta categoría


FLAG_CATEGORIES: tuple[CategorySpec, ...] = (
    CategorySpec("runtimes_cli", "Runtimes CLI (Claude / Codex)",
        "Comportamiento de los agentes que corren como CLI: gates de contrato, autocorrección, hooks, resume, MCP, modelos."),
    CategorySpec("contexto_memoria", "Contexto y memoria",
        "Qué información recibe el agente: presupuesto/dedup/rerank de contexto, memoria colaborativa, skills, few-shot, catálogo."),
    CategorySpec("calidad_verificacion", "Calidad y verificación del entregable",
        "Criterios de aceptación, verificación ejecutable, contrato de aceptación, anti-verde-falso, convergencia, self-review, esfuerzo."),
    CategorySpec("integridad_grounding", "Integridad y grounding del resultado",
        "Verifica que lo que el agente afirma sea real: precondiciones, verificación post-create de tasks, anclado de referencias."),
    CategorySpec("epicas_ado", "Épicas, briefs y publicación en ADO",
        "Generación, saneamiento, gates, preview, descomposición y selector de modelo de épicas/issues hacia Azure DevOps."),
    CategorySpec("flujo_funcional", "Flujo funcional (Tasks)",
        "Creación de Tasks funcionales en ADO y su gate determinista."),
    CategorySpec("routing_costo", "Routing de modelo y costo",
        "Estimación de complejidad, routing por dificultad, advisor de runtime, presupuesto por ticket, caché de runs, evals."),
    CategorySpec("fiabilidad_ciclo_vida", "Fiabilidad y ciclo de vida del run",
        "Higiene de procesos: reaping, watchdog, validación pending-task, idempotencia, retries, runaway guard, auto-reparación, intake."),
    CategorySpec("observabilidad_notif", "Observabilidad y notificaciones",
        "KPIs en harness-health, historial, footer ADO, webhooks, notificaciones, telemetría en vivo, salud operativa, pipelines, trazabilidad."),
    CategorySpec("aprendizaje", "Aprendizaje y memoria que empuja",
        "Rechazos como anti-patrones, nota del operador a memoria, aprendizaje desde ediciones humanas en ADO."),
    CategorySpec("preflight_intencion", "Pre-vuelo de intención",
        "Brief de intención negociable que el operador aprueba antes del run."),
    CategorySpec("base_datos", "Base de datos y caché ADO",
        "Directiva de acceso read-only a la BD, caché y pre-warm de lecturas caras de ADO."),
    CategorySpec("avanzado", "Avanzado / experimental",
        "Kill-switches internos y features beta: egress check, especulación anticipatoria."),
    CategorySpec("migrador_ado_gitlab", "Migrador ADO → GitLab",
        "Plan 74 — Migración segura e idempotente de work items ADO (épicas, issues, tasks, comentarios, attachments) hacia GitLab."),
    CategorySpec("gitlab_deep_links", "GitLab / Deep Links",
        "Plan 75 — Deep links bidireccionales GitLab: issue, MR, pipeline, commit, épica. Kill-switch con default OFF."),
    CategorySpec("otros", "Otros / sin categorizar",
        "Flags aún no asignadas a una categoría (no debería haber ninguna; el test lo garantiza)."),
)

_CATEGORY_KEYS: dict[str, tuple[str, ...]] = {
    "runtimes_cli": (
        "CLAUDE_CODE_CLI_CONTRACT_GATE_ENABLED", "CLAUDE_CODE_CLI_AUTOCORRECT_ENABLED",
        "CLAUDE_CODE_CLI_AUTOCORRECT_MAX_RETRIES", "CLAUDE_CODE_CLI_HOOKS_ENABLED",
        "CLAUDE_CODE_CLI_PROJECT_KNOWLEDGE_ENABLED", "CLAUDE_CODE_CLI_PROJECT_KNOWLEDGE_PROJECTS",
        "CLAUDE_CODE_CLI_RESUME_ENABLED", "CLAUDE_CODE_CLI_RESUME_PROJECTS",
        "CLAUDE_CODE_CLI_MCP_ENABLED", "CLAUDE_CODE_CLI_MCP_PROJECTS",
        "CODEX_CLI_CONTRACT_GATE_ENABLED", "CODEX_CLI_AUTOCORRECT_ENABLED",
        "CODEX_CLI_AUTOCORRECT_MAX_RETRIES", "CODEX_CLI_MODEL_DENYLIST",
        "CODEX_CLI_RESUME_ENABLED", "CODEX_CLI_RESUME_PROJECTS",
    ),
    "contexto_memoria": (
        "STACKY_CONTEXT_BUDGET_ENABLED", "STACKY_CONTEXT_BUDGET_PROJECTS",
        "STACKY_CONTEXT_BUDGET_TOKENS", "STACKY_CONTEXT_DEDUP_ENABLED",
        "STACKY_CONTEXT_DEDUP_PROJECTS", "STACKY_CONTEXT_RERANK_ENABLED",
        "STACKY_PARALLEL_INJECTORS_ENABLED", "STACKY_RETRIEVAL_EXPANSION_ENABLED",
        "STACKY_MEMORY_INJECTION_ENABLED", "STACKY_MEMORY_INJECTION_PROJECTS",
        "STACKY_MEMORY_CAPS_JSON", "STACKY_MEMORY_REVIEW_SWEEP_HOURS",
        "STACKY_MEMORY_DIRECTIVE_MAX_CHARS", "STACKY_MEMORY_INJECT_SCOPES",
        "STACKY_SKILLS_ENABLED", "STACKY_SKILLS_PROJECTS",
        "STACKY_CLI_FEWSHOT_ENABLED", "STACKY_CLI_FEWSHOT_K", "STACKY_CLI_FEWSHOT_PROJECTS",
        "STACKY_INJECT_PROCESS_CATALOG", "STACKY_CAPS_ADVISOR_ENABLED",
        "STACKY_RAG_CATALOG_ENABLED", "STACKY_RAG_CATALOG_TOP_K",
        "STACKY_PROCESS_DISCIPLINE_ENABLED",   # Plan 67, C6 v2.1
    ),
    "calidad_verificacion": (
        "STACKY_ACCEPTANCE_CRITERIA_INJECTION_ENABLED", "STACKY_ACCEPTANCE_CRITERIA_PROJECTS",
        "STACKY_CRITERIA_REPAIR_ENABLED", "STACKY_CRITERIA_REPAIR_MAX_RETRIES",
        "STACKY_SELF_REVIEW_MODE", "STACKY_SELF_REVIEW_MIN_SCORE",
        "STACKY_EXEC_VERIFICATION_ENABLED", "STACKY_EXEC_VERIFICATION_MODE",
        "STACKY_EXEC_VERIFICATION_TIMEOUT_S", "STACKY_EXEC_VERIFICATION_BUDGET_S",
        "STACKY_EXEC_VERIFICATION_PROJECTS", "STACKY_EXEC_REPAIR_ENABLED",
        "STACKY_EXEC_REPAIR_MAX_RETRIES", "STACKY_FAKE_GREEN_GUARD_ENABLED",
        "STACKY_FAKE_GREEN_GUARD_HARD", "STACKY_EXEC_VERIFICATION_VERDICT_CARD_ENABLED",
        "STACKY_ACCEPTANCE_CONTRACT_ENABLED", "STACKY_ACCEPTANCE_CONTRACT_MODE",
        "STACKY_ACCEPTANCE_CONTRACT_MAX_CHECKS", "STACKY_ACCEPTANCE_CONTRACT_PROJECTS",
        "STACKY_ACCEPTANCE_GATE_ENABLED", "STACKY_ACCEPTANCE_REPAIR_ENABLED",
        "STACKY_ACCEPTANCE_REPAIR_MAX_RETRIES", "STACKY_ACCEPTANCE_INTEGRITY_ENABLED",
        "STACKY_ACCEPTANCE_VERDICT_CARD_ENABLED", "STACKY_QUALITY_CONVERGENCE_ENABLED",
        "STACKY_QUALITY_CONVERGENCE_MAX_ITERATIONS", "STACKY_ADAPTIVE_EFFORT_ENABLED",
        "STACKY_EFFORT_FLOOR",
    ),
    "integridad_grounding": (
        "STACKY_RUN_PREFLIGHT_GATE_ENABLED", "STACKY_VERIFY_TASK_BEFORE_CONSUMED_ENABLED",
        "STACKY_OUTPUT_GROUNDING_ENABLED", "STACKY_OUTPUT_GROUNDING_REPAIR",
    ),
    "epicas_ado": (
        "STACKY_EPIC_FROM_BRIEF_ENABLED", "STACKY_BRIEF_MODEL_SELECT_ENABLED",
        "STACKY_EPIC_GROUNDING_PREFLIGHT_ENABLED", "STACKY_EPIC_SUMMARY_ENABLED",
        "STACKY_GROUNDING_OBSERVATORY_ENABLED", "STACKY_PROCESS_CATALOG_SUGGESTIONS_ENABLED",
        "STACKY_EPIC_SANITIZE_ENABLED", "STACKY_EPIC_STRUCTURE_WARNINGS_ENABLED",
        "STACKY_CATALOG_GROUNDING_WARNINGS_ENABLED", "STACKY_EPIC_GATE_ENABLED",
        "STACKY_EPIC_CATALOG_GATE_ENABLED", "STACKY_ADO_PREVIEW_ENABLED",
        "STACKY_EPIC_PORTFOLIO_ENABLED", "STACKY_EPIC_DECOMPOSITION_ENABLED",
        "STACKY_ADAPTIVE_SELECTOR_ENABLED", "STACKY_PROJECT_AUTOPROFILE_ENABLED",
        "STACKY_COMMENT_FULL_SCAN_ENABLED",
        "STACKY_TICKETS_PROVIDER_ENABLED",   # Plan 70 — consumers por puerto TrackerProvider
        "STACKY_PIPELINE_PROVIDER_ENABLED",  # Plan 71 — sub-puerto CIProvider
        "STACKY_PIPELINE_TRIGGER_ENABLED",   # Plan 72 — trigger y monitoreo CI (HITL)
        "STACKY_PIPELINE_GENERATOR_ENABLED", # Plan 73 — generador declarativo PipelineSpec→YAML
    ),
    "migrador_ado_gitlab": (
        "STACKY_MIGRATOR_ADO_TO_GITLAB_ENABLED",  # Plan 74 — habilita el migrador
        "STACKY_MIGRATOR_EPIC_POLICY",             # Plan 74 — política de épicas (auto|premium_native|free_degrade)
    ),
    "gitlab_deep_links": (
        "STACKY_GITLAB_DEEP_LINKS_ENABLED",  # Plan 75 — deep links bidireccionales GitLab
    ),
    "flujo_funcional": (
        "STACKY_TASK_GATE_ENABLED", "STACKY_TASK_GATE_BLOCKING",
    ),
    "routing_costo": (
        "STACKY_COMPLEXITY_ESTIMATION_ENABLED", "STACKY_DIFFICULTY_ROUTING_ENABLED",
        "STACKY_RUN_ADVISOR_ENABLED", "STACKY_RUN_ADVISOR_ENFORCE",
        "STACKY_BUDGET_PER_TICKET_USD", "STACKY_RUN_CACHE_DAYS",
        "STACKY_EVALS_INTERVAL_HOURS", "STACKY_EVAL_GATE_MODE",
        "STACKY_MAX_CONCURRENT_RUNS",
    ),
    "fiabilidad_ciclo_vida": (
        "STACKY_RUNNER_REAP_ON_CLOSE_ENABLED", "STACKY_LOG_FLUSH_INCREMENTAL_ENABLED",
        "STACKY_ORPHAN_REAPER_ENABLED", "STACKY_ORPHAN_REAPER_INTERVAL_SEC",
        "STACKY_STALL_WATCHDOG_SECONDS", "STACKY_PENDING_TASK_STRICT_VALIDATION_ENABLED",
        "STACKY_PUBLISH_IDEMPOTENT_GUARD_ENABLED", "STACKY_RUNAWAY_MAX_TURNS",
        "STACKY_RUNAWAY_MAX_COST_USD", "STACKY_RUN_REPAIR_ENABLED",
        "STACKY_TRANSIENT_RUN_RETRY_ENABLED", "STACKY_TRANSIENT_RUN_RETRY_MAX",
        "STACKY_ARTIFACT_INTAKE_ENABLED", "STACKY_ARTIFACT_RESCUE_ENABLED",
    ),
    "observabilidad_notif": (
        "STACKY_RELIABILITY_KPIS_ENABLED", "STACKY_QUALITY_KPIS_ENABLED",
        "STACKY_INTEGRITY_KPIS_ENABLED", "STACKY_EXEC_VERIFICATION_KPIS_ENABLED",
        "STACKY_ACCEPTANCE_KPIS_ENABLED", "STACKY_EXECUTION_HISTORY_ENABLED",
        "STACKY_ADO_RUN_FOOTER_ENABLED", "STACKY_WEBHOOKS_V2_ENABLED",
        "STACKY_DESKTOP_NOTIFY_ENABLED", "STACKY_LIVE_TELEMETRY_ENABLED",
        "STACKY_OPERATIONAL_HEALTH_ENABLED", "STACKY_PIPELINES_ENABLED",
        "STACKY_EXECUTION_TRACE_ENABLED", "STACKY_TRACE_PROMPT_TEXT_ENABLED",
        "STACKY_DIGEST_INTERVAL_HOURS", "STACKY_ADO_FAILURE_COMMENT_ENABLED",
        "STACKY_UNBLOCKER_COMPLETED_CAP",   # Plan 66 C4 v4.1
    ),
    "aprendizaje": (
        "STACKY_PUSH_REJECTIONS_ENABLED", "STACKY_OPERATOR_NOTE_TO_MEMORY_ENABLED",
        "STACKY_ADO_EDIT_LEARNING_ENABLED", "STACKY_ADO_EDIT_SWEEP_HOURS",
        "STACKY_ADO_SERVICE_IDENTITY",
    ),
    "preflight_intencion": (
        "INTENT_PREFLIGHT_ENABLED", "INTENT_PREFLIGHT_AUTO_APPROVE",
        "INTENT_PREFLIGHT_AUTO_APPROVE_MIN_CONF",
    ),
    "base_datos": (
        "STACKY_DB_READONLY_DIRECTIVE_ENABLED", "STACKY_ADO_READ_CACHE_TTL_SEC",
        "STACKY_ADO_PREWARM_ENABLED",
    ),
    "avanzado": (
        "STACKY_CLI_EGRESS_ENABLED", "STACKY_SPECULATIVE_ENABLED", "STACKY_SPECULATIVE_MODE",
    ),
    # "otros" intencionalmente vacío: es el fallback de categorize().
}

# NOTA: toda flag nueva debe agregarse también a _CATEGORY_KEYS (arriba) o el test
# test_every_registry_flag_is_categorized rompe CI a propósito (Plan 63).
FLAG_REGISTRY: tuple[FlagSpec, ...] = (
    FlagSpec(
        key="CLAUDE_CODE_CLI_CONTRACT_GATE_ENABLED",
        type="bool",
        label="Gate de contrato (claude)",
        description="F1.1 — Si ON, outputs con errores duros degradan el run a needs_review.",
        group="claude_code_cli",
    ),
    FlagSpec(
        key="CLAUDE_CODE_CLI_AUTOCORRECT_ENABLED",
        type="bool",
        label="Autocorrección stdin (claude)",
        description="F1.3 — Loop de autocorrección al fin de cada turno via stdin.",
        group="claude_code_cli",
    ),
    FlagSpec(
        key="CLAUDE_CODE_CLI_AUTOCORRECT_MAX_RETRIES",
        type="int",
        label="Max reintentos autocorrección",
        description="Máximo de mensajes correctivos por run (default 2).",
        group="claude_code_cli",
    ),
    FlagSpec(
        key="CLAUDE_CODE_CLI_HOOKS_ENABLED",
        type="bool",
        label="Hooks PostToolUse (claude)",
        description="F1.4 — settings.json efímero con hook de validación de artifacts.",
        group="claude_code_cli",
    ),
    FlagSpec(
        key="CLAUDE_CODE_CLI_PROJECT_KNOWLEDGE_ENABLED",
        type="bool",
        label="Conocimiento de proyecto (claude)",
        description="F2.2 — Anti-patrones/decisiones/constraints/glosario en el system prompt.",
        group="claude_code_cli",
        pair="CLAUDE_CODE_CLI_PROJECT_KNOWLEDGE_PROJECTS",
    ),
    FlagSpec(
        key="CLAUDE_CODE_CLI_PROJECT_KNOWLEDGE_PROJECTS",
        type="csv",
        label="Proyectos — conocimiento",
        description="Allowlist CSV de proyectos. Vacío = todos (escape hatch).",
        group="claude_code_cli",
    ),
    FlagSpec(
        key="CLAUDE_CODE_CLI_RESUME_ENABLED",
        type="bool",
        label="Resume de sesión (claude)",
        description="F2.3 — Re-runs con --resume + delta prompt.",
        group="claude_code_cli",
        pair="CLAUDE_CODE_CLI_RESUME_PROJECTS",
    ),
    FlagSpec(
        key="CLAUDE_CODE_CLI_RESUME_PROJECTS",
        type="csv",
        label="Proyectos — resume",
        description="Allowlist CSV de proyectos. Vacío = todos.",
        group="claude_code_cli",
    ),
    FlagSpec(
        key="CLAUDE_CODE_CLI_MCP_ENABLED",
        type="bool",
        label="MCP server (claude)",
        description="F2.1 — Stacky MCP server inyectado vía --mcp-config.",
        group="claude_code_cli",
        pair="CLAUDE_CODE_CLI_MCP_PROJECTS",
    ),
    FlagSpec(
        key="CLAUDE_CODE_CLI_MCP_PROJECTS",
        type="csv",
        label="Proyectos — MCP",
        description="Allowlist CSV de proyectos. Vacío = todos.",
        group="claude_code_cli",
    ),
    FlagSpec(
        key="STACKY_CONTEXT_BUDGET_ENABLED",
        type="bool",
        label="Presupuesto de contexto",
        description="F2.4 — Ranking + truncado de bloques de contexto.",
        group="global",
        pair="STACKY_CONTEXT_BUDGET_PROJECTS",
    ),
    FlagSpec(
        key="STACKY_CONTEXT_BUDGET_PROJECTS",
        type="csv",
        label="Proyectos — budget contexto",
        description="Allowlist CSV de proyectos. Vacío = todos.",
        group="global",
    ),
    FlagSpec(
        key="STACKY_CONTEXT_BUDGET_TOKENS",
        type="int",
        label="Tokens máx contexto",
        description="Presupuesto global de tokens estimados (default 25000).",
        group="global",
    ),
    # ── I0.1 — Dedup léxico entre bloques de contexto ────────────────────────
    FlagSpec(
        key="STACKY_CONTEXT_DEDUP_ENABLED",
        type="bool",
        label="Dedup léxico de contexto",
        description=(
            "I0.1 — Elimina líneas idénticas de bloques de menor prioridad cuando "
            "ya aparecen en bloques de mayor prioridad. Corre antes del budget."
        ),
        group="global",
        pair="STACKY_CONTEXT_DEDUP_PROJECTS",
    ),
    FlagSpec(
        key="STACKY_CONTEXT_DEDUP_PROJECTS",
        type="csv",
        label="Proyectos — dedup contexto",
        description="Allowlist CSV de proyectos. Vacío = todos.",
        group="global",
    ),
    FlagSpec(
        key="STACKY_MEMORY_INJECTION_ENABLED",
        type="bool",
        label="Inyección de memoria colaborativa",
        description="F2.5 — Inyecta observaciones curadas en el user prompt.",
        group="global",
        pair="STACKY_MEMORY_INJECTION_PROJECTS",
        env_only=True,  # leído de os.environ en call time, no atributo de Config
    ),
    FlagSpec(
        key="STACKY_MEMORY_INJECTION_PROJECTS",
        type="csv",
        label="Proyectos — memoria",
        description="Allowlist CSV de proyectos. Vacío = todos.",
        group="global",
    ),
    # ── M0.1 — Caps de contexto por agente configurables ─────────────────────
    FlagSpec(
        key="STACKY_MEMORY_CAPS_JSON",
        type="json",
        label="Caps de memoria por agente (JSON)",
        description=(
            "M0.1 — Override por agente de (max_memorias, max_chars). "
            'Shape: {"developer":[16,16000]}. Vacío = defaults hardcodeados.'
        ),
        group="global",
    ),
    # ── M0.3 — Barrido de revisión de memorias ───────────────────────────────
    FlagSpec(
        key="STACKY_MEMORY_REVIEW_SWEEP_HOURS",
        type="int",
        label="Barrido de revisión de memoria (horas)",
        description=(
            "M0.3 — Cada N horas marca needs_review las memorias con review_after "
            "vencido. 0 = off (default)."
        ),
        group="global",
    ),
    # ── M1.2 — Presupuesto de directivas ──────────────────────────────────────
    FlagSpec(
        key="STACKY_MEMORY_DIRECTIVE_MAX_CHARS",
        type="int",
        label="Chars máx directivas",
        description=(
            "M1.2 — Techo de caracteres reservado a las directivas obligatorias "
            "dentro del bloque de memoria (default 4000)."
        ),
        group="global",
    ),
    # ── M3.1 — Scopes inyectables ─────────────────────────────────────────────
    FlagSpec(
        key="STACKY_MEMORY_INJECT_SCOPES",
        type="csv",
        label="Scopes de memoria inyectables",
        description=(
            "M3.1 — CSV de scopes que se inyectan. Vacío = project,team,global "
            "(default). Agregá 'personal' para el caso mono-operador."
        ),
        group="global",
    ),
    # ── H3.3 — Egress check para runtimes CLI ────────────────────────────────
    FlagSpec(
        key="STACKY_CLI_EGRESS_ENABLED",
        type="bool",
        label="Egress check en CLI (claude + codex)",
        description=(
            "H3.3 — Si ON, corre egress_policies.check sobre el prompt final de cada "
            "runtime CLI antes de hacer spawn. Si bloquea, el run termina con error."
        ),
        group="global",
        env_only=True,  # leído de os.environ en call time, no atributo de Config
    ),
    # ── H2 — Paridad codex_cli ────────────────────────────────────────────────
    FlagSpec(
        key="CODEX_CLI_CONTRACT_GATE_ENABLED",
        type="bool",
        label="Gate de contrato (codex)",
        description="H2.1 — Si ON, outputs con errores duros degradan el run a needs_review.",
        group="codex_cli",
    ),
    FlagSpec(
        key="CODEX_CLI_AUTOCORRECT_ENABLED",
        type="bool",
        label="Autocorrección exec resume (codex)",
        description="H2.3 — Loop de autocorrección al fin del run via codex exec resume.",
        group="codex_cli",
    ),
    FlagSpec(
        key="CODEX_CLI_AUTOCORRECT_MAX_RETRIES",
        type="int",
        label="Max reintentos autocorrección (codex)",
        description="Máximo de resumes correctivos por run codex (default 2).",
        group="codex_cli",
    ),
    FlagSpec(
        key="CODEX_CLI_MODEL_DENYLIST",
        type="csv",
        label="Denylist de modelos (codex)",
        description="H2.4 — CSV de modelos codex bloqueados; si matchea degrada a CODEX_CLI_MODEL.",
        group="codex_cli",
    ),
    # ── H4 — Stacky Skills ────────────────────────────────────────────────────
    FlagSpec(
        key="STACKY_SKILLS_ENABLED",
        type="bool",
        label="Stacky Skills (todos los runtimes)",
        description=(
            "H4.3 — Si ON, inyecta el índice/cuerpo de skills relevantes en el "
            "system prompt de claude, codex y copilot antes de _STACKY_RULES."
        ),
        group="global",
        pair="STACKY_SKILLS_PROJECTS",
    ),
    FlagSpec(
        key="STACKY_SKILLS_PROJECTS",
        type="csv",
        label="Proyectos — Skills",
        description="Allowlist CSV de proyectos. Vacío = todos.",
        group="global",
    ),
    # ── H7 — Resume unificado (codex) ────────────────────────────────────────
    FlagSpec(
        key="CODEX_CLI_RESUME_ENABLED",
        type="bool",
        label="Resume de sesión (codex)",
        description="H7.1 — Re-runs con codex exec resume + delta prompt (paridad con claude F2.3).",
        group="codex_cli",
        pair="CODEX_CLI_RESUME_PROJECTS",
    ),
    FlagSpec(
        key="CODEX_CLI_RESUME_PROJECTS",
        type="csv",
        label="Proyectos — resume (codex)",
        description="Allowlist CSV de proyectos. Vacío = todos.",
        group="codex_cli",
    ),
    # ── H5 — Runaway guard in-run ─────────────────────────────────────────────
    FlagSpec(
        key="STACKY_RUNAWAY_MAX_TURNS",
        type="int",
        label="Runaway: turnos máx por run",
        description=(
            "H5 — Máximo de turnos por run agéntico. 0 = sin límite (desactivado). "
            "Al superar: señal de cierre + needs_review."
        ),
        group="global",
    ),
    FlagSpec(
        key="STACKY_RUNAWAY_MAX_COST_USD",
        type="float",
        label="Runaway: costo máx por run (USD)",
        description=(
            "H5 — Costo máximo en USD por run agéntico. 0.0 = sin límite (desactivado). "
            "Solo disponible en claude (codex no reporta costo en stream)."
        ),
        group="global",
    ),
    # ── V0.3 — Cap de concurrencia de runs CLI ────────────────────────────────
    FlagSpec(
        key="STACKY_MAX_CONCURRENT_RUNS",
        type="int",
        label="Concurrencia: runs CLI simultáneos máx",
        description=(
            "V0.3 — Techo de subprocesos CLI simultáneos en la máquina del operador. "
            "0 = ilimitado (retro-compat). Al superar: 429 en el launch."
        ),
        group="global",
    ),
    FlagSpec(
        key="STACKY_ADO_RUN_FOOTER_ENABLED",
        type="bool",
        label="Firma visible Stacky en ADO",
        description="U0.2 — Agrega footer con agente/runtime/modelo/run en comentarios y tasks.",
        group="global",
    ),
    FlagSpec(
        key="STACKY_WEBHOOKS_V2_ENABLED",
        type="bool",
        label="Webhooks v2 multi-runtime",
        description="U0.3 — Emite exec.completed/failed/needs_review para todos los runtimes.",
        group="global",
    ),
    FlagSpec(
        key="STACKY_DESKTOP_NOTIFY_ENABLED",
        type="bool",
        label="Notificación desktop global",
        description="U0.4 — Toast del SO al cerrar runs, incluso fuera del browser.",
        group="global",
    ),
    FlagSpec(
        key="STACKY_LIVE_TELEMETRY_ENABLED",
        type="bool",
        label="Telemetría en vivo en consola",
        description="U0.5 — Emite eventos SSE telemetry con turnos/tokens/costo durante el run.",
        group="global",
    ),
    FlagSpec(
        key="STACKY_SELF_REVIEW_MODE",
        type="csv",
        label="Self-review mode",
        description="U1.2 — off | annotate | gate para review contra acceptance criteria.",
        group="global",
    ),
    FlagSpec(
        key="STACKY_SELF_REVIEW_MIN_SCORE",
        type="float",
        label="Self-review score mínimo",
        description="U1.2 — Umbral de score (0..1) usado cuando mode=gate.",
        group="global",
    ),
    FlagSpec(
        key="STACKY_ADO_FAILURE_COMMENT_ENABLED",
        type="bool",
        label="Comentario ADO en fallo",
        description="U1.3 — Encola comentario de diagnóstico en runs error/needs_review.",
        group="global",
    ),
    FlagSpec(
        key="STACKY_DIGEST_INTERVAL_HOURS",
        type="int",
        label="Intervalo digest (horas)",
        description="U1.5 — 0 desactiva; >0 emite digest.ready periódico por webhooks.",
        group="global",
    ),
    FlagSpec(
        key="STACKY_PIPELINES_ENABLED",
        type="bool",
        label="Pipelines orquestados",
        description="U2.1 — Habilita /api/pipelines y encadenamiento por etapas con pausa en fallos.",
        group="global",
    ),
    # ── V1.3 — Intake universal de outputs file-based ──────────────────────────
    FlagSpec(
        key="STACKY_ARTIFACT_INTAKE_ENABLED",
        type="bool",
        label="Intake universal de artefactos (codex/file-based)",
        description=(
            "V1.3 — Si ON, todo output file-based pasa por validación+reparación "
            "determinista (anti-ordinal incluido) antes de encolarse a ADO. "
            "OFF = path actual byte-idéntico."
        ),
        group="global",
        env_only=True,
    ),
    # ── V1.2 — Smart dispatch v1 (advisor) ─────────────────────────────────────
    FlagSpec(
        key="STACKY_RUN_ADVISOR_ENABLED",
        type="bool",
        label="Advisor de runtime/modelo (recomendación)",
        description=(
            "V1.2 — Si ON, el endpoint /advise recomienda runtime+modelo según los "
            "KPIs históricos del arnés. Nunca fuerza (v1 solo sugiere)."
        ),
        group="global",
        env_only=True,
    ),
    # ── V2.2 — Smart dispatch v2 (enforce + budget) ────────────────────────────
    FlagSpec(
        key="STACKY_RUN_ADVISOR_ENFORCE",
        type="bool",
        label="Advisor enforce (auto-routing)",
        description=(
            "V2.2 — Si ON y el payload no trae runtime explícito, el launch usa la "
            "recomendación del advisor. El humano siempre gana si elige runtime."
        ),
        group="global",
        env_only=True,
    ),
    FlagSpec(
        key="STACKY_BUDGET_PER_TICKET_USD",
        type="float",
        label="Presupuesto por ticket (USD)",
        description=(
            "V2.2 — Tope de costo acumulado por ticket. 0.0 = sin límite. Al superar: "
            "degrada modelo un escalón; si aún excede → 402 (override force_budget)."
        ),
        group="global",
        env_only=True,
    ),
    # ── V2.3 — Evals programados + gate endurecible ────────────────────────────
    FlagSpec(
        key="STACKY_EVALS_INTERVAL_HOURS",
        type="int",
        label="Evals programados: intervalo (horas)",
        description="V2.3 — Corre 'evals run all' cada N horas en daemon. 0 = off.",
        group="global",
        env_only=True,
    ),
    FlagSpec(
        key="STACKY_EVAL_GATE_MODE",
        type="csv",
        label="Modo del gate de evals en import",
        description="V2.3 — off|warn|block. warn (default) solo loguea; block rechaza el import (409).",
        group="global",
        env_only=True,
    ),
    # ── V2.4 — Cache/dedup de runs CLI ─────────────────────────────────────────
    FlagSpec(
        key="STACKY_RUN_CACHE_DAYS",
        type="int",
        label="Cache de runs: ventana (días)",
        description=(
            "V2.4 — Ventana para sugerir reusar un run idéntico (mismo fingerprint). "
            "0 = off. Nunca auto-skip: el operador decide."
        ),
        group="global",
        env_only=True,
    ),
    # ── I0.2 — Cómputo consistente de fingerprint_complexity ─────────────────
    FlagSpec(
        key="STACKY_COMPLEXITY_ESTIMATION_ENABLED",
        type="bool",
        label="Estimación de complejidad automática",
        description=(
            "I0.2 — Calcula fingerprint_complexity (S/M/L/XL) automáticamente "
            "en los 3 runtimes usando heurística determinística (sin LLM). "
            "OFF = routing byte-idéntico (fingerprint_complexity=None)."
        ),
        group="global",
    ),
    # ── I1.1 — Auto-reparación de run ante output vacío/malformado ───────────
    FlagSpec(
        key="STACKY_RUN_REPAIR_ENABLED",
        type="bool",
        label="Auto-reparación de run (output vacío/malformado)",
        description=(
            "I1.1 — Un único reintento si el output queda vacío o un artefacto "
            ".json es malformado. Solo en runtimes con resume (claude/codex). "
            "Comparte presupuesto con el autocorrect. OFF = sin cambio."
        ),
        group="global",
    ),
    # ── I1.2 — Routing por dificultad estimada dentro del clamp ──────────────
    FlagSpec(
        key="STACKY_DIFFICULTY_ROUTING_ENABLED",
        type="bool",
        label="Routing por dificultad estimada",
        description=(
            "I1.2 — Downgrade a haiku en encargos S; upgrade a sonnet en L/XL. "
            "El clamp duro (§5.2) nunca se supera. Override del operador gana. "
            "OFF = decide() comportamiento actual."
        ),
        group="global",
    ),
    # ── I3.2 — Caché en memoria de lecturas caras de ADO ─────────────────────
    FlagSpec(
        key="STACKY_ADO_READ_CACHE_TTL_SEC",
        type="int",
        label="Caché ADO: TTL en segundos",
        description=(
            "I3.2 — TTL del caché en memoria para lecturas ADO (similar, comments). "
            "0 = sin caché (byte-idéntico). >0 = segundos de vida de cada entrada. "
            "Escritura exitosa en outbox invalida el key automáticamente."
        ),
        group="global",
    ),
    # ── I2.3 — Expansión y normalización de query ─────────────────────────────
    FlagSpec(
        key="STACKY_RETRIEVAL_EXPANSION_ENABLED",
        type="bool",
        label="Expansión de query en retrieval",
        description=(
            "I2.3 — Fold de acentos + sinónimos del dominio sobre el query de "
            "retrieval (embeddings.top_k y memory_store.search). El corpus NO "
            "cambia. OFF = tokenizer y ranking byte-idénticos."
        ),
        group="global",
    ),
    # ── I2.1 — Re-ranking de bloques por relevancia al ticket ─────────────────
    FlagSpec(
        key="STACKY_CONTEXT_RERANK_ENABLED",
        type="bool",
        label="Rerank de contexto por relevancia al ticket",
        description=(
            "I2.1 — Cuando el budget obliga a recortar, conserva los bloques más "
            "relevantes al ticket (TF-IDF coseno) en vez de solo los de prioridad "
            "fija más alta. Alta prioridad nunca se corta. "
            "OFF = _apply_context_budget byte-idéntico."
        ),
        group="global",
    ),
    # ── I3.1 — Paralelización de injectors ───────────────────────────────────
    FlagSpec(
        key="STACKY_PARALLEL_INJECTORS_ENABLED",
        type="bool",
        label="Injectors de contexto en paralelo",
        description=(
            "I3.1 — similar_tickets + ado_context corren en paralelo (stdlib "
            "ThreadPoolExecutor, max_workers=2). El orden final es byte-idéntico "
            "al serial. Excepción en un injector no tumba los demás. "
            "OFF = serial byte-idéntico."
        ),
        group="global",
    ),
    # ── I0.3 — Pre-warming del caché ADO ──────────────────────────────────────
    FlagSpec(
        key="STACKY_ADO_PREWARM_ENABLED",
        type="bool",
        label="Pre-warming del caché ADO",
        description=(
            "I0.3 — POST /tickets/<ado_id>/prewarm dispara en background las "
            "lecturas caras (similar, comments) para que el run siguiente use caché. "
            "Requiere STACKY_ADO_READ_CACHE_TTL_SEC > 0. "
            "OFF = endpoint devuelve {status: disabled}."
        ),
        group="global",
    ),
    # ── I3.3 — Asesor de caps de contexto ──────────────────────────────────────
    FlagSpec(
        key="STACKY_CAPS_ADVISOR_ENABLED",
        type="bool",
        label="Asesor de caps de contexto (solo lectura)",
        description=(
            "I3.3 — GET /metrics/caps-advisor sugiere caps de memoria por agente "
            "basándose en la telemetría histórica. NUNCA escribe; el operador aplica "
            "las sugerencias vía STACKY_MEMORY_CAPS_JSON. "
            "OFF = endpoint devuelve {enabled: false}."
        ),
        group="global",
    ),
    # ── Plan 28 — Lifecycle e higiene de procesos ─────────────────────────────
    FlagSpec(
        key="STACKY_RUNNER_REAP_ON_CLOSE_ENABLED",
        type="bool",
        label="Reaping de subproceso al cerrar",
        description=(
            "R0.1 — terminate→wait(grace)→kill al marcar terminal o cerrar ejecución. "
            "Solo actúa sobre el pid exacto registrado por el runner. OFF = sin cambio."
        ),
        group="global",
        default=True,
    ),
    FlagSpec(
        key="STACKY_LOG_FLUSH_INCREMENTAL_ENABLED",
        type="bool",
        label="Flush incremental de logs",
        description=(
            "R0.2 — Persiste el buffer de log a DB antes de matar el proceso (reap). "
            "Append idempotente por secuencia. OFF = solo en close() (comportamiento actual)."
        ),
        group="global",
    ),
    FlagSpec(
        key="STACKY_ORPHAN_REAPER_ENABLED",
        type="bool",
        label="Reaper de huérfanos",
        description=(
            "R0.3 — Reconcilia runs running sin heartbeat reciente: flush+reap+"
            "sealed metadata['reaped']. Al arrancar y periódicamente. OFF = solo reporta."
        ),
        group="global",
        default=True,
    ),
    FlagSpec(
        key="STACKY_ORPHAN_REAPER_INTERVAL_SEC",
        type="int",
        label="Reaper de huérfanos: intervalo (segundos)",
        description="R0.3 — 0 = solo al arrancar. >0 = barrido periódico cada N segundos.",
        group="global",
    ),
    FlagSpec(
        key="STACKY_STALL_WATCHDOG_SECONDS",
        type="int",
        label="Watchdog de inactividad (segundos)",
        description=(
            "R1.1 — 0 = desactivado. >0 = cierre failed/stalled si el stream no emite "
            "eventos por N segundos. Independiente del timeout de sesión total."
        ),
        group="global",
    ),
    FlagSpec(
        key="STACKY_PENDING_TASK_STRICT_VALIDATION_ENABLED",
        type="bool",
        label="Validación estructural pending-task",
        description=(
            "R1.2 — Gate estructural mínimo antes del POST: campos requeridos, tipos, "
            "coherencia ordinal vs parent ADO id. Inválido → cuarentena + telemetría."
        ),
        group="global",
        default=True,
    ),
    FlagSpec(
        key="STACKY_PUBLISH_IDEMPOTENT_GUARD_ENABLED",
        type="bool",
        label="Guardia de idempotencia de publicación",
        description=(
            "R1.3 — Persiste intención de publicación antes del POST a ADO. "
            "Reintento detecta marker existente → no re-postea. OFF = comportamiento actual."
        ),
        group="global",
    ),
    FlagSpec(
        key="STACKY_RELIABILITY_KPIS_ENABLED",
        type="bool",
        label="KPIs de fiabilidad en harness-health",
        description=(
            "R2.1/R2.2 — Bloque 'reliability' en harness-health: dead_letter, "
            "cuarentenas, reaped, stalled, persist_failures, tasa_exito_creacion, "
            "duracion_saneada. Read-only; degrada con gracia si fuente ausente."
        ),
        group="global",
    ),
    # ── Plan 29 — Calidad del resultado a la primera ──────────────────────────
    FlagSpec(
        key="STACKY_ACCEPTANCE_CRITERIA_INJECTION_ENABLED",
        type="bool",
        label="Inyección de criterios de aceptación (checklist)",
        description=(
            "Q0.1 — Inyecta los acceptance criteria del ticket en el briefing "
            "como checklist obligatorio. Bloque 'acceptance-criteria', alta prioridad, "
            "nunca podado. OFF = enrich_blocks byte-idéntico."
        ),
        group="global",
        pair="STACKY_ACCEPTANCE_CRITERIA_PROJECTS",
    ),
    FlagSpec(
        key="STACKY_ACCEPTANCE_CRITERIA_PROJECTS",
        type="csv",
        label="Proyectos — criterios de aceptación",
        description="Allowlist CSV de proyectos. Vacío = todos.",
        group="global",
    ),
    FlagSpec(
        key="STACKY_ADAPTIVE_EFFORT_ENABLED",
        type="bool",
        label="Esfuerzo adaptativo por dificultad",
        description=(
            "Q0.2 — Mapea S→low, M→medium, L/XL→high en los runtimes CLI. "
            "Respeta STACKY_EFFORT_FLOOR como piso. Override del operador gana. "
            "OFF = effort fijo (byte-idéntico)."
        ),
        group="global",
    ),
    FlagSpec(
        key="STACKY_EFFORT_FLOOR",
        type="csv",
        label="Piso de effort adaptativo",
        description="Q0.2 — Nivel mínimo de effort (low/medium/high). Default: medium.",
        group="global",
    ),
    FlagSpec(
        key="STACKY_CRITERIA_REPAIR_ENABLED",
        type="bool",
        label="Pase correctivo de criterios incumplidos",
        description=(
            "Q1.1 — Si self-review detecta criterios incumplidos, envía un único "
            "mensaje correctivo antes de finalize_run (solo runtimes con resume). "
            "Presupuesto compartido con autocorrect. OFF = sin pase correctivo."
        ),
        group="global",
    ),
    FlagSpec(
        key="STACKY_CRITERIA_REPAIR_MAX_RETRIES",
        type="int",
        label="Max reintentos pase correctivo",
        description="Q1.1 — Máximo de pases correctivos por run (default 1).",
        group="global",
    ),
    FlagSpec(
        key="STACKY_CLI_FEWSHOT_ENABLED",
        type="bool",
        label="Few-shot de outputs aprobados (runtimes CLI)",
        description=(
            "Q1.2 — Inyecta ejemplos de outputs aprobados del mismo agente/proyecto "
            "en enrich_blocks. Solo en CLI (no duplica copilot). OFF = byte-idéntico."
        ),
        group="global",
        pair="STACKY_CLI_FEWSHOT_PROJECTS",
    ),
    FlagSpec(
        key="STACKY_CLI_FEWSHOT_K",
        type="int",
        label="Few-shot: cantidad de ejemplos (k)",
        description="Q1.2 — Número máximo de ejemplos a inyectar (default 2).",
        group="global",
    ),
    FlagSpec(
        key="STACKY_CLI_FEWSHOT_PROJECTS",
        type="csv",
        label="Proyectos — few-shot CLI",
        description="Allowlist CSV de proyectos. Vacío = todos.",
        group="global",
    ),
    FlagSpec(
        key="STACKY_QUALITY_KPIS_ENABLED",
        type="bool",
        label="KPIs de calidad 'aprobado a la primera'",
        description=(
            "Q2.2 — Bloque 'quality' en harness-health: tasa_aprobado_a_la_primera, "
            "needs_review_por_criterio, tasa_recuperacion_criteria_repair, corte "
            "few-shot/criterios. Read-only; degrada con gracia. OFF = byte-idéntico."
        ),
        group="global",
    ),
    # ── Plan 30 — Integridad verificada contra la realidad ────────────────────
    FlagSpec(
        key="STACKY_RUN_PREFLIGHT_GATE_ENABLED",
        type="bool",
        label="Gate de precondiciones pre-run (G0.1)",
        description=(
            "G0.1 — Verifica precondiciones deterministas antes de lanzar el run: "
            "outputs_dir escribible, repo presente si el runtime lo requiere, PAT "
            "si auto-create ON, binario del runtime resolvible. "
            "Fallo duro → run bloqueado con metadata['precondition_failure']. "
            "OFF = run_agent byte-idéntico."
        ),
        group="global",
    ),
    FlagSpec(
        key="STACKY_VERIFY_TASK_BEFORE_CONSUMED_ENABLED",
        type="bool",
        label="Verificación post-create de task en ADO (G1.1)",
        description=(
            "G1.1 — Después del POST auto-create, verifica vía ado_read_cache que "
            "la task existe en ADO antes de marcar consumed. Si no existe: "
            "cuarentena (sin auto-recrear). Error transitorio → fallback consumed. "
            "OFF = output_watcher byte-idéntico."
        ),
        group="global",
    ),
    FlagSpec(
        key="STACKY_OUTPUT_GROUNDING_ENABLED",
        type="bool",
        label="Grounding de referencias del output (G1.2)",
        description=(
            "G1.2 — Extrae rutas/IDs del output y verifica su existencia "
            "(solo referencias de lectura/modificación, nunca las de creación). "
            "Produce metadata['grounding']. OFF = finalize_run byte-idéntico."
        ),
        group="global",
    ),
    FlagSpec(
        key="STACKY_OUTPUT_GROUNDING_REPAIR",
        type="bool",
        label="Pase correctivo de grounding (G1.2)",
        description=(
            "G1.2 — Si hay referencias no ancladas y Q1.1 (STACKY_CRITERIA_REPAIR_ENABLED) "
            "está disponible: pase correctivo dirigido a referencias rotas. "
            "Sin Q1.1 → solo anota. Exige STACKY_OUTPUT_GROUNDING_ENABLED."
        ),
        group="global",
    ),
    FlagSpec(
        key="STACKY_INTEGRITY_KPIS_ENABLED",
        type="bool",
        label="KPIs de integridad en harness-health (G2.1)",
        description=(
            "G2.1 — Bloque 'integrity' en harness-health: runs_condenados_evitados, "
            "exitos_fantasma_atrapados, tasa_referencias_ancladas, "
            "tasa_exito_real_creacion. Read-only; degrada con gracia. OFF = byte-idéntico."
        ),
        group="global",
    ),
    FlagSpec(
        key="STACKY_TRANSIENT_RUN_RETRY_ENABLED",
        type="bool",
        label="Retry de runs transitorios (G2.2 - DIFERIDO)",
        description=(
            "G2.2 — DIFERIDO: la clasificación confiable de exit-codes transitorios "
            "requiere instrumentación adicional en los runtimes. Flag declarado para "
            "completitud del registro. OFF siempre = comportamiento actual."
        ),
        group="global",
    ),
    FlagSpec(
        key="STACKY_TRANSIENT_RUN_RETRY_MAX",
        type="int",
        label="Retry transitorio: máx reintentos (G2.2 - DIFERIDO)",
        description="G2.2 — Máximo de reintentos transitorios por run (default 1). DIFERIDO.",
        group="global",
    ),
    # ── Plan 31 — Verificación ejecutable del entregable ─────────────────────
    FlagSpec(
        key="STACKY_EXEC_VERIFICATION_ENABLED",
        type="bool",
        label="Verificación ejecutable del entregable (E0.1)",
        description=(
            "E0.1 — Master del motor de verificación ejecutable. Corre verificadores "
            "objetivos (parse, compile, tsc, pytest, lint) sobre los archivos cambiados "
            "por el agente, barato-primero + short-circuit. OFF = finalize_run byte-idéntico."
        ),
        group="global",
        pair="STACKY_EXEC_VERIFICATION_PROJECTS",
    ),
    FlagSpec(
        key="STACKY_EXEC_VERIFICATION_MODE",
        type="csv",
        label="Modo de verificación ejecutable",
        description=(
            "E0.1 — off|annotate|gate. 'annotate' solo anota en metadata sin bloquear; "
            "'gate' + E1.1 bloquea si hay hard failures no recuperados."
        ),
        group="global",
    ),
    FlagSpec(
        key="STACKY_EXEC_VERIFICATION_TIMEOUT_S",
        type="int",
        label="Timeout por verificador (segundos)",
        description="E0.1 — Timeout máximo por verificador individual (default 120s).",
        group="global",
    ),
    FlagSpec(
        key="STACKY_EXEC_VERIFICATION_BUDGET_S",
        type="int",
        label="Budget global de verificación (segundos)",
        description="E0.1 — Budget total para todos los verificadores del run (default 300s).",
        group="global",
    ),
    FlagSpec(
        key="STACKY_EXEC_VERIFICATION_PROJECTS",
        type="csv",
        label="Proyectos — verificación ejecutable",
        description="Allowlist CSV de proyectos. Vacío = todos (cuando master ON).",
        group="global",
    ),
    FlagSpec(
        key="STACKY_EXEC_REPAIR_ENABLED",
        type="bool",
        label="Pase correctivo ante fallo ejecutable (E1.1)",
        description=(
            "E1.1 — Si verificación en modo 'gate' detecta hard failures, intenta un "
            "único pase correctivo dirigido al fallo. Solo en runtimes con resume. "
            "Re-verifica una vez con verificador ORIGINAL. OFF = degrada a needs_review."
        ),
        group="global",
    ),
    FlagSpec(
        key="STACKY_EXEC_REPAIR_MAX_RETRIES",
        type="int",
        label="Max reintentos reparación ejecutable",
        description="E1.1 — Máximo de pases correctivos por fallo ejecutable (default 1).",
        group="global",
    ),
    FlagSpec(
        key="STACKY_FAKE_GREEN_GUARD_ENABLED",
        type="bool",
        label="Guard anti-verde-falso (E1.2)",
        description=(
            "E1.2 — Detecta tests sin assert, cuerpos vacíos, todos-skip. "
            "Soft-warn por defecto; escalable a HARD con _HARD=true. "
            "Solo archivos de test en changed_files. OFF = byte-idéntico."
        ),
        group="global",
    ),
    FlagSpec(
        key="STACKY_FAKE_GREEN_GUARD_HARD",
        type="bool",
        label="Guard anti-verde-falso: hard fail",
        description=(
            "E1.2 — Si ON, verde-falso detectado es HARD (gateable); por defecto es soft-warn."
        ),
        group="global",
    ),
    FlagSpec(
        key="STACKY_EXEC_VERIFICATION_VERDICT_CARD_ENABLED",
        type="bool",
        label="Card de verificación ejecutable en verdict (E2.1)",
        description=(
            "E2.1 — Incluye el bloque exec_verification en el payload de la ejecución "
            "(read-only). Si ausente → campo omitido. OFF = payload byte-idéntico."
        ),
        group="global",
    ),
    FlagSpec(
        key="STACKY_EXEC_VERIFICATION_KPIS_ENABLED",
        type="bool",
        label="KPIs de verificación ejecutable en harness-health (E2.2)",
        description=(
            "E2.2 — Bloque 'exec_verification' en harness-health: tasa_verde_a_la_primera, "
            "tasa_recuperacion_exec_repair, entregables_rotos_atrapados, "
            "verde_falso_atrapado, costo_medio_verificacion_ms. Read-only; degrada con gracia."
        ),
        group="global",
    ),
    # ── Plan 32 — Contrato de Aceptación Ejecutable ───────────────────────────
    FlagSpec(
        key="STACKY_ACCEPTANCE_CONTRACT_ENABLED",
        type="bool",
        label="Contrato de aceptación ejecutable (A0.1)",
        description=(
            "A0.1 — Deriva chequeos ejecutables desde el ticket (LLM bajo clamp_model), "
            "los valida contra baseline (fail-red conserva, pass descarta), y persiste "
            "en metadata['acceptance_contract'] antes del run. OFF = finalize_run byte-idéntico."
        ),
        group="global",
        pair="STACKY_ACCEPTANCE_CONTRACT_PROJECTS",
    ),
    FlagSpec(
        key="STACKY_ACCEPTANCE_CONTRACT_MODE",
        type="csv",
        label="Modo del contrato de aceptación",
        description=(
            "A0.1 — off|annotate|gate. 'annotate' deriva+valida sin inyectar ni gatear; "
            "'gate' inyecta como blanco de alta prioridad y gatea en finalize_run."
        ),
        group="global",
    ),
    FlagSpec(
        key="STACKY_ACCEPTANCE_CONTRACT_MAX_CHECKS",
        type="int",
        label="Contrato: máx chequeos por run",
        description="A0.1 — Cap de chequeos ejecutables derivados por complejidad (default 4).",
        group="global",
    ),
    FlagSpec(
        key="STACKY_ACCEPTANCE_CONTRACT_PROJECTS",
        type="csv",
        label="Proyectos — contrato de aceptación",
        description="Allowlist CSV de proyectos. Vacío = todos (cuando master ON).",
        group="global",
    ),
    FlagSpec(
        key="STACKY_ACCEPTANCE_GATE_ENABLED",
        type="bool",
        label="Gate del contrato de aceptación (A1.1)",
        description=(
            "A1.1 — Ejecuta los chequeos del contrato en finalize_run. "
            "Todos pasan → completed; alguno falla → pase correctivo o needs_review."
        ),
        group="global",
    ),
    FlagSpec(
        key="STACKY_ACCEPTANCE_REPAIR_ENABLED",
        type="bool",
        label="Pase correctivo del contrato (A1.1)",
        description=(
            "A1.1 — Único pase correctivo dirigido al chequeo en rojo. Solo runtimes "
            "con resume. Re-ejecuta el contrato una vez. OFF = needs_review directo."
        ),
        group="global",
    ),
    FlagSpec(
        key="STACKY_ACCEPTANCE_REPAIR_MAX_RETRIES",
        type="int",
        label="Contrato: max reintentos pase correctivo",
        description="A1.1 — Presupuesto compartido con autocorrect/run_repair/Q1.1/E1.1 (default 1).",
        group="global",
    ),
    FlagSpec(
        key="STACKY_ACCEPTANCE_INTEGRITY_ENABLED",
        type="bool",
        label="Guard de independencia del contrato (A1.2)",
        description=(
            "A1.2 — Los artefactos del contrato se ejecutan desde ubicación de solo-arnés. "
            "Si el agente muta un generated_test → restaurado + 'mutated_checks' en metadata. "
            "OFF = ejecución desde path de proyecto (byte-idéntico)."
        ),
        group="global",
    ),
    FlagSpec(
        key="STACKY_ACCEPTANCE_VERDICT_CARD_ENABLED",
        type="bool",
        label="Card de contrato en verdict (A2.1)",
        description=(
            "A2.1 — Incluye acceptance_contract en el payload de la ejecución (read-only). "
            "Bloque compacto: 4/4 o chequeos en rojo con traza al ticket. "
            "Si ausente → campo omitido. OFF = payload byte-idéntico."
        ),
        group="global",
    ),
    FlagSpec(
        key="STACKY_ACCEPTANCE_KPIS_ENABLED",
        type="bool",
        label="KPIs del contrato en harness-health (A2.2)",
        description=(
            "A2.2 — Bloque 'acceptance_contract' en harness-health: tasa_contrato_derivable, "
            "tasa_cumplido_a_la_primera, tasa_recuperacion, calidad_del_examen, "
            "intentos_de_gameo_atrapados, cobertura_media. Read-only; degrada con gracia."
        ),
        group="global",
    ),
    # ── Plan 38 — Versión visible, épica desde brief, trazabilidad ──────────
    FlagSpec(
        key="STACKY_EPIC_FROM_BRIEF_ENABLED",
        type="bool",
        label="Épica desde Brief (B0)",
        description=(
            "Plan 38 B0 — Habilita POST /api/tickets/epics/from-brief. "
            "Human-in-the-loop duro: el operador debe enviar confirm:true. "
            "OFF = endpoint devuelve 404 feature_disabled."
        ),
        group="global",
        default=True,
    ),
    FlagSpec(
        key="STACKY_EXECUTION_TRACE_ENABLED",
        type="bool",
        label="Trazabilidad de ejecución (C0/C1)",
        description=(
            "Plan 38 C0/C1 — Agrega agent_type, agent_name, prompt_sha y produced_files "
            "a la metadata de cada ejecución (los 3 runtimes). "
            "OFF = metadata byte-idéntica al plan anterior."
        ),
        group="global",
        default=True,
    ),
    FlagSpec(
        key="STACKY_TRACE_PROMPT_TEXT_ENABLED",
        type="bool",
        label="Texto del prompt en trazabilidad (C0/C1, privacidad OFF)",
        description=(
            "Plan 38 C0/C1 — Si ON, incluye el texto completo del prompt (JSON de "
            "context_blocks) en la metadata. Privacidad: default OFF. Solo activar "
            "en ambientes controlados donde el contenido del prompt no es sensible."
        ),
        group="global",
    ),
    # ── Plan 39 — Historial de runs, fix épica CLI y BD read-only ────────────
    FlagSpec(
        key="STACKY_DB_READONLY_DIRECTIVE_ENABLED",
        type="bool",
        label="Directiva de acceso BD read-only (C2)",
        description=(
            "Plan 39 C2 — Si ON, inyecta una sección en el perfil del cliente con el "
            "usuario read-only de la BD configurado (readonly_user_hint / auth/db_readonly.json). "
            "NUNCA incluye el password. Guía al agente a usar sql_login en lugar de auth "
            "integrada de Windows. OFF = build_client_profile_block byte-idéntico."
        ),
        group="database",
    ),
    FlagSpec(
        key="STACKY_EXECUTION_HISTORY_ENABLED",
        type="bool",
        label="Historial de ejecuciones (A1)",
        description=(
            "Plan 39 A1 — Habilita GET /api/executions/history con historial completo: "
            "duración, costo, tokens, runtime, modelo, prompt_sha, archivos producidos. "
            "Soporta filtros por proyecto/agente/runtime/estado/días y paginación. "
            "OFF = endpoint devuelve 404 feature_disabled."
        ),
        group="observability",
    ),
    FlagSpec(
        key="STACKY_UNBLOCKER_COMPLETED_CAP",
        type="int",
        label="Desatascador: cap de tickets completados visibles",
        description=(
            "Plan 66 — Número máximo de tickets con readiness=completed_ok que aparecen "
            "en el board del desatascador. Los más antiguos se ocultan (se reportan en "
            "counts.completed_ok_truncated). Default 50 (inline). 0 = sin cota (todos). "
            "Editable por UI para no saturar el board con histórico."
        ),
        env_only=True,  # leído via os.environ.get en unblocker_board(); default 50 inline
        group="observabilidad_notif",
    ),
    # Plan 42 — flags nuevos
    FlagSpec(
        key="STACKY_BRIEF_MODEL_SELECT_ENABLED",
        type="bool",
        label="Selector de modelo/esfuerzo en Épica desde Brief (F3)",
        description=(
            "Plan 42 F3 — Si ON, el frontend puede enviar model+effort en el body de "
            "run-brief; el backend aplica clamp_model (cap sonnet-4-6) y valida effort. "
            "OFF = model_override=None + effort='high' siempre (igual que Plan 40)."
        ),
        env_only=True,  # leído via os.getenv; no es atributo de Config
        group="agents",
    ),
    FlagSpec(
        key="STACKY_INJECT_PROCESS_CATALOG",
        type="bool",
        label="Inyección de diccionario de procesos en context (F0)",
        description=(
            "Plan 42 F0 — Si ON, inyecta un bloque 'process-catalog' construido desde "
            "client_profile.process_catalog en los context blocks del agente. "
            "OFF = enrich_blocks byte-idéntico a Plan 41."
        ),
        env_only=True,  # leído via os.getenv; no es atributo de Config
        group="context",
    ),
    FlagSpec(
        key="STACKY_RAG_CATALOG_ENABLED",
        type="bool",
        label="RAG catálogo de procesos",
        description=(
            "Plan 64 — Si ON, inyecta solo los top-K procesos más relevantes al ticket "
            "(TF-IDF puro) en lugar del catálogo completo. "
            "Reduce ruido de contexto y mejora el grounding. Default OFF."
        ),
        group="global",
        pair="STACKY_RAG_CATALOG_TOP_K",
        env_only=True,  # leído via os.getenv en _inject_process_catalog_block
    ),
    FlagSpec(
        key="STACKY_RAG_CATALOG_TOP_K",
        type="int",
        label="RAG catálogo: top-K procesos",
        description=(
            "Plan 64 — Cantidad de procesos a recuperar por similitud TF-IDF cuando "
            "STACKY_RAG_CATALOG_ENABLED=true. Rango recomendado: 5-15. Default 8."
        ),
        group="global",
        env_only=True,  # leído via os.getenv en _inject_process_catalog_block
    ),
    FlagSpec(
        key="STACKY_PROCESS_DISCIPLINE_ENABLED",
        type="bool",
        label="Disciplina de procesos: reusar por default (Plan 67)",
        description=(
            "Plan 67 — Si ON, inyecta un bloque 'process-discipline' que decide "
            "REUTILIZAR un proceso existente del catálogo vs CREAR uno nuevo, según "
            "instrucción explícita del ticket y similitud con el catálogo. "
            "Default OFF = enrich_blocks byte-idéntico al Plan 64."
        ),
        group="contexto_memoria",
        env_only=False,  # editable por UI (Plan 62/63 HarnessFlagsPanel); NO es kill-switch interno
    ),
    FlagSpec(
        key="STACKY_EPIC_GROUNDING_PREFLIGHT_ENABLED",
        type="bool",
        label="Preflight de grounding en épica (F2)",
        description=(
            "Plan 42 F2 — Si ON, antes de publicar la épica en ADO verifica que el "
            "HTML cite módulos/procesos fuente; adjunta grounding_warnings en metadata "
            "pero NUNCA bloquea la publicación. OFF = autopublish_epic_from_run sin "
            "análisis de grounding."
        ),
        env_only=True,  # leído via os.getenv; no es atributo de Config
        group="agents",
    ),
    FlagSpec(
        key="STACKY_EPIC_SUMMARY_ENABLED",
        type="bool",
        label="Resumen post-épica accionable (F4)",
        description=(
            "Plan 42 F4 — Si ON, tras publicar la épica adjunta en metadata['epic_summary'] "
            "un resumen estructurado: ado_id, rf_count, cited_modules, warnings, confidence. "
            "OFF = autopublish_epic_from_run sin resumen."
        ),
        env_only=True,  # leído via os.getenv; no es atributo de Config
        group="agents",
    ),
    FlagSpec(
        key="STACKY_PROJECT_AUTOPROFILE_ENABLED",
        type="bool",
        label="Auto-perfilado de proyecto desde docs (F5)",
        description=(
            "Plan 42 F5 — Si ON, habilita GET /api/projects/{project}/autoprofile que "
            "deriva un perfil de proyecto de forma determinista desde los docs locales "
            "(sin LLM, sin inventar). Default OFF para no exponer un feature incompleto."
        ),
        env_only=True,  # leído via os.getenv; no es atributo de Config
        group="agents",
    ),
    FlagSpec(
        key="STACKY_GROUNDING_OBSERVATORY_ENABLED",
        type="bool",
        label="Observatorio de grounding de épicas (Plan 44)",
        description=(
            "Plan 44 F2 — Si ON, expone GET /api/agents/epics/grounding-observatory "
            "con métricas agregadas de grounding de épicas (solo-lectura, default ON). "
            "OFF = el endpoint responde 404 feature_disabled."
        ),
        group="agents",
        default=True,
    ),
    FlagSpec(
        key="STACKY_PROCESS_CATALOG_SUGGESTIONS_ENABLED",
        type="bool",
        label="Sugeridor de diccionario de procesos (Plan 44)",
        description=(
            "Plan 44 F3 — Si ON, expone GET /api/agents/projects/{project}/"
            "process-catalog-suggestions con procesos citados en épicas que faltan "
            "en el catálogo (solo sugiere, nunca escribe, default ON). OFF = 404."
        ),
        group="agents",
        default=True,
    ),
    FlagSpec(
        key="STACKY_OPERATIONAL_HEALTH_ENABLED",
        type="bool",
        label="Panel de salud operativa",
        description=(
            "Plan 46 — Triage solo-lectura de runs (needs_review/failed/caras/zombie). "
            "OFF = endpoint 404 y card oculta."
        ),
        group="global",
        env_only=True,
        default=True,
    ),
    FlagSpec(
        key="STACKY_OPERATOR_NOTE_TO_MEMORY_ENABLED",
        type="bool",
        label="Nota del operador → memoria",
        description=(
            "Plan 47 — Si ON, la nota humana de una run revisada se guarda como "
            "memoria operator_note reutilizable. Default OFF."
        ),
        group="global",
        env_only=True,
    ),
    FlagSpec(
        key="INTENT_PREFLIGHT_ENABLED",
        type="bool",
        label="Pre-vuelo de Intención (41)",
        description=(
            "Plan 41 — Si ON, antes del run genera un Brief de Intención que el "
            "operador aprueba/corrige. Default OFF (byte-idéntico al actual)."
        ),
        group="preflight",
    ),
    FlagSpec(
        key="INTENT_PREFLIGHT_AUTO_APPROVE",
        type="bool",
        label="Pre-vuelo: auto-aprobar si está claro",
        description=(
            "Plan 41 — Si ON, salta el modal cuando no hay preguntas abiertas y la "
            "confianza supera el umbral."
        ),
        group="preflight",
    ),
    FlagSpec(
        key="INTENT_PREFLIGHT_AUTO_APPROVE_MIN_CONF",
        type="float",
        label="Pre-vuelo: confianza mínima para auto-aprobar",
        description="Plan 41 — Umbral de confianza para auto-aprobar sin modal (default 0.8).",
        group="preflight",
    ),
    FlagSpec(
        key="STACKY_ARTIFACT_RESCUE_ENABLED",
        type="bool",
        label="Rescate de épica desde disco",
        description=(
            "Plan 47 — Si ON, cuando el agente narra en vez de devolver el HTML "
            "de la épica, el backend rescata el artefacto que el agente ya escribió "
            "en Agentes/outputs y lo publica. Default OFF."
        ),
        group="global",
        env_only=True,  # se lee con os.getenv en autopublish_epic_from_run
    ),
    FlagSpec(
        key="STACKY_PUSH_REJECTIONS_ENABLED",
        type="bool",
        label="Memoria que empuja: rechazos como anti-patrones",
        description=(
            "Plan 48+54 — Si ON, las notas de rechazo del operador (memoria "
            "operator_note) se inyectan como anti-patrones imperativos en el "
            "próximo run del mismo proyecto, en los 3 runtimes "
            "(copilot/claude_code_cli/codex). Default OFF."
        ),
        group="global",
    ),
    FlagSpec(
        key="STACKY_EPIC_SANITIZE_ENABLED",
        type="bool",
        label="Saneamiento de forma de la épica",
        description=(
            "Plan 50 F1 — Si ON, normaliza SOLO la forma del HTML de la épica "
            "antes de publicar (RF-12, fences residuales, emojis de checklist, "
            "dedup de bloques RF idénticos). Pura e idempotente. Default ON."
        ),
        group="global",
        env_only=True,  # se lee con os.getenv en _extract_epic_html
        default=True,
    ),
    FlagSpec(
        key="STACKY_EPIC_STRUCTURE_WARNINGS_ENABLED",
        type="bool",
        label="Warnings estructurales de la épica",
        description=(
            "Plan 50 F2 — Si ON, agrega warnings NO bloqueantes por defectos "
            "estructurales de la épica (RF duplicados/no consecutivos, headings "
            "vacíos, bloques RF sin contenido) al Observatorio. Default ON."
        ),
        group="global",
        env_only=True,  # se lee con os.getenv en _epic_grounding_warnings
        default=True,
    ),
    FlagSpec(
        key="STACKY_CATALOG_GROUNDING_WARNINGS_ENABLED",
        type="bool",
        label="Warnings de catálogo (grounding)",
        description=(
            "Plan 50 F3 — Si ON, warning NO bloqueante cuando la épica cita "
            "procesos que no existen en el process_catalog del proyecto. "
            "Default OFF (evita falsos positivos hasta catálogo curado)."
        ),
        group="global",
        env_only=True,  # se lee con os.getenv en el flujo de warnings de tickets
    ),
    FlagSpec(
        key="STACKY_COMMENT_FULL_SCAN_ENABLED",
        type="bool",
        label="Idempotencia: escanear todas las páginas de comentarios",
        description=(
            "Plan 52 F1 — Si ON (default), comment_exists recorre TODAS las "
            "páginas de comentarios del work item para encontrar el marker "
            "idempotente aunque haya >50 comentarios. Si OFF, vuelve al "
            "comportamiento legacy de 1 página."
        ),
        group="global",
        env_only=True,  # se lee con os.getenv en ado_client.comment_exists
        default=True,
    ),
    FlagSpec(
        key="STACKY_EPIC_GATE_ENABLED",
        type="bool",
        label="Gate correctivo determinista de épica",
        description=(
            "Plan 51 F3 — Si ON, ante defectos no reparables (huecos RF, bloques "
            "vacíos) bloquea el autopublish de la épica (needs_review) y dispara "
            "un pase correctivo inline ante defectos de forma reparables. "
            "Caso feliz = 0 tokens extra. Default OFF."
        ),
        group="global",
        env_only=True,  # se lee con os.getenv en api/tickets y el runner CLI
    ),
    FlagSpec(
        key="STACKY_EPIC_CATALOG_GATE_ENABLED",
        type="bool",
        label="Bloqueo por catálogo (procesos inventados)",
        description=(
            "Plan 51 F3 — Si ON (requiere STACKY_EPIC_GATE_ENABLED), un proceso "
            "citado que no exista en el process_catalog del cliente bloquea el "
            "autopublish. Opt-in dentro de opt-in. Default OFF."
        ),
        group="global",
        env_only=True,  # se lee con os.getenv en api/tickets
    ),
    # ── Plan 61 — Gate determinista del flujo funcional (Task) ──────────────────
    FlagSpec(
        key="STACKY_TASK_GATE_ENABLED",
        type="bool",
        label="Gate determinista del flujo funcional (Task)",
        description=(
            "Plan 61 — Si ON, clasifica defectos del pending-task.json antes de crear "
            "la Task en ADO y adjunta el veredicto (decision/defects/blocking) a la "
            "respuesta. Default OFF."
        ),
        group="global",
        env_only=True,
    ),
    FlagSpec(
        key="STACKY_TASK_GATE_BLOCKING",
        type="bool",
        label="Bloqueo del flujo funcional (Task)",
        description=(
            "Plan 61 — Requiere STACKY_TASK_GATE_ENABLED. Si ON, un defecto de "
            "severidad needs_review impide la creación en ADO (devuelve 400 "
            "TASK_GATE_BLOCKED). Default OFF."
        ),
        group="global",
        env_only=True,
    ),
    # ── Plan 53 — Selector adaptativo de modelo/effort por confidence ──────────
    FlagSpec(
        key="STACKY_ADAPTIVE_SELECTOR_ENABLED",
        type="bool",
        label="Selector adaptativo modelo/effort (Plan 53)",
        description=(
            "Plan 53 — Si ON, ajusta automáticamente modelo y effort según el "
            "confidence del grounding de la épica: bajo confidence → Opus/max; "
            "alto confidence → Sonnet/low. El override manual del operador "
            "(model/effort en el body) siempre gana. Default OFF."
        ),
        group="agents",
    ),
    # ── Plan 55 — Preview ejecutable ADO y portafolio N épicas ───────────────
    FlagSpec(
        key="STACKY_ADO_PREVIEW_ENABLED",
        type="bool",
        label="Preview ejecutable de publicación ADO (Plan 55)",
        description=(
            "Plan 55 — Si ON (default), habilita GET /api/tickets/epic-preview "
            "que simula la publicación en ADO sin escribir nada (solo-lectura). "
            "OFF = endpoint responde 404 feature_disabled."
        ),
        group="agents",
        env_only=True,  # leído via os.getenv en tickets.py; no es atributo de Config
        default=True,
    ),
    FlagSpec(
        key="STACKY_EPIC_PORTFOLIO_ENABLED",
        type="bool",
        label="Portafolio N épicas desde un brief (Plan 55, beta)",
        description=(
            "Plan 55 — Si ON, habilita la generación de N épicas en paralelo "
            "desde un único brief (feature beta, default OFF). "
            "OFF = endpoint devuelve 404 feature_disabled."
        ),
        group="agents",
        env_only=True,  # leído via os.getenv en tickets.py; no es atributo de Config
    ),
    # ── Plan 57 — FA-36 Especulación anticipatoria (kill-switches internos) ───
    FlagSpec(
        key="STACKY_SPECULATIVE_ENABLED",
        type="bool",
        label="Especulación anticipatoria FA-36",
        description=(
            "Plan 57 — Kill-switch interno de FA-36. Si ON (env-only), el backend "
            "pre-ejecuta el agente en background antes de que el operador confirme. "
            "Cuando confirma, si el hash coincide → latencia cero. "
            "Default OFF. Activar SOLO tras F0 auditoría = 5 PASS."
        ),
        group="global",
        env_only=True,
    ),
    FlagSpec(
        key="STACKY_SPECULATIVE_MODE",
        type="csv",
        label="Modo de especulación anticipatoria",
        description=(
            "Plan 57 — Modo de FA-36: 'eager' (especula ASAP) | 'lazy' (deferred v1.1) | "
            "'off'. En v1 solo 'eager' es operativo; 'lazy' hace fallback a eager con "
            "warning. Ignorado si STACKY_SPECULATIVE_ENABLED=false."
        ),
        group="global",
        env_only=True,
    ),
    # ── Plan 59 — Descomposición vertical épica→hijos ────────────────────────
    FlagSpec(
        key="STACKY_EPIC_DECOMPOSITION_ENABLED",
        type="bool",
        label="Descomposición vertical épica→hijos",
        description=(
            "Plan 59 — Si ON, tras aprobar una épica el operador puede previsualizar "
            "y crear los hijos (Features/Tasks) colgando del Epic. "
            "Default OFF = solo el Epic, sin desglose hijo."
        ),
        group="global",
        env_only=True,  # leído con os.getenv en api/tickets en call time
    ),
    # ── Plan 58 — Bucle de convergencia de calidad determinista (épica) ──────
    FlagSpec(
        key="STACKY_QUALITY_CONVERGENCE_ENABLED",
        type="bool",
        label="Bucle de convergencia de calidad (épica)",
        description=(
            "Plan 58 — Si ON, el pase correctivo de épica re-evalúa el gate y reintenta "
            "hasta PASS o agotar el presupuesto. OFF = un solo pase (actual)."
        ),
        group="global",
    ),
    FlagSpec(
        key="STACKY_QUALITY_CONVERGENCE_MAX_ITERATIONS",
        type="int",
        label="Máx. iteraciones de convergencia",
        description=(
            "Plan 58 — Máximo de pases correctivos del bucle (>=1). 1 = single-shot. Default 2."
        ),
        group="global",
    ),
    # ── Plan 60 — Aprendizaje bidireccional: ediciones humanas en ADO ─────────
    FlagSpec(
        key="STACKY_ADO_EDIT_LEARNING_ENABLED",
        type="bool",
        label="Aprender de ediciones en ADO (plan 60)",
        description=(
            "Plan 60 — Si ON, Stacky lee de vuelta las correcciones humanas del WI publicado "
            "y las materializa como lección en el corpus (plan 54). Pasivo, default OFF."
        ),
        group="global",
        env_only=True,
    ),
    FlagSpec(
        key="STACKY_ADO_EDIT_SWEEP_HOURS",
        type="int",
        label="Intervalo del sweep ADO (horas)",
        description=(
            "Plan 60 — Cada cuántas horas el daemon relee los WI publicados buscando "
            "ediciones humanas. Default 6."
        ),
        group="global",
        env_only=True,
    ),
    FlagSpec(
        key="STACKY_ADO_SERVICE_IDENTITY",
        type="csv",
        label="Identidad(es) de servicio Stacky en ADO",
        description=(
            "Plan 60 — CSV de uniqueName/displayName con que Stacky publica WI en ADO; "
            "sus revisiones se ignoran como 'no humanas'. Vacío = heurístico por autor de baseline."
        ),
        group="global",
        env_only=True,
    ),
    FlagSpec(
        key="STACKY_TICKETS_PROVIDER_ENABLED",
        type="bool",
        label="Tracker Provider en tickets.py (Plan 70)",
        description=(
            "Plan 70 — Si ON, api/tickets.py enruta sus call sites por el puerto "
            "TrackerProvider (get_tracker_provider) en vez de por "
            "_ado_client_for_ticket; cae al fallback ADO si el provider del "
            "proyecto no está disponible (ej. GitLab sin STACKY_GITLAB_ENABLED). "
            "OFF (default): byte-idéntico al comportamiento pre-Plan-70."
        ),
        group="global",
        env_only=False,  # editable por UI (regla dura operator-config-always-via-ui)
    ),
    FlagSpec(
        key="STACKY_PIPELINE_PROVIDER_ENABLED",
        type="bool",
        label="CIProvider sub-puerto (Plan 71)",
        description=(
            "Plan 71 — Si ON, los endpoints ado-pipeline-status y ado-pipeline-batch "
            "enrutan por el sub-puerto CIProvider (AdoCIProvider / GitLabCIProvider) "
            "en vez de llamar directamente a infer_pipeline. Habilita inferencia CI "
            "agnóstica del tracker (ADO + GitLab). OFF (default): comportamiento "
            "pre-Plan-71 byte-idéntico."
        ),
        group="global",
        env_only=False,  # editable por UI (regla dura operator-config-always-via-ui)
    ),
    FlagSpec(
        key="STACKY_PIPELINE_TRIGGER_ENABLED",
        type="bool",
        label="Trigger y monitoreo CI — HITL (Plan 72)",
        description=(
            "Plan 72 — Si ON, habilita los endpoints POST /api/ci/<project>/trigger "
            "(dispara pipeline CI con confirm=True obligatorio — HITL) y "
            "GET /api/ci/<project>/pipeline/<id> (monitoreo). "
            "PAT GitLab debe tener scope api. Default OFF. "
            "OFF: guard 404 per-request; el blueprint siempre está registrado."
        ),
        group="global",
        env_only=False,  # editable por UI (regla dura operator-config-always-via-ui)
    ),
    FlagSpec(
        key="STACKY_PIPELINE_GENERATOR_ENABLED",
        type="bool",
        label="Generador declarativo de pipelines ADO/GitLab (Plan 73)",
        description=(
            "Plan 73 — Si ON, habilita el generador declarativo PipelineSpec→YAML. "
            "Endpoints: POST /api/pipeline-generator/preview (render ADO+GitLab puro, sin commit) "
            "y POST /api/pipeline-generator/commit (commit en repo vía HITL confirm=True). "
            "PAT GitLab debe tener scope api para commit. "
            "Default OFF. OFF: guard 404 per-request; el blueprint siempre está registrado."
        ),
        group="global",
        env_only=False,  # editable por UI (regla dura operator-config-always-via-ui, C9)
    ),
    # ── Plan 74 — Migrador ADO→GitLab ────────────────────────────────────────
    FlagSpec(
        key="STACKY_MIGRATOR_ADO_TO_GITLAB_ENABLED",
        type="bool",
        label="Migrador ADO → GitLab (Plan 74)",
        description=(
            "Plan 74 — Habilita la migración segura e idempotente de work items ADO→GitLab. "
            "Expone POST /api/migrator/plan (dry-run) y POST /api/migrator/execute (HITL confirm=True). "
            "La migración es read-only sobre ADO; el dry-run es obligatorio antes de ejecutar. "
            "Default OFF. Con OFF, los endpoints retornan 503."
        ),
        group="global",
        env_only=False,  # editable por UI (categoría 'migrador_ado_gitlab')
    ),
    FlagSpec(
        key="STACKY_MIGRATOR_EPIC_POLICY",
        type="str",
        label="Política de épicas en migración ADO→GitLab (Plan 74)",
        description=(
            "Plan 74 — Cómo migrar épicas ADO en GitLab. "
            "auto: detecta si GitLab tiene licencia Premium (group epics) y elige el modo; "
            "premium_native: fuerza epic nativo (falla si no hay licencia); "
            "free_degrade: siempre issue + label type::epic (compatible con GitLab Free). "
            "Default: auto."
        ),
        group="global",
        env_only=False,  # editable por UI (categoría 'migrador_ado_gitlab')
        default="auto",
    ),
    # ── Plan 75 — Deep links bidireccionales GitLab ───────────────────────────
    FlagSpec(
        key="STACKY_GITLAB_DEEP_LINKS_ENABLED",
        type="bool",
        label="Deep links GitLab bidireccionales (Plan 75)",
        description=(
            "Plan 75 — Si ON, habilita la composición de deep links GitLab (issue, MR, "
            "commit, épica) en el backend. Con OFF, item_url/mr_url/commit_url/epic_url "
            "del provider GitLab devuelven None y el frontend muestra el ID como texto plano. "
            "Default OFF. Activa cuando el proyecto use GitLab y quieras links clickeables."
        ),
        group="global",
        env_only=False,  # editable por UI (categoría 'gitlab_deep_links')
    ),
)

# Índice rápido para lookups O(1)
_REGISTRY_INDEX: dict[str, FlagSpec] = {s.key: s for s in FLAG_REGISTRY}

_KEY_CATEGORY: dict[str, str] = {
    key: cat_id for cat_id, keys in _CATEGORY_KEYS.items() for key in keys
}


def categorize(key: str) -> str:
    """Categoría (id) de una flag. Fallback determinista a 'otros'."""
    return _KEY_CATEGORY.get(key, "otros")


def _type_zero(flag_type: str) -> object:
    if flag_type == "bool":
        return False
    if flag_type in ("csv", "json"):
        return ""
    if flag_type == "float":
        return 0.0
    return 0  # int


def declared_default(spec: FlagSpec) -> object:
    """Default DECLARADO para la UI. spec.default si está; si no, type-zero (= off/seguro)."""
    return spec.default if spec.default is not None else _type_zero(spec.type)


def default_is_known(spec: FlagSpec) -> bool:
    """v2/C1 — True solo si el default fue curado con confianza (spec.default explícito)."""
    return spec.default is not None


def is_active(spec: FlagSpec, value: object) -> bool:
    """v2/C1 — 'con valor / activa': el valor difiere de su type-zero."""
    if spec.type == "bool":
        return bool(value)
    if spec.type in ("int", "float"):
        try:
            return float(value) != 0.0
        except (TypeError, ValueError):
            return bool(str(value).strip())
    return bool(str(value).strip())  # csv / json (string)


def list_categories() -> list[dict]:
    """Categorías ordenadas para el frontend (id/label/description)."""
    return [{"id": c.id, "label": c.label, "description": c.description}
            for c in FLAG_CATEGORIES]


def read_current() -> list[dict]:
    """Devuelve spec + valor actual de cada flag del registry."""
    from config import config

    result = []
    for spec in FLAG_REGISTRY:
        if spec.env_only:
            raw = os.getenv(spec.key)
            if raw is None:
                value: object = (
                    False if spec.type == "bool"
                    else ("" if spec.type in ("csv", "json")
                    else (0.0 if spec.type == "float"
                    else 0))
                )
            else:
                value = _cast(spec, raw)
        else:
            value = getattr(config, spec.key)

        result.append({
            "key": spec.key,
            "type": spec.type,
            "label": spec.label,
            "description": spec.description,
            "group": spec.group,
            "pair": spec.pair,
            "env_only": spec.env_only,
            "value": value,
            "category": categorize(spec.key),
            "default": declared_default(spec),
            "default_known": default_is_known(spec),
            "active": is_active(spec, value),
        })
    return result


def apply_updates(updates: dict[str, object]) -> dict[str, object]:
    """Valida y castea los valores recibidos.

    Returns:
        Dict con los valores tipados y listos para persistir/aplicar.

    Raises:
        ValueError: si alguna key no está en el registry, o el valor no puede
            castearse al tipo declarado.

    No persiste ni aplica (eso es responsabilidad del endpoint).
    """
    result: dict[str, object] = {}
    for key, raw_value in updates.items():
        if key not in _REGISTRY_INDEX:
            raise ValueError(
                f"Flag desconocida: {key!r}. Solo se aceptan keys registradas en FLAG_REGISTRY."
            )
        spec = _REGISTRY_INDEX[key]
        result[key] = _cast(spec, raw_value)
    return result


def get_flag(key: str) -> bool:
    """Lee un flag bool del registry por env var (Plan 67 — convenience helper).

    Lee directamente os.getenv. Default False si la var no está configurada.
    Útil para lazy-import dentro de funciones; patchen en tests para controlar
    el valor sin setear env vars reales.
    """
    return os.getenv(key, "false").strip().lower() in {"1", "true", "on", "yes"}


def _cast(spec: FlagSpec, raw: object) -> object:
    """Castea `raw` al tipo declarado por `spec`. Lanza ValueError si no puede."""
    if spec.type == "bool":
        if isinstance(raw, bool):
            return raw
        s = str(raw).strip().lower()
        if s in ("1", "true", "yes", "on"):
            return True
        if s in ("0", "false", "no", "off", ""):
            return False
        raise ValueError(
            f"Flag {spec.key!r}: valor no válido para bool: {raw!r}. "
            "Usar true/false, 1/0, yes/no."
        )
    if spec.type == "csv":
        # Normalizar: trim por elemento, trailing comas eliminadas
        parts = [p.strip() for p in str(raw).split(",") if p.strip()]
        return ",".join(parts)
    if spec.type == "int":
        try:
            return int(str(raw).strip())
        except (ValueError, TypeError):
            raise ValueError(
                f"Flag {spec.key!r}: valor no válido para int: {raw!r}."
            )
    if spec.type == "float":
        try:
            return float(str(raw).strip())
        except (ValueError, TypeError):
            raise ValueError(
                f"Flag {spec.key!r}: valor no válido para float: {raw!r}."
            )
    if spec.type == "json":
        # Texto crudo JSON. "" = vacío (usar default del consumidor). Si no es
        # vacío, debe parsear; si no, se rechaza el hot-apply (mejor que dejar
        # entrar un JSON roto que el consumidor ignora en silencio).
        import json as _json

        s = "" if raw is None else str(raw).strip()
        if s == "":
            return ""
        try:
            _json.loads(s)
        except Exception:
            raise ValueError(
                f"Flag {spec.key!r}: valor no válido para json: {raw!r}."
            )
        return s
    raise ValueError(f"Tipo desconocido en FLAG_REGISTRY para {spec.key!r}: {spec.type!r}")
