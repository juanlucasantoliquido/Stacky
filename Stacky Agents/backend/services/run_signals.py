"""Plan 171 F1 — Núcleo PURO de señales operativas.

Toda la señal (proyección, agregados, percentiles, series, ventanas, reglas) como
funciones puras sin Flask ni DB, alimentadas por los `ExecRecord` que
`cost_analytics` ya produce.

Determinista o no existe: cada regla tiene umbrales explícitos y mínimos de
muestra. Sin datos suficientes la regla NO dispara — un aviso falso es peor que
ningún aviso.

Imports permitidos acá: stdlib puro. PROHIBIDO importar db/models/flask/config.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

TERMINAL_STATUSES = ("completed", "needs_review", "error")   # espejo harness_health.py
ACTIVE_STATUSES = ("preparing", "running")                   # espejo agent_runner.py
ERROR_STATUS = "error"
SIN_DATO = "sin dato"          # clave de agrupación para model=None
DESCONOCIDO = "desconocido"    # clave de agrupación para runtime/agent_type=None
CURRENT_WINDOW_DAYS = 7
BASELINE_WINDOW_DAYS = 28      # baseline = los 28 días ANTERIORES a la ventana actual

DEFAULT_THRESHOLDS = {
    "schema_version": 1,
    "error_rate_warn": 0.3,        # R-O1
    "error_rate_delta": 0.15,      # R-O2
    "min_runs": 5,                 # mínimo de runs terminales en ventana actual
    "baseline_min_runs": 10,       # mínimo de runs terminales en baseline
    "p90_regression_factor": 1.5,  # R-O3
    "p90_min_seconds": 30.0,       # R-O3: baseline p90 menor a esto = ruido
    "stall_minutes": None,         # R-O4: None = usar EXECUTION_TIMEOUT_MINUTES
                                   # (resuelto en ops_telemetry.load_thresholds();
                                   #  el core SIEMPRE recibe el valor efectivo int)
    "daily_budget_usd": None,      # R-O5: null = regla apagada (default silencioso)
}

_BILLABLE_KINDS = ("reported", "estimated")


def _utcnow() -> datetime:
    """Naive-UTC canónico del plan (comparable con started_at de la DB)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


@dataclass
class RunPoint:
    execution_id: int
    agent_type: str
    runtime: str
    model: str | None
    status: str
    started_at: datetime
    duration_seconds: float | None
    billable_usd: float
    has_model: bool


# ── Proyección ───────────────────────────────────────────────────────────────

def from_exec_record(r) -> RunPoint:
    """Proyecta un `cost_analytics.ExecRecord` (duck-typing: no se importa el tipo).

    `duration_seconds` SOLO si status=="completed" y hay ambos timestamps: los
    errores suelen fallar rápido y falsearían la latencia "sana" hacia abajo.
    """
    row = getattr(r, "row", None)
    status = getattr(r, "status", None) or ""
    started = getattr(r, "started_at", None)
    completed = getattr(r, "completed_at", None)

    duration = None
    if status == "completed" and started is not None and completed is not None:
        try:
            duration = round((completed - started).total_seconds(), 3)
        except (TypeError, AttributeError):
            duration = None

    cost_usd = getattr(row, "cost_usd", None)
    cost_kind = getattr(row, "cost_kind", "") or ""
    billable = float(cost_usd) if (cost_kind in _BILLABLE_KINDS and cost_usd is not None) else 0.0
    model = getattr(row, "model", None)

    return RunPoint(
        execution_id=getattr(r, "execution_id", 0),
        agent_type=getattr(r, "agent_type", None) or DESCONOCIDO,
        runtime=getattr(row, "runtime", None) or DESCONOCIDO,
        model=model,
        status=status,
        started_at=started,
        duration_seconds=duration,
        billable_usd=billable,
        has_model=model is not None,
    )


# ── Percentiles ──────────────────────────────────────────────────────────────

def percentile_nearest_rank(values: list, q: float) -> float | None:
    """Nearest-rank: rank = ceil(q*n), idx = max(0, rank-1). Vacío → None."""
    if not values:
        return None
    ordered = sorted(values)
    rank = math.ceil(q * len(ordered))
    idx = max(0, rank - 1)
    idx = min(idx, len(ordered) - 1)
    return round(ordered[idx], 3)


# ── Agregados ────────────────────────────────────────────────────────────────

def _empty_totals() -> dict:
    return {
        "runs": 0, "terminal": 0, "completed": 0, "needs_review": 0, "error": 0,
        "running": 0, "error_rate": None, "p50_seconds": None, "p90_seconds": None,
        "billable_usd": 0.0, "runs_sin_modelo": 0,
    }


def _rate(error: int, terminal: int) -> float | None:
    return round(error / terminal, 4) if terminal else None


def summarize_groups(points: list) -> dict:
    """`{"totals": {...}, "groups": [...]}` con el shape congelado del plan.

    `groups` ordenado por `runs` DESC y desempate por (agent_type, runtime) ASC.
    """
    totals = _empty_totals()
    durations_all: list = []
    cells: dict = {}

    for p in points or []:
        totals["runs"] += 1
        if p.status in TERMINAL_STATUSES:
            totals["terminal"] += 1
        if p.status == "completed":
            totals["completed"] += 1
        elif p.status == "needs_review":
            totals["needs_review"] += 1
        elif p.status == ERROR_STATUS:
            totals["error"] += 1
        if p.status in ACTIVE_STATUSES:
            totals["running"] += 1
        if not p.has_model:
            totals["runs_sin_modelo"] += 1
        totals["billable_usd"] += float(p.billable_usd or 0.0)
        if p.duration_seconds is not None:
            durations_all.append(p.duration_seconds)

        key = (p.agent_type, p.runtime)
        cell = cells.setdefault(key, {
            "agent_type": p.agent_type, "runtime": p.runtime, "runs": 0, "terminal": 0,
            "completed": 0, "error": 0, "error_rate": None, "p50_seconds": None,
            "p90_seconds": None, "billable_usd": 0.0, "models": {}, "_durations": [],
        })
        cell["runs"] += 1
        if p.status in TERMINAL_STATUSES:
            cell["terminal"] += 1
        if p.status == "completed":
            cell["completed"] += 1
        elif p.status == ERROR_STATUS:
            cell["error"] += 1
        cell["billable_usd"] += float(p.billable_usd or 0.0)
        if p.duration_seconds is not None:
            cell["_durations"].append(p.duration_seconds)
        model_key = p.model if p.model else SIN_DATO
        cell["models"][model_key] = cell["models"].get(model_key, 0) + 1

    totals["error_rate"] = _rate(totals["error"], totals["terminal"])
    totals["p50_seconds"] = percentile_nearest_rank(durations_all, 0.5)
    totals["p90_seconds"] = percentile_nearest_rank(durations_all, 0.9)
    totals["billable_usd"] = round(totals["billable_usd"], 6)

    groups: list = []
    for cell in cells.values():
        durations = cell.pop("_durations")
        cell["error_rate"] = _rate(cell["error"], cell["terminal"])
        cell["p50_seconds"] = percentile_nearest_rank(durations, 0.5)
        cell["p90_seconds"] = percentile_nearest_rank(durations, 0.9)
        cell["billable_usd"] = round(cell["billable_usd"], 6)
        groups.append(cell)
    groups.sort(key=lambda g: (-g["runs"], g["agent_type"], g["runtime"]))

    return {"totals": totals, "groups": groups}


# ── Series diarias ───────────────────────────────────────────────────────────

def daily_series(points: list, days: int, now: datetime) -> list:
    """Exactamente `days` entradas consecutivas terminando HOY (eje continuo)."""
    days = max(1, int(days or 1))
    buckets: dict = {}
    for p in points or []:
        if p.started_at is None:
            continue
        key = p.started_at.strftime("%Y-%m-%d")
        slot = buckets.setdefault(key, {"runs": 0, "errors": 0, "billable_usd": 0.0,
                                        "_durations": []})
        slot["runs"] += 1
        if p.status == ERROR_STATUS:
            slot["errors"] += 1
        slot["billable_usd"] += float(p.billable_usd or 0.0)
        if p.duration_seconds is not None:
            slot["_durations"].append(p.duration_seconds)

    out: list = []
    for offset in range(days - 1, -1, -1):
        date_key = (now - timedelta(days=offset)).strftime("%Y-%m-%d")
        slot = buckets.get(date_key)
        if slot is None:
            out.append({"date": date_key, "runs": 0, "errors": 0, "billable_usd": 0.0,
                        "p50_seconds": None})
        else:
            out.append({
                "date": date_key,
                "runs": slot["runs"],
                "errors": slot["errors"],
                "billable_usd": round(slot["billable_usd"], 6),
                "p50_seconds": percentile_nearest_rank(slot["_durations"], 0.5),
            })
    return out


# ── Ventanas ─────────────────────────────────────────────────────────────────

def split_windows(points: list, now: datetime) -> tuple:
    """current = started_at > now-7d ; baseline = now-35d < started_at <= now-7d."""
    cutoff_current = now - timedelta(days=CURRENT_WINDOW_DAYS)
    cutoff_baseline = now - timedelta(days=CURRENT_WINDOW_DAYS + BASELINE_WINDOW_DAYS)
    current: list = []
    baseline: list = []
    for p in points or []:
        if p.started_at is None:
            continue
        if p.started_at > cutoff_current:
            current.append(p)
        elif p.started_at > cutoff_baseline:
            baseline.append(p)
    return current, baseline


# ── Reglas ───────────────────────────────────────────────────────────────────

def _breach(rule_id, severity, agent_type, runtime, message, observed, reference, threshold) -> dict:
    return {
        "rule_id": rule_id, "severity": severity, "agent_type": agent_type,
        "runtime": runtime, "message": message, "observed": observed,
        "reference": reference, "threshold": threshold,
    }


def _cells_of(points: list) -> dict:
    cells: dict = {}
    for p in points or []:
        cells.setdefault((p.agent_type, p.runtime), []).append(p)
    return cells


def _cell_stats(cell_points: list) -> dict:
    terminal = [p for p in cell_points if p.status in TERMINAL_STATUSES]
    errors = [p for p in terminal if p.status == ERROR_STATUS]
    durations = [p.duration_seconds for p in cell_points if p.duration_seconds is not None]
    return {
        "terminal": len(terminal),
        "errors": len(errors),
        "error_rate": _rate(len(errors), len(terminal)),
        "durations": durations,
        "p90": percentile_nearest_rank(durations, 0.9),
    }


def detect_regressions(current: list, baseline: list, thresholds: dict) -> list:
    """R-O2 (tasa de error) y R-O3 (latencia p90) por celda (agent_type, runtime)."""
    t = thresholds or {}
    min_runs = int(t.get("min_runs") or 0)
    base_min = int(t.get("baseline_min_runs") or 0)
    rate_delta = float(t.get("error_rate_delta") or 0.0)
    factor = float(t.get("p90_regression_factor") or 1.0)
    p90_floor = float(t.get("p90_min_seconds") or 0.0)

    cur_cells = _cells_of(current)
    base_cells = _cells_of(baseline)
    out: list = []

    for key in sorted(set(cur_cells) & set(base_cells)):
        agent_type, runtime = key
        cur = _cell_stats(cur_cells[key])
        base = _cell_stats(base_cells[key])

        # R-O2 — regresión de tasa de error.
        if (cur["terminal"] >= min_runs and base["terminal"] >= base_min
                and cur["error_rate"] is not None and base["error_rate"] is not None
                and cur["error_rate"] - base["error_rate"] >= rate_delta):
            out.append(_breach(
                "R-O2", "critical", agent_type, runtime,
                f"Regresión de tasa de error vs baseline: {cur['error_rate']} ahora "
                f"vs {base['error_rate']} histórico",
                cur["error_rate"], base["error_rate"], rate_delta,
            ))

        # R-O3 — regresión de latencia p90 (solo sobre corridas con duración).
        if (len(cur["durations"]) >= min_runs and len(base["durations"]) >= base_min
                and base["p90"] is not None and cur["p90"] is not None
                and base["p90"] >= p90_floor and cur["p90"] >= factor * base["p90"]):
            out.append(_breach(
                "R-O3", "warn", agent_type, runtime,
                f"Regresión de latencia: p90 {cur['p90']}s ahora vs {base['p90']}s histórico",
                cur["p90"], base["p90"], factor,
            ))
    return out


def evaluate_thresholds(points: list, thresholds: dict, now: datetime) -> tuple:
    """Devuelve `(breaches R-O1+R-O4+R-O5, stalls_dict)`."""
    t = thresholds or {}
    min_runs = int(t.get("min_runs") or 0)
    rate_warn = float(t.get("error_rate_warn") or 0.0)
    stall_minutes = t.get("stall_minutes")
    budget = t.get("daily_budget_usd")

    out: list = []

    # R-O1 — tasa de error alta por celda, en la ventana visible.
    for key in sorted(_cells_of(points)):
        agent_type, runtime = key
        stats = _cell_stats(_cells_of(points)[key])
        if stats["terminal"] >= min_runs and stats["error_rate"] is not None \
                and stats["error_rate"] >= rate_warn:
            out.append(_breach(
                "R-O1", "warn", agent_type, runtime,
                f"Tasa de error alta: {stats['errors']}/{stats['terminal']} corridas en la ventana",
                stats["error_rate"], None, rate_warn,
            ))

    # R-O4 — corridas activas más viejas que el umbral de cuelgue.
    stalls = {"count": 0, "execution_ids": []}
    if stall_minutes is not None:
        limite = now - timedelta(minutes=int(stall_minutes))
        colgadas = [p for p in (points or [])
                    if p.status in ACTIVE_STATUSES and p.started_at is not None
                    and p.started_at < limite]
        colgadas.sort(key=lambda p: p.started_at)  # los más viejos primero
        if colgadas:
            stalls = {"count": len(colgadas),
                      "execution_ids": [p.execution_id for p in colgadas[:20]]}
            out.append(_breach(
                "R-O4", "warn", None, None,
                f"{len(colgadas)} corrida(s) activas hace más de {int(stall_minutes)} minutos",
                len(colgadas), None, int(stall_minutes),
            ))

    # R-O5 — presupuesto diario (solo lo facturable de HOY, UTC).
    if budget is not None:
        inicio_de_hoy = now.replace(hour=0, minute=0, second=0, microsecond=0)
        hoy_usd = round(sum(
            float(p.billable_usd or 0.0) for p in (points or [])
            if p.started_at is not None and p.started_at >= inicio_de_hoy
        ), 6)
        if hoy_usd >= float(budget):
            out.append(_breach(
                "R-O5", "warn", None, None,
                f"Presupuesto diario alcanzado: {hoy_usd} USD de {budget} USD",
                hoy_usd, None, float(budget),
            ))

    return out, stalls


# ── Umbrales y orden ─────────────────────────────────────────────────────────

def merge_thresholds(overrides: dict | None) -> dict:
    """DEFAULT_THRESHOLDS copiado + overrides superficiales SOLO de claves conocidas."""
    effective = dict(DEFAULT_THRESHOLDS)
    if isinstance(overrides, dict):
        for key, value in overrides.items():
            if key in DEFAULT_THRESHOLDS and key != "schema_version":
                effective[key] = value
    return effective


_SEVERITY_ORDER = {"critical": 0, "warn": 1}


def sort_breaches(breaches: list) -> list:
    """critical primero, después warn; dentro de cada severidad por rule_id ASC."""
    return sorted(
        list(breaches or []),
        key=lambda b: (_SEVERITY_ORDER.get(b.get("severity"), 9), b.get("rule_id") or ""),
    )
