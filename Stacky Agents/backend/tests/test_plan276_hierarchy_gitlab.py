"""tests/test_plan276_hierarchy_gitlab.py — Plan 276 F7.

`GET /api/tickets/hierarchy` NO necesitaba cambios: clasifica por `work_item_type`
y `parent_ado_id`, que es exactamente lo que F5 ahora puebla. Este archivo lo
DEMUESTRA en vez de afirmarlo, y es el gate de que la terna que escribe el sync cae
en la primera rama de `_ticket_project_filter` — si no cayera, el grafo seguiría
vacío con las filas en la base.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

CTX = SimpleNamespace(
    stacky_project_name="RIPLEY",
    tracker_project="ripley/agenda-web",
    tracker_type="gitlab",
)


@pytest.fixture(scope="module")
def _bd_temporal(tmp_path_factory):
    """UNA base para todo el archivo, a propósito.

    `db.py` construye el engine al IMPORTARSE y una sola vez por proceso, así que
    una BD por test es imposible: el engine se quedaría apuntando a la del primer
    test. El aislamiento que importa (P2-6) es respecto de la BD REAL del operador
    (181 MB), y eso se verifica abajo. Las tablas se limpian por test en `_sembrar`.
    """
    ruta = tmp_path_factory.mktemp("plan276h") / "p276h.db"
    import os

    os.environ["DATABASE_URL"] = f"sqlite:///{ruta.as_posix()}"
    os.environ["STACKY_SKIP_STARTUP_SYNC"] = "1"
    import db as db_mod

    url = str(db_mod.engine.url)
    assert "pytest" in url and url.endswith("p276h.db"), (
        f"la BD del test NO está aislada de la del operador: {url}"
    )
    return ruta


@pytest.fixture()
def client(_bd_temporal):
    from app import create_app

    app = create_app()
    app.config.update(TESTING=True)
    with app.test_client() as c:
        yield c


def _sembrar(filas):
    from db import session_scope
    from models import Ticket

    with session_scope() as session:
        session.query(Ticket).delete()
        for f in filas:
            session.add(Ticket(**f))


def _fila(ado_id, external_id, *, tipo="Issue", parent=None, tracker="gitlab",
          stacky="RIPLEY", proyecto="ripley/agenda-web"):
    return {
        "ado_id": ado_id, "external_id": external_id, "project": proyecto,
        "stacky_project_name": stacky, "tracker_type": tracker,
        "title": f"issue {ado_id}", "ado_state": "opened",
        "work_item_type": tipo, "parent_ado_id": parent,
    }


def _hierarchy(client, monkeypatch, project="RIPLEY"):
    import api.tickets as t

    monkeypatch.setattr(t, "resolve_project_context", lambda **kw: CTX)
    return client.get(f"/api/tickets/hierarchy?project={project}").get_json()


def test_epica_con_dos_hijas_y_una_suelta(client, monkeypatch):
    _sembrar([
        _fila(1, 1001, tipo="Epic"),
        _fila(2, 1002, parent=1),
        _fila(3, 1003, parent=1),
        _fila(4, 1004),
    ])
    body = _hierarchy(client, monkeypatch)
    assert len(body["epics"]) == 1, body
    assert len(body["epics"][0]["children"]) == 2, body["epics"][0]
    assert len(body["orphans"]) == 1, body["orphans"]


def test_el_grafo_no_esta_vacio_con_filas_de_gitlab(client, monkeypatch):
    """EL CRITERIO DEL PLAN: hoy devuelve {"epics":[],"orphans":[]} porque nadie
    escribía filas de GitLab. Este es el gate de que la terna del sync cae en la
    primera rama de _ticket_project_filter."""
    _sembrar([_fila(1, 1001), _fila(2, 1002)])
    body = _hierarchy(client, monkeypatch)
    assert len(body["epics"]) + len(body["orphans"]) > 0, f"el grafo sigue vacío: {body}"


def test_hija_cuyo_padre_no_esta_en_bd_cae_en_orphans(client, monkeypatch):
    _sembrar([_fila(2, 1002, parent=999)])
    body = _hierarchy(client, monkeypatch)
    assert body["epics"] == []
    assert len(body["orphans"]) == 1


def test_el_filtro_por_proyecto_no_mezcla_tickets_de_ado(client, monkeypatch):
    """Aislamiento: un proyecto Stacky distinto (con tracker ADO) no puede aparecer
    en el grafo de RIPLEY."""
    _sembrar([
        _fila(1, 1001),
        _fila(50, 5050, tracker="azure_devops", stacky="OTRO", proyecto="OtroProj"),
    ])
    body = _hierarchy(client, monkeypatch)
    todos = body["epics"] + body["orphans"]
    assert len(todos) == 1, f"se filtró un ticket de otro proyecto: {todos}"
    assert todos[0]["ado_id"] == 1


def test_work_item_type_en_cualquier_caja_cuenta_como_epica(client, monkeypatch):
    """El endpoint compara en minúsculas; F5 escribe 'Epic' capitalizado."""
    _sembrar([_fila(1, 1001, tipo="Epic"), _fila(2, 1002, tipo="epic")])
    body = _hierarchy(client, monkeypatch)
    assert len(body["epics"]) == 2, body
