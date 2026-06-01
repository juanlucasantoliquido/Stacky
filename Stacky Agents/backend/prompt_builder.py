"""
Prompt builder modular: cada agente arma el prompt user via su `build_prompt`,
pero los bloques de contexto se serializan acá de manera consistente.
"""
from __future__ import annotations

from typing import Any


def render_blocks(blocks: list[dict]) -> str:
    """Convierte una lista de ContextBlock (JSON) en markdown para el prompt user."""
    out: list[str] = []
    for block in blocks:
        kind = block.get("kind", "auto")
        title = block.get("title") or ""
        if title:
            out.append(f"## {title}\n")
        if kind == "choice":
            for item in block.get("items", []):
                if item.get("selected"):
                    out.append(f"- {item.get('label', '')}\n")
        else:
            content = block.get("content")
            if content:
                out.append(f"{content}\n")
        out.append("")
    return "\n".join(out).strip()


def _resolve_active_display_name() -> str:
    """Lee `display_name` del proyecto activo. Best-effort: si Stacky aún no
    tiene proyecto activo, devuelve un placeholder genérico en vez de hardcoded
    'RSPacifico'."""
    try:
        from project_manager import get_active_project, get_project_config

        name = get_active_project()
        if not name:
            return "(sin proyecto activo)"
        cfg = get_project_config(name) or {}
        display = (cfg.get("display_name") or name or "").strip()
        return display or name or "(sin proyecto activo)"
    except Exception:
        return "(sin proyecto activo)"


def with_project_header(prompt: str, agent_type: str, project_display_name: str | None = None) -> str:
    """Antepone un header identificando agente + proyecto activo.

    `project_display_name` permite que el caller pase un nombre explícito
    (útil cuando el caller ya conoce el proyecto del ticket). Si se omite,
    se resuelve via `project_manager.get_active_project()`.
    """
    display = (project_display_name or "").strip() or _resolve_active_display_name()
    return (
        f"# Stacky Agents — agente: {agent_type}\n"
        f"# Proyecto: {display}\n\n"
        f"{prompt}"
    )


def estimate_tokens(text: str) -> int:
    """Estimación grosera: 1 token ≈ 4 caracteres."""
    return max(1, len(text) // 4)
