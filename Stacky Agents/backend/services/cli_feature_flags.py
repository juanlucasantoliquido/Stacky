"""cli_feature_flags.py — Resolución de flags por proyecto para Fase 2 (CLI).

Regla del plan (§4.1): cero fricción nueva al operador. Cada feature de Fase 2
es OFF por default y se enciende por proyecto, no global. El patrón es:

    master flag (*_ENABLED)  AND  proyecto en la allowlist (*_PROJECTS, CSV)

Semántica de la allowlist:
  - vacía  → si el master está ON, aplica a TODOS los proyectos (escape hatch de
             staging; explícito en el plan F2.4 "presupuesto global").
  - con N nombres → solo esos proyectos (match case-insensitive, trim).

Este módulo es la fuente ÚNICA de esa decisión: ningún runner debe re-parsear
los CSV a mano. Pura lectura de config; no toca DB ni disco.
"""
from __future__ import annotations


def _csv_set(raw: str | None) -> set[str]:
    if not raw:
        return set()
    return {p.strip().lower() for p in raw.split(",") if p.strip()}


def project_enabled(
    *, enabled: bool, projects_csv: str | None, project_name: str | None
) -> bool:
    """Decide si una feature está activa para `project_name`.

    - `enabled` False → siempre False.
    - allowlist vacía → True (master ON aplica a todos).
    - allowlist con nombres → True solo si el proyecto matchea.
    """
    if not enabled:
        return False
    allow = _csv_set(projects_csv)
    if not allow:
        return True
    if not project_name:
        return False
    return project_name.strip().lower() in allow


# ── Wrappers tipados por feature (un solo lugar que lee cada par de flags) ──────


def project_knowledge_enabled(project_name: str | None) -> bool:
    """F2.2 — conocimiento del proyecto en el system prompt del CLI."""
    from config import config

    return project_enabled(
        enabled=config.CLAUDE_CODE_CLI_PROJECT_KNOWLEDGE_ENABLED,
        projects_csv=config.CLAUDE_CODE_CLI_PROJECT_KNOWLEDGE_PROJECTS,
        project_name=project_name,
    )


def resume_enabled(project_name: str | None) -> bool:
    """F2.3 — re-runs con --resume + delta prompt."""
    from config import config

    return project_enabled(
        enabled=config.CLAUDE_CODE_CLI_RESUME_ENABLED,
        projects_csv=config.CLAUDE_CODE_CLI_RESUME_PROJECTS,
        project_name=project_name,
    )


def context_budget_enabled(project_name: str | None) -> bool:
    """F2.4 — presupuesto de contexto con ranking."""
    from config import config

    return project_enabled(
        enabled=config.STACKY_CONTEXT_BUDGET_ENABLED,
        projects_csv=config.STACKY_CONTEXT_BUDGET_PROJECTS,
        project_name=project_name,
    )


def memory_injection_enabled(project_name: str | None) -> bool:
    """F2.5 — memoria colaborativa en el CLI, por proyecto.

    Master = STACKY_MEMORY_INJECTION_ENABLED (env, leído en context_enrichment).
    """
    import os

    master = os.getenv("STACKY_MEMORY_INJECTION_ENABLED", "true").lower() in {
        "1",
        "true",
        "on",
        "yes",
    }
    from config import config

    return project_enabled(
        enabled=master,
        projects_csv=config.STACKY_MEMORY_INJECTION_PROJECTS,
        project_name=project_name,
    )


def memory_inject_scopes() -> tuple[str, ...]:
    """M3.1 — Scopes inyectables configurables (STACKY_MEMORY_INJECT_SCOPES).

    Default "project,team,global" = byte-idéntico al histórico INJECT_SCOPES.
    Permite, p. ej., incluir 'personal' para el caso mono-operador.
    """
    import os

    raw = os.getenv("STACKY_MEMORY_INJECT_SCOPES", "") or ""
    parts = tuple(p.strip().lower() for p in raw.split(",") if p.strip())
    if not parts:
        from services.memory_store import INJECT_SCOPES

        return tuple(INJECT_SCOPES)
    return parts


def mcp_enabled(project_name: str | None) -> bool:
    """F2.1 — Stacky MCP server inyectado vía --mcp-config."""
    from config import config

    return project_enabled(
        enabled=config.CLAUDE_CODE_CLI_MCP_ENABLED,
        projects_csv=config.CLAUDE_CODE_CLI_MCP_PROJECTS,
        project_name=project_name,
    )


def codex_resume_enabled(project_name: str | None) -> bool:
    """H7.1 — Re-runs con codex exec resume + delta prompt (paridad con claude F2.3)."""
    from config import config

    return project_enabled(
        enabled=config.CODEX_CLI_RESUME_ENABLED,
        projects_csv=config.CODEX_CLI_RESUME_PROJECTS,
        project_name=project_name,
    )


def skills_enabled(project_name: str | None) -> bool:
    """H4.3 — Stacky Skills en el system prompt de todos los runtimes CLI."""
    from config import config

    return project_enabled(
        enabled=config.STACKY_SKILLS_ENABLED,
        projects_csv=config.STACKY_SKILLS_PROJECTS,
        project_name=project_name,
    )


def codebase_memory_mcp_enabled(project_name: str | None) -> bool:
    """Plan 80 — server MCP externo codebase-memory-mcp, por proyecto."""
    from config import config

    return project_enabled(
        enabled=config.STACKY_CODEBASE_MEMORY_MCP_ENABLED,
        projects_csv=config.STACKY_CODEBASE_MEMORY_MCP_PROJECTS,
        project_name=project_name,
    )
