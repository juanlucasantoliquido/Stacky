"""Plan 270 F4 — Writeback del estado local: la fila deja de mentir.

TOCA LA DB (sqlite en memoria) => correr POR ARCHIVO.
CERO RED Y CERO TRACKER REAL: el writeback LEE del tracker, y ese tracker esta
siempre doblado. Ningun test de este archivo puede tocar el Azure DevOps ni el
GitLab del operador.

12 casos (§4 F4 del plan 270). El caso 12 cubre `diverged_count` (costura F4<->F5:
vive aca porque necesita golpear un endpoint, y el .test.ts de F5 es TS puro).
"""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

WB_FLAG = "STACKY_TICKET_STATE_WRITEBACK_ENABLED"
OPERADOR = "operador.test@example.invalid"
_ADO_MIN, _ADO_MAX = 3500, 3599


@pytest.fixture
def tmp_repo(monkeypatch):
    tmp = tempfile.TemporaryDirectory()
    monkeypatch.setenv("STACKY_REPO_ROOT", tmp.name)
    yield Path(tmp.name)
    tmp.cleanup()


class _FakeAdo:
    def __init__(self, reg):
        self._reg = reg

    def update_work_item_state(self, ado_id, new_state):
        self._reg["ado_state_calls"].append((ado_id, new_state))
        return {"id": ado_id}

    def post_comment(self, ado_id, text, fmt="html"):
        return {"id": 1}


class _FakeProvider:
    """Provider doblado: `state` es lo que devuelve get_item."""

    name = "gitlab"

    def __init__(self, reg, state="opened"):
        self._reg = reg
        self.state = state
        self.raise_on_get = False

    def update_item_state(self, item_id, logical_state):
        self._reg["gl_state_calls"].append((item_id, logical_state))
        self.state = "closed"
        return {"state": self.state}

    def get_item(self, item_id):
        self._reg["gl_get_calls"].append(item_id)
        if self.raise_on_get:
            raise RuntimeError("GitLab no responde")
        return {"state": self.state}


@pytest.fixture
def writers(monkeypatch):
    reg = {"ado_state_calls": [], "ado_built": 0, "gl_state_calls": [],
           "gl_get_calls": [], "upsert_calls": [], "provider_error": None}
    fake_ado = _FakeAdo(reg)
    fake_gl = _FakeProvider(reg)

    def _build_ado(*a, **kw):
        reg["ado_built"] += 1
        return fake_ado

    def _get_provider(project=None):
        if reg["provider_error"] is not None:
            raise reg["provider_error"]
        return fake_gl

    import api.tickets as tickets_mod
    import services.ado_client as ado_client_mod
    from services import project_context, tracker_provider

    monkeypatch.setattr(project_context, "build_ado_client", _build_ado)
    monkeypatch.setattr(tracker_provider, "get_tracker_provider", _get_provider)
    monkeypatch.setattr(tickets_mod, "_ado_client_for_ticket", lambda *a, **kw: _build_ado())
    monkeypatch.setattr(ado_client_mod, "AdoClient", lambda *a, **kw: fake_ado)
    return SimpleNamespace(reg=reg, ado=fake_ado, gitlab=fake_gl)


@pytest.fixture
def fake_upsert(monkeypatch, writers):
    """Doblega ado_sync.upsert_single_work_item: escribe ado_state y nada mas.

    El helper real hace un GET a Azure DevOps; acá NUNCA se llega a la red.
    """
    from db import session_scope
    from models import Ticket
    from services import ado_sync

    def _fake(client, ado_id):
        writers.reg["upsert_calls"].append(ado_id)
        with session_scope() as s:
            t = s.query(Ticket).filter(Ticket.ado_id == ado_id).first()
            if t is not None:
                t.ado_state = writers.reg.get("ado_remote_state", "Done")
                t.last_synced_at = datetime.utcnow()
        return {"ado_id": ado_id}

    monkeypatch.setattr(ado_sync, "upsert_single_work_item", _fake)
    return _fake


@pytest.fixture
def client(tmp_repo, monkeypatch):
    import app as app_module

    monkeypatch.setenv("STACKY_OUTPUT_WATCHER_ENABLED", "false")
    monkeypatch.setenv("STACKY_MANIFEST_WATCHER_ENABLED", "false")
    monkeypatch.setattr(app_module, "_startup_sync", lambda logger: None)
    app = app_module.create_app()
    app.config.update(TESTING=True)
    from services.ticket_status import stop_stale_recovery

    stop_stale_recovery()
    with app.test_client() as c:
        yield c
    stop_stale_recovery()


def _inbox_project() -> str:
    """El filtro de proyecto de la bandeja compara contra el contexto activo."""
    from services.project_context import resolve_project_context

    ctx = resolve_project_context()
    return (getattr(ctx, "tracker_project", None) if ctx else None) or "TEST"


def _mk_ticket(ado_id, *, tracker_type="azure_devops", ado_state="Active",
               stacky_status="running", work_item_type="Bug", con_exec=True) -> int:
    from db import session_scope
    from models import AgentExecution, Ticket

    with session_scope() as s:
        t = Ticket(
            ado_id=ado_id, project=_inbox_project(), stacky_project_name=None,
            title=f"t-{ado_id}", ado_state=ado_state, stacky_status=stacky_status,
            tracker_type=tracker_type, work_item_type=work_item_type,
        )
        s.add(t)
        s.flush()
        if con_exec:
            s.add(AgentExecution(
                ticket_id=t.id, agent_type="developer", status="running",
                input_context_json="[]", started_by="test",
                started_at=datetime.utcnow(),
            ))
            s.flush()
        return t.id


def _estado(ticket_id):
    from db import session_scope
    from models import Ticket

    with session_scope() as s:
        t = s.get(Ticket, ticket_id)
        return (t.ado_state, t.stacky_status)


def _items(client, scope="open"):
    r = client.get(f"/api/incident-inbox/items?scope={scope}")
    assert r.status_code == 200
    data = r.get_json()
    return data, [i for i in data["items"] if _ADO_MIN <= (i.get("ado_id") or 0) <= _ADO_MAX]


# ── Casos ─────────────────────────────────────────────────────────────────────

def test_1_ado_refresca_la_columna_local(client, writers, fake_upsert):
    from services.ticket_state_writeback import refresh_local_state

    tid = _mk_ticket(3501, ado_state="Active")
    writers.reg["ado_remote_state"] = "Done"
    res = refresh_local_state(tid)
    assert res["refreshed"] is True
    assert res["reason"] == "ok"
    assert _estado(tid)[0] == "Done"


def test_2_gitlab_refresca_desde_el_provider(client, writers):
    from services.ticket_state_writeback import refresh_local_state

    tid = _mk_ticket(3502, tracker_type="gitlab", ado_state="opened")
    writers.gitlab.state = "closed"
    res = refresh_local_state(tid)
    assert res["refreshed"] is True
    assert res["ado_state"] == "closed"
    assert _estado(tid)[0] == "closed"


def test_3_kpi_el_tablero_deja_de_mentir_camino_manual(client, writers, fake_upsert):
    """De punta a punta: cerrar desde la bandeja saca la fila de scope=open."""
    tid = _mk_ticket(3503, ado_state="Active", work_item_type="Issue")
    writers.reg["ado_remote_state"] = "Done"

    _, antes = _items(client, "open")
    assert any(i["ado_id"] == 3503 for i in antes), "la siembra no es visible en la bandeja"

    r = client.post(
        f"/api/tickets/{tid}/finish-work",
        json={"operator_reason": "cierre de prueba del plan 270",
              "target_ado_state": "Done", "publish_to_ado": False},
        headers={"X-User-Email": OPERADOR},
    )
    assert r.status_code == 200

    _, abiertas = _items(client, "open")
    assert not any(i["ado_id"] == 3503 for i in abiertas), "la fila sigue mintiendo"
    _, todas = _items(client, "all")
    fila = next(i for i in todas if i["ado_id"] == 3503)
    assert fila["is_open"] is False


def test_4_error_del_tracker_no_pisa_la_columna(client, writers):
    from services.ticket_state_writeback import refresh_local_state

    tid = _mk_ticket(3504, tracker_type="gitlab", ado_state="opened")
    writers.gitlab.raise_on_get = True
    res = refresh_local_state(tid)
    assert res["refreshed"] is False
    assert res["reason"].startswith("tracker_error:")
    assert _estado(tid)[0] == "opened"


def test_5_flag_off_no_refresca_ni_agrega_el_action(client, writers, fake_upsert, monkeypatch):
    from config import config as cfg
    from services.ticket_state_writeback import refresh_local_state

    monkeypatch.setattr(cfg, WB_FLAG, False)
    tid = _mk_ticket(3505, ado_state="Active")
    res = refresh_local_state(tid)
    assert res["reason"] == "flag_off"
    assert res["refreshed"] is False
    assert _estado(tid)[0] == "Active"

    r = client.post(
        f"/api/tickets/{tid}/finish-work",
        json={"operator_reason": "cierre de prueba del plan 270",
              "target_ado_state": "Done", "publish_to_ado": False},
        headers={"X-User-Email": OPERADOR},
    )
    acciones = [a.get("action") for a in (r.get_json().get("actions") or [])]
    assert "refresh_local_state" not in acciones


def test_6_ado_id_sentinela_no_gasta_una_llamada_de_red(client, writers, fake_upsert):
    from services.ticket_state_writeback import refresh_local_state

    tid = _mk_ticket(-3, ado_state="Active")
    res = refresh_local_state(tid)
    assert res["reason"] == "no_ado_id"
    assert writers.reg["upsert_calls"] == []
    assert writers.reg["gl_get_calls"] == []
    assert writers.reg["ado_built"] == 0


def test_7_el_writeback_no_pisa_stacky_status(client, writers, fake_upsert):
    from services.ticket_state_writeback import refresh_local_state

    tid = _mk_ticket(3507, ado_state="Active", stacky_status="completed")
    writers.reg["ado_remote_state"] = "Done"
    refresh_local_state(tid)
    assert _estado(tid) == ("Done", "completed")


def test_8_estado_ausente_no_pisa_la_columna(client, writers):
    from services.ticket_state_writeback import refresh_local_state

    tid = _mk_ticket(3508, tracker_type="gitlab", ado_state="opened")
    writers.gitlab.state = ""
    res = refresh_local_state(tid)
    assert res["reason"] == "state_absent"
    assert res["refreshed"] is False
    assert _estado(tid)[0] == "opened"


def test_9_los_dos_estados_literales_de_gitlab_caen_del_lado_correcto():
    from services.incident_inbox import DEFAULT_CLOSED_STATES, is_open_state

    assert is_open_state("closed", DEFAULT_CLOSED_STATES) is False
    assert is_open_state("opened", DEFAULT_CLOSED_STATES) is True


@pytest.fixture
def legacy_state_branch(monkeypatch):
    """Fuerza la rama que F3 enruta en S2 (ver la nota del archivo de F3).

    Medido: STACKY_DETERMINISTIC_TASK_STATES_ENABLED tiene default `true`
    (config.py:1260-1261), contra lo que afirma el plan, y
    deterministic_task_states_enabled() lo lee de la CLASE Config.
    """
    import config as config_module

    monkeypatch.setattr(
        config_module.Config, "STACKY_DETERMINISTIC_TASK_STATES_ENABLED", False,
        raising=False,
    )


@pytest.fixture
def publish_ok(monkeypatch):
    from services import agent_completion_internal as aci

    monkeypatch.setattr(
        aci, "close_execution_with_publish",
        lambda **kw: SimpleNamespace(publish={"ok": True, "reason": "fake"}),
    )


def test_10_kpi_en_el_camino_automatico(client, writers, publish_ok, legacy_state_branch):
    """El cierre AUTOMATICO tambien saca la fila de scope=open."""
    _mk_ticket(3510, tracker_type="gitlab", ado_state="opened", work_item_type="Issue")
    writers.gitlab.state = "opened"

    _, antes = _items(client, "open")
    assert any(i["ado_id"] == 3510 for i in antes)

    r = client.patch(
        "/api/tickets/by-ado/3510/stacky-status",
        json={"status": "completed", "target_ado_state": "Done",
              "reason": "cierre automatico de prueba"},
        headers={"X-User-Email": OPERADOR},
    )
    assert r.status_code == 200, r.get_json()
    assert writers.reg["gl_state_calls"] == [("3510", "accepted")]

    _, abiertas = _items(client, "open")
    assert not any(i["ado_id"] == 3510 for i in abiertas)


def test_11_s2_con_escritura_fallida_no_gasta_una_lectura(
    client, writers, publish_ok, legacy_state_branch
):
    from services.tracker_provider import TrackerConfigError

    _mk_ticket(3511, tracker_type="gitlab", ado_state="opened", work_item_type="Issue")
    writers.reg["provider_error"] = TrackerConfigError("STACKY_GITLAB_ENABLED=false")
    r = client.patch(
        "/api/tickets/by-ado/3511/stacky-status",
        json={"status": "completed", "target_ado_state": "Done",
              "reason": "cierre automatico de prueba"},
        headers={"X-User-Email": OPERADOR},
    )
    assert r.status_code == 200
    cambio = r.get_json().get("ado_state_change") or {}
    assert cambio.get("ok") is False
    assert "local_refresh" not in cambio
    assert writers.reg["gl_get_calls"] == []


def test_12_diverged_count_es_exacto_por_agregacion(client, writers):
    """C6 — la key del backend, con datos sembrados: 3 divergentes de 5.

    Criterio DELTA a proposito: `diverged_count` es una agregacion GLOBAL del
    proyecto y los tests anteriores de este archivo dejan filas divergentes en la
    misma base (medido: el absoluto daba 4, no 3). Medir el delta fija exactamente
    lo que la fase promete —que cuente los `completed` con estado abierto y NO
    los `completed` ya cerrados— y es inmune al orden de colección.
    """
    base, _ = _items(client, "all")
    antes = base["diverged_count"]
    assert isinstance(antes, int)

    for ado in (3521, 3522, 3523):   # completed + abierto => divergentes
        _mk_ticket(ado, ado_state="Active", stacky_status="completed",
                   work_item_type="Issue", con_exec=False)
    for ado in (3524, 3525):         # completed + cerrado => NO divergentes
        _mk_ticket(ado, ado_state="Done", stacky_status="completed",
                   work_item_type="Issue", con_exec=False)

    data, _ = _items(client, "all")
    assert data["diverged_count"] == antes + 3, (
        f"diverged_count paso de {antes} a {data.get('diverged_count')}: "
        "se esperaban exactamente 3 divergentes nuevos"
    )
