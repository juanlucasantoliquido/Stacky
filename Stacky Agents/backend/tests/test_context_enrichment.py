"""Tests del pipeline de enriquecimiento extraído (services/context_enrichment.py).

Cubre:
  - build_ticket_context_text: render legible del ticket + blocks.
  - enrich_blocks: inyección de ado-epic-structured (functional + Epic) e
    idempotencia, ejercitando la función real contra una DB sqlite in-memory.

A diferencia de test_functional_epic_context_injection.py (que replica la lógica),
estos tests llaman a la función productiva, de modo que un cambio de comportamiento
en el pipeline rompe el test.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
# Mantener el enriquecimiento hermético: sin llamadas de red a ADO ni similares.
os.environ["STACKY_SIMILAR_TICKETS_ENABLED"] = "false"
os.environ["ADO_CONTEXT_ENRICH_AGENTS"] = "__none__"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_ADO_SEQ = iter(range(900000, 999999))


@pytest.fixture(scope="module")
def app_ctx():
    """Inicializa la app (y la DB sqlite in-memory) una vez por módulo."""
    from app import create_app

    app = create_app()
    app.config.update(TESTING=True)
    yield app


# ---------------------------------------------------------------------------
# build_ticket_context_text (puro, sin DB)
# ---------------------------------------------------------------------------

def test_build_ticket_context_text_includes_header_and_description():
    from services import context_enrichment

    txt = context_enrichment.build_ticket_context_text(
        ado_id=4321,
        title="Marca oficial en direcciones",
        description="Como operador quiero ver la marca oficial.",
        work_item_type="Epic",
        blocks=[],
    )
    assert "ADO-4321" in txt
    assert "Epic" in txt
    assert "Marca oficial en direcciones" in txt
    assert "Como operador quiero ver la marca oficial." in txt


def test_build_ticket_context_text_renders_blocks_with_headers():
    from services import context_enrichment

    txt = context_enrichment.build_ticket_context_text(
        ado_id=10,
        title="T",
        description=None,
        work_item_type="Task",
        blocks=[
            {"id": "ado-epic-structured", "title": "Epic ADO-9", "content": "epic_id: 9"},
            {"id": "operator-note", "title": "Nota del operador", "content": "hacelo con cuidado"},
            {"id": "empty"},  # sin título ni contenido → se omite
        ],
    )
    assert "Epic ADO-9" in txt
    assert "epic_id: 9" in txt
    assert "Nota del operador" in txt
    assert "hacelo con cuidado" in txt
    # el bloque vacío no agrega ruido
    assert "#### \n" not in txt


def test_build_ticket_context_text_empty_when_no_data():
    from services import context_enrichment

    txt = context_enrichment.build_ticket_context_text(
        ado_id=None, title=None, description=None, work_item_type=None, blocks=[]
    )
    # Siempre incluye al menos el encabezado de ticket (aunque sin ado id)
    assert "ticket sin ado id" in txt.lower()


# ---------------------------------------------------------------------------
# enrich_blocks (con DB real)
# ---------------------------------------------------------------------------

def _make_ticket(*, work_item_type: str, ado_id=None, title="ticket", description="desc"):
    from db import session_scope
    from models import Ticket

    if ado_id is None:
        ado_id = next(_ADO_SEQ)
    with session_scope() as session:
        t = Ticket(
            ado_id=ado_id,
            project="RSPacifico",
            title=title,
            ado_state="Active",
            description=description,
            work_item_type=work_item_type,
        )
        session.add(t)
        session.flush()
        return t.id


def test_enrich_blocks_injects_epic_structured_for_functional_epic(app_ctx):
    from services import context_enrichment

    ticket_id = _make_ticket(work_item_type="Epic", title="Epic de prueba", description="cuerpo")
    blocks, ado_stats = context_enrichment.enrich_blocks(
        ticket_id=ticket_id,
        agent_type="functional",
        raw_blocks=[],
        project_ctx=None,
    )
    ids = {b.get("id") for b in blocks}
    assert "ado-epic-structured" in ids
    epic_block = next(b for b in blocks if b.get("id") == "ado-epic-structured")
    assert "Epic de prueba" in epic_block["title"]
    assert "epic_ado_id:" in epic_block["content"]
    assert "epic_output_dir: Agentes/outputs/epic-" in epic_block["content"]
    assert "no uses etiquetas humanas" in epic_block["content"]
    assert "cuerpo" in epic_block["content"]
    # ado_context deshabilitado por env → stats marca skipped, sin llamada de red
    assert ado_stats is not None and ado_stats.get("skipped") is True


def test_enrich_blocks_idempotent_epic(app_ctx):
    from services import context_enrichment

    ticket_id = _make_ticket(work_item_type="Epic")
    existing = [{"id": "ado-epic-structured", "title": "ya", "content": "ya"}]
    blocks, _ = context_enrichment.enrich_blocks(
        ticket_id=ticket_id,
        agent_type="functional",
        raw_blocks=existing,
        project_ctx=None,
    )
    epic_blocks = [b for b in blocks if b.get("id") == "ado-epic-structured"]
    assert len(epic_blocks) == 1
    assert epic_blocks[0]["content"] == "ya"  # no se re-inyectó


def test_enrich_blocks_no_epic_for_task(app_ctx):
    from services import context_enrichment

    ticket_id = _make_ticket(work_item_type="Task")
    blocks, _ = context_enrichment.enrich_blocks(
        ticket_id=ticket_id,
        agent_type="functional",
        raw_blocks=[],
        project_ctx=None,
    )
    ids = {b.get("id") for b in blocks}
    assert "ado-epic-structured" not in ids


def test_enrich_blocks_no_epic_for_non_functional_agent(app_ctx):
    from services import context_enrichment

    ticket_id = _make_ticket(work_item_type="Epic")
    blocks, _ = context_enrichment.enrich_blocks(
        ticket_id=ticket_id,
        agent_type="technical",
        raw_blocks=[],
        project_ctx=None,
    )
    ids = {b.get("id") for b in blocks}
    assert "ado-epic-structured" not in ids


def test_enrich_blocks_does_not_mutate_input(app_ctx):
    from services import context_enrichment

    ticket_id = _make_ticket(work_item_type="Epic")
    original = []
    context_enrichment.enrich_blocks(
        ticket_id=ticket_id,
        agent_type="functional",
        raw_blocks=original,
        project_ctx=None,
    )
    assert original == []  # la lista de entrada no se muta
