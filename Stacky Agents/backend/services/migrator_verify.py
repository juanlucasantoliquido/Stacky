"""Plan 74 F8 — Verificación post-migración (count diffs por tipo).

verify_migration compara el plan.counts_by_type contra los items reales
en el destino que portan el marker stacky-migrated:ado:*.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from services.tracker_provider import TrackerQuery

_MARKER_RE = re.compile(r"<!--\s*stacky-migrated:ado:[\w:]+\s*-->")
_TYPE_LABEL_RE = re.compile(r"type::(\w+)")


@dataclass(frozen=True)
class VerificationResult:
    expected_by_type: dict[str, int]
    actual_by_type: dict[str, int]
    gap_by_type: dict[str, int]      # expected - actual; negativo = más de lo esperado
    passed: bool                      # True sii todo gap == 0
    needs_review: list[str]           # tipos con gap > 0


def verify_migration(plan, dest_provider, *, stacky_project: str, db) -> VerificationResult:
    """Verifica que el destino tiene los items migrados esperados.

    expected = plan.counts_by_type.
    actual = items en destino con marker stacky-migrated:ado:*, agrupados por tipo
             inferido de labels (type::X).
    passed = todo gap == 0.
    READ-ONLY: solo invoca fetch_* sobre dest_provider.
    """
    expected = dict(plan.counts_by_type)
    actual: dict[str, int] = {}

    items = dest_provider.fetch_open_items(TrackerQuery())
    for item in items:
        desc = item.get("description") or item.get("description_html") or ""
        if not _MARKER_RE.search(desc):
            continue

        # Inferir tipo desde labels
        labels = item.get("labels") or []
        if isinstance(labels, str):
            labels = [l.strip() for l in labels.split(",")]
        item_type = _infer_type_from_labels(labels) or item.get("item_type") or "Issue"
        actual[item_type] = actual.get(item_type, 0) + 1

    # Calcular gaps
    all_types = set(expected) | set(actual)
    gap: dict[str, int] = {}
    for t in all_types:
        gap[t] = expected.get(t, 0) - actual.get(t, 0)

    needs_review = [t for t in all_types if gap.get(t, 0) > 0]
    passed = not needs_review

    return VerificationResult(
        expected_by_type=expected,
        actual_by_type=actual,
        gap_by_type=gap,
        passed=passed,
        needs_review=sorted(needs_review),
    )


def _infer_type_from_labels(labels: list[str]) -> str | None:
    """Extrae el tipo del label type::X."""
    for label in labels:
        m = _TYPE_LABEL_RE.match(label.strip())
        if m:
            t = m.group(1)
            # Capitalizar para coincidir con ADO
            return t.capitalize() if t else None
    return None
