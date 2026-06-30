"""Plan 44 — Observatorio de Grounding de Épicas (núcleo puro, sin I/O).

Agrega la telemetría `epic_summary` que 42/43 ya producen y persisten por-run,
y sugiere pasivamente entradas para el `process_catalog`. Todo es solo-lectura y
agnóstico de runtime: el caller (endpoints en api/agents.py) provee los datos.

`cited_modules` (construido por build_epic_summary, tickets.py) tiene la forma
`["módulo Login", "proceso CargaNomina", ...]` — con prefijo "módulo"/"proceso".
Por eso `_is_process` clasifica por ese prefijo.
"""
from __future__ import annotations

from collections import Counter

_MAX_TOP = 10
_MAX_TREND = 20


def _is_process(citation: str) -> bool:
    """True si la cita es un proceso (empieza con 'proceso', case-insensitive).

    `cited_modules` viene con prefijo (ver build_epic_summary). Si en el futuro
    el formato cambiara a nombres crudos sin prefijo, esta función devolvería
    False para todo y `top_cited_processes` quedaría vacío (degradación segura).
    """
    return (citation or "").strip().lower().startswith("proceso")


def _normalize_process_name(citation: str) -> str:
    """Quita el prefijo 'proceso' para comparar/sugerir nombres limpios."""
    s = (citation or "").strip()
    if s.lower().startswith("proceso"):
        s = s[len("proceso"):].strip()
    return s


def aggregate_grounding(
    summaries: list[dict],
    runtimes: list[str] | None = None,
) -> dict:
    """Agrega una lista cronológica de `epic_summary` dicts en métricas.

    Ver el contrato de claves en el plan 44 F1. Función pura.
    """
    total = len(summaries)
    with_warnings = sum(1 for s in summaries if s.get("warnings"))
    confidences = [
        s["confidence"]
        for s in summaries
        if isinstance(s.get("confidence"), (int, float))
    ]
    avg_conf = (sum(confidences) / len(confidences)) if confidences else None

    mod_counter: Counter = Counter()
    proc_counter: Counter = Counter()
    for s in summaries:
        for c in (s.get("cited_modules") or []):
            name = (c or "").strip()
            if not name:
                continue
            (proc_counter if _is_process(name) else mod_counter)[name] += 1

    def _top(counter: Counter) -> list[dict]:
        return [{"name": n, "count": cnt} for n, cnt in counter.most_common(_MAX_TOP)]

    trend = [s.get("confidence") for s in summaries][-_MAX_TREND:]

    rt_seen: set[str] = set()
    if runtimes:
        for rt in runtimes:
            if rt:
                rt_seen.add(rt)
    runtime_coverage = sorted(rt_seen)

    return {
        "total_epics": total,
        "epics_with_warnings": with_warnings,
        "grounding_warning_rate": (with_warnings / total) if total else 0.0,
        "avg_confidence": avg_conf,
        "top_cited_modules": _top(mod_counter),
        "top_cited_processes": _top(proc_counter),
        "confidence_trend": trend,
        "runtime_coverage": runtime_coverage,
    }


def suggest_process_catalog_entries(
    summaries: list[dict],
    existing_catalog: list[dict] | None,
) -> list[dict]:
    """Plan 44 F3 — Procesos citados en épicas que NO están en el catálogo.

    Nunca inventa: todo nombre proviene de un `cited_modules` real de una épica
    publicada. Comparación case-insensitive por nombre normalizado. Devuelve
    `[{"name": str, "occurrences": int}, ...]` ordenado por occurrences desc.
    """
    existing = {
        _normalize_process_name(e.get("name", "")).lower()
        for e in (existing_catalog or [])
        if e.get("name")
    }
    counter: Counter = Counter()
    for s in summaries:
        for c in (s.get("cited_modules") or []):
            if not _is_process(c):
                continue
            name = _normalize_process_name(c)
            if not name or name.lower() in existing:
                continue
            counter[name] += 1
    return [
        {"name": n, "occurrences": cnt} for n, cnt in counter.most_common(_MAX_TOP)
    ]
