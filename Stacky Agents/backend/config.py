import logging
import os
from pathlib import Path
from dotenv import load_dotenv

from runtime_paths import (
    app_root,
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


def _default_vscode_prompts_dir() -> str:
    """Resolución por defecto del directorio de `.agent.md`.

    Tras el plan ``plan-agentes-bundled-en-stacky-2026-05-29.md`` la fuente
    canónica es ``<STACKY_HOME>/agents``. Mantenemos las fuentes legacy como
    fallback temporal — sólo si el canonical no existe o está vacío.
    """
    canonical = stacky_agents_dir()
    if canonical.is_dir() and any(canonical.glob("*.agent.md")):
        return str(canonical)

    # Compatibilidad: bundle directo del deploy (todavía soportado).
    bundled_agents_dir = app_root() / "github_copilot_agents"
    if bundled_agents_dir.is_dir():
        return str(bundled_agents_dir)

    # Dev / source checkout: fuente in-repo
    in_repo_dir = backend_root().parent / "DeployStackyAgents" / "github_copilot_agents"
    if in_repo_dir.is_dir():
        return str(in_repo_dir)

    # Último recurso: el prompts dir de VS Code del usuario.
    legacy = Path.home() / "AppData" / "Roaming" / "Code" / "User" / "prompts"
    if legacy.is_dir():
        _config_logger.warning(
            "VSCODE_PROMPTS_DIR cayó al directorio legacy de VS Code (%s). "
            "Importá estos agentes a Stacky/agents antes de producción.",
            legacy,
        )
        return str(legacy)

    # Fallback final: devolver el canonical aunque esté vacío, así
    # `materialize_agents()` puede poblarlo en el primer arranque.
    return str(canonical)


def _canonical_agents_dir_if_ready() -> Path | None:
    canonical = stacky_agents_dir()
    if canonical.is_dir() and any(canonical.glob("*.agent.md")):
        return canonical
    return None


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

    # VSCODE_PROMPTS_DIR es property para que el lookup se re-evalúe cada vez.
    # Si fuese atributo de clase quedaría congelado al primer import de
    # `config.py`, que sucede ANTES del bootstrap de Stacky/agents. En ese
    # momento el canonical está vacío y el fallback lo manda al bundle legacy;
    # como el atributo es estático no se actualiza cuando el bootstrap pobla
    # el canonical, y la UI sigue listando los .agent.md viejos.
    # Plan: plan-agentes-bundled-en-stacky-2026-05-29.md §2.2.
    @property
    def VSCODE_PROMPTS_DIR(self) -> str:
        project_agents_dir = _project_agents_dir_if_configured()
        if project_agents_dir is not None:
            return str(project_agents_dir)

        canonical = _canonical_agents_dir_if_ready()
        if canonical is not None and not _legacy_prompts_override_enabled():
            env_val = os.getenv("VSCODE_PROMPTS_DIR")
            if env_val and Path(env_val).expanduser().resolve() != canonical.resolve():
                _config_logger.warning(
                    "VSCODE_PROMPTS_DIR=%s ignorado: Stacky/agents es la fuente "
                    "canónica (%s). Para forzar legacy, seteá "
                    "STACKY_ALLOW_VSCODE_PROMPTS_OVERRIDE=true.",
                    env_val,
                    canonical,
                )
            return str(canonical)

        env_val = os.getenv("VSCODE_PROMPTS_DIR")
        if env_val:
            return env_val
        return _default_vscode_prompts_dir()

    # Codex CLI runtime
    CODEX_CLI_BIN = os.getenv("CODEX_CLI_BIN", "codex")
    CODEX_CLI_MODEL = os.getenv("CODEX_CLI_MODEL", "")
    CODEX_CLI_SANDBOX = os.getenv("CODEX_CLI_SANDBOX", "danger-full-access")
    CODEX_CLI_APPROVAL = os.getenv("CODEX_CLI_APPROVAL", "never")

    # Claude Code CLI runtime
    CLAUDE_CODE_CLI_BIN = os.getenv("CLAUDE_CODE_CLI_BIN", "claude")
    CLAUDE_CODE_CLI_MODEL = os.getenv("CLAUDE_CODE_CLI_MODEL", "")
    # Cap de sesión en segundos para una ejecución interactiva de Claude Code CLI.
    # 0 = ilimitado: la sesión vive hasta que el operador la cierra/cancela desde
    # la consola, o Claude termina por su cuenta. >0 = mata la sesión tras N seg.
    CLAUDE_CODE_CLI_TIMEOUT = int(os.getenv("CLAUDE_CODE_CLI_TIMEOUT", "0"))
    # Modo de permisos para tool calls en modo non-interactive (-p).
    # Choices del CLI: acceptEdits | auto | bypassPermissions | default | dontAsk | plan.
    # "acceptEdits" auto-acepta ediciones de archivos sin prompts (el equivalente
    # razonable para un agente autónomo; en -p no hay forma de aprobar interactivo).
    CLAUDE_CODE_CLI_PERMISSION_MODE = os.getenv("CLAUDE_CODE_CLI_PERMISSION_MODE", "acceptEdits")
    # Si true, pasa --dangerously-skip-permissions (bypass total, equivalente a
    # danger-full-access de Codex). Tiene prioridad sobre el permission mode.
    CLAUDE_CODE_CLI_SKIP_PERMISSIONS = os.getenv(
        "CLAUDE_CODE_CLI_SKIP_PERMISSIONS", "false"
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


config = Config()
