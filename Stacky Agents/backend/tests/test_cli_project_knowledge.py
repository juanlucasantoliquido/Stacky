"""Tests de F2.2 — conocimiento del proyecto en el system prompt del CLI."""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_system_prompt_includes_knowledge_when_provided():
    from services import claude_code_cli_runner as r

    class _Agent:
        name = "Funcional"
        filename = "Funcional.agent.md"

    sp = r._build_system_prompt(
        _Agent(),
        invocation_block="",
        project_knowledge="## Anti-patrones a evitar\n1. **Evitá**: X",
    )
    assert "Anti-patrones a evitar" in sp
    # Reglas de Stacky siguen presentes.
    assert "Reglas de ejecución (Stacky Agents)" in sp


def test_system_prompt_omits_knowledge_when_empty():
    from services import claude_code_cli_runner as r

    class _Agent:
        name = "Funcional"
        filename = "Funcional.agent.md"

    sp = r._build_system_prompt(_Agent(), project_knowledge="")
    assert "Anti-patrones" not in sp


def test_build_project_knowledge_off_by_default():
    from services import claude_code_cli_runner as r

    # Flag OFF (default) → sin conocimiento aunque haya proyecto.
    section, meta = r._build_project_knowledge(
        agent_type="functional",
        project_name="Pacifico",
        context_text="alta de marca en el mantenedor",
        log=lambda *a, **k: None,
    )
    assert section == ""
    assert meta == {}


def test_compose_section_dedups_owner(monkeypatch):
    """El composer F2.2 NO inyecta client-profile ni memoria (B6: un dueño)."""
    from services import cli_project_knowledge as k

    section, meta = k.build_project_knowledge_section(
        agent_type="functional",
        project=None,
        context_text="",
        log=lambda *a, **k: None,
    )
    # Sin datos en DB → vacío, pero nunca menciona client-profile/memoria.
    assert "client-profile" not in section.lower()
    assert "stacky-memory" not in section.lower()
