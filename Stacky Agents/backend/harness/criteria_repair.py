"""Q1.1 — Pase correctivo único de criterios de aceptación incumplidos.

Diseño:
  - Se invoca durante el stream del run (evento `result`), mientras el proceso
    sigue vivo y stdin acepta mensajes. Punto de inserción: _on_stream_event en
    cada runner (igual que AutocorrectLoop/F1.3).
  - Llama a `self_review.review_artifact(execution_id, artifact_text)` y cachea
    el resultado para que `apply_to_execution` (U1.2 post-cierre) lo reutilice
    sin re-llamar al LLM (cero doble-costo).
  - Si score < min_score AND criterios incumplidos AND runtime.supports_resume
    AND presupuesto queda: envía UN único mensaje correctivo corto.
  - Re-evalúa UNA vez: cumple → se registra como recovered; no cumple → estado
    will degrade a needs_review vía U1.2.
  - Metadata key: "criteria_repair" = {"attempted", "unmet_before", "recovered"}
    (clave NUEVA, nunca renombra existentes).

Presupuesto compartido: cuenta contra el mismo `retries_budget` del autocorrect.

Sin dependencias nuevas; usa self_review + capabilities existentes.
"""
from __future__ import annotations

import logging
from typing import Callable

from harness.capabilities import CAPABILITIES

logger = logging.getLogger("stacky.criteria_repair")

# Cache en memoria por execution_id: {execution_id: SelfReviewResult}
# Permite que apply_to_execution reutilice el resultado sin re-llamar al LLM.
_REVIEW_CACHE: dict[int, object] = {}


def get_cached_review(execution_id: int) -> object | None:
    """Devuelve el SelfReviewResult cacheado para un execution_id, o None."""
    return _REVIEW_CACHE.get(execution_id)


def attempt_criteria_repair(
    *,
    execution_id: int,
    artifact_text: str,
    runtime: str,
    retries_budget: int,
    retries_used: int,
    send_fn: Callable[[str], bool] | None,
    enabled: bool,
    min_score: float = 0.7,
) -> dict | None:
    """Intenta un pase correctivo si hay criterios incumplidos.

    Args:
        execution_id: ID de la ejecución en curso.
        artifact_text: texto de salida actual del agente.
        runtime: runtime ("claude_code_cli" | "codex_cli" | "github_copilot").
        retries_budget: techo de reintentos del autocorrect del runtime.
        retries_used: reintentos ya consumidos (autocorrect + run_repair).
        send_fn: función que envía un mensaje y devuelve True si lo aceptó stdin.
        enabled: flag STACKY_CRITERIA_REPAIR_ENABLED.
        min_score: umbral de score (STACKY_SELF_REVIEW_MIN_SCORE).

    Returns:
        dict con {"attempted", "unmet_before", "recovered"} si aplica, None si no.
    """
    if not enabled:
        return None

    caps = CAPABILITIES.get(runtime)
    if caps is None or not caps.supports_resume:
        return None

    if retries_used >= retries_budget > 0:
        return None

    if send_fn is None:
        return None

    # Invocar self_review y cachear
    try:
        from services.self_review import review_artifact
        result = review_artifact(execution_id=execution_id, artifact_text=artifact_text)
        _REVIEW_CACHE[execution_id] = result
    except Exception:  # noqa: BLE001
        logger.warning("criteria_repair: review_artifact falló, saliendo", exc_info=True)
        return None

    if result.skipped_reason is not None:
        # Sin criterios o error → no hay nada que reparar
        return None

    if result.score >= min_score:
        # Ya cumple → no hay pase correctivo
        return None

    unmet = [c["criterion"] for c in result.checklist if not c.get("met")]
    if not unmet:
        return None

    # Construir mensaje correctivo corto
    lista = "\n".join(f"- {c}" for c in unmet)
    msg = (
        "Estos criterios de aceptación NO se cumplieron:\n"
        f"{lista}\n\n"
        "Corregí SOLO eso, manteniendo el resto del entregable; mismo formato."
    )

    try:
        accepted = send_fn(msg)
    except Exception:  # noqa: BLE001
        accepted = False

    if not accepted:
        logger.debug("criteria_repair: send_fn rechazó el mensaje (proceso no activo)")
        return {"attempted": False, "unmet_before": unmet, "recovered": False}

    # accepted=True → el pase se envió. El runner re-leerá el output; la
    # re-evaluación la hace apply_to_execution después del cierre (U1.2).
    logger.info(
        "criteria_repair: pase correctivo enviado (exec=%s, unmet=%d)",
        execution_id,
        len(unmet),
    )
    return {"attempted": True, "unmet_before": unmet, "recovered": None}  # None = pendiente


def mark_recovery(execution_id: int, recovered: bool) -> None:
    """Actualiza el sello 'recovered' en la DB después de la re-evaluación post-run."""
    try:
        from db import session_scope
        from models import AgentExecution
        import json

        with session_scope() as session:
            row = session.get(AgentExecution, execution_id)
            if row is None:
                return
            md = row.metadata_dict
            repair = md.get("criteria_repair")
            if not isinstance(repair, dict):
                return
            repair["recovered"] = recovered
            md["criteria_repair"] = repair
            row.metadata_dict = md
    except Exception:  # noqa: BLE001
        logger.debug("criteria_repair: mark_recovery falló (no crítico)", exc_info=True)
