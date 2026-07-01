"""Plan 79 — F4 (SD-CENT): centinela anti-alucinación de estados.

Garantiza que, con el flag ON, el conjunto de estados que el wiring puede
aplicar está ESTRICTAMENTE contenido en {in_progress, next_state_ok} de la
config — jamás un estado del agente ni inventado. Bloqueante del DoD.

test_only_configured_states_are_applied / test_agent_target_never_reaches_provider_when_enabled /
test_blocked_state_never_auto_applied / test_vocabulary_frozen_guard cubren la invariante a nivel
unitario (provider mockeado, matriz de combinaciones). test_final_noop_when_flag_off cubre el
caso end-to-end (endpoint Flask real + Ticket en BD), reusando el patrón de
test_auto_publish_legacy.py.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

from harness.task_states import _APPLICABLE_KEYS, apply_task_start_state  # noqa: E402


def _ticket(ado_id=777, project_name="demo"):
    return SimpleNamespace(ado_id=ado_id, stacky_project_name=project_name)


_MATRIX = [
    # (agent_type, in_progress, next_state_ok, target_ado_state_alucinado_del_body)
    ("developer", "Active", "Done", "EstadoInventado"),
    ("developer", "Active", "Done", None),
    ("technical", "In Review", "Reviewed", "Blocked"),
    ("functional", None, "Accepted", "OtraCosaRara"),
    ("developer", "Active", None, "Cerrado"),
]


def _profile_for(agent_type, in_progress, next_state_ok):
    machine = {}
    if in_progress is not None:
        machine["in_progress"] = in_progress
    if next_state_ok is not None:
        machine["next_state_ok"] = next_state_ok
    return {"tracker_state_machine": {agent_type: machine}}


def test_only_configured_states_are_applied():
    from api.tickets import _apply_task_state

    captured_states: list[str] = []
    for agent_type, in_progress, next_state_ok, hallucinated in _MATRIX:
        profile = _profile_for(agent_type, in_progress, next_state_ok)
        configured = {s for s in (in_progress, next_state_ok) if s}

        # phase=start via apply_task_start_state
        provider_start = MagicMock()
        provider_start.get_item.side_effect = Exception("no item")
        provider_start.update_item_state.side_effect = (
            lambda item_id, state: captured_states.append(state)
        )
        with patch("harness.task_states.deterministic_task_states_enabled", return_value=True), \
             patch("services.client_profile.load_effective_client_profile", return_value=profile):
            apply_task_start_state(
                project_name="demo", agent_type=agent_type, ado_id=777, provider=provider_start,
            )

        # phase=final via _apply_task_state (ignora target_ado_state del body a propósito)
        provider_final = MagicMock()
        provider_final.get_item.side_effect = Exception("no item")
        provider_final.update_item_state.side_effect = (
            lambda item_id, state: captured_states.append(state)
        )
        with patch("api.tickets.load_effective_client_profile", return_value=profile), \
             patch("api.tickets._provider_for_ticket", return_value=provider_final):
            _apply_task_state(
                ticket=_ticket(), agent_type=agent_type, phase="final",
                correlation_id="corr-cent", publish_ok=True,
            )

        assert set(captured_states) <= configured, (
            f"Estado no configurado aplicado para {agent_type}: {captured_states} ⊄ {configured}"
        )
        captured_states.clear()


def test_agent_target_never_reaches_provider_when_enabled():
    """Ningún target_ado_state del body llega al provider: _apply_task_state no
    recibe ese valor como parámetro, resuelve el target solo desde la config."""
    from api.tickets import _apply_task_state

    profile = _profile_for("developer", "Active", "Done")
    provider = MagicMock()
    provider.get_item.side_effect = Exception("no item")
    captured: list[str] = []
    provider.update_item_state.side_effect = lambda item_id, state: captured.append(state)

    with patch("api.tickets.load_effective_client_profile", return_value=profile), \
         patch("api.tickets._provider_for_ticket", return_value=provider):
        _apply_task_state(
            ticket=_ticket(), agent_type="developer", phase="final",
            correlation_id="corr-agent-target", publish_ok=True,
        )

    assert captured == ["Done"]


def test_blocked_state_never_auto_applied():
    """Aunque la máquina defina blocked_state, este flujo nunca lo aplica
    (sigue siendo acción humana, Plan B7)."""
    from api.tickets import _apply_task_state

    profile = {
        "tracker_state_machine": {
            "developer": {"in_progress": "Active", "next_state_ok": "Done", "blocked_state": "Blocked"}
        }
    }
    provider = MagicMock()
    provider.get_item.side_effect = Exception("no item")
    captured: list[str] = []
    provider.update_item_state.side_effect = lambda item_id, state: captured.append(state)

    with patch("api.tickets.load_effective_client_profile", return_value=profile), \
         patch("api.tickets._provider_for_ticket", return_value=provider):
        _apply_task_state(
            ticket=_ticket(), agent_type="developer", phase="final",
            correlation_id="corr-blocked", publish_ok=True,
        )
        _apply_task_state(
            ticket=_ticket(), agent_type="developer", phase="start",
            correlation_id="corr-blocked-2", publish_ok=True,
        )

    assert "Blocked" not in captured


def test_vocabulary_frozen_guard():
    assert _APPLICABLE_KEYS == frozenset({"in_progress", "next_state_ok"})


# ── Endpoint-level (Flask real + Ticket en BD), patrón de test_auto_publish_legacy.py ──


@pytest.fixture
def tmp_repo(monkeypatch, tmp_path):
    monkeypatch.setenv("STACKY_REPO_ROOT", str(tmp_path))
    return tmp_path


@pytest.fixture
def client(tmp_repo):
    from app import create_app

    app = create_app()
    app.config.update(TESTING=True)
    from services.ticket_status import stop_stale_recovery

    stop_stale_recovery()
    with app.test_client() as c:
        yield c
    stop_stale_recovery()


def _mk_ticket_and_exec(ado_id: int, agent_type: str = "developer") -> tuple[int, int]:
    from db import session_scope
    from models import AgentExecution, Ticket

    with session_scope() as session:
        t = Ticket(
            ado_id=ado_id,
            project="RSPacifico",
            title=f"t-{ado_id}",
            ado_state="In Progress",
            stacky_status="running",
        )
        session.add(t)
        session.flush()
        e = AgentExecution(
            ticket_id=t.id,
            agent_type=agent_type,
            status="running",
            input_context_json="[]",
            started_by="test",
            started_at=datetime.utcnow(),
        )
        session.add(e)
        session.flush()
        return t.id, e.id


def _inject_publisher_stub_ok(ado_id: int):
    """Stub de services.ado_publisher que responde publish.ok=True (mismo
    patrón que test_auto_publish_legacy.py), necesario porque el bloque de
    transición de estado (legacy o determinista) solo corre si publish_ok."""
    import types
    from dataclasses import dataclass

    @dataclass
    class _FakePublishResult:
        ok: bool
        status: str
        reason: str | None = None
        ado_id: int | None = None
        execution_id: int | None = None
        html_sha256: str | None = None
        ado_response: dict | None = None
        record_id: int | None = None

    def fake_publish(execution_id: int, triggered_by: str = "legacy_auto_publish", **kw):
        return _FakePublishResult(ok=True, status="ok", ado_id=ado_id, execution_id=execution_id)

    stub = types.ModuleType("services.ado_publisher")
    stub.publish_from_execution = fake_publish
    sys.modules["services.ado_publisher"] = stub
    if "services" in sys.modules:
        sys.modules["services"].ado_publisher = stub  # type: ignore[attr-defined]


def _remove_publisher_stub():
    sys.modules.pop("services.ado_publisher", None)
    if "services" in sys.modules and hasattr(sys.modules["services"], "ado_publisher"):
        try:
            delattr(sys.modules["services"], "ado_publisher")
        except AttributeError:
            pass


@pytest.fixture(autouse=True)
def _clean_publisher_stub():
    _remove_publisher_stub()
    yield
    _remove_publisher_stub()


def test_final_noop_when_flag_off_and_uses_config_when_flag_on(client, tmp_repo, monkeypatch):
    """Un solo test end-to-end (un solo create_app() en el proceso — llamarlo
    2 veces contamina el registro de modelos SQLAlchemy, ver
    test_auto_publish_legacy.py que tiene el mismo problema preexistente)
    que cubre AMBAS ramas del flag sobre el endpoint real:

    1) OFF → usa el target_ado_state legacy del body (byte-idéntico al actual);
       _apply_task_state NUNCA se invoca en esta rama.
    2) ON  → ignora el target_ado_state del body y aplica el estado-final de
       la config."""
    from config import Config

    # ── Rama 1: flag OFF ──────────────────────────────────────────────────
    monkeypatch.setattr(Config, "STACKY_DETERMINISTIC_TASK_STATES_ENABLED", False, raising=False)
    ado_id_off = 9101
    _mk_ticket_and_exec(ado_id_off)
    _inject_publisher_stub_ok(ado_id_off)

    with patch("api.tickets._apply_task_state") as mock_apply, \
         patch("api.tickets._provider_for_ticket", return_value=None), \
         patch("api.tickets._ado_client_for_ticket") as mock_legacy_client:
        resp_off = client.patch(
            f"/api/tickets/by-ado/{ado_id_off}/stacky-status",
            json={
                "status": "completed",
                "agent_type": "developer",
                "html_output_path": f"Agentes/outputs/{ado_id_off}/comment.html",
                "target_ado_state": "LegacyStateDelAgente",
            },
        )
    assert resp_off.status_code == 200
    mock_apply.assert_not_called()
    mock_legacy_client.return_value.update_work_item_state.assert_called_once_with(
        ado_id_off, "LegacyStateDelAgente"
    )

    # ── Rama 2: flag ON ───────────────────────────────────────────────────
    monkeypatch.setattr(Config, "STACKY_DETERMINISTIC_TASK_STATES_ENABLED", True, raising=False)
    ado_id_on = 9102
    _mk_ticket_and_exec(ado_id_on)
    _inject_publisher_stub_ok(ado_id_on)

    profile = _profile_for("developer", "Active", "Done")
    provider = MagicMock()
    provider.get_item.side_effect = Exception("no item")
    captured: list[str] = []
    provider.update_item_state.side_effect = lambda item_id, state: captured.append(state)

    with patch("api.tickets.load_effective_client_profile", return_value=profile), \
         patch("api.tickets._provider_for_ticket", return_value=provider):
        resp_on = client.patch(
            f"/api/tickets/by-ado/{ado_id_on}/stacky-status",
            json={
                "status": "completed",
                "agent_type": "developer",
                "html_output_path": f"Agentes/outputs/{ado_id_on}/comment.html",
                "target_ado_state": "EstadoAlucinadoPorElAgente",
            },
        )
    assert resp_on.status_code == 200
    assert captured == ["Done"]
    assert "EstadoAlucinadoPorElAgente" not in captured
