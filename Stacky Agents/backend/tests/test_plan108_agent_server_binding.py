"""tests/test_plan108_agent_server_binding.py — Plan 108 F3: el chat del agente
DevOps acepta server_alias y ancla el turno al servidor seleccionado (cierra RC1
en el backend). Mockea SIEMPRE agent_runner.run_agent (origen), NUNCA _launch_turn."""
from __future__ import annotations

import datetime
import json

import pytest

import config as _config


@pytest.fixture
def app():
    import config as cfg
    orig = getattr(cfg.config, "STACKY_DEVOPS_AGENT_ENABLED", False)
    cfg.config.STACKY_DEVOPS_AGENT_ENABLED = True
    from app import create_app
    from db import init_db
    flask_app = create_app()
    flask_app.config["TESTING"] = True
    init_db()
    yield flask_app
    cfg.config.STACKY_DEVOPS_AGENT_ENABLED = orig


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def remote_target_on(monkeypatch):
    """Las 3 flags que _validate_remote_target exige para pasar el gate de deps."""
    monkeypatch.setattr(_config.config, "STACKY_DEVOPS_REMOTE_TARGET_ENABLED", True)
    monkeypatch.setattr(_config.config, "STACKY_DEVOPS_SERVERS_ENABLED", True)
    monkeypatch.setattr(_config.config, "STACKY_DEVOPS_REMOTE_CONSOLE_ENABLED", True)


@pytest.fixture
def mock_server_registry(monkeypatch):
    import services.server_registry

    def fake_get_server(alias):
        return {"alias": alias, "host": "example.com", "username": "user"}

    monkeypatch.setattr(services.server_registry, "get_server", fake_get_server)
    return fake_get_server


def _seed_sealed_conversation(server_alias="srv1", last_status="completed"):
    """Ticket sellado (description con server_alias) + AgentExecution. Retorna cid."""
    from db import session_scope
    from models import Ticket, AgentExecution
    with session_scope() as session:
        ticket = Ticket(
            ado_id=-2,
            project="p",
            stacky_project_name="p",
            title="chat sellado",
            description=json.dumps({"kind": "devops_chat", "server_alias": server_alias}),
            work_item_type="Task",
            ado_state="Active",
        )
        session.add(ticket)
        session.flush()
        ticket.external_id = -ticket.id
        ex = AgentExecution(
            ticket_id=ticket.id,
            agent_type="devops",
            status=last_status,
            started_by="test",
            started_at=datetime.datetime.utcnow(),
        )
        ex.input_context = []
        ex.metadata_dict = {"runtime": "claude_code_cli"}
        session.add(ex)
        session.commit()
        return ticket.id


class TestAgentServerBinding:
    """F3 — 9 tests (incluye C3 v2 y ADICIÓN ARQUITECTO v2)."""

    def test_start_without_alias_unchanged(self, client, monkeypatch):
        """1. Byte-compat: sin server_alias, el content NO contiene el header de consola."""
        captured = []

        def fake_run(**kw):
            captured.append(kw)
            return 1

        monkeypatch.setattr("agent_runner.run_agent", fake_run)
        rv = client.post("/api/devops/agent/conversations", json={"project": "p", "message": "hola"})
        assert rv.status_code == 202
        content = captured[0]["context_blocks"][0]["content"]
        assert "CONSOLA REMOTA" not in content

    def test_start_with_alias_flag_off_400(self, client):
        """2. server_alias sin la flag 108 ⇒ 400 remote_target_disabled."""
        rv = client.post(
            "/api/devops/agent/conversations",
            json={"project": "p", "message": "hola", "server_alias": "srv1"},
        )
        assert rv.status_code == 400
        assert rv.get_json()["error"] == "remote_target_disabled"

    def test_start_with_alias_deps_off_409(self, client, monkeypatch):
        """3. Flag 108 ON pero servers/consola OFF ⇒ 409."""
        monkeypatch.setattr(_config.config, "STACKY_DEVOPS_REMOTE_TARGET_ENABLED", True)
        rv = client.post(
            "/api/devops/agent/conversations",
            json={"project": "p", "message": "hola", "server_alias": "srv1"},
        )
        assert rv.status_code == 409
        assert rv.get_json()["error"] == "remote_target_requires_servers_and_console"

    def test_start_with_alias_unknown_404(self, client, remote_target_on, monkeypatch):
        """4. get_server lanza ⇒ 404 server_not_found."""
        import services.server_registry

        def raise_unknown(alias):
            raise KeyError(alias)

        monkeypatch.setattr(services.server_registry, "get_server", raise_unknown)
        rv = client.post(
            "/api/devops/agent/conversations",
            json={"project": "p", "message": "hola", "server_alias": "srv1"},
        )
        assert rv.status_code == 404
        assert rv.get_json()["error"] == "server_not_found"

    def test_start_with_alias_wraps_and_seals(self, client, remote_target_on, mock_server_registry, monkeypatch):
        """5. Flags ON + get_server OK ⇒ 202, content envuelto, Ticket sellado, resp con alias."""
        captured = []

        def fake_run(**kw):
            captured.append(kw)
            return 55

        monkeypatch.setattr("agent_runner.run_agent", fake_run)
        rv = client.post(
            "/api/devops/agent/conversations",
            json={"project": "p", "message": "hola", "server_alias": "srv1"},
        )
        assert rv.status_code == 202
        body = rv.get_json()
        assert body["server_alias"] == "srv1"
        content = captured[0]["context_blocks"][0]["content"]
        assert "[CONSOLA REMOTA STACKY — servidor: srv1]" in content
        assert "PROHIBIDO usar tus herramientas locales" in content

        from db import session_scope
        from models import Ticket
        with session_scope() as s:
            t = s.get(Ticket, body["conversation_id"])
            meta = json.loads(t.description)
            assert meta["server_alias"] == "srv1"

    def test_send_message_new_turn_rewraps(self, client, remote_target_on, mock_server_registry, monkeypatch):
        """6. Turno nuevo sobre ticket sellado ⇒ content re-envuelto."""
        cid = _seed_sealed_conversation()
        captured = []

        def fake_run(**kw):
            captured.append(kw)
            return 66

        monkeypatch.setattr("agent_runner.run_agent", fake_run)
        rv = client.post(f"/api/devops/agent/conversations/{cid}/message", json={"message": "seguimos"})
        assert rv.status_code in (200, 202)
        content = captured[0]["context_blocks"][0]["content"]
        assert "[CONSOLA REMOTA STACKY — servidor: srv1]" in content

    def test_list_conversations_exposes_alias(self, client, remote_target_on, mock_server_registry, monkeypatch):
        """7. GET lista ⇒ item con server_alias."""
        monkeypatch.setattr("agent_runner.run_agent", lambda **kw: 1)
        client.post(
            "/api/devops/agent/conversations",
            json={"project": "p", "message": "hola", "server_alias": "srv1"},
        )
        rv = client.get("/api/devops/agent/conversations?project=p")
        assert rv.status_code == 200
        items = rv.get_json()["conversations"]
        assert any(it.get("server_alias") == "srv1" for it in items)

    def test_send_message_sealed_flag_off_409(self, client, monkeypatch):
        """8 (C3 v2). Conversación sellada + flag 108 OFF ⇒ 409, NUNCA turno local silencioso."""
        cid = _seed_sealed_conversation()
        called = {"n": 0}

        def fake_run(**kw):
            called["n"] += 1
            return 1

        monkeypatch.setattr("agent_runner.run_agent", fake_run)
        rv = client.post(f"/api/devops/agent/conversations/{cid}/message", json={"message": "algo"})
        assert rv.status_code == 409
        assert rv.get_json()["error"] == "remote_target_disabled_for_sealed_conversation"
        assert called["n"] == 0

    def test_list_conversations_audited_count(self, client, remote_target_on, mock_server_registry, monkeypatch):
        """9 (ADICIÓN ARQUITECTO v2). audited_remote_commands: conteo / ausente / None."""
        monkeypatch.setattr("agent_runner.run_agent", lambda **kw: 1)
        rv = client.post(
            "/api/devops/agent/conversations",
            json={"project": "p", "message": "hola", "server_alias": "srv1"},
        )
        cid = rv.get_json()["conversation_id"]

        def fake_read_audit(alias, limit=500):
            return [
                {"kind": "exec", "conversation_id": cid},
                {"kind": "exec", "conversation_id": cid},
                {"kind": "exec", "conversation_id": cid},
                {"kind": "exec", "conversation_id": 999999},
                {"kind": "write_mode", "conversation_id": cid},
            ]

        monkeypatch.setattr("services.remote_exec.read_audit", fake_read_audit)
        rv2 = client.get("/api/devops/agent/conversations?project=p")
        item = next(it for it in rv2.get_json()["conversations"] if it["conversation_id"] == cid)
        assert item["audited_remote_commands"] == 3

        # Conversación SIN alias ⇒ key ausente.
        monkeypatch.setattr("agent_runner.run_agent", lambda **kw: 2)
        client.post("/api/devops/agent/conversations", json={"project": "p", "message": "sin alias"})
        rv3 = client.get("/api/devops/agent/conversations?project=p")
        no_alias_item = next(it for it in rv3.get_json()["conversations"] if not it.get("server_alias"))
        assert "audited_remote_commands" not in no_alias_item

        # read_audit lanza ⇒ key None, 200 igual (jamás se cae el listado).
        def raise_exc(alias, limit=500):
            raise RuntimeError("boom")

        monkeypatch.setattr("services.remote_exec.read_audit", raise_exc)
        rv4 = client.get("/api/devops/agent/conversations?project=p")
        assert rv4.status_code == 200
        item4 = next(it for it in rv4.get_json()["conversations"] if it["conversation_id"] == cid)
        assert item4["audited_remote_commands"] is None
