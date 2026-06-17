"""M0.3 — Caducidad/revisión: expires_at deja de ser letra muerta.

Cubre:
  - memoria con expires_at en el pasado → no aparece en search ni get_context_for_run
  - memoria sin fechas → comportamiento actual exacto (byte-idéntico)
  - memoria con review_after vencido → mark_stale_for_review la pasa a needs_review
    (NUNCA deleted); las no vencidas quedan intactas
  - save_observation acepta review_after (param aditivo)
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(scope="module")
def app_ctx():
    from app import create_app

    app = create_app()
    app.config.update(TESTING=True)
    yield app


def _past():
    return datetime.utcnow() - timedelta(days=1)


def _future():
    return datetime.utcnow() + timedelta(days=30)


def test_expired_memory_not_in_search_or_context(app_ctx):
    from services import memory_store

    project = "MEM_EXP1"
    live = memory_store.save_observation(
        project=project, type="bugfix", title="vigente facturacion",
        content="regla de facturacion vigente", author_email="op@x.com",
    )
    expired = memory_store.save_observation(
        project=project, type="bugfix", title="expirada facturacion",
        content="regla de facturacion expirada", author_email="op@x.com",
        expires_at=_past(),
    )
    found_ids = {r["memory_id"] for r in memory_store.search(project=project, query_text="facturacion")}
    assert live in found_ids
    assert expired not in found_ids

    ctx = memory_store.get_context_for_run(
        project=project, agent_type="developer", query_text="facturacion"
    )
    assert expired not in ctx["memory_ids"]
    assert live in ctx["memory_ids"]


def test_memory_with_future_expiry_still_appears(app_ctx):
    from services import memory_store

    project = "MEM_EXP2"
    mid = memory_store.save_observation(
        project=project, type="bugfix", title="cobranzas futuro",
        content="regla cobranzas con expiracion futura", author_email="op@x.com",
        expires_at=_future(),
    )
    found = {r["memory_id"] for r in memory_store.search(project=project, query_text="cobranzas")}
    assert mid in found


def test_no_dates_behaves_unchanged(app_ctx):
    from services import memory_store

    project = "MEM_EXP3"
    mid = memory_store.save_observation(
        project=project, type="bugfix", title="sin fechas",
        content="memoria sin fechas de caducidad", author_email="op@x.com",
    )
    found = {r["memory_id"] for r in memory_store.search(project=project, query_text="caducidad")}
    assert mid in found


def test_mark_stale_for_review_moves_to_needs_review(app_ctx):
    from services import memory_store

    project = "MEM_REV1"
    overdue = memory_store.save_observation(
        project=project, type="bugfix", title="revision vencida",
        content="esta necesita revision", author_email="op@x.com",
        review_after=_past(),
    )
    fresh = memory_store.save_observation(
        project=project, type="bugfix", title="revision al dia",
        content="esta no necesita revision", author_email="op@x.com",
        review_after=_future(),
    )
    nofecha = memory_store.save_observation(
        project=project, type="bugfix", title="sin review",
        content="sin review_after", author_email="op@x.com",
    )

    n = memory_store.mark_stale_for_review(project=project)
    assert n == 1

    assert memory_store.get(overdue)["status"] == "needs_review"
    assert memory_store.get(fresh)["status"] == "active"
    assert memory_store.get(nofecha)["status"] == "active"


def test_mark_stale_never_deletes(app_ctx):
    from services import memory_store

    project = "MEM_REV2"
    overdue = memory_store.save_observation(
        project=project, type="bugfix", title="vencida",
        content="vencida de revision", author_email="op@x.com",
        review_after=_past(),
    )
    memory_store.mark_stale_for_review(project=project)
    row = memory_store.get(overdue)
    assert row["status"] == "needs_review"
    assert row["status"] != "deleted"
