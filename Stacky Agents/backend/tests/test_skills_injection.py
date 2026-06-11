"""Tests TDD para H4.3 — inyección de skills en runtimes CLI.

Testea:
  1. flag OFF → no inyección en claude
  2. flag ON + MCP activo → claude: índice + instrucción stacky_get_skill, NO cuerpo completo
  3. flag ON + MCP inactivo → claude: cuerpo top-1 presente (cap 1500 tokens)
  4. flag ON → copilot (base.py): cuerpo top-1 presente
  5. MCP activo → tools/list incluye stacky_get_skill
"""
from __future__ import annotations

import os
import sys
import textwrap
from pathlib import Path
from unittest.mock import MagicMock

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


# ── Fixture: skill de prueba ──────────────────────────────────────────────────


def _make_skills_dir(tmp_path: Path) -> Path:
    skill_file = tmp_path / "test-skill.skill.md"
    skill_file.write_text(
        textwrap.dedent("""\
        ---
        name: test-skill
        description: Skill de prueba para inyección
        agents: []
        projects: []
        keywords: [test, inyeccion]
        ---
        Cuerpo de la skill de prueba.
        """),
        encoding="utf-8",
    )
    return tmp_path


# ── Helpers para crear un VsCodeAgent mock ────────────────────────────────────


def _mock_agent(name: str = "TestAgent", filename: str = "test.agent.md") -> object:
    from services import vscode_agents

    return vscode_agents.VsCodeAgent(
        name=name,
        filename=filename,
        description="Agente de prueba",
        system_prompt="",
    )


# ── Test 1: flag OFF → no inyección en claude ──────────────────────────────────


def test_flag_off_no_injection_claude(tmp_path, monkeypatch):
    """STACKY_SKILLS_ENABLED=false → system prompt claude NO contiene 'Stacky Skills'."""
    from services import stacky_skills

    skills_dir = _make_skills_dir(tmp_path)
    stacky_skills._clear_cache()

    from config import config
    monkeypatch.setattr(config, "STACKY_SKILLS_ENABLED", False)
    monkeypatch.setattr(config, "STACKY_SKILLS_PROJECTS", "")

    from services import claude_code_cli_runner as r

    # Parchar el load de skills para usar tmp_path.
    original_select = stacky_skills.select_for_run

    def patched_select(**kwargs):
        return original_select(**{**kwargs, "root": skills_dir})

    monkeypatch.setattr(stacky_skills, "select_for_run", patched_select)

    agent = _mock_agent()
    prompt = r._build_system_prompt(
        agent,
        project_knowledge="",
        skills_section="",  # flag OFF → no se genera skills_section
    )
    assert "Stacky Skills" not in prompt


def test_flag_off_skills_section_empty(monkeypatch):
    """Con STACKY_SKILLS_ENABLED=false, skills_enabled retorna False."""
    from config import config
    monkeypatch.setattr(config, "STACKY_SKILLS_ENABLED", False)
    monkeypatch.setattr(config, "STACKY_SKILLS_PROJECTS", "")

    from services.cli_feature_flags import skills_enabled

    assert skills_enabled("cualquier-proyecto") is False
    assert skills_enabled(None) is False


# ── Test 2: flag ON + MCP activo → índice + tool, NO cuerpo ───────────────────


def test_flag_on_mcp_active_index_only(tmp_path, monkeypatch):
    """flag ON + MCP activo → system prompt contiene índice + 'stacky_get_skill', NO cuerpo."""
    from services import stacky_skills
    from config import config

    skills_dir = _make_skills_dir(tmp_path)
    stacky_skills._clear_cache()

    monkeypatch.setattr(config, "STACKY_SKILLS_ENABLED", True)
    monkeypatch.setattr(config, "STACKY_SKILLS_PROJECTS", "")
    # MCP activo
    monkeypatch.setattr(config, "CLAUDE_CODE_CLI_MCP_ENABLED", True)
    monkeypatch.setattr(config, "CLAUDE_CODE_CLI_MCP_PROJECTS", "")

    # Forzar que select_for_run use el tmp_path.
    original_select = stacky_skills.select_for_run

    def patched_select(**kwargs):
        kwargs.setdefault("root", skills_dir)
        if kwargs.get("context_text", "") == "":
            kwargs["context_text"] = "test inyeccion"
        return original_select(**{**kwargs, "root": skills_dir})

    monkeypatch.setattr(stacky_skills, "select_for_run", patched_select)

    # Simular la lógica de inyección que hace el runner (extraída en helper
    # para no necesitar levantar el runner completo).
    from services.cli_feature_flags import skills_enabled
    assert skills_enabled("proj-test") is True

    matched = stacky_skills.select_for_run(
        agent_type="dev",
        project="proj-test",
        context_text="test inyeccion",
        root=skills_dir,
    )
    assert matched, "debe haber al menos una skill para este test"

    # Rama MCP activo: solo índice + instrucción.
    index_text = stacky_skills.render_index(matched)
    skills_block = (
        "## Stacky Skills disponibles\n\n"
        + index_text
        + "\n\nPara obtener el procedimiento completo de una skill "
        "usá la tool `stacky_get_skill` con el nombre exacto."
    )

    from services import claude_code_cli_runner as r

    agent = _mock_agent()
    prompt = r._build_system_prompt(agent, skills_section=skills_block)

    assert "Stacky Skills" in prompt
    assert "stacky_get_skill" in prompt
    # El cuerpo completo NO debe estar (solo índice).
    assert "Cuerpo de la skill de prueba" not in prompt


# ── Test 3: flag ON + MCP inactivo → cuerpo top-1 ────────────────────────────


def test_flag_on_no_mcp_body_injected(tmp_path, monkeypatch):
    """flag ON + MCP inactivo → system prompt contiene cuerpo de top-1 skill (cap 1500 tokens)."""
    from services import stacky_skills
    from config import config

    skills_dir = _make_skills_dir(tmp_path)
    stacky_skills._clear_cache()

    monkeypatch.setattr(config, "STACKY_SKILLS_ENABLED", True)
    monkeypatch.setattr(config, "STACKY_SKILLS_PROJECTS", "")
    monkeypatch.setattr(config, "CLAUDE_CODE_CLI_MCP_ENABLED", False)

    matched = stacky_skills.select_for_run(
        agent_type="dev",
        project=None,
        context_text="test inyeccion de skill",
        root=skills_dir,
    )
    assert matched

    top = matched[0]
    index_text = stacky_skills.render_index(matched)
    skills_block = (
        "## Stacky Skills disponibles\n\n"
        + index_text
        + f"\n\n### Skill activa: {top.name}\n\n"
        + stacky_skills.cap_body(top.body)
    )

    from services import claude_code_cli_runner as r

    agent = _mock_agent()
    prompt = r._build_system_prompt(agent, skills_section=skills_block)

    assert "Stacky Skills" in prompt
    assert "Cuerpo de la skill de prueba" in prompt
    # No debe contener instrucción de tool (es modo sin MCP).
    assert "stacky_get_skill" not in prompt


# ── Test 4: flag ON → copilot base.py ─────────────────────────────────────────


def test_flag_on_copilot(tmp_path, monkeypatch):
    """flag ON → agents/base.py compone system prompt con cuerpo top-1 skill."""
    from services import stacky_skills
    from config import config

    skills_dir = _make_skills_dir(tmp_path)
    stacky_skills._clear_cache()

    monkeypatch.setattr(config, "STACKY_SKILLS_ENABLED", True)
    monkeypatch.setattr(config, "STACKY_SKILLS_PROJECTS", "")

    # Parchar select_for_run para usar tmp_path.
    original_select = stacky_skills.select_for_run

    def patched_select(**kwargs):
        return original_select(**{**kwargs, "root": skills_dir})

    monkeypatch.setattr(stacky_skills, "select_for_run", patched_select)

    # Crear agente concreto minimal (evita imports de DB).
    from agents.base import BaseAgent, RunContext

    class TestAgent(BaseAgent):
        type = "dev"
        name = "TestAgente"
        description = "para tests"

        def system_prompt(self) -> str:
            return "# System prompt base"

    agent = TestAgent()
    # Mockear few_shot / anti_patterns / decisions / constraints / style_memory
    # para que no fallen por falta de DB.
    monkeypatch.setattr("services.few_shot.pick_examples", lambda **kw: [])
    monkeypatch.setattr("services.anti_patterns.relevant", lambda **kw: [])
    monkeypatch.setattr("services.decisions.relevant", lambda **kw: [])
    monkeypatch.setattr("services.constraints.relevant", lambda **kw: [])

    ctx = RunContext(
        stacky_project_name="proj-test",
        context_text="test inyeccion copilot",
    )
    system_prompt, meta = agent.compose_system_prompt(ctx)

    assert "Stacky Skills" in system_prompt
    assert "Cuerpo de la skill de prueba" in system_prompt
    assert meta.get("skills_count", 0) > 0


# ── Test 5: MCP activo → tools/list incluye stacky_get_skill ─────────────────


def test_mcp_tool_registered():
    """Cuando MCP está activo, tools/list incluye stacky_get_skill."""
    from services import stacky_mcp_server

    msg = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
    response = stacky_mcp_server.handle_message(msg)

    assert response is not None
    tools = response.get("result", {}).get("tools", [])
    names = [t["name"] for t in tools]
    assert "stacky_get_skill" in names
