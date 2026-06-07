"""Tests de inyección de memoria en el pipeline de contexto — Fase A.

Verifica que `context_enrichment.enrich_blocks`:
  - con STACKY_MEMORY_INJECTION_ENABLED=true, PREPEND-ea el bloque
    `stacky-memory` en índice 0 (antes que cualquier otro bloque),
  - con el flag OFF (default), NO inyecta nada,
  - no inyecta memoria de otro proyecto.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
# Mantener hermético: sin red ADO, sin similares, sin client-profile.
os.environ["STACKY_SIMILAR_TICKETS_ENABLED"] = "false"
os.environ["ADO_CONTEXT_ENRICH_AGENTS"] = "__none__"
os.environ["STACKY_INJECT_CLIENT_PROFILE"] = "false"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_ADO_SEQ = iter(range(800000, 899999))


@pytest.fixture(scope="module")
def app_ctx():
    from app import create_app

    app = create_app()
    app.config.update(TESTING=True)
    yield app


def _make_ticket(*, project: str, title: str, description: str, work_item_type: str = "Task"):
    from db import session_scope
    from models import Ticket

    with session_scope() as session:
        t = Ticket(
            ado_id=next(_ADO_SEQ),
            project=project,
            title=title,
            ado_state="Active",
            description=description,
            work_item_type=work_item_type,
        )
        session.add(t)
        session.flush()
        return t.id


def test_memory_block_prepended_at_index_0_when_enabled(app_ctx, monkeypatch):
    from services import context_enrichment, memory_store

    project = "MEM_INJ_1"
    memory_store.save_observation(
        project=project,
        type="bugfix",
        title="Watcher de outputs",
        content="chequear ordinal vs ADO id al detectar el comment.html generado",
    )
    ticket_id = _make_ticket(
        project=project,
        title="Falla detección de archivos del Developer",
        description="el comment.html no se detecta al completar",
    )

    monkeypatch.setenv("STACKY_MEMORY_INJECTION_ENABLED", "true")
    blocks, _ = context_enrichment.enrich_blocks(
        ticket_id=ticket_id,
        agent_type="developer",
        raw_blocks=[{"id": "operator-note", "title": "Nota", "content": "ojo"}],
        project_ctx=None,
    )
    assert blocks[0]["id"] == "stacky-memory"
    assert "ordinal vs ADO id" in blocks[0]["content"]
    # el bloque original sigue presente, después de la memoria
    assert any(b.get("id") == "operator-note" for b in blocks)


def test_memory_not_injected_when_flag_off(app_ctx, monkeypatch):
    from services import context_enrichment, memory_store

    project = "MEM_INJ_2"
    memory_store.save_observation(
        project=project, type="pattern", title="X", content="contenido de memoria que no debe aparecer"
    )
    ticket_id = _make_ticket(
        project=project, title="ticket", description="desc"
    )

    monkeypatch.delenv("STACKY_MEMORY_INJECTION_ENABLED", raising=False)
    blocks, _ = context_enrichment.enrich_blocks(
        ticket_id=ticket_id,
        agent_type="developer",
        raw_blocks=[],
        project_ctx=None,
    )
    assert all(b.get("id") != "stacky-memory" for b in blocks)


def test_memory_does_not_leak_across_projects(app_ctx, monkeypatch):
    from services import context_enrichment, memory_store

    memory_store.save_observation(
        project="MEM_INJ_OTHER",
        type="pattern",
        title="Secreto de otro proyecto",
        content="esto pertenece a otro proyecto y no debe filtrarse",
    )
    ticket_id = _make_ticket(
        project="MEM_INJ_3", title="ticket propio", description="contenido propio"
    )

    monkeypatch.setenv("STACKY_MEMORY_INJECTION_ENABLED", "true")
    blocks, _ = context_enrichment.enrich_blocks(
        ticket_id=ticket_id,
        agent_type="developer",
        raw_blocks=[],
        project_ctx=None,
    )
    mem_blocks = [b for b in blocks if b.get("id") == "stacky-memory"]
    # No hay memoria del proyecto propio → no se inyecta, y nunca la de otro proyecto.
    assert mem_blocks == [] or "otro proyecto" not in mem_blocks[0]["content"]
