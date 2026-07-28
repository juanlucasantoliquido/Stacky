"""Plan 242 F0 — Senales enriquecidas sobre ExecRecord (aditivo, read-only).

Cubre los 18 casos de F0.5 del plan. Todo es PURO: sin DB, sin red, sin LLM.

Regla de oro heredada del Plan 142: dato ausente -> None, JAMAS 0 inventado.
"""
import ast
import dataclasses
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from services.cost_analytics import CostRow, ExecRecord
from services.cost_signals import (
    SignalRow,
    duration_seconds,
    extract_signal_row,
    output_chars,
)

BACKEND_ROOT = Path(__file__).resolve().parent.parent


def _row(**kw) -> CostRow:
    base = dict(runtime="codex_cli", model="gpt-5", tokens_in=100, tokens_out=50,
                cache_read_tokens=None, cost_usd=0.01, cost_kind="reported",
                cache_savings_usd=None)
    base.update(kw)
    return CostRow(**base)


# ── extract_signal_row: ausencia de dato ────────────────────────────────────

def test_metadata_none_devuelve_todo_none():
    s = extract_signal_row(None)
    assert s == SignalRow()
    assert (s.cache_creation_tokens, s.turns, s.tool_calls, s.retries, s.effort) == (
        None, None, None, None, None)


def test_metadata_vacia_devuelve_todo_none():
    assert extract_signal_row({}) == SignalRow()


def test_harness_telemetry_no_dict_no_crashea():
    # Un valor escalar donde se esperaba un dict no debe romper la extraccion.
    assert extract_signal_row({"harness_telemetry": "x"}) == SignalRow()
    assert extract_signal_row({"claude_telemetry": 7}) == SignalRow()
    assert extract_signal_row({"harness_telemetry": {"raw": "no-dict"}}) == SignalRow()


# ── extract_signal_row: fuentes de cache de escritura ───────────────────────

def test_cache_creation_desde_harness_telemetry():
    md = {"harness_telemetry": {"cache_creation_tokens": 4096}}
    assert extract_signal_row(md).cache_creation_tokens == 4096


def test_cache_creation_desde_claude_usage_legacy():
    md = {"claude_telemetry": {"usage": {"cache_creation_input_tokens": 777}}}
    assert extract_signal_row(md).cache_creation_tokens == 777


def test_string_numerico_se_convierte_a_int():
    md = {"harness_telemetry": {"cache_creation_tokens": "1234"}}
    v = extract_signal_row(md).cache_creation_tokens
    assert v == 1234 and isinstance(v, int)


def test_string_no_numerico_devuelve_none_no_cero():
    md = {"harness_telemetry": {"cache_creation_tokens": "abc"}}
    assert extract_signal_row(md).cache_creation_tokens is None


# ── extract_signal_row: esfuerzo (vocabulario cerrado) ──────────────────────

def test_effort_normaliza_mayusculas():
    assert extract_signal_row({"effort": "HIGH"}).effort == "high"
    assert extract_signal_row({"reasoning_effort": "  Medium "}).effort == "medium"


def test_effort_fuera_de_vocabulario_es_none():
    assert extract_signal_row({"effort": "turbo"}).effort is None
    assert extract_signal_row({"effort": 3}).effort is None


def test_turns_precedencia_num_turns_sobre_turns():
    md = {"harness_telemetry": {"num_turns": 9, "turns": 2}}
    assert extract_signal_row(md).turns == 9


# ── duration_seconds ────────────────────────────────────────────────────────

def test_duracion_none_si_falta_un_extremo():
    dt = datetime(2026, 7, 1, 10, 0, 0)
    assert duration_seconds(None, dt) is None
    assert duration_seconds(dt, None) is None
    assert duration_seconds(None, None) is None


def test_duracion_negativa_devuelve_none():
    ini = datetime(2026, 7, 1, 10, 0, 0)
    fin = ini - timedelta(seconds=5)      # reloj corrido / fila corrupta
    assert duration_seconds(ini, fin) is None


def test_duracion_redondea_a_3_decimales():
    ini = datetime(2026, 7, 1, 10, 0, 0)
    fin = ini + timedelta(seconds=12, microseconds=345600)   # 12.3456 s
    assert duration_seconds(ini, fin) == 12.346


# ── output_chars ────────────────────────────────────────────────────────────

def test_output_chars_none_vs_cadena_vacia():
    assert output_chars(None) is None      # "no hay dato"
    assert output_chars("") == 0           # dato legitimo: salida vacia
    assert output_chars("hola") == 4


# ── ExecRecord: aditividad 100% retrocompatible ─────────────────────────────

def test_execrecord_se_construye_sin_los_campos_nuevos():
    """La firma del Plan 142 sigue funcionando; los 7 campos nuevos quedan None."""
    r = ExecRecord(execution_id=1, ticket_id=None, ado_id=None, project=None,
                   agent_type="developer", status="completed",
                   started_at=datetime(2026, 7, 1), row=_row())
    assert r.signals is None
    assert r.duration_s is None
    assert r.verdict is None
    assert r.completion_source is None
    assert r.output_chars is None
    assert r.work_item_type is None
    assert r.priority is None


def test_execrecord_no_declara_completed_at_dos_veces():
    """C2 — el diff de v1 duplicaba `completed_at` (ya lo puso el Plan 171)."""
    nombres = [f.name for f in dataclasses.fields(ExecRecord)]
    assert nombres.count("completed_at") == 1
    # y ningun campo nuevo pisa uno existente
    assert len(nombres) == len(set(nombres))


# ── Anti-ciclo de imports ───────────────────────────────────────────────────

def test_cost_signals_no_importa_cost_analytics():
    """F0.1 — la direccion es cost_analytics -> cost_signals, nunca al reves."""
    src = (BACKEND_ROOT / "services" / "cost_signals.py").read_text(encoding="utf-8")
    arbol = ast.parse(src)
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            for a in nodo.names:
                assert "cost_analytics" not in a.name
        elif isinstance(nodo, ast.ImportFrom):
            assert "cost_analytics" not in (nodo.module or "")


# ── Convivencia declarada con el Plan 171 (C3) ──────────────────────────────

def test_duracion_de_costo_difiere_de_la_operativa_en_runs_fallidos():
    """C3 — divergencia A PROPOSITO, fijada por test para que nadie la 'arregle'.

    run_signals (171, salud operativa) mide latencia SOLO de runs completados.
    cost_signals (242, insumo de costo) mide cualquier estado terminal: un run
    que explota igual costo dinero.
    """
    from services import run_signals as rs

    ini = datetime(2026, 7, 1, 10, 0, 0)
    fin = ini + timedelta(seconds=30)
    r = ExecRecord(execution_id=7, ticket_id=1, ado_id=None, project="P",
                   agent_type="developer", status="error",
                   started_at=ini, row=_row(), completed_at=fin,
                   duration_s=duration_seconds(ini, fin))

    assert r.duration_s == 30.0                          # 242: si mide
    assert rs.from_exec_record(r).duration_seconds is None  # 171: no mide
