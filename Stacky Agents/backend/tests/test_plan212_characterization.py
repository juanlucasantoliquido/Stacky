"""Plan 212 F0 — Caracterización de los 3 agujeros del selector de modelo/effort.

Estos tests describen el estado REAL del sistema antes de F1-F3. Tres nacen en
rojo a propósito (el agujero que el plan cierra) y tres nacen verdes: son el
ratchet anti-regresión de la política de modelos y de la matriz de efforts.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

_EFFORTS = ["low", "medium", "high", "xhigh", "max"]


# ---------------------------------------------------------------------------
# Agujero 1 — la elección de modelo no llega al router del runner
# ---------------------------------------------------------------------------

def test_decide_accepts_allow_opus_and_keeps_opus():
    """El permiso que el endpoint ya otorga tiene que poder viajar hasta decide()."""
    from services import llm_router

    decision = llm_router.decide(
        agent_type="business", blocks=[], override="claude-opus-4-8",
        backend="anthropic", allow_opus=True,
    )

    assert decision.model == "claude-opus-4-8"


def test_decide_without_allow_opus_still_clamps():
    """Ratchet G4: sin permiso explícito, el cap global sigue mandando."""
    from services import llm_router

    decision = llm_router.decide(
        agent_type="business", blocks=[], override="claude-opus-4-8",
        backend="anthropic",
    )

    assert decision.model == "claude-sonnet-5"
    assert "clamp" in decision.reason


# ---------------------------------------------------------------------------
# Agujero 2 — /api/agents/run no tiene canal de effort
# ---------------------------------------------------------------------------

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


def _mk_ticket(ado_id: int = 21200) -> int:
    from db import session_scope
    from models import Ticket

    with session_scope() as session:
        t = Ticket(ado_id=ado_id, project="RSPacifico", title="t",
                   ado_state="To Do", stacky_status="idle")
        session.add(t)
        session.flush()
        return t.id


def _spy_run_agent(monkeypatch) -> dict:
    """Captura los kwargs con que el endpoint invoca run_agent."""
    import agent_runner

    capturado: dict = {}

    def _fake(**kwargs):
        capturado.update(kwargs)
        return 4242

    monkeypatch.setattr(agent_runner, "run_agent", _fake)
    return capturado


def test_run_endpoint_accepts_effort_and_propagates(client, monkeypatch):
    capturado = _spy_run_agent(monkeypatch)
    tid = _mk_ticket()

    r = client.post("/api/agents/run", json={
        "agent_type": "developer", "ticket_id": tid,
        "runtime": "github_copilot", "effort": "high",
    })

    assert r.status_code == 202, r.get_json()
    assert capturado.get("effort_override") == "high"


def test_run_endpoint_rejects_unknown_effort(client, monkeypatch):
    monkeypatch.setattr(
        __import__("agent_runner"), "run_agent",
        lambda **kw: pytest.fail("no se lanza un run con un effort inválido"),
    )
    tid = _mk_ticket(21201)

    r = client.post("/api/agents/run", json={
        "agent_type": "developer", "ticket_id": tid,
        "runtime": "github_copilot", "effort": "ultra",
    })

    assert r.status_code == 400
    assert r.get_json()["error"] == "invalid_effort"


# ---------------------------------------------------------------------------
# Agujero 3 — el catálogo puede driftear respecto de la política real
# ---------------------------------------------------------------------------

def _catalogo() -> dict:
    path = ROOT / "config" / "model_catalog.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_effort_matrix_parity_catalog_vs_clamp():
    """Ratchet KPI-4: lo que el catálogo promete es lo que el clamp respeta."""
    from api.agents import _clamp_effort_for_model

    soporte = _catalogo()["runtimes"]["claude_code_cli"]["effort_support"]

    for model_id, soportados in soporte.items():
        for effort in _EFFORTS:
            sin_degradar = _clamp_effort_for_model(effort, model_id) == effort
            assert sin_degradar is (effort in soportados), (
                f"drift: {model_id} + {effort} → catálogo dice "
                f"{effort in soportados} pero el clamp dice {sin_degradar}"
            )


def test_runner_effort_set_is_superset_of_catalog():
    """El runner no puede tirar un effort que el catálogo ofrece al operador."""
    from services.claude_code_cli_runner import CLI_VALID_EFFORTS

    del_runner = set(CLI_VALID_EFFORTS)
    cli = _catalogo()["runtimes"]["claude_code_cli"]
    # `efforts` son objetos {id,label}: al operador se le ofrece el `id`.
    del_catalogo = {e["id"] for e in cli["efforts"]} | {
        e for lista in cli["effort_support"].values() for e in lista
    }

    assert del_catalogo <= del_runner, (
        f"el catálogo ofrece efforts que el runner descarta: {del_catalogo - del_runner}"
    )
