"""KPI engine determinístico para PM Intelligence Suite — Fase 1 MVP.

Sin IA, sin heurísticas con confidence inventada. Solo fórmulas verificables
sobre snapshots de work items y sus revisiones (state transitions).

Fórmulas implementadas (plan v2 §12):
- aging_days        — días desde created hasta now (o closed si está cerrado)
- cycle_time_days   — desde primera entrada a estado activo hasta closed
- lead_time_days    — desde created hasta closed
- blocked_time_days — suma de tiempo en estados de tipo blocked
- reopen_count      — transiciones de done → active
- sprint_completion_rate — points completados / committed (o items si no hay points)

Estados configurables vía StateMap. Default refleja convención ADO estándar.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable


# ── Configuración de estados (override-able por proyecto si hace falta) ────────
@dataclass(frozen=True)
class StateMap:
    """Mapeo de estados ADO a categorías PM determinísticas.

    Compara case-insensitive. Default cubre la convención más común (Agile, Scrum,
    Basic, CMMI). Para proyectos con estados custom, instanciar con sets propios.
    """
    active: frozenset[str] = frozenset({"in progress", "doing", "active", "committed", "approved"})
    done: frozenset[str] = frozenset({"done", "closed", "resolved", "completed"})
    blocked: frozenset[str] = frozenset({"blocked", "on hold", "waiting"})
    new: frozenset[str] = frozenset({"new", "to do", "proposed", "open"})

    def category(self, state: str | None) -> str:
        if not state:
            return "unknown"
        s = state.lower().strip()
        if s in self.done:
            return "done"
        if s in self.blocked:
            return "blocked"
        if s in self.active:
            return "active"
        if s in self.new:
            return "new"
        return "unknown"


DEFAULT_STATE_MAP = StateMap()


# ── KPIs por work item ─────────────────────────────────────────────────────────

def compute_aging_days(
    work_item: dict,
    *,
    now: datetime | None = None,
    state_map: StateMap = DEFAULT_STATE_MAP,
) -> float | None:
    """Días transcurridos desde la creación hasta hoy (o hasta cierre si está done)."""
    created = work_item.get("created_at")
    if not isinstance(created, datetime):
        return None
    if state_map.category(work_item.get("state")) == "done":
        closed = work_item.get("closed_at")
        if isinstance(closed, datetime):
            return _days_between(created, closed)
    return _days_between(created, now or datetime.utcnow())


def compute_cycle_time_days(
    transitions: list[dict],
    *,
    state_map: StateMap = DEFAULT_STATE_MAP,
) -> float | None:
    """Cycle time = primera entrada a 'active' → primera entrada a 'done'.

    Devuelve None si no hay alguna de las dos transiciones (work item no cerrado
    o sin paso por active).
    """
    first_active: datetime | None = None
    first_done: datetime | None = None
    for t in transitions:
        cat = state_map.category(t.get("state"))
        entered = t.get("entered_at")
        if not isinstance(entered, datetime):
            continue
        if cat == "active" and first_active is None:
            first_active = entered
        elif cat == "done" and first_done is None and first_active is not None:
            first_done = entered
            break
    if first_active is None or first_done is None:
        return None
    return _days_between(first_active, first_done)


def compute_lead_time_days(work_item: dict) -> float | None:
    """Lead time = created → closed. Solo aplica a work items cerrados."""
    created = work_item.get("created_at")
    closed = work_item.get("closed_at")
    if not isinstance(created, datetime) or not isinstance(closed, datetime):
        return None
    return _days_between(created, closed)


def compute_blocked_time_days(
    transitions: list[dict],
    *,
    now: datetime | None = None,
    state_map: StateMap = DEFAULT_STATE_MAP,
) -> float:
    """Suma de tiempo total que el work item estuvo en estados de tipo blocked.

    Si la última transición es a 'blocked' y el ítem sigue ahí, se cuenta hasta `now`.
    """
    if not transitions:
        return 0.0
    cutoff = now or datetime.utcnow()
    total = 0.0
    for i, t in enumerate(transitions):
        if state_map.category(t.get("state")) != "blocked":
            continue
        entered = t.get("entered_at")
        if not isinstance(entered, datetime):
            continue
        if i + 1 < len(transitions):
            next_entered = transitions[i + 1].get("entered_at")
            exit_at = next_entered if isinstance(next_entered, datetime) else cutoff
        else:
            exit_at = cutoff
        total += _days_between(entered, exit_at)
    return round(total, 4)


def compute_reopen_count(
    transitions: list[dict],
    *,
    state_map: StateMap = DEFAULT_STATE_MAP,
) -> int:
    """Cantidad de veces que el work item pasó de done → (active|new|blocked)."""
    if len(transitions) < 2:
        return 0
    reopens = 0
    for prev, curr in zip(transitions, transitions[1:]):
        prev_cat = state_map.category(prev.get("state"))
        curr_cat = state_map.category(curr.get("state"))
        if prev_cat == "done" and curr_cat in {"active", "new", "blocked"}:
            reopens += 1
    return reopens


# ── KPIs agregados de sprint ───────────────────────────────────────────────────

@dataclass
class SprintKPIs:
    """KPIs determinísticos de un sprint. Sin confidence — todos son cálculos exactos."""
    sprint_id: str
    sprint_name: str
    total_items: int = 0
    done_items: int = 0
    active_items: int = 0
    blocked_items: int = 0
    new_items: int = 0
    committed_story_points: float = 0.0
    completed_story_points: float = 0.0
    completion_rate_pct: float = 0.0
    bug_count: int = 0
    bug_rate_pct: float = 0.0
    avg_aging_days: float | None = None
    avg_cycle_time_days: float | None = None
    items_without_estimation: int = 0
    items_without_owner: int = 0
    days_remaining: int | None = None
    data_quality_warnings: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "sprint_id": self.sprint_id,
            "sprint_name": self.sprint_name,
            "total_items": self.total_items,
            "done_items": self.done_items,
            "active_items": self.active_items,
            "blocked_items": self.blocked_items,
            "new_items": self.new_items,
            "committed_story_points": self.committed_story_points,
            "completed_story_points": self.completed_story_points,
            "completion_rate_pct": self.completion_rate_pct,
            "bug_count": self.bug_count,
            "bug_rate_pct": self.bug_rate_pct,
            "avg_aging_days": self.avg_aging_days,
            "avg_cycle_time_days": self.avg_cycle_time_days,
            "items_without_estimation": self.items_without_estimation,
            "items_without_owner": self.items_without_owner,
            "days_remaining": self.days_remaining,
            "data_quality_warnings": self.data_quality_warnings,
        }


def compute_sprint_kpis(
    *,
    sprint: dict,
    work_items: Iterable[dict],
    transitions_by_ado_id: dict[int, list[dict]] | None = None,
    now: datetime | None = None,
    state_map: StateMap = DEFAULT_STATE_MAP,
) -> SprintKPIs:
    """Calcula todos los KPIs MVP para un sprint dado.

    Args:
        sprint: dict normalizado de iteración (con id, name, start_date, end_date).
        work_items: iterable de work items NORMALIZADOS (post pm_normalizer).
        transitions_by_ado_id: mapa opcional ado_id → lista de transiciones.
        now: timestamp de referencia (default: utcnow).
        state_map: configuración de mapeo de estados.
    """
    now = now or datetime.utcnow()
    transitions_by_ado_id = transitions_by_ado_id or {}

    items = list(work_items)
    kpis = SprintKPIs(
        sprint_id=str(sprint.get("id") or sprint.get("path") or "unknown"),
        sprint_name=str(sprint.get("name") or "unknown"),
    )

    aging_values: list[float] = []
    cycle_values: list[float] = []

    for wi in items:
        kpis.total_items += 1
        cat = state_map.category(wi.get("state"))
        if cat == "done":
            kpis.done_items += 1
        elif cat == "active":
            kpis.active_items += 1
        elif cat == "blocked":
            kpis.blocked_items += 1
        elif cat == "new":
            kpis.new_items += 1

        sp = wi.get("story_points")
        if isinstance(sp, (int, float)):
            kpis.committed_story_points += float(sp)
            if cat == "done":
                kpis.completed_story_points += float(sp)
        else:
            kpis.items_without_estimation += 1

        if not wi.get("assigned_to"):
            kpis.items_without_owner += 1

        wit = (wi.get("work_item_type") or "").lower()
        if wit == "bug":
            kpis.bug_count += 1

        aging = compute_aging_days(wi, now=now, state_map=state_map)
        if aging is not None:
            aging_values.append(aging)

        transitions = transitions_by_ado_id.get(int(wi["ado_id"])) if wi.get("ado_id") else None
        if transitions:
            ct = compute_cycle_time_days(transitions, state_map=state_map)
            if ct is not None:
                cycle_values.append(ct)

    if kpis.committed_story_points > 0:
        kpis.completion_rate_pct = round(
            100.0 * kpis.completed_story_points / kpis.committed_story_points, 2
        )
    elif kpis.total_items > 0:
        kpis.completion_rate_pct = round(100.0 * kpis.done_items / kpis.total_items, 2)

    if kpis.total_items > 0:
        kpis.bug_rate_pct = round(100.0 * kpis.bug_count / kpis.total_items, 2)

    if aging_values:
        kpis.avg_aging_days = round(sum(aging_values) / len(aging_values), 2)
    if cycle_values:
        kpis.avg_cycle_time_days = round(sum(cycle_values) / len(cycle_values), 2)

    end = sprint.get("end_date")
    if isinstance(end, datetime):
        delta = end - now
        kpis.days_remaining = max(0, delta.days)

    if kpis.total_items > 0 and kpis.items_without_estimation > 0:
        pct_missing = round(100.0 * kpis.items_without_estimation / kpis.total_items, 1)
        if pct_missing >= 25:
            kpis.data_quality_warnings.append({
                "warning_type": "missing_story_points",
                "count": kpis.items_without_estimation,
                "percentage": pct_missing,
                "impact": "completion_rate_pct usa items en lugar de story points",
            })
    if kpis.total_items == 0:
        kpis.data_quality_warnings.append({
            "warning_type": "empty_sprint",
            "count": 0,
            "percentage": 0,
            "impact": "sprint sin work items asociados",
        })

    return kpis


# ── helpers privados ──────────────────────────────────────────────────────────

def _days_between(start: datetime, end: datetime) -> float:
    seconds = (end - start).total_seconds()
    return round(seconds / 86400.0, 4)
