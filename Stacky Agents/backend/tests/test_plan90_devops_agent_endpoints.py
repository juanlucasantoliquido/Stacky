"""Plan 90 F2 — blueprint de conversaciones /api/devops/agent/... (tests primero).

Fixtures: patrón test_plan73_generator_endpoint.py:8-31 + DB real en memoria
(patrón test_ado_publisher_attachments.py:11-21) para ejercer el UNIQUE de tickets
(guard C1). Mocks: parchear agent_runner.run_agent EN EL MÓDULO ORIGEN (imports del
blueprint son lazy, patrón plan 28).
"""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

import pytest


@pytest.fixture
def app_flag_on():
    import config as cfg
    orig_agent = getattr(cfg.config, "STACKY_DEVOPS_AGENT_ENABLED", False)
    orig_panel = getattr(cfg.config, "STACKY_DEVOPS_PANEL_ENABLED", False)
    cfg.config.STACKY_DEVOPS_AGENT_ENABLED = True
    cfg.config.STACKY_DEVOPS_PANEL_ENABLED = True
    from app import create_app
    from db import init_db
    app = create_app()
    app.config["TESTING"] = True
    init_db()
    yield app
    cfg.config.STACKY_DEVOPS_AGENT_ENABLED = orig_agent
    cfg.config.STACKY_DEVOPS_PANEL_ENABLED = orig_panel


@pytest.fixture
def app_flag_off():
    import config as cfg
    orig = getattr(cfg.config, "STACKY_DEVOPS_AGENT_ENABLED", False)
    cfg.config.STACKY_DEVOPS_AGENT_ENABLED = False
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    yield app
    cfg.config.STACKY_DEVOPS_AGENT_ENABLED = orig


def _client(app):
    return app.test_client()


# ── F2 tests ──────────────────────────────────────────────────────────────────

def test_f2_flag_off_404(app_flag_off):
    c = _client(app_flag_off)
    assert c.post("/api/devops/agent/conversations", json={"project": "p", "message": "hola"}).status_code == 404
    assert c.post("/api/devops/agent/conversations/1/message", json={"message": "x"}).status_code == 404
    assert c.get("/api/devops/agent/conversations").status_code == 404


def test_f2_start_requires_project_and_message(app_flag_on):
    c = _client(app_flag_on)
    assert c.post("/api/devops/agent/conversations", json={}).status_code == 400
    assert c.post("/api/devops/agent/conversations", json={"project": "p"}).status_code == 400
    assert c.post("/api/devops/agent/conversations", json={"message": "m"}).status_code == 400


def test_f2_start_rejects_copilot(app_flag_on):
    c = _client(app_flag_on)
    r = c.post("/api/devops/agent/conversations",
               json={"project": "p", "message": "m", "runtime": "github_copilot"})
    assert r.status_code == 400
    assert r.get_json()["error"] == "devops_chat_requires_cli_runtime"


def test_f2_start_happy_path(app_flag_on, monkeypatch):
    import agent_runner
    monkeypatch.setattr(agent_runner, "run_agent", lambda **kw: 123)
    captured = {}
    orig = agent_runner.run_agent

    def _spy(**kw):
        captured.update(kw)
        return 123

    monkeypatch.setattr(agent_runner, "run_agent", _spy)
    c = _client(app_flag_on)
    r = c.post("/api/devops/agent/conversations", json={"project": "proj-x", "message": "diagnostica el deploy"})
    assert r.status_code == 202, r.get_data(as_text=True)
    body = r.get_json()
    assert body["execution_id"] == 123
    assert isinstance(body["conversation_id"], int)
    assert captured["agent_type"] == "devops"
    assert captured["vscode_agent_filename"] == "DevOpsAgent.agent.md"
    assert captured["work_item_type"] == "Task"
    assert captured["use_few_shot"] is False
    # Ticket ancla en DB con ado_id=-2
    from db import session_scope
    from models import Ticket
    with session_scope() as s:
        t = s.get(Ticket, body["conversation_id"])
        assert t is not None
        assert t.ado_id == -2


def test_f2_start_two_conversations_two_tickets(app_flag_on, monkeypatch):
    """Guard C1: 2 conversaciones del MISMO proyecto conviven (external_id=None ⇒
    NULLs distintos en el UNIQUE ux_tickets_stacky_tracker_external). Si volviera
    external_id=-2 fijo, el 2º INSERT tiraría IntegrityError y este test se pondría rojo."""
    import agent_runner
    monkeypatch.setattr(agent_runner, "run_agent", lambda **kw: 1)
    c = _client(app_flag_on)
    r1 = c.post("/api/devops/agent/conversations", json={"project": "same-proj", "message": "uno"})
    r2 = c.post("/api/devops/agent/conversations", json={"project": "same-proj", "message": "dos"})
    assert r1.status_code == 202
    assert r2.status_code == 202
    id1 = r1.get_json()["conversation_id"]
    id2 = r2.get_json()["conversation_id"]
    assert id1 != id2
    from db import session_scope
    from models import Ticket
    with session_scope() as s:
        t1 = s.get(Ticket, id1)
        t2 = s.get(Ticket, id2)
        assert t1.ado_id == -2 and t2.ado_id == -2


def test_f2_start_clamps_model(app_flag_on, monkeypatch):
    import agent_runner
    from services import llm_router
    calls = {}

    def _spy_clamp(model, allow_opus=False):
        calls["model"] = model
        calls["allow_opus"] = allow_opus
        return "sonnet-clamped"

    monkeypatch.setattr(llm_router, "clamp_model", _spy_clamp)
    captured = {}

    def _spy_run(**kw):
        captured.update(kw)
        return 7

    monkeypatch.setattr(agent_runner, "run_agent", _spy_run)
    c = _client(app_flag_on)
    r = c.post("/api/devops/agent/conversations",
               json={"project": "p", "message": "m", "model": "opus-4.8"})
    assert r.status_code == 202
    assert calls["allow_opus"] is False  # NUNCA Opus (guardarraíl 11)
    assert captured["model_override"] == "sonnet-clamped"


def _make_conversation(app, monkeypatch, *, last_status, runtime="claude_code_cli"):
    """Crea una conversación (ticket ancla) + una ejecución con status dado."""
    import agent_runner
    monkeypatch.setattr(agent_runner, "run_agent", lambda **kw: 999)
    c = _client(app)
    r = c.post("/api/devops/agent/conversations", json={"project": "p", "message": "inicial"})
    conv_id = r.get_json()["conversation_id"]
    from db import session_scope
    from models import AgentExecution
    with session_scope() as s:
        ex = AgentExecution(
            ticket_id=conv_id,
            agent_type="devops",
            status=last_status,
            input_context_json="[]",
            started_by="tester",
        )
        ex.metadata_dict = {"runtime": runtime}
        s.add(ex)
        s.flush()
        ex_id = ex.id
    return conv_id, ex_id


def test_f2_message_live_stdin(app_flag_on, monkeypatch):
    conv_id, ex_id = _make_conversation(app_flag_on, monkeypatch, last_status="running")
    from services import claude_code_cli_runner
    monkeypatch.setattr(
        claude_code_cli_runner, "send_input",
        lambda _id, _text, *, user=None: {"ok": True, "mode": "stdin", "execution_id": _id},
    )
    import agent_runner
    run_called = {"n": 0}
    monkeypatch.setattr(agent_runner, "run_agent", lambda **kw: run_called.__setitem__("n", run_called["n"] + 1) or 1)
    c = _client(app_flag_on)
    r = c.post(f"/api/devops/agent/conversations/{conv_id}/message", json={"message": "seguime"})
    assert r.status_code == 200
    assert r.get_json()["mode"] == "stdin"
    assert run_called["n"] == 0  # NO relanzó run_agent


def test_f2_message_dead_run_launches_new(app_flag_on, monkeypatch):
    conv_id, ex_id = _make_conversation(app_flag_on, monkeypatch, last_status="running")
    from services import claude_code_cli_runner

    def _dead(_id, _text, *, user=None):
        raise RuntimeError("stdin cerrado")

    monkeypatch.setattr(claude_code_cli_runner, "send_input", _dead)
    import agent_runner
    captured = {}

    def _spy_run(**kw):
        captured.update(kw)
        return 456

    monkeypatch.setattr(agent_runner, "run_agent", _spy_run)
    c = _client(app_flag_on)
    r = c.post(f"/api/devops/agent/conversations/{conv_id}/message", json={"message": "continua"})
    assert r.status_code == 202
    assert r.get_json()["mode"] == "new_run"
    assert captured["ticket_id"] == conv_id


def test_f2_message_completed_launches_new(app_flag_on, monkeypatch):
    conv_id, ex_id = _make_conversation(app_flag_on, monkeypatch, last_status="completed")
    from services import claude_code_cli_runner
    send_called = {"n": 0}
    monkeypatch.setattr(
        claude_code_cli_runner, "send_input",
        lambda *a, **k: send_called.__setitem__("n", send_called["n"] + 1) or {"ok": True},
    )
    import agent_runner
    captured = {}
    monkeypatch.setattr(agent_runner, "run_agent", lambda **kw: captured.update(kw) or 789)
    c = _client(app_flag_on)
    r = c.post(f"/api/devops/agent/conversations/{conv_id}/message", json={"message": "retoma"})
    assert r.status_code == 202
    assert r.get_json()["mode"] == "new_run"
    assert send_called["n"] == 0  # no intentó send_input sobre run completado
    assert captured["ticket_id"] == conv_id


def test_f2_message_not_found_404(app_flag_on):
    c = _client(app_flag_on)
    r = c.post("/api/devops/agent/conversations/999999/message", json={"message": "x"})
    assert r.status_code == 404
    assert r.get_json()["error"] == "conversation_not_found"


def test_f2_list_returns_conversation_and_resume_flag(app_flag_on, monkeypatch):
    conv_id, ex_id = _make_conversation(app_flag_on, monkeypatch, last_status="completed")
    c = _client(app_flag_on)
    r = c.get("/api/devops/agent/conversations")
    assert r.status_code == 200
    body = r.get_json()
    assert "resume_enabled" in body and isinstance(body["resume_enabled"], bool)
    ids = [it["conversation_id"] for it in body["conversations"]]
    assert conv_id in ids
    item = next(it for it in body["conversations"] if it["conversation_id"] == conv_id)
    assert item["last_execution_id"] == ex_id


def test_f2_list_item_continuable_flag(app_flag_on, monkeypatch):
    import config as cfg
    from services.cli_feature_flags import project_enabled  # noqa: F401 (doc)

    # resume OFF ⇒ todo item continuable_with_memory == False
    orig_enabled = getattr(cfg.config, "CLAUDE_CODE_CLI_RESUME_ENABLED", False)
    orig_projects = getattr(cfg.config, "CLAUDE_CODE_CLI_RESUME_PROJECTS", "")
    try:
        cfg.config.CLAUDE_CODE_CLI_RESUME_ENABLED = False
        conv_id, _ = _make_conversation(app_flag_on, monkeypatch, last_status="completed")
        c = _client(app_flag_on)
        body = c.get("/api/devops/agent/conversations?project=p").get_json()
        assert all(it["continuable_with_memory"] is False for it in body["conversations"])

        # resume ON + último run completed ⇒ True
        cfg.config.CLAUDE_CODE_CLI_RESUME_ENABLED = True
        cfg.config.CLAUDE_CODE_CLI_RESUME_PROJECTS = ""  # vacío = todos
        body2 = c.get("/api/devops/agent/conversations?project=p").get_json()
        item2 = next(it for it in body2["conversations"] if it["conversation_id"] == conv_id)
        assert item2["continuable_with_memory"] is True

        # resume ON pero último run failed ⇒ False (la señal no miente)
        conv_id3, _ = _make_conversation(app_flag_on, monkeypatch, last_status="failed")
        body3 = c.get("/api/devops/agent/conversations?project=p").get_json()
        item3 = next(it for it in body3["conversations"] if it["conversation_id"] == conv_id3)
        assert item3["continuable_with_memory"] is False
    finally:
        cfg.config.CLAUDE_CODE_CLI_RESUME_ENABLED = orig_enabled
        cfg.config.CLAUDE_CODE_CLI_RESUME_PROJECTS = orig_projects


def test_f2_route_registered(app_flag_on):
    rules = [r.rule for r in app_flag_on.url_map.iter_rules()]
    assert "/api/devops/agent/conversations" in rules


def test_f2_health_has_agent_enabled(app_flag_on):
    c = _client(app_flag_on)
    r = c.get("/api/devops/health")
    assert r.status_code == 200
    assert "agent_enabled" in r.get_json()
