"""Tests del store de memoria colaborativa (services/memory_store.py) — Fase A.

Cubre:
  - save_observation + get
  - upsert_by_topic_key incrementa revision_count y mantiene una sola fila
  - upsert personal scope con autores distintos NO se pisa
  - search TF-IDF encuentra por contenido y respeta status='active'
  - search topic_key exacto
  - mark_relation('supersedes') marca la vieja como superseded → no aparece
  - get_context_for_run: cap por cantidad, supresión de conflicts_with activo-activo
"""
from __future__ import annotations

import os
import sys
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


def test_save_and_get(app_ctx):
    from services import memory_store

    mid = memory_store.save_observation(
        project="MEM_T1",
        type="bugfix",
        title="Detección de artefactos en Developer",
        content="What: el watcher no detectaba el comment.html\nLearned: chequear ordinal vs ADO id",
        tags=["developer", "output-watcher"],
        author_email="dev@empresa.com",
        author_role="developer",
    )
    assert mid.startswith("mem-")
    row = memory_store.get(mid)
    assert row is not None
    assert row["type"] == "bugfix"
    assert row["status"] == "active"
    assert row["revision_count"] == 1
    assert "developer" in row["tags"]
    assert row["author_email"] == "dev@empresa.com"


def test_upsert_does_not_demote_active_to_draft(app_ctx):
    from services import memory_store

    mid = memory_store.save_observation(
        project="MEM_DEMOTE",
        type="bugfix",
        title="Approved",
        content="approved content",
        topic_key="session/demote",
        scope="project",
        status="active",
    )
    # Re-run: captura DRAFT del mismo topic_key. No debe degradar ni pisar.
    same = memory_store.save_observation(
        project="MEM_DEMOTE",
        type="bugfix",
        title="Re-run draft",
        content="rerun draft content",
        topic_key="session/demote",
        scope="project",
        status="draft",
    )

    assert same == mid
    row = memory_store.get(mid)
    assert row["status"] == "active"
    assert row["content"] == "approved content"


def test_upsert_by_topic_key_increments_revision(app_ctx):
    from services import memory_store

    mid1 = memory_store.save_observation(
        project="MEM_T2",
        type="decision",
        title="Política DML",
        content="v1",
        topic_key="policy/db-dml-runtime",
    )
    mid2 = memory_store.save_observation(
        project="MEM_T2",
        type="decision",
        title="Política DML (actualizada)",
        content="v2",
        topic_key="policy/db-dml-runtime",
    )
    assert mid1 == mid2  # misma fila
    row = memory_store.get(mid1)
    assert row["revision_count"] == 2
    assert row["content"] == "v2"

    listed = memory_store.list_observations(project="MEM_T2", type="decision")
    assert len(listed) == 1  # una sola fila vigente


def test_personal_scope_does_not_collide_across_authors(app_ctx):
    from services import memory_store

    mid_a = memory_store.save_observation(
        project="MEM_T3",
        type="preference",
        title="Estilo A",
        content="prefiere bullets",
        scope="personal",
        topic_key="preference/output-style",
        author_email="ana@empresa.com",
    )
    mid_b = memory_store.save_observation(
        project="MEM_T3",
        type="preference",
        title="Estilo B",
        content="prefiere prosa",
        scope="personal",
        topic_key="preference/output-style",
        author_email="juan@empresa.com",
    )
    assert mid_a != mid_b  # no se pisaron entre autores distintos
    assert memory_store.get(mid_a)["revision_count"] == 1
    assert memory_store.get(mid_b)["revision_count"] == 1


def test_search_finds_by_content_and_filters_status(app_ctx):
    from services import memory_store

    memory_store.save_observation(
        project="MEM_T4",
        type="pattern",
        title="Idempotencia en outbox",
        content="usar mutation_id unico para dedupe de publicaciones repetidas",
    )
    draft = memory_store.save_observation(
        project="MEM_T4",
        type="pattern",
        title="Patrón en draft",
        content="idempotencia draft que no debe aparecer",
        status="draft",
    )

    hits = memory_store.search(project="MEM_T4", query_text="idempotencia outbox dedupe")
    ids = {h["memory_id"] for h in hits}
    assert any(h["title"].startswith("Idempotencia") for h in hits)
    # el draft no se inyecta (status != active)
    assert draft not in ids


def test_search_topic_key_exact(app_ctx):
    from services import memory_store

    mid = memory_store.save_observation(
        project="MEM_T5",
        type="decision",
        title="Naming de ramas",
        content="stacky-memory/<project>",
        topic_key="decision/branch-naming",
    )
    hits = memory_store.search(project="MEM_T5", query_text="decision/branch-naming")
    assert len(hits) == 1
    assert hits[0]["memory_id"] == mid
    assert hits[0]["_score"] == 1.0


def test_supersedes_hides_old_memory(app_ctx):
    from services import memory_store

    old = memory_store.save_observation(
        project="MEM_T6",
        type="client_policy",
        title="Política vieja",
        content="DML directo permitido",
    )
    new = memory_store.save_observation(
        project="MEM_T6",
        type="client_policy",
        title="Política nueva",
        content="DML solo vía procedure",
    )
    memory_store.mark_relation(
        project="MEM_T6",
        source_memory_id=new,
        target_memory_id=old,
        relation="supersedes",
        reason="reemplaza la anterior",
    )
    # la vieja quedó superseded
    assert memory_store.get(old)["status"] == "superseded"
    ctx = memory_store.get_context_for_run(
        project="MEM_T6", agent_type="developer", query_text="DML política"
    )
    assert old not in ctx["memory_ids"]
    assert new in ctx["memory_ids"]


def test_conflicts_with_suppresses_both(app_ctx):
    from services import memory_store

    a = memory_store.save_observation(
        project="MEM_T7", type="decision", title="Opción A", content="usar enfoque alfa para deploy"
    )
    b = memory_store.save_observation(
        project="MEM_T7", type="decision", title="Opción B", content="usar enfoque beta para deploy"
    )
    memory_store.mark_relation(
        project="MEM_T7",
        source_memory_id=a,
        target_memory_id=b,
        relation="conflicts_with",
        reason="contradicción sin resolver",
    )
    ctx = memory_store.get_context_for_run(
        project="MEM_T7", agent_type="developer", query_text="enfoque deploy"
    )
    assert a not in ctx["memory_ids"]
    assert b not in ctx["memory_ids"]
    assert ctx["suppressed_hits"] >= 2


def test_get_context_respects_agent_cap(app_ctx):
    from services import memory_store

    for i in range(10):
        memory_store.save_observation(
            project="MEM_T8",
            type="pattern",
            title=f"Patrón deploy {i}",
            content=f"detalle de deploy numero {i} con idempotencia",
        )
    # business cap = 6 memorias
    ctx = memory_store.get_context_for_run(
        project="MEM_T8", agent_type="business", query_text="deploy idempotencia patrón"
    )
    assert ctx["active_hits"] <= 6
    assert len(ctx["memory_ids"]) == ctx["active_hits"]
    assert ctx["content"]
