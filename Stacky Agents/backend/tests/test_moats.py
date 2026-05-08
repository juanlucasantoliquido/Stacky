"""Tests rápidos de los moats implementados (FA-09, FA-31, FA-33, FA-35, FA-45/14)."""
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")


@pytest.fixture
def client():
    from app import create_app

    app = create_app()
    app.config.update(TESTING=True)
    with app.test_client() as c:
        yield c


# ---------- FA-09: glossary ----------

def test_fa09_glossary_detects_terms():
    from services.glossary import detect_terms, build_glossary_block

    terms = detect_terms(["Necesitamos agregar una entrada RIDIOMA y modificar la cobranza."])
    canonical = {t.term for t in terms}
    assert "RIDIOMA" in canonical
    assert "Cobranza" in canonical

    block = build_glossary_block(["Hay que tocar el módulo de cobranzas y los RPARAM batch."])
    assert block is not None
    assert block["kind"] == "auto"
    assert "Cobranza" in block["content"] or "RPARAM" in block["content"]


def test_fa09_glossary_endpoint(client):
    from db import session_scope
    from models import Ticket

    with session_scope() as session:
        t = Ticket(
            ado_id=4242,
            project="RSPacifico",
            title="Cargar nuevo RIDIOMA para errores de cobranza",
            description="El módulo Batch necesita un RPARAM nuevo.",
            ado_state="To Do",
        )
        session.add(t)
        session.flush()
        tid = t.id
    r = client.get(f"/api/tickets/{tid}/glossary")
    assert r.status_code == 200
    block = r.get_json()
    assert block is not None
    assert block["kind"] == "auto"


# ---------- FA-31: output cache ----------

def test_fa31_cache_key_stable():
    from services.output_cache import compute_key

    blocks_a = [{"kind": "auto", "title": "x", "content": "hola"}]
    blocks_b = [{"kind": "auto", "title": "x", "content": "hola"}]
    blocks_c = [{"kind": "auto", "title": "x", "content": "diferente"}]
    assert compute_key(agent_type="functional", blocks=blocks_a) == compute_key(
        agent_type="functional", blocks=blocks_b
    )
    assert compute_key(agent_type="functional", blocks=blocks_a) != compute_key(
        agent_type="functional", blocks=blocks_c
    )


def test_fa31_lookup_miss_then_store_then_hit():
    from services import output_cache

    blocks = [{"kind": "editable", "title": "Notes", "content": "test cache"}]
    miss = output_cache.lookup(agent_type="qa", blocks=blocks)
    assert miss is None
    output_cache.store(agent_type="qa", blocks=blocks, output="# OK\nVerdict: PASS")
    hit = output_cache.lookup(agent_type="qa", blocks=blocks)
    assert hit is not None
    assert "Verdict: PASS" in hit["output"]
    assert hit["hits"] >= 1


# ---------- FA-33: cost preview ----------

def test_fa33_estimate_endpoint(client):
    payload = {
        "agent_type": "technical",
        "context_blocks": [
            {"kind": "auto", "title": "ticket", "content": "x" * 800},
            {"kind": "editable", "title": "notes", "content": "y" * 400},
        ],
    }
    r = client.post("/api/agents/estimate", json=payload)
    assert r.status_code == 200
    d = r.get_json()
    assert d["tokens_in"] > 0
    assert d["tokens_out"] > 0
    assert d["cost_usd_total"] >= 0
    assert "cache_hit" in d


# ---------- FA-35: confidence ----------

def test_fa35_confidence_high_for_structured_output():
    from services.confidence import score

    output = """\
# Análisis
## 1. Sección uno
Implementación detallada en `Cobranza.cs:84` con TU-001.
Verdict: PASS.
| col | val |
|-----|-----|
| a   | 1   |
"""
    r = score(output)
    assert r.overall >= 70


def test_fa35_confidence_low_for_hedge():
    from services.confidence import score

    output = """\
# Análisis
## 1. Algo
No estoy seguro pero creo que podría ser. TODO: FIXME. Tal vez quizás.
"""
    r = score(output)
    assert r.overall < 70


# ---------- FA-45 + FA-14: similarity ----------

def test_fa45_similar_endpoint_runs(client):
    from db import session_scope
    from models import AgentExecution, Ticket

    with session_scope() as session:
        t1 = Ticket(ado_id=901, project="RSPacifico", title="Cobranza con SMS", ado_state="To Do")
        t2 = Ticket(ado_id=902, project="RSPacifico", title="Notificación SMS de cobranza fallida", ado_state="Done")
        session.add_all([t1, t2])
        session.flush()
        e = AgentExecution(
            ticket_id=t2.id,
            agent_type="technical",
            status="completed",
            verdict="approved",
            started_by="dev@local",
            input_context_json='[{"kind":"auto","title":"x","content":"cobranza notificacion sms"}]',
            output="# técnico\nflujo de notificacion sms en cobranza",
        )
        session.add(e)
        session.flush()
        ref_id = t1.id

    r = client.get(f"/api/similarity/similar?ticket_id={ref_id}&agent_type=technical")
    assert r.status_code == 200
    hits = r.get_json()
    assert isinstance(hits, list)
    # Debería encontrar al menos la exec de t2
    assert any(h["ticket_ado_id"] == 902 for h in hits)


def test_fa14_graveyard_endpoint_runs(client):
    from db import session_scope
    from models import AgentExecution, Ticket

    with session_scope() as session:
        t = Ticket(ado_id=8800, project="RSPacifico", title="Test graveyard", ado_state="Done")
        session.add(t)
        session.flush()
        e = AgentExecution(
            ticket_id=t.id,
            agent_type="developer",
            status="completed",
            verdict="discarded",
            started_by="dev@local",
            input_context_json="[]",
            output="intento fallido de implementacion con cobranza tabla rota",
        )
        session.add(e)
        session.flush()

    r = client.get("/api/similarity/graveyard?q=cobranza+tabla&agent_type=developer")
    assert r.status_code == 200
    hits = r.get_json()
    assert isinstance(hits, list)
