"""B1 — Tests para BusinessAgent.agent.md bundled."""
from __future__ import annotations

import re
from pathlib import Path

import pytest


AGENT_MD_PATH = (
    Path(__file__).resolve().parent.parent
    / "Stacky" / "agents" / "BusinessAgent.agent.md"
)


def _parse_frontmatter(text: str) -> dict:
    """Extrae el primer bloque YAML frontmatter (entre ---) como dict simple k:v."""
    m = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return {}
    result: dict = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            result[k.strip()] = v.strip().strip('"').strip("'")
    return result


def test_agent_md_file_exists():
    """El archivo BusinessAgent.agent.md debe existir en Stacky/agents/."""
    assert AGENT_MD_PATH.exists(), f"No existe: {AGENT_MD_PATH}"


def test_business_agent_appears_in_list_agents():
    """agents.list_agents() debe incluir un agente de tipo 'business'."""
    import agents
    types = [a.get("type") for a in agents.list_agents()]
    assert "business" in types, f"'business' no está en {types}"


def test_frontmatter_has_valid_stacky_agent_type():
    """El frontmatter del .agent.md debe tener stacky_agent_type: business."""
    text = AGENT_MD_PATH.read_text(encoding="utf-8")
    fm = _parse_frontmatter(text)
    assert fm, "No se encontró frontmatter en BusinessAgent.agent.md"
    assert fm.get("stacky_agent_type") == "business", (
        f"stacky_agent_type esperado 'business', obtenido '{fm.get('stacky_agent_type')}'"
    )
