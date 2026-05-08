"""Tests fase 6 (cierre del catálogo): FA-01, FA-02, FA-17, FA-27, FA-28,
FA-29, FA-41, FA-48, FA-49, FA-51."""
import os, sys
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


# ── FA-41 egress controls ────────────────────────────────────

def test_fa41_no_policies_allows_all():
    from services import egress_policies
    d = egress_policies.check(project=None, model="claude-sonnet-4-6",
                              context_text="DNI 12345678 y email a@b.com")
    # No policies set → allowed=True (data classes detected but no rules)
    assert d.allowed is True


def test_fa41_blocks_when_policy_disallows():
    from services import egress_policies
    egress_policies.create(
        data_class="financial",
        allowed_llms=["claude-opus-4-7"],   # solo opus
        action="block",
    )
    # Sonnet NO está permitido para financial
    d = egress_policies.check(
        project=None, model="claude-sonnet-4-6",
        context_text="CBU 1234567890123456789012",
    )
    assert d.allowed is False
    assert "financial" in d.blocked_classes


def test_fa41_detect_classes():
    from services.egress_policies import detect_classes
    assert "pii" in detect_classes("Email a@b.com y DNI 12345678")
    assert "financial" in detect_classes("CBU 1234567890123456789012")
    assert "regulatory" in detect_classes("Cumplimiento BCRA y SOX")
    assert "production" in detect_classes("Datos de PROD y data real")


# ── FA-48 + FA-49 — refinement / parallel (smoke) ────────────

def test_fa48_explore_endpoint(client):
    from db import session_scope
    from models import Ticket
    with session_scope() as session:
        t = Ticket(ado_id=22201, project="RSPacifico", title="explore",
                   ado_state="To Do")
        session.add(t); session.flush(); tid = t.id
    r = client.post("/api/agents/explore", json={
        "agent_type": "qa", "ticket_id": tid,
        "context_blocks": [{"id": "b1", "kind": "auto", "title": "x", "content": "test"}],
        "variants": [{"model": "mock-1.0", "label": "test"}]
    })
    assert r.status_code == 200
    d = r.get_json()
    assert len(d["execution_ids"]) == 1


def test_fa48_refine_endpoint(client):
    from db import session_scope
    from models import Ticket
    with session_scope() as session:
        t = Ticket(ado_id=22202, project="RSPacifico", title="refine",
                   ado_state="To Do")
        session.add(t); session.flush(); tid = t.id
    r = client.post("/api/agents/refine", json={
        "agent_type": "qa", "ticket_id": tid,
        "context_blocks": [{"id": "b1", "kind": "auto", "title": "x", "content": "test"}],
        "template": "default",
    })
    assert r.status_code == 200
    d = r.get_json()
    assert len(d["execution_ids"]) >= 1
    assert len(d["prompts"]) == 3


# ── FA-51 — macros ──────────────────────────────────────────

def test_fa51_validate_definition():
    from services.macros import validate
    errs = validate({"steps": [{"agent": "qa"}]})
    assert errs == []
    errs = validate({"steps": []})
    assert len(errs) >= 1
    errs = validate({"steps": [{"agent": "unknown"}]})
    assert any("agent" in e.field for e in errs)


def test_fa51_create_and_list(client):
    r = client.post("/api/macros", json={
        "slug": "test-macro",
        "name": "Test Macro",
        "definition": {"steps": [{"agent": "qa"}]},
    })
    assert r.status_code == 201
    r2 = client.get("/api/macros")
    assert any(m["slug"] == "test-macro" for m in r2.get_json())


# ── FA-29 — CI failure webhook ───────────────────────────────

def test_fa29_webhook_creates_debug_exec(client):
    r = client.post("/api/ci/failure-webhook", json={
        "ticket_ado_id": 33301,
        "build_log": "[ERROR] test_foo failed at line 42",
        "commit_sha": "abc123",
        "failed_tests": ["test_foo", "test_bar"],
    })
    assert r.status_code == 200
    assert "execution_id" in r.get_json()


# ── FA-28 — PR review webhook ────────────────────────────────

def test_fa28_pr_webhook(client):
    from db import session_scope
    from models import Ticket
    with session_scope() as session:
        t = Ticket(ado_id=44401, project="RSPacifico", title="pr review",
                   ado_state="Doing")
        session.add(t); session.flush()
    r = client.post("/api/pr/review-webhook", json={
        "ticket_ado_id": 44401, "pr_id": 99,
        "diff": "--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-old\n+new",
        "description": "Fix",
    })
    assert r.status_code == 200
    assert "execution_id" in r.get_json()


# ── FA-01 — embeddings retrieval ─────────────────────────────

def test_fa01_index_and_topk():
    from db import session_scope
    from models import AgentExecution, Ticket
    from services import embeddings

    with session_scope() as session:
        t1 = Ticket(ado_id=55501, project="RSPacifico", title="cobranza SMS",
                    ado_state="Done")
        session.add(t1); session.flush()
        e1 = AgentExecution(
            ticket_id=t1.id, agent_type="technical", status="completed",
            verdict="approved", started_by="dev@local",
            input_context_json='[{"kind":"auto","title":"t","content":"flujo cobranza notificacion sms"}]',
            output="Análisis del flujo de cobranza con SMS",
        )
        session.add(e1); session.flush(); eid = e1.id

    embeddings.index_execution(eid)
    hits = embeddings.top_k(query_text="cobranza SMS notificacion",
                            agent_type="technical", k=5)
    assert any(h.execution_id == eid for h in hits)


def test_fa01_topk_endpoint(client):
    r = client.post("/api/retrieval/top-k", json={
        "query": "cobranza SMS", "k": 3,
    })
    assert r.status_code == 200
    assert isinstance(r.get_json(), list)


# ── FA-02 — live BD ──────────────────────────────────────────

def test_fa02_live_db_select_mock(client):
    r = client.post("/api/live-db/select", json={
        "sql": "SELECT * FROM clientes",
        "max_rows": 5,
    })
    assert r.status_code == 200
    d = r.get_json()
    assert d["row_count"] >= 1   # mock returns dummy rows


def test_fa02_live_db_blocks_destructive(client):
    r = client.post("/api/live-db/select", json={"sql": "DROP TABLE x"})
    d = r.get_json()
    assert d["error"] is not None
    assert "SELECT" in d["error"]


def test_fa02_live_db_blocks_multi_statement(client):
    r = client.post("/api/live-db/select", json={
        "sql": "SELECT 1; SELECT 2",
    })
    assert r.get_json()["error"] is not None


# ── FA-17 — typecheck ────────────────────────────────────────

def test_fa17_python_valid():
    from services import typecheck
    r = typecheck.check_python("x = 1\nprint(x)")
    assert r.passed
    assert not r.issues


def test_fa17_python_syntax_error():
    from services import typecheck
    r = typecheck.check_python("def x(:\n  pass")
    assert not r.passed
    assert r.issues


def test_fa17_extract_blocks():
    from services.typecheck import extract_blocks
    md = "Texto.\n```python\nx = 1\n```\nY otro:\n```ts\nconst y = 2;\n```"
    blocks = extract_blocks(md)
    langs = {lang for lang, _ in blocks}
    assert "python" in langs
    assert "typescript" in langs


def test_fa17_endpoint(client):
    r = client.post("/api/typecheck/output", json={
        "output": "```python\nx = 1\nprint(x)\n```",
    })
    assert r.status_code == 200
    d = r.get_json()
    assert d["blocks_checked"] == 1
    assert d["any_failed"] is False


# ── FA-27 — slash commands ───────────────────────────────────

def test_fa27_help():
    from services import slash_commands
    r = slash_commands.handle("help")
    assert "slash commands" in r.text.lower() or "stacky" in r.text.lower()


def test_fa27_unknown_command():
    from services import slash_commands
    r = slash_commands.handle("foobar")
    assert "no reconocido" in r.text.lower() or "help" in r.text.lower()


def test_fa27_endpoint_requires_token(client):
    r = client.post("/api/slash/stacky", data={"text": "help", "user_name": "test"})
    assert r.status_code == 401


def test_fa27_endpoint_with_valid_token(client):
    import os
    token = os.getenv("SLASH_TOKEN", "stacky-slash-default-secret")
    r = client.post(
        "/api/slash/stacky",
        data={"text": "help", "user_name": "test"},
        headers={"X-Stacky-Slash-Token": token},
    )
    assert r.status_code == 200
    d = r.get_json()
    assert "text" in d
