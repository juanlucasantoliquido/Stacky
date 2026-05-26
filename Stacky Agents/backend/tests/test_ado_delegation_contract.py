import os
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")


def test_functional_and_technical_prompts_delegate_ado_to_stacky():
    from agents.functional import FunctionalAgent
    from agents.technical import TechnicalAgent

    functional = FunctionalAgent().system_prompt()
    technical = TechnicalAgent().system_prompt()

    for prompt in (functional, technical):
        assert "NO toques Azure DevOps" in prompt
        assert "Stacky Agents es el único autorizado a escribir en ADO" in prompt

    assert "pending-task.json" in functional
    assert "Agentes/outputs/epic-<ADO_ID>/<RF_SLUG>/pending-task.json" in functional
    assert "Agentes/outputs/<ADO_ID>/comment.html" in technical


def test_cli_runtime_prompts_remove_ado_escape_hatch():
    from services.codex_cli_runner import _build_codex_prompt
    from services.claude_code_cli_runner import _build_claude_code_prompt

    selected = SimpleNamespace(
        name="AnalistaFuncionalPacifico",
        filename="AnalistaFuncionalPacifico.agent.md",
        description="Analista funcional",
        system_prompt="System prompt del agente",
    )
    all_agents = [selected]
    ticket_message = "# ADO-123\nContexto del ticket"

    codex_prompt = _build_codex_prompt(
        selected_agent=selected,
        all_agents=all_agents,
        ticket_message=ticket_message,
        agent_bundle_dir=Path("C:/tmp/agents"),
        agent_manifest_file=Path("C:/tmp/agents/manifest.json"),
    )
    claude_prompt = _build_claude_code_prompt(
        selected_agent=selected,
        all_agents=all_agents,
        ticket_message=ticket_message,
    )

    for prompt in (codex_prompt, claude_prompt):
        assert "Regla absoluta: no toques Azure DevOps" in prompt
        assert "Stacky Agents es el unico autorizado a" in prompt
        assert "Agentes/outputs/<ADO_ID>/comment.html" in prompt
        assert "pending-task.json" in prompt
        assert "salvo que las instrucciones del agente seleccionado" not in prompt
