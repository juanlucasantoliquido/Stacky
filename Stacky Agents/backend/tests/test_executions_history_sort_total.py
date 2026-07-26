"""Plan 173 F5 — `sort` + `include_total` en GET /api/executions/history.

Ver Stacky Agents/docs/173_PLAN_VISTAS_GUARDADAS_PRESETS_DE_FILTROS_Y_PREFERENCIAS_DE_TABLA.md §F5.

Los dos son ADITIVOS y opt-in: lo que más importa acá es que el contrato viejo
(una lista pelada) siga byte-compatible, porque hay consumidores que lo esperan.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")


@pytest.fixture(scope="module")
def _app():
    os.environ["STACKY_EXECUTION_HISTORY_ENABLED"] = "true"
    from app import create_app

    app = create_app()
    app.config["TESTING"] = True
    return app


@pytest.fixture(scope="module")
def client(_app):
    with _app.test_client() as c:
        yield c


# Rango propio para no colisionar con test_executions_history (90000).
_NEXT_ADO_ID = 91000
_PROYECTO = "sorttotalproj"


def _seed_exec(*, agent_type: str = "developer", status: str = "completed",
               started_at: datetime | None = None, runtime: str = "codex_cli"):
    global _NEXT_ADO_ID
    _NEXT_ADO_ID += 1
    ado_id = _NEXT_ADO_ID

    from db import session_scope
    from models import AgentExecution, Ticket

    with session_scope() as session:
        t = Ticket(
            ado_id=ado_id,
            project=_PROYECTO,
            stacky_project_name=_PROYECTO,
            title=f"Ticket {ado_id}",
            ado_state="Active",
        )
        session.add(t)
        session.flush()

        when = started_at or datetime.utcnow()
        e = AgentExecution(
            ticket_id=t.id,
            agent_type=agent_type,
            status=status,
            input_context_json="[]",
            started_by="test",
            started_at=when,
            completed_at=when + timedelta(seconds=10),
            metadata_json=json.dumps({"runtime": runtime, "model": "o4-mini"}),
        )
        session.add(e)
        session.flush()
        return e.id


def _get(client, qs: str = ""):
    return client.get(f"/api/executions/history?project={_PROYECTO}{qs}")


# ---------------------------------------------------------------------------
# Contrato legacy
# ---------------------------------------------------------------------------

def test_sin_include_total_la_respuesta_sigue_siendo_una_lista_pelada(client):
    # Envolverla siempre rompería a cualquier consumidor que haga body.map(...).
    _seed_exec()

    body = _get(client).get_json()

    assert isinstance(body, list)


def test_un_sort_desconocido_no_es_un_400(client):
    # Un `sort` que no existe es un cliente viejo o un typo: se cae al orden de
    # siempre en vez de romperle la pantalla al operador.
    _seed_exec()

    resp = _get(client, "&sort=columna_inventada&dir=asc")

    assert resp.status_code == 200
    assert isinstance(resp.get_json(), list)


# ---------------------------------------------------------------------------
# include_total
# ---------------------------------------------------------------------------

def test_include_total_devuelve_envelope(client):
    for _ in range(3):
        _seed_exec()

    body = _get(client, "&include_total=1&limit=2").get_json()

    assert isinstance(body, dict)
    assert len(body["items"]) == 2
    # El total cuenta TODO lo filtrado, no lo paginado.
    assert body["total"] >= 3


def test_el_total_no_depende_de_la_pagina(client):
    _seed_exec()

    p1 = _get(client, "&include_total=1&limit=1&offset=0").get_json()
    p2 = _get(client, "&include_total=1&limit=1&offset=1").get_json()

    assert p1["total"] == p2["total"]


def test_el_total_respeta_los_filtros_sql(client):
    _seed_exec(agent_type="developer")
    _seed_exec(agent_type="tester")

    todos = _get(client, "&include_total=1").get_json()["total"]
    testers = _get(client, "&include_total=1&agent_type=tester").get_json()["total"]

    assert testers < todos


def test_include_total_acepta_las_formas_habituales(client):
    _seed_exec()

    for valor in ("1", "true", "yes"):
        assert isinstance(_get(client, f"&include_total={valor}").get_json(), dict)
    for valor in ("0", "false", ""):
        assert isinstance(_get(client, f"&include_total={valor}").get_json(), list)


# ---------------------------------------------------------------------------
# sort
# ---------------------------------------------------------------------------

def test_sort_id_asc(client):
    for _ in range(3):
        _seed_exec()

    ids = [it["id"] for it in _get(client, "&sort=id&dir=asc&include_total=1").get_json()["items"]]

    assert ids == sorted(ids)


def test_sort_id_desc(client):
    for _ in range(3):
        _seed_exec()

    ids = [it["id"] for it in _get(client, "&sort=id&dir=desc&include_total=1").get_json()["items"]]

    assert ids == sorted(ids, reverse=True)


def test_el_default_sigue_siendo_started_at_desc(client):
    # Cambiar el orden por default sería un cambio de comportamiento silencioso
    # para todas las pantallas que ya consumen esto.
    viejo = _seed_exec(started_at=datetime.utcnow() - timedelta(days=3))
    nuevo = _seed_exec(started_at=datetime.utcnow())

    ids = [it["id"] for it in _get(client).get_json()]

    assert ids.index(nuevo) < ids.index(viejo)


def test_sort_por_agent_type(client):
    _seed_exec(agent_type="aaa")
    _seed_exec(agent_type="zzz")

    tipos = [
        it["agent_type"]
        for it in _get(client, "&sort=agent_type&dir=asc&include_total=1").get_json()["items"]
    ]

    assert tipos == sorted(tipos)


def test_el_sort_ordena_el_conjunto_entero_no_solo_la_pagina(client):
    """La aserción que distingue ordenar de "ordenar lo que ya vino"."""
    for _ in range(4):
        _seed_exec()

    todos = [it["id"] for it in _get(client, "&sort=id&dir=asc&include_total=1&limit=500").get_json()["items"]]
    primera = _get(client, "&sort=id&dir=asc&include_total=1&limit=2").get_json()["items"]

    assert [it["id"] for it in primera] == todos[:2]
