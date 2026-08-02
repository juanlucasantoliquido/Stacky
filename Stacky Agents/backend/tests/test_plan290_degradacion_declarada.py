"""Plan 290 F0 — los dos centinelas: la degradacion tiene que dejar RASTRO.

Estos dos casos son de EJECUCION, no estaticos, y a proposito:

  * El caso 1 entra por `context_enrichment.enrich_blocks(...)`, que es el MISMO
    seam que usan los 3 runtimes (agent_runner.py:809, claude_code_cli_runner.py:677,
    codex_cli_runner.py:334). Llamar a `business_preflight.evaluate(...)` directo
    verificaria el PRODUCTOR, que es exactamente el bloqueante central del Plan 289:
    un test asi se pone verde sin que ningun runtime escriba nunca nada.
  * El caso 2 entra por `self_review.review_artifact(...)`, el punto unico por el
    que pasan los 3 runtimes via `apply_to_execution`.

Lo que se verifica es el EFECTO en la fila de la base, nunca la presencia del
simbolo en el fuente: una llamada dentro de una rama muerta pasaria un grep.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
# Enriquecimiento hermetico: sin red hacia ADO ni hacia el buscador de similares.
os.environ["STACKY_SIMILAR_TICKETS_ENABLED"] = "false"
os.environ["ADO_CONTEXT_ENRICH_AGENTS"] = "__none__"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

PROYECTO_GITLAB = "Plan290_ProyectoGitLab"
_ADO_SEQ = iter(range(920000, 929999))


@pytest.fixture(scope="module")
def app_ctx():
    from app import create_app

    app = create_app()
    app.config.update(TESTING=True)
    yield app


@pytest.fixture
def proyecto_no_ado(monkeypatch):
    """`tracker_is_azure_devops` y `tracker_declarado_del_proyecto` resuelven por
    `project_manager.get_project_config`, importado POR REFERENCIA dentro de cada
    funcion. Parchearlo ahi es el seam declarado (project_context.py:58-61)."""
    import project_manager

    def _cfg(nombre):
        if (nombre or "").strip() == PROYECTO_GITLAB:
            return {"issue_tracker": {"type": "gitlab"}}
        return None

    monkeypatch.setattr(project_manager, "get_project_config", _cfg)
    from services import project_context

    project_context._reset_memo_tracker_declarado()
    yield PROYECTO_GITLAB
    project_context._reset_memo_tracker_declarado()


@pytest.fixture
def flags_on(monkeypatch):
    from config import config

    monkeypatch.setattr(config, "STACKY_RUN_DIRECTIVE_ENABLED", True)
    monkeypatch.setattr(config, "STACKY_BUSINESS_PREFLIGHT_ENABLED", True)
    monkeypatch.setattr(config, "STACKY_TRACKER_ROUTING_STRICT_ENABLED", True)
    return config


@pytest.fixture
def fila(app_ctx, proyecto_no_ado):
    """(ticket_id, execution_id) de un proyecto NO-ADO, con ado_id positivo."""
    from db import session_scope
    from models import AgentExecution, Ticket

    with session_scope() as sesion:
        t = Ticket(
            ado_id=next(_ADO_SEQ),
            project=PROYECTO_GITLAB,
            stacky_project_name=PROYECTO_GITLAB,
            title="Ticket de un tracker que no es Azure DevOps",
            ado_state="Doing",
            work_item_type="Task",
            tracker_type="gitlab",
        )
        sesion.add(t)
        sesion.flush()
        ejecucion = AgentExecution(
            ticket_id=t.id,
            agent_type="functional",
            status="running",
            input_context_json="[]",
            started_by="plan290",
        )
        sesion.add(ejecucion)
        sesion.flush()
        return t.id, ejecucion.id


def _degradaciones(execution_id: int) -> list[dict]:
    from db import session_scope
    from models import AgentExecution

    with session_scope() as sesion:
        row = sesion.get(AgentExecution, execution_id)
        assert row is not None, "la fila de la ejecucion desaparecio"
        md = row.metadata_dict or {}
    entradas = md.get("capability_degraded")
    assert isinstance(entradas, list), (
        f"metadata['capability_degraded'] deberia ser una lista y es {entradas!r}. "
        f"Claves presentes: {sorted(md)}"
    )
    return entradas


def test_preflight_no_ado_declara_la_degradacion_en_la_metadata(
    fila, flags_on, monkeypatch
):
    """El guard de business_preflight (sitio 5) decide no hacer el cross-check de
    comentarios y hoy devuelve ok=True en silencio. Tiene que quedar declarado."""
    from services import context_enrichment

    ticket_id, execution_id = fila
    context_enrichment.enrich_blocks(
        ticket_id=ticket_id,
        agent_type="functional",
        raw_blocks=[],
        execution_id=execution_id,
    )

    entradas = _degradaciones(execution_id)
    capacidades = [e.get("capability") for e in entradas]
    assert "tracker.comments.list" in capacidades, (
        f"el preflight degrado y no lo declaro. Capacidades declaradas: {capacidades}"
    )


def test_self_review_sin_criterios_declara_la_degradacion(fila, flags_on):
    """`review_artifact` devuelve score=1.0 ("perfecto") sobre un artefacto que
    nadie reviso, porque el tracker no tiene AcceptanceCriteria. Que quede dicho."""
    from services import self_review

    _ticket_id, execution_id = fila
    resultado = self_review.review_artifact(
        execution_id=execution_id, artifact_text="x"
    )
    assert resultado.skipped_reason == "no_acceptance_criteria"

    entradas = _degradaciones(execution_id)
    capacidades = [e.get("capability") for e in entradas]
    assert "tracker.acceptance_criteria" in capacidades, (
        f"el self-review se salteo y no lo declaro. Capacidades: {capacidades}"
    )
