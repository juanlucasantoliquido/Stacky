"""Plan 208 F3 — Auto-sync best-effort, no bloqueante, coalescido, con breaker.

Cubre: flag off; breaker abierto; coalescing (N eventos ⇒ 1 sync); despacho
multi-tracker (ADO/Jira/Mantis); upsert puntual; fallo que registra el breaker
sin propagar.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

_PROJECT = "RSPacifico"


class Spy:
    def __init__(self, result=None, raises=None):
        self.calls: list[tuple] = []
        self.result = result if result is not None else {
            "project": _PROJECT, "fetched": 1, "created": 0,
            "updated": 1, "removed": 0, "synced_at": "now",
        }
        self.raises = raises

    def __call__(self, *a, **kw):
        self.calls.append((a, kw))
        if self.raises:
            raise self.raises
        return self.result


@pytest.fixture(autouse=True)
def _clean_state():
    from db import init_db
    from services import completion_sync as cs

    init_db()
    cs._last_sync_ts.clear()
    cs._pending.clear()
    yield
    cs._last_sync_ts.clear()
    cs._pending.clear()


@pytest.fixture
def mk_ticket():
    created: list[int] = []

    def _mk(ado_id: int = 99300, tracker_type: str = "azure_devops",
            stacky_project: str | None = _PROJECT):
        from db import session_scope
        from models import Ticket

        with session_scope() as s:
            t = Ticket(ado_id=ado_id, project="Strategist_Pacifico",
                       stacky_project_name=stacky_project, tracker_type=tracker_type,
                       title=f"t{ado_id}", work_item_type="Task", stacky_status="running")
            s.add(t)
            s.flush()
            created.append(t.id)
            return t.id

    yield _mk
    from db import session_scope
    from models import Ticket

    with session_scope() as s:
        for tid in created:
            row = s.get(Ticket, tid)
            if row is not None:
                s.delete(row)


@pytest.fixture
def breaker_open_off(monkeypatch):
    from services import integration_breaker as brk

    monkeypatch.setattr(brk, "should_skip", lambda integ, proj: False, raising=True)
    monkeypatch.setattr(brk, "record_success", lambda integ, proj: None, raising=True)


def _ev(tid: int) -> dict:
    return {"ticket_id": tid, "execution_id": 1, "final_status": "completed",
            "agent_type": "developer"}


def test_flag_off_no_sync(monkeypatch, mk_ticket):
    from config import config as cfg
    from services import ado_sync, completion_sync as cs

    spy = Spy()
    monkeypatch.setattr(ado_sync, "sync_tickets", spy, raising=True)
    monkeypatch.setattr(cfg, "STACKY_ADO_SYNC_ON_COMPLETION_ENABLED", False, raising=False)

    cs.maybe_coalesced_sync(_ev(mk_ticket()))

    assert spy.calls == [], "con la flag OFF no se toca el tracker"


def test_breaker_abierto_skip(monkeypatch, mk_ticket):
    from services import ado_sync, completion_sync as cs, integration_breaker as brk

    spy = Spy()
    monkeypatch.setattr(ado_sync, "sync_tickets", spy, raising=True)
    monkeypatch.setattr(brk, "should_skip", lambda integ, proj: True, raising=True)

    cs.maybe_coalesced_sync(_ev(mk_ticket()))

    assert spy.calls == [], "breaker abierto ⇒ no se golpea la red"


def test_coalescing_una_sola_llamada(monkeypatch, mk_ticket, breaker_open_off):
    from services import ado_sync, completion_sync as cs, project_context

    spy = Spy()
    monkeypatch.setattr(ado_sync, "sync_tickets", spy, raising=True)
    monkeypatch.setattr(ado_sync, "upsert_single_work_item", Spy(result={}), raising=True)
    monkeypatch.setattr(project_context, "build_ado_client",
                        lambda **kw: object(), raising=True)

    tid = mk_ticket()
    for _ in range(5):
        cs.maybe_coalesced_sync(_ev(tid))

    assert len(spy.calls) == 1, f"5 eventos en la ventana ⇒ 1 sync, hubo {len(spy.calls)}"
    assert cs._pending.get(_PROJECT) is not None, "los 4 restantes quedan pendientes de flush"

    cs.flush_pending_syncs()
    assert len(spy.calls) == 2, "el flush drena 1 sync más por proyecto (no 4)"
    assert cs._pending == {}


def test_upsert_single_se_invoca_para_ado(monkeypatch, mk_ticket, breaker_open_off):
    from services import ado_sync, completion_sync as cs, project_context

    sync_spy, upsert_spy = Spy(), Spy(result={})
    client = object()
    monkeypatch.setattr(ado_sync, "sync_tickets", sync_spy, raising=True)
    monkeypatch.setattr(ado_sync, "upsert_single_work_item", upsert_spy, raising=True)
    monkeypatch.setattr(project_context, "build_ado_client", lambda **kw: client, raising=True)

    cs.maybe_coalesced_sync(_ev(mk_ticket(ado_id=99301)))

    assert len(upsert_spy.calls) == 1
    assert upsert_spy.calls[0][0] == (client, 99301), "upsert puntual con el client y el ado_id"
    assert sync_spy.calls[0][1]["project_name"] == _PROJECT


def test_multitracker_despacha_jira(monkeypatch, mk_ticket, breaker_open_off):
    from services import ado_sync, completion_sync as cs, jira_sync
    import project_manager

    jira_spy, ado_spy = Spy(), Spy()
    tracker_cfg = {"type": "jira", "project": "PROJ", "url": "https://x"}
    monkeypatch.setattr(jira_sync, "sync_tickets", jira_spy, raising=True)
    monkeypatch.setattr(ado_sync, "sync_tickets", ado_spy, raising=True)
    monkeypatch.setattr(project_manager, "get_project_config",
                        lambda name: {"issue_tracker": tracker_cfg}, raising=True)

    cs.maybe_coalesced_sync(_ev(mk_ticket(ado_id=99302, tracker_type="jira")))

    assert ado_spy.calls == [], "un ticket Jira NO debe sincronizar por ADO"
    assert len(jira_spy.calls) == 1
    assert jira_spy.calls[0][1] == {"tracker_config": tracker_cfg}, (
        "jira_sync.sync_tickets NO acepta project_name: se le pasa tracker_config"
    )


def test_multitracker_despacha_mantis(monkeypatch, mk_ticket, breaker_open_off):
    from services import completion_sync as cs, mantis_sync
    import project_manager

    spy = Spy()
    tracker_cfg = {"type": "mantis", "url": "https://m", "project_id": "7"}
    monkeypatch.setattr(mantis_sync, "sync_tickets", spy, raising=True)
    monkeypatch.setattr(project_manager, "get_project_config",
                        lambda name: {"issue_tracker": tracker_cfg}, raising=True)

    cs.maybe_coalesced_sync(_ev(mk_ticket(ado_id=99303, tracker_type="mantis")))

    assert len(spy.calls) == 1
    assert spy.calls[0][1] == {"tracker_config": tracker_cfg}


def test_falla_registra_breaker_no_propaga(monkeypatch, mk_ticket):
    from services import ado_sync, completion_sync as cs, integration_breaker as brk, project_context

    failures: list[tuple] = []
    monkeypatch.setattr(brk, "should_skip", lambda integ, proj: False, raising=True)
    monkeypatch.setattr(brk, "record_failure",
                        lambda integ, proj, reason, msg: failures.append((integ, proj, reason)),
                        raising=True)
    monkeypatch.setattr(ado_sync, "sync_tickets", Spy(raises=RuntimeError("ADO caído")), raising=True)
    monkeypatch.setattr(ado_sync, "upsert_single_work_item", Spy(result={}), raising=True)
    monkeypatch.setattr(project_context, "build_ado_client", lambda **kw: object(), raising=True)

    cs.maybe_coalesced_sync(_ev(mk_ticket(ado_id=99304)))  # no debe lanzar

    assert len(failures) == 1, "un fallo de red debe registrarse en el breaker"
    assert failures[0][0] == "ado_sync"
    assert _PROJECT not in cs._last_sync_ts, "un sync fallido no debe sellar la ventana"


def test_sin_stacky_project_no_sync(monkeypatch, mk_ticket, breaker_open_off):
    from services import ado_sync, completion_sync as cs

    spy = Spy()
    monkeypatch.setattr(ado_sync, "sync_tickets", spy, raising=True)

    cs.maybe_coalesced_sync(_ev(mk_ticket(ado_id=99305, stacky_project=None)))

    assert spy.calls == [], "sin stacky_project_name no hay key canónica: skip"


def test_breaker_key_es_la_canonica(monkeypatch, mk_ticket):
    """La key debe salir de ado_breaker_project (misma que _startup_sync y el sync manual)."""
    from services import completion_sync as cs, integration_breaker as brk

    seen: list = []
    monkeypatch.setattr(brk, "should_skip",
                        lambda integ, proj: (seen.append((integ, proj)), True)[1], raising=True)

    cs.maybe_coalesced_sync(_ev(mk_ticket(ado_id=99306)))

    assert seen == [("ado_sync", brk.ado_breaker_project(_PROJECT))]


def test_coalesce_window_es_30s():
    from services import completion_sync as cs

    assert cs._COALESCE_WINDOW_SEC == 30
    assert cs.coalesce_window_sec() == 30.0
