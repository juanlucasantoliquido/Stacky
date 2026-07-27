"""Plan 254 F5 — reconciliación post-cierre: el falso ROJO, MEDIDO.

F1-F4 CREEN haber arreglado el falso rojo. Nada en el sistema lo PRUEBA. Sin un
número, dentro de dos semanas nadie sabe si el bug volvió por otro camino.

`services/run_reconciliation.py` compara, para cada run terminado, el estado del
ticket contra la evidencia objetiva del run, y LISTA las discrepancias.
READ-ONLY absoluto: no cambia ni un estado, no reintenta, no publica. El
operador decide qué hacer con cada línea (human-in-the-loop).
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


@pytest.fixture()
def db(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    from app import create_app  # noqa: F401
    from db import init_db

    create_app()
    init_db()
    yield


def _ev(**kw):
    from services.run_reconciliation import RunEvidence

    base = dict(
        execution_id=1,
        ticket_id=1,
        ticket_status="completed",
        return_code=0,
        result_ok_seen=True,
        outcome_reason="clean_exit",
        self_reported_completed=False,
        blocked_downgrade=False,
        drain_timed_out=False,
    )
    base.update(kw)
    return RunEvidence(**base)


def _kinds(discrepancies) -> set[str]:
    return {d.kind for d in discrepancies}


# ── evaluate() — función PURA, sin base ───────────────────────────────────────


def test_red_with_delivered_work_se_detecta():
    """EL contador del falso ROJO: ticket en 'error' con trabajo entregado."""
    from services.run_reconciliation import evaluate

    d = evaluate(_ev(ticket_status="error", return_code=1, result_ok_seen=True,
                     outcome_reason="dirty_exit_after_work"))
    assert "red_with_delivered_work" in _kinds(d)
    # También cuenta el rc==0 con ticket en error.
    d2 = evaluate(_ev(ticket_status="error", return_code=0, result_ok_seen=False,
                      outcome_reason="clean_exit"))
    assert "red_with_delivered_work" in _kinds(d2)


def test_run_sano_no_produce_discrepancias():
    """Control negativo OBLIGATORIO: sin esto, una función que siempre devuelve
    una discrepancia pasaría el test anterior."""
    from services.run_reconciliation import evaluate

    assert evaluate(_ev()) == []


def test_green_with_dirty_close_se_detecta():
    """El caso de F1-bis: verde preservado sobre un cierre sucio, sin revisar."""
    from services.run_reconciliation import evaluate

    d = evaluate(_ev(ticket_status="completed", return_code=1, result_ok_seen=True,
                     blocked_downgrade=True, outcome_reason="dirty_exit_after_work"))
    assert "green_with_dirty_close" in _kinds(d)


def test_green_self_reported_only_se_detecta():
    """'completed' solo por auto-reporte, rc!=0 y sin result ok."""
    from services.run_reconciliation import evaluate

    d = evaluate(_ev(ticket_status="completed", return_code=1, result_ok_seen=False,
                     self_reported_completed=True, outcome_reason="cli_failure"))
    assert "green_self_reported_only" in _kinds(d)
    # Con result ok NO es una discrepancia: hay evidencia objetiva de trabajo.
    d2 = evaluate(_ev(ticket_status="completed", return_code=1, result_ok_seen=True,
                      self_reported_completed=True,
                      outcome_reason="dirty_exit_after_work"))
    assert "green_self_reported_only" not in _kinds(d2)


def test_unclassified_outcome_se_detecta():
    """Run terminado sin outcome_reason → F2 no está cableada en ese camino."""
    from services.run_reconciliation import evaluate

    d = evaluate(_ev(outcome_reason=None))
    assert "unclassified_outcome" in _kinds(d)


def test_drain_timeout_se_detecta():
    from services.run_reconciliation import DISCREPANCY_KINDS, evaluate

    d = evaluate(_ev(drain_timed_out=True))
    assert "drain_timeout" in _kinds(d)
    # Ningún kind inventado fuera del vocabulario declarado.
    assert _kinds(d) <= set(DISCREPANCY_KINDS)


def test_evaluate_es_pura_y_no_toca_la_base():
    """Llamar `evaluate` sin session_scope activo no lanza."""
    from services.run_reconciliation import evaluate

    for _ in range(3):
        assert isinstance(evaluate(_ev(ticket_status="error", result_ok_seen=True)), list)


# ── scan_recent() — lee la base, NO la escribe ────────────────────────────────


_ADO_SEQ = [254_900]


def _seed_run(*, ticket_status: str, exec_status: str, metadata: dict) -> tuple[int, int]:
    """El discriminador real de un ticket es (ado_id, project): ado_id ÚNICO por
    seed o el startup sync revienta por la constraint de external_id."""
    from db import session_scope
    from models import AgentExecution, Ticket

    _ADO_SEQ[0] += 1
    with session_scope() as session:
        t = Ticket(ado_id=_ADO_SEQ[0],
                   project="PLAN254F5", title="fixture reconciliación",
                   ado_state="Active", stacky_status=ticket_status)
        session.add(t)
        session.flush()
        ex = AgentExecution(ticket_id=t.id, agent_type="developer",
                            status=exec_status, started_by="system")
        ex.input_context = []
        ex.metadata_dict = metadata
        session.add(ex)
        session.flush()
        return t.id, ex.id


def test_scan_recent_detecta_el_falso_rojo_en_la_base(db):
    from services.run_reconciliation import scan_recent

    _seed_run(ticket_status="error", exec_status="error",
              metadata={"outcome_reason": "dirty_exit_after_work", "exit_code": 1,
                        "finalized_after_result": {"reason": "stall_or_oneshot_close"}})
    hits = scan_recent(limit=50)
    assert "red_with_delivered_work" in {d.kind for d in hits}


def test_scan_recent_es_read_only(db):
    """Blinda el riel 'no cambia nada': ni una fila escrita, ni un estado tocado."""
    from db import session_scope
    from models import AgentExecution, Ticket
    from services.run_reconciliation import scan_recent
    from services.ticket_status import TicketStatusEvent

    _seed_run(ticket_status="error", exec_status="error",
              metadata={"outcome_reason": "dirty_exit_after_work", "exit_code": 1,
                        "finalized_after_result": {"reason": "x"}})

    def _snapshot():
        with session_scope() as session:
            return (
                session.query(TicketStatusEvent).count(),
                session.query(AgentExecution).count(),
                sorted((t.id, t.stacky_status) for t in session.query(Ticket).all()),
            )

    antes = _snapshot()
    scan_recent(limit=200)
    scan_recent(limit=200)
    assert _snapshot() == antes, "scan_recent escribió en la base"


# ── endpoint ──────────────────────────────────────────────────────────────────


def test_endpoint_run_reconciliation_responde_200(db):
    from app import create_app

    app = create_app()
    client = app.test_client()
    resp = client.get("/api/diag/run-reconciliation")
    assert resp.status_code == 200
    body = resp.get_json()
    assert set(("total", "by_kind", "items")) <= set(body)
    assert isinstance(body["total"], int)
    assert isinstance(body["by_kind"], dict)
    assert isinstance(body["items"], list)
    # `red_with_delivered_work` es LITERALMENTE el contador del falso rojo:
    # tiene que existir siempre, aunque valga 0.
    assert "red_with_delivered_work" in body["by_kind"]
