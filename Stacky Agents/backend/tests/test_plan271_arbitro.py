# backend/tests/test_plan271_arbitro.py
"""Plan 271 F2-bis — árbitro anti-doble-escritura SIMÉTRICO y respeto del gate
de build del plan 210. Casos 1-6 ejercitan el motor A (completion_state.py);
7-8 ejercitan la simetría con el motor B (_attempt_state_change, F3-bis-2) —
quedan declarados rojos hasta que F3/F3-bis-2 cableen el helper ahí también."""
from __future__ import annotations

import inspect
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

import pytest

from tests.plan271_helpers import patch_motor_a


@pytest.fixture(autouse=True)
def _init_app_for_schema():
    from app import create_app

    create_app()


@pytest.fixture(autouse=True)
def clean_db():
    from db import session_scope
    from models import AgentExecution, Ticket

    yield
    with session_scope() as session:
        session.query(AgentExecution).delete()
        session.query(Ticket).delete()


def _flag_on(monkeypatch):
    import config as _config
    monkeypatch.setattr(_config.config, "STACKY_FINAL_STATE_ROLE_FALLBACK_ENABLED", True, raising=False)


def _ev(**over):
    base = {"ticket_id": 1, "execution_id": 9, "final_status": "completed", "agent_type": "developer"}
    base.update(over)
    return base


PERFIL_DEV = {"tracker_state_machine": {"developer": {"next_state_ok": "Done"}}}


def test_1_gate_sin_estado_no_escribe(monkeypatch):
    from services import completion_state
    import services.dev_build_verify as dbv

    _flag_on(monkeypatch)
    monkeypatch.setattr(dbv, "workspace_root_for_ado", lambda _id: "/ws")
    monkeypatch.setattr(dbv, "latest_execution_id_for_ado", lambda _id: 9)
    monkeypatch.setattr(dbv, "gate_final_state", lambda **_k: (None, {"reason": "build_stale"}))
    prov = patch_motor_a(monkeypatch, profile=PERFIL_DEV)

    out = completion_state.maybe_apply_state_transition(_ev())
    assert out.get("skipped") is True
    assert out.get("reason") == "dev_build_gate_no_state"
    assert prov.writes == []


def test_2_gate_degrada_el_estado(monkeypatch):
    from services import completion_state
    import services.dev_build_verify as dbv

    _flag_on(monkeypatch)
    monkeypatch.setattr(dbv, "workspace_root_for_ado", lambda _id: "/ws")
    monkeypatch.setattr(dbv, "latest_execution_id_for_ado", lambda _id: 9)
    monkeypatch.setattr(dbv, "gate_final_state", lambda **_k: ("En revisión", {"reason": "stale_verdict"}))
    prov = patch_motor_a(monkeypatch, profile=PERFIL_DEV)

    out = completion_state.maybe_apply_state_transition(_ev())
    assert out.get("ok") is True
    assert out.get("to") == "En revisión"
    assert prov.writes == [("4242", "En revisión")]


def test_3_gate_lanza_fail_open(monkeypatch):
    from services import completion_state
    import services.dev_build_verify as dbv

    _flag_on(monkeypatch)
    monkeypatch.setattr(dbv, "workspace_root_for_ado", lambda _id: "/ws")
    monkeypatch.setattr(dbv, "latest_execution_id_for_ado", lambda _id: 9)

    def _raise(**_k):
        raise RuntimeError("boom")

    monkeypatch.setattr(dbv, "gate_final_state", _raise)
    prov = patch_motor_a(monkeypatch, profile=PERFIL_DEV)

    out = completion_state.maybe_apply_state_transition(_ev())
    assert out.get("ok") is True
    assert out.get("to") == "Done"
    assert prov.writes == [("4242", "Done")]


def test_4_no_developer_no_llama_workspace_root(monkeypatch):
    from services import completion_state
    import services.dev_build_verify as dbv

    _flag_on(monkeypatch)
    calls = {"n": 0}

    def _spy(_id):
        calls["n"] += 1
        return "/ws"

    monkeypatch.setattr(dbv, "workspace_root_for_ado", _spy)
    perfil = {"tracker_state_machine": {"technical": {"next_state_ok": "To Do"}}}
    patch_motor_a(monkeypatch, profile=perfil, work_item_type=None)

    out = completion_state.maybe_apply_state_transition(_ev(agent_type="technical"))
    assert out.get("ok") is True
    assert calls["n"] == 0, "D11: se llamó workspace_root_for_ado para un rol != developer"


def _seed_real_ticket_y_execution(*, applied: bool):
    """A diferencia de `patch_motor_a` (que fakea `db.session_scope` ENTERO),
    los casos 5/6 necesitan que `final_state_already_written` lea una fila REAL
    de AgentExecution — así que acá se siembra en la DB real y NO se parchea
    `db.session_scope`, sólo los colaboradores externos (perfil/provider/log)."""
    from db import session_scope
    from models import AgentExecution, Ticket

    with session_scope() as s:
        t = Ticket(ado_id=4242, project="P271", stacky_project_name="P271",
                   title="t", ado_state="New", stacky_status="running")
        s.add(t)
        s.flush()
        e = AgentExecution(ticket_id=t.id, agent_type="technical", status="running",
                           input_context_json="[]", started_by="test")
        e.metadata_dict = {"final_state_outcome": {"applied": applied, "to": "To Do" if applied else None}}
        s.add(e)
        s.flush()
        return t.id, e.id


def _patch_colaboradores_sin_fakear_db(monkeypatch, *, profile: dict, provider):
    import services.client_profile as _cp
    import services.completion_dispatcher as _cd
    import services.tracker_provider as _tp

    monkeypatch.setattr(_cp, "load_effective_client_profile", lambda *_a, **_k: profile)
    monkeypatch.setattr(_tp, "get_tracker_provider", lambda *_a, **_k: provider)
    monkeypatch.setattr(_cd, "emit_completion_log", lambda **_k: None)


def test_5_ya_escrito_por_otro_motor_no_reescribe(monkeypatch):
    from services import completion_state
    from tests.plan271_helpers import FakeProvider

    _flag_on(monkeypatch)
    ticket_id, exec_id = _seed_real_ticket_y_execution(applied=True)
    prov = FakeProvider()
    perfil = {"tracker_state_machine": {"technical": {"next_state_ok": "To Do"}}}
    _patch_colaboradores_sin_fakear_db(monkeypatch, profile=perfil, provider=prov)

    out = completion_state.maybe_apply_state_transition(
        _ev(agent_type="technical", ticket_id=ticket_id, execution_id=exec_id)
    )
    assert out.get("skipped") is True
    assert out.get("reason") == "already_written_by_other_engine"
    assert prov.writes == []


def test_6_skip_previo_no_bloquea_reintento(monkeypatch):
    from services import completion_state
    from tests.plan271_helpers import FakeProvider

    _flag_on(monkeypatch)
    ticket_id, exec_id = _seed_real_ticket_y_execution(applied=False)
    prov = FakeProvider()
    perfil = {"tracker_state_machine": {"technical": {"next_state_ok": "To Do"}}}
    _patch_colaboradores_sin_fakear_db(monkeypatch, profile=perfil, provider=prov)

    out = completion_state.maybe_apply_state_transition(
        _ev(agent_type="technical", ticket_id=ticket_id, execution_id=exec_id)
    )
    assert out.get("ok") is True
    assert prov.writes == [("4242", "To Do")]


def test_7_simetria_motor_b_no_reescribe(monkeypatch):
    """Verde recién con F3-bis-2 (después de F5): mismo helper, motor B."""
    from db import session_scope
    from models import AgentExecution, Ticket
    from services import agent_completion_internal as aci

    with session_scope() as s:
        t = Ticket(ado_id=4242, project="P271", stacky_project_name="P271",
                   title="t", ado_state="New", stacky_status="running")
        s.add(t)
        s.flush()
        e = AgentExecution(ticket_id=t.id, agent_type="technical", status="running",
                           input_context_json="[]", started_by="test")
        e.metadata_dict = {"final_state_outcome": {"applied": True, "to": "To Do"}}
        s.add(e)
        s.flush()
        ticket_id, exec_id = t.id, e.id

    out = aci._attempt_state_change(ticket_id=ticket_id, target_state="To Do", execution_id=exec_id)
    assert out.get("skipped") is True
    assert out.get("reason") == "already_written_by_other_engine"


def test_8_los_dos_motores_usan_el_mismo_helper():
    from services import completion_state
    from services import agent_completion_internal as aci

    src_a = inspect.getsource(completion_state.maybe_apply_state_transition)
    src_b = inspect.getsource(aci._attempt_state_change)
    assert "final_state_already_written" in src_a
    assert "final_state_already_written" in src_b
