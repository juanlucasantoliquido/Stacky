"""Plan 129 F1 — services/global_search.py: search_all puro y determinista."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import global_search as gs


@pytest.fixture(scope="module", autouse=True)
def _init_app():
    from app import create_app
    app = create_app()
    app.config.update(TESTING=True)
    yield app


@pytest.fixture(autouse=True)
def clean_db():
    from db import session_scope
    from models import AgentExecution, Ticket

    yield
    with session_scope() as session:
        session.query(AgentExecution).delete()
        session.query(Ticket).delete()


def _seed_ticket(ado_id: int, title: str, ado_state: str = "Active") -> int:
    from db import session_scope
    from models import Ticket
    from services.project_context import resolve_project_context

    ctx = resolve_project_context()
    with session_scope() as session:
        t = Ticket(
            ado_id=ado_id,
            project=getattr(ctx, "tracker_project", "TEST"),
            stacky_project_name=getattr(ctx, "stacky_project_name", None),
            title=title,
            ado_state=ado_state,
        )
        session.add(t)
        session.flush()
        return t.id


def _seed_exec(ticket_id: int, agent_type: str = "developer", status: str = "failed") -> int:
    from db import session_scope
    from models import AgentExecution

    with session_scope() as session:
        e = AgentExecution(
            ticket_id=ticket_id,
            agent_type=agent_type,
            status=status,
            input_context_json="[]",
            started_by="test",
        )
        session.add(e)
        session.flush()
        return e.id


# ── score() / normalize() ─────────────────────────────────────────────────

def test_score_substring_temprano_gana():
    assert gs.score("plan", "plan.md") > gs.score("plan", "x_plan.md")


def test_score_acentos_insensible():
    assert gs.score("busqueda", "Búsqueda profunda") > 0


def test_score_multitoken_and():
    assert gs.score("doctor local", "Doctor DevOps local") == 40
    assert gs.score("doctor zz", "Doctor DevOps local") == 0


# ── _search_tickets ────────────────────────────────────────────────────────

def test_tickets_hit_shape_y_nav():
    tid = _seed_ticket(ado_id=4567, title="Alta cliente PF")
    hits = gs._search_tickets("alta cliente pf", 8)
    assert len(hits) == 1
    hit = hits[0]
    assert hit["label"] == "T-4567 — Alta cliente PF"
    assert hit["nav"] == f"/tickets?ticket={tid}"
    assert hit["kind"] == "ticket"
    assert hit["id"] == str(tid)


# ── _search_executions ──────────────────────────────────────────────────────

def test_executions_hit_y_hint_ticket():
    tid = _seed_ticket(ado_id=9911, title="Ticket con ejecucion")
    eid = _seed_exec(tid, agent_type="developer", status="failed")
    hits = gs._search_executions(f"run #{eid}", 8)
    assert len(hits) == 1
    hit = hits[0]
    assert hit["label"] == f"Run #{eid} · developer · failed"
    assert hit["hint"] == "T-9911"
    assert hit["nav"] == f"/history?execution={eid}"


# ── _search_docs ─────────────────────────────────────────────────────────

def _fake_doc_index():
    return {
        "roots": [
            {
                "id": "technical-docs",
                "label": "Documentación Técnica",
                "children": [
                    {
                        "kind": "folder",
                        "label": "docs",
                        "path": "docs",
                        "children": [
                            {
                                "kind": "file",
                                "label": "plan.md",
                                "path": "docs/plan.md",
                                "children": [],
                            },
                        ],
                    },
                ],
            },
        ],
    }


def test_docs_solo_hojas_y_nav_urlencoded(monkeypatch):
    monkeypatch.setattr("services.doc_indexer.build_index", _fake_doc_index)
    hits = gs._search_docs("plan", 8)
    assert len(hits) == 1
    hit = hits[0]
    assert hit["label"] == "plan.md"
    assert hit["id"] == "docs/plan.md"
    assert hit["nav"] == "/docs?path=docs%2Fplan.md"


# ── limit / orden / fuente rota / servers / query vacía (search_all) ──────

def test_limit_y_orden_estable():
    ids = [_seed_ticket(ado_id=70000 + i, title=f"zzzmatch {i:03d}") for i in range(30)]
    hits = gs._search_tickets("zzzmatch", 5)
    assert len(hits) == 5
    expected_ids = sorted(str(i) for i in ids)[:5]
    assert [h["id"] for h in hits] == expected_ids


def test_fuente_rota_no_tumba(monkeypatch):
    def _boom(qn, limit):
        raise RuntimeError("boom")

    monkeypatch.setitem(gs._SOURCES, "doc", _boom)
    _seed_ticket(ado_id=8123, title="ticket robusto ante fuente rota")
    result = gs.search_all("robusto")
    assert result["ok"] is True
    kinds = {g["kind"] for g in result["groups"]}
    assert "doc" not in kinds
    assert "ticket" in kinds


def test_servers_sin_password(monkeypatch):
    fake_server = {"alias": "PF", "host": "10.10.1.5", "password": "supersecret"}
    monkeypatch.setattr(
        "services.server_registry.list_servers", lambda: [fake_server]
    )
    hits = gs._search_servers("pf", 8)
    assert "password" not in json.dumps(hits)
    assert hits[0]["hint"] == "10.10.1.5"


def test_query_vacia_groups_vacios():
    assert gs.search_all("  ") == {"ok": True, "query": "", "groups": []}
