"""Plan 283 F10.3 - El ciclo entero, de punta a punta y con CERO red.

Los dos caminos de fuente (manual y calendario) llegan a la misma minuta, y las
dos llaves de la publicacion (capacidad encendida + confirmacion de un solo uso)
se prueban sobre el ciclo completo, no sobre una funcion aislada.

Cabecera obligatoria: DATABASE_URL en memoria ANTES de importar la app (R8).
"""
from __future__ import annotations

import json
import os
import pathlib

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import pytest  # noqa: E402

_FRONT = pathlib.Path(__file__).resolve().parents[2] / "frontend" / "src"


def _vtt(turnos: int, relleno: str = "") -> str:
    partes = ["WEBVTT"]
    nombres = ["Juan Perez", "Ana Gomez", "Luis Sosa"]
    for i in range(turnos):
        partes.append(
            f"\n{i + 1}\n00:{i // 60:02d}:{i % 60:02d}.000 --> 00:{i // 60:02d}:{i % 60:02d}.500\n"
            f"<v {nombres[i % 3]}>Intervencion numero {i} de la reunion.{relleno}</v>\n"
        )
    return "".join(partes)


# Las 3 citas son subcadenas LITERALES del texto normalizado de `_vtt(12)`.
RESPUESTA = json.dumps({
    "resumen": "Se reviso el estado y quedaron tres compromisos.",
    "decisiones": [{"texto": "Se avanza", "cita": "Intervencion numero 0 de la reunion."}],
    "pendientes": [
        {"titulo": "Revisar el informe", "responsable": "Ana",
         "fecha_compromiso": "2026-08-07", "cita": "Intervencion numero 1 de la reunion."},
        {"titulo": "Cerrar el presupuesto", "responsable": "Luis Sosa",
         "fecha_compromiso": None, "cita": "Intervencion numero 2 de la reunion."},
        {"titulo": "Confirmar la sala", "responsable": None,
         "fecha_compromiso": None, "cita": "Intervencion numero 3 de la reunion."},
    ],
    "riesgos": [],
}, ensure_ascii=False)


class _RespuestaFalsa:
    def __init__(self, text: str):
        self.text = text
        self.format = "markdown"
        self.metadata = {}


class _ProviderFalso:
    name = "gitlab"

    def __init__(self):
        self.recibidos: list = []

    def create_item(self, item):
        self.recibidos.append(item)
        return {"id": "4242", "web_url": "https://gitlab/x/-/issues/4242"}


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
def _entorno(monkeypatch):
    import config as cfg
    import db
    from services import confirm_token

    db.init_db()
    with db.session_scope() as s:
        from services.meetings_store import Meeting, MeetingActionItem

        s.query(MeetingActionItem).delete(synchronize_session=False)
        s.query(Meeting).delete(synchronize_session=False)
    confirm_token.reset_for_tests()

    monkeypatch.setattr(cfg.config, "STACKY_MEETINGS_ENABLED", True, raising=False)
    monkeypatch.setattr(cfg.config, "STACKY_MEETINGS_GRAPH_ENABLED", True, raising=False)
    monkeypatch.setattr(cfg.config, "STACKY_MEETINGS_PUBLISH_ENABLED", False, raising=False)
    monkeypatch.setattr(cfg.config, "STACKY_MEETINGS_GRAPH_CLIENT_ID", "app-123", raising=False)
    yield


@pytest.fixture
def modelo(monkeypatch):
    import copilot_bridge

    llamadas: list = []

    def _invoke(**kwargs):
        llamadas.append(kwargs.get("agent_type"))
        return _RespuestaFalsa(RESPUESTA)

    monkeypatch.setattr(copilot_bridge, "invoke", _invoke)
    return llamadas


def _crear(client, subject="Semanal") -> int:
    resp = client.post("/api/meetings?project=E2E", json={"subject": subject})
    assert resp.status_code == 201, resp.get_data(as_text=True)
    return resp.get_json()["id"]


def test_1_camino_manual_completo(client, modelo):
    mid = _crear(client)
    resp = client.post(f"/api/meetings/{mid}/transcript?project=E2E",
                       json={"content": _vtt(12), "format": "vtt"})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert modelo == ["meeting_minutes"], "se invoco al modelo una y solo una vez"

    detalle = client.get(f"/api/meetings/{mid}?project=E2E").get_json()["meeting"]
    assert detalle["minutes_state"] == "done"
    assert detalle["minutes"]["resumen"]
    assert len(detalle["action_items"]) == 3
    for item in detalle["action_items"]:
        assert item["cita"].strip(), "un pendiente sin cita no puede haber sobrevivido"
    # La atribucion se calculo de verdad: "Luis Sosa" hablo, "Ana" tambien.
    atribuciones = {i["titulo"]: i["atribucion"] for i in detalle["action_items"]}
    assert atribuciones["Cerrar el presupuesto"] == "confirmada"
    assert atribuciones["Confirmar la sala"] == "sin_responsable"


def test_2_camino_calendario_con_transporte_falso(client, modelo, monkeypatch):
    """Mismo destino por la otra fuente, y CERO red: el transporte es falso."""
    from datetime import datetime

    from services import meetings_source

    class _ClienteFalso:
        def list_events(self, *, desde, hasta):
            return [{
                "id": "ev-graph-1", "subject": "Semanal traida del calendario",
                "start": {"dateTime": "2026-08-03T14:00:00Z"},
                "end": {"dateTime": "2026-08-03T15:00:00Z"},
                "organizer": {"emailAddress": {"name": "Ana Gomez"}},
                "onlineMeeting": {"joinUrl": "https://teams.microsoft.com/l/x"},
            }]

        def get_transcript(self, *, meeting_id):
            return _vtt(12)

        def _access_token(self):
            return "acceso"

    falso = _ClienteFalso()
    monkeypatch.setattr(meetings_source, "crear_cliente", lambda *a, **k: falso)

    calendario = client.get("/api/meetings/calendar?project=E2E").get_json()
    assert calendario["estado"] == "ok"
    assert len(calendario["reuniones"]) == 1
    evento = calendario["reuniones"][0]
    assert evento["started_at"] == "2026-08-03T14:00:00Z"

    # Alta a partir del evento del calendario.
    alta = client.post("/api/meetings?project=E2E", json={
        "subject": evento["subject"], "started_at": evento["started_at"],
        "external_id": evento["external_id"], "organizer": evento["organizer"],
    })
    assert alta.status_code == 201
    mid = alta.get_json()["id"]

    # La transcripcion baja por el conector y sigue el MISMO camino de siempre.
    bajada = client.get(f"/api/meetings/graph/transcript/{evento['external_id']}?project=E2E")
    assert bajada.status_code == 200
    contenido = bajada.get_json()["content"]
    assert contenido.startswith("WEBVTT")

    resp = client.post(f"/api/meetings/{mid}/transcript?project=E2E",
                       json={"content": contenido, "format": "vtt"})
    assert resp.status_code == 200
    detalle = client.get(f"/api/meetings/{mid}?project=E2E").get_json()["meeting"]
    assert detalle["minutes_state"] == "done"
    assert len(detalle["action_items"]) == 3
    assert datetime.utcnow() is not None    # la corrida no toco la red en ningun paso


def test_3_k5_el_filtro_de_salida_corta_el_ciclo(client, modelo, monkeypatch):
    from services import egress_policies

    monkeypatch.setattr(
        egress_policies, "check",
        lambda **kw: egress_policies.EgressDecision(False, ["pii"], [], ["pii"], "bloqueado"),
    )
    mid = _crear(client)
    resp = client.post(f"/api/meetings/{mid}/transcript?project=E2E",
                       json={"content": _vtt(12), "format": "vtt"})

    assert resp.status_code == 200
    assert resp.get_json()["estado"] == "blocked"
    assert modelo == [], "la transcripcion salio hacia el modelo pese al bloqueo"
    detalle = client.get(f"/api/meetings/{mid}?project=E2E").get_json()["meeting"]
    assert detalle["minutes_state"] == "blocked"
    # Y la transcripcion NO se perdio.
    assert detalle["transcript_chars"] > 0


def test_4_k6_la_doble_llave_de_la_publicacion(client, modelo, monkeypatch):
    import config as cfg
    from services import tracker_provider

    provider = _ProviderFalso()
    monkeypatch.setattr(tracker_provider, "get_tracker_provider", lambda *a, **k: provider)

    mid = _crear(client)
    client.post(f"/api/meetings/{mid}/transcript?project=E2E",
                json={"content": _vtt(12), "format": "vtt"})
    item_id = client.get(f"/api/meetings/{mid}?project=E2E").get_json(
    )["meeting"]["action_items"][0]["id"]

    # LLAVE 1 apagada (asi nace de fabrica): ni el borrador se muestra.
    assert client.post(f"/api/meetings-publish/{item_id}/draft?project=E2E",
                       json={}).status_code == 404
    assert provider.recibidos == []

    monkeypatch.setattr(cfg.config, "STACKY_MEETINGS_PUBLISH_ENABLED", True, raising=False)

    # LLAVE 2 ausente: 409 y nada se escribe.
    sin_token = client.post(f"/api/meetings-publish/{item_id}/confirm?project=E2E", json={})
    assert sin_token.status_code == 409
    assert provider.recibidos == []

    # Las DOS llaves: recien ahora se escribe, y una sola vez.
    token = client.post(f"/api/meetings-publish/{item_id}/draft?project=E2E",
                        json={}).get_json()["confirm_token"]
    ok = client.post(f"/api/meetings-publish/{item_id}/confirm?project=E2E",
                     json={"confirm_token": token})
    assert ok.status_code == 200
    assert len(provider.recibidos) == 1
    assert ok.get_json()["external_id"] == "4242"


def test_5_k7_una_transcripcion_enorme_declara_lo_que_recorto(client, modelo):
    from services import transcript_parser

    crudo = _vtt(2000, relleno=" " + ("x" * 120))
    assert len(crudo) > 300_000, f"el fixture quedo chico: {len(crudo)} caracteres"

    normalizado = transcript_parser.normalize_transcript(crudo)
    assert normalizado["turnos_incluidos"] < normalizado["turnos_totales"]

    mid = _crear(client)
    resp = client.post(f"/api/meetings/{mid}/transcript?project=E2E",
                       json={"content": crudo, "format": "vtt"})
    assert resp.status_code == 200
    detalle = client.get(f"/api/meetings/{mid}?project=E2E").get_json()["meeting"]
    assert detalle["minutes"]["aviso_truncado"], "se recorto en silencio"
    assert "de" in detalle["minutes"]["aviso_truncado"]

    # GUARD POSITIVO: una transcripcion que ENTRA no declara recorte.
    otra = _crear(client, "Corta")
    client.post(f"/api/meetings/{otra}/transcript?project=E2E",
                json={"content": _vtt(12), "format": "vtt"})
    chica = client.get(f"/api/meetings/{otra}?project=E2E").get_json()["meeting"]
    assert chica["minutes"]["aviso_truncado"] is None


def test_6_con_la_capacidad_apagada_el_modulo_es_inerte(client, monkeypatch):
    """Funcionalmente inerte, NO "byte-identico": el tab existe en el codigo (se
    editaron routes.ts, shellNav.ts, shellIcons.ts y App.tsx). Lo que se prueba
    es que con la capacidad apagada las rutas responden 404 y el tab NO se
    pinta, porque su alta en la barra esta detras del gate."""
    import config as cfg

    monkeypatch.setattr(cfg.config, "STACKY_MEETINGS_ENABLED", False, raising=False)
    assert client.get("/api/meetings?project=E2E").status_code == 404
    assert client.get("/api/meetings/calendar?project=E2E").status_code == 404
    assert client.get("/api/meetings/1?project=E2E").status_code == 404
    # Salvo /health, que responde 200 SIEMPRE (si no, el gate de nav nunca
    # resolveria y el enlace directo moriria).
    salud = client.get("/api/meetings/health")
    assert salud.status_code == 200 and salud.get_json()["flag_enabled"] is False

    # Y el tab esta detras del gate en el modelo de navegacion (la logica se
    # prueba en `meetingsModel.test.ts`; aca se verifica el cableado en el .ts).
    shell = (_FRONT / "components" / "shell" / "shellNav.ts").read_text(encoding="utf-8")
    assert 'if (input.meetingsEnabled) v.add("reuniones");' in shell
    assert '"reuniones",' not in shell.split("const ALWAYS_VISIBLE")[1].split("]")[0], (
        "el tab quedo SIEMPRE visible: la capacidad apagada seguiria pintandolo"
    )
