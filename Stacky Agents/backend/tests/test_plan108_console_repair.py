"""tests/test_plan108_console_repair.py — Plan 108 F0: reparar consola remota del Plan 105."""
from __future__ import annotations

import json

import pytest

# Config mock
import config as _config


@pytest.fixture(autouse=True)
def _mock_flags(monkeypatch):
    """Mock flags necesarias."""
    monkeypatch.setattr(_config.config, "STACKY_DEVOPS_REMOTE_CONSOLE_ENABLED", True)
    monkeypatch.setattr(_config.config, "STACKY_DEVOPS_SERVERS_ENABLED", True)


@pytest.fixture
def mock_server_registry(monkeypatch):
    """Mock de get_server."""
    import services.server_registry

    def fake_get_server(alias):
        return {"alias": alias, "host": "example.com", "username": "user"}

    monkeypatch.setattr(services.server_registry, "get_server", fake_get_server)
    return fake_get_server


@pytest.fixture
def client(app):
    """Cliente Flask de prueba."""
    return app.test_client()


@pytest.fixture
def app(monkeypatch):
    """App Flask configurada."""
    from app import create_app

    # Mock current_user
    from api._helpers import current_user

    monkeypatch.setattr(current_user, "__call__", lambda: "test-user")

    return create_app()


class TestPlan108ConsoleRepair:
    """Tests F0 — reparación de la consola remota (bug P0)."""

    def test_create_conversation_launches_real_run(self, client, mock_server_registry, monkeypatch):
        """POST /conversations crea una ejecución real via run_agent (no mock mentiroso)."""
        # Mock de agent_runner.run_agent (origen del efecto, no _launch_turn)
        call_kwargs_store = {}
        original_run_agent = None

        def fake_run_agent(*args, **kwargs):
            call_kwargs_store.update(kwargs)
            return 101

        monkeypatch.setattr("agent_runner.run_agent", fake_run_agent)
        payload = {"server_alias": "srv1", "project": "P", "message": "hola"}
        rv = client.post("/api/devops/console/conversations", json=payload)
        assert rv.status_code == 202
        data = rv.get_json()
        assert data["execution_id"] == 101
        # Verificar kwargs recibidos
        assert call_kwargs_store["agent_type"] == "devops"
        assert call_kwargs_store["runtime"] == "claude_code_cli"

    def test_create_conversation_message_is_wrapped(self, client, mock_server_registry, monkeypatch):
        """El mensaje enviado al agente contiene el header de consola remota."""
        # Capturar context_blocks
        captured_blocks = []

        def side_effect(*args, **kwargs):
            captured_blocks.append(kwargs.get("context_blocks"))
            return 101

        monkeypatch.setattr("agent_runner.run_agent", side_effect)
        payload = {"server_alias": "srv1", "project": "P", "message": "hola"}
        rv = client.post("/api/devops/console/conversations", json=payload)
        assert rv.status_code == 202
        assert len(captured_blocks) == 1
        content = captured_blocks[0][0]["content"]
        assert "[CONSOLA REMOTA STACKY — servidor: srv1]" in content
        assert "hola" in content

    def test_message_new_turn_when_last_completed(self, client, mock_server_registry, monkeypatch):
        """POST /conversations/<cid>/message crea nuevo turno cuando el último está completed."""
        from db import session_scope
        from models import Ticket, AgentExecution
        import datetime

        # Sembrar ticket consola + execution completed
        with session_scope() as session:
            ticket = Ticket(
                ado_id=-4,
                project="P",
                title="Test consola",
                description=json.dumps({"kind": "remote_console", "server_alias": "srv1", "write_enabled": False}),
                ado_state="Active",
            )
            session.add(ticket)
            session.flush()
            ticket.external_id = -ticket.id
            exec1 = AgentExecution(
                ticket_id=ticket.id,
                agent_type="devops",
                status="completed",
                started_by="test",
                started_at=datetime.datetime.utcnow(),
            )
            exec1.input_context = []
            exec1.metadata_dict = {"runtime": "claude_code_cli"}
            session.add(exec1)
            session.commit()
            cid = ticket.id

        call_count = [0]
        def fake_run(*args, **kwargs):
            call_count[0] += 1
            return 101
        monkeypatch.setattr("agent_runner.run_agent", fake_run)
        payload = {"message": "nuevo mensaje"}
        rv = client.post(f"/api/devops/console/conversations/{cid}/message", json=payload)
        assert rv.status_code in (200, 202)
        assert call_count[0] == 1

    def test_message_live_uses_runner_send_input(self, client, mock_server_registry, monkeypatch):
        """POST /conversations/<cid>/message usa send_input del runner si execution está running."""
        from db import session_scope
        from models import Ticket, AgentExecution
        import datetime

        with session_scope() as session:
            ticket = Ticket(
                ado_id=-4,
                project="P",
                title="Test consola",
                description=json.dumps({"kind": "remote_console", "server_alias": "srv1", "write_enabled": False}),
                ado_state="Active",
            )
            session.add(ticket)
            session.flush()
            ticket.external_id = -ticket.id
            exec1 = AgentExecution(
                ticket_id=ticket.id,
                agent_type="devops",
                status="running",
                started_by="test",
                started_at=datetime.datetime.utcnow(),
            )
            exec1.input_context = []
            exec1.metadata_dict = {"runtime": "claude_code_cli"}
            session.add(exec1)
            session.commit()
            cid = ticket.id
            exec_id = exec1.id

        # Mock send_input del ORIGEN (gotcha lazy import)
        call_log = []
        def fake_send_input(exec_id_arg, message, user):
            call_log.append({"exec_id": exec_id_arg, "message": message, "user": user})
            return {"mode": "stdin"}
        monkeypatch.setattr("services.claude_code_cli_runner.send_input", fake_send_input)
        payload = {"message": "input texto"}
        rv = client.post(f"/api/devops/console/conversations/{cid}/message", json=payload)
        assert rv.status_code == 200
        assert len(call_log) == 1
        assert call_log[0]["exec_id"] == exec_id
        assert call_log[0]["message"] == "input texto"

    def test_source_has_no_send_input_import(self):
        """Centinela: el fuente NO contiene _send_input ni ticket_id ni .executions ni .state (C1 v2)."""
        from pathlib import Path

        # Path relativo al directorio backend
        source_file = Path(__file__).parent.parent / "api" / "devops_remote_console.py"
        source = source_file.read_text(encoding="utf-8")
        assert "_send_input" not in source
        assert "ticket_id=" not in source
        assert ".executions" not in source
        assert ".state" not in source

    def test_list_conversations_returns_last_execution_status(self, client, mock_server_registry):
        """GET /conversations devuelve last_execution con status (no state) y sin detached error."""
        from db import session_scope
        from models import Ticket, AgentExecution
        import datetime

        with session_scope() as session:
            ticket = Ticket(
                ado_id=-4,
                project="P",
                title="Test consola F0-6",
                description=json.dumps({"kind": "remote_console", "server_alias": "srv1", "write_enabled": False}),
                ado_state="Active",
            )
            session.add(ticket)
            session.flush()
            ticket.external_id = -ticket.id
            exec1 = AgentExecution(
                ticket_id=ticket.id,
                agent_type="devops",
                status="completed",
                started_by="test",
                started_at=datetime.datetime.utcnow(),
            )
            exec1.input_context = []
            session.add(exec1)
            session.commit()
            ticket_id = ticket.id
            exec_id = exec1.id

        rv = client.get("/api/devops/console/conversations?server=srv1")
        assert rv.status_code == 200
        data = rv.get_json()
        # Puede haber otros tickets de tests anteriores
        matching = [item for item in data if item["id"] == ticket_id]
        assert len(matching) == 1
        item = matching[0]
        assert "last_execution" in item
        assert item["last_execution"]["id"] == exec_id
        assert item["last_execution"]["status"] == "completed"
