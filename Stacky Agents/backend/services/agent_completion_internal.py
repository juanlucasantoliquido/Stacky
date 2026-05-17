"""Helper interno de cierre de ejecuciones — usada por múltiples callers.

Esta función centraliza el path de:
  1. Marcar AgentExecution como terminal (completed | error | cancelled).
  2. Actualizar stacky_status del ticket + escribir TicketStatusEvent.
  3. Disparar ado_publisher.publish_from_execution si corresponde (auto-publish
     server-side, con dedupe SHA en la tabla agent_html_publish).

Callers:
  - api.tickets.set_stacky_status_by_ado (PATCH /stacky-status legacy)
  - api.tickets.finish_work (parcial — finish_work hace más cosas)
  - services.output_watcher (cierre automático por filesystem)

Beneficios de extraerlo:
  - Una sola lógica de auto-publish (antes había tres copias divergiendo).
  - Idempotencia uniforme: si execution ya está terminal, retorna no-op.
  - Audit trail consistente (mismos campos de SystemLog).
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from db import session_scope
from models import AgentExecution, Ticket
from services import ticket_status

logger = logging.getLogger("stacky.completion_internal")

_TERMINAL_STATUSES = frozenset({"completed", "error", "cancelled"})


@dataclass
class CloseResult:
    """Resultado de un intento de cierre."""

    ok: bool
    execution_id: int
    ticket_id: int | None
    final_status: str
    already_terminal: bool = False
    publish: dict = field(default_factory=lambda: {"skipped": True, "reason": "not_attempted"})
    ado_state_change: dict = field(default_factory=lambda: {"skipped": True, "reason": "not_requested"})
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "execution_id": self.execution_id,
            "ticket_id": self.ticket_id,
            "final_status": self.final_status,
            "already_terminal": self.already_terminal,
            "publish": self.publish,
            "ado_state_change": self.ado_state_change,
            "error": self.error,
        }


def close_execution_with_publish(
    *,
    execution_id: int,
    triggered_by: str,
    final_status: str = "completed",
    html_output_path: str | None = None,
    user: str = "system",
    reason: str | None = None,
    completion_source: str | None = None,
    agent_type_hint: str | None = None,
    auto_publish: bool | None = None,
    target_ado_state: str | None = None,
) -> CloseResult:
    """Cierra una AgentExecution `running`/`queued` y dispara auto-publish si corresponde.

    Idempotente: si la execution ya está en estado terminal, retorna
    `already_terminal=True` y no toca nada.

    Args:
        execution_id: ID de la AgentExecution a cerrar.
        triggered_by: etiqueta corta que se propaga a ado_publisher.publish_from_execution
            y a SystemLog. Ej: "patch_endpoint" | "output_watcher_mode_b" | "finish_work".
        final_status: "completed" | "error" | "cancelled". Default "completed".
        html_output_path: ruta del HTML del agente (set como attr en la execution).
            Si está presente y final_status="completed", habilita auto-publish.
        user: identificador del actor que dispara el cierre (para audit).
        reason: texto libre que se loguea como reason del TicketStatusEvent.
        completion_source: campo de auditoría P2 ("manual" | "agent" | "recovery" | ...).
        agent_type_hint: si se provee, se incluye en on_execution_end (para hooks).
        auto_publish: None = decide por env STACKY_LEGACY_AUTO_PUBLISH. True/False = forzar.

    Returns:
        CloseResult con detalle del outcome.
    """
    if final_status not in _TERMINAL_STATUSES:
        return CloseResult(
            ok=False,
            execution_id=execution_id,
            ticket_id=None,
            final_status=final_status,
            error=f"final_status inválido: {final_status!r}",
        )

    ticket_id: int | None = None
    agent_type: str | None = None
    already_terminal = False

    # ── Paso 1: transicionar execution row ────────────────────────────────────
    with session_scope() as session:
        exec_row = session.get(AgentExecution, execution_id)
        if exec_row is None:
            return CloseResult(
                ok=False,
                execution_id=execution_id,
                ticket_id=None,
                final_status=final_status,
                error="execution_not_found",
            )

        ticket_id = exec_row.ticket_id
        agent_type = agent_type_hint or exec_row.agent_type

        if exec_row.status in _TERMINAL_STATUSES:
            already_terminal = True
        else:
            exec_row.status = final_status
            if exec_row.completed_at is None:
                exec_row.completed_at = datetime.utcnow()
            if final_status == "error" and reason and not exec_row.error_message:
                exec_row.error_message = reason
            if html_output_path and hasattr(exec_row, "html_output_path"):
                exec_row.html_output_path = html_output_path
            if completion_source and hasattr(exec_row, "completion_source"):
                exec_row.completion_source = completion_source

    # ── Paso 2: stacky_status + TicketStatusEvent (no-op si idempotente) ──────
    if not already_terminal and ticket_id is not None:
        try:
            ticket_status.on_execution_end(
                ticket_id=ticket_id,
                execution_id=execution_id,
                final_status=final_status,
                agent_type=agent_type,
                error=reason if final_status == "error" else None,
                # Para final_status != error, propagamos el reason del caller
                # como reason_override (e.g. el output_watcher pone su marca
                # "output_watcher mode_b: ..." que sirve para audit/dedup).
                reason_override=reason if final_status != "error" else None,
                metadata_override={"triggered_by": triggered_by} if triggered_by else None,
            )
        except Exception:
            logger.exception(
                "[exec=%s] on_execution_end falló — la execution row ya fue actualizada",
                execution_id,
            )

    # ── Paso 3: decidir auto-publish ──────────────────────────────────────────
    # Importante: el publish puede correr incluso si ya estaba terminal, siempre
    # que se haya pasado un html_output_path nuevo y auto_publish esté habilitado.
    # Esto cubre el race Modo A → Modo B del output_watcher: si Modo A cerró el
    # Epic antes de que Modo B detectara comment.html, Modo B aún debe publicar.
    # El dedup SHA-256 en agent_html_publish evita doble-publish.
    publish_result: dict

    if final_status != "completed":
        publish_result = {"skipped": True, "reason": "status_not_completed"}
    elif not html_output_path:
        publish_result = {
            "skipped": True,
            "reason": "html_output_path_missing"
            if not already_terminal
            else "already_terminal_no_html",
        }
    else:
        publish_enabled = _should_auto_publish(auto_publish)
        if not publish_enabled:
            publish_result = {"skipped": True, "reason": "auto_publish_disabled"}
        else:
            publish_result = _attempt_publish(execution_id=execution_id, triggered_by=triggered_by)

    # ── Paso 4: transición de System.State en ADO ────────────────────────────
    # Solo si target_ado_state explícito + publish.ok + ticket tiene ado_id.
    # Si publish falló/skipeó, NO cambiamos estado (evita ticket "Done" sin
    # comentario publicado).
    state_result: dict
    if not target_ado_state:
        state_result = {"skipped": True, "reason": "not_requested"}
    elif not publish_result.get("ok"):
        state_result = {
            "skipped": True,
            "reason": "publish_not_ok",
            "publish_status": publish_result.get("reason") or publish_result.get("event"),
        }
    else:
        state_result = _attempt_state_change(
            ticket_id=ticket_id,
            target_state=target_ado_state,
            execution_id=execution_id,
        )

    return CloseResult(
        ok=True,
        execution_id=execution_id,
        ticket_id=ticket_id,
        final_status=final_status,
        already_terminal=already_terminal,
        publish=publish_result,
        ado_state_change=state_result,
    )


# ── Helpers ──────────────────────────────────────────────────────────────────


def _should_auto_publish(override: bool | None) -> bool:
    """Decide si auto-publish está habilitado.

    - Si `override` es True/False, gana.
    - Si es None, lee STACKY_LEGACY_AUTO_PUBLISH (default "on").
    """
    if override is not None:
        return override
    return os.getenv("STACKY_LEGACY_AUTO_PUBLISH", "on").lower().strip() != "off"


def _attempt_state_change(
    *, ticket_id: int | None, target_state: str, execution_id: int,
) -> dict:
    """Aplica `target_state` al System.State del work item ADO del ticket.

    Cualquier excepción se convierte en `state_change.failed`.
    """
    if ticket_id is None:
        return {"skipped": True, "reason": "no_ticket_id"}

    # Necesitamos ado_id para llamar a AdoClient
    ado_id: int | None = None
    try:
        with session_scope() as session:
            ticket = session.get(Ticket, ticket_id)
            if ticket is not None:
                ado_id = getattr(ticket, "ado_id", None)
    except Exception:
        logger.exception("[exec=%s] no se pudo leer ado_id para state change", execution_id)
        return {"skipped": True, "reason": "ticket_lookup_failed"}

    if ado_id is None:
        return {"skipped": True, "reason": "no_ado_id"}

    try:
        from services.ado_client import AdoClient
    except ImportError as exc:
        logger.warning(
            "[exec=%s] AdoClient no disponible — state change skipped: %s",
            execution_id, exc,
        )
        return {"skipped": True, "reason": "ado_client_unavailable"}

    try:
        AdoClient().update_work_item_state(int(ado_id), target_state)
        logger.info(
            "[exec=%s] ado state changed → %s (ADO-%s)",
            execution_id, target_state, ado_id,
        )
        return {"ok": True, "to": target_state, "ado_id": ado_id}
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "[exec=%s] update_work_item_state falló — ADO-%s target=%s",
            execution_id, ado_id, target_state,
        )
        return {
            "ok": False,
            "to": target_state,
            "ado_id": ado_id,
            "error": str(exc),
            "type": type(exc).__name__,
        }


def _attempt_publish(*, execution_id: int, triggered_by: str) -> dict:
    """Invoca ado_publisher.publish_from_execution y normaliza el resultado.

    Cualquier excepción se convierte en `publish.failed` (no propaga al caller).
    """
    try:
        from services.ado_publisher import publish_from_execution
    except ImportError as exc:
        logger.warning(
            "[exec=%s] ado_publisher no disponible (%s) — publish skipped",
            execution_id, exc,
        )
        return {
            "skipped": True,
            "reason": "ado_publisher_unavailable",
            "type": "ImportError",
        }

    try:
        pr = publish_from_execution(execution_id, triggered_by=triggered_by)
    except Exception as exc:  # noqa: BLE001
        logger.exception("[exec=%s] publish_from_execution lanzó excepción", execution_id)
        return {
            "ok": False,
            "reason": str(exc),
            "type": type(exc).__name__,
            "event": "publish.failed",
        }

    if pr.ok:
        return {
            "ok": True,
            "status": pr.status,
            "ado_id": pr.ado_id,
            "execution_id": pr.execution_id,
            "html_sha256": pr.html_sha256,
            "ado_response": pr.ado_response,
            "record_id": pr.record_id,
            "event": "publish.succeeded",
        }
    return {
        "ok": False,
        "status": pr.status,
        "reason": pr.reason,
        "execution_id": pr.execution_id,
        "event": "publish.failed",
    }
