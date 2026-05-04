"""
ado_evidence_publisher.py — Publish UAT dossier as an ADO comment (with idempotence).

SPEC: SPEC/ado_evidence_publisher.md
CLI:
    python ado_evidence_publisher.py \
        --ticket-id 70 \
        --dossier evidence/70/dossier.json \
        [--mode dry-run | publish] \
        [--ado-path <path>] \
        [--verbose]

SAFETY RULES:
  1. Default mode is DRY-RUN. Never publish without explicit --mode publish.
  2. FORBIDDEN: ado.py state / update_state subcommands in all uat_*.py files.
     (enforced by test_no_state_subcommand_in_codebase).
  3. Idempotence: Check existing comments for the stacky-qa-uat marker.
     - Same hash → skip (already published).
     - Different hash → update comment.
  4. Audit log written on EVERY invocation (dry-run and publish).

Output: JSON to stdout.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.qa_uat.evidence_publisher")

_TOOL_VERSION = "1.0.0"
_MARKER_RE = re.compile(
    r'<!--\s*stacky-qa-uat:run\s+id="([^"]+)"\s+hash="([^"]+)"\s*-->',
    re.IGNORECASE,
)
_AUDIT_DIR = Path(__file__).resolve().parent / "audit"


def _resolve_sibling_tool(tool_dir_name: str, entrypoint: str) -> Path:
    """Locate a sibling tool by walking up to the `Stacky tools` container.

    See qa_uat_pipeline._resolve_sibling_tool for full rationale. Required
    because this file used to compute `parent.parent.parent / "ADO Manager"`,
    which lands one level too high (Stacky/, not Stacky tools/) and breaks
    any invocation outside ADO Manager's working dir.
    """
    here = Path(__file__).resolve()
    for ancestor in here.parents:
        if ancestor.name == "Stacky tools":
            return ancestor / tool_dir_name / entrypoint
    return Path(__file__).resolve().parent.parent / tool_dir_name / entrypoint


_DEFAULT_ADO_PATH = _resolve_sibling_tool("ADO Manager", "ado.py")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    args = _parse_args()
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, stream=sys.stderr,
                            format="%(levelname)s %(name)s: %(message)s")
    else:
        logging.basicConfig(level=logging.WARNING, stream=sys.stderr)

    result = run(
        ticket_id=args.ticket_id,
        dossier_path=Path(args.dossier),
        mode=args.mode,
        ado_path=Path(args.ado_path) if args.ado_path else None,
        verbose=args.verbose,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result.get("ok") else 1)


def run(
    ticket_id: int,
    dossier_path: Path,
    mode: str = "dry-run",
    ado_path: Optional[Path] = None,
    verbose: bool = False,
) -> dict:
    """Core logic — callable from tests."""
    started = time.time()
    ado_path = ado_path or _DEFAULT_ADO_PATH

    # Load dossier
    try:
        dossier = json.loads(dossier_path.read_text(encoding="utf-8"))
    except Exception as exc:
        result = _err("missing_dossier", f"Cannot read dossier.json: {exc}")
        _write_audit(ticket_id, mode, result, dossier_path)
        return result

    if not dossier.get("ok"):
        result = _err("missing_dossier", "dossier.json has ok=false")
        _write_audit(ticket_id, mode, result, dossier_path)
        return result

    # Locate ado_comment.html
    dossier_dir = dossier_path.parent
    html_path = dossier_dir / "ado_comment.html"
    if not html_path.is_file():
        result = _err("missing_artifact", "ado_comment.html not found next to dossier.json")
        _write_audit(ticket_id, mode, result, dossier_path)
        return result

    html_content = html_path.read_text(encoding="utf-8")

    # Extract marker from the HTML
    marker_match = _MARKER_RE.search(html_content)
    if not marker_match:
        result = _err("marker_not_found",
                      "Idempotence marker not found in ado_comment.html. "
                      "Re-run uat_dossier_builder to regenerate.")
        _write_audit(ticket_id, mode, result, dossier_path)
        return result

    run_id = marker_match.group(1)
    comment_hash = marker_match.group(2)

    # Dry-run: generate preview without touching ADO
    if mode == "dry-run":
        result = {
            "ok": True,
            "mode": "dry-run",
            "ticket_id": ticket_id,
            "run_id": run_id,
            "comment_hash": comment_hash,
            "verdict": dossier.get("verdict"),
            "action": "preview_only",
            "message": "DRY-RUN: No changes made to ADO. Run with --mode publish to publish.",
            "html_preview_length": len(html_content),
            "meta": {"tool": "ado_evidence_publisher", "version": _TOOL_VERSION,
                     "duration_ms": int((time.time() - started) * 1000)},
        }
        _write_audit(ticket_id, mode, result, dossier_path)
        return result

    # Publish mode: check idempotence
    existing = _get_existing_comment(ticket_id, ado_path)
    if existing is None:
        # ADO call failed
        result = _err("ado_manager_failure",
                      "Failed to retrieve existing comments from ADO")
        _write_audit(ticket_id, mode, result, dossier_path)
        return result

    existing_run_id, existing_hash = existing.get("run_id"), existing.get("hash")

    if existing_hash == comment_hash:
        result = {
            "ok": True,
            "mode": "publish",
            "ticket_id": ticket_id,
            "run_id": run_id,
            "comment_hash": comment_hash,
            "verdict": dossier.get("verdict"),
            "action": "skipped_unchanged",
            "message": "Comment already published with the same hash. No update needed.",
            "meta": {"tool": "ado_evidence_publisher", "version": _TOOL_VERSION,
                     "duration_ms": int((time.time() - started) * 1000)},
        }
        _write_audit(ticket_id, mode, result, dossier_path)
        return result

    # Post or update comment
    action = "updated" if existing_hash else "created"
    publish_result = _post_comment(ticket_id, html_content, ado_path)
    if not publish_result.get("ok"):
        result = _err("ado_manager_failure",
                      f"ADO Manager error: {publish_result.get('message', 'unknown')}")
        _write_audit(ticket_id, mode, result, dossier_path)
        return result

    result = {
        "ok": True,
        "mode": "publish",
        "ticket_id": ticket_id,
        "run_id": run_id,
        "comment_hash": comment_hash,
        "verdict": dossier.get("verdict"),
        "action": action,
        "message": f"Comment {action} successfully in ADO ticket #{ticket_id}.",
        "meta": {"tool": "ado_evidence_publisher", "version": _TOOL_VERSION,
                 "duration_ms": int((time.time() - started) * 1000)},
    }
    _write_audit(ticket_id, mode, result, dossier_path)
    return result


# ── ADO interaction ────────────────────────────────────────────────────────────

def _ado_subprocess_env() -> dict:
    """
    Force UTF-8 IO for the ado.py child process. Without this, Windows
    cp1252 stdout fails on tickets containing non-ASCII chars (e.g. arrow
    glyphs in comments) with: 'charmap' codec can't encode character.
    """
    import os
    return {**os.environ, "PYTHONIOENCODING": "utf-8"}


def _get_existing_comment(ticket_id: int, ado_path: Path) -> Optional[dict]:
    """
    Call `python ado.py comments <id>` and scan for stacky-qa-uat marker.
    Returns {"run_id": ..., "hash": ...} or {} if not found, or None on failure.
    """
    try:
        proc = subprocess.run(
            [sys.executable, str(ado_path), "comments", str(ticket_id)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            env=_ado_subprocess_env(),
        )
        if proc.returncode != 0:
            logger.warning("ado.py comments returned exit %d: %s", proc.returncode, proc.stderr[:200])
            return None
        data = json.loads(proc.stdout)
        # ADO Manager returns the list under "result" (current contract);
        # fall back to "comments" for backward compatibility.
        comments = data.get("result") or data.get("comments") or []
        for comment in comments:
            text = comment.get("text", "")
            m = _MARKER_RE.search(text)
            if m:
                return {"run_id": m.group(1), "hash": m.group(2)}
        return {}  # Not found = no existing comment
    except Exception as exc:
        logger.error("Error calling ado.py comments: %s", exc)
        return None


def _post_comment(ticket_id: int, html_content: str, ado_path: Path) -> dict:
    """
    Call `python ado.py comment <id> --html --text "<html>"`.
    Returns the ADO Manager JSON response.
    """
    try:
        proc = subprocess.run(
            [sys.executable, str(ado_path), "comment", str(ticket_id),
             "--html", "--text", html_content],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            env=_ado_subprocess_env(),
        )
        if proc.returncode != 0:
            try:
                return json.loads(proc.stdout)
            except Exception:
                return {"ok": False, "message": proc.stderr[:200]}
        return json.loads(proc.stdout)
    except subprocess.TimeoutExpired:
        return {"ok": False, "message": "ADO Manager call timed out"}
    except Exception as exc:
        return {"ok": False, "message": str(exc)[:200]}


# ── Audit log ─────────────────────────────────────────────────────────────────

def _write_audit(ticket_id: int, mode: str, result: dict, dossier_path: Path) -> None:
    """Append an audit row to audit/<YYYY-MM-DD>.jsonl."""
    try:
        _AUDIT_DIR.mkdir(parents=True, exist_ok=True)
        today = datetime.utcnow().strftime("%Y-%m-%d")
        log_file = _AUDIT_DIR / f"{today}.jsonl"
        row = {
            "ts": datetime.utcnow().isoformat() + "Z",
            "ticket_id": ticket_id,
            "mode": mode,
            "ok": result.get("ok", False),
            "action": result.get("action"),
            "verdict": result.get("verdict"),
            "error": result.get("error"),
            "dossier_path": str(dossier_path),
        }
        with log_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.warning("Could not write audit log: %s", exc)


# ── Utilities ─────────────────────────────────────────────────────────────────

def _err(code: str, message: str) -> dict:
    return {"ok": False, "error": code, "message": message}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="ado_evidence_publisher — Publish UAT dossier to ADO"
    )
    parser.add_argument("--ticket-id", required=True, type=int, dest="ticket_id")
    parser.add_argument("--dossier", required=True, help="Path to dossier.json")
    parser.add_argument(
        "--mode",
        choices=["dry-run", "publish"],
        default="dry-run",
        help="dry-run (default) or publish",
    )
    parser.add_argument("--ado-path", default=None, dest="ado_path",
                        help="Path to ado.py (default: auto-detect)")
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    main()
