"""Plan 242 F6 — API read-only: /cost-stats y /cost-scores.

Alcance recortado del plan (§0.3): SOLO los 2 endpoints read-only. Los 4 que
escriben o entrenan (model-status, model-train, forecast, calibration) son del
plan siguiente.

Reglas del 142 que los 2 respetan:
  1. Flag OFF -> {"enabled": false}, 200. NUNCA 404, NUNCA 500.
  2. Si el Centro de Costos entero esta apagado, ninguna sub-funcion se enciende.
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

_NUEVOS = ("/api/metrics/cost-stats", "/api/metrics/cost-scores")
# C17 — no-regresion sobre los 8 endpoints de costo que YA existen (142 + 199).
_LOS_8 = (
    "/api/metrics/cost-center/health",
    "/api/metrics/cost-summary",
    "/api/metrics/cost-burn",
    "/api/metrics/cost-burn-stacked",
    "/api/metrics/cost-heatmap",
    "/api/metrics/cost-distribution",
    # `dimension` es OBLIGATORIA en /cost-breakdown desde el Plan 142: sin ella
    # el endpoint devuelve 400 invalid_dimension. Es su contrato, no una
    # regresion — el smoke tiene que llamarlo como lo llama la UI.
    "/api/metrics/cost-breakdown?dimension=runtime",
    "/api/metrics/cost-reconciliation-audit",
)


@pytest.fixture(scope="module")
def _app():
    os.environ["STACKY_COST_CENTER_ENABLED"] = "true"
    os.environ["STACKY_COST_STATS_ENABLED"] = "true"
    os.environ["STACKY_COST_SCORING_ENABLED"] = "true"
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    return app


@pytest.fixture(scope="module")
def client(_app):
    with _app.test_client() as c:
        yield c


_NEXT_ADO_ID = 242000   # rango reservado para este archivo (no colisiona)


def _seed_exec(*, runtime="claude_code_cli", model="claude-sonnet-5",
               agent_type="developer", status="completed", started_at=None,
               ht=None, top=None, project="plan242proj", verdict=None,
               output="ok"):
    global _NEXT_ADO_ID
    _NEXT_ADO_ID += 1
    ado_id = _NEXT_ADO_ID

    from db import session_scope
    from models import AgentExecution, Ticket

    with session_scope() as session:
        t = Ticket(ado_id=ado_id, project=project, stacky_project_name=project,
                   title=f"plan242-{ado_id}", ado_state="Active",
                   work_item_type="Task", priority=2)
        session.add(t)
        session.flush()

        when = started_at or datetime.utcnow()
        md: dict = {"runtime": runtime, "model": model}
        if ht is not None:
            md["harness_telemetry"] = ht
        if top is not None:
            md.update(top)

        e = AgentExecution(ticket_id=t.id, agent_type=agent_type, status=status,
                           input_context_json="[]", started_by="test",
                           started_at=when, completed_at=when + timedelta(seconds=5),
                           verdict=verdict, output=output,
                           metadata_json=json.dumps(md))
        session.add(e)
        session.flush()
        return e.id, t.id


# ── Regla 1: flag OFF -> enabled false, 200 ─────────────────────────────────

@pytest.mark.parametrize("ruta,flag", [
    ("/api/metrics/cost-stats", "STACKY_COST_STATS_ENABLED"),
    ("/api/metrics/cost-scores", "STACKY_COST_SCORING_ENABLED"),
])
def test_cost_stats_flag_off_devuelve_enabled_false_200(client, monkeypatch, ruta, flag):
    import config as config_module
    # G10 — la INSTANCIA config.config, no el modulo: sobre el modulo se lee el
    # default y el branch OFF queda muerto.
    monkeypatch.setattr(config_module.config, flag, False)
    resp = client.get(ruta)
    assert resp.status_code == 200
    assert resp.get_json() == {"enabled": False}


@pytest.mark.parametrize("ruta", _NUEVOS)
def test_cost_center_off_apaga_los_dos(client, monkeypatch, ruta):
    """Regla 2 — el Centro de Costos apagado apaga toda sub-funcion."""
    import config as config_module
    monkeypatch.setattr(config_module.config, "STACKY_COST_CENTER_ENABLED", False)
    resp = client.get(ruta)
    assert resp.status_code == 200
    assert resp.get_json() == {"enabled": False}


# ── Validacion de entrada ───────────────────────────────────────────────────

@pytest.mark.parametrize("ruta", _NUEVOS)
def test_fecha_invalida_400(client, ruta):
    resp = client.get(f"{ruta}?from=not-a-date")
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "invalid_date"


def test_cost_stats_metric_invalida_400(client):
    """El ValueError de cost_stats.metric_value NO debe explotar como 500."""
    resp = client.get("/api/metrics/cost-stats?metric=metrica_inventada")
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "invalid_metric"


def test_cost_stats_dimension_invalida_400(client):
    resp = client.get("/api/metrics/cost-stats?dimension=dimension_inventada")
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "invalid_dimension"


def test_cost_stats_metric_valida_200(client):
    resp = client.get("/api/metrics/cost-stats?metric=duration_s&bins=5")
    assert resp.status_code == 200
    assert resp.get_json()["metric"] == "duration_s"


# ── G7: facturable vs nominal, separados ────────────────────────────────────

def test_cost_stats_separa_billable_de_nominal(client):
    _seed_exec(runtime="claude_code_cli",
               ht={"total_cost_usd": 1.5, "cost_estimated": False,
                   "input_tokens": 1000, "output_tokens": 200})
    _seed_exec(runtime="github_copilot",
               ht={"input_tokens": 500, "output_tokens": 100})
    body = client.get("/api/metrics/cost-stats").get_json()
    assert body["ok"] is True and body["enabled"] is True

    runtimes_billable = set(body["billable_only"]["by_dimension"]["runtime"])
    runtimes_nominal = set(body["nominal_only"]["by_dimension"]["runtime"])
    assert "github_copilot" not in runtimes_billable
    assert "github_copilot" in runtimes_nominal


def test_cost_stats_ambas_claves_siempre_presentes(client):
    """Sin records en la ventana -> payload vacio BIEN FORMADO, no 404 ni clave ausente."""
    body = client.get("/api/metrics/cost-stats?from=1999-01-01&to=1999-01-02").get_json()
    assert body["ok"] is True
    for bloque in ("billable_only", "nominal_only"):
        assert bloque in body
        assert body[bloque]["runs_total"] == 0
        assert body[bloque]["metrics"]["cost_usd"]["overall"]["n"] == 0


def test_cost_stats_echo_y_capped_presentes(client):
    body = client.get("/api/metrics/cost-stats").get_json()
    assert "filters_echo" in body and "capped" in body and "generated_at" in body


# ── /cost-scores ────────────────────────────────────────────────────────────

def test_cost_scores_shape(client):
    _seed_exec(ht={"total_cost_usd": 0.4, "cost_estimated": False,
                   "input_tokens": 800, "output_tokens": 400})
    body = client.get("/api/metrics/cost-scores").get_json()
    assert body["ok"] is True and body["enabled"] is True
    for clave in ("cohorts", "executions", "tickets", "grade_distribution",
                  "runs_total", "runs_scored", "filters_echo", "capped"):
        assert clave in body, clave


def test_cost_scores_top_n_clampeado_1_200(client):
    for pedido, tope in ((0, 1), (-5, 1), (99999, 200)):
        body = client.get(f"/api/metrics/cost-scores?top_n={pedido}").get_json()
        assert len(body["executions"]) <= tope


def test_cost_scores_top_n_no_numerico_no_rompe(client):
    resp = client.get("/api/metrics/cost-scores?top_n=abc")
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True


def test_cost_scores_toda_puntuacion_trae_razones(client):
    """KPI-2 sobre el payload REAL del endpoint, no sobre un fixture."""
    body = client.get("/api/metrics/cost-scores").get_json()
    assert body["executions"], "el seeding de este archivo debe dejar ejecuciones"
    for e in body["executions"]:
        assert e["reasons"], e["execution_id"]


# ── G3: nada de red ni LLM ──────────────────────────────────────────────────

@pytest.mark.parametrize("ruta", _NUEVOS)
def test_ningun_endpoint_nuevo_abre_red_ni_llm(client, monkeypatch, ruta):
    import socket
    import subprocess

    import requests

    def _boom(*a, **k):
        raise AssertionError("acceso a red/proceso prohibido en un endpoint read-only")

    monkeypatch.setattr(requests, "get", _boom)
    monkeypatch.setattr(requests, "post", _boom)
    monkeypatch.setattr(socket, "socket", _boom)
    monkeypatch.setattr(subprocess, "Popen", _boom)
    assert client.get(ruta).status_code == 200


# ── No-regresion ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("ruta", _LOS_8)
def test_los_8_endpoints_de_costo_siguen_iguales(client, ruta):
    """C17 — los 3 del Plan 199 son los vecinos inmediatos del punto de
    insercion; v1 cubria 5 y los dejaba justo afuera."""
    resp = client.get(ruta)
    assert resp.status_code == 200, ruta
    body = resp.get_json()
    assert body is not None and body.get("enabled") is not False, ruta


def test_endpoints_legacy_siguen_intactos(client):
    """R3 — el 242 no toca _execution_costs / ticket-costs / project-costs."""
    assert client.get("/api/metrics/project-costs").status_code == 200


def test_las_dos_funciones_nuevas_existen_en_metrics(client):
    """Anti-falso-verde: que el modulo declare las 2 vistas por nombre exacto."""
    from api import metrics
    assert callable(getattr(metrics, "cost_stats", None))
    assert callable(getattr(metrics, "cost_scores", None))
