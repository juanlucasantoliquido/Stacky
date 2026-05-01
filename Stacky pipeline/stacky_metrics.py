"""
stacky_metrics.py — Métricas de velocity del equipo para Stacky.

Agrega datos de pipeline/state.json de todos los proyectos y calcula:
  - Tickets procesados por semana/mes
  - Tiempo promedio por etapa (PM, Dev, QA)
  - Tasa de retrabajos (rework_rate)
  - Tickets por desarrollador (asignado)
  - Tendencias (mejorando/empeorando vs semana anterior)
  - Leaderboard de velocidad
"""

import json
import os
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path


BASE_DIR = Path(__file__).parent


def _load_all_states() -> list[dict]:
    """Carga state.json de todos los proyectos inicializados."""
    entries = []
    projects_dir = BASE_DIR / "projects"
    if not projects_dir.exists():
        return entries
    for proj_dir in projects_dir.iterdir():
        if not proj_dir.is_dir():
            continue
        state_file = proj_dir / "pipeline" / "state.json"
        if not state_file.exists():
            state_file = BASE_DIR / "pipeline" / "state.json"
        if state_file.exists():
            try:
                data = json.loads(state_file.read_text(encoding="utf-8"))
                project = proj_dir.name
                for tid, entry in data.get("tickets", {}).items():
                    entries.append({**entry, "_ticket_id": tid, "_project": project})
            except Exception:
                pass
    return entries


def _parse_dt(s: str) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return None


def _duration_seg(entry: dict, ini_key: str, fin_key: str) -> float | None:
    ini = _parse_dt(entry.get(ini_key))
    fin = _parse_dt(entry.get(fin_key))
    if ini and fin:
        d = (fin - ini).total_seconds()
        return d if d > 0 else None
    return None


def compute(days: int = 30) -> dict:
    """
    Calcula métricas de los últimos `days` días.
    Retorna un dict con todas las métricas.
    """
    entries  = _load_all_states()
    cutoff   = datetime.now() - timedelta(days=days)
    cutoff_7 = datetime.now() - timedelta(days=7)

    # Filtrar por ventana temporal (usar completado_at o pm_completado_at)
    recent = []
    for e in entries:
        ts_str = (e.get("completado_at") or e.get("tester_completado_at") or
                  e.get("pm_completado_at"))
        ts = _parse_dt(ts_str)
        if ts and ts >= cutoff:
            recent.append({**e, "_ts": ts})

    # ── Totales ───────────────────────────────────────────────────────────────
    total          = len(recent)
    completados    = sum(1 for e in recent if e.get("estado") == "completado")
    con_error      = sum(1 for e in recent if "error" in e.get("estado", ""))
    con_rework     = sum(1 for e in recent if e.get("intentos_dev", 0) > 1
                         or e.get("intentos_tester", 0) > 1)
    rework_rate    = round(con_rework / total * 100, 1) if total else 0

    # ── Por semana (últimas 8 semanas) ────────────────────────────────────────
    by_week: dict[str, int] = defaultdict(int)
    for e in recent:
        week = e["_ts"].strftime("%Y-W%W")
        by_week[week] += 1

    # ── Duración promedio por etapa ────────────────────────────────────────────
    def _avg_dur(key_ini, key_fin):
        durs = [d for e in recent if (d := _duration_seg(e, key_ini, key_fin)) is not None]
        return round(sum(durs) / len(durs) / 60, 1) if durs else None  # en minutos

    dur_pm     = _avg_dur("pm_inicio_at",     "pm_fin_at")
    dur_dev    = _avg_dur("dev_inicio_at",    "dev_fin_at")
    dur_tester = _avg_dur("tester_inicio_at", "tester_fin_at")

    # Tiempo total (pm_inicio → completado_at)
    total_durs = []
    for e in recent:
        ini = _parse_dt(e.get("pm_inicio_at"))
        fin = _parse_dt(e.get("completado_at") or e.get("tester_completado_at"))
        if ini and fin:
            d = (fin - ini).total_seconds()
            if d > 0:
                total_durs.append(d)
    dur_total_avg = round(sum(total_durs) / len(total_durs) / 3600, 1) if total_durs else None

    # ── Por desarrollador ─────────────────────────────────────────────────────
    by_dev: dict[str, dict] = defaultdict(lambda: {"total": 0, "completados": 0,
                                                     "rework": 0, "durs": []})
    for e in recent:
        dev = e.get("asignado", "Sin asignar") or "Sin asignar"
        by_dev[dev]["total"] += 1
        if e.get("estado") == "completado":
            by_dev[dev]["completados"] += 1
        if e.get("intentos_dev", 0) > 1:
            by_dev[dev]["rework"] += 1
        d = _duration_seg(e, "pm_inicio_at", "completado_at")
        if d:
            by_dev[dev]["durs"].append(d)

    leaderboard = []
    for dev, data in by_dev.items():
        avg_h = round(sum(data["durs"]) / len(data["durs"]) / 3600, 1) if data["durs"] else None
        leaderboard.append({
            "dev":          dev,
            "total":        data["total"],
            "completados":  data["completados"],
            "rework":       data["rework"],
            "avg_hours":    avg_h,
        })
    leaderboard.sort(key=lambda x: (-x["completados"], x.get("avg_hours") or 9999))

    # ── Tendencia: esta semana vs semana anterior ─────────────────────────────
    this_week = sum(1 for e in recent if e["_ts"] >= cutoff_7)
    prev_week = sum(1 for e in recent
                    if cutoff_7 - timedelta(days=7) <= e["_ts"] < cutoff_7)
    trend     = "up" if this_week > prev_week else ("down" if this_week < prev_week else "flat")
    trend_pct = (
        round((this_week - prev_week) / prev_week * 100, 1) if prev_week else None
    )

    # ── Por proyecto ──────────────────────────────────────────────────────────
    by_project: dict[str, int] = defaultdict(int)
    for e in recent:
        by_project[e.get("_project", "?")] += 1

    # ── Distribución por gravedad / prioridad ─────────────────────────────────
    by_priority: dict[int, int] = defaultdict(int)
    for e in recent:
        p = e.get("priority", 9)
        by_priority[p] += 1

    return {
        "period_days":     days,
        "total":           total,
        "completados":     completados,
        "con_error":       con_error,
        "rework_rate_pct": rework_rate,
        "this_week":       this_week,
        "prev_week":       prev_week,
        "trend":           trend,
        "trend_pct":       trend_pct,
        "by_week":         dict(sorted(by_week.items())),
        "dur_pm_min":      dur_pm,
        "dur_dev_min":     dur_dev,
        "dur_tester_min":  dur_tester,
        "dur_total_hrs":   dur_total_avg,
        "leaderboard":     leaderboard,
        "by_project":      dict(by_project),
        "by_priority":     {str(k): v for k, v in sorted(by_priority.items())},
    }
