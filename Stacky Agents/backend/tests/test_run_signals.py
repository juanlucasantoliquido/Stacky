"""Plan 171 F1/F2 — Núcleo PURO de señales operativas + persistencia de umbrales.

Todo lo de este archivo es determinista: sin Flask, sin DB (salvo el caso 15, que
solo toca un JSON en tmp_path). Sin datos suficientes, una regla NO dispara: un
aviso falso es peor que ningún aviso.
"""
from __future__ import annotations

import os
import sys
import types
from datetime import datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

from services import run_signals as rs  # noqa: E402

_NOW = datetime(2026, 7, 25, 12, 0, 0)
_SEQ = [0]


def _p(**kw) -> rs.RunPoint:
    _SEQ[0] += 1
    base = {
        "execution_id": _SEQ[0],
        "agent_type": "developer",
        "runtime": "codex_cli",
        "model": "claude-sonnet-5",
        "status": "completed",
        "started_at": _NOW - timedelta(hours=1),
        "duration_seconds": 10.0,
        "billable_usd": 0.0,
        "has_model": True,
    }
    base.update(kw)
    if "has_model" not in kw:
        base["has_model"] = base["model"] is not None
    return rs.RunPoint(**base)


def _th(**kw) -> dict:
    return rs.merge_thresholds({"stall_minutes": 60, **kw})


# ── 1. Percentil ─────────────────────────────────────────────────────────────

def test_percentile_ejemplos_normativos():
    assert rs.percentile_nearest_rank([5, 1, 3, 2, 4], 0.5) == 3
    assert rs.percentile_nearest_rank([5, 1, 3, 2, 4], 0.9) == 5
    assert rs.percentile_nearest_rank([], 0.5) is None
    assert rs.percentile_nearest_rank([7.0], 0.5) == 7.0
    assert rs.percentile_nearest_rank([7.0], 0.99) == 7.0


# ── 2-4. Proyección desde ExecRecord ─────────────────────────────────────────

def _record(*, status, started, completed, cost_kind="estimated", cost_usd=0.25, model="m1"):
    from services.cost_analytics import CostRow

    row = CostRow(runtime="codex_cli", model=model, tokens_in=10, tokens_out=5,
                  cache_read_tokens=None, cost_usd=cost_usd, cost_kind=cost_kind,
                  cache_savings_usd=None)
    return types.SimpleNamespace(execution_id=7, ticket_id=1, ado_id=1, project="p",
                                 agent_type="developer", status=status,
                                 started_at=started, completed_at=completed, row=row)


def test_from_exec_record_completed_con_duracion():
    started = _NOW - timedelta(seconds=30)
    point = rs.from_exec_record(_record(status="completed", started=started, completed=_NOW))

    assert point.duration_seconds == 30.0
    assert point.billable_usd == 0.25, "estimated es facturable"
    assert point.has_model is True
    assert point.runtime == "codex_cli"

    nominal = rs.from_exec_record(
        _record(status="completed", started=started, completed=_NOW, cost_kind="nominal")
    )
    assert nominal.billable_usd == 0.0, "nominal (suscripción) NUNCA es facturable"


def test_from_exec_record_error_sin_duracion():
    point = rs.from_exec_record(
        _record(status="error", started=_NOW - timedelta(seconds=30), completed=_NOW)
    )

    assert point.status == "error"
    assert point.duration_seconds is None, "los percentiles solo miran corridas completed"


def test_from_exec_record_model_none_es_sin_dato_en_grupos():
    point = rs.from_exec_record(
        _record(status="completed", started=_NOW - timedelta(seconds=5), completed=_NOW, model=None)
    )
    assert point.model is None
    assert point.has_model is False

    body = rs.summarize_groups([point])
    assert body["groups"][0]["models"] == {rs.SIN_DATO: 1}
    assert body["totals"]["runs_sin_modelo"] == 1


# ── 5-6. Agregados ───────────────────────────────────────────────────────────

def test_summarize_groups_totales_y_orden():
    points = (
        [_p(agent_type="b", runtime="r1") for _ in range(3)]
        + [_p(agent_type="a", runtime="r1") for _ in range(5)]
        + [_p(agent_type="a", runtime="r2", status="error", duration_seconds=None)]
        + [_p(agent_type="a", runtime="r2", status="completed", duration_seconds=4.0)]
        + [_p(agent_type="c", runtime="r1", status="running", duration_seconds=None)]
    )
    body = rs.summarize_groups(points)

    assert [(g["agent_type"], g["runtime"]) for g in body["groups"]] == [
        ("a", "r1"), ("b", "r1"), ("a", "r2"), ("c", "r1"),
    ], "orden por runs DESC, desempate alfabético"
    celda = next(g for g in body["groups"] if (g["agent_type"], g["runtime"]) == ("a", "r2"))
    assert celda["terminal"] == 2
    assert celda["error"] == 1
    assert celda["error_rate"] == 0.5
    assert body["totals"]["runs"] == 11
    assert body["totals"]["running"] == 1
    assert body["totals"]["error"] == 1
    assert body["totals"]["terminal"] == 10
    assert body["totals"]["error_rate"] == round(1 / 10, 4)


def test_summarize_groups_vacio():
    body = rs.summarize_groups([])

    assert body["groups"] == []
    assert body["totals"] == {
        "runs": 0, "terminal": 0, "completed": 0, "needs_review": 0, "error": 0,
        "running": 0, "error_rate": None, "p50_seconds": None, "p90_seconds": None,
        "billable_usd": 0.0, "runs_sin_modelo": 0,
    }


# ── 7-8. Series y ventanas ───────────────────────────────────────────────────

def test_daily_series_rellena_dias_vacios():
    ayer = _NOW - timedelta(days=1)
    series = rs.daily_series(
        [_p(started_at=ayer, duration_seconds=8.0, billable_usd=0.5)], days=3, now=_NOW
    )

    assert len(series) == 3
    assert [s["date"] for s in series] == [
        (_NOW - timedelta(days=2)).strftime("%Y-%m-%d"),
        ayer.strftime("%Y-%m-%d"),
        _NOW.strftime("%Y-%m-%d"),
    ]
    assert series[0] == {"date": series[0]["date"], "runs": 0, "errors": 0,
                         "billable_usd": 0.0, "p50_seconds": None}
    assert series[1]["runs"] == 1
    assert series[1]["p50_seconds"] == 8.0
    assert series[1]["billable_usd"] == 0.5
    assert series[2]["runs"] == 0
    assert series[2]["p50_seconds"] is None


def test_split_windows_bordes():
    p6 = _p(started_at=_NOW - timedelta(days=6))
    p8 = _p(started_at=_NOW - timedelta(days=8))
    p40 = _p(started_at=_NOW - timedelta(days=40))

    current, baseline = rs.split_windows([p6, p8, p40], _NOW)

    assert [x.execution_id for x in current] == [p6.execution_id]
    assert [x.execution_id for x in baseline] == [p8.execution_id]


# ── 9-13. Reglas ─────────────────────────────────────────────────────────────

def test_r_o1_dispara_y_respeta_min_runs():
    errores = [_p(status="error", duration_seconds=None) for _ in range(4)]
    ok = [_p(status="completed")]
    breaches, _stalls = rs.evaluate_thresholds(errores + ok, _th(), _NOW)

    r1 = [b for b in breaches if b["rule_id"] == "R-O1"]
    assert len(r1) == 1
    assert r1[0]["severity"] == "warn"
    assert r1[0]["observed"] == 0.8
    assert r1[0]["threshold"] == 0.3
    assert r1[0]["message"] == "Tasa de error alta: 4/5 corridas en la ventana"

    pocos, _ = rs.evaluate_thresholds(errores, _th(), _NOW)
    assert [b for b in pocos if b["rule_id"] == "R-O1"] == [], "4 runs < min_runs=5: NO dispara"


def test_r_o2_regresion_error_rate():
    baseline = ([_p(status="error", duration_seconds=None)]
                + [_p(status="completed") for _ in range(19)])
    current = ([_p(status="error", duration_seconds=None) for _ in range(4)]
               + [_p(status="completed") for _ in range(2)])

    breaches = rs.detect_regressions(current, baseline, _th())
    r2 = [b for b in breaches if b["rule_id"] == "R-O2"]

    assert len(r2) == 1
    assert r2[0]["severity"] == "critical"
    assert r2[0]["observed"] == round(4 / 6, 4)
    assert r2[0]["reference"] == 0.05
    assert r2[0]["threshold"] == 0.15
    assert r2[0]["agent_type"] == "developer" and r2[0]["runtime"] == "codex_cli"

    baseline_corto = [_p(status="completed") for _ in range(5)]
    assert [b for b in rs.detect_regressions(current, baseline_corto, _th())
            if b["rule_id"] == "R-O2"] == [], "baseline < baseline_min_runs: NO dispara"


def test_r_o3_regresion_latencia():
    baseline = [_p(duration_seconds=40.0) for _ in range(10)]
    current = [_p(duration_seconds=90.0) for _ in range(5)]

    r3 = [b for b in rs.detect_regressions(current, baseline, _th()) if b["rule_id"] == "R-O3"]
    assert len(r3) == 1
    assert r3[0]["severity"] == "warn"
    assert r3[0]["observed"] == 90.0
    assert r3[0]["reference"] == 40.0

    baseline_rapido = [_p(duration_seconds=10.0) for _ in range(10)]
    assert [b for b in rs.detect_regressions(current, baseline_rapido, _th())
            if b["rule_id"] == "R-O3"] == [], "baseline p90 < p90_min_seconds: es ruido"


def test_r_o4_stalls():
    viejo = _p(status="running", duration_seconds=None,
               started_at=_NOW - timedelta(minutes=120))
    nuevo = _p(status="running", duration_seconds=None,
               started_at=_NOW - timedelta(minutes=90))
    sano = _p(status="running", duration_seconds=None,
              started_at=_NOW - timedelta(minutes=5))

    breaches, stalls = rs.evaluate_thresholds([nuevo, sano, viejo], _th(), _NOW)

    r4 = [b for b in breaches if b["rule_id"] == "R-O4"]
    assert len(r4) == 1
    assert r4[0]["observed"] == 2
    assert r4[0]["agent_type"] is None and r4[0]["runtime"] is None
    assert r4[0]["message"] == "2 corrida(s) activas hace más de 60 minutos"
    assert stalls == {"count": 2, "execution_ids": [viejo.execution_id, nuevo.execution_id]}, \
        "ids con los más viejos primero"


def test_r_o5_presupuesto_null_no_dispara_y_seteado_si():
    hoy = [_p(started_at=_NOW - timedelta(hours=2), billable_usd=1.5)]

    breaches, _ = rs.evaluate_thresholds(hoy, _th(), _NOW)
    assert [b for b in breaches if b["rule_id"] == "R-O5"] == [], "budget null = regla apagada"

    breaches2, _ = rs.evaluate_thresholds(hoy, _th(daily_budget_usd=1.0), _NOW)
    r5 = [b for b in breaches2 if b["rule_id"] == "R-O5"]
    assert len(r5) == 1
    assert r5[0]["observed"] == 1.5
    assert r5[0]["threshold"] == 1.0

    ayer = [_p(started_at=_NOW - timedelta(days=1), billable_usd=9.0)]
    breaches3, _ = rs.evaluate_thresholds(ayer, _th(daily_budget_usd=1.0), _NOW)
    assert [b for b in breaches3 if b["rule_id"] == "R-O5"] == [], "solo cuenta HOY (UTC)"


# ── 14. Umbrales y orden ─────────────────────────────────────────────────────

def test_merge_y_sort():
    merged = rs.merge_thresholds({"stall_minutes": 30, "desconocida": 1})

    assert merged["stall_minutes"] == 30
    assert "desconocida" not in merged
    assert merged["error_rate_warn"] == rs.DEFAULT_THRESHOLDS["error_rate_warn"]
    assert rs.merge_thresholds(None) == rs.DEFAULT_THRESHOLDS
    assert rs.merge_thresholds(None) is not rs.DEFAULT_THRESHOLDS, "debe ser una copia"

    desordenados = [
        {"rule_id": "R-O4", "severity": "warn"},
        {"rule_id": "R-O2", "severity": "critical"},
        {"rule_id": "R-O1", "severity": "warn"},
        {"rule_id": "R-O3", "severity": "critical"},
    ]
    assert [b["rule_id"] for b in rs.sort_breaches(desordenados)] == [
        "R-O2", "R-O3", "R-O1", "R-O4",
    ]


# ── 15. Persistencia de umbrales (F2) ────────────────────────────────────────

def test_ops_thresholds_roundtrip_con_tmp_path(tmp_path, monkeypatch):
    import runtime_paths
    from services import ops_telemetry as ot
    from services.ticket_status import EXECUTION_TIMEOUT_MINUTES

    monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)

    efectivo = ot.load_thresholds()
    assert efectivo["stall_minutes"] == EXECUTION_TIMEOUT_MINUTES
    assert efectivo["stall_minutes"] is not None, "el core SIEMPRE recibe el int resuelto"
    assert efectivo["error_rate_warn"] == rs.DEFAULT_THRESHOLDS["error_rate_warn"]

    ot.save_thresholds({"stall_minutes": 30})
    assert ot.load_thresholds()["stall_minutes"] == 30

    ot.save_thresholds({"stall_minutes": None})
    assert ot.load_thresholds()["stall_minutes"] == EXECUTION_TIMEOUT_MINUTES

    with pytest.raises(ValueError) as exc:
        ot.save_thresholds({"error_rate_warn": 2})
    assert str(exc.value).startswith("invalid_thresholds:error_rate_warn")

    with pytest.raises(ValueError) as exc2:
        ot.save_thresholds({"clave_falsa": 1})
    assert str(exc2.value).startswith("invalid_thresholds:clave_falsa")

    (tmp_path / "telemetry" / "ops_thresholds.json").write_text("{{{", encoding="utf-8")
    corrupto = ot.load_thresholds()
    assert corrupto["error_rate_warn"] == rs.DEFAULT_THRESHOLDS["error_rate_warn"]
    assert corrupto["stall_minutes"] == EXECUTION_TIMEOUT_MINUTES
