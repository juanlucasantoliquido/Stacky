"""Plan 279 F5 — Tests de /api/pipeline-copilot/*.

10 casos. El endpoint SOLO mueve el estado de la sesion: no ejecuta ninguna
accion (caso 8 lo gatea por `ast`).

Cabecera obligatoria: DATABASE_URL en memoria ANTES de importar la app, para no
escribir en la base viva del operador (R8).
"""
from __future__ import annotations

import ast
import json
import os
import pathlib

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import pytest  # noqa: E402

_CONVERSATION_ADO_ID = -2

_MODULE_PATH = (
    pathlib.Path(__file__).resolve().parents[1] / "api" / "pipeline_copilot.py"
)


@pytest.fixture
def app():
    from app import create_app

    application = create_app()
    application.config["TESTING"] = True
    return application


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def copilot_on(monkeypatch):
    import config as cfg

    monkeypatch.setattr(cfg.config, "STACKY_PIPELINE_COPILOT_ENABLED", True,
                        raising=False)
    monkeypatch.setattr(cfg.config, "STACKY_PIPELINE_GENERATOR_ENABLED", True,
                        raising=False)


def _nueva_conversacion(description: str | None = None) -> int:
    """Crea un Ticket de conversacion DevOps y devuelve su id."""
    from db import session_scope
    from models import Ticket

    with session_scope() as session:
        ticket = Ticket(
            ado_id=_CONVERSATION_ADO_ID,
            project="ProyectoDePrueba",
            stacky_project_name="ProyectoDePrueba",
            title="[Stacky] DevOps Chat — plan 279",
            work_item_type="Task",
            ado_state="Active",
            description=description,
        )
        session.add(ticket)
        session.flush()
        ticket.external_id = -ticket.id
        session.flush()
        return ticket.id


def _description(conversation_id: int) -> str | None:
    from db import session_scope
    from models import Ticket

    with session_scope() as session:
        t = session.query(Ticket).filter_by(id=conversation_id).first()
        return t.description if t is not None else None


# --------------------------------------------------------------------------


def test_flag_off_da_404(client, monkeypatch):
    import config as cfg

    monkeypatch.setattr(cfg.config, "STACKY_PIPELINE_COPILOT_ENABLED", False,
                        raising=False)
    cid = _nueva_conversacion()
    assert client.get(f"/api/pipeline-copilot/session/{cid}").status_code == 404
    assert client.post(
        f"/api/pipeline-copilot/session/{cid}/advance", json={"to": "discovery"}
    ).status_code == 404
    assert client.get(
        f"/api/pipeline-copilot/session/{cid}/question").status_code == 404
    assert client.get(
        f"/api/pipeline-copilot/session/{cid}/undo-hint").status_code == 404


def test_get_session_de_conversacion_inexistente_da_404(client, copilot_on):
    assert client.get("/api/pipeline-copilot/session/99999999").status_code == 404


def test_get_session_nueva_devuelve_intake(client, copilot_on):
    cid = _nueva_conversacion()
    r = client.get(f"/api/pipeline-copilot/session/{cid}")
    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json()
    assert body["ok"] is True
    assert body["session"]["state"] == "intake"


def test_advance_legal_persiste_el_estado(client, copilot_on):
    cid = _nueva_conversacion()
    r = client.post(f"/api/pipeline-copilot/session/{cid}/advance",
                    json={"to": "discovery",
                          "fields": {"provider": "ado", "stack": "python"}})
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["session"]["state"] == "discovery"
    # Se RELEE con un GET posterior: si no persistio, esto lo caza.
    body = client.get(f"/api/pipeline-copilot/session/{cid}").get_json()
    assert body["session"]["state"] == "discovery"
    assert body["session"]["provider"] == "ado"
    assert body["session"]["stack"] == "python"


def test_advance_ilegal_da_409_y_no_muta(client, copilot_on):
    cid = _nueva_conversacion()
    r = client.post(f"/api/pipeline-copilot/session/{cid}/advance",
                    json={"to": "committed"})
    assert r.status_code == 409, r.get_data(as_text=True)
    body = r.get_json()
    assert body["ok"] is False
    assert body["error"] == "transicion_ilegal"
    assert body["detail"], "el 409 debe declarar el motivo"
    # Y la sesion sigue donde estaba.
    assert client.get(
        f"/api/pipeline-copilot/session/{cid}"
    ).get_json()["session"]["state"] == "intake"


def test_advance_preserva_server_alias_del_plan_108(client, copilot_on):
    """Guard anti-regresion de D4: la sesion se guarda EN el mismo JSON que ya
    usa el plan 108. Pisar la clave ajena romperia el anclaje remoto."""
    cid = _nueva_conversacion(
        json.dumps({"kind": "devops_chat", "server_alias": "srv-01"})
    )
    r = client.post(f"/api/pipeline-copilot/session/{cid}/advance",
                    json={"to": "discovery"})
    assert r.status_code == 200, r.get_data(as_text=True)
    meta = json.loads(_description(cid) or "{}")
    assert meta.get("server_alias") == "srv-01", meta
    assert meta.get("kind") == "devops_chat", meta
    assert meta.get("pipeline_session", {}).get("state") == "discovery", meta


def test_question_devuelve_la_primera_pregunta_abierta(client, copilot_on):
    cid = _nueva_conversacion()
    # Sin preguntas abiertas => "".
    assert client.get(
        f"/api/pipeline-copilot/session/{cid}/question").get_json()["question"] == ""
    client.post(f"/api/pipeline-copilot/session/{cid}/advance",
                json={"to": "discovery",
                      "fields": {"open_questions": ["que rama?", "que stack?"]}})
    r = client.get(f"/api/pipeline-copilot/session/{cid}/question")
    assert r.status_code == 200
    assert r.get_json()["question"] == "que rama?"


def test_el_endpoint_no_ejecuta_ninguna_accion():
    """D1: el endpoint mueve el estado y NADA MAS. Gate por `ast`, no por grep."""
    src = _MODULE_PATH.read_text(encoding="utf-8")
    arbol = ast.parse(src)

    importados: list[str] = []
    llamadas: list[str] = []
    for node in ast.walk(arbol):
        if isinstance(node, ast.ImportFrom) and node.module:
            importados.append(node.module)
        elif isinstance(node, ast.Import):
            importados.extend(a.name for a in node.names)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            llamadas.append(node.func.id)

    # Guard anti-falso-verde: el censo TIENE que ver los imports que si estan.
    assert any("pipeline_session" in m for m in importados), importados

    ofensores = [m for m in importados if "pipeline_generator" in m]
    assert ofensores == [], ofensores
    assert "commit_route" not in llamadas, llamadas


def test_con_generator_off_la_sesion_declara_que_falta(client, monkeypatch):
    """[C6] Degradacion honesta: se NOMBRA la flag que falta, no un 404 mudo."""
    import config as cfg

    monkeypatch.setattr(cfg.config, "STACKY_PIPELINE_COPILOT_ENABLED", True,
                        raising=False)
    cid = _nueva_conversacion()

    # PRIMERO el caso ON, para que el assert de lista vacia no pase por accidente
    # (si el endpoint nunca poblara la clave, el caso OFF pasaria igual).
    monkeypatch.setattr(cfg.config, "STACKY_PIPELINE_GENERATOR_ENABLED", True,
                        raising=False)
    on = client.get(f"/api/pipeline-copilot/session/{cid}").get_json()
    assert on["unavailable_actions"] == [], on
    assert on["unavailable_reason"] == "", on

    monkeypatch.setattr(cfg.config, "STACKY_PIPELINE_GENERATOR_ENABLED", False,
                        raising=False)
    off = client.get(f"/api/pipeline-copilot/session/{cid}").get_json()
    assert off["unavailable_actions"] == [
        "devops.pipeline_new.draft", "devops.pipeline_new.commit"
    ], off
    assert off["unavailable_reason"] == "STACKY_PIPELINE_GENERATOR_ENABLED", off


def test_undo_hint_route_devuelve_el_texto_en_confirm_y_vacio_en_intake(
    client, copilot_on
):
    """[ADICION ARQUITECTO] K7 por HTTP."""
    cid = _nueva_conversacion()
    # En intake todavia no hay nada que deshacer.
    assert client.get(
        f"/api/pipeline-copilot/session/{cid}/undo-hint"
    ).get_json()["undo_hint"] == ""

    for destino, campos in (
        ("discovery", {"provider": "ado", "branch": "feature/x", "project": "P"}),
        ("draft", {}), ("review", {}), ("confirm", {}),
    ):
        r = client.post(f"/api/pipeline-copilot/session/{cid}/advance",
                        json={"to": destino, "fields": campos})
        assert r.status_code == 200, (destino, r.get_data(as_text=True))

    texto = client.get(
        f"/api/pipeline-copilot/session/{cid}/undo-hint"
    ).get_json()["undo_hint"]
    assert "azure-pipelines.yml" in texto, texto
    assert "feature/x" in texto, texto


# ---------------------------------------------------------------------------
# Plan 288 — el destino de escritura lo decide el PROYECTO, no un default.
#
# El defecto que estos 3 casos matan: `draftProvider()` del frontend
# (services/devopsActionBindings.ts:63) devuelve 'ado' salvo que alguien haya
# puesto 'gitlab' en los params, asi que un proyecto GitLab terminaba creando
# `azure-pipelines.yml`. La sesion tiene que DECLARAR el proveedor que sale del
# config del proyecto (services/project_context.tracker_declarado_del_proyecto,
# Plan 286), y declararlo VACIO cuando no lo puede resolver — nunca 'ado'.
# ---------------------------------------------------------------------------


def _forzar_tracker(monkeypatch, valor):
    """Fuerza lo que declara el config del proyecto. Se parchea en el ORIGEN
    (services.project_context) porque api/pipeline_copilot.py lo importa local
    dentro de la funcion, que es el idioma interceptable de la casa."""
    import services.project_context as pc

    vistos: list = []

    def _fake(project_name):
        vistos.append(project_name)
        return valor

    monkeypatch.setattr(pc, "tracker_declarado_del_proyecto", _fake)
    return vistos


def test_el_payload_declara_el_provider_del_proyecto(client, copilot_on, monkeypatch):
    """El proyecto manda: azure_devops -> ado, gitlab -> gitlab.

    Los DOS casos viven en el mismo test a proposito: un `_payload` que
    devolviera la constante 'ado' pasaria la mitad del test, y uno que
    devolviera 'gitlab' pasaria la otra mitad. Juntos, ninguna constante pasa.
    """
    cid = _nueva_conversacion()

    vistos = _forzar_tracker(monkeypatch, "azure_devops")
    ado = client.get(f"/api/pipeline-copilot/session/{cid}").get_json()
    assert ado["provider"] == "ado", ado
    assert ado["provider_source"] == "project", ado
    assert ado["pipeline_file"] == "azure-pipelines.yml", ado
    # Y le pregunto al proyecto de ESTA conversacion, no a "el proyecto activo".
    assert vistos == ["ProyectoDePrueba"], vistos

    _forzar_tracker(monkeypatch, "gitlab")
    gl = client.get(f"/api/pipeline-copilot/session/{cid}").get_json()
    assert gl["provider"] == "gitlab", gl
    assert gl["provider_source"] == "project", gl
    assert gl["pipeline_file"] == ".gitlab-ci.yml", gl


def test_sin_tracker_resoluble_el_provider_queda_vacio_no_ado(
    client, copilot_on, monkeypatch
):
    """Degradacion HONESTA: si el proyecto no declara tracker, la sesion lo dice.

    Guard anti-falso-verde: primero se comprueba que el mismo endpoint SI sabe
    resolver un provider (si no, el `== ""` de abajo pasaria porque la clave
    nunca se puebla).
    """
    cid = _nueva_conversacion()

    _forzar_tracker(monkeypatch, "gitlab")
    poblado = client.get(f"/api/pipeline-copilot/session/{cid}").get_json()
    assert poblado["provider"] == "gitlab", poblado

    for sin_tracker in (None, "", "   ", "jira"):
        _forzar_tracker(monkeypatch, sin_tracker)
        r = client.get(f"/api/pipeline-copilot/session/{cid}").get_json()
        assert r["provider"] == "", (sin_tracker, r)
        assert r["provider_source"] == "unknown", (sin_tracker, r)
        assert r["pipeline_file"] == "", (sin_tracker, r)


def test_advance_devuelve_el_mismo_provider_que_get(client, copilot_on, monkeypatch):
    """Las dos rutas que devuelven la sesion comparten `_payload`: si una lo
    declara y la otra no, la UI ve el destino cambiar sola al avanzar."""
    cid = _nueva_conversacion()
    _forzar_tracker(monkeypatch, "gitlab")

    antes = client.get(f"/api/pipeline-copilot/session/{cid}").get_json()
    r = client.post(f"/api/pipeline-copilot/session/{cid}/advance",
                    json={"to": "discovery"})
    assert r.status_code == 200, r.get_data(as_text=True)
    despues = r.get_json()

    assert antes["provider"] == "gitlab", antes
    assert despues["provider"] == "gitlab", despues
    assert despues["pipeline_file"] == antes["pipeline_file"] == ".gitlab-ci.yml"


def test_la_conversacion_del_copiloto_se_puede_reencontrar(
    client, copilot_on, monkeypatch
):
    """Plan 288 — la seccion promete "la sesion se retoma sola" y hasta hoy no
    tenia con que: /devops/agent/conversations no distinguia un hilo del
    copiloto de uno de chat libre.

    Presencia Y ausencia en el MISMO caso: una conversacion sellada como sesion
    de pipeline marca True y una de chat libre marca False. Con la clave
    ausente (el defecto) el `is True` falla.
    """
    import config as cfg

    # monkeypatch y NO asignacion directa: `cfg.config` es un singleton de
    # proceso y una asignacion pelada contamina las suites que corren despues.
    monkeypatch.setattr(cfg.config, "STACKY_DEVOPS_AGENT_ENABLED", True,
                        raising=False)
    con_sesion = _nueva_conversacion(json.dumps({
        "kind": "devops_chat",
        "pipeline_session": {"state": "draft", "version": "1"},
    }))
    sin_sesion = _nueva_conversacion()

    r = client.get("/api/devops/agent/conversations?project=ProyectoDePrueba")
    assert r.status_code == 200, r.get_data(as_text=True)
    por_id = {c["conversation_id"]: c for c in r.get_json()["conversations"]}

    assert por_id[con_sesion]["pipeline_copilot"] is True, por_id[con_sesion]
    assert por_id[sin_sesion]["pipeline_copilot"] is False, por_id[sin_sesion]
