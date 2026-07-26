"""Plan 209 F5 — Sentinel anti-alucinación.

Convierte el principio "ningún paso sin fuente" en un invariante ejecutable:
ningún camino (A ni B) puede publicar un paso huérfano, y sin evidencia el
sistema degrada con el mensaje honesto exacto.
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
    SECTION_TITLE,
    ValidationPlaybook,
    ValidationStep,
    assert_no_invented_steps,
    assess_grounding,
    build_from_grounding,
    detect,
    render_playbook_html,
)

_CATALOG = [
    {"name": "IncHost", "kind": "batch", "purpose": "Asignar obligaciones y verlas en el inicio"},
    {"name": "RsExtrae", "kind": "batch", "purpose": "Extraer clientes y obligaciones del host"},
]


@pytest.fixture(autouse=True)
def _sin_docs(monkeypatch):
    from services import docs_rag

    monkeypatch.setattr(docs_rag, "search", lambda *a, **kw: [], raising=True)


def test_build_sin_grounding_es_degradado_con_mensaje_exacto():
    pb = build_from_grounding(ticket_title="lo que sea", ticket_text="",
                              project_name="RSPACIFICO", process_catalog=None)

    assert pb.status == "degraded"
    assert DEGRADED_MESSAGE in render_playbook_html(pb)


@pytest.mark.parametrize(
    "title, catalog",
    [
        ("Asignar obligacion al host", _CATALOG),
        ("Extraer clientes", _CATALOG),
        ("obligaciones inicio host", _CATALOG),
    ],
)
def test_ningun_step_sin_source_en_enriched(title, catalog):
    pb = build_from_grounding(ticket_title=title, ticket_text="",
                              project_name="RSPACIFICO", process_catalog=catalog)

    assert assert_no_invented_steps(pb) == []
    if pb.status == "enriched":
        assert pb.steps, "un playbook enriched sin pasos no tiene sentido"
        assert all(s.source.strip() for s in pb.steps)


def test_assess_elimina_steps_sin_source():
    pb = ValidationPlaybook(
        status="agent_provided",
        steps=[ValidationStep(1, "con fuente", "r", "func-docs:a"),
               ValidationStep(2, "sin fuente", "r", ""),
               ValidationStep(3, "otra con fuente", "r", "catalog:IncHost")],
        sources=[], confidence=0.6, degraded_reason=None,
    )
    out, warnings = assess_grounding(pb, None)

    assert out.status == "agent_provided"
    assert [s.action for s in out.steps] == ["con fuente", "otra con fuente"]
    assert [s.n for s in out.steps] == [1, 2], "los pasos supervivientes se renumeran"
    assert len(warnings) == 1

    solo_huerfanos = ValidationPlaybook(
        status="agent_provided", steps=[ValidationStep(1, "a", "r", "")],
        sources=[], confidence=0.6, degraded_reason=None,
    )
    out2, _ = assess_grounding(solo_huerfanos, None)
    assert out2.status == "degraded"
    assert out2.steps == []


def test_proceso_fuera_de_catalogo_no_se_publica_como_grounded():
    pb = ValidationPlaybook(
        status="agent_provided",
        steps=[ValidationStep(1, "Ejecutá el proceso Fantasma desde el menú", "r", "func-docs:a")],
        sources=[], confidence=0.9, degraded_reason=None,
    )
    out, warnings = assess_grounding(pb, _CATALOG)

    assert any("process_not_in_catalog" in w for w in warnings), warnings
    assert out.status == "degraded", "si el único paso cita un proceso inexistente, se degrada"
    assert out.steps == []


def test_render_degradado_no_tiene_pasos():
    pb = ValidationPlaybook(status="degraded", steps=[], sources=[], confidence=0.0,
                            degraded_reason="no_grounding")
    html = render_playbook_html(pb)

    assert "<li" not in html
    assert "<ol" not in html
    assert SECTION_TITLE in html


def test_detect_agente_con_pasos_sin_fuente_degrada():
    """A entrega pasos huérfanos ⇒ el pipeline completo termina en degraded."""
    html = (f'<section data-stacky="validation-playbook" data-confidence="1.0">'
            f"<h2>{SECTION_TITLE}</h2><ol>"
            f"<li>Entrá a la pantalla mágica</li>"
            f"<li>Apretá el botón que no existe</li>"
            f"</ol></section>")

    pb = detect(html)
    assert pb.status == "agent_provided"
    assert len(pb.steps) == 2

    out, warnings = assess_grounding(pb, None)
    assert out.status == "degraded", "pasos sin fuente NO se publican como válidos"
    assert out.steps == []
    assert len(warnings) == 2
    assert DEGRADED_MESSAGE in render_playbook_html(out)


def test_invariante_todo_camino_es_grounded_o_degradado():
    """Property-style: para cualquier entrada, o hay fuentes en todos los pasos, o hay 0 pasos."""
    entradas = [
        None, "", "<p>nada</p>",
        '<section data-stacky="validation-playbook"><ol><li>huerfano</li></ol></section>',
        f'<section data-stacky="validation-playbook"><ol>'
        f'<li data-source="func-docs:x">ok</li><li>huerfano</li></ol></section>',
        f'<section data-stacky="validation-playbook"><p>{DEGRADED_MESSAGE}</p></section>',
    ]
    for html in entradas:
        pb = detect(html)
        if pb is None:
            pb = build_from_grounding(ticket_title="x", ticket_text="",
                                      project_name="RSPACIFICO", process_catalog=None)
        out, _ = assess_grounding(pb, _CATALOG, source_text=html)
        assert assert_no_invented_steps(out) == [], f"{html!r} produjo pasos sin fuente"
        if out.status == "degraded":
            assert out.steps == []
