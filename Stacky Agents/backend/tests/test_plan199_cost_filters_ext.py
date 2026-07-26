"""Plan 199 F4/F5 — Filtros nuevos y agregadores nuevos del Centro de Costos.

Todo aditivo: los contratos congelados del 142 (`summarize`, `breakdown`, `burn`)
no se tocan, y `CostFilters` gana campos AL FINAL con default, así todo caller
previo sigue construyéndola igual.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

from services import cost_analytics as ca  # noqa: E402


def _rec(cost=1.0, kind="reported", runtime="codex_cli", model="gpt-5",
         when=None, agent_type="developer") -> ca.ExecRecord:
    return ca.ExecRecord(
        execution_id=1, ticket_id=None, ado_id=None, project="P",
        agent_type=agent_type, status="completed",
        started_at=when or datetime(2026, 7, 1, 10, 0, 0),
        row=ca.CostRow(runtime=runtime, model=model, tokens_in=10, tokens_out=5,
                       cache_read_tokens=0, cost_usd=cost, cost_kind=kind,
                       cache_savings_usd=None),
    )


# ---------------------------------------------------------------------------
# F4 — filtros
# ---------------------------------------------------------------------------

def test_costfilters_es_backward_compatible():
    """Los campos nuevos van AL FINAL con default: nadie tiene que cambiar."""
    f = ca.CostFilters()

    assert f.runtimes == () and f.models == ()
    assert f.min_cost_usd is None and f.max_cost_usd is None


def test_plurales_coexisten_con_singulares():
    """`runtime` sigue existiendo; `runtimes` no lo reemplaza."""
    f = ca.CostFilters(runtime="codex_cli", runtimes=("a", "b"))

    assert f.runtime == "codex_cli" and f.runtimes == ("a", "b")


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("STACKY_REAPER_ENABLED", "false")
    monkeypatch.setenv("STACKY_MANIFEST_WATCHER_ENABLED", "false")

    from app import create_app
    from services.manifest_watcher import stop_manifest_watcher
    from services.ticket_status import stop_stale_recovery

    app = create_app()
    app.config.update(TESTING=True)
    stop_stale_recovery()
    stop_manifest_watcher()
    with app.test_client() as c:
        yield c
    stop_stale_recovery()
    stop_manifest_watcher()


def test_parse_filters_lee_los_nuevos_params(client):
    from api.metrics import _parse_filters

    with client.application.test_request_context(
            "/?runtimes=codex_cli,claude_code_cli&models=gpt-5&min_cost=0.5&max_cost=2"):
        from flask import request

        f = _parse_filters(request.args)

    assert f.runtimes == ("codex_cli", "claude_code_cli")
    assert f.models == ("gpt-5",)
    assert f.min_cost_usd == 0.5 and f.max_cost_usd == 2.0


def test_parse_filters_tolera_basura(client):
    from api.metrics import _parse_filters

    with client.application.test_request_context("/?min_cost=abc&runtimes=,,"):
        from flask import request

        f = _parse_filters(request.args)

    assert f.min_cost_usd is None and f.runtimes == ()


# ---------------------------------------------------------------------------
# F5 — burn_stacked
# ---------------------------------------------------------------------------

def test_burn_stacked_desglosa_por_grupo():
    records = [
        _rec(cost=1.0, runtime="codex_cli"),
        _rec(cost=2.0, runtime="claude_code_cli"),
    ]

    r = ca.burn_stacked(records, "day", "runtime")

    assert r["group_by"] == "runtime"
    assert r["groups"] == ["claude_code_cli", "codex_cli"]
    punto = r["series"][0]
    assert punto["groups"]["codex_cli"] == 1.0
    assert punto["billable_usd"] == 3.0


def test_burn_stacked_group_by_invalido_cae_a_runtime():
    assert ca.burn_stacked([_rec()], "day", "inventado")["group_by"] == "runtime"


def test_burn_stacked_sin_fecha_no_entra():
    sin_fecha = _rec()
    sin_fecha.started_at = None

    assert ca.burn_stacked([sin_fecha], "day", "runtime")["series"] == []


def test_burn_stacked_nominal_no_suma():
    """Solo lo facturable cuenta; un costo nominal no es gasto real."""
    r = ca.burn_stacked([_rec(cost=5.0, kind="nominal")], "day", "runtime")

    assert r["series"][0]["billable_usd"] == 0.0


# ---------------------------------------------------------------------------
# F5 — heatmap
# ---------------------------------------------------------------------------

def test_heatmap_agrupa_por_dia_y_hora():
    # 2026-07-01 es miércoles (weekday 2).
    records = [
        _rec(cost=1.0, when=datetime(2026, 7, 1, 10, 30)),
        _rec(cost=2.0, when=datetime(2026, 7, 1, 10, 45)),
        _rec(cost=4.0, when=datetime(2026, 7, 2, 3, 0)),
    ]

    r = ca.heatmap(records)

    celda = next(c for c in r["cells"] if c["weekday"] == 2 and c["hour"] == 10)
    assert celda["billable_usd"] == 3.0 and celda["runs"] == 2
    assert r["max_billable_usd"] == 4.0


def test_heatmap_ignora_sin_fecha():
    sin_fecha = _rec()
    sin_fecha.started_at = None

    assert ca.heatmap([sin_fecha])["cells"] == []


def test_heatmap_vacio_no_rompe():
    assert ca.heatmap([]) == {"cells": [], "max_billable_usd": 0.0}


# ---------------------------------------------------------------------------
# F5 — distribution
# ---------------------------------------------------------------------------

def test_distribution_arma_el_histograma():
    records = [_rec(cost=c) for c in (1.0, 2.0, 3.0, 10.0)]

    r = ca.distribution(records, bins=3)

    assert len(r["bins"]) == 3
    assert sum(b["count"] for b in r["bins"]) == 4
    assert r["min"] == 1.0 and r["max"] == 10.0 and r["total"] == 4


def test_distribution_el_maximo_cae_en_el_ultimo_bin():
    """Sin el guard, el valor máximo caería en un bin que no existe."""
    r = ca.distribution([_rec(cost=0.0), _rec(cost=10.0)], bins=5)

    assert r["bins"][-1]["count"] == 1
    assert sum(b["count"] for b in r["bins"]) == 2


def test_distribution_todos_iguales_no_divide_por_cero():
    r = ca.distribution([_rec(cost=2.0), _rec(cost=2.0)], bins=10)

    assert r["bins"] == [{"lo": 2.0, "hi": 2.0, "count": 2}]


def test_distribution_ignora_los_sin_costo():
    """Una corrida sin costo conocido no es una corrida de $0."""
    r = ca.distribution([_rec(cost=1.0), _rec(cost=None)], bins=4)

    assert r["total"] == 1


def test_distribution_sin_datos():
    assert ca.distribution([], bins=5) == {
        "bins": [], "total": 0, "min": None, "max": None}


def test_distribution_bins_clampeado():
    assert len(ca.distribution([_rec(cost=1.0), _rec(cost=5.0)], bins=999)["bins"]) == 50
    assert len(ca.distribution([_rec(cost=1.0), _rec(cost=5.0)], bins=0)["bins"]) == 1


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

def test_endpoints_flag_off(client, monkeypatch):
    from config import config as cfg

    monkeypatch.setattr(cfg, "STACKY_COST_CENTER_ENABLED", False, raising=False)

    for ruta in ("/api/metrics/cost-burn-stacked", "/api/metrics/cost-heatmap",
                 "/api/metrics/cost-distribution"):
        r = client.get(ruta)
        assert r.status_code == 200 and r.get_json() == {"enabled": False}, ruta


def test_burn_stacked_valida_sus_parametros(client):
    assert client.get(
        "/api/metrics/cost-burn-stacked?group_by=zzz").get_json()["error"] == "invalid_group_by"
    assert client.get(
        "/api/metrics/cost-burn-stacked?bucket=zzz").get_json()["error"] == "invalid_bucket"


def test_endpoints_responden_ok(client):
    for ruta in ("/api/metrics/cost-burn-stacked", "/api/metrics/cost-heatmap",
                 "/api/metrics/cost-distribution?bins=5"):
        body = client.get(ruta).get_json()
        assert body["ok"] is True and body["enabled"] is True, ruta


def test_fecha_malformada_da_400(client):
    """Comparten el mismo guard de filtros que los endpoints del 142."""
    assert client.get(
        "/api/metrics/cost-heatmap?from=no-es-fecha").status_code == 400
