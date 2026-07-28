"""Plan 242 KPI-10 — paridad de los 3 runtimes.

codex_cli, claude_code_cli y github_copilot producen los tres un payload
completo. Copilot queda etiquetado "nominal" (suscripcion plana) y NUNCA entra
en agregados facturables (G7).

Alcance recortado (§0.3): F0 (senales), F1 (estadistica) y F2 (scoring). El
entrenamiento y el forecast son del plan siguiente.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from services.cost_analytics import ExecRecord, extract_cost_row
from services.cost_signals import duration_seconds, extract_signal_row, output_chars
from services.cost_scoring import build_cohorts, score_execution, score_payload
from services.cost_stats import by_dimension, stats_payload

_T0 = datetime(2026, 7, 1, 10, 0, 0)

# Metadata REALISTA por runtime, con la forma que cada uno persiste de verdad.
_METADATA = {
    "codex_cli": {
        "runtime": "codex_cli", "model": "gpt-5",
        "harness_telemetry": {"total_cost_usd": 0.42, "cost_estimated": False,
                              "input_tokens": 4000, "output_tokens": 900,
                              "cache_read_tokens": 1200, "cache_creation_tokens": 300,
                              "num_turns": 6, "tool_calls": 11},
    },
    "claude_code_cli": {
        "runtime": "claude_code_cli", "model": "claude-sonnet-5",
        "claude_telemetry": {"total_cost_usd": 0.31,
                             "usage": {"input_tokens": 3000, "output_tokens": 700,
                                       "cache_read_input_tokens": 900,
                                       "cache_creation_input_tokens": 250}},
    },
    "github_copilot": {
        "runtime": "github_copilot", "model": "claude-sonnet-5",
        "harness_telemetry": {"input_tokens": 2000, "output_tokens": 500},
    },
}
_RUNTIMES = tuple(_METADATA)


def _rec(runtime: str, execution_id: int = 1, ticket_id: int = 1,
         status: str = "completed") -> ExecRecord:
    md = _METADATA[runtime]
    fin = _T0 + timedelta(seconds=42)
    return ExecRecord(
        execution_id=execution_id, ticket_id=ticket_id, ado_id=1000 + execution_id,
        project="paridad", agent_type="developer", status=status,
        started_at=_T0, row=extract_cost_row(md), raw_metadata=md, completed_at=fin,
        signals=extract_signal_row(md),
        duration_s=duration_seconds(_T0, fin),
        verdict="pass", completion_source="agent_gateway",
        output_chars=output_chars("salida de prueba"),
        work_item_type="Task", priority=2)


def _los_tres() -> list[ExecRecord]:
    return [_rec(rt, execution_id=i + 1, ticket_id=i + 1)
            for i, rt in enumerate(_RUNTIMES)]


# ── F0 ──────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("runtime", _RUNTIMES)
def test_los_3_runtimes_producen_signal_row(runtime):
    s = extract_signal_row(_METADATA[runtime])
    assert s is not None
    # Lo que NO viene queda en None, JAMAS en 0 (G4).
    for campo in ("cache_creation_tokens", "turns", "tool_calls", "retries"):
        v = getattr(s, campo)
        assert v is None or isinstance(v, int)


def test_codex_llena_turnos_y_herramientas():
    s = extract_signal_row(_METADATA["codex_cli"])
    assert s.turns == 6 and s.tool_calls == 11 and s.cache_creation_tokens == 300


def test_claude_llena_cache_desde_usage_legacy():
    s = extract_signal_row(_METADATA["claude_code_cli"])
    assert s.cache_creation_tokens == 250


def test_copilot_deja_las_senales_en_none_no_en_cero():
    """G4 — la ausencia se declara, no se rellena con ceros."""
    s = extract_signal_row(_METADATA["github_copilot"])
    assert s.cache_creation_tokens is None
    assert s.turns is None and s.tool_calls is None and s.retries is None


@pytest.mark.parametrize("runtime", _RUNTIMES)
def test_los_3_runtimes_tienen_duracion_y_tamano_de_salida(runtime):
    r = _rec(runtime)
    assert r.duration_s == 42.0
    assert r.output_chars == len("salida de prueba")


# ── F1 ──────────────────────────────────────────────────────────────────────

def test_los_3_runtimes_aparecen_en_stats():
    recs = _los_tres()
    dist = by_dimension(recs, "runtime", "cost_usd")
    assert set(dist) == set(_RUNTIMES)
    assert len(dist) == 3


def test_copilot_va_a_nominal_only_y_no_a_billable_only():
    """G7 / KPI-10 — el separador es cost_kind, y copilot es SIEMPRE nominal."""
    recs = _los_tres()
    billable = [r for r in recs if r.row.cost_kind in ("reported", "estimated")]
    nominal = [r for r in recs if r.row.cost_kind == "nominal"]

    assert {r.row.runtime for r in nominal} == {"github_copilot"}
    assert "github_copilot" not in {r.row.runtime for r in billable}

    pb = stats_payload(billable)
    pn = stats_payload(nominal)
    assert "github_copilot" not in pb["by_dimension"]["runtime"]
    assert "github_copilot" in pn["by_dimension"]["runtime"]
    assert pb["runs_total"] == 2 and pn["runs_total"] == 1


def test_stats_payload_de_los_3_es_json_serializable():
    import json
    json.dumps(stats_payload(_los_tres()))


# ── F2 ──────────────────────────────────────────────────────────────────────

def test_los_3_runtimes_reciben_score():
    recs = _los_tres()
    coh = build_cohorts(recs)
    for r in recs:
        s = score_execution(r, coh)
        assert s.reasons, r.row.runtime
        assert s.grade in ("A", "B", "C", "D", "E", "N/D")


def test_copilot_score_excluye_componentes_de_precio():
    """G7 — a copilot no se lo puntua por precio: se renormaliza sobre el resto."""
    recs = _los_tres()
    coh = build_cohorts(recs)
    s = score_execution(_rec("github_copilot"), coh)
    assert "cost_position" not in s.components
    assert "unit_cost" not in s.components
    assert s.components, "igual tiene que puntuar por resultado/cache/rework"
    assert any("suscripción plana" in x for x in s.reasons)


def test_copilot_no_contamina_las_cohortes_de_precio():
    """Su costo nominal no puede ser la referencia de 'caro' para nadie."""
    recs = _los_tres()
    coh = build_cohorts(recs)
    copilot_cost = _rec("github_copilot").row.cost_usd
    if copilot_cost is not None:
        for c in coh.values():
            assert copilot_cost not in c.costs_sorted


def test_score_payload_de_los_3_cuenta_bien():
    p = score_payload(_los_tres())
    assert p["runs_total"] == 3
    assert sum(p["grade_distribution"].values()) == 3


def test_fallback_declarado_por_runtime_sin_telemetria():
    """Un runtime SIN harness_telemetry degrada explicitamente: senales en None
    y componentes ausentes. NUNCA ceros inventados."""
    md = {"runtime": "runtime_desconocido", "model": None}
    r = ExecRecord(execution_id=99, ticket_id=None, ado_id=None, project=None,
                   agent_type="developer", status="running", started_at=_T0,
                   row=extract_cost_row(md), signals=extract_signal_row(md))
    assert r.signals.cache_creation_tokens is None
    assert r.duration_s is None
    s = score_execution(r, {})
    assert s.score is None and s.grade == "N/D"
    assert s.cost_usd is None            # no es 0.0
    assert s.reasons


def test_los_3_runtimes_conservan_su_cost_kind():
    kinds = {r.row.runtime: r.row.cost_kind for r in _los_tres()}
    assert kinds["github_copilot"] == "nominal"
    for rt in ("codex_cli", "claude_code_cli"):
        assert kinds[rt] in ("reported", "estimated"), rt
