# backend/tests/test_plan271_reason_persisted.py
"""Plan 271 F5 — la razón del cambio (o no-cambio) de estado se persiste en
metadata_json y se promueve en el payload de /api/executions/<id>."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

import pytest


@pytest.fixture(autouse=True)
def _init_app_for_schema():
    from app import create_app

    create_app()


@pytest.fixture
def client():
    from app import create_app

    app = create_app()
    app.config.update(TESTING=True)
    with app.test_client() as c:
        yield c


@pytest.fixture(autouse=True)
def clean_db():
    from db import session_scope
    from models import AgentExecution, Ticket

    yield
    with session_scope() as session:
        session.query(AgentExecution).delete()
        session.query(Ticket).delete()


def _flag_reason_visible(monkeypatch, value: bool):
    import config as _config
    monkeypatch.setattr(_config.config, "STACKY_FINAL_STATE_REASON_VISIBLE_ENABLED", value, raising=False)


def _seed_ticket_y_execution():
    from db import session_scope
    from models import AgentExecution, Ticket

    with session_scope() as s:
        t = Ticket(ado_id=4242, project="P271", stacky_project_name="P271",
                   tracker_type="azure_devops", title="t", ado_state="New",
                   stacky_status="running")
        s.add(t)
        s.flush()
        e = AgentExecution(ticket_id=t.id, agent_type="technical", status="running",
                           input_context_json="[]", started_by="test")
        s.add(e)
        s.flush()
        return t.id, e.id


def _metadata_of(execution_id: int) -> dict:
    from db import session_scope
    from models import AgentExecution

    with session_scope() as s:
        row = s.get(AgentExecution, execution_id)
        return dict(row.metadata_dict or {})


def test_1_transicion_ok_motor_a_persiste_source_role(monkeypatch):
    from services import completion_state
    from services.tracker_write_router import StateWriter
    from tests.plan271_helpers import FakeProvider

    _flag_reason_visible(monkeypatch, True)
    import config as _config
    monkeypatch.setattr(_config.config, "STACKY_FINAL_STATE_ROLE_FALLBACK_ENABLED", True, raising=False)

    ticket_id, exec_id = _seed_ticket_y_execution()

    import services.client_profile as _cp
    import services.completion_dispatcher as _cd
    import services.tracker_provider as _tp

    perfil = {"tracker_state_machine": {"technical": {"next_state_ok": "To Do"}}}
    prov = FakeProvider()
    monkeypatch.setattr(_cp, "load_effective_client_profile", lambda *_a, **_k: perfil)
    monkeypatch.setattr(_tp, "get_tracker_provider", lambda *_a, **_k: prov)
    monkeypatch.setattr(_cd, "emit_completion_log", lambda **_k: None)

    out = completion_state.maybe_apply_state_transition(
        {"ticket_id": ticket_id, "execution_id": exec_id, "final_status": "completed",
         "agent_type": "technical"}
    )
    assert out.get("ok") is True

    fso = _metadata_of(exec_id).get("final_state_outcome")
    assert fso is not None
    assert fso.get("applied") is True
    assert fso.get("to") == "To Do"
    assert fso.get("source") == "role"
    assert fso.get("reason") == "ok"
    assert fso.get("at")


def test_2_publish_not_ok_persiste_applied_false(monkeypatch):
    """A diferencia de F0/RC-2 (sin nada que publicar), acá la publicación SE
    INTENTÓ (hay `html_output_path`) y falló de verdad: el gate F4 sigue
    bloqueando el cambio de estado — `publish_not_ok` es el resultado correcto."""
    from services import agent_completion_internal as aci

    _flag_reason_visible(monkeypatch, True)
    monkeypatch.setattr(aci, "_resolve_transition_state_from_config", lambda **_k: "To Do")
    monkeypatch.setattr(
        aci, "_attempt_publish",
        lambda **_k: {"ok": False, "reason": "boom", "event": "publish.failed"},
    )
    ticket_id, exec_id = _seed_ticket_y_execution()

    res = aci.close_execution_with_publish(
        execution_id=exec_id, triggered_by="test", final_status="completed",
        html_output_path="outputs/comment.html",
    )
    assert res.ado_state_change.get("reason") == "publish_not_ok"

    fso = _metadata_of(exec_id).get("final_state_outcome")
    assert fso is not None
    assert fso.get("applied") is False
    assert fso.get("reason") == "publish_not_ok"


def test_3_review_mode_hold_persiste_source_none(monkeypatch):
    from services import agent_completion_internal as aci

    _flag_reason_visible(monkeypatch, True)
    ticket_id, exec_id = _seed_ticket_y_execution()

    import project_manager as pm
    monkeypatch.setattr(pm, "get_project_config", lambda *_a, **_k: {"publish_mode": "review"})

    res = aci.close_execution_with_publish(
        execution_id=exec_id, triggered_by="test", final_status="completed",
        html_output_path=None,
    )
    assert res.ado_state_change.get("reason") == "review_mode_hold"

    fso = _metadata_of(exec_id).get("final_state_outcome")
    assert fso is not None
    assert fso.get("applied") is False
    assert fso.get("reason") == "review_mode_hold"
    assert fso.get("source") == "none"


def test_4_skip_motor_a_no_config_persiste(monkeypatch):
    from services import completion_state
    from tests.plan271_helpers import patch_motor_a

    _flag_reason_visible(monkeypatch, True)
    import config as _config
    monkeypatch.setattr(_config.config, "STACKY_FINAL_STATE_ROLE_FALLBACK_ENABLED", True, raising=False)

    ticket_id, exec_id = _seed_ticket_y_execution()

    import services.client_profile as _cp
    import services.completion_dispatcher as _cd

    monkeypatch.setattr(_cp, "load_effective_client_profile", lambda *_a, **_k: {})
    monkeypatch.setattr(_cd, "emit_completion_log", lambda **_k: None)

    out = completion_state.maybe_apply_state_transition(
        {"ticket_id": ticket_id, "execution_id": exec_id, "final_status": "completed",
         "agent_type": "technical"}
    )
    assert out.get("reason") == "no_config"

    fso = _metadata_of(exec_id).get("final_state_outcome")
    assert fso is not None
    assert fso.get("applied") is False
    assert fso.get("reason") == "no_config"


def test_5_flag_off_no_agrega_la_key(monkeypatch):
    from services import agent_completion_internal as aci

    _flag_reason_visible(monkeypatch, False)
    monkeypatch.setattr(aci, "_resolve_transition_state_from_config", lambda **_k: None)
    ticket_id, exec_id = _seed_ticket_y_execution()

    aci.close_execution_with_publish(
        execution_id=exec_id, triggered_by="test", final_status="completed",
        html_output_path=None,
    )
    assert "final_state_outcome" not in _metadata_of(exec_id)


def test_6_endpoint_devuelve_final_state_outcome(client, monkeypatch):
    from services import agent_completion_internal as aci

    _flag_reason_visible(monkeypatch, True)
    monkeypatch.setattr(aci, "_resolve_transition_state_from_config", lambda **_k: None)
    ticket_id, exec_id = _seed_ticket_y_execution()

    aci.close_execution_with_publish(
        execution_id=exec_id, triggered_by="test", final_status="completed",
        html_output_path=None,
    )
    resp = client.get(f"/api/executions/{exec_id}")
    assert resp.status_code == 200
    body = resp.get_json()
    fso = body.get("final_state_outcome")
    assert fso is not None
    assert set(fso.keys()) >= {"applied", "to", "source", "reason", "at"}


def test_7_independiente_de_la_flag_del_254(client, monkeypatch):
    """C14 — con STACKY_UI_OUTCOME_REASON_BADGE_ENABLED apagada (ajena, plan
    254), `final_state_outcome` SIGUE presente en el payload."""
    from services import agent_completion_internal as aci

    _flag_reason_visible(monkeypatch, True)
    import config as _config
    monkeypatch.setattr(_config.config, "STACKY_UI_OUTCOME_REASON_BADGE_ENABLED", False, raising=False)
    monkeypatch.setattr(aci, "_resolve_transition_state_from_config", lambda **_k: None)
    ticket_id, exec_id = _seed_ticket_y_execution()

    aci.close_execution_with_publish(
        execution_id=exec_id, triggered_by="test", final_status="completed",
        html_output_path=None,
    )
    resp = client.get(f"/api/executions/{exec_id}")
    body = resp.get_json()
    assert body.get("final_state_outcome") is not None
    assert "outcome_reason" not in body  # la flag del 254 sigue apagando SU campo


def test_8_execution_id_none_no_lanza(monkeypatch):
    from services.agent_completion_internal import _persist_final_state_outcome

    _flag_reason_visible(monkeypatch, True)
    _persist_final_state_outcome(execution_id=None, result={"ok": True, "to": "To Do"})
