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
  - QA UAT never publishes directly.
  - With explicit mode=publish, Stacky publishes centrally from Agentes/outputs.
"""
from __future__ import annotations

import json
import re
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

from flask import Blueprint, abort, jsonify, request

import log_streamer
from db import session_scope
from models import AgentExecution, Ticket
from ._helpers import current_user

bp = Blueprint("qa_uat", __name__, url_prefix="/qa-uat")


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


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
        mode        str     optional  — "dry-run" (default) or "publish" via Stacky
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

        pipeline_mode = "dry-run" if mode == "publish" else mode
        result = qa_uat_pipeline.run(
            ticket_id=ticket_id,
            mode=pipeline_mode,
            headed=headed,
            timeout_ms=timeout_ms,
            verbose=True,
        )
        result["requested_mode"] = mode
        result["pipeline_mode"] = pipeline_mode

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
                row.output = json.dumps(result, ensure_ascii=False)
                meta = row.metadata_dict or {}
                meta["verdict"] = verdict
                meta["elapsed_s"] = result.get("elapsed_s")
                meta["requested_mode"] = mode
                meta["pipeline_mode"] = result.get("pipeline_mode")
                # Sprint 1 — store run_id and artifact_root for UI navigation
                if result.get("run_id"):
                    meta["run_id"] = result["run_id"]
                if result.get("artifact_root"):
                    meta["artifact_root"] = result["artifact_root"]
                handoff = result.get("stacky_handoff") or {}
                if handoff.get("html_output_path"):
                    meta["html_output_path"] = handoff["html_output_path"]
                # Sprint 6 — store governance metadata for historial + policy enforcement
                _s6_fields = {
                    "category":              result.get("category"),
                    "reason":                result.get("reason"),
                    "failed_stage":          result.get("failed_stage"),
                    "evidence_complete":     result.get("_evidence_complete"),
                    "evidence_missing":      result.get("_evidence_missing") or [],
                    "normalized":            result.get("_normalized", False),
                }
                # contract results (from Sprint 4 contract validator)
                _stages = result.get("stages") or {}
                if "compiler_contract" in _stages:
                    _s6_fields["compiler_contract_ok"] = _stages["compiler_contract"].get("ok")
                if "generator_contract" in _stages:
                    _s6_fields["generator_contract_ok"] = _stages["generator_contract"].get("ok")
                # confidence: use pipeline_verdict_decision confidence if present
                if "confidence" in result:
                    _s6_fields["confidence"] = result["confidence"]
                meta.update({k: v for k, v in _s6_fields.items() if v is not None})
                row.metadata_dict = meta

        handoff_path = ((result.get("stacky_handoff") or {}).get("html_output_path"))
        should_publish = status == "completed" and mode == "publish" and bool(handoff_path)
        try:
            from services.agent_completion_internal import close_execution_with_publish
            close_result = close_execution_with_publish(
                execution_id=execution_id,
                triggered_by="qa_uat_pipeline",
                final_status="completed" if status == "completed" else "error",
                html_output_path=handoff_path,
                user="qa_uat_pipeline",
                reason=f"QA UAT pipeline finalizado para ADO-{ticket_id}",
                completion_source="qa_uat_pipeline",
                agent_type_hint=_AGENT_TYPE,
                auto_publish=True if should_publish else False,
            )
            result["stacky_publish"] = close_result.publish
            with session_scope() as session:
                row = session.get(AgentExecution, execution_id)
                if row is not None:
                    row.output = json.dumps(result, ensure_ascii=False)
                    meta = row.metadata_dict or {}
                    meta["stacky_publish"] = close_result.publish
                    row.metadata_dict = meta
            if should_publish and close_result.publish.get("ok"):
                log("info", "comentario ADO publicado por Stacky")
            elif should_publish:
                log("error", f"Stacky publish failed: {close_result.publish}")
        except Exception as close_exc:  # noqa: BLE001
            log("error", f"close/publish failed: {close_exc}")
            with session_scope() as session:
                row = session.get(AgentExecution, execution_id)
                if row is not None:
                    row.status = "failed"
                    row.error_message = str(close_exc)
                    row.completed_at = datetime.utcnow()

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


# ── Sprint 6: Publish policy endpoint ────────────────────────────────────────

@bp.post("/run/<int:execution_id>/policy")
def check_run_publish_policy(execution_id: int):
    """Sprint 6 — Evaluate publish policy for a completed QA UAT run.

    POST /api/qa-uat/run/<execution_id>/policy
    Body (optional): {"human_approved": true, "mode": "publish"}
    Response: {"ok": true, "allowed": false, "violations": [...]}
    """
    _ensure_pipeline_on_path()
    payload = request.get_json(force=True, silent=True) or {}
    human_approved = bool(payload.get("human_approved", False))
    mode = payload.get("mode", "dry-run")

    with session_scope() as session:
        row = session.get(AgentExecution, execution_id)
        if row is None:
            return jsonify({"ok": False, "error": "not_found",
                            "message": f"execution {execution_id} not found"}), 404
        meta = row.metadata_dict or {}
        verdict = meta.get("verdict")
        run_id  = meta.get("run_id")
        artifact_root = meta.get("artifact_root")

    evidence_dir = Path(artifact_root) if artifact_root else None

    try:
        from qa_uat_publish_policy import evaluate_policy, write_policy_result
        policy_result = evaluate_policy(
            verdict=verdict,
            run_id=run_id,
            evidence_dir=evidence_dir,
            human_approved=human_approved,
            mode=mode,
        )
        if evidence_dir:
            write_policy_result(evidence_dir, policy_result)
    except Exception as exc:
        return jsonify({"ok": False, "error": "policy_error", "message": str(exc)}), 500

    return jsonify({
        "ok": True,
        "execution_id": execution_id,
        **policy_result.to_dict(),
    })


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


# ── Sprint 9 — Data Request endpoints ────────────────────────────────────────
#
# POST /api/qa-uat/data-request/<run_id>          — create pending data request
# POST /api/qa-uat/data-request/<request_id>/resolve — resolve with value/decision
# GET  /api/qa-uat/data-request/<request_id>/status  — query status


@bp.post("/data-request/<run_id>")
def create_data_request(run_id: str):
    """
    Create a set of data resolution requests for a pipeline run that has
    missing data requirements (data_readiness_v2 returned MISSING).

    POST /api/qa-uat/data-request/<run_id>
    Body:
        {
            "readiness_result": {   // DataReadinessCheckResult as dict
                "scenario_id": "RF-007-CA-01",
                "ticket_id": 120,
                "missing": [...]
            },
            "environment": "QA"    // optional, defaults to QA_UAT_TARGET_ENVIRONMENT env var
        }

    Response (201):
        {"ok": true, "result": {"pending_request_ids": [...], "decisions": [...]}}

    Errors:
        400 — missing/invalid body
        503 — broker module not available
        500 — broker error
    """
    _ensure_pipeline_on_path()
    try:
        from data_resolution_broker import run as broker_run  # type: ignore[import]
    except ImportError as exc:
        return jsonify({"ok": False, "error": "import_error",
                        "message": f"data_resolution_broker not available: {exc}"}), 503

    payload = request.get_json(force=True, silent=True) or {}
    readiness_result = payload.get("readiness_result")
    if not readiness_result or not isinstance(readiness_result, dict):
        abort(400, "readiness_result (dict) is required")

    missing = readiness_result.get("missing", [])
    if not isinstance(missing, list):
        abort(400, "readiness_result.missing must be a list")

    environment = payload.get("environment") or None

    # Determine evidence_dir from run_id
    ticket_id = readiness_result.get("ticket_id", 0)
    evidence_dir = _PIPELINE_ROOT / "evidence" / str(ticket_id)

    try:
        result = broker_run(
            readiness_result=readiness_result,
            run_id=run_id,
            evidence_dir=evidence_dir,
            environment=environment,
        )
        return jsonify({"ok": True, "result": result.to_dict()}), 201
    except Exception as exc:
        return jsonify({"ok": False, "error": "broker_error",
                        "message": str(exc)}), 500


@bp.post("/data-request/<request_id>/resolve")
def resolve_data_request(request_id: str):
    """
    Resolve a pending data request with a user-supplied value or decision.

    POST /api/qa-uat/data-request/<request_id>/resolve
    Body:
        {
            "resolution_type": "provide_existing_value",  // one of the option IDs
            "supplied_fields": {"CLCOD": "12345"},        // when resolution_type = provide_existing_value
            "note": "optional human note",
            "run_id": "120-abc",          // required to locate qa_data_requests.json
            "ticket_id": 120,             // required to locate evidence directory
            "scenario_id": "RF-007-CA-01"
        }

    Response (200):
        {"ok": true, "result": {"request_id": "...", "valid": true, "resolved_data_ref": "..."}}

    Errors:
        400 — missing/invalid body
        404 — request_id not found in store
        422 — validation failed
        503 — module not available
        500 — internal error
    """
    _ensure_pipeline_on_path()
    payload = request.get_json(force=True, silent=True) or {}

    resolution_type = payload.get("resolution_type")
    if not resolution_type:
        abort(400, "resolution_type is required")

    run_id = payload.get("run_id")
    ticket_id = payload.get("ticket_id")
    if not run_id or not ticket_id:
        abort(400, "run_id and ticket_id are required")

    evidence_dir = _PIPELINE_ROOT / "evidence" / str(ticket_id)
    store_path = evidence_dir / str(run_id) / "qa_data_requests.json"

    # Load the pending record
    if not store_path.is_file():
        return jsonify({"ok": False, "error": "not_found",
                        "message": f"No data requests found for run_id={run_id}"}), 404

    try:
        import json as _json
        records = _json.loads(store_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return jsonify({"ok": False, "error": "store_read_error",
                        "message": str(exc)}), 500

    record = next((r for r in records if r.get("id") == request_id), None)
    if record is None:
        return jsonify({"ok": False, "error": "not_found",
                        "message": f"Request {request_id} not found"}), 404

    if record.get("status") not in ("pending_user_input",):
        return jsonify({"ok": False, "error": "already_resolved",
                        "message": f"Request {request_id} is already {record.get('status')}"}), 409

    # If user is providing a value, validate it
    supplied_fields = payload.get("supplied_fields") or {}
    validation_result = None

    if resolution_type == "provide_existing_value" and supplied_fields:
        try:
            from user_data_validator import validate as udv_validate  # type: ignore[import]
            user = current_user()
            validation_result = udv_validate(
                request_id=request_id,
                supplied_fields=supplied_fields,
                supplied_by=user,
                evidence_dir=evidence_dir,
                run_id=run_id,
            )
            if not validation_result.valid:
                return jsonify({
                    "ok": False,
                    "error": "validation_failed",
                    "message": validation_result.reason or "Validation failed",
                    "result": validation_result.to_dict(),
                }), 422
            if validation_result.injection_detected:
                return jsonify({
                    "ok": False,
                    "error": "prompt_injection_detected",
                    "message": "Prompt injection detected in supplied data",
                    "result": validation_result.to_dict(),
                }), 422
        except ImportError as exc:
            return jsonify({"ok": False, "error": "import_error",
                            "message": f"user_data_validator not available: {exc}"}), 503

    # Update the record
    import datetime as _dt
    now = _dt.datetime.now(_dt.timezone.utc).isoformat().replace("+00:00", "Z")
    record["status"] = "resolved"
    record["resolved_at"] = now
    record["resolved_by"] = current_user()
    record["resolution_type"] = resolution_type
    if payload.get("note"):
        record["note"] = payload["note"]

    try:
        store_path.write_text(
            __import__("json").dumps(records, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
    except Exception as exc:
        return jsonify({"ok": False, "error": "store_write_error",
                        "message": str(exc)}), 500

    response_body = {
        "ok": True,
        "result": {
            "request_id": request_id,
            "status": "resolved",
            "resolution_type": resolution_type,
            "resolved_at": now,
        },
    }
    if validation_result is not None:
        response_body["result"]["validation"] = {
            "valid": validation_result.valid,
            "resolved_data_ref": validation_result.resolved_data_ref,
        }
    return jsonify(response_body)


@bp.get("/data-request/<request_id>/status")
def get_data_request_status(request_id: str):
    """
    Return the status of a data resolution request.

    GET /api/qa-uat/data-request/<request_id>/status?run_id=<run_id>&ticket_id=<ticket_id>

    Query params:
        run_id    string  required
        ticket_id int     required

    Response (200):
        {"ok": true, "result": {"request_id": "...", "status": "pending_user_input", ...}}

    Errors:
        400 — missing query params
        404 — not found
    """
    run_id = request.args.get("run_id")
    ticket_id_raw = request.args.get("ticket_id")

    if not run_id or not ticket_id_raw:
        abort(400, "run_id and ticket_id query parameters are required")

    try:
        ticket_id = int(ticket_id_raw)
    except ValueError:
        abort(400, "ticket_id must be an integer")

    evidence_dir = _PIPELINE_ROOT / "evidence" / str(ticket_id)
    store_path = evidence_dir / run_id / "qa_data_requests.json"

    if not store_path.is_file():
        return jsonify({"ok": False, "error": "not_found",
                        "message": f"No data requests found for run_id={run_id}"}), 404

    try:
        records = json.loads(store_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return jsonify({"ok": False, "error": "store_read_error",
                        "message": str(exc)}), 500

    record = next((r for r in records if r.get("id") == request_id), None)
    if record is None:
        return jsonify({"ok": False, "error": "not_found",
                        "message": f"Request {request_id} not found"}), 404

    return jsonify({"ok": True, "result": record})


@bp.get("/data-request")
def list_data_requests():
    """
    List all data resolution requests for a given run.

    GET /api/qa-uat/data-request?run_id=<run_id>&ticket_id=<ticket_id>

    Query params:
        run_id    string   required
        ticket_id int      required
        status    string   optional — filter by status (pending_user_input|resolved|timeout)

    Response (200):
        {"ok": true, "requests": [...], "total": N, "pending": N}

    Errors:
        400 — missing query params
        404 — no requests file found for this run
    """
    run_id = request.args.get("run_id")
    ticket_id_raw = request.args.get("ticket_id")
    status_filter = request.args.get("status")

    if not run_id or not ticket_id_raw:
        abort(400, "run_id and ticket_id query parameters are required")

    try:
        ticket_id = int(ticket_id_raw)
    except ValueError:
        abort(400, "ticket_id must be an integer")

    evidence_dir = _PIPELINE_ROOT / "evidence" / str(ticket_id)
    store_path = evidence_dir / run_id / "qa_data_requests.json"

    if not store_path.is_file():
        return jsonify({
            "ok": True,
            "requests": [],
            "total": 0,
            "pending": 0,
            "message": f"No data requests found for run_id={run_id}",
        })

    try:
        records = json.loads(store_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return jsonify({"ok": False, "error": "store_read_error",
                        "message": str(exc)}), 500

    if status_filter:
        records = [r for r in records if r.get("status") == status_filter]

    pending_count = sum(1 for r in records if r.get("status") == "pending_user_input")

    # Also load the resolution artifact for context if available
    resolution_artifacts: dict = {}
    resolution_dir = evidence_dir / run_id
    if resolution_dir.is_dir():
        for artifact_file in resolution_dir.glob("data_resolution_request_*.json"):
            try:
                artifact_data = json.loads(artifact_file.read_text(encoding="utf-8"))
                scenario_id = artifact_data.get("scenario_id", "")
                if scenario_id:
                    resolution_artifacts[scenario_id] = artifact_data
            except Exception:
                pass

    return jsonify({
        "ok": True,
        "requests": records,
        "total": len(records),
        "pending": pending_count,
        "resolution_artifacts": resolution_artifacts,
    })


# ── Sprint 10: Seed Proposal Preview ─────────────────────────────────────────

@bp.get("/seed-proposal")
def get_seed_proposal():
    """
    GET /api/qa-uat/seed-proposal?run_id=<id>&ticket_id=<id>&scenario_id=<optional>

    Returns seed proposal scripts and safety results for a pipeline run.
    Scripts are read from evidence artifacts written by sql_seed_generator.py.

    Response: {"ok": true, "proposals": [...], "total": N}

    Each proposal:
      {
          "scenario_id": "RF-007-CA-01",
          "seed_run_id": "seed-120-ABCDEF",
          "script_path": "...",
          "cleanup_path": "...",
          "script_content": "...",    -- null if file too large (>64KB)
          "cleanup_content": "...",
          "script_sha256": "...",
          "safety_result": { "safe": true, "risk_level": "low", ... }
      }
    """
    _ensure_pipeline_on_path()

    run_id = request.args.get("run_id", "").strip()
    ticket_id_raw = request.args.get("ticket_id", "").strip()
    scenario_filter = request.args.get("scenario_id", "").strip() or None

    if not run_id:
        return jsonify({"ok": False, "error": "missing_run_id",
                        "message": "run_id is required"}), 400
    if not ticket_id_raw:
        return jsonify({"ok": False, "error": "missing_ticket_id",
                        "message": "ticket_id is required"}), 400

    evidence_dir = _PIPELINE_ROOT / "evidence" / str(ticket_id_raw)
    run_dir = evidence_dir / run_id

    proposals = []
    if run_dir.is_dir():
        for seed_file in sorted(run_dir.glob("seed_proposal_*.sql")):
            # Extract scenario_id from filename: seed_proposal_<scenario_id>.sql
            scenario_id = seed_file.stem.replace("seed_proposal_", "")
            if scenario_filter and scenario_id != scenario_filter:
                continue

            cleanup_file = run_dir / f"cleanup_proposal_{scenario_id}.sql"
            safety_file = run_dir / f"seed_safety_result_{scenario_id}.json"

            # Read script content (capped at 64KB for safety)
            script_content = None
            try:
                raw = seed_file.read_bytes()
                if len(raw) <= 65536:
                    script_content = raw.decode("utf-8", errors="replace")
            except Exception:
                pass

            cleanup_content = None
            try:
                raw = cleanup_file.read_bytes()
                if len(raw) <= 65536:
                    cleanup_content = raw.decode("utf-8", errors="replace")
            except Exception:
                pass

            safety_result = None
            try:
                if safety_file.exists():
                    safety_result = json.loads(safety_file.read_text(encoding="utf-8"))
            except Exception:
                pass

            proposals.append({
                "scenario_id": scenario_id,
                "script_path": str(seed_file),
                "cleanup_path": str(cleanup_file) if cleanup_file.exists() else None,
                "script_content": script_content,
                "cleanup_content": cleanup_content,
                "safety_result": safety_result,
            })

    return jsonify({"ok": True, "proposals": proposals, "total": len(proposals)})


@bp.post("/seed-proposal/validate")
def validate_seed_proposal():
    """
    POST /api/qa-uat/seed-proposal/validate

    Validate an arbitrary SQL seed script against safety rules.
    Useful for operator-edited scripts or re-validation after manual review.

    Body: { "sql_text": "...", "source": "optional-label" }
    Response: { "ok": true, "result": { "safe": bool, "risk_level": str, ... } }
    """
    _ensure_pipeline_on_path()

    body = request.get_json(silent=True) or {}
    sql_text = body.get("sql_text", "")
    source = body.get("source", "operator_submitted")[:200]

    if not sql_text or not sql_text.strip():
        return jsonify({"ok": False, "error": "empty_sql",
                        "message": "sql_text is required and must not be empty"}), 400

    if len(sql_text) > 131072:  # 128KB hard cap
        return jsonify({"ok": False, "error": "sql_too_large",
                        "message": "sql_text exceeds 128KB limit"}), 400

    try:
        from sql_safety_validator import validate as safety_validate  # type: ignore[import]
    except ImportError as exc:
        return jsonify({"ok": False, "error": "import_error",
                        "message": f"sql_safety_validator not available: {exc}"}), 503

    try:
        result = safety_validate(sql_text, source=source)
        return jsonify({"ok": True, "result": result.to_dict()})
    except Exception as exc:
        return jsonify({"ok": False, "error": "validation_error",
                        "message": str(exc)}), 500


# ── Sprint 11: Human Approval + Seed Executor + Cleanup ──────────────────────

@bp.post("/seed-proposal/approve")
def approve_seed_proposal():
    """
    POST /api/qa-uat/seed-proposal/approve

    Record operator approval for a seed script and optionally trigger execution.
    The operator supplies the SHA-256 of the script they reviewed — this is
    matched against the actual file content before any execution.

    Body:
      {
          "run_id": "120",
          "ticket_id": 120,
          "scenario_id": "RF-007-CA-01",
          "approved_sha256": "<sha256 of reviewed script>",
          "approved_by": "operator@example.com",
          "dry_run": true          -- default true; set false to trigger real execution
      }

    Response:
      { "ok": true, "result": { "verdict": "SKIPPED|APPLIED|...", ... } }
    """
    _ensure_pipeline_on_path()

    body = request.get_json(silent=True) or {}
    run_id = str(body.get("run_id", "")).strip()
    ticket_id_raw = body.get("ticket_id")
    scenario_id = str(body.get("scenario_id", "")).strip()
    approved_sha256 = str(body.get("approved_sha256", "")).strip()
    approved_by = str(body.get("approved_by", current_user() or "unknown"))[:200].strip()
    dry_run = bool(body.get("dry_run", True))

    for field_name, val in [("run_id", run_id), ("scenario_id", scenario_id),
                             ("approved_sha256", approved_sha256)]:
        if not val:
            return jsonify({"ok": False, "error": f"missing_{field_name}",
                            "message": f"{field_name} is required"}), 400

    if ticket_id_raw is None:
        return jsonify({"ok": False, "error": "missing_ticket_id",
                        "message": "ticket_id is required"}), 400

    try:
        from seed_executor import execute as seed_execute  # type: ignore[import]
    except ImportError as exc:
        return jsonify({"ok": False, "error": "import_error",
                        "message": f"seed_executor not available: {exc}"}), 503

    # Locate the seed script in evidence directory
    evidence_dir = _PIPELINE_ROOT / "evidence" / str(ticket_id_raw)
    run_dir = evidence_dir / run_id
    safe_id = re.sub(r"[^a-zA-Z0-9_\-]", "_", scenario_id)
    script_path = run_dir / f"seed_proposal_{safe_id}.sql"

    if not script_path.exists():
        return jsonify({"ok": False, "error": "script_not_found",
                        "message": f"Seed script not found: {script_path}"}), 404

    # Record approval in evidence
    approval_record = {
        "scenario_id": scenario_id,
        "approved_sha256": approved_sha256,
        "approved_by": approved_by,
        "approved_at": _utcnow_iso(),
        "dry_run": dry_run,
    }
    try:
        approval_path = run_dir / f"seed_approval_{safe_id}.json"
        approval_path.write_text(
            __import__("json").dumps(approval_record, indent=2), encoding="utf-8"
        )
    except Exception:
        pass  # Non-fatal; proceed with execution

    try:
        result = seed_execute(
            script_path=script_path,
            approved_sha256=approved_sha256,
            scenario_id=scenario_id,
            seed_run_id=f"seed-{ticket_id_raw}-{run_id}",
            run_id=run_id,
            ticket_id=ticket_id_raw,
            evidence_dir=evidence_dir,
            dry_run=dry_run,
        )
        return jsonify({"ok": True, "result": result.to_dict()})
    except Exception as exc:
        return jsonify({"ok": False, "error": "execution_error",
                        "message": str(exc)}), 500


@bp.post("/seed-proposal/cleanup")
def trigger_cleanup():
    """
    POST /api/qa-uat/seed-proposal/cleanup

    Trigger cleanup for seeded data after a UAT run.

    Body:
      {
          "run_id": "120",
          "ticket_id": 120,
          "scenario_id": "RF-007-CA-01",
          "seed_run_id": "seed-120-ABCDEF",
          "cleanup_policy": "after_run",   -- default
          "dry_run": true
      }

    Response:
      { "ok": true, "result": { "verdict": "CLEANED|SKIPPED|...", ... } }
    """
    _ensure_pipeline_on_path()

    body = request.get_json(silent=True) or {}
    run_id = str(body.get("run_id", "")).strip()
    ticket_id_raw = body.get("ticket_id")
    scenario_id = str(body.get("scenario_id", "")).strip()
    seed_run_id = str(body.get("seed_run_id", "")).strip()
    cleanup_policy = str(body.get("cleanup_policy", "after_run")).strip()
    dry_run = bool(body.get("dry_run", True))

    for field_name, val in [("run_id", run_id), ("scenario_id", scenario_id),
                             ("seed_run_id", seed_run_id)]:
        if not val:
            return jsonify({"ok": False, "error": f"missing_{field_name}",
                            "message": f"{field_name} is required"}), 400

    if ticket_id_raw is None:
        return jsonify({"ok": False, "error": "missing_ticket_id",
                        "message": "ticket_id is required"}), 400

    try:
        from cleanup_manager import cleanup as do_cleanup  # type: ignore[import]
    except ImportError as exc:
        return jsonify({"ok": False, "error": "import_error",
                        "message": f"cleanup_manager not available: {exc}"}), 503

    evidence_dir = _PIPELINE_ROOT / "evidence" / str(ticket_id_raw)
    run_dir = evidence_dir / run_id
    safe_id = re.sub(r"[^a-zA-Z0-9_\-]", "_", scenario_id)
    cleanup_script_path = run_dir / f"cleanup_proposal_{safe_id}.sql"

    if not cleanup_script_path.exists():
        return jsonify({"ok": False, "error": "cleanup_script_not_found",
                        "message": f"Cleanup script not found: {cleanup_script_path}"}), 404

    try:
        result = do_cleanup(
            cleanup_script_path=cleanup_script_path,
            seed_run_id=seed_run_id,
            scenario_id=scenario_id,
            run_id=run_id,
            ticket_id=ticket_id_raw,
            cleanup_policy=cleanup_policy,
            evidence_dir=evidence_dir,
            dry_run=dry_run,
        )
        return jsonify({"ok": True, "result": result.to_dict()})
    except Exception as exc:
        return jsonify({"ok": False, "error": "cleanup_error",
                        "message": str(exc)}), 500


@bp.get("/seed-proposal/approvals")
def list_seed_approvals():
    """
    GET /api/qa-uat/seed-proposal/approvals?run_id=<id>&ticket_id=<id>

    List all seed approval records for a run.

    Response: { "ok": true, "approvals": [...], "total": N }
    """
    run_id = request.args.get("run_id", "").strip()
    ticket_id_raw = request.args.get("ticket_id", "").strip()

    if not run_id:
        return jsonify({"ok": False, "error": "missing_run_id",
                        "message": "run_id is required"}), 400
    if not ticket_id_raw:
        return jsonify({"ok": False, "error": "missing_ticket_id",
                        "message": "ticket_id is required"}), 400

    run_dir = _PIPELINE_ROOT / "evidence" / str(ticket_id_raw) / run_id
    approvals = []
    if run_dir.is_dir():
        for ap_file in sorted(run_dir.glob("seed_approval_*.json")):
            try:
                approvals.append(__import__("json").loads(ap_file.read_text(encoding="utf-8")))
            except Exception:
                pass

    return jsonify({"ok": True, "approvals": approvals, "total": len(approvals)})


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


# ── Sprint 12: Catalog Readiness ───────────────────────────────────────────────


@bp.get("/catalog-readiness")
def get_catalog_readiness():
    """
    GET /api/qa-uat/catalog-readiness?run_id=&ticket_id=&scenario_id=

    Returns catalog readiness artifacts from the evidence directory for a
    given run. Reads `catalog_readiness_<scenario_id>.json` files.

    Query params:
      run_id      (required)
      ticket_id   (required)
      scenario_id (optional, filter)

    Response:
      { "ok": true, "catalogs": [...], "total": N }
    """
    run_id = request.args.get("run_id", "").strip()
    ticket_id = request.args.get("ticket_id", "").strip()
    scenario_id = request.args.get("scenario_id", "").strip()

    if not run_id:
        return jsonify({"ok": False, "error": "missing_run_id",
                        "message": "run_id is required"}), 400
    if not ticket_id:
        return jsonify({"ok": False, "error": "missing_ticket_id",
                        "message": "ticket_id is required"}), 400

    evidence_dir = _PIPELINE_ROOT / "evidence" / ticket_id / run_id
    pattern = f"catalog_readiness_{re.sub(r'[^a-zA-Z0-9_-]', '_', scenario_id)}*.json" \
        if scenario_id else "catalog_readiness_*.json"

    results = []
    for artifact in sorted(evidence_dir.glob(pattern)) if evidence_dir.is_dir() else []:
        try:
            data = json.loads(artifact.read_text(encoding="utf-8"))
            results.append(data)
        except Exception:
            pass

    return jsonify({"ok": True, "catalogs": results, "total": len(results)})


@bp.post("/catalog-readiness/check")
def check_catalog_readiness_endpoint():
    """
    POST /api/qa-uat/catalog-readiness/check

    Trigger an on-demand catalog readiness check for a list of catalog names.

    Body:
      {
          "run_id": "120",
          "ticket_id": 120,
          "scenario_id": "RF-007-CA-01",
          "required_catalogs": ["Provincia", "Departamento", "TipoDoc"],
          "dry_run": true
      }

    Response:
      { "ok": true, "result": { ...CatalogReadinessResult... } }
    """
    _ensure_pipeline_on_path()

    body = request.get_json(silent=True) or {}
    run_id = str(body.get("run_id", "")).strip()
    ticket_id_raw = body.get("ticket_id")
    scenario_id = str(body.get("scenario_id", "")).strip()
    required_catalogs = body.get("required_catalogs", [])
    dry_run = bool(body.get("dry_run", True))

    if not run_id:
        return jsonify({"ok": False, "error": "missing_run_id",
                        "message": "run_id is required"}), 400
    if ticket_id_raw is None:
        return jsonify({"ok": False, "error": "missing_ticket_id",
                        "message": "ticket_id is required"}), 400
    if not isinstance(required_catalogs, list) or not required_catalogs:
        return jsonify({"ok": False, "error": "missing_required_catalogs",
                        "message": "required_catalogs must be a non-empty list"}), 400

    try:
        from catalog_readiness_checker import check_catalog_readiness  # type: ignore[import]
    except ImportError as exc:
        return jsonify({"ok": False, "error": "import_error",
                        "message": f"catalog_readiness_checker not available: {exc}"}), 503

    evidence_dir = _PIPELINE_ROOT / "evidence"
    fixtures_path = _PIPELINE_ROOT / "fixtures" / "catalog_fixtures.yml"

    try:
        result = check_catalog_readiness(
            scenario_id=scenario_id or str(ticket_id_raw),
            required_catalogs=required_catalogs,
            db_url=None,  # read-only; no write credentials here
            exec_logger=None,
            evidence_dir=evidence_dir,
            run_id=run_id,
            ticket_id=ticket_id_raw,
            fixtures_path=fixtures_path,
            dry_run=dry_run,
        )
        return jsonify({"ok": True, "result": result.to_dict()})
    except Exception as exc:
        return jsonify({"ok": False, "error": "catalog_check_error",
                        "message": str(exc)}), 500


@bp.get("/catalog-readiness/fixtures")
def list_catalog_fixtures():
    """
    GET /api/qa-uat/catalog-readiness/fixtures

    Returns the list of catalog fixtures defined in catalog_fixtures.yml.
    Used by the frontend catalog dashboard to display available catalogs.

    Response:
      { "ok": true, "fixtures": [...], "total": N }
    """
    _ensure_pipeline_on_path()

    try:
        from catalog_readiness_checker import load_catalog_fixtures  # type: ignore[import]
    except ImportError as exc:
        return jsonify({"ok": False, "error": "import_error",
                        "message": f"catalog_readiness_checker not available: {exc}"}), 503

    fixtures_path = _PIPELINE_ROOT / "fixtures" / "catalog_fixtures.yml"
    try:
        fixtures = load_catalog_fixtures(fixtures_path)
        return jsonify({
            "ok": True,
            "fixtures": [f.to_dict() for f in fixtures.values()],
            "total": len(fixtures),
        })
    except Exception as exc:
        return jsonify({"ok": False, "error": "fixtures_load_error",
                        "message": str(exc)}), 500


# ── Sprint 13: Oracle Engine + Weak Assertion Detector ───────────────────────


@bp.get("/oracle-result")
def get_oracle_results():
    """
    GET /api/qa-uat/oracle-result?run_id=&ticket_id=&scenario_id=

    List oracle_result.json artifacts for a run.

    Query params:
      run_id     (required)
      ticket_id  (required)
      scenario_id (optional — filter by scenario)

    Response:
      { "ok": true, "results": [...], "total": N }
    """
    _ensure_pipeline_on_path()

    run_id = request.args.get("run_id", "").strip()
    ticket_id_raw = request.args.get("ticket_id", "").strip()
    scenario_id = request.args.get("scenario_id", "").strip()

    if not run_id or not ticket_id_raw:
        return jsonify({"ok": False, "error": "missing_params",
                        "message": "run_id and ticket_id are required"}), 400

    try:
        ticket_id = int(ticket_id_raw)
    except ValueError:
        return jsonify({"ok": False, "error": "invalid_ticket_id",
                        "message": "ticket_id must be an integer"}), 400

    evidence_dir = _PIPELINE_ROOT / "evidence" / str(ticket_id) / run_id

    results = []
    artifact_path = evidence_dir / "oracle_result.json"
    if artifact_path.is_file():
        try:
            import json as _json
            data = _json.loads(artifact_path.read_text(encoding="utf-8"))
            # Filter by scenario_id if provided
            if scenario_id:
                scenario_results = [
                    r for r in data.get("scenario_results", [])
                    if r.get("scenario_id") == scenario_id
                ]
                data = {**data, "scenario_results": scenario_results}
            results.append(data)
        except Exception as exc:
            return jsonify({"ok": False, "error": "read_error",
                            "message": str(exc)}), 500

    return jsonify({"ok": True, "results": results, "total": len(results)})


@bp.post("/oracle-result/evaluate")
def trigger_oracle_evaluation():
    """
    POST /api/qa-uat/oracle-result/evaluate

    Trigger on-demand oracle evaluation for a run.

    Body:
      {
          "run_id": "120",
          "ticket_id": 120,
          "scenarios_path": null,       -- optional, resolved from evidence_dir if absent
          "runner_output_path": null,   -- optional
          "oracle_contracts_dir": null  -- optional
      }

    Response:
      { "ok": true, "result": { ... OracleEvaluationResult ... } }
    """
    _ensure_pipeline_on_path()

    try:
        from oracle_engine import evaluate as oracle_evaluate  # type: ignore[import]
    except ImportError as exc:
        return jsonify({"ok": False, "error": "import_error",
                        "message": f"oracle_engine not available: {exc}"}), 503

    body = request.get_json(silent=True) or {}
    run_id = str(body.get("run_id", "")).strip()
    ticket_id_raw = body.get("ticket_id")

    if not run_id:
        return jsonify({"ok": False, "error": "missing_run_id",
                        "message": "run_id is required"}), 400

    if ticket_id_raw is None:
        return jsonify({"ok": False, "error": "missing_ticket_id",
                        "message": "ticket_id is required"}), 400

    try:
        ticket_id = int(ticket_id_raw)
    except (ValueError, TypeError):
        return jsonify({"ok": False, "error": "invalid_ticket_id",
                        "message": "ticket_id must be an integer"}), 400

    evidence_dir = _PIPELINE_ROOT / "evidence" / str(ticket_id) / run_id
    _pipeline_root = _PIPELINE_ROOT

    # Resolve paths: use body overrides or default to evidence locations
    scenarios_path_raw = body.get("scenarios_path")
    runner_output_path_raw = body.get("runner_output_path")
    oracle_contracts_dir_raw = body.get("oracle_contracts_dir")

    from pathlib import Path as _Path  # noqa: PLC0415
    scenarios_path = _Path(scenarios_path_raw) if scenarios_path_raw else evidence_dir / "scenarios.json"
    runner_output_path = _Path(runner_output_path_raw) if runner_output_path_raw else evidence_dir / "runner_output.json"
    oracle_contracts_dir = _Path(oracle_contracts_dir_raw) if oracle_contracts_dir_raw else evidence_dir / "oracle_contracts"
    fixtures_path = _pipeline_root / "fixtures" / "catalog_fixtures.yml"

    try:
        result = oracle_evaluate(
            scenarios_path=scenarios_path if scenarios_path.exists() else None,
            runner_output_path=runner_output_path if runner_output_path.exists() else None,
            oracle_contracts_dir=oracle_contracts_dir if oracle_contracts_dir.is_dir() else None,
            exec_logger=None,
            evidence_dir=evidence_dir,
            run_id=run_id,
            ticket_id=ticket_id,
            fixtures_path=fixtures_path if fixtures_path.exists() else None,
        )
        return jsonify({"ok": True, "result": result.to_dict()})
    except Exception as exc:
        return jsonify({"ok": False, "error": "oracle_evaluation_error",
                        "message": str(exc)}), 500


@bp.get("/oracle-result/weak-assertions")
def get_weak_assertions():
    """
    GET /api/qa-uat/oracle-result/weak-assertions?run_id=&ticket_id=

    Return the weak_assertion_report.json for a run.

    Query params:
      run_id     (required)
      ticket_id  (required)

    Response:
      { "ok": true, "report": { ... WeakAssertionReport ... } }
    """
    _ensure_pipeline_on_path()

    run_id = request.args.get("run_id", "").strip()
    ticket_id_raw = request.args.get("ticket_id", "").strip()

    if not run_id or not ticket_id_raw:
        return jsonify({"ok": False, "error": "missing_params",
                        "message": "run_id and ticket_id are required"}), 400

    try:
        ticket_id = int(ticket_id_raw)
    except ValueError:
        return jsonify({"ok": False, "error": "invalid_ticket_id",
                        "message": "ticket_id must be an integer"}), 400

    evidence_dir = _PIPELINE_ROOT / "evidence" / str(ticket_id) / run_id
    artifact_path = evidence_dir / "weak_assertion_report.json"

    if not artifact_path.is_file():
        return jsonify({"ok": True, "report": None,
                        "message": "no_report_available"})

    try:
        import json as _json
        report = _json.loads(artifact_path.read_text(encoding="utf-8"))
        return jsonify({"ok": True, "report": report})
    except Exception as exc:
        return jsonify({"ok": False, "error": "read_error",
                        "message": str(exc)}), 500


# ── Sprint 14: Test Confidence + Data Lineage ─────────────────────────────────


@bp.get("/confidence-report")
def get_confidence_report():
    """
    GET /api/qa-uat/confidence-report?run_id=&ticket_id=

    Return the confidence_report.json for a run.

    Query params:
      run_id     (required)
      ticket_id  (required)

    Response:
      { "ok": true, "report": { ... ConfidenceScorerResult ... } }
    """
    _ensure_pipeline_on_path()

    run_id = request.args.get("run_id", "").strip()
    ticket_id_raw = request.args.get("ticket_id", "").strip()

    if not run_id or not ticket_id_raw:
        return jsonify({"ok": False, "error": "missing_params",
                        "message": "run_id and ticket_id are required"}), 400

    try:
        ticket_id = int(ticket_id_raw)
    except ValueError:
        return jsonify({"ok": False, "error": "invalid_ticket_id",
                        "message": "ticket_id must be an integer"}), 400

    evidence_dir = _PIPELINE_ROOT / "evidence" / str(ticket_id) / run_id
    artifact_path = evidence_dir / "confidence_report.json"

    if not artifact_path.is_file():
        return jsonify({"ok": True, "report": None, "message": "no_report_available"})

    try:
        import json as _json
        report = _json.loads(artifact_path.read_text(encoding="utf-8"))
        return jsonify({"ok": True, "report": report})
    except Exception as exc:
        return jsonify({"ok": False, "error": "read_error",
                        "message": str(exc)}), 500


@bp.post("/confidence-report/score")
def trigger_confidence_score():
    """
    POST /api/qa-uat/confidence-report/score

    Trigger on-demand confidence scoring for a run.

    Body:
      {
          "run_id": "120",
          "ticket_id": 120,
          "min_confidence": 60,            -- optional, default 60
          "deployment_matched": null        -- optional bool
      }

    Response:
      { "ok": true, "result": { ... ConfidenceScorerResult ... } }
    """
    _ensure_pipeline_on_path()

    try:
        from test_confidence_scorer import score_all as confidence_score_all  # type: ignore[import]
    except ImportError as exc:
        return jsonify({"ok": False, "error": "import_error",
                        "message": f"test_confidence_scorer not available: {exc}"}), 503

    body = request.get_json(silent=True) or {}
    run_id = str(body.get("run_id", "")).strip()
    ticket_id_raw = body.get("ticket_id")

    if not run_id:
        return jsonify({"ok": False, "error": "missing_run_id",
                        "message": "run_id is required"}), 400
    if ticket_id_raw is None:
        return jsonify({"ok": False, "error": "missing_ticket_id",
                        "message": "ticket_id is required"}), 400

    try:
        ticket_id = int(ticket_id_raw)
    except (ValueError, TypeError):
        return jsonify({"ok": False, "error": "invalid_ticket_id",
                        "message": "ticket_id must be an integer"}), 400

    min_confidence = int(body.get("min_confidence", 60))
    deployment_matched = body.get("deployment_matched")  # None | True | False
    if deployment_matched is not None:
        deployment_matched = bool(deployment_matched)

    evidence_dir = _PIPELINE_ROOT / "evidence" / str(ticket_id) / run_id
    scenarios_file = evidence_dir / "scenarios.json"

    scenarios: list = []
    if scenarios_file.is_file():
        try:
            import json as _json
            raw = _json.loads(scenarios_file.read_text(encoding="utf-8"))
            scenarios = raw.get("scenarios", []) if isinstance(raw, dict) else raw
        except Exception:
            pass

    try:
        result = confidence_score_all(
            scenarios=scenarios,
            evidence_dir=evidence_dir,
            run_id=run_id,
            ticket_id=ticket_id,
            deployment_matched=deployment_matched,
            min_confidence=min_confidence,
        )
        return jsonify({"ok": True, "result": result.to_dict()})
    except Exception as exc:
        return jsonify({"ok": False, "error": "scoring_error",
                        "message": str(exc)}), 500


@bp.get("/data-lineage")
def get_data_lineage():
    """
    GET /api/qa-uat/data-lineage?run_id=&ticket_id=

    Return the data_lineage.json artifact for a run.

    Query params:
      run_id     (required)
      ticket_id  (required)

    Response:
      { "ok": true, "lineage": { ... DataLineageResult ... } }
    """
    _ensure_pipeline_on_path()

    run_id = request.args.get("run_id", "").strip()
    ticket_id_raw = request.args.get("ticket_id", "").strip()

    if not run_id or not ticket_id_raw:
        return jsonify({"ok": False, "error": "missing_params",
                        "message": "run_id and ticket_id are required"}), 400

    try:
        ticket_id = int(ticket_id_raw)
    except ValueError:
        return jsonify({"ok": False, "error": "invalid_ticket_id",
                        "message": "ticket_id must be an integer"}), 400

    evidence_dir = _PIPELINE_ROOT / "evidence" / str(ticket_id) / run_id
    artifact_path = evidence_dir / "data_lineage.json"

    if not artifact_path.is_file():
        return jsonify({"ok": True, "lineage": None, "message": "no_lineage_available"})

    try:
        import json as _json
        lineage = _json.loads(artifact_path.read_text(encoding="utf-8"))
        return jsonify({"ok": True, "lineage": lineage})
    except Exception as exc:
        return jsonify({"ok": False, "error": "read_error",
                        "message": str(exc)}), 500


@bp.post("/data-lineage/build")
def trigger_data_lineage_build():
    """
    POST /api/qa-uat/data-lineage/build

    Trigger on-demand data lineage build for a run.

    Body:
      { "run_id": "120", "ticket_id": 120 }

    Response:
      { "ok": true, "result": { ... DataLineageResult ... } }
    """
    _ensure_pipeline_on_path()

    try:
        from data_lineage_builder import build as lineage_build  # type: ignore[import]
    except ImportError as exc:
        return jsonify({"ok": False, "error": "import_error",
                        "message": f"data_lineage_builder not available: {exc}"}), 503

    body = request.get_json(silent=True) or {}
    run_id = str(body.get("run_id", "")).strip()
    ticket_id_raw = body.get("ticket_id")

    if not run_id:
        return jsonify({"ok": False, "error": "missing_run_id",
                        "message": "run_id is required"}), 400
    if ticket_id_raw is None:
        return jsonify({"ok": False, "error": "missing_ticket_id",
                        "message": "ticket_id is required"}), 400

    try:
        ticket_id = int(ticket_id_raw)
    except (ValueError, TypeError):
        return jsonify({"ok": False, "error": "invalid_ticket_id",
                        "message": "ticket_id must be an integer"}), 400

    evidence_dir = _PIPELINE_ROOT / "evidence" / str(ticket_id) / run_id

    try:
        result = lineage_build(
            evidence_dir=evidence_dir,
            run_id=run_id,
            ticket_id=ticket_id,
        )
        return jsonify({"ok": True, "result": result.to_dict()})
    except Exception as exc:
        return jsonify({"ok": False, "error": "lineage_build_error",
                        "message": str(exc)}), 500
