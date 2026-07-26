"""Plan 208 F6 — Observabilidad: SystemLog de transiciones y de auto-sync.

Sin tablas nuevas: reusa SystemLog. C6 — el `source` logueado sale del PLAN
(="matrix"), nunca del dict de `_safe_transition` (que lo hardcodea a "config").
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

_PROJECT = "RSPacifico"
_ADO_ID = 99500


class FakeProvider:
    name = "azure_devops"

    def __init__(self, current="In Progress"):
        self.current = current
        self.updates: list = []

    def get_item(self, item_id):
        return {"fields": {"System.State": self.current}}

    def update_item_state(self, item_id, state):
        self.updates.append((str(item_id), state))
        self.current = state
        return {"ok": True}


@pytest.fixture(autouse=True)
def _clean():
    from db import init_db, session_scope
    from models import SystemLog
    from services import completion_sync as cs

    init_db()
    with session_scope() as s:
        s.query(SystemLog).filter(SystemLog.source == "completion_dispatcher").delete()
    cs._last_sync_ts.clear()
    cs._pending.clear()
    yield
    cs._last_sync_ts.clear()
    cs._pending.clear()


def _logs(action: str) -> list[dict]:
    from db import session_scope
    from models import SystemLog

    with session_scope() as s:
        rows = (
            s.query(SystemLog)
            .filter(SystemLog.action == action)
            .order_by(SystemLog.id.asc())
            .all()
        )
        return [
            {
                "level": r.level,
                "source": r.source,
                "ticket_id": r.ticket_id,
                "execution_id": r.execution_id,
                "context": json.loads(r.context_json or "{}"),
                "tags": json.loads(r.tags_json or "[]"),
            }
            for r in rows
        ]


@pytest.fixture
def ticket_id():
    from db import session_scope
    from models import Ticket

    with session_scope() as s:
        t = Ticket(ado_id=_ADO_ID, project="Strategist_Pacifico",
                   stacky_project_name=_PROJECT, tracker_type="azure_devops",
                   title="obs", work_item_type="Task", stacky_status="running")
        s.add(t)
        s.flush()
        tid = t.id
    yield tid
    with session_scope() as s:
        row = s.get(Ticket, tid)
        if row is not None:
            s.delete(row)


def test_transicion_aplicada_emite_system_log(ticket_id, monkeypatch):
    profile = {
        "tracker_state_machine": {
            "developer": {
                "input_states": ["Ready for Dev"],
                "in_progress": "In Progress",
                "next_state_ok": "Code Review",
                "by_work_item_type": {"Task": {"next_state_ok": "Ready for QA"}},
            }
        }
    }
    monkeypatch.setattr("services.client_profile.load_effective_client_profile",
                        lambda project: profile, raising=True)
    monkeypatch.setattr("services.tracker_provider.get_tracker_provider",
                        lambda project=None: FakeProvider(), raising=True)

    from services.completion_state import maybe_apply_state_transition

    res = maybe_apply_state_transition(
        {"ticket_id": ticket_id, "execution_id": 77, "final_status": "completed",
         "agent_type": "developer"}
    )
    assert res.get("ok") is True, res

    rows = _logs("completion.matrix_transition")
    assert len(rows) == 1, rows
    row = rows[0]
    assert row["level"] == "INFO"
    assert row["ticket_id"] == ticket_id
    assert row["execution_id"] == 77
    assert row["tags"] == ["plan208", "matrix"]
    ctx = row["context"]
    assert ctx["result"] == "ok"
    assert ctx["source"] == "matrix", (
        "C6: el source es el del PLAN, no el 'config' hardcodeado de _safe_transition"
    )
    assert ctx["to"] == "Ready for QA"
    assert ctx["work_item_type"] == "Task"
    assert ctx["agent_type"] == "developer"
    assert ctx["ado_id"] == _ADO_ID
    assert ctx["project"] == _PROJECT


def test_skip_por_guardia_humana_queda_trazado(ticket_id, monkeypatch):
    profile = {
        "tracker_state_machine": {
            "developer": {
                "input_states": ["Ready for Dev"],
                "in_progress": "In Progress",
                "next_state_ok": "Code Review",
                "by_work_item_type": {"Task": {"next_state_ok": "Ready for QA"}},
            }
        }
    }
    monkeypatch.setattr("services.client_profile.load_effective_client_profile",
                        lambda project: profile, raising=True)
    monkeypatch.setattr("services.tracker_provider.get_tracker_provider",
                        lambda project=None: FakeProvider(current="On Hold"), raising=True)

    from services.completion_state import maybe_apply_state_transition

    maybe_apply_state_transition(
        {"ticket_id": ticket_id, "execution_id": 78, "final_status": "completed",
         "agent_type": "developer"}
    )

    rows = _logs("completion.matrix_transition")
    assert len(rows) == 1
    assert rows[0]["context"]["result"] == "skipped"
    assert rows[0]["context"]["reason"] == "human_moved_out_of_flow"


def test_auto_sync_emite_system_log(ticket_id, monkeypatch):
    from services import ado_sync, completion_sync as cs, integration_breaker as brk, project_context

    monkeypatch.setattr(brk, "should_skip", lambda integ, proj: False, raising=True)
    monkeypatch.setattr(brk, "record_success", lambda integ, proj: None, raising=True)
    monkeypatch.setattr(project_context, "build_ado_client", lambda **kw: object(), raising=True)
    monkeypatch.setattr(ado_sync, "upsert_single_work_item", lambda c, i: {}, raising=True)
    monkeypatch.setattr(
        ado_sync, "sync_tickets",
        lambda **kw: {"project": _PROJECT, "fetched": 4, "created": 1, "updated": 2, "removed": 0},
        raising=True,
    )

    cs.maybe_coalesced_sync(
        {"ticket_id": ticket_id, "execution_id": 79, "final_status": "completed",
         "agent_type": "developer"}
    )

    rows = _logs("completion.auto_sync")
    assert len(rows) == 1, rows
    ctx = rows[0]["context"]
    assert rows[0]["tags"] == ["plan208", "auto_sync"]
    assert ctx["project"] == _PROJECT
    assert ctx["tracker_type"] == "azure_devops"
    assert (ctx["fetched"], ctx["created"], ctx["updated"], ctx["removed"]) == (4, 1, 2, 0)
    assert ctx["breaker_open"] is False
    assert ctx["error"] is None


def test_sync_fallido_loguea_warning(ticket_id, monkeypatch):
    from services import ado_sync, completion_sync as cs, integration_breaker as brk, project_context

    monkeypatch.setattr(brk, "should_skip", lambda integ, proj: False, raising=True)
    monkeypatch.setattr(brk, "record_failure", lambda *a, **kw: None, raising=True)
    monkeypatch.setattr(project_context, "build_ado_client", lambda **kw: object(), raising=True)
    monkeypatch.setattr(ado_sync, "upsert_single_work_item", lambda c, i: {}, raising=True)

    def _boom(**kw):
        raise RuntimeError("ADO 503")

    monkeypatch.setattr(ado_sync, "sync_tickets", _boom, raising=True)

    cs.maybe_coalesced_sync(
        {"ticket_id": ticket_id, "execution_id": 80, "final_status": "completed",
         "agent_type": "developer"}
    )

    rows = _logs("completion.auto_sync")
    assert len(rows) == 1
    assert rows[0]["level"] == "WARNING"
    assert "ADO 503" in (rows[0]["context"]["error"] or "")
