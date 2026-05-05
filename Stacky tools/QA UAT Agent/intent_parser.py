"""
intent_parser.py — Validate and normalize an intent_spec.json produced by the
orchestrator agent (UserInterfaceQAFreeForm).

Fase 1 of the QA UAT Agent free-form improvement plan.
Fase 2 adds automatic navigation_path[] computation via path_planner.py.

This tool does NOT use an LLM.  The orchestrator agent is responsible for
producing a well-formed intent_spec.json.  This tool only:
  1. Validates the file against schemas/intent_spec.schema.json.
  2. Resolves placeholder tokens (e.g. ``{{LOTE_ID}}``) inside test_cases[]
     using the ``resolved_data`` dict.
  3. Detects remaining unresolved placeholders and returns them as
     ``pending_data`` so the caller can emit a data_request.
  4. [Fase 2] Auto-computes navigation_path[] via the navigation graph + BFS
     when the field is absent or empty in intent_spec.

CLI:
    python intent_parser.py --intent-file intent_spec.json [--verbose]
    python intent_parser.py --intent-file intent_spec.json --data-file resolved_data.json [--verbose]

Output: JSON to stdout
    {"ok": true,  "intent_spec": {...}, "pending_data": [...]}
    {"ok": false, "error": "validation_failed", "message": "...", "details": [...]}

Exit codes:
    0  — ok, all placeholders resolved
    1  — hard error (file not found, invalid JSON, schema violation)
    2  — ok but pending_data is non-empty (data_request needed)
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("stacky.qa_uat.intent_parser")

_TOOL_VERSION = "1.1.0"
_SCHEMAS_DIR = Path(__file__).resolve().parent / "schemas"
_EVIDENCE_DIR = Path(__file__).resolve().parent / "evidence"

# Path planner is a Fase-2 optional dependency.  If navigation_graph.py or
# path_planner.py are not present (e.g. running on an old installation), the
# parser degrades gracefully and leaves navigation_path empty.
try:
    import path_planner as _path_planner
    _PATH_PLANNER_AVAILABLE = True
except ImportError:
    _path_planner = None  # type: ignore[assignment]
    _PATH_PLANNER_AVAILABLE = False

# Regex matching placeholder tokens like {{LOTE_ID}} or {LOTE_ID} in values.
_PLACEHOLDER_RE = re.compile(r'\{\{?([A-Z][A-Z0-9_]*)\}?\}')


# ── Public API ────────────────────────────────────────────────────────────────

def run(
    intent_file: Path,
    data_file: Optional[Path] = None,
    verbose: bool = False,
) -> dict:
    """Validate and normalize intent_spec, resolving data from data_file.

    Returns:
        {
            "ok": True,
            "intent_spec": <normalized dict>,
            "pending_data": [],          # empty = all resolved
            "run_id": "<str>",
            "meta": {...}
        }
    or on hard error:
        {"ok": False, "error": "<code>", "message": "<str>"}
    Exit code 2 when ok=True but pending_data is non-empty.
    """
    started = time.time()

    # ── Load intent_spec.json ────────────────────────────────────────────────
    try:
        raw = intent_file.read_text(encoding="utf-8")
        intent_spec = json.loads(raw)
    except FileNotFoundError:
        return _err("intent_file_not_found", f"File not found: {intent_file}")
    except json.JSONDecodeError as exc:
        return _err("intent_file_invalid_json", f"Cannot parse {intent_file}: {exc}")

    if not isinstance(intent_spec, dict):
        return _err("intent_file_invalid_json", "intent_spec.json must be a JSON object")

    # ── Validate required top-level fields ───────────────────────────────────
    required = ("intent_raw", "test_cases")
    missing = [f for f in required if not intent_spec.get(f)]
    if missing:
        return _err("intent_spec_missing_fields",
                    f"Required fields missing or empty: {missing}")

    if not isinstance(intent_spec.get("test_cases"), list) or not intent_spec["test_cases"]:
        return _err("intent_spec_empty_test_cases",
                    "test_cases must be a non-empty list")

    # ── Merge extra resolved_data from data_file ─────────────────────────────
    resolved_data: dict = dict(intent_spec.get("resolved_data") or {})
    if data_file and data_file.is_file():
        try:
            extra = json.loads(data_file.read_text(encoding="utf-8"))
            if isinstance(extra, dict):
                resolved_data.update(extra)
                logger.debug("Merged %d entries from data_file %s", len(extra), data_file)
        except Exception as exc:
            logger.warning("Could not load data_file %s: %s — ignoring", data_file, exc)

    # Normalize resolved_data values to strings (sqlcmd may return ints)
    resolved_data = {k: str(v) for k, v in resolved_data.items()}

    # ── Resolve placeholders in test_cases ───────────────────────────────────
    test_cases, pending = _resolve_test_cases(
        intent_spec["test_cases"], resolved_data
    )
    intent_spec = dict(intent_spec)  # shallow copy — don't mutate caller's dict
    intent_spec["test_cases"] = test_cases
    intent_spec["resolved_data"] = resolved_data
    intent_spec["pending_data"] = pending

    # Ensure run_id exists
    run_id = intent_spec.get("run_id") or f"freeform-{_ts()}"
    intent_spec["run_id"] = run_id

    # ── [Fase 2] Auto-compute navigation_path via path planner ───────────────
    path_planner_used = False
    path_planner_warning = ""
    if not intent_spec.get("navigation_path") and _PATH_PLANNER_AVAILABLE:
        goal_action = intent_spec.get("goal_action") or ""
        entry_screen = intent_spec.get("entry_screen") or None
        if goal_action:
            try:
                plan_result = _path_planner.plan(
                    goal_action=goal_action,
                    entry_screen=entry_screen,
                    assume_logged_in=False,
                )
                intent_spec["navigation_path"] = plan_result.path
                path_planner_used = True
                if plan_result.warning:
                    path_planner_warning = plan_result.warning
                logger.debug(
                    "intent_parser: path_planner computed path %s (source=%s)",
                    plan_result.path, plan_result.source,
                )
            except Exception as exc:
                logger.warning("intent_parser: path_planner failed: %s", exc)
        else:
            logger.debug(
                "intent_parser: navigation_path absent but no goal_action — skipping path planner"
            )
    elif intent_spec.get("navigation_path"):
        logger.debug(
            "intent_parser: navigation_path already present — path planner skipped"
        )

    logger.debug(
        "intent_parser: run_id=%s test_cases=%d resolved=%d pending=%d path_planner=%s",
        run_id, len(test_cases), len(resolved_data), len(pending), path_planner_used,
    )

    return {
        "ok": True,
        "intent_spec": intent_spec,
        "pending_data": pending,
        "run_id": run_id,
        "meta": {
            "tool": "intent_parser",
            "version": _TOOL_VERSION,
            "duration_ms": int((time.time() - started) * 1000),
            "path_planner_used": path_planner_used,
            "path_planner_warning": path_planner_warning,
        },
    }


# ── Internal helpers ─────────────────────────────────────────────────────────

def _resolve_test_cases(
    test_cases: list,
    resolved_data: dict,
) -> tuple[list, list]:
    """Replace {{PLACEHOLDER}} tokens in test_case fields.

    Returns (resolved_test_cases, pending_fields_list).
    pending_fields_list contains dicts: {field, in_case_id, description}.
    """
    resolved: list = []
    pending_map: dict = {}  # field → list of case ids

    for case in test_cases:
        if not isinstance(case, dict):
            resolved.append(case)
            continue
        new_case = {}
        for key, value in case.items():
            if not isinstance(value, str):
                new_case[key] = value
                continue
            resolved_value, unresolved = _resolve_string(value, resolved_data)
            new_case[key] = resolved_value
            for field in unresolved:
                pending_map.setdefault(field, []).append(case.get("id", "?"))
        resolved.append(new_case)

    # Flatten pending_map to list
    pending = []
    for field, case_ids in pending_map.items():
        pending.append({
            "field": field,
            "in_case_ids": case_ids,
            "description": f"Unresolved placeholder {{{{{field}}}}} in test cases {case_ids}",
        })

    return resolved, pending


def _resolve_string(value: str, resolved_data: dict) -> tuple[str, list]:
    """Replace placeholders in a string. Returns (resolved, list_of_unresolved_fields)."""
    unresolved = []

    def replacer(m: re.Match) -> str:
        field = m.group(1)
        if field in resolved_data:
            return resolved_data[field]
        unresolved.append(field)
        return m.group(0)  # keep original token

    result = _PLACEHOLDER_RE.sub(replacer, value)
    return result, unresolved


def _ts() -> str:
    """Compact timestamp for run_id generation."""
    import datetime
    return datetime.datetime.now().strftime("%Y%m%d-%H%M%S")


def _err(code: str, message: str) -> dict:
    return {"ok": False, "error": code, "message": message}


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    args = _parse_args()
    # Default: show everything (DEBUG). --background suppresses to WARNING.
    if args.background:
        logging.basicConfig(level=logging.WARNING, stream=sys.stderr,
                            format="%(levelname)s %(name)s: %(message)s")
    else:
        logging.basicConfig(level=logging.DEBUG, stream=sys.stderr,
                            format="%(levelname)s %(name)s: %(message)s")

    result = run(
        intent_file=Path(args.intent_file),
        data_file=Path(args.data_file) if args.data_file else None,
        verbose=not args.background,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if not result.get("ok"):
        sys.exit(1)
    if result.get("pending_data"):
        sys.exit(2)
    sys.exit(0)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Validate and normalize intent_spec.json for the QA UAT pipeline."
    )
    p.add_argument("--intent-file", required=True,
                   help="Path to intent_spec.json produced by the orchestrator agent.")
    p.add_argument("--data-file", default=None,
                   help="Optional resolved_data.json to merge into intent_spec.resolved_data.")
    p.add_argument("--background", action="store_true",
                   help="Background mode: suppress verbose logging (only warnings/errors).")
    return p.parse_args()


if __name__ == "__main__":
    main()
