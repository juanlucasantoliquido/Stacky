"""Plan 290 F3 — el self-review declara que se salteó, y NADA de su retorno cambia.

`review_artifact` es el punto UNICO por el que pasan los 3 runtimes: los tres
llaman a `apply_to_execution` (agent_completion_internal.py:174,
claude_code_cli_runner.py:3227, codex_cli_runner.py:2008), que llega a
`review_artifact` por self_review.py:168. Instrumentar los tres call sites
triplicaria el mismo registro.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

PROYECTO_GITLAB = "Plan290_SelfReview_GitLab"
PROYECTO_ADO = "Plan290_SelfReview_ADO"
_ADO_SEQ = iter(range(940000, 949999))


@pytest.fixture(scope="module")
def app_ctx():
    from app import create_app

    app = create_app()
    app.config.update(TESTING=True)
    yield app


@pytest.fixture
def cfg_proyectos(monkeypatch):
    import project_manager

    def _cfg(nombre):
        nombre = (nombre or "").strip()
        if nombre == PROYECTO_GITLAB:
            return {"issue_tracker": {"type": "gitlab"}}
        if nombre == PROYECTO_ADO:
            return {"issue_tracker": {"type": "azure_devops"}}
        return None

    monkeypatch.setattr(project_manager, "get_project_config", _cfg)
    from services import project_context

    project_context._reset_memo_tracker_declarado()
    yield
    project_context._reset_memo_tracker_declarado()


@pytest.fixture
def flag_on(monkeypatch):
    from config import config

    monkeypatch.setattr(config, "STACKY_TRACKER_ROUTING_STRICT_ENABLED", True)
    return config


def _crear(proyecto: str, tracker: str):
    from db import session_scope
    from models import AgentExecution, Ticket

    with session_scope() as sesion:
        t = Ticket(
            ado_id=next(_ADO_SEQ), project=proyecto, stacky_project_name=proyecto,
            title="t", ado_state="Doing", work_item_type="Task", tracker_type=tracker,
        )
        sesion.add(t)
        sesion.flush()
        e = AgentExecution(
            ticket_id=t.id, agent_type="functional", status="completed",
            input_context_json="[]", started_by="plan290",
        )
        sesion.add(e)
        sesion.flush()
        return e.id


def _metadata(execution_id: int) -> dict:
    from db import session_scope
    from models import AgentExecution

    with session_scope() as sesion:
        return dict(sesion.get(AgentExecution, execution_id).metadata_dict or {})


def test_el_retorno_no_cambio(app_ctx, cfg_proyectos, flag_on):
    """Byte a byte lo de hoy. Este plan agrega una llamada ANTES del return."""
    from services import self_review

    execution_id = _crear(PROYECTO_GITLAB, "gitlab")
    r = self_review.review_artifact(execution_id=execution_id, artifact_text="x")
    assert r.score == 1.0
    assert r.checklist == []
    assert r.skipped_reason == "no_acceptance_criteria"

    entradas = _metadata(execution_id)["capability_degraded"]
    assert [e["capability"] for e in entradas] == ["tracker.acceptance_criteria"]
    assert entradas[0]["site"] == "self_review.review_artifact"
    assert entradas[0]["provider"] == "gitlab"


def test_proyecto_ado_sin_criterios_no_declara(app_ctx, cfg_proyectos, flag_on, monkeypatch):
    """Sentinela del falso positivo: un ticket ADO sin criterios cargados NO es
    una degradación de capacidad, es un ticket incompleto."""
    from services import self_review

    monkeypatch.setattr(self_review, "_resolve_criteria", lambda t: "")
    execution_id = _crear(PROYECTO_ADO, "azure_devops")
    r = self_review.review_artifact(execution_id=execution_id, artifact_text="x")
    assert r.skipped_reason == "no_acceptance_criteria"
    assert "capability_degraded" not in _metadata(execution_id)


def test_flag_apagada_no_declara(app_ctx, cfg_proyectos, monkeypatch):
    """El kill-switch heredado apaga el guard y su declaración de un movimiento."""
    from config import config
    from services import self_review

    monkeypatch.setattr(config, "STACKY_TRACKER_ROUTING_STRICT_ENABLED", False)
    monkeypatch.setattr(self_review, "_resolve_criteria", lambda t: "")
    execution_id = _crear(PROYECTO_GITLAB, "gitlab")
    r = self_review.review_artifact(execution_id=execution_id, artifact_text="x")
    assert r.skipped_reason == "no_acceptance_criteria"
    assert "capability_degraded" not in _metadata(execution_id)


def test_declarar_falla_y_el_review_sigue(app_ctx, cfg_proyectos, flag_on, monkeypatch):
    """Riel "nunca levanta": si el registro explota, el review devuelve lo normal.

    Se parchea `declarar` para LEVANTAR (no para devolver False): lo que se prueba
    es que una excepción del telemétrico no puede tumbar la corrida."""
    from services import capability_degradation, self_review

    def _revienta(**_kw):
        raise RuntimeError("database is locked")

    monkeypatch.setattr(capability_degradation, "declarar", _revienta)
    execution_id = _crear(PROYECTO_GITLAB, "gitlab")

    with pytest.raises(RuntimeError):
        capability_degradation.declarar(execution_id=1, capability="x", reason="",
                                        provider="", site="")  # el parche está puesto

    r = self_review.review_artifact(execution_id=execution_id, artifact_text="x")
    assert r.score == 1.0
    assert r.checklist == []
    assert r.skipped_reason == "no_acceptance_criteria"
