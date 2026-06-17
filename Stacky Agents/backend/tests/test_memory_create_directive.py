"""M2.1 — Alta de directiva vía POST /api/memory (extendido).

Cubre:
  - crear observación normal → idéntico a hoy (sin enforcement/applies_to)
  - crear directiva con targeting → fila con type=directive, enforcement, applies_to_json
  - directiva sin targeting (applies_to vacío) → 400
  - enforcement=always con type != directive → 400
  - applies_to con clave desconocida → 400
  - applies_to con valor no-lista → 400
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


def test_create_normal_observation_unchanged(client):
    r = client.post("/api/memory", json={
        "project": "M21A", "type": "bugfix", "title": "obs", "content": "c",
    })
    assert r.status_code == 201
    mid = r.get_json()["memory_id"]
    row = client.get(f"/api/memory/{mid}").get_json()
    assert row["type"] == "bugfix"
    assert row["enforcement"] is None
    assert row["applies_to"] == {}


def test_create_directive_with_targeting(client):
    r = client.post("/api/memory", json={
        "project": "M21B", "type": "directive",
        "title": "Regla cobranzas", "content": "hacelo asi",
        "enforcement": "always", "priority": 5,
        "applies_to": {"agent_types": ["developer"], "title_keywords": ["cobranzas"]},
    })
    assert r.status_code == 201, r.get_data(as_text=True)
    mid = r.get_json()["memory_id"]
    row = client.get(f"/api/memory/{mid}").get_json()
    assert row["type"] == "directive"
    assert row["enforcement"] == "always"
    assert row["priority"] == 5
    assert row["applies_to"]["agent_types"] == ["developer"]


def test_directive_without_targeting_rejected(client):
    r = client.post("/api/memory", json={
        "project": "M21C", "type": "directive",
        "title": "sin target", "content": "x",
        "enforcement": "always", "applies_to": {},
    })
    assert r.status_code == 400


def test_always_only_for_directive(client):
    r = client.post("/api/memory", json={
        "project": "M21D", "type": "bugfix",
        "title": "obs always", "content": "x", "enforcement": "always",
    })
    assert r.status_code == 400


def test_applies_to_unknown_key_rejected(client):
    r = client.post("/api/memory", json={
        "project": "M21E", "type": "directive",
        "title": "t", "content": "c", "enforcement": "always",
        "applies_to": {"bogus": ["x"]},
    })
    assert r.status_code == 400


def test_applies_to_non_list_value_rejected(client):
    r = client.post("/api/memory", json={
        "project": "M21F", "type": "directive",
        "title": "t", "content": "c", "enforcement": "always",
        "applies_to": {"agent_types": "developer"},
    })
    assert r.status_code == 400


def test_directive_default_enforcement_is_suggest(client):
    r = client.post("/api/memory", json={
        "project": "M21G", "type": "directive",
        "title": "borrador", "content": "x",
        "applies_to": {"agent_types": ["developer"]},
    })
    assert r.status_code == 201
    mid = r.get_json()["memory_id"]
    row = client.get(f"/api/memory/{mid}").get_json()
    assert row["enforcement"] == "suggest"
