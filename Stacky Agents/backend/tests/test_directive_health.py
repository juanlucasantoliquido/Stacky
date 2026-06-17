"""M3.2 — Salud de directivas: overlapping, budget_pressure, stale.

Cubre:
  - dos directivas con el mismo targeting → overlapping
  - directivas que suman > 80% del slice → budget_pressure con bandera
  - directiva con review_after vencido → stale
  - proyecto sin directivas → todo vacío (no error)
  - GET /api/memory/directive-health
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta
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


def _mk_directive(project, *, title, content, applies_to, enforcement="always",
                  review_after=None):
    import json as _json
    from db import session_scope
    from services import memory_store

    mid = memory_store.save_observation(
        project=project, type="directive", title=title, content=content,
        author_email="op@x.com", review_after=review_after,
    )
    with session_scope() as s:
        row = s.query(memory_store.StackyMemoryObservation).filter_by(memory_id=mid).first()
        row.enforcement = enforcement
        row.applies_to_json = _json.dumps(applies_to)
    return mid


def test_empty_project_is_all_empty(client):
    from services import memory_store

    h = memory_store.directive_health("M32EMPTY")
    assert h["overlapping"] == []
    assert h["stale"] == []
    assert isinstance(h["budget_pressure"], list)


def test_overlapping_same_targeting(client):
    from services import memory_store

    project = "M32OVL"
    a = _mk_directive(project, title="A", content="x",
                      applies_to={"agent_types": ["developer"], "work_item_types": ["Bug"]})
    b = _mk_directive(project, title="B", content="y",
                      applies_to={"agent_types": ["developer"], "work_item_types": ["Bug"]})
    h = memory_store.directive_health(project)
    pairs = [set(o["ids"]) for o in h["overlapping"]]
    assert {a, b} in pairs


def test_stale_review_overdue(client):
    from services import memory_store

    project = "M32STALE"
    past = datetime.utcnow() - timedelta(days=2)
    mid = _mk_directive(project, title="vieja", content="x",
                        applies_to={"agent_types": ["developer"]}, review_after=past)
    h = memory_store.directive_health(project)
    stale_ids = {s["id"] for s in h["stale"]}
    assert mid in stale_ids


def test_budget_pressure_flag(client):
    from services import memory_store

    project = "M32BUD"
    # cap chico para forzar ratio alto
    os.environ["STACKY_MEMORY_CAPS_JSON"] = '{"developer": [10, 1000]}'
    os.environ["STACKY_MEMORY_DIRECTIVE_MAX_CHARS"] = "500"
    memory_store._invalidate_caps_cache()
    try:
        _mk_directive(project, title="grande",
                      content="contenido muy largo del operador " * 30,
                      applies_to={"agent_types": ["developer"]})
        h = memory_store.directive_health(project)
        flagged = [b for b in h["budget_pressure"] if b.get("ratio", 0) > 0.8]
        assert flagged, h["budget_pressure"]
    finally:
        os.environ.pop("STACKY_MEMORY_CAPS_JSON", None)
        os.environ.pop("STACKY_MEMORY_DIRECTIVE_MAX_CHARS", None)
        memory_store._invalidate_caps_cache()


def test_endpoint(client):
    project = "M32EP"
    _mk_directive(project, title="d", content="x",
                  applies_to={"agent_types": ["developer"]})
    r = client.get(f"/api/memory/directive-health?project={project}")
    assert r.status_code == 200
    body = r.get_json()
    assert "overlapping" in body and "budget_pressure" in body and "stale" in body
