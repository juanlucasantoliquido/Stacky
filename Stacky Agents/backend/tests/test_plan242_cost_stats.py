"""Plan 242 F1 — Motor estadistico puro (cost_stats.py).

Cubre los 33 casos de F1.5. Todo PURO: sin DB, sin red, sin LLM.
KPI-1: >=6 metricas x >=6 dimensiones con distribucion completa.
"""
import ast
import json
import math
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from services import cost_analytics as ca
from services.cost_analytics import CostRow, ExecRecord
from services.cost_signals import SignalRow
from services.cost_stats import (
    _DIMENSIONS,
    _METRICS,
    Distribution,
    by_dimension,
    cache_efficiency,
    describe,
    dimension_key,
    histogram,
    mad_outliers,
    metric_value,
    percentile,
    rework_index,
    stats_payload,
    tukey_outliers,
)

BACKEND_ROOT = Path(__file__).resolve().parent.parent
_T0 = datetime(2026, 7, 1, 10, 0, 0)


def _row(**kw) -> CostRow:
    base = dict(runtime="codex_cli", model="gpt-5", tokens_in=1000, tokens_out=500,
                cache_read_tokens=None, cost_usd=0.05, cost_kind="reported",
                cache_savings_usd=None)
    base.update(kw)
    return CostRow(**base)


def _rec(execution_id=1, ticket_id=1, agent_type="developer", project="P",
         status="completed", started_at=None, row=None, signals=None,
         duration_s=None, work_item_type="Task", priority=2, **kw) -> ExecRecord:
    return ExecRecord(execution_id=execution_id, ticket_id=ticket_id, ado_id=None,
                      project=project, agent_type=agent_type, status=status,
                      started_at=started_at or _T0, row=row or _row(),
                      signals=signals, duration_s=duration_s,
                      work_item_type=work_item_type, priority=priority, **kw)


# ── percentile ──────────────────────────────────────────────────────────────

def test_percentile_lista_vacia_es_none():
    assert percentile([], 50) is None


def test_percentile_un_elemento():
    assert percentile([7.0], 99) == 7.0
    assert percentile([7.0], 0) == 7.0


def test_percentile_interpolacion_lineal_conocida():
    assert percentile([1.0, 2.0, 3.0, 4.0], 50) == 2.5


def test_percentile_p0_y_p100_son_min_y_max():
    v = [1.0, 4.0, 9.0, 16.0]
    assert percentile(v, 0) == 1.0
    assert percentile(v, 100) == 16.0


def test_p50_coincide_con_median():
    for datos in ([1.0, 2.0, 3.0], [1.0, 2.0, 3.0, 4.0], [5.5, 0.1, 9.9, 2.2, 7.7]):
        d = describe(datos)
        assert d.p50 == d.median


# ── describe ────────────────────────────────────────────────────────────────

def test_describe_expone_las_13_claves():
    """KPI-1 — las 13 claves de dispersion + los 5 percentiles."""
    d = describe([1.0, 2.0, 3.0, 4.0, 5.0])
    for campo in ("n", "n_missing", "total", "minimum", "maximum", "mean", "median",
                  "stdev", "q1", "q3", "iqr", "cv", "mad",
                  "p50", "p75", "p90", "p95", "p99"):
        assert hasattr(d, campo), campo
        assert getattr(d, campo) is not None, campo


def test_describe_lista_vacia_todo_none():
    d = describe([])
    assert d.n == 0 and d.n_missing == 0
    for campo in ("total", "minimum", "maximum", "mean", "median", "stdev",
                  "q1", "q3", "iqr", "cv", "mad", "p50", "p99"):
        assert getattr(d, campo) is None, campo


def test_describe_un_elemento_stdev_none():
    d = describe([3.0])
    assert d.n == 1
    assert d.stdev is None and d.iqr is None and d.cv is None
    assert d.mad == 0.0
    assert d.minimum == d.maximum == d.mean == d.median == d.p50 == 3.0


def test_describe_todos_iguales_mad_cero():
    d = describe([0.05] * 10)
    assert d.stdev == 0.0 and d.iqr == 0.0 and d.mad == 0.0 and d.cv == 0.0


def test_describe_ignora_none_y_cuenta_missing():
    d = describe([1.0, None, 3.0, None, 5.0])
    assert d.n == 3 and d.n_missing == 2
    assert d.mean == 3.0


def test_describe_mean_cero_no_divide_por_cero():
    d = describe([0.0, 0.0, 0.0, 0.0])
    assert d.mean == 0.0
    assert d.cv is None          # NO ZeroDivisionError


def test_stdev_es_muestral_n_menos_1():
    # [2,4,4,4,5,5,7,9] -> stdev poblacional 2.0 ; muestral = sqrt(32/7)
    d = describe([2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0])
    # rel_tol 1e-6: describe() redondea a 6 decimales antes de devolver (G5).
    assert math.isclose(d.stdev, math.sqrt(32 / 7), rel_tol=1e-6)
    assert not math.isclose(d.stdev, 2.0, rel_tol=1e-6)   # 2.0 seria la POBLACIONAL


# ── histogram ───────────────────────────────────────────────────────────────

def test_histogram_vacio_es_lista_vacia():
    assert histogram([]) == []
    assert histogram([None, None]) == []


def test_histogram_todos_iguales_un_solo_bin():
    bins = histogram([0.05] * 7)
    assert len(bins) == 1
    assert bins[0].lo == bins[0].hi == 0.05 and bins[0].count == 7


def test_histogram_el_maximo_cae_en_el_ultimo_bin():
    bins = histogram([0.0, 1.0, 2.0, 3.0, 4.0], bins=4)
    assert len(bins) == 4
    assert sum(b.count for b in bins) == 5
    assert bins[-1].count == 2       # el 3.0 y el maximo 4.0


def test_histogram_bins_se_clampea_1_a_100():
    datos = [float(i) for i in range(200)]
    assert len(histogram(datos, bins=0)) == 1
    assert len(histogram(datos, bins=-5)) == 1
    assert len(histogram(datos, bins=5000)) == 100


def test_histogram_coincide_con_cost_analytics_distribution():
    """C19 — una sola verdad: `cost_stats.histogram` es la canonica y
    `cost_analytics.distribution` (Plan 199) devuelve lo mismo para cost_usd."""
    costos = [0.01, 0.02, 0.05, 0.13, 0.21, 0.34, 0.55, 0.89]
    recs = [_rec(execution_id=i, row=_row(cost_usd=c)) for i, c in enumerate(costos)]
    mio = histogram(costos, bins=5)
    suyo = ca.distribution(recs, bins=5)
    assert len(mio) == len(suyo["bins"])
    for a, b in zip(mio, suyo["bins"]):
        assert a.count == b["count"]
        assert math.isclose(a.lo, b["lo"], rel_tol=1e-9, abs_tol=1e-9)
        assert math.isclose(a.hi, b["hi"], rel_tol=1e-9, abs_tol=1e-9)


# ── outliers ────────────────────────────────────────────────────────────────

def test_tukey_iqr_cero_no_aplica():
    r = tukey_outliers([0.05] * 8)
    assert r.applicable is False and r.indices == [] and r.n_outliers == 0
    assert "IQR" in r.reason


def test_tukey_menos_de_4_muestras_no_aplica():
    r = tukey_outliers([1.0, 2.0, 3.0])
    assert r.applicable is False and "4 muestras" in r.reason


def test_tukey_detecta_outlier_alto_conocido():
    datos = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 100.0]
    r = tukey_outliers(datos)
    assert r.applicable is True
    assert r.indices == [8] and r.n_outliers == 1
    assert r.fence_high is not None and r.fence_high < 100.0


def test_tukey_indices_son_de_la_lista_original_con_nones():
    datos = [1.0, None, 2.0, 3.0, None, 4.0, 5.0, 6.0, 7.0, 8.0, 100.0]
    r = tukey_outliers(datos)
    assert r.indices == [10]           # posicion en la lista ORIGINAL
    assert datos[r.indices[0]] == 100.0


def test_mad_cero_no_aplica_y_no_divide():
    r = mad_outliers([2.0, 2.0, 2.0, 2.0, 2.0, 9.0])
    assert r.applicable is False and r.indices == []
    assert "MAD" in r.reason


def test_mad_detecta_outlier_conocido():
    datos = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 500.0]
    r = mad_outliers(datos)
    assert r.applicable is True
    assert 8 in r.indices
    assert r.method == "mad"


# ── metric_value / dimension_key ────────────────────────────────────────────

def test_metric_value_tokens_total_none_si_falta_uno():
    r = _rec(row=_row(tokens_in=100, tokens_out=None))
    assert metric_value(r, "tokens_total") is None      # no suma contra 0
    r2 = _rec(row=_row(tokens_in=100, tokens_out=50))
    assert metric_value(r2, "tokens_total") == 150


def test_metric_value_usd_por_ktok_none_si_tokens_out_cero():
    r = _rec(row=_row(cost_usd=0.5, tokens_out=0))
    assert metric_value(r, "usd_per_ktok_out") is None
    r2 = _rec(row=_row(cost_usd=0.5, tokens_out=1000))
    assert metric_value(r2, "usd_per_ktok_out") == 0.5


def test_metric_value_cache_creation_desde_signals():
    r = _rec(signals=SignalRow(cache_creation_tokens=42))
    assert metric_value(r, "cache_creation_tokens") == 42
    assert metric_value(_rec(signals=None), "cache_creation_tokens") is None


def test_metric_value_metrica_desconocida_lanza():
    with pytest.raises(ValueError):
        metric_value(_rec(), "metrica_inventada")


def test_dimension_key_ausente_es_sin_dato():
    r = _rec(row=_row(runtime=None, model=None), agent_type=None, project=None,
             work_item_type=None, priority=None)
    assert dimension_key(r, "runtime") == "(sin dato)"
    assert dimension_key(r, "model") == "(sin dato)"
    assert dimension_key(r, "agent_type") == "(sin dato)"
    assert dimension_key(r, "project") == "(sin proyecto)"
    assert dimension_key(r, "work_item_type") == "(sin tipo)"
    assert dimension_key(r, "priority") == "(sin prioridad)"
    with pytest.raises(ValueError):
        dimension_key(r, "dimension_inventada")


def test_by_dimension_cubre_las_6_dimensiones():
    """KPI-1 — 6 metricas x 6 dimensiones."""
    assert len(_DIMENSIONS) >= 6 and len(_METRICS) >= 6
    recs = [_rec(execution_id=1, row=_row(runtime="codex_cli")),
            _rec(execution_id=2, row=_row(runtime="claude_code_cli"))]
    for dim in _DIMENSIONS:
        out = by_dimension(recs, dim, "cost_usd")
        assert out, dim
        assert all(isinstance(v, Distribution) for v in out.values())


def test_by_dimension_claves_ordenadas_alfabeticamente():
    recs = [_rec(execution_id=1, row=_row(runtime="zeta")),
            _rec(execution_id=2, row=_row(runtime="alfa")),
            _rec(execution_id=3, row=_row(runtime="mike"))]
    claves = list(by_dimension(recs, "runtime", "cost_usd").keys())
    assert claves == sorted(claves) == ["alfa", "mike", "zeta"]


# ── cache_efficiency / rework_index ─────────────────────────────────────────

def test_cache_efficiency_denominador_cero_es_none():
    recs = [_rec(row=_row(cache_read_tokens=None, tokens_in=None))]
    out = cache_efficiency(recs)
    assert out["cache_read_ratio"] is None
    assert out["cache_write_overhead_ratio"] is None
    assert out["runs_with_cache_data"] == 0


def test_cache_efficiency_calcula_ratios():
    recs = [_rec(row=_row(cache_read_tokens=500, tokens_in=500, cache_savings_usd=0.01),
                 signals=SignalRow(cache_creation_tokens=250))]
    out = cache_efficiency(recs)
    assert out["cache_read_ratio"] == 0.5
    assert out["cache_write_overhead_ratio"] == 0.5
    assert out["runs_with_cache_data"] == 1
    assert out["cache_savings_usd_total"] == 0.01


def test_rework_index_desempate_por_execution_id():
    """Determinismo: mismo started_at -> el primero del par es el id mas chico."""
    recs = [_rec(execution_id=9, ticket_id=1, started_at=_T0, row=_row(cost_usd=1.0)),
            _rec(execution_id=3, ticket_id=1, started_at=_T0, row=_row(cost_usd=2.0))]
    out = rework_index(recs)
    assert out["pairs_total"] == 1 and out["pairs_with_rework"] == 1
    assert out["rework_runs"] == 1
    # el "primero" es el id 3 -> el rework cuesta lo del id 9 (1.0)
    assert out["rework_cost_usd"] == 1.0


def test_rework_cost_solo_facturables():
    recs = [_rec(execution_id=1, ticket_id=1, started_at=_T0, row=_row(cost_usd=1.0)),
            _rec(execution_id=2, ticket_id=1, started_at=_T0 + timedelta(minutes=1),
                 row=_row(runtime="github_copilot", cost_usd=5.0, cost_kind="nominal"))]
    out = rework_index(recs)
    assert out["rework_runs"] == 1
    assert out["rework_cost_usd"] == 0.0     # el nominal NO suma


def test_rework_orphan_runs_se_reportan_aparte():
    recs = [_rec(execution_id=1, ticket_id=None), _rec(execution_id=2, ticket_id=5)]
    out = rework_index(recs)
    assert out["orphan_runs"] == 1
    assert out["pairs_total"] == 1


def test_rework_top_es_determinista():
    recs = ([_rec(execution_id=i, ticket_id=1, started_at=_T0 + timedelta(minutes=i))
             for i in range(4)]
            + [_rec(execution_id=100 + i, ticket_id=2,
                    started_at=_T0 + timedelta(minutes=i)) for i in range(4)])
    a = rework_index(recs)["top_rework"]
    b = rework_index(list(reversed(recs)))["top_rework"]
    assert a == b
    assert [x["ticket_id"] for x in a] == [1, 2]     # empate de runs -> ticket_id asc


# ── stats_payload ───────────────────────────────────────────────────────────

def test_stats_payload_es_json_serializable():
    recs = [_rec(execution_id=i, row=_row(cost_usd=0.01 * i), duration_s=float(i))
            for i in range(1, 6)]
    payload = stats_payload(recs)
    json.dumps(payload)          # no debe lanzar
    assert payload["runs_total"] == 5
    assert set(payload["metrics"]) == set(_METRICS)
    assert set(payload["by_dimension"]) == set(_DIMENSIONS)


def test_stats_payload_vacio_no_rompe():
    payload = stats_payload([])
    json.dumps(payload)
    assert payload["runs_total"] == 0
    for m in _METRICS:
        assert payload["metrics"][m]["overall"]["n"] == 0
        assert payload["metrics"][m]["histogram"] == []
        assert payload["metrics"][m]["outliers_tukey"]["applicable"] is False


def test_cost_stats_es_puro_sin_db():
    """El modulo no importa db ni models (verificado por AST)."""
    src = (BACKEND_ROOT / "services" / "cost_stats.py").read_text(encoding="utf-8")
    arbol = ast.parse(src)
    modulos = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            modulos.update(a.name.split(".")[0] for a in nodo.names)
        elif isinstance(nodo, ast.ImportFrom) and nodo.module:
            modulos.add(nodo.module.split(".")[0])
    assert "db" not in modulos and "models" not in modulos
    assert not (modulos & {"numpy", "sklearn", "scipy", "pandas"})


def test_percentil_de_costo_difiere_del_operativo_a_proposito():
    """C3 — dos definiciones legitimas conviviendo, fijadas por test.

    cost_stats.percentile  = interpolacion lineal, q en 0..100 (costo)
    run_signals.percentile_nearest_rank = nearest-rank, q en 0..1 (alertas)

    OJO — la divergencia NO es solo de metodo, es tambien de UNIDAD: el del 171
    hace `rank = ceil(q * n)`, asi que espera una FRACCION. Pasarle 50 devuelve
    el maximo en silencio (ceil(50*4)=200 -> clamp al ultimo indice). Por eso
    esta PROHIBIDO que una llame a la otra: ademas de dar numeros distintos, se
    llaman distinto.
    """
    from services.run_signals import percentile_nearest_rank

    datos = [1.0, 2.0, 3.0, 4.0]
    assert percentile(datos, 50) == 2.5                    # 242: q en 0..100
    assert percentile_nearest_rank(datos, 0.5) == 2.0      # 171: q en 0..1
    # La trampa, fijada para que nadie "unifique" las firmas sin darse cuenta:
    assert percentile_nearest_rank(datos, 50) == 4.0       # devuelve el MAXIMO
