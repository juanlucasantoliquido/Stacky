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

Sprint 8 — New endpoints:
GET  /api/qa-uat/lanes                   — available lanes with metadata
GET  /api/qa-uat/portfolio/<ticket_id>   — test_portfolio.json of last run
GET  /api/qa-uat/dashboard?period=7      — 3-panel dashboard summary
POST /api/qa-uat/budget-check            — estimate cost for a run
GET  /api/qa-uat/quarantine              — list active quarantine entries
POST /api/qa-uat/quarantine              — add a quarantine entry
DELETE /api/qa-uat/quarantine/<id>       — resolve a quarantine entry

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


def _ensure_pipeline_on_path() -> None:
    """Add pipeline root to sys.path if not already present."""
    root = str(_PIPELINE_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


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


# ── Sprint 8 endpoints ────────────────────────────────────────────────────────


@bp.get("/lanes")
def get_lanes():
    """
    Return the list of available execution lanes with metadata.

    GET /api/qa-uat/lanes
    Response: {"ok": true, "lanes": [...]}
    """
    lanes = [
        {
            "id": "preflight",
            "label": "Preflight",
            "description": "Solo ambiente y fingerprint",
            "estimated_seconds": 20,
        },
        {
            "id": "compile-only",
            "label": "Compile Only",
            "description": "Sin browser — intake, screen, compiler, selector_contract",
            "estimated_seconds": 45,
        },
        {
            "id": "smoke-uat",
            "label": "Smoke UAT",
            "description": "Recorridos P0 — pipeline completo, filtrado a alta prioridad",
            "estimated_seconds": 180,
        },
        {
            "id": "full-uat",
            "label": "Full UAT",
            "description": "Pipeline completo — todos los CAs UAT",
            "estimated_seconds": None,
        },
        {
            "id": "forensic-rerun",
            "label": "Forensic Rerun",
            "description": "Evidencia maxima — trace always, HAR, screenshots, video",
            "estimated_seconds": None,
        },
        {
            "id": "nightly-regression",
            "label": "Nightly Regression",
            "description": "Todos los tickets activos priorizados por riesgo",
            "estimated_seconds": None,
        },
    ]
    return jsonify({"ok": True, "lanes": lanes})


@bp.get("/portfolio/<int:ticket_id>")
def get_portfolio(ticket_id: int):
    """
    Return the test_portfolio.json from the most recent run of a ticket.

    GET /api/qa-uat/portfolio/<ticket_id>
    Response: {"ok": true, "portfolio": {...}}
    """
    evidence_dir = _PIPELINE_ROOT / "evidence" / str(ticket_id)
    if not evidence_dir.exists():
        return jsonify({"ok": False, "error": "not_found",
                        "message": f"No evidence directory for ticket {ticket_id}"}), 404

    # Find the most recent run subdirectory containing test_portfolio.json
    portfolio_file: Path | None = None
    run_dirs = sorted(evidence_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
    for run_dir in run_dirs:
        candidate = run_dir / "test_portfolio.json"
        if candidate.exists():
            portfolio_file = candidate
            break

    # Also check root evidence directory
    if portfolio_file is None:
        root_candidate = evidence_dir / "test_portfolio.json"
        if root_candidate.exists():
            portfolio_file = root_candidate

    if portfolio_file is None:
        return jsonify({"ok": False, "error": "not_found",
                        "message": f"No test_portfolio.json found for ticket {ticket_id}"}), 404

    try:
        with portfolio_file.open(encoding="utf-8") as fh:
            portfolio = json.load(fh)
        return jsonify({"ok": True, "portfolio": portfolio,
                        "source": str(portfolio_file.relative_to(_PIPELINE_ROOT))})
    except Exception as exc:
        return jsonify({"ok": False, "error": "parse_error",
                        "message": str(exc)}), 500


@bp.get("/dashboard")
def get_dashboard():
    """
    Return the 3-panel QA dashboard for the requested period.

    GET /api/qa-uat/dashboard?period=7
    Response: {"ok": true, "panels": {"run_health": {...}, ...}}
    """
    _ensure_pipeline_on_path()
    try:
        from dashboard_builder import build_dashboard  # type: ignore[import]
    except ImportError as exc:
        return jsonify({"ok": False, "error": "import_error",
                        "message": f"dashboard_builder not available: {exc}"}), 503

    period_raw = request.args.get("period", "7")
    try:
        period = int(period_raw)
        if period < 1 or period > 365:
            raise ValueError("out of range")
    except ValueError:
        abort(400, "period must be an integer between 1 and 365")

    try:
        dashboard = build_dashboard(period_days=period)
        return jsonify(dashboard)
    except Exception as exc:
        return jsonify({"ok": False, "error": "dashboard_error",
                        "message": str(exc)}), 500


@bp.post("/budget-check")
def budget_check():
    """
    Estimate the cost of a planned run and check against the configured budget.

    POST /api/qa-uat/budget-check
    Body: {"lane": "forensic-rerun", "ticket_id": 122, "scenario_count": 4,
           "model_tier": "standard"}
    Response: {"ok": true, "result": {"allowed": true, "decision": "allow", ...}}
    """
    _ensure_pipeline_on_path()
    try:
        from budget_enforcer import check_budget  # type: ignore[import]
    except ImportError as exc:
        return jsonify({"ok": False, "error": "import_error",
                        "message": f"budget_enforcer not available: {exc}"}), 503

    payload = request.get_json(force=True, silent=True) or {}

    lane = payload.get("lane")
    if not lane or not isinstance(lane, str):
        abort(400, "lane is required and must be a string")

    ticket_id = payload.get("ticket_id")
    if not ticket_id or not isinstance(ticket_id, int):
        abort(400, "ticket_id must be a positive integer")

    scenario_count = int(payload.get("scenario_count", 0))
    model_tier = str(payload.get("model_tier", "standard"))

    try:
        result = check_budget(
            lane=lane,
            ticket_id=ticket_id,
            scenario_count=scenario_count,
            model_tier=model_tier,
        )
        return jsonify({
            "ok": True,
            "result": {
                "allowed": result.allowed,
                "lane": result.lane,
                "estimated_cost_usd": result.estimated_cost_usd,
                "budget_remaining_usd": result.budget_remaining_usd,
                "budget_total_usd": result.budget_total_usd,
                "used_usd": result.used_usd,
                "decision": result.decision,
                "reason": result.reason,
            },
        })
    except Exception as exc:
        return jsonify({"ok": False, "error": "budget_check_error",
                        "message": str(exc)}), 500


@bp.get("/quarantine")
def list_quarantine():
    """
    List active quarantine entries.

    GET /api/qa-uat/quarantine
    Response: {"ok": true, "entries": [...], "total": N, "active": N, "expired": N}
    """
    _ensure_pipeline_on_path()
    try:
        from quarantine_registry import QuarantineRegistry  # type: ignore[import]
    except ImportError as exc:
        return jsonify({"ok": False, "error": "import_error",
                        "message": f"quarantine_registry not available: {exc}"}), 503

    try:
        registry = QuarantineRegistry()
        registry.expire_old_quarantines()
        summary = registry.get_quarantine_summary()

        # Serialize all known entries (active + expired + resolved)
        all_entries = registry._load_all_entries()
        entries_out = [e.to_dict() for e in all_entries]

        return jsonify({
            "ok": True,
            "entries": entries_out,
            "total": summary.active_count + summary.expired_unresolved_count + summary.resolved_count,
            "active": summary.active_count,
            "expired": summary.expired_unresolved_count,
        })
    except Exception as exc:
        return jsonify({"ok": False, "error": "quarantine_list_error",
                        "message": str(exc)}), 500


@bp.post("/quarantine")
def add_quarantine():
    """
    Add a scenario to quarantine.

    POST /api/qa-uat/quarantine
    Body: {
        "scenario_id": "RF-008-CA-01",
        "screen": "FrmDetalleClie.aspx",
        "category": "NAV",
        "reason": "FLAKY_SELECTOR",
        "owner": "qa_automation",
        "ttl_days": 7,
        "notes": "optional"
    }
    Response: {"ok": true, "entry": {...}}
    """
    _ensure_pipeline_on_path()
    try:
        from quarantine_registry import QuarantineRegistry, QuarantineEntry  # type: ignore[import]
    except ImportError as exc:
        return jsonify({"ok": False, "error": "import_error",
                        "message": f"quarantine_registry not available: {exc}"}), 503

    payload = request.get_json(force=True, silent=True) or {}

    scenario_id = payload.get("scenario_id")
    owner = payload.get("owner")
    ttl_days = payload.get("ttl_days")

    if not scenario_id:
        abort(400, "scenario_id is required")
    if not owner:
        abort(400, "owner is required")
    if not ttl_days or not isinstance(ttl_days, int) or ttl_days < 1:
        abort(400, "ttl_days must be a positive integer")

    try:
        registry = QuarantineRegistry()
        entry = QuarantineEntry(
            test_id=scenario_id,
            scenario_id=scenario_id,
            screen=str(payload.get("screen", "")) or None,
            category=str(payload.get("category", "NAV")),
            reason=str(payload.get("reason", "MANUAL_QUARANTINE")),
            owner=owner,
            ttl_days=ttl_days,
        )
        force = bool(payload.get("force", False))
        created = registry.add_quarantine(entry, force=force)
        return jsonify({
            "ok": True,
            "entry": {
                "id": created.id,
                "scenario_id": created.scenario_id,
                "status": created.status,
                "expires_at": created.expires_at,
                "owner": created.owner,
            },
        }), 201
    except ValueError as exc:
        return jsonify({"ok": False, "error": "validation_error",
                        "message": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": "quarantine_add_error",
                        "message": str(exc)}), 500


@bp.delete("/quarantine/<quarantine_id>")
def resolve_quarantine(quarantine_id: str):
    """
    Resolve (close) a quarantine entry.

    DELETE /api/qa-uat/quarantine/<id>
    Response: {"ok": true, "resolved": true}
    """
    _ensure_pipeline_on_path()
    try:
        from quarantine_registry import QuarantineRegistry  # type: ignore[import]
    except ImportError as exc:
        return jsonify({"ok": False, "error": "import_error",
                        "message": f"quarantine_registry not available: {exc}"}), 503

    try:
        registry = QuarantineRegistry()
        resolved = registry.resolve_quarantine(quarantine_id)
        if not resolved:
            return jsonify({"ok": False, "error": "not_found",
                            "message": f"Quarantine entry {quarantine_id} not found"}), 404
        return jsonify({"ok": True, "resolved": True, "id": quarantine_id})
    except Exception as exc:
        return jsonify({"ok": False, "error": "quarantine_resolve_error",
                        "message": str(exc)}), 500
