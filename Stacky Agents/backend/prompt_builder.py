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


def with_project_header(prompt: str, agent_type: str) -> str:
    return (
        f"# Stacky Agents — agente: {agent_type}\n"
        f"# Proyecto: RSPacifico\n\n"
        f"{prompt}"
    )


def estimate_tokens(text: str) -> int:
    """Estimación grosera: 1 token ≈ 4 caracteres."""
    return max(1, len(text) // 4)
