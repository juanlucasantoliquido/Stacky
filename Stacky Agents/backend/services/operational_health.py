"""Plan 46 — Panel de Salud Operativa (agregación PURA, sin I/O).

Destila las runs recientes (AgentExecution como dicts) en 4 buckets de triage:
needs_review, failed, expensive, zombie. Cero I/O, cero Flask/DB: el endpoint
(api/diag.py) hace la query y le pasa los dicts + umbrales. Testeable en memoria.
"""
from __future__ import annotations

from datetime import datetime

DEFAULT_THRESHOLDS: dict = {
    "cost_usd": 1.0,
    # Fallback de la función PURA cuando se la llama sin thresholds (G1: no
    # importa EXECUTION_TIMEOUT_MINUTES para no acoplarse al sistema). El default
    # EFECTIVO en producción lo siembra el endpoint = EXECUTION_TIMEOUT_MINUTES (120).
    "zombie_minutes": 30,
    "needs_review_stale_days": 3,
    "max_rows_per_bucket": 20,
}


def _coerce_cost(metadata: dict) -> float | None:
    """Normaliza metadata['cost'] (número, dict {total/reported/estimated}, o ausente)."""
    raw = (metadata or {}).get("cost")
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    if isinstance(raw, dict):
        for key in ("total", "reported", "estimated"):
            v = raw.get(key)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                return float(v)
    return None


def _runtime_of(run: dict) -> str:
    meta = run.get("metadata") or {}
    return meta.get("runtime") or run.get("agent_type") or "unknown"


def _age_minutes(now_iso: str, started_at: str | None) -> float | None:
    """Diferencia en minutos entre now_iso y started_at (ambos ISO-8601). None si no parsea."""
    if not started_at:
        return None
    try:
        now = datetime.fromisoformat(now_iso)
        start = datetime.fromisoformat(started_at)
    except (TypeError, ValueError):
        return None
    return (now - start).total_seconds() / 60.0


def aggregate_operational_health(
    runs: list[dict],
    now_iso: str,
    thresholds: dict | None = None,
) -> dict:
    """Clasifica runs en los 4 buckets de triage. Función pura y determinista."""
    th = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    cap = th["max_rows_per_bucket"]

    needs_review: list[dict] = []
    failed: list[dict] = []
    expensive: list[dict] = []
    zombie: list[dict] = []

    for run in runs:
        meta = run.get("metadata") or {}
        rt = _runtime_of(run)
        row = {
            "id": run.get("id"),
            "ticket_id": run.get("ticket_id"),
            "agent_type": run.get("agent_type"),
            "runtime": rt,
            "project": run.get("project"),
            "started_at": run.get("started_at"),
            "status": run.get("status"),
        }
        status = (run.get("status") or "").lower()
        age = _age_minutes(now_iso, run.get("started_at"))

        if status == "needs_review":
            nr = {**row, "age_days": round(age / 1440, 2) if age is not None else None}
            nr["stale"] = (
                nr["age_days"] is not None
                and nr["age_days"] >= th["needs_review_stale_days"]
            )
            needs_review.append(nr)

        if status in ("error", "failed"):
            failed.append({
                **row,
                "failure_kind": meta.get("failure_kind") or "unknown",
                "error_message": run.get("error_message"),
            })

        cost = _coerce_cost(meta)
        if cost is not None and cost >= th["cost_usd"]:
            expensive.append({**row, "cost_usd": round(cost, 4), "model": meta.get("model")})

        if status == "running" and age is not None and age >= th["zombie_minutes"]:
            zombie.append({**row, "age_minutes": round(age, 1)})

    needs_review.sort(key=lambda r: (r["age_days"] is None, -(r["age_days"] or 0)))
    failed.sort(key=lambda r: (r["started_at"] or ""), reverse=True)
    expensive.sort(key=lambda r: -(r["cost_usd"] or 0))
    zombie.sort(key=lambda r: -(r["age_minutes"] or 0))

    def cost_by(key_fn, rows: list[dict]) -> dict:
        out: dict = {}
        for r in rows:
            k = key_fn(r) or "unknown"
            out[k] = round(out.get(k, 0) + (r["cost_usd"] or 0), 4)
        return out

    return {
        "generated_at": now_iso,
        "thresholds": th,
        "summary": {
            "needs_review_pending": len(needs_review),
            "needs_review_stale": sum(1 for r in needs_review if r.get("stale")),
            "failed": len(failed),
            "expensive": len(expensive),
            "zombie": len(zombie),
            "scanned": len(runs),
        },
        "needs_review": needs_review[:cap],
        "failed": failed[:cap],
        "expensive": expensive[:cap],
        "zombie": zombie[:cap],
        "expensive_cost_by_model": cost_by(lambda r: r.get("model"), expensive),
        "expensive_cost_by_runtime": cost_by(lambda r: r.get("runtime"), expensive),
    }
