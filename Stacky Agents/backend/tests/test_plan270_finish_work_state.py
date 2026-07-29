"""Plan 270 F3 — finish_work y el cierre automatico escriben en el tracker CORRECTO.

TOCA LA DB (sqlite en memoria) => correr POR ARCHIVO.
CERO RED Y CERO TRACKER REAL: todo escritor de estado esta doblado (ver la
fixture `writers`). Ningun test de este archivo puede tocar el Azure DevOps ni
el GitLab del operador.

10 casos (§4 F3 del plan 270): 1-7 sobre S1 (finish_work), 8-10 sobre S2
(set_stacky_status_by_ado, el camino automatico de mayor volumen).
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

FLAG = "STACKY_TRACKER_STATE_WRITE_ROUTING_ENABLED"
# Correo sinteticamente falso: nunca PII real en fixtures (.invalid es reservado).
OPERADOR = "operador.test@example.invalid"


@pytest.fixture
def tmp_repo(monkeypatch):
    tmp = tempfile.TemporaryDirectory()
    monkeypatch.setenv("STACKY_REPO_ROOT", tmp.name)
    yield Path(tmp.name)
    tmp.cleanup()


class _FakeAdo:
    """Cliente ADO doblado. Registra, no hace red."""

    def __init__(self, registro):
        self._registro = registro

    def update_work_item_state(self, ado_id, new_state):
        self._registro["ado_state_calls"].append((ado_id, new_state))
        return {"id": ado_id, "fields": {"System.State": new_state}}

    def post_comment(self, ado_id, text, fmt="html"):
        return {"id": 1, "url": "fake://c"}


class _FakeGitLabProvider:
    name = "gitlab"

    def __init__(self, registro):
        self._registro = registro
        self.state = "opened"

    def update_item_state(self, item_id, logical_state):
        self._registro["gl_state_calls"].append((item_id, logical_state))
        self.state = "closed"
        return {"state": self.state}

    def get_item(self, item_id):
        self._registro["gl_get_calls"].append(item_id)
        return {"state": self.state}


@pytest.fixture
def writers(monkeypatch):
    """Doblega TODOS los caminos de escritura de estado. Cero red, cero tracker real."""
    reg = {
        "ado_state_calls": [],
        "ado_built": 0,
        "gl_state_calls": [],
        "gl_get_calls": [],
        "provider_error": None,
    }
    fake_ado = _FakeAdo(reg)
    fake_gl = _FakeGitLabProvider(reg)

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

    # Camino del router (F1) y camino historico (rollback), los dos doblados.
    monkeypatch.setattr(project_context, "build_ado_client", _build_ado)
    monkeypatch.setattr(tracker_provider, "get_tracker_provider", _get_provider)
    monkeypatch.setattr(tickets_mod, "_ado_client_for_ticket", lambda *a, **kw: _build_ado())
    monkeypatch.setattr(ado_client_mod, "AdoClient", lambda *a, **kw: fake_ado)

    return SimpleNamespace(reg=reg, ado=fake_ado, gitlab=fake_gl)


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


def _mk_ticket(ado_id: int, *, tracker_type="azure_devops", stacky_status="running",
               ado_state="In Progress", work_item_type="Bug") -> int:
    from db import session_scope
    from models import AgentExecution, Ticket

    with session_scope() as session:
        t = Ticket(
            ado_id=ado_id, project="RSPacifico", title=f"t-{ado_id}",
            ado_state=ado_state, stacky_status=stacky_status,
            tracker_type=tracker_type, work_item_type=work_item_type,
        )
        session.add(t)
        session.flush()
        session.add(AgentExecution(
            ticket_id=t.id, agent_type="developer", status="running",
            input_context_json="[]", started_by="test", started_at=datetime.utcnow(),
        ))
        session.flush()
        return t.id


def _finish(client, ticket_id, target="Done"):
    return client.post(
        f"/api/tickets/{ticket_id}/finish-work",
        json={
            "operator_reason": "cierre de prueba del plan 270",
            "target_ado_state": target,
            "publish_to_ado": False,
        },
        headers={"X-User-Email": OPERADOR},
    )


def _accion(resp, nombre="update_ado_state"):
    data = resp.get_json()
    return next((a for a in (data.get("actions") or []) if a.get("action") == nombre), None)


# ── S1 — finish_work ──────────────────────────────────────────────────────────

def test_1_ticket_ado_recibe_exactamente_el_mismo_argumento_que_hoy(client, writers):
    tid = _mk_ticket(3401)
    r = _finish(client, tid, "Done")
    assert r.status_code == 200
    assert (3401, "Done") in writers.reg["ado_state_calls"]


def test_2_ticket_gitlab_va_al_provider_y_el_cliente_ado_no_se_instancia(client, writers):
    tid = _mk_ticket(3402, tracker_type="gitlab")
    r = _finish(client, tid, "Done")
    assert r.status_code == 200
    assert writers.reg["gl_state_calls"] == [("3402", "accepted")]
    assert writers.reg["ado_built"] == 0, "se construyo un cliente ADO para un ticket GitLab"
    assert writers.reg["ado_state_calls"] == []


def test_3_gitlab_sin_proveedor_falla_declarado_y_no_escribe_en_ado(client, writers):
    from services.tracker_provider import TrackerConfigError

    writers.reg["provider_error"] = TrackerConfigError(
        "issue_tracker.type=gitlab pero STACKY_GITLAB_ENABLED=false"
    )
    tid = _mk_ticket(3403, tracker_type="gitlab")
    r = _finish(client, tid, "Done")
    assert r.status_code == 200
    acc = _accion(r)
    assert acc is not None and acc["ok"] is False
    assert "gitlab" in acc["reason"].lower()
    assert writers.reg["ado_built"] == 0
    assert writers.reg["ado_state_calls"] == []
    # El workaround viaja hasta la UI: nombra la flag literal.
    assert "STACKY_GITLAB_ENABLED" in acc["reason"]


def test_4_rollback_por_flag_off_vuelve_al_camino_historico(client, writers, monkeypatch):
    import config

    monkeypatch.setattr(config.config, FLAG, False)
    tid = _mk_ticket(3404, tracker_type="gitlab")
    r = _finish(client, tid, "Done")
    assert r.status_code == 200
    # Camino historico: _provider_for_ticket devuelve None (su flag esta OFF) y
    # cae al cliente ADO, bug incluido. Es el rollback.
    assert writers.reg["ado_built"] >= 1
    assert writers.reg["gl_state_calls"] == []


def test_5_las_keys_aditivas_no_rompen_el_contrato_viejo(client, writers):
    tid = _mk_ticket(3405)
    r = _finish(client, tid, "Done")
    acc = _accion(r)
    assert acc is not None
    for key in ("action", "ok", "to", "reason"):
        assert key in acc, f"se perdio la key historica {key}"
    assert acc["requested"] == "Done"
    assert acc["tracker_type"] == "azure_devops"
    assert acc["to"] == "Done"


def test_6_estado_no_mapeable_en_gitlab_no_emite_ninguna_escritura(client, writers):
    tid = _mk_ticket(3406, tracker_type="gitlab")
    r = _finish(client, tid, "Cualquier Cosa")
    assert r.status_code == 200
    acc = _accion(r)
    assert acc is not None and acc["ok"] is False
    assert acc["reason"].startswith("ValueError")
    assert writers.reg["gl_state_calls"] == []


def test_7_c1_el_bug_de_integracion_de_la_2_tupla_esta_fijado(client, writers):
    """resolve_closed_states NO se monkeypatchea: devuelve su 2-tupla real.

    Si el implementador olvida el desempaquetado, este test da ok=False con
    reason 'ValueError: unmappable_state:Done'.
    """
    tid = _mk_ticket(3407, tracker_type="gitlab")
    r = _finish(client, tid, "Done")
    acc = _accion(r)
    assert acc is not None, "no hubo action update_ado_state"
    assert acc["ok"] is True, f"la 2-tupla no se desempaqueto: {acc.get('reason')}"
    assert writers.reg["gl_state_calls"] == [("3407", "accepted")]


# ── S2 — set_stacky_status_by_ado (camino automatico) ──────────────────────────

@pytest.fixture
def publish_ok(monkeypatch):
    """Fuerza publish_result.ok=True para llegar a la rama `elif target_ado_state`.

    El handler importa close_execution_with_publish LOCALMENTE (api/tickets.py:1368)
    desde services.agent_completion_internal, asi que el monkeypatch va sobre el
    modulo de origen. MONKEYPATCH, no edicion: ese archivo es territorio del plan
    271 y este plan no lo modifica (el DoD lo verifica con git diff --stat).
    """
    from services import agent_completion_internal as aci

    def _fake_close(**kwargs):
        return SimpleNamespace(publish={"ok": True, "reason": "fake"})

    monkeypatch.setattr(aci, "close_execution_with_publish", _fake_close)
    return _fake_close


@pytest.fixture
def legacy_state_branch(monkeypatch):
    """Fuerza la rama que F3 enruta en S2, en vez de depender de un default.

    SUPUESTO DEL PLAN QUE RESULTO FALSO AL MEDIRLO. El plan 270 (F3, caso 8)
    afirma que "con STACKY_DETERMINISTIC_TASK_STATES_ENABLED en su default OFF,
    esa es la rama viva". Medido en este arbol: config.py:1260-1261 declara el
    default "true" y el valor efectivo es True, asi que con los defaults de
    fabrica un cierre `completed` entra por _apply_task_state (eje del plan 79,
    sitio S4 del censo) y NO por el `elif target_ado_state` que F3 toca.

    Por eso el test fuerza la flag EXPLICITAMENTE en vez de apoyarse en una
    decision de configuracion (regla del repo). Ademas
    deterministic_task_states_enabled() (harness/task_states.py:19-26) lee
    getattr(Config, KEY) sobre la CLASE, no sobre la instancia config.config:
    parchear la instancia no lo apaga.
    """
    import config as config_module

    monkeypatch.setattr(
        config_module.Config, "STACKY_DETERMINISTIC_TASK_STATES_ENABLED", False,
        raising=False,
    )
    return True


def _patch_status(client, ado_id, target="Done"):
    return client.patch(
        f"/api/tickets/by-ado/{ado_id}/stacky-status",
        json={"status": "completed", "target_ado_state": target,
              "reason": "cierre automatico de prueba"},
        headers={"X-User-Email": OPERADOR},
    )


def test_8_s2_ticket_gitlab_va_al_provider_y_no_instancia_el_cliente_ado(
    client, writers, publish_ok, legacy_state_branch
):
    _mk_ticket(3408, tracker_type="gitlab")
    r = _patch_status(client, 3408, "Done")
    assert r.status_code == 200, r.get_json()
    assert writers.reg["gl_state_calls"] == [("3408", "accepted")]
    assert writers.reg["ado_built"] == 0
    assert writers.reg["ado_state_calls"] == []


def test_9_s2_con_flag_off_vuelve_al_camino_historico(
    client, writers, publish_ok, legacy_state_branch, monkeypatch
):
    import config

    monkeypatch.setattr(config.config, FLAG, False)
    _mk_ticket(3409, tracker_type="gitlab")
    r = _patch_status(client, 3409, "Done")
    assert r.status_code == 200
    assert writers.reg["ado_built"] >= 1
    assert writers.reg["gl_state_calls"] == []


def test_10_s2_paridad_ado_byte_identica(client, writers, publish_ok, legacy_state_branch):
    _mk_ticket(3410, tracker_type="azure_devops")
    r = _patch_status(client, 3410, "Done")
    assert r.status_code == 200
    assert (3410, "Done") in writers.reg["ado_state_calls"]

