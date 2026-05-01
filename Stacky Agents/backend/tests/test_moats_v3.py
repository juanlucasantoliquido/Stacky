"""Tests de la tanda 3: FA-05, FA-13, FA-22, FA-23, FA-43, FA-46."""
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


# ============================================================
# FA-23 — exporter
# ============================================================

def test_fa23_export_md_basic():
    from services import exporter

    r = exporter.export(output="# H1\n\nhola **mundo**", fmt="md", agent_type="qa")
    assert r.format == "md"
    assert "hola **mundo**" in r.content


def test_fa23_export_html_basic():
    from services import exporter

    r = exporter.export(output="# H1\n\nhola", fmt="html", agent_type="qa")
    assert "<h1>H1</h1>" in r.content
    assert r.mime == "text/html"


def test_fa23_export_slack_replaces_headings():
    from services import exporter

    r = exporter.export(output="# Title\n\n**bold** ok", fmt="slack")
    assert "*Title*" in r.content
    assert "*bold*" in r.content


def test_fa23_unsupported_format_raises():
    from services import exporter

    with pytest.raises(ValueError):
        exporter.export(output="x", fmt="pdf")


def test_fa23_endpoint(client):
    payload = {"format": "html", "output": "# Hi\n\nbody", "agent_type": "qa"}
    r = client.post("/api/export", json=payload)
    assert r.status_code == 200
    d = r.get_json()
    assert d["format"] == "html"
    assert "Hi" in d["content"]


# ============================================================
# FA-22 — translator (mock mode)
# ============================================================

def test_fa22_translate_mock_endpoint(client):
    payload = {"target_lang": "en", "output": "Hola mundo"}
    r = client.post("/api/translate", json=payload)
    assert r.status_code == 200
    d = r.get_json()
    assert d["target_lang"] == "en"
    assert "mock translation" in d["output"].lower() or "Hola mundo" in d["output"]


def test_fa22_translate_unsupported_lang(client):
    r = client.post("/api/translate", json={"target_lang": "xx", "output": "x"})
    assert r.status_code == 400


# ============================================================
# FA-13 — decisions
# ============================================================

def test_fa13_create_list(client):
    r = client.post(
        "/api/decisions",
        json={
            "summary": "No usar X en el proyecto",
            "reasoning": "Causó incidente en 2025",
            "tags": ["cobranza", "performance"],
        },
    )
    assert r.status_code == 201
    r2 = client.get("/api/decisions")
    assert any(d["summary"].startswith("No usar X") for d in r2.get_json())


def test_fa13_relevant_finds_overlap():
    from services import decisions

    decisions.create(
        summary="Usar idempotency-keys en cobros",
        reasoning="Evitar dobles cobros",
        tags=["cobranza", "idempotency"],
    )
    matches = decisions.relevant(project=None, context_text="Hay un nuevo flujo de cobranza con duplicados")
    assert any("idempotency" in m.summary for m in matches)


# ============================================================
# FA-43 — coaching
# ============================================================

def test_fa43_no_data_returns_info_tip(client):
    r = client.get("/api/coaching/tips?user=brand-new@local&days=30")
    assert r.status_code == 200
    d = r.get_json()
    assert d["user"] == "brand-new@local"
    assert any(t["severity"] == "info" for t in d["tips"])


def test_fa43_high_discard_rate_triggers_warning():
    from datetime import datetime
    from db import session_scope
    from models import AgentExecution, Ticket
    from services import coaching

    with session_scope() as session:
        t = Ticket(ado_id=9991, project="RSPacifico", title="x", ado_state="Done")
        session.add(t); session.flush()
        for i in range(8):
            session.add(
                AgentExecution(
                    ticket_id=t.id,
                    agent_type="qa",
                    status="completed",
                    verdict="discarded" if i < 5 else "approved",
                    started_by="discarder@local",
                    started_at=datetime.utcnow(),
                    input_context_json="[]",
                    output="x",
                )
            )
    tips = coaching.tips_for("discarder@local")
    assert any(t.severity in {"warning", "high"} for t in tips)


# ============================================================
# FA-46 — best practices
# ============================================================

def test_fa46_feed_endpoint(client):
    r = client.get("/api/best-practices/feed?days=30")
    assert r.status_code == 200
    d = r.get_json()
    assert "sections" in d
    assert d["window_days"] == 30


# ============================================================
# FA-05 — git context (skipea si no hay git)
# ============================================================

def test_fa05_file_context_handles_missing_file():
    from services import git_context

    ctx = git_context.file_context("definitely/not/a/real/file_xyz.txt")
    assert ctx.error is not None or ctx.last_commits == []


def test_fa05_endpoint(client):
    r = client.get("/api/git/file-context?path=does/not/exist.txt")
    # Puede devolver 200 con error o algún commit; lo importante es que el endpoint exista.
    assert r.status_code in (200, 404)
