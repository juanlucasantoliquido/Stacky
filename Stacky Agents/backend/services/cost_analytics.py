"""Plan 142 — Centro de Costos + Codeburn: extractor canónico + motor de agregación.

F0 (extractor, PURO, sin DB): `extract_cost_row(md)` reconcilia las 3 fuentes de costo
que hoy conviven en `AgentExecution.metadata_dict` (harness_telemetry canónico /
claude_telemetry legacy / top-level cost_usd) en una única `CostRow`, clasificando
`cost_kind` en reported|estimated|nominal|unknown. Corrige la divergencia real
documentada en el plan (R3): `api/metrics.py:_execution_costs` solo lee
`claude_telemetry` (ignora codex) y trata `cost_estimated` (bool) como monto (float).

F1 (agregación, toca DB): `load_records` hace UNA query SQL acotada (`_MAX_ROWS`) con
filtros de columna + outerjoin a Ticket; `summarize`/`burn`/`breakdown` son funciones
PURAS que agregan `list[ExecRecord]` en memoria (testeables sin DB).

Reglas: read-only siempre. `github_copilot` (suscripción plana) es "nominal" y NUNCA
entra en `billable_usd`. Sin costo/tokens -> `None`, NUNCA 0.0 inventado.
"""
from __future__ import annotations

import dataclasses
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta

from harness.pricing import _MTOK, _load_prices, estimate_cost
from services.cost_signals import (
    SignalRow,
    duration_seconds,
    extract_signal_row,
    output_chars,
)

logger = logging.getLogger("stacky.services.cost_analytics")

# Runtimes de suscripción plana: su costo NUNCA es facturable, sólo hint "nominal".
_SUBSCRIPTION_RUNTIMES: frozenset[str] = frozenset({"github_copilot"})


@dataclass
class CostRow:
    runtime: str | None
    model: str | None
    tokens_in: int | None
    tokens_out: int | None
    cache_read_tokens: int | None
    cost_usd: float | None          # mejor número de costo disponible (o None si n/d)
    cost_kind: str                  # "reported" | "estimated" | "nominal" | "unknown"
    cache_savings_usd: float | None  # ahorro ESTIMADO por cache reads (o None)


def input_price_per_mtok(model: str | None) -> float | None:
    """Precio input USD/Mtok del prefijo más largo que matchea. None si no matchea."""
    if not model:
        return None
    prices = _load_prices()
    best = None
    best_len = -1
    for prefix, (in_price, _out) in prices.items():
        if model.startswith(prefix) and len(prefix) > best_len:
            best = in_price
            best_len = len(prefix)
    return best


def _first_int(*vals) -> int | None:
    for v in vals:
        if v is not None:
            try:
                return int(v)
            except (TypeError, ValueError):
                continue
    return None


def _as_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def extract_cost_row(md: dict | None) -> CostRow:
    md = md or {}
    ht = md.get("harness_telemetry") if isinstance(md.get("harness_telemetry"), dict) else {}
    ct = md.get("claude_telemetry") if isinstance(md.get("claude_telemetry"), dict) else {}
    ct_usage = ct.get("usage") if isinstance(ct.get("usage"), dict) else {}

    runtime = md.get("runtime") or ht.get("runtime")
    # C3 — UNA sola línea correcta (no copiar variantes). Precedencia: top-level > harness_telemetry.raw.model.
    _ht_raw = ht.get("raw") if isinstance(ht.get("raw"), dict) else {}
    model = md.get("model") or _ht_raw.get("model")

    tokens_in = _first_int(ht.get("input_tokens"), ct_usage.get("input_tokens"), md.get("tokens_in"))
    tokens_out = _first_int(ht.get("output_tokens"), ct_usage.get("output_tokens"), md.get("tokens_out"))
    cache_read = _first_int(ht.get("cache_read_tokens"), ct_usage.get("cache_read_input_tokens"))

    # raw_cost + is_estimated según precedencia (harness > claude legacy > top-level)
    raw_cost = None
    is_estimated = False
    if ht.get("total_cost_usd") is not None:
        raw_cost = _as_float(ht.get("total_cost_usd"))
        is_estimated = bool(ht.get("cost_estimated"))
    elif ct.get("total_cost_usd") is not None:
        raw_cost = _as_float(ct.get("total_cost_usd"))
        is_estimated = False  # legacy claude = reportado
    elif md.get("cost_usd") is not None:
        raw_cost = _as_float(md.get("cost_usd"))
        is_estimated = False

    # Clasificación de cost_kind (mutuamente excluyente por run -> sin doble conteo)
    if runtime in _SUBSCRIPTION_RUNTIMES:
        cost = raw_cost if raw_cost is not None else estimate_cost(model, tokens_in, tokens_out)
        kind = "nominal"
    elif raw_cost is None:
        est = estimate_cost(model, tokens_in, tokens_out)
        if est is not None:
            cost, kind = est, "estimated"
        else:
            cost, kind = None, "unknown"
    elif is_estimated:
        cost, kind = raw_cost, "estimated"
    else:
        cost, kind = raw_cost, "reported"

    # Ahorro estimado por cache reads: cache_read_tokens * input_price / 1e6
    savings = None
    ip = input_price_per_mtok(model)
    if cache_read and ip is not None:
        savings = round(cache_read * ip / _MTOK, 6)

    return CostRow(runtime=runtime, model=model, tokens_in=tokens_in, tokens_out=tokens_out,
                    cache_read_tokens=cache_read, cost_usd=cost, cost_kind=kind, cache_savings_usd=savings)


# ─────────────────────────────────────────────────────────────────────────────
# F1 — Motor de agregación (query acotada + funciones puras summarize/burn/breakdown)
# ─────────────────────────────────────────────────────────────────────────────

_MAX_ROWS = 20000  # cap duro de seguridad (mono-operador)


@dataclass
class ExecRecord:
    execution_id: int
    ticket_id: int | None
    ado_id: int | None
    project: str | None
    agent_type: str | None
    status: str | None
    started_at: datetime | None
    row: CostRow
    # F8 (opcional) — metadata_dict crudo, para legacy_cost_mirror en la auditoría de
    # reconciliación SIN una segunda query. Default None: 100% aditivo/retrocompatible
    # (F0/F1 no lo usan; F1 sigue construyendo ExecRecord sin pasar este campo).
    raw_metadata: dict | None = None
    # Plan 171 (aditivo, default None = 100% retrocompatible): fin de la corrida,
    # para duraciones/percentiles en services/run_signals.py.
    completed_at: datetime | None = None
    # ── Plan 242 F0 — señales enriquecidas. TODAS con default: 100% aditivo.
    # Ningún caller del Plan 142 las pasa, y todos los tests del 142 siguen verdes.
    signals: SignalRow | None = None
    duration_s: float | None = None
    verdict: str | None = None
    completion_source: str | None = None
    output_chars: int | None = None
    work_item_type: str | None = None      # de Ticket (ya cargado por el outerjoin)
    priority: int | None = None            # de Ticket — models.py lo declara Mapped[int|None]


@dataclass
class CostFilters:
    date_from: datetime | None = None
    date_to: datetime | None = None
    days: int = 30                 # usado sólo si date_from/date_to no vienen
    runtime: str | None = None     # filtro Python (metadata)
    model: str | None = None       # filtro Python (metadata), match exacto
    agent_type: str | None = None  # filtro SQL
    ticket_id: int | None = None   # filtro SQL
    project: str | None = None     # filtro SQL (stacky_project_name o project)
    statuses: tuple[str, ...] = ()  # filtro SQL (csv)
    cost_kind: str | None = None   # filtro Python: reported|estimated|nominal|unknown
    # Plan 199 F4 — aditivos AL FINAL con default: todo caller previo sigue
    # construyendo CostFilters igual. Los plurales COEXISTEN con los singulares
    # (no los reemplazan): quien ya filtraba por un runtime sigue funcionando.
    runtimes: tuple = ()           # OR entre varios runtimes
    models: tuple = ()             # OR entre varios modelos
    min_cost_usd: float | None = None
    max_cost_usd: float | None = None


def load_records(f: CostFilters) -> list[ExecRecord]:
    """UNA query SQL con filtros de columna + join Ticket. Cap _MAX_ROWS. Filtros
    de runtime/model/cost_kind se aplican en Python (viven en metadata)."""
    from db import session_scope
    from models import AgentExecution, Ticket

    now = datetime.utcnow()
    start = f.date_from or (now - timedelta(days=max(1, min(f.days, 365))))
    end = f.date_to or (now + timedelta(seconds=1))
    out: list[ExecRecord] = []
    # C7 — construir los ExecRecord DENTRO del session_scope (robustez; no depender
    # de que expire_on_commit=False para que los atributos sigan legibles tras cerrar).
    # C8 — outerjoin: no descartar ejecuciones huérfanas (ticket borrado) del conteo de costo,
    # coherente con "consolida TODA la telemetría" (§1). tk puede ser None con outerjoin.
    with session_scope() as session:
        q = (session.query(AgentExecution, Ticket)
             .outerjoin(Ticket, Ticket.id == AgentExecution.ticket_id)
             .filter(AgentExecution.started_at >= start, AgentExecution.started_at < end))
        if f.agent_type:
            q = q.filter(AgentExecution.agent_type == f.agent_type)
        if f.ticket_id:
            q = q.filter(AgentExecution.ticket_id == f.ticket_id)
        if f.statuses:
            q = q.filter(AgentExecution.status.in_(list(f.statuses)))
        if f.project:
            # el filtro de proyecto excluye huérfanas por definición (no hay ticket) -> OK.
            q = q.filter((Ticket.stacky_project_name == f.project) | (Ticket.project == f.project))
        q = q.order_by(AgentExecution.started_at.desc()).limit(_MAX_ROWS)
        for ex, tk in q.all():
            md = ex.metadata_dict
            cr = extract_cost_row(md)
            if f.runtime and cr.runtime != f.runtime:
                continue
            if f.model and cr.model != f.model:
                continue
            if f.cost_kind and cr.cost_kind != f.cost_kind:
                continue
            # Plan 199 F4 — filtros aditivos. Una fila SIN costo no entra en un
            # rango de costo: "no sé cuánto salió" no es "salió $0".
            if f.runtimes and (cr.runtime or "") not in f.runtimes:
                continue
            if f.models and (cr.model or "") not in f.models:
                continue
            if f.min_cost_usd is not None and (
                    cr.cost_usd is None or cr.cost_usd < f.min_cost_usd):
                continue
            if f.max_cost_usd is not None and (
                    cr.cost_usd is None or cr.cost_usd > f.max_cost_usd):
                continue
            out.append(ExecRecord(
                execution_id=ex.id, ticket_id=ex.ticket_id,
                ado_id=getattr(tk, "ado_id", None) if tk else None,
                project=(tk.stacky_project_name or tk.project) if tk else None,
                agent_type=ex.agent_type, status=ex.status, started_at=ex.started_at, row=cr,
                raw_metadata=md, completed_at=ex.completed_at,
                # Plan 242 F0 — sin query adicional: ex y tk ya están cargados.
                signals=extract_signal_row(md),
                duration_s=duration_seconds(ex.started_at, ex.completed_at),
                verdict=ex.verdict,
                completion_source=ex.completion_source,
                output_chars=output_chars(ex.output),
                work_item_type=getattr(tk, "work_item_type", None) if tk else None,
                priority=getattr(tk, "priority", None) if tk else None))
    return out


def _billable(kind: str) -> bool:  # reported+estimated son facturables; nominal/unknown NO
    return kind in ("reported", "estimated")


def summarize(records: list[ExecRecord], top_n: int = 10) -> dict:
    runs_total = len(records)
    reported_usd = 0.0
    estimated_usd = 0.0
    nominal_usd = 0.0
    tokens_in_total = 0
    tokens_out_total = 0
    cache_read_total = 0
    cache_savings_usd_total = 0.0
    runs_with_cost = 0
    completed_count = 0

    for r in records:
        cr = r.row
        if cr.cost_usd is not None:
            runs_with_cost += 1
            if cr.cost_kind == "reported":
                reported_usd += cr.cost_usd
            elif cr.cost_kind == "estimated":
                estimated_usd += cr.cost_usd
            elif cr.cost_kind == "nominal":
                nominal_usd += cr.cost_usd
        tokens_in_total += cr.tokens_in or 0
        tokens_out_total += cr.tokens_out or 0
        cache_read_total += cr.cache_read_tokens or 0
        cache_savings_usd_total += cr.cache_savings_usd or 0.0
        if (r.status or "").lower() == "completed":
            completed_count += 1

    billable_usd = round(reported_usd + estimated_usd, 6)
    pct_estimated = round(estimated_usd / billable_usd, 6) if billable_usd > 0 else 0.0
    avg_cost_per_run_usd = round(billable_usd / runs_with_cost, 6) if runs_with_cost > 0 else 0.0
    cost_per_completed_task_usd = round(billable_usd / completed_count, 6) if completed_count > 0 else 0.0
    tokens_out_in_ratio = round(tokens_out_total / tokens_in_total, 6) if tokens_in_total > 0 else 0.0

    ranked = sorted(
        (r for r in records if r.row.cost_usd is not None),
        key=lambda r: r.row.cost_usd,
        reverse=True,
    )[:max(1, top_n)]
    top_runs = [{
        "execution_id": r.execution_id, "ticket_id": r.ticket_id, "agent_type": r.agent_type,
        "runtime": r.row.runtime, "model": r.row.model,
        "cost_usd": round(r.row.cost_usd, 6) if r.row.cost_usd is not None else None,
        "cost_kind": r.row.cost_kind,
        "started_at": r.started_at.isoformat() if r.started_at else None,
    } for r in ranked]

    return {
        "runs_total": runs_total, "runs_with_cost": runs_with_cost,
        "runs_without_cost": runs_total - runs_with_cost,
        "reported_usd": round(reported_usd, 6), "estimated_usd": round(estimated_usd, 6),
        "nominal_usd": round(nominal_usd, 6),
        "billable_usd": billable_usd,
        "pct_estimated": pct_estimated,
        "tokens_in_total": tokens_in_total, "tokens_out_total": tokens_out_total,
        "cache_read_total": cache_read_total,
        "cache_savings_usd_total": round(cache_savings_usd_total, 6),
        "avg_cost_per_run_usd": avg_cost_per_run_usd,
        "cost_per_completed_task_usd": cost_per_completed_task_usd,
        "tokens_out_in_ratio": tokens_out_in_ratio,
        "top_runs": top_runs,
    }


def _bucket_start(dt: datetime, bucket: str) -> datetime:
    """Trunca `dt` al inicio de su bucket (hora/día/semana-ISO-lunes)."""
    d = dt.replace(minute=0, second=0, microsecond=0)
    if bucket == "hour":
        return d
    d = d.replace(hour=0)
    if bucket == "day":
        return d
    # week: lunes de la semana ISO (isoweekday(): lunes=1..domingo=7)
    return d - timedelta(days=d.isoweekday() - 1)


def _bucket_step(bucket: str) -> timedelta:
    if bucket == "hour":
        return timedelta(hours=1)
    if bucket == "week":
        return timedelta(weeks=1)
    return timedelta(days=1)


def _bucket_key(dt: datetime, bucket: str) -> str:
    if bucket == "hour":
        return dt.strftime("%Y-%m-%dT%H:00")
    if bucket == "week":
        # ISO year-week zero-padded ("%G-%V"): calculado vía isocalendar() y NO
        # strftime, porque los directivas %G/%V no son portables en Windows (CRT
        # de msvcrt no las soporta; glibc-only). isocalendar() es multiplataforma.
        iso_year, iso_week, _ = dt.isocalendar()
        return f"{iso_year:04d}-W{iso_week:02d}"
    return dt.strftime("%Y-%m-%d")  # day (default)


def burn(records: list[ExecRecord], bucket: str = "day") -> dict:
    dated = [r for r in records if r.started_at is not None]
    if not dated:
        return {"bucket": bucket, "series": []}

    buckets: dict[datetime, dict] = {}
    for r in dated:
        bs = _bucket_start(r.started_at, bucket)
        acc = buckets.setdefault(bs, {
            "reported_usd": 0.0, "estimated_usd": 0.0, "nominal_usd": 0.0,
            "tokens_in": 0, "tokens_out": 0, "runs": 0,
        })
        cr = r.row
        if cr.cost_usd is not None:
            if cr.cost_kind == "reported":
                acc["reported_usd"] += cr.cost_usd
            elif cr.cost_kind == "estimated":
                acc["estimated_usd"] += cr.cost_usd
            elif cr.cost_kind == "nominal":
                acc["nominal_usd"] += cr.cost_usd
        acc["tokens_in"] += cr.tokens_in or 0
        acc["tokens_out"] += cr.tokens_out or 0
        acc["runs"] += 1

    start = min(buckets)
    end = max(buckets)
    step = _bucket_step(bucket)
    empty_acc = {"reported_usd": 0.0, "estimated_usd": 0.0, "nominal_usd": 0.0,
                 "tokens_in": 0, "tokens_out": 0, "runs": 0}

    series = []
    cur = start
    cumulative = 0.0
    while cur <= end:
        acc = buckets.get(cur, empty_acc)
        billable = round(acc["reported_usd"] + acc["estimated_usd"], 6)
        cumulative = round(cumulative + billable, 6)
        series.append({
            "bucket": _bucket_key(cur, bucket),
            "reported_usd": round(acc["reported_usd"], 6),
            "estimated_usd": round(acc["estimated_usd"], 6),
            "nominal_usd": round(acc["nominal_usd"], 6),
            "billable_usd": billable,
            "cumulative_billable_usd": cumulative,
            "tokens_in": acc["tokens_in"], "tokens_out": acc["tokens_out"], "runs": acc["runs"],
        })
        cur = cur + step

    return {"bucket": bucket, "series": series}


def _dim_key(r: ExecRecord, dimension: str) -> str:
    if dimension == "runtime":
        return r.row.runtime or "unknown"
    if dimension == "model":
        return r.row.model or "unknown"
    if dimension == "agent_type":
        return r.agent_type or "unknown"
    if dimension == "ticket":
        return str(r.ticket_id) if r.ticket_id is not None else "unknown"
    if dimension == "project":
        return r.project or "unknown"
    if dimension == "day":
        return r.started_at.strftime("%Y-%m-%d") if r.started_at else "unknown"
    return "unknown"


def breakdown(records: list[ExecRecord], dimension: str) -> dict:
    groups: dict[str, dict] = {}
    for r in records:
        key = _dim_key(r, dimension)
        acc = groups.setdefault(key, {
            "reported_usd": 0.0, "estimated_usd": 0.0, "nominal_usd": 0.0,
            "tokens_in": 0, "tokens_out": 0, "runs": 0,
        })
        cr = r.row
        if cr.cost_usd is not None:
            if cr.cost_kind == "reported":
                acc["reported_usd"] += cr.cost_usd
            elif cr.cost_kind == "estimated":
                acc["estimated_usd"] += cr.cost_usd
            elif cr.cost_kind == "nominal":
                acc["nominal_usd"] += cr.cost_usd
        acc["tokens_in"] += cr.tokens_in or 0
        acc["tokens_out"] += cr.tokens_out or 0
        acc["runs"] += 1

    out = []
    for key, acc in groups.items():
        billable = round(acc["reported_usd"] + acc["estimated_usd"], 6)
        out.append({
            "key": key,
            "reported_usd": round(acc["reported_usd"], 6),
            "estimated_usd": round(acc["estimated_usd"], 6),
            "nominal_usd": round(acc["nominal_usd"], 6),
            "billable_usd": billable,
            "tokens_in": acc["tokens_in"], "tokens_out": acc["tokens_out"], "runs": acc["runs"],
        })
    out.sort(key=lambda g: (g["billable_usd"], g["runs"]), reverse=True)
    return {"dimension": dimension, "groups": out}


# ─────────────────────────────────────────────────────────────────────────────
# C5 — filters_echo / previous_period / burn_with_comparison (requeridos por F1
# y F2; viven acá porque son PUROS y F1 ya los testea sin DB).
# ─────────────────────────────────────────────────────────────────────────────

def filters_echo(f: CostFilters) -> dict:
    """Filtros efectivos resueltos, para que la UI muestre 'estás viendo: …'.
    Devuelve ISO strings y el rango efectivo ya resuelto (no None)."""
    now = datetime.utcnow()
    start = f.date_from or (now - timedelta(days=max(1, min(f.days, 365))))
    end = f.date_to or now
    return {
        "date_from": start.isoformat(), "date_to": end.isoformat(),
        "days_effective": (end - start).days or f.days,
        "runtime": f.runtime, "model": f.model, "agent_type": f.agent_type,
        "ticket_id": f.ticket_id, "project": f.project,
        "statuses": list(f.statuses), "cost_kind": f.cost_kind,
    }


def previous_period(f: CostFilters) -> CostFilters:
    """Rango previo de IGUAL longitud, inmediatamente anterior. Semántica C5:
    - Si vinieron date_from Y date_to explícitas: span = (date_to - date_from);
      nuevo rango = [date_from - span, date_from).
    - Si NO (se usó days): span = days; nuevo rango = [now-2*days, now-days).
    Conserva TODOS los demás filtros (runtime/model/agent_type/ticket/project/status/cost_kind)."""
    now = datetime.utcnow()
    if f.date_from and f.date_to:
        span = f.date_to - f.date_from
        return dataclasses.replace(f, date_from=f.date_from - span, date_to=f.date_from)
    d = max(1, min(f.days, 365))
    return dataclasses.replace(f, date_from=now - timedelta(days=2 * d), date_to=now - timedelta(days=d))


def burn_with_comparison(cur: list[ExecRecord], prev: list[ExecRecord], bucket: str) -> dict:
    """burn(cur, bucket) + period_comparison contra el total billable de prev.
    delta_pct = (cur-prev)/prev*100, 0.0 si prev==0. Todos los montos round(x,6)."""
    b = burn(cur, bucket=bucket)
    cur_bill = round(sum(r.row.cost_usd or 0.0 for r in cur if _billable(r.row.cost_kind)), 6)
    prev_bill = round(sum(r.row.cost_usd or 0.0 for r in prev if _billable(r.row.cost_kind)), 6)
    delta = 0.0 if prev_bill == 0 else round((cur_bill - prev_bill) / prev_bill * 100, 2)
    b["period_comparison"] = {
        "current_billable_usd": cur_bill,
        "previous_billable_usd": prev_bill,
        "delta_pct": delta,
    }
    return b


# ─────────────────────────────────────────────────────────────────────────────
# F8 (OPCIONAL) — espejo puro del bug legacy, SOLO para auditoría read-only.
# ─────────────────────────────────────────────────────────────────────────────

def legacy_cost_mirror(md: dict | None) -> float:
    """Replica EXACTO lo que hoy hace `api/metrics.py:_execution_costs`: lee sólo
    `md["claude_telemetry"]["total_cost_usd"]` (reportado) + `float(md.get("cost_estimated") or 0)`
    (trata el bool `cost_estimated` como si fuera un MONTO — el bug real, R3). Documentado
    como espejo del bug legacy: NO usar para nada que no sea comparar canónico vs legacy."""
    md = md or {}
    reported = 0.0
    estimated = 0.0

    telemetry = md.get("claude_telemetry") if isinstance(md.get("claude_telemetry"), dict) else {}
    value = telemetry.get("total_cost_usd") if isinstance(telemetry, dict) else None
    if value is not None:
        try:
            reported = float(value)
        except (TypeError, ValueError):
            reported = 0.0

    est_val = md.get("cost_estimated")
    if est_val is not None:
        try:
            estimated = float(est_val)
        except (TypeError, ValueError):
            estimated = 0.0

    return reported + estimated


# ─────────────────────────────────────────────────────────────────────────────
# F7 (OPCIONAL) — reconciliación con export externo tipo ccusage/codeburn.
# Flag STACKY_COST_CODEBURN_IMPORT_ENABLED (default OFF, excepción dura #3):
# prerequisito no garantizado (archivo JSONL externo de una herramienta que el
# operador puede no tener). Si OFF o el path no existe/es inválido -> None,
# SIN CRASH (silencio total, ver F2 /cost-summary).
# ─────────────────────────────────────────────────────────────────────────────

def load_external_codeburn() -> dict | None:
    """Lee un JSONL externo opcional (ccusage/codeburn) si el operador lo configuró.

    Cada línea = un registro `{cost_usd, tokens_in, tokens_out, timestamp, model?}`.
    Devuelve `{"source": "external_jsonl", "total_usd": X, "records": N}` o `None`
    si la flag está OFF, el path está vacío/no existe, o el archivo es inválido.
    NUNCA crashea: cualquier error se loguea como warning y degrada a None.
    """
    from config import config as _cfg

    if not getattr(_cfg, "STACKY_COST_CODEBURN_IMPORT_ENABLED", False):
        return None
    path = (getattr(_cfg, "STACKY_COST_CODEBURN_IMPORT_PATH", "") or "").strip()
    if not path or not os.path.isfile(path):
        return None

    total_usd = 0.0
    records = 0
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                entry = json.loads(line)
                cost = entry.get("cost_usd")
                if cost is not None:
                    total_usd += float(cost)
                records += 1
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        logger.warning("load_external_codeburn: JSONL malformado en %s (%s)", path, exc)
        return None

    return {"source": "external_jsonl", "total_usd": round(total_usd, 6), "records": records}


# ─────────────────────────────────────────────────────────────────────────────
# Plan 158 F4 — backfill idempotente y aditivo: copia metadata["claude_code_model"]
# -> metadata["model"] en filas históricas de claude_code_cli que no tienen
# "model". NUNCA inventa datos: si claude_code_model tampoco existe, no hace
# nada con esa fila (queda "unknown" legítimamente, ver plan158 §6).
# ─────────────────────────────────────────────────────────────────────────────

_BACKFILL_MAX_ROWS = 20000  # mismo cap duro de seguridad que _MAX_ROWS (mono-operador)


def backfill_claude_model_key() -> dict:
    """Copia claude_code_model -> model en filas claude_code_cli sin "model".

    PURO en su lógica de decisión (sólo copia una clave existente), pero SÍ
    toca DB (lectura + escritura acotada por _BACKFILL_MAX_ROWS). Idempotente:
    correrlo N veces produce el mismo resultado final; en la segunda corrida
    "updated" es 0 para las filas ya arregladas.

    Devuelve {"scanned": N, "updated": M}.
    """
    from db import session_scope
    from models import AgentExecution

    scanned = 0
    updated = 0
    with session_scope() as session:
        rows = (
            session.query(AgentExecution)
            .order_by(AgentExecution.id.desc())
            .limit(_BACKFILL_MAX_ROWS)
            .all()
        )
        for row in rows:
            scanned += 1
            md = row.metadata_dict
            if md.get("runtime") != "claude_code_cli":
                continue
            if md.get("model") is not None:
                continue
            claude_model = md.get("claude_code_model")
            if not claude_model:
                continue
            md["model"] = claude_model
            row.metadata_dict = md
            updated += 1
    return {"scanned": scanned, "updated": updated}


# ---------------------------------------------------------------------------
# Plan 199 F5 — Agregadores nuevos. Puros, append-only: ningún contrato del 142
# se toca, y `burn`/`breakdown`/`summarize` siguen exactamente igual.
# ---------------------------------------------------------------------------

def burn_stacked(records: list, bucket: str = "day", group_by: str = "runtime") -> dict:
    """Como `burn`, pero cada punto trae el desglose por grupo.

    Sirve para ver de dónde sale el gasto en el tiempo, no solo cuánto: un pico
    puede ser "un runtime se disparó" o "todos subieron parejo", y son problemas
    distintos.
    """
    if group_by not in ("runtime", "model", "agent_type"):
        group_by = "runtime"

    dated = [r for r in records if r.started_at is not None]
    if not dated:
        return {"bucket": bucket, "group_by": group_by, "series": [], "groups": []}

    por_bucket: dict = {}
    grupos: set = set()
    for r in dated:
        inicio = _bucket_start(r.started_at, bucket)
        clave = _dim_key(r, group_by)
        grupos.add(clave)
        acumulado = por_bucket.setdefault(inicio, {})
        if r.row.cost_usd is not None and _billable(r.row.cost_kind):
            acumulado[clave] = round(acumulado.get(clave, 0.0) + r.row.cost_usd, 6)
        else:
            acumulado.setdefault(clave, 0.0)

    series = [
        {
            "bucket": _bucket_key(inicio, bucket),
            "groups": dict(sorted(por_bucket[inicio].items())),
            "billable_usd": round(sum(por_bucket[inicio].values()), 6),
        }
        for inicio in sorted(por_bucket)
    ]
    return {"bucket": bucket, "group_by": group_by,
            "series": series, "groups": sorted(grupos)}


def heatmap(records: list) -> dict:
    """Gasto por día de semana × hora.

    Responde "¿cuándo se gasta?", que es lo que permite ver si el gasto se
    concentra en horario laboral o si hay algo corriendo de madrugada.
    """
    celdas: dict = {}
    for r in records:
        if r.started_at is None:
            continue
        clave = (r.started_at.weekday(), r.started_at.hour)
        acumulado = celdas.setdefault(clave, {"billable_usd": 0.0, "runs": 0})
        if r.row.cost_usd is not None and _billable(r.row.cost_kind):
            acumulado["billable_usd"] = round(
                acumulado["billable_usd"] + r.row.cost_usd, 6)
        acumulado["runs"] += 1

    salida = [
        {"weekday": d, "hour": h,
         "billable_usd": v["billable_usd"], "runs": v["runs"]}
        for (d, h), v in sorted(celdas.items())
    ]
    return {
        "cells": salida,
        "max_billable_usd": max((c["billable_usd"] for c in salida), default=0.0),
    }


def distribution(records: list, bins: int = 20) -> dict:
    """Histograma del costo por corrida.

    Un promedio esconde la forma: 100 corridas baratas y una carísima dan el
    mismo promedio que 101 medianas, y no son la misma situación.

    Solo entran las corridas CON costo conocido: una sin costo no es una de $0.
    """
    bins = max(1, min(int(bins or 1), 50))
    costos = [r.row.cost_usd for r in records
              if r.row.cost_usd is not None]

    if not costos:
        return {"bins": [], "total": 0, "min": None, "max": None}

    minimo, maximo = min(costos), max(costos)
    if maximo == minimo:
        # Todo el mismo valor: un solo bin, o el ancho sería cero.
        return {"bins": [{"lo": minimo, "hi": maximo, "count": len(costos)}],
                "total": len(costos), "min": minimo, "max": maximo}

    ancho = (maximo - minimo) / bins
    conteos = [0] * bins
    for c in costos:
        indice = int((c - minimo) / ancho)
        if indice >= bins:      # el máximo exacto cae en el último bin
            indice = bins - 1
        conteos[indice] += 1

    return {
        "bins": [
            {"lo": round(minimo + i * ancho, 6),
             "hi": round(minimo + (i + 1) * ancho, 6),
             "count": conteos[i]}
            for i in range(bins)
        ],
        "total": len(costos), "min": minimo, "max": maximo,
    }
