"""
qa_uat_pipeline.py — Orchestrator for the full QA UAT pipeline.

Connects all 8 tools in sequence:
  B1 uat_ticket_reader → B3 ui_map_builder (per screen) → B4 uat_scenario_compiler
  → B5 playwright_test_generator → B6 uat_test_runner
  → B7 uat_dossier_builder → B8 ado_evidence_publisher

CLI:
    python qa_uat_pipeline.py --ticket 70 [--mode dry-run|publish] [--headed] [--verbose]
    python qa_uat_pipeline.py --ticket 70 --skip-to runner [--verbose]

Options:
    --ticket         ADO work item ID (required)
    --mode           dry-run (default) or publish — controls ado_evidence_publisher
    --headed         Run Playwright in headed mode (shows browser)
    --timeout-ms     Playwright per-step timeout in ms (default: 30000)
    --skip-to        Skip all stages before: reader|ui_map|compiler|generator|runner|dossier|publisher
    --ado-path       Path to ado.py (default: ../ADO Manager/ado.py)
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

_TOOL_VERSION = "1.0.0"
_TOOL_ROOT = Path(__file__).resolve().parent
_DEFAULT_ADO_PATH = _TOOL_ROOT.parent.parent / "ADO Manager" / "ado.py"

_STAGE_NAMES = [
    "reader",
    "ui_map",
    "compiler",
    "preconditions",
    "generator",
    "runner",
    "evaluator",
    "failure_analyzer",
    "dossier",
    "publisher",
]


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    args = _parse_args()
    if args.verbose:
        logging.basicConfig(
            level=logging.DEBUG,
            stream=sys.stderr,
            format="%(levelname)s %(name)s: %(message)s",
        )
    else:
        logging.basicConfig(level=logging.WARNING, stream=sys.stderr)

    result = run(
        ticket_id=args.ticket,
        mode=args.mode,
        headed=args.headed,
        timeout_ms=args.timeout_ms,
        skip_to=args.skip_to,
        ado_path=Path(args.ado_path) if args.ado_path else None,
        verbose=args.verbose,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result.get("ok") else 1)


# ── Core logic ────────────────────────────────────────────────────────────────

def run(
    ticket_id: int,
    mode: str = "dry-run",
    headed: bool = False,
    timeout_ms: int = 30_000,
    skip_to: Optional[str] = None,
    ado_path: Optional[Path] = None,
    verbose: bool = False,
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

    # ── Stage 2: ui_map (per screen) ─────────────────────────────────────────
    stage = "ui_map"
    # Derive screens from plan_pruebas (or default to FrmAgenda.aspx)
    screens = _extract_screens(ticket_result)

    if stage in skip_stages:
        stages[stage] = {"ok": True, "skipped": True, "screens": screens}
    else:
        from ui_map_builder import run as ui_map_run
        _log_stage(stage)
        ui_results = {}
        for screen in screens:
            logger.debug("Building UI map for screen: %s", screen)
            ui_result = ui_map_run(screen=screen, rebuild=False, verbose=verbose)
            ui_results[screen] = ui_result
            if not ui_result.get("ok"):
                stages[stage] = {
                    "ok": False,
                    "skipped": False,
                    "screen": screen,
                    "error": ui_result.get("error"),
                    "message": ui_result.get("message"),
                }
                return _build_output(ticket_id, stages, ui_result, started)
        stages[stage] = {"ok": True, "skipped": False, "screens": screens}

    # ── Stage 3: compiler ────────────────────────────────────────────────────
    stage = "compiler"
    if stage in skip_stages:
        stages[stage] = {"ok": True, "skipped": True}
        # Load cached scenarios
        scenarios_file = evidence_dir / "scenarios.json"
        if not scenarios_file.is_file():
            return _fail(stage, "cache_miss",
                         f"--skip-to {skip_to} requires cached scenarios at {scenarios_file}")
        compiler_result = json.loads(scenarios_file.read_text(encoding="utf-8"))
    else:
        from uat_scenario_compiler import run as compiler_run
        _log_stage(stage)
        compiler_result = compiler_run(
            ticket_json=ticket_result,
            scope_screen=screens[0] if len(screens) == 1 else None,
            verbose=verbose,
        )
        stages[stage] = _summarise_compiler(compiler_result)
        if not compiler_result.get("ok"):
            return _build_output(ticket_id, stages, compiler_result, started)

    # ── Stage 3b: precondition_checker ──────────────────────────────────────
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
            # DB unavailable is non-fatal (warn + continue)
            if prec_result.get("error") in ("db_credentials_missing", "db_unreachable"):
                logger.warning(
                    "Precondition check skipped (%s): %s",
                    prec_result.get("error"),
                    prec_result.get("message"),
                )
                stages[stage] = {
                    "ok": True, "skipped": True,
                    "reason": prec_result.get("error"),
                }
            else:
                stages[stage] = {
                    "ok": False, "skipped": False,
                    "error": prec_result.get("error"),
                    "message": prec_result.get("message"),
                }
                return _build_output(ticket_id, stages, prec_result, started)

    # ── Stage 4: generator ───────────────────────────────────────────────────
    stage = "generator"
    tests_dir = evidence_dir / "tests"
    ui_maps_dir = _TOOL_ROOT / "cache" / "ui_maps"

    if stage in skip_stages:
        stages[stage] = {"ok": True, "skipped": True}
        # Persist scenarios.json to disk so generator can read it
        _persist_json(evidence_dir / "scenarios.json", compiler_result)
    else:
        from playwright_test_generator import run as generator_run
        _log_stage(stage)

        # Persist scenarios.json to disk for generator
        _persist_json(evidence_dir / "scenarios.json", compiler_result)

        generator_result = generator_run(
            scenarios_path=evidence_dir / "scenarios.json",
            ui_maps_dir=ui_maps_dir,
            out_dir=tests_dir,
            template_path=None,
            verbose=verbose,
        )
        stages[stage] = _summarise_generator(generator_result)
        if not generator_result.get("ok"):
            return _build_output(ticket_id, stages, generator_result, started)

        # All scenarios blocked → warn but continue to dossier (skip runner)
        gen_specs = generator_result.get("specs", [])
        all_blocked = gen_specs and all(s.get("status") == "blocked" for s in gen_specs)
        if all_blocked:
            logger.warning("All scenarios are blocked (missing selectors). Skipping runner.")
            stages["runner"] = {"ok": True, "skipped": True,
                                "reason": "all_scenarios_blocked"}
            stages["evaluator"] = {"ok": True, "skipped": True,
                                   "reason": "all_scenarios_blocked"}
            stages["failure_analyzer"] = {"ok": True, "skipped": True,
                                          "reason": "all_scenarios_blocked"}
            # Build synthetic runner output
            runner_result = _synthetic_runner_output(ticket_id, gen_specs)
            _persist_json(evidence_dir / "runner_output.json", runner_result)
            return _run_dossier_and_publisher(
                ticket_id=ticket_id,
                stages=stages,
                evidence_dir=evidence_dir,
                runner_result=runner_result,
                ticket_result=ticket_result,
                mode=mode,
                ado_path=ado_path,
                verbose=verbose,
                started=started,
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

    # ── Stage 6: assertion_evaluator ─────────────────────────────────────────
    stage = "evaluator"
    if stage in skip_stages:
        stages[stage] = {"ok": True, "skipped": True}
        eval_file = evidence_dir / "evaluations.json"
        if not eval_file.is_file():
            # Evaluations optional — continue without them
            evaluations_result = None
        else:
            evaluations_result = json.loads(eval_file.read_text(encoding="utf-8"))
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

    # ── Stage 7: failure_analyzer ─────────────────────────────────────────────
    stage = "failure_analyzer"
    # Only run if there are failures to analyze
    has_failures = bool(
        evaluations_result
        and any(
            e.get("status") == "fail"
            for e in (evaluations_result.get("evaluations") or [])
        )
    )
    if stage in skip_stages or not has_failures:
        stages[stage] = {"ok": True, "skipped": True}
    else:
        from uat_failure_analyzer import run as analyzer_run
        _log_stage(stage)
        evals_path = evidence_dir / "evaluations.json"
        analyzer_result = analyzer_run(
            evaluations_path=evals_path,
            runner_output_path=evidence_dir / "runner_output.json",
            verbose=verbose,
        )
        stages[stage] = _summarise_failure_analyzer(analyzer_result)
        if not analyzer_result.get("ok"):
            return _build_output(ticket_id, stages, analyzer_result, started)

    return _run_dossier_and_publisher(
        ticket_id=ticket_id,
        stages=stages,
        evidence_dir=evidence_dir,
        runner_result=runner_result,
        ticket_result=ticket_result,
        mode=mode,
        ado_path=ado_path,
        verbose=verbose,
        started=started,
    )


# ── Dossier + Publisher sub-flow ─────────────────────────────────────────────

def _run_dossier_and_publisher(
    ticket_id: int,
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

    dossier_result = dossier_run(
        runner_output_path=runner_output_path,
        ticket_path=ticket_path,
        out_dir=evidence_dir,
        verbose=verbose,
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


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_screens(ticket_result: dict) -> list:
    """
    Derive the list of screens referenced in plan_pruebas.
    Falls back to ['FrmAgenda.aspx'] if none found.
    """
    _supported = {
        "FrmAgenda.aspx", "FrmDetalleLote.aspx", "FrmGestion.aspx", "Login.aspx"
    }
    found = set()
    for item in ticket_result.get("plan_pruebas") or []:
        title_text = (item.get("title") or "") + " " + (item.get("description") or "")
        for screen in _supported:
            if screen.lower() in title_text.lower():
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
        specs = r.get("specs") or []
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
        base["pass"] = r.get("pass_count", 0)
        base["fail"] = r.get("fail_count", 0)
        base["blocked"] = r.get("blocked_count", 0)
        base["total"] = r.get("total_count", 0)
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
    base = {"ok": r.get("ok", False), "skipped": False}
    if r.get("ok"):
        summary = r.get("summary", {})
        base["total"] = summary.get("total", 0)
        base["ok_count"] = summary.get("ok", 0)
        base["blocked"] = summary.get("blocked", 0)
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
        description="QA UAT Pipeline — orchestrates all 8 tools for a given ADO ticket."
    )
    p.add_argument("--ticket", type=int, required=True, help="ADO work item ID")
    p.add_argument(
        "--mode",
        choices=["dry-run", "publish"],
        default="dry-run",
        help="dry-run (default): no ADO write. publish: post comment to ADO.",
    )
    p.add_argument("--headed", action="store_true",
                   help="Run Playwright in headed mode (shows browser window).")
    p.add_argument("--timeout-ms", type=int, default=30_000,
                   help="Playwright per-step timeout in ms (default: 30000).")
    p.add_argument(
        "--skip-to",
        choices=_STAGE_NAMES,
        default=None,
        help="Skip all stages before this one (requires evidence files already on disk).",
    )
    p.add_argument("--ado-path", default=None,
                   help="Path to ado.py CLI (default: ../ADO Manager/ado.py).")
    p.add_argument("--verbose", action="store_true", help="Debug logging to stderr.")
    return p.parse_args()


if __name__ == "__main__":
    main()
