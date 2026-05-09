"""
qa_dossier_builder.py — Sprint 5: Generar dossier canónico de pipeline para revisión humana.

PURPOSE
-------
Produce dossier.json and ado_comment.html for every pipeline run,
including runs blocked before Playwright ever started. This complements
uat_dossier_builder.py (which is runner-output focused) by being
pipeline-centric: it covers the full run lifecycle from session_start
to pipeline_verdict_decision.

Unlike uat_dossier_builder.py, this module:
  - Works even with no runner_output.json (BLOCKED early exits)
  - Derives its data primarily from execution.jsonl and result.json
  - Produces a lightweight dossier focused on: what happened, why,
    who needs to act, what evidence exists, and is it publishable.

USAGE (library)
---------------
  from qa_dossier_builder import build_dossier, build_ado_comment_html
  dossier = build_dossier(
      ticket_id=122,
      run_id="uat-122-...",
      evidence_dir=Path("evidence/122/uat-122-..."),
      result=pipeline_result,   # from qa_uat_pipeline._build_output or run()
  )
  # Writes: evidence_dir/dossier.json, evidence_dir/ado_comment.html,
  #         evidence_dir/publish_audit.json

USAGE (CLI)
-----------
  python qa_dossier_builder.py \\
      --evidence-dir evidence/122/uat-122-... \\
      --ticket-id 122 \\
      [--result result.json] \\
      [--verbose]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.qa_uat.qa_dossier_builder")

_TOOL_VERSION = "1.0.0"
_SCHEMA_VERSION = "qa-pipeline-dossier/1.0"


# ── Summary generation ────────────────────────────────────────────────────────

def _root_cause_summary(result: dict) -> str:
    """Generate a concise, human-readable root cause string from result."""
    verdict  = result.get("verdict", "UNKNOWN")
    category = result.get("category", "")
    reason   = result.get("reason", "")
    stage    = result.get("failed_stage") or result.get("stage", "")
    message  = result.get("message", "")

    if verdict in ("PASS", "PARTIAL_PASS"):
        return "All executable scenarios passed."

    parts = []
    if stage:
        parts.append(f"Failed at stage '{stage}'.")
    if category and reason:
        parts.append(f"[{category}] {reason}.")
    elif reason:
        parts.append(f"Reason: {reason}.")
    if message and message not in reason:
        parts.append(message[:200])
    return " ".join(parts) or f"Pipeline exited with verdict={verdict}."


def _human_action_required(result: dict) -> str:
    """Extract or generate a human-readable action."""
    explicit = result.get("human_action_required")
    if explicit:
        return str(explicit)

    verdict  = result.get("verdict", "BLOCKED")
    reason   = result.get("reason", "")
    category = result.get("category", "")

    action_map = {
        "UI_MAP_MISSING":                 "Run ui_map_builder.py --screen <SCREEN> --rebuild",
        "SELECTOR_ALIAS_NOT_IN_UI_MAP":   "Add missing aliases to UI map and rebuild selector contract",
        "COMPILER_EMPTY":                 "Check ticket acceptance criteria — no scenarios were generated",
        "NO_EXECUTABLE_SCENARIOS":        "Review out_of_scope list — all scenarios were excluded",
        "COMPILER_CONTRACT_INVALID":      "Fix compiler output schema violations (see compiler_contract_result.json)",
        "GENERATOR_CONTRACT_INVALID":     "Fix generator output schema violations (see generator_contract_result.json)",
        "GRID_EMPTY":                     "Provide test data with matching entities (see data_readiness.json)",
        "CATALOG_MISSING":                "Create or restore the missing catalog data",
        "CATALOG_EMPTY":                  "Populate the required catalog with test data",
        "BUILD_MISMATCH":                 "Deploy the expected build or update deployment fingerprint config",
        "BUILD_UNVERIFIABLE":             "Check deployment fingerprint service / application version endpoint",
        "MISSING_CREDENTIALS":            "Set AGENDA_WEB_USER and AGENDA_WEB_PASS environment variables",
        "EVIDENCE_INCOMPLETE":            "Rerun pipeline — missing artifacts indicate an early crash",
        "ASSERTION_FAILED":              "Review failing test assertions in dossier and runner_output.json",
        "RUNNER_CRASH":                   "Check playwright-report/ and console.log for crash details",
        "UNKNOWN":                        "Open bug P0 in Stacky — UNKNOWN verdict must never occur in new runs",
    }
    if reason in action_map:
        return action_map[reason]
    if verdict in ("FAIL", "MIXED"):
        return "Review dossier and runner_output.json, then approve or reject publication to ADO"
    if verdict == "BLOCKED":
        return f"Investigate {category}/{reason} and rerun pipeline"
    return "Review dossier and decide whether to publish to ADO"


def _collect_evidence_refs(evidence_dir: Path) -> list[str]:
    """List existing artifact files in evidence_dir (relative names)."""
    if not evidence_dir.exists():
        return []
    return sorted(
        f.name
        for f in evidence_dir.iterdir()
        if f.is_file() and not f.name.startswith(".")
    )


def _compute_publish_audit_hash(ticket_id: int, run_id: str, verdict: str, reason: str) -> str:
    """Stable content hash for idempotency of ADO publish."""
    payload = f"{ticket_id}|{run_id}|{verdict}|{reason}"
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


# ── Build dossier ─────────────────────────────────────────────────────────────

def build_dossier(
    ticket_id: int,
    run_id: str,
    evidence_dir: Path,
    result: dict,
    exec_log_events: Optional[list] = None,
    verbose: bool = False,
) -> dict:
    """Build and write dossier.json (and supporting files) for a pipeline run.

    Parameters
    ----------
    ticket_id : int
        ADO work item ID.
    run_id : str
        Canonical run identity (e.g., uat-122-20240101T120000Z-abc123).
    evidence_dir : Path
        Run-specific evidence directory.
    result : dict
        Pipeline result dict (from _build_output or run()).
    exec_log_events : list | None
        Optionally pass pre-loaded execution.jsonl events (avoids re-reading).
    verbose : bool

    Returns
    -------
    dict — the dossier document (same as written to dossier.json).
    """
    t0 = time.monotonic()
    evidence_dir = Path(evidence_dir)
    if verbose:
        logging.basicConfig(level=logging.DEBUG, stream=sys.stderr,
                            format="%(levelname)s %(name)s: %(message)s")

    # ── Extract fields from result ────────────────────────────────────────────
    verdict      = result.get("verdict") or "BLOCKED"
    category     = result.get("category") or "PIP"
    reason       = result.get("reason") or "pipeline_error"
    failed_stage = result.get("failed_stage") or result.get("stage") or "unknown"
    confidence   = result.get("confidence", 1.0)
    ok           = result.get("ok", False)

    root_cause = _root_cause_summary(result)
    human_action = _human_action_required(result)
    evidence_refs = _collect_evidence_refs(evidence_dir)

    # ── Load exec log summary if needed ───────────────────────────────────────
    exec_summary: dict = {}
    if exec_log_events is None:
        exec_jsonl = evidence_dir / "execution.jsonl"
        if exec_jsonl.exists():
            try:
                events = []
                for line in exec_jsonl.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line:
                        events.append(json.loads(line))
                exec_log_events = events
            except Exception as e:  # noqa: BLE001
                logger.warning("qa_dossier_builder: could not read execution.jsonl: %s", e)
                exec_log_events = []

    if exec_log_events:
        session_start = next(
            (e for e in exec_log_events if e.get("event") == "session_start"), {}
        )
        pipeline_verdict_ev = next(
            (e for e in reversed(exec_log_events)
             if e.get("event") == "pipeline_verdict_decision"), {}
        )
        exec_summary = {
            "session_started_at": session_start.get("ts") or session_start.get("data", {}).get("ts"),
            "pipeline_verdict_decision_emitted": bool(pipeline_verdict_ev),
            "total_events": len(exec_log_events),
        }

    # ── Artifacts present ─────────────────────────────────────────────────────
    artifacts: dict[str, str] = {}
    for fname in evidence_refs:
        artifacts[fname.replace(".", "_")] = str(evidence_dir / fname)

    # ── Build dossier ─────────────────────────────────────────────────────────
    now_iso = datetime.now(timezone.utc).isoformat()

    dossier: dict = {
        "schema_version": _SCHEMA_VERSION,
        "tool_version": _TOOL_VERSION,
        "generated_at": now_iso,
        "ticket_id": ticket_id,
        "run_id": run_id,
        "verdict": verdict,
        "category": category,
        "reason": reason,
        "failed_stage": failed_stage if not ok else None,
        "ok": ok,
        "confidence": confidence,
        "root_cause_summary": root_cause,
        "human_action_required": human_action,
        "exec_summary": exec_summary,
        "artifacts": artifacts,
        "evidence_refs": evidence_refs,
        "elapsed_build_ms": round((time.monotonic() - t0) * 1000, 1),
    }

    # ── Write dossier.json ────────────────────────────────────────────────────
    dossier_path = evidence_dir / "dossier.json"
    try:
        evidence_dir.mkdir(parents=True, exist_ok=True)
        dossier_path.write_text(
            json.dumps(dossier, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        logger.debug("qa_dossier_builder: wrote %s", dossier_path)
    except Exception as e:  # noqa: BLE001
        logger.error("qa_dossier_builder: could not write dossier.json: %s", e)

    # ── Write ado_comment.html ────────────────────────────────────────────────
    html = build_ado_comment_html(dossier)
    html_path = evidence_dir / "ado_comment.html"
    try:
        html_path.write_text(html, encoding="utf-8")
        logger.debug("qa_dossier_builder: wrote %s", html_path)
    except Exception as e:  # noqa: BLE001
        logger.warning("qa_dossier_builder: could not write ado_comment.html: %s", e)

    # ── Write publish_audit.json ──────────────────────────────────────────────
    content_hash = _compute_publish_audit_hash(ticket_id, run_id, verdict, reason)
    publish_audit = {
        "schema_version": _SCHEMA_VERSION,
        "ticket_id": ticket_id,
        "run_id": run_id,
        "verdict": verdict,
        "reason": reason,
        "content_hash": content_hash,
        "generated_at": now_iso,
        "idempotency_key": f"{run_id}|{content_hash}",
    }
    audit_path = evidence_dir / "publish_audit.json"
    try:
        audit_path.write_text(
            json.dumps(publish_audit, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        logger.debug("qa_dossier_builder: wrote %s", audit_path)
    except Exception as e:  # noqa: BLE001
        logger.warning("qa_dossier_builder: could not write publish_audit.json: %s", e)

    dossier["_publish_audit"] = publish_audit
    return dossier


# ── ADO comment HTML ──────────────────────────────────────────────────────────

_VERDICT_COLORS = {
    "PASS": "#107C10",
    "PARTIAL_PASS": "#498205",
    "FAIL": "#A4262C",
    "MIXED": "#CA5010",
    "BLOCKED": "#797775",
    "SKIPPED": "#605E5C",
}

_VERDICT_ICONS = {
    "PASS": "✅",
    "PARTIAL_PASS": "🟡",
    "FAIL": "❌",
    "MIXED": "⚠️",
    "BLOCKED": "🚫",
    "SKIPPED": "⏭️",
}


def build_ado_comment_html(dossier: dict) -> str:
    """Build an HTML string suitable for posting as an ADO work item comment."""
    verdict = dossier.get("verdict", "UNKNOWN")
    category = dossier.get("category", "")
    reason = dossier.get("reason", "")
    failed_stage = dossier.get("failed_stage") or ""
    ticket_id = dossier.get("ticket_id", "")
    run_id = dossier.get("run_id", "")
    root_cause = dossier.get("root_cause_summary", "")
    human_action = dossier.get("human_action_required", "")
    generated_at = dossier.get("generated_at", "")
    confidence = dossier.get("confidence", 1.0)
    evidence_refs = dossier.get("evidence_refs", [])

    color = _VERDICT_COLORS.get(verdict, "#605E5C")
    icon  = _VERDICT_ICONS.get(verdict, "❓")

    refs_html = ""
    if evidence_refs:
        items = "".join(f"<li><code>{r}</code></li>" for r in evidence_refs[:20])
        refs_html = f"<details><summary>Evidence artifacts ({len(evidence_refs)})</summary><ul>{items}</ul></details>"

    failed_stage_row = (
        f"<tr><td><b>Failed Stage</b></td><td><code>{failed_stage}</code></td></tr>"
        if failed_stage else ""
    )

    html = f"""<div style="font-family:Segoe UI,Arial,sans-serif;max-width:720px">
<h3 style="border-left:4px solid {color};padding-left:8px;margin:0 0 12px">
  {icon} QA UAT Pipeline — {verdict}
</h3>
<table style="border-collapse:collapse;width:100%;font-size:13px">
<tbody>
<tr><td style="width:140px"><b>Ticket</b></td><td>#{ticket_id}</td></tr>
<tr><td><b>Run ID</b></td><td><code style="font-size:11px">{run_id}</code></td></tr>
<tr><td><b>Verdict</b></td><td><span style="color:{color};font-weight:bold">{verdict}</span></td></tr>
<tr><td><b>Category</b></td><td><code>{category}</code></td></tr>
<tr><td><b>Reason</b></td><td><code>{reason}</code></td></tr>
{failed_stage_row}
<tr><td><b>Confidence</b></td><td>{confidence:.0%}</td></tr>
<tr><td><b>Generated</b></td><td>{generated_at}</td></tr>
</tbody>
</table>
<hr style="margin:12px 0;border:none;border-top:1px solid #e0e0e0">
<p><b>Root Cause:</b> {root_cause}</p>
<p><b>Action Required:</b> <em>{human_action}</em></p>
{refs_html}
<p style="color:#797775;font-size:11px;margin-top:16px">
  Generated by Stacky QA UAT Agent — qa_dossier_builder v{_TOOL_VERSION}<br>
  This comment was produced automatically. Human review required before publishing.
</p>
</div>"""
    return html


# ── CLI ───────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Build QA pipeline dossier for a run.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--evidence-dir", required=True, help="Run evidence directory path")
    p.add_argument("--ticket-id", type=int, required=True, help="ADO ticket ID")
    p.add_argument("--run-id", help="Run ID (default: inferred from evidence-dir name)")
    p.add_argument("--result", help="Path to result.json (default: <evidence-dir>/result.json)")
    p.add_argument("--verbose", action="store_true")
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, stream=sys.stderr,
                            format="%(levelname)s %(name)s: %(message)s")

    evidence_dir = Path(args.evidence_dir)
    run_id = args.run_id or evidence_dir.name

    result_path = Path(args.result) if args.result else evidence_dir / "result.json"
    if result_path.exists():
        result = json.loads(result_path.read_text(encoding="utf-8"))
    else:
        result = {"verdict": "BLOCKED", "reason": "result_json_not_found"}
        logger.warning("result.json not found at %s — using minimal result", result_path)

    dossier = build_dossier(
        ticket_id=args.ticket_id,
        run_id=run_id,
        evidence_dir=evidence_dir,
        result=result,
        verbose=args.verbose,
    )

    print(json.dumps(dossier, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
