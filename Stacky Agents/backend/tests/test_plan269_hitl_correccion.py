"""Plan 269 F6 — HITL: corregir UNA incidencia sin publicar en el tracker real.

TOCA LA DB (sqlite en memoria) => correr POR ARCHIVO.
El punto central: el endpoint elegido NO escribe en el Azure DevOps ni en el
GitLab del operador. El test 1 lo prueba contando filas en agent_html_publish.

6 casos (§5 F6 del plan 269).
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

HITL_FLAG = "STACKY_RUN_RECONCILIATION_HITL_ENABLED"
OPERADOR = "operador.test@example.invalid"


@pytest.fixture
def client(monkeypatch):
    import app as app_module

    tmp = tempfile.TemporaryDirectory()
    monkeypatch.setenv("STACKY_REPO_ROOT", tmp.name)
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
    tmp.cleanup()


def _ticket(ado_id, stacky_status="error"):
    from db import session_scope
    from models import Ticket

    with session_scope() as s:
        t = Ticket(ado_id=ado_id, project="P269H", title=f"t-{ado_id}",
                   ado_state="Active", stacky_status=stacky_status,
                   tracker_type="azure_devops", work_item_type="Bug")
        s.add(t)
        s.flush()
        return t.id


def _publicaciones():
    from db import session_scope
    from services.ado_publisher import AgentHtmlPublish

    with session_scope() as s:
        return s.query(AgentHtmlPublish).count()


def _corregir(client, ticket_id, status="completed", reason="[269] prueba"):
    # La ruta PERMITIDA: por ticket_id. NUNCA la que va por ado_id, que publica.
    return client.patch(
        f"/api/tickets/{ticket_id}/stacky-status",
        json={"status": status, "reason": reason},
        headers={"X-User-Email": OPERADOR},
    )


def test_1_patch_por_ticket_id_no_publica(client):
    """La prueba de que el HITL NO escribe en el tracker real del operador."""
    tid = _ticket(7301)
    antes = _publicaciones()
    r = _corregir(client, tid)
    assert r.status_code == 200, r.get_data(as_text=True)
    assert _publicaciones() == antes, "el HITL publico algo en el tracker"


def test_2_patch_por_ticket_id_no_corre_post_hooks(client):
    """El guard y los hooks son de on_execution_end, no de set_status."""
    from services import ticket_status as ts

    marca = {"corrio": False}

    def _hook(*a, **kw):
        marca["corrio"] = True

    registrar = getattr(ts, "register_post_hook", None)
    if registrar is None:
        pytest.skip("register_post_hook no existe en este arbol")
    registrar(_hook)
    tid = _ticket(7302)
    r = _corregir(client, tid)
    assert r.status_code == 200
    assert marca["corrio"] is False, "set_status disparo un post-hook"


def test_3_correccion_queda_auditada(client):
    """changed_by = el header X-User-Email, no 'system': es mano humana."""
    from db import session_scope
    from services.ticket_status import TicketStatusEvent

    tid = _ticket(7303)
    r = _corregir(client, tid, reason="[269] correccion manual de falso rojo (execution 9)")
    assert r.status_code == 200
    with session_scope() as s:
        eventos = (
            s.query(TicketStatusEvent)
            .filter(TicketStatusEvent.ticket_id == tid)
            .all()
        )
        assert eventos, "no quedo auditada la correccion"
        assert any(e.changed_by == OPERADOR for e in eventos), (
            f"changed_by no es el operador: {[e.changed_by for e in eventos]}"
        )


def test_4_estado_invalido_devuelve_400(client):
    tid = _ticket(7304)
    r = _corregir(client, tid, status="published")
    assert r.status_code == 400, (
        f"un estado fuera del vocabulario deberia dar 400, dio {r.status_code}"
    )


def test_5_flag_off_no_ofrece_hitl(client, monkeypatch):
    from config import config as cfg

    r_on = client.get("/api/diag/run-reconciliation")
    assert r_on.status_code == 200
    assert r_on.get_json().get("hitl_enabled") is True

    monkeypatch.setattr(cfg, HITL_FLAG, False)
    r_off = client.get("/api/diag/run-reconciliation")
    assert r_off.status_code == 200
    assert r_off.get_json().get("hitl_enabled") is False


def test_6_rama_de_error_no_ofrece_hitl(client, monkeypatch):
    """Falla CERRADO: ausencia o false => la card no dibuja botones."""
    from services import run_reconciliation as rr

    def _boom(*a, **kw):
        raise RuntimeError("scan roto")

    monkeypatch.setattr(rr, "summarize", _boom)
    r = client.get("/api/diag/run-reconciliation")
    assert r.status_code == 200, "el endpoint debe degradar, no reventar"
    data = r.get_json()
    assert not data.get("hitl_enabled"), (
        f"la rama de error ofrecio HITL: {data.get('hitl_enabled')!r}"
    )
