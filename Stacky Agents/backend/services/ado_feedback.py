from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from config import config
from db import session_scope
from models import AgentExecution, Ticket
from runtime_paths import data_dir

logger = logging.getLogger("stacky.ado_feedback")


def _summarize_failure(row: AgentExecution) -> str:
    metadata = row.metadata_dict or {}
    failure_kind = str(metadata.get("failure_kind") or "").strip()
    if failure_kind:
        return failure_kind
    msg = (row.error_message or "sin detalle").strip().splitlines()[0]
    return msg[:300]


def comment_run_outcome(execution_id: int) -> dict:
    if not bool(config.STACKY_ADO_FAILURE_COMMENT_ENABLED):
        return {"ok": False, "skipped": True, "reason": "flag_off"}

    with session_scope() as session:
        row = session.get(AgentExecution, execution_id)
        if row is None:
            return {"ok": False, "skipped": True, "reason": "execution_not_found"}
        if row.status not in {"error", "needs_review"}:
            return {"ok": False, "skipped": True, "reason": "status_not_failure"}
        ticket = session.get(Ticket, row.ticket_id)
        if ticket is None or ticket.ado_id is None:
            return {"ok": False, "skipped": True, "reason": "ticket_or_ado_missing"}

        summary = _summarize_failure(row)
        html = (
            "<p><b>🤖 Stacky</b>: el agente "
            f"<b>{row.agent_type}</b> no completó esta tarea.</p>"
            f"<p>Causa: {summary}</p>"
            f"<p>Estado: requiere revisión del operador. (run #{row.id})</p>"
        )

    from services import ado_write_outbox

    payload_hash = hashlib.sha256(html.encode("utf-8")).hexdigest()
    outbox_dir = data_dir() / "ado_feedback"
    outbox_dir.mkdir(parents=True, exist_ok=True)
    html_path = outbox_dir / f"failure_comment_exec_{execution_id}.html"
    html_path.write_text(html, encoding="utf-8")

    result = ado_write_outbox.enqueue(
        kind=ado_write_outbox.KIND_POST_COMMENT,
        source="ado_feedback",
        idempotency_key=f"failure-comment:{execution_id}",
        payload={"ado_id": int(ticket.ado_id), "path": str(html_path)},
        execution_id=row.id,
        ticket_id=row.ticket_id,
        target_ado_id=int(ticket.ado_id),
        payload_sha256=payload_hash,
        payload_path=str(html_path),
    )
    logger.info("ado_feedback enqueued exec=%s ado=%s", execution_id, ticket.ado_id)
    return {"ok": True, "enqueue": result}
