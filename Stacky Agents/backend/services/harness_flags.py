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
    type: str            # "bool" | "csv" | "int" | "float" | "str" | "json"
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
    CategorySpec("paridad_proveedores", "Paridad de proveedores (ADO ↔ GitLab)",
        "Plan 218 — registro de capacidades, destino por proyecto, vocabulario canónico y degradación declarada del eje multi-proveedor.",
        tier="advanced", intent="Ver y controlar la paridad entre Azure DevOps y GitLab"),
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
        "STACKY_MODEL_CATALOG_ENABLED",  # Plan 159 — catálogo unificado modelos/efforts
        "STACKY_CLAUDE_ACCOUNT_MODELS_ENABLED",  # Plan 288 — modelos de la cuenta local
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
        # Plan 284 — knobs numéricos del Documentador (nota, gate de citas, minería, presupuesto)
        "STACKY_DOCS_OPERATOR_NOTE_MAX_CHARS",
        "STACKY_DOCS_CITATION_GATE_MIN_RATIO",
        "STACKY_DOCS_TICKET_MINING_MAX",
        "STACKY_DOCS_PIPELINE_MAX_LLM_CALLS",
        # Plan 285 — los 2 knobs numéricos del rigor por afirmación
        "STACKY_DOCS_RIGOR_MIN_DENSITY",
        "STACKY_DOCS_RIGOR_MIN_CITATIONS",
        # Plan 35 — aprendizaje del arnés (cosecha + reinyección + 2 knobs).
        # Reusan esta categoría en vez de crear "harness_learning": un grupo
        # nuevo sin entrada acá pone rojo test_every_registry_flag_is_categorized.
        "STACKY_HARNESS_LEARNING_HARVEST_ENABLED",
        "STACKY_HARNESS_LEARNING_INJECT_ENABLED",
        "STACKY_HARNESS_LEARNING_INJECT_MAX",
        "STACKY_HARNESS_LEARNING_INJECT_MIN_CONF",
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
        # Plan 240 F8 — runtime veraz del agente QA UAT E2E
        "STACKY_QA_UAT_ADO_BRIDGE_ENABLED", "STACKY_QA_UAT_FUNCTIONAL_VERDICT_ENABLED",
        "STACKY_QA_UAT_AUTOSTART_AGENDA_ENABLED",
        # Plan 241 F2/F7 — cero falso verde: discriminacion estricta y roll-up de epicas
        "STACKY_QA_UAT_STRICT_DISCRIMINATION_ENABLED", "STACKY_QA_UAT_EPIC_ROLLUP_ENABLED",
        # Plan 274 — eficiencia de navegacion del agente QA UAT
        "STACKY_QA_UAT_SCREENSHOT_BUDGET_ENABLED", "STACKY_QA_UAT_STATE_WAITS_ENABLED",
        "STACKY_QA_UAT_RESPECT_WORKERS_ENABLED", "STACKY_QA_UAT_DEEPLINK_PROBE_ENABLED",
        "STACKY_QA_UAT_DATA_CACHE_ENABLED", "STACKY_QA_UAT_STAGE_DEADLINE_ENABLED",
        # Plan 209 — guia "Como validar esto" para el usuario de RS
        "STACKY_VALIDATION_PLAYBOOK_ENABLED",
        # Plan 214 — validacion QAUAT E2E al completar el Developer
        "STACKY_QA_UAT_ON_DEV_COMPLETE_ENABLED", "STACKY_QA_UAT_AUTORUN_ENABLED",
        # Plan 213 — analistas declaran supuestos en vez de frenar el pipeline
        "STACKY_ASSUMPTION_MODE_ENABLED", "STACKY_ASSUMPTION_MODE_AGENT_TYPES",
        "STACKY_ASSUMPTION_MAX_PER_RUN",
        # Plan 262 — recuperacion en caliente: una ruta invalida no es una caida
        "STACKY_QA_UAT_HOT_RECOVERY_ENABLED", "STACKY_QA_UAT_RECOVERY_MAX_PER_RUN",
        "STACKY_QA_UAT_RECOVERY_MAX_PER_CASE", "STACKY_QA_UAT_HEALTH_PROBE_TIMEOUT_S",
        "STACKY_QA_UAT_HEALTH_PROBE_CONFIRM_S", "STACKY_QA_UAT_ROUTE_ALLOWLIST",
        "STACKY_QA_UAT_SAFE_ROUTE", "AGENDA_WEB_BASE_URL", "QA_NAV_RETRIES",
    ),
    "integridad_grounding": (
        "STACKY_RUN_PREFLIGHT_GATE_ENABLED", "STACKY_VERIFY_TASK_BEFORE_CONSUMED_ENABLED",
        "STACKY_OUTPUT_GROUNDING_ENABLED", "STACKY_OUTPUT_GROUNDING_REPAIR",
        # Plan 133 — Contrato de inyección de contexto por agente.
        "STACKY_RUN_TICKET_REFRESH_ENABLED", "STACKY_BUSINESS_PREFLIGHT_ENABLED",
        "STACKY_ADO_BLOCKER_BLOCK_ENABLED", "STACKY_RUN_DIRECTIVE_ENABLED",
        "STACKY_REQUIRED_BLOCKS_ENABLED",
    ),
    "epicas_ado": (
        "STACKY_EPIC_FROM_BRIEF_ENABLED", "STACKY_BRIEF_MODEL_SELECT_ENABLED",
        "STACKY_EPIC_AUTOPUBLISH_BACKEND",   # Plan 278 F6 — gobierna el autopublish en los 3 runtimes
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
        "STACKY_CI_RUN_LEDGER_ENABLED",      # Plan 191 — bitácora durable de corridas CI
        "STACKY_CI_FAILURE_TRIAGE_ENABLED",  # Plan 193 — triage de fallos CI (logs inline)
        "STACKY_PIPELINE_GENERATOR_ENABLED", # Plan 73 — generador declarativo PipelineSpec→YAML
        "STACKY_PIPELINE_PROFILER_ENABLED",  # Plan 247 — perfilador de pipelines
        "STACKY_PIPELINE_AUDIT_ENABLED",     # Plan 248 — auditoria de pipelines
        "STACKY_PIPELINE_NL_EDIT_ENABLED",   # Plan 250 — edicion quirurgica (analiza)
        "STACKY_PIPELINE_NL_EDIT_COMMIT_ENABLED",  # Plan 250 — commit al repo REAL (OFF)
        "STACKY_PIPELINE_ENV_MATRIX_ENABLED",  # Plan 251 — matriz de entornos (read-only)
        "STACKY_PIPELINE_HANDOFF_BUNDLE_ENABLED",  # Plan 252 — paquete de entrega
    ),
    "migrador_ado_gitlab": (
        # NOTA: el master STACKY_MIGRATOR_ADO_TO_GITLAB_ENABLED (feature opt-in) → "capacidades_optin".
        "STACKY_MIGRATOR_EPIC_POLICY",             # Plan 74 — política de épicas (auto|premium_native|free_degrade)
    ),
    "gitlab_deep_links": (
        # NOTA: el master STACKY_GITLAB_DEEP_LINKS_ENABLED (feature opt-in) → "capacidades_optin".
        # Plan 282 — paridad GitLab: las 7 del eje "GitLab deja de ser un ADO
        # disfrazado" viven acá, en un bloque contiguo (la frontera de merge más
        # caliente del árbol: 280/281/282 escriben en este archivo a la vez).
        "STACKY_COMMENT_PUBLISH_ROUTED_ENABLED",       # F1 — el comentario llega al issue
        "STACKY_GITLAB_PROVIDER_FACTORY_ONLY_ENABLED", # F2 — un solo constructor, con ca_bundle
        "STACKY_GITLAB_ASSIGNEE_STRICT_ENABLED",       # F3 — deja de borrar al asignado
        "STACKY_TRACKER_LABELS_GLOBAL_ENABLED",        # F4 — rótulos por tracker
        "STACKY_TRACKER_URLS_ROUTED_ENABLED",          # F5 — links que no van al tracker ajeno
        "STACKY_TICKET_STATE_FILTER_ROUTED_ENABLED",   # F6 — filtro y colores por tracker
        "STACKY_ADO_ONLY_TABS_GATED_ENABLED",          # F7 — tabs ADO-only deshabilitados
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
        "STACKY_DEVOPS_PIPELINE_MONITOR_ENABLED",  # Plan 103 — monitor vivo del ultimo pipeline
        "STACKY_DEVOPS_ONE_CLICK_PUBLISH_ENABLED",  # Plan 102 — publicar en un paso
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
        "STACKY_DEVOPS_LOCAL_DOCTOR_ENABLED",  # Plan 127 — doctor local DevOps (IA local)
        "STACKY_DEVOPS_BUILD_WORKSHOP_ENABLED",  # Plan 201 — Taller de Compilación (.sln + build Release)
        "STACKY_DEVOPS_SOLUTION_PUBLISHER_ENABLED",  # Plan 215 — Publicador de Soluciones
        "STACKY_DEV_BUILD_VERIFY_ENABLED",  # Plan 210 — gate de build determinista del Developer
        "STACKY_DEV_POST_BUILD_INSPECT_ENABLED",  # Plan 211 — inspector post-build
        "STACKY_DEV_PORT_RESIDUE_SCAN_ENABLED",  # Plan 211 — barrido de residuos de port
        "STACKY_PR_REVIEWER_ENABLED",       # Plan 110 — revisor de PRs
        "STACKY_PR_REVIEW_HAIKU_MODEL",     # Plan 110 — modelo Haiku para la revisión
        "STACKY_PR_REVIEW_DIFF_MAX_CHARS",  # Plan 110 — tope del diff (privacidad, camino Haiku)
        "STACKY_PR_REVIEW_LOCAL_DIFF_MAX_CHARS",  # Plan 110 v2.1 — tope del diff del camino solo-local (velocidad, 0=sin límite)
        "STACKY_PR_REVIEW_TIMEOUT_SEC",     # Plan 110 — timeout de la revisión Haiku
        "STACKY_DEVOPS_UI_V2_ENABLED",  # Plan 119 — rediseño minimalista del shell DevOps
        "STACKY_CONFIG_TRANSFER_DEVOPS_ENABLED",  # Plan 190 — equipaje DevOps en export/import
        "STACKY_DEVOPS_PIPELINE_LINT_ENABLED",  # Plan 186 — lint determinista de pipelines
        "STACKY_DEVOPS_FAILURE_EVIDENCE_ENABLED",  # Plan 188 — evidencia de fallos de despliegue
        "STACKY_DEVOPS_ROLLBACK_READINESS_ENABLED",  # Plan 189 — semáforo de rollback + simulacro
        "STACKY_DEVOPS_ENV_APPLY_LEDGER_ENABLED",  # Plan 198 — bitácora de applies de ambientes
        "STACKY_DEVOPS_COCKPIT_ENABLED",  # Plan 239 — cockpit DevOps (Resumen + nav agrupada)
        "STACKY_PIPELINE_INVENTORY_ENABLED",  # Plan 246 — inventario vivo de pipelines
        # Costura OLA 1 (P0, 2026-07-28)
        "STACKY_DEVOPS_ACTION_CATALOG_ENABLED",  # Plan 267 — catálogo único de acciones DevOps
        "STACKY_DEVOPS_ACTION_NL_ENABLED",  # Plan 267 — pedir la acción en castellano
        "STACKY_DEVOPS_AGENT_ACTION_RUN_ENABLED",  # Plan 267 — el asistente EJECUTA (nace OFF)
        "STACKY_PIPELINE_ENV_DECLARE_ENABLED",       # Plan 260 — declarar nombres (OFF, escribe)
        "STACKY_PIPELINE_TRIGGER_ENV_GATE_ENABLED",  # Plan 260 — bloquear disparo con faltantes
        "STACKY_PIPELINE_SECRET_COMMIT_GATE_ENABLED",  # Plan 260 — bloquear commit con secreto
        "STACKY_PIPELINE_COPILOT_ENABLED",  # Plan 279 — copiloto de pipelines (lee, planea, explica)
        "STACKY_PIPELINE_COPILOT_COMMIT_ENABLED",  # Plan 279 — crear la pipeline en el repo REAL (nace OFF)
    ),
    "flujo_funcional": (
        "STACKY_TASK_GATE_ENABLED", "STACKY_TASK_GATE_BLOCKING",
        "STACKY_DETERMINISTIC_TASK_STATES_ENABLED",
        "STACKY_ADO_STATE_MATRIX_ENABLED",  # Plan 208 — matriz (tipo de ticket x agente)
        "STACKY_STATE_CONFIG_CENTRALIZED_ENABLED",  # Plan 216 — estados en el perfil
        "STACKY_FINAL_STATE_ROLE_FALLBACK_ENABLED",  # Plan 271 — fallback a nivel rol
        "STACKY_FINAL_STATE_WRITER_ROUTED_ENABLED",  # Plan 271 — escritor ruteado
        "STACKY_FINAL_STATE_PUBLISH_GATE_PRECISE_ENABLED",  # Plan 271 — gate preciso
        "STACKY_FINAL_STATE_REASON_VISIBLE_ENABLED",  # Plan 271 — razón visible
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
        "STACKY_ADO_SYNC_ON_COMPLETION_ENABLED",  # Plan 208 — auto-sync al completar un agente
        # Plan 253 — barrera de escrituras de arranque + reintento por unidad de trabajo
        "STACKY_STARTUP_WRITE_BARRIER_WAIT_S", "STACKY_SQLITE_LOCK_RETRY_ENABLED",
        # Plan 254 — fin del falso ROJO: guard anti-degradacion, taxonomia de
        # desenlaces y drenaje del stream medido.
        "STACKY_TICKET_STATUS_NO_DOWNGRADE_ENABLED",
        "STACKY_RUN_OUTCOME_TAXONOMY_ENABLED",
        "STACKY_CLI_STREAM_DRAIN_TIMEOUT_S",
        # Plan 280 — el desenlace mira el trabajo entregado (cablea el mapa del 254).
        "STACKY_OUTCOME_WORK_EVIDENCE_ENABLED",
        # Plan 256 — cuarentena de intake persistente, copia del original y
        # descarte HITL (la superficie ya vivia aca desde el plan 149).
        "STACKY_INTAKE_QUARANTINE_SIDECAR_ENABLED",
        "STACKY_INTAKE_PRESERVE_ORIGINAL_ENABLED",
        "STACKY_INTAKE_QUARANTINE_DISCARD_ENABLED",
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
        "STACKY_TELEMETRY_HARVEST_ENABLED",           # Plan 199
        "STACKY_TELEMETRY_HARVEST_AUTOSCAN_ENABLED",  # Plan 199
        "STACKY_TELEMETRY_HARVEST_ATTRIBUTED_ONLY",   # Plan 199
        "STACKY_TELEMETRY_HARVEST_LOOKBACK_DAYS",     # Plan 199
        "STACKY_TELEMETRY_HARVEST_ROOTS_JSON",        # Plan 199
        # Plan 253 — purga por retencion del historial de actividad
        "STACKY_SYSLOG_AUTO_PURGE_ENABLED", "STACKY_SYSLOG_PURGE_INTERVAL_S",
        "STACKY_SYSLOG_RETENTION_DAYS",
        # Plan 254 — lo que solo se VE: badge de causa y panel de reconciliacion.
        "STACKY_UI_OUTCOME_REASON_BADGE_ENABLED", "STACKY_RUN_RECONCILIATION_ENABLED",
        # Plan 255 — cero fallas mudas: contador de silencio, nivel por clase y canario.
        "STACKY_SILENT_FAILURE_COUNTER_ENABLED",
        "STACKY_STRUCTURAL_ERRORS_TO_ERROR_LEVEL",
        "STACKY_DORMANT_CANARY_ENABLED",
        # Plan 257 — observabilidad antirruido: agrupado de repetidos, volcado
        # del conteo, rotacion por tamano y retencion efectiva de los archivos.
        # (La tarjeta de firmas ruidosas va en "interfaz_ui", no aca.)
        "STACKY_LOG_THROTTLE_ENABLED", "STACKY_LOG_THROTTLE_WINDOW_S",
        "STACKY_LOG_THROTTLE_MAX_SIGNATURES", "STACKY_LOG_THROTTLE_FLUSH_S",
        "STACKY_LOG_SIZE_ROTATION_ENABLED", "STACKY_LOG_MAX_BYTES",
        "STACKY_LOG_MAX_PARTS_PER_DAY", "STACKY_LOG_RETENTION_DAYS",
        # Plan 258 — telemetria veraz de los archivos de registro: esquema,
        # procedencia, huerfanos de CI, limpieza asistida y estanqueidad.
        "STACKY_LEDGER_STRICT_SCHEMA_ENABLED", "STACKY_LEDGER_LEGACY_INFERENCE_ENABLED",
        "STACKY_LEDGER_TEST_MARKERS", "STACKY_LEDGER_ORPHAN_REPORT_ENABLED",
        "STACKY_LEDGER_PURGE_ENABLED", "STACKY_HARNESS_AIRTIGHT_GUARD_ENABLED",
        "STACKY_COST_CENTER_ENABLED", "STACKY_COST_CODEBURN_IMPORT_ENABLED",
        "STACKY_COST_CODEBURN_IMPORT_PATH",  # Plan 142
        "STACKY_OPS_TELEMETRY_ENABLED",   # Plan 171 — telemetría operativa (salud/tendencias)
        "STACKY_OPS_BASELINE_ENABLED",    # Plan 171 — baselines y regresiones deterministas
        "STACKY_OPS_TRACE_ENABLED",       # Plan 171 — traza estructurada por corrida
        # Plan 242 — Centro de Costos telemétrico. Van acá (y no en
        # "observabilidad" a secas) por consistencia con sus hermanas de costo
        # del 142/158, que ya viven en esta categoría.
        "STACKY_COST_STATS_ENABLED",      # Plan 242 — percentiles, outliers, cache, rework
        "STACKY_COST_SCORING_ENABLED",    # Plan 242 — nota A–E explicable por corrida
        "STACKY_COST_CLAUDE_CLI_TELEMETRY_PARITY_ENABLED",  # Plan 158
        "STACKY_COST_CLAUDE_MODEL_BACKFILL_ENABLED",  # Plan 158
        "STACKY_TYPED_ERROR_ENVELOPE_ENABLED",  # Plan 149 F0 — envelope de errores tipado
        "STACKY_PLANS_BOARD_ENABLED",       # Plan 128 — tablero de evolución de planes
        "STACKY_PLANS_PIPELINE_ACTIONS_ENABLED",  # Plan 196 — acciones HITL del pipeline
        "STACKY_EVOLUTION_CENTER_ENABLED",              # Plan 167 — Centro de Evolución (panel)
        "STACKY_EVOLUTION_PLANS_TRIAGE_ENABLED",        # Plan 237 — triage de planes en el Centro de Evolución
        "STACKY_EVOLUTION_CYCLE_ENABLED",               # Plan 167 — ciclo MAPE on-demand
        "STACKY_EVOLUTION_AUTO_APPLY_KNOWLEDGE_ENABLED",# Plan 167 — human-on-the-loop lecciones (OFF)
        "STACKY_EVOLUTION_CYCLE_TOKEN_BUDGET",          # Plan 167 — presupuesto tokens/ciclo
        "STACKY_EVAL_HARNESS_ENABLED",     # Plan 168 — arnés de fitness (golden tasks)
        "STACKY_EVAL_JUDGE_ENABLED",       # Plan 168 — juez LLM local con rubricas
        "STACKY_EVAL_RUN_TOKEN_BUDGET",    # Plan 168 — presupuesto tokens por corrida
        "STACKY_EVOLUTION_OPTIMIZER_ENABLED",         # Plan 169 — optimizador evolutivo
        "STACKY_EVOLUTION_OPTIMIZER_GENERATOR",       # Plan 169 — generador (auto/local/runtime)
        "STACKY_EVOLUTION_OPTIMIZER_VARIANTS",        # Plan 169 — K variantes por corrida
        "STACKY_EVOLUTION_OPTIMIZER_TOKEN_BUDGET",    # Plan 169 — presupuesto tokens por corrida
        "STACKY_EVOLUTION_OPTIMIZER_MIN_MARGIN_PCT",  # Plan 169 — margen minimo (centesimas)
        "STACKY_KNOWLEDGE_FLYWHEEL_ENABLED",    # Plan 170 — flywheel de conocimiento
        "STACKY_KNOWLEDGE_INJECTION_ENABLED",   # Plan 170 — inyeccion de lecciones
        "STACKY_KNOWLEDGE_INJECT_TOP_N",        # Plan 170 — top-N por corrida
        "STACKY_KNOWLEDGE_INJECT_MAX_CHARS",    # Plan 170 — tope de caracteres
        "STACKY_KNOWLEDGE_MAX_LESSONS",         # Plan 170 — cap sugerente del corpus
        # Costura OLA 1 (P0, 2026-07-28)
        "STACKY_RUN_VERDICT_ENABLED",              # Plan 269 F0 — veredicto de 3 niveles
        "STACKY_RUN_EVIDENCE_COLLECTORS_ENABLED",  # Plan 269 F1 — recolectores de evidencia
        "STACKY_UI_RUN_VERDICT_BADGE_ENABLED",     # Plan 269 F2/F3/F4 — veredicto en la lista
        "STACKY_INCIDENT_INBOX_VERDICT_ENABLED",   # Plan 269 F5 — veredicto en la bandeja
        "STACKY_RUN_RECONCILIATION_HITL_ENABLED",  # Plan 269 F6 — correccion manual (HITL)
        "STACKY_PLANS_ESTADO_FALLBACK_ENABLED",      # Plan 263 — ningun plan sin estado
        "STACKY_PLANS_NORMALIZE_PREVIEW_ENABLED",    # Plan 263 — vista previa (solo lectura)
        "STACKY_PLANS_NORMALIZE_APPLY_ENABLED",      # Plan 263 — escritura HITL en los .md
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
        # Plan 253 — concurrencia y mantenimiento de la base de runtime
        "STACKY_SQLITE_WAL_ENABLED", "STACKY_SQLITE_BUSY_TIMEOUT_MS",
        "STACKY_SQLITE_SYNCHRONOUS_NORMAL_ENABLED", "STACKY_DB_COMPACT_ENABLED",
    ),
    "avanzado": (
        "STACKY_CLI_EGRESS_ENABLED", "STACKY_SPECULATIVE_ENABLED", "STACKY_SPECULATIVE_MODE",
        # NOTA: el master STACKY_CODEBASE_MEMORY_MCP_ENABLED (feature opt-in) → "capacidades_optin".
        "STACKY_CODEBASE_MEMORY_MCP_PROJECTS", "STACKY_CODEBASE_MEMORY_MCP_BINARY_PATH",  # Plan 80
        "LOCAL_LLM_ENABLED", "LOCAL_LLM_ENDPOINT", "LOCAL_LLM_MODEL", "LOCAL_LLM_TIMEOUT_SEC",  # Plan 106
        "STACKY_LOCAL_INSIGHTS_ENABLED", "STACKY_LOCAL_INSIGHTS_SWEEP_SEC",  # Plan 117
        "STACKY_LOCAL_INSIGHTS_MAX_PER_CYCLE", "STACKY_LOCAL_INSIGHTS_LOOKBACK_DAYS",  # Plan 117
        "STACKY_LOCAL_INSIGHTS_DIGEST_NARRATIVE_ENABLED",  # Plan 117
        "STACKY_EGRESS_SENTINEL_ENABLED", "STACKY_EGRESS_SENTINEL_MAX_PER_CYCLE",  # Plan 121
        "STACKY_EGRESS_SENTINEL_LOOKBACK_DAYS", "STACKY_EGRESS_SENTINEL_MAX_CHARS",  # Plan 121
        "STACKY_EXEC_ERROR_ANALYSIS_ENABLED",  # Plan 127 — análisis de errores con IA local
        "STACKY_PALETTE_DEEP_SEARCH_ENABLED",  # Plan 129 — búsqueda profunda multi-fuente (paleta)
    ),
    "capacidades_optin": (
        # Activación operador 2026-07-10 — features que el operador invoca a demanda
        # (botón/tab/endpoint) y NO disparan trabajo ni costo dentro de otro flujo.
        # Todas promovidas a default ON; agrupadas aquí para que se vean distintas.
        "STACKY_DOCS_GRAPH_ENABLED",            # Plan 109 — grafo documental read-only (tab Docs)
        "STACKY_DOCS_STALENESS_ENABLED",        # Plan 114 — chip staleness doc↔código
        "STACKY_DOCS_DOCUMENTER_ENABLED",       # Plan 113 — botón "Lanzar Documentador"
        "STACKY_DOCS_DOCUMENTER_V2_ENABLED",    # Plan 137 — evidencia real + citas + historial
        # Plan 284 — el Documentador deja de mezclar y de adivinar
        "STACKY_DOCS_TAXONOMY_ENABLED",         # Plan 284 — clasifica plan vs proyecto
        "STACKY_DOCS_OPERATOR_NOTE_ENABLED",    # Plan 284 — nota libre del operador
        "STACKY_DOCS_CITATION_GATE_ENABLED",    # Plan 284 — el gate de citas rechaza
        "STACKY_DOCS_TICKET_MINING_ENABLED",    # Plan 284 — triage determinista de tickets
        "STACKY_DOCS_PIPELINE_STAGES_ENABLED",  # Plan 284 — pipeline de 5 etapas
        "STACKY_DOCS_PIPELINE_AUTOAPPLY",       # Plan 284 — escribe sin confirmación (OFF)
        "STACKY_DOCS_RADIOGRAPHY_ENABLED",      # Plan 284 — cobertura sobre el grafo
        # Plan 285 — corpus vivo, rigor por afirmación y descarte trazable.
        # OJO: la categorización NO se deriva del prefijo. Toda flag nueva se
        # declara acá a mano o test_every_registry_flag_is_categorized se pone rojo.
        "STACKY_DOCS_CORPUS_AUTOINDEX_ENABLED",       # Plan 285 — indexa antes de documentar
        "STACKY_DOCS_CORPUS_RETRIEVAL_ENABLED",       # Plan 285 — el corpus se LEE
        "STACKY_DOCS_CORPUS_ORPHANS_ENABLED",         # Plan 285 — lista los huérfanos
        "STACKY_DOCS_CORPUS_PURGE_ENABLED",           # Plan 285 — purga (OFF, destructiva)
        "STACKY_DOCS_RIGOR_PER_CLAIM_ENABLED",        # Plan 285 — rigor por afirmación
        "STACKY_DOCS_TICKET_TRIAGE_VISIBLE_ENABLED",  # Plan 285 — descarte trazable
        "STACKY_DOCS_TREE_GROUP_BY_CLASS_ENABLED",    # Plan 285 — el árbol deja de mezclar
        "STACKY_DOCS_RAG_HYBRID_ENABLED",       # Plan 112 — retrieval híbrido docs
        "STACKY_CAPS_ADVISOR_ENABLED",          # I3.3 — GET /metrics/caps-advisor (solo lectura)
        "STACKY_MIGRATOR_ADO_TO_GITLAB_ENABLED",# Plan 74 — migrador ADO→GitLab (dry-run + HITL)
        "STACKY_EPIC_DECOMPOSITION_ENABLED",    # Plan 59 — previsualizar/crear hijos de la épica
        "STACKY_EPIC_PORTFOLIO_ENABLED",        # Plan 55 — N épicas desde un brief (beta)
        "STACKY_CODEBASE_MEMORY_MCP_ENABLED",   # Plan 76 — MCP externo opt-in (estado + guía)
        "STACKY_GITLAB_DEEP_LINKS_ENABLED",     # Plan 75 — deep links GitLab clickeables
        "STACKY_ADO_PREWARM_ENABLED",           # I0.3 — prewarm caché ADO (inerte sin TTL>0)
        "STACKY_DB_COMPARE_ENABLED",            # Plan 122 — comparador de BD entre ambientes (master, default OFF)
        "STACKY_CODE_INTEGRITY_ENABLED",        # Plan 130 — gate determinista sintaxis+imports (card Diagnóstico)
        "STACKY_INCIDENT_RESOLVER_ENABLED",     # Plan 131 — botón "Resolver incidencia" (default ON, promovida 08df035b)
        "STACKY_INCIDENT_CONSOLE_ENABLED",          # Plan 200 R1 — consola por incidencia
        "STACKY_SQL_DEPLOY_DETECT_ENABLED",         # Plan 200 R2 — marcado de despliegue SQL
        "STACKY_SQL_EXEC_LEDGER_ENABLED",           # Plan 200 R4 — bitácora append-only
        "STACKY_SQL_EXEC_ENABLED",                  # Plan 200 R3 — ejecución SQL (default OFF)
        "STACKY_INCIDENT_TICKET_PERSIST_ENABLED",  # Plan 166 F1 — espejo local de la Issue
        "STACKY_INCIDENT_VISION_OCR_ENABLED",      # Plan 166 F2 — OCR de capturas
        "STACKY_INCIDENT_VISION_ENDPOINT",         # Plan 166 F2 — endpoint de visión
        "STACKY_INCIDENT_VISION_MODEL",            # Plan 166 F2 — modelo de visión
        "STACKY_INCIDENT_AUTO_PUBLISH_ENABLED",    # Plan 166 F3 — creación directa/lote
        "STACKY_INCIDENT_DEV_RESOLVER_ENABLED",    # Plan 166 F4/F5 — Dev Resolutor
        "STACKY_INCIDENT_DEV_PR_ENABLED",          # Plan 177 — auto-PR del Dev Resolutor
        "STACKY_NOTIFICATION_CENTER_ENABLED",      # Plan 152 — centro de actividad (campana + feed, default ON)
        # Plan 202 — La Fragua Nocturna: master opt-in (default OFF) + su techo de
        # gasto. Van juntas acá porque son la MISMA capacidad opt-in; el techo no
        # tiene sentido sin el master (y lo declara con `requires`).
        "STACKY_NIGHT_FOUNDRY_ENABLED",
        "STACKY_NIGHT_FOUNDRY_TOKEN_BUDGET",
        # Costura OLA 1 (P0, 2026-07-28)
        "STACKY_DOCS_GRAPH_EXPLORER_ENABLED",   # Plan 268 — explorador read-only del grafo de docs
        # Plan 283 — calendario de reuniones, minutas y pendientes accionables.
        # Capacidad opt-in que el operador usa a demanda desde su propio tab:
        # no dispara trabajo ni costo dentro de otro flujo (D7: cero daemons).
        "STACKY_MEETINGS_ENABLED",              # Plan 283 — master del modulo de reuniones
        "STACKY_MEETINGS_GRAPH_ENABLED",        # Plan 283 — conector de calendario, solo lectura
        "STACKY_MEETINGS_PUBLISH_ENABLED",      # Plan 283 — publicar un pendiente al tracker (OFF)
        "STACKY_MEETINGS_GRAPH_TENANT",         # Plan 283 — organizacion de Microsoft
        "STACKY_MEETINGS_GRAPH_CLIENT_ID",      # Plan 283 — identificador de la aplicacion
    ),
    "comparador_bd": (
        "STACKY_DB_COMPARE_CONNECT_TIMEOUT_SEC",  # Plan 122
        "STACKY_DB_COMPARE_DATA_DIFF_ENABLED",    # Plan 126
        "STACKY_DB_COMPARE_DATA_MAX_ROWS",        # Plan 126
        "STACKY_DB_COMPARE_CONFIG_IN_PLACE_ENABLED",   # Plan 157
        "STACKY_DB_COMPARE_WEBCONFIG_IMPORT_ENABLED",  # Plan 157
        "STACKY_DB_COMPARE_MIGRATION_PANEL_ENABLED",   # Plan 157
        "STACKY_DB_COMPARE_DEMO_ENABLED",         # Plan 183 — sandbox de demostración
        "STACKY_DB_COMPARE_SNAPSHOT_V2_ENABLED",  # Plan 179 — fidelidad snapshot v2 (tipos exactos)
        "STACKY_DB_COMPARE_DATA_MERGE_ENABLED",   # Plan 182 — scripts de datos v2 (MERGE idempotente)
        "STACKY_DB_COMPARE_MASKING_ENABLED",      # Plan 181 — masking de secretos en el data-diff (presentación)
        "STACKY_DB_COMPARE_SUMMARY_SHAPE_ENABLED",  # Plan 266 — forma garantizada del summary (normalización solo-lectura)
        "STACKY_DB_COMPARE_RADAR_ENABLED",        # Plan 178 — radar de ambientes (matriz/baseline/tendencia/avisos)
        "STACKY_DB_COMPARE_WATCH_INTERVAL_MIN",   # Plan 178 — intervalo del vigía de drift
        "STACKY_DB_COMPARE_WATCH_MAX_RUNS_PER_DAY",  # Plan 178 — presupuesto diario del vigía
        "STACKY_DB_COMPARE_REPO_BRIDGE_ENABLED",  # Plan 180 — puente diff→repo (índice read-only de scripts ticketeados)
        "STACKY_DB_COMPARE_REPO_BRIDGE_GLOBS",    # Plan 180 — globs de scripts del repo (CSV)
        "STACKY_DB_COMPARE_REPO_BRIDGE_MAX_FILES",  # Plan 180 — cap de archivos escaneados por refresh
        "STACKY_MODEL_PROBE_ENABLED",  # Plan 212 F6 — probe vivo del CLI
        "STACKY_RUNTIME_CAPABILITIES_ENABLED",      # Plan 264
        "STACKY_CODEX_EFFORT_PARITY_ENABLED",       # Plan 264
        "STACKY_RUN_SELECTION_PREFS_ENABLED",       # Plan 264
        "STACKY_MODEL_PICKER_EVERYWHERE_ENABLED",   # Plan 264
        "STACKY_DB_COMPARE_TRIAGE_ENABLED",  # Plan 176
        "STACKY_DB_COMPARE_GATES_ENABLED",  # Plan 176
        "STACKY_DB_COMPARE_TABLE_PREFS_ENABLED",  # Plan 176
        "STACKY_DB_COMPARE_DIFF_UX_V2_ENABLED",  # Plan 176
    ),
    "interfaz_ui": (
        "STACKY_UI_SHORTCUTS_ENABLED",  # Plan 172 — registro de atajos + overlay ?
        "STACKY_MODEL_PICKER_IN_BOARD_ENABLED",  # Plan 212 — selector de modelo/effort en el tablero
        "STACKY_UI_SAVED_VIEWS_ENABLED",  # Plan 173
        "STACKY_UI_VIRTUALIZATION_ENABLED",  # Plan 174
        "STACKY_UI_PREFETCH_ENABLED",  # Plan 174
        "STACKY_UI_INSTANT_NAV_ENABLED",  # Plan 174
        "STACKY_UI_PEEK_ENABLED",  # Plan 175
        "STACKY_UI_CONTEXT_MENU_ENABLED",  # Plan 175
        "STACKY_UI_SHELL_V2_ENABLED",  # Plan 139 — shell v2 (sidebar agrupada + TopBar + iconografía)
        "STACKY_COPY_EXPORT_ENABLED",  # Plan 194 — portapapeles universal ("Copiar como…")
        "STACKY_UNDO_UNIVERSAL_ENABLED",  # Plan 185 — undo universal (acciones optimistas + gracia)
        "STACKY_BULK_ACTIONS_ENABLED",  # Plan 187 — selección múltiple y acciones en lote
        "STACKY_CONNECTION_RESILIENCE_ENABLED",  # Plan 192 — resiliencia de conexión (banner + re-hidratación)
        "STACKY_INCIDENT_INBOX_ENABLED",  # Plan 238 — bandeja de incidencias abiertas
        "STACKY_INCIDENT_INBOX_ACTIONS_ENABLED",  # Acciones (cerrar / resolver+PR) desde la bandeja
        "STACKY_UI_LOG_NOISE_CARD_ENABLED",  # Plan 257 — tarjeta de firmas de log mas repetidas
        # Costura OLA 1 (P0, 2026-07-28) — el plan 270 la ubica en la categoría de
        # STACKY_INCIDENT_INBOX_ACTIONS_ENABLED (su vecino), NO en paridad_proveedores.
        "STACKY_INCIDENT_DIVERGENCE_BADGE_ENABLED",  # Plan 270 F5 — marca "Sin sincronizar" en la bandeja
        "STACKY_CONSOLE_FULLSCREEN_ENABLED",    # Plan 265 — consola en pantalla completa
        "STACKY_CONSOLE_RICH_RENDER_ENABLED",   # Plan 265
        "STACKY_CONSOLE_REPO_PANEL_ENABLED",    # Plan 265
        "STACKY_CONSOLE_AUDIT_LOG_ENABLED",     # Plan 265
        "STACKY_TICKET_FULLVIEW_ENABLED",       # Plan 287 — ficha del ticket a pantalla completa
    ),
    "paridad_proveedores": (
        "STACKY_PROVIDER_PARITY_ENABLED",             # Plan 218 F2/F8 — registro de capacidades + panel
        "STACKY_TRACKER_TARGET_PER_PROJECT_ENABLED",  # Plan 218 F4 — destino de tracker por proyecto
        "STACKY_CANONICAL_VOCABULARY_ENABLED",        # Plan 218 F5 — alias canónicos aditivos
        "STACKY_CAPABILITY_DEGRADATION_ENABLED",      # Plan 218 F6 — 200 available:false en vez de 500 mudo
        "STACKY_GITLAB_SEMANTIC_RULES_ENABLED",       # Plan 249 — reglas GL000..GL011 de GitLab CI
        # Costura OLA 1 (P0, 2026-07-28)
        "STACKY_PROJECT_GITLAB_ONBOARDING_ENABLED",  # Plan 259 F1/F2/F5 — alta de proyecto GitLab
        "STACKY_SETUP_GUIDE_ENABLED",                # Plan 259 F4/F6 — botón INFO + guía
        "STACKY_SETUP_GUIDE_VERIFY_ENABLED",         # Plan 259 F4/F6 — "Verificar ahora"
        "STACKY_TRACKER_STATE_WRITE_ROUTING_ENABLED",  # Plan 270 F1/F2 — enrutar el estado al tracker real
        "STACKY_TICKET_STATE_WRITEBACK_ENABLED",       # Plan 270 F4 — re-leer y refrescar la copia local
        # Plan 276 — GitLab self-hosted de punta a punta (TLS + sync + veredicto)
        "STACKY_GITLAB_TLS_ADAPTER_ENABLED",     # Plan 276 F1/F2 — contexto OpenSSL genuino por conexión
        "STACKY_TRACKER_PROBE_STRICT_ENABLED",   # Plan 276 F4 — 4 sub-veredictos en vez de un nombre
        "STACKY_GITLAB_SYNC_ENABLED",            # Plan 276 F5 — sync GitLab → BD de Stacky
        # Plan 277 — Jerarquía de GitLab con un solo contrato de tipo y padre
        "STACKY_GITLAB_HIERARCHY_CONTRACT_ENABLED",  # Plan 277 F1/F2 — un solo motor de type::/epic::
        "STACKY_GITLAB_HIERARCHY_LOCAL_CLASSIFY_ENABLED",  # Plan 277 F4 — clasificacion local en la BD de Stacky
        "STACKY_GITLAB_SYNC_PARENTS_ENABLED",  # Plan 277 F6 — traer los padres ausentes del listado de abiertos
        "STACKY_GITLAB_HIERARCHY_LABEL_WRITE_ENABLED",  # Plan 277 F5 — publicar etiquetas EN el GitLab del operador (OFF)
        # Plan 281 — El ruteo por tracker deja de mentir
        "STACKY_TRACKER_ROUTING_STRICT_ENABLED",  # Plan 281 F3/F4/F7 — "no se" deja de significar "es ADO"
        # Plan 287 — la ficha lee del puerto, igual para los dos trackers
        "STACKY_TICKET_HISTORY_API_ENABLED",        # Plan 287 F1 — historial por fetch_item_updates
        "STACKY_TRACKER_CAPABILITIES_API_ENABLED",  # Plan 287 F2 — la matriz de capacidades, publicada
        # Plan 289 — los comentarios del issue llegan al contexto del agente
        "STACKY_TRACKER_CONTEXT_ENABLED",           # Plan 289 F6 — dispatcher de contexto por tracker
    ),
    # "otros" intencionalmente vacío: es el fallback de categorize().
}

# NOTA: toda flag nueva debe agregarse también a _CATEGORY_KEYS (arriba) o el test
# test_every_registry_flag_is_categorized rompe CI a propósito (Plan 63).
FLAG_REGISTRY: tuple[FlagSpec, ...] = (
    # -- Plan 274 - Eficiencia de navegacion del agente QA UAT ---------------
    # Las 6 nacen ON. Ninguna cae en (A) quemar tokens en reposo — no hay un solo
    # LLM en todo el plan — ni en (B) escribir en un sistema real del operador.
    FlagSpec(
        key="STACKY_QA_UAT_SCREENSHOT_BUDGET_ENABLED",
        type="bool",
        label="Techo de capturas por escenario en el QA UAT",
        description=(
            "Plan 274 F2 — Pone un techo de 25 capturas por escenario y unifica el "
            "manejo de errores al sacarlas, conectando screenshot_budget.py, que "
            "estaba escrito y testeado pero sin usar. Solo decide si se saca o no "
            "un PNG en el directorio de evidencia del propio tool. Apagarla emite "
            "el bloque sin limites (comportamiento previo al plan)."
        ),
        group="global",
        env_only=False,
        # Curada en _CURATED_DEFAULTS_ON (test_default_known_only_for_curated).
        default=True,
    ),
    FlagSpec(
        key="STACKY_QA_UAT_STATE_WAITS_ENABLED",
        type="bool",
        label="Esperar por estado en vez de dormir un tiempo fijo",
        description=(
            "Plan 274 F1 — El generador de specs espera a que AgendaWeb se aquiete "
            "(waitForAgendaStable) en vez de dormir 800 ms pase lo que pase. Sin LLM "
            "y sin escritura externa. Apagarla hace que el template vuelva a emitir "
            "el sleep historico, sin revertir codigo."
        ),
        group="global",
        env_only=False,
        default=True,
    ),
    FlagSpec(
        key="STACKY_QA_UAT_RESPECT_WORKERS_ENABLED",
        type="bool",
        label="Respetar QA_UAT_WORKERS en vez de ignorarlo",
        description=(
            "Plan 274 F3 — El runner deja de inyectar un numero fijo de workers que "
            "pisaba QA_UAT_WORKERS. ENCENDERLA NO CAMBIA EL COMPORTAMIENTO: el "
            "default de la env var sigue siendo 1 y una guardia fuerza 1 mientras no "
            "haya sesion por worker (AgendaWeb es WebForms con una sola sesion). "
            "Solo elimina una config que mentia."
        ),
        group="global",
        env_only=False,
        default=True,
    ),
    FlagSpec(
        key="STACKY_QA_UAT_DEEPLINK_PROBE_ENABLED",
        type="bool",
        label="Probar el deep link antes de gastar una corrida en el",
        description=(
            "Plan 274 F4 — Antes de usar un deep link, un GET HTTP de SOLO LECTURA "
            "contra la propia AgendaWeb verifica que no redirija a login. No corre en "
            "reposo: solo cuando el pipeline ya decidio usar un deeplink. Falla "
            "ABIERTO: si el probe no puede correr, el flujo sigue como antes."
        ),
        group="global",
        env_only=False,
        default=True,
    ),
    FlagSpec(
        key="STACKY_QA_UAT_DATA_CACHE_ENABLED",
        type="bool",
        label="Reusar el dato de test ya resuelto por SQL",
        description=(
            "Plan 274 F6 — Cachea en disco local, por campo y con TTL de 8 h, el "
            "resultado de un SELECT ya ejecutado, para no repetirlo en cada corrida. "
            "REDUCE la carga sobre la BD del operador y no escribe en ella. No se "
            "cachean errores ni resultados vacios, y QA_UAT_FORCE_RUN lo saltea."
        ),
        group="global",
        env_only=False,
        default=True,
    ),
    FlagSpec(
        key="STACKY_QA_UAT_STAGE_DEADLINE_ENABLED",
        type="bool",
        label="Chequear el presupuesto de 6 minutos en mas etapas",
        description=(
            "Plan 274 F7 — El presupuesto maximo de la corrida se consulta en 8 "
            "etapas en vez de 2, para cortar antes de EMPEZAR una etapa pesada si ya "
            "no hay tiempo. Cortar por deadline YA es el comportamiento actual: esto "
            "solo lo extiende."
        ),
        group="global",
        env_only=False,
        default=True,
    ),
    # -- Plan 240 F8 / Plan 241 F8 - Agente QA UAT E2E -----------------------
    FlagSpec(
        key="STACKY_QA_UAT_ADO_BRIDGE_ENABLED",
        type="bool",
        label="Leer tickets de QA UAT con las credenciales de Stacky",
        description=(
            "Plan 240 — El pipeline QA UAT lee el work item con el PAT cifrado que ya "
            "usa Stacky, en vez de exigir un ado-config.json con el PAT en texto plano. "
            "Solo lectura. Si falla, cae al CLI legacy."
        ),
        group="global",
        env_only=False,
        # Curada en _CURATED_DEFAULTS_ON (test_default_known_only_for_curated).
        default=True,
    ),
    FlagSpec(
        key="STACKY_QA_UAT_FUNCTIONAL_VERDICT_ENABLED",
        type="bool",
        label="Veredicto funcional por criterios de aceptacion",
        description=(
            "Plan 240 — Extrae los criterios de aceptacion del ticket y exige "
            "verificarlos: un run sin ninguna asercion funcional verificada nunca da "
            "PASS (queda MIXED). Determinista, sin LLM."
        ),
        group="global",
        env_only=False,
        # Curada en _CURATED_DEFAULTS_ON (test_default_known_only_for_curated).
        default=True,
    ),
    FlagSpec(
        key="STACKY_QA_UAT_AUTOSTART_AGENDA_ENABLED",
        type="bool",
        label="Arrancar AgendaWeb local para validar",
        description=(
            "Plan 240 — Si AgendaWeb no responde, el pipeline intenta UN arranque local "
            "con IIS Express y lo apaga al terminar. Requiere IIS Express instalado, el "
            "applicationhost.config del cliente y la solucion compilada. Solo localhost."
        ),
        group="global",
        env_only=False,
        # Promovida a default ON (barrido del operador 2026-07-27): no quema tokens en
        # reposo y no escribe en ningun sistema real — arranca un proceso local en
        # localhost DENTRO de una corrida que el operador ya lanzo, y lo apaga al
        # terminar. El motivo original de su OFF era "prerequisito no garantizado",
        # que el operador invalido explicitamente: lo on-demand degrada sin romper
        # (si falta IIS Express el arranque falla y el pipeline lo dice).
        # Curada en _CURATED_DEFAULTS_ON (test_default_known_only_for_curated).
        default=True,
    ),
    FlagSpec(
        key="STACKY_QA_UAT_STRICT_DISCRIMINATION_ENABLED",
        type="bool",
        label="Exigir aserciones que sepan fallar (control negativo)",
        description=(
            "Plan 241 — Un criterio solo cuenta como verificado si su asercion viene "
            "con un control negativo probado: el valor pre-fix contra el cual la MISMA "
            "asercion da fail. Sin esa prueba el criterio queda not_verifiable y el run "
            "no puede ser PASS. Determinista, sin LLM y sin abrir el navegador."
        ),
        group="global",
        env_only=False,
        # Curada en _CURATED_DEFAULTS_ON: el default laxo ES el bug que el plan mata.
        default=True,
    ),
    FlagSpec(
        key="STACKY_QA_UAT_EPIC_ROLLUP_ENABLED",
        type="bool",
        label="Veredicto de epicas por agregacion de sus hijas",
        description=(
            "Plan 241 — Una epica no tiene pasos de reproduccion propios: en vez de "
            "BLOCKED/missing_technical_analysis, su veredicto se calcula agregando el de "
            "sus tasks hijas. Consulta ADO de SOLO LECTURA."
        ),
        group="global",
        env_only=False,
        # Curada en _CURATED_DEFAULTS_ON (aditivo y solo lectura).
        default=True,
    ),
    # -- Plan 262 F2 - Recuperacion en caliente del QA UAT --------------------
    # Las 8 de VALOR van SIN default=: default_is_known(spec) es literalmente
    # `spec.default is not None` (type-agnostico), asi que hasta un default=0
    # las volveria "conocidas" y pondria rojo test_default_known_only_for_curated.
    # Su default EFECTIVO vive en config.py.
    FlagSpec(
        key="STACKY_QA_UAT_HOT_RECOVERY_ENABLED",
        type="bool",
        label="Recuperar la prueba en caliente ante una ruta invalida",
        description=(
            "Plan 262 — Ante una excepcion durante la corrida, comprueba si la aplicacion "
            "responde y distingue una caida real de una ruta mal construida. Reintenta solo "
            "el caso afectado. Determinista, sin LLM."
        ),
        group="global",
        env_only=False,
        # Default ON: no quema tokens en reposo (cero LLM, INV-6), no escribe en ningun
        # sistema real del operador y no le saca ninguna decision. Con OFF, el
        # comportamiento es el de hoy (INV-8).
        # Curada en _CURATED_DEFAULTS_ON (test_default_known_only_for_curated).
        default=True,
    ),
    FlagSpec(
        key="STACKY_QA_UAT_RECOVERY_MAX_PER_RUN",
        type="int",
        label="Recuperaciones maximas por corrida",
        description=(
            "Plan 262 — Cota global anti-bucle. 0 = modo observacion: se clasifica y se "
            "registra, pero no se recupera nada. El default efectivo (6) vive en config.py."
        ),
        group="global",
        env_only=False,
        min_value=0,
        max_value=50,
    ),
    FlagSpec(
        key="STACKY_QA_UAT_RECOVERY_MAX_PER_CASE",
        type="int",
        label="Recuperaciones maximas por caso",
        description=(
            "Plan 262 — Cuantas veces se puede reintentar UN mismo caso. Alineado con "
            "_MAX_REAUTH_PER_STEP=1 del navegador. El default efectivo (1) vive en config.py."
        ),
        group="global",
        env_only=False,
        min_value=0,
        max_value=10,
    ),
    FlagSpec(
        key="STACKY_QA_UAT_HEALTH_PROBE_TIMEOUT_S",
        type="float",
        label="Espera maxima del chequeo de disponibilidad (segundos)",
        description=(
            "Plan 262 — Timeout de cada consulta HTTP contra la URL base. El default "
            "efectivo (5.0) vive en config.py y es identico al del preflight."
        ),
        group="global",
        env_only=False,
        min_value=1,
        max_value=30,
    ),
    FlagSpec(
        key="STACKY_QA_UAT_HEALTH_PROBE_CONFIRM_S",
        type="float",
        label="Pausa entre las dos muestras de disponibilidad (segundos)",
        description=(
            "Plan 262 F1.5 — Declarar la aplicacion caida exige DOS consultas fallidas "
            "seguidas. 0 = confirmar sin pausa (sigue exigiendo 2 muestras). El default "
            "efectivo (2.0) vive en config.py."
        ),
        group="global",
        env_only=False,
        min_value=0,
        max_value=15,
    ),
    FlagSpec(
        key="STACKY_QA_UAT_ROUTE_ALLOWLIST",
        type="csv",
        label="Rutas permitidas de la aplicacion",
        description=(
            "Plan 262 — Lista separada por comas de pantallas legales (ej "
            "FrmLogin.aspx,FrmBusqueda.aspx). Vacia = lista derivada del codigo, en modo "
            "permisivo. El default efectivo (vacio) vive en config.py."
        ),
        group="global",
        env_only=False,
    ),
    FlagSpec(
        key="STACKY_QA_UAT_SAFE_ROUTE",
        type="str",
        label="Ruta segura a la que volver tras una excepcion",
        description=(
            "Plan 262 — Pantalla a la que se regresa antes de reintentar. Vacia = la URL "
            "base, que siempre existe y siempre es valida. El default efectivo (vacio) "
            "vive en config.py."
        ),
        group="global",
        env_only=False,
    ),
    FlagSpec(
        key="AGENDA_WEB_BASE_URL",
        type="str",
        label="Direccion base de AgendaWeb",
        description=(
            "Plan 262 — La direccion contra la que se valida que la aplicacion responde. "
            "Es el nombre EXACTO que el pipeline ya lee. Su default en config.py es "
            "env-first: si ya la tenias configurada en el entorno, se adopta TU valor."
        ),
        group="global",
        env_only=False,
    ),
    FlagSpec(
        key="QA_NAV_RETRIES",
        type="int",
        label="Reintentos de navegacion por paso",
        description=(
            "Plan 262 F6 — Cota canonica de reintentos al navegar entre pantallas. El "
            "default efectivo (3) vive en config.py y es el vigente hoy; bajarlo a 1 seria "
            "una regresion silenciosa de comportamiento."
        ),
        group="global",
        env_only=False,
        min_value=0,
        max_value=10,
    ),
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
        default=True,  # promovida a default ON (operador 2026-07-17: runs deben ser autosuficientes para perfiles no técnicos; curada en _CURATED_DEFAULTS_ON).
        label="Auto-confiar workspace (claude)",
        description="Si el workspace no está confiado, escribe hasTrustDialogAccepted=true en ~/.claude.json automáticamente. Apagalo si preferís aceptar el diálogo de trust a mano.",
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
    # ── Plan 256 — Intake sin pérdida: ningún artefacto rechazado sin razón ───
    FlagSpec(
        key="STACKY_INTAKE_QUARANTINE_SIDECAR_ENABLED",
        type="bool",
        label="Cuarentena de intake persistente en disco",
        description=(
            "Plan 256 — Si ON, cada artefacto en cuarentena deja un sidecar "
            "<artefacto>.quarantine.json con la causa y la antigüedad, y la cuarentena "
            "sobrevive al reinicio del backend. Nunca modifica el artefacto. "
            "OFF = solo en memoria (comportamiento legacy)."
        ),
        group="global",
        env_only=False,   # SÍ es atributo de Config (ver plan 256 C16)
        default=True,
    ),
    FlagSpec(
        key="STACKY_INTAKE_PRESERVE_ORIGINAL_ENABLED",
        type="bool",
        label="Copia del original antes de reparar un artefacto",
        description=(
            "Plan 256 — Si ON, la reparación automática del intake guarda "
            "<artefacto>.orig con el contenido crudo del agente ANTES de reescribir "
            "el archivo in place, y ABORTA la reparación si no puede escribir la "
            "copia. OFF = camino actual exacto (reescribe sin respaldo)."
        ),
        group="global",
        env_only=False,
        default=True,
    ),
    FlagSpec(
        key="STACKY_INTAKE_QUARANTINE_DISCARD_ENABLED",
        type="bool",
        label="Descartar artefactos en cuarentena desde la UI",
        description=(
            "Plan 256 — Si ON, el operador puede marcar un artefacto en cuarentena "
            "como descartado (con confirmación explícita). NUNCA borra ni modifica "
            "el artefacto: el marcador va al sidecar y el archivo queda intacto en "
            "disco."
        ),
        group="global",
        env_only=False,
        # Promovida a default ON (barrido del operador 2026-07-27): no quema tokens en
        # reposo y NO es destructiva — el artefacto queda intacto en disco (api/diag.py
        # solo escribe un marcador en el sidecar) y la accion exige el interlock de dos
        # pasos de services/confirm_token.py. Habilitar el boton no descarta nada.
        # Curada en _CURATED_DEFAULTS_ON (test_default_known_only_for_curated).
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
        key="STACKY_MODEL_CATALOG_ENABLED",
        type="bool",
        label="Catálogo unificado de modelos/efforts",
        description=(
            "Plan 159 — fuente única backend de modelos/efforts disponibles por "
            "runtime (Claude Code CLI, Codex CLI, GitHub Copilot), consumida por "
            "los 3 selectores del frontend. OFF = cada selector usa su fallback "
            "estático embebido (comportamiento pre-159)."
        ),
        group="global",
        default=True,  # Grupo B — sin costo de tokens, solo UI; promovida ON de alta.
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
    # ── Plan 133 — Contrato de inyección de contexto por agente ───────────────
    FlagSpec(
        key="STACKY_RUN_TICKET_REFRESH_ENABLED",
        type="bool",
        label="Refresh just-in-time del ticket antes del run",
        description=(
            "Plan 133 F1 — Re-sincroniza work_item_type/ado_state/título/"
            "descripción del ticket desde el tracker (ADO) al inicio de "
            "POST /api/agents/run, para que preflight e inyección decidan "
            "sobre datos frescos. Solo tracker ADO; fail-open ante red. "
            "OFF = /run byte-idéntico."
        ),
        group="global",
        default=True,  # Solo agrega una lectura cacheable; no gasta tokens.
    ),
    FlagSpec(
        key="STACKY_BUSINESS_PREFLIGHT_ENABLED",
        type="bool",
        label="Preflight de negocio antes del run",
        description=(
            "Plan 133 F2 — Rechaza con 400 accionable el lanzamiento de un "
            "agente cuyo ticket no cumple los prerequisitos deterministas de "
            "su contrato (p. ej. FunctionalAnalyst sobre una Task sin "
            "bloqueante), ANTES de gastar el run. Fail-open ante red. "
            "OFF = /run byte-idéntico."
        ),
        group="global",
        default=True,  # Ahorra runs quemados; nunca gasta tokens de más.
    ),
    FlagSpec(
        key="STACKY_ADO_BLOCKER_BLOCK_ENABLED",
        type="bool",
        label="Bloque 'ado-blocker' server-side",
        description=(
            "Plan 133 F3 — Si un comentario ADO contiene el marcador "
            "bloqueante, lo marca como bloque de contexto de primera clase "
            "('ado-blocker') en vez de dejar que el agente lo busque entre "
            "hasta 30 comentarios crudos. OFF = ado_context byte-idéntico."
        ),
        group="global",
        default=True,  # Agrega un bloque chico (~10 líneas); evita abortos.
    ),
    FlagSpec(
        key="STACKY_RUN_DIRECTIVE_ENABLED",
        type="bool",
        label="Bloque 'run-directive' server-side",
        description=(
            "Plan 133 F4 — Inyecta la decisión de modo (A/B) calculada por "
            "el backend como bloque de máxima prioridad; el paso de "
            "auto-validación del agente pasa a ser un cross-check. "
            "OFF = enrich_blocks byte-idéntico."
        ),
        group="global",
        default=True,  # Agrega un bloque chico; evita abortos de contrato.
    ),
    FlagSpec(
        key="STACKY_REQUIRED_BLOCKS_ENABLED",
        type="bool",
        label="Contrato declarativo 'stacky_required_blocks'",
        description=(
            "Plan 133 F5 — Valida, post-enriquecimiento y pre-spawn, que los "
            "bloques de contexto que el .agent.md declara obligatorios "
            "(frontmatter stacky_required_blocks) hayan sido producidos. Si "
            "faltan: el run queda failed SIN spawnear el CLI. "
            "OFF = sin validación (comportamiento actual)."
        ),
        group="global",
        default=True,  # Evita spawnear CLI con contexto incompleto (ahorra tokens).
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
        label="Texto del prompt en trazabilidad (C0/C1, privacidad: nace ON)",
        description=(
            "Plan 38 C0/C1 — Si ON, incluye el texto completo del prompt (JSON de "
            "context_blocks) en la metadata. Default ON. Solo activar "
            "en ambientes controlados donde el contenido del prompt no es sensible. "
            "Hoy nace ON: el texto completo del prompt SÍ queda en la metadata de "
            "cada ejecución. Apagala si el contenido de tus prompts es sensible."
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
    # ── Plan 199 — Cosecha histórica de telemetría desde disco ─────────────────
    FlagSpec(
        key="STACKY_TELEMETRY_HARVEST_ENABLED",
        type="bool",
        default=True,
        label="Cosecha histórica de telemetría (desde disco)",
        description=(
            "Plan 199 — Descubre en disco los artefactos de sesión de los CLIs "
            "(rollouts de codex, transcripts de Claude Code) y trae al Centro de "
            "Costos lo que se gastó fuera de Stacky. Read-only: sin las carpetas, "
            "degrada a vacío."
        ),
        group="observabilidad",
    ),
    FlagSpec(
        key="STACKY_TELEMETRY_HARVEST_AUTOSCAN_ENABLED",
        type="bool",
        default=True,
        label="Escanear la telemetría histórica al arrancar",
        description=(
            "Plan 199 — Corre la cosecha en segundo plano al iniciar, sin bloquear "
            "el arranque. Excepción #3 citada: depende de carpetas de disco que una "
            "instalación default puede no tener; si faltan, no hace nada y lo dice."
        ),
        group="observabilidad",
        requires="STACKY_TELEMETRY_HARVEST_ENABLED",
    ),
    FlagSpec(
        key="STACKY_TELEMETRY_HARVEST_ATTRIBUTED_ONLY",
        type="bool",
        default=True,
        label="Solo sesiones atribuibles a una ejecución",
        description=(
            "Plan 199 — Ingesta únicamente las sesiones que matchean una ejecución "
            "conocida. Privacidad por default: lo no atribuible queda en la bitácora "
            "para que el operador decida, no entra solo."
        ),
        group="observabilidad",
        requires="STACKY_TELEMETRY_HARVEST_ENABLED",
    ),
    FlagSpec(
        key="STACKY_TELEMETRY_HARVEST_LOOKBACK_DAYS",
        type="int",
        # SIN default=: un default declarado la trata como "curada" y ese set es
        # solo para bools ON. El valor efectivo (180) vive en config.py.
        label="Cuántos días hacia atrás cosechar",
        description="Plan 199 — Ventana del escaneo en disco. Default 180 días.",
        group="observabilidad",
        requires="STACKY_TELEMETRY_HARVEST_ENABLED",
        min_value=1,
        max_value=3650,
    ),
    FlagSpec(
        key="STACKY_TELEMETRY_HARVEST_ROOTS_JSON",
        type="str",
        label="Raíces de artefactos por runtime (JSON)",
        description=(
            "Plan 199 — Override de dónde buscar los artefactos, p.ej. "
            '{"codex_cli": "D:/codex/sessions"}. Vacío = rutas por defecto del CLI.'
        ),
        group="observabilidad",
        requires="STACKY_TELEMETRY_HARVEST_ENABLED",
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
            "/cost-summary. Sin shell-out, sin dependencia nueva. Con la ruta vacía "
            "(el default) no hace nada: degrada sin romper."
        ),
        group="observabilidad",
        pair="STACKY_COST_CODEBURN_IMPORT_PATH",
        # Promovida a default ON (barrido del operador 2026-07-27): lee un archivo
        # local bajo demanda, no llama a ningun modelo y no escribe en ningun lado.
        # Su OFF original citaba "prerequisito no garantizado", motivo que el operador
        # invalido: con STACKY_COST_CODEBURN_IMPORT_PATH vacio queda inerte.
        # Curada en _CURATED_DEFAULTS_ON (test_default_known_only_for_curated).
        default=True,
    ),
    FlagSpec(
        key="STACKY_COST_CODEBURN_IMPORT_PATH",
        type="str",
        label="Centro de Costos: ruta del JSONL externo",
        description="Plan 142 F7 — Ruta absoluta al export JSONL. Vacío = desactivado.",
        group="observabilidad",
        requires="STACKY_COST_CODEBURN_IMPORT_ENABLED",
    ),
    # ── Plan 213 — Analistas que infieren y declaran supuestos ─────────────────
    FlagSpec(
        key="STACKY_ASSUMPTION_MODE_ENABLED",
        type="bool",
        default=True,
        label="Analistas declaran supuestos en vez de frenar",
        description=(
            "Plan 213 — El Analista Técnico y el Funcional infieren lo que falta, lo "
            "declaran como [SUPUESTO: … | base: … | impacto: …] y terminan el análisis, "
            "en vez de publicar una consulta pre-bloqueo y dejar el ticket esperando. "
            "Declarar un supuesto deja de restar confidence. OFF: comportamiento "
            "pre-213 (consulta pre-bloqueo y espera humana). Default ON."
        ),
        group="global",
    ),
    FlagSpec(
        key="STACKY_ASSUMPTION_MODE_AGENT_TYPES",
        type="csv",
        label="Agentes que reciben la política de supuestos",
        description=(
            "Plan 213 — Tipos de agente a los que se les inyecta la política. El "
            "Developer queda fuera a propósito: no declara supuestos, construye. "
            "Vacío = ninguno."
        ),
        group="global",
        requires="STACKY_ASSUMPTION_MODE_ENABLED",
    ),
    FlagSpec(
        key="STACKY_ASSUMPTION_MAX_PER_RUN",
        type="int",
        label="Techo de supuestos por ejecución",
        description=(
            "Plan 213 — Superarlo marca la corrida como assumption_overload: un "
            "análisis mayormente supuesto necesita ojos humanos."
        ),
        group="global",
        requires="STACKY_ASSUMPTION_MODE_ENABLED",
    ),
    # ── Plan 216 — Config de estados centralizada en el perfil del cliente ─────
    FlagSpec(
        key="STACKY_STATE_CONFIG_CENTRALIZED_ENABLED",
        type="bool",
        default=True,
        label="Config de estados centralizada en el perfil del cliente",
        description=(
            "Plan 216 — Las reglas estado→agente (Flujo) se leen y escriben en "
            "client_profile.state_flow, con migración automática desde "
            "flow_config.json (que NO se borra). Así la config de flujo viaja en los "
            "backups y transfers del proyecto. OFF: comportamiento legacy "
            "byte-idéntico. Default ON."
        ),
        group="global",
    ),
    # ── Plan 214 — Validación QAUAT E2E al completar el Developer ───────────────
    FlagSpec(
        key="STACKY_QA_UAT_ON_DEV_COMPLETE_ENABLED",
        type="bool",
        default=True,
        label="Sugerir validación QAUAT al completar el Developer",
        description=(
            "Plan 214 — Al completar el Developer un ticket, deja preparado el "
            "candidato de validación E2E (QA UAT) visible en la ejecución. No corre "
            "nada ni publica nada por sí solo. Default ON."
        ),
        group="global",
    ),
    FlagSpec(
        key="STACKY_QA_UAT_AUTORUN_ENABLED",
        type="bool",
        # Sin `default=` explícito a propósito: el type-zero de bool ya es False, y
        # `default_is_known` (que exige estar en _CURATED_DEFAULTS_ON) solo aplica a
        # los defaults ON curados.
        label="Autorun QAUAT (dry-run) al completar el Developer",
        description=(
            "Plan 214 — Lanza automáticamente el pipeline QA UAT en dry-run al "
            "completar el Developer. Requiere AgendaWeb local corriendo, credenciales "
            "y browsers Playwright instalados. Default OFF (prerequisito no "
            "garantizado en una instalación default)."
        ),
        group="global",
        requires="STACKY_QA_UAT_ON_DEV_COMPLETE_ENABLED",
    ),
    # ── Plan 211 — Inspector post-build + residuos de port entre clientes ───────
    FlagSpec(
        key="STACKY_DEV_POST_BUILD_INSPECT_ENABLED",
        type="bool",
        default=True,
        label="Inspector post-build",
        description=(
            "Plan 211 — Detecta PostBuildEvents, tareas Copy y OutputPath con rutas "
            "absolutas o de otros clientes en los .csproj que construyó el Developer. "
            "Un hallazgo bloqueante baja el 'Build OK'. Default ON."
        ),
        group="global",
    ),
    FlagSpec(
        key="STACKY_DEV_PORT_RESIDUE_SCAN_ENABLED",
        type="bool",
        default=True,
        label="Barrido de residuos de port",
        description=(
            "Plan 211 — Detecta, en los archivos que tocó el Developer, tokens "
            "(servidores, rutas, nombres) de OTROS clientes del registro de perfiles. "
            "Solo los tokens inequívocos bloquean; los dudosos avisan. Default ON."
        ),
        group="global",
    ),
    # ── Plan 210 — Gate de build determinista del Developer ─────────────────────
    FlagSpec(
        key="STACKY_DEV_BUILD_VERIFY_ENABLED",
        type="bool",
        default=True,
        label="Verificación de build del Developer",
        description=(
            "Plan 210 — Verifica de forma determinista que el Developer compiló "
            "(.sln real, build de máquina) antes de permitir el 'Build OK' del "
            "entregable y la transición de estado. La AUSENCIA de veredicto se "
            "trata como 'no verificado', nunca como OK. Default ON."
        ),
        group="global",
    ),
    # ── Plan 201 — Taller de Compilación ────────────────────────────────────────
    FlagSpec(
        key="STACKY_DEVOPS_BUILD_WORKSHOP_ENABLED",
        type="bool",
        default=True,
        label="Taller de Compilación",
        description=(
            "Plan 201 — Detecta soluciones .sln del workspace, compila en Release y "
            "produce artefactos descargables. La detección y el catálogo son read-only "
            "y siempre seguros; el build requiere toolchain .NET (si falta, muestra el "
            "doctor y no hace nada). Default ON."
        ),
        group="global",
    ),
    # ── Plan 215 — Publicador de Soluciones ─────────────────────────────────────
    FlagSpec(
        key="STACKY_DEVOPS_SOLUTION_PUBLISHER_ENABLED",
        type="bool",
        default=True,
        label="Publicador de Soluciones",
        description=(
            "Escanea una única vez los .sln del workspace, permite configurar el "
            "publish de cada solución y publicarla con un click; asistencia del "
            "agente DevOps ante fallos (el publish requiere toolchain .NET)."
        ),
        group="global",
    ),
    # ── Plan 171 — Telemetría operativa ─────────────────────────────────────────
    FlagSpec(
        key="STACKY_OPS_TELEMETRY_ENABLED",
        type="bool", default=True,
        label="Telemetría operativa",
        description=(
            "Salud y tendencias por agente/runtime/modelo dentro del Centro de Costos: "
            "tasas de fallo, percentiles de duración, series diarias y avisos por umbral. "
            "Solo lectura, calculado al abrir la página. (Distinta de 'Telemetría en vivo' "
            "STACKY_LIVE_TELEMETRY_ENABLED, que emite eventos durante la corrida.)"
        ),
        group="observabilidad",
    ),
    FlagSpec(
        key="STACKY_OPS_BASELINE_ENABLED",
        type="bool", default=True,
        label="Regresiones vs baseline",
        description=(
            "Compara la última semana contra las 4 semanas previas por agente y runtime, "
            "y avisa (solo avisa) si la tasa de error o la latencia p90 empeoraron más "
            "allá del umbral."
        ),
        group="observabilidad", requires="STACKY_OPS_TELEMETRY_ENABLED",
    ),
    FlagSpec(
        key="STACKY_OPS_TRACE_ENABLED",
        type="bool", default=True,
        label="Traza por corrida",
        description=(
            "Vista estructurada de una ejecución en su panel de detalle: fases, duración, "
            "costo clasificado, fuente de telemetría, incidente enlazado y campos sin dato "
            "explícitos. (Distinta de 'Traza de ejecución' STACKY_EXECUTION_TRACE_ENABLED, "
            "que es la CAPTURA runner-side de prompt_sha/agent_name; esta flag solo LEE.)"
        ),
        group="observabilidad", requires="STACKY_OPS_TELEMETRY_ENABLED",
    ),
    # ── Plan 158 — Fix telemetría de costo claude_code_cli ─────────────────────
    FlagSpec(
        key="STACKY_COST_CLAUDE_CLI_TELEMETRY_PARITY_ENABLED",
        type="bool",
        default=True,
        label="Centro de Costos: telemetría real claude_code_cli",
        description=(
            "Plan 158 — Persiste harness_telemetry + metadata['model'] canónico "
            "en ejecuciones claude_code_cli (paridad con codex_cli). Kill-switch: "
            "OFF revierte al comportamiento previo exacto (sin cambios de datos)."
        ),
        group="observabilidad_notif",
    ),
    FlagSpec(
        key="STACKY_COST_CLAUDE_MODEL_BACKFILL_ENABLED",
        type="bool",
        default=True,
        label="Centro de Costos: backfill de modelo histórico (claude_code_cli)",
        description=(
            "Plan 158 — Al arrancar, copia una sola vez metadata['claude_code_model'] "
            "-> metadata['model'] en ejecuciones históricas de claude_code_cli que ya "
            "tienen la clave vieja pero no la canónica. Idempotente, aditivo, nunca "
            "inventa costo."
        ),
        group="observabilidad_notif",
    ),
    # ── Plan 242 — Centro de Costos telemétrico: estadística + scoring ─────────
    # Las DOS default ON: read-only puro sobre filas ya persistidas, sin LLM,
    # sin red, sin escritura en disco y sin quitarle una decisión al operador.
    # Ninguna de las 2 categorías de excepción dura aplica (ni gasto en reposo,
    # ni escritura en un sistema real). El default EFECTIVO vive en config.py.
    FlagSpec(
        key="STACKY_COST_STATS_ENABLED",
        type="bool",
        default=True,   # curada en _CURATED_DEFAULTS_ON (test_default_known_only_for_curated)
        label="Centro de Costos: estadística profunda",
        description=(
            "Plan 242 — Habilita GET /api/metrics/cost-stats: percentiles, desvío, "
            "IQR, MAD, histograma y outliers por métrica y por dimensión, más "
            "eficiencia de cache y rework. Read-only, sin LLM y sin red. OFF = el "
            "endpoint responde {\"enabled\": false} y la UI oculta el sub-tab "
            "Estadísticas."
        ),
        group="observabilidad_notif",
    ),
    FlagSpec(
        key="STACKY_COST_SCORING_ENABLED",
        type="bool",
        default=True,   # curada en _CURATED_DEFAULTS_ON (test_default_known_only_for_curated)
        label="Centro de Costos: nota de eficiencia por corrida",
        description=(
            "Plan 242 — Habilita GET /api/metrics/cost-scores: puntaje 0–100 y nota "
            "A–E por ejecución y por ticket, con las razones en español que lo "
            "justifican. Determinista y sin LLM. OFF = el endpoint responde "
            "{\"enabled\": false} y la UI oculta el sub-tab Scoring."
        ),
        group="observabilidad_notif",
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
            "Reduce ruido de contexto y mejora el grounding. Default ON."
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
            "ningún documento. Default ON."
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
            "que no contiene la palabra buscada. Default ON = búsqueda byte-idéntica "
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
            "la conserva o descarta. No toca docs/sistema/. Default ON."
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
            "detección; degrada a 'sin staleness' si no hay git. Default ON."
        ),
        group="global",
        env_only=False,
        requires="STACKY_DOCS_GRAPH_ENABLED",
    ),
    # ── Plan 284 — el Documentador deja de mezclar y de adivinar ──────────────
    FlagSpec(
        key="STACKY_DOCS_TAXONOMY_ENABLED",
        default=True,  # curada en _CURATED_DEFAULTS_ON (test_default_known_only_for_curated)
        type="bool",
        label="Documentador: separar planes de documentación del proyecto (Plan 284)",
        description=(
            "Plan 284 — Si está en ON, cada documento del árbol lleva su clase "
            "(plan / sistema / proyecto / agente), los documentos de plan dejan de "
            "contaminar el corpus de búsqueda documental y el cómputo de salud "
            "documental los ignora. Clasificar es cálculo puro sobre el nombre del "
            "archivo: no mueve ni borra nada. Default ON."
        ),
        group="global",
        env_only=False,
        requires="STACKY_DOCS_GRAPH_ENABLED",
    ),
    FlagSpec(
        key="STACKY_DOCS_OPERATOR_NOTE_ENABLED",
        default=True,  # curada en _CURATED_DEFAULTS_ON (test_default_known_only_for_curated)
        type="bool",
        label="Documentador: nota libre del operador al lanzarlo (Plan 284)",
        description=(
            "Plan 284 — Si está en ON, al lanzar el Documentador aparece un campo de "
            "texto opcional donde el operador escribe indicaciones libres, que se "
            "inyectan como bloque de contexto prioritario del agente. Vacío ⇒ el "
            "comportamiento es idéntico al de hoy. Default ON."
        ),
        group="global",
        env_only=False,
        requires="STACKY_DOCS_DOCUMENTER_ENABLED",
    ),
    FlagSpec(
        key="STACKY_DOCS_OPERATOR_NOTE_MAX_CHARS",
        type="int",
        label="Documentador: tope de caracteres de la nota del operador",
        description=(
            "Plan 284 — Máximo de caracteres de la nota libre del operador. La nota "
            "más larga se trunca en silencio (no se rechaza: rechazar sería trabajo "
            "extra para el operador). Default 4000."
        ),
        group="global",
        env_only=False,
        requires="STACKY_DOCS_DOCUMENTER_ENABLED",
        min_value=0,
        max_value=100000,
    ),
    FlagSpec(
        key="STACKY_DOCS_CITATION_GATE_ENABLED",
        default=True,  # curada en _CURATED_DEFAULTS_ON (test_default_known_only_for_curated)
        type="bool",
        label="Documentador: rechazar archivos con citas inválidas (Plan 284)",
        description=(
            "Plan 284 — Si está en ON, un archivo de documentación cuyas citas "
            "archivo:línea no resuelven contra el código NO se escribe: se rechaza "
            "antes de tocar el disco y aparece en el panel con el motivo. Endurece el "
            "artefacto (antes se escribía y recién después se contaban las citas). "
            "Default ON."
        ),
        group="global",
        env_only=False,
        requires="STACKY_DOCS_DOCUMENTER_ENABLED",
    ),
    FlagSpec(
        key="STACKY_DOCS_CITATION_GATE_MIN_RATIO",
        type="float",
        label="Documentador: proporción mínima de citas válidas",
        description=(
            "Plan 284 — Proporción mínima de citas archivo:línea que deben resolver "
            "para que el archivo se escriba. Un documento sin ninguna cita no se "
            "rechaza. Default 0.8."
        ),
        group="global",
        env_only=False,
        requires="STACKY_DOCS_DOCUMENTER_ENABLED",
        min_value=0.0,
        max_value=1.0,
    ),
    FlagSpec(
        key="STACKY_DOCS_TICKET_MINING_ENABLED",
        default=True,  # curada en _CURATED_DEFAULTS_ON (test_default_known_only_for_curated)
        type="bool",
        label="Documentador: minar el corpus de tickets (Plan 284)",
        description=(
            "Plan 284 — Si está en ON, el Documentador barre los tickets del proyecto "
            "y separa señal de ruido con criterios deterministas y auditables (sin "
            "modelo), pasando al agente sólo los que aportan historia documentable. "
            "Es un barrido de sólo lectura y sólo cuando el operador lanza el "
            "Documentador: no hay bucle ni proceso de fondo. Default ON."
        ),
        group="global",
        env_only=False,
        requires="STACKY_DOCS_DOCUMENTER_ENABLED",
    ),
    FlagSpec(
        key="STACKY_DOCS_TICKET_MINING_MAX",
        type="int",
        label="Documentador: tope de tickets barridos por run",
        description=(
            "Plan 284 — Máximo de tickets que el barrido examina en un run. Si el "
            "corpus supera el tope, el resumen queda marcado como truncado. "
            "Default 500."
        ),
        group="global",
        env_only=False,
        requires="STACKY_DOCS_DOCUMENTER_ENABLED",
        min_value=1,
        max_value=100000,
    ),
    FlagSpec(
        key="STACKY_DOCS_PIPELINE_STAGES_ENABLED",
        default=True,  # curada en _CURATED_DEFAULTS_ON (test_default_known_only_for_curated)
        type="bool",
        label="Documentador: pipeline de 5 etapas con veredicto (Plan 284)",
        description=(
            "Plan 284 — Si está en ON, el Documentador deja de resolver todo en una "
            "pasada y corre PROPONER, CRITICAR, MEJORAR, IMPLEMENTAR y VERIFICAR, con "
            "el estado de cada etapa persistido y un veredicto explícito al final. "
            "Planear, criticar y verificar son lectura y cálculo. Default ON."
        ),
        group="global",
        env_only=False,
        requires="STACKY_DOCS_DOCUMENTER_ENABLED",
    ),
    FlagSpec(
        # Plan 284 — nace OFF por la excepción (B): le saca la decisión al operador.
        # Con ON, la etapa IMPLEMENTAR escribe sin esperar la confirmación humana.
        # Igual que STACKY_PIPELINE_COPILOT_COMMIT_ENABLED (Plan 279), su FlagSpec
        # NO declara `default=`: si lo declarara, default_is_known() daría True y el
        # assert de igualdad de conjuntos de test_default_known_only_for_curated
        # exigiría curarla, pero test_declared_default_true_set exige que toda key
        # curada tenga declared_default is True. Sin `default=`, ambos quedan verdes.
        key="STACKY_DOCS_PIPELINE_AUTOAPPLY",
        type="bool",
        label="Documentador: aplicar sin pedir confirmación (Plan 284)",
        description=(
            "Plan 284 — Si está en ON, el Documentador escribe la documentación sin "
            "pedirte confirmación. Si la encendés, el Documentador escribe sin pedirte "
            "confirmación. Con OFF (default) el run se detiene y espera tu aprobación "
            "antes de tocar un solo archivo. Default OFF."
        ),
        group="global",
        env_only=False,
        requires="STACKY_DOCS_DOCUMENTER_ENABLED",
    ),
    FlagSpec(
        key="STACKY_DOCS_PIPELINE_MAX_LLM_CALLS",
        type="int",
        label="Documentador: tope de invocaciones al agente por run",
        description=(
            "Plan 284 — Techo duro de invocaciones al agente en un solo run del "
            "Documentador. Al agotarse, el run se detiene ordenadamente y conserva lo "
            "ya escrito. Un valor de 0 o menos significa AGOTADO, nunca 'sin límite'. "
            "Default 12."
        ),
        group="global",
        env_only=False,
        requires="STACKY_DOCS_DOCUMENTER_ENABLED",
        min_value=1,
        max_value=200,
    ),
    FlagSpec(
        key="STACKY_DOCS_RADIOGRAPHY_ENABLED",
        default=True,  # curada en _CURATED_DEFAULTS_ON (test_default_known_only_for_curated)
        type="bool",
        label="Documentador: radiografía de cobertura documental (Plan 284)",
        description=(
            "Plan 284 — Si está en ON, al terminar el run se calcula qué parte del "
            "proyecto quedó documentada y cuál no, más la variación contra el run "
            "anterior. Es una lectura derivada del grafo documental que ya existe: no "
            "construye un grafo paralelo ni escribe nada. Default ON."
        ),
        group="global",
        env_only=False,
        requires="STACKY_DOCS_GRAPH_ENABLED",
    ),
    # ── Plan 285 — el Documentador pisa firme ────────────────────────────────
    FlagSpec(
        key="STACKY_DOCS_CORPUS_AUTOINDEX_ENABLED",
        default=True,  # curada en _CURATED_DEFAULTS_ON (test_default_known_only_for_curated)
        type="bool",
        label="Documentador: indexar la documentación del proyecto antes de escribir (Plan 285)",
        description=(
            "Plan 285 — Si está en ON, al lanzar el Documentador se re-indexa la "
            "documentación .md del proyecto en el corpus de búsqueda, para que el "
            "agente pueda consultarla en vez de reescribirla desde cero. Es lectura "
            "de archivos locales más una tabla derivada propia de Stacky: no hay "
            "bucle ni proceso de fondo y no llama a ningún modelo. Default ON."
        ),
        group="global",
        env_only=False,
        requires="STACKY_DOCS_DOCUMENTER_ENABLED",
    ),
    FlagSpec(
        key="STACKY_DOCS_CORPUS_RETRIEVAL_ENABLED",
        default=True,  # curada en _CURATED_DEFAULTS_ON (test_default_known_only_for_curated)
        type="bool",
        label="Documentador: pasarle al agente la documentación ya escrita (Plan 285)",
        description=(
            "Plan 285 — Si está en ON, el Documentador busca en el corpus la "
            "documentación que el proyecto YA tiene y se la pasa al agente para que "
            "amplíe o corrija en vez de duplicar. Viaja dentro del prompt que igual se "
            "iba a mandar: no agrega ninguna llamada a un modelo. Default ON."
        ),
        group="global",
        env_only=False,
        requires="STACKY_DOCS_DOCUMENTER_ENABLED",
    ),
    FlagSpec(
        key="STACKY_DOCS_CORPUS_ORPHANS_ENABLED",
        default=True,  # curada en _CURATED_DEFAULTS_ON (test_default_known_only_for_curated)
        type="bool",
        label="Documentador: listar proyectos huérfanos del corpus (Plan 285)",
        description=(
            "Plan 285 — Si está en ON, se puede ver qué proyectos quedaron en el "
            "corpus de búsqueda sin existir ya en la configuración de Stacky, con su "
            "conteo de fragmentos. Sólo lista y muestra: no borra nada. Default ON."
        ),
        group="global",
        env_only=False,
        requires="STACKY_DOCS_DOCUMENTER_ENABLED",
    ),
    FlagSpec(
        # EXCEPCION (B) — DESTRUYE DATOS. Borra filas del corpus de forma
        # irreversible: el re-indexado sólo regenera proyectos que existen, así
        # que un huérfano borrado NO vuelve (docs_rag.py:199 purga por
        # project_name; nada re-crea un proyecto que ya no está configurado).
        # Nace OFF, hace backup a .jsonl antes de cualquier DELETE, valida el
        # conteo de filas y exige confirmación explícita del operador en la UI.
        # Sin `default=`: default_is_known() es `spec.default is not None`, así
        # que hasta un default=False explícito rompe test_default_known_only_for_curated.
        key="STACKY_DOCS_CORPUS_PURGE_ENABLED",
        type="bool",
        label="Documentador: permitir borrar los proyectos huérfanos del corpus (Plan 285)",
        description=(
            "Plan 285 — Si la encendés, se habilita el borrado de los fragmentos que "
            "quedaron en el corpus de búsqueda de proyectos que ya no existen. Es la "
            "única operación de este plan que destruye datos, por eso viene apagada: "
            "antes de borrar deja una copia de respaldo y te pide confirmar el número "
            "exacto de filas. Default OFF."
        ),
        group="global",
        env_only=False,
        requires="STACKY_DOCS_DOCUMENTER_ENABLED",
    ),
    FlagSpec(
        key="STACKY_DOCS_RIGOR_PER_CLAIM_ENABLED",
        default=True,  # curada en _CURATED_DEFAULTS_ON (test_default_known_only_for_curated)
        type="bool",
        label="Documentador: exigir rigor por afirmación (Plan 285)",
        description=(
            "Plan 285 — Si está en ON, un documento largo que apenas trae una marca de "
            "confianza suelta y ninguna cita al código se rechaza antes de escribirse, "
            "con el motivo a la vista. Endurece un artefacto que Stacky genera en su "
            "propia rama, siempre revertible. Default ON."
        ),
        group="global",
        env_only=False,
        requires="STACKY_DOCS_DOCUMENTER_ENABLED",
    ),
    FlagSpec(
        key="STACKY_DOCS_RIGOR_MIN_DENSITY",
        type="float",
        label="Documentador: proporción mínima de afirmaciones marcadas",
        description=(
            "Plan 285 — Qué parte de las afirmaciones de un documento tienen que "
            "llevar marca de confianza para que se escriba. Los encabezados y las "
            "líneas dentro de un bloque de código no cuentan como afirmación, y un "
            "documento muy corto nunca se rechaza. Default 0.5."
        ),
        group="global",
        env_only=False,
        requires="STACKY_DOCS_DOCUMENTER_ENABLED",
        min_value=0.0,
        max_value=1.0,
    ),
    FlagSpec(
        key="STACKY_DOCS_RIGOR_MIN_CITATIONS",
        type="int",
        label="Documentador: citas al código mínimas por documento",
        description=(
            "Plan 285 — Cuántas citas archivo:línea válidas tiene que traer un "
            "documento largo para que se escriba. Si no se pudieron contar las citas, "
            "este chequeo se omite en vez de rechazar. Default 1."
        ),
        group="global",
        env_only=False,
        requires="STACKY_DOCS_DOCUMENTER_ENABLED",
        min_value=0,
        max_value=50,
    ),
    FlagSpec(
        key="STACKY_DOCS_TICKET_TRIAGE_VISIBLE_ENABLED",
        default=True,  # curada en _CURATED_DEFAULTS_ON (test_default_known_only_for_curated)
        type="bool",
        label="Documentador: mostrar los tickets descartados y por qué (Plan 285)",
        description=(
            "Plan 285 — Si está en ON, el panel del Documentador muestra qué tickets "
            "quedaron afuera del barrido y con qué motivo. Guarda y muestra el "
            "resultado de un cálculo que ya se hacía y se tiraba. Default ON."
        ),
        group="global",
        env_only=False,
        requires="STACKY_DOCS_DOCUMENTER_ENABLED",
    ),
    FlagSpec(
        key="STACKY_DOCS_TREE_GROUP_BY_CLASS_ENABLED",
        default=True,  # curada en _CURATED_DEFAULTS_ON (test_default_known_only_for_curated)
        type="bool",
        label="Documentación: separar los planes de la documentación del proyecto (Plan 285)",
        description=(
            "Plan 285 — Si está en ON, el árbol de documentación agrupa por clase y te "
            "deja filtrar, así los documentos de plan dejan de aparecer revueltos con "
            "la documentación del proyecto. Sólo cambia cómo se presenta información "
            "que el backend ya envía. Default ON."
        ),
        group="global",
        env_only=False,
        requires="STACKY_DOCS_DOCUMENTER_ENABLED",
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
            "Default ON = enrich_blocks byte-idéntico al Plan 64."
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
            "(sin LLM, sin inventar). Default ON para no exponer un feature incompleto."
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
            "memoria operator_note reutilizable. Default ON."
        ),
        group="global",
        env_only=True,
    ),
    FlagSpec(
        key="STACKY_EPIC_AUTOPUBLISH_BACKEND",
        type="bool",
        default=True,          # ya era true en config.py:1054; NO se cambia el default
        label="Autopublicar la épica del brief (41)",
        description=(
            "Plan 41 / Plan 278 — Si ON, al cerrar una run brief→épica el backend publica "
            "la Épica/Issue en el tracker del proyecto, en los 3 runtimes. OFF = run_brief "
            "rechaza Epic/Issue con 'autopublish_disabled' en vez de terminar en falso verde."
        ),
        group="global",
    ),
    FlagSpec(
        key="INTENT_PREFLIGHT_ENABLED",
        type="bool",
        default=True,  # promovida a default ON (operador 2026-07-15, config se hace despues desde la UI)
        label="Pre-vuelo de Intención (41)",
        description=(
            "Plan 41 — Si ON, antes del run genera un Brief de Intención que el "
            "operador aprueba/corrige. Default ON (byte-idéntico al actual)."
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
            "en Agentes/outputs y lo publica. Default ON."
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
            "(copilot/claude_code_cli/codex). Default ON."
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
            "Default ON (evita falsos positivos hasta catálogo curado)."
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
            "autopublish. Opt-in dentro de opt-in. Default ON."
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
            "respuesta. Default ON."
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
            "TASK_GATE_BLOCKED). Default ON."
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
            "proponga el agente. Default ON."
        ),
        group="global",
        env_only=False,
    ),
    # ── Plan 209 — Guía "Cómo validar esto" en el entregable ──────────────────
    FlagSpec(
        key="STACKY_VALIDATION_PLAYBOOK_ENABLED",
        type="bool",
        default=True,
        label="Guía 'Cómo validar' en el entregable",
        description=(
            "Plan 209 — Anexa al deliverable pasos de validación para el usuario "
            "de RS, grounded en la documentación del cliente y citando la fuente; "
            "degrada honestamente si no hay evidencia. Solo agentes de producto. "
            "Sin llamadas LLM extra. Default ON."
        ),
        group="global",
        env_only=False,
    ),
    # ── Plan 208 — Auto-sync al completar + matriz de estados por tipo ────────
    FlagSpec(
        key="STACKY_ADO_SYNC_ON_COMPLETION_ENABLED",
        type="bool",
        default=True,
        label="Auto-sync ADO al completar",
        description=(
            "Plan 208 — Al terminar cualquier agente, refresca los tickets del "
            "proyecto desde el tracker (pull read-only, coalescido, respeta el "
            "circuit breaker). Elimina el clic manual de 'Sincronizar'. Default ON."
        ),
        group="global",
        env_only=False,
    ),
    FlagSpec(
        key="STACKY_ADO_STATE_MATRIX_ENABLED",
        type="bool",
        default=True,
        label="Matriz de estados por tipo de ticket",
        description=(
            "Plan 208 — Aplica el estado ADO configurado por (tipo de work item x "
            "tipo de agente) cuando el agente termina OK. NO-OP hasta que el "
            "operador configure la matriz en el perfil del proyecto. Default ON."
        ),
        group="global",
        env_only=False,
    ),
    # ── Plan 271 — La incidencia se mueve al estado configurado al terminar ──
    FlagSpec(
        key="STACKY_FINAL_STATE_ROLE_FALLBACK_ENABLED",
        type="bool",
        default=True,
        label="Estado final de nivel rol (fallback)",
        description=(
            "Plan 271 — Cuando la matriz no define un estado final para ese "
            "tipo de ticket, aplica el estado configurado a nivel ROL en la "
            "pantalla de Estados. Repara una promesa ya hecha al operador. "
            "Default ON."
        ),
        group="global",
        env_only=False,
    ),
    FlagSpec(
        key="STACKY_FINAL_STATE_WRITER_ROUTED_ENABLED",
        type="bool",
        default=True,
        label="Escritor de estado ruteado por proveedor",
        description=(
            "Plan 271 — El escritor de estado del cierre por empleado rutea "
            "por el proveedor del proyecto (ADO o GitLab) en vez de asumir "
            "siempre ADO. Corrige el destino, no agrega escrituras. Default ON."
        ),
        group="global",
        env_only=False,
    ),
    FlagSpec(
        key="STACKY_FINAL_STATE_PUBLISH_GATE_PRECISE_ENABLED",
        type="bool",
        default=True,
        label="Gate de publicación preciso",
        description=(
            "Plan 271 — Deja de bloquear el cambio de estado cuando no había "
            "nada que publicar (sin HTML, auto-publish apagado, publisher no "
            "disponible). Sigue bloqueando si la publicación se intentó y "
            "falló. Default ON."
        ),
        group="global",
        env_only=False,
    ),
    FlagSpec(
        key="STACKY_FINAL_STATE_REASON_VISIBLE_ENABLED",
        type="bool",
        default=True,
        label="Razón del cambio de estado visible",
        description=(
            "Plan 271 — Persiste y muestra en el detalle de la ejecución por "
            "qué la incidencia se movió o por qué no. Solo lectura, no escribe "
            "en el tracker. Default ON."
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
            "(model/effort en el body) siempre gana. Default ON."
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
            "desde un único brief (feature beta, default ON). "
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
            "Default ON = solo el Epic, sin desglose hijo."
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
            "y las materializa como lección en el corpus (plan 54). Pasivo, default ON."
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
    # ── Plan 247 — Perfilador de pipelines (stack + anatomía + propósito) ──────
    FlagSpec(
        key="STACKY_PIPELINE_PROFILER_ENABLED",
        type="bool",
        label="Perfilador de pipelines (Plan 247)",
        description=(
            "Plan 247 — Si ON, habilita POST /api/pipeline-profiler/profile: dado un YAML de "
            "pipeline ADO devuelve stack, fases presentes y AUSENTES, artefactos, entornos, "
            "agentes y un propósito en 1 línea. 100% determinista y sin LLM en el camino default. "
            "Default ON (ninguna de las 4 excepciones duras aplica: read-only, no destructivo, "
            "sin prerequisitos nuevos, no reduce seguridad; curada en _CURATED_DEFAULTS_ON de "
            "tests/test_harness_flags.py). "
            "OFF: guard 404 per-request; el blueprint sigue registrado y el resto del panel "
            "queda byte-idéntico."
        ),
        group="global",
        env_only=False,  # editable por UI (regla dura operator-config-always-via-ui)
        default=True,
    ),
    # ── Plan 249 — Reglas semánticas de GitLab CI (GL000..GL011) ──────────────
    FlagSpec(
        key="STACKY_GITLAB_SEMANTIC_RULES_ENABLED",
        type="bool",
        default=True,  # default ON (ninguna de las 4 excepciones duras aplica; curada en
                       # _CURATED_DEFAULTS_ON). NO declara requires="STACKY_GITLAB_ENABLED":
                       # analizar el TEXTO de un .gitlab-ci.yml no necesita instancia GitLab,
                       # y atarlas dejaria la capacidad muerta en una instalacion limpia.
        label="Reglas semánticas de GitLab CI",
        description=(
            "Plan 249 - agrega los hallazgos GL000..GL011 (stage no declarado, needs a un stage "
            "posterior, only/except mezclado con rules, deploy a produccion sin compuerta manual) "
            "al validador de pipelines cuando el proveedor es GitLab. "
            "OFF: el endpoint devuelve exactamente las PL001..PL014 de hoy, byte-identico."
        ),
        group="global",
        env_only=False,
    ),
    # ── Plan 248 — Auditoría de pipelines (seguridad + optimización) ──────────
    FlagSpec(
        key="STACKY_PIPELINE_AUDIT_ENABLED",
        type="bool",
        default=True,   # default ON: NINGUNA de las 4 excepciones duras aplica — es read-only,
                        # sin red, sin LLM, no publica nada y no reduce la seguridad por default.
                        # Curada en _CURATED_DEFAULTS_ON (test_harness_flags.py).
        label="Auditoría de pipelines",
        description=(
            "Plan 248 - audita pipelines existentes: riesgos de seguridad (SEC001..SEC008) y "
            "recomendaciones de optimización (OPT001..OPT004). Read-only: detecta y explica, "
            "nunca aplica cambios. OFF: el panel de auditoría desaparece y /api/pipeline-audit/* "
            "devuelve 404; el lint PL001..PL014 y las reglas RS001..RS009 siguen idénticos."
        ),
        group="global",
        env_only=False,  # editable por UI (regla dura operator-config-always-via-ui)
    ),
    # ── Plan 252 — Paquete de entrega + frontera de capacidades ───────────────
    FlagSpec(
        key="STACKY_PIPELINE_HANDOFF_BUNDLE_ENABLED",
        type="bool",
        default=True,   # default ON: NINGUNA de las 4 excepciones duras aplica — solo
                        # produce un archivo descargable, no ejecuta nada, no publica
                        # nada y no reduce la seguridad. Curada en _CURATED_DEFAULTS_ON.
        label="Paquete de entrega de pipelines",
        description=(
            "Plan 252 - genera un .zip unico con los YAML, los scripts y un README "
            "operativo para lo que Stacky no puede hacer solo, mas la frontera de "
            "capacidades (que hace Stacky y que te toca a vos). OFF: desaparece el boton "
            "y /api/pipeline-handoff/* responde 404; todo lo demas del panel queda igual."
        ),
        group="global",
        env_only=False,  # editable por UI (regla dura operator-config-always-via-ui)
        # SIN `requires` a proposito: el paquete se puede armar aunque el generador
        # este OFF (los YAML pueden venir del repo). Y agregarla a _REQUIRES_MAP_FROZEN
        # pondria ESE test en rojo, porque el mapa solo lista las specs CON requires.
    ),
    # ── Plan 251 — Matriz de entornos y valores que solo el operador conoce ───
    FlagSpec(
        key="STACKY_PIPELINE_ENV_MATRIX_ENABLED",
        type="bool",
        default=True,   # default ON: NINGUNA de las 4 excepciones duras aplica — es de
                        # SOLO LECTURA (no escribe ni en el repo, ni en el proveedor, ni
                        # en el servidor), no bypasea revision humana, no agrega
                        # prerequisitos y SUBE la seguridad (enumera que credenciales
                        # hacen falta). Curada en _CURATED_DEFAULTS_ON.
        label="Matriz de entornos (Plan 251)",
        description=(
            "Plan 251 - Detecta que valores exige una pipeline (variables, secretos, "
            "servidores, rutas de despliegue, parametros) y los cruza contra los "
            "entornos reales de esa pipeline, resolviendo primero contra la caja fuerte "
            "(94) y el registro de servidores (91) para pedir SOLO lo que falta. Solo "
            "lectura: no escribe nada. OFF: /api/pipeline-environments da 404 y la "
            "seccion no se muestra."
        ),
        group="global",
        env_only=False,  # editable por UI (regla dura operator-config-always-via-ui)
        # R4 profundidad 1: cuelga del master del panel, NUNCA de
        # STACKY_DEVOPS_VARIABLES_ENABLED (esa ya declara requires y encadenar rompe
        # validate_requires_graph).
        requires="STACKY_DEVOPS_PANEL_ENABLED",
    ),
    # ── Plan 260 — Ninguna pipeline corre a ciegas ─────────────────────────────
    FlagSpec(
        key="STACKY_PIPELINE_ENV_DECLARE_ENABLED",
        type="bool",
        # SIN `default=`: el default EFECTIVO es el de config.py ("false"). Declararlo
        # aca (aunque sea `default=False`) haria default_is_known()==True y rompe
        # test_default_known_only_for_curated (mismo patron que
        # STACKY_PIPELINE_NL_EDIT_COMMIT_ENABLED, arriba).
        # EXCEPCION DURA (B): es la UNICA ruta nueva que ESCRIBE en un sistema externo
        # real del operador — crea variables vacias en su ADO/GitLab via el puerto
        # del Plan 94 (services/ci_variables.py, set_variable).
        label="Declarar nombres de variables faltantes",
        description=(
            "Plan 260 - crea, con valor vacio, los nombres de variables/secretos que la "
            "matriz de entornos detecto como faltantes, para que el operador solo tenga "
            "que pegar el valor. Requiere confirmacion explicita (HITL) y nunca escribe "
            "un valor. OFF: el boton de declarar no aparece y /declare responde 404."
        ),
        group="global",
        env_only=False,  # editable por UI (regla dura operator-config-always-via-ui)
        requires="STACKY_DEVOPS_PANEL_ENABLED",
    ),
    FlagSpec(
        key="STACKY_PIPELINE_TRIGGER_ENV_GATE_ENABLED",
        type="bool",
        default=True,   # default ON: solo LEE (mismo resolve() que ya corre /analyze),
                        # corre a pedido dentro del request de disparo (sin loop ni
                        # daemon), y solo bloquea con evidencia POSITIVA de faltantes;
                        # nunca bloquea por no haber podido resolver. Curada en
                        # _CURATED_DEFAULTS_ON (test_harness_flags.py).
        label="Bloquear el disparo si faltan valores",
        description=(
            "Plan 260 - antes de disparar una pipeline, verifica que los valores "
            "obligatorios ya esten cargados en el proveedor y frena el disparo si "
            "falta alguno con evidencia positiva (nunca por no haber podido verificar). "
            "OFF: el disparo funciona exactamente como hoy, sin ninguna verificacion previa."
        ),
        group="global",
        env_only=False,  # editable por UI (regla dura operator-config-always-via-ui)
        requires="STACKY_PIPELINE_TRIGGER_ENABLED",
    ),
    FlagSpec(
        key="STACKY_PIPELINE_SECRET_COMMIT_GATE_ENABLED",
        type="bool",
        default=True,   # default ON: solo puede IMPEDIR una fuga (nunca escribe nada,
                        # no consume tokens). Apagarlo es la decision rara, no
                        # encenderlo. Curada en _CURATED_DEFAULTS_ON.
        label="Bloquear el commit de un secreto literal",
        description=(
            "Plan 260 - antes de guardar una canalizacion (generador o editor), revisa "
            "que no tenga un secreto escrito en claro y frena el guardado si lo "
            "encuentra. OFF: el guardado funciona exactamente como antes, sin esta "
            "revision."
        ),
        group="global",
        env_only=False,  # editable por UI (regla dura operator-config-always-via-ui)
        requires="STACKY_DEVOPS_PANEL_ENABLED",
    ),
    # ── Plan 250 — Edicion quirurgica de pipelines existentes ─────────────────
    FlagSpec(
        key="STACKY_PIPELINE_NL_EDIT_ENABLED",
        type="bool",
        default=True,   # default ON: NINGUNA de las 4 excepciones duras aplica —
                        # analiza y muestra el diff, NO escribe en ningun lado, no
                        # bypasea revision humana (la exige), no agrega prerequisitos
                        # (PyYAML ya esta) y no reduce la seguridad (agrega gates).
                        # Curada en _CURATED_DEFAULTS_ON (test_harness_flags.py).
        label="Edicion de pipelines existentes",
        description=(
            "Plan 250 - modificar una pipeline que YA existe describiendo el cambio; "
            "patch quirurgico por splice de lineas (nunca re-render, que borraria los "
            "comentarios) con diff visible. OFF: desaparece el panel de edicion y "
            "/api/pipeline-editor/* devuelve 404; el builder grafico queda IDENTICO."
        ),
        group="global",
        env_only=False,  # editable por UI (regla dura operator-config-always-via-ui)
    ),
    FlagSpec(
        key="STACKY_PIPELINE_NL_EDIT_COMMIT_ENABLED",
        type="bool",
        # SIN `default=`: el default EFECTIVO es el de config.py ("false"). Declararlo
        # aca —aunque sea `default=False`— la haria `default_is_known` y pondria roja a
        # test_default_known_only_for_curated, que exige que el conjunto de flags con
        # default declarado sea EXACTAMENTE _CURATED_DEFAULTS_ON. El plan escribia
        # `default=False`: las dos cosas no pueden ser ciertas a la vez.
        # EXCEPCION DURA (2): es la UNICA ruta que ESCRIBE en un sistema externo real del
        # operador (push a su Azure DevOps via ado_provider.commit_file:146, real desde
        # el plan 95 F1.a). Que sea reversible borrando la rama no lo hace no-escritura.
        label="Permitir commitear la pipeline editada",
        description=(
            "Plan 250 - habilita SOLO el commit del YAML parcheado a una rama del repo "
            "REAL. Ver el cambio y el diff NO necesita esta flag. OFF: el boton de "
            "commit explica como activarla y ofrece copiar el YAML; los otros 3 "
            "endpoints siguen funcionando."
        ),
        group="global",
        env_only=False,  # editable por UI (regla dura operator-config-always-via-ui)
        requires="STACKY_PIPELINE_NL_EDIT_ENABLED",
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
    # ── Plan 102 — Publicar en un paso (orquestador HITL) ──────────────────────
    FlagSpec(
        key="STACKY_DEVOPS_ONE_CLICK_PUBLISH_ENABLED",
        type="bool",
        label="Publicar en un paso (Plan 102)",
        description=(
            "Plan 102 — Agrega un boton 'Publicar en un paso' en Publicaciones y "
            "Ambientes: un solo resumen previo (preset, procesos resueltos, YAML "
            "final, branch destino) y un solo confirm que encadena materializar -> "
            "commit -> disparo del pipeline. Default OFF a proposito: comprime dos "
            "efectos externos reales (escribir en el repo y disparar una corrida) "
            "detras de una sola confirmacion. Los caminos de siempre quedan "
            "intactos y disponibles. Necesita ademas el generador y el disparo de "
            "pipelines activos; si falta alguno, el boton avisa cual."
        ),
        group="global",  # mismo group que STACKY_DEVOPS_PANEL_ENABLED (87 v2 F0)
        env_only=False,  # editable por UI (categoría 'devops')
        # R4 (harness_flags.py, profundidad maxima 1): el master apuntado NO puede
        # tener a su vez `requires`. STACKY_DEVOPS_PUBLICATIONS_ENABLED SI declara
        # requires=PANEL, asi que apuntarle seria "cadena prohibida" y dejaria
        # test_harness_flags_requires en rojo. Se apunta al PANEL, sin condicional.
        requires="STACKY_DEVOPS_PANEL_ENABLED",
        # SIN kwarg `default`: es default OFF. Declarar default=False rompe
        # test_default_known_only_for_curated (esa lista es solo de flags ON).
    ),
    # ── Plan 103 — Monitor vivo del ultimo pipeline ────────────────────────────
    FlagSpec(
        key="STACKY_DEVOPS_PIPELINE_MONITOR_ENABLED",
        type="bool",
        label="Monitor vivo del ultimo pipeline (Plan 103)",
        description=(
            "Plan 103 — El estado del ultimo pipeline que disparaste queda en un "
            "badge del header del panel DevOps: sobrevive al cambio de sub-seccion "
            "y a recargar la pagina, se lee en castellano en vez de JSON crudo, y "
            "el sondeo usa backoff (3s->5s->10s->30s) y se pausa cuando la pestana "
            "del navegador no esta al frente. Default ON: es solo-lectura, no "
            "dispara nada ni gasta tokens. Con OFF, Trigger CI vuelve al sondeo "
            "fijo de 3s y al JSON crudo de hoy."
        ),
        group="global",  # mismo group que STACKY_DEVOPS_PANEL_ENABLED (87 v2 F0)
        env_only=False,  # editable por UI (categoría 'devops')
        requires="STACKY_DEVOPS_PANEL_ENABLED",  # Plan 82 — declarativo, informa en UI
        # Default ON: ninguna de las 4 excepciones duras aplica (no bypasea revisión
        # humana, no es destructiva, no depende de un prerequisito ausente y no baja
        # la seguridad). Curada en _CURATED_DEFAULTS_ON, que
        # test_default_known_only_for_curated exige para toda flag con default conocido.
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
        # Promovida a default ON (barrido del operador 2026-07-27): el master solo
        # muestra la seccion y el PLAN (dry-run). Determinista, cero LLM, cero tokens
        # en reposo. Lo que ESCRIBE (deploy/rollback real) lo gatea su hija
        # STACKY_DEPLOYMENTS_EXECUTE_ENABLED, que sigue default OFF.
        # Curada en _CURATED_DEFAULTS_ON (test_default_known_only_for_curated).
        default=True,
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
        # Promovida a default ON (barrido del operador 2026-07-27): es un BOTON
        # on-demand contra el modelo LOCAL (costo de tokens cero) y no escribe nada.
        # No hay gasto en reposo: sin clic no corre. Si el modelo local no esta,
        # el boton queda deshabilitado con hint (degrada sin romper).
        # Curada en _CURATED_DEFAULTS_ON (test_default_known_only_for_curated).
        default=True,
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
    # ── Plan 190 — Equipaje portable DevOps en export/import de configuración ──
    FlagSpec(
        key="STACKY_CONFIG_TRANSFER_DEVOPS_ENABLED",
        type="bool",
        label="Equipaje DevOps en export/import",
        description=(
            "Plan 190 — Incluye servidores DevOps (sin contraseñas — quedan en el "
            "keyring) y apps del Centro de Despliegues en el export/import de "
            "configuración, con checklist de re-vinculación de credenciales al "
            "importar. Default ON: exportar NUNCA incluye secretos e importar NUNCA "
            "toca el keyring. Con OFF, el catálogo y el comportamiento quedan "
            "EXACTOS a hoy."
        ),
        group="global",
        env_only=False,
        # SIN requires: la transferencia de config es GLOBAL, no vive dentro del
        # panel DevOps (secciones top-level como uiPreferences).
        # Curada en _CURATED_DEFAULTS_ON (test_default_known_only_for_curated).
        default=True,
    ),
    # ── Plan 186 — Lint determinista de pipelines ────────────────────────────
    FlagSpec(
        key="STACKY_DEVOPS_PIPELINE_LINT_ENABLED",
        type="bool",
        label="Lint determinista de pipelines",
        description=(
            "Plan 186 — Valida el YAML del pipeline (ADO/GitLab) local y al instante "
            "(reglas PLxxx), muestra el plan de ejecución estilo terraform-plan y "
            "sugiere fixes con diff aplicables por click (HITL). Determinista, sin "
            "red, sin IA. Con OFF el endpoint devuelve 404 y el panel queda idéntico "
            "a hoy."
        ),
        group="global",
        env_only=False,
        requires="STACKY_DEVOPS_PANEL_ENABLED",  # vive dentro del panel 87 (depth-1)
        # Curada en _CURATED_DEFAULTS_ON (test_default_known_only_for_curated).
        default=True,
    ),
    # ── Plan 188 — Del fallo de despliegue a la incidencia ───────────────────
    FlagSpec(
        key="STACKY_DEVOPS_FAILURE_EVIDENCE_ENABLED",
        type="bool",
        label="Evidencia de fallos de despliegue",
        description=(
            "Plan 188 — En un run fallido del Centro de Despliegues, arma el "
            "paquete de evidencia (resumen + markdown + JSON, sin secretos) y "
            "abre el modal de incidencias prellenado. Solo-lectura local; crear "
            "la incidencia sigue siendo decisión del operador (HITL). Con OFF el "
            "endpoint devuelve 404 y el panel queda idéntico a hoy."
        ),
        group="global",
        env_only=False,
        requires="STACKY_DEVOPS_PANEL_ENABLED",  # vive dentro del panel 87 (depth-1)
        # Curada en _CURATED_DEFAULTS_ON (test_default_known_only_for_curated).
        default=True,
    ),
    # ── Plan 189 — Semáforo de rollback y simulacro read-only ────────────────
    FlagSpec(
        key="STACKY_DEVOPS_ROLLBACK_READINESS_ENABLED",
        type="bool",
        label="Semáforo de rollback y simulacro",
        description=(
            "Plan 189 — Muestra por app y destino si hay rollback disponible (y a "
            "qué versión) y permite SIMULAR los pasos exactos del rollback SIN "
            "ejecutar nada. Solo lecturas locales del ledger; el rollback real y "
            "sus confirmaciones quedan intactos. Con OFF el endpoint devuelve 404 "
            "y las cards quedan idénticas a hoy."
        ),
        group="global",
        env_only=False,
        requires="STACKY_DEVOPS_PANEL_ENABLED",  # R4 profundidad-1 (master del panel 87)
        # Curada en _CURATED_DEFAULTS_ON (test_default_known_only_for_curated).
        default=True,
    ),
    # ── Plan 191 — Bitácora durable de corridas CI ──────────────────────────
    FlagSpec(
        key="STACKY_CI_RUN_LEDGER_ENABLED",
        type="bool",
        label="Bitácora de corridas CI",
        description=(
            "Plan 191 — Registra localmente cada pipeline disparado desde Stacky "
            "(ref, id, resultado) y muestra el historial con estado vivo y "
            "re-disparo con confirmación. Solo metadata local; sin secretos. "
            "Con OFF el endpoint /api/ci/runs devuelve 404 y la sección de "
            "disparo queda idéntica a hoy."
        ),
        group="global",
        env_only=False,
        requires="STACKY_PIPELINE_TRIGGER_ENABLED",  # sin triggers no hay contenido (depth-1)
        # Curada en _CURATED_DEFAULTS_ON (test_default_known_only_for_curated).
        default=True,
    ),
    # ── Plan 193 — Triage de fallos CI (logs inline enmascarados, read-only) ──
    FlagSpec(
        key="STACKY_CI_FAILURE_TRIAGE_ENABLED",
        type="bool",
        label="Triage de fallos CI (logs inline)",
        description=(
            "Plan 193 — En un pipeline fallido, lista los jobs fallidos y muestra el "
            "log de cada uno dentro de Stacky (recortado a 200 KB y con tokens "
            "enmascarados). Solo lectura; el Doctor IA sigue disponible como paso "
            "siguiente. Con OFF los endpoints devuelven 404 y la sección de disparo "
            "queda idéntica a hoy."
        ),
        group="global",
        env_only=False,
        requires="STACKY_PIPELINE_TRIGGER_ENABLED",  # la superficie vive en la sección de trigger/monitor (depth-1)
        # Curada en _CURATED_DEFAULTS_ON (test_default_known_only_for_curated).
        default=True,
    ),
    # ── Plan 198 — Bitácora de applies de ambientes ──────────────────────────
    FlagSpec(
        key="STACKY_DEVOPS_ENV_APPLY_LEDGER_ENABLED",
        type="bool",
        label="Bitácora de applies de ambientes",
        description=(
            "Plan 198 — Registra localmente cada apply de carpetas (local o remoto): "
            "qué se creó, dónde, con qué fingerprint y resultado — y avisa si la "
            "DEFINICIÓN del layout cambió desde el último apply. Solo metadata local; "
            "sin contenido de archivos. Con OFF el endpoint /environments/applies "
            "devuelve 404 y la sección de Ambientes queda idéntica a hoy."
        ),
        group="global",
        env_only=False,
        requires="STACKY_DEVOPS_PANEL_ENABLED",  # R4 profundidad-1 (master del panel 87)
        # Curada en _CURATED_DEFAULTS_ON (test_default_known_only_for_curated).
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
            "Default ON. Con OFF, los endpoints retornan 503."
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
    # ── Plan 282 — GitLab deja de ser un ADO disfrazado ──────────────────────
    # Las 7 nacen ON y están curadas en _CURATED_DEFAULTS_ON. Bloque CONTIGUO a
    # propósito: 280, 281 y 282 escriben en este archivo a la vez, y un bloque se
    # resuelve como UN conflicto, no como siete.
    FlagSpec(
        key="STACKY_COMMENT_PUBLISH_ROUTED_ENABLED",
        default=True,
        type="bool",
        label="El comentario del agente se publica en el tracker del ticket (Plan 282)",
        description=(
            "Plan 282 F1 - Si esta ON, el publicador de comentarios resuelve el cliente "
            "por el TRACKER DEL TICKET en vez de construir siempre un cliente Azure "
            "DevOps. En un proyecto GitLab el HTML del agente llega al issue; antes "
            "quedaba en disco y la bitacora registraba 'failed'. Si esta OFF vuelve el "
            "comportamiento previo. No agrega ninguna escritura automatica: la dispara "
            "el checkbox 'Publicar comentario' del cierre, y es idempotente por dos "
            "barreras (dedupe por contenido y dedupe por marcador contra el tracker)."
        ),
        group="global",
        env_only=False,
    ),
    FlagSpec(
        key="STACKY_GITLAB_PROVIDER_FACTORY_ONLY_ENABLED",
        default=True,
        type="bool",
        label="Un solo constructor del proveedor GitLab, con certificado (Plan 282)",
        description=(
            "Plan 282 F2 - Si esta ON, los servicios de CI, logs, preflight y variables "
            "piden el proveedor GitLab a la fabrica, que resuelve el bundle de "
            "certificado del proyecto. Antes lo construian a mano y morian con "
            "CERTIFICATE_VERIFY_FAILED contra un GitLab con autoridad interna, mientras "
            "la sonda y el listado de tickets funcionaban. Si esta OFF vuelve la "
            "construccion directa, sin certificado."
        ),
        group="global",
        env_only=False,
    ),
    FlagSpec(
        key="STACKY_GITLAB_ASSIGNEE_STRICT_ENABLED",
        default=True,
        type="bool",
        label="Un usuario GitLab que no resuelve falla en vez de desasignar (Plan 282)",
        description=(
            "Plan 282 F3 - Si esta ON, asignar un issue de GitLab a un username que no "
            "existe levanta un error con el nombre que no se pudo resolver. Antes "
            "mandaba la lista de asignados VACIA, asi que un error de tipeo o una caida "
            "momentanea del endpoint de usuarios desasignaba el issue en silencio. "
            "Desasignar a proposito (dejando el campo vacio) se conserva. Si esta OFF "
            "vuelve el borrado silencioso."
        ),
        group="global",
        env_only=False,
    ),
    FlagSpec(
        key="STACKY_TRACKER_LABELS_GLOBAL_ENABLED",
        default=True,
        type="bool",
        label="Los rotulos de la pantalla siguen al tracker del proyecto (Plan 282)",
        description=(
            "Plan 282 F4 - Si esta ON, las referencias, botones, tooltips y titulos usan "
            "el nombre del tracker del proyecto activo: en GitLab dicen '#1115' y "
            "'GitLab' donde antes decian 'ADO-1115' y 'ADO'. Solo lectura y "
            "presentacion. Si esta OFF, toda la interfaz vuelve a hablar Azure DevOps."
        ),
        group="global",
        env_only=False,
    ),
    FlagSpec(
        key="STACKY_TRACKER_URLS_ROUTED_ENABLED",
        default=True,
        type="bool",
        label="Los enlaces del ticket dejan de apuntar al tracker de otro cliente (Plan 282)",
        description=(
            "Plan 282 F5 - Si esta ON, 'Abrir' y 'Copiar link' usan la URL que manda el "
            "backend o la construyen con la organizacion REAL del proyecto; si no hay "
            "ninguna, la accion no se ofrece. Antes se armaba con una organizacion y un "
            "proyecto fijos de otro cliente, asi que en un proyecto GitLab el enlace "
            "llevaba a un lugar ajeno. Si esta OFF, la interfaz usa unicamente la URL "
            "que provee el backend."
        ),
        group="global",
        env_only=False,
    ),
    FlagSpec(
        key="STACKY_TICKET_STATE_FILTER_ROUTED_ENABLED",
        default=True,
        type="bool",
        label="El filtro 'Solo abiertos' y los colores entienden el tracker (Plan 282)",
        description=(
            "Plan 282 F6 - Si esta ON, el vocabulario de estados terminales y los colores "
            "de los distintivos se resuelven por tracker. En GitLab, cuyos estados son "
            "'opened' y 'closed', el filtro dejaba pasar todo y los distintivos caian "
            "todos al mismo gris. Solo lectura y presentacion. Si esta OFF vuelve el "
            "vocabulario unico de Azure DevOps."
        ),
        group="global",
        env_only=False,
    ),
    FlagSpec(
        key="STACKY_ADO_ONLY_TABS_GATED_ENABLED",
        default=True,
        type="bool",
        label="Las pantallas que solo funcionan con Azure DevOps se deshabilitan (Plan 282)",
        description=(
            "Plan 282 F7 - Si esta ON, en un proyecto que no usa Azure DevOps los accesos "
            "a PM, Sprint Board y Estadisticas por usuario aparecen deshabilitados con "
            "el motivo en el globo de ayuda, en vez de llevar a una pantalla que "
            "responde 'solo disponible para proyectos Azure DevOps'. No se ocultan: "
            "ocultarlos romperia el enlace directo. Si esta OFF, nada se deshabilita."
        ),
        group="global",
        env_only=False,
    ),
    FlagSpec(
        key="STACKY_GITLAB_DEEP_LINKS_ENABLED",
        default=True,  # promovida a default ON (operador 2026-07-10, curada en _CURATED_DEFAULTS_ON)
        type="bool",
        label="Deep links GitLab bidireccionales (Plan 75)",
        description=(
            "Plan 75 — Si ON, habilita la composición de deep links GitLab (issue, MR, "
            "commit, épica) en el backend. Con OFF, item_url/mr_url/commit_url/epic_url "
            "del provider GitLab devuelven None y el frontend muestra el ID como texto plano. "
            "Default ON. Activa cuando el proyecto use GitLab y quieras links clickeables."
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
        default=True,  # Plan 239 F0 — promovida a ON; curada en _CURATED_DEFAULTS_ON
        label="Shell DevOps minimalista (Plan 119)",
        description=(
            "Plan 119 — Reemplaza el shell del panel DevOps (header, sub-tabs y "
            "selector de servidor) por un diseño minimalista que usa los tokens de "
            "theme.css, y la sección Servidores por una tabla. Solo presentación: "
            "cero cambios de comportamiento. Default ON (plan 239 F0): con la flag "
            "apagada la UI vuelve al shell legacy."
        ),
        group="global",
        env_only=False,
        requires="STACKY_DEVOPS_PANEL_ENABLED",  # profundidad 1 (master del panel, no una flag hija)
    ),
    # ── Plan 239 — Cockpit DevOps ─────────────────────────────────────────────
    FlagSpec(
        key="STACKY_DEVOPS_COCKPIT_ENABLED",
        type="bool",
        default=True,  # curada en _CURATED_DEFAULTS_ON (test_harness_flags.py:467)
        label="Cockpit DevOps (Plan 239)",
        description=(
            "Plan 239 — Agrega la sección Resumen del panel DevOps (KPIs de despliegue "
            "y CI, alertas determinísticas, actividad reciente y tendencia de 14 días), "
            "agrupa las secciones en 4 clusters navegables y hace cada sección "
            "direccionable por URL (/devops/<seccion>). Solo lectura: no ejecuta "
            "despliegues, pipelines ni comandos remotos. OFF = panel del plan 119."
        ),
        group="global",
        env_only=False,
        requires="STACKY_DEVOPS_PANEL_ENABLED",  # profundidad 1 (master del panel)
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
    # ── Plan 157 — Comparador de BD: configuración en contexto, import web.config
    # (agente local determinista) y Panel de Migración siempre visible. 3 flags de
    # UX bajo el master 122, default ON (curadas en _CURATED_DEFAULTS_ON). ──
    FlagSpec(
        key="STACKY_DB_COMPARE_CONFIG_IN_PLACE_ENABLED",
        type="bool", default=True, requires="STACKY_DB_COMPARE_ENABLED",
        label="Configurar ambientes desde el propio Comparador",
        description="Muestra el alta/edición guiada de ambientes de BD dentro del Comparador (arriba de todo), no en una pantalla aparte.",
        group="comparador_bd",
    ),
    FlagSpec(
        key="STACKY_DB_COMPARE_WEBCONFIG_IMPORT_ENABLED",
        type="bool", default=True, requires="STACKY_DB_COMPARE_ENABLED",
        label="Autodetectar conexión desde web.config",
        description="Permite elegir un archivo web.config/XMLConfig y autodetectar las connection strings para precargar el ambiente. El parseo es local; la contraseña se enmascara y se guarda en el Administrador de credenciales de Windows.",
        group="comparador_bd",
    ),
    FlagSpec(
        key="STACKY_DB_COMPARE_MIGRATION_PANEL_ENABLED",
        type="bool", default=True, requires="STACKY_DB_COMPARE_ENABLED",
        label="Panel de Migración de BD siempre visible",
        description="Muestra un panel persistente de scripts de paridad + backups por corrida, sin pegar el run_id a mano.",
        group="comparador_bd",
    ),
    # ── Plan 183 — Comparador de BD: sandbox de demostración (par sqlite RS-like) ──
    FlagSpec(
        key="STACKY_DB_COMPARE_DEMO_ENABLED",
        type="bool",
        default=True,  # default ON: nada corre solo (seed/delete son por click), sqlite es stdlib, jamás toca una BD real (curada en _CURATED_DEFAULTS_ON).
        label="Comparador BD: sandbox de demostración",
        description=(
            "Par de ambientes sqlite de ejemplo (test-demo-dev/test-demo-test, prefijo "
            "reservado al sandbox) con drift RS-like, sembrado y quitado con un click. "
            "Nada corre solo; jamás toca una BD real. OFF = endpoints 403 y cero UI "
            "(los ambientes ya sembrados persisten como ambientes normales)."
        ),
        group="global",
        requires="STACKY_DB_COMPARE_ENABLED",
    ),
    # ── Plan 179 — Fidelidad Snapshot v2 (tipos exactos + defaults normalizados) ──
    FlagSpec(
        key="STACKY_DB_COMPARE_SNAPSHOT_V2_ENABLED",
        type="bool",
        default=True,  # ON: mejora invisible read-only del motor; los snapshots nuevos capturan type_detail. OFF: captura byte-idéntica a v1. El diff es pasivo por versión (usa v2 sii ambos snapshots lo traen).
        label="Comparador BD: snapshot v2 (fidelidad de tipos)",
        description="Captura estructurada por columna (precision, scale, length, collation, identity, computed cuando el dialecto los reporta) y diff quirúrgico con defaults normalizados. OFF = snapshots v1 idénticos a antes.",
        group="global",
        requires="STACKY_DB_COMPARE_ENABLED",
    ),
    # ── Plan 182 — Scripts de datos v2: MERGE idempotente por dialecto ────────
    FlagSpec(
        key="STACKY_DB_COMPARE_DATA_MERGE_ENABLED",
        type="bool",
        default=True,  # ON: mejora invisible del ARTEFACTO generado (upsert set-based idempotente); nada se ejecuta solo, el operador sigue revisando/ejecutando. OFF = bundle byte-idéntico a v1 (data_insert). Curada en _CURATED_DEFAULTS_ON.
        label="Comparador BD: scripts de datos v2 (MERGE idempotente)",
        description="Emite un MERGE/upsert set-based por tabla para filas faltantes + UPDATE con guard anti-no-op NULL-safe; DELETE por PK intacto. Re-ejecutar las piezas DML es seguro y convergente. OFF = scripts v1 (INSERT idempotente por fila).",
        group="global",
        requires="STACKY_DB_COMPARE_ENABLED",
    ),
    # ── Plan 181 — Masking determinista de secretos/PII en el data-diff ───────
    FlagSpec(
        key="STACKY_DB_COMPARE_MASKING_ENABLED",
        type="bool",
        default=True,  # presentación protegida por default; revelar = 1 click persistido (HITL); ninguna excepción dura aplica. OFF = respuesta del run byte-idéntica a main. Curada en _CURATED_DEFAULTS_ON.
        label="Comparador BD: masking de secretos en el data-diff",
        description="Enmascara por default los valores de columnas sensibles (password/token/connection string) en las respuestas de presentación del data-diff; el motor, el disco y los scripts DML del bundle quedan intactos. Revelar una columna es 1 click humano persistido. OFF = respuesta cruda byte-idéntica a v1.",
        group="global",
        requires="STACKY_DB_COMPARE_ENABLED",
    ),
    # ── Plan 266 — Forma garantizada del summary de las corridas ───────────────
    FlagSpec(
        key="STACKY_DB_COMPARE_SUMMARY_SHAPE_ENABLED",
        type="bool",
        default=True,  # normalización SOLO-LECTURA y en memoria; no escribe disco ni sistema del operador ⇒ ON. OFF = payload byte-idéntico a antes del plan 266. Curada en _CURATED_DEFAULTS_ON.
        label="Comparador BD: forma garantizada del summary",
        description="Completa en memoria los contadores faltantes del resumen de una comparación (by_severity/by_action/by_object_type) antes de devolverlo, para que una corrida vieja o interrumpida no rompa la pestaña. OFF = summary tal cual está guardado en disco.",
        group="comparador_bd",
        requires="STACKY_DB_COMPARE_ENABLED",
    ),
    # ── Plan 178 — Radar de ambientes (vigía de drift + matriz N×N + baseline) ──
    FlagSpec(
        key="STACKY_DB_COMPARE_RADAR_ENABLED",
        type="bool",
        default=True,  # ON: matriz/baseline/tendencia/avisos solo LEEN datos locales; el vigía per-par nace OFF y se enciende con 1 click (aprobación humana explícita — excepción dura 3: credenciales/conectividad a BD del cliente no garantizadas). Curada en _CURATED_DEFAULTS_ON.
        label="Comparador BD: radar de ambientes",
        description="Radar continuo (plan 178): matriz N×N de drift por par, baseline pinneado, tendencia y avisos locales. El vigía programado por par se activa con un click en la UI. OFF = todo invisible y el loop de fondo en no-op.",
        group="global",
        requires="STACKY_DB_COMPARE_ENABLED",
    ),
    FlagSpec(
        key="STACKY_DB_COMPARE_WATCH_INTERVAL_MIN",
        type="int",
        label="Comparador BD: intervalo del vigía (min)",
        description="Cada cuántos minutos el vigía re-corre snapshot+diff de esquema de cada par vigilado. Default 60.",
        group="global",
        # NO default= acá: mismo gotcha que STACKY_DB_COMPARE_CONNECT_TIMEOUT_SEC
        # (Plan 122) — default_is_known() trata cualquier spec.default no-None como
        # "curado" y exige alta en _CURATED_DEFAULTS_ON, set reservado a promociones
        # bool=True. El valor real "60" vive en config.py.
        requires="STACKY_DB_COMPARE_ENABLED",
        min_value=5,
        max_value=1440,
    ),
    FlagSpec(
        key="STACKY_DB_COMPARE_WATCH_MAX_RUNS_PER_DAY",
        type="int",
        label="Comparador BD: presupuesto del vigía (corridas/día)",
        description="Cap duro de corridas lanzadas por el vigía por día calendario UTC, sumando todos los pares vigilados. Default 48.",
        group="global",
        # NO default= acá: mismo gotcha que arriba; el valor real "48" vive en config.py.
        # max_value=100 y no más (fix C5): el conteo diario se computa desde los runs
        # retenidos (_MAX_RUNS_KEPT=100, services/dbcompare_runs.py:32) — un presupuesto
        # mayor a la retención sería incontable y por lo tanto una promesa falsa.
        requires="STACKY_DB_COMPARE_ENABLED",
        min_value=1,
        max_value=100,
    ),
    # ── Plan 180 — Puente diff→repo: índice de scripts SQL ticketeados ────────
    FlagSpec(
        key="STACKY_DB_COMPARE_REPO_BRIDGE_ENABLED",
        type="bool",
        default=True,  # read-only sobre archivos LOCALES del workspace ya configurado; sin credenciales, sin red, sin acciones automáticas => ninguna excepción dura aplica. Sin workspace o sin .sql => no-op inocuo. Curada en _CURATED_DEFAULTS_ON.
        label="Comparador BD: puente al repo (scripts ticketeados)",
        description="Indexa (solo lectura) los scripts .sql ticketeados del workspace del proyecto activo y muestra qué ítems del diff ya tienen script candidato. Solo informa: nunca excluye, edita ni ejecuta nada.",
        group="global",
        requires="STACKY_DB_COMPARE_ENABLED",
    ),
    FlagSpec(
        key="STACKY_DB_COMPARE_REPO_BRIDGE_GLOBS",
        type="csv",
        label="Comparador BD: patrones de scripts del repo (CSV)",
        description="Globs relativos al workspace_root del proyecto activo donde viven los .sql ticketeados. Default: trunk/BD/**/*.sql,**/BD/**/*.sql (convención del prior art). Patrones absolutos, con ':' o con '..' se ignoran (log).",
        group="global",
        # NO default= acá: mismo gotcha que STACKY_DB_COMPARE_CONNECT_TIMEOUT_SEC
        # (Plan 122) — default_is_known() trata cualquier spec.default no-None como
        # "curado" y ese set es reservado a bools True. El valor real vive en config.py.
        requires="STACKY_DB_COMPARE_ENABLED",
    ),
    FlagSpec(
        key="STACKY_DB_COMPARE_REPO_BRIDGE_MAX_FILES",
        type="int",
        label="Comparador BD: máx. archivos escaneados por refresh",
        description="Cap duro de archivos .sql procesados por escaneo del puente al repo; excedente = índice truncado REPORTADO. Default 5000.",
        group="global",
        # NO default= acá: mismo gotcha; el valor real "5000" vive en config.py.
        requires="STACKY_DB_COMPARE_ENABLED",
        min_value=100,
        max_value=50000,
    ),
    # ── Plan 212 F6 — Descubrimiento vivo de modelos del CLI ──────────────────
    FlagSpec(
        key="STACKY_MODEL_PROBE_ENABLED",
        type="bool",
        default=True,
        label="Descubrir modelos preguntándole al CLI instalado",
        description=(
            "Plan 212 — Completa el catálogo de Claude Code con lo que el CLI "
            "realmente instalado declara, en vez de depender solo de un archivo "
            "fechado. Costo de tokens CERO: solo usa subcomandos de listado, "
            "nunca invoca un modelo. Corre una vez cada 5 minutos y, ante "
            "cualquier problema, deja el catálogo del archivo intacto."
        ),
        group="global",
    ),
    # ── Plan 264 — herramienta/modelo/effort elegibles en todo punto de uso ──
    FlagSpec(
        key="STACKY_RUNTIME_CAPABILITIES_ENABLED",
        type="bool", default=True,   # Curada en tests/test_harness_flags.py:467.
        label="Matriz unica de capacidades de runtime",
        description=(
            "Plan 264 — Una sola fuente para 'que modelos y efforts admite cada "
            "herramienta y como degrada'. Reemplaza las 12 copias de la lista de "
            "efforts. Calculo puro sobre el catalogo ya cacheado."
        ),
        group="global",
    ),
    FlagSpec(
        key="STACKY_CODEX_EFFORT_PARITY_ENABLED",
        type="bool", default=True,   # Curada en tests/test_harness_flags.py:467.
        label="El effort elegido llega tambien a Codex",
        description=(
            "Plan 264 — Codex no tiene --effort: el esfuerzo elegido se traduce a "
            "una fraccion del cap de turnos, siempre POR DEBAJO del cap. Hoy se "
            "descarta en silencio (agent_runner.py:442-450). Solo aplica a corridas "
            "que el operador lanza; no enciende ningun proceso de fondo."
        ),
        group="global",
        requires="STACKY_RUNTIME_CAPABILITIES_ENABLED",   # → _REQUIRES_MAP_FROZEN
    ),
    FlagSpec(
        key="STACKY_RUN_SELECTION_PREFS_ENABLED",
        type="bool", default=True,   # Curada en tests/test_harness_flags.py:467.
        label="Recordar herramienta/modelo/effort por proyecto",
        description=(
            "Plan 264 — La ultima eleccion del operador se guarda en el archivo de "
            "preferencias de Stacky (api/preferences.py) y se preselecciona la "
            "proxima vez. Un override explicito siempre gana. Requiere que el store "
            "de preferencias de UI este activo (STACKY_UI_SAVED_VIEWS_ENABLED)."
        ),
        group="global",
        requires="STACKY_RUNTIME_CAPABILITIES_ENABLED",   # → _REQUIRES_MAP_FROZEN
    ),
    FlagSpec(
        key="STACKY_MODEL_PICKER_EVERYWHERE_ENABLED",
        type="bool", default=True,   # Curada en tests/test_harness_flags.py:467.
        label="Selector de modelo/effort en todas las pantallas",
        description=(
            "Plan 264 — El mismo ModelEffortPicker (Plan 212 F4) en el tablero de "
            "planes, la bandeja de incidencias y las secciones DevOps, en vez de un "
            "selector distinto hecho a mano en cada pantalla."
        ),
        group="global",
        requires="STACKY_RUNTIME_CAPABILITIES_ENABLED",   # → _REQUIRES_MAP_FROZEN
    ),
    # ── Plan 176 — Triage curado, gates read-only y UX v2 del comparador ──────
    FlagSpec(
        key="STACKY_DB_COMPARE_TRIAGE_ENABLED",
        type="bool",
        default=True,
        label="Comparador BD: triage del diff (curar qué migrar)",
        description=(
            "Permite marcar cada diferencia como confirmada o excluida con nota; "
            "los scripts respetan la curación y habilita la verificación de cierre "
            "de migración."
        ),
        group="comparador_bd",
        requires="STACKY_DB_COMPARE_ENABLED",
    ),
    FlagSpec(
        key="STACKY_DB_COMPARE_GATES_ENABLED",
        type="bool",
        default=True,
        label="Comparador BD: gates de precondiciones (solo lectura)",
        description=(
            "Deriva consultas SELECT de verificación previa para cambios riesgosos "
            "(NOT NULL, PK, UNIQUE) y permite ejecutarlas read-only con un click "
            "para ver pass/fail antes de migrar."
        ),
        group="comparador_bd",
        requires="STACKY_DB_COMPARE_ENABLED",
    ),
    FlagSpec(
        key="STACKY_DB_COMPARE_TABLE_PREFS_ENABLED",
        type="bool",
        default=True,
        label="Comparador BD: tablas de parámetro y claves naturales",
        description=(
            "Permite marcar tablas de parámetro (preseleccionadas al comparar datos) "
            "y definir una clave natural para tablas sin PK."
        ),
        group="comparador_bd",
        requires="STACKY_DB_COMPARE_ENABLED",
    ),
    FlagSpec(
        key="STACKY_DB_COMPARE_DIFF_UX_V2_ENABLED",
        type="bool",
        default=True,
        label="Comparador BD: diff UX v2 (filtros múltiples, export, snapshots)",
        description=(
            "Filtro multi-tipo, export CSV/JSON del diff filtrado, diff por líneas "
            "en vistas y comparación de snapshots históricos."
        ),
        group="comparador_bd",
        requires="STACKY_DB_COMPARE_ENABLED",
    ),
    # ── Plan 139 — App Shell v2 (sidebar agrupada + TopBar + iconografía) ────
    # PROMOVIDA a default ON (operador 2026-07-18): es la presentación de
    # fábrica. Curada en _CURATED_DEFAULTS_ON (test_default_known_only_for_curated
    # exige la pertenencia al set); el default efectivo True vive también en
    # config.py. El operador puede volver al topnav apagando la flag por UI.
    FlagSpec(
        key="STACKY_UI_SHORTCUTS_ENABLED",
        type="bool",
        default=True,
        label="Atajos de teclado y ayuda con ?",
        description=(
            "Plan 172 — Registro único de atajos: lo que está registrado es lo que "
            "funciona y lo que muestra el overlay de ayuda (?), sin listas escritas a "
            "mano que mientan. Agrega navegación de listas con j/k y foco roving. "
            "Default ON. Apagala y quedan solo los 3 atajos de siempre."
        ),
        group="global",
    ),
    FlagSpec(
        key="STACKY_MODEL_PICKER_IN_BOARD_ENABLED",
        type="bool",
        default=True,
        label="Selector de modelo/effort en el tablero de tickets",
        description=(
            "Plan 212 — muestra el selector de modelo y effort al lanzar agentes sobre "
            "tickets ADO. OFF = el tablero lanza con el default del backend "
            "(comportamiento pre-212)."
        ),
        group="global",
    ),
    FlagSpec(
        key="STACKY_UI_SAVED_VIEWS_ENABLED",
        type="bool",
        default=True,
        label="Vistas guardadas y preferencias de tabla",
        description=(
            "Plan 173 — Presets nombrados de filtros por pantalla y preferencias de columnas persistidas en el backend. Default ON. Apagala y cada pantalla vuelve a arrancar con sus filtros por defecto, como antes."
        ),
        group="global",
    ),
    FlagSpec(
        key="STACKY_UI_VIRTUALIZATION_ENABLED",
        type="bool",
        default=True,
        label="Virtualización de listas largas",
        description=(
            "Plan 174 — Renderiza solo las filas visibles en las listas largas (logs y diff). Default ON. Apagala y se vuelve a renderizar la lista entera."
        ),
        group="global",
    ),
    FlagSpec(
        key="STACKY_UI_PREFETCH_ENABLED",
        type="bool",
        default=True,
        label="Prefetch del detalle al pasar el mouse",
        description=(
            "Plan 174 — Precarga el detalle de una ejecución al hacer hover o foco, con presupuesto acotado. Default ON. Apagala y el detalle se pide recién al abrir."
        ),
        group="global",
    ),
    FlagSpec(
        key="STACKY_UI_INSTANT_NAV_ENABLED",
        type="bool",
        default=True,
        label="Navegación sin parpadeo",
        description=(
            "Plan 174 — Mantiene los datos anteriores mientras llega la página nueva, en vez de vaciar la tabla. Default ON."
        ),
        group="global",
    ),
    FlagSpec(
        key="STACKY_UI_PEEK_ENABLED",
        type="bool",
        default=True,
        label="Vista previa al hover sostenido",
        description=(
            "Plan 175 — Tarjeta flotante con lo esencial de una ejecución o ticket sin abrir el detalle. Default ON."
        ),
        group="global",
    ),
    FlagSpec(
        key="STACKY_UI_CONTEXT_MENU_ENABLED",
        type="bool",
        default=True,
        label="Menú contextual y acciones rápidas",
        description=(
            "Plan 175 — Clic derecho sobre una fila abre las acciones de esa entidad, y las seguras aparecen inline al hover. Default ON. Nada destructivo sin confirmar."
        ),
        group="global",
    ),
    FlagSpec(
        key="STACKY_UI_SHELL_V2_ENABLED",
        type="bool",
        label="Shell v2: navegación lateral agrupada",
        description=(
            "Plan 139 — Reemplaza la fila de pestañas superior por una barra lateral "
            "agrupada por temas (Trabajo, Observabilidad, Conocimiento, Plataforma, "
            "Configuración) con iconografía y una barra superior renovada. Default ON: "
            "es la presentación de fábrica. Apagala para volver al topnav clásico. Solo "
            "cambia la presentación; mismas pantallas y misma navegación."
        ),
        group="global",
        default=True,  # promovida a default ON (operador 2026-07-18, curada en _CURATED_DEFAULTS_ON)
    ),
    # ── Plan 187 — Selección múltiple y acciones en lote ──────────────────────
    FlagSpec(
        key="STACKY_BULK_ACTIONS_ENABLED",
        type="bool",
        label="Selección múltiple y acciones en lote",
        description=(
            "Plan 187 — Checkboxes por fila, rango con Shift, barra flotante de "
            "acciones en lote y resultado agregado en Bandeja de revisión e "
            "Historial. OFF = interfaz idéntica a la actual."
        ),
        group="global",
        default=True,  # default ON (ninguna de las 4 excepciones duras aplica; curada en _CURATED_DEFAULTS_ON)
    ),
    # ── Plan 121 — Centinela local de egreso ──────────────────────────────────
    FlagSpec(
        key="STACKY_EGRESS_SENTINEL_ENABLED",
        type="bool",
        label="Centinela de egreso (IA local)",
        description="Centinela de egreso: auditoría semántica de secretos/PII con la IA local sobre los prompts salientes de las ejecuciones (advisory, nunca bloquea).",
        group="global",
        # SIN default= (no curada en _CURATED_DEFAULTS_ON; el default efectivo OFF vive en config.py — gotcha Plan 63/81).
        # SIN requires= estático hacia LOCAL_LLM_ENABLED: la dependencia se chequea en runtime (R4 prohíbe cadenas), patrón plan 117.
    ),
    FlagSpec(
        key="STACKY_EGRESS_SENTINEL_MAX_PER_CYCLE",
        type="int",
        label="Centinela de egreso: máximo por ciclo",
        description="Tope de ejecuciones auditadas por ciclo del barrido del centinela de egreso.",
        group="global",
        requires="STACKY_EGRESS_SENTINEL_ENABLED",
        min_value=1,
        max_value=20,
    ),
    FlagSpec(
        key="STACKY_EGRESS_SENTINEL_LOOKBACK_DAYS",
        type="int",
        label="Centinela de egreso: ventana (días)",
        description="Solo se auditan ejecuciones iniciadas dentro de esta ventana hacia atrás.",
        group="global",
        requires="STACKY_EGRESS_SENTINEL_ENABLED",
        min_value=1,
        max_value=90,
    ),
    FlagSpec(
        key="STACKY_EGRESS_SENTINEL_MAX_CHARS",
        type="int",
        label="Centinela de egreso: tope de caracteres",
        description="Máximo de caracteres del texto que recibe la IA local por auditoría. 0 = sin límite.",
        group="global",
        requires="STACKY_EGRESS_SENTINEL_ENABLED",
        min_value=0,
        max_value=200000,
    ),
    # ── Plan 127 — Reuso IA local: análisis de errores + doctor local DevOps ────
    FlagSpec(
        key="STACKY_EXEC_ERROR_ANALYSIS_ENABLED",
        type="bool",
        label="Análisis de errores con IA local",
        description=(
            "Plan 127 — Botón en el detalle de una ejecución fallida que pide al "
            "modelo local (Plan 106) causa raíz y próximos pasos. Default ON "
            "(directiva del operador 2026-07-12). Requiere el modelo local "
            "habilitado (chequeo en runtime)."
        ),
        group="global",
        env_only=False,
        # SIN requires= estático hacia LOCAL_LLM_ENABLED: la dependencia se chequea
        # en runtime vía _guard() (R4 prohíbe cadenas; precedente harness_flags.py:2684).
        default=True,
    ),
    FlagSpec(
        key="STACKY_DEVOPS_LOCAL_DOCTOR_ENABLED",
        type="bool",
        label="Doctor local DevOps (IA local)",
        description=(
            "Plan 127 — Alternativa gratuita y sin egreso al doctor de sección: "
            "analiza pipeline/environments/publicaciones y fallos de CI con el "
            "modelo local. Nada sale de tu máquina. Default ON (directiva del "
            "operador 2026-07-12)."
        ),
        group="global",
        env_only=False,
        requires="STACKY_DEVOPS_PANEL_ENABLED",
        default=True,
    ),
    # ── Plan 128 — Tablero de evolución de planes (solo lectura) ──────────────
    FlagSpec(
        key="STACKY_PLANS_BOARD_ENABLED",
        type="bool",
        label="Tablero de evolución de planes",
        description=(
            "Tab 'Planes' de solo lectura: estado del pipeline "
            "proponer→criticar→implementar→supervisar por cada plan de docs/, "
            "aprobación del supervisor, commits sin push y acción sugerida copiable."
        ),
        group="global",
        default=True,   # Plan 237: promovido a ON (lectura local, sin egreso). Curado en _CURATED_DEFAULTS_ON.
        # SIN requires= (no tiene master). SIN env_only= (queda UI-editable).
    ),
    # ── Plan 196 — acciones HITL del pipeline de planes sobre el Tablero (128) ──
    FlagSpec(
        key="STACKY_PLANS_PIPELINE_ACTIONS_ENABLED",
        type="bool",
        default=True,
        label="Acciones del pipeline de planes",
        description=(
            "Plan 196 — botones Proponer/Criticar/Implementar/Supervisar en el "
            "Tablero de Planes: lanzan la corrida (Claude Code CLI + skills del "
            "repo) con modelo y effort a eleccion. Siempre con click y "
            "confirmacion; el push sigue siendo manual."
        ),
        group="global",
        requires="STACKY_PLANS_BOARD_ENABLED",
    ),
    # ── Plan 263 — ningun plan sin estado + migracion con evidencia ──────────
    FlagSpec(
        key="STACKY_PLANS_ESTADO_FALLBACK_ENABLED",
        type="bool",
        default=True,   # Curada en _CURATED_DEFAULTS_ON (tests/test_harness_flags.py).
        label="Ningun plan sin estado en el tablero",
        description=(
            "Plan 263 — Un plan cuyo documento no declara **Estado:** se muestra como "
            "IMPLEMENTADO (inferido) en vez de 'Sin estado', para que el tablero le "
            "ofrezca la accion Supervisar. Calculo puro en memoria, no toca el disco."
        ),
        group="global",
        requires="STACKY_PLANS_BOARD_ENABLED",
    ),
    FlagSpec(
        key="STACKY_PLANS_NORMALIZE_PREVIEW_ENABLED",
        type="bool",
        default=True,   # Curada en _CURATED_DEFAULTS_ON (tests/test_harness_flags.py).
        label="Vista previa de normalizacion de estados",
        description=(
            "Plan 263 — Calcula, SOLO EN MEMORIA, que linea **Estado:** habria que "
            "escribir en cada plan sin estado, con la evidencia que la respalda "
            "(ledger, contenido del doc, numero del plan). No escribe nada."
        ),
        group="global",
        requires="STACKY_PLANS_BOARD_ENABLED",
    ),
    FlagSpec(
        key="STACKY_PLANS_NORMALIZE_APPLY_ENABLED",
        type="bool",
        # SIN default=: el default EFECTIVO es el de config.py ("false"). Declararlo
        # aca —aunque fuera default=False— la volveria default_is_known
        # (services/harness_flags.py: `spec.default is not None`; False NO es None) y
        # pondria ROJO a test_default_known_only_for_curated, que exige igualdad EXACTA
        # con el conjunto curado. Precedente identico y ya vivo en este archivo:
        # STACKY_PIPELINE_NL_EDIT_COMMIT_ENABLED (Plan 250).
        #
        # OFF por CATEGORIA (B): escribe en un sistema REAL del operador — los .md de
        # "Stacky Agents"/docs/ en su working tree, que ademas suele tener cambios sin
        # commitear. La escritura vive en
        # services/plans_estado_migration.py::apply_estado_migration.
        label="Aplicar la normalizacion de estados a los .md",
        description=(
            "Plan 263 — Escribe la linea **Estado:** en los planes que no la tienen, "
            "uno por uno, con confirmacion y diff a la vista. Nunca corre sola. "
            "El commit y el push siguen siendo manuales."
        ),
        group="global",
        requires="STACKY_PLANS_BOARD_ENABLED",
    ),
    # ── Plan 167 — Centro de Evolución (serie auto-mejora recursiva 1/4) ──
    FlagSpec(
        key="STACKY_EVOLUTION_CENTER_ENABLED",
        type="bool", default=True,
        label="Centro de Evolución",
        description="Panel de auto-mejora de Stacky: aspectos mejorables, propuestas con aprobación humana, ciclo MAPE on-demand, ledger auditable y rollback 1-click.",
        group="global",
    ),
    FlagSpec(
        key="STACKY_EVOLUTION_CYCLE_ENABLED",
        type="bool", default=True,
        label="Ciclo MAPE on-demand",
        description="Habilita el botón 'Correr ciclo': lee la telemetría existente (costos, ejecuciones, incidencias, tablero de planes) y emite borradores de propuesta. Nunca aplica nada solo.",
        group="global", requires="STACKY_EVOLUTION_CENTER_ENABLED",
    ),
    # ── Plan 237 — Triage de planes dentro del Centro de Evolución ──
    FlagSpec(
        key="STACKY_EVOLUTION_PLANS_TRIAGE_ENABLED",
        type="bool", default=True,
        label="Planes en el Centro de Evolución",
        description="Sección de solo lectura que lista TODOS los planes de docs/ agrupados por triage: primero los que faltan implementar, después los que faltan criticar, después los completados.",
        group="global", requires="STACKY_EVOLUTION_CENTER_ENABLED",
    ),
    FlagSpec(
        key="STACKY_EVOLUTION_AUTO_APPLY_KNOWLEDGE_ENABLED",
        type="bool",
        label="Auto-aplicar lecciones de conocimiento (human-on-the-loop)",
        description="SOLO lecciones de conocimiento reversibles: el ciclo las aplica solo y vos auditás/revertís después. Apagada por defecto porque saltea la revisión previa.",
        group="global", requires="STACKY_EVOLUTION_CENTER_ENABLED",
        # SIN default= (C1): default_is_known() no distingue por type; un default
        # explícito rompería test_default_known_only_for_curated. Default EFECTIVO OFF en config.py.
    ),
    FlagSpec(
        key="STACKY_EVOLUTION_CYCLE_TOKEN_BUDGET",
        type="int",
        label="Presupuesto de tokens por ciclo",
        description="Tope de tokens estimados que una corrida del ciclo puede mandar al modelo local (default 20000, definido en config). Si las señales exceden el tope, se truncan y el ciclo lo deja registrado.",
        group="global", requires="STACKY_EVOLUTION_CENTER_ENABLED",
        # SIN default= (C1): int nunca va a _CURATED_DEFAULTS_ON (G4). Default EFECTIVO 20000 en config.py.
    ),
    # ── Plan 168 — Arnés de fitness (serie auto-mejora recursiva 2/4) ──
    FlagSpec(
        key="STACKY_EVAL_HARNESS_ENABLED",
        type="bool", default=True,
        label="Arnés de fitness de agentes",
        description="Golden tasks por agente con jerarquía de señal (deterministas > ejecución > juez LLM), scorecards con tendencia y fitness before/after de las propuestas del Centro de Evolución.",
        group="global", requires="STACKY_EVOLUTION_CENTER_ENABLED",
    ),
    FlagSpec(
        key="STACKY_EVAL_JUDGE_ENABLED",
        type="bool", default=True,
        label="Juez LLM local de evals",
        description="Evalúa artefactos con el modelo local y rubricas versionadas, emitiendo score y crítica textual. Sin endpoint local configurado, el arnés corre igual solo con señales deterministas.",
        group="global", requires="STACKY_EVOLUTION_CENTER_ENABLED",
    ),
    FlagSpec(
        key="STACKY_EVAL_RUN_TOKEN_BUDGET",
        type="int",
        label="Presupuesto de tokens por corrida de evals",
        description="Tope de tokens estimados que una corrida puede mandar al juez local (default efectivo: 30000, definido en config.py). Al agotarse, los casos con juez restantes quedan como omitidos y la corrida lo registra.",
        group="global", requires="STACKY_EVOLUTION_CENTER_ENABLED",
        # C10: SIN default= — default_is_known es type-agnostic (harness_flags.py:3397) y
        # los ints no se curan (G4); el default efectivo 30000 vive en config.py.
    ),
    # ── Plan 169 — Optimizador evolutivo (serie auto-mejora recursiva 3/4) ──
    FlagSpec(
        key="STACKY_EVOLUTION_OPTIMIZER_ENABLED",
        type="bool", default=True,
        label="Optimizador evolutivo de prompts",
        description="Habilita el botón 'Optimizar' del Centro de Evolución: genera variantes de un prompt de agente con mutación reflexiva, las evalúa con el arnés de fitness y emite una propuesta que vos aprobás. Nunca aplica nada solo.",
        group="global", requires="STACKY_EVOLUTION_CENTER_ENABLED",
    ),
    FlagSpec(
        key="STACKY_EVOLUTION_OPTIMIZER_GENERATOR",
        type="str",  # SIN default= (C14: efectivo "auto" en config.py; gotcha :3397)
        label="Generador de variantes",
        description="Quién redacta las variantes: 'auto' usa el modelo local si está configurado y si no el runtime de agentes; 'local' exige modelo local; 'runtime' usa Codex/Claude/Copilot.",
        group="global", requires="STACKY_EVOLUTION_CENTER_ENABLED",
    ),
    FlagSpec(
        key="STACKY_EVOLUTION_OPTIMIZER_VARIANTS",
        type="int",  # SIN default= (C14: efectivo 3 en config.py)
        label="Variantes por corrida (K)",
        description="Cuántas variantes genera y evalúa una corrida de optimización. Más variantes = más señal y más tokens.",
        group="global", requires="STACKY_EVOLUTION_CENTER_ENABLED",
    ),
    FlagSpec(
        key="STACKY_EVOLUTION_OPTIMIZER_TOKEN_BUDGET",
        type="int",  # SIN default= (C14: efectivo 60000 en config.py)
        label="Presupuesto de tokens por corrida del optimizador",
        description="Tope de tokens estimados que una corrida puede gastar generando variantes. Al agotarse, la corrida se detiene y lo registra.",
        group="global", requires="STACKY_EVOLUTION_CENTER_ENABLED",
    ),
    FlagSpec(
        key="STACKY_EVOLUTION_OPTIMIZER_MIN_MARGIN_PCT",
        type="int",  # SIN default= (C14: efectivo 2 en config.py)
        label="Margen mínimo de mejora (centésimas de score)",
        description="Cuánto debe superar la mejor variante al artefacto actual para que se emita una propuesta. 2 significa 0.02 puntos de score.",
        group="global", requires="STACKY_EVOLUTION_CENTER_ENABLED",
    ),
    # ── Plan 170 — Flywheel de conocimiento (serie auto-mejora recursiva 4/4) ──
    FlagSpec(
        key="STACKY_KNOWLEDGE_FLYWHEEL_ENABLED",
        type="bool", default=True,
        label="Flywheel de conocimiento",
        description="Lecciones aprendidas de incidencias resueltas y mejoras verificadas: cosecha con tu aprobación, panel con uso e impacto, y retiro con un click.",
        group="global", requires="STACKY_EVOLUTION_CENTER_ENABLED",
    ),
    FlagSpec(
        key="STACKY_KNOWLEDGE_INJECTION_ENABLED",
        type="bool", default=True,
        label="Inyectar lecciones al contexto de agentes",
        description="Agrega a cada corrida un bloque acotado con las lecciones activas que aplican al agente y al proyecto. Con tope duro de tamaño; apagalo si un prompt se comporta raro.",
        group="global", requires="STACKY_EVOLUTION_CENTER_ENABLED",
    ),
    FlagSpec(
        key="STACKY_KNOWLEDGE_INJECT_TOP_N",
        type="int",  # SIN default= (C14: efectivo 3 en config.py)
        label="Lecciones por corrida (top-N)",
        description="Cuántas lecciones, ordenadas por relevancia al ticket, entran al contexto de una corrida. (default 3)",
        group="global", requires="STACKY_EVOLUTION_CENTER_ENABLED",
    ),
    FlagSpec(
        key="STACKY_KNOWLEDGE_INJECT_MAX_CHARS",
        type="int",  # SIN default= (C14: efectivo 4000 en config.py)
        label="Tope de caracteres del bloque de lecciones",
        description="Límite duro del tamaño del bloque de lecciones en el prompt. El prompt nunca crece sin control por conocimiento acumulado. (default 4000)",
        group="global", requires="STACKY_EVOLUTION_CENTER_ENABLED",
    ),
    FlagSpec(
        key="STACKY_KNOWLEDGE_MAX_LESSONS",
        type="int",  # SIN default= (C14: efectivo 200 en config.py)
        label="Cap del corpus de lecciones",
        description="Al superarlo, el panel sugiere retirar las lecciones menos usadas (LRU). Solo sugiere: retirar siempre es tu decisión. (default 200)",
        group="global", requires="STACKY_EVOLUTION_CENTER_ENABLED",
    ),
    # ── Plan 129 — Paleta global: búsqueda profunda multi-fuente ──
    FlagSpec(
        key="STACKY_PALETTE_DEEP_SEARCH_ENABLED",
        type="bool",
        label="Búsqueda profunda en la paleta (Ctrl+K)",
        description="Plan 129 — La paleta de comandos busca también ejecuciones, documentos, servidores DevOps y flags vía /api/search/global (local, sin IA). OFF = paleta actual sin cambios.",
        group="global",
        # Promovida a default ON (barrido del operador 2026-07-27): busqueda LOCAL sin
        # IA, solo lectura, y solo corre cuando el operador abre la paleta y tipea.
        # Cero tokens en reposo, cero escritura.
        # Curada en _CURATED_DEFAULTS_ON (test_default_known_only_for_curated).
        default=True,
    ),
    FlagSpec(
        key="STACKY_CODE_INTEGRITY_ENABLED",
        type="bool",
        label="Verificador de integridad de código",
        description=(
            "Gate determinista pre-publicación: sintaxis (ast.parse) e imports de "
            "primera parte de todo el backend, en segundos, sin ejecutar código y sin IA. "
            "Expone GET /api/diag/code-integrity y la card en Diagnóstico."
        ),
        group="global",
        default=True,  # Default ON (activado 2026-07-13, decisión explícita del operador — patrón triple Plan 127 §3.6)
    ),
    FlagSpec(
        key="STACKY_INCIDENT_RESOLVER_ENABLED",
        type="bool",
        label="Resolutor de incidencias multimodal (Plan 131)",
        description=(
            "Plan 131 — Botón 'Resolver incidencia' en Tickets: el operador carga fotos, "
            "archivos y texto libre; el agente unificado IncidentAnalyst (negocio + "
            "funcional + técnico en una pasada) desglosa la incidencia dev-ready; Stacky "
            "publica el Issue en el tracker linkeado a su épica, sube los archivos como "
            "attachments y escribe el doc del incidente en el grafo documental. "
            "Publicación siempre con preview y confirmación del operador. Default ON "
            "(promovida 2026-07-15, patrón capacidades_optin: botón invocado a mano, "
            "sin costo ni publicación automática)."
        ),
        group="global",
        default=True,
        env_only=False,
    ),
    # ── Plan 200 — consola por incidencia, marcado de despliegue SQL y ejecución ──
    FlagSpec(
        key="STACKY_INCIDENT_CONSOLE_ENABLED",
        type="bool", default=True,
        label="Consola del agente por incidencia",
        description=(
            "Muestra en el detalle de cada incidencia el transcript de lo que respondió "
            "el agente (análisis y dev-resolutor). Read-only: reusa la consola de "
            "ejecuciones, no agrega un canal nuevo."
        ),
        group="global", requires="STACKY_INCIDENT_RESOLVER_ENABLED",
    ),
    FlagSpec(
        key="STACKY_SQL_DEPLOY_DETECT_ENABLED",
        type="bool", default=True,
        label="Marcado de despliegue SQL en tickets e incidencias",
        description=(
            "Detecta de forma determinista cuándo un ticket o incidencia implica "
            "desplegar scripts SQL en otros ambientes y lo avisa con un badge. Read-only."
        ),
        group="global", requires="STACKY_INCIDENT_RESOLVER_ENABLED",
    ),
    FlagSpec(
        key="STACKY_SQL_EXEC_LEDGER_ENABLED",
        type="bool", default=True,
        label="Bitácora de ejecuciones SQL por ambiente",
        description=(
            "Registra localmente cada ejecución SQL (qué script, en qué ambiente, "
            "cuándo, resultado) con cadena de hash, y avisa si un script ya se ejecutó. "
            "Solo metadata local; sin connection strings."
        ),
        group="global", requires="STACKY_DB_COMPARE_ENABLED",
    ),
    FlagSpec(
        key="STACKY_SQL_EXEC_ENABLED",
        type="bool",
        # SIN default= a propósito: declararlo la vuelve "conocida" y el meta-test
        # exige que las conocidas estén en el set curado, que es sólo para bools ON.
        # El default efectivo (False) vive en config.py.
        label="Ejecutar scripts SQL en ambientes (PELIGROSO)",
        description=(
            "Habilita ejecutar DDL/DML contra una BD real desde Stacky. OFF por default: "
            "es una acción destructiva e irreversible y requiere credenciales de "
            "ambientes que no vienen en la instalación default. Cada ejecución exige "
            "confirmación humana explícita."
        ),
        group="global", requires="STACKY_DB_COMPARE_ENABLED",
    ),
    FlagSpec(
        key="STACKY_INCIDENT_TICKET_PERSIST_ENABLED",
        type="bool", default=True,
        label="Persistir Issue de incidencia en Tickets",
        description="Al publicar una incidencia, crea el ticket local de la Issue al instante (no esperás al sync de ADO).",
        group="global", requires="STACKY_INCIDENT_RESOLVER_ENABLED",
    ),
    FlagSpec(
        key="STACKY_INCIDENT_VISION_OCR_ENABLED",
        type="bool", default=True,
        label="Procesar capturas (OCR/visión)",
        description="Extrae el texto de las capturas adjuntas y lo suma al desglose. Si no hay modelo de visión configurado, degrada a marcar la captura como pendiente.",
        group="global", requires="STACKY_INCIDENT_RESOLVER_ENABLED",
    ),
    FlagSpec(
        key="STACKY_INCIDENT_VISION_ENDPOINT", type="str",
        label="Endpoint de visión (OpenAI-compatible)",
        description="URL COMPLETA de chat-completions del endpoint de visión (ej. http://localhost:11434/v1/chat/completions). Mismo contrato que el endpoint del modelo local del Arnés. Vacío = usar ese endpoint local.",
        # requires apunta al ROOT (STACKY_INCIDENT_RESOLVER_ENABLED), NO a
        # STACKY_INCIDENT_VISION_OCR_ENABLED: ese último ya tiene su propio
        # requires, y R4 (harness_flags.py::validate_requires_graph) prohíbe
        # cadenas de profundidad >1. Mismo patrón que STACKY_CODEBASE_MEMORY_MCP_PROJECTS.
        group="global", requires="STACKY_INCIDENT_RESOLVER_ENABLED",
        # SIN default= (verificado: default_is_known() no distingue por type; un
        # default explícito acá también rompería test_default_known_only_for_curated,
        # mismo motivo documentado en LOCAL_LLM_ENDPOINT). El default EFECTIVO vive en config.py.
    ),
    FlagSpec(
        key="STACKY_INCIDENT_VISION_MODEL", type="str",
        label="Modelo de visión",
        description="Nombre del modelo de visión (ej. llama3.2-vision, llava). Vacío = usar el modelo local del Arnés.",
        # Mismo motivo que STACKY_INCIDENT_VISION_ENDPOINT (R4 profundidad 1).
        group="global", requires="STACKY_INCIDENT_RESOLVER_ENABLED",
        # SIN default= (mismo motivo que STACKY_INCIDENT_VISION_ENDPOINT).
    ),
    FlagSpec(
        key="STACKY_INCIDENT_AUTO_PUBLISH_ENABLED",
        type="bool", default=True,
        label="Crear incidencias directo (sin confirmar)",
        description="Publica la Issue apenas el análisis termina, sin pedir confirmación, y permite cargar varias seguidas. Apagalo para volver al paso de revisión manual.",
        group="global", requires="STACKY_INCIDENT_RESOLVER_ENABLED",
    ),
    FlagSpec(
        key="STACKY_INCIDENT_DEV_RESOLVER_ENABLED",
        type="bool", default=True,
        label="Agente Dev Resolutor de Incidencias",
        description="Habilita el botón 'Resolver con agente' en las Issues para que un agente dev analice el repo y proponga el fix.",
        group="global",
    ),
    FlagSpec(
        key="STACKY_INCIDENT_DEV_PR_ENABLED",
        type="bool", default=True,
        label="Abrir PR al resolver incidencias",
        description="Tras resolver una Issue con el agente dev, abre automáticamente un Pull Request con el fix y los tests (podés desmarcar el checkbox al resolver). Requiere el Agente Dev Resolutor.",
        group="global", requires="STACKY_INCIDENT_DEV_RESOLVER_ENABLED",
    ),
    # Plan 152 — Centro de Actividad: campana en la barra superior con un feed
    # de lo que pasó (fines de run, errores de la interfaz, umbrales de costo).
    # Default ON: es una superficie informativa aditiva, sin autonomía ni
    # escritura. OFF oculta la campana y apaga la captura (interfaz idéntica a hoy).
    FlagSpec(
        key="STACKY_NOTIFICATION_CENTER_ENABLED",
        type="bool", default=True,
        label="Centro de notificaciones y actividad",
        description="Muestra una campana en la barra superior con un contador de novedades sin leer y un feed desplegable que reúne fines de ejecución, errores de la interfaz y avisos de costo. Solo informa y navega; nunca ejecuta acciones. Con OFF la barra queda igual que hoy.",
        group="global", env_only=False,
    ),
    # ── Plan 194 — Portapapeles universal ("Copiar como…") ─────────────────────
    FlagSpec(
        key="STACKY_COPY_EXPORT_ENABLED",
        type="bool",
        default=True,  # default ON (ninguna de las 4 excepciones duras aplica: copiar es read-only; curada en _CURATED_DEFAULTS_ON)
        label="Copiar como… (portapapeles universal)",
        description=(
            "Plan 194 — Botones 'Copiar como' (Markdown/CSV/Texto/Tabla ADO) en drawers y tablas. "
            "Solo lectura: copiar nunca muta datos. Default ON; desactivable desde la UI."
        ),
        group="global",
    ),
    # ── Plan 185 — Undo universal (acciones optimistas + gracia de deshacer) ────
    FlagSpec(
        key="STACKY_UNDO_UNIVERSAL_ENABLED",
        type="bool",
        default=True,  # default ON (ninguna de las 4 excepciones duras aplica: la acción la inicia el operador y es cancelable; curada en _CURATED_DEFAULTS_ON)
        label="Undo universal (deshacer con gracia)",
        description=(
            "Plan 185 — Las acciones reversibles se aplican de forma optimista y su efecto real "
            "se difiere una gracia corta (6 s) con un toast 'Deshacer' (y Ctrl+Z). Con OFF el "
            "dashboard se comporta como antes (commit inmediato, sin toast). Default ON; "
            "desactivable desde la UI."
        ),
        group="global",
    ),
    # ── Plan 192 — Resiliencia de conexión dashboard-backend (UI) ──────────────
    FlagSpec(
        key="STACKY_CONNECTION_RESILIENCE_ENABLED",
        type="bool",
        default=True,  # default ON (ninguna de las 4 excepciones duras aplica; curada en _CURATED_DEFAULTS_ON)
        label="Resiliencia de conexion del dashboard",
        description=(
            "Plan 192 - Monitor pasivo de conexion dashboard-backend: banner global "
            "con reintento exponencial durante caidas y re-hidratacion automatica "
            "(refetch de lecturas) al recuperar. Solo observa; nunca reintenta mutaciones."
        ),
        group="global",
    ),
    # ── Plan 218 — Paridad total Azure DevOps ↔ GitLab (sustrato multi-proveedor) ──
    FlagSpec(
        key="STACKY_PROVIDER_PARITY_ENABLED",
        type="bool",
        default=True,  # default ON (ninguna de las 4 excepciones duras aplica; curada en _CURATED_DEFAULTS_ON)
        label="Registro de capacidades por proveedor",
        description=(
            "Plan 218 — Maestra del eje multi-proveedor: expone GET /api/parity/matrix y el "
            "panel de paridad en Diagnósticos, y habilita que el backend consulte qué soporta "
            "el tracker activo ANTES de intentarlo. Es un registro puro leído en proceso: sin "
            "red, sin prerequisitos. Con OFF el endpoint devuelve 404, el panel no se monta y "
            "toda capacidad se considera disponible ⇒ comportamiento byte-idéntico al previo."
        ),
        group="global",
    ),
    FlagSpec(
        key="STACKY_TRACKER_TARGET_PER_PROJECT_ENABLED",
        type="bool",
        default=True,  # default ON (corrección de resolución interna; curada en _CURATED_DEFAULTS_ON)
        label="Destino de tracker por proyecto",
        description=(
            "Plan 218 — Cada proyecto resuelve su propio destino de tracker (URL de instancia, "
            "path de proyecto, grupo y archivo de credenciales) en vez de compartir un único "
            "GitLab global. Si el proyecto no declara nada, cae a la configuración global de "
            "hoy. Con OFF vuelve la ruta legacy, byte-idéntica."
        ),
        group="global",
    ),
    FlagSpec(
        key="STACKY_CANONICAL_VOCABULARY_ENABLED",
        type="bool",
        default=True,  # default ON (cambio puramente aditivo; curada en _CURATED_DEFAULTS_ON)
        label="Vocabulario canónico de tickets",
        description=(
            "Plan 218 — El payload de cada ticket suma los campos neutrales "
            "(external_id, tracker_state, item_url, parent_external_id, assignee, item_type) "
            "SIN quitar los campos ado_* existentes. Es un superconjunto: ningún consumidor "
            "actual se rompe. Con OFF el payload es idéntico al de hoy."
        ),
        group="global",
    ),
    FlagSpec(
        key="STACKY_CAPABILITY_DEGRADATION_ENABLED",
        type="bool",
        default=True,  # default ON (convierte un 500 mudo en un 200 accionable; curada en _CURATED_DEFAULTS_ON)
        label="Degradación declarada por capacidad",
        description=(
            "Plan 218 — Cuando el tracker activo no soporta una capacidad, el endpoint responde "
            "200 con {available:false, capability, reason, workaround} en vez de reventar con "
            "un 500 mudo. Mejora estabilidad y DX; no agrega prerequisitos ni reduce seguridad. "
            "Con OFF vuelve la excepción legacy."
        ),
        group="global",
    ),
    # ── Plan 276 — GitLab self-hosted de punta a punta ────────────────────────
    # Las 3 nacen default ON y están curadas en _CURATED_DEFAULTS_ON. Ninguna cae
    # en las categorías de excepción: no hay loop/daemon/barrido ni llamada a
    # modelo (A no aplica) y no escriben en ningún sistema del operador ni le
    # sacan una decisión (B no aplica).
    FlagSpec(
        key="STACKY_GITLAB_TLS_ADAPTER_ENABLED",
        type="bool",
        default=True,  # default ON (corrige una conexión rota; es solo lectura; curada en _CURATED_DEFAULTS_ON)
        label="Certificado interno de GitLab por conexión",
        description=(
            "Plan 276 — Monta un contexto OpenSSL genuino con el certificado del proyecto SOLO en "
            "la sesión de GitLab. Hace falta porque truststore (obligatorio por la inspección TLS "
            "de la red corporativa) verifica por el almacén de Windows e ignora el pin de "
            "certificado hoja, así que un GitLab interno muere en el handshake aunque el "
            "certificado viaje bien. Azure DevOps, Jira y las APIs de modelos NO se tocan. "
            "Con OFF vuelve el verify=<bundle> de hoy."
        ),
        group="global",
    ),
    FlagSpec(
        key="STACKY_TRACKER_PROBE_STRICT_ENABLED",
        type="bool",
        default=True,  # default ON (solo lectura: leer, calcular y mostrar; curada en _CURATED_DEFAULTS_ON)
        label="Veredicto estricto del check de tracker",
        description=(
            "Plan 276 — 'Probar conexión' reporta cuatro sub-veredictos por separado (TLS, "
            "credenciales, proyecto legible, cantidad de ítems) y sale verde solo si los cuatro "
            "pasan. Mata el falso verde que ya costó una jornada: check en verde con el listado "
            "roto, porque el rótulo afirmaba 'alcanzable' sin haber hecho ping. Con OFF vuelve el "
            "veredicto único de hoy."
        ),
        group="global",
    ),
    FlagSpec(
        key="STACKY_GITLAB_SYNC_ENABLED",
        type="bool",
        default=True,  # default ON (escribe en la BD de Stacky, no en un sistema del operador, y es on-demand; curada en _CURATED_DEFAULTS_ON)
        label="Sincronizar issues de GitLab",
        description=(
            "Plan 276 — El botón 'Sincronizar' de un proyecto GitLab trae los issues abiertos a la "
            "tabla de tickets de Stacky, que es lo único que puede hacer que el grafo deje de estar "
            "vacío (salda la deuda que api/tickets.py delegaba a un 'Plan 220' que nunca se "
            "escribió). Escribe en la BD de Stacky, NUNCA en el GitLab del operador, nunca borra "
            "(un issue que desaparece se marca cerrado) y es on-demand: sin polling ni sync de "
            "fondo. Con OFF vuelve la carencia declarada y el grafo queda vacío."
        ),
        group="global",
    ),
    # ── Plan 281 — El ruteo por tracker deja de mentir ────────────────────────
    FlagSpec(
        key="STACKY_TRACKER_ROUTING_STRICT_ENABLED",
        type="bool",
        default=True,  # default ON (camino de LECTURA: no publica, no escribe en el tracker del operador ni le saca decisiones; curada en _CURATED_DEFAULTS_ON)
        label="Ruteo estricto por tipo de tracker",
        description=(
            "Plan 281 — Si Stacky no puede resolver el contexto de un proyecto, deja de asumir que "
            "es de Azure DevOps: avisa el problema real en vez de devolver un error del proveedor "
            "equivocado. Ademas el sync de arranque sincroniza los proyectos que no son de Azure "
            "DevOps (antes morian en un error tragado como aviso) y las funciones que piden un "
            "cliente de Azure DevOps preguntan primero de que tracker es el proyecto. Es solo "
            "lectura: no publica, no sube nada al tracker y no borra datos. Si la apagas vuelve el "
            "comportamiento anterior, incluido el cartel 'El proyecto no usa Azure DevOps' que "
            "aparecia cada tanto en un proyecto de GitLab."
        ),
        group="global",
    ),
    # ── Plan 277 — Jerarquía de GitLab: un solo contrato de tipo y padre ──────
    FlagSpec(
        key="STACKY_GITLAB_HIERARCHY_CONTRACT_ENABLED",
        type="bool",
        default=True,  # default ON (solo parsea etiquetas que ya vienen en el payload; no toca el GitLab del operador; curada en _CURATED_DEFAULTS_ON)
        label="Contrato de tipo y padre de GitLab",
        description=(
            "Plan 277 — El tipo de cada issue sale de la etiqueta 'type::<tipo>' y su padre de "
            "'epic::<iid>', con UNA sola normalización (services/gitlab_hierarchy.py) en vez de "
            "los cuatro motores divergentes de hoy. Mata el no-determinismo de tomar 'el primer "
            "label del array' (la API de GitLab no garantiza ese orden) y el motivo real de que "
            "todo issue termine huérfano en el grafo. Solo lectura del payload que ya se bajó: "
            "cero llamadas extra y cero escritura en el GitLab del operador. Con OFF vuelve la "
            "lectura divergente de hoy."
        ),
        group="global",
    ),
    FlagSpec(
        key="STACKY_GITLAB_HIERARCHY_LOCAL_CLASSIFY_ENABLED",
        type="bool",
        default=True,  # default ON (escribe en la BD de Stacky, NUNCA en el GitLab del operador, y es el operador quien decide ítem por ítem; curada en _CURATED_DEFAULTS_ON)
        label="Clasificación local de jerarquía de GitLab",
        description=(
            "Plan 277 — El operador marca desde la pantalla de qué tipo es un ticket de GitLab y "
            "de cuál otro cuelga, SIN escribir una sola letra en el GitLab de la empresa: la "
            "marca vive en dos columnas de la tabla de tickets de Stacky. Es lo único que sirve "
            "para los issues heredados que no tienen ninguna etiqueta del contrato. Precedencia "
            "sin excepciones: si GitLab declara el tipo o el padre, gana GitLab y la marca local "
            "queda guardada igual (se cuenta como superseded, nunca se borra). Con OFF el control "
            "no se renderiza, el sync ignora esas columnas aunque tengan valor y la escritura "
            "responde 403 nombrando esta flag."
        ),
        group="global",
    ),
    FlagSpec(
        key="STACKY_GITLAB_SYNC_PARENTS_ENABLED",
        type="bool",
        default=True,  # default ON (un GET acotado y con tope duro por los padres que las etiquetas ya nombraron; escribe en la BD de Stacky y es on-demand; curada en _CURATED_DEFAULTS_ON)
        label="Traer los padres que faltan al sincronizar GitLab",
        description=(
            "Plan 277 — El sync pide los issues ABIERTOS, así que una épica ya cerrada no viene "
            "en el listado y todos sus hijos quedan sueltos en el grafo aunque su etiqueta de "
            "padre sea correcta. Con esta flag, al terminar el sync se piden UNO A UNO —y solo— "
            "los que las etiquetas nombraron y no llegaron, con tope duro de 50 por corrida y un "
            "aviso cuando el tope recorta. Es solo lectura sobre GitLab, escribe en la BD de "
            "Stacky, no hace polling ni barrido, y si un pedido falla se cuenta y la corrida "
            "sigue. Con OFF vuelve el comportamiento de hoy: los hijos de una épica cerrada "
            "quedan sueltos."
        ),
        group="global",
    ),
    FlagSpec(
        key="STACKY_GITLAB_HIERARCHY_LABEL_WRITE_ENABLED",
        type="bool",
        # SIN `default=`: el default EFECTIVO es el de config.py ("false"). Declararlo
        # acá —aunque sea `default=False`— la haría `default_is_known` (el chequeo es
        # literalmente `spec.default is not None`) y pondría roja a
        # test_default_known_only_for_curated, que exige que el conjunto de flags con
        # default declarado sea EXACTAMENTE _CURATED_DEFAULTS_ON. Mismo trato que su
        # precedente STACKY_PIPELINE_NL_EDIT_COMMIT_ENABLED (:3588).
        # default OFF — excepcion (B): PUT add_labels contra el GitLab del operador (gitlab_hierarchy_backfill.ejecutar_backfill)
        label="Publicar las etiquetas de jerarquía en GitLab",
        description=(
            "Plan 277 — Publica en el GitLab de la empresa, como etiquetas reales, la "
            "clasificación que el operador hizo dentro de Stacky: 'type::<tipo>' y "
            "'epic::<iid>'. Es la ÚNICA ruta del plan que escribe en su sistema, sobre issues "
            "que Stacky no creó, y por eso nace apagada. Solo AGREGA ('add_labels'): nunca "
            "manda el juego completo de etiquetas —que lo reemplazaría y borraría las del "
            "operador— ni quita ninguna; escribe SOLO los ítems que el operador eligió uno "
            "por uno; corta ante el primer fallo sin reintentar; y un issue cuyo tipo remoto "
            "difiere del local se marca en conflicto y NO se toca (manda GitLab). Con OFF, "
            "ver el diff sigue funcionando: lo read-only no lleva flag."
        ),
        group="global",
        env_only=False,  # editable por UI (regla dura operator-config-always-via-ui)
    ),
    # ── Plan 238 — Bandeja de incidencias abiertas dentro de Tickets ADO ──────
    FlagSpec(
        key="STACKY_INCIDENT_INBOX_ENABLED",
        type="bool",
        default=True,  # default ON (ninguna de las 4 excepciones duras aplica; curada en _CURATED_DEFAULTS_ON)
        label="Bandeja de incidencias abiertas",
        description=(
            "Plan 238 - Vista dedicada que lista SOLO incidencias (Issue/Bug) con foco "
            "en las abiertas, accesible desde Tickets ADO. Solo lectura: no lanza agentes "
            "ni modifica el tracker. OFF: la vista, el tab, la entrada de la paleta y el "
            "boton de entrada desaparecen, y el tablero general queda identico."
        ),
        group="global",
    ),
    # ── Acciones dentro de la bandeja de incidencias (cerrar / resolver+PR) ───
    FlagSpec(
        key="STACKY_INCIDENT_INBOX_ACTIONS_ENABLED",
        type="bool",
        default=True,  # default ON (ninguna de las 4 excepciones duras aplica; curada en _CURATED_DEFAULTS_ON)
        label="Acciones desde la bandeja de incidencias",
        description=(
            "Levanta el guardarrail de solo-lectura del Plan 238: la bandeja pasa a permitir "
            "cerrar la incidencia en el tracker (mismo camino que 'Terminar trabajo' del "
            "tablero) y lanzar el Dev Resolutor con 'Abrir PR', ademas de seleccion multiple "
            "y lote. Cada accion sigue exigiendo confirmacion del operador y respeta los "
            "gates de sus propias flags. OFF: la bandeja vuelve a ser un listado de solo "
            "lectura y el tablero general queda identico."
        ),
        group="global",
        requires="STACKY_INCIDENT_INBOX_ENABLED",
    ),
    # ── Plan 246 — Inventario vivo de pipelines ─────────────────────────────────
    FlagSpec(
        key="STACKY_PIPELINE_INVENTORY_ENABLED",
        type="bool",
        default=True,  # default ON: NINGUNA de las 4 excepciones duras aplica (read-only,
                       # no destructivo, sin prerequisito extra, no reduce seguridad).
                       # Curada en _CURATED_DEFAULTS_ON (test_default_known_only_for_curated).
        label="Inventario de pipelines",
        description=(
            "Plan 246 - Lista TODAS las pipelines del proyecto: las registradas en Azure "
            "DevOps, las de GitLab y los YAML que existen en el repo sin estar registrados "
            "(huerfanas). Solo lectura: no crea, no edita y no dispara nada. Si falta el PAT "
            "o el proveedor no responde, muestra lo que si pudo descubrir. "
            "OFF: desaparece la seccion Inventario del panel DevOps y el endpoint responde "
            "404; todo lo demas queda identico."
        ),
        group="global",
    ),
    # ── Plan 202 — La Fragua Nocturna (turno mínimo viable) ─────────────────────
    FlagSpec(
        key="STACKY_NIGHT_FOUNDRY_ENABLED",
        type="bool",
        # SIN default= a propósito: default_is_known() es `spec.default is not None`
        # (type-agnóstico), así que declarar `default=False` la volvería "curada" y
        # rompería test_default_known_only_for_curated. El default EFECTIVO (OFF)
        # vive en config.py.
        #
        # Default OFF citando la EXCEPCIÓN DURA #3 (prerequisito NO garantizado en
        # una instalación default): la Fragua es una herramienta del árbol de
        # desarrollo —necesita el repo git y la carpeta de planes, que no existen en
        # el deploy congelado— y su turno nocturno depende de /loop, que es nativo de
        # Claude Code y no existe en Codex ni en Copilot. Además es un orquestador
        # nocturno: encenderlo sin querer sería gasto en reposo.
        label="La Fragua Nocturna",
        description=(
            "Plan 202 - Habilita la maquinaria de la Fragua Nocturna: la cola derivada del "
            "estado real del repo, la bitácora durable, el resumen triado de la mañana, el "
            "panel de solo lectura y el botón manual 'correr un turno'. NO corre nada sola: "
            "la corrida nocturna la arma el operador. Solo produce papel revisable (críticas, "
            "auditorías de solo lectura y paquetes listos para implementar); nunca mergea, "
            "nunca publica y nunca implementa. Default OFF (excepción dura #3: depende del "
            "árbol de desarrollo y de /loop, que es propio de Claude Code). "
            "OFF: las rutas responden 404 y todo queda idéntico a hoy."
        ),
        group="global",
    ),
    FlagSpec(
        key="STACKY_NIGHT_FOUNDRY_TOKEN_BUDGET",
        type="int",
        # SIN default= (mismo motivo type-agnóstico de arriba; los ints no se curan).
        # El default EFECTIVO (40000) vive en config.py.
        label="Presupuesto de la Fragua por noche",
        description=(
            "Plan 202 - Corte DURO: la Fragua deja de tomar trabajo nuevo cuando el gasto "
            "estimado de la noche supera este techo. Se evalúa antes de cada ítem, y el "
            "carril de crítica pre-reserva su costo estimado para que uno solo no se pase."
        ),
        group="global",
        requires="STACKY_NIGHT_FOUNDRY_ENABLED",
        # OBLIGATORIO en la FlagSpec: test_bounds_map_is_frozen deriva `actual` de
        # FlagSpec.min_value/max_value y lo compara contra _FROZEN_BOUNDS.
        min_value=1000, max_value=500000,
    ),
    # ── Plan 253 — concurrencia SQLite y mantenimiento de la base ───────────
    FlagSpec(
        key="STACKY_SQLITE_WAL_ENABLED",
        type="bool",
        label="Base de datos: lectura y escritura simultaneas",
        description=(
            "Plan 253 - Pone la base de runtime en WAL: un escritor deja de bloquear a los "
            "lectores. Si el sistema de archivos lo rechaza, se sigue en el modo anterior "
            "con espera por lock y el estado queda visible en /api/diag/health."
        ),
        group="global",
        default=True,
        restart_required=True,   # el listener se ata al engine en el import de db.py
    ),
    FlagSpec(
        key="STACKY_SQLITE_BUSY_TIMEOUT_MS",
        type="int",
        # SIN default= a proposito: default_is_known() es `spec.default is not None`
        # (type-agnostico), asi que declararlo la volveria "curada" y romperia
        # test_default_known_only_for_curated. El default EFECTIVO vive en config.py.
        label="Base de datos: espera maxima ante bloqueo (ms)",
        description="Plan 253 - Milisegundos que se espera si la base esta tomada. 0 = sin espera.",
        group="global",
        min_value=0,
        max_value=120000,
        restart_required=True,
    ),
    FlagSpec(
        key="STACKY_SQLITE_SYNCHRONOUS_NORMAL_ENABLED",
        type="bool",
        # SIN default= (mismo motivo type-agnostico). Default EFECTIVO OFF en config.py
        # por EXCEPCION DURA #4: reduce la durabilidad ante corte de energia.
        label="Base de datos: guardado rapido con menor durabilidad",
        description=(
            "Plan 253 - Baja el nivel de sincronizacion a disco a NORMAL. Acelera el "
            "guardado pero un corte abrupto de energia puede perder la ultima operacion "
            "confirmada. Default OFF (excepcion dura #4: reduce seguridad de los datos)."
        ),
        group="global",
        restart_required=True,
    ),
    FlagSpec(
        key="STACKY_STARTUP_WRITE_BARRIER_WAIT_S",
        type="float",
        # SIN default= (numerica; el default EFECTIVO 30.0 vive en config.py).
        label="Espera de las tareas de fondo a la carga inicial (segundos)",
        description=(
            "Plan 253 - Segundos que los procesos de fondo esperan a que termine la fase "
            "de escritura del arranque antes de trabajar. 0 = sin espera (como antes)."
        ),
        group="global",
        min_value=0,
        max_value=300,
    ),
    FlagSpec(
        key="STACKY_SQLITE_LOCK_RETRY_ENABLED",
        type="bool",
        label="Reintentar operaciones bloqueadas por la base",
        description=(
            "Plan 253 - Reintenta la unidad de trabajo COMPLETA (una transaccion nueva por "
            "intento) cuando falla solo porque la base estaba tomada. Cualquier otro error "
            "se re-lanza en el primer intento: no enmascara bugs."
        ),
        group="global",
        default=True,
    ),
    FlagSpec(
        key="STACKY_SYSLOG_AUTO_PURGE_ENABLED",
        type="bool",
        label="Borrado automatico del historial vencido",
        description=(
            "Plan 253 - Hace EFECTIVA la retencion declarada: borra en lotes las filas de "
            "system_logs mas viejas que el plazo configurado. Corre en el hilo de "
            "mantenimiento; costo ocioso cero."
        ),
        group="global",
        default=True,
    ),
    FlagSpec(
        key="STACKY_SYSLOG_PURGE_INTERVAL_S",
        type="int",
        # SIN default= (numerica; el default EFECTIVO 21600 vive en config.py).
        label="Cada cuanto se revisa el historial vencido (segundos)",
        description="Plan 253 - Intervalo entre pasadas de borrado del historial vencido.",
        group="global",
        # SIN `requires=`: la tabla congelada del plan (seccion 4) no declara aristas y
        # `requires` obliga a un 7mo lugar (tests/test_harness_flags_requires.py
        # _REQUIRES_MAP_FROZEN) fuera del contrato de esta serie.
        min_value=300,
        max_value=604800,
    ),
    FlagSpec(
        key="STACKY_SYSLOG_RETENTION_DAYS",
        type="int",
        # SIN default= (numerica; el default EFECTIVO 90 vive en config.py, que
        # ademas respeta la env var historica SYSLOG_RETENTION_DAYS).
        label="Dias de conservacion del historial de actividad",
        description=(
            "Plan 253 - Cuantos dias se conserva el historial antes de poder borrarse. "
            "Fuente unica: reemplaza al valor congelado en el import de stacky_logger."
        ),
        group="global",
        min_value=1,
        max_value=3650,
    ),
    FlagSpec(
        key="STACKY_DB_COMPACT_ENABLED",
        type="bool",
        # SIN default= (default EFECTIVO OFF en config.py) por EXCEPCION DURA #2:
        # la compactacion borra filas historicas y reescribe el archivo de la base.
        label="Habilitar el boton de compactar la base",
        description=(
            "Plan 253 - Habilita el diagnostico y el boton de compactacion. Nada se borra "
            "ni se compacta sin confirmacion explicita del operador, con el conteo exacto "
            "a la vista y copia de respaldo previa. Default OFF (excepcion dura #2: "
            "destructiva e irreversible)."
        ),
        group="global",
    ),

    # ── Plan 254 — fin del falso ROJO: cierre veraz de las corridas ─────────
    FlagSpec(
        key="STACKY_TICKET_STATUS_NO_DOWNGRADE_ENABLED",
        type="bool",
        label="No pisar un trabajo ya terminado con un error posterior",
        description=(
            "Plan 254 - Si un ticket ya quedo terminado con exito, un cierre posterior "
            "en error NO lo pisa: se conserva el estado bueno, se registra el intento y "
            "el caso queda marcado para que lo revise una persona. Asimetrico a proposito: "
            "cancelar y mandar a revision siguen permitidos."
        ),
        group="global",
        default=True,
    ),
    FlagSpec(
        key="STACKY_RUN_OUTCOME_TAXONOMY_ENABLED",
        type="bool",
        label="Clasificar la causa del desenlace de cada corrida",
        description=(
            "Plan 254 - Distingue nueve desenlaces (cuota agotada, bloqueo previo, "
            "quedo ocioso tras entregar, tiempo maximo excedido, perdida de senal, fallo "
            "real del runtime...) que hoy se ven todos igual. Solo agrega informacion."
        ),
        group="global",
        default=True,
    ),
    # ── Plan 280 — El desenlace mira el trabajo entregado ─────────────────
    FlagSpec(
        key="STACKY_OUTCOME_WORK_EVIDENCE_ENABLED",
        type="bool",
        default=True,   # default ON: NINGUNA excepcion aplica. No bypasea revision
                        # humana (al contrario: manda a revision lo que hoy se
                        # cierra solo), no es destructiva, no pide prerequisito
                        # nuevo y no reduce seguridad. Curada en _CURATED_DEFAULTS_ON.
        label="Mirar el trabajo entregado antes de dar una corrida por fallida",
        description=(
            "Plan 280 - Hoy una corrida se juzga por como cerro el proceso, no por lo "
            "que produjo: si el agente entrego su trabajo pero la salida se corto mal, "
            "queda marcada como fallo. Con esto, cuando hay trabajo entregado la corrida "
            "pasa a REVISION en vez de a error, y tampoco puede darse por buena sola. "
            "OFF: se decide como hasta ahora, solo por el cierre del proceso."
        ),
        group="global",
        env_only=False,  # editable por UI (regla dura operator-config-always-via-ui)
    ),
    FlagSpec(
        key="STACKY_CLI_STREAM_DRAIN_TIMEOUT_S",
        type="float",
        # SIN default= (numerica; el default EFECTIVO 15.0 vive en config.py).
        label="Espera maxima para terminar de leer la salida del agente (segundos)",
        description=(
            "Plan 254 - Tope de espera para terminar de leer lo que el agente dejo en "
            "vuelo antes de decidir como termino. Es un TECHO, no un costo: si ya no "
            "queda nada por leer, se sigue de largo. El plazo se reparte entre los dos "
            "lectores, no se cuenta para cada uno."
        ),
        group="global",
        min_value=1,
        max_value=120,
    ),
    FlagSpec(
        key="STACKY_UI_OUTCOME_REASON_BADGE_ENABLED",
        type="bool",
        label="Mostrar la causa del desenlace en el detalle de la corrida",
        description=(
            "Plan 254 - Pinta la causa en lenguaje humano y avisa cuando se conservo un "
            "estado bueno sobre un cierre sucio. Apagada, el detalle no recibe el dato y "
            "el aviso no se dibuja."
        ),
        group="global",
        default=True,
    ),
    FlagSpec(
        key="STACKY_RUN_RECONCILIATION_ENABLED",
        type="bool",
        label="Contar las corridas cuyo estado no coincide con la evidencia",
        description=(
            "Plan 254 - Compara el estado de cada ticket contra lo que de verdad paso en "
            "su corrida y lista las diferencias. Solo lectura: no cambia ni un estado, no "
            "reintenta y no corre solo (se consulta a pedido)."
        ),
        group="global",
        default=True,
    ),
    # ── Plan 255 — cero fallas mudas ───────────────────────────────
    FlagSpec(
        key="STACKY_SILENT_FAILURE_COUNTER_ENABLED",
        type="bool",
        label="Contar los fallos que el sistema se traga en silencio",
        description=(
            "Plan 255 - Registra cuantas veces cada punto del codigo atrapo un fallo y "
            "no dejo rastro. Un dict en memoria: no escribe a disco, no loguea y jamas "
            "levanta. Apagada, el contador no cuenta y el panel queda vacio."
        ),
        group="global",
        default=True,
    ),
    FlagSpec(
        key="STACKY_STRUCTURAL_ERRORS_TO_ERROR_LEVEL",
        type="bool",
        label="Anotar como graves los fallos que son bugs de codigo",
        description=(
            "Plan 255 - Un fallo de importacion, de atributo o de nombre se anota como "
            "'error'; los transitorios (bloqueo, timeout, red) siguen como 'warning'. "
            "TypeError queda EXCLUIDO a proposito. Apagada, todo vuelve a 'warning'."
        ),
        group="global",
        default=True,
    ),
    FlagSpec(
        key="STACKY_DORMANT_CANARY_ENABLED",
        type="bool",
        label="Avisar cuando un mecanismo caro dejo de dar senales de exito",
        description=(
            "Plan 255 - Lo inverso a una huella de regresion: alarma cuando un patron "
            "BUENO deja de aparecer en el log. Lee un tail acotado bajo demanda, sin "
            "loop y sin red. AVISA, nunca arregla ni re-habilita nada."
        ),
        group="global",
        default=True,
    ),
    # ── Plan 257 — observabilidad antirruido (throttle / rotacion / purga) ───
    # 9 entradas. LOG_LEVEL NO se registra aca a proposito (C14): el hot-apply
    # de este panel solo hace setattr sobre config y no ejecuta efectos, asi que
    # una FlagSpec diria "aplicado" mientras el logging sigue igual. Va por
    # api/global_config.py, que es quien llama apply_log_level.
    FlagSpec(
        key="STACKY_LOG_THROTTLE_ENABLED",
        type="bool",
        label="Agrupar los mensajes repetidos del registro de actividad",
        description=(
            "Plan 257 - Emite la PRIMERA aparicion de cada mensaje y agrupa las "
            "repeticiones dentro de una ventana, con el conteo acumulado. Nunca pierde "
            "informacion: el conteo se emite siempre. Los mensajes graves y criticos "
            "quedan exentos. Medido: una sola firma se comio el 71% de los avisos del "
            "peor dia."
        ),
        group="global",
        default=True,
        # Se consume UNA vez al arrancar (se instala el filtro compartido en los
        # tres destinos del registro), asi que un cambio no aplica en caliente.
        restart_required=True,
    ),
    FlagSpec(
        key="STACKY_LOG_THROTTLE_WINDOW_S",
        type="float",
        # SIN default= (numerica; el default EFECTIVO 60.0 vive en config.py).
        label="Ventana para agrupar mensajes repetidos (segundos)",
        description=(
            "Plan 257 - Cuantos segundos se agrupan las repeticiones de un mismo "
            "mensaje antes de volver a emitirlo con su conteo."
        ),
        group="global",
        requires="STACKY_LOG_THROTTLE_ENABLED",
        min_value=1,
        max_value=3600,
        restart_required=True,
    ),
    FlagSpec(
        key="STACKY_LOG_THROTTLE_MAX_SIGNATURES",
        type="int",
        # SIN default= (numerica; el default EFECTIVO 1000 vive en config.py).
        label="Maximo de mensajes distintos que se siguen a la vez",
        description=(
            "Plan 257 - Cota de memoria del agrupador. Superado el tope, los mensajes "
            "nuevos pasan sin agrupar: se prefiere ruido antes que silencio."
        ),
        group="global",
        requires="STACKY_LOG_THROTTLE_ENABLED",
        min_value=10,
        max_value=100000,
        restart_required=True,
    ),
    FlagSpec(
        key="STACKY_LOG_THROTTLE_FLUSH_S",
        type="int",
        # SIN default= (numerica; el default EFECTIVO 300 vive en config.py).
        label="Cada cuanto se vuelca el conteo de repeticiones (segundos)",
        description=(
            "Plan 257 - Sin este volcado, el conteo de un mensaje que deja de repetirse "
            "no se emite nunca y el registro dice '1 vez' de algo que paso 854. 0 = solo "
            "al apagar el servicio. Lo corre el hilo de mantenimiento compartido."
        ),
        group="global",
        requires="STACKY_LOG_THROTTLE_ENABLED",
        min_value=0,
        max_value=86400,
    ),
    FlagSpec(
        key="STACKY_LOG_SIZE_ROTATION_ENABLED",
        type="bool",
        label="Abrir un archivo nuevo cuando el del dia crece demasiado",
        description=(
            "Plan 257 - Hoy solo hay un archivo por dia y puede crecer sin techo "
            "(medido: 4,45 MB en un dia). Al llegar al tope se abre una parte nueva. "
            "Al agotar las partes NO se deja de escribir: se sigue en la ultima."
        ),
        group="global",
        default=True,
    ),
    FlagSpec(
        key="STACKY_LOG_MAX_BYTES",
        type="int",
        # SIN default= (numerica; el default EFECTIVO 20971520 vive en config.py).
        label="Tamano maximo de cada archivo de registro (bytes)",
        description="Plan 257 - Al superarlo se abre la parte siguiente del mismo dia.",
        group="global",
        requires="STACKY_LOG_SIZE_ROTATION_ENABLED",
        min_value=65536,
        max_value=1073741824,
    ),
    FlagSpec(
        key="STACKY_LOG_MAX_PARTS_PER_DAY",
        type="int",
        # SIN default= (numerica; el default EFECTIVO 10 vive en config.py).
        label="Maximo de partes por dia del registro",
        description=(
            "Plan 257 - Techo de archivos por dia. Alcanzado el techo se sigue "
            "escribiendo en la ultima parte, con un unico aviso."
        ),
        group="global",
        requires="STACKY_LOG_SIZE_ROTATION_ENABLED",
        min_value=1,
        max_value=1000,
    ),
    FlagSpec(
        key="STACKY_LOG_RETENTION_DAYS",
        type="int",
        # SIN default= (numerica; el default EFECTIVO 14 vive en config.py, que
        # ademas reemplaza a la constante congelada del modulo de registro).
        label="Dias que se conservan los archivos de registro",
        description=(
            "Plan 257 - La retencion declarada de 14 dias casi nunca se aplicaba: solo "
            "corria al cruzar la medianoche con el servicio vivo. Ahora corre al "
            "arrancar y cada 6 horas. Fuente unica del valor."
        ),
        group="global",
        min_value=1,
        max_value=3650,
    ),
    FlagSpec(
        key="STACKY_UI_LOG_NOISE_CARD_ENABLED",
        type="bool",
        label="Mostrar los mensajes mas repetidos en Diagnostico",
        description=(
            "Plan 257 - Tarjeta de solo lectura con las firmas que mas inundan el "
            "registro y cuantas se agruparon. Sale de memoria: no vuelve a leer ningun "
            "archivo y no borra los contadores."
        ),
        group="global",
        default=True,
    ),
    # ── Plan 258 — telemetria veraz de los archivos de registro ──────────────
    # 6 entradas. Medido antes del plan: 8 de 8 lineas de ci_runs.jsonl eran
    # fixture de test y 10 de 10 de env_applies.jsonl las escribio pytest.
    FlagSpec(
        key="STACKY_LEDGER_STRICT_SCHEMA_ENABLED",
        type="bool",
        label="Rechazar los eventos incompletos de los archivos de registro",
        description=(
            "Plan 258 - Un evento al que le falta alguna clave obligatoria no se "
            "escribe y queda anotado como error, en vez de entrar mutilado. Apagada, "
            "el sello de procedencia se sigue poniendo pero no se rechaza nada."
        ),
        group="global",
        default=True,
    ),
    FlagSpec(
        key="STACKY_LEDGER_LEGACY_INFERENCE_ENABLED",
        type="bool",
        label="Deducir la procedencia de las lineas viejas sin marca",
        description=(
            "Plan 258 - Clasifica EN MEMORIA al leer las lineas anteriores al sello: "
            "'test' solo si hay evidencia en un campo nombrado, si no 'unknown'. NUNCA "
            "deduce 'prod' y NUNCA reescribe el archivo. Apagada, todo queda 'unknown'."
        ),
        group="global",
        default=True,
    ),
    FlagSpec(
        key="STACKY_LEDGER_TEST_MARKERS",
        type="csv",
        # SIN default= (no es booleana; el default EFECTIVO 'myproject' vive en
        # config.py). Declararlo la meteria en el ratchet de defaults curados.
        label="Nombres de proyecto que se consideran de prueba",
        description=(
            "Plan 258 - Lista separada por comas. Un proyecto REAL que se llame igual "
            "que uno de prueba se saca de aca y deja de marcarse. Vaciarla desactiva "
            "esa regla sin tocar codigo."
        ),
        group="global",
        requires="STACKY_LEDGER_LEGACY_INFERENCE_ENABLED",
    ),
    FlagSpec(
        key="STACKY_LEDGER_ORPHAN_REPORT_ENABLED",
        type="bool",
        label="Avisar de las corridas de CI reales que nunca cerraron",
        description=(
            "Plan 258 - Lista las corridas de produccion que se dispararon y jamas "
            "reportaron desenlace. Solo cuenta 'prod': incluir las de prueba llenaria "
            "el reporte de basura desde el minuto uno. Solo lectura."
        ),
        group="global",
        default=True,
    ),
    FlagSpec(
        key="STACKY_LEDGER_PURGE_ENABLED",
        type="bool",
        # SIN default=: nace APAGADA por la excepcion dura #2 (destructiva e
        # irreversible). Por eso NO va a _CURATED_DEFAULTS_ON.
        label="Permitir borrar las lineas de prueba de un archivo de registro",
        description=(
            "Plan 258 - APAGADA por default: es lo unico de este plan que borra datos. "
            "Aun encendida exige pedirlo en modo real de forma explicita, una "
            "confirmacion con el conteo a la vista y una copia previa. Nunca toca las "
            "lineas de produccion ni las de procedencia desconocida."
        ),
        group="global",
        requires="STACKY_LEDGER_LEGACY_INFERENCE_ENABLED",
    ),
    FlagSpec(
        key="STACKY_HARNESS_AIRTIGHT_GUARD_ENABLED",
        type="bool",
        label="Verificar que las pruebas no toquen los archivos del operador",
        description=(
            "Plan 258 - Toma una huella de los archivos de datos antes y despues de "
            "correr las pruebas y nombra cualquiera que haya cambiado. Solo compara: "
            "no modifica nada. Cubre tambien los archivos que se agreguen en el futuro."
        ),
        group="global",
        default=True,
    ),
    # =====================================================================
    # COSTURA DE FLAGS DE LA OLA 1 (paquete P0, 2026-07-28)
    # Las 15 flags de los planes 259, 267, 268, 269 y 270, pre-declaradas de
    # una sola vez para que los 4 paquetes que implementan esos planes NO
    # toquen este archivo y puedan correr en paralelo sin pisarse.
    # REGLA DURA: quien implemente 259/267/268/269/270 NO vuelve a declarar
    # ninguna de estas. Si cree que falta una, PARA y avisa.
    # =====================================================================
    # ── Plan 259 — Alta de proyecto GitLab + guia de configuracion ────────
    FlagSpec(
        key="STACKY_PROJECT_GITLAB_ONBOARDING_ENABLED",
        type="bool",
        default=True,   # Curada en _CURATED_DEFAULTS_ON (test_default_known_only_for_curated).
        label="Crear proyectos GitLab desde la pantalla de alta",
        description=(
            "Plan 259 - Agrega GitLab a los sistemas de tickets elegibles al crear un "
            "proyecto y habilita la rama GitLab del alta en el backend. Si la apagas, el "
            "boton no aparece y el backend rechaza tracker_type=gitlab con un mensaje "
            "explicito en vez de convertir el proyecto a Azure DevOps."
        ),
        group="global",
        env_only=False,
    ),
    FlagSpec(
        key="STACKY_SETUP_GUIDE_ENABLED",
        type="bool",
        default=True,   # Curada en _CURATED_DEFAULTS_ON (test_default_known_only_for_curated).
        label="Boton INFO con la guia de configuracion paso a paso",
        description=(
            "Plan 259 - Muestra un boton INFO junto al sistema de tickets elegido que abre "
            "la guia exacta de configuracion (12 pasos para GitLab). Texto de solo lectura, "
            "sin red."
        ),
        group="global",
        env_only=False,
    ),
    FlagSpec(
        key="STACKY_SETUP_GUIDE_VERIFY_ENABLED",
        type="bool",
        default=True,   # Curada en _CURATED_DEFAULTS_ON (test_default_known_only_for_curated).
        label='Boton "Verificar ahora" dentro de la guia',
        description=(
            "Plan 259 - Corre 5 controles de solo lectura contra la instancia que "
            "escribiste en el formulario y marca cual falla. No escribe nada, ni en GitLab "
            "ni en disco."
        ),
        group="global",
        env_only=False,
    ),
    # ── Plan 267 — Catalogo unico de acciones DevOps ──────────────────────
    FlagSpec(
        key="STACKY_DEVOPS_ACTION_CATALOG_ENABLED",
        type="bool",
        default=True,   # default ON: NINGUNA excepcion aplica. Solo LISTA lo que ya
                        # existe; no escribe en ningun lado, no llama a ningun modelo,
                        # no corre en reposo (se sirve a pedido de la pantalla) y no le
                        # saca ninguna decision al operador.
                        # Curada en _CURATED_DEFAULTS_ON (tests/test_harness_flags.py).
        label="Catalogo de acciones DevOps",
        description=(
            "Plan 267 - declara en un solo lugar que se puede hacer en el panel DevOps "
            "(que accion, en que seccion, si lee o escribe, que impacto, sobre que "
            "entorno). Lo consumen los botones, la paleta de comandos y el asistente. "
            "OFF: /api/devops/actions/catalog devuelve 404 y las tres superficies "
            "quedan como hoy."
        ),
        group="global",
        env_only=False,  # editable por UI (regla dura operator-config-always-via-ui)
    ),
    FlagSpec(
        key="STACKY_DEVOPS_ACTION_NL_ENABLED",
        type="bool",
        default=True,   # default ON - ninguna excepcion aplica: solo INTERPRETA una frase
                        # que el operador acaba de escribir y devuelve una propuesta; no
                        # corre en reposo (no hay loop ni daemon: se dispara por request),
                        # no llama a ningun modelo (el matcher es determinista) y no
                        # escribe absolutamente nada. Curada en _CURATED_DEFAULTS_ON.
        label="Pedir una tarea de despliegue escribiendola en castellano",
        description=(
            "Plan 267 - Permite pedir una tarea de despliegue escribiendola en castellano, "
            "y que el asistente muestre cual seria la accion antes de hacer nada. El "
            "reconocimiento es determinista: no interviene ningun modelo. OFF: el "
            "asistente vuelve a responder solo con texto."
        ),
        group="global",
        env_only=False,
        requires="STACKY_DEVOPS_ACTION_CATALOG_ENABLED",
    ),
    FlagSpec(
        key="STACKY_DEVOPS_AGENT_ACTION_RUN_ENABLED",
        # SIN default= A PROPOSITO (regla dura): una flag default OFF NO declara
        # default=False, porque eso la volveria default_is_known y
        # test_default_known_only_for_curated exige que ese conjunto sea EXACTAMENTE
        # _CURATED_DEFAULTS_ON, donde una flag OFF no puede entrar.
        # El OFF vive SOLO en config.py. NO va en _CURATED_DEFAULTS_ON.
        # Nace OFF porque es la unica del plan que EJECUTA sobre los servidores y
        # repositorios REALES del operador.
        type="bool",
        label="El asistente puede ejecutar las tareas que confirmes",
        description=(
            "Plan 267 - Decide si el asistente puede llevar a cabo por si mismo las tareas "
            "que modifican tus servidores y repositorios, o si solo puede mostrartelas. "
            "Nace APAGADA: aun encendida exige tu confirmacion antes de cada tarea. OFF: "
            "el asistente muestra la tarjeta completa y un boton que te lleva a la "
            "pantalla para hacerlo vos."
        ),
        group="global",
        env_only=False,
        requires="STACKY_DEVOPS_ACTION_CATALOG_ENABLED",
    ),
    # ── Plan 279 — Copiloto de pipelines: un solo hilo conversacional ─────
    FlagSpec(
        key="STACKY_PIPELINE_COPILOT_ENABLED",
        type="bool",
        default=True,   # default ON: NINGUNA excepcion aplica. Solo LEE, PLANEA,
                        # SIMULA y EXPLICA (lint/explain/preflight son estaticos);
                        # no escribe en ningun sistema real, no corre en reposo (se
                        # dispara por request) y no le saca ninguna decision al
                        # operador. Curada en _CURATED_DEFAULTS_ON.
        label="Copiloto de pipelines en un solo hilo",
        description=(
            "Plan 279 - Pone un solo hilo conversacional encima de lo que ya existe: "
            "describis en castellano la pipeline que necesitas y el copiloto arma el "
            "borrador, lo valida, explica que va a correr y dice que variables faltan, "
            "sin salir de una sola pantalla. NO escribe nada en el repositorio: eso lo "
            "gatea STACKY_PIPELINE_COPILOT_COMMIT_ENABLED. OFF: el panel DevOps queda "
            "exactamente como hoy y la seccion 'Copiloto de pipelines' se atenua."
        ),
        group="global",
        env_only=False,  # editable por UI (regla dura operator-config-always-via-ui)
        requires="STACKY_DEVOPS_ACTION_CATALOG_ENABLED",
    ),
    FlagSpec(
        key="STACKY_PIPELINE_COPILOT_COMMIT_ENABLED",
        # SIN default= A PROPOSITO (regla dura, precedentes literales:
        # STACKY_DEVOPS_AGENT_ACTION_RUN_ENABLED y
        # STACKY_PIPELINE_NL_EDIT_COMMIT_ENABLED). Una flag default OFF NO declara
        # default=False, porque eso la volveria default_is_known() y
        # test_default_known_only_for_curated exige que ese conjunto sea EXACTAMENTE
        # _CURATED_DEFAULTS_ON, donde una flag OFF no puede entrar.
        # El OFF vive SOLO en config.py. NO va en _CURATED_DEFAULTS_ON.
        # Excepcion dura (B): ESCRIBE el archivo de pipeline en el repositorio REAL.
        type="bool",
        label="El copiloto puede crear la pipeline en el repositorio",
        description=(
            "Plan 279 - Decide si el copiloto puede escribir el archivo de pipeline "
            "(azure-pipelines.yml o .gitlab-ci.yml) en la rama que elijas de tu "
            "repositorio real, o si solo puede mostrarte el borrador. Nace APAGADA: aun "
            "encendida exige tu confirmacion explicita y te muestra ANTES como deshacer "
            "el cambio. OFF: el copiloto llega hasta el borrador validado y te lleva a la "
            "pantalla para crearlo vos."
        ),
        group="global",
        env_only=False,  # editable por UI (regla dura operator-config-always-via-ui)
        requires="STACKY_DEVOPS_ACTION_CATALOG_ENABLED",
    ),
    # ── Plan 268 — Explorador del grafo documental ────────────────────────
    FlagSpec(
        key="STACKY_DOCS_GRAPH_EXPLORER_ENABLED",
        default=True,  # Plan 268 — read-only puro: nace ON (regla de defaults 2026-07-27)
        type="bool",
        label="Explorador del grafo documental (Plan 268)",
        description=(
            "Plan 268 — Convierte la pestaña 'Grafo' de la página Docs en un "
            "explorador: barra de filtros (fuente, tipo de nodo, tipo de arista, "
            "grado, huérfanas, desactualizadas), búsqueda navegable con conteo y "
            "encuadre, foco por vecindario a profundidad 1-3 con historial, "
            "agrupación por fuente con color y colapso, controles de zoom y "
            "atajos de teclado, minimapa y vista previa del contenido del nodo "
            "seleccionado. 100% read-only: no escribe ningún documento. Si la "
            "apagás, la pestaña 'Grafo' vuelve a comportarse como en el Plan 111. "
            "Default ON."
        ),
        group="global",
        env_only=False,
        requires="STACKY_DOCS_GRAPH_ENABLED",
    ),
    # ── Plan 269 — Veredicto por evidencia (3 niveles) ────────────────────
    # NINGUNA declara requires= (decision deliberada del plan, §3.7): la
    # dependencia entre la flag de UI y la del nucleo se resuelve EN CODIGO
    # (una funcion lee las dos), no en el registro.
    FlagSpec(
        key="STACKY_RUN_VERDICT_ENABLED",
        type="bool",
        default=True,   # Curada en _CURATED_DEFAULTS_ON. No cambia ningun estado por su cuenta.
        label="Veredicto de la corrida en tres niveles",
        description=(
            "Plan 269 - Decide si una corrida termino bien, termino con advertencias o "
            "fallo de verdad, mirando ademas si dejo resultados. No cambia ningun estado "
            "por su cuenta. OFF: se sigue viendo solo el estado crudo, sin el veredicto "
            "ni la explicacion de la causa."
        ),
        group="global",
        env_only=False,
    ),
    FlagSpec(
        key="STACKY_RUN_EVIDENCE_COLLECTORS_ENABLED",
        type="bool",
        default=True,   # Curada en _CURATED_DEFAULTS_ON. Solo LEE evidencia ya producida.
        label="Buscar las pruebas de que la corrida dejo resultados",
        description=(
            "Plan 269 - Busca las pruebas de que una corrida dejo resultados: archivos, "
            "comentario publicado, cambios en el repositorio y controles pasados. Solo "
            "lee lo que la corrida ya produjo. OFF: el veredicto no puede comprobar nada "
            "y queda siempre en advertencia por falta de pruebas."
        ),
        group="global",
        env_only=False,
    ),
    FlagSpec(
        key="STACKY_UI_RUN_VERDICT_BADGE_ENABLED",
        type="bool",
        default=True,   # Curada en _CURATED_DEFAULTS_ON. Solo presentacion.
        label="Veredicto visible en la lista de corridas",
        description=(
            "Plan 269 - Muestra el veredicto de tres niveles en la lista de corridas, no "
            "solo adentro del detalle, y permite filtrar por el. OFF: la lista queda como "
            "antes, con el estado crudo y sin la columna de veredicto."
        ),
        group="global",
        env_only=False,
    ),
    FlagSpec(
        key="STACKY_INCIDENT_INBOX_VERDICT_ENABLED",
        type="bool",
        default=True,   # Curada en _CURATED_DEFAULTS_ON. Solo presentacion.
        label="Veredicto de la ultima corrida en la bandeja de incidencias",
        description=(
            "Plan 269 - Muestra en la bandeja de incidencias el veredicto de la ultima "
            "corrida de cada una, para ver de un vistazo cuales necesitan atencion de "
            "verdad y cuales solo figuran mal. OFF: la bandeja se ve igual que antes y "
            "hay que abrir cada incidencia para saberlo."
        ),
        group="global",
        env_only=False,
    ),
    FlagSpec(
        key="STACKY_RUN_RECONCILIATION_HITL_ENABLED",
        type="bool",
        default=True,   # Curada en _CURATED_DEFAULTS_ON. NO autocorrige: la correccion la
                        # decide y la firma SIEMPRE el operador, y queda registrada.
        label="Corregir a mano una corrida mal marcada",
        description=(
            "Plan 269 - Deja corregir a mano, desde la pantalla, el estado de una corrida "
            "que quedo mal marcada. Nada se corrige solo: cada correccion la decide el "
            "operador y queda registrada con su autor. OFF: se sigue viendo cuantos casos "
            "hay mal marcados, pero sin boton para corregirlos desde ahi."
        ),
        group="global",
        env_only=False,
    ),
    # ── Plan 270 — El tablero de incidencias dice la verdad ───────────────
    FlagSpec(
        key="STACKY_TRACKER_STATE_WRITE_ROUTING_ENABLED",
        type="bool",
        default=True,   # Curada en _CURATED_DEFAULTS_ON. Escribe en el tablero real, pero
                        # SOLO por un cierre que el operador ya pidio: enruta y traduce ese
                        # mismo cambio en vez de mandarlo al sistema equivocado.
        label="Enrutar el cambio de estado al sistema de tickets correcto",
        description=(
            "Plan 270 - Manda el cambio de estado al sistema de tickets que el proyecto usa "
            "de verdad, en vez de intentarlo siempre contra Azure DevOps, y traduce el "
            "estado al vocabulario de ese sistema. Si no puede traducirlo, avisa y no "
            "escribe nada. OFF: vuelve el comportamiento viejo, que intenta el cambio "
            "contra Azure DevOps aunque el proyecto viva en otro lado."
        ),
        group="global",
        env_only=False,
    ),
    FlagSpec(
        key="STACKY_TICKET_STATE_WRITEBACK_ENABLED",
        type="bool",
        default=True,   # Curada en _CURATED_DEFAULTS_ON. Re-lee el estado que acaba de
                        # cambiar y refresca la copia LOCAL; no origina cambios nuevos.
        label="Refrescar el estado local despues de cerrar en el tracker",
        description=(
            "Plan 270 - Despues de cambiar el estado en el sistema de tickets, vuelve a "
            "leerlo y actualiza la copia local para que la lista no muestre datos viejos. "
            "OFF: el cierre igual se hace, pero la fila sigue mostrando el estado anterior "
            "hasta la proxima sincronizacion."
        ),
        group="global",
        env_only=False,
    ),
    FlagSpec(
        key="STACKY_INCIDENT_DIVERGENCE_BADGE_ENABLED",
        type="bool",
        default=True,   # Curada en _CURATED_DEFAULTS_ON. Puramente informativa: no cambia
                        # nada, solo marca la fila desalineada.
        label="Marca \"Sin sincronizar\" en la bandeja de incidencias",
        description=(
            "Plan 270 - Marca en la lista las incidencias que Stacky ya dio por terminadas "
            "pero el sistema de tickets sigue mostrando abiertas, y agrega un filtro para "
            "ver solo esas. No cambia nada: solo lo muestra. OFF: la lista se ve igual que "
            "antes y las filas desalineadas no se distinguen del resto."
        ),
        group="global",
        env_only=False,
    ),
    # ── Plan 265 — la consola como experiencia principal ──
    FlagSpec(
        key="STACKY_CONSOLE_FULLSCREEN_ENABLED",
        type="bool",
        default=True,   # Curada en _CURATED_DEFAULTS_ON de tests/test_harness_flags.py.
        label="Consola en pantalla completa",
        description=(
            "Plan 265 — La consola de corridas puede ocupar toda la pantalla util, "
            "con paneles laterales, busqueda y atajos, sobre la MISMA sesion que el "
            "dock. Presentacion de UI: no cambia como corre nada."
        ),
        group="global",
    ),
    FlagSpec(
        key="STACKY_CONSOLE_RICH_RENDER_ENABLED",
        type="bool",
        default=True,   # Curada en _CURATED_DEFAULTS_ON de tests/test_harness_flags.py.
        label="Markdown y bloques de codigo en la consola",
        description=(
            "Plan 265 — En pantalla completa, la salida se renderiza con markdown y "
            "resaltado de sintaxis, con boton de copia por bloque. El dock sigue "
            "mostrando lineas crudas. Sin dependencias nuevas."
        ),
        group="global",
        requires="STACKY_CONSOLE_FULLSCREEN_ENABLED",
    ),
    FlagSpec(
        key="STACKY_CONSOLE_REPO_PANEL_ENABLED",
        type="bool",
        default=True,   # Curada en _CURATED_DEFAULTS_ON de tests/test_harness_flags.py.
        label="Panel de repositorio en la consola",
        description=(
            "Plan 265 — Muestra archivos modificados y sus diferencias, de SOLO "
            "LECTURA, sobre el workspace de la corrida. Sin repositorio, sin git "
            "instalado o si expira el tiempo, el panel lo dice y no rompe nada."
        ),
        group="global",
        requires="STACKY_CONSOLE_FULLSCREEN_ENABLED",
    ),
    FlagSpec(
        key="STACKY_CONSOLE_AUDIT_LOG_ENABLED",
        type="bool",
        default=True,   # Curada en _CURATED_DEFAULTS_ON de tests/test_harness_flags.py.
        label="Bitacora de acciones de la consola",
        description=(
            "Plan 265 — Registra que acciones disparo el operador desde la consola "
            "(cancelar, volver a lanzar, copiar) en el directorio de datos de Stacky. "
            "Es registro, no restriccion: mono-operador, sin RBAC."
        ),
        group="global",
        requires="STACKY_CONSOLE_FULLSCREEN_ENABLED",
    ),
    # =====================================================================
    # Plan 283 — El calendario de reuniones: de la transcripcion a los
    # pendientes accionables. Cinco entradas: un master, dos de conexion con
    # el calendario de Microsoft (valores, no interruptores) y la de
    # publicacion, que es la unica que escribe afuera.
    # REGLA R4 (profundidad 1): las 4 hijas cuelgan del master, y el master NO
    # declara `requires`.
    # =====================================================================
    FlagSpec(
        key="STACKY_MEETINGS_ENABLED",
        type="bool",
        default=True,   # Curada en _CURATED_DEFAULTS_ON de tests/test_harness_flags.py.
                        # Nace ON: ninguna excepcion aplica. Lee y escribe SOLO en
                        # la base local de Stacky, y no gasta nada en reposo (D7
                        # prohibe hilos, temporizadores y barridos; hay un gate por
                        # AST que lo verifica).
        label="Reuniones: minutas y pendientes a partir de una transcripcion",
        description=(
            "Plan 283 - Habilita la seccion Reuniones: el operador pega o sube la "
            "transcripcion de una reunion y Stacky devuelve minuta, decisiones, "
            "riesgos y pendientes con su fecha. Cada pendiente exige una cita "
            "textual verificada contra la transcripcion. OFF: la seccion no se "
            "pinta y sus rutas devuelven 404."
        ),
        group="global",
        env_only=False,  # editable por UI (regla dura operator-config-always-via-ui)
    ),
    FlagSpec(
        key="STACKY_MEETINGS_GRAPH_ENABLED",
        type="bool",
        default=True,   # Curada en _CURATED_DEFAULTS_ON de tests/test_harness_flags.py.
                        # Nace ON: conector de SOLO LECTURA y ON-DEMAND (se dispara
                        # por request del operador, nunca solo). "Prerequisito no
                        # garantizado en una instalacion default" NO es excepcion
                        # valida: sin credenciales degrada con un aviso accionable
                        # y el camino manual sigue entero.
        label="Traer las reuniones y sus transcripciones del calendario de Microsoft",
        description=(
            "Plan 283 - Permite listar las reuniones proximas del calendario del "
            "operador y descargar la transcripcion de una reunion sin copiarla a "
            "mano. Solo lectura y solo cuando el operador lo pide: no hay ningun "
            "proceso que sincronice por su cuenta. OFF: queda el camino manual, "
            "que cubre el ciclo completo."
        ),
        group="global",
        env_only=False,
        requires="STACKY_MEETINGS_ENABLED",
    ),
    FlagSpec(
        key="STACKY_MEETINGS_PUBLISH_ENABLED",
        # SIN default= A PROPOSITO (regla dura): una flag default OFF NO declara
        # default=False, porque `default_is_known(spec)` es literalmente
        # `spec.default is not None` y eso la meteria en el conjunto que
        # test_default_known_only_for_curated exige que sea EXACTAMENTE
        # _CURATED_DEFAULTS_ON. El OFF vive SOLO en config.py.
        # Nace OFF por EXCEPCION (B): es lo unico de este plan que ESCRIBE en un
        # sistema real del operador — crea work items en su Azure DevOps o
        # GitLab via create_item(). Mismo precedente que
        # STACKY_PIPELINE_NL_EDIT_COMMIT_ENABLED: ver y proponer va ON, escribir
        # de verdad va OFF. Aun encendida exige una confirmacion de un solo uso.
        type="bool",
        label="Convertir un pendiente de la reunion en una tarea del sistema de tickets",
        description=(
            "Plan 283 - Decide si Stacky puede crear tareas reales a partir de los "
            "pendientes de una reunion. Nace APAGADA: aun encendida exige una "
            "confirmacion explicita por cada publicacion, y nunca asigna un "
            "responsable que no se haya podido verificar contra los que hablaron "
            "en la reunion. OFF: el pendiente se ve y se edita solo dentro de Stacky."
        ),
        group="global",
        env_only=False,
        requires="STACKY_MEETINGS_ENABLED",
    ),
    FlagSpec(
        key="STACKY_MEETINGS_GRAPH_TENANT",
        # SIN default= A PROPOSITO: es `str` y `default_is_known` es
        # type-agnostico (`spec.default is not None`), asi que declarar cualquier
        # valor rompe la biyeccion con _CURATED_DEFAULTS_ON. El default efectivo
        # es "" en config.py, y "common" se resuelve en services/graph_client.py
        # cuando el valor esta vacio: asi el panel no miente sobre lo que hay.
        type="str",
        label="Organizacion de Microsoft del calendario",
        description=(
            "Plan 283 - Nombre o identificador de la organizacion de Microsoft "
            "contra la que se pide el permiso de lectura del calendario. Vacio "
            "usa el valor generico, que sirve para cuentas personales y para la "
            "mayoria de las organizaciones."
        ),
        group="global",
        env_only=False,
        requires="STACKY_MEETINGS_ENABLED",
    ),
    FlagSpec(
        key="STACKY_MEETINGS_GRAPH_CLIENT_ID",
        # SIN default= A PROPOSITO: misma razon que la anterior.
        # El SECRETO no vive aca: el refresco de la sesion se guarda cifrado con
        # DPAPI en backend/projects/<PROYECTO>/auth/graph_auth.json.
        type="str",
        label="Identificador de la aplicacion registrada en Microsoft",
        description=(
            "Plan 283 - Identificador publico de la aplicacion que la organizacion "
            "dio de alta para que Stacky pueda pedir permiso de lectura del "
            "calendario. No es un secreto y no se guarda cifrado; la credencial "
            "de sesion si se cifra en el equipo del operador. Vacio deshabilita "
            "la conexion con un aviso, sin romper el camino manual."
        ),
        group="global",
        env_only=False,
        requires="STACKY_MEETINGS_ENABLED",
    ),
    # ── Plan 35 — Aprendizaje del arnés: patrones reutilizables ──────────────
    # Grupo "contexto_memoria" (categoría EXISTENTE, decisión C6 del plan): un
    # grupo nuevo sin entrada en _CATEGORY_KEYS pone rojo el CI a propósito.
    # Las 4 tienen env_only=False y su atributo correspondiente en config.py:
    # sin eso quedarían INERTES (el getattr del consumidor cae al default).
    FlagSpec(
        key="STACKY_HARNESS_LEARNING_HARVEST_ENABLED",
        type="bool",
        label="Aprendizaje del arnés: cosechar (F1)",
        description=(
            "35.F1 — Post-run cosecha fallos/remedios como patrones. Pasivo, sin LLM."
        ),
        group="contexto_memoria",
        env_only=False,
        default=True,
    ),
    FlagSpec(
        key="STACKY_HARNESS_LEARNING_INJECT_ENABLED",
        type="bool",
        label="Aprendizaje del arnés: reinyectar (F2)",
        description=(
            "35.F2 — Inyecta pistas de fallos conocidos (podables, prioridad 45)."
        ),
        group="contexto_memoria",
        env_only=False,
        default=True,
    ),
    FlagSpec(
        key="STACKY_HARNESS_LEARNING_INJECT_MAX",
        # SIN default= A PROPOSITO: default_is_known es `spec.default is not
        # None` (type-agnóstico), así que declarar default=5 la metería en
        # known_keys y rompería test_default_known_only_for_curated, que compara
        # por IGUALDAD contra _CURATED_DEFAULTS_ON. El default EFECTIVO (5) lo
        # fija backend/config.py.
        type="int",
        label="Máx. patrones por run",
        description="35.F2 — Cuántas pistas como máximo inyectar (default 5).",
        group="contexto_memoria",
        env_only=False,
        # SIN requires= : `test_requires_map_is_frozen` congela el mapa de
        # dependencias y declararlo metería drift en un ratchet que este plan no
        # toca. La referencia canónica de §F4 tampoco lo declara.
    ),
    FlagSpec(
        key="STACKY_HARNESS_LEARNING_INJECT_MIN_CONF",
        # SIN default= A PROPOSITO: misma razón que la anterior. El default
        # EFECTIVO (0.5) lo fija backend/config.py.
        type="float",
        label="Confianza mínima de pista",
        description=(
            "35.F2/F3 — Solo inyecta patrones con confidence >= este valor (default 0.5)."
        ),
        group="contexto_memoria",
        env_only=False,
        # SIN requires= : misma razón que la anterior.
    ),
    # ── Plan 287 — la ficha del ticket a pantalla completa ────────────────────
    FlagSpec(
        key="STACKY_TICKET_FULLVIEW_ENABLED",
        type="bool",
        label="Ficha del ticket a pantalla completa",
        description=(
            "Plan 287 — Habilita abrir un ticket en una ficha a pantalla completa "
            "con descripcion, comentarios, adjuntos, historial e hijos, y navegar "
            "padre/hijos/hermanos sin cerrarla. Solo lectura y presentacion."
        ),
        group="global",
        env_only=False,
        default=True,
        # SIN requires= a proposito: ver Plan 287 seccion 5.1.
    ),
    FlagSpec(
        key="STACKY_TICKET_HISTORY_API_ENABLED",
        type="bool",
        label="Historial de cambios del ticket",
        description=(
            "Plan 287 — Expone el historial de cambios del ticket leyendolo del "
            "puerto TrackerProvider (fetch_item_updates), igual para Azure DevOps "
            "y GitLab. Se consulta solo cuando el operador abre el panel."
        ),
        group="global",
        env_only=False,
        default=True,
    ),
    FlagSpec(
        key="STACKY_TRACKER_CAPABILITIES_API_ENABLED",
        type="bool",
        label="Avisar que un panel viene incompleto",
        description=(
            "Plan 287 — Publica el estado declarado de cada capacidad del tracker "
            "activo para que cada panel de la ficha avise cuando su informacion "
            "viene parcial, y con que perdida. Lee un diccionario en memoria."
        ),
        group="global",
        env_only=False,
        default=True,
    ),
    # ── Plan 288 — el selector de modelos deja de mentir ──────────────────────
    FlagSpec(
        key="STACKY_CLAUDE_ACCOUNT_MODELS_ENABLED",
        type="bool",
        label="Modelos habilitados en tu cuenta de Claude Code",
        description=(
            "Plan 288 — Lee del disco local lo que el programa de Claude Code ya "
            "guardo sobre esta cuenta (modelos usados, opciones extra ofrecidas y "
            "tipo de suscripcion) y SUMA al catalogo solo los que Stacky puede "
            "ejecutar de verdad; lo descartado se informa con su motivo. Solo "
            "lectura: sin red, sin credenciales y sin gasto. Nunca resta modelos."
        ),
        group="global",
        env_only=False,
        default=True,
        # SIN requires= a proposito: ver Plan 288 seccion 5.2 pata 5.
    ),
    # ── Plan 289 — el agente deja de trabajar a ciegas sobre un ticket de GitLab ──
    FlagSpec(
        key="STACKY_TRACKER_CONTEXT_ENABLED",
        type="bool",
        label="Comentarios del ticket en el contexto del agente (GitLab)",
        description=(
            "Plan 289 — Cuando el proyecto no usa Azure DevOps, Stacky lee los "
            "comentarios del ticket por la costura de proveedor y los inyecta al "
            "contexto del agente, igual que ya hace con Azure DevOps. Solo LECTURA: "
            "no escribe nada en el tracker. Apagarla devuelve el comportamiento "
            "previo al plan (el agente trabaja sin los comentarios del issue)."
        ),
        group="global",
        env_only=False,
        # Curada en _CURATED_DEFAULTS_ON (test_default_known_only_for_curated).
        default=True,
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
