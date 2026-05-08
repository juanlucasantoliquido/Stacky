"""
qa_uat.py — Flask Blueprint for the QA UAT pipeline endpoint.

POST /api/qa-uat/run
    Body: {"ticket_id": 70, "mode": "dry-run|publish", "headed": false, "timeout_ms": 30000}
    Returns: {"execution_id": <int>, "ticket_id": 70, "mode": "dry-run"}

    Runs qa_uat_pipeline.py in a background thread. Progress is streamed via
    the existing SSE endpoint:  GET /api/executions/{execution_id}/logs/stream

    On completion, the execution row is updated:
      - status: "completed" | "failed"
      - output: JSON string with pipeline summary
      - verdict field: PASS | FAIL | BLOCKED | MIXED (stored in metadata_dict["verdict"])

GET /api/qa-uat/run/<execution_id>
    Returns the pipeline result once completed (or status if still running).

SAFETY RULES (same as all uat_*.py):
  - FORBIDDEN: ado.py state / update_state subcommands
  - Default mode is dry-run
  - Never publish without explicit mode=publish in request body
"""
from __future__ import annotations

import json
import sys
import threading
from datetime import datetime
from pathlib import Path

from flask import Blueprint, abort, jsonify, request

import log_streamer
from db import session_scope
from models import AgentExecution, Ticket
from ._helpers import current_user

bp = Blueprint("qa_uat", __name__, url_prefix="/qa-uat")

# Path to qa_uat_pipeline.py — two levels up from the Stacky Agents backend
_PIPELINE_ROOT = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "Stacky tools"
    / "QA UAT Agent"
)
_AGENT_TYPE = "qa-uat"


# ── Endpoint: POST /api/qa-uat/run ────────────────────────────────────────────

@bp.post("/run")
def run_pipeline():
    """
    Launch the QA UAT pipeline for a given ticket.

    Request body (JSON):
        ticket_id   int     required  — ADO work item ID
        mode        str     optional  — "dry-run" (default) or "publish"
        headed      bool    optional  — run Playwright headed (default: false)
        timeout_ms  int     optional  — per-step timeout ms (default: 30000)

    Returns:
        {"execution_id": 12, "ticket_id": 70, "mode": "dry-run"}
        HTTP 202 Accepted

    Errors:
        400 — missing/invalid fields
        404 — ticket_id not found in Stacky DB
    """
    payload = request.get_json(force=True, silent=True) or {}

    # Validate required fields
    ticket_id = payload.get("ticket_id")
    if not ticket_id or not isinstance(ticket_id, int) or ticket_id < 1:
        abort(400, "ticket_id must be a positive integer")

    mode = payload.get("mode", "dry-run")
    if mode not in ("dry-run", "publish"):
        abort(400, "mode must be 'dry-run' or 'publish'")

    headed = bool(payload.get("headed", False))
    timeout_ms = int(payload.get("timeout_ms", 30_000))
    if timeout_ms < 1000 or timeout_ms > 300_000:
        abort(400, "timeout_ms must be between 1000 and 300000")

    user = current_user()

    # Locate ticket in Stacky DB (create stub row if not synced yet)
    with session_scope() as session:
        ticket_row = (
            session.query(Ticket).filter(Ticket.ado_id == ticket_id).first()
        )
        if ticket_row is None:
            abort(404, f"Ticket {ticket_id} not found in Stacky DB. "
                       "Run ADO sync first or create the ticket via the UI.")
        internal_ticket_id = ticket_row.id

    # Create execution row
    with session_scope() as session:
        exec_row = AgentExecution(
            ticket_id=internal_ticket_id,
            agent_type=_AGENT_TYPE,
            status="running",
            started_by=user,
            started_at=datetime.utcnow(),
        )
        exec_row.input_context = [
            {
                "id": "pipeline_params",
                "kind": "readonly",
                "title": "QA UAT Pipeline params",
                "content": json.dumps(
                    {"ticket_id": ticket_id, "mode": mode,
                     "headed": headed, "timeout_ms": timeout_ms},
                    ensure_ascii=False,
                ),
            }
        ]
        exec_row.chain_from = []
        exec_row.output_format = "json"
        exec_row.metadata_dict = {
            "pipeline_ticket_id": ticket_id,
            "mode": mode,
        }
        session.add(exec_row)
        session.flush()
        execution_id = exec_row.id

    log_streamer.open(execution_id)
    log_streamer.push(execution_id, "info",
                      f"▶ qa-uat pipeline started for ticket {ticket_id} (mode={mode})")

    # Launch background thread
    thread = threading.Thread(
        target=_run_pipeline_in_background,
        args=(execution_id, ticket_id, mode, headed, timeout_ms),
        daemon=True,
        name=f"qa-uat-pipeline-{ticket_id}",
    )
    thread.start()

    return jsonify({
        "execution_id": execution_id,
        "ticket_id": ticket_id,
        "mode": mode,
        "stream_url": f"/api/executions/{execution_id}/logs/stream",
    }), 202


# ── Endpoint: GET /api/qa-uat/run/<execution_id> ──────────────────────────────

@bp.get("/run/<int:execution_id>")
def get_run_result(execution_id: int):
    """
    Poll a QA UAT pipeline execution for its result.

    Returns execution dict with output parsed as JSON if available.
    The execution row output contains the full pipeline summary JSON.
    """
    with session_scope() as session:
        row = session.get(AgentExecution, execution_id)
        if row is None or row.agent_type != _AGENT_TYPE:
            abort(404, f"QA UAT execution {execution_id} not found")

        d = row.to_dict()

    # Parse JSON output if available
    if d.get("output"):
        try:
            d["pipeline_result"] = json.loads(d["output"])
        except (json.JSONDecodeError, TypeError):
            pass

    return jsonify(d)


# ── Background worker ─────────────────────────────────────────────────────────

def _run_pipeline_in_background(
    execution_id: int,
    ticket_id: int,
    mode: str,
    headed: bool,
    timeout_ms: int,
) -> None:
    """
    Execute qa_uat_pipeline.run() and persist the result to AgentExecution.
    All log events are pushed via log_streamer so the client can follow via SSE.
    """
    log = log_streamer.logger_for(execution_id)

    # Dynamically import pipeline from the Stacky tools directory
    # (avoids coupling the Flask backend's sys.path permanently)
    if str(_PIPELINE_ROOT) not in sys.path:
        sys.path.insert(0, str(_PIPELINE_ROOT))

    try:
        import qa_uat_pipeline

        log("info", f"pipeline root: {_PIPELINE_ROOT}")
        log("info", f"ticket_id={ticket_id} mode={mode} headed={headed} timeout_ms={timeout_ms}")

        result = qa_uat_pipeline.run(
            ticket_id=ticket_id,
            mode=mode,
            headed=headed,
            timeout_ms=timeout_ms,
            verbose=True,
        )

        verdict = result.get("verdict", "UNKNOWN")
        status = "completed"
        log("info", f"✅ pipeline finished — verdict={verdict} ok={result.get('ok')}")

    except Exception as exc:
        import traceback
        log("error", f"❌ pipeline crashed: {exc}")
        log("error", traceback.format_exc())
        result = {
            "ok": False,
            "ticket_id": ticket_id,
            "error": "pipeline_exception",
            "message": str(exc),
        }
        verdict = "ERROR"
        status = "failed"

    finally:
        # Persist result regardless of success/failure
        with session_scope() as session:
            row = session.get(AgentExecution, execution_id)
            if row is not None:
                row.status = status
                row.completed_at = datetime.utcnow()
                row.output = json.dumps(result, ensure_ascii=False)
                meta = row.metadata_dict or {}
                meta["verdict"] = verdict
                meta["elapsed_s"] = result.get("elapsed_s")
                row.metadata_dict = meta

        log_streamer.close(execution_id)
