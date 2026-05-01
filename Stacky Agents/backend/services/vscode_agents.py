"""
Lee los archivos .agent.md del directorio de prompts de VS Code (GitHub Copilot
custom agents) y los expone como agentes seleccionables en el workbench.

Formato esperado (frontmatter YAML opcional):

    ---
    description: "..."
    tools: [...]
    version: "1.0.0"
    ---
    # Nombre del agente
    contenido del system prompt...

Si el archivo no tiene frontmatter, todo el contenido se trata como system prompt
y la descripción se deriva de la primera línea o queda vacía.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


@dataclass
class VsCodeAgent:
    name: str
    filename: str
    description: str
    system_prompt: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Devuelve (frontmatter_dict, body). Si no hay frontmatter válido, dict vacío."""
    # Tolerar BOM al inicio.
    if text.startswith("﻿"):
        text = text.lstrip("﻿")
    if not text.startswith("---"):
        return {}, text
    rest = text[3:]
    # Permitir un newline opcional después del primer `---`.
    if rest.startswith("\r\n"):
        rest = rest[2:]
    elif rest.startswith("\n"):
        rest = rest[1:]
    end = rest.find("\n---")
    if end < 0:
        return {}, text
    raw_fm = rest[:end]
    body_start = end + len("\n---")
    body = rest[body_start:]
    if body.startswith("\r\n"):
        body = body[2:]
    elif body.startswith("\n"):
        body = body[1:]
    try:
        data = yaml.safe_load(raw_fm) or {}
        if not isinstance(data, dict):
            data = {}
    except yaml.YAMLError as exc:
        logger.warning("frontmatter YAML inválido: %s", exc)
        data = {}
    return data, body


def _load_agent_file(path: Path) -> VsCodeAgent | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("no se pudo leer %s: %s", path, exc)
        return None

    fm, body = _parse_frontmatter(text)

    name = path.name
    if name.endswith(".agent.md"):
        name = name[: -len(".agent.md")]
    elif name.endswith(".prompt.md"):
        name = name[: -len(".prompt.md")]
    elif name.endswith(".md"):
        name = name[: -len(".md")]

    description = ""
    if isinstance(fm.get("description"), str):
        description = fm["description"].strip()
    if not description:
        # Fallback: primer párrafo no vacío del body.
        for line in body.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                description = stripped[:240]
                break

    system_prompt = body.strip() or text.strip()

    return VsCodeAgent(
        name=name,
        filename=path.name,
        description=description,
        system_prompt=system_prompt,
    )


def list_agents(prompts_dir: str | Path) -> list[VsCodeAgent]:
    """Devuelve los .agent.md presentes en `prompts_dir`. Lista vacía si el dir
    no existe."""
    base = Path(prompts_dir)
    if not base.is_dir():
        logger.info("VSCODE_PROMPTS_DIR no existe: %s", base)
        return []

    agents: list[VsCodeAgent] = []
    for path in sorted(base.glob("*.agent.md")):
        if not path.is_file():
            continue
        agent = _load_agent_file(path)
        if agent is not None:
            agents.append(agent)
    return agents


def get_agent_by_filename(prompts_dir: str | Path, filename: str) -> VsCodeAgent | None:
    safe = Path(filename).name  # evita path traversal
    if not safe.endswith(".agent.md"):
        return None
    path = Path(prompts_dir) / safe
    if not path.is_file():
        return None
    return _load_agent_file(path)
