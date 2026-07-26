"""Plan 171 F4/F2b — Endpoints de telemetría operativa + señal en el ciclo RSI.

Read-only y gateados por flag: con la master OFF, cada endpoint devuelve
`{"enabled": false}` con 200 y la app queda como hoy.
"""
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

import db  # noqa: E402

db.init_db()


@pytest.fixture(scope="module")
def _app():
    os.environ["STACKY_OPS_TELEMETRY_ENABLED"] = "true"
    os.environ["STACKY_OPS_BASELINE_ENABLED"] = "true"
    os.environ["STACKY_OPS_TRACE_ENABLED"] = "true"
    from app import create_app

    app = create_app()
    app.config["TESTING"] = True
    return app


@pytest.fixture(scope="module")
def client(_app):
    with _app.test_client() as c:
        yield c


@pytest.fixture(autouse=True)
def _aislar_umbrales(tmp_path, monkeypatch):
    """Umbrales por test: nunca se pisa el JSON real del operador."""
    import runtime_paths

    monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)


@pytest.fixture(autouse=True)
def _flags_on(monkeypatch):
    from config import config as cfg

    monkeypatch.setattr(cfg, "STACKY_OPS_TELEMETRY_ENABLED", True, raising=False)
    monkeypatch.setattr(cfg, "STACKY_OPS_BASELINE_ENABLED", True, raising=False)
    monkeypatch.setattr(cfg, "STACKY_OPS_TRACE_ENABLED", True, raising=False)


_NEXT_ADO_ID = 171000


def _seed_exec(*, runtime="codex_cli", model="claude-sonnet-5", agent_type="developer",
               status="completed", started_at=None, duration_s=5, md_extra=None,
               project="opsapiproj"):
    global _NEXT_ADO_ID
    _NEXT_ADO_ID += 1
    ado_id = _NEXT_ADO_ID

    from db import session_scope
    from models import AgentExecution, Ticket

    with session_scope() as session:
        t = Ticket(ado_id=ado_id, project=project, stacky_project_name=project,
                   title=f"ops-{ado_id}", ado_state="Active")
        session.add(t)
        session.flush()

        when = started_at or datetime.utcnow()
        md: dict = {"runtime": runtime}
        if model is not None:
            md["model"] = model
        md.update(md_extra or {})

        e = AgentExecution(
            ticket_id=t.id, agent_type=agent_type, status=status,
            input_context_json="[]", started_by="test", started_at=when,
            completed_at=(when + timedelta(seconds=duration_s)) if duration_s is not None else None,
            metadata_json=json.dumps(md),
        )
        session.add(e)
        session.flush()
        return e.id


def test_ops_health_siempre_200(client):
    r = client.get("/api/metrics/ops/health")

    assert r.status_code == 200
    body = r.get_json()
    assert isinstance(body["ok"], bool)
    assert isinstance(body["flag_enabled"], bool)


def test_summary_off_devuelve_enabled_false(client, monkeypatch):
    from config import config as cfg

    monkeypatch.setattr(cfg, "STACKY_OPS_TELEMETRY_ENABLED", False, raising=False)

    for ruta in ("/api/metrics/ops-summary", "/api/metrics/ops-trends",
                 "/api/metrics/ops-thresholds", "/api/metrics/run-trace/1"):
        r = client.get(ruta)
        assert r.status_code == 200, ruta
        assert r.get_json() == {"enabled": False}, ruta

    r_post = client.post("/api/metrics/ops-thresholds", json={"stall_minutes": 30})
    assert r_post.status_code == 200
    assert r_post.get_json() == {"enabled": False}


def test_summary_on_agrupa_por_agente_runtime(client):
    proyecto = "opsgroupproj"
    for _ in range(2):
        _seed_exec(agent_type="developer", runtime="codex_cli", project=proyecto)
    _seed_exec(agent_type="developer", runtime="codex_cli", status="error",
               duration_s=None, project=proyecto)
    _seed_exec(agent_type="qa", runtime="github_copilot", project=proyecto,
               md_extra={"tokens_in": 10, "tokens_out": 5})

    body = client.get(f"/api/metrics/ops-summary?project={proyecto}").get_json()

    assert body["enabled"] is True
    assert body["totals"]["runs"] == 4
    assert body["totals"]["error"] == 1
    celdas = {(g["agent_type"], g["runtime"]): g for g in body["groups"]}
    assert celdas[("developer", "codex_cli")]["runs"] == 3
    assert celdas[("developer", "codex_cli")]["error"] == 1
    assert celdas[("qa", "github_copilot")]["runs"] == 1
    assert body["baseline"]["enabled"] is True
    assert "thresholds" in body and body["thresholds"]["stall_minutes"] is not None


def test_summary_cuenta_runs_sin_modelo(client):
    proyecto = "opssinmodelo"
    _seed_exec(runtime="claude_code_cli", model=None, project=proyecto,
               md_extra={"claude_telemetry": {"usage": {"input_tokens": 5}}})

    body = client.get(f"/api/metrics/ops-summary?project={proyecto}").get_json()

    assert body["totals"]["runs_sin_modelo"] >= 1
    assert any("sin dato" in g["models"] for g in body["groups"])


def test_summary_baseline_off_por_flag(client, monkeypatch):
    from config import config as cfg

    monkeypatch.setattr(cfg, "STACKY_OPS_BASELINE_ENABLED", False, raising=False)
    body = client.get("/api/metrics/ops-summary").get_json()

    assert body["baseline"]["enabled"] is False
    assert body["baseline"]["regressions"] == []
    assert all(b["rule_id"] not in ("R-O2", "R-O3") for b in body["breaches"])


def test_trends_serie_continua(client):
    body = client.get("/api/metrics/ops-trends?days=5").get_json()

    assert body["enabled"] is True
    assert body["days"] == 5
    fechas = [s["date"] for s in body["series"]]
    assert len(fechas) == 5
    assert fechas == sorted(fechas), "orden ascendente"
    assert fechas[-1] == datetime.utcnow().strftime("%Y-%m-%d"), "termina HOY (UTC)"
    for i in range(1, 5):
        anterior = datetime.strptime(fechas[i - 1], "%Y-%m-%d")
        actual = datetime.strptime(fechas[i], "%Y-%m-%d")
        assert (actual - anterior).days == 1, "días consecutivos"


def test_thresholds_roundtrip_y_400(client):
    inicial = client.get("/api/metrics/ops-thresholds").get_json()
    assert inicial["enabled"] is True
    assert inicial["thresholds"]["error_rate_warn"] == 0.3

    r = client.post("/api/metrics/ops-thresholds", json={"stall_minutes": 30})
    assert r.status_code == 200
    assert r.get_json()["ok"] is True
    assert client.get("/api/metrics/ops-thresholds").get_json()["thresholds"]["stall_minutes"] == 30

    malo = client.post("/api/metrics/ops-thresholds", json={"stall_minutes": 0})
    assert malo.status_code == 400
    assert malo.get_json()["error"] == "invalid_thresholds:stall_minutes"

    desconocida = client.post("/api/metrics/ops-thresholds", json={"clave_falsa": 1})
    assert desconocida.status_code == 400
    assert desconocida.get_json()["error"] == "invalid_thresholds:clave_falsa"

    assert client.get("/api/metrics/ops-thresholds").get_json()["thresholds"]["stall_minutes"] == 30, \
        "un POST inválido no debe haber tocado el archivo"


def test_run_trace_ok_y_404(client):
    exec_id = _seed_exec(project="opstraceproj")

    r = client.get(f"/api/metrics/run-trace/{exec_id}")
    assert r.status_code == 200
    body = r.get_json()
    assert body["enabled"] is True
    assert body["trace"]["execution_id"] == exec_id

    r404 = client.get("/api/metrics/run-trace/999999")
    assert r404.status_code == 404
    assert r404.get_json()["error"] == "execution_not_found"


def test_summary_fecha_malformada_400(client):
    r = client.get("/api/metrics/ops-summary?from=chau")

    assert r.status_code == 400
    assert r.get_json()["error"] == "invalid_date"


# ── F2b — señal operativa en el ciclo de evolución (RSI) ─────────────────────

def test_evolution_collect_signals_incluye_ops(client):
    _seed_exec(project="opsrsiproj")
    from services.evolution_cycle import collect_signals

    s = collect_signals()

    assert "ops" in s
    assert s["ops"]["schema_version"] == 1
    assert "regressions" in s["ops"]
    assert "breaches" in s["ops"]
    assert "stalls" in s["ops"]


def test_evolution_collect_signals_flag_off_sin_ops(monkeypatch):
    from config import config as cfg
    from services.evolution_cycle import collect_signals

    monkeypatch.setattr(cfg, "STACKY_OPS_TELEMETRY_ENABLED", False, raising=False)

    assert "ops" not in collect_signals(), "flag OFF ⇒ shape previo byte-idéntico"
