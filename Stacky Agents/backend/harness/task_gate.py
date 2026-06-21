"""Plan 61 F1 — Gate determinista del flujo funcional (Task).

Todas las funciones son puras y nunca lanzan excepciones al operador.
"""
from __future__ import annotations

from enum import Enum
from typing import NamedTuple


class TaskGateDecision(str, Enum):
    PASS = "pass"
    REPAIR = "repair"
    NEEDS_REVIEW = "needs_review"


class TaskGateVerdict(NamedTuple):
    decision: TaskGateDecision
    defects: list
    blocking: bool


_REPAIRABLE = frozenset({"title_empty", "description_empty", "description_missing_rf"})


def _is_blank(v: object) -> bool:
    if v is None:
        return True
    return not str(v).strip()


def classify_task_defects(payload: dict, plan_de_pruebas_text: str | None) -> dict:
    """Devuelve {code: severity} ordenado. Nunca lanza."""
    if not isinstance(payload, dict):
        payload = {}
    defects: dict[str, str] = {}

    if _is_blank(payload.get("title")):
        defects["title_empty"] = "repair"

    if _is_blank(payload.get("rf_id")):
        defects["rf_id_empty"] = "needs_review"

    desc = payload.get("description_html") or ""
    if _is_blank(desc):
        defects["description_empty"] = "repair"
    else:
        rf_id = str(payload.get("rf_id") or "").strip()
        if rf_id and rf_id not in desc:
            defects["description_missing_rf"] = "repair"

    if _is_blank(plan_de_pruebas_text):
        defects["plan_de_pruebas_empty"] = "needs_review"

    raw_epic = str(payload.get("epic_id") or "").strip()
    if raw_epic and not raw_epic.isdigit():
        defects["epic_id_not_numeric"] = "needs_review"

    return dict(sorted(defects.items()))


def evaluate_task_gate(
    *,
    payload: dict | None,
    plan_de_pruebas_text: str | None,
    blocking_enabled: bool,
) -> TaskGateVerdict:
    """Evalúa el gate sobre el pending-task payload. Nunca lanza."""
    try:
        defects = classify_task_defects(payload or {}, plan_de_pruebas_text)
    except Exception:
        defects = {}

    sorted_codes = sorted(defects.keys())
    severities = set(defects.values())

    has_needs_review = "needs_review" in severities
    has_repair = "repair" in severities

    is_blocking = blocking_enabled and has_needs_review

    if is_blocking:
        decision = TaskGateDecision.NEEDS_REVIEW
    elif has_repair or has_needs_review:
        decision = TaskGateDecision.REPAIR if has_repair else TaskGateDecision.NEEDS_REVIEW
    else:
        decision = TaskGateDecision.PASS

    return TaskGateVerdict(decision=decision, defects=sorted_codes, blocking=is_blocking)
