"""Plan 242 F0 — Senales enriquecidas, PURAS (sin DB, sin red, sin LLM).

Regla de oro heredada del Plan 142: dato ausente -> None, JAMAS 0 inventado.
Este modulo NO importa cost_analytics (evita ciclo de imports): la direccion
es cost_analytics -> cost_signals, nunca al reves.

Convivencia con el Plan 171 (services/run_signals.py), declarada a proposito:
`run_signals.from_exec_record` calcula `duration_seconds` SOLO si el run
completo (los errores fallan rapido y falsearian la latencia "sana"), mientras
que `duration_seconds` de aca la calcula para cualquier estado terminal porque
un run que exploto igual costo dinero. Los nombres son deliberadamente
distintos (`duration_seconds` vs `ExecRecord.duration_s`) para que nadie los
tome por intercambiables. PROHIBIDO hacer que uno llame al otro.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

# Vocabulario cerrado de esfuerzo declarado por los runtimes.
_EFFORT_VALUES: frozenset[str] = frozenset({"low", "medium", "high", "max"})


@dataclass
class SignalRow:
    cache_creation_tokens: int | None = None  # tokens escritos al cache (costo extra)
    turns: int | None = None                  # num_turns / turns reportado por el runtime
    tool_calls: int | None = None             # cantidad de invocaciones de herramientas
    retries: int | None = None                # reintentos de autocorreccion del contrato
    effort: str | None = None                 # low|medium|high|max o None


def _first_int(*vals) -> int | None:
    """Primer valor convertible a int; None si ninguno lo es. (Copia local
    deliberada de cost_analytics._first_int: mantiene cost_signals sin imports.)"""
    for v in vals:
        if v is None:
            continue
        try:
            return int(v)
        except (TypeError, ValueError):
            continue
    return None


def _as_dict(value) -> dict:
    """dict o {} — un escalar donde se esperaba un objeto no debe romper nada."""
    return value if isinstance(value, dict) else {}


def extract_signal_row(md: dict | None) -> SignalRow:
    """Extrae de metadata_dict las senales derivables SOLO de metadata."""
    md = md if isinstance(md, dict) else {}
    ht = _as_dict(md.get("harness_telemetry"))
    raw = _as_dict(ht.get("raw"))
    ct = _as_dict(md.get("claude_telemetry"))
    ct_usage = _as_dict(ct.get("usage"))

    cache_creation = _first_int(
        ht.get("cache_creation_tokens"),
        ct_usage.get("cache_creation_input_tokens"),
        raw.get("cache_creation_input_tokens"),
    )
    turns = _first_int(ht.get("num_turns"), ht.get("turns"), raw.get("num_turns"),
                       md.get("turns"))
    tool_calls = _first_int(ht.get("tool_calls"), raw.get("tool_calls"), md.get("tool_calls"))
    retries = _first_int(md.get("autocorrect_retries"), md.get("retries"), ht.get("retries"))

    effort_raw = md.get("effort") or md.get("reasoning_effort") or raw.get("effort")
    effort = None
    if isinstance(effort_raw, str) and effort_raw.strip().lower() in _EFFORT_VALUES:
        effort = effort_raw.strip().lower()

    return SignalRow(cache_creation_tokens=cache_creation, turns=turns,
                     tool_calls=tool_calls, retries=retries, effort=effort)


def duration_seconds(started_at: datetime | None,
                     completed_at: datetime | None) -> float | None:
    """Duracion en segundos. None si falta un extremo o si el delta es negativo
    (reloj corrido / fila corrupta): NUNCA devolver un negativo ni un 0 inventado."""
    if started_at is None or completed_at is None:
        return None
    try:
        delta = (completed_at - started_at).total_seconds()
    except (TypeError, AttributeError):
        return None
    if delta < 0:
        return None
    return round(delta, 3)


def output_chars(output: str | None) -> int | None:
    """Tamano de la salida en caracteres. None si no hay salida; 0 es un valor
    legitimo si el output es la cadena vacia (distinto de 'no hay dato')."""
    if output is None:
        return None
    return len(output)
