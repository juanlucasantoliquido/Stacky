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

from services.harness_flags_help import plain_help_for  # Plan 86 — ayuda en lenguaje llano


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
    requires: str | None = None  # Plan 82 — key de una flag bool que debe estar ON para que
                                 # esta flag tenga efecto. None = sin dependencia. Solo
                                 # informativo para la UI; NINGÚN runner lo evalúa.
    min_value: float | None = None  # Plan 83 — mínimo válido inclusive (solo type int/float).
    max_value: float | None = None  # Plan 83 — máximo válido inclusive. None = sin límite.
                                    # Solo los evalúan apply_updates y read_current; NINGÚN runner.
    restart_required: bool = False  # Plan 84 — True = la flag se consume UNA vez en
                                    # create_app (arranque de daemons); un cambio por UI
                                    # persiste pero NO aplica hasta reiniciar el backend.
                                    # Solo informativo para la UI; ningún runner lo evalúa.
    reserved: bool = False        # Plan 85 — True = declarada para fase diferida, SIN consumidor aún
    reserved_reason: str = ""     # Plan 85 — obligatoria si reserved=True (qué fase la cablea)


@dataclass(frozen=True)
class CategorySpec:
    id: str          # slug estable (no cambia)
    label: str       # título humano para la UI (español)
    description: str # 1 línea: qué controla esta categoría
    tier: str = "advanced"  # "simple" | "advanced" — nivel de profundidad para la UI (Plan 78)
    intent: str = ""        # frase humana "¿qué querés lograr?" para navegación por intención (Plan 78)


FLAG_CATEGORIES: tuple[CategorySpec, ...] = (
    # Plan 78 — tier/intent aditivos. Default tier="advanced" si no se declara (seguro: cae al catch-all).
    CategorySpec("runtimes_cli", "Runtimes CLI (Claude / Codex)",
        "Comportamiento de los agentes que corren como CLI: gates de contrato, autocorrección, hooks, resume, MCP, modelos.",
        tier="simple", intent="Elegir cómo y con qué modelo corren los agentes"),
    CategorySpec("contexto_memoria", "Contexto y memoria",
        "Qué información recibe el agente: presupuesto/dedup/rerank de contexto, memoria colaborativa, skills, few-shot, catálogo.",
        tier="advanced", intent="Qué información y memoria recibe el agente"),
    CategorySpec("calidad_verificacion", "Calidad y verificación del entregable",
        "Criterios de aceptación, verificación ejecutable, contrato de aceptación, anti-verde-falso, convergencia, self-review, esfuerzo.",
        tier="simple", intent="Asegurar que el entregable cumpla y esté verificado"),
    CategorySpec("integridad_grounding", "Integridad y grounding del resultado",
        "Verifica que lo que el agente afirma sea real: precondiciones, verificación post-create de tasks, anclado de referencias.",
        tier="advanced", intent="Verificar que lo que el agente afirma sea real"),
    CategorySpec("epicas_ado", "Épicas, briefs y publicación en ADO",
        "Generación, saneamiento, gates, preview, descomposición y selector de modelo de épicas/issues hacia Azure DevOps.",
        tier="simple", intent="Generar y publicar épicas e issues en ADO"),
    CategorySpec("flujo_funcional", "Flujo funcional (Tasks)",
        "Creación de Tasks funcionales en ADO y su gate determinista.",
        tier="advanced", intent="Crear Tasks funcionales en ADO"),
    CategorySpec("routing_costo", "Routing de modelo y costo",
        "Estimación de complejidad, routing por dificultad, advisor de runtime, presupuesto por ticket, caché de runs, evals.",
        tier="simple", intent="Controlar el costo y a qué modelo va cada ticket"),
    CategorySpec("fiabilidad_ciclo_vida", "Fiabilidad y ciclo de vida del run",
        "Higiene de procesos: reaping, watchdog, validación pending-task, idempotencia, retries, runaway guard, auto-reparación, intake.",
        tier="advanced", intent="Mantener sanos los procesos y reintentos"),
    CategorySpec("observabilidad_notif", "Observabilidad y notificaciones",
        "KPIs en harness-health, historial, footer ADO, webhooks, notificaciones, telemetría en vivo, salud operativa, pipelines, trazabilidad.",
        tier="simple", intent="Ver salud, KPIs y recibir notificaciones"),
    CategorySpec("aprendizaje", "Aprendizaje y memoria que empuja",
        "Rechazos como anti-patrones, nota del operador a memoria, aprendizaje desde ediciones humanas en ADO.",
        tier="advanced", intent="Que Stacky aprenda de rechazos y ediciones"),
    CategorySpec("preflight_intencion", "Pre-vuelo de intención",
        "Brief de intención negociable que el operador aprueba antes del run.",
        tier="advanced", intent="Aprobar la intención antes de que el agente corra"),
    CategorySpec("base_datos", "Base de datos y caché ADO",
        "Directiva de acceso read-only a la BD, caché y pre-warm de lecturas caras de ADO.",
        tier="advanced", intent="Acceso read-only y caché de la base ADO"),
    CategorySpec("avanzado", "Avanzado / experimental",
        "Kill-switches internos y features beta: egress check, especulación anticipatoria.",
        tier="advanced", intent="Kill-switches internos y features beta"),
    CategorySpec("migrador_ado_gitlab", "Migrador ADO → GitLab",
        "Plan 74 — Migración segura e idempotente de work items ADO (épicas, issues, tasks, comentarios, attachments) hacia GitLab.",
        tier="advanced", intent="Migrar work items de ADO a GitLab"),
    CategorySpec("gitlab_deep_links", "GitLab / Deep Links",
        "Plan 75 — Deep links bidireccionales GitLab: issue, MR, pipeline, commit, épica. Kill-switch con default OFF.",
        tier="advanced", intent="Activar deep links bidireccionales con GitLab"),
    CategorySpec("devops", "DevOps",
        "Panel DevOps: creación gráfica de pipelines y operaciones de publicación.",
        tier="advanced", intent="Crear y gestionar pipelines de CI/CD visualmente"),
    CategorySpec("capacidades_optin", "Capacidades opt-in",
        "Features que activás y usás a demanda (botón/tab/endpoint) y que NO disparan trabajo ni costo dentro de otro flujo: documentador, grafo/staleness de docs, retrieval híbrido, migrador ADO→GitLab, deep links GitLab, MCP externo, descomposición/portafolio de épicas, asesores read-only, prewarm de caché.",
        tier="simple", intent="Activar capacidades opcionales que usás cuando querés"),
    CategorySpec("comparador_bd", "Comparador de BD entre ambientes",
        "Serie 122-126 — comparación de esquema/datos entre ambientes, snapshots, scripts de paridad y backups.",
        tier="simple", intent="Comparar bases entre ambientes y generar scripts de paridad"),
    CategorySpec("interfaz_ui", "Interfaz",
        "Aspecto y disposición de la aplicación: estilo de navegación (fila de pestañas o barra lateral agrupada) y presentación general.",
        tier="simple", intent="Elegir el estilo de navegación y la presentación de la app"),
    CategorySpec("otros", "Otros / sin categorizar",
        "Flags aún no asignadas a una categoría (no debería haber ninguna; el test lo garantiza).",
        tier="advanced", intent="Flags sin categorizar (no debería haber ninguna)"),
)

_CATEGORY_KEYS: dict[str, tuple[str, ...]] = {
    "runtimes_cli": (
        "CLAUDE_CODE_CLI_CONTRACT_GATE_ENABLED", "CLAUDE_CODE_CLI_AUTOCORRECT_ENABLED",
        "CLAUDE_CODE_CLI_AUTOCORRECT_MAX_RETRIES", "CLAUDE_CODE_CLI_HOOKS_ENABLED",
        "CLAUDE_CODE_CLI_PROJECT_KNOWLEDGE_ENABLED", "CLAUDE_CODE_CLI_PROJECT_KNOWLEDGE_PROJECTS",
        "CLAUDE_CODE_CLI_RESUME_ENABLED", "CLAUDE_CODE_CLI_RESUME_PROJECTS",
        "CLAUDE_CODE_CLI_MCP_ENABLED", "CLAUDE_CODE_CLI_MCP_PROJECTS",
        "CLAUDE_CODE_CLI_TRUST_PREFLIGHT_ENABLED", "CLAUDE_CODE_CLI_TRUST_AUTOSET_ENABLED",  # Plan 144
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
        "STACKY_INJECT_PROCESS_CATALOG",
        "STACKY_RAG_CATALOG_ENABLED", "STACKY_RAG_CATALOG_TOP_K",
        "STACKY_PROCESS_DISCIPLINE_ENABLED",   # Plan 67, C6 v2.1
        # NOTA: los masters DOCS_GRAPH / DOCS_RAG_HYBRID / DOCS_DOCUMENTER / DOCS_STALENESS
        # y CAPS_ADVISOR se movieron a "capacidades_optin" (features opt-in). Sus knobs
        # de tuning (ALPHA/BETA/MAX_NEIGHBORS/MAX_FILES) quedan aquí, con requires al master.
        "STACKY_DOCS_RAG_HYBRID_ALPHA", "STACKY_DOCS_RAG_HYBRID_BETA",
        "STACKY_DOCS_RAG_HYBRID_MAX_NEIGHBORS",  # Plan 112 — pesos + tope vecinos
        "STACKY_DOCS_DOCUMENTER_MAX_FILES",  # Plan 113 — tope de archivos por run
        "STACKY_DOCS_DOCUMENTER_EVIDENCE_MAX_CHARS",  # Plan 137 — tope de evidencia de código
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
        # NOTA: EPIC_PORTFOLIO y EPIC_DECOMPOSITION (features opt-in) → "capacidades_optin".
        "STACKY_ADAPTIVE_SELECTOR_ENABLED", "STACKY_PROJECT_AUTOPROFILE_ENABLED",
        "STACKY_COMMENT_FULL_SCAN_ENABLED",
        "STACKY_ISSUE_PHASE_COMMENTS_ENABLED",  # Plan 77 — fases de Issue como comentarios idempotentes
        "STACKY_TICKETS_PROVIDER_ENABLED",   # Plan 70 — consumers por puerto TrackerProvider
        "STACKY_PIPELINE_PROVIDER_ENABLED",  # Plan 71 — sub-puerto CIProvider
        "STACKY_PIPELINE_TRIGGER_ENABLED",   # Plan 72 — trigger y monitoreo CI (HITL)
        "STACKY_PIPELINE_GENERATOR_ENABLED", # Plan 73 — generador declarativo PipelineSpec→YAML
    ),
    "migrador_ado_gitlab": (
        # NOTA: el master STACKY_MIGRATOR_ADO_TO_GITLAB_ENABLED (feature opt-in) → "capacidades_optin".
        "STACKY_MIGRATOR_EPIC_POLICY",             # Plan 74 — política de épicas (auto|premium_native|free_degrade)
    ),
    "gitlab_deep_links": (
        # NOTA: el master STACKY_GITLAB_DEEP_LINKS_ENABLED (feature opt-in) → "capacidades_optin".
        # Categoría sin keys propias por ahora (solo el master, ya movido).
    ),
    "devops": (
        "STACKY_DEVOPS_PANEL_ENABLED",  # Plan 87 — panel DevOps: creador gráfico de pipelines
        "STACKY_DEVOPS_PUBLICATIONS_ENABLED",  # Plan 88 — publicaciones parametrizables de procesos
        "STACKY_DEVOPS_ENVIRONMENTS_ENABLED",  # Plan 89 — inicialización de ambientes
        "STACKY_DEVOPS_AGENT_ENABLED",  # Plan 90 — agente DevOps interactivo multi-turno
        "STACKY_DEVOPS_SERVERS_ENABLED",  # Plan 91 — registro de servidores DevOps
        "STACKY_DEVOPS_PREFLIGHT_ENABLED",  # Plan 93 — preflight semáforo de pipelines
        "STACKY_DEVOPS_VARIABLES_ENABLED",  # Plan 94 — caja fuerte variables secretas
        "STACKY_DEVOPS_STACK_DETECT_ENABLED",  # Plan 97 — deteccion de stack para presets
        "STACKY_DEVOPS_PRODUCTION_ENABLED",  # Plan 95 — llevar a producción MR/PR
        "STACKY_DEVOPS_DOCTOR_ENABLED",  # Plan 96 — doctor de pipelines: diagnóstico en llano
        "STACKY_DEVOPS_SECTION_DOCTOR_ENABLED",  # Plan 104 — doctores IA por sección
        "STACKY_DEVOPS_BOOTSTRAP_ENABLED",  # Plan 98 — bootstrap unico + PATCH por clave
        "STACKY_DEVOPS_REMOTE_CONSOLE_ENABLED",  # Plan 105 — consola remota
        "STACKY_DEVOPS_REMOTE_TARGET_ENABLED",  # Plan 108 — anclaje remoto agente/ambientes
        "STACKY_DEVOPS_ENV_TREE_PREVIEW_ENABLED",  # Plan 107 — preview de árbol de ambientes
        "STACKY_DEVOPS_ENV_SANDBOX_ENABLED",  # Plan 107 — raíz sandbox de pruebas
        "STACKY_DEVOPS_CONNECTION_DOCTOR_ENABLED",  # Plan 116 — doctor de conexiones
        "STACKY_DEPLOYMENTS_ENABLED",  # Plan 120 — Centro de Despliegues (master)
        "STACKY_DEPLOYMENTS_EXECUTE_ENABLED",  # Plan 120 — habilita ejecutar deploy/rollback
        "STACKY_DEPLOYMENTS_AI_DIAGNOSIS_ENABLED",  # Plan 120 — diagnóstico IA local de fallas
        "STACKY_DEPLOYMENTS_RETAIN_RELEASES",  # Plan 120 — releases retenidas por destino
        "STACKY_DEPLOYMENTS_SMOKE_TIMEOUT_SEC",  # Plan 120 — timeout del smoke post-deploy
        "STACKY_PR_REVIEWER_ENABLED",       # Plan 110 — revisor de PRs
        "STACKY_PR_REVIEW_HAIKU_MODEL",     # Plan 110 — modelo Haiku para la revisión
        "STACKY_PR_REVIEW_DIFF_MAX_CHARS",  # Plan 110 — tope del diff (privacidad, camino Haiku)
        "STACKY_PR_REVIEW_LOCAL_DIFF_MAX_CHARS",  # Plan 110 v2.1 — tope del diff del camino solo-local (velocidad, 0=sin límite)
        "STACKY_PR_REVIEW_TIMEOUT_SEC",     # Plan 110 — timeout de la revisión Haiku
        "STACKY_DEVOPS_UI_V2_ENABLED",  # Plan 119 — rediseño minimalista del shell DevOps
    ),
    "flujo_funcional": (
        "STACKY_TASK_GATE_ENABLED", "STACKY_TASK_GATE_BLOCKING",
        "STACKY_DETERMINISTIC_TASK_STATES_ENABLED",
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
        "STACKY_INTEGRATION_DEGRADATION_ENABLED",  # Plan 148 — degradacion de integraciones
        "STACKY_INTAKE_QUARANTINE_SURFACE_ENABLED",  # Plan 149 F4 — cuarentena intake en board
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
        "STACKY_COST_CENTER_ENABLED", "STACKY_COST_CODEBURN_IMPORT_ENABLED",
        "STACKY_COST_CODEBURN_IMPORT_PATH",  # Plan 142
        "STACKY_TYPED_ERROR_ENVELOPE_ENABLED",  # Plan 149 F0 — envelope de errores tipado
    ),
    "aprendizaje": (
        "STACKY_PUSH_REJECTIONS_ENABLED", "STACKY_OPERATOR_NOTE_TO_MEMORY_ENABLED",
        "STACKY_ADO_EDIT_LEARNING_ENABLED", "STACKY_ADO_EDIT_SWEEP_HOURS",
        "STACKY_ADO_SERVICE_IDENTITY", "STACKY_NEGATIVE_GOLDEN_FROM_EDITS_ENABLED",
    ),
    "preflight_intencion": (
        "INTENT_PREFLIGHT_ENABLED", "INTENT_PREFLIGHT_AUTO_APPROVE",
        "INTENT_PREFLIGHT_AUTO_APPROVE_MIN_CONF",
    ),
    "base_datos": (
        # NOTA: el master STACKY_ADO_PREWARM_ENABLED (feature opt-in) → "capacidades_optin".
        # STACKY_ADO_READ_CACHE_TTL_SEC (que lo habilita de verdad) queda aquí.
        "STACKY_DB_READONLY_DIRECTIVE_ENABLED", "STACKY_ADO_READ_CACHE_TTL_SEC",
    ),
    "avanzado": (
        "STACKY_CLI_EGRESS_ENABLED", "STACKY_SPECULATIVE_ENABLED", "STACKY_SPECULATIVE_MODE",
        # NOTA: el master STACKY_CODEBASE_MEMORY_MCP_ENABLED (feature opt-in) → "capacidades_optin".
        "STACKY_CODEBASE_MEMORY_MCP_PROJECTS", "STACKY_CODEBASE_MEMORY_MCP_BINARY_PATH",  # Plan 80
        "LOCAL_LLM_ENABLED", "LOCAL_LLM_ENDPOINT", "LOCAL_LLM_MODEL", "LOCAL_LLM_TIMEOUT_SEC",  # Plan 106
        "STACKY_LOCAL_INSIGHTS_ENABLED", "STACKY_LOCAL_INSIGHTS_SWEEP_SEC",  # Plan 117
        "STACKY_LOCAL_INSIGHTS_MAX_PER_CYCLE", "STACKY_LOCAL_INSIGHTS_LOOKBACK_DAYS",  # Plan 117
        "STACKY_LOCAL_INSIGHTS_DIGEST_NARRATIVE_ENABLED",  # Plan 117
    ),
    "capacidades_optin": (
        # Activación operador 2026-07-10 — features que el operador invoca a demanda
        # (botón/tab/endpoint) y NO disparan trabajo ni costo dentro de otro flujo.
        # Todas promovidas a default ON; agrupadas aquí para que se vean distintas.
        "STACKY_DOCS_GRAPH_ENABLED",            # Plan 109 — grafo documental read-only (tab Docs)
        "STACKY_DOCS_STALENESS_ENABLED",        # Plan 114 — chip staleness doc↔código
        "STACKY_DOCS_DOCUMENTER_ENABLED",       # Plan 113 — botón "Lanzar Documentador"
        "STACKY_DOCS_DOCUMENTER_V2_ENABLED",    # Plan 137 — evidencia real + citas + historial
        "STACKY_DOCS_RAG_HYBRID_ENABLED",       # Plan 112 — retrieval híbrido docs
        "STACKY_CAPS_ADVISOR_ENABLED",          # I3.3 — GET /metrics/caps-advisor (solo lectura)
        "STACKY_MIGRATOR_ADO_TO_GITLAB_ENABLED",# Plan 74 — migrador ADO→GitLab (dry-run + HITL)
        "STACKY_EPIC_DECOMPOSITION_ENABLED",    # Plan 59 — previsualizar/crear hijos de la épica
        "STACKY_EPIC_PORTFOLIO_ENABLED",        # Plan 55 — N épicas desde un brief (beta)
        "STACKY_CODEBASE_MEMORY_MCP_ENABLED",   # Plan 76 — MCP externo opt-in (estado + guía)
        "STACKY_GITLAB_DEEP_LINKS_ENABLED",     # Plan 75 — deep links GitLab clickeables
        "STACKY_ADO_PREWARM_ENABLED",           # I0.3 — prewarm caché ADO (inerte sin TTL>0)
        "STACKY_DB_COMPARE_ENABLED",            # Plan 122 — comparador de BD entre ambientes (master, default OFF)
    ),
    "comparador_bd": (
        "STACKY_DB_COMPARE_CONNECT_TIMEOUT_SEC",  # Plan 122
        "STACKY_DB_COMPARE_DATA_DIFF_ENABLED",    # Plan 126
        "STACKY_DB_COMPARE_DATA_MAX_ROWS",        # Plan 126
    ),
    "interfaz_ui": (
        "STACKY_UI_SHELL_V2_ENABLED",  # Plan 139 — shell v2 (sidebar agrupada + TopBar + iconografía)
    ),
    # "otros" intencionalmente vacío: es el fallback de categorize().
}

# NOTA: toda flag nueva debe agregarse también a _CATEGORY_KEYS (arriba) o el test
# test_every_registry_flag_is_categorized rompe CI a propósito (Plan 63).
FLAG_REGISTRY: tuple[FlagSpec, ...] = (
    FlagSpec(
        key="CLAUDE_CODE_CLI_CONTRACT_GATE_ENABLED",
        type="bool",
        default=True,  # promovida a default ON (operador 2026-07-15, barrido de flags 122-141 + revision general)
        label="Gate de contrato (claude)",
        description="F1.1 — Si ON, outputs con errores duros degradan el run a needs_review.",
        group="claude_code_cli",
    ),
    FlagSpec(
        key="CLAUDE_CODE_CLI_AUTOCORRECT_ENABLED",
        type="bool",
        default=True,  # promovida a default ON (operador 2026-07-15, barrido de flags 122-141 + revision general)
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
        requires="CLAUDE_CODE_CLI_AUTOCORRECT_ENABLED",
        min_value=0,  # Plan 83 — 0 = sin reintentos.
    ),
    FlagSpec(
        key="CLAUDE_CODE_CLI_HOOKS_ENABLED",
        type="bool",
        default=True,  # promovida a default ON (operador 2026-07-15, barrido de flags 122-141 + revision general)
        label="Hooks PostToolUse (claude)",
        description="F1.4 — settings.json efímero con hook de validación de artifacts.",
        group="claude_code_cli",
    ),
    FlagSpec(
        key="CLAUDE_CODE_CLI_PROJECT_KNOWLEDGE_ENABLED",
        type="bool",
        default=True,  # promovida a default ON (operador 2026-07-15, barrido de flags 122-141 + revision general)
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
        default=True,  # promovida a default ON (operador 2026-07-15, barrido de flags 122-141 + revision general)
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
        default=True,  # promovida a default ON (operador 2026-07-15, barrido de flags 122-141 + revision general)
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
        key="CLAUDE_CODE_CLI_TRUST_PREFLIGHT_ENABLED",
        type="bool",
        default=True,  # Plan 144 F2 — kill-switch default ON (detecta+falla temprano; no reduce seguridad).
        label="Preflight de confianza de workspace (claude)",
        description="Antes de lanzar claude, verifica hasTrustDialogAccepted del workspace; si no, falla temprano con remedio en vez de code 1 mudo.",
        group="claude_code_cli",
    ),
    FlagSpec(
        key="CLAUDE_CODE_CLI_TRUST_AUTOSET_ENABLED",
        type="bool",
        # SIN default= → default_is_known False → NO va en _CURATED_DEFAULTS_ON (default OFF via config.py).
        label="Auto-confiar workspace (claude)",
        description="OPT-IN. Si el workspace no está confiado, escribe hasTrustDialogAccepted=true en ~/.claude.json (setting de seguridad). OFF por defecto.",
        group="claude_code_cli",
        requires="CLAUDE_CODE_CLI_TRUST_PREFLIGHT_ENABLED",
    ),
    FlagSpec(
        key="STACKY_CONTEXT_BUDGET_ENABLED",
        type="bool",
        label="Presupuesto de contexto",
        description="F2.4 — Ranking + truncado de bloques de contexto.",
        group="global",
        pair="STACKY_CONTEXT_BUDGET_PROJECTS",
        default=True,  # Grupo A — determinista, ahorra tokens (topa el contexto).
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
        requires="STACKY_CONTEXT_BUDGET_ENABLED",
        min_value=0,  # Plan 83 — context_enrichment.py: budget<=0 → no-op.
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
        default=True,  # Grupo A — determinista, ahorra tokens (dedup de contexto).
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
        default=True,  # promovida a default ON (operador 2026-07-15, barrido de flags 122-141 + revision general)
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
        min_value=0,  # Plan 83 — app.py: gate `if hours > 0`, 0 = daemon nunca arranca.
        restart_required=True,  # Plan 84 — consumido una vez en app.py:386-387.
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
        min_value=0,  # Plan 83 — chars negativos sin sentido; 0 cae al fallback agent_max_chars.
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
        default=True,  # promovida a default ON (operador 2026-07-15, barrido de flags 122-141 + revision general)
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
        default=True,  # promovida a default ON (operador 2026-07-15, barrido de flags 122-141 + revision general)
        label="Gate de contrato (codex)",
        description="H2.1 — Si ON, outputs con errores duros degradan el run a needs_review.",
        group="codex_cli",
    ),
    FlagSpec(
        key="CODEX_CLI_AUTOCORRECT_ENABLED",
        type="bool",
        default=True,  # promovida a default ON (operador 2026-07-15, barrido de flags 122-141 + revision general)
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
        requires="CODEX_CLI_AUTOCORRECT_ENABLED",
        min_value=0,  # Plan 83 — 0 = sin reintentos.
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
        default=True,  # Grupo B — paridad 3 runtimes; tokens marginales-moderados; no-op si no hay skills.
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
        default=True,  # promovida a default ON (operador 2026-07-15, barrido de flags 122-141 + revision general)
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
        min_value=0,  # Plan 83 — 0 = sin límite (desactivado, doc propia).
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
        min_value=0,  # Plan 83 — 0.0 = sin límite (desactivado, doc propia).
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
        # Plan 83 — DESVÍO de la tabla F1 (proponía min=1): run_slots.py:6,19,23,33
        # confirma 0 = ilimitado (retro-compat), NO "bloquea todo run". min=0.
        min_value=0,
    ),
    FlagSpec(
        key="STACKY_ADO_RUN_FOOTER_ENABLED",
        type="bool",
        default=True,  # promovida a default ON (operador 2026-07-15, barrido de flags 122-141 + revision general)
        label="Firma visible Stacky en ADO",
        description="U0.2 — Agrega footer con agente/runtime/modelo/run en comentarios y tasks.",
        group="global",
    ),
    FlagSpec(
        key="STACKY_WEBHOOKS_V2_ENABLED",
        type="bool",
        default=True,  # promovida a default ON (operador 2026-07-15, barrido de flags 122-141 + revision general)
        label="Webhooks v2 multi-runtime",
        description="U0.3 — Emite exec.completed/failed/needs_review para todos los runtimes.",
        group="global",
    ),
    FlagSpec(
        key="STACKY_DESKTOP_NOTIFY_ENABLED",
        type="bool",
        default=True,  # promovida a default ON (operador 2026-07-15, barrido de flags 122-141 + revision general)
        label="Notificación desktop global",
        description="U0.4 — Toast del SO al cerrar runs, incluso fuera del browser.",
        group="global",
    ),
    FlagSpec(
        key="STACKY_LIVE_TELEMETRY_ENABLED",
        type="bool",
        default=True,  # promovida a default ON (operador 2026-07-15, barrido de flags 122-141 + revision general)
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
        min_value=0, max_value=1,  # Plan 83 — score normalizado.
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
        min_value=0,  # Plan 83 — app.py: gate `if hours > 0`, 0 = daemon nunca arranca.
        restart_required=True,  # Plan 84 — consumido una vez en app.py:366-367.
    ),
    FlagSpec(
        key="STACKY_PIPELINES_ENABLED",
        type="bool",
        default=True,  # promovida a default ON (operador 2026-07-15, barrido de flags 122-141 + revision general)
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
        default=True,  # Grupo A — validación/reparación determinista anti-ordinal (causa raíz task-not-created).
    ),
    # ── Plan 149 F0 — Envelope de errores tipado (V6) ───────────────────────────
    FlagSpec(
        key="STACKY_TYPED_ERROR_ENVELOPE_ENABLED",
        type="bool",
        label="Envelope de errores tipado (API)",
        description=(
            "Plan 149 — Si ON, los errores no atrapados se devuelven como "
            "envelope tipado {error_type, message, request_id, exec_id} en vez "
            "de un 500 mudo. OFF = respuesta legacy byte-idéntica."
        ),
        group="global",
        env_only=True,
        default=True,
    ),
    # ── Plan 149 F4 — Superficie de cuarentena de intake en Desatascador ───────
    FlagSpec(
        key="STACKY_INTAKE_QUARANTINE_SURFACE_ENABLED",
        type="bool",
        label="Superficie de cuarentena de intake en Desatascador",
        description=(
            "Plan 149 — Si ON, el board Desatascador muestra pending-task.json "
            "rechazados por intake con su causa exacta (reason_code) y habilita "
            "el re-procesamiento 1-click. OFF = comportamiento legacy (json.loads "
            "plano)."
        ),
        group="global",
        env_only=True,
        default=True,
    ),
    # ── V1.2 — Smart dispatch v1 (advisor) ─────────────────────────────────────
    FlagSpec(
        key="STACKY_RUN_ADVISOR_ENABLED",
        type="bool",
        default=True,  # promovida a default ON (operador 2026-07-15, barrido de flags 122-141 + revision general)
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
        reserved=True,
        reserved_reason="Plan 22 V2.2 (smart dispatch enforce) declarada anticipadamente; el enforcement nunca se implementó.",
    ),
    FlagSpec(
        # Plan 83 F1 — descartado: sin consumidor real en código (grep fuera de
        # services/harness_flags.py, config.py y tests/ no encuentra lectura del
        # valor; la degradación de modelo/402 que describe la nota V2.2 no está
        # cableada). NO se declaran bounds (procedimiento F1 paso 4).
        key="STACKY_BUDGET_PER_TICKET_USD",
        type="float",
        label="Presupuesto por ticket (USD)",
        description=(
            "V2.2 — Tope de costo acumulado por ticket. 0.0 = sin límite. Al superar: "
            "degrada modelo un escalón; si aún excede → 402 (override force_budget)."
        ),
        group="global",
        env_only=True,
        reserved=True,
        reserved_reason="Plan 22 V2.2 (budget por ticket) declarada anticipadamente; el tope de costo nunca se implementó. Hoy NO limita nada.",
    ),
    # ── V2.3 — Evals programados + gate endurecible ────────────────────────────
    FlagSpec(
        key="STACKY_EVALS_INTERVAL_HOURS",
        type="int",
        label="Evals programados: intervalo (horas)",
        description="V2.3 — Corre 'evals run all' cada N horas en daemon. 0 = off.",
        group="global",
        env_only=True,
        min_value=0,  # Plan 83 — app.py: gate `if interval > 0`, 0 = daemon nunca arranca.
        restart_required=True,  # Plan 84 — consumido una vez en app.py:336-347.
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
        min_value=0,  # Plan 83 — 0 = off (doc propia).
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
        default=True,  # Grupo A — heurística sin LLM; habilita routing/effort adaptativos.
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
        default=True,  # Grupo B — tokens marginales y condicionales (solo si el output falla).
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
        default=True,  # Grupo B — net token-negativo (S→haiku); requiere COMPLEXITY_ESTIMATION.
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
        min_value=0,  # Plan 83 — 0 = sin caché (doc propia).
    ),
    # ── I2.3 — Expansión y normalización de query ─────────────────────────────
    FlagSpec(
        key="STACKY_RETRIEVAL_EXPANSION_ENABLED",
        type="bool",
        default=True,  # promovida a default ON (operador 2026-07-15, barrido de flags 122-141 + revision general)
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
        default=True,  # Grupo A — TF-IDF local, sin tokens; mejora qué contexto sobrevive al recorte.
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
        default=True,  # Grupo A — sin tokens; solo paraleliza injectors (orden byte-idéntico).
    ),
    # ── I0.3 — Pre-warming del caché ADO ──────────────────────────────────────
    FlagSpec(
        key="STACKY_ADO_PREWARM_ENABLED",
        default=True,  # promovida a default ON (operador 2026-07-10, curada en _CURATED_DEFAULTS_ON). Inerte hasta STACKY_ADO_READ_CACHE_TTL_SEC>0.
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
        default=True,  # promovida a default ON (operador 2026-07-10, curada en _CURATED_DEFAULTS_ON)
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
        default=True,  # Grupo A — higiene de logs; evita perder logs de runs que mueren (zombies).
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
        min_value=0,  # Plan 83 — orphan_reaper.py:192-193: `if interval_sec <= 0: return`.
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
        min_value=0,  # Plan 83 — 0 = desactivado (doc propia; codex_cli_runner.py confirma).
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
        default=True,  # Grupo A — determinista; evita publicaciones duplicadas en ADO.
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
        default=True,  # Grupo A — KPIs read-only; degrada con gracia si la fuente está ausente.
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
        default=True,  # Grupo B — tokens marginales (bloque de contexto); mejora aprobado-a-la-primera.
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
        default=True,  # Grupo B — moderado en L/XL (más razonamiento), ahorra en S.
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
        default=True,  # promovida a default ON (operador 2026-07-15, barrido de flags 122-141 + revision general)
        label="Pase correctivo de criterios incumplidos",
        description=(
            "Q1.1 — Si self-review detecta criterios incumplidos, envía un único "
            "mensaje correctivo antes de finalize_run (solo runtimes con resume). "
            "Presupuesto compartido con autocorrect. OFF = sin pase correctivo."
        ),
        group="global",
    ),
    FlagSpec(
        # Plan 83 F1 — descartado: sin consumidor real. claude_code_cli_runner.py:900-920
        # gatea el pase correctivo solo por STACKY_CRITERIA_REPAIR_ENABLED y lo corre
        # una única vez (`_criteria_repair_done[0]`); el retries_budget que de hecho
        # se pasa es CLAUDE_CODE_CLI_AUTOCORRECT_MAX_RETRIES, NO esta key. NO se
        # declaran bounds (procedimiento F1 paso 4).
        key="STACKY_CRITERIA_REPAIR_MAX_RETRIES",
        type="int",
        label="Max reintentos pase correctivo",
        description="Q1.1 — Máximo de pases correctivos por run (default 1).",
        group="global",
    ),
    FlagSpec(
        key="STACKY_CLI_FEWSHOT_ENABLED",
        type="bool",
        default=True,  # promovida a default ON (operador 2026-07-15, barrido de flags 122-141 + revision general)
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
        requires="STACKY_CLI_FEWSHOT_ENABLED",
        # Plan 83 — DESVÍO de la tabla F1 (proponía min=1): context_enrichment.py:1458
        # pasa k crudo a few_shot.pick_examples, que hace `scored[:k*3]`; k=0 da lista
        # vacía (benigno, "sin ejemplos"), pero k negativo produce slicing con índice
        # negativo (comportamiento silenciosamente incorrecto). min=0, no min=1.
        min_value=0,
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
        default=True,  # Grupo A — KPIs read-only; degrada con gracia.
    ),
    # ── Plan 30 — Integridad verificada contra la realidad ────────────────────
    FlagSpec(
        key="STACKY_RUN_PREFLIGHT_GATE_ENABLED",
        type="bool",
        default=True,  # promovida a default ON (operador 2026-07-15, barrido de flags 122-141 + revision general)
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
        default=True,  # promovida a default ON (operador 2026-07-15, barrido de flags 122-141 + revision general)
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
        default=True,  # promovida a default ON (operador 2026-07-15, barrido de flags 122-141 + revision general)
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
        default=True,  # promovida a default ON (operador 2026-07-15, barrido de flags 122-141 + revision general)
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
        default=True,  # Grupo A — KPIs read-only; degrada con gracia.
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
        # Plan 83 F1 — descartado: sin consumidor real. La propia label/description
        # lo marca "DIFERIDO" (G2.2 nunca se cableó, ver comentario del spec anterior
        # STACKY_TRANSIENT_RUN_RETRY_ENABLED). NO se declaran bounds (procedimiento
        # F1 paso 4).
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
        default=True,  # Grupo B — modo 'annotate' por default (nunca 'gate'); sin tokens LLM, gasta CPU. EXEC_REPAIR queda OFF.
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
        requires="STACKY_EXEC_VERIFICATION_ENABLED",
    ),
    FlagSpec(
        key="STACKY_EXEC_VERIFICATION_TIMEOUT_S",
        type="int",
        label="Timeout por verificador (segundos)",
        description="E0.1 — Timeout máximo por verificador individual (default 120s).",
        group="global",
        requires="STACKY_EXEC_VERIFICATION_ENABLED",
        min_value=1,  # Plan 83 — exec_verification.py:538 NO clampa; 0/negativo rompe el timeout.
    ),
    FlagSpec(
        key="STACKY_EXEC_VERIFICATION_BUDGET_S",
        type="int",
        label="Budget global de verificación (segundos)",
        description="E0.1 — Budget total para todos los verificadores del run (default 300s).",
        group="global",
        requires="STACKY_EXEC_VERIFICATION_ENABLED",
        min_value=1,  # Plan 83 — exec_verification.py:539 NO clampa; idem timeout.
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
        default=True,  # promovida a default ON (operador 2026-07-15, barrido de flags 122-141 + revision general)
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
        requires="STACKY_EXEC_REPAIR_ENABLED",
        min_value=0,  # Plan 83 — harness/exec_repair.py:120 `hard_failed[:max_retries]`, 0 = sin pase.
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
        default=True,  # Grupo B — soft-warn (HARD queda OFF); determinista, no bloquea.
    ),
    FlagSpec(
        key="STACKY_FAKE_GREEN_GUARD_HARD",
        type="bool",
        default=True,  # promovida a default ON (operador 2026-07-15, barrido de flags 122-141 + revision general)
        label="Guard anti-verde-falso: hard fail",
        description=(
            "E1.2 — Si ON, verde-falso detectado es HARD (gateable); por defecto es soft-warn."
        ),
        group="global",
    ),
    FlagSpec(
        key="STACKY_EXEC_VERIFICATION_VERDICT_CARD_ENABLED",
        type="bool",
        default=True,  # promovida a default ON (operador 2026-07-15, barrido de flags 122-141 + revision general)
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
        default=True,  # Grupo A — KPIs read-only; degrada con gracia.
    ),
    # ── Plan 32 — Contrato de Aceptación Ejecutable ───────────────────────────
    FlagSpec(
        key="STACKY_ACCEPTANCE_CONTRACT_ENABLED",
        type="bool",
        default=True,  # promovida a default ON (operador 2026-07-15, barrido de flags 122-141 + revision general)
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
        requires="STACKY_ACCEPTANCE_CONTRACT_ENABLED",
    ),
    FlagSpec(
        key="STACKY_ACCEPTANCE_CONTRACT_MAX_CHECKS",
        type="int",
        label="Contrato: máx chequeos por run",
        description="A0.1 — Cap de chequeos ejecutables derivados por complejidad (default 4).",
        group="global",
        requires="STACKY_ACCEPTANCE_CONTRACT_ENABLED",
        min_value=1,  # Plan 83 — acceptance_contract.py:342 `min(cap_complejidad, global_max)`; 0 checks sin sentido para un gate de integridad.
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
        default=True,  # promovida a default ON (operador 2026-07-15, barrido de flags 122-141 + revision general)
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
        default=True,  # promovida a default ON (operador 2026-07-15, barrido de flags 122-141 + revision general)
        label="Pase correctivo del contrato (A1.1)",
        description=(
            "A1.1 — Único pase correctivo dirigido al chequeo en rojo. Solo runtimes "
            "con resume. Re-ejecuta el contrato una vez. OFF = needs_review directo."
        ),
        group="global",
    ),
    FlagSpec(
        # Plan 83 F1 — descartado: sin consumidor real (grep fuera de
        # services/harness_flags.py, config.py y tests/ solo encuentra un docstring
        # en services/acceptance_gate.py:17; el valor nunca se lee en el código).
        # NO se declaran bounds (procedimiento F1 paso 4).
        key="STACKY_ACCEPTANCE_REPAIR_MAX_RETRIES",
        type="int",
        label="Contrato: max reintentos pase correctivo",
        description="A1.1 — Presupuesto compartido con autocorrect/run_repair/Q1.1/E1.1 (default 1).",
        group="global",
    ),
    FlagSpec(
        key="STACKY_ACCEPTANCE_INTEGRITY_ENABLED",
        type="bool",
        default=True,  # promovida a default ON (operador 2026-07-15, barrido de flags 122-141 + revision general)
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
        default=True,  # promovida a default ON (operador 2026-07-15, barrido de flags 122-141 + revision general)
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
        default=True,  # Grupo A — KPIs read-only; degrada con gracia.
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
        default=True,  # promovida a default ON (operador 2026-07-15, config se hace despues desde la UI)
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
        default=True,  # Grupo B — tokens marginales; no aporta si el proyecto no tiene db_readonly configurado.
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
        default=True,  # Grupo A — endpoint de lectura; observabilidad sin costo de tokens.
    ),
    # ── Plan 142 — Centro de Costos + Codeburn ─────────────────────────────────
    FlagSpec(
        key="STACKY_COST_CENTER_ENABLED",
        type="bool",
        default=True,  # C1 — default ON (read-only; no aplica ninguna de las 4 excepciones duras)
        label="Centro de Costos (KPIs + Codeburn)",
        description=(
            "Plan 142 — Vista read-only de costos USD/tokens multidimensionales y "
            "burn temporal. Default ON; desactivable desde la UI."
        ),
        group="observabilidad",
    ),
    FlagSpec(
        key="STACKY_COST_CODEBURN_IMPORT_ENABLED",
        type="bool",
        label="Centro de Costos: reconciliación con export externo (ccusage/codeburn)",
        description=(
            "Plan 142 F7 — Si ON, lee un JSONL externo opcional (ruta en "
            "STACKY_COST_CODEBURN_IMPORT_PATH) y agrega 'external_reconciliation' a "
            "/cost-summary. Sin shell-out, sin dependencia nueva. OFF por default: "
            "excepción dura #3 — el archivo/ruta NO está garantizado en una instalación "
            "default y sólo aplica si el operador YA usa esa herramienta externa."
        ),
        group="observabilidad",
        pair="STACKY_COST_CODEBURN_IMPORT_PATH",
    ),
    FlagSpec(
        key="STACKY_COST_CODEBURN_IMPORT_PATH",
        type="str",
        label="Centro de Costos: ruta del JSONL externo",
        description="Plan 142 F7 — Ruta absoluta al export JSONL. Vacío = desactivado.",
        group="observabilidad",
        requires="STACKY_COST_CODEBURN_IMPORT_ENABLED",
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
        # Plan 83 — DESVÍO de la tabla F1 (proponía min=1): api/tickets.py:2825-2829
        # ya clampa `cap = max(0, cap_raw)` y solo aplica el recorte `if cap > 0`;
        # con cap=0 el bloque de recorte se salta ENTERO (0 = sin cota, doc propia),
        # NO "vacía el panel" como asumía la tabla. min=0, no min=1.
        min_value=0,
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
        reserved=True,
        reserved_reason="Superseded por Plan 43: el selector model/effort de run-brief quedó siempre activo, sin gate. Esta flag nunca se cableó.",
    ),
    FlagSpec(
        key="STACKY_INJECT_PROCESS_CATALOG",
        type="bool",
        default=True,  # promovida a default ON (operador 2026-07-15, barrido de flags 122-141 + revision general)
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
        default=True,  # promovida a default ON (operador 2026-07-15, barrido de flags 122-141 + revision general)
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
        key="STACKY_DOCS_GRAPH_ENABLED",
        default=True,  # promovida a default ON (operador 2026-07-10, curada en _CURATED_DEFAULTS_ON)
        type="bool",
        label="Grafo documental (Plan 109)",
        description=(
            "Plan 109 — Construye un grafo READ-ONLY de la documentación del "
            "proyecto (links markdown, wikilinks [[nombre]] y referencias a "
            "código) y lo expone en GET /api/docs/graph junto a un diagnóstico "
            "de salud documental. Habilita la pestaña 'Cobertura' (y en Plan "
            "111 la pestaña 'Grafo') de la página Docs. No escribe ni modifica "
            "ningún documento. Default OFF."
        ),
        group="global",
        env_only=False,
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
        requires="STACKY_RAG_CATALOG_ENABLED",
        min_value=1,  # Plan 83 — consumidor ya clampa max(1,..) (context_enrichment.py:800); redundante pero informativo.
    ),
    FlagSpec(
        key="STACKY_DOCS_RAG_HYBRID_ENABLED",
        default=True,  # promovida a default ON (operador 2026-07-10, curada en _CURATED_DEFAULTS_ON)
        type="bool",
        label="Retrieval híbrido docs (Plan 112)",
        description=(
            "Plan 112 — Si ON, la búsqueda de docs deja de ser solo por término: "
            "expande 1 salto por los links del grafo documental (plan 109) para "
            "traer notas vecinas enlazadas y prioriza las notas muy referenciadas "
            "(hubs). Mejora el recall cuando la respuesta vive en una nota linkeada "
            "que no contiene la palabra buscada. Default OFF = búsqueda byte-idéntica "
            "a hoy. Si el grafo 109 no está disponible, degrada a búsqueda léxica pura."
        ),
        group="global",
        env_only=False,
    ),
    FlagSpec(
        key="STACKY_DOCS_RAG_HYBRID_ALPHA",
        type="float",
        label="Retrieval híbrido: peso del match de término",
        description=(
            "Plan 112 — Peso del puntaje léxico (coincidencia de término) al ordenar "
            "resultados del retrieval híbrido. Default 1.0. Solo aplica con "
            "STACKY_DOCS_RAG_HYBRID_ENABLED=true."
        ),
        group="global",
        env_only=False,
        requires="STACKY_DOCS_RAG_HYBRID_ENABLED",
        min_value=0.0,
        max_value=10.0,
    ),
    FlagSpec(
        key="STACKY_DOCS_RAG_HYBRID_BETA",
        type="float",
        label="Retrieval híbrido: peso de notas referenciadas",
        description=(
            "Plan 112 — Peso del prior de backlinks: cuánto sube una nota por ser muy "
            "referenciada por otras (hub). Default 0.15. Solo aplica con "
            "STACKY_DOCS_RAG_HYBRID_ENABLED=true."
        ),
        group="global",
        env_only=False,
        requires="STACKY_DOCS_RAG_HYBRID_ENABLED",
        min_value=0.0,
        max_value=10.0,
    ),
    FlagSpec(
        key="STACKY_DOCS_RAG_HYBRID_MAX_NEIGHBORS",
        type="int",
        label="Retrieval híbrido: tope de notas vecinas por hit",
        description=(
            "Plan 112 — Máximo de notas vecinas (a 1 link) que se traen por cada "
            "resultado léxico durante la expansión. Default 8. Solo aplica con "
            "STACKY_DOCS_RAG_HYBRID_ENABLED=true."
        ),
        group="global",
        env_only=False,
        requires="STACKY_DOCS_RAG_HYBRID_ENABLED",
        min_value=0,
        max_value=100,
    ),
    FlagSpec(
        key="STACKY_DOCS_DOCUMENTER_ENABLED",
        default=True,  # promovida a default ON (operador 2026-07-10, curada en _CURATED_DEFAULTS_ON)
        type="bool",
        label="Documentador 1-click (Plan 113)",
        description=(
            "Plan 113 — Si ON, agrega en la página Docs un botón 'Lanzar Documentador' "
            "que con un click detecta el estado de la documentación (sin docs / mal "
            "formato / incompleta / sana), decide qué trabajo hace falta y deja la doc "
            "creada/corregida en formato Obsidian en una rama git dedicada y revertible "
            "(nunca en la rama de trabajo, nunca push). El operador la revisa como diff y "
            "la conserva o descarta. No toca docs/sistema/. Default OFF."
        ),
        group="global",
        env_only=False,
    ),
    FlagSpec(
        key="STACKY_DOCS_DOCUMENTER_MAX_FILES",
        type="int",
        label="Documentador: tope de archivos por run",
        description=(
            "Plan 113 — Máximo de archivos de documentación que el Documentador puede "
            "escribir en un solo run (límite de seguridad). Default 40. Solo aplica con "
            "STACKY_DOCS_DOCUMENTER_ENABLED=true."
        ),
        group="global",
        env_only=False,
        requires="STACKY_DOCS_DOCUMENTER_ENABLED",
        min_value=1,
        max_value=500,
    ),
    FlagSpec(
        key="STACKY_DOCS_DOCUMENTER_V2_ENABLED",
        default=True,  # promovida a default ON (directiva operador 2026-07-15: ninguna
        # de las 4 excepciones duras aplica — sin autopublish, no destructivo, sin
        # prerequisito externo no garantizado, no reduce seguridad)
        type="bool",
        label="Documentador v2: evidencia, citas e historial (Plan 137)",
        description=(
            "Plan 137 — Activa evidencia real de código (árbol + símbolos con línea) en "
            "el contexto del Documentador, verificación determinista de citas [V] contra "
            "el filesystem, short-circuit de modos sin targets (ahorra invocaciones LLM), "
            "historial persistente de corridas (sobrevive a un restart) y preview por "
            "archivo en el panel de revisión. Requiere STACKY_DOCS_DOCUMENTER_ENABLED=true."
        ),
        group="global",
        env_only=False,
        requires="STACKY_DOCS_DOCUMENTER_ENABLED",
    ),
    FlagSpec(
        key="STACKY_DOCS_DOCUMENTER_EVIDENCE_MAX_CHARS",
        type="int",
        label="Documentador v2: tope de caracteres de evidencia",
        description=(
            "Plan 137 — Máximo de caracteres de evidencia de código (árbol + símbolos) "
            "que se agregan al contexto del Documentador por módulo. Default 12000. Solo "
            "aplica con STACKY_DOCS_DOCUMENTER_V2_ENABLED=true."
        ),
        group="global",
        env_only=False,
        requires="STACKY_DOCS_DOCUMENTER_ENABLED",
        min_value=1000,
        max_value=100000,
    ),
    FlagSpec(
        key="STACKY_DOCS_STALENESS_ENABLED",
        default=True,  # promovida a default ON (operador 2026-07-10, curada en _CURATED_DEFAULTS_ON)
        type="bool",
        label="Doctor de staleness doc↔código (Plan 114)",
        description=(
            "Plan 114 — Si ON, el grafo documental (Plan 109) marca como 'stale' las "
            "referencias nota→código cuyo archivo de código cambió en git DESPUÉS de la "
            "última edición de la nota, y muestra un chip de advertencia en la nota con "
            "un botón 'Proponer actualización' que encola el Documentador (Plan 113) en "
            "modo ACTUALIZAR acotado a esa sola nota. Señal 100% git, sin LLM en la "
            "detección; degrada a 'sin staleness' si no hay git. Default OFF."
        ),
        group="global",
        env_only=False,
        requires="STACKY_DOCS_GRAPH_ENABLED",
    ),
    FlagSpec(
        key="STACKY_PROCESS_DISCIPLINE_ENABLED",
        type="bool",
        default=True,  # promovida a default ON (operador 2026-07-15, barrido de flags 122-141 + revision general)
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
        default=True,  # promovida a default ON (operador 2026-07-15, barrido de flags 122-141 + revision general)
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
        default=True,  # promovida a default ON (operador 2026-07-15, barrido de flags 122-141 + revision general)
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
        default=True,  # promovida a default ON (operador 2026-07-15, barrido de flags 122-141 + revision general)
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
        default=True,  # promovida a default ON (operador 2026-07-15, barrido de flags 122-141 + revision general)
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
        default=True,  # promovida a default ON (operador 2026-07-15, config se hace despues desde la UI)
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
        default=True,  # promovida a default ON (operador 2026-07-15, config se hace despues desde la UI)
        label="Pre-vuelo: auto-aprobar si está claro",
        description=(
            "Plan 41 — Si ON, salta el modal cuando no hay preguntas abiertas y la "
            "confianza supera el umbral."
        ),
        group="preflight",
        requires="INTENT_PREFLIGHT_ENABLED",
    ),
    FlagSpec(
        key="INTENT_PREFLIGHT_AUTO_APPROVE_MIN_CONF",
        type="float",
        label="Pre-vuelo: confianza mínima para auto-aprobar",
        description="Plan 41 — Umbral de confianza para auto-aprobar sin modal (default 0.8).",
        group="preflight",
        requires="INTENT_PREFLIGHT_ENABLED",
        min_value=0, max_value=1,  # Plan 83 — confidence normalizada.
    ),
    FlagSpec(
        key="STACKY_ARTIFACT_RESCUE_ENABLED",
        type="bool",
        default=True,  # promovida a default ON (operador 2026-07-15, barrido de flags 122-141 + revision general)
        label="Rescate de épica desde disco",
        description=(
            "Plan 47 — Si ON, cuando el agente narra en vez de devolver el HTML "
            "de la épica, el backend rescata el artefacto que el agente ya escribió "
            "en Agentes/outputs y lo publica. Default OFF."
        ),
        group="global",
        env_only=True,  # se lee con os.getenv en autopublish_epic_from_run
    ),
    # ── Plan 148 — Degradación explícita de integraciones no configuradas ────
    FlagSpec(
        key="STACKY_INTEGRATION_DEGRADATION_ENABLED",
        type="bool",
        default=True,  # kill-switch, default ON (curada en _CURATED_DEFAULTS_ON)
        label="Degradación explícita de integraciones no configuradas",
        description=(
            "Circuit-breaker + backoff para ADO/Jira/LLM local cuando no están "
            "configurados o caídos: deja de reintentar cada ciclo, muestra el estado "
            "en la UI y responde 200 available/linked:false en vez de 502. OFF = "
            "comportamiento previo (reintenta siempre, 502 crudos)."
        ),
        group="global",
        env_only=False,
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
        default=True,  # Grupo B — paridad 3 runtimes; tokens marginales; solo actúa si hay rechazos guardados.
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
        default=True,  # promovida a default ON (operador 2026-07-15, config se hace despues desde la UI)
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
    # ── Plan 77 — Issue como épica de un ticket: fases como comentarios ────────
    FlagSpec(
        key="STACKY_ISSUE_PHASE_COMMENTS_ENABLED",
        type="bool",
        label="Comentarios de fase del Issue (funcional/técnico/implementación)",
        description=(
            "Plan 77 — Postea el análisis funcional/técnico/implementación de un "
            "Issue como comentarios idempotentes en el mismo work item (no crea hijos). "
            "Los 3 runtimes participan (paridad real). Default OFF."
        ),
        group="global",
        # env_only no seteado (default False) → atributo de Config, editable en UI
    ),
    FlagSpec(
        key="STACKY_EPIC_GATE_ENABLED",
        type="bool",
        default=True,  # promovida a default ON (operador 2026-07-15, tras arreglar la causa raíz)
        label="Gate correctivo determinista de épica",
        description=(
            "Plan 51 F3 — Si ON, ante defectos no reparables (huecos RF, bloques "
            "vacíos) bloquea el autopublish de la épica (needs_review) y dispara "
            "un pase correctivo inline ante defectos de forma reparables. "
            "Caso feliz = 0 tokens extra. Default ON (2026-07-15): la causa raíz real "
            "del intento de promoción anterior era el fixture _VALID_EPIC de "
            "test_autopublish_rescue.py con un RF sin cuerpo (rf_empty_body "
            "correctamente detectado); corregido con contenido real, no el gate."
        ),
        group="global",
        env_only=True,  # se lee con os.getenv en api/tickets y el runner CLI
    ),
    FlagSpec(
        key="STACKY_EPIC_CATALOG_GATE_ENABLED",
        type="bool",
        default=True,  # promovida a default ON (operador 2026-07-15, config se hace despues desde la UI)
        label="Bloqueo por catálogo (procesos inventados)",
        description=(
            "Plan 51 F3 — Si ON (requiere STACKY_EPIC_GATE_ENABLED), un proceso "
            "citado que no exista en el process_catalog del cliente bloquea el "
            "autopublish. Opt-in dentro de opt-in. Default OFF."
        ),
        group="global",
        env_only=True,  # se lee con os.getenv en api/tickets
        requires="STACKY_EPIC_GATE_ENABLED",
    ),
    # ── Plan 61 — Gate determinista del flujo funcional (Task) ──────────────────
    FlagSpec(
        key="STACKY_TASK_GATE_ENABLED",
        type="bool",
        default=True,  # promovida a default ON (operador 2026-07-15, barrido de flags 122-141 + revision general)
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
        default=True,  # promovida a default ON (operador 2026-07-15, barrido de flags 122-141 + revision general)
        label="Bloqueo del flujo funcional (Task)",
        description=(
            "Plan 61 — Requiere STACKY_TASK_GATE_ENABLED. Si ON, un defecto de "
            "severidad needs_review impide la creación en ADO (devuelve 400 "
            "TASK_GATE_BLOCKED). Default OFF."
        ),
        group="global",
        env_only=True,
        requires="STACKY_TASK_GATE_ENABLED",
    ),
    # ── Plan 79 — Estados de tarea deterministas y configurables ─────────────
    FlagSpec(
        key="STACKY_DETERMINISTIC_TASK_STATES_ENABLED",
        type="bool",
        default=True,  # promovida a default ON (operador 2026-07-15, config se hace despues desde la UI)
        label="Estados de tarea deterministas",
        description=(
            "Plan 79 — Stacky aplica el estado-en-progreso (al iniciar) y el "
            "estado-final (al completar) desde la config del proyecto "
            "(tracker_state_machine por agente), ignorando el estado que "
            "proponga el agente. Default OFF."
        ),
        group="global",
        env_only=False,
    ),
    # ── Plan 53 — Selector adaptativo de modelo/effort por confidence ──────────
    FlagSpec(
        key="STACKY_ADAPTIVE_SELECTOR_ENABLED",
        type="bool",
        default=True,  # promovida a default ON (operador 2026-07-15, barrido de flags 122-141 + revision general)
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
        default=True,  # promovida a default ON (operador 2026-07-10, curada en _CURATED_DEFAULTS_ON). env_only: default efectivo también en el read-site tickets.py.
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
        reserved=True,
        reserved_reason="Plan 57 v1 solo opera modo eager; la lectura del modo quedó diferida a v1.1 (F2a post-GA).",
    ),
    # ── Plan 59 — Descomposición vertical épica→hijos ────────────────────────
    FlagSpec(
        key="STACKY_EPIC_DECOMPOSITION_ENABLED",
        default=True,  # promovida a default ON (operador 2026-07-10, curada en _CURATED_DEFAULTS_ON). env_only: default efectivo también en el read-site tickets.py.
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
        default=True,  # promovida a default ON (operador 2026-07-15, barrido de flags 122-141 + revision general)
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
        requires="STACKY_QUALITY_CONVERGENCE_ENABLED",
        min_value=1,  # Plan 83 — consumidor ya clampa max(1,..) (claude_code_cli_runner.py:983); doc propia ">=1".
    ),
    # ── Plan 60 — Aprendizaje bidireccional: ediciones humanas en ADO ─────────
    FlagSpec(
        key="STACKY_ADO_EDIT_LEARNING_ENABLED",
        type="bool",
        default=True,  # promovida a default ON (operador 2026-07-15, barrido de flags 122-141 + revision general)
        label="Aprender de ediciones en ADO (plan 60)",
        description=(
            "Plan 60 — Si ON, Stacky lee de vuelta las correcciones humanas del WI publicado "
            "y las materializa como lección en el corpus (plan 54). Pasivo, default OFF."
        ),
        group="global",
        env_only=True,
        restart_required=True,  # Plan 84 — consumido una vez en app.py:410-413.
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
        requires="STACKY_ADO_EDIT_LEARNING_ENABLED",
        # Plan 83 — DESVÍO de la tabla F1 (proponía min=0 "0 = sin barrido"): app.py:414-424
        # NO tiene gate `if hours > 0` (a diferencia de digest/memory-review/evals); una
        # vez STACKY_ADO_EDIT_LEARNING_ENABLED=true, hours=0 produce `time.sleep(0)` en
        # un bucle infinito — busy-loop real, no "sin barrido". min=1.
        min_value=1,
        restart_required=True,  # Plan 84 — consumido una vez en app.py:414.
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
    # ── Plan 81 — Golden negativo desde ediciones humanas en ADO ──────────────
    FlagSpec(
        key="STACKY_NEGATIVE_GOLDEN_FROM_EDITS_ENABLED",
        type="bool",
        label="Golden negativo desde ediciones ADO (plan 81)",
        description=(
            "Plan 81 — Si ON, lo que el operador BORRA al editar un WI publicado se convierte en "
            "golden NEGATIVO determinista: el gate de regresión (plan 56) marca su reaparición en "
            "épicas futuras (y bloquea si STACKY_REGRESSION_GATE_BLOCKING=true). Productor: requiere "
            "STACKY_ADO_EDIT_LEARNING_ENABLED=true. Default ON (activado 2026-07-05, decisión "
            "explícita del operador)."
        ),
        group="global",
        env_only=False,
        default=True,
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
            "OFF (default): byte-idéntico al comportamiento pre-Plan-70. "
            "BLOQUEADA 2026-07-15 (diagnóstico exacto, no una excusa genérica): "
            "AdoTrackerProvider (services/ado_provider.py) construye su cliente ADO "
            "llamando build_ado_client() DIRECTO (services/project_context.py), NO "
            "vía api.tickets._ado_client_for_ticket — decisión de diseño explícita "
            "del propio módulo ('no reemplaza esos seams') para evitar import "
            "circular. 27 tests en 8 archivos mockean _ado_client_for_ticket (el "
            "seam pre-Plan-70) y dejan de interceptar la llamada real en cuanto el "
            "flag rutea por el provider — no es que falte el fallback a None (ese sí "
            "funciona para GitLab mal configurado), es que ambos caminos construyen "
            "clientes ADO reales pero por seams DISTINTOS. Arreglo correcto = migrar "
            "esos 27 mocks a build_ado_client(); alcance verificado pero fuera de "
            "esta pasada (ver [[barrido-flags-default-on-2026-07-15]])."
        ),
        group="global",
        env_only=False,  # editable por UI (regla dura operator-config-always-via-ui)
    ),
    FlagSpec(
        key="STACKY_PIPELINE_PROVIDER_ENABLED",
        type="bool",
        default=True,  # promovida a default ON (operador 2026-07-15, verificado sin el bug de TICKETS_PROVIDER)
        label="CIProvider sub-puerto (Plan 71)",
        description=(
            "Plan 71 — Si ON, los endpoints ado-pipeline-status y ado-pipeline-batch "
            "enrutan por el sub-puerto CIProvider (AdoCIProvider / GitLabCIProvider) "
            "en vez de llamar directamente a infer_pipeline. Habilita inferencia CI "
            "agnóstica del tracker (ADO + GitLab). Default ON (2026-07-15): a diferencia "
            "de STACKY_TICKETS_PROVIDER_ENABLED, AdoCIProvider delega a infer_pipeline "
            "existente (no construye su propio cliente ADO), así que no comparte el "
            "bug de seam de testeo; 60/61 tests Plan 71/72 verdes con el flag forzado."
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
            "PAT GitLab debe tener scope api. Default ON (activado 2026-07-05, decisión "
            "explícita del operador). "
            "OFF: guard 404 per-request; el blueprint siempre está registrado."
        ),
        group="global",
        env_only=False,  # editable por UI (regla dura operator-config-always-via-ui)
        default=True,
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
            "Default ON (activado 2026-07-05, decisión explícita del operador). "
            "OFF: guard 404 per-request; el blueprint siempre está registrado."
        ),
        group="global",
        env_only=False,  # editable por UI (regla dura operator-config-always-via-ui, C9)
        default=True,
    ),
    # ── Plan 87 — Panel DevOps ─────────────────────────────────────────────────
    FlagSpec(
        key="STACKY_DEVOPS_PANEL_ENABLED",
        type="bool",
        label="Panel DevOps (Plan 87)",
        description=(
            "Plan 87 — Muestra la seccion DevOps en la UI (creador grafico de "
            "pipelines). Expone GET /api/devops/health y POST /api/devops/parse-yaml. "
            "Default ON (activado 2026-07-05, decisión explícita del operador). "
            "Con OFF la tab no aparece y parse-yaml retorna 404."
        ),
        group="global",  # mismo group que STACKY_MIGRATOR_ADO_TO_GITLAB_ENABLED (harness_flags.py:1936)
        env_only=False,  # editable por UI (categoría 'devops')
        default=True,
        # SIN requires (supervisión 2026-07-05): la arista PANEL→GENERATOR violaba la
        # regla R4 del Plan 82 (profundidad máx 1, validate_requires_graph) al combinarse
        # con las hijas de la serie §3.12 (88/89/90/91 declaran requires=PANEL), y era
        # semánticamente incorrecta: el panel NO requiere el generator — degrada con
        # FlagGateBanner (87 v3 C14) y sus secciones agente/servidores/ambientes no lo usan.
    ),
    # ── Plan 88 — Publicaciones parametrizables de procesos (seccion DevOps) ────
    FlagSpec(
        key="STACKY_DEVOPS_PUBLICATIONS_ENABLED",
        type="bool",
        label="Publicaciones DevOps (Plan 88)",
        description=(
            "Plan 88 — Seccion Publicaciones del panel DevOps: materializa presets "
            "de procesos del catalogo como pipelines (preview/commit plan 73, "
            "trigger plan 72). Default ON (activado 2026-07-05, decisión explícita "
            "del operador). Con OFF el endpoint materialize da 404 y la seccion no aparece."
        ),
        group="global",  # mismo group que STACKY_DEVOPS_PANEL_ENABLED (87 v2 F0)
        env_only=False,  # editable por UI (categoría 'devops')
        requires="STACKY_DEVOPS_PANEL_ENABLED",  # Plan 82 — declarativo, informa en UI
        default=True,
    ),
    # ── Plan 89 — Inicialización de ambientes (seccion DevOps) ──────────────────
    FlagSpec(
        key="STACKY_DEVOPS_ENVIRONMENTS_ENABLED",
        type="bool",
        label="Ambientes DevOps (Plan 89)",
        description=(
            "Plan 89 — Seccion Ambientes del panel DevOps: crea el arbol de "
            "carpetas del ambiente derivado del catalogo (plan-then-apply con "
            "confirmacion, NUNCA borra ni sobrescribe) y lanza la publicacion "
            "inicial reusando el plan 88. Default ON (activado 2026-07-05, decisión "
            "explícita del operador). Con OFF los endpoints "
            "/api/devops/environments/* dan 404 y la seccion no aparece."
        ),
        group="global",  # mismo group que STACKY_DEVOPS_PANEL_ENABLED (87 v2 F0)
        env_only=False,  # editable por UI (categoría 'devops')
        requires="STACKY_DEVOPS_PANEL_ENABLED",  # Plan 82 — declarativo, informa en UI
        default=True,
    ),
    # ── Plan 90 — Agente DevOps interactivo multi-turno (seccion DevOps) ────────
    FlagSpec(
        key="STACKY_DEVOPS_AGENT_ENABLED",
        type="bool",
        label="Agente DevOps interactivo (Plan 90)",
        description=(
            "Plan 90 — Habilita el agente DevOps conversacional del panel DevOps: "
            "conversaciones multi-turno sobre runtimes CLI (claude/codex) con "
            "confirmacion explicita para acciones mutantes. Expone "
            "/api/devops/agent/conversations. Default ON (activado 2026-07-05, decisión "
            "explícita del operador, con conocimiento de que cada turno consume una "
            "llamada LLM completa). Con OFF los endpoints devuelven 404 y la seccion "
            "muestra aviso."
        ),
        group="global",  # mismo group que STACKY_DEVOPS_PANEL_ENABLED (87 F0)
        env_only=False,  # editable por UI (categoría 'devops')
        requires="STACKY_DEVOPS_PANEL_ENABLED",  # sin panel no hay seccion donde usarlo
        default=True,
    ),
    # ── Plan 91 — Registro de servidores DevOps ────────────────────────────────
    FlagSpec(
        key="STACKY_DEVOPS_SERVERS_ENABLED",
        type="bool",
        label="Servidores DevOps (Plan 91)",
        description=(
            "Plan 91 — Registro de servidores con alias (host+usuario+dominio; "
            "password en Windows Credential Manager, nunca en disco). Habilita "
            "/api/devops/servers (CRUD, test de conectividad, conexion RDP 1-click) "
            "y la seccion Servidores del panel DevOps. Default ON (activado 2026-07-05, "
            "decisión explícita del operador, con conocimiento de que maneja credenciales "
            "y conexiones RDP)."
        ),
        group="global",
        env_only=False,  # editable por UI (regla operator-config-always-via-ui)
        requires="STACKY_DEVOPS_PANEL_ENABLED",  # la sección vive dentro del panel 87
        default=True,
    ),
    # ── Plan 93 — Preflight de pipelines DevOps (semáforo "¿Va a funcionar?") ───
    FlagSpec(
        key="STACKY_DEVOPS_PREFLIGHT_ENABLED",
        type="bool",
        label="Preflight de pipelines (Plan 93)",
        description=(
            "Plan 93 — Boton '¿Va a funcionar?' del panel DevOps: chequea el "
            "pipeline ANTES de commit/trigger (YAML valido en el tracker real, "
            "steps placeholder, runners/agents disponibles, variables sin "
            "definir) para ADO y GitLab. Solo-lectura. Default ON: el endpoint "
            "/api/devops/preflight/check está disponible y el boton aparece de "
            "entrada; poné esta flag en OFF para volver al comportamiento "
            "anterior (404 y boton oculto)."
        ),
        group="global",  # mismo group que STACKY_DEVOPS_PANEL_ENABLED
        env_only=False,  # editable por UI (categoría 'devops')
        requires="STACKY_DEVOPS_PANEL_ENABLED",
        # ON por default por decisión explícita del operador (2026-07-09): rompe el
        # default-OFF original conscientemente. Está curada en _CURATED_DEFAULTS_ON
        # (test_default_known_only_for_curated exige la pertenencia al set).
        default=True,
    ),
    # ── Plan 94 — Caja fuerte de variables (secretos del pipeline fuera del YAML) ───
    FlagSpec(
        key="STACKY_DEVOPS_VARIABLES_ENABLED",
        type="bool",
        label="Variables del pipeline (Plan 94)",
        description=(
            "Plan 94 — Caja fuerte de variables: las secretas se guardan en el tracker "
            "(GitLab masked / ADO isSecret), nunca en el YAML ni en archivos de Stacky. "
            "Default ON: /api/devops/variables está disponible y la sección aparece "
            "de entrada; poné esta flag en OFF para volver al comportamiento anterior "
            "(404 y sección oculta)."
        ),
        group="global",
        env_only=False,  # editable por UI (categoría 'devops')
        requires="STACKY_DEVOPS_PANEL_ENABLED",
        # ON por default por decisión explícita del operador (2026-07-09): rompe el
        # default-OFF original conscientemente. Está curada en _CURATED_DEFAULTS_ON
        # (test_default_known_only_for_curated exige la pertenencia al set).
        default=True,
    ),
    # ── Plan 95 — Llevar a producción (Merge Request / Pull Request + merge HITL) ──
    FlagSpec(
        key="STACKY_DEVOPS_PRODUCTION_ENABLED",
        type="bool",
        label="Llevar a producción (Plan 95)",
        description=(
            "Plan 95 — Crea el Merge Request (GitLab) o Pull Request (ADO) del "
            "pipeline commiteado, muestra su pipeline en vivo y permite mergear con "
            "confirmación HITL. Default ON: /api/devops/production/* está disponible, "
            "el botón aparece y el modal de commit de ADO ya no muestra la nota 501; "
            "poné esta flag en OFF para volver al comportamiento anterior. Nota: la "
            "paridad ADO de commit/trigger/monitor NO depende de esta flag (completa "
            "contratos existentes ya gateados por sus propias flags del arnés)."
        ),
        group="global",
        env_only=False,  # editable por UI (categoría 'devops')
        requires="STACKY_DEVOPS_PANEL_ENABLED",
        # ON por default por decisión explícita del operador (2026-07-09): rompe el
        # default-OFF original conscientemente. Está curada en _CURATED_DEFAULTS_ON
        # (test_default_known_only_for_curated exige la pertenencia al set).
        default=True,
    ),
    # ── Plan 96 — Doctor de pipelines: diagnóstico del fallo en llano (ADO+GitLab) ──
    FlagSpec(
        key="STACKY_DEVOPS_DOCTOR_ENABLED",
        type="bool",
        label="Doctor de pipelines (Plan 96)",
        description=(
            "Plan 96 — Cuando un pipeline falla, el botón '¿Qué pasó?' baja el log "
            "del job y te lo explica en lenguaje llano; opcionalmente se lo pasa al "
            "agente DevOps. Solo lee, nunca ejecuta. Default ON: el botón aparece de "
            "entrada; poné esta flag en OFF para volver al comportamiento anterior "
            "(botón oculto)."
        ),
        group="global",
        env_only=False,  # editable por UI (categoría 'devops')
        requires="STACKY_DEVOPS_PANEL_ENABLED",
        # ON por default por decisión explícita del operador (2026-07-09): rompe el
        # default-OFF original conscientemente. Está curada en _CURATED_DEFAULTS_ON
        # (test_default_known_only_for_curated exige la pertenencia al set).
        default=True,
    ),
    # ── Plan 97 — Detección de stack técnico para presets de pipeline ───────────
    FlagSpec(
        key="STACKY_DEVOPS_STACK_DETECT_ENABLED",
        type="bool",
        label="Detección de stack para presets (Plan 97)",
        description=(
            "Plan 97 — Agrega el boton 'Detectar stack de mi proyecto' en el "
            "builder de pipelines: lee (solo lectura) los archivos de manifiesto "
            "del proyecto (requirements.txt, package.json, *.csproj) y "
            "preselecciona el preset de pasos mas probable. Default ON: el boton "
            "aparece de entrada; poné esta flag en OFF para volver al comportamiento "
            "anterior (galeria de presets manual, sin detección)."
        ),
        group="global",
        env_only=False,
        requires="STACKY_DEVOPS_PANEL_ENABLED",
        # ON por default por decisión explícita del operador (2026-07-09): rompe el
        # default-OFF original conscientemente. Está curada en _CURATED_DEFAULTS_ON
        # (test_default_known_only_for_curated exige la pertenencia al set).
        default=True,
    ),
    # ── Plan 98 — Bootstrap unico del panel DevOps ──────────────────────────────
    FlagSpec(
        key="STACKY_DEVOPS_BOOTSTRAP_ENABLED",
        type="bool",
        label="Carga rapida del panel DevOps (Plan 98)",
        description=(
            "Plan 98 — El panel DevOps se hidrata con un solo request "
            "(GET /api/devops/bootstrap) y los guardados de pipelines/publicaciones/"
            "ambientes viajan como PATCH por clave (payload chico, merge en el "
            "backend). Default ON. Con OFF todo funciona igual que antes (mas "
            "requests, payloads completos). No cambia ningun dato guardado."
        ),
        group="global",  # mismo group que STACKY_DEVOPS_PANEL_ENABLED (87 v2 F0)
        env_only=False,  # editable por UI (categoría 'devops')
        requires="STACKY_DEVOPS_PANEL_ENABLED",  # Plan 82 — declarativo, informa en UI
        # ON por default por decisión explícita del operador (2026-07-09): rompe el
        # default-OFF original conscientemente. Está curada en _CURATED_DEFAULTS_ON
        # (test_default_known_only_for_curated exige la pertenencia al set).
        default=True,
    ),
    # ── Plan 104 — Doctores IA por sección del panel DevOps ────────────────────
    FlagSpec(
        key="STACKY_DEVOPS_SECTION_DOCTOR_ENABLED",
        type="bool",
        label="Doctores IA por sección (Plan 104)",
        description=(
            "Plan 104 — Agrega un botón 'Doctor' en las secciones Pipeline/Ambientes/"
            "Publicaciones del panel DevOps: invoca a un agente IA (Claude Code CLI, "
            "Codex CLI o GitHub Copilot Pro) con el contexto de esa sección para que "
            "PROPONGA mejoras en markdown (nunca aplica cambios, HITL). Requiere el "
            "agente DevOps del plan 90. Default ON: el botón aparece de entrada; "
            "poné esta flag en OFF para volver al comportamiento anterior (botón "
            "oculto)."
        ),
        group="global",
        env_only=False,
        # [DESVÍO del plan 104 F4 v4, verificado contra código real]: el doc pedía
        # requires="STACKY_DEVOPS_AGENT_ENABLED", pero ESA flag YA declara
        # requires="STACKY_DEVOPS_PANEL_ENABLED" (línea de arriba) — encadenar
        # rompería R4 (profundidad máxima 1, validate_requires_graph:2309,
        # "cadena prohibida"). Se usa el mismo master que TODAS las hermanas de la
        # sección DevOps (Publicaciones/Ambientes/Agente/Servidores/Preflight/
        # Variables/Producción/StackDetect/Doctor): STACKY_DEVOPS_PANEL_ENABLED. La
        # dependencia FUNCIONAL real con el agente DevOps (sin el 90 no hay runtime
        # IA) se sigue exigiendo en el endpoint F2 con un guard explícito de
        # STACKY_DEVOPS_AGENT_ENABLED (404 propio, independiente de esta flag).
        requires="STACKY_DEVOPS_PANEL_ENABLED",
        # ON por default por decisión explícita del operador (2026-07-09): rompe el
        # default-OFF original conscientemente. Está curada en _CURATED_DEFAULTS_ON
        # (test_default_known_only_for_curated exige la pertenencia al set).
        default=True,
    ),
    # ── Plan 105 — Consola remota de prompts por servidor ─────────────────────
    FlagSpec(
        key="STACKY_DEVOPS_REMOTE_CONSOLE_ENABLED",
        type="bool",
        label="Consola remota (Plan 105)",
        description=(
            "Plan 105 — Consola remota de prompts por servidor (auditada, reversible, 1-click switch). "
            "El operador selecciona un servidor del registro del plan 91, escribe un prompt, y un agente "
            "ejecuta comandos PowerShell EN el servidor vía WinRM con auditoría completa JSONL por alias. "
            "Modo read-only por default (validador conservador); modo escritura opt-in por conversación. "
            "Requiere el panel DevOps y al menos un servidor registrado. Default ON "
            "(activado 2026-07-09, decisión explícita del operador; ya estaba en true en el "
            "deploy vivo)."
        ),
        group="global",
        env_only=False,
        requires="STACKY_DEVOPS_PANEL_ENABLED",
        # ON por default por decisión explícita del operador (2026-07-09): rompe el
        # default-OFF original conscientemente. Está curada en _CURATED_DEFAULTS_ON
        # (test_default_known_only_for_curated exige la pertenencia al set).
        default=True,
    ),
    # ── Plan 107 — Preview de árbol de directorios y raíz sandbox (Ambientes) ──
    FlagSpec(
        key="STACKY_DEVOPS_ENV_TREE_PREVIEW_ENABLED",
        type="bool",
        label="Preview de árbol de ambientes (Plan 107)",
        description=(
            "Plan 107 — En la sección Ambientes, muestra las carpetas a crear como "
            "ÁRBOL jerárquico (en vez de lista plana), con estado por nodo. "
            "SOLO-LECTURA, no cambia qué se crea. Default ON. Con OFF la sección "
            "usa la tabla plana de siempre."
        ),
        group="global",
        env_only=False,
        requires="STACKY_DEVOPS_PANEL_ENABLED",  # master del panel (depth-1, NO la flag hija Environments)
        # ON por default por decisión explícita del operador (2026-07-09): rompe el
        # default-OFF original conscientemente (el plan 107 traía default=False
        # explícito -- ver docstring de test_plan107_flags.py). Está curada en
        # _CURATED_DEFAULTS_ON (test_default_known_only_for_curated exige la
        # pertenencia al set).
        default=True,
    ),
    FlagSpec(
        key="STACKY_DEVOPS_ENV_SANDBOX_ENABLED",
        type="bool",
        label="Raíz sandbox de pruebas (Plan 107)",
        description=(
            "Plan 107 — Permite apuntar el plan/apply de Ambientes a una carpeta "
            "sandbox temporal para probar, SIN tocar la raíz de producción. Guard "
            "duro: rechaza rutas que sean iguales/contengan/estén contenidas en la "
            "raíz real. Default ON. La raíz sandbox NUNCA se guarda en el perfil."
        ),
        group="global",
        env_only=False,
        requires="STACKY_DEVOPS_PANEL_ENABLED",  # master del panel (depth-1)
        # ON por default por decisión explícita del operador (2026-07-09): idem
        # nota arriba (rompe el default-OFF original conscientemente; curada en
        # _CURATED_DEFAULTS_ON).
        default=True,
    ),
    # ── Plan 116 — Doctor de conexiones con remediación guiada ──
    FlagSpec(
        key="STACKY_DEVOPS_CONNECTION_DOCTOR_ENABLED",
        type="bool",
        default=True,  # promovida a default ON (operador 2026-07-15, barrido de flags 122-141 + revision general)
        label="Doctor de conexiones DevOps (Plan 116)",
        description=(
            "Plan 116 — Tira de salud de conexiones en el panel DevOps: diagnostica "
            "tracker (ADO/GitLab/Jira/Mantis), servidores registrados, CLIs de los "
            "runtimes y keyring con remediación paso a paso. Determinista (sin IA, "
            "sin costo). Solo corre con click del operador. Con OFF el panel queda "
            "idéntico a hoy."
        ),
        group="global",
        env_only=False,
        requires="STACKY_DEVOPS_PANEL_ENABLED",  # master del panel (R4 profundidad-1)
        # SIN default= (gotcha Plan 63): nace OFF; el default vive en config.py.
    ),
    # ── Plan 120 — Centro de Despliegues: deploy multi-destino, rollback 1-click ──
    FlagSpec(
        key="STACKY_DEPLOYMENTS_ENABLED",
        type="bool",
        label="Centro de Despliegues (Plan 120)",
        description=(
            "Plan 120 — Sección 'Despliegues' del panel DevOps: deploy multi-destino "
            "(servidores registrados + Local) con releases inmutables, rollback 1-click, "
            "verificación post-deploy y métricas DORA locales. Determinista, cero LLM en "
            "el camino feliz. Con OFF el panel queda idéntico a hoy."
        ),
        group="global",
        env_only=False,
        requires="STACKY_DEVOPS_PANEL_ENABLED",  # master del panel (R4 profundidad-1)
        # SIN default= (gotcha Plan 63): nace OFF; el default vive en config.py.
    ),
    FlagSpec(
        key="STACKY_DEPLOYMENTS_EXECUTE_ENABLED",
        type="bool",
        label="Ejecutar deploys y rollbacks (Plan 120)",
        description=(
            "Plan 120 — Habilita EJECUTAR deploy/rollback (no solo el dry-run /plan). "
            "Con OFF, /execute y /rollback devuelven 403 aunque el master esté ON: "
            "el operador puede ver el plan sin poder disparar acciones de escritura."
        ),
        group="global",
        env_only=False,
        requires="STACKY_DEVOPS_PANEL_ENABLED",  # master del panel (R4 profundidad-1)
    ),
    FlagSpec(
        key="STACKY_DEPLOYMENTS_AI_DIAGNOSIS_ENABLED",
        type="bool",
        label="Diagnóstico IA de deploys fallidos (Plan 120)",
        description=(
            "Plan 120 — Botón de diagnóstico con el modelo LOCAL (Plan 106, costo cero) "
            "sobre un deploy fallido: explica el paso que falló y sugiere remediación. "
            "Requiere el modelo local alcanzable; si no lo está, el botón queda "
            "deshabilitado con hint y el deploy sigue 100% funcional sin esto."
        ),
        group="global",
        env_only=False,
        requires="STACKY_DEVOPS_PANEL_ENABLED",  # master del panel (R4 profundidad-1)
    ),
    FlagSpec(
        key="STACKY_DEPLOYMENTS_RETAIN_RELEASES",
        type="int",
        label="Releases retenidas por destino",
        description=(
            "Plan 120 — Cuántas releases anteriores se conservan en `releases\\` de cada "
            "destino (para poder hacer rollback sin volver a transferir). Las más viejas "
            "se borran tras cada deploy exitoso. Default 3."
        ),
        group="global",
        env_only=False,
        requires="STACKY_DEVOPS_PANEL_ENABLED",
        min_value=1,
        max_value=10,
    ),
    FlagSpec(
        key="STACKY_DEPLOYMENTS_SMOKE_TIMEOUT_SEC",
        type="int",
        label="Timeout del smoke post-deploy (segundos)",
        description=(
            "Plan 120 — Tiempo máximo de espera de la verificación post-deploy (smoke "
            "HTTP o comando PowerShell) antes de considerarla fallida. Default 30."
        ),
        group="global",
        env_only=False,
        requires="STACKY_DEVOPS_PANEL_ENABLED",
        min_value=5,
        max_value=300,
    ),
    FlagSpec(
        key="STACKY_DEVOPS_REMOTE_TARGET_ENABLED",
        type="bool",
        label="Operar en el servidor seleccionado (Plan 108)",
        description=(
            "Plan 108 — Ancla el chat del agente DevOps y el plan/apply de Ambientes "
            "al servidor seleccionado en el panel: exploración y comandos corren vía "
            "WinRM auditado (Plan 105), nunca en la máquina local. Requiere Servidores (91) "
            "y Consola remota (105) activos. Default ON."
        ),
        group="global",
        env_only=False,
        requires="STACKY_DEVOPS_PANEL_ENABLED",  # master del panel (depth-1)
        # ON por default por decisión explícita del operador (2026-07-09): idem
        # nota arriba (rompe el default-OFF original conscientemente; curada en
        # _CURATED_DEFAULTS_ON).
        default=True,
    ),
    # ── Plan 74 — Migrador ADO→GitLab ────────────────────────────────────────
    FlagSpec(
        key="STACKY_MIGRATOR_ADO_TO_GITLAB_ENABLED",
        default=True,  # promovida a default ON (operador 2026-07-10, curada en _CURATED_DEFAULTS_ON)
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
        # default="auto" removido (supervisión 2026-07-02): config.py:856 ya provee "auto"
        # como default de runtime; un default= explícito sin curar rompía el centinela
        # test_default_known_only_for_curated del Plan 63 (gotcha harness-flags-default-explicit-gotcha).
    ),
    # ── Plan 75 — Deep links bidireccionales GitLab ───────────────────────────
    FlagSpec(
        key="STACKY_GITLAB_DEEP_LINKS_ENABLED",
        default=True,  # promovida a default ON (operador 2026-07-10, curada en _CURATED_DEFAULTS_ON)
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
    # ── Plan 76 — Integración opcional codebase-memory-mcp (externo) ──────────
    FlagSpec(
        key="STACKY_CODEBASE_MEMORY_MCP_ENABLED",
        default=True,  # promovida a default ON (operador 2026-07-10, curada en _CURATED_DEFAULTS_ON)
        type="bool",
        label="Codebase Memory MCP (externo, opt-in) — Plan 76",
        description=(
            "Plan 76 — Si ON, el operador puede integrar el servidor externo "
            "codebase-memory-mcp (instalado aparte) para indexar el codebase. "
            "Stacky NO empaqueta el binario; solo expone estado + guía de instalación. "
            "OFF (default): byte-idéntico a hoy, sin endpoints activos ni config MCP inyectada. "
            "Ver /api/codebase-memory-mcp/status para instrucciones de instalación."
        ),
        group="global",
        env_only=False,  # editable por UI (regla dura operator-config-always-via-ui)
        # default=False removido (supervisión 2026-07-02): config.py:871 ya provee "false"
        # (bool type-zero=False); un default= explícito sin curar rompía el centinela
        # test_default_known_only_for_curated del Plan 63 (gotcha harness-flags-default-explicit-gotcha).
    ),
    # ── Plan 80 — Wiring real codebase-memory-mcp: allowlist + ruta del binario ──
    FlagSpec(
        key="STACKY_CODEBASE_MEMORY_MCP_PROJECTS",
        type="csv",
        label="Codebase Memory MCP — proyectos (CSV) — Plan 80",
        description=(
            "Plan 80 — Lista CSV de proyectos donde inyectar el MCP externo codebase-memory-mcp. "
            "Vacío = todos (si el master STACKY_CODEBASE_MEMORY_MCP_ENABLED está ON). "
            "Requiere también STACKY_CODEBASE_MEMORY_MCP_BINARY_PATH seteado."
        ),
        group="global",
        pair="STACKY_CODEBASE_MEMORY_MCP_ENABLED",  # renderiza junto al master toggle
        env_only=False,
        requires="STACKY_CODEBASE_MEMORY_MCP_ENABLED",  # ya cubierta por `pair`; refuerza el payload
    ),
    FlagSpec(
        key="STACKY_CODEBASE_MEMORY_MCP_BINARY_PATH",
        type="str",
        label="Codebase Memory MCP — ruta del binario — Plan 80",
        description=(
            "Plan 80 — Ruta absoluta al ejecutable codebase-memory-mcp instalado por el operador. "
            "Vacío = no se inyecta el 2º server (seguro). Stacky NO empaqueta el binario. "
            "Ejemplo: C:\\\\tools\\\\codebase-memory-mcp.exe"
        ),
        group="global",
        env_only=False,
        requires="STACKY_CODEBASE_MEMORY_MCP_ENABLED",
    ),
    # ── Plan 106 — Modelo local (Qwen 3 32B q4 u otro, vía Ollama/LM Studio/vLLM) ──
    FlagSpec(
        key="LOCAL_LLM_ENABLED",
        type="bool",
        label="Modelo local (Ollama/LM Studio/vLLM)",
        description="Habilita el cliente LLM local para análisis de código y sugerencias de pipeline con modelos como Qwen 3 32B q4.",
        group="global",
        # ON por default por decisión explícita del operador (2026-07-09): rompe el
        # default-OFF original conscientemente. Está curada en _CURATED_DEFAULTS_ON
        # (test_default_known_only_for_curated exige la pertenencia al set).
        default=True,
    ),
    FlagSpec(
        key="LOCAL_LLM_ENDPOINT",
        type="str",
        label="Endpoint del modelo local",
        description="URL OpenAI-compatible del servidor local (Ollama: http://localhost:11434/v1/chat/completions).",
        group="global",
        requires="LOCAL_LLM_ENABLED",
        # SIN default= (verificado: default_is_known() no distingue por type; un
        # default explícito acá también rompería test_default_known_only_for_curated,
        # que solo curó bools). El default EFECTIVO ya vive en config.py.
    ),
    FlagSpec(
        key="LOCAL_LLM_MODEL",
        type="str",
        label="Modelo local (tag)",
        description="Tag del modelo en el servidor local (ej. qwen3:32b).",
        group="global",
        requires="LOCAL_LLM_ENABLED",
        # SIN default= (mismo motivo que LOCAL_LLM_ENDPOINT).
    ),
    FlagSpec(
        key="LOCAL_LLM_TIMEOUT_SEC",
        type="int",
        label="Timeout modelo local (segundos)",
        description="Tiempo máximo de espera por respuesta del modelo local. Modelos 32B en CPU/GPU consumer pueden tardar minutos.",
        group="global",
        requires="LOCAL_LLM_ENABLED",
        min_value=10,
        max_value=600,
        # SIN default= (mismo motivo que LOCAL_LLM_ENDPOINT).
    ),
    # ── Plan 110 — Revisor de PRs (Haiku solo-lectura + modelo local) ──────────
    FlagSpec(
        key="STACKY_PR_REVIEWER_ENABLED",
        type="bool",
        label="Revisor de PRs (Plan 110)",
        description=(
            "Plan 110 — Sección 'Revisor de PRs' del panel DevOps: lista las PRs "
            "abiertas del tracker activo y permite revisarlas con Claude Haiku "
            "(solo-lectura, recomienda una acción) o con el modelo local. "
            "Default ON: la sección aparece; apagala si /api/pr-review/* debe dar 404."
        ),
        group="global",
        env_only=False,
        requires="STACKY_DEVOPS_PANEL_ENABLED",  # H19: master sin requires propio
        # DEFAULT ON (operador). Curada en _CURATED_DEFAULTS_ON (única vía canónica
        # sin romper test_default_known_only_for_curated / test_declared_default_true_set).
        default=True,
    ),
    FlagSpec(
        key="STACKY_PR_REVIEW_HAIKU_MODEL",
        type="str",
        label="Modelo Haiku para revisar PRs",
        description=(
            "Plan 110 — Id del modelo Claude Haiku que usa la revisión de PRs "
            "(se valida que contenga 'haiku'). Elegilo con 'Ver modelos "
            "disponibles' en la sección. Default: claude-3.5-haiku."
        ),
        group="global",
        env_only=False,
        requires="STACKY_DEVOPS_PANEL_ENABLED",  # H19: NO encadenar a STACKY_PR_REVIEWER_ENABLED
    ),
    FlagSpec(
        key="STACKY_PR_REVIEW_DIFF_MAX_CHARS",
        type="int",
        label="Tope de tamaño del diff (caracteres)",
        description=(
            "Plan 110 — Máximo de caracteres del diff que se le manda al modelo. "
            "Diffs más grandes se truncan (protege privacidad y velocidad). "
            "Default 60000."
        ),
        group="global",
        env_only=False,
        requires="STACKY_DEVOPS_PANEL_ENABLED",
        min_value=1000,
        max_value=500000,
    ),
    FlagSpec(
        key="STACKY_PR_REVIEW_LOCAL_DIFF_MAX_CHARS",
        type="int",
        label="Tope del diff en el camino solo-local (caracteres)",
        description=(
            "Plan 110 v2.1 — Máximo de caracteres del diff que recibe el modelo LOCAL "
            "(que no saca nada de tu máquina). Es sólo un tope de velocidad/ventana de "
            "contexto, NO de privacidad. 0 = sin límite (contexto completo). Default 200000."
        ),
        group="global",
        env_only=False,
        requires="STACKY_DEVOPS_PANEL_ENABLED",
        min_value=0,       # 0 = sin límite / contexto completo
        max_value=2000000,
    ),
    FlagSpec(
        key="STACKY_PR_REVIEW_TIMEOUT_SEC",
        type="int",
        label="Timeout de la revisión Haiku (segundos)",
        description=(
            "Plan 110 — Tiempo máximo de espera por la respuesta de Haiku. "
            "Default 120."
        ),
        group="global",
        env_only=False,
        requires="STACKY_DEVOPS_PANEL_ENABLED",
        min_value=10,
        max_value=600,
    ),
    # ── Plan 119 — Rediseño minimalista del shell DevOps ──────────────────────
    FlagSpec(
        key="STACKY_DEVOPS_UI_V2_ENABLED",
        type="bool",
        label="Shell DevOps minimalista (Plan 119)",
        description=(
            "Plan 119 — Reemplaza el shell del panel DevOps (header, sub-tabs y "
            "selector de servidor) por un diseño minimalista que usa los tokens de "
            "theme.css, y la sección Servidores por una tabla. Solo presentación: "
            "cero cambios de comportamiento. Default OFF: con la flag apagada la UI "
            "es idéntica a la actual."
        ),
        group="global",
        env_only=False,
        requires="STACKY_DEVOPS_PANEL_ENABLED",  # profundidad 1 (master del panel, no una flag hija)
        # SIN default= (solo _CURATED_DEFAULTS_ON puede; default OFF vive en config.py).
    ),
    # ── Plan 117 — Insights locales de ejecuciones (TL;DR + triage + digest narrado) ──
    FlagSpec(
        key="STACKY_LOCAL_INSIGHTS_ENABLED",
        type="bool",
        default=True,  # promovida a default ON (operador 2026-07-15, config se hace despues desde la UI)
        label="Insights locales de ejecuciones",
        description="TL;DR y triage automáticos de cada run terminado usando el modelo local (Plan 106). Requiere el modelo local habilitado y configurado.",
        group="global",
        # SIN default= (no curada en _CURATED_DEFAULTS_ON; el default efectivo OFF vive en config.py — gotcha Plan 63/81).
        # SIN requires= estático hacia LOCAL_LLM_ENABLED: la dependencia se chequea en runtime (R4 prohíbe cadenas).
    ),
    FlagSpec(
        key="STACKY_LOCAL_INSIGHTS_SWEEP_SEC",
        type="int",
        label="Intervalo del sweep de insights (segundos)",
        description="Cada cuántos segundos el barrido de fondo busca ejecuciones terminadas sin insight.",
        group="global",
        requires="STACKY_LOCAL_INSIGHTS_ENABLED",
        min_value=30,
        max_value=3600,
    ),
    FlagSpec(
        key="STACKY_LOCAL_INSIGHTS_MAX_PER_CYCLE",
        type="int",
        label="Máximo de insights por ciclo",
        description="Tope de ejecuciones anotadas por ciclo del barrido (protege la CPU/GPU local).",
        group="global",
        requires="STACKY_LOCAL_INSIGHTS_ENABLED",
        min_value=1,
        max_value=20,
    ),
    FlagSpec(
        key="STACKY_LOCAL_INSIGHTS_LOOKBACK_DAYS",
        type="int",
        label="Ventana de insights (días)",
        description="Solo se anotan ejecuciones iniciadas dentro de esta ventana hacia atrás.",
        group="global",
        requires="STACKY_LOCAL_INSIGHTS_ENABLED",
        min_value=1,
        max_value=90,
    ),
    FlagSpec(
        key="STACKY_LOCAL_INSIGHTS_DIGEST_NARRATIVE_ENABLED",
        type="bool",
        default=True,  # promovida a default ON (operador 2026-07-15, config se hace despues desde la UI)
        label="Narrativa local del digest",
        description="Habilita narrar el digest de ejecuciones en lenguaje natural con el modelo local (botón en la card del digest).",
        group="global",
        requires="STACKY_LOCAL_INSIGHTS_ENABLED",
    ),
    # ── Plan 122 — Comparador de BD entre ambientes (serie 122-126, núcleo) ──
    FlagSpec(
        key="STACKY_DB_COMPARE_ENABLED",
        type="bool",
        default=True,  # promovida a default ON (operador 2026-07-15, config se hace despues desde la UI)
        label="Comparador de BD entre ambientes",
        description="Master del comparador (serie 122-126): tab UI, registro de ambientes, snapshots y comparaciones. OFF = invisible.",
        group="global",
    ),
    FlagSpec(
        key="STACKY_DB_COMPARE_CONNECT_TIMEOUT_SEC",
        type="int",
        label="Comparador BD: timeout de conexión (seg)",
        description="Timeout de login/TCP al abrir conexión read-only a un ambiente registrado.",
        group="global",
        # NO default= acá: default_is_known() trata CUALQUIER spec.default no-None
        # (no solo bool) como "curado" y exige alta en _CURATED_DEFAULTS_ON
        # (ratchet Plan 63, ver test_harness_flags.py:465) — ese set es exclusivamente
        # para promociones bool a True; el valor real "10" ya vive en config.py y
        # llega al operador vía read_current()["value"], no vía spec.default.
        requires="STACKY_DB_COMPARE_ENABLED",
        min_value=1,
        max_value=120,
    ),
    # ── Plan 126 — Comparador de BD entre ambientes (paridad de DATOS) ────────
    FlagSpec(
        key="STACKY_DB_COMPARE_DATA_DIFF_ENABLED",
        type="bool",
        default=True,  # promovida a default ON (operador 2026-07-15, config se hace despues desde la UI)
        label="Comparador BD: paridad de datos",
        description="Permite comparar DATOS de tablas de parámetros por PK y generar scripts DML + backups. OFF = solo esquema.",
        group="global",
        requires="STACKY_DB_COMPARE_ENABLED",
    ),
    FlagSpec(
        key="STACKY_DB_COMPARE_DATA_MAX_ROWS",
        type="int",
        label="Comparador BD: máx. filas por tabla (datos)",
        description="Cap duro de filas leídas por tabla y por lado en el diff de datos; excedente = resultado truncado. Default 5000.",
        group="global",
        # NO default= acá: mismo gotcha que STACKY_DB_COMPARE_CONNECT_TIMEOUT_SEC
        # (Plan 122) — default_is_known() trata cualquier spec.default no-None
        # como "curado" y exige alta en _CURATED_DEFAULTS_ON, set reservado a
        # promociones bool=True. El valor sugerido "5000" vive en config.py.
        requires="STACKY_DB_COMPARE_ENABLED",
        min_value=100,
        max_value=200000,
    ),
    # ── Plan 139 — App Shell v2 (sidebar agrupada + TopBar + iconografía) ────
    # Default OFF (decisión de criterio, ver comentario largo en config.py):
    # reemplaza el chrome de navegación completo; mismo patrón sin objeciones
    # del plan 119 (STACKY_DEVOPS_UI_V2_ENABLED, también default OFF).
    FlagSpec(
        key="STACKY_UI_SHELL_V2_ENABLED",
        type="bool",
        label="Shell v2: navegación lateral agrupada",
        description=(
            "Plan 139 — Reemplaza la fila de pestañas superior por una barra lateral "
            "agrupada por temas (Trabajo, Observabilidad, Conocimiento, Plataforma, "
            "Configuración) con iconografía y una barra superior renovada. Default OFF: "
            "con OFF la interfaz es idéntica a la actual. Solo cambia la presentación; "
            "mismas pantallas y misma navegación."
        ),
        group="global",
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
    if flag_type in ("csv", "json", "str"):
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
    """Categorías ordenadas para el frontend (id/label/description/tier/intent).
    Plan 78 F0 — tier e intent expuestos de forma ADITIVA (no rompe campos previos)."""
    return [{"id": c.id, "label": c.label, "description": c.description,
             "tier": c.tier, "intent": c.intent}
            for c in FLAG_CATEGORIES]


def requires_met(spec: FlagSpec, values_by_key: dict[str, object]) -> bool:
    """True si la dependencia declarada está satisfecha (o no hay dependencia).

    values_by_key: mapa key→valor actual (el que arma read_current).
    Casos borde:
    - spec.requires is None → True.
    - la key requerida no está en values_by_key → True (fail-open: nunca
      marcar 'sin efecto' por un bug de datos).
    - valor del master truthy (bool True) → True; False/None/'' → False.
    """
    if spec.requires is None:
        return True
    if spec.requires not in values_by_key:  # [C3 v3] fail-open simple
        return True
    return bool(values_by_key[spec.requires])


def validate_requires_graph() -> list[str]:
    """Valida el grafo de dependencias del registry. Devuelve lista de errores ('' vacía = OK).

    Reglas (todas estructurales, deterministas):
    R1: spec.requires debe ser la key de un FlagSpec existente en FLAG_REGISTRY.
    R2: el master apuntado debe tener type == 'bool'.
    R3: prohibida la auto-referencia (spec.requires != spec.key).
    R4: profundidad máxima 1 — un master apuntado NO puede tener a su vez requires
        (sin cadenas ni ciclos por construcción).
    """
    errors: list[str] = []
    for spec in FLAG_REGISTRY:
        if spec.requires is None:
            continue
        master = _REGISTRY_INDEX.get(spec.requires)
        if master is None:
            errors.append(f"{spec.key}: requires apunta a key inexistente {spec.requires!r}")
            continue
        if master.type != "bool":
            errors.append(f"{spec.key}: requires apunta a {spec.requires} de tipo {master.type!r}, debe ser bool")
        if spec.requires == spec.key:
            errors.append(f"{spec.key}: requires auto-referencial")
        if master.requires is not None:
            errors.append(f"{spec.key}: cadena prohibida — {spec.requires} también declara requires")
    return errors


def value_in_bounds(spec: FlagSpec, value: object) -> bool:
    """True si `value` respeta los bounds declarados (o no hay bounds).

    Casos borde (todos deterministas):
    - spec sin bounds (ambos None) → True.
    - spec.type no es "int" ni "float" → True (bounds solo aplican a numéricas).
    - value None o no convertible a float → True (fail-open: nunca marcar
      fuera-de-rango por un bug de datos; el tipo lo valida _cast aparte).
    - comparación INCLUSIVE: min_value <= v <= max_value.
    """
    if spec.min_value is None and spec.max_value is None:
        return True
    if spec.type not in ("int", "float"):
        return True
    try:
        v = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return True
    if spec.min_value is not None and v < spec.min_value:
        return False
    if spec.max_value is not None and v > spec.max_value:
        return False
    return True


def validate_bounds_registry() -> list[str]:
    """Valida los bounds declarados en FLAG_REGISTRY. Lista vacía = OK.

    Reglas estructurales:
    R1: bounds solo en specs con type "int" o "float".
    R2: si ambos declarados, min_value <= max_value.
    R3: si el spec declara `default` (no None) numérico, debe cumplir sus propios bounds.
    """
    errors: list[str] = []
    for spec in FLAG_REGISTRY:
        if spec.min_value is None and spec.max_value is None:
            continue
        if spec.type not in ("int", "float"):
            errors.append(f"{spec.key}: bounds declarados sobre type {spec.type!r} (solo int/float)")
            continue
        if spec.min_value is not None and spec.max_value is not None and spec.min_value > spec.max_value:
            errors.append(f"{spec.key}: min_value {spec.min_value} > max_value {spec.max_value}")
        if spec.default is not None and not value_in_bounds(spec, spec.default):
            errors.append(f"{spec.key}: default {spec.default!r} fuera de sus propios bounds")
    return errors


# Plan 84 — snapshot de los valores boot-time de las flags restart_required.
# Lo llena create_app() vía snapshot_boot_values(). Vacío = fail-open (tests).
_BOOT_VALUES: dict[str, object] = {}


def _current_value(spec: FlagSpec) -> object:
    """Valor vigente de la flag: os.getenv casteado (env_only) o atributo de config."""
    if spec.env_only:
        raw = os.getenv(spec.key)
        if raw is None:
            return _type_zero(spec.type)
        return _cast(spec, raw)
    from config import config
    return getattr(config, spec.key)


def snapshot_boot_values() -> None:
    """Captura el valor boot-time de cada flag restart_required. Idempotente NO:
    pisa siempre (create_app la llama UNA vez, al principio, antes de armar daemons)."""
    _BOOT_VALUES.clear()
    for spec in FLAG_REGISTRY:
        if spec.restart_required:
            _BOOT_VALUES[spec.key] = _current_value(spec)


def pending_restart(spec: FlagSpec, value: object) -> bool:
    """True si la flag es restart_required, hay snapshot, y el valor actual difiere
    del valor con el que arrancó el proceso. Fail-open: sin snapshot → False."""
    if not spec.restart_required:
        return False
    if spec.key not in _BOOT_VALUES:
        return False
    return value != _BOOT_VALUES[spec.key]


def read_current() -> list[dict]:
    """Devuelve spec + valor actual de cada flag del registry."""
    result = []
    for spec in FLAG_REGISTRY:
        value = _current_value(spec)
        unset = spec.env_only and os.getenv(spec.key) is None

        # Plan 84 — computar UNA vez antes del dict: is_pending = pending_restart(spec, value)
        is_pending = pending_restart(spec, value)

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
            "plain_help": plain_help_for(spec.key),  # Plan 86 — ayuda en lenguaje llano
            "requires": spec.requires,
            "requires_met": True,   # se corrige en el pase de abajo
            "min_value": spec.min_value,
            "max_value": spec.max_value,
            "in_bounds": True if unset else value_in_bounds(spec, value),
            # Plan 84 — metadata de restart
            "restart_required": spec.restart_required,
            "pending_restart": is_pending,
            "boot_value": _BOOT_VALUES.get(spec.key) if is_pending else None,
            # Plan 85 — metadata de cableado honesto
            "reserved": spec.reserved,
            "reserved_reason": spec.reserved_reason,
        })

    values_by_key = {r["key"]: r["value"] for r in result}
    by_key = {s.key: s for s in FLAG_REGISTRY}
    for r in result:
        r["requires_met"] = requires_met(by_key[r["key"]], values_by_key)
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
        if not value_in_bounds(spec, result[key]):
            lo = "-inf" if spec.min_value is None else spec.min_value
            hi = "inf" if spec.max_value is None else spec.max_value
            raise ValueError(
                f"Flag {spec.key!r}: valor {result[key]!r} fuera de rango [{lo}..{hi}]."
            )
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
    if spec.type == "str":
        return "" if raw is None else str(raw)
    raise ValueError(f"Tipo desconocido en FLAG_REGISTRY para {spec.key!r}: {spec.type!r}")
