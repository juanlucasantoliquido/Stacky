"""Plan 60 F2 — Detector PURO de ediciones humanas en revisiones de ADO.

Funciones puras sobre dicts crudos de /updates (sin red, sin BD).
Todo acceso al shape de ADO via helpers defensivos (_extract_*) que usan .get()
— nunca KeyError aunque el shape cambie (C3).
"""
from __future__ import annotations

from dataclasses import dataclass

_BODY_FIELDS = ("System.Description",)  # campos de cuerpo que rastreamos


@dataclass(frozen=True)
class HumanEdit:
    """Edición humana detectada. C4: NO guarda 'author' (anti-PII por construcción)."""
    ado_id: int
    rev: int
    edited_html: str   # newValue del body field


# ── Extractores defensivos del shape crudo de ADO /updates ────────────────────

def _extract_rev(revision: dict) -> int | None:
    """PURA. revision.get('rev') si es int, si no None."""
    v = revision.get("rev")
    return int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _extract_author(revision: dict) -> str | None:
    """PURA. uniqueName (fallback displayName) de revisedBy, normalizado a lower().
    None si falta o vacío.
    """
    rb = (revision.get("revisedBy") or {})
    name = rb.get("uniqueName") or rb.get("displayName")
    return name.lower().strip() if name and isinstance(name, str) else None


def _extract_body(revision: dict) -> str:
    """PURA. Primer newValue no vacío de _BODY_FIELDS. '' si falta o todo vacío."""
    fields = revision.get("fields") or {}
    for f in _BODY_FIELDS:
        field_dict = fields.get(f) or {}
        nv = field_dict.get("newValue")
        if nv and isinstance(nv, str):
            return nv
    return ""


def _service_identities(csv: str) -> set[str]:
    """PURA. Parsea STACKY_ADO_SERVICE_IDENTITY (CSV) a set normalizado lower()."""
    if not csv or not csv.strip():
        return set()
    return {s.strip().lower() for s in csv.split(",") if s.strip()}


def is_human_edit(
    revision: dict,
    *,
    baseline_rev: int | None,
    baseline_author: str | None,
    service_identities: set[str],
) -> HumanEdit | None:
    """PURA. Aplica las 4 condiciones del §3 del plan 60.

    Devuelve HumanEdit si la revisión es una edición humana aprendible; None si no.
    C4: HumanEdit NO incluye el autor (anti-PII).
    """
    rev = _extract_rev(revision)
    if rev is None:
        return None
    if rev <= (baseline_rev or 0):
        return None

    body = _extract_body(revision)
    if not body:
        return None

    author = _extract_author(revision)
    if service_identities and author in service_identities:
        return None
    if not service_identities and baseline_author and author == baseline_author.lower().strip():
        return None

    # Construimos HumanEdit con ado_id=0 (el caller lo sabe; fill in en ado_edit_learning)
    return HumanEdit(ado_id=0, rev=rev, edited_html=body)


def select_latest_human_edit(
    revisions: list[dict],
    *,
    baseline_rev: int | None,
    baseline_author: str | None,
    service_identities: set[str],
    already_processed_revs: set[int],
) -> HumanEdit | None:
    """PURA. Recorre revisiones DESC por rev, devuelve la MÁS RECIENTE no procesada.

    Solo la revisión más reciente no aprendida → versión humana vigente.
    """
    sorted_revs = sorted(revisions, key=lambda r: (_extract_rev(r) or 0), reverse=True)
    for rev_dict in sorted_revs:
        candidate = is_human_edit(
            rev_dict,
            baseline_rev=baseline_rev,
            baseline_author=baseline_author,
            service_identities=service_identities,
        )
        if candidate is None:
            continue
        if candidate.rev in already_processed_revs:
            continue
        return candidate
    return None
