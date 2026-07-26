"""Plan 199 F1 — Backfill idempotente de la telemetría cosechada.

Una ejecución vieja que quedó sin costo no aparece en el Centro de Costos. El
artefacto del CLI en disco sabe lo que gastó: esto los ata por session_id y
rellena la metadata con las MISMAS claves que el extractor ya lee, así el
tablero la clasifica sin cambiarle una línea.

Lo reportado en vivo siempre gana: pisarlo con una estimación de disco sería
degradar un dato bueno.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

from services import telemetry_harvest as H  # noqa: E402


@pytest.fixture
def ticket():
    from db import init_db, session_scope
    from models import AgentExecution, Ticket

    init_db()
    with session_scope() as session:
        session.query(AgentExecution).delete()
        session.query(Ticket).delete()
        t = Ticket(ado_id=19910, project="RSPacifico", title="t",
                   ado_state="To Do", stacky_status="idle")
        session.add(t)
        session.flush()
        return t.id


def _ejecucion(ticket_id: int, md: dict) -> int:
    from db import session_scope
    from models import AgentExecution

    with session_scope() as session:
        ex = AgentExecution(
            ticket_id=ticket_id, agent_type="developer", status="completed",
            input_context_json="{}", started_by="test",
            started_at=datetime.utcnow() - timedelta(hours=1),
            metadata_json=json.dumps(md),
        )
        session.add(ex)
        session.flush()
        return ex.id


def _md(exec_id: int) -> dict:
    from db import session_scope
    from models import AgentExecution

    with session_scope() as session:
        return dict(session.get(AgentExecution, exec_id).metadata_dict or {})


def _run(session_id: str | None, **over) -> H.HarvestedRun:
    base = dict(
        runtime="codex_cli", session_id=session_id, model="gpt-5",
        tokens_in=100, tokens_out=40, cache_read_tokens=0,
        total_cost_usd=None, cost_estimated=False,
        started_at=datetime.utcnow(), project_hint="Stacky", cwd="Stacky",
        artifact="rollout-x.jsonl", source_format="codex_rollout", num_events=3,
    )
    base.update(over)
    return H.HarvestedRun(**base)


def test_backfill_matches_by_codex_session_id(ticket):
    from services.cost_analytics import extract_cost_row

    eid = _ejecucion(ticket, {"runtime": "codex_cli", "codex_session_id": "s1"})

    resumen = H.backfill_from_harvest([_run("s1")], lookback_days=30)

    assert resumen["matched"] == 1 and resumen["backfilled"] == 1
    md = _md(eid)
    assert md["harness_telemetry"]["input_tokens"] == 100
    assert extract_cost_row(md).cost_kind in ("estimated", "reported")


def test_backfill_matches_by_harness_session_id(ticket):
    eid = _ejecucion(ticket, {"runtime": "claude_code_cli",
                              "harness_telemetry": {"session_id": "c9"}})

    H.backfill_from_harvest([_run("c9", runtime="claude_code_cli")], lookback_days=30)

    assert _md(eid)["harness_telemetry"]["input_tokens"] == 100


def test_backfill_idempotent(ticket):
    _ejecucion(ticket, {"runtime": "codex_cli", "codex_session_id": "s1"})

    H.backfill_from_harvest([_run("s1")], lookback_days=30)
    segundo = H.backfill_from_harvest([_run("s1")], lookback_days=30)

    assert segundo["backfilled"] == 0
    assert segundo["skipped_billable"] >= 1


def test_backfill_skips_already_billable(ticket):
    """Lo que el CLI reportó en vivo no se pisa con una estimación de disco."""
    eid = _ejecucion(ticket, {
        "runtime": "codex_cli", "codex_session_id": "s1",
        "harness_telemetry": {"session_id": "s1", "total_cost_usd": 1.23}})

    resumen = H.backfill_from_harvest([_run("s1")], lookback_days=30)

    assert resumen["skipped_billable"] == 1 and resumen["backfilled"] == 0
    assert _md(eid)["harness_telemetry"]["total_cost_usd"] == 1.23


def test_backfill_unmatched_untouched(ticket):
    eid = _ejecucion(ticket, {"runtime": "codex_cli", "codex_session_id": "s1"})
    antes = _md(eid)

    resumen = H.backfill_from_harvest([_run("zzz")], lookback_days=30)

    assert resumen["matched"] == 0 and resumen["scanned"] == 1
    assert _md(eid) == antes


def test_run_sin_session_id_no_matchea(ticket):
    _ejecucion(ticket, {"runtime": "codex_cli", "codex_session_id": "s1"})

    assert H.backfill_from_harvest([_run(None)], lookback_days=30)["matched"] == 0


def test_backfill_sets_provenance(ticket):
    eid = _ejecucion(ticket, {"runtime": "codex_cli", "codex_session_id": "s1"})

    H.backfill_from_harvest([_run("s1")], lookback_days=30)

    md = _md(eid)
    assert md["telemetry_harvest"]["source_format"] == "codex_rollout"
    assert md["telemetry_harvest"]["artifact"] == "rollout-x.jsonl"
    assert md["harness_telemetry"]["source"] == "harvest_disk", \
        "un run cosechado tiene que distinguirse de uno capturado en vivo"
    assert md["telemetry_harvest_backfilled"] is True


def test_dry_run_cuenta_igual_pero_no_escribe(ticket):
    """El preview tiene que dar los mismos números o no sirve para decidir."""
    eid = _ejecucion(ticket, {"runtime": "codex_cli", "codex_session_id": "s1"})
    antes = _md(eid)

    preview = H.backfill_from_harvest([_run("s1")], lookback_days=30, dry_run=True)

    assert preview["dry_run"] is True
    assert preview["matched"] == 1 and preview["backfilled"] == 1
    assert _md(eid) == antes, "un preview que escribe no es un preview"


def test_modelo_no_pisa_el_existente(ticket):
    eid = _ejecucion(ticket, {"runtime": "codex_cli", "codex_session_id": "s1",
                              "model": "el-que-ya-estaba"})

    H.backfill_from_harvest([_run("s1")], lookback_days=30)

    assert _md(eid)["model"] == "el-que-ya-estaba"


def test_matched_ids_apunta_a_la_ejecucion(ticket):
    eid = _ejecucion(ticket, {"runtime": "codex_cli", "codex_session_id": "s1"})

    resumen = H.backfill_from_harvest([_run("s1")], lookback_days=30)

    assert resumen["matched_ids"] == {"codex_cli:s1": eid}


def test_fuera_de_la_ventana_no_matchea(ticket):
    from db import session_scope
    from models import AgentExecution

    eid = _ejecucion(ticket, {"runtime": "codex_cli", "codex_session_id": "s1"})
    with session_scope() as session:
        session.get(AgentExecution, eid).started_at = datetime.utcnow() - timedelta(days=400)

    assert H.backfill_from_harvest([_run("s1")], lookback_days=30)["matched"] == 0


def test_metadata_queda_serializada(ticket):
    """metadata_json es Text: el accessor tiene que haber serializado."""
    from db import session_scope
    from models import AgentExecution

    eid = _ejecucion(ticket, {"runtime": "codex_cli", "codex_session_id": "s1"})
    H.backfill_from_harvest([_run("s1")], lookback_days=30)

    with session_scope() as session:
        crudo = session.get(AgentExecution, eid).metadata_json

    assert isinstance(crudo, str)
    assert json.loads(crudo)["telemetry_harvest_backfilled"] is True
