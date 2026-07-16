"""Tests del wiring del preflight de confianza en _run_pre_run_checks
(Plan 144 F2/F3, cierra D1). Monkeypatch de `config` y `claude_workspace_trust`
— no toca el ~/.claude.json real ni corre git de verdad."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")


@pytest.fixture()
def db(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    from app import create_app  # noqa: F401 — fuerza el wiring de la app/DB
    from db import init_db

    create_app()
    init_db()
    yield


def _new_ticket_and_exec(**kw):
    from datetime import datetime

    from db import session_scope
    from models import AgentExecution, Ticket

    with session_scope() as session:
        t = Ticket(
            ado_id=kw.pop("ado_id", 9201),
            project="X",
            title="plan 144 F2 fixture",
            ado_state="Active",
            stacky_status="running",
        )
        session.add(t)
        session.flush()
        ticket_id = t.id
        ex = AgentExecution(
            ticket_id=ticket_id,
            agent_type="developer",
            status="running",
            input_context_json="[]",
            started_by="test",
            started_at=datetime.utcnow(),
        )
        session.add(ex)
        session.flush()
        execution_id = ex.id
    return ticket_id, execution_id


def _stub_pull_check_ok(monkeypatch):
    """Evita correr git real: run_pull_check siempre ok, sin warnings/errors."""
    from services import pre_run_git

    class _StubResult:
        ok = True
        warnings: list[str] = []
        errors: list[str] = []

        def to_dict(self):
            return {"ok": True, "warnings": [], "errors": []}

    monkeypatch.setattr(pre_run_git, "run_pull_check", lambda *a, **kw: _StubResult())


def test_preflight_off_skips(db, monkeypatch):
    from config import config
    from services import claude_code_cli_runner, claude_workspace_trust

    _stub_pull_check_ok(monkeypatch)
    monkeypatch.setattr(config, "CLAUDE_CODE_CLI_TRUST_PREFLIGHT_ENABLED", False)

    calls: list[str] = []
    monkeypatch.setattr(
        claude_workspace_trust, "read_workspace_trust",
        lambda *a, **kw: calls.append("called"),
    )

    ticket_id, execution_id = _new_ticket_and_exec(ado_id=9201)
    ok = claude_code_cli_runner._run_pre_run_checks(
        execution_id, str(ROOT), ticket_id, "developer",
    )
    assert ok is True
    assert calls == [], "preflight OFF no debe llamar a read_workspace_trust"


def test_untrusted_autoset_off_fails_early(db, monkeypatch):
    from config import config
    from services import claude_code_cli_runner, claude_workspace_trust, ticket_status
    from services.claude_workspace_trust import WorkspaceTrust

    _stub_pull_check_ok(monkeypatch)
    monkeypatch.setattr(config, "CLAUDE_CODE_CLI_TRUST_PREFLIGHT_ENABLED", True)
    monkeypatch.setattr(config, "CLAUDE_CODE_CLI_TRUST_AUTOSET_ENABLED", False)

    untrusted = WorkspaceTrust(
        trusted=False, present=False, config_path="C:/fake/.claude.json",
        project_key="C:/fake/ws", error=None,
    )
    monkeypatch.setattr(claude_workspace_trust, "read_workspace_trust", lambda *a, **kw: untrusted)

    ticket_id, execution_id = _new_ticket_and_exec(ado_id=9202)
    ok = claude_code_cli_runner._run_pre_run_checks(
        execution_id, str(ROOT), ticket_id, "developer",
    )
    assert ok is False

    from db import session_scope
    from models import AgentExecution

    with session_scope() as session:
        row = session.get(AgentExecution, execution_id)
        assert row.status == "error"
        assert "no está confiado" in (row.error_message or "")
        assert "hasTrustDialogAccepted" in (row.error_message or "")

    assert ticket_status.get_current_status(ticket_id) == "error"


def test_untrusted_autoset_on_proceeds(db, monkeypatch):
    from config import config
    from services import claude_code_cli_runner, claude_workspace_trust
    from services.claude_workspace_trust import WorkspaceTrust

    _stub_pull_check_ok(monkeypatch)
    monkeypatch.setattr(config, "CLAUDE_CODE_CLI_TRUST_PREFLIGHT_ENABLED", True)
    monkeypatch.setattr(config, "CLAUDE_CODE_CLI_TRUST_AUTOSET_ENABLED", True)

    untrusted = WorkspaceTrust(
        trusted=False, present=False, config_path="C:/fake/.claude.json",
        project_key="C:/fake/ws", error=None,
    )
    trusted_after = WorkspaceTrust(
        trusted=True, present=True, config_path="C:/fake/.claude.json",
        project_key="C:/fake/ws", error=None,
    )
    monkeypatch.setattr(claude_workspace_trust, "read_workspace_trust", lambda *a, **kw: untrusted)
    set_calls: list[str] = []

    def _fake_set(workspace_root, **kw):
        set_calls.append(workspace_root)
        return trusted_after

    monkeypatch.setattr(claude_workspace_trust, "set_workspace_trusted", _fake_set)

    ticket_id, execution_id = _new_ticket_and_exec(ado_id=9203)
    ok = claude_code_cli_runner._run_pre_run_checks(
        execution_id, str(ROOT), ticket_id, "developer",
    )
    assert ok is True
    assert len(set_calls) == 1


def test_trusted_proceeds(db, monkeypatch):
    from config import config
    from services import claude_code_cli_runner, claude_workspace_trust
    from services.claude_workspace_trust import WorkspaceTrust

    _stub_pull_check_ok(monkeypatch)
    monkeypatch.setattr(config, "CLAUDE_CODE_CLI_TRUST_PREFLIGHT_ENABLED", True)
    monkeypatch.setattr(config, "CLAUDE_CODE_CLI_TRUST_AUTOSET_ENABLED", False)

    trusted = WorkspaceTrust(
        trusted=True, present=True, config_path="C:/fake/.claude.json",
        project_key="C:/fake/ws", error=None,
    )
    set_calls: list[str] = []
    monkeypatch.setattr(claude_workspace_trust, "read_workspace_trust", lambda *a, **kw: trusted)
    monkeypatch.setattr(
        claude_workspace_trust, "set_workspace_trusted",
        lambda *a, **kw: set_calls.append("called"),
    )

    ticket_id, execution_id = _new_ticket_and_exec(ado_id=9204)
    ok = claude_code_cli_runner._run_pre_run_checks(
        execution_id, str(ROOT), ticket_id, "developer",
    )
    assert ok is True
    assert set_calls == [], "trusted=True no debe invocar set_workspace_trusted"
