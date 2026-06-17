"""Q0.1 — Helper compartido para resolver acceptance criteria de un ticket.

Extrae la lógica antes inline en `self_review._resolve_criteria` como módulo
independiente para que:
  1. `context_enrichment.enrich_blocks` lo inyecte como checklist en el briefing.
  2. `self_review.review_artifact` lo reutilice (sin duplicar la lectura ADO).

Contrato:
  - `resolve(ticket) -> str` — devuelve el texto de AC (puede vacío si no hay).
  - `render_checklist(criteria_text) -> str` — formatea el AC como checklist
    para el agente.
  - Sin efectos secundarios; best-effort; nunca lanza al caller.
"""
from __future__ import annotations

import re


def _strip_html(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", value)).strip()


def resolve(ticket: object) -> str:
    """Devuelve el texto de acceptance criteria del ticket (cadena vacía si no hay).

    Primero lee AcceptanceCriteria; si está vacío usa Description como fallback.
    Usa la misma lógica que `self_review._resolve_criteria` para ser intercambiable.
    """
    try:
        from services.project_context import build_ado_client

        client = build_ado_client(
            project_name=ticket.stacky_project_name,  # type: ignore[attr-defined]
            tracker_project=ticket.project,            # type: ignore[attr-defined]
        )
        payload = client._batch_get([int(ticket.ado_id)])  # type: ignore[attr-defined]
        if not payload:
            return ""
        fields = (payload[0] or {}).get("fields") or {}
        ac = _strip_html(fields.get("Microsoft.VSTS.Common.AcceptanceCriteria"))
        if ac:
            return ac
        return _strip_html(fields.get("System.Description"))
    except Exception:  # noqa: BLE001 — best-effort
        return ""


def render_checklist(criteria_text: str) -> str:
    """Formatea el texto de AC como checklist imperativo para el agente.

    Ejemplo de salida:
        Tu entregable DEBE cumplir, uno por uno:
        - Criterio A
        - Criterio B
    """
    if not criteria_text:
        return ""
    lines = [ln.strip() for ln in criteria_text.splitlines() if ln.strip()]
    if not lines:
        return ""
    items = "\n".join(f"- {ln}" for ln in lines)
    return (
        "Tu entregable DEBE cumplir, uno por uno:\n"
        f"{items}"
    )
