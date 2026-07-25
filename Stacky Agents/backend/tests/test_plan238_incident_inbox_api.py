"""tests/test_plan238_incident_inbox_api.py -- Plan 238 F2: /api/incident-inbox/*.

La DB es la REAL: toda siembra se limpia con try/finally sobre el rango de
ado_id reservado por este plan (9200..9299).
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from db import session_scope  # noqa: E402
from models import Ticket  # noqa: E402

_ADO_MIN, _ADO_MAX = 9200, 9299


@pytest.fixture
def client():
    from app import create_app

    app = create_app()
    app.config.update(TESTING=True)
    with app.test_client() as c:
        yield c


def _active_tracker_project() -> str:
    """Proyecto del contexto activo.

    `_ticket_project_filter` (api/tickets.py) filtra por
    `stacky_project_name IS NULL AND project == ctx.tracker_project`, asi que la
    siembra tiene que usar ESE valor o las filas quedan fuera del alcance de la
    consulta (y el test daria un falso rojo por siembra invisible).
    """
    from services.project_context import resolve_project_context
    ctx = resolve_project_context()
    return getattr(ctx, "tracker_project", None) or "TEST" if ctx else "TEST"


def _seed(rows: list[dict]) -> None:
    proyecto = _active_tracker_project()
    with session_scope() as s:
        for r in rows:
            s.add(Ticket(project=proyecto, stacky_project_name=None, **r))


def _cleanup() -> None:
    with session_scope() as s:
        s.query(Ticket).filter(
            Ticket.ado_id >= _ADO_MIN, Ticket.ado_id <= _ADO_MAX
        ).delete(synchronize_session=False)


def _items(data: dict) -> list[dict]:
    """Solo los items sembrados por este archivo (la DB real tiene otros)."""
    return [i for i in data["items"] if _ADO_MIN <= (i.get("ado_id") or 0) <= _ADO_MAX]


def test_status_200_con_flag_on(client):
    r = client.get("/api/incident-inbox/status")
    assert r.status_code == 200
    data = r.get_json()
    assert data["ok"] is True
    assert data["enabled"] is True
    assert data["incident_types"] == ["issue", "bug"]
    assert data["closed_states_source"] == "default"


def test_status_200_con_flag_off(client):
    with patch("api.incident_inbox._enabled", return_value=False):
        r = client.get("/api/incident-inbox/status")
    assert r.status_code == 200
    assert r.get_json()["enabled"] is False


def test_items_404_con_flag_off(client):
    with patch("api.incident_inbox._enabled", return_value=False):
        r = client.get("/api/incident-inbox/items")
    assert r.status_code == 404
    assert r.get_json()["error"] == "feature_disabled"


def test_items_devuelve_solo_incidencias(client):
    try:
        _seed([
            {"ado_id": 9201, "title": "Incidencia viva", "work_item_type": "Issue", "ado_state": "Active"},
            {"ado_id": 9202, "title": "Bug cerrado", "work_item_type": "Bug", "ado_state": "Done"},
            {"ado_id": 9203, "title": "Una tarea", "work_item_type": "Task", "ado_state": "Active"},
            {"ado_id": 9204, "title": "Una epica", "work_item_type": "Epic", "ado_state": "New"},
        ])
        data = client.get("/api/incident-inbox/items?scope=all").get_json()
        mios = _items(data)
        assert {i["ado_id"] for i in mios} == {9201, 9202}
        assert all(i["work_item_type"] not in {"Task", "Epic"} for i in data["items"])
    finally:
        _cleanup()


def test_scope_open_filtra_cerradas(client):
    try:
        _seed([
            {"ado_id": 9211, "title": "Abierta", "work_item_type": "Issue", "ado_state": "Active"},
            {"ado_id": 9212, "title": "Cerrada", "work_item_type": "Bug", "ado_state": "Done"},
        ])
        data = client.get("/api/incident-inbox/items?scope=open").get_json()
        ids = {i["ado_id"] for i in _items(data)}
        assert 9211 in ids
        assert 9212 not in ids
    finally:
        _cleanup()


def test_scope_invalido_cae_a_open(client):
    r = client.get("/api/incident-inbox/items?scope=basura")
    assert r.status_code == 200
    assert r.get_json()["scope"] == "open"


def test_counts_cuenta_todas_no_solo_el_scope(client):
    try:
        _seed([
            {"ado_id": 9221, "title": "Abierta", "work_item_type": "Issue", "ado_state": "Active"},
            {"ado_id": 9222, "title": "Cerrada", "work_item_type": "Bug", "ado_state": "Done"},
        ])
        data = client.get("/api/incident-inbox/items?scope=open").get_json()
        counts = data["counts"]
        assert counts["closed"] >= 1
        assert counts["total"] == counts["open"] + counts["closed"]
    finally:
        _cleanup()


def test_item_conserva_las_keys_del_ticket(client):
    try:
        _seed([{"ado_id": 9231, "title": "Con keys", "work_item_type": "Issue", "ado_state": "Active"}])
        data = client.get("/api/incident-inbox/items?scope=all").get_json()
        mios = _items(data)
        assert mios, "la incidencia sembrada tiene que aparecer"
        item = mios[0]
        for k in ("id", "ado_id", "title", "work_item_type", "ado_state", "stacky_status", "is_open"):
            assert k in item, f"falta la key {k!r}"
    finally:
        _cleanup()


def test_abiertas_primero(client):
    try:
        _seed([
            {"ado_id": 9241, "title": "Cerrada", "work_item_type": "Bug", "ado_state": "Done"},
            {"ado_id": 9242, "title": "Abierta", "work_item_type": "Issue", "ado_state": "Active"},
        ])
        data = client.get("/api/incident-inbox/items?scope=all").get_json()
        assert data["items"], "tiene que haber al menos una incidencia"
        assert data["items"][0]["is_open"] is True
    finally:
        _cleanup()


def test_gitlab_sin_tipo_reporta_untyped_count(client):
    """[ADICION A2] Nunca una pantalla vacia mentirosa."""
    try:
        _seed([{
            "ado_id": 9251, "title": "Issue de GitLab", "work_item_type": None,
            "ado_state": "opened", "tracker_type": "gitlab",
        }])
        data = client.get("/api/incident-inbox/items?scope=all").get_json()
        assert 9251 not in {i["ado_id"] for i in data["items"]}
        assert data["untyped_count"] >= 1
    finally:
        _cleanup()


def test_respuesta_declara_provider(client):
    data = client.get("/api/incident-inbox/items").get_json()
    assert "provider" in data


def test_seam_de_filtro_de_proyecto_existe():
    """Ratchet del seam: si api/tickets.py renombra estos helpers, esto se pone rojo."""
    from api.tickets import _request_project_name, _ticket_project_filter  # noqa: F401
