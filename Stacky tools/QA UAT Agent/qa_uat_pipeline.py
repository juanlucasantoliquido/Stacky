"""
qa_uat_pipeline.py — Orchestrator for the full QA UAT pipeline.

Connects all 8 tools in sequence:
  B1 uat_ticket_reader → B3 ui_map_builder (per screen) → B4 uat_scenario_compiler
  → B5 playwright_test_generator → B6 uat_test_runner
  → B7 uat_dossier_builder → B8 ado_evidence_publisher

Fase 9 — Multi-round replanning:
  After runner stage, if failures are detected and --replan is set, the pipeline
  calls replan_engine.analyze() to compute a fix, patches intent_spec, and
  re-runs from the generator stage.  Up to MAX_REPLAN_ROUNDS=3 attempts.
  After 3 rounds (or when replan_engine returns "escalate"), the pipeline
  continues to the dossier/publisher stages as normal with full context.

CLI:
    python qa_uat_pipeline.py --ticket 70 [--mode dry-run|publish] [--headed] [--verbose]
    python qa_uat_pipeline.py --ticket 70 --skip-to runner [--verbose]
    python qa_uat_pipeline.py --intent-file spec.json --replan [--verbose]

Options:
    --ticket         ADO work item ID (required unless --intent-file)
    --mode           dry-run (default) or publish — controls ado_evidence_publisher
    --headed         Run Playwright in headed mode (shows browser)
    --timeout-ms     Playwright per-test timeout in ms (default: 90000).
                     Cubre login ASP.NET + 2-3 navegaciones + steps + screenshots.
    --skip-to        Skip all stages before: reader|ui_map|compiler|generator|runner|dossier|publisher
    --ado-path       Path to ado.py (default: ../ADO Manager/ado.py)
    --replan         Enable multi-round replanning (Fase 9). Up to 3 retry rounds.
    --verbose        Debug logging to stderr

Output: JSON to stdout with pipeline summary.
Errors: {"ok": false, "error": "<code>", "stage": "<stage_name>", "message": "..."} exit code 1.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.qa_uat.pipeline")

_TOOL_VERSION = "1.1.0"  # Fase 9 — multi-round replanning
_TOOL_ROOT = Path(__file__).parent  # NOT resolved — avoid symlink/junction issues on Windows
_MAX_REPLAN_ROUNDS: int = 3  # Fase 9 — maximum retry rounds before escalation


def _resolve_sibling_tool(tool_dir_name: str, entrypoint: str) -> Path:
    """
    Resolve the path to a sibling tool inside the same `Stacky tools/` parent.

    `qa_uat_pipeline.py` lives in `Stacky tools/QA UAT Agent/`, so its sibling
    `ADO Manager/ado.py` is at `_TOOL_ROOT.parent / "ADO Manager" / "ado.py"`.

    This helper walks upward from this file looking for the `Stacky tools`
    container directory, then descends into the requested sibling. This is
    robust against moves of the `QA UAT Agent` folder within `Stacky tools/`.
    Falls back to a 1-up sibling lookup if the marker is not found.
    """
    here = Path(__file__).resolve()
    for ancestor in here.parents:
        if ancestor.name == "Stacky tools":
            candidate = ancestor / tool_dir_name / entrypoint
            if candidate.is_file():
                return candidate
            return candidate  # return even if missing, so error is informative
    # Fallback: assume sibling-of-QA-UAT-Agent layout
    return Path(__file__).parent.parent / tool_dir_name / entrypoint


_DEFAULT_ADO_PATH = _resolve_sibling_tool("ADO Manager", "ado.py")

_STAGE_NAMES = [
    "reader",
    "ui_map",
    "compiler",
    "preconditions",
    "generator",
    "runner",
    "annotator",     # Fase 2 — non-fatal, draws bbox boxes on screenshots
    "evaluator",
    "failure_analyzer",
    "dossier",
    "publisher",
]


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    args = _parse_args()

    # Default: show EVERYTHING (DEBUG). --background suppresses to WARNING only.
    if getattr(args, "background", False):
        logging.basicConfig(level=logging.WARNING, stream=sys.stderr,
                            format="%(levelname)s %(name)s: %(message)s")
        verbose = False
    else:
        logging.basicConfig(level=logging.DEBUG, stream=sys.stderr,
                            format="%(levelname)s %(name)s: %(message)s")
        verbose = True

    # Validate mutually exclusive --ticket / --intent-file
    if args.ticket is None and not getattr(args, "intent_file", None):
        sys.stderr.write(
            "error: one of --ticket or --intent-file is required\n"
        )
        sys.exit(1)
    if args.ticket is not None and getattr(args, "intent_file", None):
        sys.stderr.write(
            "error: --ticket and --intent-file are mutually exclusive\n"
        )
        sys.exit(1)
    if getattr(args, "resume", False) and not getattr(args, "data_file", None):
        sys.stderr.write("error: --resume requires --data-file\n")
        sys.exit(1)

    if args.ticket is not None:
        # ── ADO ticket mode (original) ────────────────────────────────────────
        result = run(
            ticket_id=args.ticket,
            mode=args.mode,
            headed=args.headed,
            timeout_ms=args.timeout_ms,
            skip_to=args.skip_to,
            ado_path=Path(args.ado_path) if args.ado_path else None,
            detect_screen_errors=getattr(args, "detect_screen_errors", False),
            detect_screen_errors_vision=getattr(args, "detect_screen_errors_vision", False),
            verbose=verbose,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        sys.exit(0 if result.get("ok") else 1)
    else:
        # ── Free-form mode (Fase 1) ───────────────────────────────────────────
        result = _run_freeform(
            intent_file=Path(args.intent_file),
            data_file=Path(args.data_file) if args.data_file else None,
            resume=getattr(args, "resume", False),
            mode=args.mode,
            headed=args.headed,
            timeout_ms=args.timeout_ms,
            skip_to=args.skip_to,
            ado_path=Path(args.ado_path) if args.ado_path else None,
            auto_resolve=getattr(args, "auto_resolve", False),
            detect_screen_errors=getattr(args, "detect_screen_errors", False),
            detect_screen_errors_vision=getattr(args, "detect_screen_errors_vision", False),
            verbose=verbose,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if not result.get("ok"):
            sys.exit(1)
        if result.get("pending_data"):
            sys.exit(2)   # PENDING_DATA — orchestrator must resolve + --resume
        sys.exit(0)


# ── Core logic ────────────────────────────────────────────────────────────────

def run(
    ticket_id: int,
    mode: str = "dry-run",
    headed: bool = False,
    timeout_ms: int = 90_000,
    skip_to: Optional[str] = None,
    ado_path: Optional[Path] = None,
    detect_screen_errors: bool = False,
    detect_screen_errors_vision: bool = False,
    replan: bool = False,
    verbose: bool = True,
) -> dict:
    """
    Orchestrate the full UAT pipeline for a given ticket.

    Returns a pipeline summary dict:
    {
        "ok": true,
        "ticket_id": 70,
        "verdict": "PASS|FAIL|BLOCKED|MIXED",
        "stages": {
            "reader":    {"ok": true, "skipped": false, ...},
            "ui_map":    {"ok": true, "skipped": false, "screens": [...]},
            "compiler":  {"ok": true, "skipped": false, "scenario_count": 6},
            "generator": {"ok": true, "skipped": false, "generated": 5, "blocked": 1},
            "runner":    {"ok": true, "skipped": false, "pass": 4, "fail": 1, "blocked": 1},
            "dossier":   {"ok": true, "skipped": false, "paths": {...}},
            "publisher": {"ok": true, "skipped": false, "publish_state": "dry-run"},
        },
        "elapsed_s": 12.3,
    }
    """
    started = time.time()

    if mode not in ("dry-run", "publish"):
        return _fail("reader", "invalid_mode", f"mode must be 'dry-run' or 'publish', got: {mode!r}")

    ado_path = ado_path or _DEFAULT_ADO_PATH
    evidence_dir = _TOOL_ROOT / "evidence" / str(ticket_id)
    skip_stages: set = set()
    if skip_to and skip_to in _STAGE_NAMES:
        skip_stages = set(_STAGE_NAMES[: _STAGE_NAMES.index(skip_to)])
        logger.info("Skipping stages: %s", skip_stages)

    stages: dict = {}

    # ── Stage 1: reader ──────────────────────────────────────────────────────
    stage = "reader"
    if stage in skip_stages:
        stages[stage] = {"ok": True, "skipped": True}
        # Load cached ticket for downstream stages
        cache_file = evidence_dir / "ticket.json"
        if not cache_file.is_file():
            return _fail(stage, "cache_miss",
                         f"--skip-to {skip_to} requires cached ticket at {cache_file}")
        ticket_result = json.loads(cache_file.read_text(encoding="utf-8"))
    else:
        from uat_ticket_reader import run as reader_run
        _log_stage(stage)
        ticket_result = reader_run(
            ticket_id=ticket_id,
            use_cache=False,
            ado_path=ado_path,
            verbose=verbose,
        )
        stages[stage] = _summarise_reader(ticket_result)
        if not ticket_result.get("ok"):
            return _build_output(ticket_id, stages, ticket_result, started)

    # Delegate stages 2-11 to shared implementation (also used by _run_freeform)
    pipeline_result = _run_pipeline_stages(
        ticket_result=ticket_result,
        evidence_dir=evidence_dir,
        ticket_id=ticket_id,
        mode=mode,
        headed=headed,
        timeout_ms=timeout_ms,
        skip_to=skip_to,
        skip_stages=skip_stages,
        ado_path=ado_path,
        detect_screen_errors=detect_screen_errors,
        detect_screen_errors_vision=detect_screen_errors_vision,
        replan=replan,
        verbose=verbose,
        started=started,
    )
    if isinstance(pipeline_result.get("stages"), dict):
        pipeline_result["stages"] = {**stages, **pipeline_result["stages"]}
    return pipeline_result



# ── Dossier + Publisher sub-flow ─────────────────────────────────────────────

def _run_dossier_and_publisher(
    ticket_id,   # int (ADO) or str run_id (freeform)
    stages: dict,
    evidence_dir: Path,
    runner_result: dict,
    ticket_result: dict,
    mode: str,
    ado_path: Path,
    verbose: bool,
    started: float,
) -> dict:
    """Stages 6 (dossier) and 7 (publisher) — shared by main flow and blocked shortcut."""
    from uat_dossier_builder import run as dossier_run
    from ado_evidence_publisher import run as publisher_run

    # ── Stage 6: dossier ─────────────────────────────────────────────────────
    _log_stage("dossier")
    runner_output_path = evidence_dir / "runner_output.json"
    ticket_path = evidence_dir / "ticket.json"

    # Pass evaluations.json explicitly so the dossier consolidates the semantic
    # evaluator status with the raw runner status. Auto-detect would also work
    # since it lives next to runner_output.json, but being explicit keeps the
    # contract clear and surfaces missing evaluator output during debugging.
    evaluations_path = evidence_dir / "evaluations.json"
    dossier_result = dossier_run(
        runner_output_path=runner_output_path,
        ticket_path=ticket_path,
        out_dir=evidence_dir,
        verbose=verbose,
        evaluations_path=evaluations_path if evaluations_path.is_file() else None,
    )
    stages["dossier"] = _summarise_dossier(dossier_result)
    if not dossier_result.get("ok"):
        return _build_output(ticket_id, stages, dossier_result, started)

    # ── Stage 7: publisher ───────────────────────────────────────────────────
    _log_stage("publisher")
    dossier_path = evidence_dir / "dossier.json"
    publisher_result = publisher_run(
        ticket_id=ticket_id,
        dossier_path=dossier_path,
        mode=mode,
        ado_path=ado_path,
        verbose=verbose,
    )
    stages["publisher"] = _summarise_publisher(publisher_result, mode)
    if not publisher_result.get("ok"):
        return _build_output(ticket_id, stages, publisher_result, started)

    verdict = dossier_result.get("verdict", "UNKNOWN")
    return {
        "ok": True,
        "ticket_id": ticket_id,
        "verdict": verdict,
        "stages": stages,
        "elapsed_s": round(time.time() - started, 2),
    }


# ── Free-form entry point (Fase 1) ───────────────────────────────────────────

def _run_freeform(
    intent_file: Path,
    data_file: Optional[Path] = None,
    resume: bool = False,
    mode: str = "dry-run",
    headed: bool = False,
    timeout_ms: int = 90_000,
    skip_to: Optional[str] = None,
    ado_path: Optional[Path] = None,
    auto_resolve: bool = False,
    detect_screen_errors: bool = False,
    detect_screen_errors_vision: bool = False,
    replan: bool = False,
    verbose: bool = True,
) -> dict:
    """Free-form pipeline entry point (Fase 1/3).

    Replaces Stage 1 (reader) with intent_parser + synthetic_ticket_builder.
    When unresolved placeholders exist:
      - If auto_resolve=True (Fase 3): tries to resolve via data_resolver first.
        If all resolve successfully, continues without exit code 2.
        If some remain unresolved, emits data_request.json for only those fields.
      - If auto_resolve=False (default): emits data_request.json and returns
        {"ok": True, "pending_data": [...], ...} — caller should exit with code 2.
    On resume (--resume --data-file), merges resolved_data and continues.

    Evidence dir: evidence/<run_id>/  (run_id from intent_spec)
    Publisher: always dry-run (no real ADO ticket in free-form mode).
    """
    from intent_parser import run as parser_run
    from synthetic_ticket_builder import run as builder_run

    started = time.time()

    if mode not in ("dry-run", "publish"):
        return _fail("intent_parser", "invalid_mode",
                     f"mode must be 'dry-run' or 'publish', got: {mode!r}")

    # ── Step 1: parse + validate intent_spec ────────────────────────────────
    _log_stage("intent_parser")
    parser_result = parser_run(
        intent_file=intent_file,
        data_file=data_file,
        verbose=verbose,
    )
    if not parser_result.get("ok"):
        return {
            "ok": False,
            "stage": "intent_parser",
            "error": parser_result.get("error"),
            "message": parser_result.get("message"),
            "elapsed_s": round(time.time() - started, 2),
        }

    intent_spec = parser_result["intent_spec"]
    run_id: str = parser_result["run_id"]
    pending_data: list = parser_result.get("pending_data") or []

    evidence_dir = _TOOL_ROOT / "evidence" / run_id
    evidence_dir.mkdir(parents=True, exist_ok=True)

    # Save current intent_spec state (with any newly merged resolved_data)
    _persist_json(evidence_dir / "intent_spec.json", intent_spec)

    stages: dict = {}
    stages["intent_parser"] = {
        "ok": True, "skipped": False,
        "run_id": run_id,
        "test_cases": len(intent_spec.get("test_cases") or []),
        "resolved_data_keys": list((intent_spec.get("resolved_data") or {}).keys()),
        "pending": len(pending_data),
    }

    # ── Step 2: handle pending_data (auto-resolve or emit data_request) ─────
    if pending_data:
        # [Fase 3] --auto-resolve: try to execute hint_queries automatically
        if auto_resolve:
            pending_data = _auto_resolve_pending(
                pending_data=pending_data,
                intent_spec=intent_spec,
                evidence_dir=evidence_dir,
                run_id=run_id,
                verbose=verbose,
            )
            # Update stages summary after auto-resolve attempt
            stages["intent_parser"]["pending"] = len(pending_data)
            stages["intent_parser"]["auto_resolved"] = True
            # Re-persist intent_spec with newly merged resolved_data
            _persist_json(evidence_dir / "intent_spec.json", intent_spec)

        if pending_data:
            data_req = _build_data_request(
                run_id=run_id,
                pending_data=pending_data,
                intent_spec=intent_spec,
                evidence_dir=evidence_dir,
            )
            _persist_json(evidence_dir / "data_request.json", data_req)
            logger.warning(
                "PENDING_DATA: %d fields unresolved. data_request.json written to %s",
                len(pending_data), evidence_dir / "data_request.json",
            )
            return {
                "ok": True,
                "run_id": run_id,
                "pending_data": pending_data,
                "data_request": data_req,
                "data_request_path": str(evidence_dir / "data_request.json"),
                "resume_command": data_req.get("resume_command", ""),
                "stages": stages,
                "elapsed_s": round(time.time() - started, 2),
            }
        # All fields auto-resolved — fall through to synthetic_ticket_builder
        logger.info("data_resolver: all pending fields auto-resolved — continuing pipeline")

    # ── Step 3: build synthetic ticket.json ──────────────────────────────────
    _log_stage("synthetic_ticket_builder")
    ticket_result = builder_run(intent_spec=intent_spec, verbose=verbose)
    if not ticket_result.get("ok"):
        return {
            "ok": False,
            "stage": "synthetic_ticket_builder",
            "error": ticket_result.get("error"),
            "message": ticket_result.get("message"),
            "stages": stages,
            "elapsed_s": round(time.time() - started, 2),
        }

    stages["synthetic_ticket_builder"] = {
        "ok": True, "skipped": False,
        "plan_item_count": len(ticket_result.get("plan_pruebas") or []),
    }

    # Persist ticket.json so downstream stages can cache-load it
    _persist_json(evidence_dir / "ticket.json", ticket_result)

    ado_path = ado_path or _DEFAULT_ADO_PATH

    # ── Steps 4-11: run the shared pipeline stages ───────────────────────────
    # We reuse all downstream stages from run() by delegating to the shared
    # stage runner.  Evidence dir is freeform-<run_id>/ instead of <ticket_id>/.
    # Publisher is forced to dry-run (no real ADO ticket).
    skip_stages: set = set()
    if skip_to and skip_to in _STAGE_NAMES:
        skip_stages = set(_STAGE_NAMES[: _STAGE_NAMES.index(skip_to)])

    pipeline_result = _run_pipeline_stages(
        ticket_result=ticket_result,
        evidence_dir=evidence_dir,
        ticket_id=run_id,         # used only for logging / output keys
        mode="dry-run",           # free-form runs never write to ADO
        headed=headed,
        timeout_ms=timeout_ms,
        skip_to=skip_to,
        skip_stages=skip_stages,
        ado_path=ado_path,
        detect_screen_errors=detect_screen_errors,
        detect_screen_errors_vision=detect_screen_errors_vision,
        replan=replan,
        verbose=verbose,
        started=started,
    )
    # Merge freeform-specific stages into the result
    if isinstance(pipeline_result.get("stages"), dict):
        pipeline_result["stages"] = {**stages, **pipeline_result["stages"]}
    pipeline_result["run_id"] = run_id
    pipeline_result["source"] = "freeform"
    return pipeline_result


def _auto_resolve_pending(
    pending_data: list,
    intent_spec: dict,
    evidence_dir: Path,
    run_id: str,
    verbose: bool = True,
) -> list:
    """[Fase 3] Attempt to auto-resolve pending_data fields via data_resolver.

    Builds a minimal data_request dict (in memory, not written yet), calls
    data_resolver.resolve_fields(), injects resolved values into intent_spec
    resolved_data in-place, and returns only the fields that could NOT be resolved.

    If data_resolver is not available, returns pending_data unchanged.
    """
    try:
        from data_resolver import resolve_fields
    except ImportError:
        logger.debug(
            "_auto_resolve_pending: data_resolver not available — skipping auto-resolve"
        )
        return pending_data

    # Build the requests list (same format as data_request.requests[])
    # using the existing hint_query infrastructure
    requests_for_resolver = []
    for item in pending_data:
        field = item.get("field", "UNKNOWN")
        hint_query, hint_tables = _hint_query_for_field(field, intent_spec)
        requests_for_resolver.append({
            "field": field,
            "description": item.get("description", f"Value needed for {field}"),
            "hint_query": hint_query,
            "hint_tables": hint_tables,
            "reason": item.get("description", ""),
            "in_case_ids": item.get("in_case_ids") or [],
        })

    logger.info(
        "_auto_resolve_pending: attempting to auto-resolve %d fields via data_resolver",
        len(requests_for_resolver),
    )

    result = resolve_fields(requests=requests_for_resolver, verbose=verbose)

    if result.resolved:
        # Inject resolved values into intent_spec (in-place mutation is intentional)
        resolved_data = intent_spec.setdefault("resolved_data", {})
        resolved_data.update(result.resolved)
        logger.info(
            "_auto_resolve_pending: resolved %d/%d fields: %s",
            len(result.resolved), len(pending_data), list(result.resolved.keys()),
        )
        # Persist resolved_data.json next to intent_spec
        resolved_path = evidence_dir / "resolved_data.json"
        existing: dict = {}
        if resolved_path.is_file():
            try:
                import json as _json
                existing = _json.loads(resolved_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        merged = {**existing, **result.resolved}
        _persist_json(resolved_path, merged)

    if result.blocked:
        logger.warning(
            "_auto_resolve_pending: %d fields blocked by SQL guard: %s",
            len(result.blocked), [b["field"] for b in result.blocked],
        )

    # Return only fields that still need manual resolution
    remaining_fields = {f["field"] for f in result.unresolved} | {b["field"] for b in result.blocked}
    still_pending = [item for item in pending_data if item.get("field") in remaining_fields]
    return still_pending


def _build_data_request(
    run_id: str,
    pending_data: list,
    intent_spec: dict,
    evidence_dir: Path,
) -> dict:
    """Build data_request.json contents for fields that need resolution."""
    requests = []
    for item in pending_data:
        field = item.get("field", "UNKNOWN")
        case_ids = item.get("in_case_ids", [])
        # Generate a sensible hint_query using whitelisted tables
        hint_query, hint_tables = _hint_query_for_field(field, intent_spec)
        requests.append({
            "field": field,
            "description": item.get("description", f"Value needed for {field}"),
            "hint_query": hint_query,
            "hint_tables": hint_tables,
            "reason": f"Required by test cases: {', '.join(case_ids)}",
            "in_case_ids": case_ids,
        })

    tool_root_rel = str(evidence_dir.relative_to(_TOOL_ROOT)).replace("\\", "/")
    resume_cmd = (
        f"python qa_uat_pipeline.py "
        f"--intent-file {tool_root_rel}/intent_spec.json "
        f"--resume --data-file {tool_root_rel}/resolved_data.json"
    )
    return {
        "schema_version": "1.0",
        "run_id": run_id,
        "stage": "intent_parser",
        "requests": requests,
        "resume_command": resume_cmd,
        "resolved_data_path": f"{tool_root_rel}/resolved_data.json",
    }


def _hint_query_for_field(field: str, intent_spec: dict) -> tuple:
    """
    Return a (hint_query_string, hint_tables_list) for common placeholder field names.
    [Fase 3] Delegates to data_resolver.FIELD_HINTS for the authoritative mapping.
    Falls back to a generic comment when field is unknown.
    """
    try:
        from data_resolver import FIELD_HINTS
        if field in FIELD_HINTS:
            return FIELD_HINTS[field]
    except ImportError:
        pass  # data_resolver not available (old installation) — use inline fallback

    # Inline fallback for the most common fields (keeps pipeline self-contained)
    _FALLBACK: dict = {
        "CLIENTE_ID": (
            "SELECT TOP 1 RIDIOMA FROM RIDIOMA WHERE ESTADO = 'A' ORDER BY NEWID()",
            ["RIDIOMA"],
        ),
        "LOTE_ID": (
            "SELECT TOP 1 RAGEN FROM RAGEN WHERE ESTAGEN = 'A' ORDER BY NEWID()",
            ["RAGEN"],
        ),
        "AGENTE_ID": (
            "SELECT TOP 1 RAGTIP FROM RAGTIP ORDER BY NEWID()",
            ["RAGTIP"],
        ),
        "MOTIVO_ID": (
            "SELECT TOP 1 RAGMOT FROM RAGMOT ORDER BY NEWID()",
            ["RAGMOT"],
        ),
        "CALIDAD_ID": (
            "SELECT TOP 1 RAGCAL FROM RAGCAL ORDER BY NEWID()",
            ["RAGCAL"],
        ),
        "SISTEMA_ID": (
            "SELECT TOP 1 RASIST FROM RASIST WHERE ACTIVO = 1 ORDER BY NEWID()",
            ["RASIST"],
        ),
    }
    if field in _FALLBACK:
        return _FALLBACK[field]
    return (
        f"-- Resolve {field}: provide the correct value for this placeholder.\n"
        f"-- Example: SELECT TOP 1 RIDIOMA FROM RIDIOMA WHERE ESTADO = 'A'",
        ["RIDIOMA"],
    )


def _run_pipeline_stages(
    ticket_result: dict,
    evidence_dir: Path,
    ticket_id,   # int for ADO mode, str run_id for freeform
    mode: str,
    headed: bool,
    timeout_ms: int,
    skip_to: Optional[str],
    skip_stages: set,
    ado_path: Path,
    verbose: bool,
    started: float,
    detect_screen_errors: bool = False,
    detect_screen_errors_vision: bool = False,
    replan: bool = False,
) -> dict:
    """
    Run stages 2-11 (ui_map through publisher) given an already-loaded ticket_result.
    Used by both run() (ADO mode) and _run_freeform() (free-form mode).
    """
    stages: dict = {}
    ui_maps_dir = _TOOL_ROOT / "cache" / "ui_maps"

    # ── Stage 2: ui_map ──────────────────────────────────────────────────────
    stage = "ui_map"
    screens = _extract_screens(ticket_result)
    if stage in skip_stages:
        stages[stage] = {"ok": True, "skipped": True, "screens": screens}
    else:
        from ui_map_builder import run as ui_map_run
        _log_stage(stage)
        for screen in screens:
            logger.debug("Building UI map for screen: %s", screen)
            ui_result = ui_map_run(screen=screen, rebuild=False, verbose=verbose)
            if not ui_result.get("ok"):
                stages[stage] = {
                    "ok": False, "skipped": False, "screen": screen,
                    "error": ui_result.get("error"), "message": ui_result.get("message"),
                }
                return _build_output(ticket_id, stages, ui_result, started)
        stages[stage] = {"ok": True, "skipped": False, "screens": screens}

    # ── Stage 3: compiler ────────────────────────────────────────────────────
    stage = "compiler"
    if stage in skip_stages:
        stages[stage] = {"ok": True, "skipped": True}
        scenarios_file = evidence_dir / "scenarios.json"
        if not scenarios_file.is_file():
            return _fail(stage, "cache_miss",
                         f"--skip-to {skip_to} requires cached scenarios at {scenarios_file}")
        compiler_result = json.loads(scenarios_file.read_text(encoding="utf-8"))
    else:
        from uat_scenario_compiler import run as compiler_run
        _log_stage(stage)
        ui_aliases: list = []
        ui_elements: list = []
        for screen in screens:
            ui_map_file = ui_maps_dir / f"{screen}.json"
            if ui_map_file.is_file():
                try:
                    ui_data = json.loads(ui_map_file.read_text(encoding="utf-8"))
                    for el in ui_data.get("elements", []):
                        alias = el.get("alias_semantic")
                        if alias:
                            ui_aliases.append(alias)
                            ui_elements.append(el)
                except Exception:
                    pass
        compiler_result = compiler_run(
            ticket_json=ticket_result,
            scope_screen=screens[0] if len(screens) == 1 else None,
            ui_aliases=ui_aliases or None,
            ui_elements=ui_elements or None,
            verbose=verbose,
        )
        stages[stage] = _summarise_compiler(compiler_result)
        if not compiler_result.get("ok"):
            return _build_output(ticket_id, stages, compiler_result, started)
        # Write scenarios.json now so that preconditions (next stage) can read it
        _persist_json(evidence_dir / "scenarios.json", compiler_result)

    # ── Stage 3b: preconditions ──────────────────────────────────────────────
    stage = "preconditions"
    if stage in skip_stages:
        stages[stage] = {"ok": True, "skipped": True}
    else:
        from uat_precondition_checker import run as preconditions_run
        _log_stage(stage)
        prec_result = preconditions_run(
            scenarios_path=evidence_dir / "scenarios.json",
            verbose=verbose,
        )
        if prec_result.get("ok"):
            stages[stage] = _summarise_preconditions(prec_result)
        else:
            if prec_result.get("error") in ("db_credentials_missing", "db_unreachable"):
                logger.warning("Precondition check skipped (%s): %s",
                               prec_result.get("error"), prec_result.get("message"))
                stages[stage] = {"ok": True, "skipped": True,
                                 "reason": prec_result.get("error")}
            else:
                stages[stage] = {"ok": False, "skipped": False,
                                 "error": prec_result.get("error"),
                                 "message": prec_result.get("message")}
                return _build_output(ticket_id, stages, prec_result, started)

    # ── Stage 4: generator ───────────────────────────────────────────────────
    stage = "generator"
    tests_dir = evidence_dir / "tests"
    if stage in skip_stages:
        stages[stage] = {"ok": True, "skipped": True}
        _persist_json(evidence_dir / "scenarios.json", compiler_result)
    else:
        from playwright_test_generator import run as generator_run
        _log_stage(stage)
        _persist_json(evidence_dir / "scenarios.json", compiler_result)
        generator_result = generator_run(
            scenarios_path=evidence_dir / "scenarios.json",
            ui_maps_dir=ui_maps_dir,
            out_dir=tests_dir,
            template_path=None,
            detect_screen_errors=detect_screen_errors,
            detect_screen_errors_vision=detect_screen_errors_vision,
            verbose=verbose,
        )
        stages[stage] = _summarise_generator(generator_result)
        if not generator_result.get("ok"):
            return _build_output(ticket_id, stages, generator_result, started)
        gen_specs = generator_result.get("results") or generator_result.get("specs", [])
        all_blocked = gen_specs and all(s.get("status") == "blocked" for s in gen_specs)
        if all_blocked:
            logger.warning("All scenarios blocked (missing selectors). Skipping runner.")
            stages["runner"] = {"ok": True, "skipped": True, "reason": "all_scenarios_blocked"}
            stages["evaluator"] = {"ok": True, "skipped": True, "reason": "all_scenarios_blocked"}
            stages["failure_analyzer"] = {"ok": True, "skipped": True,
                                          "reason": "all_scenarios_blocked"}
            runner_result = _synthetic_runner_output(ticket_id, gen_specs)
            _persist_json(evidence_dir / "runner_output.json", runner_result)
            return _run_dossier_and_publisher(
                ticket_id=ticket_id, stages=stages, evidence_dir=evidence_dir,
                runner_result=runner_result, ticket_result=ticket_result,
                mode=mode, ado_path=ado_path, verbose=verbose, started=started,
            )

    # ── Stage 5: runner ──────────────────────────────────────────────────────
    stage = "runner"
    if stage in skip_stages:
        stages[stage] = {"ok": True, "skipped": True}
        runner_file = evidence_dir / "runner_output.json"
        if not runner_file.is_file():
            return _fail(stage, "cache_miss",
                         f"--skip-to {skip_to} requires cached runner_output at {runner_file}")
        runner_result = json.loads(runner_file.read_text(encoding="utf-8"))
    else:
        from uat_test_runner import run as runner_run
        _log_stage(stage)
        runner_result = runner_run(
            tests_dir=tests_dir,
            evidence_out=evidence_dir,
            headed=headed,
            timeout_ms=timeout_ms,
            verbose=verbose,
        )
        stages[stage] = _summarise_runner(runner_result)
        if not runner_result.get("ok"):
            return _build_output(ticket_id, stages, runner_result, started)
        _persist_json(evidence_dir / "runner_output.json", runner_result)

        # ── Fase 9: Multi-round replanning ───────────────────────────────────
        # Trigger only when --replan is set AND there are failures/blocks.
        # Runs up to _MAX_REPLAN_ROUNDS rounds in-place, patching scenarios.json
        # and re-running generator + runner for each actionable fix.
        # After exhausting rounds (or getting "escalate") it falls through to
        # the normal evaluator → failure_analyzer → dossier pipeline.
        if replan:
            runner_result, stages = _run_replan_loop(
                runner_result=runner_result,
                stages=stages,
                evidence_dir=evidence_dir,
                ticket_result=ticket_result,
                tests_dir=tests_dir,
                ui_maps_dir=ui_maps_dir,
                headed=headed,
                timeout_ms=timeout_ms,
                detect_screen_errors=detect_screen_errors,
                detect_screen_errors_vision=detect_screen_errors_vision,
                verbose=verbose,
            )
            # Re-persist the final runner_output after all replan rounds
            _persist_json(evidence_dir / "runner_output.json", runner_result)

    # ── Stage 5b: annotator (non-fatal) ─────────────────────────────────────
    stage = "annotator"
    if stage not in skip_stages:
        try:
            from screenshot_annotator import annotate_evidence_dir
            _log_stage(stage)
            annotator_result = annotate_evidence_dir(evidence_dir=evidence_dir, verbose=verbose)
            stages[stage] = {
                "ok": True, "skipped": False,
                "annotated": annotator_result.get("annotated", 0),
                "errors": annotator_result.get("errors", []),
            }
        except ImportError:
            stages[stage] = {"ok": True, "skipped": True,
                             "reason": "screenshot_annotator_not_found"}
        except Exception as exc:
            logger.warning("Annotator stage failed (non-fatal): %s", exc)
            stages[stage] = {"ok": True, "skipped": True, "reason": f"annotator_error: {exc}"}
    else:
        stages[stage] = {"ok": True, "skipped": True}

    # ── Stage 6: evaluator ───────────────────────────────────────────────────
    stage = "evaluator"
    if stage in skip_stages:
        stages[stage] = {"ok": True, "skipped": True}
        eval_file = evidence_dir / "evaluations.json"
        evaluations_result = (
            json.loads(eval_file.read_text(encoding="utf-8")) if eval_file.is_file() else None
        )
    else:
        from uat_assertion_evaluator import run as evaluator_run
        _log_stage(stage)
        evaluations_result = evaluator_run(
            scenarios_path=evidence_dir / "scenarios.json",
            runner_output_path=evidence_dir / "runner_output.json",
            verbose=verbose,
        )
        stages[stage] = _summarise_evaluator(evaluations_result)
        if not evaluations_result.get("ok"):
            return _build_output(ticket_id, stages, evaluations_result, started)

    # ── Stage 7: failure_analyzer ────────────────────────────────────────────
    stage = "failure_analyzer"
    has_failures = bool(
        evaluations_result
        and any(e.get("status") == "fail"
                for e in (evaluations_result.get("evaluations") or []))
    )
    if stage in skip_stages or not has_failures:
        stages[stage] = {"ok": True, "skipped": True}
    else:
        from uat_failure_analyzer import run as analyzer_run
        _log_stage(stage)
        analyzer_result = analyzer_run(
            evaluations_path=evidence_dir / "evaluations.json",
            runner_output_path=evidence_dir / "runner_output.json",
            verbose=verbose,
        )
        stages[stage] = _summarise_failure_analyzer(analyzer_result)
        if not analyzer_result.get("ok"):
            return _build_output(ticket_id, stages, analyzer_result, started)

    return _run_dossier_and_publisher(
        ticket_id=ticket_id, stages=stages, evidence_dir=evidence_dir,
        runner_result=runner_result, ticket_result=ticket_result,
        mode=mode, ado_path=ado_path, verbose=verbose, started=started,
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _run_replan_loop(
    runner_result: dict,
    stages: dict,
    evidence_dir: Path,
    ticket_result: dict,
    tests_dir: Path,
    ui_maps_dir: Path,
    headed: bool,
    timeout_ms: int,
    detect_screen_errors: bool,
    detect_screen_errors_vision: bool,
    verbose: bool,
) -> tuple[dict, dict]:
    """Fase 9 — Multi-round replanning loop.

    Called right after the runner stage when --replan is set.
    Attempts up to _MAX_REPLAN_ROUNDS corrective iterations.

    Each round:
      1. Load current intent_spec from evidence_dir/intent_spec.json
         (may not exist in ADO-ticket mode — degrade gracefully)
      2. Call replan_engine.analyze() to classify failures and compute patch
      3. If action=="no_action": break (all tests pass now)
      4. If action=="escalate":  break (no automated fix available)
      5. If action=="retry":
         a. Persist patched intent_spec → evidence_dir/intent_spec.json
         b. Re-run playwright_test_generator with the updated spec
         c. Re-run uat_test_runner
         d. Update stages["runner"] with latest counts

    Returns (final_runner_result, updated_stages).
    Never raises — any error degrades gracefully (log + return current state).
    """
    try:
        from replan_engine import analyze as replan_analyze, MAX_REPLAN_ROUNDS
    except ImportError:
        logger.warning("replan_engine not available — skipping replan loop")
        return runner_result, stages

    try:
        from playwright_test_generator import run as generator_run
        from uat_test_runner import run as runner_run
    except ImportError as exc:
        logger.warning("replan_loop: missing dependency %s — skipping", exc)
        return runner_result, stages

    intent_spec_path = evidence_dir / "intent_spec.json"
    current_runner = runner_result
    current_stages = stages.copy()

    for round_number in range(1, MAX_REPLAN_ROUNDS + 1):
        # Check if there are still failures to address
        has_failures = _runner_has_failures(current_runner)
        if not has_failures:
            logger.info("replan_loop: round %d — no failures, stopping replan", round_number)
            break

        logger.info("replan_loop: starting round %d of %d", round_number, MAX_REPLAN_ROUNDS)

        # Load current intent_spec (may not exist in ADO-ticket mode)
        if not intent_spec_path.is_file():
            logger.warning(
                "replan_loop: intent_spec.json not found at %s — cannot patch; escalating",
                intent_spec_path,
            )
            current_stages[f"replan_round_{round_number}"] = {
                "ok": True, "skipped": True,
                "reason": "intent_spec_not_found",
            }
            break

        try:
            intent_spec = json.loads(intent_spec_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("replan_loop: cannot parse intent_spec.json: %s — escalating", exc)
            break

        # Load evaluations if available
        evaluations = None
        eval_path = evidence_dir / "evaluations.json"
        if eval_path.is_file():
            try:
                evaluations = json.loads(eval_path.read_text(encoding="utf-8"))
            except Exception:
                pass

        # Analyse failures and compute replan action
        replan_result = replan_analyze(
            runner_output=current_runner,
            evaluations=evaluations,
            intent_spec=intent_spec,
            evidence_dir=evidence_dir,
            round_number=round_number,
        )

        current_stages[f"replan_round_{round_number}"] = {
            "ok": True,
            "skipped": False,
            "action": replan_result.action,
            "decisions": [
                {"scenario_id": d.scenario_id, "replan_type": d.replan_type,
                 "confidence": d.confidence}
                for d in replan_result.decisions
            ],
        }

        if replan_result.action == "no_action":
            logger.info("replan_loop: round %d — no_action returned; stopping", round_number)
            break

        if replan_result.action == "escalate":
            logger.warning(
                "replan_loop: round %d — escalating to operator: %s",
                round_number, replan_result.escalation_reason,
            )
            current_stages[f"replan_round_{round_number}"]["escalation_reason"] = (
                replan_result.escalation_reason
            )
            break

        # action == "retry" — patch intent_spec and re-run generator + runner
        if replan_result.patched_intent_spec:
            _persist_json(intent_spec_path, replan_result.patched_intent_spec)
            logger.info("replan_loop: round %d — intent_spec patched and persisted", round_number)

        # Re-run generator with patched scenarios
        scenarios_path = evidence_dir / "scenarios.json"
        if not scenarios_path.is_file():
            logger.warning("replan_loop: scenarios.json not found — cannot re-generate; stopping")
            break

        try:
            gen_result = generator_run(
                scenarios_path=scenarios_path,
                ui_maps_dir=ui_maps_dir,
                out_dir=tests_dir,
                template_path=None,
                detect_screen_errors=detect_screen_errors,
                detect_screen_errors_vision=detect_screen_errors_vision,
                verbose=verbose,
            )
            if not gen_result.get("ok"):
                logger.warning(
                    "replan_loop: generator failed on round %d: %s",
                    round_number, gen_result.get("message"),
                )
                break
            current_stages[f"replan_round_{round_number}"]["generator"] = {
                "generated": gen_result.get("generated", 0),
                "blocked": gen_result.get("blocked", 0),
            }
        except Exception as exc:
            logger.warning("replan_loop: generator exception on round %d: %s", round_number, exc)
            break

        # Re-run Playwright tests
        try:
            new_runner = runner_run(
                tests_dir=tests_dir,
                evidence_out=evidence_dir,
                headed=headed,
                timeout_ms=timeout_ms,
                verbose=verbose,
            )
            if not new_runner.get("ok"):
                logger.warning(
                    "replan_loop: runner failed on round %d: %s",
                    round_number, new_runner.get("message"),
                )
                break
            current_runner = new_runner
            current_stages[f"replan_round_{round_number}"]["runner"] = {
                "pass": new_runner.get("pass_count", 0),
                "fail": new_runner.get("fail_count", 0),
                "blocked": new_runner.get("blocked_count", 0),
            }
            # Update main runner stage summary
            current_stages["runner"] = _summarise_runner(current_runner)
            logger.info(
                "replan_loop: round %d complete — pass=%d fail=%d blocked=%d",
                round_number,
                new_runner.get("pass_count", 0),
                new_runner.get("fail_count", 0),
                new_runner.get("blocked_count", 0),
            )
        except Exception as exc:
            logger.warning("replan_loop: runner exception on round %d: %s", round_number, exc)
            break

    return current_runner, current_stages


def _runner_has_failures(runner_result: dict) -> bool:
    """Return True if runner_result has any FAIL or BLOCKED scenarios."""
    runs = runner_result.get("runs") or []
    return any(r.get("status") in ("fail", "blocked", "error") for r in runs)


def _extract_screens(ticket_result: dict) -> list:
    """
    Derive the list of screens referenced in plan_pruebas.
    Falls back to ['FrmAgenda.aspx'] if none found.

    Pre-Fase-1 the supported-screen set was duplicated here. It now reads
    from the shared catalogue in `agenda_screens.SUPPORTED_SCREENS` so
    extending the MVP with a new screen is a one-file change.

    NOTE: freeform tickets use Spanish field names (descripcion/datos/esperado)
    instead of English (title/description). Both are checked.
    Also checks navigation_path from the ticket for explicit screen references.
    """
    from agenda_screens import SUPPORTED_SCREENS

    found = set()

    # Check navigation_path explicitly (freeform mode — most reliable source)
    for screen in ticket_result.get("navigation_path") or []:
        if screen in SUPPORTED_SCREENS:
            found.add(screen)

    # Check plan_pruebas — both English (ADO) and Spanish (freeform) field names
    for item in ticket_result.get("plan_pruebas") or []:
        title_text = (
            (item.get("title") or "")
            + " " + (item.get("description") or "")
            + " " + (item.get("descripcion") or "")
            + " " + (item.get("datos") or "")
            + " " + (item.get("esperado") or "")
        )
        lower = title_text.lower()
        for screen in SUPPORTED_SCREENS:
            if screen.lower() in lower:
                found.add(screen)
    return sorted(found) if found else ["FrmAgenda.aspx"]


def _persist_json(path: Path, data: dict) -> None:
    """Write dict to JSON file, creating parent dirs as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _synthetic_runner_output(ticket_id: int, gen_specs: list) -> dict:
    """Build a runner_output.json where all scenarios are BLOCKED (missing selectors)."""
    runs = []
    for spec in gen_specs:
        runs.append({
            "scenario_id": spec.get("scenario_id", ""),
            "spec_file": spec.get("spec_file", ""),
            "status": "blocked",
            "reason": spec.get("blocked_reason", "missing_selectors"),
            "duration_ms": 0,
            "assertion_failures": [],
            "artifacts": {},
        })
    return {
        "ok": True,
        "ticket_id": ticket_id,
        "runs": runs,
        "pass_count": 0,
        "fail_count": 0,
        "blocked_count": len(runs),
        "total_count": len(runs),
        "elapsed_s": 0.0,
    }


def _log_stage(name: str) -> None:
    logger.info("▶ Stage: %s", name)


def _fail(stage: str, error: str, message: str) -> dict:
    return {"ok": False, "stage": stage, "error": error, "message": message}


def _build_output(ticket_id: int, stages: dict, failed_result: dict, started: float) -> dict:
    return {
        "ok": False,
        "ticket_id": ticket_id,
        "stage": failed_result.get("stage", "unknown"),
        "error": failed_result.get("error", "pipeline_error"),
        "message": failed_result.get("message", ""),
        "stages": stages,
        "elapsed_s": round(time.time() - started, 2),
    }


# ── Per-stage summaries ───────────────────────────────────────────────────────

def _summarise_reader(r: dict) -> dict:
    base = {"ok": r.get("ok", False), "skipped": False}
    if r.get("ok"):
        ticket = r.get("ticket") or {}
        base["ticket_id"] = r.get("ticket_id")
        base["title"] = ticket.get("title", "")
        base["plan_item_count"] = len(r.get("plan_pruebas") or [])
    else:
        base["error"] = r.get("error")
        base["message"] = r.get("message")
    return base


def _summarise_compiler(r: dict) -> dict:
    base = {"ok": r.get("ok", False), "skipped": False}
    if r.get("ok"):
        scenarios = r.get("scenarios") or []
        in_scope = [s for s in scenarios if not s.get("out_of_scope")]
        out_scope = [s for s in scenarios if s.get("out_of_scope")]
        base["scenario_count"] = len(in_scope)
        base["out_of_scope_count"] = len(out_scope)
    else:
        base["error"] = r.get("error")
        base["message"] = r.get("message")
    return base


def _summarise_generator(r: dict) -> dict:
    base = {"ok": r.get("ok", False), "skipped": False}
    if r.get("ok"):
        specs = r.get("results") or r.get("specs") or []
        base["generated"] = sum(1 for s in specs if s.get("status") == "generated")
        base["blocked"] = sum(1 for s in specs if s.get("status") == "blocked")
        base["total"] = len(specs)
    else:
        base["error"] = r.get("error")
        base["message"] = r.get("message")
    return base


def _summarise_runner(r: dict) -> dict:
    base = {"ok": r.get("ok", False), "skipped": False}
    if r.get("ok"):
        base["pass"] = r.get("pass", r.get("pass_count", 0))
        base["fail"] = r.get("fail", r.get("fail_count", 0))
        base["blocked"] = r.get("blocked", r.get("blocked_count", 0))
        base["total"] = r.get("total", r.get("total_count", 0))
    else:
        base["error"] = r.get("error")
        base["message"] = r.get("message")
    return base


def _summarise_dossier(r: dict) -> dict:
    base = {"ok": r.get("ok", False), "skipped": False}
    if r.get("ok"):
        base["verdict"] = r.get("verdict")
        base["paths"] = r.get("paths")
        base["run_id"] = r.get("run_id")
    else:
        base["error"] = r.get("error")
        base["message"] = r.get("message")
    return base


def _summarise_preconditions(r: dict) -> dict:
    base = {"ok": r.get("ok", False), "skipped": r.get("skipped", False)}
    if r.get("ok"):
        summary = r.get("summary", {})
        base["total"] = summary.get("total", 0)
        base["ok_count"] = summary.get("ok", 0)
        base["blocked"] = summary.get("blocked", 0)
        if r.get("skipped"):
            base["skip_reason"] = r.get("skip_reason", "")
    else:
        base["error"] = r.get("error")
        base["message"] = r.get("message")
    return base


def _summarise_evaluator(r: dict) -> dict:
    base = {"ok": r.get("ok", False), "skipped": False}
    if r.get("ok"):
        evals = r.get("evaluations") or []
        base["pass"] = sum(1 for e in evals if e.get("status") == "pass")
        base["fail"] = sum(1 for e in evals if e.get("status") == "fail")
        base["blocked"] = sum(1 for e in evals if e.get("status") == "blocked")
        base["review"] = sum(1 for e in evals if e.get("status") == "review")
    else:
        base["error"] = r.get("error")
        base["message"] = r.get("message")
    return base


def _summarise_failure_analyzer(r: dict) -> dict:
    base = {"ok": r.get("ok", False), "skipped": False}
    if r.get("ok"):
        analyses = r.get("analyses") or []
        base["analyzed"] = len(analyses)
        categories: dict = {}
        for a in analyses:
            cat = a.get("category", "unknown")
            categories[cat] = categories.get(cat, 0) + 1
        base["categories"] = categories
    else:
        base["error"] = r.get("error")
        base["message"] = r.get("message")
    return base


def _summarise_publisher(r: dict, mode: str) -> dict:
    base = {"ok": r.get("ok", False), "skipped": False}
    if r.get("ok"):
        base["publish_state"] = r.get("publish_state", "dry-run")
        base["mode"] = mode
    else:
        base["error"] = r.get("error")
        base["message"] = r.get("message")
    return base


# ── CLI ───────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "QA UAT Pipeline — orchestrates all tools for an ADO ticket or a free-form intent. "
            "By default shows ALL output (DEBUG level). Use --background to suppress."
        )
    )
    # Source of truth: ADO ticket (original) OR intent_spec.json (free-form)
    source = p.add_mutually_exclusive_group()
    source.add_argument("--ticket", type=int, default=None,
                        help="ADO work item ID (original ticket mode).")
    source.add_argument("--intent-file", dest="intent_file", default=None,
                        help="Path to intent_spec.json for free-form QA (Fase 1).")
    # Free-form resume after data resolution
    p.add_argument("--resume", action="store_true",
                   help="Resume a free-form run after the orchestrator resolved data. "
                        "Requires --intent-file and --data-file.")
    p.add_argument("--data-file", dest="data_file", default=None,
                   help="Path to resolved_data.json for --resume.")
    # Common options
    p.add_argument(
        "--mode",
        choices=["dry-run", "publish"],
        default="dry-run",
        help="dry-run (default): no ADO write. publish: post comment to ADO.",
    )
    p.add_argument("--headed", action="store_true",
                   help="Run Playwright in headed mode (shows browser window).")
    p.add_argument("--timeout-ms", type=int, default=90_000, dest="timeout_ms",
                   help="Playwright per-test timeout in ms (default: 90000).")
    p.add_argument(
        "--skip-to",
        choices=_STAGE_NAMES,
        default=None,
        help="Skip all stages before this one (requires evidence files already on disk).",
    )
    p.add_argument("--ado-path", default=None,
                   help="Path to ado.py CLI (default: ../ADO Manager/ado.py).")
    p.add_argument("--background", action="store_true",
                   help="Background/quiet mode: suppress verbose output (only warnings/errors). "
                        "Default is to show EVERYTHING.")
    # Keep --verbose as a no-op alias for backwards compatibility
    p.add_argument("--verbose", action="store_true",
                   help="(Legacy flag — verbose is now the default. Use --background to suppress.)")
    # Fase 3 — Data Request Protocol
    p.add_argument("--auto-resolve", dest="auto_resolve", action="store_true",
                   help="[Fase 3] Auto-execute hint_queries from data_request via data_resolver.py "
                        "before emitting exit code 2. Resolves common fields (CLIENTE_ID, LOTE_ID, ...) "
                        "automatically; only truly missing data causes exit code 2.")
    # Fase 4 — In-flight UI error detection
    p.add_argument(
        "--detect-screen-errors", dest="detect_screen_errors", action="store_true",
        help="[Fase 4] Inject post-step DOM scan into generated specs. Fails the "
             "step immediately when a known validation/error pattern is found "
             "(ASP.NET validators, .alert-danger, 'campo requerido', ...).",
    )
    p.add_argument(
        "--detect-screen-errors-vision", dest="detect_screen_errors_vision",
        action="store_true",
        help="[Fase 4] Add vision-LLM screen analysis. Implies --detect-screen-errors. "
             "Requires `python screen_error_detector.py serve` running and the "
             "QA_UAT_VISION_DETECTOR_URL env var pointing to it.",
    )
    # Fase 9 — Multi-round replanning
    p.add_argument(
        "--replan", action="store_true",
        help="[Fase 9] Enable multi-round replanning. After a FAIL or BLOCKED result "
             "the pipeline calls replan_engine to compute an automated fix and "
             f"retries the generator+runner stages up to {_MAX_REPLAN_ROUNDS} times "
             "before escalating to the operator.",
    )
    args = p.parse_args()
    if args.detect_screen_errors_vision:
        args.detect_screen_errors = True
    return args


if __name__ == "__main__":
    main()
