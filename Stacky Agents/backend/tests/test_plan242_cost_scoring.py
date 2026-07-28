"""Plan 242 F2 — Scoring de eficiencia economica: determinista y explicable.

Cubre los 34 casos de F2.8.
KPI-2: toda puntuacion trae razones EN ESPANOL con su numero.
KPI-3: mismo input -> mismo output byte a byte, 50 corridas.
"""
import ast
import json
import math
import random
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from services.cost_analytics import CostRow, ExecRecord
from services.cost_scoring import (
    _GRADE_CUTS,
    _WEIGHTS,
    CohortStats,
    build_cohorts,
    model_family,
    percent_rank,
    score_execution,
    score_payload,
    score_ticket,
)

BACKEND_ROOT = Path(__file__).resolve().parent.parent
_T0 = datetime(2026, 7, 1, 10, 0, 0)


def _row(**kw) -> CostRow:
    base = dict(runtime="codex_cli", model="gpt-5", tokens_in=1000, tokens_out=1000,
                cache_read_tokens=None, cost_usd=0.05, cost_kind="reported",
                cache_savings_usd=None)
    base.update(kw)
    return CostRow(**base)


def _rec(execution_id=1, ticket_id=1, agent_type="developer", status="completed",
         started_at=None, row=None, verdict=None, **kw) -> ExecRecord:
    return ExecRecord(execution_id=execution_id, ticket_id=ticket_id, ado_id=None,
                      project="P", agent_type=agent_type, status=status,
                      started_at=started_at or _T0, row=row or _row(),
                      verdict=verdict, **kw)


def _cohorte(key="developer|gpt-5", n=10, costos=None, median_unit=0.05) -> dict:
    costos = costos if costos is not None else [0.01 * i for i in range(1, n + 1)]
    return {key: CohortStats(key=key, n=n, costs_sorted=sorted(costos),
                             median_unit_cost=median_unit)}


def _comp(rec, cohorts=None, prev_runs=0):
    return score_execution(rec, cohorts if cohorts is not None else {},
                           prev_runs=prev_runs).components


# ── pesos y percent_rank ────────────────────────────────────────────────────

def test_pesos_suman_exactamente_uno():
    assert math.isclose(sum(_WEIGHTS.values()), 1.0, rel_tol=1e-9)


def test_percent_rank_midrank_todos_iguales_da_medio():
    assert percent_rank([0.05] * 10, 0.05) == 0.5     # neutro, NO 100 de falso merito


def test_percent_rank_minimo_y_maximo():
    v = [1.0, 2.0, 3.0, 4.0]
    assert percent_rank(v, 1.0) == 0.125              # 0.5/4
    assert percent_rank(v, 4.0) == 0.875              # (3 + 0.5)/4


def test_percent_rank_lista_vacia_es_none():
    assert percent_rank([], 1.0) is None


# ── (1) cost_position ───────────────────────────────────────────────────────

def test_cost_position_mas_barato_da_100():
    coh = _cohorte(n=20, costos=[float(i) for i in range(1, 21)])
    # x=0 es mas barato que todos -> pr=0 -> componente 100
    c = _comp(_rec(row=_row(cost_usd=0.0)), coh)
    assert c["cost_position"] == 100.0


def test_cost_position_none_si_cohorte_menor_a_3():
    coh = _cohorte(n=2, costos=[0.01, 0.02])
    assert "cost_position" not in _comp(_rec(), coh)


def test_cost_position_none_para_nominal_copilot():
    """G7 — copilot es suscripcion plana: NO se puntua por precio."""
    coh = _cohorte(key="developer|(otro)", n=10)
    r = _rec(row=_row(runtime="github_copilot", model=None, cost_kind="nominal",
                      cost_usd=None))
    c = _comp(r, coh)
    assert "cost_position" not in c and "unit_cost" not in c


# ── (2) outcome ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("status,esperado", [
    ("completed", 100.0), ("error", 0.0), ("failed", 0.0),
    ("cancelled", 20.0), ("canceled", 20.0), ("timeout", 10.0),
    ("running", None), ("pending", None), ("queued", None),
    ("lo_que_sea", 50.0),
])
def test_outcome_tabla_cerrada_los_9_estados(status, esperado):
    c = _comp(_rec(status=status))
    assert c.get("outcome") == esperado


def test_outcome_verdict_fail_fuerza_maximo_30():
    c = _comp(_rec(status="completed", verdict="fail"))
    assert c["outcome"] == 30.0
    assert _comp(_rec(status="completed", verdict="pass"))["outcome"] == 100.0
    assert _comp(_rec(status="error", verdict="fail"))["outcome"] == 0.0   # min(0,30)


def test_outcome_running_es_none():
    assert "outcome" not in _comp(_rec(status="running"))


# ── (3) cache ───────────────────────────────────────────────────────────────

def test_cache_ratio_50pct_da_100():
    c = _comp(_rec(row=_row(cache_read_tokens=1000, tokens_in=1000)))
    assert c["cache"] == 100.0


def test_cache_denominador_cero_es_none():
    assert "cache" not in _comp(_rec(row=_row(cache_read_tokens=0, tokens_in=0)))
    assert "cache" not in _comp(_rec(row=_row(cache_read_tokens=None, tokens_in=100)))


def test_cache_ratio_25pct_da_50():
    c = _comp(_rec(row=_row(cache_read_tokens=250, tokens_in=750)))
    assert c["cache"] == 50.0


# ── (4) unit_cost ───────────────────────────────────────────────────────────

def test_unit_cost_igual_a_mediana_da_100():
    coh = _cohorte(median_unit=0.05)
    c = _comp(_rec(row=_row(cost_usd=0.05, tokens_out=1000)), coh)
    assert c["unit_cost"] == 100.0


def test_unit_cost_doble_de_mediana_da_50():
    coh = _cohorte(median_unit=0.05)
    c = _comp(_rec(row=_row(cost_usd=0.10, tokens_out=1000)), coh)
    assert c["unit_cost"] == 50.0


def test_unit_cost_tokens_out_cero_es_none():
    coh = _cohorte(median_unit=0.05)
    assert "unit_cost" not in _comp(_rec(row=_row(cost_usd=0.5, tokens_out=0)), coh)


# ── (5) rework ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("prev,esperado", [(0, 100.0), (1, 60.0), (2, 30.0), (3, 0.0), (7, 0.0)])
def test_rework_tabla_cerrada_0_1_2_3(prev, esperado):
    assert _comp(_rec(), prev_runs=prev)["rework"] == esperado


def test_rework_none_si_no_hay_ticket():
    assert "rework" not in _comp(_rec(ticket_id=None))


# ── renormalizacion, grade, clamp ───────────────────────────────────────────

def test_renormalizacion_pesos_suman_uno_cuando_faltan_componentes():
    """Caso borde 2 — copilot: solo outcome+cache+rework, renormalizados."""
    r = _rec(row=_row(runtime="github_copilot", model=None, cost_kind="nominal",
                      cost_usd=None, cache_read_tokens=500, tokens_in=500))
    s = score_execution(r, {}, prev_runs=0)
    assert set(s.components) == {"outcome", "cache", "rework"}
    assert math.isclose(sum(s.weights_used.values()), 1.0, rel_tol=1e-9)
    assert math.isclose(s.weights_used["outcome"], 0.50, rel_tol=1e-9)
    assert math.isclose(s.weights_used["cache"], 0.30, rel_tol=1e-9)
    assert math.isclose(s.weights_used["rework"], 0.20, rel_tol=1e-9)


def test_sin_componentes_score_none_y_grade_nd():
    r = _rec(ticket_id=None, status="running",
             row=_row(cost_usd=None, tokens_in=None, tokens_out=None,
                      cache_read_tokens=None, cost_kind="unknown"))
    s = score_execution(r, {})
    assert s.score is None and s.grade == "N/D"
    assert s.reasons and any(ch.isalpha() for ch in s.reasons[0])


@pytest.mark.parametrize("score,grade", [
    (100.0, "A"), (85.0, "A"), (84.99, "B"), (70.0, "B"), (69.99, "C"),
    (55.0, "C"), (54.99, "D"), (40.0, "D"), (39.99, "E"), (0.0, "E"),
])
def test_grade_bordes_exactos(score, grade):
    from services.cost_scoring import grade_for
    assert grade_for(score) == grade


def test_score_clampeado_a_0_100():
    for r in (_rec(status="completed"), _rec(status="error"), _rec(status="timeout")):
        s = score_execution(r, _cohorte())
        assert s.score is None or 0.0 <= s.score <= 100.0


def test_grade_cuts_estan_ordenados_descendente():
    umbrales = [u for u, _ in _GRADE_CUTS]
    assert umbrales == sorted(umbrales, reverse=True)


# ── razones (KPI-2) ─────────────────────────────────────────────────────────

def test_toda_puntuacion_trae_razones_con_numeros():
    """KPI-2 — reasons no vacio y >=1 razon con un digito que la justifica."""
    coh = _cohorte(n=20, costos=[0.01 * i for i in range(1, 21)])
    recs = [_rec(execution_id=i, row=_row(cost_usd=0.01 * i, cache_read_tokens=100,
                                          tokens_in=900), status="completed")
            for i in range(1, 6)]
    for r in recs:
        s = score_execution(r, coh)
        assert s.reasons, "sin razones"
        assert any(any(ch.isdigit() for ch in razon) for razon in s.reasons)


def test_razon_especial_copilot_menciona_suscripcion_plana():
    r = _rec(row=_row(runtime="github_copilot", model=None, cost_kind="nominal",
                      cost_usd=None))
    s = score_execution(r, {})
    assert any("suscripción plana" in x for x in s.reasons)


def test_razon_de_componente_no_evaluado_usa_motivo_de_tabla_cerrada():
    from services.cost_scoring import _MOTIVOS
    r = _rec(ticket_id=None, status="running",
             row=_row(cost_usd=None, tokens_out=None, cache_read_tokens=None))
    s = score_execution(r, {})
    citados = [x for x in s.reasons if "no evaluado" in x]
    assert citados
    for razon in citados:
        assert any(m in razon for m in _MOTIVOS.values()), razon


def test_confidence_alta_media_baja():
    coh_grande = _cohorte(n=25, costos=[0.01 * i for i in range(1, 26)])
    r_completo = _rec(row=_row(cache_read_tokens=500, tokens_in=500, tokens_out=1000))
    assert score_execution(r_completo, coh_grande).confidence == "alta"

    coh_media = _cohorte(n=6, costos=[0.01 * i for i in range(1, 7)])
    assert score_execution(r_completo, coh_media).confidence == "media"

    assert score_execution(_rec(status="running", ticket_id=None), {}).confidence == "baja"


def test_confidence_baja_agrega_su_razon():
    s = score_execution(_rec(), {})
    assert s.confidence == "baja"
    assert any("Confianza baja" in x for x in s.reasons)


# ── determinismo (KPI-3) ────────────────────────────────────────────────────

def _muestra(n=30):
    recs = []
    for i in range(1, n + 1):
        recs.append(_rec(execution_id=i, ticket_id=(i % 7) + 1,
                         agent_type=["developer", "qa", "technical"][i % 3],
                         status=["completed", "error", "cancelled"][i % 3],
                         started_at=_T0 + timedelta(minutes=i),
                         row=_row(cost_usd=0.01 * i, tokens_out=100 * i,
                                  cache_read_tokens=(i * 10) if i % 2 else None)))
    return recs


def test_scoring_es_determinista_50_corridas():
    """KPI-3 — mismo input, mismo output byte a byte."""
    recs = _muestra()
    primero = json.dumps(score_payload(recs), sort_keys=True)
    for _ in range(49):
        assert json.dumps(score_payload(recs), sort_keys=True) == primero


def test_scoring_no_depende_del_orden_de_entrada():
    recs = _muestra()
    barajado = list(recs)
    random.Random(1234).shuffle(barajado)
    assert (json.dumps(score_payload(recs), sort_keys=True)
            == json.dumps(score_payload(barajado), sort_keys=True))


# ── score_ticket ────────────────────────────────────────────────────────────

def test_score_ticket_penalidad_rework_tope_20():
    recs = [_rec(execution_id=i, ticket_id=1, started_at=_T0 + timedelta(minutes=i))
            for i in range(10)]
    t = score_ticket(recs, _cohorte())
    assert t.rework_penalty == 20.0      # min(20, 4*9)


def test_score_ticket_cohorte_entra_por_parametro():
    """C8 — el componente de mayor peso (0,35) no se puede anular solo."""
    coh = _cohorte(n=20, costos=[0.01 * i for i in range(1, 21)])
    recs = [_rec(execution_id=1, ticket_id=1, row=_row(cost_usd=0.01))]
    s = score_execution(recs[0], coh)
    assert "cost_position" in s.components     # con cohorte GLOBAL si se computa
    t = score_ticket(recs, coh)
    assert t.score is not None


def test_score_ticket_worst_execution_desempata_por_id():
    """Empate REAL de score -> gana el execution_id mas chico.

    Los dos runs usan agent_type distinto a proposito: si compartieran agente,
    el segundo cargaria la penalidad de rework y los scores NO empataria.
    Con `cohorts={}` ninguno computa cost_position/unit_cost, asi que ambos
    quedan con el mismo par outcome+rework.
    """
    recs = [_rec(execution_id=9, ticket_id=1, agent_type="qa", status="error",
                 started_at=_T0 + timedelta(minutes=1)),
            _rec(execution_id=3, ticket_id=1, agent_type="developer",
                 status="error", started_at=_T0)]
    a = score_execution(recs[0], {}, prev_runs=0).score
    b = score_execution(recs[1], {}, prev_runs=0).score
    assert a == b, "el test necesita un empate real para probar el desempate"
    t = score_ticket(recs, {})
    assert t.worst_execution_id == 3     # empate de score -> id mas chico


def test_score_ticket_billable_excluye_nominal():
    recs = [_rec(execution_id=1, ticket_id=1, row=_row(cost_usd=1.0)),
            _rec(execution_id=2, ticket_id=1, started_at=_T0 + timedelta(minutes=1),
                 row=_row(runtime="github_copilot", cost_kind="nominal", cost_usd=9.0))]
    t = score_ticket(recs, _cohorte())
    assert t.billable_usd == 1.0


def test_score_ticket_vacio_lanza():
    with pytest.raises(ValueError):
        score_ticket([], _cohorte())


# ── score_payload ───────────────────────────────────────────────────────────

def test_score_payload_ordena_peores_primero_y_none_al_final():
    recs = _muestra()
    p = score_payload(recs)
    scores = [e["score"] for e in p["executions"]]
    validos = [s for s in scores if s is not None]
    assert validos == sorted(validos)                       # peores (menor score) primero
    idx_none = [i for i, s in enumerate(scores) if s is None]
    if idx_none:
        assert min(idx_none) >= len(validos)                # los None, al FINAL


def test_score_payload_grade_distribution_suma_runs_total():
    recs = _muestra()
    p = score_payload(recs)
    assert sum(p["grade_distribution"].values()) == p["runs_total"] == len(recs)
    assert set(p["grade_distribution"]) == {"A", "B", "C", "D", "E", "N/D"}


def test_score_payload_vacio_no_rompe():
    p = score_payload([])
    assert p["runs_total"] == 0 and p["runs_scored"] == 0
    assert p["executions"] == [] and p["tickets"] == [] and p["cohorts"] == {}
    assert all(v == 0 for v in p["grade_distribution"].values())
    json.dumps(p)


def test_score_payload_cohorts_ordenadas_alfabeticamente():
    recs = _muestra()
    claves = list(score_payload(recs)["cohorts"].keys())
    assert claves == sorted(claves)


def test_score_payload_top_n_recorta():
    recs = _muestra(30)
    assert len(score_payload(recs, top_n=5)["executions"]) == 5


# ── model_family / build_cohorts ────────────────────────────────────────────

def test_model_family_sin_modelo_y_desconocido():
    assert model_family(None) == "(sin modelo)"
    assert model_family("modelo-que-no-existe-jamas") == "(otro)"


def test_build_cohorts_agrupa_por_agente_y_familia():
    recs = [_rec(execution_id=1, agent_type="developer", row=_row(cost_usd=0.01)),
            _rec(execution_id=2, agent_type="developer", row=_row(cost_usd=0.03)),
            _rec(execution_id=3, agent_type="qa", row=_row(cost_usd=0.02))]
    coh = build_cohorts(recs)
    assert len(coh) == 2
    for c in coh.values():
        assert c.costs_sorted == sorted(c.costs_sorted)


def test_build_cohorts_excluye_nominal_de_los_costos():
    """G7 — un costo que nadie paga no puede ser la referencia de 'caro'."""
    recs = [_rec(execution_id=1, row=_row(cost_usd=0.01)),
            _rec(execution_id=2, row=_row(runtime="github_copilot",
                                          cost_kind="nominal", cost_usd=99.0))]
    coh = build_cohorts(recs)
    todos = [c for cs in coh.values() for c in cs.costs_sorted]
    assert 99.0 not in todos


# ── pureza (G3 / G5) ────────────────────────────────────────────────────────

def _imports_de(nombre: str) -> set[str]:
    src = (BACKEND_ROOT / "services" / nombre).read_text(encoding="utf-8")
    arbol = ast.parse(src)
    out = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            out.update(a.name.split(".")[0] for a in nodo.names)
        elif isinstance(nodo, ast.ImportFrom) and nodo.module:
            out.add(nodo.module.split(".")[0])
    return out


def test_cost_scoring_no_invoca_llm_ni_red():
    """G3 — sin requests, sin socket, sin subprocess, sin urllib."""
    assert not (_imports_de("cost_scoring.py")
                & {"requests", "socket", "subprocess", "urllib", "http"})


def test_cost_scoring_no_usa_random():
    """G5 — determinismo: nada de azar."""
    assert "random" not in _imports_de("cost_scoring.py")
    assert not (_imports_de("cost_scoring.py") & {"numpy", "sklearn", "scipy", "pandas"})
