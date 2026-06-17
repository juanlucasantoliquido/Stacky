"""M2.2 — PATCH de contenido por memory_id + dry-run de targeting.

Cubre:
  - update_observation: update parcial (None = no tocar), revision_count +1,
    normalized_hash recalculado, status NO cambia
  - PATCH /api/memory/<id>: edición de contenido y de targeting de directiva
  - PATCH de id inexistente → 404
  - PATCH sin campos → 400
  - POST /directive-preview: match / no-match contra un ticket real
  - upsert_by_topic_key sigue verde (no se rompió la unicidad por topic_key)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture()
def client():
    from app import create_app

    app = create_app()
    app.config.update(TESTING=True)
    with app.test_client() as c:
        yield c


def test_update_observation_partial_and_revision(client):
    from services import memory_store

    mid = memory_store.save_observation(
        project="M22A", type="bugfix", title="orig", content="contenido original",
        author_email="op@x.com",
    )
    before = memory_store.get(mid)
    ok = memory_store.update_observation(mid, content="contenido nuevo")
    assert ok is True
    after = memory_store.get(mid)
    assert after["content"] == "contenido nuevo"
    assert after["title"] == "orig"  # None = no tocar
    assert after["revision_count"] == before["revision_count"] + 1
    assert after["status"] == before["status"]  # status NO cambia


def test_update_recalculates_hash(client):
    from services import memory_store
    from db import session_scope

    mid = memory_store.save_observation(
        project="M22B", type="bugfix", title="t", content="c1", author_email="op@x.com",
    )
    with session_scope() as s:
        h1 = s.query(memory_store.StackyMemoryObservation).filter_by(memory_id=mid).first().normalized_hash
    memory_store.update_observation(mid, content="c2 distinto")
    with session_scope() as s:
        h2 = s.query(memory_store.StackyMemoryObservation).filter_by(memory_id=mid).first().normalized_hash
    assert h1 != h2


def test_update_nonexistent_returns_false(client):
    from services import memory_store

    assert memory_store.update_observation("mem-nope") is False


def test_patch_endpoint_updates_targeting(client):
    # crear directiva
    r = client.post("/api/memory", json={
        "project": "M22C", "type": "directive", "title": "d", "content": "x",
        "enforcement": "always", "applies_to": {"agent_types": ["developer"]},
    })
    mid = r.get_json()["memory_id"]
    # editar targeting
    r2 = client.patch(f"/api/memory/{mid}", json={
        "applies_to": {"agent_types": ["qa"], "title_keywords": ["bug"]},
    })
    assert r2.status_code == 200, r2.get_data(as_text=True)
    row = client.get(f"/api/memory/{mid}").get_json()
    assert row["applies_to"]["agent_types"] == ["qa"]


def test_patch_404(client):
    r = client.patch("/api/memory/mem-nope", json={"content": "x"})
    assert r.status_code == 404


def test_patch_no_fields_400(client):
    r = client.post("/api/memory", json={
        "project": "M22D", "type": "bugfix", "title": "t", "content": "c",
    })
    mid = r.get_json()["memory_id"]
    r2 = client.patch(f"/api/memory/{mid}", json={})
    assert r2.status_code == 400


def test_directive_preview_match_and_no_match(client):
    from db import session_scope
    from models import Ticket

    with session_scope() as s:
        t = Ticket(ado_id=999001, project="M22E", title="Proceso de cobranzas mensual",
                   description="detalle", work_item_type="User Story")
        s.add(t)
        s.flush()
        tid = t.id

    r = client.post("/api/memory/directive-preview", json={
        "applies_to": {"work_item_types": ["User Story"], "title_keywords": ["cobranzas"]},
        "ticket_id": tid,
    })
    assert r.status_code == 200
    body = r.get_json()
    assert body["matches"] is True

    r2 = client.post("/api/memory/directive-preview", json={
        "applies_to": {"work_item_types": ["Epic"]},
        "ticket_id": tid,
    })
    assert r2.get_json()["matches"] is False


def test_upsert_by_topic_key_still_works(client):
    from services import memory_store

    a = memory_store.save_observation(
        project="M22F", type="bugfix", title="t1", content="c1",
        topic_key="bug/x", author_email="op@x.com",
    )
    b = memory_store.save_observation(
        project="M22F", type="bugfix", title="t2", content="c2",
        topic_key="bug/x", author_email="op@x.com",
    )
    assert a == b  # misma fila, upsert
    assert memory_store.get(a)["revision_count"] == 2
