"""Plan 209 F3 — Enfoque B: relleno determinista por retrieval local.

B nunca inventa: cada paso sale de un fragmento recuperado y cita su fuente.
Sin grounding, degrada honestamente.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

from services.validation_playbook import (  # noqa: E402
    DEGRADED_MESSAGE,
    MARKER_COMMENT,
    SECTION_TITLE,
    ValidationPlaybook,
    ValidationStep,
    assert_no_invented_steps,
    build_from_grounding,
    render_playbook_html,
)

_CATALOG = [
    {"name": "IncHost", "kind": "batch",
     "purpose": "Asignar obligaciones al host de incidencias y mostrarlas en el inicio"},
    {"name": "RsExtrae", "kind": "batch", "purpose": "Extraer clientes y obligaciones"},
]


@pytest.fixture(autouse=True)
def _sin_docs(monkeypatch):
    """Por defecto docs_rag no aporta (proyecto sin índice); cada test lo overridea."""
    from services import docs_rag

    monkeypatch.setattr(docs_rag, "search", lambda *a, **kw: [], raising=True)


def test_build_sin_grounding_degrada():
    pb = build_from_grounding(ticket_title="Alta de cliente", ticket_text="",
                              project_name="RSPACIFICO", process_catalog=None)

    assert pb.status == "degraded"
    assert pb.steps == []
    assert pb.degraded_reason == "no_grounding"
    assert pb.confidence == 0.0


def test_build_con_catalogo_grounded():
    pb = build_from_grounding(
        ticket_title="Asignar obligacion al host de incidencias",
        ticket_text="obligaciones inicio",
        project_name="RSPACIFICO",
        process_catalog=_CATALOG,
    )

    assert pb.status == "enriched", pb
    assert pb.steps, "con catálogo afín debe haber pasos"
    assert all(s.source.startswith("catalog:") for s in pb.steps), [s.source for s in pb.steps]
    assert any("IncHost" in s.source for s in pb.steps)
    assert pb.sources
    assert 0.0 < pb.confidence <= 1.0


def test_build_con_docs_grounded(monkeypatch):
    from services import docs_rag

    class Hit:
        file_path = "docs/funcional/alta-cliente.md"
        section_heading = "Alta de cliente"
        chunk_text = "Para dar de alta un cliente entrá a Clientes > Nuevo y completá el RUT."
        score = 0.9

    monkeypatch.setattr(docs_rag, "search", lambda *a, **kw: [Hit()], raising=True)

    pb = build_from_grounding(ticket_title="Alta de cliente", ticket_text="",
                              project_name="RSPACIFICO", process_catalog=None)

    assert pb.status == "enriched"
    assert len(pb.steps) == 1
    assert pb.steps[0].source.startswith("func-docs:")
    assert "Alta de cliente" in pb.steps[0].source


def test_build_nunca_inventa():
    entradas = [
        {"ticket_title": "x", "ticket_text": "", "process_catalog": None},
        {"ticket_title": "Asignar obligacion", "ticket_text": "inicio", "process_catalog": _CATALOG},
        {"ticket_title": "", "ticket_text": "", "process_catalog": []},
        {"ticket_title": "zzz sin relacion alguna", "ticket_text": "", "process_catalog": _CATALOG},
    ]
    for kw in entradas:
        pb = build_from_grounding(project_name="RSPACIFICO", **kw)
        assert assert_no_invented_steps(pb) == [], f"{kw} produjo pasos sin fuente"
        if pb.status == "degraded":
            assert pb.steps == []


def test_build_docs_que_lanza_no_rompe(monkeypatch):
    from services import docs_rag

    def _boom(*a, **kw):
        raise RuntimeError("índice inexistente")

    monkeypatch.setattr(docs_rag, "search", _boom, raising=True)

    pb = build_from_grounding(ticket_title="Asignar obligacion", ticket_text="",
                              project_name="RSPACIFICO", process_catalog=_CATALOG)

    assert pb.status == "enriched", "si docs falla, el catálogo igual sirve"


def test_render_degradado_sin_ol():
    pb = ValidationPlaybook(status="degraded", steps=[], sources=[], confidence=0.0,
                            degraded_reason="no_grounding")
    html = render_playbook_html(pb)

    assert DEGRADED_MESSAGE in html
    assert "<ol>" not in html
    assert "<li" not in html
    assert SECTION_TITLE in html


def test_render_idempotente():
    pb = ValidationPlaybook(status="enriched",
                            steps=[ValidationStep(1, "Entrar", "Se abre", "func-docs:x")],
                            sources=["func-docs:x"], confidence=0.6, degraded_reason=None)
    html = render_playbook_html(pb)

    assert html.startswith(MARKER_COMMENT)
    assert 'data-stacky="validation-playbook"' in html
    assert 'data-source="func-docs:x"' in html
    assert "<ol>" in html


def test_render_escapa_html():
    pb = ValidationPlaybook(
        status="enriched",
        steps=[ValidationStep(1, '<script>alert("x")</script>', "ok & fin", 'a"b')],
        sources=["<b>s</b>"], confidence=0.5, degraded_reason=None,
    )
    html = render_playbook_html(pb)

    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "&amp;" in html
