"""Tests de la API de memoria colaborativa (api/memory.py) — Fase A."""
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


def test_create_list_search_and_preview(client):
    r = client.post(
        "/api/memory",
        json={
            "project": "MEM_API_1",
            "type": "bugfix",
            "title": "Detección de output del Developer",
            "content": "chequear ordinal vs ADO id al detectar comment.html",
            "tags": ["developer"],
        },
        headers={"X-User-Email": "ana@empresa.com"},
    )
    assert r.status_code == 201
    memory_id = r.get_json()["memory_id"]

    # listado por proyecto
    r = client.get("/api/memory?project=MEM_API_1")
    rows = r.get_json()
    assert any(row["memory_id"] == memory_id for row in rows)
    assert rows[0]["author_email"] == "ana@empresa.com"

    # búsqueda
    r = client.get("/api/memory/search?project=MEM_API_1&q=ordinal+ADO+comment")
    hits = r.get_json()
    assert any(h["memory_id"] == memory_id for h in hits)

    # preview de inyección
    r = client.get("/api/memory/context-preview?project=MEM_API_1&agent_type=developer&q=deteccion+output")
    ctx = r.get_json()
    assert ctx["active_hits"] >= 1
    assert "ordinal vs ADO id" in ctx["content"]


def test_create_requires_fields(client):
    r = client.post("/api/memory", json={"project": "X"})
    assert r.status_code == 400


def test_supersedes_relation_hides_old_in_preview(client):
    old = client.post(
        "/api/memory",
        json={"project": "MEM_API_2", "type": "client_policy", "title": "vieja", "content": "DML directo permitido"},
    ).get_json()["memory_id"]
    new = client.post(
        "/api/memory",
        json={"project": "MEM_API_2", "type": "client_policy", "title": "nueva", "content": "DML solo via procedure"},
    ).get_json()["memory_id"]

    r = client.post(
        "/api/memory/relations",
        json={
            "project": "MEM_API_2",
            "source_memory_id": new,
            "target_memory_id": old,
            "relation": "supersedes",
        },
    )
    assert r.status_code == 201

    assert client.get(f"/api/memory/{old}").get_json()["status"] == "superseded"
    ctx = client.get("/api/memory/context-preview?project=MEM_API_2&agent_type=developer&q=DML+politica").get_json()
    assert old not in ctx["memory_ids"]


def test_status_counts(client):
    client.post(
        "/api/memory",
        json={"project": "MEM_API_3", "type": "pattern", "title": "p1", "content": "activo uno"},
    )
    client.post(
        "/api/memory",
        json={"project": "MEM_API_3", "type": "pattern", "title": "p2", "content": "draft uno", "status": "draft"},
    )
    counts = client.get("/api/memory/status?project=MEM_API_3").get_json()["counts"]
    assert counts["active"] == 1
    assert counts["draft"] == 1
