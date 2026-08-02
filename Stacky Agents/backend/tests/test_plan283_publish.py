"""Plan 283 F8 - El unico camino que escribe afuera, con doble llave.

Cabecera obligatoria: DATABASE_URL en memoria ANTES de importar la app (R8).
"""
from __future__ import annotations

import ast
import os
import pathlib
from datetime import datetime

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import pytest  # noqa: E402

_MODULO = pathlib.Path(__file__).resolve().parents[1] / "api" / "meetings_publish.py"

# Marca unica sembrada en la transcripcion FUERA de la cita: si aparece en el
# work item, es que viajo texto que no tenia que viajar.
MARCA = "MARCA-UNICA-QUE-NO-DEBE-SALIR-7F3A"
TRANSCRIPCION = (
    "Juan Perez: arrancamos con el estado del proyecto.\n"
    f"Ana Gomez: {MARCA} y ademas yo reviso el informe el viernes.\n"
)
CITA = "yo reviso el informe el viernes"


class _ProviderFalso:
    name = "gitlab"

    def __init__(self, excepcion=None):
        self.recibidos: list = []
        self._excepcion = excepcion

    def create_item(self, item):
        self.recibidos.append(item)
        if self._excepcion is not None:
            raise self._excepcion
        return {"id": "1234", "web_url": "https://gitlab/x/-/issues/1234"}


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
    from services import confirm_token

    db.init_db()
    with db.session_scope() as s:
        from services.meetings_store import Meeting, MeetingActionItem

        s.query(MeetingActionItem).delete(synchronize_session=False)
        s.query(Meeting).delete(synchronize_session=False)
    confirm_token.reset_for_tests()
    yield


@pytest.fixture
def publicacion_on(monkeypatch):
    import config as cfg

    monkeypatch.setattr(cfg.config, "STACKY_MEETINGS_ENABLED", True, raising=False)
    monkeypatch.setattr(cfg.config, "STACKY_MEETINGS_PUBLISH_ENABLED", True, raising=False)


@pytest.fixture
def espia(monkeypatch):
    """UN SOLO espia por archivo: asi el caso que exige 0 llamadas no puede
    pasar por un espia roto — el caso que exige 1 usa el mismo."""
    from services import tracker_provider

    provider = _ProviderFalso()
    monkeypatch.setattr(tracker_provider, "get_tracker_provider", lambda *a, **k: provider)
    return provider


def _pendiente(atribucion="confirmada", responsable="Ana Gomez") -> int:
    from services import meetings_store as st

    mid = st.create_meeting(project="P283", subject="Semanal de proyecto")
    st.save_transcript(mid, content=TRANSCRIPCION, fmt="txt")
    st.replace_action_items(mid, [{
        "titulo": "Revisar el informe", "responsable": responsable,
        "fecha_compromiso": datetime(2026, 8, 7), "cita": CITA, "atribucion": atribucion,
    }])
    detalle = st.get_meeting_dict(mid, project="P283")
    return int(detalle["action_items"][0]["id"])


def test_1_draft_con_la_flag_apagada_da_404(client, espia, monkeypatch):
    """La flag gatea TAMBIEN el borrador: el borrador ya nombra el proyecto
    destino, asi que mostrarlo con la capacidad apagada seria ofrecer un
    callejon sin salida."""
    import config as cfg

    monkeypatch.setattr(cfg.config, "STACKY_MEETINGS_ENABLED", True, raising=False)
    monkeypatch.setattr(cfg.config, "STACKY_MEETINGS_PUBLISH_ENABLED", False, raising=False)
    item_id = _pendiente()

    resp = client.post(f"/api/meetings-publish/{item_id}/draft?project=P283", json={})
    assert resp.status_code == 404
    assert resp.get_json()["error"] == "feature_disabled"
    assert espia.recibidos == []


def test_2_draft_no_escribe_nada(client, publicacion_on, espia):
    item_id = _pendiente()
    resp = client.post(f"/api/meetings-publish/{item_id}/draft?project=P283", json={})

    assert resp.status_code == 200
    cuerpo = resp.get_json()
    assert cuerpo["confirm_token"]
    assert cuerpo["draft"]["title"] == "Revisar el informe"
    assert cuerpo["draft"]["item_type"] == "Task"
    assert len(espia.recibidos) == 0, "el borrador escribio en el tracker"


def test_3_confirm_con_token_valido_crea_el_work_item(client, publicacion_on, espia):
    item_id = _pendiente()
    token = client.post(
        f"/api/meetings-publish/{item_id}/draft?project=P283", json={}
    ).get_json()["confirm_token"]

    resp = client.post(f"/api/meetings-publish/{item_id}/confirm?project=P283",
                       json={"confirm_token": token})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert len(espia.recibidos) == 1
    assert resp.get_json()["external_id"] == "1234"

    from services import meetings_store as st

    assert st.get_action_item_dict(item_id)["estado"] == "publicado"


def test_4_k6_sin_confirmacion_no_se_escribe(client, publicacion_on, espia):
    """GUARD POSITIVO: el caso 3 usa el MISMO espia y SI llega a 1, asi que un
    espia roto no puede hacer pasar este assert de ausencia."""
    item_id = _pendiente()
    client.post(f"/api/meetings-publish/{item_id}/draft?project=P283", json={})

    resp = client.post(f"/api/meetings-publish/{item_id}/confirm?project=P283", json={})
    assert resp.status_code == 409
    assert resp.get_json()["error"] == "confirmacion_requerida"
    assert espia.recibidos == []

    # Y con un token inventado tampoco.
    otra = client.post(f"/api/meetings-publish/{item_id}/confirm?project=P283",
                       json={"confirm_token": "inventado"})
    assert otra.status_code == 409
    assert espia.recibidos == []


def test_5_token_vencido_da_409(client, publicacion_on, espia):
    from services import confirm_token

    item_id = _pendiente()
    token = client.post(
        f"/api/meetings-publish/{item_id}/draft?project=P283", json={}
    ).get_json()["confirm_token"]

    confirm_token.expire_token_for_tests(token)
    resp = client.post(f"/api/meetings-publish/{item_id}/confirm?project=P283",
                       json={"confirm_token": token})
    assert resp.status_code == 409
    assert espia.recibidos == []


def test_6_el_token_es_de_un_solo_uso(client, publicacion_on, espia):
    item_id = _pendiente()
    token = client.post(
        f"/api/meetings-publish/{item_id}/draft?project=P283", json={}
    ).get_json()["confirm_token"]

    primera = client.post(f"/api/meetings-publish/{item_id}/confirm?project=P283",
                          json={"confirm_token": token})
    assert primera.status_code == 200
    segunda = client.post(f"/api/meetings-publish/{item_id}/confirm?project=P283",
                          json={"confirm_token": token})
    assert segunda.status_code == 409
    assert len(espia.recibidos) == 1, "el reintento con el mismo token duplico el work item"


def test_7_si_el_tracker_falla_el_pendiente_no_queda_publicado(client, publicacion_on, monkeypatch):
    from services import meetings_store, tracker_provider
    from services.tracker_provider import TrackerApiError

    provider = _ProviderFalso(excepcion=TrackerApiError(500, "boom", kind="server"))
    monkeypatch.setattr(tracker_provider, "get_tracker_provider", lambda *a, **k: provider)

    item_id = _pendiente()
    token = client.post(
        f"/api/meetings-publish/{item_id}/draft?project=P283", json={}
    ).get_json()["confirm_token"]
    resp = client.post(f"/api/meetings-publish/{item_id}/confirm?project=P283",
                       json={"confirm_token": token})

    assert resp.status_code == 502
    assert len(provider.recibidos) == 1, "el guard: se intento de verdad"
    assert meetings_store.get_action_item_dict(item_id)["estado"] == "propuesto", (
        "quedo marcado publicado por un fallo: mentiria sobre un work item inexistente"
    )


def test_8_d6_gate_por_ast_sin_api_tickets():
    def _ofensas(fuente: str) -> list[str]:
        encontradas: list[str] = []
        for nodo in ast.walk(ast.parse(fuente)):
            if isinstance(nodo, ast.ImportFrom) and "tickets" in (nodo.module or ""):
                encontradas.append(f"from {nodo.module}")
            if isinstance(nodo, ast.Import):
                for alias in nodo.names:
                    if "tickets" in alias.name:
                        encontradas.append(f"import {alias.name}")
        return encontradas

    # GUARD POSITIVO, PRIMERO.
    assert _ofensas("from api.tickets import x\nimport api.tickets\n") == [
        "from api.tickets", "import api.tickets",
    ]
    assert _ofensas(_MODULO.read_text(encoding="utf-8")) == []


def test_9_viaja_la_cita_y_no_la_transcripcion(client, publicacion_on, espia):
    import html

    from services import meetings_store

    item_id = _pendiente()
    token = client.post(
        f"/api/meetings-publish/{item_id}/draft?project=P283", json={}
    ).get_json()["confirm_token"]
    client.post(f"/api/meetings-publish/{item_id}/confirm?project=P283",
                json={"confirm_token": token})

    assert len(espia.recibidos) == 1
    enviado = espia.recibidos[0]

    # GUARD POSITIVO, PRIMERO: la marca SI esta en la transcripcion guardada.
    # Sin esto, un description_html vacio haria pasar el assert de ausencia.
    guardada, _fmt = meetings_store.get_transcript(
        int(meetings_store.get_action_item_dict(item_id)["meeting_id"])
    )
    assert MARCA in guardada, "la marca no llego a la base: el guard no prueba nada"

    assert html.escape(CITA) in enviado.description_html
    assert MARCA not in enviado.description_html, "viajo texto de la reunion fuera de la cita"
    assert enviado.labels == ("reunion",)
    assert enviado.parent_id is None
    assert enviado.fields == {}


def test_10_k8_no_se_asigna_a_nadie_sin_atribucion_confirmada(client, publicacion_on, espia):
    """GUARD POSITIVO PRIMERO: el sub-caso `confirmada` corre ANTES, con el
    MISMO espia, asi que un `assignee` siempre-None no puede hacer pasar el
    segundo sub-caso."""
    confirmado = _pendiente(atribucion="confirmada", responsable="Ana Gomez")
    token = client.post(
        f"/api/meetings-publish/{confirmado}/draft?project=P283", json={}
    ).get_json()["confirm_token"]
    client.post(f"/api/meetings-publish/{confirmado}/confirm?project=P283",
                json={"confirm_token": token})
    assert espia.recibidos[0].assignee == "Ana Gomez"

    dudoso = _pendiente(atribucion="sin_hablante", responsable="Marcela")
    token2 = client.post(
        f"/api/meetings-publish/{dudoso}/draft?project=P283", json={}
    ).get_json()["confirm_token"]
    client.post(f"/api/meetings-publish/{dudoso}/confirm?project=P283",
                json={"confirm_token": token2})

    assert len(espia.recibidos) == 2
    enviado = espia.recibidos[1]
    assert enviado.assignee is None, "se asigno trabajo real por una atribucion no probada"
    # Y el work item DICE en castellano por que no se asigno.
    assert "no se pudo verificar" in enviado.description_html
    assert "Marcela" in enviado.description_html      # se propone, no se asigna
