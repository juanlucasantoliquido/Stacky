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


def _utc_now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


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

        # B2: datos para resolver el transition_state configurado por empleado.
        # El filename del agente se persiste en metadata al lanzar (agent_runner);
        # el proyecto sale del ticket. Se leen dentro del mismo scope para evitar
        # un segundo round-trip a la DB.
        _exec_meta = exec_row.metadata_dict or {}
        agent_filename = _exec_meta.get("agent_filename") or _exec_meta.get("vscode_agent_filename")
        ticket_obj = session.get(Ticket, ticket_id) if ticket_id else None
        stacky_project_name = getattr(ticket_obj, "stacky_project_name", None) if ticket_obj else None

        if exec_row.status in _TERMINAL_STATUSES:
            already_terminal = True
        else:
            exec_row.status = final_status
            if exec_row.completed_at is None:
                exec_row.completed_at = datetime.utcnow()
            if final_status == "error" and reason and not exec_row.error_message:
                exec_row.error_message = reason
            # html_output_path y completion_source ahora son columnas reales
            # (Fase 1 plan creacion-tareas-comentarios-100-efectiva). Antes eran
            # atributos dinamicos que no persistian; el comentario los seteaba en
            # memoria pero ado_publisher no los veia tras un restart.
            if html_output_path:
                exec_row.html_output_path = html_output_path
            if completion_source:
                exec_row.completion_source = completion_source

    # R0.1/R0.2 — flush incremental y reap DESPUES de marcar estado en DB.
    if not already_terminal:
        try:
            from config import config as _cfg
            if _cfg.STACKY_RUNNER_REAP_ON_CLOSE_ENABLED:
                if _cfg.STACKY_LOG_FLUSH_INCREMENTAL_ENABLED:
                    import log_streamer as _ls
                    _ls.flush(execution_id)
                from services.runner_reap import reap_by_db
                reap_by_db(execution_id)
        except Exception:  # noqa: BLE001
            logger.debug("[exec=%s] reap_by_db fallo (no critico)", execution_id, exc_info=True)

    # ── Paso 2: stacky_status + TicketStatusEvent (no-op si idempotente) ──────
    # U1.2: self-review contra acceptance criteria (modo annotate/gate).
    # Se ejecuta antes de publicar para poder degradar a needs_review en mode=gate.
    if not already_terminal and final_status == "completed":
        try:
            from services import self_review

            review_outcome = self_review.apply_to_execution(execution_id=execution_id)
            if review_outcome.get("status") == "needs_review":
                final_status = "needs_review"
        except Exception:
            logger.exception("[exec=%s] self_review.apply_to_execution falló (fail-open)", execution_id)

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

    publish_mode = _resolve_publish_mode(project_name=stacky_project_name)
    if final_status == "completed" and publish_mode == "review":
        _set_publish_hold(
            execution_id=execution_id,
            html_output_path=html_output_path,
            triggered_by=triggered_by,
        )
        return CloseResult(
            ok=True,
            execution_id=execution_id,
            ticket_id=ticket_id,
            final_status=final_status,
            already_terminal=already_terminal,
            publish={"skipped": True, "reason": "review_mode_hold"},
            ado_state_change={"skipped": True, "reason": "review_mode_hold"},
        )

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

    # ── Paso 3.5 (B2): resolver el estado de transición configurado ───────────
    # Si el caller no pasó un target explícito, intentamos derivarlo de la config
    # de workflow del empleado (transition_state) que hoy era write-only: se
    # guardaba en config.json pero nada lo consumía al terminar. Sólo en cierres
    # exitosos (completed); el gateo por publish.ok del Paso 4 sigue vigente.
    effective_target = target_ado_state
    target_source = "caller" if target_ado_state else None
    if effective_target is None and final_status in {"completed", "error", "needs_review"}:
        effective_target = _resolve_transition_state_from_config(
            project_name=stacky_project_name,
            agent_type=agent_type,
            agent_filename=agent_filename,
            final_status=final_status,
            execution_id=execution_id,
        )
        if effective_target:
            target_source = "employee_config"

    # ── Paso 4: transición de System.State en ADO ────────────────────────────
    # Solo si hay target (explícito o resuelto de config) + publish.ok + ado_id.
    # Si publish falló/skipeó, NO cambiamos estado (evita ticket "Done" sin
    # comentario publicado).
    state_result: dict
    if not effective_target:
        state_result = {"skipped": True, "reason": "not_requested"}
    elif final_status == "completed" and not publish_result.get("ok"):
        state_result = {
            "skipped": True,
            "reason": "publish_not_ok",
            "publish_status": publish_result.get("reason") or publish_result.get("event"),
        }
    else:
        state_result = _attempt_state_change(
            ticket_id=ticket_id,
            target_state=effective_target,
            execution_id=execution_id,
        )
        if isinstance(state_result, dict):
            state_result.setdefault("source", target_source)

    if final_status in {"error", "needs_review"}:
        try:
            from services import ado_feedback

            ado_feedback.comment_run_outcome(execution_id)
        except Exception:
            logger.exception("[exec=%s] ado_feedback falló en close_execution_with_publish", execution_id)

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


def _infer_agent_type_from_filename(filename: str) -> str:
    """Infiere el agent_type a partir del nombre del .agent.md (misma heurística
    que api/agents._infer_agent_type_from_filename y el frontend)."""
    f = (filename or "").lower()
    if "business" in f or "negocio" in f:
        return "business"
    if "functional" in f or "funcional" in f:
        return "functional"
    if "technical" in f or "tecnic" in f:
        return "technical"
    if "dev" in f or "desarrollador" in f:
        return "developer"
    if "qa" in f or "test" in f:
        return "qa"
    return "custom"


def _resolve_transition_state_from_config(
    *,
    project_name: str | None,
    agent_type: str | None,
    agent_filename: str | None,
    final_status: str,
    execution_id: int,
) -> str | None:
    """B2 — Resuelve el `transition_state` configurado por empleado para este cierre.

    Mapeo `(project, agent) → transition_state`:
      1. Si la execution persistió el filename del agente, lee directo
         `agent_workflow_configs[<filename>].transition_state`.
      2. Fallback: busca en los workflow configs del proyecto el primero cuyo tipo
         inferido coincida con `agent_type` y tenga `transition_state`.

    Devuelve None si no hay config, si el flag está apagado, o ante cualquier error
    (defensivo: nunca rompe el cierre). Gated por STACKY_APPLY_TRANSITION_FROM_CONFIG
    (default "on") para permitir rollback sin redeploy.
    """
    if os.getenv("STACKY_APPLY_TRANSITION_FROM_CONFIG", "on").lower().strip() == "off":
        return None
    if not project_name:
        return None

    try:
        from project_manager import get_agent_workflow_config, get_project_config
    except Exception:  # noqa: BLE001
        logger.debug("[exec=%s] project_manager no disponible para transition_state", execution_id)
        return None

    field_name = "transition_state" if final_status == "completed" else "on_failure_state"

    # (1) por filename persistido en la execution
    if agent_filename:
        try:
            cfg = get_agent_workflow_config(project_name, agent_filename) or {}
            ts = (cfg.get(field_name) or "").strip()
            if ts:
                logger.info(
                    "[exec=%s] %s desde config (filename=%s) → %s",
                    execution_id, field_name, agent_filename, ts,
                )
                return ts
        except Exception:  # noqa: BLE001
            logger.debug("[exec=%s] lookup transition_state por filename falló", execution_id)

    # (2) fallback: por tipo inferido del agente
    if agent_type:
        try:
            proj_cfg = get_project_config(project_name) or {}
            configs = proj_cfg.get("agent_workflow_configs") or {}
            for fname, wf in configs.items():
                if not isinstance(wf, dict):
                    continue
                ts = (wf.get(field_name) or "").strip()
                if ts and _infer_agent_type_from_filename(fname) == agent_type:
                    logger.info(
                        "[exec=%s] %s desde config (tipo=%s, filename=%s) → %s",
                        execution_id, field_name, agent_type, fname, ts,
                    )
                    return ts
        except Exception:  # noqa: BLE001
            logger.debug("[exec=%s] lookup transition_state por tipo falló", execution_id)

    return None


def _should_auto_publish(override: bool | None) -> bool:
    """Decide si auto-publish está habilitado.

    - Si `override` es True/False, gana.
    - Si es None, lee STACKY_LEGACY_AUTO_PUBLISH (default "on").
    """
    if override is not None:
        return override
    return os.getenv("STACKY_LEGACY_AUTO_PUBLISH", "on").lower().strip() != "off"


def _resolve_publish_mode(*, project_name: str | None) -> str:
    """Resuelve el modo de publicación por proyecto: auto|review.

    Default retrocompatible: auto.
    """
    if not project_name:
        return "auto"
    try:
        from project_manager import get_project_config

        cfg = get_project_config(project_name) or {}
        mode = str(cfg.get("publish_mode") or "auto").strip().lower()
        if mode in {"auto", "review"}:
            return mode
    except Exception:
        logger.debug("publish_mode lookup falló project=%s", project_name, exc_info=True)
    return "auto"


def _set_publish_hold(*, execution_id: int, html_output_path: str | None, triggered_by: str) -> None:
    with session_scope() as session:
        row = session.get(AgentExecution, execution_id)
        if row is None:
            return
        md = dict(row.metadata_dict or {})
        md["publish_hold"] = {
            "reason": "review_mode",
            "artifacts": [html_output_path] if html_output_path else [],
            "created_at": _utc_now_iso(),
            "triggered_by": triggered_by,
        }
        row.metadata_dict = md


def publish_execution_from_review(*, execution_id: int, triggered_by: str = "operator_review") -> dict:
    """Libera un publish_hold y publica a ADO por el path real de publisher.

    Retorna dict estable para API; no lanza excepciones fatales.
    """
    ticket_id: int | None = None
    agent_type: str | None = None
    agent_filename: str | None = None
    project_name: str | None = None
    has_hold = False

    with session_scope() as session:
        row = session.get(AgentExecution, execution_id)
        if row is None:
            return {"ok": False, "reason": "execution_not_found", "status": 404}
        md = dict(row.metadata_dict or {})
        hold = md.get("publish_hold") if isinstance(md.get("publish_hold"), dict) else None
        has_hold = hold is not None and not hold.get("released_at")
        if not has_hold:
            return {"ok": False, "reason": "publish_hold_missing", "status": 409}

        ticket_id = row.ticket_id
        agent_type = row.agent_type
        if row.status != "completed":
            return {"ok": False, "reason": "status_not_completed", "status": 409}

        ticket = session.get(Ticket, row.ticket_id) if row.ticket_id else None
        project_name = getattr(ticket, "stacky_project_name", None) if ticket else None
        _exec_meta = row.metadata_dict or {}
        agent_filename = _exec_meta.get("agent_filename") or _exec_meta.get("vscode_agent_filename")

    publish_result = _attempt_publish(execution_id=execution_id, triggered_by=triggered_by)
    state_result: dict = {"skipped": True, "reason": "not_requested"}
    if publish_result.get("ok"):
        target_state = _resolve_transition_state_from_config(
            project_name=project_name,
            agent_type=agent_type,
            agent_filename=agent_filename,
            final_status="completed",
            execution_id=execution_id,
        )
        if target_state:
            state_result = _attempt_state_change(
                ticket_id=ticket_id,
                target_state=target_state,
                execution_id=execution_id,
            )

    if publish_result.get("ok"):
        with session_scope() as session:
            row = session.get(AgentExecution, execution_id)
            if row is not None:
                md = dict(row.metadata_dict or {})
                hold = md.get("publish_hold") if isinstance(md.get("publish_hold"), dict) else {}
                hold["released_at"] = _utc_now_iso()
                hold["released_by"] = triggered_by
                md["publish_hold"] = hold
                row.metadata_dict = md

    return {
        "ok": bool(publish_result.get("ok")),
        "execution_id": execution_id,
        "publish": publish_result,
        "ado_state_change": state_result,
        "status": 200 if publish_result.get("ok") else 500,
    }


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


def _r13_check_publish_guard(execution_id: int) -> bool | None:
    """R1.3 — Comprueba si ya existe marker de intencion de publicacion.

    Retorna True si se detecto un marker existente (idempotent_replay).
    Retorna False si no existe marker.
    Retorna None si el check fallo (fallback al comportamiento actual).
    """
    try:
        from db import session_scope
        from models import AgentExecution
        with session_scope() as session:
            row = session.get(AgentExecution, execution_id)
            if row is None:
                return None
            md = row.metadata_dict or {}
            intent = md.get("publish_intent")
            if intent and intent.get("marker") == "pending":
                # Marker existente: ya se habia intentado el POST.
                return True
        return False
    except Exception:  # noqa: BLE001
        return None  # fallback


def _r13_write_publish_intent(execution_id: int) -> bool:
    """R1.3 — Escribe marker de intencion antes del POST (best-effort).

    Retorna True si el write fue exitoso.
    """
    try:
        from db import session_scope
        from models import AgentExecution
        with session_scope() as session:
            row = session.get(AgentExecution, execution_id)
            if row is None:
                return False
            md = row.metadata_dict or {}
            md["publish_intent"] = {
                "marker": "pending",
                "at": datetime.utcnow().isoformat(),
            }
            row.metadata_dict = md
        return True
    except Exception:  # noqa: BLE001
        return False


def _attempt_publish(*, execution_id: int, triggered_by: str) -> dict:
    """Invoca ado_publisher.publish_from_execution y normaliza el resultado.

    Cualquier excepcion se convierte en `publish.failed` (no propaga al caller).
    R1.3: si STACKY_PUBLISH_IDEMPOTENT_GUARD_ENABLED, persiste intencion antes
    del POST y detecta replays sin re-postear.
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

    # R1.3 — guardia de idempotencia: detecta replays sin re-postear.
    try:
        from config import config as _cfg
        _r13_enabled = _cfg.STACKY_PUBLISH_IDEMPOTENT_GUARD_ENABLED
    except Exception:  # noqa: BLE001
        _r13_enabled = False

    if _r13_enabled:
        existing = _r13_check_publish_guard(execution_id)
        if existing is True:
            # Marker detectado → reintento sin re-postear.
            logger.info("[exec=%s] R1.3 idempotent_replay: marker existente, no re-posea", execution_id)
            return {
                "ok": False,
                "status": "idempotent_replay",
                "reason": "publish_intent marker existente (reintento sin re-POST)",
                "execution_id": execution_id,
                "event": "publish.idempotent_replay",
            }
        if existing is False:
            # No hay marker: escribir intencion antes del POST.
            _r13_write_publish_intent(execution_id)

    try:
        pr = publish_from_execution(execution_id, triggered_by=triggered_by)
    except Exception as exc:  # noqa: BLE001
        logger.exception("[exec=%s] publish_from_execution lanzo excepcion", execution_id)
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
