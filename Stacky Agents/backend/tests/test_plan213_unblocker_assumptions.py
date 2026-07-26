"""Plan 213 F7 — Los supuestos de alto impacto aparecen donde el operador ya mira.

Regla dura del plan: esto es INFORMATIVO. Todo el 213 existe para dejar de
frenar el pipeline; si este aviso bloqueara el ticket, lo anularía entero.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

_KEY = "STACKY_ASSUMPTION_MODE_ENABLED"
_TYPES = "STACKY_ASSUMPTION_MODE_AGENT_TYPES"
_ADO = 21370


@pytest.fixture(autouse=True)
def modo_on(monkeypatch):
    from config import config as cfg

    monkeypatch.setattr(cfg, _KEY, True, raising=False)
    monkeypatch.setattr(cfg, _TYPES, "technical,functional", raising=False)


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("STACKY_REAPER_ENABLED", "false")
    monkeypatch.setenv("STACKY_MANIFEST_WATCHER_ENABLED", "false")

    from db import init_db, session_scope
    from models import AgentExecution, Ticket

    init_db()
    with session_scope() as session:
        session.query(AgentExecution).delete()
        session.query(Ticket).delete()

    import api.tickets as tickets_mod
    from app import create_app
    from services.manifest_watcher import stop_manifest_watcher
    from services.ticket_status import stop_stale_recovery

    monkeypatch.setattr(tickets_mod, "REPO_ROOT", tmp_path)
    app = create_app()
    app.config.update(TESTING=True)
    stop_stale_recovery()
    stop_manifest_watcher()
    with app.test_client() as c:
        yield c
    stop_stale_recovery()
    stop_manifest_watcher()


def _sembrar(items: list, agent_type: str = "technical", ado_id: int = _ADO) -> int:
    """Ticket con comment.html (para que entre al board) y su última ejecución."""
    from db import session_scope
    from models import AgentExecution, Ticket

    with session_scope() as session:
        t = Ticket(ado_id=ado_id, project="TestProject", title="t",
                   work_item_type="Task", ado_state="Active",
                   stacky_status="idle")
        session.add(t)
        session.flush()
        ex = AgentExecution(
            ticket_id=t.id, agent_type=agent_type, status="completed",
            input_context_json="{}", started_by="test",
            started_at=datetime.utcnow(),
            metadata_json=json.dumps({"assumptions": {"items": items}}),
        )
        session.add(ex)
        session.flush()
        return t.id


def _item(impact: str, status: str = "pending") -> dict:
    return {"text": "algo", "basis": "", "impact": impact,
            "needs_confirmation": impact == "high", "status": status}


def _blockers(client) -> list:
    from api.tickets import _supuestos_altos_sin_confirmar  # noqa: F401  (existencia)

    body = client.get("/api/tickets/unblocker-board").get_json()
    todos: list = []
    for item in body.get("items", []):
        todos.extend(item.get("blockers") or [])
    return todos


# ---------------------------------------------------------------------------
# El helper, directo
# ---------------------------------------------------------------------------

def _ejecucion_falsa(items: list, agent_type: str = "technical"):
    class _Fake:
        def __init__(self):
            self.agent_type = agent_type
            self.metadata_dict = {"assumptions": {"items": items}}
    return _Fake()


def test_cuenta_solo_los_altos_pendientes():
    from api.tickets import _supuestos_altos_sin_confirmar

    n = _supuestos_altos_sin_confirmar(_ejecucion_falsa([
        _item("high"), _item("high"), _item("medium"), _item("low")]))

    assert n == 2


def test_ignora_los_confirmados():
    from api.tickets import _supuestos_altos_sin_confirmar

    assert _supuestos_altos_sin_confirmar(_ejecucion_falsa([
        _item("high", "confirmed"), _item("high", "corrected")])) == 0


def test_ignora_low_y_medium():
    from api.tickets import _supuestos_altos_sin_confirmar

    assert _supuestos_altos_sin_confirmar(_ejecucion_falsa([
        _item("medium"), _item("low")])) == 0


def test_item_sin_status_cuenta_como_pendiente():
    """Una metadata vieja sin `status` es un supuesto que nadie miró."""
    from api.tickets import _supuestos_altos_sin_confirmar

    assert _supuestos_altos_sin_confirmar(
        _ejecucion_falsa([{"text": "x", "impact": "high"}])) == 1


def test_developer_no_cuenta():
    """G6: el Developer no declara supuestos."""
    from api.tickets import _supuestos_altos_sin_confirmar

    assert _supuestos_altos_sin_confirmar(
        _ejecucion_falsa([_item("high")], agent_type="developer")) == 0


def test_sin_ejecucion_da_cero():
    from api.tickets import _supuestos_altos_sin_confirmar

    assert _supuestos_altos_sin_confirmar(None) == 0


def test_metadata_rota_no_rompe_el_board():
    from api.tickets import _supuestos_altos_sin_confirmar

    class _Roto:
        agent_type = "technical"

        @property
        def metadata_dict(self):
            raise RuntimeError("metadata ilegible")

    assert _supuestos_altos_sin_confirmar(_Roto()) == 0


def test_flag_off_no_cuenta(monkeypatch):
    from config import config as cfg

    from api.tickets import _supuestos_altos_sin_confirmar

    monkeypatch.setattr(cfg, _TYPES, "", raising=False)

    assert _supuestos_altos_sin_confirmar(_ejecucion_falsa([_item("high")])) == 0


# ---------------------------------------------------------------------------
# El board
# ---------------------------------------------------------------------------

def _comment(tmp_path: Path, ado_id: int = _ADO) -> None:
    destino = tmp_path / "Agentes" / "outputs" / str(ado_id)
    destino.mkdir(parents=True, exist_ok=True)
    (destino / "comment.html").write_text("<p>x</p>", encoding="utf-8")


def test_board_lists_high_impact_pending(client, tmp_path):
    _sembrar([_item("high"), _item("high"), _item("low")])
    _comment(tmp_path)

    avisos = [b for b in _blockers(client) if "supuesto_alto_sin_confirmar" in b]

    assert len(avisos) == 1
    assert "2 supuesto(s)" in avisos[0]


def test_board_ignores_confirmed(client, tmp_path):
    _sembrar([_item("high", "confirmed")])
    _comment(tmp_path)

    assert not [b for b in _blockers(client) if "supuesto_alto" in b]


def test_board_entry_does_not_change_ticket_state(client, tmp_path):
    """El aviso es visibilidad, no un gate: el ticket no se mueve."""
    from db import session_scope
    from models import Ticket

    tid = _sembrar([_item("high")])
    _comment(tmp_path)
    with session_scope() as session:
        antes = (session.get(Ticket, tid).ado_state,
                 session.get(Ticket, tid).stacky_status)

    client.get("/api/tickets/unblocker-board")

    with session_scope() as session:
        assert (session.get(Ticket, tid).ado_state,
                session.get(Ticket, tid).stacky_status) == antes


def test_flag_off_board_identical(client, tmp_path, monkeypatch):
    from config import config as cfg

    _sembrar([_item("high")])
    _comment(tmp_path)
    con_flag = client.get("/api/tickets/unblocker-board").get_json()

    monkeypatch.setattr(cfg, _TYPES, "", raising=False)
    sin_flag = client.get("/api/tickets/unblocker-board").get_json()

    avisos_con = [b for i in con_flag["items"] for b in i.get("blockers") or []
                  if "supuesto_alto" in b]
    avisos_sin = [b for i in sin_flag["items"] for b in i.get("blockers") or []
                  if "supuesto_alto" in b]
    assert avisos_con and not avisos_sin


# ---------------------------------------------------------------------------
# KPI-1: el freno silencioso queda medible, no solo logueado
# ---------------------------------------------------------------------------

def test_kpi_blocked_without_pending_persisted():
    """C6: un contador consultable, no una línea de log que nadie agrega."""
    from services.assumptions import apply_to_metadata

    meta: dict = {}
    apply_to_metadata(
        "technical",
        "❓ CONSULTA TÉCNICA (pre-bloqueo): no sé el tope y me detengo",
        meta)

    assert meta["assumptions"]["blocked_without_pending"] is True


def test_kpi_no_se_marca_si_declaro_el_pendiente():
    from services.assumptions import apply_to_metadata

    meta: dict = {}
    apply_to_metadata(
        "technical",
        "❓ CONSULTA TÉCNICA (pre-bloqueo): falta el tope\n"
        "[PENDIENTE: tope | necesito: el valor de negocio]",
        meta)

    assert meta["assumptions"]["blocked_without_pending"] is False
