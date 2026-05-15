"""
agent_completion.py — Servicio AgentCompletionGateway (Plan SSD P1).

Responsabilidades:
- Resolver la AgentExecution activa para un ticket (prioridad estricta §5.1).
- Validar el HTML de salida del agente.
- Construir el «plan de cierre» (resolución → validación → cierre → publish → transición).
- En modo SHADOW: solo simular, sin mutar DB ni ADO. Registrar discrepancias.
- En modo ON (P5): ejecutar el plan real.

Diagrama de resolución (primer match gana):
  1. execution_id explícito → verifica pertenencia + estado activo.
  2. Última AgentExecution activa cuyo agent_type == payload.agent_type.
  3. Si hay exactamente UNA activa (cualquier agent_type) → usar esa + log mismatch.
  4. Cero activas + allow_synthetic_rescue=True → execution sintética kind=rescue.
  5. Cero activas sin flag → 409 no_active_execution.

Estados terminales aceptados por el gateway:
  completed | error | cancelled | needs_review

IMPORTANTE: este módulo NO muta ADO ni DB en modo shadow.
En modo on (P5), el orquestador real se implementará aquí.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any

from db import session_scope
from models import AgentExecution, SystemLog, Ticket

logger = logging.getLogger("stacky.agent_completion_gateway")

# ── Constantes ────────────────────────────────────────────────────────────────

ACTIVE_STATUSES = frozenset({"running", "queued"})
TERMINAL_STATUSES = frozenset({"completed", "error", "cancelled", "needs_review"})

_GATEWAY_SOURCE = "completion_gateway"


# ── Payload v1 ────────────────────────────────────────────────────────────────


@dataclass
class CompletionMetadata:
    html_sha256: str | None = None
    agent_version: str | None = None
    duration_ms: int | None = None

    @classmethod
    def from_dict(cls, d: dict) -> "CompletionMetadata":
        return cls(
            html_sha256=d.get("html_sha256"),
            agent_version=d.get("agent_version"),
            duration_ms=d.get("duration_ms"),
        )

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class CompletionPayload:
    """Payload v1 del endpoint agent-completion."""

    execution_id: int | None
    agent_type: str
    status: str
    html_output_path: str | None
    metadata: CompletionMetadata
    reason: str | None
    allow_synthetic_rescue: bool = False

    @classmethod
    def from_dict(cls, d: dict) -> "CompletionPayload":
        if not d.get("agent_type"):
            raise ValueError("agent_type is required")
        status = d.get("status", "").strip()
        if status not in TERMINAL_STATUSES:
            raise ValueError(
                f"status '{status}' no es un estado terminal válido. "
                f"Aceptados: {sorted(TERMINAL_STATUSES)}"
            )
        return cls(
            execution_id=d.get("execution_id"),
            agent_type=d["agent_type"].strip(),
            status=status,
            html_output_path=d.get("html_output_path"),
            metadata=CompletionMetadata.from_dict(d.get("metadata") or {}),
            reason=d.get("reason"),
            allow_synthetic_rescue=bool(d.get("allow_synthetic_rescue", False)),
        )


# ── Resultado tipado ──────────────────────────────────────────────────────────


@dataclass
class GatewayError:
    http_status: int
    code: str
    message: str
    detail: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"error": {"code": self.code, "message": self.message, **self.detail}}


@dataclass
class ClosurePlanStep:
    step: str
    description: str
    skipped: bool = False
    skip_reason: str | None = None

    def to_dict(self) -> dict:
        d = {"step": self.step, "description": self.description}
        if self.skipped:
            d["skipped"] = True
            d["skip_reason"] = self.skip_reason
        return d


@dataclass
class GatewayResult:
    """Resultado del gateway en modo shadow o on."""

    mode: str                         # "shadow" | "on"
    ok: bool
    would_succeed: bool               # solo informativo en shadow
    correlation_id: str
    ticket_id: int | None
    execution_id: int | None
    agent_type_resolved: str | None
    agent_type_mismatch: bool
    html_sha256: str | None
    plan: list[ClosurePlanStep]
    errors: list[GatewayError]
    discrepancies: list[dict]         # vacío si no hay divergencia con legacy
    duration_ms: int | None = None

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "ok": self.ok,
            "would_succeed": self.would_succeed,
            "correlation_id": self.correlation_id,
            "ticket_id": self.ticket_id,
            "execution_id": self.execution_id,
            "agent_type_resolved": self.agent_type_resolved,
            "agent_type_mismatch": self.agent_type_mismatch,
            "html_sha256": self.html_sha256,
            "plan": [s.to_dict() for s in self.plan],
            "errors": [e.to_dict() for e in self.errors],
            "discrepancies": self.discrepancies,
            "duration_ms": self.duration_ms,
        }


# ── Funciones auxiliares ──────────────────────────────────────────────────────


def _compute_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _emit_system_log(
    *,
    action: str,
    level: str = "INFO",
    ticket_id: int | None = None,
    execution_id: int | None = None,
    user: str | None = None,
    correlation_id: str | None = None,
    context: dict | None = None,
    tags: list[str] | None = None,
    session=None,
) -> None:
    """Persiste un SystemLog directamente en la sesión activa.

    Usa sesión pasada para poder participar en transacciones del llamador.
    Si no hay sesión, abre una propia (para logs fuera de transacción).
    """
    ctx = context or {}
    if correlation_id:
        ctx["correlation_id"] = correlation_id

    row = SystemLog(
        level=level,
        source=_GATEWAY_SOURCE,
        action=action,
        ticket_id=ticket_id,
        execution_id=execution_id,
        user=user,
        context_json=json.dumps(ctx, ensure_ascii=False, default=str),
        tags_json=json.dumps(tags or ["completion_gateway"], ensure_ascii=False),
    )

    if session is not None:
        session.add(row)
    else:
        with session_scope() as s:
            s.add(row)


# ── Resolución de ejecución ───────────────────────────────────────────────────


def _resolve_execution(
    ticket_id: int,
    payload: CompletionPayload,
    correlation_id: str,
    session,
) -> tuple[AgentExecution | None, bool, GatewayError | None]:
    """Resuelve la AgentExecution activa según la prioridad §5.1.

    Returns:
        (execution, agent_type_mismatch, error)
        Si error no es None, la resolución falló.
    """
    # Prioridad 1: execution_id explícito
    if payload.execution_id is not None:
        exec_row = session.get(AgentExecution, payload.execution_id)
        if exec_row is None:
            return None, False, GatewayError(
                http_status=409,
                code="execution_state_invalid",
                message=f"execution_id={payload.execution_id} no existe",
                detail={"execution_id": payload.execution_id},
            )
        if exec_row.ticket_id != ticket_id:
            return None, False, GatewayError(
                http_status=409,
                code="execution_state_invalid",
                message=(
                    f"execution_id={payload.execution_id} pertenece al ticket "
                    f"{exec_row.ticket_id}, no al ticket {ticket_id}"
                ),
                detail={"execution_id": payload.execution_id, "ticket_id": ticket_id},
            )
        if exec_row.status not in ACTIVE_STATUSES:
            return None, False, GatewayError(
                http_status=409,
                code="execution_state_invalid",
                message=(
                    f"execution_id={payload.execution_id} ya está en estado terminal "
                    f"'{exec_row.status}' (esperado: {sorted(ACTIVE_STATUSES)})"
                ),
                detail={"execution_id": payload.execution_id, "current_status": exec_row.status},
            )
        return exec_row, False, None

    # Prioridad 2: última activa con el mismo agent_type
    q = (
        session.query(AgentExecution)
        .filter(
            AgentExecution.ticket_id == ticket_id,
            AgentExecution.status.in_(list(ACTIVE_STATUSES)),
            AgentExecution.agent_type == payload.agent_type,
        )
        .order_by(AgentExecution.started_at.desc())
    )
    matched = q.first()
    if matched is not None:
        return matched, False, None

    # Prioridad 3: exactamente una activa (cualquier agent_type)
    all_active = (
        session.query(AgentExecution)
        .filter(
            AgentExecution.ticket_id == ticket_id,
            AgentExecution.status.in_(list(ACTIVE_STATUSES)),
        )
        .order_by(AgentExecution.started_at.desc())
        .all()
    )
    if len(all_active) == 1:
        logger.warning(
            "gateway resolve: using single active exec with mismatched agent_type "
            "ticket_id=%s exec_id=%s exec_agent_type=%s payload_agent_type=%s corr=%s",
            ticket_id, all_active[0].id, all_active[0].agent_type,
            payload.agent_type, correlation_id,
        )
        return all_active[0], True, None  # mismatch=True

    # Prioridad 4: cero activas + allow_synthetic_rescue
    if len(all_active) == 0:
        if payload.allow_synthetic_rescue:
            # En shadow no se crea; se registra en el plan
            return None, False, None  # se marca como synthetic en el plan
        return None, False, GatewayError(
            http_status=409,
            code="no_active_execution",
            message=(
                f"No hay ejecuciones activas para ticket_id={ticket_id} "
                f"con agent_type='{payload.agent_type}'. "
                "Pase allow_synthetic_rescue=true para crear una execution de rescate."
            ),
            detail={"ticket_id": ticket_id, "agent_type": payload.agent_type},
        )

    # Múltiples activas: ambigüedad
    return None, False, GatewayError(
        http_status=409,
        code="no_active_execution",
        message=(
            f"Hay {len(all_active)} ejecuciones activas para el ticket "
            f"(agent_types: {[e.agent_type for e in all_active]}). "
            "Especifique execution_id explícito para desambiguar."
        ),
        detail={"ticket_id": ticket_id, "active_count": len(all_active)},
    )


# ── Validación de HTML ────────────────────────────────────────────────────────


def _validate_html(
    ado_id: int,
    html_output_path: str | None,
    correlation_id: str,
) -> tuple[str | None, str | None, GatewayError | None]:
    """Valida el HTML del agente.

    Returns:
        (html_content, sha256, error)
    """
    from services import agent_html_output as html_io

    try:
        result = html_io.read_and_validate(ado_id=ado_id, hint=html_output_path)
        sha256 = _compute_sha256(result.html)
        logger.debug(
            "gateway html_valid: ado_id=%s size=%d sha256=%s corr=%s",
            ado_id, result.size_bytes, sha256, correlation_id,
        )
        return result.html, sha256, None
    except html_io.ValidationError as exc:
        logger.warning(
            "gateway html_invalid: ado_id=%s code=%s corr=%s",
            ado_id, exc.code, correlation_id,
        )
        return None, None, GatewayError(
            http_status=422,
            code="html_invalid",
            message=f"HTML inválido: [{exc.code}] {exc.message}",
            detail={"validation_code": exc.code},
        )


# ── Construcción del plan de cierre ──────────────────────────────────────────


def _build_closure_plan(
    execution: AgentExecution | None,
    payload: CompletionPayload,
    html_sha256: str | None,
    agent_type_mismatch: bool,
    is_synthetic: bool,
) -> list[ClosurePlanStep]:
    """Genera el plan de cierre de pasos que se ejecutarían en modo on."""
    plan: list[ClosurePlanStep] = []

    # Paso 1: resolución
    if execution is not None:
        desc = f"Usar AgentExecution id={execution.id} status={execution.status}"
        if agent_type_mismatch:
            desc += f" [MISMATCH: exec.agent_type={execution.agent_type}, payload.agent_type={payload.agent_type}]"
        plan.append(ClosurePlanStep(step="resolve_execution", description=desc))
    elif is_synthetic:
        plan.append(ClosurePlanStep(
            step="resolve_execution",
            description=f"Crear AgentExecution sintética kind=rescue para ticket (allow_synthetic_rescue=true)",
        ))
    else:
        plan.append(ClosurePlanStep(
            step="resolve_execution",
            description="Sin execution activa — bloqueado",
            skipped=True,
            skip_reason="no_active_execution",
        ))

    # Paso 2: validación HTML
    if html_sha256:
        plan.append(ClosurePlanStep(
            step="validate_html",
            description=f"HTML válido sha256={html_sha256[:12]}...",
        ))
    else:
        plan.append(ClosurePlanStep(
            step="validate_html",
            description="HTML inválido o ausente",
            skipped=True,
            skip_reason="html_invalid",
        ))

    # Paso 3: cierre de execution
    if execution is not None or is_synthetic:
        plan.append(ClosurePlanStep(
            step="close_execution",
            description=f"AgentExecution.status → '{payload.status}', completed_at=now()",
        ))
    else:
        plan.append(ClosurePlanStep(
            step="close_execution",
            skipped=True,
            skip_reason="no_execution_resolved",
            description="Saltado por falta de execution",
        ))

    # Paso 4: publish ADO
    if html_sha256 and (execution is not None or is_synthetic):
        plan.append(ClosurePlanStep(
            step="ado_publish",
            description=(
                "ado_publisher.publish_from_execution(execution_id, triggered_by='agent_gateway') "
                "— INSERT AgentHtmlPublish idempotente por (execution_id, html_sha256)"
            ),
        ))
    else:
        plan.append(ClosurePlanStep(
            step="ado_publish",
            skipped=True,
            skip_reason="blocked_by_previous_step",
            description="Saltado: sin HTML válido o sin execution",
        ))

    # Paso 5: transición de estado del ticket
    if execution is not None or is_synthetic:
        plan.append(ClosurePlanStep(
            step="ticket_status_transition",
            description=(
                f"ticket_status.on_execution_end(ticket_id, execution_id, "
                f"final_status='{payload.status}', agent_type='{payload.agent_type}')"
            ),
        ))
    else:
        plan.append(ClosurePlanStep(
            step="ticket_status_transition",
            skipped=True,
            skip_reason="blocked_by_previous_step",
            description="Saltado",
        ))

    # Paso 6: audit seal
    if execution is not None or is_synthetic:
        plan.append(ClosurePlanStep(
            step="audit_seal",
            description="audit_chain.seal(execution_id) → AuditEntry node_hash",
        ))
    else:
        plan.append(ClosurePlanStep(
            step="audit_seal",
            skipped=True,
            skip_reason="blocked_by_previous_step",
            description="Saltado",
        ))

    return plan


# ── Gateway en modo shadow ────────────────────────────────────────────────────


def run_shadow(
    *,
    ado_id: int,
    payload: CompletionPayload,
    user: str | None,
    correlation_id: str,
    legacy_state: dict | None = None,
) -> tuple[GatewayResult, int]:
    """Ejecuta el gateway en modo shadow: solo simula, no escribe.

    Args:
        ado_id: ID ADO del ticket.
        payload: Payload v1 validado.
        user: email del usuario/agente.
        correlation_id: UUID de correlación para esta invocación.
        legacy_state: estado observado del legacy (para detectar discrepancias).

    Returns:
        (GatewayResult, http_status_code)
    """
    t0 = time.monotonic()
    errors: list[GatewayError] = []
    discrepancies: list[dict] = []
    plan: list[ClosurePlanStep] = []
    execution: AgentExecution | None = None
    agent_type_mismatch = False
    html_sha256: str | None = None
    ticket_id: int | None = None
    is_synthetic = False

    logger.info(
        "gateway[shadow] start: ado_id=%s agent_type=%s execution_id=%s corr=%s",
        ado_id, payload.agent_type, payload.execution_id, correlation_id,
    )

    # ── Fase de lectura: todo en una sola session, sin SystemLog writes ────────
    # SystemLogs se escriben FUERA de esta session para evitar deadlock con el
    # stacky_logger background writer que también escribe a system_logs en SQLite.
    with session_scope() as session:
        # 1. Resolver ticket
        ticket = session.query(Ticket).filter(Ticket.ado_id == ado_id).first()
        if ticket is None:
            errors.append(GatewayError(
                http_status=404,
                code="ticket_not_found",
                message=f"No se encontró ticket con ado_id={ado_id}",
                detail={"ado_id": ado_id},
            ))
        else:
            ticket_id = ticket.id

            # 2. Validar HTML (READ ONLY)
            _html_content, html_sha256, html_err = _validate_html(
                ado_id=ado_id,
                html_output_path=payload.html_output_path,
                correlation_id=correlation_id,
            )
            if html_err is not None:
                errors.append(html_err)

            # 3. Resolver execution (READ ONLY)
            execution, agent_type_mismatch, resolve_err = _resolve_execution(
                ticket_id=ticket_id,
                payload=payload,
                correlation_id=correlation_id,
                session=session,
            )
            if resolve_err is not None:
                errors.append(resolve_err)
            elif execution is None and payload.allow_synthetic_rescue:
                is_synthetic = True

            # 4. Construir plan
            plan = _build_closure_plan(
                execution=execution,
                payload=payload,
                html_sha256=html_sha256,
                agent_type_mismatch=agent_type_mismatch,
                is_synthetic=is_synthetic,
            )

    # Capturar ids ANTES de cerrar la session (expire_on_commit=False en la config)
    exec_id_for_log = execution.id if execution else None
    exec_agent_type_for_log = execution.agent_type if execution else payload.agent_type

    would_succeed = len(errors) == 0

    # 5. Detectar discrepancias con legacy (fuera de la session principal)
    if legacy_state is not None and ticket_id is not None:
        discrepancies = _compare_with_legacy(
            gateway_would_succeed=would_succeed,
            gateway_plan=plan,
            legacy_state=legacy_state,
            ticket_id=ticket_id,
            execution_id=exec_id_for_log,
            agent_type_resolved=exec_agent_type_for_log,
            correlation_id=correlation_id,
            session=None,   # abre sesión propia para evitar deadlock con logger
            payload=payload,
            user=user,
        )

    # 6. Log de la invocación shadow (sesión propia)
    if ticket_id is not None:
        _emit_system_log(
            action="shadow.ticket_not_found" if ticket_id is None else "shadow.invocation",
            level="INFO" if would_succeed else "WARNING",
            ticket_id=ticket_id,
            execution_id=exec_id_for_log,
            user=user,
            correlation_id=correlation_id,
            context={
                "ado_id": ado_id,
                "agent_type": payload.agent_type,
                "status": payload.status,
                "mode": "shadow",
                "would_succeed": would_succeed,
                "html_sha256": html_sha256,
                "agent_type_mismatch": agent_type_mismatch,
                "is_synthetic": is_synthetic,
                "plan_steps": [s.step for s in plan],
                "errors": [e.code for e in errors],
                "discrepancy_count": len(discrepancies),
            },
            tags=["completion_gateway", "shadow"],
        )
    else:
        _emit_system_log(
            action="shadow.ticket_not_found",
            level="WARNING",
            correlation_id=correlation_id,
            user=user,
            context={"ado_id": ado_id, "agent_type": payload.agent_type, "mode": "shadow"},
        )

    # 7. Métrica de duración (sesión propia)
    duration_ms = int((time.monotonic() - t0) * 1000)
    _emit_system_log(
        action="metric.completion_gateway",
        level="INFO",
        ticket_id=ticket_id,
        execution_id=exec_id_for_log,
        user=user,
        correlation_id=correlation_id,
        context={
            "metric": "stacky_agent_completion_total",
            "result": "would_succeed" if would_succeed else "would_fail",
            "agent_type": payload.agent_type,
            "mode": "shadow",
            "duration_ms": duration_ms,
        },
        tags=["metric", "completion_gateway"],
    )

    logger.info(
        "gateway[shadow] done: ado_id=%s ticket_id=%s exec_id=%s would_succeed=%s "
        "discrepancies=%d duration_ms=%d corr=%s",
        ado_id, ticket_id,
        execution.id if execution else None,
        would_succeed,
        len(discrepancies),
        duration_ms,
        correlation_id,
    )

    # ticket_not_found: devolver 404 (excepción al "shadow siempre 200")
    has_404 = any(e.http_status == 404 for e in errors)

    result = GatewayResult(
        mode="shadow",
        ok=not has_404,  # 404 es un error real, no un "shadow would_fail"
        would_succeed=would_succeed,
        correlation_id=correlation_id,
        ticket_id=ticket_id,
        execution_id=exec_id_for_log,
        agent_type_resolved=exec_agent_type_for_log if exec_id_for_log else (
            payload.agent_type if is_synthetic else None
        ),
        agent_type_mismatch=agent_type_mismatch,
        html_sha256=html_sha256,
        plan=plan,
        errors=errors,
        discrepancies=discrepancies,
        duration_ms=duration_ms,
    )
    http_status = 404 if has_404 else 200
    return result, http_status


# ── Detección de discrepancias con legacy ─────────────────────────────────────


def _compare_with_legacy(
    *,
    gateway_would_succeed: bool,
    gateway_plan: list[ClosurePlanStep],
    legacy_state: dict,
    ticket_id: int,
    execution_id: int | None,
    agent_type_resolved: str | None,
    correlation_id: str,
    session,
    payload: CompletionPayload,
    user: str | None,
) -> list[dict]:
    """Compara el plan del gateway con el estado observado del legacy.

    Emite SystemLog de discrepancia si hay divergencia.

    Returns:
        Lista de campos divergentes.
    """
    divergence_fields: list[dict] = []

    # Comparar: si legacy marcó success pero gateway habría fallado
    legacy_ok = legacy_state.get("ok", False)
    if legacy_ok and not gateway_would_succeed:
        divergence_fields.append({
            "field": "overall_success",
            "gateway": "would_fail",
            "legacy": "succeeded",
            "impact": "HIGH",
        })

    # Comparar stacky_status resultante
    legacy_status = legacy_state.get("current_status")
    gateway_would_set = payload.status
    if legacy_status and legacy_status != gateway_would_set:
        divergence_fields.append({
            "field": "stacky_status",
            "gateway": gateway_would_set,
            "legacy": legacy_status,
            "impact": "MEDIUM",
        })

    # Comparar execution_id resuelto
    legacy_exec_id = legacy_state.get("execution_id")
    if legacy_exec_id and execution_id and legacy_exec_id != execution_id:
        divergence_fields.append({
            "field": "execution_id",
            "gateway": execution_id,
            "legacy": legacy_exec_id,
            "impact": "HIGH",
        })

    if not divergence_fields:
        return []

    logger.warning(
        "gateway[shadow] discrepancy: ticket_id=%s corr=%s divergence_fields=%s",
        ticket_id, correlation_id, divergence_fields,
    )

    # Escribir logs en sesión propia (no la sesión del llamador) para evitar
    # deadlock con el stacky_logger background writer en SQLite.
    _emit_system_log(
        action="shadow.discrepancy_detected",
        level="WARNING",
        ticket_id=ticket_id,
        execution_id=execution_id,
        user=user,
        correlation_id=correlation_id,
        context={
            "ticket_id": ticket_id,
            "execution_id": execution_id,
            "agent_type_resolved": agent_type_resolved,
            "agent_payload": {
                "agent_type": payload.agent_type,
                "status": payload.status,
                "execution_id": payload.execution_id,
            },
            "gateway_plan": [s.step for s in gateway_plan],
            "legacy_observed": legacy_state,
            "divergence_fields": divergence_fields,
        },
        tags=["completion_gateway", "shadow", "discrepancy"],
        session=None,  # sesión propia para no interferir con el llamador
    )

    # Métrica de discrepancia
    for div in divergence_fields:
        _emit_system_log(
            action="metric.shadow_discrepancy",
            level="WARNING",
            ticket_id=ticket_id,
            user=user,
            correlation_id=correlation_id,
            context={
                "metric": "stacky_shadow_discrepancy_total",
                "kind": div["field"],
                "mode": "shadow",
                "impact": div.get("impact"),
            },
            tags=["metric", "shadow_discrepancy"],
            session=None,  # sesión propia para no interferir con el llamador
        )

    return divergence_fields


# ── Gateway en modo on (P5) ───────────────────────────────────────────────────


def _close_execution(
    execution: AgentExecution,
    payload: CompletionPayload,
    html_sha256: str | None,
    correlation_id: str,
    session,
) -> None:
    """Cierra la AgentExecution en base de datos (paso 3 del plan §4).

    Muta directamente el objeto dentro de la sesión activa.
    No persiste — el commit lo hace el llamador.
    """
    execution.status = payload.status
    execution.completed_at = datetime.utcnow()

    # Persistir completion_source si el campo existe (P2).
    if hasattr(execution, "completion_source"):
        execution.completion_source = "agent_gateway"

    # Persistir html_output_path si el campo existe (P2).
    if hasattr(execution, "html_output_path") and payload.html_output_path:
        execution.html_output_path = payload.html_output_path

    # Persistir sha256 en metadata
    meta = {}
    if hasattr(execution, "metadata_json") and execution.metadata_json:
        try:
            meta = json.loads(execution.metadata_json)
        except (json.JSONDecodeError, TypeError):
            meta = {}
    meta["completion_gateway"] = {
        "html_sha256": html_sha256,
        "correlation_id": correlation_id,
        "agent_version": payload.metadata.agent_version,
        "duration_ms": payload.metadata.duration_ms,
        "reason": payload.reason,
    }
    execution.metadata_json = json.dumps(meta, ensure_ascii=False, default=str)

    logger.debug(
        "gateway[on] close_execution: exec_id=%s status=%s sha256=%s corr=%s",
        execution.id, payload.status,
        html_sha256[:12] if html_sha256 else None,
        correlation_id,
    )


def _publish_to_ado(
    *,
    execution: AgentExecution,
    html_sha256: str | None,
    correlation_id: str,
    session,
) -> dict:
    """Publica el HTML en ADO mediante ado_publisher (paso 4 del plan §4).

    Idempotente: si AgentHtmlPublish ya existe para (execution_id, sha256),
    devuelve el registro existente sin republicar.

    Returns:
        dict con resultado de la publicación: {published: bool, idempotent: bool, ...}
    """
    try:
        from services import ado_publisher  # noqa: PLC0415
        result = ado_publisher.publish_from_execution(
            execution.id,
            triggered_by="agent_gateway",
            html_sha256=html_sha256,
        )
        logger.info(
            "gateway[on] ado_publish ok: exec_id=%s idempotent=%s corr=%s",
            execution.id, result.get("idempotent", False), correlation_id,
        )
        return result
    except Exception as exc:
        logger.error(
            "gateway[on] ado_publish failed: exec_id=%s error=%s corr=%s",
            execution.id, exc, correlation_id,
        )
        # No re-raise: el reaper reintentará la publicación
        return {"published": False, "error": str(exc), "idempotent": False}


def _apply_workflow_transition(
    *,
    ticket: "Ticket",
    execution: AgentExecution,
    payload: CompletionPayload,
    correlation_id: str,
) -> dict:
    """Aplica la transición de estado ADO declarativa (paso 5 del plan §4).

    Lee workflow.json del proyecto. Si no existe el archivo de workflow,
    usa fallback (sin cambio de estado ADO).

    Returns:
        dict con decision, target_ado_state, source.
    """
    try:
        from services import ado_workflow  # noqa: PLC0415
        project = getattr(ticket, "project", None) or "UNKNOWN"
        current_ado_state = getattr(ticket, "ado_state", None) or "Active"
        result = ado_workflow.apply_transition(
            project=project,
            agent_type=payload.agent_type,
            current_state=current_ado_state,
        )
        logger.info(
            "gateway[on] workflow_transition: project=%s agent_type=%s "
            "current=%s target=%s decision=%s corr=%s",
            project, payload.agent_type, current_ado_state,
            result.target_state, result.decision, correlation_id,
        )
        return {
            "target_ado_state": result.target_state,
            "decision": result.decision,
            "source": result.source,
            "comment_template": result.comment_template,
        }
    except ImportError:
        # ado_workflow no disponible (rama sin P3 mergeada)
        logger.warning(
            "gateway[on] ado_workflow not available — transition skipped corr=%s",
            correlation_id,
        )
        return {"target_ado_state": None, "decision": "skipped", "source": "no_workflow_module"}
    except Exception as exc:
        logger.error(
            "gateway[on] workflow_transition failed: error=%s corr=%s",
            exc, correlation_id,
        )
        return {"target_ado_state": None, "decision": "error", "source": str(exc)}


def _seal_audit(
    *,
    ticket_id: int,
    execution: AgentExecution,
    payload: CompletionPayload,
    html_sha256: str | None,
    workflow_decision: dict,
    correlation_id: str,
    user: str | None,
) -> None:
    """Sella la cadena de auditoría (paso 6 del plan §4).

    Intenta llamar a audit_chain.seal si está disponible.
    Si no, emite SystemLog como fallback.
    """
    try:
        from services import audit_chain  # noqa: PLC0415
        audit_chain.seal(
            execution_id=execution.id,
            kind="agent_completion",
            metadata={
                "correlation_id": correlation_id,
                "agent_type": payload.agent_type,
                "status": payload.status,
                "html_sha256": html_sha256,
                "workflow_decision": workflow_decision,
                "completion_source": "agent_gateway",
                "user": user,
            },
        )
        logger.debug(
            "gateway[on] audit_seal ok: exec_id=%s corr=%s",
            execution.id, correlation_id,
        )
    except ImportError:
        # audit_chain no disponible
        _emit_system_log(
            action="on.audit_seal_fallback",
            level="INFO",
            ticket_id=ticket_id,
            execution_id=execution.id,
            user=user,
            correlation_id=correlation_id,
            context={
                "kind": "agent_completion",
                "html_sha256": html_sha256,
                "workflow_decision": workflow_decision,
                "note": "audit_chain module not available",
            },
            tags=["completion_gateway", "on", "audit"],
        )
    except Exception as exc:
        logger.error(
            "gateway[on] audit_seal failed (non-fatal): exec_id=%s error=%s corr=%s",
            execution.id, exc, correlation_id,
        )


def run_on(
    *,
    ado_id: int,
    payload: CompletionPayload,
    user: str | None,
    correlation_id: str,
) -> tuple[GatewayResult, int]:
    """Ejecuta el gateway en modo on: transacción real de cierre/publicación.

    Pasos (plan §4):
      1. resolve_execution() — prioridad documentada
      2. validate_html()
      3. close_execution() — muta AgentExecution en DB (dentro de sesión)
      4. ado_publisher.publish_from_execution() — INSERT AgentHtmlPublish
      5. ticket_status.on_execution_end() + workflow.apply_transition()
      6. audit_chain.seal()

    Idempotencia: si la ejecución ya está en estado terminal y el hash SHA256
    coincide, se responde 200 idempotent_replay sin republicar.

    Args:
        ado_id: ID ADO del ticket.
        payload: Payload v1 validado.
        user: email del usuario/agente.
        correlation_id: UUID de correlación para esta invocación.

    Returns:
        (GatewayResult, http_status_code)
    """
    t0 = time.monotonic()
    errors: list[GatewayError] = []
    plan: list[ClosurePlanStep] = []
    execution: AgentExecution | None = None
    agent_type_mismatch = False
    html_sha256: str | None = None
    ticket_id: int | None = None
    is_synthetic = False
    idempotent_replay = False

    logger.info(
        "gateway[on] start: ado_id=%s agent_type=%s execution_id=%s corr=%s",
        ado_id, payload.agent_type, payload.execution_id, correlation_id,
    )

    # ── Fase 1: Resolución + validación HTML (READ) ────────────────────────────
    with session_scope() as session:
        # Resolver ticket
        ticket = session.query(Ticket).filter(Ticket.ado_id == ado_id).first()
        if ticket is None:
            return _build_error_result(
                mode="on",
                error=GatewayError(
                    http_status=404,
                    code="ticket_not_found",
                    message=f"No se encontró ticket con ado_id={ado_id}",
                    detail={"ado_id": ado_id},
                ),
                correlation_id=correlation_id,
                t0=t0,
                user=user,
                ado_id=ado_id,
                payload=payload,
            )
        ticket_id = ticket.id
        ticket_project = getattr(ticket, "project", None) or "UNKNOWN"
        ticket_ado_state = getattr(ticket, "ado_state", None) or "Active"

        # Resolver ejecución activa
        execution, agent_type_mismatch, resolve_err = _resolve_execution(
            ticket_id=ticket_id,
            payload=payload,
            correlation_id=correlation_id,
            session=session,
        )
        if resolve_err is not None:
            errors.append(resolve_err)
        elif execution is None and payload.allow_synthetic_rescue:
            is_synthetic = True

        # Chequeo idempotente: si la execution ya está terminal con este sha256
        if (
            execution is not None
            and execution.status in TERMINAL_STATUSES
            and payload.metadata.html_sha256
            and hasattr(execution, "html_sha256_cache")
        ):
            cached_sha256 = getattr(execution, "html_sha256_cache", None)
            if cached_sha256 == payload.metadata.html_sha256:
                idempotent_replay = True

        # Validar HTML
        _html_content, html_sha256, html_err = _validate_html(
            ado_id=ado_id,
            html_output_path=payload.html_output_path,
            correlation_id=correlation_id,
        )
        if html_err is not None:
            errors.append(html_err)

    # Si hay errores irrecuperables, retornar antes de mutar
    if errors:
        result_error = errors[0]
        _emit_system_log(
            action="on.pre_flight_failed",
            level="WARNING",
            ticket_id=ticket_id,
            execution_id=execution.id if execution else None,
            user=user,
            correlation_id=correlation_id,
            context={
                "ado_id": ado_id,
                "errors": [e.code for e in errors],
                "mode": "on",
            },
            tags=["completion_gateway", "on", "error"],
        )
        return _build_error_result(
            mode="on",
            error=result_error,
            correlation_id=correlation_id,
            t0=t0,
            user=user,
            ado_id=ado_id,
            payload=payload,
        )

    if idempotent_replay:
        logger.info(
            "gateway[on] idempotent_replay: exec_id=%s sha256=%s corr=%s",
            execution.id if execution else None,
            html_sha256, correlation_id,
        )
        return _build_idempotent_result(
            execution=execution,
            html_sha256=html_sha256,
            correlation_id=correlation_id,
            ticket_id=ticket_id,
            payload=payload,
            t0=t0,
        )

    # ── Fase 2: Mutación (WRITE) — transacción única ───────────────────────────
    publish_result: dict = {}
    workflow_decision: dict = {}

    with session_scope() as session:
        # Re-cargar ticket y execution en esta sesión
        ticket = session.query(Ticket).filter(Ticket.ado_id == ado_id).first()
        if ticket is None:
            return _build_error_result(
                mode="on",
                error=GatewayError(
                    http_status=404,
                    code="ticket_not_found",
                    message=f"Ticket ADO-{ado_id} no encontrado",
                    detail={"ado_id": ado_id},
                ),
                correlation_id=correlation_id,
                t0=t0,
                user=user,
                ado_id=ado_id,
                payload=payload,
            )
        ticket_id = ticket.id

        if execution is not None:
            # Re-cargar la execution en la nueva sesión
            exec_fresh = session.get(AgentExecution, execution.id)
            if exec_fresh is None:
                return _build_error_result(
                    mode="on",
                    error=GatewayError(
                        http_status=409,
                        code="execution_state_invalid",
                        message=f"execution_id={execution.id} desapareció entre fases",
                        detail={"execution_id": execution.id},
                    ),
                    correlation_id=correlation_id,
                    t0=t0,
                    user=user,
                    ado_id=ado_id,
                    payload=payload,
                )
            # Verificar idempotencia real (ejecución ya terminal)
            if exec_fresh.status in TERMINAL_STATUSES:
                logger.info(
                    "gateway[on] idempotent_replay (execution already terminal): "
                    "exec_id=%s status=%s corr=%s",
                    exec_fresh.id, exec_fresh.status, correlation_id,
                )
                idempotent_replay = True
                # Responder sin mutar
                plan = _build_closure_plan(
                    execution=exec_fresh,
                    payload=payload,
                    html_sha256=html_sha256,
                    agent_type_mismatch=agent_type_mismatch,
                    is_synthetic=False,
                )
                # No necesitamos el session para más nada
            else:
                # Paso 3: cerrar execution
                _close_execution(
                    execution=exec_fresh,
                    payload=payload,
                    html_sha256=html_sha256,
                    correlation_id=correlation_id,
                    session=session,
                )
                plan = _build_closure_plan(
                    execution=exec_fresh,
                    payload=payload,
                    html_sha256=html_sha256,
                    agent_type_mismatch=agent_type_mismatch,
                    is_synthetic=is_synthetic,
                )
                # session commit automático al salir del context manager

    if not idempotent_replay:
        # Paso 4: publicar en ADO (fuera de la sesión principal para independencia)
        if execution is not None and html_sha256:
            publish_result = _publish_to_ado(
                execution=execution,
                html_sha256=html_sha256,
                correlation_id=correlation_id,
                session=None,
            )

        # Paso 5: transición de estado del ticket
        if execution is not None and payload.status in TERMINAL_STATUSES:
            try:
                from services import ticket_status as ts  # noqa: PLC0415
                ts.on_execution_end(
                    ticket_id=ticket_id,
                    execution_id=execution.id,
                    final_status=payload.status,
                    agent_type=payload.agent_type,
                )
            except Exception as exc:
                logger.error(
                    "gateway[on] on_execution_end failed: exec_id=%s error=%s corr=%s",
                    execution.id, exc, correlation_id,
                )

        # Obtener transición declarativa del workflow
        if ticket is not None:
            workflow_decision = _apply_workflow_transition(
                ticket=ticket,
                execution=execution,
                payload=payload,
                correlation_id=correlation_id,
            )

        # Paso 6: audit seal
        if execution is not None:
            _seal_audit(
                ticket_id=ticket_id,
                execution=execution,
                payload=payload,
                html_sha256=html_sha256,
                workflow_decision=workflow_decision,
                correlation_id=correlation_id,
                user=user,
            )

    # ── Métricas ────────────────────────────────────────────────────────────────
    duration_ms = int((time.monotonic() - t0) * 1000)
    exec_id_for_log = execution.id if execution else None
    exec_agent_type_for_log = (
        execution.agent_type if execution else payload.agent_type
    )

    _emit_system_log(
        action="on.completion" if not idempotent_replay else "on.idempotent_replay",
        level="INFO",
        ticket_id=ticket_id,
        execution_id=exec_id_for_log,
        user=user,
        correlation_id=correlation_id,
        context={
            "ado_id": ado_id,
            "agent_type": payload.agent_type,
            "status": payload.status,
            "mode": "on",
            "html_sha256": html_sha256,
            "agent_type_mismatch": agent_type_mismatch,
            "is_synthetic": is_synthetic,
            "idempotent_replay": idempotent_replay,
            "publish_result": publish_result,
            "workflow_decision": workflow_decision,
            "plan_steps": [s.step for s in plan],
            "duration_ms": duration_ms,
        },
        tags=["completion_gateway", "on"],
    )
    _emit_system_log(
        action="metric.completion_gateway",
        level="INFO",
        ticket_id=ticket_id,
        execution_id=exec_id_for_log,
        user=user,
        correlation_id=correlation_id,
        context={
            "metric": "stacky_agent_completion_total",
            "result": "idempotent_replay" if idempotent_replay else "success",
            "agent_type": payload.agent_type,
            "mode": "on",
            "duration_ms": duration_ms,
        },
        tags=["metric", "completion_gateway"],
    )

    logger.info(
        "gateway[on] done: ado_id=%s ticket_id=%s exec_id=%s status=%s "
        "idempotent=%s publish=%s duration_ms=%d corr=%s",
        ado_id, ticket_id, exec_id_for_log, payload.status,
        idempotent_replay, publish_result.get("published", "N/A"),
        duration_ms, correlation_id,
    )

    result = GatewayResult(
        mode="on",
        ok=True,
        would_succeed=True,
        correlation_id=correlation_id,
        ticket_id=ticket_id,
        execution_id=exec_id_for_log,
        agent_type_resolved=exec_agent_type_for_log,
        agent_type_mismatch=agent_type_mismatch,
        html_sha256=html_sha256,
        plan=plan,
        errors=[],
        discrepancies=[],
        duration_ms=duration_ms,
    )
    # Agregar campos extra al dict de resultado para modo on
    result_dict = result.to_dict()
    result_dict["idempotent_replay"] = idempotent_replay
    result_dict["publish_result"] = publish_result
    result_dict["workflow_decision"] = workflow_decision

    return result, 200


# ── Helpers para run_on ───────────────────────────────────────────────────────


def _build_error_result(
    *,
    mode: str,
    error: GatewayError,
    correlation_id: str,
    t0: float,
    user: str | None,
    ado_id: int,
    payload: "CompletionPayload",
) -> tuple[GatewayResult, int]:
    """Construye un GatewayResult de error y emite SystemLog."""
    duration_ms = int((time.monotonic() - t0) * 1000)
    _emit_system_log(
        action=f"on.error.{error.code}",
        level="WARNING",
        user=user,
        correlation_id=correlation_id,
        context={
            "ado_id": ado_id,
            "error_code": error.code,
            "error_message": error.message,
            "mode": mode,
            "duration_ms": duration_ms,
        },
        tags=["completion_gateway", mode, "error"],
    )
    result = GatewayResult(
        mode=mode,
        ok=False,
        would_succeed=False,
        correlation_id=correlation_id,
        ticket_id=None,
        execution_id=None,
        agent_type_resolved=payload.agent_type,
        agent_type_mismatch=False,
        html_sha256=None,
        plan=[],
        errors=[error],
        discrepancies=[],
        duration_ms=duration_ms,
    )
    return result, error.http_status


def _build_idempotent_result(
    *,
    execution: "AgentExecution | None",
    html_sha256: str | None,
    correlation_id: str,
    ticket_id: int | None,
    payload: "CompletionPayload",
    t0: float,
) -> tuple[GatewayResult, int]:
    """Construye respuesta de replay idempotente."""
    duration_ms = int((time.monotonic() - t0) * 1000)
    result = GatewayResult(
        mode="on",
        ok=True,
        would_succeed=True,
        correlation_id=correlation_id,
        ticket_id=ticket_id,
        execution_id=execution.id if execution else None,
        agent_type_resolved=execution.agent_type if execution else payload.agent_type,
        agent_type_mismatch=False,
        html_sha256=html_sha256,
        plan=[],
        errors=[],
        discrepancies=[],
        duration_ms=duration_ms,
    )
    return result, 200
