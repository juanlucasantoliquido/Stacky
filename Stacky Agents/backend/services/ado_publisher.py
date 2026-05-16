"""
ado_publisher.py — Servicio centralizado de publicación de comentarios en
Azure DevOps a partir del HTML generado por los agentes de Stacky.

REGLA CRÍTICA (plan PLAN-stacky-agents-state-sync-ado-delegation.md, Fase 3):
Este es el ÚNICO módulo del backend autorizado a publicar comentarios HTML
de agente en ADO. Ningún `.agent.md`, ningún CLI tool, ningún subproceso del
agente debe hacer `AdoClient().post_comment()` directamente. La cadena es:

    agente → escribe HTML en Agentes/outputs/<ADO_ID>/comment.html
          → PATCH stacky-status con html_output_path
    stacky → hook post-ejecución → ado_publisher.publish_from_execution(...)
          → AdoClient.post_comment(...)

Idempotencia:
  La tabla `agent_html_publish` registra cada publicación con un hash del
  contenido HTML. Si una segunda llamada con el mismo (execution_id, hash)
  llega, se considera no-op y NO se vuelve a llamar a ADO.

Observabilidad:
  Cada publicación (éxito, skip, falla) emite un evento al stacky_logger con
  source='ado_publisher' y action en {publish.ok, publish.skipped, publish.failed}.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column

from db import Base, session_scope
from models import AgentExecution, Ticket
from services import agent_html_output as html_io

logger = logging.getLogger("stacky.ado_publisher")


# ── Modelo de registro (idempotencia + audit) ─────────────────────────────────


class AgentHtmlPublish(Base):
    """Log append-only de publicaciones de HTML del agente en ADO.

    Sirve para:
      1. Detectar duplicados antes de tocar ADO (idempotencia).
      2. Permitir auditoría de qué se publicó y cuándo desde Stacky Agents.
    """

    __tablename__ = "agent_html_publish"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    execution_id: Mapped[int | None] = mapped_column(
        ForeignKey("agent_executions.id", ondelete="SET NULL")
    )
    ticket_id: Mapped[int] = mapped_column(
        ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False
    )
    ado_id: Mapped[int] = mapped_column(Integer, nullable=False)
    html_path: Mapped[str] = mapped_column(String(500), nullable=False)
    html_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # ok | skipped | failed
    ado_response: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    triggered_by: Mapped[str] = mapped_column(String(40), nullable=False)  # post_hook | manual | finish_work
    published_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    __table_args__ = (
        Index("ix_ahp_execution", "execution_id"),
        Index("ix_ahp_ticket_pub", "ticket_id", "published_at"),
        Index("ix_ahp_dedupe", "execution_id", "html_sha256", "status"),
        # P2: DB-level idempotency guarantee.
        # Ensures no two rows share (execution_id, html_sha256) — same execution
        # with the same HTML content is a no-op regardless of call count.
        # The index is named explicitly so _migrate_add_columns can detect it.
        UniqueConstraint(
            "execution_id", "html_sha256",
            name="uq_agent_html_publish_execution_sha",
        ),
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "execution_id": self.execution_id,
            "ticket_id": self.ticket_id,
            "ado_id": self.ado_id,
            "html_path": self.html_path,
            "html_sha256": self.html_sha256,
            "status": self.status,
            "error_message": self.error_message,
            "triggered_by": self.triggered_by,
            "published_at": self.published_at.isoformat(),
        }


# ── Resultado tipado ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PublishResult:
    ok: bool
    status: str   # ok | skipped | failed
    reason: str | None      # detalle textual (skip o failure)
    ado_id: int | None
    execution_id: int | None
    html_sha256: str | None
    ado_response: dict | None
    record_id: int | None


# ── API pública ───────────────────────────────────────────────────────────────


def publish_from_execution(
    execution_id: int,
    *,
    triggered_by: str = "post_hook",
    client_factory=None,
    force: bool = False,
) -> PublishResult:
    """Publica en ADO el HTML del agente para una ejecución dada.

    Idempotencia (P2):
      La tabla agent_html_publish tiene UNIQUE(execution_id, html_sha256).
      Si la misma (execution_id, sha256) llega más de una vez:
        - Paso 4a detecta la fila existente ANTES de llamar a ADO.
        - Si la DB lanza IntegrityError de todos modos (race condition),
          lo capturamos en paso 6, buscamos el registro existente y
          devolvemos status='idempotent_replay'.
      Cada idempotent_replay se registra con el counter
      stacky_publish_idempotent_replay_total.

    Semántica de force:
      force=True permite insertar una NUEVA fila cuando el HTML cambió
      (sha256 distinto). NO omite el UNIQUE de DB — solo omite el dedupe
      previo por sha256 para la misma ejecución, permitiendo un nuevo
      html diferente. El UNIQUE sigue protegiendo contra doble-inserción
      del mismo (execution_id, sha256) incluso con force=True.

      Si llega el mismo sha256 con force=True → el UNIQUE de DB lo bloquea
      → IntegrityError → idempotent_replay (comportamiento idéntico).

    Pasos:
      1. Carga AgentExecution + Ticket. Si no existe o no tiene ado_id → falla.
      2. Resuelve el path del HTML (execution.html_output_path o fallback canónico).
      3. Lee+valida el HTML (servicio agent_html_output).
      4. Dedupe pre-ADO: busca fila existente con mismo (execution_id, sha256) y status=ok.
         - Si existe → retorna PublishResult(status='idempotent_replay') sin llamar ADO.
         - Si force=True → omite este paso (permite nuevo SHA para misma execution).
      5. Llama a AdoClient.post_comment (única invocación autorizada).
      6. Registra el resultado en AgentHtmlPublish.
         - Si la DB lanza IntegrityError → idempotent_replay (race condition capturada).

    Args:
        execution_id: ID de la ejecución cuyo HTML se publica.
        triggered_by: origen del disparo: 'post_hook' | 'manual' | 'finish_work' | 'rescue' | 'gateway'.
        client_factory: callable que devuelve un objeto con `.post_comment(ado_id, html)`.
                        Default: lambda: AdoClient(). Útil para tests.
        force: si True, omite el dedupe previo pero NO omite el UNIQUE de DB.
               Permite publicar un HTML distinto (sha256 diferente) para la
               misma execution. Usar con auditoría explícita.

    Returns:
        PublishResult — nunca lanza excepción salvo errores de programación.
    """
    # ── 1. Cargar contexto desde BD ───────────────────────────────────────────
    with session_scope() as session:
        exec_row = session.get(AgentExecution, execution_id)
        if exec_row is None:
            return _emit_and_persist(
                PublishResult(
                    ok=False, status="failed",
                    reason=f"AgentExecution {execution_id} no existe",
                    ado_id=None, execution_id=execution_id,
                    html_sha256=None, ado_response=None, record_id=None,
                ),
                ticket_id=0, ado_id=0, html_path="", triggered_by=triggered_by,
            )
        ticket = session.get(Ticket, exec_row.ticket_id)
        if ticket is None or not getattr(ticket, "ado_id", None):
            return _emit_and_persist(
                PublishResult(
                    ok=False, status="failed",
                    reason=f"Ticket {exec_row.ticket_id} sin ado_id",
                    ado_id=None, execution_id=execution_id,
                    html_sha256=None, ado_response=None, record_id=None,
                ),
                ticket_id=exec_row.ticket_id, ado_id=0,
                html_path="", triggered_by=triggered_by,
            )
        ado_id = int(ticket.ado_id)
        ticket_id = ticket.id
        hint = exec_row.html_output_path

    # ── 2-3. Resolver y validar HTML ──────────────────────────────────────────
    try:
        output = html_io.read_and_validate(ado_id, hint=hint)
    except html_io.ValidationError as exc:
        result = PublishResult(
            ok=False,
            status="failed" if exc.code in ("SECRET_DETECTED",) else "skipped",
            reason=str(exc),
            ado_id=ado_id,
            execution_id=execution_id,
            html_sha256=None,
            ado_response=None,
            record_id=None,
        )
        return _emit_and_persist(
            result,
            ticket_id=ticket_id, ado_id=ado_id,
            html_path=str(html_io.default_html_path(ado_id)),
            triggered_by=triggered_by,
        )

    html_sha = hashlib.sha256(output.html.encode("utf-8")).hexdigest()

    # ── 4. Dedupe pre-ADO (idempotencia aplicativa + DB) ─────────────────────
    # force=True omite este check para permitir un HTML distinto (sha diferente).
    # Con force=True y mismo sha → el UNIQUE de DB bloquea en paso 6 → idempotent_replay.
    if not force:
        with session_scope() as session:
            already = (
                session.query(AgentHtmlPublish)
                .filter(
                    AgentHtmlPublish.execution_id == execution_id,
                    AgentHtmlPublish.html_sha256 == html_sha,
                    AgentHtmlPublish.status == "ok",
                )
                .first()
            )
            if already is not None:
                result = PublishResult(
                    ok=True, status="idempotent_replay",
                    reason="duplicate_hash_pre_check",
                    ado_id=ado_id, execution_id=execution_id,
                    html_sha256=html_sha, ado_response=None,
                    record_id=already.id,
                )
                _emit_event(result, triggered_by=triggered_by, html_path=str(output.path))
                _increment_idempotent_replay_counter(execution_id=execution_id, ado_id=ado_id)
                return result

    # ── 5. Publicar en ADO (única invocación autorizada) ──────────────────────
    try:
        client = (client_factory or _default_client)()
        ado_response = client.post_comment(ado_id, output.html, "html")
    except Exception as exc:  # noqa: BLE001
        result = PublishResult(
            ok=False, status="failed",
            reason=f"ADO post_comment failed: {type(exc).__name__}: {exc}",
            ado_id=ado_id, execution_id=execution_id,
            html_sha256=html_sha, ado_response=None, record_id=None,
        )
        return _emit_and_persist(
            result, ticket_id=ticket_id, ado_id=ado_id,
            html_path=str(output.path), triggered_by=triggered_by,
        )

    # ── 6. Persistir — capturar IntegrityError (race condition UNIQUE) ────────
    ok_result = PublishResult(
        ok=True, status="ok", reason=None,
        ado_id=ado_id, execution_id=execution_id,
        html_sha256=html_sha,
        ado_response=ado_response if isinstance(ado_response, dict) else None,
        record_id=None,
    )
    try:
        return _emit_and_persist(
            ok_result, ticket_id=ticket_id, ado_id=ado_id,
            html_path=str(output.path), triggered_by=triggered_by,
        )
    except IntegrityError:
        # UNIQUE constraint fired: another concurrent call already inserted this row.
        # Find the existing record and return idempotent_replay.
        logger.warning(
            "publish_from_execution: IntegrityError on execution=%d sha=%s — "
            "race condition, returning idempotent_replay",
            execution_id, html_sha,
        )
        _increment_idempotent_replay_counter(execution_id=execution_id, ado_id=ado_id)
        with session_scope() as session:
            existing = (
                session.query(AgentHtmlPublish)
                .filter(
                    AgentHtmlPublish.execution_id == execution_id,
                    AgentHtmlPublish.html_sha256 == html_sha,
                )
                .first()
            )
            record_id = existing.id if existing else None
        replay_result = PublishResult(
            ok=True, status="idempotent_replay",
            reason="integrity_error_race_condition",
            ado_id=ado_id, execution_id=execution_id,
            html_sha256=html_sha, ado_response=None,
            record_id=record_id,
        )
        _emit_event(replay_result, triggered_by=triggered_by, html_path=str(output.path))
        return replay_result


# ── Hook post-ejecución ───────────────────────────────────────────────────────


def ado_publish_post_hook(
    *, ticket_id: int, execution_id: int, final_status: str,
    agent_type: str | None = None, error: str | None = None,
    **_kw: Any,
) -> None:
    """Hook invocado por services.ticket_status._run_post_hooks.

    Se dispara para CADA transición al final de una ejecución, pero solo
    publica si:
      - final_status == 'completed'
      - existe un HTML del agente en disco

    NUNCA bloquea; nunca lanza. Errores se loguean y van al registro.
    """
    if final_status != "completed":
        return
    try:
        result = publish_from_execution(
            execution_id, triggered_by="post_hook"
        )
        logger.info(
            "ado_publish_post_hook execution=%d → status=%s reason=%s",
            execution_id, result.status, result.reason,
        )
    except Exception:  # noqa: BLE001
        logger.exception("ado_publish_post_hook execution=%d falló", execution_id)


# ── Internos ──────────────────────────────────────────────────────────────────


def _increment_idempotent_replay_counter(
    *, execution_id: int | None, ado_id: int | None
) -> None:
    """Registra métrica stacky_publish_idempotent_replay_total (P2).

    En producción, aquí se incrementaría un counter Prometheus o similar.
    Por ahora emite un evento estructurado al stacky_logger para observabilidad.
    Nunca falla ni propaga excepción.
    """
    try:
        from services.stacky_logger import logger as slog
        slog.info(
            "ado_publisher",
            "stacky_publish_idempotent_replay_total",
            execution_id=execution_id,
            ticket_id=None,
            context_data={"ado_id": ado_id, "metric": "idempotent_replay"},
            tags=["publish", "idempotent_replay", "metric"],
        )
    except Exception:  # noqa: BLE001
        logger.debug("_increment_idempotent_replay_counter falló (no crítico)")


def _default_client():
    """Construye el AdoClient real. Tests inyectan client_factory."""
    from services.ado_client import AdoClient
    return AdoClient()


def _emit_and_persist(
    result: PublishResult, *,
    ticket_id: int, ado_id: int, html_path: str, triggered_by: str,
) -> PublishResult:
    """Persiste el resultado en AgentHtmlPublish y emite el evento estructurado.

    Devuelve un nuevo PublishResult con `record_id` poblado si se persistió.

    IntegrityError (P2): re-propagada al llamador (publish_from_execution) para
    que pueda hacer el lookup del registro existente y devolver idempotent_replay.
    Cualquier otro error de persistencia se absorbe (no crítico para el flujo).
    """
    record_id: int | None = None
    try:
        with session_scope() as session:
            row = AgentHtmlPublish(
                execution_id=result.execution_id,
                ticket_id=ticket_id or 0,
                ado_id=ado_id or 0,
                html_path=html_path or "",
                html_sha256=result.html_sha256 or "",
                status=result.status,
                ado_response=(
                    str(result.ado_response)[:2000]
                    if result.ado_response is not None else None
                ),
                error_message=result.reason if result.status != "ok" else None,
                triggered_by=triggered_by,
            )
            session.add(row)
            session.flush()
            record_id = row.id
    except IntegrityError:
        # Re-propagate so publish_from_execution can handle idempotent_replay.
        raise
    except Exception:  # noqa: BLE001
        logger.exception("persist AgentHtmlPublish falló (no crítico)")

    final = PublishResult(
        ok=result.ok, status=result.status, reason=result.reason,
        ado_id=result.ado_id, execution_id=result.execution_id,
        html_sha256=result.html_sha256, ado_response=result.ado_response,
        record_id=record_id,
    )
    _emit_event(final, triggered_by=triggered_by, html_path=html_path)
    return final


def _emit_event(
    result: PublishResult, *, triggered_by: str, html_path: str,
) -> None:
    """Publica un evento estructurado en stacky_logger.

    action: ado_publish.ok | ado_publish.skipped | ado_publish.failed
    """
    try:
        from services.stacky_logger import logger as slog
        action = f"ado_publish.{result.status}"
        level = "info" if result.ok or result.status == "skipped" else "warning"
        emitter = getattr(slog, level)
        emitter(
            "ado_publisher",
            action,
            execution_id=result.execution_id,
            ticket_id=None,
            context_data={
                "ado_id": result.ado_id,
                "html_sha256": result.html_sha256,
                "html_path": html_path,
                "reason": result.reason,
                "triggered_by": triggered_by,
                "record_id": result.record_id,
            },
            tags=["ado", "publish", result.status],
        )
    except Exception:  # noqa: BLE001
        logger.exception("emit ado_publish event falló (no crítico)")
