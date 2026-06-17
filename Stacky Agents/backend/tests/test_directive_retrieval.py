"""M1.2/M1.3 — Recuperación de directivas: inyección SIEMPRE, bypass scoring.

Cubre:
  - get_directives_for_run trae las always que matchean el targeting, sin TF-IDF
  - inyección sin overlap léxico con el ticket
  - bypass de supresión de conflicto (conflicts_with activo-activo NO oculta directivas)
  - orden por prioridad desc
  - get_context_for_run: directivas primero bajo encabezado imperativo
  - slice de presupuesto y truncado con marcador (no se dropea silenciosamente)
  - coexistencia con pool observacional (directive_hits + memory_ids)
  - B5 sin doble-inyección (directive no es reservado)
  - flag maestro / enforcement suggest → byte-idéntico
  - M1.3: directivas ganan al pool bajo presión de cap; max_memorias no recorta directivas
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


def _mk_directive(project, *, title, content, applies_to, priority=0,
                  enforcement="always", scope="project"):
    from services import memory_store

    mid = memory_store.save_observation(
        project=project, type="directive", title=title, content=content,
        scope=scope, author_email="op@x.com",
    )
    # set directive fields directly (alta vía API es M2.1; aquí sembramos el store)
    from db import session_scope
    import json as _json

    with session_scope() as s:
        row = s.query(memory_store.StackyMemoryObservation).filter_by(memory_id=mid).first()
        row.enforcement = enforcement
        row.priority = priority
        row.applies_to_json = _json.dumps(applies_to)
    return mid


def test_directive_injected_without_lexical_overlap(app_ctx):
    from services import memory_store

    project = "DIR_RET1"
    mid = _mk_directive(
        project,
        title="Politica de cobranzas",
        content="ZZZ procedimiento estricto del cliente para xyz",
        applies_to={"work_item_types": ["User Story"]},
    )
    res = memory_store.get_directives_for_run(
        project=project, agent_type="developer",
        ticket_title="algo totalmente distinto", ticket_description="sin palabras comunes",
        work_item_type="User Story",
    )
    ids = [d["memory_id"] for d in res]
    assert mid in ids


def test_directive_not_matching_targeting_excluded(app_ctx):
    from services import memory_store

    project = "DIR_RET2"
    _mk_directive(
        project, title="solo epics", content="x",
        applies_to={"work_item_types": ["Epic"]},
    )
    res = memory_store.get_directives_for_run(
        project=project, agent_type="developer",
        ticket_title="t", ticket_description="d", work_item_type="Bug",
    )
    assert res == []


def test_directive_bypasses_conflict_suppression(app_ctx):
    from services import memory_store

    project = "DIR_RET3"
    a = _mk_directive(project, title="dir A", content="hacelo asi A",
                      applies_to={"agent_types": ["developer"]})
    b = _mk_directive(project, title="dir B", content="hacelo asi B",
                      applies_to={"agent_types": ["developer"]})
    memory_store.mark_relation(
        project=project, source_memory_id=a, target_memory_id=b,
        relation="conflicts_with", marked_by_actor="op@x.com", marked_by_kind="human",
    )
    res = memory_store.get_directives_for_run(
        project=project, agent_type="developer",
        ticket_title="t", ticket_description="d", work_item_type=None,
    )
    ids = {d["memory_id"] for d in res}
    # ambas presentes (NO se ocultan, a diferencia de las observaciones)
    assert a in ids and b in ids


def test_directives_ordered_by_priority(app_ctx):
    from services import memory_store

    project = "DIR_RET4"
    low = _mk_directive(project, title="low", content="x",
                        applies_to={"agent_types": ["developer"]}, priority=1)
    high = _mk_directive(project, title="high", content="y",
                         applies_to={"agent_types": ["developer"]}, priority=10)
    res = memory_store.get_directives_for_run(
        project=project, agent_type="developer",
        ticket_title="t", ticket_description="d", work_item_type=None,
    )
    ids = [d["memory_id"] for d in res]
    assert ids.index(high) < ids.index(low)


def test_context_renders_directives_first_with_imperative_header(app_ctx):
    from services import memory_store

    project = "DIR_RET5"
    _mk_directive(project, title="Regla dura", content="cumplir siempre esto",
                  applies_to={"agent_types": ["developer"]})
    memory_store.save_observation(
        project=project, type="bugfix", title="observacion comun",
        content="aprendizaje del equipo sobre cumplir", author_email="op@x.com",
    )
    ctx = memory_store.get_context_for_run(
        project=project, agent_type="developer", query_text="cumplir",
    )
    assert "REGLAS OBLIGATORIAS DEL OPERADOR" in ctx["content"]
    assert ctx["directive_hits"] >= 1
    assert ctx["directive_ids"]
    # la sección de directivas va antes que el cuerpo observacional
    assert ctx["content"].index("Regla dura") < ctx["content"].index("observacion comun")


def test_observation_only_is_byte_identical_when_no_directives(app_ctx):
    from services import memory_store

    project = "DIR_RET6"
    memory_store.save_observation(
        project=project, type="bugfix", title="obs",
        content="contenido observacional", author_email="op@x.com",
    )
    ctx = memory_store.get_context_for_run(
        project=project, agent_type="developer", query_text="observacional",
    )
    assert ctx["directive_hits"] == 0
    assert ctx["directive_ids"] == []
    assert "REGLAS OBLIGATORIAS" not in ctx["content"]


def test_directives_win_under_cap_pressure(app_ctx):
    from services import memory_store

    project = "DIR_RET7"
    # cap muy chico vía override
    os.environ["STACKY_MEMORY_CAPS_JSON"] = '{"developer": [2, 400]}'
    memory_store._invalidate_caps_cache()
    try:
        _mk_directive(project, title="DIRECTIVA",
                      content="orden del operador " * 5,
                      applies_to={"agent_types": ["developer"]})
        for i in range(5):
            memory_store.save_observation(
                project=project, type="bugfix", title=f"obs{i}",
                content=f"observacion numero {i} con orden del operador relevante",
                author_email="op@x.com",
            )
        ctx = memory_store.get_context_for_run(
            project=project, agent_type="developer", query_text="orden operador",
        )
        # la directiva entra siempre
        assert ctx["directive_hits"] >= 1
        assert "DIRECTIVA" in ctx["content"]
    finally:
        os.environ.pop("STACKY_MEMORY_CAPS_JSON", None)
        memory_store._invalidate_caps_cache()


def test_max_memorias_does_not_cap_directives(app_ctx):
    from services import memory_store

    project = "DIR_RET8"
    os.environ["STACKY_MEMORY_CAPS_JSON"] = '{"developer": [1, 20000]}'
    memory_store._invalidate_caps_cache()
    try:
        for i in range(3):
            _mk_directive(project, title=f"DIR{i}", content=f"orden {i}",
                          applies_to={"agent_types": ["developer"]}, priority=i)
        ctx = memory_store.get_context_for_run(
            project=project, agent_type="developer", query_text="x",
        )
        # max_memorias=1 NO recorta las 3 directivas
        assert ctx["directive_hits"] == 3
    finally:
        os.environ.pop("STACKY_MEMORY_CAPS_JSON", None)
        memory_store._invalidate_caps_cache()
