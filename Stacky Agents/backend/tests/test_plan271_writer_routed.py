# backend/tests/test_plan271_writer_routed.py
"""Plan 271 F3 — el escritor del chokepoint (_attempt_state_change) rutea por
services.tracker_write_router.resolve_state_writer para paridad ADO↔GitLab."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

import pytest

from services.final_state_resolver import ALL_FINAL_STATE_REASONS


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


def _flag(monkeypatch, value: bool):
    import config as _config
    monkeypatch.setattr(_config.config, "STACKY_FINAL_STATE_WRITER_ROUTED_ENABLED", value, raising=False)


def _seed_ticket(*, ado_id=4242, project="P271", tracker_type="azure_devops"):
    from db import session_scope
    from models import Ticket

    with session_scope() as s:
        t = Ticket(ado_id=ado_id, project=project, stacky_project_name=project,
                   tracker_type=tracker_type, title="t", ado_state="New",
                   stacky_status="running")
        s.add(t)
        s.flush()
        return t.id


class _FakeAdoHandle:
    """Doble del `AdoClient` (o de lo que `resolve_state_writer` resuelva para
    ADO). §8-2: NUNCA se construye un AdoClient real en este archivo."""

    def __init__(self, raise_exc: Exception | None = None):
        self.calls: list[tuple[int, str]] = []
        self._raise = raise_exc

    def update_work_item_state(self, ado_id: int, target: str) -> None:
        if self._raise is not None:
            raise self._raise
        self.calls.append((ado_id, target))


class _FakeGitlabProvider:
    """Doble de GitLabTrackerProvider. `state_map` simula el vocabulario REAL
    (E24): un `logical_state` fuera del mapa levanta, igual que
    `gitlab_provider.py::update_item_state`."""

    def __init__(self, current_state: str | None = None, state_map: dict | None = None,
                 raise_exc: Exception | None = None):
        self.current_state = current_state
        self.state_map = state_map if state_map is not None else {
            "functional": {}, "accepted": {}, "rejected": {}, "in_progress": {},
        }
        self.writes: list[tuple[str, str]] = []
        self._raise = raise_exc

    def get_item(self, item_id: str) -> dict:
        return {"state": self.current_state} if self.current_state else {}

    def update_item_state(self, item_id: str, logical_state: str) -> dict:
        if self._raise is not None:
            raise self._raise
        if logical_state not in self.state_map:
            from services.tracker_provider import CapabilityUnavailable
            raise CapabilityUnavailable(
                "tracker.items.update_state", "gitlab",
                reason=f"el estado '{logical_state}' no existe en el mapa de estados de GitLab",
            )
        self.writes.append((str(item_id), logical_state))
        return {"ok": True}


def _patch_resolver(monkeypatch, *, writer=None, exc=None):
    import services.tracker_write_router as twr

    def _resolve(_ticket):
        if exc is not None:
            raise exc
        return writer

    monkeypatch.setattr(twr, "resolve_state_writer", _resolve)


def _patch_ado_client_guard(monkeypatch, handle: _FakeAdoHandle):
    """§8-2 guard: el camino LEGACY construye `_legacy_ado_client()` de verdad
    salvo que se parchee. Se parchea acá para que ningún test de este archivo
    llame a un ADO real."""
    import services.agent_completion_internal as aci

    monkeypatch.setattr(aci, "_legacy_ado_client", lambda: handle)


def test_1_proyecto_ado_rutea_por_legacy_client_fn(monkeypatch):
    from services import agent_completion_internal as aci
    from services.tracker_write_router import StateWriter

    _flag(monkeypatch, True)
    ticket_id = _seed_ticket(tracker_type="azure_devops")
    handle = _FakeAdoHandle()
    _patch_resolver(monkeypatch, writer=StateWriter(tracker_type="azure_devops", kind="ado_client", handle=handle))

    out = aci._attempt_state_change(ticket_id=ticket_id, target_state="To Do",
                                     execution_id=1, project_name="P271")
    assert out.get("ok") is True
    assert handle.calls == [(4242, "To Do")]


def test_2_proyecto_gitlab_rutea_por_provider_no_ado(monkeypatch):
    from services import agent_completion_internal as aci
    from services.tracker_write_router import StateWriter

    _flag(monkeypatch, True)
    ticket_id = _seed_ticket(tracker_type="gitlab")
    prov = _FakeGitlabProvider()
    _patch_resolver(monkeypatch, writer=StateWriter(tracker_type="gitlab", kind="provider", handle=prov))

    def _no_ado(*_a, **_k):
        raise AssertionError("AdoClient no debe construirse en el camino GitLab")

    monkeypatch.setattr("services.agent_completion_internal._legacy_ado_client", _no_ado)

    out = aci._attempt_state_change(ticket_id=ticket_id, target_state="functional",
                                     execution_id=1, project_name="P271")
    assert out.get("ok") is True
    assert prov.writes == [("4242", "functional")]


def test_3_resolver_lanza_capability_unavailable_no_rompe(monkeypatch):
    from services import agent_completion_internal as aci
    from services.tracker_provider import CapabilityUnavailable

    _flag(monkeypatch, True)
    ticket_id = _seed_ticket(tracker_type="gitlab")
    _patch_resolver(monkeypatch, exc=CapabilityUnavailable(
        "tracker.items.update_state", "gitlab", reason="GitLab apagado"))

    out = aci._attempt_state_change(ticket_id=ticket_id, target_state="functional",
                                     execution_id=1, project_name="P271")
    assert out.get("skipped") is True
    assert out.get("reason") == "provider_unavailable"


def test_4_idempotencia_ya_en_el_target_no_escribe(monkeypatch):
    from services import agent_completion_internal as aci
    from services.tracker_write_router import StateWriter

    _flag(monkeypatch, True)
    ticket_id = _seed_ticket(tracker_type="gitlab")
    prov = _FakeGitlabProvider(current_state="To Do")
    _patch_resolver(monkeypatch, writer=StateWriter(tracker_type="gitlab", kind="provider", handle=prov))

    out = aci._attempt_state_change(ticket_id=ticket_id, target_state="To Do",
                                     execution_id=1, project_name="P271")
    assert out.get("skipped") is True
    assert out.get("reason") == "already_in_state"
    assert prov.writes == []


def test_5_flag_off_camino_legacy_byte_identico(monkeypatch):
    from services import agent_completion_internal as aci

    _flag(monkeypatch, False)
    ticket_id = _seed_ticket(tracker_type="azure_devops")
    handle = _FakeAdoHandle()
    _patch_ado_client_guard(monkeypatch, handle)

    out = aci._attempt_state_change(ticket_id=ticket_id, target_state="To Do",
                                     execution_id=1, project_name="P271")
    assert out.get("ok") is True
    assert handle.calls == [(4242, "To Do")]


def test_9bis_legacy_ado_client_lanza_transition_failed(monkeypatch):
    from services import agent_completion_internal as aci

    _flag(monkeypatch, False)
    ticket_id = _seed_ticket(tracker_type="azure_devops")
    handle = _FakeAdoHandle(raise_exc=RuntimeError("ADO 400"))
    _patch_ado_client_guard(monkeypatch, handle)

    out = aci._attempt_state_change(ticket_id=ticket_id, target_state="To Do",
                                     execution_id=1, project_name="P271")
    assert out.get("ok") is False
    assert out.get("reason") == "transition_failed"


def test_6_sin_ado_id_skip(monkeypatch):
    """`Ticket.ado_id` es NOT NULL en la DB real; este camino defensivo
    (`getattr(ticket, "ado_id", None)`) se ejercita con un doble de fila.
    `agent_completion_internal` hace `from db import session_scope` A NIVEL DE
    MÓDULO (no dentro de la función), así que hay que parchear el propio
    módulo, no `db.session_scope`."""
    import contextlib
    from services import agent_completion_internal as aci

    class _TicketSinAdoId:
        ado_id = None

    @contextlib.contextmanager
    def _scope(*_a, **_k):
        class _S:
            def get(self, _model, _pk):
                return _TicketSinAdoId()
        yield _S()

    _flag(monkeypatch, True)
    monkeypatch.setattr(aci, "session_scope", _scope)

    out = aci._attempt_state_change(ticket_id=1, target_state="To Do",
                                     execution_id=1, project_name="P271")
    assert out.get("skipped") is True
    assert out.get("reason") == "no_ado_id"


def test_7_sin_project_name_camino_legacy_con_nota(monkeypatch):
    from services import agent_completion_internal as aci
    import services.tracker_write_router as twr

    _flag(monkeypatch, True)
    ticket_id = _seed_ticket(tracker_type="azure_devops")
    handle = _FakeAdoHandle()
    _patch_ado_client_guard(monkeypatch, handle)

    llamado = {"n": 0}
    original = twr.resolve_state_writer

    def _spy(ticket):
        llamado["n"] += 1
        return original(ticket)

    monkeypatch.setattr(twr, "resolve_state_writer", _spy)

    out = aci._attempt_state_change(ticket_id=ticket_id, target_state="To Do",
                                     execution_id=1, project_name=None)
    assert out.get("ok") is True
    assert out.get("note") == "no_project_context"
    assert llamado["n"] == 0, "no debe llamarse resolve_state_writer sin project_name"
    assert handle.calls == [(4242, "To Do")]


def test_8_exito_ruteado_no_trae_source_trae_writer(monkeypatch):
    from services import agent_completion_internal as aci
    from services.tracker_write_router import StateWriter

    _flag(monkeypatch, True)
    ticket_id = _seed_ticket(tracker_type="gitlab")
    prov = _FakeGitlabProvider()
    _patch_resolver(monkeypatch, writer=StateWriter(tracker_type="gitlab", kind="provider", handle=prov))

    out = aci._attempt_state_change(ticket_id=ticket_id, target_state="functional",
                                     execution_id=1, project_name="P271")
    assert out.get("ok") is True
    assert "source" not in out
    assert out.get("writer") == "safe_transition"


def test_9_provider_lanza_al_escribir_transition_failed(monkeypatch):
    from services import agent_completion_internal as aci
    from services.tracker_write_router import StateWriter

    _flag(monkeypatch, True)
    ticket_id = _seed_ticket(tracker_type="gitlab")
    prov = _FakeGitlabProvider(raise_exc=RuntimeError("gitlab 500"))
    _patch_resolver(monkeypatch, writer=StateWriter(tracker_type="gitlab", kind="provider", handle=prov))

    out = aci._attempt_state_change(ticket_id=ticket_id, target_state="functional",
                                     execution_id=1, project_name="P271")
    assert out.get("ok") is False
    assert out.get("reason") == "transition_failed"


def test_10_todos_los_reasons_estan_en_el_catalogo(monkeypatch):
    """D3, adelanto local de F9: todo dict devuelto trae `reason` del catálogo
    cerrado, salvo el éxito ruteado (que trae `ok=True` sin `reason`)."""
    from services import agent_completion_internal as aci
    from services.tracker_write_router import StateWriter

    _flag(monkeypatch, True)
    casos = []

    # no_ticket_id
    casos.append(aci._attempt_state_change(ticket_id=None, target_state="To Do", execution_id=1))
    # ticket no encontrado (ticket_id inexistente en la DB) -> ado_id None -> no_ado_id
    casos.append(aci._attempt_state_change(ticket_id=999999, target_state="To Do", execution_id=1))
    # provider_unavailable
    from services.tracker_provider import CapabilityUnavailable
    tid_gitlab = _seed_ticket(tracker_type="gitlab")
    _patch_resolver(monkeypatch, exc=CapabilityUnavailable("x", "gitlab", reason="off"))
    casos.append(aci._attempt_state_change(ticket_id=tid_gitlab, target_state="To Do",
                                            execution_id=1, project_name="P271"))
    # transition_failed (provider lanza)
    prov = _FakeGitlabProvider(raise_exc=RuntimeError("boom"))
    _patch_resolver(monkeypatch, writer=StateWriter(tracker_type="gitlab", kind="provider", handle=prov))
    casos.append(aci._attempt_state_change(ticket_id=tid_gitlab, target_state="functional",
                                            execution_id=2, project_name="P271"))
    # already_in_state
    prov2 = _FakeGitlabProvider(current_state="functional")
    _patch_resolver(monkeypatch, writer=StateWriter(tracker_type="gitlab", kind="provider", handle=prov2))
    casos.append(aci._attempt_state_change(ticket_id=tid_gitlab, target_state="functional",
                                            execution_id=3, project_name="P271"))

    for out in casos:
        if out.get("ok") is True:
            continue
        assert out.get("reason") in ALL_FINAL_STATE_REASONS, f"reason fuera del catálogo: {out}"


def test_11_gitlab_estado_fuera_de_vocabulario_transition_failed(monkeypatch):
    """E24 — GitLab sólo entiende 4 claves lógicas. `target_state='To Do'`
    (vocabulario ADO) no es ninguna de las 4: el FakeProvider replica el
    `state_map.get(...) is None -> levanta` REAL, no acepta cualquier string."""
    from services import agent_completion_internal as aci
    from services.tracker_write_router import StateWriter

    _flag(monkeypatch, True)
    ticket_id = _seed_ticket(tracker_type="gitlab")
    prov = _FakeGitlabProvider()  # vocabulario real: functional/accepted/rejected/in_progress
    _patch_resolver(monkeypatch, writer=StateWriter(tracker_type="gitlab", kind="provider", handle=prov))

    out = aci._attempt_state_change(ticket_id=ticket_id, target_state="To Do",
                                     execution_id=1, project_name="P271")
    assert out.get("ok") is False
    assert out.get("reason") == "transition_failed"
    assert prov.writes == []


def test_12_sin_origin_guard_escribe_igual_y_deja_rastro_en_el_log(monkeypatch, caplog):
    """R18 — motor B no tiene `_origin_guard`: un ticket en 'Done' (fuera de
    flujo) se sobreescribe igual. Mide el agujero (no lo cierra) y confirma el
    logger.warning de visibilidad barata que agrega el v7."""
    import logging
    from services import agent_completion_internal as aci
    from services.tracker_write_router import StateWriter

    _flag(monkeypatch, True)
    ticket_id = _seed_ticket(tracker_type="gitlab")
    prov = _FakeGitlabProvider(current_state="Done")
    _patch_resolver(monkeypatch, writer=StateWriter(tracker_type="gitlab", kind="provider", handle=prov))

    with caplog.at_level(logging.WARNING, logger="stacky.completion_internal"):
        out = aci._attempt_state_change(ticket_id=ticket_id, target_state="functional",
                                         execution_id=1, project_name="P271")
    assert out.get("ok") is True
    assert prov.writes == [("4242", "functional")]
    assert any("origin-guard" in r.message and "R18" in r.message for r in caplog.records)
