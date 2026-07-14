"""Plan 133 F2 — Preflight de negocio por agent_type antes de lanzar el run."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from db import session_scope  # noqa: E402
from models import AgentExecution, Ticket  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def app_ctx():
    from app import create_app

    app = create_app()
    app.config.update(TESTING=True)
    yield app


def _make_ticket(**overrides) -> int:
    defaults = dict(
        ado_id=331,
        project="Strategist_Pacifico",
        title="Task de prueba",
        ado_state="Doing",
        work_item_type="Task",
        tracker_type="azure_devops",
    )
    defaults.update(overrides)
    with session_scope() as session:
        t = Ticket(**defaults)
        session.add(t)
        session.flush()
        return t.id


class _FakeAdoClient:
    def __init__(self, comments):
        self._comments = comments

    def fetch_comments(self, ado_id, top=30):
        return list(self._comments)


@pytest.fixture(autouse=True)
def _clear_cache():
    from services import ado_read_cache

    ado_read_cache.clear()
    yield
    ado_read_cache.clear()


def _patch_client(monkeypatch, comments=None, raises=None):
    from services import project_context

    def _fake_build(**kwargs):
        if raises is not None:
            raise raises
        return _FakeAdoClient(comments or [])

    monkeypatch.setattr(project_context, "build_ado_client", _fake_build)


def _patch_profile(monkeypatch, tracker_state_machine=None):
    from services import client_profile

    profile = {"tracker_state_machine": tracker_state_machine or {}}
    monkeypatch.setattr(client_profile, "load_client_profile", lambda project: profile)
    monkeypatch.setattr(client_profile, "get_project_tracker_type", lambda project: "azure_devops")
    monkeypatch.setattr(client_profile, "merge_with_defaults", lambda persisted, tracker_type: persisted)


def test_flag_off_ok_true(monkeypatch):
    from config import config
    from services import business_preflight

    monkeypatch.setattr(config, "STACKY_BUSINESS_PREFLIGHT_ENABLED", False)
    ticket_id = _make_ticket()
    result = business_preflight.evaluate(ticket_id=ticket_id, agent_type="functional")
    assert result.ok is True
    assert result.reason == "preflight_off"


def test_agent_type_sin_predicados_ok_true(monkeypatch):
    from config import config
    from services import business_preflight

    monkeypatch.setattr(config, "STACKY_BUSINESS_PREFLIGHT_ENABLED", True)
    ticket_id = _make_ticket()
    result = business_preflight.evaluate(ticket_id=ticket_id, agent_type="developer")
    assert result.ok is True
    assert result.reason == "not_applicable"


def test_task_doing_sin_bloqueante_rechaza(monkeypatch):
    """Caso ADO-331: Task, 'Doing', comentarios sin marcador."""
    from config import config
    from services import business_preflight

    monkeypatch.setattr(config, "STACKY_BUSINESS_PREFLIGHT_ENABLED", True)
    _patch_profile(monkeypatch, {"functional": {"input_states": ["New"]}})
    _patch_client(monkeypatch, comments=[
        {"author": "Dev", "date": "2026-07-13", "text": "avance normal, sin bloqueo"},
    ])
    ticket_id = _make_ticket(ado_id=331, work_item_type="Task", ado_state="Doing")
    result = business_preflight.evaluate(ticket_id=ticket_id, agent_type="functional")
    assert result.ok is False
    assert result.check == "functional_prereqs_unmet"
    assert "ADO-331" in result.reason
    assert "BLOQUEANTE TÉCNICO" in result.reason


def test_epic_en_input_state_modo_a(monkeypatch):
    from config import config
    from services import business_preflight

    monkeypatch.setattr(config, "STACKY_BUSINESS_PREFLIGHT_ENABLED", True)
    _patch_profile(monkeypatch, {"functional": {"input_states": ["New", "Approved"]}})
    ticket_id = _make_ticket(ado_id=500, work_item_type="Epic", ado_state="New")
    result = business_preflight.evaluate(ticket_id=ticket_id, agent_type="functional")
    assert result.ok is True
    assert result.mode == "A"
    assert result.epic_ado_id == 500


def test_epic_fuera_de_input_state_sin_bloqueante_rechaza(monkeypatch):
    from config import config
    from services import business_preflight

    monkeypatch.setattr(config, "STACKY_BUSINESS_PREFLIGHT_ENABLED", True)
    _patch_profile(monkeypatch, {"functional": {"input_states": ["New"]}})
    _patch_client(monkeypatch, comments=[
        {"author": "Dev", "date": "2026-07-13", "text": "nada especial"},
    ])
    ticket_id = _make_ticket(ado_id=501, work_item_type="Epic", ado_state="Closed")
    result = business_preflight.evaluate(ticket_id=ticket_id, agent_type="functional")
    assert result.ok is False
    assert result.check == "functional_prereqs_unmet"


def test_task_con_comentario_bloqueante_modo_b(monkeypatch):
    from config import config
    from services import business_preflight

    monkeypatch.setattr(config, "STACKY_BUSINESS_PREFLIGHT_ENABLED", True)
    _patch_profile(monkeypatch, {"functional": {"input_states": ["New"]}})
    _patch_client(monkeypatch, comments=[
        {"author": "Dev", "date": "2026-07-10", "text": "primer comentario"},
        {"author": "Dev", "date": "2026-07-13", "text": "🚫 BLOQUEANTE TÉCNICO: falta config X"},
    ])
    ticket_id = _make_ticket(ado_id=331, work_item_type="Task", ado_state="Doing")
    result = business_preflight.evaluate(ticket_id=ticket_id, agent_type="functional")
    assert result.ok is True
    assert result.mode == "B"
    assert result.blocker is not None
    assert result.blocker["excerpt"]


def test_marcador_solo_en_comentario_viejo_rechaza(monkeypatch):
    from config import config
    from services import business_preflight

    monkeypatch.setattr(config, "STACKY_BUSINESS_PREFLIGHT_ENABLED", True)
    _patch_profile(monkeypatch, {"functional": {"input_states": ["New"]}})
    _patch_client(monkeypatch, comments=[
        {"author": "Dev", "date": "2026-07-10", "text": "🚫 BLOQUEANTE TÉCNICO: viejo"},
        {"author": "Dev", "date": "2026-07-13", "text": "ya se resolvió, sin marcador"},
    ])
    ticket_id = _make_ticket(ado_id=331, work_item_type="Task", ado_state="Doing")
    result = business_preflight.evaluate(ticket_id=ticket_id, agent_type="functional")
    assert result.ok is False


def test_fetch_comentarios_usa_cache_i32(monkeypatch):
    from config import config
    from services import business_preflight

    monkeypatch.setattr(config, "STACKY_BUSINESS_PREFLIGHT_ENABLED", True)
    monkeypatch.setattr(config, "STACKY_ADO_READ_CACHE_TTL_SEC", 60)
    _patch_profile(monkeypatch, {"functional": {"input_states": ["New"]}})

    calls = {"n": 0}

    class _CountingClient:
        def fetch_comments(self, ado_id, top=30):
            calls["n"] += 1
            return [{"author": "Dev", "date": "2026-07-13", "text": "sin marcador"}]

    from services import project_context

    monkeypatch.setattr(project_context, "build_ado_client", lambda **kwargs: _CountingClient())
    ticket_id = _make_ticket(ado_id=331, work_item_type="Task", ado_state="Doing")
    business_preflight.evaluate(ticket_id=ticket_id, agent_type="functional")
    business_preflight.evaluate(ticket_id=ticket_id, agent_type="functional")
    assert calls["n"] == 1


def test_blocked_states_definidos_exige_estado(monkeypatch):
    from config import config
    from services import business_preflight

    monkeypatch.setattr(config, "STACKY_BUSINESS_PREFLIGHT_ENABLED", True)
    _patch_profile(monkeypatch, {
        "functional": {"input_states": ["New"], "blocked_states": ["Blocked"]},
    })
    _patch_client(monkeypatch, comments=[
        {"author": "Dev", "date": "2026-07-13", "text": "🚫 BLOQUEANTE TÉCNICO: x"},
    ])
    ticket_id = _make_ticket(ado_id=331, work_item_type="Task", ado_state="Doing")
    result = business_preflight.evaluate(ticket_id=ticket_id, agent_type="functional")
    assert result.ok is False


def test_error_red_comentarios_fail_open(monkeypatch):
    from config import config
    from services import business_preflight

    monkeypatch.setattr(config, "STACKY_BUSINESS_PREFLIGHT_ENABLED", True)
    _patch_profile(monkeypatch, {"functional": {"input_states": ["New"]}})
    _patch_client(monkeypatch, raises=RuntimeError("timeout"))
    ticket_id = _make_ticket(ado_id=331, work_item_type="Task", ado_state="Doing")
    result = business_preflight.evaluate(ticket_id=ticket_id, agent_type="functional")
    assert result.ok is True
    assert result.mode is None
    assert result.warnings


def test_sentinel_negativo_ok_true(monkeypatch):
    from config import config
    from services import business_preflight

    monkeypatch.setattr(config, "STACKY_BUSINESS_PREFLIGHT_ENABLED", True)
    ticket_id = _make_ticket(ado_id=-6, work_item_type="Task", ado_state="Doing")
    result = business_preflight.evaluate(ticket_id=ticket_id, agent_type="functional")
    assert result.ok is True
    assert result.reason == "not_applicable"


def test_endpoint_run_devuelve_400(app_ctx):
    from services import business_preflight, run_ticket_refresh

    rejecting = business_preflight.BusinessPreflightResult(
        ok=False,
        check="functional_prereqs_unmet",
        reason="ADO-331 no cumple prerequisitos.",
    )
    with session_scope() as session:
        before = session.query(AgentExecution).count()

    with patch.object(business_preflight, "evaluate", return_value=rejecting), \
         patch.object(run_ticket_refresh, "refresh_ticket_snapshot",
                       return_value={"refreshed": True, "reason": "ok"}):
        with app_ctx.test_client() as c:
            r = c.post(
                "/api/agents/run",
                json={
                    "agent_type": "functional",
                    "ticket_id": 331,
                    "runtime": "github_copilot",
                },
                headers={"X-User-Email": "op@x"},
            )
    assert r.status_code == 400
    body = r.get_json()
    assert body["ok"] is False
    assert body["error"] == "business_preflight_failed"
    assert body["check"] == "functional_prereqs_unmet"
    assert body["message"] == "ADO-331 no cumple prerequisitos."
    assert body["snapshot_fresh"] is True

    with session_scope() as session:
        after = session.query(AgentExecution).count()
    assert after == before
