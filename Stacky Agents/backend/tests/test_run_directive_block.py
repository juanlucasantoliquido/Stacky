"""Plan 133 F4 — Bloque 'run-directive' server-side dentro de enrich_blocks."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from db import session_scope  # noqa: E402
from models import Ticket  # noqa: E402

AGENT_MD_PATH = (
    Path(__file__).resolve().parent.parent
    / "Stacky" / "agents" / "FunctionalAnalyst.agent.md"
)


@pytest.fixture(scope="module", autouse=True)
def app_ctx():
    from app import create_app

    app = create_app()
    app.config.update(TESTING=True)
    yield app


@pytest.fixture
def ticket_id():
    with session_scope() as session:
        t = Ticket(
            ado_id=331, project="Strategist_Pacifico", title="Task de prueba",
            ado_state="Doing", work_item_type="Task", tracker_type="azure_devops",
        )
        session.add(t)
        session.flush()
        return t.id


def _call(monkeypatch, ticket_id, *, flag_on=True, agent_type="functional", bp_result=None, refresh=None):
    from config import config
    from services import business_preflight, context_enrichment, run_ticket_refresh

    monkeypatch.setattr(config, "STACKY_RUN_DIRECTIVE_ENABLED", flag_on)
    if bp_result is not None:
        monkeypatch.setattr(business_preflight, "evaluate", lambda **kw: bp_result)
    if refresh is not None:
        monkeypatch.setattr(run_ticket_refresh, "refresh_ticket_snapshot", lambda tid: refresh)
    return context_enrichment._inject_run_directive(
        ticket_id=ticket_id, agent_type=agent_type, blocks=[{"id": "other", "content": "x"}], log=lambda *a, **k: None,
    )


def test_flag_off_identidad(monkeypatch, ticket_id):
    blocks = _call(monkeypatch, ticket_id, flag_on=False)
    assert blocks == [{"id": "other", "content": "x"}]


def test_agent_no_functional_identidad(monkeypatch, ticket_id):
    blocks = _call(monkeypatch, ticket_id, agent_type="developer")
    assert blocks == [{"id": "other", "content": "x"}]


def test_modo_a_prepend_primero(monkeypatch, ticket_id):
    from services.business_preflight import BusinessPreflightResult

    bp = BusinessPreflightResult(ok=True, mode="A", epic_ado_id=500, validated_state="New")
    blocks = _call(monkeypatch, ticket_id, bp_result=bp, refresh={"refreshed": True, "reason": "ok"})
    assert blocks[0]["id"] == "run-directive"
    assert "modo: A" in blocks[0]["content"]
    assert "500" in blocks[0]["content"]
    assert blocks[1]["id"] == "other"


def test_modo_b_incluye_razon(monkeypatch, ticket_id):
    from services.business_preflight import BusinessPreflightResult

    bp = BusinessPreflightResult(ok=True, mode="B", reason="prerequisitos validados")
    blocks = _call(monkeypatch, ticket_id, bp_result=bp, refresh={"refreshed": True, "reason": "ok"})
    assert blocks[0]["id"] == "run-directive"
    assert "modo: B" in blocks[0]["content"]
    assert "prerequisitos validados" in blocks[0]["content"]


def test_fail_open_modo_indeterminado(monkeypatch, ticket_id):
    from services.business_preflight import BusinessPreflightResult

    bp = BusinessPreflightResult(ok=True, mode=None, warnings=["comentarios inaccesibles: timeout"])
    blocks = _call(monkeypatch, ticket_id, bp_result=bp, refresh={"refreshed": False, "reason": "tracker_error: timeout"})
    content = blocks[0]["content"]
    assert "indeterminado" in content
    assert "Stacky YA validó" not in content
    assert "no disponible" in blocks[0]["title"]


def test_directiva_incluye_snapshot_fresh(monkeypatch, ticket_id):
    from services.business_preflight import BusinessPreflightResult

    bp = BusinessPreflightResult(ok=True, mode="A", epic_ado_id=1, validated_state="New")
    blocks = _call(monkeypatch, ticket_id, bp_result=bp, refresh={"refreshed": True, "reason": "ok"})
    assert "snapshot_fresh: true" in blocks[0]["content"]

    blocks2 = _call(monkeypatch, ticket_id, bp_result=bp, refresh={"refreshed": False, "reason": "tracker_error: x"})
    assert "snapshot_fresh: false" in blocks2[0]["content"]


def test_agent_md_consume_directiva():
    text = AGENT_MD_PATH.read_text(encoding="utf-8")
    assert "run-directive" in text
    assert "cross-check" in text
