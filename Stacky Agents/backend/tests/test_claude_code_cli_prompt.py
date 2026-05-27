"""Tests del armado de prompt de claude_code_cli_runner.

Verifica que `_build_claude_code_prompt` renderice el `ticket_message` (ya
enriquecido con descripción + épica + blocks) dentro de la sección
"## Ticket y contexto", y no solo el título — el bug B del plan.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class _FakeAgent:
    def __init__(self, name, filename, description, system_prompt):
        self.name = name
        self.filename = filename
        self.description = description
        self.system_prompt = system_prompt


def _selected():
    return _FakeAgent(
        name="Funcional Pacifico",
        filename="FuncionalPacifico.agent.md",
        description="Analista funcional",
        system_prompt="Sos el analista funcional. Generá criterios de aceptación.",
    )


def test_prompt_includes_rich_ticket_context():
    from services import claude_code_cli_runner, context_enrichment

    ticket_message = context_enrichment.build_ticket_context_text(
        ado_id=206,
        title="Marca oficial en el mantenedor de direcciones",
        description="Como operador quiero registrar la marca oficial.",
        work_item_type="Epic",
        blocks=[
            {"id": "ado-epic-structured", "title": "Epic ADO-206", "content": "epic_id: 206\nepic_title: Marca oficial"},
            {"id": "ado-comments", "title": "Comentarios ADO", "content": "QA: revisar validación"},
            {"id": "modal_user_input", "title": "Mensaje adicional", "content": "priorizá el alta"},
        ],
    )

    prompt = claude_code_cli_runner._build_claude_code_prompt(
        selected_agent=_selected(),
        all_agents=[_selected()],
        ticket_message=ticket_message,
    )

    # Persona del agente embebida (Fase C la moverá a system prompt; acá solo
    # comprobamos que el contexto del ticket llega completo).
    assert "## Ticket y contexto" in prompt
    # Encabezado del ticket
    assert "ADO-206" in prompt
    assert "Marca oficial en el mantenedor de direcciones" in prompt
    # Descripción (antes se perdía: solo iba el título)
    assert "Como operador quiero registrar la marca oficial." in prompt
    # Bloque de épica estructurada
    assert "epic_id: 206" in prompt
    # Comentarios ADO
    assert "QA: revisar validación" in prompt
    # Mensaje adicional del modal
    assert "priorizá el alta" in prompt


def test_prompt_includes_agent_inventory_and_system_prompt():
    from services import claude_code_cli_runner

    prompt = claude_code_cli_runner._build_claude_code_prompt(
        selected_agent=_selected(),
        all_agents=[_selected()],
        ticket_message="ADO-1\nTítulo: x",
    )
    assert "Funcional Pacifico" in prompt
    assert "FuncionalPacifico.agent.md" in prompt
    assert "Generá criterios de aceptación." in prompt


# ---------------------------------------------------------------------------
# Fase C — persona vía system prompt (separación system vs user)
# ---------------------------------------------------------------------------

def test_system_prompt_carries_persona_and_stacky_rules():
    from services import claude_code_cli_runner

    sp = claude_code_cli_runner._build_system_prompt(_selected())
    # Persona del .agent.md
    assert "Sos el analista funcional. Generá criterios de aceptación." in sp
    assert "Funcional Pacifico" in sp
    # Reglas duras de Stacky (definen el cómo)
    assert "no toques Azure DevOps" in sp
    assert "comment.html" in sp


def test_user_message_has_context_but_not_persona():
    from services import claude_code_cli_runner

    um = claude_code_cli_runner._build_user_message(
        all_agents=[_selected()],
        ticket_message="ADO-206\nTítulo: Marca oficial",
    )
    # El ticket/contexto SÍ
    assert "ADO-206" in um
    assert "Marca oficial" in um
    # La persona NO debe estar embebida en el mensaje de usuario (canal equivocado)
    assert "Sos el analista funcional. Generá criterios de aceptación." not in um


def test_build_command_appends_system_prompt_file_when_provided(tmp_path):
    from services import claude_code_cli_runner

    spf = tmp_path / "system_prompt.md"
    spf.write_text("persona", encoding="utf-8")
    cmd = claude_code_cli_runner._build_command(model_override=None, system_prompt_file=spf)
    assert "--append-system-prompt-file" in cmd
    assert str(spf) in cmd
    # contrato base intacto
    assert "--input-format" in cmd and "stream-json" in cmd


def test_build_command_omits_system_prompt_file_when_none():
    from services import claude_code_cli_runner

    cmd = claude_code_cli_runner._build_command(model_override=None, system_prompt_file=None)
    assert "--append-system-prompt-file" not in cmd
