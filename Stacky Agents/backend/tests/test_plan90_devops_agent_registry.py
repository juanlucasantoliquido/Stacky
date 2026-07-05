"""Plan 90 F1 — DevOpsAgent en el registry + .agent.md con guardrails (tests primero)."""
from pathlib import Path

import agents


def test_f1_agent_registered():
    a = agents.get("devops")
    assert a is not None
    assert a.type == "devops"
    assert a.name == "DevOps"
    assert "CONFIRMO" in a.system_prompt()


def test_f1_agent_in_list_agents():
    entries = agents.list_agents()
    assert any(e.get("type") == "devops" for e in entries)


def test_f1_agent_never_business():
    # Proxy binario: el autopublish de épicas exige agent_type == "business"
    # (claude_code_cli_runner.py:1302); este agente jamás lo dispara.
    assert agents.get("devops").type != "business"


def test_f1_agent_md_exists_with_guardrails():
    # Resolver ruta relativa al repo (backend/Stacky/agents/DevOpsAgent.agent.md).
    backend_root = Path(__file__).parent.parent
    md_path = backend_root / "Stacky" / "agents" / "DevOpsAgent.agent.md"
    assert md_path.exists(), f"no encontrado: {md_path}"
    content = md_path.read_text(encoding="utf-8")
    assert content.strip(), "el .agent.md no puede estar vacío"
    assert "R-HITL" in content
    assert "CONFIRMO" in content
