"""Plan 208 F2 + F5 — Transición determinista desde la matriz + centinela.

Cubre: cell configurado transiciona; sin cell es no-op; idempotencia; flag off;
estados de fallo y needs_review (HITL); provider None; guardia de origen (P11);
centinela de conjunto cerrado; validación no bloqueante contra el tracker.
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

_ADO_ID = 99208
_PROJECT = "RSPacifico"


def _profile(cell: dict | None = None) -> dict:
    machine = {
        "input_states": ["Ready for Dev"],
        "in_progress": "In Progress",
        "blocked_state": "Blocked",
        "next_state_ok": "Code Review",
    }
    if cell is not None:
        machine["by_work_item_type"] = {"Task": cell}
    return {"tracker_state_machine": {"developer": machine}}


class FakeProvider:
    name = "azure_devops"

    def __init__(self, current: str = "In Progress"):
        self.current = current
        self.updates: list[tuple[str, str]] = []

    def get_item(self, item_id):
        return {"fields": {"System.State": self.current}}

    def update_item_state(self, item_id, state):
        self.updates.append((str(item_id), state))
        self.current = state
        return {"ok": True}

    def fetch_states(self):
        return ["Ready for Dev", "In Progress", "Blocked", "Code Review", "Ready for QA"]


@pytest.fixture(autouse=True)
def _db():
    from db import init_db

    init_db()


@pytest.fixture
def ticket_id():
    from db import session_scope
    from models import Ticket

    with session_scope() as s:
        t = Ticket(
            ado_id=_ADO_ID,
            project="Strategist_Pacifico",
            stacky_project_name=_PROJECT,
            tracker_type="azure_devops",
            title="Ticket plan208",
            work_item_type="Task",
            ado_state="In Progress",
            stacky_status="running",
        )
        s.add(t)
        s.flush()
        tid = t.id
    yield tid
    with session_scope() as s:
        row = s.get(Ticket, tid)
        if row is not None:
            s.delete(row)


@pytest.fixture
def wired(monkeypatch):
    """Devuelve un helper que cablea profile+provider y corre la transición.

    Plan 271 F2-bis GUARDIA 1 cableó el gate de build del plan 210
    (dev_build_verify.gate_final_state) en motor A para agent_type=="developer".
    Este archivo prueba la lógica de motor A en sí (matriz/rol/resolve_final_state),
    no el gate de build (que tiene su propia suite) — se simula un veredicto
    fresco y verde (execution_id=1, igual al de `maybe_apply_state_transition`
    más abajo) para que el gate pase de largo sin degradar el target.
    """

    def _run(*, cell, provider, final_status="completed", agent_type="developer",
             tid=None, profile=None):
        prof = profile if profile is not None else _profile(cell)
        monkeypatch.setattr(
            "services.client_profile.load_effective_client_profile",
            lambda project: prof,
            raising=True,
        )
        monkeypatch.setattr(
            "services.tracker_provider.get_tracker_provider",
            lambda project=None: provider,
            raising=True,
        )
        from services.dev_build_verify import BuildVerdict

        monkeypatch.setattr(
            "services.dev_build_verify.read_verdict",
            lambda ado_id, workspace_root: BuildVerdict(
                ok=True, gate_ok=True, reason="verified", execution_id=1,
            ),
            raising=True,
        )
        from services.completion_state import maybe_apply_state_transition

        return maybe_apply_state_transition(
            {"ticket_id": tid, "execution_id": 1, "final_status": final_status,
             "agent_type": agent_type}
        )

    return _run


# ── F2 ───────────────────────────────────────────────────────────────────────

def test_transiciona_con_cell_configurado(ticket_id, wired):
    prov = FakeProvider(current="In Progress")
    res = wired(cell={"next_state_ok": "Ready for QA"}, provider=prov, tid=ticket_id)

    assert res.get("ok") is True, res
    assert res.get("to") == "Ready for QA"
    assert prov.updates == [(str(_ADO_ID), "Ready for QA")]


def test_no_op_sin_cell(ticket_id, wired):
    """Plan 271 F1/F2 (RC-1) cambió este comportamiento a propósito: sin celda de
    matriz para el work item type, motor A ya NO se queda mudo — cae al
    `next_state_ok` de NIVEL ROL que el operador configuró (STACKY_FINAL_STATE_
    ROLE_FALLBACK_ENABLED, default ON). El profile de este archivo siempre
    declara ese nivel rol ("Code Review"), así que el resultado correcto hoy es
    una transición real, no un skip."""
    prov = FakeProvider(current="In Progress")
    res = wired(cell=None, provider=prov, tid=ticket_id)

    assert res.get("ok") is True, res
    assert res.get("to") == "Code Review"
    assert prov.updates == [(str(_ADO_ID), "Code Review")]


def test_idempotente_segundo_llamado(ticket_id, wired):
    prov = FakeProvider(current="In Progress")
    first = wired(cell={"next_state_ok": "Ready for QA"}, provider=prov, tid=ticket_id)
    second = wired(cell={"next_state_ok": "Ready for QA"}, provider=prov, tid=ticket_id)

    assert first.get("ok") is True
    assert second.get("skipped") is True
    assert second.get("reason") == "already_in_state"
    assert len(prov.updates) == 1, "el segundo intento no debe escribir de nuevo"


def test_flag_off_skip(ticket_id, wired, monkeypatch):
    from config import config as cfg

    monkeypatch.setattr(cfg, "STACKY_ADO_STATE_MATRIX_ENABLED", False, raising=False)
    prov = FakeProvider(current="In Progress")
    res = wired(cell={"next_state_ok": "Ready for QA"}, provider=prov, tid=ticket_id)

    assert res == {"skipped": True, "reason": "flag_off"}
    assert prov.updates == []


@pytest.mark.parametrize("status", ["error", "cancelled", "idle", "running"])
def test_status_de_fallo_no_transiciona(ticket_id, wired, status):
    prov = FakeProvider(current="In Progress")
    res = wired(cell={"next_state_ok": "Ready for QA"}, provider=prov,
                final_status=status, tid=ticket_id)

    assert res.get("reason") == "not_ok_status"
    assert prov.updates == []


def test_needs_review_no_transiciona(ticket_id, wired):
    """C2 — needs_review EXIGE revisión humana: auto-transicionar violaría HITL."""
    prov = FakeProvider(current="In Progress")
    res = wired(cell={"next_state_ok": "Ready for QA"}, provider=prov,
                final_status="needs_review", tid=ticket_id)

    assert res.get("reason") == "not_ok_status"
    assert prov.updates == []


def test_ok_statuses_excluye_terminales_no_exitosos():
    from services.completion_state import _OK_STATUSES
    from services.status_vocabulary import TERMINAL_STATUSES

    assert _OK_STATUSES == frozenset({"completed"})
    assert "completed" in TERMINAL_STATUSES
    assert not (_OK_STATUSES & {"needs_review", "error", "cancelled"})


def test_provider_none_skip(ticket_id, wired):
    res = wired(cell={"next_state_ok": "Ready for QA"}, provider=None, tid=ticket_id)

    assert res.get("skipped") is True
    assert res.get("reason") == "no_provider"


def test_sin_ticket_skip(wired):
    res = wired(cell={"next_state_ok": "Ready for QA"}, provider=FakeProvider(), tid=None)

    assert res.get("reason") == "no_ticket"


def test_sin_stacky_project_skip(wired):
    from db import session_scope
    from models import Ticket

    with session_scope() as s:
        t = Ticket(ado_id=99209, project="Strategist_Pacifico", stacky_project_name=None,
                   title="sin workspace", work_item_type="Task", stacky_status="running")
        s.add(t)
        s.flush()
        tid = t.id

    prov = FakeProvider()
    res = wired(cell={"next_state_ok": "Ready for QA"}, provider=prov, tid=tid)

    assert res.get("reason") == "no_ado_id_or_stacky_project"
    assert prov.updates == []


def test_no_pisa_estado_movido_por_humano(ticket_id, wired):
    """P11 — el humano movió el ticket fuera del flujo del rol: no re-empujar."""
    prov = FakeProvider(current="On Hold")
    res = wired(cell={"next_state_ok": "Ready for QA"}, provider=prov, tid=ticket_id)

    assert res.get("skipped") is True
    assert res.get("reason") == "human_moved_out_of_flow"
    assert res.get("current") == "On Hold"
    assert prov.updates == [], "update_item_state NO debe llamarse si el humano lo movió"


def test_no_skipea_desde_in_progress_de_la_matriz(ticket_id, wired):
    """El estado en-progreso de la MATRIZ también es origen legítimo del flujo."""
    prov = FakeProvider(current="Active")
    res = wired(cell={"in_progress": "Active", "next_state_ok": "Ready for QA"},
                provider=prov, tid=ticket_id)

    assert res.get("ok") is True, f"'Active' viene del propio flujo (matriz), no del humano: {res}"
    assert prov.updates == [(str(_ADO_ID), "Ready for QA")]


def test_get_item_que_falla_no_bloquea(ticket_id, wired):
    class BrokenReader(FakeProvider):
        def get_item(self, item_id):
            raise RuntimeError("tracker caído")

    prov = BrokenReader(current="In Progress")
    res = wired(cell={"next_state_ok": "Ready for QA"}, provider=prov, tid=ticket_id)

    assert res.get("ok") is True, "sin lectura de estado, best-effort: no bloquea"
    assert prov.updates == [(str(_ADO_ID), "Ready for QA")]


def test_shadow_no_encola_evento(ticket_id):
    """run_shadow simula y NO llama on_execution_end ⇒ no dispara R2/R3.

    Control positivo en el mismo test: on_execution_end SÍ encola, así el verde
    del shadow no puede venir de un post-hook desregistrado.
    """
    from services import completion_dispatcher as cd
    from services import ticket_status
    from services.agent_completion import CompletionPayload, run_shadow

    cd.register(ticket_status.register_post_hook)
    while not cd._Q.empty():
        cd._Q.get_nowait()

    payload = CompletionPayload.from_dict(
        {"agent_type": "developer", "status": "completed", "execution_id": None}
    )
    result, _status = run_shadow(
        ado_id=_ADO_ID, payload=payload, user="tester", correlation_id="corr-208-shadow"
    )
    assert result is not None, "run_shadow debe devolver un resultado (no romper antes de correr)"
    assert cd._Q.empty(), "shadow NO debe encolar eventos de completación"

    ticket_status.on_execution_end(
        ticket_id=ticket_id, execution_id=1, final_status="completed", agent_type="developer"
    )
    assert not cd._Q.empty(), "control positivo: on_execution_end SÍ debe encolar"
    while not cd._Q.empty():
        cd._Q.get_nowait()


# ── F5 — centinela + validación ──────────────────────────────────────────────

def test_centinela_estado_fuera_de_matriz_no_se_aplica(ticket_id, wired, monkeypatch):
    """El conjunto cerrado manda: si el target no está en applicable_states, no se aplica."""
    import harness.task_states as ts

    monkeypatch.setattr(ts, "applicable_states", lambda plan: frozenset(), raising=True)
    prov = FakeProvider(current="In Progress")
    res = wired(cell={"next_state_ok": "Ready for QA"}, provider=prov, tid=ticket_id)

    assert res.get("reason") == "state_not_applicable"
    assert prov.updates == [], "_safe_transition NO debe llamarse con target fuera del conjunto"


def test_validacion_marca_estado_inexistente():
    from harness.task_states import validate_states_against_tracker

    profile = _profile({"in_progress": "Activo", "next_state_ok": "Estado Fantasma"})
    warnings = validate_states_against_tracker(
        profile, ["Ready for Dev", "In Progress", "Blocked", "Code Review", "Ready for QA"]
    )

    valores = {w["value"] for w in warnings}
    assert "Estado Fantasma" in valores
    assert "Activo" in valores
    assert all(w["reason"] == "state_not_in_tracker" for w in warnings)
    assert any(w.get("work_item_type") == "Task" for w in warnings), (
        "el warning debe identificar el tipo de work item del cell"
    )
    assert "Code Review" not in valores, "los estados válidos no deben generar warning"
