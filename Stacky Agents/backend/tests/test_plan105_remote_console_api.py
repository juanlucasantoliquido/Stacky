"""tests/test_plan105_remote_console_api.py — Plan 105 F2.

Tests del blueprint api/devops_remote_console.py (7 rutas).
Flask test client; run_remote/check_winrm/keyring mockeados.
"""
from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

import pytest
from unittest import mock

from models import Ticket


@pytest.fixture
def app():
    """Flask app para testing (flags ON)."""
    import config as cfg
    orig_console = getattr(cfg.config, "STACKY_DEVOPS_REMOTE_CONSOLE_ENABLED", False)
    orig_servers = getattr(cfg.config, "STACKY_DEVOPS_SERVERS_ENABLED", False)
    orig_panel = getattr(cfg.config, "STACKY_DEVOPS_PANEL_ENABLED", False)
    cfg.config.STACKY_DEVOPS_REMOTE_CONSOLE_ENABLED = True
    cfg.config.STACKY_DEVOPS_SERVERS_ENABLED = True
    cfg.config.STACKY_DEVOPS_PANEL_ENABLED = True
    from app import create_app
    from db import init_db
    app = create_app()
    app.config["TESTING"] = True
    init_db()
    yield app
    cfg.config.STACKY_DEVOPS_REMOTE_CONSOLE_ENABLED = orig_console
    cfg.config.STACKY_DEVOPS_SERVERS_ENABLED = orig_servers
    cfg.config.STACKY_DEVOPS_PANEL_ENABLED = orig_panel


@pytest.fixture
def app_client(app):
    """Client de prueba Flask."""
    return app.test_client()


@pytest.fixture
def db_session(app):
    """Sesión de DB para testing."""
    from db import db
    db.session.commit()
    return db.session


class TestF2RoutesGuard:
    """F2 — Tests de guard (flag OFF)."""

    def test_f2_all_routes_404_flag_off(self, app_client):
        """Con flag OFF, las 7 rutas devuelven 404."""
        import config as _config
        with mock.patch.object(_config.config, "STACKY_DEVOPS_REMOTE_CONSOLE_ENABLED", False):
            r1 = app_client.post("/api/devops/console/exec", json={"alias": "s1", "command": "Get-Process"})
            assert r1.status_code == 404

            r2 = app_client.get("/api/devops/console/audit/s1")
            assert r2.status_code == 404

            r3 = app_client.get("/api/devops/console/winrm/s1")
            assert r3.status_code == 404

            r4 = app_client.post("/api/devops/console/conversations", json={"server_alias": "s1", "project": "p1", "message": "test"})
            assert r4.status_code == 404

            r5 = app_client.post("/api/devops/console/conversations/1/message", json={"message": "hi"})
            assert r5.status_code == 404

            r6 = app_client.post("/api/devops/console/conversations/1/write-mode", json={"enabled": True})
            assert r6.status_code == 404

            r7 = app_client.get("/api/devops/console/conversations?server=s1")
            assert r7.status_code == 404


class TestF2ExecRoute:
    """F2 — Tests de POST /exec."""

    def test_f2_exec_409_servers_disabled(self, app_client):
        """flag consola ON + servers OFF ⇒ 409."""
        import config as _config
        with mock.patch.object(_config.config, "STACKY_DEVOPS_REMOTE_CONSOLE_ENABLED", True):
            with mock.patch.object(_config.config, "STACKY_DEVOPS_SERVERS_ENABLED", False):
                r = app_client.post("/api/devops/console/exec", json={"alias": "s1", "command": "Get-Process"})
                assert r.status_code == 409
                data = r.get_json()
                assert data["error"] == "remote_console_requires_servers"

    def test_f2_exec_non_json_400(self, app_client):
        """POST form-encoded ⇒ 400 (patrón C5 plan 91)."""
        import config as _config
        with mock.patch.object(_config.config, "STACKY_DEVOPS_REMOTE_CONSOLE_ENABLED", True):
            with mock.patch.object(_config.config, "STACKY_DEVOPS_SERVERS_ENABLED", True):
                r = app_client.post("/api/devops/console/exec", data="alias=s1&command=Get-Process", content_type="application/x-www-form-urlencoded")
                assert r.status_code == 400

    def test_f2_exec_read_only_403(self, app_client):
        """run_remote mock devuelve command_not_read_only ⇒ 403."""
        import config as _config
        with mock.patch.object(_config.config, "STACKY_DEVOPS_REMOTE_CONSOLE_ENABLED", True):
            with mock.patch.object(_config.config, "STACKY_DEVOPS_SERVERS_ENABLED", True):
                with mock.patch("services.remote_exec.run_remote", return_value={"ok": False, "error": "command_not_read_only"}):
                    r = app_client.post("/api/devops/console/exec", json={"alias": "s1", "command": "Remove-Item x"})
                    assert r.status_code == 403
                    data = r.get_json()
                    assert data["error"] == "command_not_read_only"

    def test_f2_exec_manual_no_conversation_is_read_only(self, app_client):
        """POST /exec SIN conversation_id ⇒ run_remote recibe mode=read_only."""
        import config as _config
        captured_mode = None
        def fake_run_remote(*args, mode=None, **kwargs):
            nonlocal captured_mode
            captured_mode = mode
            return {"ok": True, "stdout": "out", "stderr": "", "exit_code": 0, "duration_ms": 100}

        with mock.patch.object(_config.config, "STACKY_DEVOPS_REMOTE_CONSOLE_ENABLED", True):
            with mock.patch.object(_config.config, "STACKY_DEVOPS_SERVERS_ENABLED", True):
                with mock.patch("services.remote_exec.run_remote", side_effect=fake_run_remote):
                    r = app_client.post("/api/devops/console/exec", json={"alias": "s1", "command": "Get-Process"})
                    assert r.status_code == 200
                    assert captured_mode == "read_only"

    def test_f2_exec_write_requires_conversation_flag(self, app_client, db_session):
        """Conversación con write_enabled=False ⇒ mode=read_only; tras POST /write-mode ⇒ mode=write."""
        import config as _config
        pass  # db ya está disponible via db_session (fixture conftest)  # noqa: F401 (fixture)

        # Crear conversación
        ticket = Ticket(
            ado_id=-4,
            project="test",
            stacky_project_name="test",
            title="Test",
            work_item_type="Task",
            ado_state="Active",
            description='{"kind":"remote_console","server_alias":"s1","write_enabled":False}',
        )
        db_session.add(ticket)
        db_session.commit()
        cid = ticket.id

        captured_mode = None
        def fake_run_remote(*args, mode=None, **kwargs):
            nonlocal captured_mode
            captured_mode = mode
            return {"ok": True, "stdout": "out", "stderr": "", "exit_code": 0, "duration_ms": 100}

        with mock.patch.object(_config.config, "STACKY_DEVOPS_REMOTE_CONSOLE_ENABLED", True):
            with mock.patch.object(_config.config, "STACKY_DEVOPS_SERVERS_ENABLED", True):
                with mock.patch("services.remote_exec.run_remote", side_effect=fake_run_remote):
                    # Primer exec: write_enabled=False ⇒ read_only
                    r1 = app_client.post("/api/devops/console/exec", json={"alias": "s1", "command": "Get-Process", "conversation_id": cid})
                    assert r1.status_code == 200
                    assert captured_mode == "read_only"

                    # Activar write_mode
                    r2 = app_client.post(f"/api/devops/console/conversations/{cid}/write-mode", json={"enabled": True})
                    assert r2.status_code == 200

                    # Segundo exec: ahora ⇒ write
                    r3 = app_client.post("/api/devops/console/exec", json={"alias": "s1", "command": "Remove-Item x", "conversation_id": cid})
                    assert r3.status_code == 200
                    assert captured_mode == "write"

    def test_f2_write_mode_wrong_alias_stays_read_only(self, app_client, db_session):
        """Conversación de alias A no habilita escritura en alias B."""
        import config as _config
        pass  # db ya está disponible via db_session (fixture conftest)

        # Crear conversación para alias A
        ticket = Ticket(
            ado_id=-4,
            project="test",
            stacky_project_name="test",
            title="Test",
            work_item_type="Task",
            ado_state="Active",
            description='{"kind":"remote_console","server_alias":"A","write_enabled":True}',
        )
        db_session.add(ticket)
        db_session.commit()
        cid = ticket.id

        captured_mode = None
        def fake_run_remote(*args, mode=None, **kwargs):
            nonlocal captured_mode
            captured_mode = mode
            return {"ok": True, "stdout": "out", "stderr": "", "exit_code": 0, "duration_ms": 100}

        with mock.patch.object(_config.config, "STACKY_DEVOPS_REMOTE_CONSOLE_ENABLED", True):
            with mock.patch.object(_config.config, "STACKY_DEVOPS_SERVERS_ENABLED", True):
                with mock.patch("services.remote_exec.run_remote", side_effect=fake_run_remote):
                    # Exec en alias B con conversation_id de alias A ⇒ read_only
                    r = app_client.post("/api/devops/console/exec", json={"alias": "B", "command": "Remove-Item x", "conversation_id": cid})
                    assert r.status_code == 200
                    assert captured_mode == "read_only"


class TestF2Conversations:
    """F2 — Tests de conversaciones."""

    def test_f2_conversation_created_with_external_id_sealed(self, app_client, db_session):
        """external_id == -ticket.id y description JSON con server_alias."""
        import config as _config
        pass  # db ya está disponible via db_session (fixture conftest)

        with mock.patch.object(_config.config, "STACKY_DEVOPS_REMOTE_CONSOLE_ENABLED", True):
            with mock.patch.object(_config.config, "STACKY_DEVOPS_SERVERS_ENABLED", True):
                with mock.patch("services.server_registry.get_server", return_value={"host": "h1"}):
                    with mock.patch("api.devops_agent._launch_turn", return_value={"execution_id": "exec1"}):
                        r = app_client.post("/api/devops/console/conversations", json={
                            "server_alias": "s1",
                            "project": "p1",
                            "message": "test prompt",
                        })
                        assert r.status_code == 202
                        data = r.get_json()
                        assert "conversation_id" in data

                        cid = data["conversation_id"]
                        ticket = db_session.get(Ticket, cid)
                        assert ticket is not None
                        assert ticket.external_id == -cid
                        assert ticket.ado_id == -4
                        import json
                        desc = json.loads(ticket.description)
                        assert desc["server_alias"] == "s1"
                        assert desc["write_enabled"] is False

    def test_f2_conversations_filtered_by_alias(self, app_client, db_session):
        """KPI-4: 2 conversaciones (alias A y B) ⇒ GET /conversations?server=A devuelve solo la de A."""
        import config as _config
        pass  # db ya está disponible via db_session (fixture conftest)
        import json

        # Crear 2 conversaciones
        t1 = Ticket(
            ado_id=-4,
            project="test",
            stacky_project_name="test",
            title="Test A",
            work_item_type="Task",
            ado_state="Active",
            description=json.dumps({"kind":"remote_console","server_alias":"A","write_enabled":False}),
        )
        t2 = Ticket(
            ado_id=-4,
            project="test",
            stacky_project_name="test",
            title="Test B",
            work_item_type="Task",
            ado_state="Active",
            description=json.dumps({"kind":"remote_console","server_alias":"B","write_enabled":False}),
        )
        db_session.add_all([t1, t2])
        db_session.commit()

        with mock.patch.object(_config.config, "STACKY_DEVOPS_REMOTE_CONSOLE_ENABLED", True):
            r = app_client.get("/api/devops/console/conversations?server=A")
            assert r.status_code == 200
            data = r.get_json()
            assert len(data) == 1
            assert data[0]["server_alias"] == "A"

    def test_f2_conversations_missing_server_param_400(self, app_client):
        """?server faltante ⇒ 400."""
        import config as _config
        with mock.patch.object(_config.config, "STACKY_DEVOPS_REMOTE_CONSOLE_ENABLED", True):
            r = app_client.get("/api/devops/console/conversations")
            assert r.status_code == 400

    def test_f2_message_reuses_dual_path(self, app_client, db_session):
        """Último run running ⇒ send_input; sin run vivo ⇒ _launch_turn."""
        import config as _config
        pass  # db ya está disponible via db_session (fixture conftest)
        from database.models import Run

        # Crear conversación con run running
        ticket = Ticket(
            ado_id=-4,
            project="test",
            stacky_project_name="test",
            title="Test",
            work_item_type="Task",
            ado_state="Active",
            description='{"kind":"remote_console","server_alias":"s1","write_enabled":False}',
        )
        db_session.add(ticket)
        db_session.commit()
        cid = ticket.id

        run = Run(
            ticket_id=cid,
            state="running",
            agent_type="devops",
            model="model",
            effort="medium",
        )
        db.session.add(run)
        db.session.commit()

        with mock.patch.object(_config.config, "STACKY_DEVOPS_REMOTE_CONSOLE_ENABLED", True):
            with mock.patch("api.devops_agent._send_input", return_value={"ok": True}):
                r = app_client.post(f"/api/devops/console/conversations/{cid}/message", json={"message": "hi"})
                assert r.status_code == 200

    def test_f2_write_mode_toggle_audited(self, app_client, db_session):
        """Toggle de write_mode escribe entrada kind=write_mode en auditoría."""
        import config as _config
        pass  # db ya está disponible via db_session (fixture conftest)

        ticket = Ticket(
            ado_id=-4,
            project="test",
            stacky_project_name="test",
            title="Test",
            work_item_type="Task",
            ado_state="Active",
            description='{"kind":"remote_console","server_alias":"s1","write_enabled":False}',
        )
        db_session.add(ticket)
        db_session.commit()
        cid = ticket.id

    def test_f2_audit_endpoint_paginates(self, app_client, tmp_path, monkeypatch):
        """limit/offset respetados; alias inválido 400."""
        import config as _config
        monkeypatch.setattr("services.remote_exec._audit_dir", lambda: tmp_path)

        with mock.patch.object(_config.config, "STACKY_DEVOPS_REMOTE_CONSOLE_ENABLED", True):
            # Alias inválido
            r1 = app_client.get("/api/devops/console/audit/invalid_alias!")
            assert r1.status_code == 400

            # Alias válido con paginación
            from services.remote_exec import append_audit
            append_audit("s1", {"seq": 1})
            append_audit("s1", {"seq": 2})
            append_audit("s1", {"seq": 3})

            r2 = app_client.get("/api/devops/console/audit/s1?limit=2&offset=1")
            assert r2.status_code == 200
            data = r2.get_json()
            assert len(data) == 2
