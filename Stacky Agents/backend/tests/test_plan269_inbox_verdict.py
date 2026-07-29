"""Plan 269 F5 — El veredicto en la fila de la bandeja de incidencias.

TOCA LA DB (sqlite en memoria) => correr POR ARCHIVO.
CERO RED, CERO TRACKER REAL.

7 casos (§5 F5 del plan 269).
"""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

FLAG = "STACKY_INCIDENT_INBOX_VERDICT_ENABLED"
_ADO_MIN, _ADO_MAX = 7100, 7199


@pytest.fixture
def client(monkeypatch):
    import app as app_module

    tmp = tempfile.TemporaryDirectory()
    monkeypatch.setenv("STACKY_REPO_ROOT", tmp.name)
    monkeypatch.setenv("STACKY_OUTPUT_WATCHER_ENABLED", "false")
    monkeypatch.setenv("STACKY_MANIFEST_WATCHER_ENABLED", "false")
    monkeypatch.setattr(app_module, "_startup_sync", lambda logger: None)
    app = app_module.create_app()
    app.config.update(TESTING=True)
    from services.ticket_status import stop_stale_recovery

    stop_stale_recovery()
    with app.test_client() as c:
        yield c
    stop_stale_recovery()
    tmp.cleanup()


def _inbox_project() -> str:
    from services.project_context import resolve_project_context

    ctx = resolve_project_context()
    return (getattr(ctx, "tracker_project", None) if ctx else None) or "TEST"


def _ticket(ado_id, *, stacky_status="error", ado_state="Active", ejecuciones=()):
    """`ejecuciones` = [(status, minutos_atras), ...]. Devuelve (ticket_id, [exec_ids])."""
    from db import session_scope
    from models import AgentExecution, Ticket

    with session_scope() as s:
        t = Ticket(ado_id=ado_id, project=_inbox_project(), stacky_project_name=None,
                   title=f"t-{ado_id}", ado_state=ado_state,
                   stacky_status=stacky_status, tracker_type="azure_devops",
                   work_item_type="Bug")
        s.add(t)
        s.flush()
        ids = []
        for status, minutos in ejecuciones:
            ex = AgentExecution(
                ticket_id=t.id, agent_type="developer", status=status,
                input_context_json="[]", started_by="test",
                started_at=datetime.utcnow() - timedelta(minutes=minutos),
            )
            s.add(ex)
            s.flush()
            ids.append(ex.id)
        return t.id, ids


def _items(client):
    r = client.get("/api/incident-inbox/items?scope=all")
    assert r.status_code == 200, r.get_data(as_text=True)
    data = r.get_json()
    return {
        i["ado_id"]: i for i in data["items"]
        if _ADO_MIN <= (i.get("ado_id") or 0) <= _ADO_MAX
    }


def test_1_flag_off_la_bandeja_es_identica(client, monkeypatch):
    from config import config as cfg

    _ticket(7101, ejecuciones=[("error", 1)])
    con = _items(client)
    monkeypatch.setattr(cfg, FLAG, False)
    sin = _items(client)

    assert 7101 in sin
    assert "run_verdict" not in sin[7101]
    # El resto del payload, clave por clave, es identico.
    for k in sin[7101]:
        assert sin[7101][k] == con[7101][k], f"la flag OFF cambio la clave {k}"


def test_2_flag_on_agrega_verdict_solo_a_los_que_tienen_ejecucion(client):
    _ticket(7102, ejecuciones=[("error", 1)])
    _ticket(7103, ejecuciones=[])            # sin ejecuciones
    items = _items(client)
    assert isinstance(items[7102].get("run_verdict"), dict)
    assert "run_verdict" not in items[7103], "un ticket sin ejecuciones no tiene veredicto"


def test_3_una_sola_query_extra(client):
    """El costo extra no crece con el tamano del lote."""
    from sqlalchemy import event

    from db import engine

    def _contar():
        n = {"q": 0}

        def _hook(conn, cursor, statement, params, context, executemany):
            n["q"] += 1

        event.listen(engine, "before_cursor_execute", _hook)
        try:
            client.get("/api/incident-inbox/items?scope=all")
        finally:
            event.remove(engine, "before_cursor_execute", _hook)
        return n["q"]

    for i in range(3):
        _ticket(7110 + i, ejecuciones=[("error", 1)])
    con_3 = _contar()
    for i in range(27):
        _ticket(7120 + i, ejecuciones=[("error", 1)])
    con_30 = _contar()
    assert con_30 == con_3, (
        f"el costo de queries CRECE con el lote: {con_3} con 3 tickets y {con_30} con 30"
    )


def test_4_lote_acotado_no_trae_el_historico(client):
    """50 ejecuciones de un ticket => _last_execution_by_ticket devuelve 1 objeto."""
    from api.incident_inbox import _last_execution_by_ticket
    from db import session_scope

    tid, _ = _ticket(7190, ejecuciones=[("error", m) for m in range(50)])
    with session_scope() as s:
        out = _last_execution_by_ticket(s, [tid])
    assert len(out) == 1, f"se materializaron {len(out)} filas para 1 ticket"
    assert tid in out


def test_5_ultima_ejecucion_es_la_mas_reciente(client):
    from db import session_scope
    from models import AgentExecution

    from api.incident_inbox import _last_execution_by_ticket

    tid, ids = _ticket(7150, ejecuciones=[("error", 30), ("completed", 10), ("cancelled", 1)])
    with session_scope() as s:
        out = _last_execution_by_ticket(s, [tid])
        assert out[tid].id == ids[-1], "no gano la de started_at mayor"

    # Empate exacto de started_at: gana el id mayor (determinista).
    momento = datetime.utcnow()
    with session_scope() as s:
        from models import Ticket

        t = s.query(Ticket).filter(Ticket.ado_id == 7150).first()
        a = AgentExecution(ticket_id=t.id, agent_type="developer", status="error",
                           input_context_json="[]", started_by="test",
                           started_at=momento + timedelta(days=1))
        b = AgentExecution(ticket_id=t.id, agent_type="developer", status="completed",
                           input_context_json="[]", started_by="test",
                           started_at=momento + timedelta(days=1))
        s.add(a)
        s.add(b)
        s.flush()
        mayor = max(a.id, b.id)
    with session_scope() as s:
        out = _last_execution_by_ticket(s, [tid])
        assert out[tid].id == mayor, "el empate no se resolvio por id mayor"


def test_6_excepcion_en_el_veredicto_no_rompe_la_bandeja(client, monkeypatch):
    """Sin el logger declarado en el paso 1, esto daria 500 en vez de 200."""
    from services import run_verdict as rv

    _ticket(7160, ejecuciones=[("error", 1)])

    def _boom(**kwargs):
        raise RuntimeError("veredicto roto")

    monkeypatch.setattr(rv, "evaluate_verdict", _boom)
    r = client.get("/api/incident-inbox/items?scope=all")
    assert r.status_code == 200, "la bandeja devolvio un error en vez de degradar"
    items = _items(client)
    assert 7160 in items, "los items se perdieron"
    assert "run_verdict" not in items[7160]


def test_7_no_se_agregan_estados_al_ticket(client, monkeypatch):
    from config import config as cfg

    _ticket(7170, stacky_status="completed", ejecuciones=[("error", 1)])
    con = _items(client)
    monkeypatch.setattr(cfg, FLAG, False)
    sin = _items(client)
    assert con[7170]["stacky_status"] == sin[7170]["stacky_status"]
    # Y el veredicto es una DIMENSION separada: no es un estado.
    from services.run_verdict import VERDICT_LEVELS

    assert con[7170]["stacky_status"] not in VERDICT_LEVELS
