"""Plan 196 F2 — modulo puro del pipeline de planes (sin Flask, sin red)."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from services import plans_pipeline


def test_action_commands_frozen():
    assert plans_pipeline._ACTION_COMMANDS == {
        "proponer": "/proponer-plan-stacky",
        "criticar": "/criticar-y-mejorar-plan",
        "implementar": "/implementar-plan-stacky",
        "supervisar": "/supervisar-implementaciones-planes",
    }


def test_build_prompt_criticar():
    out = plans_pipeline.build_action_prompt("criticar", "187", None)
    assert out == "/criticar-y-mejorar-plan 187"
    assert "\n" not in out


def test_build_prompt_proponer_sin_idea():
    assert plans_pipeline.build_action_prompt("proponer", None, None) == "/proponer-plan-stacky"


def test_build_prompt_proponer_sanea_idea():
    idea = "linea1\nlinea2\t  x\x1b[31m " + "a" * 600
    out = plans_pipeline.build_action_prompt("proponer", None, idea)
    assert out.startswith("/proponer-plan-stacky Tema: linea1 linea2 x")
    assert "\x1b" not in out
    assert "\n" not in out
    assert len(out) <= len("/proponer-plan-stacky Tema: ") + 500


def test_build_prompt_requiere_numero():
    with pytest.raises(ValueError):
        plans_pipeline.build_action_prompt("implementar", None, None)


def test_allowed_actions_table():
    assert plans_pipeline.allowed_actions_for("PROPUESTO", None) == ("criticar",)
    assert plans_pipeline.allowed_actions_for("CRITICADO", None) == ("implementar",)
    assert plans_pipeline.allowed_actions_for("IMPLEMENTADO", None) == ("supervisar",)
    assert plans_pipeline.allowed_actions_for("IMPLEMENTADO_PARCIAL", None) == ("supervisar",)
    assert plans_pipeline.allowed_actions_for("SIN_ESTADO", None) == ()
    assert "supervisar" in plans_pipeline.allowed_actions_for("PROPUESTO", True)


def test_sentinel_registered_one_shot():
    from services.claude_code_cli_runner import _ONE_SHOT_ADO_IDS

    assert plans_pipeline.PLANS_PIPELINE_ADO_ID == -9
    assert plans_pipeline.PLANS_PIPELINE_ADO_ID in _ONE_SHOT_ADO_IDS


def test_agent_registered():
    import agents

    a = agents.get("plans_pipeline")
    assert a is not None
    assert a.name == "Plans Pipeline Runner"
    sp = a.system_prompt()
    assert "push" in sp
    assert "--amend" in sp
    assert "--no-verify" in sp


def test_ensure_agent_file_writes_template(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "services.plans_pipeline_context.stacky_agents_dir", lambda: tmp_path
    )
    from services.plans_pipeline_context import ensure_plans_pipeline_agent_file

    dest = ensure_plans_pipeline_agent_file()
    assert dest.name == "PlansPipeline.agent.md"
    assert "PROHIBIDO `git push`" in dest.read_text(encoding="utf-8")

    dest.write_text("EDITADO POR EL OPERADOR", encoding="utf-8")
    ensure_plans_pipeline_agent_file()
    assert dest.read_text(encoding="utf-8") == "EDITADO POR EL OPERADOR"


def test_started_recently_cap():
    assert plans_pipeline._started_recently(None) is True
    assert plans_pipeline._started_recently(datetime.utcnow() - timedelta(minutes=5)) is True
    assert plans_pipeline._started_recently(datetime.utcnow() - timedelta(hours=3)) is False


def test_working_tree_status(tmp_path, monkeypatch):
    from services import plans_board

    monkeypatch.setattr(plans_board, "repo_root", lambda: None)
    assert plans_pipeline.working_tree_status() is None

    class _FakeResult:
        returncode = 0
        stdout = " M a.py\n?? b.ts\n"

    monkeypatch.setattr(plans_board, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(plans_pipeline.subprocess, "run", lambda *a, **k: _FakeResult())
    assert plans_pipeline.working_tree_status() == {"dirty": True, "changes": 2}
