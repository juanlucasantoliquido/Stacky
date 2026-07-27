"""Plan 254 F5 — reconciliación post-cierre: el falso ROJO, medido.

F1-F4 CREEN haber arreglado el falso rojo; nada en el sistema lo PRUEBA. Este
módulo compara, para cada run terminado, el estado del ticket contra la
evidencia objetiva del run, y LISTA las discrepancias.

Rieles duros:
- **No cambia ningún estado.** No reintenta, no publica, no decide. Lista.
- **Read-only absoluto:** `scan_recent` no escribe una sola fila.
- **Sin autonomía proactiva:** se consulta a pedido (un `GET`). NO corre en un
  loop ni dispara nada por su cuenta. Si algún día se quisiera un barrido
  periódico, se engancha al `_maintenance_loop` compartido del plan 253 F4 —
  no se inventa otro loop.
- **Paridad de runtimes:** trabaja sobre `AgentExecution` + `TicketStatusEvent`,
  comunes a los 3.

`evaluate` es PURA (sin DB, sin red) y se testea sin base. `scan_recent` es la
única función que toca la base, y solo para LEER.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass

logger = logging.getLogger("stacky.run_reconciliation")

DISCREPANCY_KINDS = (
    "red_with_delivered_work",    # ticket 'error' pero hubo result ok / rc==0  → EL FALSO ROJO
    "green_with_dirty_close",     # ticket 'completed' con blocked_downgrade    → F1-bis sin revisar
    "green_self_reported_only",   # 'completed' solo por auto-reporte, rc!=0 y sin result ok
    "unclassified_outcome",       # run terminado sin outcome_reason            → F2 no cableada
    "drain_timeout",              # el stream no terminó de drenar              → F3
)

# Estados de ticket que representan un run ya cerrado (los únicos reconciliables).
_TERMINAL_TICKET_STATUSES = frozenset({"completed", "error", "cancelled", "needs_review"})


@dataclass(frozen=True)
class RunEvidence:
    """Los hechos objetivos de un run. Los arma el caller desde la BD;
    la función de veredicto es PURA y se testea sin base."""

    execution_id: int
    ticket_id: int
    ticket_status: str            # stacky_status actual
    return_code: int | None
    result_ok_seen: bool
    outcome_reason: str | None
    self_reported_completed: bool  # el agente PATCHeó stacky-status
    blocked_downgrade: bool        # F1 preservó un terminal de éxito
    drain_timed_out: bool          # F3


@dataclass(frozen=True)
class Discrepancy:
    execution_id: int
    ticket_id: int
    kind: str                     # ∈ DISCREPANCY_KINDS
    detail: str

    def to_dict(self) -> dict:
        return {
            "execution_id": self.execution_id,
            "ticket_id": self.ticket_id,
            "kind": self.kind,
            "detail": self.detail,
        }


def evaluate(evidence: RunEvidence) -> list[Discrepancy]:
    """PURA. Devuelve 0..n discrepancias para un run. Sin DB, sin red."""
    out: list[Discrepancy] = []

    def _add(kind: str, detail: str) -> None:
        out.append(Discrepancy(
            execution_id=evidence.execution_id,
            ticket_id=evidence.ticket_id,
            kind=kind,
            detail=detail,
        ))

    entrego_trabajo = bool(evidence.result_ok_seen) or evidence.return_code == 0

    # EL FALSO ROJO: el ticket quedó rojo y hay evidencia objetiva de trabajo.
    if evidence.ticket_status == "error" and entrego_trabajo:
        _add(
            "red_with_delivered_work",
            f"ticket en 'error' con evidencia de trabajo entregado "
            f"(rc={evidence.return_code}, result_ok={evidence.result_ok_seen})",
        )

    # F1-bis sin revisar: el verde se preservó sobre un cierre sucio.
    if evidence.ticket_status == "completed" and evidence.blocked_downgrade:
        _add(
            "green_with_dirty_close",
            "'completed' preservado sobre un cierre sucio: pendiente de revisión humana",
        )

    # Verde que solo sostiene el auto-reporte del agente, sin evidencia objetiva.
    if (
        evidence.ticket_status == "completed"
        and evidence.self_reported_completed
        and not entrego_trabajo
    ):
        _add(
            "green_self_reported_only",
            f"'completed' solo por auto-reporte del agente "
            f"(rc={evidence.return_code}, sin result ok)",
        )

    # F2 no cableada en ese camino: el desenlace no tiene causa.
    if not evidence.outcome_reason and evidence.ticket_status in _TERMINAL_TICKET_STATUSES:
        _add("unclassified_outcome", "run terminado sin outcome_reason")

    # F3: el stream no terminó de drenar antes de clasificar.
    if evidence.drain_timed_out:
        _add("drain_timeout", "el drenaje del stream venció antes de clasificar el desenlace")

    return out


def _self_reported_ticket_ids(session, ticket_ids: list[int]) -> set[int]:
    """Tickets que llegaron a 'completed' por una mano que NO es 'system'.

    El agente auto-reporta vía `PATCH /api/tickets/by-ado/{id}/stacky-status`, que
    escribe `changed_by` = header X-User-Email o "agent" (api/tickets.py). El
    cierre del runner escribe `changed_by="system"`.
    """
    if not ticket_ids:
        return set()
    from services.ticket_status import TicketStatusEvent  # noqa: PLC0415

    rows = (
        session.query(TicketStatusEvent.ticket_id)
        .filter(TicketStatusEvent.ticket_id.in_(ticket_ids))
        .filter(TicketStatusEvent.new_status == "completed")
        .filter(TicketStatusEvent.changed_by != "system")
        .all()
    )
    return {r[0] for r in rows}


def _blocked_downgrade_execution_ids(session, execution_ids: list[int]) -> set[int]:
    """Ejecuciones cuyo cierre disparó el guard de F1 (marca `pending_review`)."""
    if not execution_ids:
        return set()
    from services.ticket_status import TicketStatusEvent  # noqa: PLC0415

    rows = (
        session.query(TicketStatusEvent.execution_id, TicketStatusEvent.metadata_json)
        .filter(TicketStatusEvent.execution_id.in_(execution_ids))
        .filter(TicketStatusEvent.metadata_json.like("%blocked_downgrade%"))
        .all()
    )
    out: set[int] = set()
    for exec_id, raw in rows:
        try:
            blocked = (json.loads(raw or "{}") or {}).get("blocked_downgrade")
        except (ValueError, TypeError):
            continue
        if isinstance(blocked, dict) and blocked.get("pending_review"):
            out.add(exec_id)
    return out


def scan_recent(limit: int = 200) -> list[Discrepancy]:
    """Lee los últimos `limit` runs terminados y aplica `evaluate`.

    READ-ONLY: no escribe una sola fila. Sin efectos secundarios.
    """
    from db import session_scope  # noqa: PLC0415
    from models import AgentExecution, Ticket  # noqa: PLC0415

    out: list[Discrepancy] = []
    with session_scope() as session:
        rows = (
            session.query(AgentExecution, Ticket)
            .join(Ticket, Ticket.id == AgentExecution.ticket_id)
            .filter(AgentExecution.status.in_(("completed", "error", "cancelled", "needs_review")))
            .order_by(AgentExecution.started_at.desc())
            .limit(max(1, int(limit)))
            .all()
        )
        exec_ids = [ex.id for ex, _t in rows]
        ticket_ids = [t.id for _ex, t in rows]
        blocked_ids = _blocked_downgrade_execution_ids(session, exec_ids)
        self_reported = _self_reported_ticket_ids(session, ticket_ids)

        for ex, ticket in rows:
            meta = ex.metadata_dict or {}
            if not isinstance(meta, dict):
                meta = {}
            rc = meta.get("exit_code")
            try:
                rc = int(rc) if rc is not None else None
            except (TypeError, ValueError):
                rc = None
            # Evidencia de `result ok` tardío: el runner la sella como
            # `finalized_after_result` cuando cerró tras entregar trabajo.
            result_ok = bool(meta.get("finalized_after_result"))
            out.extend(evaluate(RunEvidence(
                execution_id=ex.id,
                ticket_id=ticket.id,
                ticket_status=getattr(ticket, "stacky_status", None) or "idle",
                return_code=rc,
                result_ok_seen=result_ok,
                outcome_reason=meta.get("outcome_reason"),
                self_reported_completed=ticket.id in self_reported,
                blocked_downgrade=ex.id in blocked_ids,
                drain_timed_out=bool(meta.get("drain_timed_out")),
            )))
    return out


def summarize(discrepancies: list[Discrepancy]) -> dict:
    """Payload del endpoint: total, conteo por tipo y la lista.

    `by_kind` declara SIEMPRE los 5 kinds, aunque valgan 0: un contador que
    desaparece cuando vale cero no sirve para mirar una tendencia.
    """
    by_kind = {kind: 0 for kind in DISCREPANCY_KINDS}
    for d in discrepancies:
        by_kind[d.kind] = by_kind.get(d.kind, 0) + 1
    return {
        "total": len(discrepancies),
        "by_kind": by_kind,
        "items": [d.to_dict() for d in discrepancies],
    }
