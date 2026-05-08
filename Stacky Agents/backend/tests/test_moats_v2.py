"""Tests de los moats agregados en la segunda tanda.

Cubre: FA-04 (LLM router), FA-11 (anti-patterns), FA-12 (few-shot),
FA-37 (PII masking), FA-42 (next-agent), FA-50 (system prompt override),
FA-52 (webhooks).
"""
import os
import sys
from datetime import datetime, timedelta
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


# ============================================================
# FA-37 — PII masker
# ============================================================

def test_fa37_mask_unmask_roundtrip():
    from services import pii_masker

    text = "Cliente DNI 12345678, email juan@ubimia.com, CUIT 30-12345678-9, tel +54 11 1234-5678."
    masked, mp = pii_masker.mask_text(text)
    assert "12345678" not in masked
    assert "juan@ubimia.com" not in masked
    assert "30-12345678-9" not in masked
    assert len(mp) >= 3
    restored = pii_masker.unmask(masked, mp)
    assert restored == text


def test_fa37_mask_blocks_consistency():
    from services import pii_masker

    blocks = [
        {"kind": "auto", "title": "ticket", "content": "email juan@x.com"},
        {"kind": "editable", "title": "notes", "content": "el mismo email juan@x.com"},
    ]
    masked, mp = pii_masker.mask_blocks(blocks)
    # ambos blocks deben usar el MISMO token
    tokens_in_a = [t for t in mp if mp[t] == "juan@x.com"]
    assert len(tokens_in_a) == 1
    token = tokens_in_a[0]
    assert token in masked[0]["content"]
    assert token in masked[1]["content"]


# ============================================================
# FA-04 — LLM router
# ============================================================

def test_fa04_router_default_per_agent():
    from services import llm_router

    blocks_small = [{"kind": "auto", "title": "x", "content": "x" * 200}]
    d = llm_router.decide(agent_type="developer", blocks=blocks_small)
    assert d.model.startswith("claude-")


def test_fa04_router_upgrades_for_xl_complexity():
    from services import llm_router

    d = llm_router.decide(
        agent_type="technical",
        blocks=[{"kind": "auto", "title": "x", "content": "x" * 200}],
        fingerprint_complexity="XL",
    )
    assert d.model == "claude-opus-4-7"
    assert "XL" in d.reason


def test_fa04_router_override_takes_precedence():
    from services import llm_router

    d = llm_router.decide(
        agent_type="qa",
        blocks=[{"kind": "auto", "title": "x", "content": "x"}],
        override="claude-opus-4-7",
        backend="anthropic",
    )
    assert d.model == "claude-opus-4-7"
    assert d.reason == "user-override"


def test_fa04_route_endpoint(client):
    payload = {
        "agent_type": "qa",
        "context_blocks": [{"kind": "auto", "title": "x", "content": "ok"}],
    }
    r = client.post("/api/agents/route", json=payload)
    assert r.status_code == 200
    d = r.get_json()
    assert "model" in d and "reason" in d and "available" in d


# ============================================================
# FA-50 — system prompt override
# ============================================================

def test_fa50_system_prompt_endpoint(client):
    r = client.get("/api/agents/qa/system-prompt")
    assert r.status_code == 200
    d = r.get_json()
    assert d["agent_type"] == "qa"
    assert "QA" in d["system_prompt"] or "qa" in d["system_prompt"].lower()


def test_fa50_compose_uses_override():
    from agents.base import RunContext
    from agents.qa import QAAgent

    a = QAAgent()
    ctx = RunContext(system_prompt_override="MI PROMPT ONE-OFF")
    sp, meta = a.compose_system_prompt(ctx)
    assert sp == "MI PROMPT ONE-OFF"
    assert meta["system_prompt_source"] == "override"


# ============================================================
# FA-12 — few-shot
# ============================================================

def test_fa12_few_shot_picks_approved_only():
    from db import session_scope
    from models import AgentExecution, Ticket
    from services import few_shot

    with session_scope() as session:
        t = Ticket(ado_id=7100, project="RSPacifico", title="Test", ado_state="Done")
        session.add(t)
        session.flush()
        # uno aprobado
        session.add(
            AgentExecution(
                ticket_id=t.id, agent_type="qa", status="completed", verdict="approved",
                started_by="dev@local", input_context_json="[]", output="# Verdict: PASS",
            )
        )
        # uno descartado (NO debería seleccionarse)
        session.add(
            AgentExecution(
                ticket_id=t.id, agent_type="qa", status="completed", verdict="discarded",
                started_by="dev@local", input_context_json="[]", output="# rejected output",
            )
        )

    examples = few_shot.pick_examples(agent_type="qa", project="RSPacifico", k=3)
    assert all("rejected" not in e.output for e in examples)
    assert any("PASS" in e.output for e in examples)


# ============================================================
# FA-11 — anti-patterns
# ============================================================

def test_fa11_create_and_inject(client):
    r = client.post(
        "/api/anti-patterns",
        json={
            "pattern": "usar decimal.Round sin MidpointRounding",
            "reason": "ADO-1100 explotó por esto",
            "agent_type": "developer",
        },
    )
    assert r.status_code == 201

    r2 = client.get("/api/anti-patterns")
    assert r2.status_code == 200
    items = r2.get_json()
    assert any("decimal.Round" in i["pattern"] for i in items)

    # Inyección al system prompt
    from agents.base import RunContext
    from agents.developer import DeveloperAgent

    a = DeveloperAgent()
    ctx = RunContext(use_anti_patterns=True, use_few_shot=False)
    sp, meta = a.compose_system_prompt(ctx)
    assert meta["anti_patterns_count"] >= 1
    assert "decimal.Round" in sp


# ============================================================
# FA-42 — next-agent suggestion
# ============================================================

def test_fa42_default_chain(client):
    r = client.get("/api/agents/next-suggestion?after_agent=functional")
    assert r.status_code == 200
    items = r.get_json()
    assert len(items) >= 1
    assert items[0]["agent_type"] == "technical"


def test_fa42_history_overrides_default():
    from db import session_scope
    from models import AgentExecution, Ticket
    from services import next_agent

    base = datetime.utcnow() - timedelta(hours=1)
    with session_scope() as session:
        t = Ticket(ado_id=7200, project="RSPacifico", title="Test", ado_state="Done")
        session.add(t)
        session.flush()
        # Crear un patrón histórico funcional → developer (5 veces) para que pese sobre el default
        for i in range(6):
            session.add(
                AgentExecution(
                    ticket_id=t.id, agent_type="functional", status="completed",
                    verdict="approved", started_by="dev@local",
                    started_at=base + timedelta(minutes=i * 10),
                    input_context_json="[]", output="ok",
                )
            )
            session.add(
                AgentExecution(
                    ticket_id=t.id, agent_type="developer", status="completed",
                    verdict="approved", started_by="dev@local",
                    started_at=base + timedelta(minutes=i * 10 + 5),
                    input_context_json="[]", output="ok",
                )
            )
    suggestions = next_agent.suggest(after_agent="functional")
    # Después de muchos approved, debería ver "developer" como sucesor histórico
    assert any(s.agent_type == "developer" and s.source == "history" for s in suggestions)


# ============================================================
# FA-52 — webhooks
# ============================================================

def test_fa52_create_list_deactivate(client):
    r = client.post(
        "/api/webhooks",
        json={"url": "http://localhost:9999/hook", "event": "exec.completed"},
    )
    assert r.status_code == 201
    wid = r.get_json()["id"]

    r2 = client.get("/api/webhooks")
    assert r2.status_code == 200
    found = next((w for w in r2.get_json() if w["id"] == wid), None)
    assert found is not None and found["active"]

    r3 = client.delete(f"/api/webhooks/{wid}")
    assert r3.status_code == 200


def test_fa52_signature_helper():
    from services.webhooks import _sign

    sig = _sign("secret-123", b'{"a":1}')
    assert isinstance(sig, str) and len(sig) == 64
    assert _sign(None, b"x") is None
