"""Plan 196 F3 — endpoints de acción, historial y commits del pipeline de planes.

Patrón de fixture app/client: tests/test_plan131_incident_flag.py.
Los casos flag-ON monkeypatchean SIEMPRE la INSTANCIA `config.config` (G1: el
getattr sobre el MÓDULO devolvería el default y mataría el branch OFF).
"""
from __future__ import annotations

import pytest


def _make_app(actions_enabled: bool):
    import config as cfg

    originals = {
        "STACKY_PLANS_BOARD_ENABLED": getattr(cfg.config, "STACKY_PLANS_BOARD_ENABLED", False),
        "STACKY_PLANS_PIPELINE_ACTIONS_ENABLED": getattr(
            cfg.config, "STACKY_PLANS_PIPELINE_ACTIONS_ENABLED", False
        ),
    }
    cfg.config.STACKY_PLANS_BOARD_ENABLED = True
    cfg.config.STACKY_PLANS_PIPELINE_ACTIONS_ENABLED = actions_enabled
    from app import create_app

    app = create_app()
    app.config["TESTING"] = True
    return app, cfg, originals


@pytest.fixture
def client_off():
    app, cfg, originals = _make_app(False)
    yield app.test_client()
    for k, v in originals.items():
        setattr(cfg.config, k, v)


@pytest.fixture
def client_on():
    app, cfg, originals = _make_app(True)
    yield app.test_client()
    for k, v in originals.items():
        setattr(cfg.config, k, v)


def _board_with(number: int, estado: str, ledger=None):
    return {
        "plans": [
            {
                "number": number,
                "number_str": f"{number:03d}",
                "filename": f"{number:03d}_PLAN_TEST.md",
                "estado": estado,
                "ledger": ledger,
            }
        ]
    }


def _skill_tree(tmp_path, skill_dir: str):
    d = tmp_path / ".claude" / "skills" / skill_dir
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text("# skill", encoding="utf-8")
    return tmp_path


def test_actions_flag_off_404(client_off):
    r = client_off.post("/api/plans-board/actions/run", json={"action": "proponer"})
    assert r.status_code == 404
    assert r.get_json()["error"] == "plans_pipeline_disabled"

    r2 = client_off.get("/api/plans-board/actions/runs")
    assert r2.status_code == 404
    assert r2.get_json()["error"] == "plans_pipeline_disabled"


def test_runtime_not_supported(client_on):
    r = client_on.post(
        "/api/plans-board/actions/run",
        json={"action": "proponer", "runtime": "codex_cli"},
    )
    assert r.status_code == 409
    body = r.get_json()
    assert body["error"] == "runtime_not_supported"
    assert body["supported"] == ["claude_code_cli"]


def test_invalid_action_400(client_on):
    r = client_on.post("/api/plans-board/actions/run", json={"action": "deployar"})
    assert r.status_code == 400
    assert r.get_json()["error"] == "invalid_action"


def test_repo_not_available_409(client_on, monkeypatch):
    from services import plans_board

    monkeypatch.setattr(plans_board, "repo_root", lambda: None)
    r = client_on.post("/api/plans-board/actions/run", json={"action": "proponer"})
    assert r.status_code == 409
    assert r.get_json()["error"] == "repo_not_available"


def test_skills_not_found_409(client_on, monkeypatch, tmp_path):
    from services import plans_board

    monkeypatch.setattr(plans_board, "repo_root", lambda: tmp_path)
    r = client_on.post("/api/plans-board/actions/run", json={"action": "proponer"})
    assert r.status_code == 409
    body = r.get_json()
    assert body["error"] == "skills_not_found"
    assert body["skill"] == "proponer-plan-stacky"


def test_action_not_allowed_for_estado(client_on, monkeypatch, tmp_path):
    from services import plans_board

    root = _skill_tree(tmp_path, "criticar-y-mejorar-plan")
    monkeypatch.setattr(plans_board, "repo_root", lambda: root)
    monkeypatch.setattr(
        plans_board, "get_board_cached",
        lambda refresh=False: _board_with(42, "IMPLEMENTADO"),
    )
    r = client_on.post(
        "/api/plans-board/actions/run",
        json={"action": "criticar", "plan_number": 42},
    )
    assert r.status_code == 409
    body = r.get_json()
    assert body["error"] == "action_not_allowed_for_estado"
    assert body["allowed"] == ["supervisar"]


def test_busy_409(client_on, monkeypatch, tmp_path):
    from services import plans_board, plans_pipeline

    root = _skill_tree(tmp_path, "criticar-y-mejorar-plan")
    monkeypatch.setattr(plans_board, "repo_root", lambda: root)
    monkeypatch.setattr(
        plans_board, "get_board_cached",
        lambda refresh=False: _board_with(42, "PROPUESTO"),
    )
    monkeypatch.setattr(plans_pipeline, "find_running_pipeline_execution", lambda: 777)
    monkeypatch.setattr(
        "services.plans_pipeline_context.ensure_plans_pipeline_agent_file",
        lambda: None,
    )
    r = client_on.post(
        "/api/plans-board/actions/run",
        json={"action": "criticar", "plan_number": 42},
    )
    assert r.status_code == 409
    body = r.get_json()
    assert body["error"] == "pipeline_action_already_running"
    assert body["execution_id"] == 777


def test_happy_path_launches_run_agent(client_on, monkeypatch, tmp_path):
    import agent_runner
    from services import plans_board, plans_pipeline

    root = _skill_tree(tmp_path, "criticar-y-mejorar-plan")
    monkeypatch.setattr(plans_board, "repo_root", lambda: root)
    monkeypatch.setattr(
        plans_board, "get_board_cached",
        lambda refresh=False: _board_with(42, "PROPUESTO"),
    )
    monkeypatch.setattr(plans_pipeline, "find_running_pipeline_execution", lambda: None)
    monkeypatch.setattr(
        "services.plans_pipeline_context.ensure_plans_pipeline_agent_file",
        lambda: None,
    )

    captured: dict = {}

    def _fake_run_agent(**kwargs):
        captured.update(kwargs)
        return 123

    monkeypatch.setattr(agent_runner, "run_agent", _fake_run_agent)

    r = client_on.post(
        "/api/plans-board/actions/run",
        json={"action": "criticar", "plan_number": 42},
    )
    assert r.status_code == 202, r.get_json()
    body = r.get_json()
    assert body["execution_id"] == 123
    assert body["prompt_line"] == "/criticar-y-mejorar-plan 042"

    assert captured["agent_type"] == "plans_pipeline"
    assert captured["runtime"] == "claude_code_cli"
    assert captured["vscode_agent_filename"] == "PlansPipeline.agent.md"
    assert captured["workspace_root_override"].endswith(tmp_path.name)
    assert captured["context_blocks"][0]["content"] == "/criticar-y-mejorar-plan 042"


def test_runs_history_serialization(client_on, monkeypatch):
    from db import session_scope
    from models import AgentExecution, Ticket
    from services import plans_pipeline

    monkeypatch.setattr(
        plans_pipeline, "working_tree_status",
        lambda: {"dirty": False, "changes": 0},
    )
    monkeypatch.setattr(plans_pipeline, "find_running_pipeline_execution", lambda: None)

    # get-or-create + limpieza: el test corre contra la DB de dev REAL, asi que
    # tiene que ser idempotente (el indice unico es
    # (stacky_project_name, tracker_type, external_id)) y no dejar basura.
    with session_scope() as s:
        t = (
            s.query(Ticket)
            .filter_by(stacky_project_name="test-plan196", external_id=-999901)
            .first()
        )
        if t is None:
            t = Ticket(
                ado_id=-9, external_id=-999901, project="default",
                stacky_project_name="test-plan196", title="pool",
                work_item_type="Task", ado_state="Active",
            )
            s.add(t)
            s.flush()
        ticket_id = t.id
        ex = AgentExecution(
            ticket_id=ticket_id, agent_type="plans_pipeline", status="completed",
            input_context_json="[]", started_by="tester",
        )
        ex.metadata_dict = {
            "plans_pipeline": {
                "action": "proponer", "plan_number": None,
                "model": "claude-sonnet-5", "effort": "high",
                "prompt_line": "/proponer-plan-stacky",
            }
        }
        s.add(ex)
        s.flush()
        execution_id = ex.id

    try:
        r = client_on.get("/api/plans-board/actions/runs")
        assert r.status_code == 200
        body = r.get_json()
        assert body["busy"] is False
        assert body["working_tree"] == {"dirty": False, "changes": 0}
        assert body["runs"][0]["action"] == "proponer"
        assert body["runs"][0]["prompt_line"] == "/proponer-plan-stacky"
    finally:
        # Solo se borra la EJECUCION. El ticket fixture queda (get-or-create):
        # borrar el padre hace que SQLAlchemy intente anular ticket_id en las
        # ejecuciones hijas, que es NOT NULL -> IntegrityError.
        with session_scope() as s:
            for row in (
                s.query(AgentExecution).filter_by(ticket_id=ticket_id).all()
            ):
                s.delete(row)


def test_commits_endpoint(client_on, monkeypatch):
    from services import plans_board, plans_pipeline

    monkeypatch.setattr(plans_board, "get_detail", lambda n: None)
    r = client_on.get("/api/plans-board/commits/999999")
    assert r.status_code == 404
    assert r.get_json()["error"] == "plan_not_found"

    monkeypatch.setattr(
        plans_board, "get_detail",
        lambda n: {"plan": {"filename": "042_PLAN_TEST.md"}},
    )
    monkeypatch.setattr(plans_pipeline, "recent_commits_for_doc", lambda f: None)
    r2 = client_on.get("/api/plans-board/commits/42")
    assert r2.status_code == 200
    body = r2.get_json()
    assert body["git_available"] is False
    assert body["commits"] == []
