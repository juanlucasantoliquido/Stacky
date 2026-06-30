"""Plan 56 F2 — Captura de goldens al emitir veredicto humano.

Esta función es el único punto de integración entre el veredicto humano
(human_review_route) y el sistema de golden regression.

Es pura salvo el IO de save_golden. Si falla: silencioso (el veredicto ya se persistió).
"""
from __future__ import annotations

import logging

logger = logging.getLogger("stacky.regression_capture")


def save_goldens_from_review(
    *,
    execution,          # AgentExecution (o duck-type compatible para tests)
    verdict: str,       # "approved" | "approved_with_notes" | "rejected"
    note: str,
) -> None:
    """Deriva y guarda un golden a partir del veredicto humano.

    - RECHAZO → golden negativo basado en la nota.
    - APROBACIÓN → golden positivo basado en el HTML del output del run.
    - Siempre activo (la captura es inocua si el gate está OFF).
    - Nunca lanza: errores → warning en log.
    """
    try:
        from harness.regression_goldens import (
            derive_negative_golden,
            derive_positive_golden,
            save_golden,
        )

        project = getattr(getattr(execution, "ticket", None), "stacky_project_name", None)
        agent_type = getattr(execution, "agent_type", "unknown")
        work_item_type = getattr(getattr(execution, "ticket", None), "work_item_type", "Epic") or "Epic"

        is_approved = verdict in ("approved", "approved_with_notes")
        is_rejected = verdict == "rejected"

        if is_rejected:
            g = derive_negative_golden(
                rejection_note=note or "",
                project=project,
                agent_type=agent_type,
                work_item_type=work_item_type,
            )
            if g is not None:
                save_golden(g)

        elif is_approved:
            raw_output = getattr(execution, "output", None) or ""
            # Extraer HTML limpio; si tickets no disponible, usa output crudo
            try:
                from api.tickets import _extract_epic_html
                clean_html = _extract_epic_html(raw_output)
            except Exception:  # noqa: BLE001
                clean_html = raw_output

            confidence: float | None = None
            try:
                meta = execution.metadata_dict
                confidence = (meta.get("epic_summary") or {}).get("confidence")
                if confidence is not None:
                    confidence = float(confidence)
            except Exception:  # noqa: BLE001
                confidence = None

            g = derive_positive_golden(
                clean_html=clean_html,
                project=project,
                agent_type=agent_type,
                work_item_type=work_item_type,
                confidence=confidence,
            )
            if g is not None:
                save_golden(g)

    except Exception:  # noqa: BLE001
        logger.warning(
            "save_goldens_from_review: fallo no crítico (ejecución=%s)",
            getattr(execution, "id", "?"),
            exc_info=True,
        )
