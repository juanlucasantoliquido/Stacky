"""Plan 295 F9 — los receptores de webhook dejan de machear un ticket AJENO.

EL BUG, medido: `api/phase6.py:167` y `:221` hacían
`session.query(Ticket).filter_by(ado_id=int(ado_id)).first()`, sin proyecto y sin
tracker. Y `ado_id` NO ES ÚNICO (models.py:42 lo declara `nullable=False` pero NO
`unique=True`; el único índice único es la TERNA
`(stacky_project_name, tracker_type, external_id)`, models.py:77-83). En GitLab
`ado_id` lleva el IID -- el número visible DENTRO del proyecto, que se REPITE entre
proyectos (gitlab_sync.py:12-16). Con dos proyectos GitLab que tengan un issue #42,
el webhook macheaba el del proyecto equivocado y CORRÍA EL DebugAgent SOBRE ÉL.

Y el auto-creado de `:170-175` escribía `project="RSPacifico"` HARDCODEADO, sin
`stacky_project_name` y sin `tracker_type` => caía en el default "azure_devops"
(models.py:49): un ticket ADO sintético dentro de un proyecto GitLab.

AISLAMIENTO: base y data_dir en tmp_path. Este archivo CREA FILAS, así que sin el
aislamiento escribe en la BD REAL del operador.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

_PROY_A = "ProyA"
_PROY_B = "ProyB"


class _Ctx:
    """Doble de ProjectContext. Se parchea el símbolo YA IMPORTADO en api.phase6,
    NO `services/project_context.py`, que la sesión paralela está editando."""

    def __init__(self, nombre, tracker_project, tracker_type):
        self.stacky_project_name = nombre
        self.tracker_project = tracker_project
        self.tracker_type = tracker_type


_CATALOGO = {
    _PROY_A: _Ctx(_PROY_A, "grupo/proy-a", "gitlab"),
    _PROY_B: _Ctx(_PROY_B, "grupo/proy-b", "gitlab"),
    "ProyADO": _Ctx("ProyADO", "TrackerADO", "azure_devops"),
}


@pytest.fixture
def entorno(tmp_path, monkeypatch):
    """Base FRESCA por caso.

    `db.engine` es de MÓDULO y se crea en el primer import (db.py:32), así que
    `DATABASE_URL` sólo manda la primera vez: los casos siguientes comparten esa
    base. Por eso se PURGA la tabla en cada caso, y se verifica que la base no sea
    la del operador -- un pytest suelto sin esta guarda le escribe filas reales.
    """
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'plan295.db'}")
    monkeypatch.setenv("STACKY_DATA_DIR", str(tmp_path))

    return tmp_path


@pytest.fixture
def cliente(entorno, monkeypatch):
    from app import create_app

    app = create_app()          # crea las tablas (init_db)
    app.config["TESTING"] = True

    import db as _db

    url = str(_db.engine.url)
    assert "Temp" in url or "tmp" in url or ":memory:" in url, (
        f"la base del test NO está aislada, apunta a {url!r}: abortar antes de escribir"
    )
    from models import Ticket

    with _db.session_scope() as s:
        s.query(Ticket).delete()

    with app.test_client() as c:
        yield c


@pytest.fixture
def activo(monkeypatch):
    """Devuelve un setter del proyecto ACTIVO usado cuando el payload no nombra uno."""
    import api.phase6 as phase6

    estado = {"nombre": _PROY_A}

    def _resolver(project_name=None, **kw):
        nombre = (project_name or "").strip() or estado["nombre"]
        # `resolve_project_context` acepta el tracker_project como project_name
        # (su docstring :381-386): se replica esa tolerancia.
        if nombre in _CATALOGO:
            return _CATALOGO[nombre]
        for ctx in _CATALOGO.values():
            if ctx.tracker_project == nombre:
                return ctx
        return None

    monkeypatch.setattr(phase6, "resolve_project_context", _resolver, raising=False)
    return estado


@pytest.fixture
def sin_agente(monkeypatch):
    """El DebugAgent NO se lanza de verdad. Devuelve el contador de llamadas."""
    import agent_runner

    llamadas: list[dict] = []

    def _fake(**kw):
        llamadas.append(kw)
        return 12345

    monkeypatch.setattr(agent_runner, "run_agent", _fake)
    from services import runtime_capabilities

    monkeypatch.setattr(
        runtime_capabilities, "resolve_run_selection",
        lambda **kw: {"model": "m", "effort": "e"}, raising=False,
    )
    return llamadas


def _sembrar(**campos):
    from db import session_scope
    from models import Ticket

    with session_scope() as s:
        t = Ticket(**campos)
        s.add(t)
        s.flush()
        return t.id


def _contar():
    from db import session_scope
    from models import Ticket

    with session_scope() as s:
        return s.query(Ticket).count()


def _fila_de(ado_id, proyecto):
    from db import session_scope
    from models import Ticket

    with session_scope() as s:
        f = (
            s.query(Ticket)
            .filter(Ticket.ado_id == ado_id, Ticket.stacky_project_name == proyecto)
            .first()
        )
        if f is None:
            return None
        return {
            "id": f.id, "ado_id": f.ado_id, "project": f.project,
            "stacky_project_name": f.stacky_project_name,
            "tracker_type": f.tracker_type, "external_id": f.external_id,
        }


def _ticket_del_id(ticket_id):
    from db import session_scope
    from models import Ticket

    with session_scope() as s:
        f = s.query(Ticket).get(ticket_id)
        return None if f is None else {
            "stacky_project_name": f.stacky_project_name, "ado_id": f.ado_id,
        }


# ------------------------------------------------------------------ casos ---
def test_1_el_webhook_machea_el_proyecto_NOMBRADO(cliente, activo, sin_agente):
    """EL BUG: dos proyectos GitLab con el issue #42; el webhook nombra el B."""
    _sembrar(ado_id=42, external_id=42, project="grupo/proy-a",
             stacky_project_name=_PROY_A, tracker_type="gitlab", title="A-42",
             ado_state="To Do")
    _sembrar(ado_id=42, external_id=42, project="grupo/proy-b",
             stacky_project_name=_PROY_B, tracker_type="gitlab", title="B-42",
             ado_state="To Do")

    resp = cliente.post("/api/ci/failure-webhook",
                        json={"ticket_ado_id": 42, "stacky_project": _PROY_B})

    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert len(sin_agente) == 1
    usado = _ticket_del_id(sin_agente[0]["ticket_id"])
    assert usado["stacky_project_name"] == _PROY_B, usado


def test_2_sin_nombrar_el_proyecto_usa_el_ACTIVO(cliente, activo, sin_agente):
    _sembrar(ado_id=42, external_id=42, project="grupo/proy-a",
             stacky_project_name=_PROY_A, tracker_type="gitlab", title="A-42",
             ado_state="To Do")
    _sembrar(ado_id=42, external_id=42, project="grupo/proy-b",
             stacky_project_name=_PROY_B, tracker_type="gitlab", title="B-42",
             ado_state="To Do")
    activo["nombre"] = _PROY_B

    cliente.post("/api/ci/failure-webhook", json={"ticket_ado_id": 42})

    usado = _ticket_del_id(sin_agente[0]["ticket_id"])
    assert usado["stacky_project_name"] == _PROY_B, usado


def test_3_el_autocreado_pone_stacky_project_name(cliente, activo, sin_agente):
    cliente.post("/api/ci/failure-webhook",
                 json={"ticket_ado_id": 42, "stacky_project": _PROY_B})
    fila = _fila_de(42, _PROY_B)
    assert fila is not None and fila["stacky_project_name"] == _PROY_B


def test_4_el_autocreado_pone_el_tracker_type_del_contexto(cliente, activo, sin_agente):
    """Sin esto la fila cae en el default "azure_devops" de models.py:49: un ticket
    ADO sintético dentro de un proyecto GitLab, que el 286 tiene que adivinar."""
    cliente.post("/api/ci/failure-webhook",
                 json={"ticket_ado_id": 42, "stacky_project": _PROY_B})
    assert _fila_de(42, _PROY_B)["tracker_type"] == "gitlab"


def test_5_el_autocreado_pone_external_id(cliente, activo, sin_agente):
    """Tercera pata del índice único: sin ella el upsert del sync crea un DUPLICADO."""
    cliente.post("/api/ci/failure-webhook",
                 json={"ticket_ado_id": 42, "stacky_project": _PROY_B})
    assert _fila_de(42, _PROY_B)["external_id"] == 42


def test_6_el_autocreado_no_inventa_rspacifico(cliente, activo, sin_agente):
    cliente.post("/api/ci/failure-webhook",
                 json={"ticket_ado_id": 42, "stacky_project": _PROY_B})
    assert _fila_de(42, _PROY_B)["project"] == "grupo/proy-b"


def test_7_sin_proyecto_resoluble_da_409_y_NO_crea_nada(cliente, activo, sin_agente):
    resp = cliente.post("/api/ci/failure-webhook",
                        json={"ticket_ado_id": 42, "stacky_project": "NoExiste"})
    assert resp.status_code == 409, resp.get_data(as_text=True)
    assert _contar() == 0, "creó un ticket fantasma"


def test_8_autocreado_OFF_da_404_y_no_crea(cliente, activo, sin_agente, monkeypatch):
    import config as _config

    monkeypatch.setattr(
        _config.config, "STACKY_WEBHOOK_TICKET_AUTOCREATE_ENABLED", False, raising=False
    )
    resp = cliente.post("/api/ci/failure-webhook",
                        json={"ticket_ado_id": 42, "stacky_project": _PROY_B})
    assert resp.status_code == 404, resp.get_data(as_text=True)
    assert _contar() == 0


def test_9_pr_webhook_con_ticket_de_OTRO_proyecto_da_404_y_NO_lanza_el_agente(
    cliente, activo, sin_agente
):
    """El caso que mide la CONSECUENCIA REAL: que el DebugAgent no corra sobre el
    ticket equivocado. Assert de PRESENCIA del valor correcto (== 0)."""
    _sembrar(ado_id=42, external_id=42, project="grupo/proy-a",
             stacky_project_name=_PROY_A, tracker_type="gitlab", title="A-42",
             ado_state="To Do")

    resp = cliente.post("/api/pr/review-webhook",
                        json={"ticket_ado_id": 42, "stacky_project": _PROY_B,
                              "pr_id": 7, "diff": "x"})

    assert resp.status_code == 404, resp.get_data(as_text=True)
    assert len(sin_agente) == 0, "el DebugAgent corrió sobre el ticket de OTRO proyecto"


@pytest.mark.parametrize("ruta", ["/api/ci/failure-webhook", "/api/pr/review-webhook"])
def test_10_ticket_ado_id_no_numerico_da_400(cliente, activo, sin_agente, ruta):
    resp = cliente.post(ruta, json={"ticket_ado_id": "no-soy-un-numero"})
    assert resp.status_code == 400, resp.get_data(as_text=True)


def test_11_NO_REGRESION_ADO_fila_historica_con_stacky_project_name_NULL(
    cliente, activo, sin_agente
):
    """Red de seguridad de los datos históricos: las filas viejas tienen
    `stacky_project_name` NULL y sólo `project` (el tracker_project). Sin el `or_`
    tolerante de api/tickets.py:362-371, F9 rompería TODOS los webhooks ADO que ya
    funcionan en el servidor del operador."""
    _sembrar(ado_id=99, project="TrackerADO", title="ADO-99", ado_state="To Do")

    resp = cliente.post("/api/ci/failure-webhook",
                        json={"ticket_ado_id": 99, "project": "TrackerADO"})

    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert len(sin_agente) == 1
    assert _ticket_del_id(sin_agente[0]["ticket_id"])["ado_id"] == 99
    assert _contar() == 1, "creó un duplicado en vez de machear la fila histórica"
