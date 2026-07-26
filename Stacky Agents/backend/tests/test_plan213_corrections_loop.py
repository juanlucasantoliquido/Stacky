"""Plan 213 F5/F6 — Confirmar o corregir un supuesto no puede ser decorativo.

El operador marca un supuesto y eso tiene que llegar al agente en la corrida
siguiente, con prioridad máxima. Si no, el agente vuelve a asumir lo mismo y el
click no sirvió para nada.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

_KEY = "STACKY_ASSUMPTION_MODE_ENABLED"
_TYPES = "STACKY_ASSUMPTION_MODE_AGENT_TYPES"


@pytest.fixture(autouse=True)
def modo_on(monkeypatch):
    from config import config as cfg

    monkeypatch.setattr(cfg, _KEY, True, raising=False)
    monkeypatch.setattr(cfg, _TYPES, "technical,functional", raising=False)


@pytest.fixture
def ticket():
    from db import init_db, session_scope
    from models import AgentExecution, Ticket

    init_db()
    with session_scope() as session:
        session.query(AgentExecution).delete()
        session.query(Ticket).delete()
        t = Ticket(ado_id=21360, project="RSPacifico", title="t",
                   ado_state="To Do", stacky_status="idle")
        session.add(t)
        session.flush()
        return t.id


def _ejecucion(ticket_id: int, items: list, minutos: int = 0,
               agent_type: str = "technical") -> int:
    from db import session_scope
    from models import AgentExecution

    with session_scope() as session:
        ex = AgentExecution(
            ticket_id=ticket_id, agent_type=agent_type, status="completed",
            input_context_json="{}", started_by="test",
            started_at=datetime.utcnow() - timedelta(minutes=minutos),
            metadata_json=json.dumps({"assumptions": {"items": items}}),
        )
        session.add(ex)
        session.flush()
        return ex.id


def _inyectar(ticket_id: int, agent_type: str = "technical", blocks=None) -> list:
    from services.context_enrichment import _inject_assumption_corrections

    return _inject_assumption_corrections(
        ticket_id, agent_type, list(blocks or []), lambda n, m: None)


def _bloque(blocks: list):
    return next((b for b in blocks if b.get("id") == "operator-corrections"), None)


# ---------------------------------------------------------------------------
# F6 — el bucle de corrección
# ---------------------------------------------------------------------------

def test_confirmed_assumption_is_injected(ticket):
    _ejecucion(ticket, [{"text": "el batch corre de noche", "status": "confirmed"}])

    bloque = _bloque(_inyectar(ticket))

    assert bloque is not None
    assert "CONFIRMADO" in bloque["content"]
    assert "el batch corre de noche" in bloque["content"]


def test_corrected_assumption_carries_the_correction(ticket):
    _ejecucion(ticket, [{
        "text": "corre a las 03:00", "status": "corrected",
        "correction": "en realidad corre a las 02:00"}])

    contenido = _bloque(_inyectar(ticket))["content"]

    assert "en realidad corre a las 02:00" in contenido
    assert "INCORRECTO" in contenido, \
        "el agente tiene que saber que su supuesto anterior estaba mal"


def test_pending_only_injects_nothing(ticket):
    _ejecucion(ticket, [{"text": "algo", "status": "pending"}])

    assert _bloque(_inyectar(ticket)) is None


def test_sin_ejecuciones_no_inyecta(ticket):
    assert _inyectar(ticket) == []


def test_corrections_accumulate_across_runs(ticket):
    """Corregir en la corrida N y confirmar otra cosa en N+1: las dos sobreviven."""
    _ejecucion(ticket, [{"text": "supuesto viejo", "status": "corrected",
                         "correction": "lo correcto es X"}], minutos=20)
    _ejecucion(ticket, [{"text": "otro supuesto", "status": "confirmed"}], minutos=10)

    contenido = _bloque(_inyectar(ticket))["content"]

    assert "lo correcto es X" in contenido
    assert "otro supuesto" in contenido


def test_el_mismo_texto_gana_la_corrida_mas_reciente(ticket):
    _ejecucion(ticket, [{"text": "mismo", "status": "corrected",
                         "correction": "decision vieja"}], minutos=20)
    _ejecucion(ticket, [{"text": "mismo", "status": "confirmed"}], minutos=5)

    contenido = _bloque(_inyectar(ticket))["content"]

    assert "CONFIRMADO" in contenido
    assert "decision vieja" not in contenido


def test_merges_with_existing_corrections_block(ticket):
    """Dos bloques con el mismo id serían ambiguos: se concatena."""
    _ejecucion(ticket, [{"text": "nuevo", "status": "confirmed"}])
    previos = [{"id": "operator-corrections", "kind": "text",
                "title": "Correcciones del operador", "content": "algo previo"}]

    blocks = _inyectar(ticket, blocks=previos)

    corrections = [b for b in blocks if b.get("id") == "operator-corrections"]
    assert len(corrections) == 1
    assert "algo previo" in corrections[0]["content"]
    assert "nuevo" in corrections[0]["content"]


def test_block_priority_is_max():
    from services.context_enrichment import _BLOCK_PRIORITY

    assert _BLOCK_PRIORITY["operator-corrections"] == 110


def test_flag_off_injects_nothing(ticket, monkeypatch):
    from config import config as cfg

    _ejecucion(ticket, [{"text": "algo", "status": "confirmed"}])
    monkeypatch.setattr(cfg, _TYPES, "", raising=False)

    assert _inyectar(ticket) == []


def test_developer_does_not_get_the_block(ticket):
    """G6: el Developer construye, no declara supuestos."""
    _ejecucion(ticket, [{"text": "algo", "status": "confirmed"}],
               agent_type="developer")

    assert _inyectar(ticket, agent_type="developer") == []


def test_secrets_are_redacted(ticket):
    _ejecucion(ticket, [{
        "text": "la clave", "status": "corrected",
        "correction": "usar password=SuperSecreto123456789"}])

    contenido = _bloque(_inyectar(ticket))["content"]

    assert "SuperSecreto123456789" not in contenido, \
        "una corrección con algo sensible no puede viajar en claro al prompt"


def test_un_error_no_rompe_el_enriquecimiento(ticket, monkeypatch):
    from services import context_enrichment

    monkeypatch.setattr("harness.run_contract.applies_to",
                        lambda t: (_ for _ in ()).throw(RuntimeError("boom")))

    assert _inyectar(ticket) == []


# ---------------------------------------------------------------------------
# F5 — el endpoint
# ---------------------------------------------------------------------------

@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("STACKY_REAPER_ENABLED", "false")
    monkeypatch.setenv("STACKY_MANIFEST_WATCHER_ENABLED", "false")

    from app import create_app
    from services.manifest_watcher import stop_manifest_watcher
    from services.ticket_status import stop_stale_recovery

    app = create_app()
    app.config.update(TESTING=True)
    stop_stale_recovery()
    stop_manifest_watcher()
    with app.test_client() as c:
        yield c
    stop_stale_recovery()
    stop_manifest_watcher()


def _ruta(exec_id: int) -> str:
    return f"/api/executions/{exec_id}/assumptions"


def test_patch_confirma(client, ticket):
    eid = _ejecucion(ticket, [{"text": "a", "status": "pending"}])

    r = client.patch(_ruta(eid), json={"updates": [{"index": 0, "status": "confirmed"}]})

    assert r.status_code == 200
    assert r.get_json()["assumptions"]["items"][0]["status"] == "confirmed"


def test_patch_corrige_con_texto(client, ticket):
    eid = _ejecucion(ticket, [{"text": "a", "status": "pending"}])

    r = client.patch(_ruta(eid), json={"updates": [
        {"index": 0, "status": "corrected", "correction": "lo correcto"}]})

    item = r.get_json()["assumptions"]["items"][0]
    assert item["status"] == "corrected" and item["correction"] == "lo correcto"


def test_patch_400_sin_correccion(client, ticket):
    eid = _ejecucion(ticket, [{"text": "a", "status": "pending"}])

    r = client.patch(_ruta(eid), json={"updates": [{"index": 0, "status": "corrected"}]})

    assert r.status_code == 400
    assert r.get_json()["error"] == "correction_required"


def test_patch_400_status_invalido(client, ticket):
    eid = _ejecucion(ticket, [{"text": "a", "status": "pending"}])

    r = client.patch(_ruta(eid), json={"updates": [{"index": 0, "status": "masomenos"}]})

    assert r.status_code == 400 and r.get_json()["error"] == "invalid_status"


def test_patch_400_index_fuera_de_rango(client, ticket):
    eid = _ejecucion(ticket, [{"text": "a", "status": "pending"}])

    for indice in (-1, 5, "x"):
        r = client.patch(_ruta(eid), json={"updates": [
            {"index": indice, "status": "confirmed"}]})
        assert r.status_code == 400 and r.get_json()["error"] == "invalid_index", indice


def test_patch_404_ejecucion_inexistente(client):
    assert client.patch(_ruta(999999), json={"updates": []}).status_code == 404


def test_patch_es_idempotente(client, ticket):
    eid = _ejecucion(ticket, [{"text": "a", "status": "pending"}])
    cuerpo = {"updates": [{"index": 0, "status": "confirmed"}]}

    primero = client.patch(_ruta(eid), json=cuerpo).get_json()
    segundo = client.patch(_ruta(eid), json=cuerpo).get_json()

    assert primero == segundo


def test_patch_guarda_json_serializado(client, ticket):
    """metadata_json es Text: un dict crudo la dejaría como feature muerta."""
    from db import session_scope
    from models import AgentExecution

    eid = _ejecucion(ticket, [{"text": "a", "status": "pending"}])
    client.patch(_ruta(eid), json={"updates": [{"index": 0, "status": "confirmed"}]})

    with session_scope() as session:
        crudo = session.get(AgentExecution, eid).metadata_json

    assert isinstance(crudo, str)
    assert json.loads(crudo)["assumptions"]["items"][0]["status"] == "confirmed"


def test_patch_no_tiene_efectos_colaterales(client, ticket):
    """G1: decidir sobre un supuesto no mueve el ticket ni relanza nada."""
    from db import session_scope
    from models import AgentExecution, Ticket

    eid = _ejecucion(ticket, [{"text": "a", "status": "pending"}])
    with session_scope() as session:
        estado_antes = session.get(Ticket, ticket).ado_state
        status_antes = session.get(AgentExecution, eid).status

    client.patch(_ruta(eid), json={"updates": [{"index": 0, "status": "confirmed"}]})

    with session_scope() as session:
        assert session.get(Ticket, ticket).ado_state == estado_antes
        assert session.get(AgentExecution, eid).status == status_antes
