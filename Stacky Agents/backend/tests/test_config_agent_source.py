from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import config as config_module  # noqa: E402


def _write_agent(directory: Path, filename: str = "Developer.agent.md") -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / filename).write_text("# Developer\n\nprompt\n", encoding="utf-8")


def test_vscode_prompts_dir_uses_canonical_when_ready(monkeypatch, tmp_path):
    canonical = tmp_path / "Stacky" / "agents"
    legacy = tmp_path / "githubcopilot-pro"
    _write_agent(canonical, "Developer.agent.md")
    _write_agent(legacy, "OldDeveloper.agent.md")

    monkeypatch.setattr(config_module, "stacky_agents_dir", lambda: canonical)
    monkeypatch.setattr(config_module, "_project_agents_dir_if_configured", lambda: None)
    monkeypatch.setenv("VSCODE_PROMPTS_DIR", str(legacy))
    monkeypatch.delenv("STACKY_ALLOW_VSCODE_PROMPTS_OVERRIDE", raising=False)

    assert config_module.config.VSCODE_PROMPTS_DIR == str(canonical)


def test_vscode_prompts_dir_ignores_project_agents_dir(monkeypatch, tmp_path):
    canonical = tmp_path / "Stacky" / "agents"
    project_agents = tmp_path / "ProjectAgents"
    legacy = tmp_path / "githubcopilot-pro"
    _write_agent(canonical, "Developer.agent.md")
    _write_agent(project_agents, "ProjectDeveloper.agent.md")
    _write_agent(legacy, "OldDeveloper.agent.md")

    monkeypatch.setattr(config_module, "stacky_agents_dir", lambda: canonical)
    monkeypatch.setattr(config_module, "_project_agents_dir_if_configured", lambda: project_agents)
    monkeypatch.setenv("VSCODE_PROMPTS_DIR", str(legacy))
    monkeypatch.delenv("STACKY_ALLOW_VSCODE_PROMPTS_OVERRIDE", raising=False)

    assert config_module.config.VSCODE_PROMPTS_DIR == str(canonical)


def test_vscode_prompts_dir_ignores_legacy_force_flag(monkeypatch, tmp_path):
    canonical = tmp_path / "Stacky" / "agents"
    legacy = tmp_path / "githubcopilot-pro"
    _write_agent(canonical, "Developer.agent.md")
    _write_agent(legacy, "OldDeveloper.agent.md")

    monkeypatch.setattr(config_module, "stacky_agents_dir", lambda: canonical)
    monkeypatch.setattr(config_module, "_project_agents_dir_if_configured", lambda: None)
    monkeypatch.setenv("VSCODE_PROMPTS_DIR", str(legacy))
    monkeypatch.setenv("STACKY_ALLOW_VSCODE_PROMPTS_OVERRIDE", "true")

    assert config_module.config.VSCODE_PROMPTS_DIR == str(canonical)
