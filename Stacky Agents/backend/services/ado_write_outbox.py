"""ado_write_outbox.py — Outbox durable de escrituras ADO (Fase 2).

Plan: docs/plans/plan-creacion-tareas-comentarios-100-efectiva-2026-05-29.md §4.1.

Toda escritura en Azure DevOps (crear Task hija, publicar comentario, subir/
linkear adjunto, cambiar estado) pasa primero por la tabla `ado_write_operations`,
que es la fuente de verdad operativa. La regla dura del plan:

    "Ningun flujo marca pending-task.json como consumido ni una publicacion como
     exitosa hasta que exista una operacion `succeeded` o `idempotent_succeeded`
     verificada."

Este modulo NO toca ADO. Solo persiste el estado de las operaciones y aplica las
reglas de idempotencia (por `idempotency_key`), backoff y transiciones de estado.
El que ejecuta contra ADO es `ado_write_executor.py`; el que reintenta en
background es `ado_write_worker.py`; el que lista/reintenta desde la UI es
`api/ado_writes.py`.

Estados (status):
    queued              recien encolada, lista para ejecutar.
    in_progress         tomada por el executor/worker.
    succeeded           ADO confirmo + verificacion por lectura ok.
    idempotent_succeeded  ya existia en ADO (marcador/registro previo); no se duplico.
    retryable_failed    fallo transitorio (red/5xx/rate limit); reintenta con backoff.
    blocked             fallo no recuperable (permisos/politica/campo invalido); requiere humano.
    dead_letter         agoto los reintentos; requiere humano.

Kinds (kind): create_task | post_comment | upload_attachment | link_attachment | update_state.
Sources (source): output_watcher | manual_ui | agent_completion | finish_work | rescue | create_child_task.
"""
from __future__ import annotations

import json
import logging
import uuid as _uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from db import Base, session_scope

logger = logging.getLogger("stacky.ado_write_outbox")

# ── Vocabulario de estado/kind/source ──────────────────────────────────────────

STATUS_QUEUED = "queued"
STATUS_IN_PROGRESS = "in_progress"
STATUS_SUCCEEDED = "succeeded"
STATUS_IDEMPOTENT = "idempotent_succeeded"
STATUS_RETRYABLE = "retryable_failed"
STATUS_BLOCKED = "blocked"
STATUS_DEAD_LETTER = "dead_letter"

_TERMINAL_OK = {STATUS_SUCCEEDED, STATUS_IDEMPOTENT}
_TERMINAL_FAIL = {STATUS_BLOCKED, STATUS_DEAD_LETTER}
_OPEN_STATES = {STATUS_QUEUED, STATUS_IN_PROGRESS, STATUS_RETRYABLE}

KIND_CREATE_TASK = "create_task"
KIND_POST_COMMENT = "post_comment"
KIND_UPLOAD_ATTACHMENT = "upload_attachment"
KIND_LINK_ATTACHMENT = "link_attachment"
KIND_UPDATE_STATE = "update_state"

# Reintentos antes de pasar a dead_letter (configurable por op via metadata futura).
MAX_ATTEMPTS = 6
# Backoff exponencial: base * 2^(attempt-1), clampeado.
_BACKOFF_BASE_SECONDS = 30
_BACKOFF_MAX_SECONDS = 30 * 60  # 30 minutos


def _now() -> datetime:
    return datetime.utcnow()


def _json_dumps(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, default=str)


def _json_loads(raw: str | None) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return raw


# ── Modelo ──────────────────────────────────────────────────────────────────


class AdoWriteOperation(Base):
    """Operacion de escritura ADO durable (outbox). Ver docstring del modulo."""

    __tablename__ = "ado_write_operations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Identificador trazable estable de la operacion (uuid). Aparece en logs,
    # respuestas de endpoint y la UI "Publicaciones ADO".
    operation_id: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)

    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default=STATUS_QUEUED)
    source: Mapped[str] = mapped_column(String(40), nullable=False)

    # Correlacion con el resto del sistema.
    execution_id: Mapped[int | None] = mapped_column(Integer)
    ticket_id: Mapped[int | None] = mapped_column(Integer)
    parent_ado_id: Mapped[int | None] = mapped_column(Integer)
    target_ado_id: Mapped[int | None] = mapped_column(Integer)

    # Idempotencia + payload.
    idempotency_key: Mapped[str] = mapped_column(String(300), nullable=False)
    payload_sha256: Mapped[str | None] = mapped_column(String(64))
    payload_path: Mapped[str | None] = mapped_column(String(500))
    payload_json: Mapped[str | None] = mapped_column(Text)

    # Retry.
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime)

    # Trazas ADO.
    ado_request_json: Mapped[str | None] = mapped_column(Text)
    ado_response_json: Mapped[str | None] = mapped_column(Text)
    ado_verified_at: Mapped[datetime | None] = mapped_column(DateTime)

    # Diagnostico.
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(Text)
    correlation_id: Mapped[str | None] = mapped_column(String(40))

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)

    __table_args__ = (
        Index("ix_awo_status_next_retry", "status", "next_retry_at"),
        Index("ix_awo_idempotency", "idempotency_key"),
        Index("ix_awo_parent", "parent_ado_id"),
        Index("ix_awo_ticket", "ticket_id"),
        Index("ix_awo_created", "created_at"),
    )

    # — Accesores JSON —

    @property
    def payload(self) -> dict:
        return _json_loads(self.payload_json) or {}

    @payload.setter
    def payload(self, value: dict | None) -> None:
        self.payload_json = _json_dumps(value or {})

    @property
    def ado_request(self) -> Any:
        return _json_loads(self.ado_request_json)

    @property
    def ado_response(self) -> Any:
        return _json_loads(self.ado_response_json)

    def is_open(self) -> bool:
        return self.status in _OPEN_STATES

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "operation_id": self.operation_id,
            "kind": self.kind,
            "status": self.status,
            "source": self.source,
            "execution_id": self.execution_id,
            "ticket_id": self.ticket_id,
            "parent_ado_id": self.parent_ado_id,
            "target_ado_id": self.target_ado_id,
            "idempotency_key": self.idempotency_key,
            "payload_sha256": self.payload_sha256,
            "payload_path": self.payload_path,
            "payload": self.payload,
            "attempt_count": self.attempt_count,
            "next_retry_at": self.next_retry_at.isoformat() if self.next_retry_at else None,
            "last_attempt_at": self.last_attempt_at.isoformat() if self.last_attempt_at else None,
            "ado_response": self.ado_response,
            "ado_verified_at": self.ado_verified_at.isoformat() if self.ado_verified_at else None,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "correlation_id": self.correlation_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# ── Backoff ─────────────────────────────────────────────────────────────────


def compute_backoff_seconds(attempt_count: int) -> int:
    """Backoff exponencial clampeado para `retryable_failed`."""
    if attempt_count <= 0:
        return _BACKOFF_BASE_SECONDS
    wait = _BACKOFF_BASE_SECONDS * (2 ** (attempt_count - 1))
    return int(min(wait, _BACKOFF_MAX_SECONDS))


# ── Encolado idempotente ──────────────────────────────────────────────────────


def enqueue(
    *,
    kind: str,
    source: str,
    idempotency_key: str,
    payload: dict | None = None,
    execution_id: int | None = None,
    ticket_id: int | None = None,
    parent_ado_id: int | None = None,
    target_ado_id: int | None = None,
    payload_sha256: str | None = None,
    payload_path: str | None = None,
    correlation_id: str | None = None,
) -> dict:
    """Crea (o recupera) una operacion outbox por `idempotency_key`.

    Reglas de idempotencia:
      - Si ya existe una operacion succeeded/idempotent_succeeded con la misma
        clave → se devuelve esa (no se duplica el trabajo). `reused=True`.
      - Si existe una abierta (queued/in_progress/retryable_failed) → se devuelve
        esa misma operacion. `reused=True`.
      - Si solo existen blocked/dead_letter → se crea una NUEVA operacion queued
        (el operador esta reintentando un caso que habia sido marcado humano).
      - Si no existe ninguna → se crea queued.

    Devuelve `{"operation": <dict>, "reused": bool, "created": bool}`.
    """
    op_dict: dict
    reused = False
    created = False
    with session_scope() as session:
        existing = (
            session.query(AdoWriteOperation)
            .filter(AdoWriteOperation.idempotency_key == idempotency_key)
            .order_by(AdoWriteOperation.id.desc())
            .all()
        )
        # Preferir un terminal-ok; si no, una abierta.
        terminal_ok = next((o for o in existing if o.status in _TERMINAL_OK), None)
        open_op = next((o for o in existing if o.status in _OPEN_STATES), None)
        reuse = terminal_ok or open_op
        if reuse is not None:
            reused = True
            op_dict = reuse.to_dict()
        else:
            op = AdoWriteOperation(
                operation_id=correlation_id or str(_uuid.uuid4()),
                kind=kind,
                status=STATUS_QUEUED,
                source=source,
                execution_id=execution_id,
                ticket_id=ticket_id,
                parent_ado_id=parent_ado_id,
                target_ado_id=target_ado_id,
                idempotency_key=idempotency_key,
                payload_sha256=payload_sha256,
                payload_path=payload_path,
                payload_json=_json_dumps(payload or {}),
                attempt_count=0,
                next_retry_at=_now(),
                correlation_id=correlation_id,
                created_at=_now(),
                updated_at=_now(),
            )
            session.add(op)
            session.flush()
            created = True
            op_dict = op.to_dict()
    return {"operation": op_dict, "reused": reused, "created": created}


# ── Toma para ejecucion ───────────────────────────────────────────────────────


def claim(operation_id: str) -> dict | None:
    """Marca una operacion como in_progress y registra el intento. Devuelve dict o None."""
    with session_scope() as session:
        op = (
            session.query(AdoWriteOperation)
            .filter(AdoWriteOperation.operation_id == operation_id)
            .first()
        )
        if op is None:
            return None
        op.status = STATUS_IN_PROGRESS
        op.attempt_count = (op.attempt_count or 0) + 1
        op.last_attempt_at = _now()
        op.updated_at = _now()
        session.flush()
        return op.to_dict()


def claim_due(limit: int = 20) -> list[dict]:
    """Toma operaciones listas para ejecutar (queued o retryable vencido).

    Las marca in_progress en una sola transaccion para evitar que dos workers
    tomen la misma. Devuelve la lista de dicts ya tomados.
    """
    now = _now()
    out: list[dict] = []
    with session_scope() as session:
        rows = (
            session.query(AdoWriteOperation)
            .filter(AdoWriteOperation.status.in_([STATUS_QUEUED, STATUS_RETRYABLE]))
            .filter(
                (AdoWriteOperation.next_retry_at.is_(None))
                | (AdoWriteOperation.next_retry_at <= now)
            )
            .order_by(AdoWriteOperation.id.asc())
            .limit(limit)
            .all()
        )
        for op in rows:
            op.status = STATUS_IN_PROGRESS
            op.attempt_count = (op.attempt_count or 0) + 1
            op.last_attempt_at = now
            op.updated_at = now
            out.append(op.to_dict())
    return out


# ── Transiciones de estado ─────────────────────────────────────────────────────


def _apply(operation_id: str, **changes) -> dict | None:
    with session_scope() as session:
        op = (
            session.query(AdoWriteOperation)
            .filter(AdoWriteOperation.operation_id == operation_id)
            .first()
        )
        if op is None:
            return None
        for key, value in changes.items():
            setattr(op, key, value)
        op.updated_at = _now()
        session.flush()
        return op.to_dict()


def mark_succeeded(
    operation_id: str,
    *,
    target_ado_id: int | None = None,
    ado_response: Any = None,
    verified: bool = True,
    idempotent: bool = False,
) -> dict | None:
    return _apply(
        operation_id,
        status=STATUS_IDEMPOTENT if idempotent else STATUS_SUCCEEDED,
        target_ado_id=target_ado_id,
        ado_response_json=_json_dumps(ado_response),
        ado_verified_at=_now() if verified else None,
        next_retry_at=None,
        error_code=None,
        error_message=None,
    )


def mark_retryable(
    operation_id: str,
    *,
    error_code: str,
    error_message: str,
    attempt_count: int | None = None,
) -> dict | None:
    """Marca fallo transitorio. Si agoto MAX_ATTEMPTS → dead_letter."""
    attempts = attempt_count if attempt_count is not None else 0
    if attempts >= MAX_ATTEMPTS:
        return _apply(
            operation_id,
            status=STATUS_DEAD_LETTER,
            error_code=error_code,
            error_message=(error_message or "")[:2000],
            next_retry_at=None,
        )
    backoff = compute_backoff_seconds(attempts)
    return _apply(
        operation_id,
        status=STATUS_RETRYABLE,
        error_code=error_code,
        error_message=(error_message or "")[:2000],
        next_retry_at=_now() + timedelta(seconds=backoff),
    )


def mark_blocked(
    operation_id: str,
    *,
    error_code: str,
    error_message: str,
    target_ado_id: int | None = None,
) -> dict | None:
    return _apply(
        operation_id,
        status=STATUS_BLOCKED,
        error_code=error_code,
        error_message=(error_message or "")[:2000],
        target_ado_id=target_ado_id,
        next_retry_at=None,
    )


def retry_now(operation_id: str, *, reset_attempts: bool = False) -> dict | None:
    """Reencola una operacion (retry manual desde UI o reconciliador)."""
    changes: dict[str, Any] = {
        "status": STATUS_QUEUED,
        "next_retry_at": _now(),
        "error_code": None,
        "error_message": None,
    }
    if reset_attempts:
        changes["attempt_count"] = 0
    return _apply(operation_id, **changes)


def resolve_manual(operation_id: str, *, reason: str, user: str) -> dict | None:
    """Marca como resuelta manualmente (rescate del operador, plan §8)."""
    op = _apply(
        operation_id,
        status=STATUS_SUCCEEDED,
        ado_verified_at=None,
        next_retry_at=None,
        error_code="manual_resolution",
        error_message=f"Resuelto manualmente por {user}: {reason}"[:2000],
    )
    return op


# ── Consultas ─────────────────────────────────────────────────────────────────


def get(operation_id: str) -> dict | None:
    with session_scope() as session:
        op = (
            session.query(AdoWriteOperation)
            .filter(AdoWriteOperation.operation_id == operation_id)
            .first()
        )
        return op.to_dict() if op else None


def list_operations(
    *,
    status: str | None = None,
    parent_ado_id: int | None = None,
    kind: str | None = None,
    limit: int = 200,
) -> list[dict]:
    with session_scope() as session:
        q = session.query(AdoWriteOperation)
        if status:
            if status == "open":
                q = q.filter(AdoWriteOperation.status.in_(list(_OPEN_STATES)))
            elif status == "attention":
                q = q.filter(AdoWriteOperation.status.in_([STATUS_BLOCKED, STATUS_DEAD_LETTER]))
            else:
                q = q.filter(AdoWriteOperation.status == status)
        if parent_ado_id is not None:
            q = q.filter(AdoWriteOperation.parent_ado_id == parent_ado_id)
        if kind:
            q = q.filter(AdoWriteOperation.kind == kind)
        rows = q.order_by(AdoWriteOperation.id.desc()).limit(limit).all()
        return [r.to_dict() for r in rows]


def summary() -> dict:
    """Conteo por estado para badges del dashboard."""
    from sqlalchemy import func

    out = {
        STATUS_QUEUED: 0,
        STATUS_IN_PROGRESS: 0,
        STATUS_SUCCEEDED: 0,
        STATUS_IDEMPOTENT: 0,
        STATUS_RETRYABLE: 0,
        STATUS_BLOCKED: 0,
        STATUS_DEAD_LETTER: 0,
    }
    with session_scope() as session:
        rows = (
            session.query(AdoWriteOperation.status, func.count(AdoWriteOperation.id))
            .group_by(AdoWriteOperation.status)
            .all()
        )
        for status, count in rows:
            out[status] = int(count)
    out["needs_attention"] = out[STATUS_BLOCKED] + out[STATUS_DEAD_LETTER]
    out["pending"] = out[STATUS_QUEUED] + out[STATUS_IN_PROGRESS] + out[STATUS_RETRYABLE]
    return out
