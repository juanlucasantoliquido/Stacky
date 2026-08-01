"""V1.2 — Tests del advisor de runtime/modelo (services/run_advisor.py)."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")


@pytest.fixture(autouse=True)
def _db_ready():
    from db import init_db, session_scope
    from models import AgentExecution, Ticket

    init_db()
    with session_scope() as session:
        session.query(AgentExecution).delete()
        session.query(Ticket).delete()
    yield


def _mk_ticket(ado_id: int = 900) -> int:
    from db import session_scope
    from models import Ticket

    with session_scope() as session:
        t = Ticket(ado_id=ado_id, project="RSPacifico", title="t",
                   ado_state="To Do", stacky_status="idle")
        session.add(t)
        session.flush()
        return t.id


def _mk_exec(ticket_id: int, *, runtime: str, status: str,
             agent_type: str = "developer", cost: float | None = None) -> None:
    from db import session_scope
    from models import AgentExecution

    md: dict = {"runtime": runtime}
    if cost is not None:
        md["claude_telemetry"] = {"total_cost_usd": cost}
    with session_scope() as session:
        e = AgentExecution(
            ticket_id=ticket_id, agent_type=agent_type, status=status,
            input_context_json="[]", started_by="test",
            started_at=datetime.utcnow() - timedelta(days=1),
            metadata_json=json.dumps(md),
        )
        session.add(e)
        session.flush()


def test_clear_dominance_recommends_winner():
    from services.run_advisor import advise

    t = _mk_ticket()
    # codex: 9/10 completed; claude: 5/10 completed para developer
    for _ in range(9):
        _mk_exec(t, runtime="codex_cli", status="completed")
    _mk_exec(t, runtime="codex_cli", status="error")
    for _ in range(5):
        _mk_exec(t, runtime="claude_code_cli", status="completed")
    for _ in range(5):
        _mk_exec(t, runtime="claude_code_cli", status="error")

    adv = advise(agent_type="developer")
    assert adv.runtime == "codex_cli"
    assert adv.confidence == "high"
    assert "codex" in adv.reason.lower() or "%" in adv.reason


def test_insufficient_data_defaults():
    from services.run_advisor import advise

    t = _mk_ticket()
    _mk_exec(t, runtime="codex_cli", status="completed")  # solo 1 run (< 5)

    adv = advise(agent_type="developer")
    assert adv.confidence == "default"
    assert adv.runtime == "github_copilot"


def test_no_data_at_all_defaults():
    from services.run_advisor import advise

    adv = advise(agent_type="qa")
    assert adv.confidence == "default"
    assert adv.runtime == "github_copilot"


def test_only_capability_runtimes_considered():
    from services.run_advisor import advise

    t = _mk_ticket()
    for _ in range(6):
        _mk_exec(t, runtime="bogus_runtime", status="completed")
    adv = advise(agent_type="developer")
    # runtime fuera de CAPABILITIES no debe ganar
    assert adv.runtime != "bogus_runtime"


def test_model_never_exceeds_cap():
    from services.run_advisor import advise

    t = _mk_ticket()
    for _ in range(6):
        _mk_exec(t, runtime="claude_code_cli", status="completed")
    adv = advise(agent_type="developer")
    if adv.model:
        assert "opus" not in adv.model.lower()
        assert "fable" not in adv.model.lower()


# ── Endpoint ─────────────────────────────────────────────────────────────────
@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("STACKY_REAPER_ENABLED", "false")
    monkeypatch.setenv("STACKY_MANIFEST_WATCHER_ENABLED", "false")
    from app import create_app
    from services.ticket_status import stop_stale_recovery
    from services.manifest_watcher import stop_manifest_watcher

    app = create_app()
    app.config.update(TESTING=True)
    stop_stale_recovery()
    stop_manifest_watcher()
    with app.test_client() as c:
        yield c
    stop_stale_recovery()
    stop_manifest_watcher()


def test_advise_endpoint(client):
    t = _mk_ticket()
    for _ in range(6):
        _mk_exec(t, runtime="codex_cli", status="completed")
    r = client.get("/api/agents/advise?agent_type=developer")
    assert r.status_code == 200
    data = r.get_json()
    assert "runtime" in data and "reason" in data and "confidence" in data


# ── V2.2 (Plan 22) — Smart dispatch ENFORCE: el advisor deja de ser decorativo ──
#
# Hasta el 2026-08-01 la flag STACKY_RUN_ADVISOR_ENFORCE estaba declarada como
# `reserved=True` y su propio reserved_reason lo confesaba: "el enforcement nunca
# se implementó". El advisor sólo respondía en GET /advise (informativo); el launch
# ignoraba su recomendación y aplicaba el default fijo "github_copilot".
# El humano SIEMPRE gana: si el payload trae runtime explícito, esto no corre.


def test_v22_guarda_la_flag_dejo_de_estar_reservada():
    """GUARDA anti-falso-verde: si la flag siguiera `reserved`, el registro estaría
    mintiendo sobre una capacidad que sí existe. Se afirma en POSITIVO."""
    from services.harness_flags import FLAG_REGISTRY

    spec = next((f for f in FLAG_REGISTRY if f.key == "STACKY_RUN_ADVISOR_ENFORCE"), None)
    assert spec is not None, "la flag debe seguir registrada"
    assert not getattr(spec, "reserved", False), (
        "V2.2 implementado ⇒ la flag ya no es reservada"
    )
    assert not getattr(spec, "reserved_reason", None)


def test_v22_default_efectivo_es_off_en_config():
    """El default EFECTIVO vive en config.py, no en el registry."""
    from config import config

    assert getattr(config, "STACKY_RUN_ADVISOR_ENFORCE", None) is False


def test_v22_enforce_off_no_consulta_al_advisor(monkeypatch):
    """Flag OFF ⇒ comportamiento v1 byte-idéntico: ni siquiera se consulta."""
    from api import agents as agents_api
    import config as cfg
    from services import run_advisor

    llamadas = []
    monkeypatch.setattr(run_advisor, "advise", lambda **kw: llamadas.append(kw))
    monkeypatch.setattr(cfg.config, "STACKY_RUN_ADVISOR_ENFORCE", False, raising=False)

    assert agents_api._apply_advisor_enforce(agent_type="developer", project=None) is None
    assert llamadas == []


def test_v22_enforce_on_rutea_con_la_recomendacion(monkeypatch):
    """Flag ON + sin runtime explícito ⇒ se usa la recomendación del advisor."""
    from api import agents as agents_api
    import config as cfg
    from services import run_advisor

    class _Adv:
        runtime = "codex_cli"
        reason = "codex_cli: 90% éxito sobre 20 runs"
        confidence = "high"

    monkeypatch.setattr(run_advisor, "advise", lambda **kw: _Adv())
    monkeypatch.setattr(cfg.config, "STACKY_RUN_ADVISOR_ENFORCE", True, raising=False)

    routing = agents_api._apply_advisor_enforce(agent_type="developer", project=None)

    assert routing is not None
    assert routing["runtime"] == "codex_cli"
    assert routing["confidence"] == "high"
    assert "90%" in routing["reason"]


def test_v22_runtime_recomendado_invalido_no_se_aplica(monkeypatch):
    """Si el advisor devuelve un runtime fuera de _VALID_RUNTIMES, se ignora.
    Nunca se rutea a un runtime que el launch no sabe ejecutar."""
    from api import agents as agents_api
    import config as cfg
    from services import run_advisor

    class _Adv:
        runtime = "gemini_cli_inexistente"
        reason = "x"
        confidence = "high"

    monkeypatch.setattr(run_advisor, "advise", lambda **kw: _Adv())
    monkeypatch.setattr(cfg.config, "STACKY_RUN_ADVISOR_ENFORCE", True, raising=False)

    assert agents_api._apply_advisor_enforce(agent_type="developer", project=None) is None


def test_v22_advisor_roto_no_tumba_el_launch(monkeypatch):
    """Fail-open: un advisor que explota deja el default, no rompe el run."""
    from api import agents as agents_api
    import config as cfg
    from services import run_advisor

    def _boom(**kw):
        raise RuntimeError("db caida")

    monkeypatch.setattr(run_advisor, "advise", _boom)
    monkeypatch.setattr(cfg.config, "STACKY_RUN_ADVISOR_ENFORCE", True, raising=False)

    assert agents_api._apply_advisor_enforce(agent_type="developer", project=None) is None


def test_v22_el_launch_consume_el_enforce():
    """Gate de CONSUMIDOR DE PRODUCCIÓN: no alcanza con que el helper exista,
    el endpoint /run tiene que llamarlo. Se lee el fuente real de run() para no
    depender de un censo por AST (que da cero si la llamada va por alias)."""
    import inspect
    from api import agents as agents_api

    fuente = inspect.getsource(agents_api.run)
    assert "_apply_advisor_enforce" in fuente, (
        "V2.2 sin cablear: /run no consulta el enforce del advisor."
    )
    # y el humano sigue ganando: sólo se consulta si el runtime vino ausente
    assert "runtime_defaulted" in fuente


# ── V2.2 (Plan 22) mitad 2 — PRESUPUESTO por ticket ─────────────────────────
#
# `harness_flags.py:1381` confesaba: "el tope de costo nunca se implementó. Hoy NO
# limita nada". Los tests viven acá (y no en un test_run_budget.py nuevo) porque
# este archivo YA está registrado en los DOS ratchets y V2.2 es UN solo ítem.


def test_v22_budget_guarda_la_flag_dejo_de_estar_reservada():
    """GUARDA anti-falso-verde, afirmada en POSITIVO antes que las ausencias."""
    from services.harness_flags import FLAG_REGISTRY

    spec = next((f for f in FLAG_REGISTRY if f.key == "STACKY_BUDGET_PER_TICKET_USD"), None)
    assert spec is not None
    assert not getattr(spec, "reserved", False)
    from config import config
    assert getattr(config, "STACKY_BUDGET_PER_TICKET_USD", None) == 0.0


def test_v22_budget_cero_es_sin_limite(monkeypatch):
    """0.0 = sin límite ⇒ no evalúa nada (byte-idéntico)."""
    import config as cfg
    from services import run_budget

    monkeypatch.setattr(cfg.config, "STACKY_BUDGET_PER_TICKET_USD", 0.0, raising=False)
    assert run_budget.evaluate(ticket_id=1, model="claude-sonnet-4-6") is None


def test_v22_degrade_model_baja_un_escalon():
    from services.run_budget import degrade_model

    assert "sonnet" in degrade_model("claude-opus-4-8")
    assert "haiku" in degrade_model("claude-sonnet-4-6")
    # El más barato de la escalera no baja más: nunca sube ni inventa modelo.
    assert degrade_model("claude-haiku-4-5") is None
    assert degrade_model(None) is None


def test_v22_dentro_del_presupuesto_pasa(monkeypatch):
    import config as cfg
    from services import run_budget

    monkeypatch.setattr(cfg.config, "STACKY_BUDGET_PER_TICKET_USD", 10.0, raising=False)
    monkeypatch.setattr(run_budget, "spent_for_ticket", lambda _t: 2.0)

    d = run_budget.evaluate(ticket_id=1, model="claude-sonnet-4-6", estimated_run_usd=1.0)
    assert d.action == run_budget.ACTION_OK
    assert d.spent_usd == 2.0 and d.projected_usd == 3.0


def test_v22_excedido_degrada_el_modelo_un_escalon(monkeypatch):
    import config as cfg
    from services import run_budget

    monkeypatch.setattr(cfg.config, "STACKY_BUDGET_PER_TICKET_USD", 5.0, raising=False)
    monkeypatch.setattr(run_budget, "spent_for_ticket", lambda _t: 4.9)

    d = run_budget.evaluate(ticket_id=1, model="claude-sonnet-4-6", estimated_run_usd=1.0)
    assert d.action == run_budget.ACTION_DEGRADE
    assert "haiku" in d.model_to
    assert d.to_metadata()["budget_degraded"] is True


def test_v22_excedido_sin_donde_degradar_bloquea_con_402(monkeypatch):
    import config as cfg
    from services import run_budget

    monkeypatch.setattr(cfg.config, "STACKY_BUDGET_PER_TICKET_USD", 5.0, raising=False)
    monkeypatch.setattr(run_budget, "spent_for_ticket", lambda _t: 9.0)

    d = run_budget.evaluate(ticket_id=1, model="claude-haiku-4-5", estimated_run_usd=1.0)
    assert d.action == run_budget.ACTION_BLOCK
    payload = d.to_error_payload()
    assert payload["error"] == "budget_exceeded"
    assert payload["spent"] == 9.0 and payload["budget"] == 5.0


def test_v22_force_budget_permite_el_override_y_lo_sella(monkeypatch):
    """El operador manda: con force_budget=true pasa igual, pero queda registrado."""
    import config as cfg
    from services import run_budget

    monkeypatch.setattr(cfg.config, "STACKY_BUDGET_PER_TICKET_USD", 5.0, raising=False)
    monkeypatch.setattr(run_budget, "spent_for_ticket", lambda _t: 99.0)

    d = run_budget.evaluate(ticket_id=1, model="claude-haiku-4-5", force=True)
    assert d.action == run_budget.ACTION_OK
    assert d.forced is True
    assert d.to_metadata()["budget_forced"] is True


def test_v22_no_medir_el_gasto_no_bloquea(monkeypatch):
    """Falla-abierto: si el cálculo del gasto explota, NO se traba al operador."""
    from services import run_budget

    def _boom(_t):
        raise RuntimeError("db caida")

    monkeypatch.setattr(run_budget, "session_scope", None, raising=False)
    assert run_budget.spent_for_ticket(999999) == 0.0


def test_v22_el_launch_consume_el_presupuesto():
    """Gate de CONSUMIDOR DE PRODUCCIÓN de la mitad 2."""
    import inspect
    from api import agents as agents_api

    fuente = inspect.getsource(agents_api.run)
    assert "run_budget" in fuente, "V2.2 mitad 2 sin cablear: /run no evalúa presupuesto."
    assert "budget_exceeded" in fuente or "402" in fuente
