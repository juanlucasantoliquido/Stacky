"""Plan 279 F9 — Recorrido de punta a punta del copiloto de pipelines.

6 casos. Cierran K6 (paridad real de los 3 runtimes) y K7 (deshacer-primero).
"""
from __future__ import annotations

import json
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import pytest  # noqa: E402

_CONVERSATION_ADO_ID = -2


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
def todo_on(monkeypatch):
    import config as cfg

    for key, value in (
        ("STACKY_DEVOPS_AGENT_ENABLED", True),
        ("STACKY_PIPELINE_COPILOT_ENABLED", True),
        ("STACKY_PIPELINE_GENERATOR_ENABLED", True),
        # La de commit queda OFF (su valor de fabrica): el caso 3 lo necesita.
        ("STACKY_PIPELINE_COPILOT_COMMIT_ENABLED", False),
        ("STACKY_DEVOPS_ACTION_CATALOG_ENABLED", True),
        ("STACKY_DEVOPS_ACTION_NL_ENABLED", True),
        ("STACKY_DEVOPS_AGENT_ACTION_RUN_ENABLED", False),
    ):
        monkeypatch.setattr(cfg.config, key, value, raising=False)


@pytest.fixture
def health_all_on(monkeypatch):
    """Health sintetico con el master y TODOS los health_key en True."""
    import api.devops_actions as mod
    from services.devops_action_catalog import DEVOPS_ACTION_CATALOG, MASTER_HEALTH_KEY

    payload = {MASTER_HEALTH_KEY: True}
    for a in DEVOPS_ACTION_CATALOG:
        if a.health_key:
            payload[a.health_key] = True
    monkeypatch.setattr(mod, "_health_payload_for_catalog", lambda: payload)


@pytest.fixture
def run_agent_mock(monkeypatch):
    import agent_runner

    caja: dict = {}

    def _fake(**kwargs):
        caja.update(kwargs)
        return 4242

    monkeypatch.setattr(agent_runner, "run_agent", _fake)
    return caja


def _nueva_conversacion() -> int:
    from db import session_scope
    from models import Ticket

    with session_scope() as session:
        ticket = Ticket(
            ado_id=_CONVERSATION_ADO_ID,
            project="ProyectoDePrueba",
            stacky_project_name="ProyectoDePrueba",
            title="[Stacky] DevOps Chat — plan 279 e2e",
            work_item_type="Task",
            ado_state="Active",
        )
        session.add(ticket)
        session.flush()
        ticket.external_id = -ticket.id
        session.flush()
        return ticket.id


def _avanzar(client, cid: int, destino: str, **campos):
    return client.post(f"/api/pipeline-copilot/session/{cid}/advance",
                       json={"to": destino, "fields": campos})


# --------------------------------------------------------------------------


def test_recorrido_feliz_intake_a_confirm(client, todo_on):
    cid = _nueva_conversacion()
    assert client.get(
        f"/api/pipeline-copilot/session/{cid}"
    ).get_json()["session"]["state"] == "intake"

    pasos = [
        ("discovery", {"provider": "ado", "stack": "python",
                       "project": "ProyectoDePrueba", "branch": "feature/x"}),
        ("draft", {"draft_ref": "draft-1"}),
        ("review", {}),
        ("secrets", {"missing_variables": ["DB_PASSWORD"]}),
        ("confirm", {}),
    ]
    for destino, campos in pasos:
        r = _avanzar(client, cid, destino, **campos)
        assert r.status_code == 200, (destino, r.get_data(as_text=True))
        assert r.get_json()["session"]["state"] == destino

    final = client.get(f"/api/pipeline-copilot/session/{cid}").get_json()["session"]
    assert final["state"] == "confirm"
    assert final["provider"] == "ado"
    assert final["draft_ref"] == "draft-1"
    assert final["missing_variables"] == ["DB_PASSWORD"]


def test_los_3_runtimes_llegan_al_copiloto(client, todo_on, run_agent_mock,
                                           monkeypatch):
    """GATE DE K6 [C3].

    NO se mide contra /api/devops/actions/propose: ese endpoint IGNORA el runtime
    (api/devops_actions.py:95) y daria verde sin probar nada. Se mide contra
    POST /api/devops/agent/conversations, que es quien discrimina.
    """
    # (a) los 2 CLI arrancan el turno.
    for runtime in ("claude_code_cli", "codex_cli"):
        r = client.post("/api/devops/agent/conversations",
                        json={"project": "ProyectoDePrueba", "message": "hola",
                              "runtime": runtime})
        assert r.status_code == 202, (runtime, r.get_data(as_text=True))
        body = r.get_json()
        assert body["ok"] is True
        assert body["execution_id"] == 4242, body
        assert run_agent_mock["runtime"] == runtime

    # (b) GitHub Copilot: 200 con el camino determinista, NO un 400.
    r = client.post("/api/devops/agent/conversations",
                    json={"project": "ProyectoDePrueba", "message": "hola",
                          "runtime": "github_copilot"})
    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json()
    assert body["mode"] == "deterministic", body
    assert body["propose_url"] == "/api/devops/actions/propose", body

    # GUARD anti-regresion (espejo de F6 caso 6): con la flag OFF sigue dando 400.
    import config as cfg

    monkeypatch.setattr(cfg.config, "STACKY_PIPELINE_COPILOT_ENABLED", False,
                        raising=False)
    r_off = client.post("/api/devops/agent/conversations",
                        json={"project": "ProyectoDePrueba", "message": "hola",
                              "runtime": "github_copilot"})
    assert r_off.status_code == 400, r_off.get_data(as_text=True)
    assert r_off.get_json()["error"] == "devops_chat_requires_cli_runtime"


def test_commit_con_flag_off_queda_bloqueado(client, todo_on, health_all_on):
    """La escritura del plan no puede proponerse ejecutable con el interruptor
    del asistente apagado (su valor de fabrica)."""
    r = client.post("/api/devops/actions/propose",
                    json={"text": "crear la pipeline nueva en el repositorio"})
    assert r.status_code == 200, r.get_data(as_text=True)
    prop = r.get_json()["proposal"]
    assert prop is not None, r.get_json()
    assert prop["action_id"] == "devops.pipeline_new.commit", prop
    assert prop["needs_confirmation"] is True, prop
    assert prop["blocked_reason"] == "agent_write_disabled", prop


def test_la_sesion_nunca_salta_a_committed_sin_pasar_por_confirm(client, todo_on):
    cid = _nueva_conversacion()
    # Desde intake: ilegal.
    assert _avanzar(client, cid, "committed").status_code == 409
    for destino in ("discovery", "draft", "review"):
        assert _avanzar(client, cid, destino).status_code == 200
        assert _avanzar(client, cid, "committed").status_code == 409, destino
    # Recien desde confirm es legal (si no, el test de arriba no discrimina).
    assert _avanzar(client, cid, "confirm").status_code == 200
    assert _avanzar(client, cid, "committed").status_code == 200


def test_la_transicion_deja_una_linea_de_log_sin_pii(client, todo_on, monkeypatch):
    import services.stacky_logger as slog

    capturado: list[tuple] = []

    def _fake_info(source, action, **kwargs):
        capturado.append((source, action, kwargs))

    monkeypatch.setattr(slog.logger, "info", _fake_info)

    cid = _nueva_conversacion()
    secreto_del_operador = "necesito-una-pipeline-para-el-cliente-ACME"
    r = _avanzar(client, cid, "discovery", provider="ado",
                 branch="feature/rama-secreta", project="ProyectoConfidencial",
                 open_questions=[secreto_del_operador],
                 missing_variables=["DB_PASSWORD"])
    assert r.status_code == 200, r.get_data(as_text=True)

    # GUARD OBLIGATORIO, PRIMERO: el capturador SI engancho. Sin esto, el assert
    # de ausencia de abajo pasaria vacio (el peor falso verde posible).
    lineas = [c for c in capturado if c[1] == "session_advance"]
    assert lineas, f"no se capturo ninguna linea session_advance: {capturado}"

    crudo = json.dumps(lineas, ensure_ascii=False, default=str)
    assert "session_advance" in crudo
    assert "pipeline_copilot" in crudo
    assert "discovery" in crudo, "el destino tiene que quedar registrado"

    # Y AHORA la ausencia: CERO PII.
    assert secreto_del_operador not in crudo, crudo
    assert "ProyectoConfidencial" not in crudo, crudo
    assert "feature/rama-secreta" not in crudo, crudo
    assert "DB_PASSWORD" not in crudo, crudo
    assert "azure-pipelines.yml" not in crudo, "el undo_hint no se loguea (trae la rama)"


def test_en_confirm_el_operador_ve_el_deshacer(client, todo_on):
    """GATE DE K7 [ADICION ARQUITECTO]: el deshacer llega ANTES de confirmar."""
    cid = _nueva_conversacion()

    # GUARD: en intake todavia no hay nada que deshacer.
    assert client.get(
        f"/api/pipeline-copilot/session/{cid}/undo-hint"
    ).get_json()["undo_hint"] == ""

    for destino, campos in (
        ("discovery", {"provider": "ado", "branch": "feature/x",
                       "project": "ProyectoDePrueba"}),
        ("draft", {}), ("review", {}), ("confirm", {}),
    ):
        assert _avanzar(client, cid, destino, **campos).status_code == 200, destino

    texto = client.get(
        f"/api/pipeline-copilot/session/{cid}/undo-hint"
    ).get_json()["undo_hint"]
    assert "azure-pipelines.yml" in texto, texto
    assert "feature/x" in texto, texto
