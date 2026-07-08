import logging
import os
from pathlib import Path
from dotenv import load_dotenv

from runtime_paths import (
    backend_root,
    data_dir,
    runtime_config,
    stacky_agents_dir,
)

BACKEND_ROOT = backend_root()
load_dotenv(BACKEND_ROOT / ".env")
load_dotenv(Path.cwd() / ".env")
_RUNTIME_CONFIG = runtime_config()
_config_logger = logging.getLogger("stacky.config")


def _project_agents_dir_if_configured() -> Path | None:
    try:
        from project_manager import get_active_project, get_project_config

        active = get_active_project()
        cfg = get_project_config(active) if active else None
    except Exception:  # noqa: BLE001
        return None

    raw = ((cfg or {}).get("agents_dir") or "").strip()
    if not raw:
        return None

    candidate = Path(raw).expanduser()
    if candidate.is_dir():
        return candidate.resolve()

    _config_logger.warning(
        "agents_dir configurado para el proyecto activo no existe o no es carpeta: %s. "
        "Uso la fuente canónica de Stacky Agents.",
        raw,
    )
    return None


def _legacy_prompts_override_enabled() -> bool:
    return os.getenv("STACKY_ALLOW_VSCODE_PROMPTS_OVERRIDE", "").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


class Config:
    PORT = int(os.getenv("PORT") or _RUNTIME_CONFIG.get("port") or "5050")
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

    DATABASE_URL = os.getenv(
        "DATABASE_URL", f"sqlite:///{data_dir() / 'stacky_agents.db'}"
    )

    _runtime_allowed_origins = _RUNTIME_CONFIG.get("allowed_origins") or []
    if isinstance(_runtime_allowed_origins, str):
        _runtime_allowed_origins = [_runtime_allowed_origins]
    ALLOWED_ORIGINS = [
        o.strip()
        for o in os.getenv(
            "ALLOWED_ORIGINS",
            ",".join(_runtime_allowed_origins) or "http://localhost:5173",
        ).split(",")
        if o.strip()
    ]
    ENABLE_CORS = os.getenv("STACKY_ENABLE_CORS", "").lower() in {"1", "true", "yes", "on"}

    LLM_BACKEND = os.getenv("LLM_BACKEND", "vscode_bridge")
    LLM_MODEL = os.getenv("LLM_MODEL", "claude-sonnet-4.5")

    # Copilot Chat API
    COPILOT_MODEL = os.getenv("COPILOT_MODEL", "gpt-4.1")
    # GitHub Models API acepta el gho_ token directamente como Bearer.
    # api.githubcopilot.com/chat/completions requiere un internal token que
    # solo se puede obtener via OAuth app de VS Code (no via gh CLI).
    COPILOT_ENDPOINT = os.getenv(
        "COPILOT_ENDPOINT", "https://models.inference.ai.azure.com/chat/completions"
    )
    # Catalog de modelos disponibles (short IDs que acepta el inference endpoint)
    COPILOT_MODELS_ENDPOINT = os.getenv(
        "COPILOT_MODELS_ENDPOINT", "https://models.github.ai/catalog/models"
    )
    COPILOT_INTEGRATION_ID = os.getenv("COPILOT_INTEGRATION_ID", "vscode-chat")

    # Puerto del bridge HTTP de la extensión VS Code
    VSCODE_BRIDGE_PORT = int(os.getenv("VSCODE_BRIDGE_PORT", "5052"))

    # VSCODE_PROMPTS_DIR se conserva como nombre de compatibilidad para APIs y
    # runners existentes, pero siempre apunta a Stacky/agents.
    @property
    def VSCODE_PROMPTS_DIR(self) -> str:
        canonical = stacky_agents_dir()
        project_agents_dir = _project_agents_dir_if_configured()
        if project_agents_dir is not None and project_agents_dir.resolve() != canonical.resolve():
            _config_logger.warning(
                "agents_dir de proyecto ignorado (%s): Stacky/agents es la "
                "fuente canónica (%s).",
                project_agents_dir,
                canonical,
            )
        env_val = os.getenv("VSCODE_PROMPTS_DIR")
        if env_val and Path(env_val).expanduser().resolve() != canonical.resolve():
            _config_logger.warning(
                "VSCODE_PROMPTS_DIR=%s ignorado: Stacky/agents es la fuente "
                "canónica (%s).",
                env_val,
                canonical,
            )
        if _legacy_prompts_override_enabled():
            _config_logger.warning(
                "STACKY_ALLOW_VSCODE_PROMPTS_OVERRIDE está seteado pero ya no "
                "habilita fuentes legacy; se usa %s.",
                canonical,
            )
        return str(canonical)

    # Codex CLI runtime
    CODEX_CLI_BIN = os.getenv("CODEX_CLI_BIN", "codex")
    CODEX_CLI_MODEL = os.getenv("CODEX_CLI_MODEL", "")
    CODEX_CLI_SANDBOX = os.getenv("CODEX_CLI_SANDBOX", "danger-full-access")
    CODEX_CLI_APPROVAL = os.getenv("CODEX_CLI_APPROVAL", "never")
    # ── H2 — Paridad codex_cli ────────────────────────────────────────────────
    # H2.1 — Gate de contrato post-run (mismo patrón que F1.1 para claude).
    # Si ON, outputs con errores duros degradan a needs_review.
    CODEX_CLI_CONTRACT_GATE_ENABLED: bool = os.getenv(
        "CODEX_CLI_CONTRACT_GATE_ENABLED", "false"
    ).lower() in ("1", "true", "yes")
    # H2.3 — Loop de autocorrección via codex exec resume.
    CODEX_CLI_AUTOCORRECT_ENABLED: bool = os.getenv(
        "CODEX_CLI_AUTOCORRECT_ENABLED", "false"
    ).lower() in ("1", "true", "yes")
    CODEX_CLI_AUTOCORRECT_MAX_RETRIES: int = int(
        os.getenv("CODEX_CLI_AUTOCORRECT_MAX_RETRIES", "2")
    )
    # H2.4 — Denylist de modelos para codex (CSV, default vacío = sin restricción).
    CODEX_CLI_MODEL_DENYLIST: str = os.getenv("CODEX_CLI_MODEL_DENYLIST", "")
    # H7.1 — Re-runs con exec resume + delta prompt para codex. OFF default; allowlist
    # CSV vacía = todos los proyectos (mismo patrón que CLAUDE_CODE_CLI_RESUME_*).
    CODEX_CLI_RESUME_ENABLED: bool = os.getenv(
        "CODEX_CLI_RESUME_ENABLED", "false"
    ).lower() in ("1", "true", "yes")
    CODEX_CLI_RESUME_PROJECTS: str = os.getenv("CODEX_CLI_RESUME_PROJECTS", "")

    # Claude Code CLI runtime
    CLAUDE_CODE_CLI_BIN = os.getenv("CLAUDE_CODE_CLI_BIN", "claude")
    # Modelo por defecto FIJO para toda invocación del CLI (requisito operador):
    # sonnet 4.6. Configurable vía .env; vacío = delegar al router (legacy).
    CLAUDE_CODE_CLI_MODEL = os.getenv("CLAUDE_CODE_CLI_MODEL", "claude-sonnet-4-6")
    # Reasoning effort del CLI (`--effort`). Valores válidos: low|medium|high.
    # Default fijo: medium. Vacío o inválido = no se pasa el flag.
    CLAUDE_CODE_CLI_EFFORT = os.getenv("CLAUDE_CODE_CLI_EFFORT", "medium")
    # Cap de sesión en segundos para una ejecución interactiva de Claude Code CLI.
    # Plan 37 (F3.1) — default FINITO (30 min) para que un run colgado no quede
    # zombie indefinido ("sin límite de sesión" gastando la cuenta). 0 = ilimitado
    # (opt-in explícito). >0 = mata la sesión tras N seg (ver claude_code_cli_runner
    # :889-902, que cierra stdin + terminate al vencer session_deadline).
    CLAUDE_CODE_CLI_TIMEOUT = int(os.getenv("CLAUDE_CODE_CLI_TIMEOUT", "1800"))
    # Modo de permisos para tool calls en modo non-interactive (-p).
    # Choices del CLI: acceptEdits | auto | bypassPermissions | default | dontAsk | plan.
    # "acceptEdits" auto-acepta ediciones de archivos sin prompts (el equivalente
    # razonable para un agente autónomo; en -p no hay forma de aprobar interactivo).
    CLAUDE_CODE_CLI_PERMISSION_MODE = os.getenv("CLAUDE_CODE_CLI_PERMISSION_MODE", "acceptEdits")
    # Si true, pasa --dangerously-skip-permissions (bypass total, equivalente a
    # danger-full-access de Codex). Tiene prioridad sobre el permission mode.
    # Default TRUE por decisión vinculante del operador (PLAN-ROBUSTECIMIENTO-
    # ARNES.md §5.3, 2026-06-09): el runtime CLI corre SIEMPRE sin prompts de
    # permisos; la mitigación es la validación de artifacts (F1.3/F1.4), no
    # permisos. La rama acceptEdits queda como flag de emergencia (=false).
    CLAUDE_CODE_CLI_SKIP_PERMISSIONS = os.getenv(
        "CLAUDE_CODE_CLI_SKIP_PERMISSIONS", "true"
    ).lower() in ("1", "true", "yes")
    # ── Fase 1 plan robustecimiento arnés (2026-06-09) ────────────────────────
    # F1.1 — Si true, contrato con errores duros degrada el run a needs_review
    # en vez de completed (la validación/persistencia de contract_result y
    # confidence corre SIEMPRE; esto solo gobierna el cambio de status).
    CLAUDE_CODE_CLI_CONTRACT_GATE_ENABLED = os.getenv(
        "CLAUDE_CODE_CLI_CONTRACT_GATE_ENABLED", "false"
    ).lower() in ("1", "true", "yes")
    # F1.3 — Loop de autocorrección sobre stdin al fin de cada turno.
    CLAUDE_CODE_CLI_AUTOCORRECT_ENABLED = os.getenv(
        "CLAUDE_CODE_CLI_AUTOCORRECT_ENABLED", "false"
    ).lower() in ("1", "true", "yes")
    # Cap de mensajes correctivos por run (plan: máx 1-2).
    CLAUDE_CODE_CLI_AUTOCORRECT_MAX_RETRIES = int(
        os.getenv("CLAUDE_CODE_CLI_AUTOCORRECT_MAX_RETRIES", "2")
    )
    # F1.4 — settings.json efímero con hook PostToolUse de validación de
    # artifacts, pasado vía --settings. Solo hooks; NO toca permisos (§5.3).
    CLAUDE_CODE_CLI_HOOKS_ENABLED = os.getenv(
        "CLAUDE_CODE_CLI_HOOKS_ENABLED", "false"
    ).lower() in ("1", "true", "yes")
    # Cómo se referencia la persona del agente (.agent.md) al CLI:
    #   "append" (default): vía --append-system-prompt-file se envía solo el
    #                       contrato/ruta del .agent.md. El contenido del agente
    #                       no se copia al prompt; el user message lleva ticket+contexto.
    #   "user_message":     rollback: el contrato/ruta va en el primer mensaje de
    #                       usuario, también sin copiar el contenido del .agent.md.
    CLAUDE_CODE_CLI_SYSTEM_PROMPT_MODE = os.getenv(
        "CLAUDE_CODE_CLI_SYSTEM_PROMPT_MODE", "append"
    ).strip().lower()
    # ── Fase 2 plan robustecimiento arnés (2026-06-09) ────────────────────────
    # Todas estas features son por proyecto y OFF por default (regla §4.1: cero
    # fricción nueva al operador). El encendido por proyecto se hace con una
    # allowlist de nombres de proyecto Stacky (CSV); el flag *_ENABLED es el
    # master global (debe estar ON además de que el proyecto esté en la lista).
    # Lista vacía + master ON = todos los proyectos (escape hatch de staging).
    #
    # F2.2 — Conocimiento del proyecto (anti-patterns/decisiones/constraints/
    # glossary) en el system prompt del CLI. Dueño único por tipo (anti B6).
    CLAUDE_CODE_CLI_PROJECT_KNOWLEDGE_ENABLED = os.getenv(
        "CLAUDE_CODE_CLI_PROJECT_KNOWLEDGE_ENABLED", "false"
    ).lower() in ("1", "true", "yes")
    CLAUDE_CODE_CLI_PROJECT_KNOWLEDGE_PROJECTS = os.getenv(
        "CLAUDE_CODE_CLI_PROJECT_KNOWLEDGE_PROJECTS", ""
    )
    # F2.3 — Re-runs con --resume + delta prompt (usa session_id de F1.2).
    CLAUDE_CODE_CLI_RESUME_ENABLED = os.getenv(
        "CLAUDE_CODE_CLI_RESUME_ENABLED", "false"
    ).lower() in ("1", "true", "yes")
    CLAUDE_CODE_CLI_RESUME_PROJECTS = os.getenv(
        "CLAUDE_CODE_CLI_RESUME_PROJECTS", ""
    )
    # F2.4 — Presupuesto de contexto con ranking en enrich_blocks. El budget es
    # global (en tokens estimados); el encendido es por proyecto.
    STACKY_CONTEXT_BUDGET_ENABLED = os.getenv(
        "STACKY_CONTEXT_BUDGET_ENABLED", "true"
    ).lower() in ("1", "true", "yes")
    STACKY_CONTEXT_BUDGET_PROJECTS = os.getenv(
        "STACKY_CONTEXT_BUDGET_PROJECTS", ""
    )
    STACKY_CONTEXT_BUDGET_TOKENS = int(
        os.getenv("STACKY_CONTEXT_BUDGET_TOKENS", "25000")
    )
    # I0.1 — Dedup léxico de hechos repetidos entre bloques de contexto.
    # OFF default (retro-compat byte-idéntica). El dedup corre ANTES del budget.
    STACKY_CONTEXT_DEDUP_ENABLED: bool = os.getenv(
        "STACKY_CONTEXT_DEDUP_ENABLED", "true"
    ).lower() in ("1", "true", "yes")
    STACKY_CONTEXT_DEDUP_PROJECTS: str = os.getenv("STACKY_CONTEXT_DEDUP_PROJECTS", "")
    # F2.5 — Memoria colaborativa en el CLI, por proyecto. Reusa el flag global
    # STACKY_MEMORY_INJECTION_ENABLED (master) + esta allowlist (por proyecto).
    STACKY_MEMORY_INJECTION_PROJECTS = os.getenv(
        "STACKY_MEMORY_INJECTION_PROJECTS", ""
    )
    # M0.1 — Caps de contexto por agente configurables (JSON). "" = usar los
    # _AGENT_CAPS hardcodeados (byte-idéntico). Shape: {"developer":[16,16000]}.
    STACKY_MEMORY_CAPS_JSON = os.getenv("STACKY_MEMORY_CAPS_JSON", "")
    # M0.3 — Cadencia del barrido de revisión (review_after vencido → needs_review).
    # 0 = off (default, byte-idéntico). >0 = horas entre barridos.
    STACKY_MEMORY_REVIEW_SWEEP_HOURS = int(
        os.getenv("STACKY_MEMORY_REVIEW_SWEEP_HOURS", "0")
    )
    # M1.2 — Techo de chars reservado a la sección de directivas obligatorias
    # dentro del bloque stacky-memory. El slice real es min(char_cap//2, este).
    STACKY_MEMORY_DIRECTIVE_MAX_CHARS = int(
        os.getenv("STACKY_MEMORY_DIRECTIVE_MAX_CHARS", "4000")
    )
    # M3.1 — Scopes inyectables configurables. "" = default histórico
    # project,team,global (byte-idéntico). Leído en call time por cli_feature_flags.
    STACKY_MEMORY_INJECT_SCOPES = os.getenv("STACKY_MEMORY_INJECT_SCOPES", "")
    # F2.1 — Stacky MCP server inyectado vía --mcp-config. Por proyecto, OFF default.
    CLAUDE_CODE_CLI_MCP_ENABLED = os.getenv(
        "CLAUDE_CODE_CLI_MCP_ENABLED", "false"
    ).lower() in ("1", "true", "yes")
    CLAUDE_CODE_CLI_MCP_PROJECTS = os.getenv(
        "CLAUDE_CODE_CLI_MCP_PROJECTS", ""
    )
    # ── H4 — Stacky Skills ───────────────────────────────────────────────────
    # H4.3 — Inyección de skills en el system prompt. OFF por default; allowlist
    # CSV de proyectos vacía = todos (escape hatch cuando master está ON).
    STACKY_SKILLS_ENABLED: bool = os.getenv(
        "STACKY_SKILLS_ENABLED", "true"
    ).lower() in ("1", "true", "yes")
    STACKY_SKILLS_PROJECTS: str = os.getenv("STACKY_SKILLS_PROJECTS", "")
    # ── H5 — Runaway guard in-run ─────────────────────────────────────────────
    # Límite de turnos por run agéntico. 0 = sin límite (desactivado).
    # Al superar el límite, el run recibe señal de cierre+resumen y termina
    # con status needs_review + metadata["runaway"].
    STACKY_RUNAWAY_MAX_TURNS: int = int(
        os.getenv("STACKY_RUNAWAY_MAX_TURNS", "0")
    )
    # Límite de costo USD por run agéntico. 0.0 = sin límite (desactivado).
    STACKY_RUNAWAY_MAX_COST_USD: float = float(
        os.getenv("STACKY_RUNAWAY_MAX_COST_USD", "0.0")
    )
    # ── V0.3 — Cap de concurrencia de runs CLI ────────────────────────────────
    # Techo de subprocesos CLI simultáneos. 0 = ilimitado (retro-compat).
    STACKY_MAX_CONCURRENT_RUNS: int = int(
        os.getenv("STACKY_MAX_CONCURRENT_RUNS", "0")
    )

    # ── Plan 23 (Fase U0) — capa perceptible ───────────────────────────────
    STACKY_ADO_RUN_FOOTER_ENABLED: bool = os.getenv(
        "STACKY_ADO_RUN_FOOTER_ENABLED", "false"
    ).lower() in ("1", "true", "yes")
    STACKY_WEBHOOKS_V2_ENABLED: bool = os.getenv(
        "STACKY_WEBHOOKS_V2_ENABLED", "false"
    ).lower() in ("1", "true", "yes")
    STACKY_DESKTOP_NOTIFY_ENABLED: bool = os.getenv(
        "STACKY_DESKTOP_NOTIFY_ENABLED", "false"
    ).lower() in ("1", "true", "yes")
    STACKY_LIVE_TELEMETRY_ENABLED: bool = os.getenv(
        "STACKY_LIVE_TELEMETRY_ENABLED", "false"
    ).lower() in ("1", "true", "yes")
    # ── U1.2 — Self-review contra acceptance criteria ───────────────────────
    # off: no ejecuta review (retro-compat exacta)
    # annotate: guarda checklist/score en metadata sin bloquear publish
    # gate: score < MIN_SCORE degrada a needs_review
    STACKY_SELF_REVIEW_MODE: str = os.getenv(
        "STACKY_SELF_REVIEW_MODE", "off"
    ).strip().lower()
    STACKY_SELF_REVIEW_MIN_SCORE: float = float(
        os.getenv("STACKY_SELF_REVIEW_MIN_SCORE", "0.7")
    )
    # ── U1.3 — Feedback de fallo en ADO ─────────────────────────────────────
    STACKY_ADO_FAILURE_COMMENT_ENABLED: bool = os.getenv(
        "STACKY_ADO_FAILURE_COMMENT_ENABLED", "false"
    ).lower() in ("1", "true", "yes")
    # ── U1.5 — Digest de valor periódico ─────────────────────────────────────
    # 0 = desactivado (default)
    STACKY_DIGEST_INTERVAL_HOURS: int = int(
        os.getenv("STACKY_DIGEST_INTERVAL_HOURS", "0")
    )
    STACKY_PIPELINES_ENABLED: bool = os.getenv(
        "STACKY_PIPELINES_ENABLED", "false"
    ).lower() in ("1", "true", "yes")
    # ── V0.1 — Perfil del arnés aplicado en boot ──────────────────────────────
    # "" (default) = no aplicar perfil. "off"|"safe"|"full" = aplicar en startup,
    # respetando env vars individuales seteadas explícitamente por el operador.
    STACKY_HARNESS_PROFILE: str = os.getenv("STACKY_HARNESS_PROFILE", "").strip().lower()

    # ── Plan 31 — Verificación ejecutable del entregable (E0.1-E2.2) ─────────
    # E0.1 — Motor de verificación ejecutable. Todos OFF por default → retro-compat.
    STACKY_EXEC_VERIFICATION_ENABLED: bool = os.getenv(
        "STACKY_EXEC_VERIFICATION_ENABLED", "true"
    ).lower() in ("1", "true", "yes")
    # off | annotate | gate — governs whether hard failures block completion.
    # Default 'annotate' (Grupo B): solo anota, NUNCA bloquea. EXEC_REPAIR queda OFF.
    STACKY_EXEC_VERIFICATION_MODE: str = os.getenv(
        "STACKY_EXEC_VERIFICATION_MODE", "annotate"
    ).strip().lower()
    STACKY_EXEC_VERIFICATION_TIMEOUT_S: int = int(
        os.getenv("STACKY_EXEC_VERIFICATION_TIMEOUT_S", "120")
    )
    STACKY_EXEC_VERIFICATION_BUDGET_S: int = int(
        os.getenv("STACKY_EXEC_VERIFICATION_BUDGET_S", "300")
    )
    # CSV de proyectos Stacky donde corre. Vacío = todos (cuando master ON).
    STACKY_EXEC_VERIFICATION_PROJECTS: str = os.getenv(
        "STACKY_EXEC_VERIFICATION_PROJECTS", ""
    )
    # E1.1 — Gate + pase correctivo único dirigido al fallo ejecutable.
    STACKY_EXEC_REPAIR_ENABLED: bool = os.getenv(
        "STACKY_EXEC_REPAIR_ENABLED", "false"
    ).lower() in ("1", "true", "yes")
    STACKY_EXEC_REPAIR_MAX_RETRIES: int = int(
        os.getenv("STACKY_EXEC_REPAIR_MAX_RETRIES", "1")
    )
    # E1.2 — Guard anti-verde-falso (soft por defecto; HARD si _HARD=true).
    STACKY_FAKE_GREEN_GUARD_ENABLED: bool = os.getenv(
        "STACKY_FAKE_GREEN_GUARD_ENABLED", "true"
    ).lower() in ("1", "true", "yes")
    STACKY_FAKE_GREEN_GUARD_HARD: bool = os.getenv(
        "STACKY_FAKE_GREEN_GUARD_HARD", "false"
    ).lower() in ("1", "true", "yes")
    # E2.1 — Bloque exec_verification en el payload de la ejecución (read-only).
    STACKY_EXEC_VERIFICATION_VERDICT_CARD_ENABLED: bool = os.getenv(
        "STACKY_EXEC_VERIFICATION_VERDICT_CARD_ENABLED", "false"
    ).lower() in ("1", "true", "yes")
    # E2.2 — KPIs de verificación ejecutable en harness_health.
    STACKY_EXEC_VERIFICATION_KPIS_ENABLED: bool = os.getenv(
        "STACKY_EXEC_VERIFICATION_KPIS_ENABLED", "true"
    ).lower() in ("1", "true", "yes")

    # ── Plan 32 — Contrato de Aceptación Ejecutable (A0.1-A2.2) ─────────────
    # A0.1 — Derivador de contrato + juez determinista.
    STACKY_ACCEPTANCE_CONTRACT_ENABLED: bool = os.getenv(
        "STACKY_ACCEPTANCE_CONTRACT_ENABLED", "false"
    ).lower() in ("1", "true", "yes")
    # off | annotate | gate
    STACKY_ACCEPTANCE_CONTRACT_MODE: str = os.getenv(
        "STACKY_ACCEPTANCE_CONTRACT_MODE", "off"
    ).strip().lower()
    STACKY_ACCEPTANCE_CONTRACT_MAX_CHECKS: int = int(
        os.getenv("STACKY_ACCEPTANCE_CONTRACT_MAX_CHECKS", "4")
    )
    STACKY_ACCEPTANCE_CONTRACT_PROJECTS: str = os.getenv(
        "STACKY_ACCEPTANCE_CONTRACT_PROJECTS", ""
    )
    # A1.1 — Inyección como blanco + gate + pase correctivo.
    STACKY_ACCEPTANCE_GATE_ENABLED: bool = os.getenv(
        "STACKY_ACCEPTANCE_GATE_ENABLED", "false"
    ).lower() in ("1", "true", "yes")
    STACKY_ACCEPTANCE_REPAIR_ENABLED: bool = os.getenv(
        "STACKY_ACCEPTANCE_REPAIR_ENABLED", "false"
    ).lower() in ("1", "true", "yes")
    STACKY_ACCEPTANCE_REPAIR_MAX_RETRIES: int = int(
        os.getenv("STACKY_ACCEPTANCE_REPAIR_MAX_RETRIES", "1")
    )
    # A1.2 — Guard de independencia (inmutabilidad del contrato).
    STACKY_ACCEPTANCE_INTEGRITY_ENABLED: bool = os.getenv(
        "STACKY_ACCEPTANCE_INTEGRITY_ENABLED", "false"
    ).lower() in ("1", "true", "yes")
    # A2.1 — Bloque acceptance_contract en el payload de la ejecución (read-only).
    STACKY_ACCEPTANCE_VERDICT_CARD_ENABLED: bool = os.getenv(
        "STACKY_ACCEPTANCE_VERDICT_CARD_ENABLED", "false"
    ).lower() in ("1", "true", "yes")
    # A2.2 — KPIs del contrato en harness_health.
    STACKY_ACCEPTANCE_KPIS_ENABLED: bool = os.getenv(
        "STACKY_ACCEPTANCE_KPIS_ENABLED", "true"
    ).lower() in ("1", "true", "yes")

    # ── Plan 39 — Historial de runs, fix épica CLI y BD read-only ────────────
    # C2 — Inyecta directiva de acceso a BD read-only en el perfil del cliente.
    #      NUNCA incluye el password. OFF por default (retro-compat).
    STACKY_DB_READONLY_DIRECTIVE_ENABLED: bool = os.getenv(
        "STACKY_DB_READONLY_DIRECTIVE_ENABLED", "true"
    ).lower() in ("1", "true", "yes")

    # ── Plan 58 — Bucle de convergencia de calidad determinista (épica) ────────
    # OFF por defecto: con OFF el pase correctivo de épica es single-shot (idéntico al actual).
    STACKY_QUALITY_CONVERGENCE_ENABLED: bool = os.getenv(
        "STACKY_QUALITY_CONVERGENCE_ENABLED", "false"
    ).lower() in ("1", "true", "yes")
    # Máximo de PASES CORRECTIVOS del bucle (>=1). 1 == single-shot actual. Default 2.
    STACKY_QUALITY_CONVERGENCE_MAX_ITERATIONS: int = int(
        os.getenv("STACKY_QUALITY_CONVERGENCE_MAX_ITERATIONS", "2")
    )
    # A1 — Habilita GET /api/executions/history con historial completo de runs.
    STACKY_EXECUTION_HISTORY_ENABLED: bool = os.getenv(
        "STACKY_EXECUTION_HISTORY_ENABLED", "true"
    ).lower() in ("1", "true", "yes")

    # ── Plan 67 — Disciplina de procesos: reutilizar por default ──────────────
    # OFF por defecto: con OFF enrich_blocks es byte-idéntico al plan 64.
    STACKY_PROCESS_DISCIPLINE_ENABLED: bool = os.getenv(
        "STACKY_PROCESS_DISCIPLINE_ENABLED", "false"
    ).lower() in ("1", "true", "yes")

    QA_BROWSER_DEFAULT_BASE_URL = os.getenv(
        "QA_BROWSER_DEFAULT_BASE_URL",
        "http://localhost:35017/AgendaWeb/",
    )

    ADO_ORG = os.getenv("ADO_ORG", "")
    ADO_PROJECT = os.getenv("ADO_PROJECT", "")
    ADO_PAT = os.getenv("ADO_PAT", "")

    CACHE_ENABLED = os.getenv("CACHE_ENABLED", "true").lower() == "true"

    # ── Gateway de finalización de agentes (Plan SSD P1) ─────────────────────
    # Valores: "off" (default) | "shadow" | "on"
    #   off    → endpoint no registrado / devuelve 404.
    #   shadow → corre en lectura/simulación, no muta DB ni ADO. P1.
    #   on     → gateway canónico activo. Reservado para P5.
    STACKY_COMPLETION_GATEWAY: str = os.getenv(
        "STACKY_COMPLETION_GATEWAY", "off"
    ).lower().strip()

    # Token simétrico que los agentes deben incluir en X-Stacky-Agent-Token.
    # Debe setearse en .env de producción. En tests se puede usar cualquier valor.
    STACKY_AGENT_TOKEN: str = os.getenv("STACKY_AGENT_TOKEN", "")

    # Pre-run workspace freshness (Plan memoria colaborativa Fase C).
    # Default seguro: diagnostico disponible, gate y pull apagados.
    STACKY_PRE_RUN_GIT_PULL_ENABLED = os.getenv(
        "STACKY_PRE_RUN_GIT_PULL_ENABLED", "false"
    ).lower() in {"1", "true", "yes", "on"}
    STACKY_PRE_RUN_GIT_PULL_REQUIRED = os.getenv(
        "STACKY_PRE_RUN_GIT_PULL_REQUIRED", "false"
    ).lower() in {"1", "true", "yes", "on"}
    STACKY_PRE_RUN_GIT_WORKSPACE_POLICY = os.getenv(
        "STACKY_PRE_RUN_GIT_WORKSPACE_POLICY", "fetch_only_warn"
    ).strip().lower()
    STACKY_PRE_RUN_GIT_TIMEOUT_SECONDS = int(os.getenv("STACKY_PRE_RUN_GIT_TIMEOUT_SECONDS", "30"))
    STACKY_PRE_RUN_GIT_LOCK_WAIT_SECONDS = int(os.getenv("STACKY_PRE_RUN_GIT_LOCK_WAIT_SECONDS", "5"))
    STACKY_PRE_RUN_TIMEOUT_SECONDS = int(os.getenv("STACKY_PRE_RUN_TIMEOUT_SECONDS", "90"))

    # Memoria colaborativa Fase D/E — gobernanza. Default seguro: el validador
    # solo corre los 4 checks baratos; los avanzados (dup-semántico, grafo de
    # conflictos, LLM judge) exigen opt-in. El git sync nace OFF: activarlo es un
    # acto explícito del operador (sign-off del cliente).
    STACKY_MEMORY_VALIDATOR_ADVANCED = os.getenv(
        "STACKY_MEMORY_VALIDATOR_ADVANCED", "false"
    ).lower() in {"1", "true", "yes", "on"}
    STACKY_MEMORY_GIT_SYNC_ENABLED = os.getenv(
        "STACKY_MEMORY_GIT_SYNC_ENABLED", "false"
    ).lower() in {"1", "true", "yes", "on"}

    # ── I0.2 — Cómputo consistente de fingerprint_complexity ─────────────────
    # OFF default: routing byte-idéntico. ON: estimate_complexity() se invoca
    # en los 3 runtimes y se pasa a llm_router.decide().
    STACKY_COMPLEXITY_ESTIMATION_ENABLED: bool = os.getenv(
        "STACKY_COMPLEXITY_ESTIMATION_ENABLED", "true"
    ).lower() in ("1", "true", "yes")

    # ── I1.1 — Auto-reparación del run ante output vacío/malformado ──────────
    # OFF default: comportamiento actual exacto. ON: un único reintento si el
    # output queda vacío/malformado y el runtime soporta resume.
    STACKY_RUN_REPAIR_ENABLED: bool = os.getenv(
        "STACKY_RUN_REPAIR_ENABLED", "true"
    ).lower() in ("1", "true", "yes")

    # ── I1.2 — Routing por dificultad estimada dentro del clamp ──────────────
    # OFF default: decide() comportamiento actual. ON: reglas de downgrade (S)
    # y upgrade (L/XL) dentro del clamp. Cap duro NUNCA se supera.
    STACKY_DIFFICULTY_ROUTING_ENABLED: bool = os.getenv(
        "STACKY_DIFFICULTY_ROUTING_ENABLED", "true"
    ).lower() in ("1", "true", "yes")

    # ── I3.2 — Caché en memoria de lecturas caras de ADO ─────────────────────
    # 0 = sin caché (byte-idéntico al comportamiento actual). >0 = TTL en
    # segundos: segunda lectura del mismo (project, ado_id, kind) dentro del
    # TTL no llama a ADO. Escritura exitosa en el outbox invalida el key.
    STACKY_ADO_READ_CACHE_TTL_SEC: int = int(
        os.getenv("STACKY_ADO_READ_CACHE_TTL_SEC", "0")
    )

    # ── I2.3 — Expansión y normalización de query para retrieval ─────────────
    # OFF default: tokenizer y ranking byte-idénticos. ON: fold de acentos +
    # sinónimos del dominio sobre el QUERY (corpus sin cambios).
    STACKY_RETRIEVAL_EXPANSION_ENABLED: bool = os.getenv(
        "STACKY_RETRIEVAL_EXPANSION_ENABLED", "false"
    ).lower() in ("1", "true", "yes")

    # ── I2.1 — Re-ranking de bloques por relevancia al ticket ─────────────────
    # OFF default: _apply_context_budget byte-idéntico. ON: la relevancia al
    # ticket (TF-IDF coseno) desempata el orden de conservación bajo presupuesto.
    STACKY_CONTEXT_RERANK_ENABLED: bool = os.getenv(
        "STACKY_CONTEXT_RERANK_ENABLED", "true"
    ).lower() in ("1", "true", "yes")

    # ── I3.1 — Paralelización de injectors independientes ────────────────────
    # OFF default: serial byte-idéntico. ON: similar_tickets + ado_context
    # corren en paralelo con ThreadPoolExecutor(max_workers=2).
    STACKY_PARALLEL_INJECTORS_ENABLED: bool = os.getenv(
        "STACKY_PARALLEL_INJECTORS_ENABLED", "true"
    ).lower() in ("1", "true", "yes")

    # ── I0.3 — Pre-warming del caché ADO al seleccionar el ticket ────────────
    # OFF default: POST /tickets/<ado_id>/prewarm devuelve {"status":"disabled"}.
    # Depende de I3.2 (STACKY_ADO_READ_CACHE_TTL_SEC > 0).
    STACKY_ADO_PREWARM_ENABLED: bool = os.getenv(
        "STACKY_ADO_PREWARM_ENABLED", "false"
    ).lower() in ("1", "true", "yes")

    # ── I3.3 — Asesor de caps de contexto por telemetría ─────────────────────
    # OFF default: GET /metrics/caps-advisor devuelve {"enabled": false}.
    # NUNCA escribe: solo produce sugerencias que el operador aplica.
    STACKY_CAPS_ADVISOR_ENABLED: bool = os.getenv(
        "STACKY_CAPS_ADVISOR_ENABLED", "false"
    ).lower() in ("1", "true", "yes")

    # ── Plan 28 — Lifecycle e higiene de procesos ─────────────────────────────
    # R0.1 — Reaping del subproceso al cerrar la ejecución.
    # OFF default (byte-idéntico). ON: terminate→wait(grace)→kill al cerrar/
    # marcar terminal. Solo actúa sobre el pid exacto registrado por el runner.
    STACKY_RUNNER_REAP_ON_CLOSE_ENABLED: bool = os.getenv(
        "STACKY_RUNNER_REAP_ON_CLOSE_ENABLED", "true"
    ).lower() in ("1", "true", "yes")

    # R0.2 — Flush incremental de logs.
    # OFF default. ON: persiste el buffer de log a DB antes de matar el proceso
    # (en reap) y periódicamente en el heartbeat.
    STACKY_LOG_FLUSH_INCREMENTAL_ENABLED: bool = os.getenv(
        "STACKY_LOG_FLUSH_INCREMENTAL_ENABLED", "true"
    ).lower() in ("1", "true", "yes")

    # R0.3 — Reaper de huérfanos + watchdog reconciliador.
    # OFF default. ON: reconcilia runs en estado running sin heartbeat reciente
    # al arrancar el backend y, si el intervalo es >0, periódicamente.
    STACKY_ORPHAN_REAPER_ENABLED: bool = os.getenv(
        "STACKY_ORPHAN_REAPER_ENABLED", "true"
    ).lower() in ("1", "true", "yes")

    # Intervalo entre barridos del reaper de huérfanos (segundos).
    # 0 = solo al arrancar (si STACKY_ORPHAN_REAPER_ENABLED=true).
    STACKY_ORPHAN_REAPER_INTERVAL_SEC: int = int(
        os.getenv("STACKY_ORPHAN_REAPER_INTERVAL_SEC", "0")
    )

    # R1.1 — Watchdog de inactividad del stream (segundos). 0 = desactivado.
    # Si el stream no emite ningún evento por N segundos → cierre limpio
    # failed(reason="stalled") con metadata["stall"]. Independiente del timeout
    # de sesión total (CLAUDE_CODE_CLI_TIMEOUT), que limita la duración total.
    STACKY_STALL_WATCHDOG_SECONDS: int = int(
        os.getenv("STACKY_STALL_WATCHDOG_SECONDS", "600")
    )

    # R1.2 — Validación estructural always-on del pending-task antes del POST.
    # OFF default. ON: gate estructural mínimo (campos requeridos, tipos,
    # coherencia ordinal vs parent ADO id) → inválido: cuarentena + telemetría.
    STACKY_PENDING_TASK_STRICT_VALIDATION_ENABLED: bool = os.getenv(
        "STACKY_PENDING_TASK_STRICT_VALIDATION_ENABLED", "true"
    ).lower() in ("1", "true", "yes")

    # R1.3 — Guardia de idempotencia ante fallo de persistencia local.
    # OFF default. ON: persiste intención de publicación (idempotency_key) antes
    # del POST a ADO. Reintento sin doble POST; si check falla → fallback actual.
    STACKY_PUBLISH_IDEMPOTENT_GUARD_ENABLED: bool = os.getenv(
        "STACKY_PUBLISH_IDEMPOTENT_GUARD_ENABLED", "true"
    ).lower() in ("1", "true", "yes")

    # R2.1/R2.2 — KPIs de fiabilidad en harness-health.
    # OFF default. ON: agrega bloque "reliability" con dead_letter/cuarentenas/
    # reaped/stalled/persist_failures y KPIs tasa_exito_creacion/duracion_saneada.
    STACKY_RELIABILITY_KPIS_ENABLED: bool = os.getenv(
        "STACKY_RELIABILITY_KPIS_ENABLED", "true"
    ).lower() in ("1", "true", "yes")

    # ── Plan 29 — Calidad del resultado a la primera ──────────────────────────

    # Q0.1 — Inyección de criterios como checklist en el briefing.
    # OFF default: enrich_blocks byte-idéntico.
    STACKY_ACCEPTANCE_CRITERIA_INJECTION_ENABLED: bool = os.getenv(
        "STACKY_ACCEPTANCE_CRITERIA_INJECTION_ENABLED", "true"
    ).lower() in ("1", "true", "yes")
    STACKY_ACCEPTANCE_CRITERIA_PROJECTS: str = os.getenv(
        "STACKY_ACCEPTANCE_CRITERIA_PROJECTS", ""
    )

    # Q0.2 — Esfuerzo adaptativo según dificultad estimada.
    # OFF default: effort fijo (byte-idéntico).
    STACKY_ADAPTIVE_EFFORT_ENABLED: bool = os.getenv(
        "STACKY_ADAPTIVE_EFFORT_ENABLED", "true"
    ).lower() in ("1", "true", "yes")
    # Piso de effort: nunca bajar por debajo de este valor.
    STACKY_EFFORT_FLOOR: str = os.getenv("STACKY_EFFORT_FLOOR", "medium").strip().lower()

    # Q1.1 — Pase correctivo único de criterios incumplidos.
    # OFF default: sin pase correctivo.
    STACKY_CRITERIA_REPAIR_ENABLED: bool = os.getenv(
        "STACKY_CRITERIA_REPAIR_ENABLED", "false"
    ).lower() in ("1", "true", "yes")
    STACKY_CRITERIA_REPAIR_MAX_RETRIES: int = int(
        os.getenv("STACKY_CRITERIA_REPAIR_MAX_RETRIES", "1")
    )

    # Q1.2 — Few-shot de outputs aprobados en runtimes CLI.
    # OFF default: CLI sin few-shot (byte-idéntico).
    STACKY_CLI_FEWSHOT_ENABLED: bool = os.getenv(
        "STACKY_CLI_FEWSHOT_ENABLED", "false"
    ).lower() in ("1", "true", "yes")
    STACKY_CLI_FEWSHOT_K: int = int(os.getenv("STACKY_CLI_FEWSHOT_K", "2"))
    STACKY_CLI_FEWSHOT_PROJECTS: str = os.getenv("STACKY_CLI_FEWSHOT_PROJECTS", "")

    # Q2.2 — KPI de "aprobado a la primera".
    # OFF default: harness_health byte-idéntico.
    STACKY_QUALITY_KPIS_ENABLED: bool = os.getenv(
        "STACKY_QUALITY_KPIS_ENABLED", "true"
    ).lower() in ("1", "true", "yes")

    # ── Plan 30 — Integridad verificada contra la realidad ────────────────────

    # G0.1 — Gate de precondiciones determinista antes de lanzar el run.
    # OFF default: run_agent byte-idéntico.
    STACKY_RUN_PREFLIGHT_GATE_ENABLED: bool = os.getenv(
        "STACKY_RUN_PREFLIGHT_GATE_ENABLED", "false"
    ).lower() in ("1", "true", "yes")

    # G1.1 — Verificación post-create de que la task existe en ADO antes de
    # marcar consumed. OFF default: output_watcher byte-idéntico.
    STACKY_VERIFY_TASK_BEFORE_CONSUMED_ENABLED: bool = os.getenv(
        "STACKY_VERIFY_TASK_BEFORE_CONSUMED_ENABLED", "false"
    ).lower() in ("1", "true", "yes")

    # G1.2 — Grounding determinista de referencias del output (rutas/IDs).
    # OFF default: finalize_run byte-idéntico.
    STACKY_OUTPUT_GROUNDING_ENABLED: bool = os.getenv(
        "STACKY_OUTPUT_GROUNDING_ENABLED", "false"
    ).lower() in ("1", "true", "yes")
    # G1.2 — Pase correctivo de grounding via Q1.1 (solo si seam disponible).
    # Exige STACKY_CRITERIA_REPAIR_ENABLED y STACKY_OUTPUT_GROUNDING_ENABLED.
    STACKY_OUTPUT_GROUNDING_REPAIR: bool = os.getenv(
        "STACKY_OUTPUT_GROUNDING_REPAIR", "false"
    ).lower() in ("1", "true", "yes")

    # G2.1 — KPIs de integridad en harness-health (read-only).
    # OFF default: harness_health byte-idéntico.
    STACKY_INTEGRITY_KPIS_ENABLED: bool = os.getenv(
        "STACKY_INTEGRITY_KPIS_ENABLED", "true"
    ).lower() in ("1", "true", "yes")

    # G2.2 — Retry transitorio (diferido: clasificación de exit-codes no es
    # confiable/barata con los runtimes actuales; ver comentario en runners).
    # Flags declarados para completitud del registro; comportamiento: OFF always.
    STACKY_TRANSIENT_RUN_RETRY_ENABLED: bool = os.getenv(
        "STACKY_TRANSIENT_RUN_RETRY_ENABLED", "false"
    ).lower() in ("1", "true", "yes")
    STACKY_TRANSIENT_RUN_RETRY_MAX: int = int(
        os.getenv("STACKY_TRANSIENT_RUN_RETRY_MAX", "1")
    )

    # ── Plan 36 — Selector de runtime sin fallback silencioso ─────────────────
    # Si true (default), /run loguea y marca cuando el runtime vino ausente en el
    # payload y tuvo que aplicarse el default github_copilot.
    # NUNCA cambia el runtime en silencio; solo registra el evento para diagnóstico.
    STACKY_RUNTIME_STRICT: bool = os.getenv(
        "STACKY_RUNTIME_STRICT", "true"
    ).lower() in ("1", "true", "yes")

    # ── Plan 38 — Versión visible, épica desde brief, trazabilidad ───────────

    # B0 — Endpoint POST /api/tickets/epics/from-brief.
    STACKY_EPIC_FROM_BRIEF_ENABLED: bool = os.getenv(
        "STACKY_EPIC_FROM_BRIEF_ENABLED", "true"
    ).lower() in ("1", "true", "yes")

    # Plan 41 — Autopublicación backend de la épica brief→épica (palanca de
    # emergencia). ON: el finalizador del runner CLI publica la épica en ADO de
    # forma autónoma e idempotente al cerrar la run, sin depender del frontend.
    STACKY_EPIC_AUTOPUBLISH_BACKEND: bool = os.getenv(
        "STACKY_EPIC_AUTOPUBLISH_BACKEND", "true"
    ).lower() in ("1", "true", "yes")

    # Plan 41 — Pre-vuelo de Intención. Default OFF → byte-idéntico al actual.
    INTENT_PREFLIGHT_ENABLED: bool = os.getenv(
        "INTENT_PREFLIGHT_ENABLED", "false"
    ).lower() in ("1", "true", "yes", "on")
    INTENT_PREFLIGHT_AUTO_APPROVE: bool = os.getenv(
        "INTENT_PREFLIGHT_AUTO_APPROVE", "false"
    ).lower() in ("1", "true", "yes", "on")
    INTENT_PREFLIGHT_AUTO_APPROVE_MIN_CONF: float = float(
        os.getenv("INTENT_PREFLIGHT_AUTO_APPROVE_MIN_CONF", "0.8")
    )

    # Plan 44 F2/F3 — Observatorio de grounding y sugeridor de diccionario. Ambos
    # son SOLO-LECTURA (no mutan estado, no llaman a ADO): default True es seguro
    # (la card aparece vacía si no hay épicas). OFF → los endpoints responden 404.
    STACKY_GROUNDING_OBSERVATORY_ENABLED: bool = os.getenv(
        "STACKY_GROUNDING_OBSERVATORY_ENABLED", "true"
    ).lower() in ("1", "true", "yes")
    STACKY_PROCESS_CATALOG_SUGGESTIONS_ENABLED: bool = os.getenv(
        "STACKY_PROCESS_CATALOG_SUGGESTIONS_ENABLED", "true"
    ).lower() in ("1", "true", "yes")

    # Plan 45 F0 — Soporte de Issues desde brief. OFF (default seguro): el flujo
    # brief→ADO solo admite Epic (byte-idéntico a hoy). ON: el operador puede
    # elegir work_item_type="Issue" en el modal; el finalizador del runner crea
    # un work item ADO tipo "Issue" y acumula el output como comentario único
    # idempotente en ese mismo WI (sin tickets hijos).
    STACKY_ISSUE_FROM_BRIEF_ENABLED: bool = os.getenv(
        "STACKY_ISSUE_FROM_BRIEF_ENABLED", "false"
    ).lower() in ("1", "true", "yes")

    # Plan 77 — Postea análisis funcional/técnico/implementación de un Issue como
    # comentarios idempotentes en el mismo WI (sin tickets hijos). Default OFF.
    STACKY_ISSUE_PHASE_COMMENTS_ENABLED: bool = os.getenv(
        "STACKY_ISSUE_PHASE_COMMENTS_ENABLED", "false"
    ).lower() in ("1", "true", "yes")

    # Fix robusto brief→épica — pase correctivo: si el BusinessAgent (one-shot)
    # devuelve narración en vez del HTML de la épica, se le pide UNA vez por stdin
    # que re-emita SOLO el HTML antes de cerrar la sesión. Reusa el presupuesto de
    # reintentos del autocorrect. OFF → solo fallo ruidoso (needs_review), sin retry.
    STACKY_EPIC_REPAIR_ENABLED: bool = os.getenv(
        "STACKY_EPIC_REPAIR_ENABLED", "true"
    ).lower() in ("1", "true", "yes")

    # C0/C1 — Trazabilidad de ejecución (agent_type, prompt_sha, produced_files).
    STACKY_EXECUTION_TRACE_ENABLED: bool = os.getenv(
        "STACKY_EXECUTION_TRACE_ENABLED", "true"
    ).lower() in ("1", "true", "yes")

    # C0/C1 — Guarda prompt_text en metadata (privacidad: default OFF).
    STACKY_TRACE_PROMPT_TEXT_ENABLED: bool = os.getenv(
        "STACKY_TRACE_PROMPT_TEXT_ENABLED", "false"
    ).lower() in ("1", "true", "yes")

    # ── Plan 53 — Selector adaptativo de modelo/effort por confidence de grounding
    # OFF por defecto → comportamiento byte-idéntico al actual.
    # ON: bajo confidence escala a Opus/max; alto confidence baja a Sonnet/low.
    # El override manual del operador (model/effort en el body del request) SIEMPRE gana.
    STACKY_ADAPTIVE_SELECTOR_ENABLED: bool = os.getenv(
        "STACKY_ADAPTIVE_SELECTOR_ENABLED", "false"
    ).lower() in ("1", "true", "yes")

    # ── Plan 54 — Memoria que empuja: rechazos como anti-patrones ────────────
    # OFF por defecto → 3 runtimes idénticos al estado previo (byte-compat).
    # ON: notas de rechazo del operador se inyectan como anti-patrones imperativos
    # en el próximo run del mismo proyecto, en los 3 runtimes (copilot/claude_cli/codex).
    STACKY_PUSH_REJECTIONS_ENABLED: bool = os.getenv(
        "STACKY_PUSH_REJECTIONS_ENABLED", "true"
    ).lower() in ("1", "true", "yes")

    # Plan 81 — Si ON, las frases borradas por el operador en ADO se derivan
    # como goldens negativos deterministas durante el sweep de edit-learning.
    # Default ON (activado 2026-07-05, decisión explícita del operador),
    # editable por UI via HarnessFlagsPanel.
    STACKY_NEGATIVE_GOLDEN_FROM_EDITS_ENABLED: bool = os.getenv(
        "STACKY_NEGATIVE_GOLDEN_FROM_EDITS_ENABLED", "true"
    ).lower() in ("1", "true", "yes")

    # ── Plan 65 — GitLab como tracker de primer nivel ─────────────────────────
    # STACKY_GITLAB_ENABLED: master switch para el adapter GitLab. OFF default.
    # Sin este flag, issue_tracker.type=gitlab rechaza en la fábrica.
    GITLAB_URL: str = os.getenv("GITLAB_URL", "")
    GITLAB_PROJECT: str = os.getenv("GITLAB_PROJECT", "")
    GITLAB_TOKEN: str = os.getenv("GITLAB_TOKEN", "")
    STACKY_GITLAB_GROUP: str = os.getenv("STACKY_GITLAB_GROUP", "")
    STACKY_GITLAB_ENABLED: bool = os.getenv(
        "STACKY_GITLAB_ENABLED", "false"
    ).lower() in ("1", "true", "yes")
    # ── Plan 70 — Desacople consumers TrackerProvider ─────────────────────────
    # ON: api/tickets.py enruta los ~18 call sites por el puerto TrackerProvider
    # (get_tracker_provider) en vez de por _ado_client_for_ticket; cae al fallback
    # ADO si el provider del proyecto no está disponible. OFF (default):
    # byte-idéntico al comportamiento pre-Plan-70 (todo por AdoClient directo).
    STACKY_TICKETS_PROVIDER_ENABLED: bool = os.getenv(
        "STACKY_TICKETS_PROVIDER_ENABLED", "false"
    ).lower() in ("1", "true", "yes")
    # Si true, usa Group Epics nativos de GitLab (requiere licencia Premium/Ultimate).
    # False (default): jerarquía vía issue-links (fallback siempre disponible).
    STACKY_GITLAB_EPICS_NATIVE: bool = os.getenv(
        "STACKY_GITLAB_EPICS_NATIVE", "false"
    ).lower() in ("1", "true", "yes")
    # ── Plan 79 — Estados de tarea deterministas y configurables ─────────────
    # ON: Stacky aplica el estado-en-progreso (al iniciar) y el estado-final
    # (al completar) desde client_profile.tracker_state_machine.<agent_type>,
    # ignorando el target_ado_state que proponga el agente. OFF (default):
    # byte-idéntico al comportamiento actual (el agente sigue proponiendo el
    # estado vía el body del run).
    STACKY_DETERMINISTIC_TASK_STATES_ENABLED: bool = os.getenv(
        "STACKY_DETERMINISTIC_TASK_STATES_ENABLED", "false"
    ).lower() in ("1", "true", "yes")
    # Si true (default), infiere pipelines CI de GitLab cuando el tracker es gitlab.
    STACKY_GITLAB_CI_INFERENCE: bool = os.getenv(
        "STACKY_GITLAB_CI_INFERENCE", "true"
    ).lower() in ("1", "true", "yes")
    # Plan 71 — Si ON, los endpoints ado-pipeline-status y ado-pipeline-batch
    # enrutan por el sub-puerto CIProvider (AdoCIProvider / GitLabCIProvider)
    # en vez de llamar directamente a infer_pipeline. OFF (default): comportamiento
    # pre-Plan-71 byte-idéntico.
    STACKY_PIPELINE_PROVIDER_ENABLED: bool = os.getenv(
        "STACKY_PIPELINE_PROVIDER_ENABLED", "false"
    ).lower() in ("1", "true", "yes")
    # Plan 72 — Trigger y monitoreo de pipelines CI (HITL). Default ON
    # (activado 2026-07-05, decisión explícita del operador).
    # Editable por UI (HarnessFlagsPanel, categoría "Pipelines / CI").
    STACKY_PIPELINE_TRIGGER_ENABLED: bool = os.getenv(
        "STACKY_PIPELINE_TRIGGER_ENABLED", "true"
    ).lower() in ("1", "true", "yes")

    # Plan 73 — Generador declarativo de pipelines ADO/GitLab (PipelineSpec). Default ON
    # (activado 2026-07-05, decisión explícita del operador).
    # Editable por UI (HarnessFlagsPanel, categoría "Pipelines / CI").
    STACKY_PIPELINE_GENERATOR_ENABLED: bool = os.getenv(
        "STACKY_PIPELINE_GENERATOR_ENABLED", "true"
    ).lower() in ("1", "true", "yes")

    # Plan 87 — Panel DevOps (creador gráfico de pipelines). Default ON
    # (activado 2026-07-05, decisión explícita del operador).
    # Editable por UI (HarnessFlagsPanel, categoría "DevOps").
    STACKY_DEVOPS_PANEL_ENABLED: bool = os.getenv(
        "STACKY_DEVOPS_PANEL_ENABLED", "true"
    ).lower() in ("1", "true", "yes")

    # Plan 88 — Publicaciones parametrizables de procesos (seccion del panel
    # DevOps). Default ON (activado 2026-07-05, decisión explícita del operador).
    # Editable por UI (HarnessFlagsPanel, categoría "DevOps").
    STACKY_DEVOPS_PUBLICATIONS_ENABLED: bool = os.getenv(
        "STACKY_DEVOPS_PUBLICATIONS_ENABLED", "true"
    ).strip().lower() == "true"

    # Plan 89 — Inicialización de ambientes (seccion del panel DevOps). Default
    # ON (activado 2026-07-05, decisión explícita del operador).
    # Editable por UI (HarnessFlagsPanel, categoría "DevOps").
    STACKY_DEVOPS_ENVIRONMENTS_ENABLED: bool = os.getenv(
        "STACKY_DEVOPS_ENVIRONMENTS_ENABLED", "true"
    ).strip().lower() == "true"

    # Plan 107 — Preview de árbol de directorios y raíz sandbox de pruebas
    # (extiende la sección Ambientes del Plan 89). Default OFF: son mejoras
    # opt-in del operador, a diferencia de Environments que está en "true".
    # Editable por UI (HarnessFlagsPanel, categoría "DevOps").
    STACKY_DEVOPS_ENV_TREE_PREVIEW_ENABLED: bool = os.getenv(
        "STACKY_DEVOPS_ENV_TREE_PREVIEW_ENABLED", "false"
    ).strip().lower() == "true"
    STACKY_DEVOPS_ENV_SANDBOX_ENABLED: bool = os.getenv(
        "STACKY_DEVOPS_ENV_SANDBOX_ENABLED", "false"
    ).strip().lower() == "true"

    # Plan 90 — Agente DevOps interactivo multi-turno (seccion del panel DevOps).
    # Default ON (activado 2026-07-05, decisión explícita del operador, con
    # conocimiento de que cada turno consume una llamada LLM completa).
    # Editable por UI (HarnessFlagsPanel, categoría "DevOps").
    STACKY_DEVOPS_AGENT_ENABLED: bool = os.getenv(
        "STACKY_DEVOPS_AGENT_ENABLED", "true"
    ).strip().lower() == "true"

    # Plan 91 — Registro de servidores DevOps (conexiones con alias). Default ON
    # (activado 2026-07-05, decisión explícita del operador, con conocimiento
    # de que maneja credenciales y conexiones RDP).
    # Editable por UI (HarnessFlagsPanel, categoría "DevOps").
    STACKY_DEVOPS_SERVERS_ENABLED: bool = os.getenv(
        "STACKY_DEVOPS_SERVERS_ENABLED", "true"
    ).lower() in ("1", "true", "yes")

    # Plan 93 — Preflight de pipelines DevOps. Default OFF. Editable por UI.
    STACKY_DEVOPS_PREFLIGHT_ENABLED: bool = os.getenv(
        "STACKY_DEVOPS_PREFLIGHT_ENABLED", "false"
    ).lower() in ("1", "true", "yes")

    # Plan 95 — Llevar a producción (Merge Request / Pull Request + merge HITL).
    # Default OFF. Editable por UI (HarnessFlagsPanel, categoría "DevOps").
    STACKY_DEVOPS_PRODUCTION_ENABLED: bool = os.getenv(
        "STACKY_DEVOPS_PRODUCTION_ENABLED", "false"
    ).lower() in ("1", "true", "yes")

    # Plan 96 — Doctor de pipelines: diagnóstico en llano del fallo (ADO + GitLab).
    # Default OFF. Editable por UI (HarnessFlagsPanel, categoría "DevOps").
    STACKY_DEVOPS_DOCTOR_ENABLED: bool = os.getenv(
        "STACKY_DEVOPS_DOCTOR_ENABLED", "false"
    ).lower() in ("1", "true", "yes")

    # Plan 94 — Caja fuerte de variables: secretos del pipeline fuera del YAML
    # (ADO + GitLab). Default OFF. Editable por UI (HarnessFlagsPanel, categoría "DevOps").
    STACKY_DEVOPS_VARIABLES_ENABLED: bool = os.getenv(
        "STACKY_DEVOPS_VARIABLES_ENABLED", "false"
    ).lower() in ("1", "true", "yes")

    # Plan 97 — Deteccion opt-in de stack tecnico para presets de pipeline. Default OFF.
    STACKY_DEVOPS_STACK_DETECT_ENABLED: bool = os.getenv(
        "STACKY_DEVOPS_STACK_DETECT_ENABLED", "false"
    ).lower() in ("1", "true", "yes")

    # Plan 98 — Bootstrap unico del panel DevOps + PATCH por clave del client-profile.
    # Default OFF.
    STACKY_DEVOPS_BOOTSTRAP_ENABLED: bool = os.getenv(
        "STACKY_DEVOPS_BOOTSTRAP_ENABLED", "false"
    ).lower() in ("1", "true", "yes")

    # Plan 104 — Doctores IA por seccion del panel DevOps. Default OFF (opt-in).
    STACKY_DEVOPS_SECTION_DOCTOR_ENABLED: bool = os.getenv(
        "STACKY_DEVOPS_SECTION_DOCTOR_ENABLED", "false"
    ).lower() in ("1", "true", "yes")

    # Plan 105 — Consola remota de prompts por servidor (default OFF).
    STACKY_DEVOPS_REMOTE_CONSOLE_ENABLED: bool = os.getenv(
        "STACKY_DEVOPS_REMOTE_CONSOLE_ENABLED", "false"
    ).lower() in ("true", "1", "yes")
    # Plan 74 — Migrador ADO→GitLab seguro e idempotente. Default OFF.
    # Editable por UI (HarnessFlagsPanel, categoría "Migrador ADO → GitLab").
    STACKY_MIGRATOR_ADO_TO_GITLAB_ENABLED: bool = os.getenv(
        "STACKY_MIGRATOR_ADO_TO_GITLAB_ENABLED", "false"
    ).lower() in ("1", "true", "yes")

    # Plan 74 — Política de épicas en la migración ADO→GitLab.
    # Valores: auto | premium_native | free_degrade. Default: auto.
    # Editable por UI (HarnessFlagsPanel, categoría "Migrador ADO → GitLab").
    STACKY_MIGRATOR_EPIC_POLICY: str = os.getenv(
        "STACKY_MIGRATOR_EPIC_POLICY", "auto"
    )

    # Plan 75 — Deep links bidireccionales GitLab. Default OFF.
    # Kill-switch que gatea la composición de URLs GitLab en el provider.
    # Editable por UI (HarnessFlagsPanel, categoría "GitLab / Deep Links").
    # Con flag OFF, item_url/mr_url/commit_url/epic_url devuelven None (frontend cae a <span>).
    STACKY_GITLAB_DEEP_LINKS_ENABLED: bool = os.getenv(
        "STACKY_GITLAB_DEEP_LINKS_ENABLED", "false"
    ).lower() in ("1", "true", "yes")

    # Plan 76 — Integración opcional con codebase-memory-mcp (externo). Default OFF.
    # Editable por UI (HarnessFlagsPanel, categoría "Avanzado / experimental").
    # Con flag OFF, Stacky es byte-idéntico a hoy (sin endpoints activos ni config MCP inyectada).
    STACKY_CODEBASE_MEMORY_MCP_ENABLED: bool = os.getenv(
        "STACKY_CODEBASE_MEMORY_MCP_ENABLED", "false"
    ).lower() in ("1", "true", "yes")

    # Plan 80 — Allowlist por proyecto para el MCP externo codebase-memory-mcp.
    # Master = STACKY_CODEBASE_MEMORY_MCP_ENABLED (Plan 76, ya existe). Vacío = todos los proyectos.
    STACKY_CODEBASE_MEMORY_MCP_PROJECTS: str = os.getenv(
        "STACKY_CODEBASE_MEMORY_MCP_PROJECTS", ""
    )
    # Plan 80 — Ruta absoluta del binario codebase-memory-mcp en la máquina del operador.
    # Vacío (default) => NO se inyecta el 2º server aunque el master esté ON (degradación segura).
    STACKY_CODEBASE_MEMORY_MCP_BINARY_PATH: str = os.getenv(
        "STACKY_CODEBASE_MEMORY_MCP_BINARY_PATH", ""
    )


config = Config()
