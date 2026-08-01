"""Plan 279 F6 — Tests del turno del agente con el contrato del copiloto.

8 casos. Cierra K1: hoy 0 acciones del catalogo son alcanzables desde el turno;
despues, las 6.

[C2] K1 se mide por `ast` (caso 8) Y por comportamiento (caso 3). Los dos son
obligatorios: el AST solo probaria que el codigo existe, no que corre; el
comportamiento solo probaria el efecto, y podria lograrse por un camino paralelo.
PROHIBIDO medir K1 con un grep/substring: un comentario lo satisface.
"""
from __future__ import annotations

import ast
import json
import os
import pathlib

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import pytest  # noqa: E402

_CONVERSATION_ADO_ID = -2

_DEVOPS_AGENT_PY = (
    pathlib.Path(__file__).resolve().parents[1] / "api" / "devops_agent.py"
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
def agente_on(monkeypatch):
    import config as cfg

    monkeypatch.setattr(cfg.config, "STACKY_DEVOPS_AGENT_ENABLED", True, raising=False)
    monkeypatch.setattr(cfg.config, "STACKY_PIPELINE_COPILOT_ENABLED", True, raising=False)
    monkeypatch.setattr(cfg.config, "STACKY_PIPELINE_COPILOT_COMMIT_ENABLED", False,
                        raising=False)


@pytest.fixture
def capturado(monkeypatch):
    """Mockea agent_runner.run_agent y captura los context_blocks del turno."""
    import agent_runner

    caja: dict = {}

    def _fake(**kwargs):
        caja.update(kwargs)
        return 4242

    monkeypatch.setattr(agent_runner, "run_agent", _fake)
    return caja


def _nueva_conversacion(description: str | None = None) -> int:
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


def _contenido(caja: dict) -> str:
    return caja["context_blocks"][0]["content"]


def _con_sesion(state: str = "draft", **campos) -> str:
    from services.pipeline_session import PipelineSession, session_to_dict

    return json.dumps({
        "kind": "devops_chat",
        "pipeline_session": session_to_dict(PipelineSession(state=state, **campos)),
    })


# --------------------------------------------------------------------------


def test_sin_flag_ni_sesion_el_modulo_importa_igual():
    """Smoke: F6 no puede romper el import de api.devops_agent."""
    import importlib

    mod = importlib.import_module("api.devops_agent")
    assert hasattr(mod, "start_conversation")
    assert hasattr(mod, "send_message")
    assert hasattr(mod, "_copilot_on")


def test_sin_sesion_el_mensaje_no_se_toca(client, agente_on, capturado):
    """Byte-compat: sin sesion, el contenido es el mensaje CRUDO, caracter por caracter."""
    cid = _nueva_conversacion()
    crudo = "listame las pipelines del proyecto"
    r = client.post(f"/api/devops/agent/conversations/{cid}/message",
                    json={"message": crudo})
    assert r.status_code == 202, r.get_data(as_text=True)
    assert _contenido(capturado) == crudo


def test_con_sesion_el_mensaje_se_envuelve(client, agente_on, capturado):
    """[C2] GATE DE COMPORTAMIENTO de K1."""
    cid = _nueva_conversacion(_con_sesion("draft"))
    crudo = "revisame el borrador"
    r = client.post(f"/api/devops/agent/conversations/{cid}/message",
                    json={"message": crudo})
    assert r.status_code == 202, r.get_data(as_text=True)
    envuelto = _contenido(capturado)
    assert envuelto != crudo, "el mensaje quedo crudo: el contrato no se aplico"
    assert crudo in envuelto, "el pedido del operador tiene que seguir adentro"
    assert "draft" in envuelto, "el prompt debe nombrar el estado de la sesion"
    assert "/api/devops/actions/propose" in envuelto


def test_con_flag_off_el_mensaje_no_se_envuelve(client, agente_on, capturado,
                                                monkeypatch):
    import config as cfg

    monkeypatch.setattr(cfg.config, "STACKY_PIPELINE_COPILOT_ENABLED", False,
                        raising=False)
    cid = _nueva_conversacion(_con_sesion("draft"))
    crudo = "revisame el borrador"
    r = client.post(f"/api/devops/agent/conversations/{cid}/message",
                    json={"message": crudo})
    assert r.status_code == 202, r.get_data(as_text=True)
    assert _contenido(capturado) == crudo


def test_copilot_con_flag_on_da_200_determinista(client, agente_on):
    r = client.post("/api/devops/agent/conversations",
                    json={"project": "ProyectoDePrueba", "message": "hola",
                          "runtime": "github_copilot"})
    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json()
    assert body["ok"] is True
    assert body["mode"] == "deterministic", body
    assert body["propose_url"] == "/api/devops/actions/propose", body


def test_copilot_con_flag_off_sigue_dando_400(client, agente_on, monkeypatch):
    """Anti-regresion R9: el 400 NO se borra, se le agrega una salida honesta.

    Borrarlo dejaria un run con Copilot terminando `completed` sin conversacion
    y sin error: exactamente el falso verde que el gate existe para evitar.
    """
    import config as cfg

    monkeypatch.setattr(cfg.config, "STACKY_PIPELINE_COPILOT_ENABLED", False,
                        raising=False)
    r = client.post("/api/devops/agent/conversations",
                    json={"project": "ProyectoDePrueba", "message": "hola",
                          "runtime": "github_copilot"})
    assert r.status_code == 400, r.get_data(as_text=True)
    body = r.get_json()
    assert body["ok"] is False
    assert body["error"] == "devops_chat_requires_cli_runtime", body
    assert "github_copilot" in body["detail"], body


def test_conversacion_anclada_conserva_el_contrato_de_consola(
    client, agente_on, capturado, monkeypatch
):
    """R10: los dos envoltorios conviven EN ORDEN (consola primero, copiloto despues)."""
    import config as cfg

    monkeypatch.setattr(cfg.config, "STACKY_DEVOPS_REMOTE_TARGET_ENABLED", True,
                        raising=False)
    cid = _nueva_conversacion(json.dumps({
        "kind": "devops_chat",
        "server_alias": "srv-01",
        "pipeline_session": json.loads(_con_sesion("draft"))["pipeline_session"],
    }))
    r = client.post(f"/api/devops/agent/conversations/{cid}/message",
                    json={"message": "mira el disco"})
    assert r.status_code == 202, r.get_data(as_text=True)
    texto = _contenido(capturado)

    assert "CONSOLA REMOTA STACKY" in texto, texto[:400]
    assert "COPILOTO DE PIPELINES STACKY" in texto, texto[:400]
    # ORDEN: el copiloto envuelve DESPUES, asi que su cabecera queda ANTES en el
    # texto final y el contrato de consola (el mas restrictivo) queda adentro.
    assert texto.index("COPILOTO DE PIPELINES STACKY") < texto.index("CONSOLA REMOTA STACKY")


def test_ast_el_turno_llama_al_constructor_del_contrato():
    """[C2] GATE ESTRUCTURAL de K1. Por `ast`, jamas por substring."""

    def censo(src: str) -> tuple[int, int]:
        arbol = ast.parse(src)
        imports = 0
        calls = 0
        for node in ast.walk(arbol):
            if isinstance(node, ast.ImportFrom):
                if node.module == "services.pipeline_copilot_prompt" and any(
                    a.name == "build_copilot_prompt" for a in node.names
                ):
                    imports += 1
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id == "build_copilot_prompt":
                    calls += 1
        return imports, calls

    # GUARD ANTI-FALSO-VERDE, PRIMERO: si el censo no distingue un comentario del
    # codigo, el gate no vale nada.
    senuelo = (
        "# from services.pipeline_copilot_prompt import build_copilot_prompt\n"
        "# build_copilot_prompt(session, url, msg, 1, commit_enabled=True)\n"
        "x = 1\n"
    )
    assert censo(senuelo) == (0, 0), "el censo cuenta comentarios: gate invalido"

    imports, calls = censo(_DEVOPS_AGENT_PY.read_text(encoding="utf-8"))
    assert imports >= 1, (
        "api/devops_agent.py no importa build_copilot_prompt desde "
        "services.pipeline_copilot_prompt (ImportFrom real, no un comentario)"
    )
    assert calls >= 1, (
        "api/devops_agent.py no LLAMA a build_copilot_prompt (ast.Call real)"
    )
