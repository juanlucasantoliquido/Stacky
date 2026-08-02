"""Plan 283 F7 - La API de reuniones.

Cabecera OBLIGATORIA (molde `tests/test_pipeline_copilot_api.py`): DATABASE_URL
en memoria ANTES de importar la app. Sin esto, `create_app()` fuera de pytest
escribe en la base VIVA del operador (R8).
"""
from __future__ import annotations

import ast
import json
import os
import pathlib

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import pytest  # noqa: E402

_MODULO = pathlib.Path(__file__).resolve().parents[1] / "api" / "meetings.py"

VTT = (
    "WEBVTT\n\n"
    "1\n00:00:01.000 --> 00:00:04.000\n<v Juan Perez>Arrancamos con el estado.</v>\n\n"
    "2\n00:00:05.000 --> 00:00:09.000\n<v Ana Gomez>Yo reviso el informe el viernes.</v>\n"
)

RESPUESTA_MODELO = json.dumps({
    "resumen": "Se reviso el estado del proyecto.",
    "decisiones": [],
    "pendientes": [{"titulo": "Revisar el informe", "responsable": "Ana",
                    "fecha_compromiso": "2026-08-07",
                    "cita": "Yo reviso el informe el viernes."}],
    "riesgos": [],
}, ensure_ascii=False)


class _RespuestaFalsa:
    def __init__(self, text: str):
        self.text = text
        self.format = "markdown"
        self.metadata = {}


@pytest.fixture
def app():
    from app import create_app

    application = create_app()
    application.config["TESTING"] = True
    return application


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture(autouse=True)
def _base_limpia():
    import db

    db.init_db()
    with db.session_scope() as s:
        from services.meetings_store import Meeting, MeetingActionItem

        s.query(MeetingActionItem).delete(synchronize_session=False)
        s.query(Meeting).delete(synchronize_session=False)
    yield


@pytest.fixture
def reuniones_on(monkeypatch):
    import config as cfg

    monkeypatch.setattr(cfg.config, "STACKY_MEETINGS_ENABLED", True, raising=False)
    monkeypatch.setattr(cfg.config, "STACKY_MEETINGS_GRAPH_ENABLED", True, raising=False)


def _crear(client, subject="Semanal"):
    resp = client.post("/api/meetings?project=P283", json={"subject": subject})
    assert resp.status_code == 201, resp.get_data(as_text=True)
    return resp.get_json()["id"]


def test_1_health_responde_200_incluso_con_la_flag_apagada(client, monkeypatch):
    """Si /health respondiera 404 con la flag apagada, el gate de navegacion
    quedaria en `unknown` para siempre y el enlace directo moriria."""
    import config as cfg

    monkeypatch.setattr(cfg.config, "STACKY_MEETINGS_ENABLED", False, raising=False)
    resp = client.get("/api/meetings/health")
    assert resp.status_code == 200
    cuerpo = resp.get_json()
    assert cuerpo["ok"] is True
    assert cuerpo["flag_enabled"] is False

    # GUARD POSITIVO: con la flag encendida dice lo contrario.
    monkeypatch.setattr(cfg.config, "STACKY_MEETINGS_ENABLED", True, raising=False)
    assert client.get("/api/meetings/health").get_json()["flag_enabled"] is True


def test_2_con_la_flag_apagada_el_listado_da_404(client, monkeypatch):
    import config as cfg

    monkeypatch.setattr(cfg.config, "STACKY_MEETINGS_ENABLED", False, raising=False)
    resp = client.get("/api/meetings?project=P283")
    assert resp.status_code == 404
    assert resp.get_json()["error"] == "feature_disabled"
    # 404 = capacidad apagada, NUNCA "sin permiso": Stacky es mono-operador.


def test_3_el_alta_manual_devuelve_201_con_id(client, reuniones_on):
    mid = _crear(client, "Semanal de proyecto")
    assert isinstance(mid, int) and mid > 0

    listado = client.get("/api/meetings?project=P283").get_json()
    assert listado["ok"] is True
    assert [m["subject"] for m in listado["meetings"]] == ["Semanal de proyecto"]
    assert listado["meetings"][0]["minutes_state"] == "pending"


def test_4_el_alta_sin_titulo_da_400(client, reuniones_on):
    resp = client.post("/api/meetings?project=P283", json={})
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "subject_required"

    resp2 = client.post("/api/meetings?project=P283", json={"subject": "   "})
    assert resp2.status_code == 400


def test_5_post_de_transcripcion_guarda_y_destila(client, reuniones_on, monkeypatch):
    import copilot_bridge

    monkeypatch.setattr(
        copilot_bridge, "invoke", lambda **kw: _RespuestaFalsa(RESPUESTA_MODELO)
    )
    mid = _crear(client)

    resp = client.post(f"/api/meetings/{mid}/transcript?project=P283",
                       json={"content": VTT, "format": "vtt"})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    cuerpo = resp.get_json()
    assert cuerpo["ok"] is True
    assert cuerpo["estado"] == "done"
    assert cuerpo["meeting"]["minutes_state"] == "done"
    # Los pendientes quedaron PERSISTIDOS, no solo en la respuesta.
    detalle = client.get(f"/api/meetings/{mid}?project=P283").get_json()["meeting"]
    assert len(detalle["action_items"]) == 1
    assert detalle["action_items"][0]["titulo"] == "Revisar el informe"
    assert detalle["action_items"][0]["atribucion"] == "confirmada"
    assert detalle["action_items"][0]["cita"]


def test_6_calendar_con_graph_apagado_da_200_y_nunca_500(client, reuniones_on, monkeypatch):
    import config as cfg

    monkeypatch.setattr(cfg.config, "STACKY_MEETINGS_GRAPH_ENABLED", False, raising=False)
    resp = client.get("/api/meetings/calendar?project=P283")
    assert resp.status_code == 200, "la pantalla del calendario NUNCA puede recibir un 500"
    cuerpo = resp.get_json()
    assert cuerpo["estado"] == "apagado"
    assert cuerpo["reuniones"] == []
    assert cuerpo["detalle"]

    # GUARD POSITIVO: con Graph encendido pero sin credenciales, degrada distinto.
    monkeypatch.setattr(cfg.config, "STACKY_MEETINGS_GRAPH_ENABLED", True, raising=False)
    monkeypatch.setattr(cfg.config, "STACKY_MEETINGS_GRAPH_CLIENT_ID", "", raising=False)
    otra = client.get("/api/meetings/calendar?project=P283")
    assert otra.status_code == 200
    assert otra.get_json()["estado"] == "sin_credenciales"


def test_7_device_login_no_devuelve_el_codigo_de_dispositivo(client, reuniones_on, monkeypatch):
    from services import meetings_source

    class _ClienteFalso:
        def start_device_login(self):
            return {"user_code": "ABCD-EFGH",
                    "verification_uri": "https://microsoft.com/devicelogin",
                    "device_code": "SECRETO-QUE-NO-DEBE-SALIR",
                    "expires_in": 900, "interval": 5}

    monkeypatch.setattr(meetings_source, "crear_cliente", lambda *a, **k: _ClienteFalso())
    resp = client.post("/api/meetings/graph/device-login?project=P283", json={})
    assert resp.status_code == 200
    crudo = resp.get_data(as_text=True)

    # GUARD POSITIVO, PRIMERO: el cuerpo SI trae lo que el operador necesita.
    assert "ABCD-EFGH" in crudo
    # Y NO trae el material de autenticacion en transito.
    assert "SECRETO-QUE-NO-DEBE-SALIR" not in crudo
    assert "device_code" not in resp.get_json()


def test_8_retry_sin_transcripcion_da_409(client, reuniones_on):
    mid = _crear(client)
    resp = client.post(f"/api/meetings/{mid}/minutes/retry?project=P283", json={})
    assert resp.status_code == 409
    assert resp.get_json()["error"] == "no_transcript"


def test_9_un_id_inexistente_da_404(client, reuniones_on):
    assert client.get("/api/meetings/999999?project=P283").status_code == 404
    assert client.post("/api/meetings/999999/transcript?project=P283",
                       json={"content": VTT}).status_code == 404
    assert client.post("/api/meetings/999999/minutes/retry?project=P283",
                       json={}).status_code == 404


def test_10_d6_la_api_no_toca_tickets_ni_publica(client):
    """`api/tickets.py` tiene 8.000+ lineas y cambios sin commitear del
    operador: editarlo o acoplarse a el crea conflicto con trabajo real. Y la
    escritura al tracker es de la otra fase, con su propia llave.
    Guard positivo primero, contra un fuente que SI hace las dos cosas."""
    def _ofensas(fuente: str) -> list[str]:
        encontradas: list[str] = []
        arbol = ast.parse(fuente)
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.ImportFrom) and "tickets" in (nodo.module or ""):
                encontradas.append(f"from {nodo.module}")
            if isinstance(nodo, ast.Import):
                for alias in nodo.names:
                    if "tickets" in alias.name:
                        encontradas.append(f"import {alias.name}")
            if isinstance(nodo, ast.Call):
                nombre = getattr(nodo.func, "attr", None) or getattr(nodo.func, "id", None)
                if nombre == "create_item":
                    encontradas.append("create_item()")
        return encontradas

    # GUARD POSITIVO, PRIMERO.
    sucio = "from api.tickets import x\nprovider.create_item(item)\n"
    assert set(_ofensas(sucio)) == {"from api.tickets", "create_item()"}

    assert _ofensas(_MODULO.read_text(encoding="utf-8")) == []
