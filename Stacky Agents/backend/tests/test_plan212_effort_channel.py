"""Plan 212 F2 — El effort elegido viaja hasta `--effort` en el flujo estándar.

Antes de esto `/api/agents/run` ni siquiera leía el campo: el operador podía
elegir lo que quisiera en un modal y el CLI recibía siempre el default.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("STACKY_REAPER_ENABLED", "false")
    monkeypatch.setenv("STACKY_MANIFEST_WATCHER_ENABLED", "false")

    from db import init_db, session_scope
    from models import AgentExecution, Ticket

    init_db()
    with session_scope() as session:
        session.query(AgentExecution).delete()
        session.query(Ticket).delete()

    from app import create_app
    from services import run_slots
    from services.manifest_watcher import stop_manifest_watcher
    from services.ticket_status import stop_stale_recovery

    run_slots._reset_for_tests()
    app = create_app()
    app.config.update(TESTING=True)
    stop_stale_recovery()
    stop_manifest_watcher()
    with app.test_client() as c:
        yield c
    stop_stale_recovery()
    stop_manifest_watcher()
    run_slots._reset_for_tests()


def _mk_ticket(ado_id: int) -> int:
    from db import session_scope
    from models import Ticket

    with session_scope() as session:
        t = Ticket(ado_id=ado_id, project="RSPacifico", title="t",
                   ado_state="To Do", stacky_status="idle")
        session.add(t)
        session.flush()
        return t.id


def _spy(monkeypatch) -> dict:
    import agent_runner

    capturado: dict = {}

    def _fake(**kwargs):
        capturado.update(kwargs)
        return 4242

    monkeypatch.setattr(agent_runner, "run_agent", _fake)
    return capturado


def _post(client, tid, **extra):
    body = {"agent_type": "developer", "ticket_id": tid, "runtime": "github_copilot"}
    body.update(extra)
    return client.post("/api/agents/run", json=body)


def test_run_accepts_effort_high(client, monkeypatch):
    capturado = _spy(monkeypatch)

    r = _post(client, _mk_ticket(21210), effort="high")

    assert r.status_code == 202, r.get_json()
    assert capturado["effort_override"] == "high"


def test_run_without_effort_passes_none(client, monkeypatch):
    """Backward-compat: no mandar el campo es exactamente el comportamiento viejo."""
    capturado = _spy(monkeypatch)

    r = _post(client, _mk_ticket(21211))

    assert r.status_code == 202, r.get_json()
    assert capturado["effort_override"] is None


def test_run_rejects_invalid_effort(client, monkeypatch):
    import agent_runner

    monkeypatch.setattr(agent_runner, "run_agent",
                        lambda **kw: pytest.fail("no se lanza con effort inválido"))

    r = _post(client, _mk_ticket(21212), effort="ultra")

    assert r.status_code == 400
    body = r.get_json()
    assert body["error"] == "invalid_effort"
    assert "low" in body["valid"]


def test_run_degrades_effort_for_model(client, monkeypatch):
    """xhigh es de Opus: pedirlo con sonnet degrada en vez de romper el spawn."""
    capturado = _spy(monkeypatch)

    r = _post(client, _mk_ticket(21213), effort="xhigh",
              model_override="claude-sonnet-5")

    assert r.status_code == 202, r.get_json()
    assert capturado["effort_override"] == "high"


def test_run_invalid_effort_releases_slot(client, monkeypatch):
    from services import run_slots

    antes = run_slots.active_count()

    r = client.post("/api/agents/run", json={
        "agent_type": "developer", "ticket_id": _mk_ticket(21214),
        "runtime": "claude_code_cli", "effort": "ultra",
    })

    assert r.status_code == 400
    assert run_slots.active_count() == antes, \
        "un payload rechazado no puede dejar el cap de concurrencia consumido"


def test_runner_clamps_effort_against_routed_model():
    """C6: el endpoint no puede degradar lo que todavía no sabe (modelo adaptativo)."""
    from services import llm_router

    assert llm_router.clamp_effort_for_model("xhigh", "claude-sonnet-5") == "high"
    assert llm_router.clamp_effort_for_model("xhigh", "claude-opus-4-8") == "xhigh"
    assert llm_router.clamp_effort_for_model("max", "claude-haiku-4-5") == "high"
    assert llm_router.clamp_effort_for_model("xhigh", None) == "xhigh", \
        "sin modelo conocido no se degrada: el runner lo hará con el efectivo"


def test_runner_wires_the_final_clamp():
    """El clamp del runner es el que salva al selector adaptativo: debe estar."""
    import ast

    src = (ROOT / "services" / "claude_code_cli_runner.py").read_text(encoding="utf-8")
    arbol = ast.parse(src)
    llamadas = [
        n for n in ast.walk(arbol)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        and n.func.attr == "clamp_effort_for_model"
    ]

    assert llamadas, "el runner no degrada el effort contra el modelo ruteado"
    args = llamadas[0].args
    assert len(args) == 2 and getattr(args[1], "id", None) == "routed_model", \
        "el clamp del runner debe usar el modelo EFECTIVO, no el pedido"


def test_clamp_effort_delegate_matches_router():
    """El símbolo viejo sigue existiendo para brief/incident/resolutor."""
    from api.agents import _clamp_effort_for_model
    from services.llm_router import clamp_effort_for_model

    for effort, modelo in (("xhigh", "claude-haiku-4-5"),
                           ("max", "claude-sonnet-4-6"),
                           ("xhigh", None)):
        assert _clamp_effort_for_model(effort, modelo) == \
            clamp_effort_for_model(effort, modelo), (effort, modelo)
