"""
tech_lead_reviewer.py — Y-05: Stage condicional Tech Lead Reviewer.

Para tickets con alta complejidad, revisa ARQUITECTURA_SOLUCION.md antes de DEV.
Si rechaza, vuelve a PM directamente (evita ciclo costoso DEV+QA fallido).
"""

import logging
import os

logger = logging.getLogger("stacky.tech_lead")

_COMPLEXITY_THRESHOLD = 12  # score de ticket_classifier para activar TL review


def is_tl_review_required(ticket_folder: str, ticket_id: str,
                           threshold: int = None) -> bool:
    """
    Retorna True si el ticket requiere revisión del Tech Lead.
    Usa el ticket_classifier (M-07) para evaluar complejidad.
    """
    th = threshold if threshold is not None else _COMPLEXITY_THRESHOLD
    try:
        from ticket_classifier import classify_ticket
        result = classify_ticket(ticket_folder, ticket_id)
        score = getattr(result, "score", 0) or 0
        logger.debug("[TL] Ticket %s — complexity score: %d (threshold: %d)",
                     ticket_id, score, th)
        return score >= th
    except Exception as e:
        logger.debug("[TL] ticket_classifier no disponible: %s — TL review omitido", e)
        return False


def get_tl_agent_name(agents: dict) -> str:
    """Retorna el nombre del agente Tech Lead, fallback al agente PM."""
    return agents.get("tl", agents.get("pm", "PM-TL STack 3"))
