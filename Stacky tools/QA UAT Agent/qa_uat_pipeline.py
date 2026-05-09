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
import os
import sys
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.qa_uat.pipeline")

# Execution logger — importado lazy para evitar que un fallo de importación
# rompa el pipeline. Se usa via _get_exec_log() a lo largo de este módulo.
try:
    from execution_logger import get_logger as _get_exec_logger, get_active_logger as _get_active_exec_logger
    _EXEC_LOG_AVAILABLE = True
except ImportError:  # noqa: BLE001
    _EXEC_LOG_AVAILABLE = False
    def _get_exec_logger(*a, **kw):  # type: ignore[misc]
        return None
    def _get_active_exec_logger():  # type: ignore[misc]
        return None


def _init_exec_log(session_id: str, evidence_dir: Path):
    """Inicializar (o recuperar) el ExecutionLogger para la sesión activa."""
    if not _EXEC_LOG_AVAILABLE:
        return None
    try:
        return _get_exec_logger(session_id, evidence_dir=evidence_dir)
    except Exception:  # noqa: BLE001
        return None


def _exec_log_stage_start(log, stage: str, params: Optional[dict] = None) -> float:
    """Emitir stage_start y devolver t0 para calcular duration_ms."""
    import time as _time
    if log is not None:
        try:
            log.stage_start(stage, params)
        except Exception:  # noqa: BLE001
            pass
    return _time.time()


def _exec_log_stage_end(log, stage: str, t0: float, ok: bool, summary: Optional[dict] = None) -> None:
    if log is not None:
        try:
            log.stage_end(stage, ok=ok,
                          duration_ms=int((time.time() - t0) * 1000),
                          result_summary=summary)
        except Exception:  # noqa: BLE001
            pass


def _exec_log_event(log, event_name: str, data: dict) -> None:
    """FASE2/OBS — Emit a named structured event. No-op if log is None."""
    if log is not None:
        try:
            log.event(event_name, data)
        except Exception:  # noqa: BLE001
            pass

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

    # ── Fase 4b: Comandos analíticos/forenses (no requieren ticket obligatorio) ──
    if getattr(args, "analytics_report", False):
        result = _cmd_analytics_report(days=getattr(args, "days", 7))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        sys.exit(0 if result.get("ok") else 1)

    if getattr(args, "replay_run", None):
        if args.ticket is None:
            sys.stderr.write("error: --replay-run requiere --ticket\n")
            sys.exit(1)
        result = _cmd_replay_run(
            ticket_id=args.ticket,
            run_id=args.replay_run,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        sys.exit(0 if result.get("ok") else 1)

    if getattr(args, "validate_observability", False):
        if args.ticket is None:
            sys.stderr.write("error: --validate-observability requiere --ticket\n")
            sys.exit(1)
        result = _cmd_validate_observability(ticket_id=args.ticket)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        sys.exit(0 if result.get("ok") else 1)

    if getattr(args, "list_blockers", None):
        if args.ticket is None:
            sys.stderr.write("error: --list-blockers requiere --ticket\n")
            sys.exit(1)
        result = _cmd_list_blockers(
            ticket_id=args.ticket,
            run_id=args.list_blockers,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        sys.exit(0)

    if getattr(args, "resolve_blocker", None):
        if args.ticket is None or not args.run_id or not args.answer:
            sys.stderr.write(
                "error: --resolve-blocker requiere --ticket, --run-id y --answer\n"
            )
            sys.exit(1)
        result = _cmd_resolve_blocker(
            ticket_id=args.ticket,
            run_id=args.run_id,
            blocker_id=args.resolve_blocker,
            answer=args.answer,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        sys.exit(0 if result.get("ok") else 1)

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

    # ── Execution logger — P0/OBS: init BEFORE preflight/smoke so that
    # ──   any early BLOCKED exit still produces execution.jsonl (roadmap Cambio 1.1).
    _run_id = str(ticket_id)
    _exec_log = _init_exec_log(_run_id, evidence_dir)
    if _exec_log is not None:
        import datetime as _dt
        _exec_log.session_start({
            "event": "session_start",
            "run_id": _run_id,
            "ticket_id": ticket_id,
            "mode": mode,
            "tool": "qa_uat_agent",
            "tool_version": _TOOL_VERSION,
            "started_at": _dt.datetime.now(_dt.timezone.utc).isoformat().replace("+00:00", "Z"),
            "headed": headed,
            "timeout_ms": timeout_ms,
            "skip_to": skip_to,
            "replan": replan,
            "verbose": verbose,
        })

    # ── Preflight: verify AgendaWeb is up before doing anything costly ───────
    # QA UAT Agent NEVER manages AgendaWeb's runtime.  If the app is not
    # running, we return BLOCKED immediately (< 15s, no browser opened).
    _t0_preflight = time.time()
    try:
        from environment_preflight import run_environment_preflight
        preflight = run_environment_preflight()
        _exec_log_stage_end(
            _exec_log, "environment_preflight", _t0_preflight, ok=preflight.ok,
            summary={"verdict": preflight.verdict, "reason": preflight.reason,
                     "base_url": preflight.base_url},
        )
        if not preflight.ok:
            logger.warning("Preflight BLOCKED: %s — %s", preflight.reason, preflight.message)
            _pf_result = {
                **preflight.to_pipeline_dict(),
                "ticket_id": ticket_id,
                "verdict": "BLOCKED",
                "category": "ENV",
                "reason": preflight.reason,
                "failed_stage": "environment_preflight",
                "stages": {"environment_preflight": preflight.to_dict()},
                "elapsed_s": round(time.time() - started, 2),
            }
            if _exec_log is not None:
                try:
                    # P0/OBS — emit pipeline_verdict_decision before session_end (roadmap Cambio 1.3)
                    _exec_log.pipeline_verdict(
                        verdict="BLOCKED",
                        category="ENV",
                        reason=preflight.reason,
                        failed_stage="environment_preflight",
                        confidence=1.0,
                        evidence_refs=["environment_preflight_result"],
                        human_action_required="Check application server and environment configuration",
                    )
                    _exec_log.session_end(_pf_result)
                    _exec_log.close()
                except Exception:  # noqa: BLE001
                    pass
            return _pf_result
        logger.info("Preflight OK: %s", preflight.message)
    except Exception as _pf_exc:  # noqa: BLE001
        logger.warning("Preflight check failed (non-fatal): %s", _pf_exc)
        # Do not block the pipeline if the preflight module itself errors

    # ── Stage 2b: deployment_fingerprint_check (Sprint 3) ────────────────────
    # Verify the running build matches the ticket's expected build BEFORE any
    # browser is opened.  BLOCKED if mismatch in any mode; WARN if source is
    # missing in dry-run mode only.
    _t0_fp = time.time()
    try:
        from deployment_fingerprint import check_deployment_fingerprint as _check_fp
        from environment_preflight import get_agenda_base_url as _get_base_url
        _fp_base_url = _get_base_url()
        # Build expected dict from env vars (ticket-level config)
        _fp_expected_build_id = (
            os.environ.get("QA_UAT_EXPECTED_BUILD_ID", "").strip()
            or os.environ.get("QA_EXPECTED_BUILD_ID", "").strip()
            or None
        )
        _fp_expected_branch = os.environ.get("QA_UAT_EXPECTED_BRANCH", "").strip() or None
        _fp_expected: Optional[dict] = None
        if _fp_expected_build_id or _fp_expected_branch:
            _fp_expected = {
                "build_id": _fp_expected_build_id,
                "commit": None,
                "branch": _fp_expected_branch,
            }
        _fp_result = _check_fp(
            ticket_id=ticket_id,
            expected=_fp_expected,
            base_url=_fp_base_url,
            mode=mode,
            exec_logger=_exec_log,
            evidence_dir=evidence_dir,
            run_id=_run_id,
        )
        if _fp_result.decision == "BLOCKED":
            logger.warning(
                "deployment_fingerprint BLOCKED: reason=%s expected=%s active=%s",
                _fp_result.reason, _fp_result.expected, _fp_result.active,
            )
            _fp_fail = {
                "ok": False,
                "verdict": "BLOCKED",
                "category": "ENV",
                "reason": _fp_result.reason or "DEPLOYMENT_MISMATCH",
                "error": (_fp_result.reason or "DEPLOYMENT_MISMATCH").lower(),
                "failed_stage": "deployment_fingerprint_check",
                "message": (
                    f"Deployment fingerprint check BLOCKED (ticket {ticket_id}): "
                    f"{_fp_result.reason}. "
                    f"Expected={_fp_result.expected}, Active={_fp_result.active}. "
                    "Deploying the expected build before running QA tests."
                ),
                "deployment_fingerprint": _fp_result.to_dict(),
                "human_action_required": (
                    "Deploy the expected build or update QA_UAT_EXPECTED_BUILD_ID "
                    "to match the active build before running QA tests."
                ),
                "ticket_id": ticket_id,
                "stages": {"deployment_fingerprint_check": _fp_result.to_dict()},
                "elapsed_s": round(time.time() - started, 2),
            }
            if _exec_log is not None:
                try:
                    _exec_log.pipeline_verdict(
                        verdict="BLOCKED",
                        category="ENV",
                        reason=_fp_result.reason or "DEPLOYMENT_MISMATCH",
                        failed_stage="deployment_fingerprint_check",
                        confidence=1.0,
                        evidence_refs=["deployment_fingerprint_check"],
                        human_action_required=_fp_fail["human_action_required"],
                    )
                    _exec_log.session_end(_fp_fail)
                    _exec_log.close()
                except Exception:  # noqa: BLE001
                    pass
            return _fp_fail
        elif _fp_result.decision == "WARN":
            logger.warning(
                "deployment_fingerprint WARN: reason=%s (continuing pipeline)",
                _fp_result.reason,
            )
    except ImportError:
        logger.debug("deployment_fingerprint module unavailable — skipping Sprint 3 check")
    except Exception as _fp_exc:  # noqa: BLE001
        logger.warning("deployment_fingerprint check failed (non-fatal): %s", _fp_exc)

    # ── Smoke path: fast pre-validation before opening browser ───────────────
    # Verifies app responds, auth file exists, and target screen is reachable.
    # Runs in ≤20s. On failure → BLOCKED immediately, no browser opened.
    # Skip with QA_UAT_SKIP_SMOKE=true if needed.
    _t0_smoke = time.time()
    try:
        from smoke_path_checker import run_smoke_path
        # Use default screen — full screen list is determined after reader
        _smoke = run_smoke_path(screen="FrmAgenda.aspx")
        _exec_log_stage_end(
            _exec_log, "smoke_path", _t0_smoke, ok=bool(_smoke.get("ok")),
            summary={"verdict": _smoke.get("verdict"), "reason": _smoke.get("reason")},
        )
        if not _smoke.get("ok"):
            logger.warning("Smoke path BLOCKED: %s — %s", _smoke.get("reason"), _smoke.get("message"))
            _smoke_result = {
                **_smoke,
                "ticket_id": ticket_id,
                "verdict": "BLOCKED",
                "category": "ENV",
                "reason": _smoke.get("reason", "SMOKE_BLOCKED"),
                "failed_stage": "smoke_path",
                "stages": {"smoke_path": _smoke},
                "elapsed_s": round(time.time() - started, 2),
            }
            if _exec_log is not None:
                try:
                    # P0/OBS — emit pipeline_verdict_decision before session_end (roadmap Cambio 1.3)
                    _exec_log.pipeline_verdict(
                        verdict="BLOCKED",
                        category="ENV",
                        reason=_smoke.get("reason", "SMOKE_BLOCKED"),
                        failed_stage="smoke_path",
                        confidence=1.0,
                        evidence_refs=["smoke_path_result"],
                        human_action_required="Check smoke path configuration and application availability",
                    )
                    _exec_log.session_end(_smoke_result)
                    _exec_log.close()
                except Exception:  # noqa: BLE001
                    pass
            return _smoke_result
        if _smoke.get("verdict") != "WARNING":
            logger.info("Smoke path OK (%dms)", _smoke.get("elapsed_ms", 0))
    except Exception as _sm_exc:  # noqa: BLE001
        logger.warning("Smoke path check failed (non-fatal): %s", _sm_exc)

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
            _out = _build_output(ticket_id, stages, ticket_result, started)
            if _exec_log is not None:
                try:
                    _exec_log.session_end(_out)
                    _exec_log.close()
                except Exception:  # noqa: BLE001
                    pass
            return _out

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
        exec_log=_exec_log,
    )
    if isinstance(pipeline_result.get("stages"), dict):
        pipeline_result["stages"] = {**stages, **pipeline_result["stages"]}
    if _exec_log is not None:
        try:
            _exec_log.session_end(pipeline_result)
            _exec_log.close()
        except Exception:  # noqa: BLE001
            pass
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

    # P0/OBS — verdict must NEVER be UNKNOWN in new runs (roadmap Cambio 1.2 + 1.3).
    # If dossier does not emit a verdict, default to PASS when ok=True (all tests ran).
    verdict = dossier_result.get("verdict") or "PASS"
    # Sprint 5 — prefer runner_summary classification for category/reason on success path
    _runner_summary = runner_result.get("runner_summary") or {}
    category = _runner_summary.get("category") or ("APP" if verdict in ("FAIL", "PASS", "MIXED") else "PIP")
    reason   = _runner_summary.get("reason") or verdict  # dossier verdict string is self-describing

    # P0/OBS: emit complete pipeline_verdict_decision event before returning (roadmap Cambio 1.3)
    _active_log = _get_active_exec_logger()
    if _active_log is not None:
        try:
            _active_log.pipeline_verdict(
                verdict=verdict,
                category=category,
                reason=reason,
                failed_stage=None,
                confidence=1.0,
                evidence_refs=["runner_summary", "evaluator_summary", "dossier"],
                human_action_required=(
                    "review_dossier_and_decide" if verdict in ("FAIL", "MIXED") else None
                ),
            )
        except Exception:  # noqa: BLE001
            pass

    return {
        "ok": True,
        "ticket_id": ticket_id,
        "verdict": verdict,
        "category": category,
        "reason": reason,
        # Sprint 5 — expose runner_summary artifact links in pipeline output
        "runner_summary": _runner_summary,
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

    # ── Execution logger (inicializar tan pronto como conocemos run_id) ──────
    _exec_log = _init_exec_log(run_id, evidence_dir)
    if _exec_log is not None:
        _exec_log.session_start({
            "run_id": run_id, "mode": mode, "headed": headed,
            "timeout_ms": timeout_ms, "skip_to": skip_to,
            "auto_resolve": auto_resolve, "verbose": verbose,
            "tool_version": _TOOL_VERSION,
            "source": "freeform",
        })

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
        exec_log=_exec_log,
    )
    # Merge freeform-specific stages into the result
    if isinstance(pipeline_result.get("stages"), dict):
        pipeline_result["stages"] = {**stages, **pipeline_result["stages"]}
    pipeline_result["run_id"] = run_id
    pipeline_result["source"] = "freeform"
    if _exec_log is not None:
        try:
            _exec_log.session_end(pipeline_result)
            _exec_log.close()
        except Exception:  # noqa: BLE001
            pass
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
    exec_log=None,   # ExecutionLogger | None  — inyectado desde run() / _run_freeform()
) -> dict:
    """
    Run stages 2-11 (ui_map through publisher) given an already-loaded ticket_result.
    Used by both run() (ADO mode) and _run_freeform() (free-form mode).
    """
    stages: dict = {}
    ui_maps_dir = _TOOL_ROOT / "cache" / "ui_maps"

    # ── Effective config freeze ───────────────────────────────────────────────
    # Read all guardrail env vars ONCE at the start and freeze them.
    # Nothing running after this point may change credentials, playbook choice,
    # target screen, or mode. Saved to evidence for auditability.
    import hashlib as _hashlib
    _user    = os.environ.get("AGENDA_WEB_USER", "")
    _pass    = os.environ.get("AGENDA_WEB_PASS", "")
    _base_url = os.environ.get("AGENDA_WEB_BASE_URL", "http://localhost:35017/AgendaWeb/")
    _pass_hash = _hashlib.sha256(_pass.encode()).hexdigest()[:8] if _pass else ""
    _effective_config = {
        "base_url":               _base_url,
        "username_source":        "env" if _user else "MISSING",
        "password_present":       bool(_pass),
        "password_hash_prefix":   _pass_hash,
        "manage_app":             False,
        "allow_ui_discovery":     os.environ.get("QA_UAT_ALLOW_UI_DISCOVERY", "false").lower() in ("1", "true", "yes"),
        "allow_llm_navigation":   os.environ.get("QA_UAT_ALLOW_LLM_NAVIGATION", "false").lower() in ("1", "true", "yes"),
        "require_playbook":       os.environ.get("QA_UAT_REQUIRE_PLAYBOOK", "true").lower() not in ("0", "false", "no"),
        "max_login_attempts":     int(os.environ.get("QA_UAT_MAX_LOGIN_ATTEMPTS", "1")),
        "max_browser_launches":   int(os.environ.get("QA_UAT_MAX_BROWSER_LAUNCHES", "1")),
        "max_total_minutes":      int(os.environ.get("QA_UAT_MAX_TOTAL_MINUTES", "6")),
        "expected_human_minutes": int(os.environ.get("QA_UAT_EXPECTED_HUMAN_MINUTES", "2")),
        "max_runtime_multiplier": int(os.environ.get("QA_UAT_MAX_RUNTIME_MULTIPLIER", "3")),
        "frozen_at":              time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    # Persist to evidence immediately for auditability
    _persist_json(evidence_dir / "effective_config.json", _effective_config)
    logger.info("Effective config frozen: %s", _effective_config)

    # Validate credentials are present before opening any browser
    if not _user or not _pass:
        _cred_err = {
            "ok": False,
            "verdict": "BLOCKED",
            "category": "ENV",
            "reason": "MISSING_CREDENTIALS",
            "message": (
                "AGENDA_WEB_USER y/o AGENDA_WEB_PASS no están configurados. "
                "Definí las variables de entorno antes de correr QA UAT."
            ),
            "credentials_source": "env",
            "username_present": bool(_user),
            "password_present": bool(_pass),
        }
        stages["config_validation"] = {"ok": False, "skipped": False, **_cred_err}
        return _build_output(ticket_id, stages, _cred_err, started)

    # ── Guardrail: max total execution time ──────────────────────────────────
    # Default: 6 minutes (3× the expected 2-minute human flow).
    # Override with QA_UAT_MAX_TOTAL_MINUTES.
    _max_minutes = _effective_config["max_total_minutes"]
    _deadline = started + _max_minutes * 60

    def _check_deadline(stage_name: str) -> Optional[dict]:
        if time.time() > _deadline:
            return {
                "ok": False,
                "verdict": "BLOCKED",
                "reason": "EXCEEDED_REASONABLE_RUNTIME",
                "message": (
                    f"La ejecución excedió el tiempo máximo de {_max_minutes} minutos "
                    f"(QA_UAT_EXPECTED_HUMAN_MINUTES={_effective_config['expected_human_minutes']}, "
                    f"QA_UAT_MAX_RUNTIME_MULTIPLIER={_effective_config['max_runtime_multiplier']}). "
                    f"Stage fallido: '{stage_name}'."
                ),
                "stage": "timeout_guard",
                "ticket_id": ticket_id,
                "stages": stages,
                "elapsed_s": round(time.time() - started, 2),
            }
        return None

    # ── Stage S8-sec: security_check (Sprint 8) — PII, secrets, injection ──
    # Run AFTER reader/credentials validation and BEFORE quality_intake / LLM calls.
    # Non-blocking: "block" decision is logged and recorded but pipeline continues.
    # The operator reviews the security_check event and decides whether to abort.
    try:
        from artifact_security import run_security_check as _run_sec_check
        _sec_texts = {
            "ticket_description": str(
                ticket_result.get("description_md") or ticket_result.get("description", "")
            ),
            "analisis_tecnico": str(ticket_result.get("analisis_tecnico", "") or ""),
            "plan_pruebas": " ".join(
                str(p) for p in (ticket_result.get("plan_pruebas") or [])
            ),
        }
        for _sec_source, _sec_text in _sec_texts.items():
            if _sec_text.strip():
                _sec_evt = _run_sec_check(
                    text=_sec_text,
                    source=_sec_source,
                    exec_logger=exec_log,
                )
                if _sec_evt.get("decision") == "block":
                    logger.warning(
                        "security_check BLOCK: source=%s injection_risk=%s patterns=%s",
                        _sec_source, _sec_evt.get("injection_risk"),
                        _sec_evt.get("injection_patterns"),
                    )
                elif _sec_evt.get("pii_found") or _sec_evt.get("secrets_found"):
                    logger.info(
                        "security_check: pii=%s secrets=%s source=%s — sanitize_and_continue",
                        _sec_evt.get("pii_found"), _sec_evt.get("secrets_found"), _sec_source,
                    )
    except ImportError:
        logger.debug("artifact_security module unavailable — skipping Sprint 8 security check")
    except Exception as _sec_exc:  # noqa: BLE001
        logger.warning("security_check failed (non-fatal): %s", _sec_exc)

    # ── Stage 2c: quality_intake_result (Sprint 4) ──────────────────────────
    # Classify each acceptance criterion by the most appropriate test layer
    # BEFORE screen detection and compilation.  Only items with
    # layer=uat or layer=smoke_e2e will be forwarded to the compiler.
    # Non-UAT items are preserved in test_portfolio.json with owner+handoff.
    # If no UAT items exist after classification → SKIPPED PIP NO_UAT_ITEMS (not error).
    _quality_intake_result: Optional[object] = None  # QualityIntakeResult | None
    _uat_cas: Optional[list] = None  # filtered list forwarded to compiler
    stage = "quality_intake"
    try:
        from quality_intake import run_quality_intake as _run_qi, extract_acceptance_criteria as _extract_cas, build_no_uat_skipped_result as _build_no_uat
        _t0_qi = _exec_log_stage_start(exec_log, stage)
        _qi_cas = _extract_cas(ticket_result)
        if _qi_cas:
            _quality_intake_result = _run_qi(
                ticket_id=ticket_id if isinstance(ticket_id, int) else 0,
                title=ticket_result.get("title", str(ticket_id)),
                description_md=ticket_result.get("description_md", ""),
                acceptance_criteria=_qi_cas,
                analisis_tecnico=ticket_result.get("analisis_tecnico", ""),
                plan_pruebas=" ".join(
                    str(p) for p in (ticket_result.get("plan_pruebas") or [])
                ),
                exec_logger=exec_log,
                evidence_dir=evidence_dir,
                run_id=str(ticket_id),
            )
            _qi_layers = _quality_intake_result.layer_counts()
            stages[stage] = {
                "ok": True,
                "skipped": False,
                "items_total": _quality_intake_result.items_total,
                "layers": _qi_layers,
                "uat_required": _quality_intake_result.uat_required,
                "manual_review_required": _quality_intake_result.manual_review_required,
                "artifact_path": _quality_intake_result.artifact_path,
            }
            _exec_log_stage_end(exec_log, stage, _t0_qi, ok=True, summary=stages[stage])

            # Build list of UAT/smoke_e2e CAs to forward to compiler
            _uat_cas = [
                i.description for i in _quality_intake_result.uat_items
            ]

            # SKIPPED path: no UAT items at all → positive signal, not error
            if not _uat_cas:
                _no_uat = _build_no_uat(
                    ticket_id=ticket_id if isinstance(ticket_id, int) else 0,
                    portfolio_path=_quality_intake_result.artifact_path,
                )
                stages[stage]["uat_required"] = False
                if exec_log is not None:
                    try:
                        exec_log.pipeline_verdict(
                            verdict="SKIPPED",
                            category="PIP",
                            reason="NO_UAT_ITEMS",
                            failed_stage=None,
                            confidence=1.0,
                            evidence_refs=["quality_intake_result"],
                            human_action_required=_no_uat.get("human_action_required"),
                        )
                        exec_log.session_end(_no_uat)
                        exec_log.close()
                    except Exception:  # noqa: BLE001
                        pass
                stages_copy = {**stages}
                _no_uat["stages"] = stages_copy
                _no_uat["elapsed_s"] = round(time.time() - started, 2)
                return _no_uat
        else:
            # No CAs found — skip quality_intake gracefully, pipeline continues normally
            stages[stage] = {
                "ok": True, "skipped": True,
                "reason": "no_acceptance_criteria_found",
            }
            _exec_log_stage_end(exec_log, stage, _t0_qi, ok=True, summary=stages[stage])
    except ImportError:
        logger.debug("quality_intake module unavailable — skipping Sprint 4 classification")
        stages[stage] = {"ok": True, "skipped": True, "reason": "module_not_found"}
    except Exception as _qi_exc:  # noqa: BLE001
        logger.warning("quality_intake failed (non-fatal): %s", _qi_exc)
        stages[stage] = {"ok": True, "skipped": True, "reason": f"error:{_qi_exc}"}

    # ── Stage 2: ui_map ──────────────────────────────────────────────────────
    # P0/PIP — use screen_detector.py for auditable, blocking-aware detection
    # (roadmap Cambio 1.4). Falls back to legacy _extract_screens() if module
    # unavailable so the pipeline degrades gracefully.
    stage = "ui_map"
    try:
        from screen_detector import detect_screens_and_persist as _detect_screens_persist
        # Sprint 2: persist screen_detection.json artifact per run alongside detection
        _detection = _detect_screens_persist(
            ticket_result=ticket_result,
            evidence_dir=evidence_dir,
            run_id=str(ticket_id),
        )
        screens = _detection.selected_screens
        # P0/OBS: emit screen_detection_result with full structured evidence (roadmap Cambio 1.4)
        # Sprint 2: include artifact_path reference in event
        _exec_log_event(exec_log, "screen_detection_result", {
            "ticket_id": ticket_id,
            **_detection.to_dict(),
            "sources_scanned": [
                "navigation_path", "analisis_tecnico",
                "plan_pruebas", "description", "screen_aliases.yml",
            ],
            "supported_screens_version": "screen_detector.py+screen_aliases.yml",
            "artifact_path": _detection.artifact_path,
        })
        # Block pipeline if detector signals ambiguity or low confidence
        if _detection.blocked:
            _block_reason = _detection.block_reason or "SCREEN_DETECTION_FAILED"
            _category = "PIP"
            _human_action = (
                "Clarify which screen the ticket targets and re-run, "
                "or add aliases to screen_aliases.yml"
            )
            logger.warning(
                "screen_detector BLOCKED: %s — screens=%s",
                _block_reason, _detection.selected_screens,
            )
            _screen_blocked_result = {
                "ok": False,
                "verdict": "BLOCKED",
                "category": _category,
                "reason": _block_reason,
                "failed_stage": "screen_detection",
                "error": _block_reason.lower(),
                "message": (
                    f"Deteccion de pantalla bloqueada: {_block_reason}. "
                    f"Pantallas candidatas: {_detection.selected_screens}. "
                    f"Accion requerida: {_human_action}"
                ),
                "screen_detection": _detection.to_dict(),
                "human_action_required": _human_action,
            }
            stages["screen_detection"] = {"ok": False, "skipped": False, **_screen_blocked_result}
            if exec_log is not None:
                try:
                    exec_log.pipeline_verdict(
                        verdict="BLOCKED",
                        category=_category,
                        reason=_block_reason,
                        failed_stage="screen_detection",
                        confidence=_detection.confidence,
                        evidence_refs=["screen_detection_result"],
                        human_action_required=_human_action,
                    )
                    exec_log.session_end(_screen_blocked_result)
                    exec_log.close()
                except Exception:  # noqa: BLE001
                    pass
            return _build_output(ticket_id, stages, _screen_blocked_result, started)
    except ImportError:
        # Graceful degradation: screen_detector.py unavailable — use legacy function
        logger.debug("screen_detector unavailable — using legacy _extract_screens()")
        screens = _extract_screens(ticket_result)
        _exec_log_event(exec_log, "screen_detection_result", {
            "ticket_id": ticket_id,
            "selected_screens": screens,
            "fallback_used": screens == ["FrmAgenda.aspx"],
            "ambiguous": False,
            "blocked": False,
            "sources_scanned": ["navigation_path", "plan_pruebas", "analisis_tecnico", "description_md"],
            "supported_screens_version": "legacy:_extract_screens",
            "artifact_path": None,
        })

    if not screens:
        # screen_detector returned empty list without blocking — fall back defensively
        screens = ["FrmAgenda.aspx"]

    if stage in skip_stages:
        stages[stage] = {"ok": True, "skipped": True, "screens": screens}
    else:
        # Guard: QA_UAT_ALLOW_UI_DISCOVERY controls whether a browser can be opened
        # to map the UI dynamically.  DEFAULT IS FALSE — only cached maps/playbooks
        # are used unless the operator explicitly opts in.
        # To enable dynamic discovery: set QA_UAT_ALLOW_UI_DISCOVERY=true
        allow_discovery = os.environ.get("QA_UAT_ALLOW_UI_DISCOVERY", "false").lower() in ("1", "true", "yes")

        if _dl := _check_deadline(stage):
            return _dl

        from ui_map_builder import run as ui_map_run
        _log_stage(stage)
        _t0 = _exec_log_stage_start(exec_log, stage, {"screens": screens})
        for screen in screens:
            logger.debug("Building UI map for screen: %s", screen)
            # If discovery is disabled, verify the cache exists without rebuilding.
            cache_file = ui_maps_dir / f"{screen}.json"
            # FASE2/OBS: emit ui_map_cache_result per screen
            _exec_log_event(exec_log, "ui_map_cache_result", {
                "screen": screen,
                "cache_hit": cache_file.is_file(),
                "cache_path": str(cache_file),
                "discovery_allowed": allow_discovery,
            })
            if not allow_discovery and not cache_file.is_file():
                ui_fail = {
                    "ok": False,
                    "verdict": "BLOCKED",
                    "category": "GEN",
                    "reason": "NO_PLAYBOOK_OR_UI_MAP",
                    "error": "ui_discovery_disabled_no_cache",
                    "message": (
                        f"QA_UAT_ALLOW_UI_DISCOVERY=false y no hay UI map cacheado para {screen}. "
                        "Grabá el flujo una vez con 'python ui_map_builder.py --screen {screen} --rebuild' "
                        "y luego reintentá."
                    ),
                }
                stages[stage] = {
                    "ok": False, "skipped": False, "screen": screen,
                    "error": ui_fail["error"], "message": ui_fail["message"],
                }
                _exec_log_stage_end(exec_log, stage, _t0, ok=False, summary=stages[stage])
                return _build_output(ticket_id, stages, ui_fail, started)
            ui_result = ui_map_run(screen=screen, rebuild=False, verbose=verbose)
            if not ui_result.get("ok"):
                stages[stage] = {
                    "ok": False, "skipped": False, "screen": screen,
                    "error": ui_result.get("error"), "message": ui_result.get("message"),
                }
                _exec_log_stage_end(exec_log, stage, _t0, ok=False, summary=stages[stage])
                return _build_output(ticket_id, stages, ui_result, started)
        stages[stage] = {"ok": True, "skipped": False, "screens": screens}
        _exec_log_stage_end(exec_log, stage, _t0, ok=True, summary=stages[stage])

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
        _t0 = _exec_log_stage_start(exec_log, stage)
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
        # Sprint 4 — Layer Router filter: only pass UAT/smoke_e2e CAs to compiler.
        # When quality_intake ran and found UAT items, build a filtered ticket copy
        # so the compiler only generates scenarios for browser-testable CAs.
        # Non-UAT items are preserved in test_portfolio.json (not discarded).
        _compiler_ticket = ticket_result
        if _uat_cas is not None:
            # quality_intake ran — build a ticket view with only UAT CAs
            # We enrich plan_pruebas with the filtered UAT descriptions so the
            # compiler sees only the items that need browser validation.
            import copy as _copy
            _compiler_ticket = _copy.deepcopy(ticket_result)
            # Replace acceptance_criteria and plan_pruebas with UAT-only items
            _compiler_ticket["acceptance_criteria"] = _uat_cas
            if isinstance(_compiler_ticket.get("plan_pruebas"), list):
                # Keep plan_pruebas items whose description matches a UAT CA
                _uat_set = set(_uat_cas)
                _compiler_ticket["plan_pruebas"] = [
                    p for p in _compiler_ticket["plan_pruebas"]
                    if (
                        isinstance(p, str) and p.strip() in _uat_set
                    ) or (
                        isinstance(p, dict) and (
                            p.get("description", "") in _uat_set
                            or p.get("descripcion", "") in _uat_set
                        )
                    )
                ]
            _exec_log_event(exec_log, "compiler_filtered_by_intake", {
                "ticket_id": ticket_id,
                "uat_ca_count": len(_uat_cas),
                "original_ca_count": len(
                    ticket_result.get("acceptance_criteria") or
                    ticket_result.get("plan_pruebas") or []
                ),
            })
        compiler_result = compiler_run(
            ticket_json=_compiler_ticket,
            scope_screen=screens[0] if len(screens) == 1 else None,
            ui_aliases=ui_aliases or None,
            ui_elements=ui_elements or None,
            verbose=verbose,
        )
        stages[stage] = _summarise_compiler(compiler_result)
        # FORENSIC-20260508 | FIX-6 | Use key 'compiled' (not 'scenario_count') to match
        # the compiler output contract. 'scenario_count' was always 0 in exec logs.
        compiled_count = compiler_result.get("compiled", 0)
        out_of_scope_count = compiler_result.get("out_of_scope", 0)
        _exec_log_stage_end(exec_log, stage, _t0, ok=compiler_result.get("ok", False),
                            summary={"scenario_count": compiled_count,
                                     "out_of_scope": out_of_scope_count})
        # FASE2/OBS: emit compiler_summary event with full detail
        _out_of_scope_items = compiler_result.get("out_of_scope_items", [])
        _scope_mismatch_count = sum(
            1 for i in _out_of_scope_items if i.get("razon") == "SCOPE_MISMATCH"
        )
        _exec_log_event(exec_log, "compiler_summary", {
            "compiled": compiled_count,
            "scenario_count": compiled_count,
            "out_of_scope": out_of_scope_count,
            "out_of_scope_count": out_of_scope_count,
            "scope_screen": screens[0] if len(screens) == 1 else screens,
            "reasons": {"SCOPE_MISMATCH": _scope_mismatch_count},
        })
        if not compiler_result.get("ok"):
            return _build_output(ticket_id, stages, compiler_result, started)
        # FORENSIC-20260508 | FIX-3 | Early-exit when 0 scenarios compiled and items
        # existed but were all discarded. Avoids wasting 3 more stages only to fail
        # at runner with the confusing 'no_tests_found' error.
        if compiled_count == 0 and out_of_scope_count > 0:
            # FASE1/PIP/FIX-3: Explicit BLOCKED verdict so session_end never has null verdict.
            no_scenarios_result = {
                "ok": False,
                "verdict": "BLOCKED",
                "category": "PIP",
                "reason": "NO_EXECUTABLE_SCENARIOS",
                "error": "no_executable_scenarios",
                "message": (
                    f"El compiler procesó {out_of_scope_count} item(s) del plan de pruebas "
                    f"pero ninguno resultó ejecutable. Revisá out_of_scope_items en scenarios.json."
                ),
                "out_of_scope_count": out_of_scope_count,
                "out_of_scope_items": _out_of_scope_items,
                "human_action_required": "review_screen_scope_or_test_plan",
            }
            _persist_json(evidence_dir / "scenarios.json", compiler_result)
            return _build_output(ticket_id, stages, no_scenarios_result, started)
        # Write scenarios.json now so that preconditions (next stage) can read it
        _persist_json(evidence_dir / "scenarios.json", compiler_result)

    # ── Stage 3b: preconditions ──────────────────────────────────────────────
    stage = "preconditions"
    if stage in skip_stages:
        stages[stage] = {"ok": True, "skipped": True}
    else:
        from uat_precondition_checker import run as preconditions_run
        _log_stage(stage)
        _t0 = _exec_log_stage_start(exec_log, stage)
        prec_result = preconditions_run(
            scenarios_path=evidence_dir / "scenarios.json",
            verbose=verbose,
        )
        if prec_result.get("ok"):
            stages[stage] = _summarise_preconditions(prec_result)
            _exec_log_stage_end(exec_log, stage, _t0, ok=True, summary=stages[stage])
        else:
            if prec_result.get("error") in ("db_credentials_missing", "db_unreachable"):
                logger.warning("Precondition check skipped (%s): %s",
                               prec_result.get("error"), prec_result.get("message"))
                stages[stage] = {"ok": True, "skipped": True,
                                 "reason": prec_result.get("error")}
                _exec_log_stage_end(exec_log, stage, _t0, ok=True, summary=stages[stage])
            else:
                stages[stage] = {"ok": False, "skipped": False,
                                 "error": prec_result.get("error"),
                                 "message": prec_result.get("message")}
                return _build_output(ticket_id, stages, prec_result, started)

    # ── Stage 3c: selector_contract_validation (Sprint 2) ───────────────────
    # Validate that all aliases requested by the compiled scenarios exist in
    # the UI map BEFORE handing control to the generator. If any alias is
    # missing or targets a decorative element, the pipeline is blocked here
    # so no .spec.ts file is ever written with broken selectors.
    #
    # NOTE: Validation only runs when compiled scenarios include explicit
    # alias_semantic / screen fields (the generator-facing format). Scenarios
    # in the legacy pantalla/pasos format are skipped — they are handled by
    # playwright_test_generator which does its own selector resolution.
    stage = "selector_contract"
    if stage not in skip_stages and "compiler" not in skip_stages:
        try:
            from selector_contract_validator import validate_all_scenarios as _validate_sc
            _sc_scenarios_raw = (compiler_result.get("scenarios") or [])
            # Filter to scenarios that use the generator-facing format
            # (must have 'screen' field and at least one step with 'alias_semantic')
            _sc_scenarios = [
                s for s in _sc_scenarios_raw
                if s.get("screen") and any(
                    step.get("alias_semantic")
                    for step in s.get("steps", [])
                )
            ]
            if not _sc_scenarios:
                # No alias-contract-checkable scenarios — skip validation gracefully.
                # This is expected for legacy pantalla/pasos compiled format or empty plans.
                stages["selector_contract"] = {
                    "ok": True, "skipped": True,
                    "reason": "no_alias_contract_scenarios",
                }
            else:
                _sc_result = _validate_sc(
                    scenarios=_sc_scenarios,
                    ui_maps_dir=ui_maps_dir,
                    evidence_dir=evidence_dir,
                    run_id=str(ticket_id),
                )
                # Emit event for every validation result
                for _sc_item in _sc_result.get("results", []):
                    _item_dict = _sc_item.to_dict()
                    _exec_log_event(exec_log, "selector_contract_validation", {
                        **_item_dict,
                        "artifact_path": _sc_item.artifact_path,
                    })
                stages["selector_contract"] = {
                    "ok": _sc_result["ok"],
                    "skipped": False,
                    "blocked_count": _sc_result["blocked_count"],
                    "allow_count": _sc_result["allow_count"],
                    "first_blocked_reason": _sc_result.get("first_blocked_reason"),
                }
                if not _sc_result["ok"]:
                    _sc_block_reason = _sc_result.get("first_blocked_reason", "SELECTOR_ALIAS_NOT_IN_UI_MAP")
                    _sc_block_screen = _sc_result.get("first_blocked_screen", screens[0] if screens else "unknown")
                    logger.warning(
                        "selector_contract BLOCKED: reason=%s screen=%s",
                        _sc_block_reason, _sc_block_screen,
                    )
                    _sc_fail = {
                        "ok": False,
                        "verdict": "BLOCKED",
                        "category": "GEN",
                        "reason": _sc_block_reason,
                        "error": _sc_block_reason.lower(),
                        "failed_stage": "selector_contract",
                        "message": (
                            f"Selector contract validation failed for screen {_sc_block_screen!r}: "
                            f"{_sc_block_reason}. "
                            f"{_sc_result['blocked_count']} scenario(s) blocked. "
                            "No .spec.ts files will be generated. "
                            "Fix the aliases in the UI map or update the compiler output."
                        ),
                        "human_action_required": (
                            "Check aliases in compiled scenarios vs. UI map. "
                            f"Run: python ui_map_builder.py --screen {_sc_block_screen} --rebuild"
                        ),
                    }
                    if exec_log is not None:
                        try:
                            exec_log.pipeline_verdict(
                                verdict="BLOCKED",
                                category="GEN",
                                reason=_sc_block_reason,
                                failed_stage="selector_contract",
                                confidence=1.0,
                                evidence_refs=["selector_contract_validation"],
                                human_action_required=_sc_fail["human_action_required"],
                            )
                            exec_log.session_end(_sc_fail)
                            exec_log.close()
                        except Exception:  # noqa: BLE001
                            pass
                    return _build_output(ticket_id, stages, _sc_fail, started)
        except ImportError:
            logger.debug("selector_contract_validator unavailable — skipping alias contract check")
            stages["selector_contract"] = {"ok": True, "skipped": True,
                                           "reason": "module_not_found"}

    # ── Sprint 4: Auto-inject data_readiness_preconditions ──────────────────
    # When quality_intake found UAT items with needs_data_seed=True, inject
    # data_readiness_preconditions into compiler_result scenarios so that
    # Stage 3d (check_data_readiness from Sprint 3) activates automatically.
    # This only mutates the in-memory compiler_result (not scenarios.json yet).
    if _quality_intake_result is not None and "compiler" not in skip_stages:
        try:
            from quality_intake import _auto_data_preconditions as _adp
            _intake_items_by_desc = {
                i.description: i
                for i in _quality_intake_result.items
                if i.needs_data_seed and i.needs_browser
            }
            if _intake_items_by_desc:
                _injected_count = 0
                for _sc in (compiler_result.get("scenarios") or []):
                    # Match scenario to intake item by description or title similarity
                    _sc_title = _sc.get("title", "") or _sc.get("pantalla", "") or ""
                    for _desc, _intake_item in _intake_items_by_desc.items():
                        # Inject if scenario doesn't already have data preconditions
                        if not _sc.get("data_readiness_preconditions"):
                            _precs = _adp(_intake_item)
                            if _precs:
                                _sc["data_readiness_preconditions"] = _precs
                                _injected_count += 1
                                break  # one intake item per scenario
                if _injected_count:
                    logger.info(
                        "Sprint 4: auto-injected data_readiness_preconditions into %d scenario(s)",
                        _injected_count,
                    )
                    _exec_log_event(exec_log, "data_preconditions_auto_injected", {
                        "ticket_id": ticket_id,
                        "injected_count": _injected_count,
                    })
        except Exception as _adp_exc:  # noqa: BLE001
            logger.warning("data_readiness_preconditions auto-inject failed (non-fatal): %s", _adp_exc)

    # ── Stage 3d: data_readiness_check (Sprint 3) ────────────────────────────
    # Verify that test data is available BEFORE opening the browser.
    # Categorizes failures as DATA (GRID_EMPTY, TEST_ENTITY_NOT_FOUND, etc.)
    # vs ENV (DATA_SOURCE_UNREACHABLE) so the root cause is clear without
    # needing to run Playwright.
    #
    # Only runs when compiled scenarios include data_readiness_preconditions.
    # If DB is unavailable, checks are skipped gracefully (not blocked).
    stage = "data_readiness_check"
    _sc_scenarios_for_readiness = (compiler_result.get("scenarios") or []) if "compiler" not in skip_stages else []
    _any_data_preconditions = any(
        s.get("data_readiness_preconditions")
        for s in _sc_scenarios_for_readiness
    )
    if stage in skip_stages:
        stages[stage] = {"ok": True, "skipped": True}
    elif not _any_data_preconditions:
        # No data readiness preconditions defined — skip gracefully
        stages[stage] = {
            "ok": True, "skipped": True,
            "reason": "no_data_readiness_preconditions",
        }
    else:
        try:
            from uat_precondition_checker import check_data_readiness as _check_dr
            _dr_blocked = False
            _dr_block_reason: Optional[str] = None
            _dr_block_category: Optional[str] = None
            _dr_results: list = []
            _t0_dr = _exec_log_stage_start(exec_log, stage)

            for _sc in _sc_scenarios_for_readiness:
                _sc_id = _sc.get("scenario_id") or _sc.get("id", "unknown")
                _dr_precs = _sc.get("data_readiness_preconditions") or []
                if not _dr_precs:
                    continue
                _dr_res = _check_dr(
                    ticket_id=ticket_id,
                    scenario_id=_sc_id,
                    preconditions=_dr_precs,
                    exec_logger=exec_log,
                    evidence_dir=evidence_dir,
                    run_id=str(ticket_id),
                )
                _dr_results.append({
                    "scenario_id": _sc_id,
                    "decision": _dr_res.decision,
                    "category": _dr_res.category,
                    "reason": _dr_res.reason,
                    "all_ready": _dr_res.all_ready,
                    "artifact_path": _dr_res.artifact_path,
                })
                if _dr_res.decision == "BLOCKED" and not _dr_blocked:
                    _dr_blocked = True
                    _dr_block_reason = _dr_res.reason
                    _dr_block_category = _dr_res.category

            stages[stage] = {
                "ok": not _dr_blocked,
                "skipped": False,
                "results": _dr_results,
                "blocked_count": sum(1 for r in _dr_results if r["decision"] == "BLOCKED"),
            }
            _exec_log_stage_end(exec_log, stage, _t0_dr, ok=not _dr_blocked,
                                summary=stages[stage])

            if _dr_blocked:
                _dr_fail = {
                    "ok": False,
                    "verdict": "BLOCKED",
                    "category": _dr_block_category or "DATA",
                    "reason": _dr_block_reason or "DATA_READINESS_FAILED",
                    "error": (_dr_block_reason or "DATA_READINESS_FAILED").lower(),
                    "failed_stage": "data_readiness_check",
                    "message": (
                        f"Data readiness check BLOCKED: {_dr_block_reason}. "
                        "Test data is not available for one or more scenarios. "
                        "No Playwright tests will be run."
                    ),
                    "human_action_required": (
                        "Seed the required test data or update input_data in the scenario. "
                        "Check data_readiness.json for per-scenario details."
                    ),
                    "data_readiness_results": _dr_results,
                }
                if exec_log is not None:
                    try:
                        exec_log.pipeline_verdict(
                            verdict="BLOCKED",
                            category=_dr_block_category or "DATA",
                            reason=_dr_block_reason or "DATA_READINESS_FAILED",
                            failed_stage="data_readiness_check",
                            confidence=1.0,
                            evidence_refs=["data_readiness_check"],
                            human_action_required=_dr_fail["human_action_required"],
                        )
                        exec_log.session_end(_dr_fail)
                        exec_log.close()
                    except Exception:  # noqa: BLE001
                        pass
                return _build_output(ticket_id, stages, _dr_fail, started)
        except ImportError:
            logger.debug("uat_precondition_checker unavailable — skipping data readiness check")
            stages[stage] = {"ok": True, "skipped": True, "reason": "module_not_found"}
        except Exception as _dr_exc:  # noqa: BLE001
            logger.warning("data_readiness_check failed (non-fatal): %s", _dr_exc)
            stages[stage] = {"ok": True, "skipped": True, "reason": f"error:{_dr_exc}"}

    # ── Stage S8b-contract: data_contract_compiler (Sprint 8b) ──────────────
    # Compile a data contract for each scenario: extract what data is needed
    # BEFORE opening the browser.  Non-blocking — the contract is used by the
    # next stage (data_readiness_v2) and recorded as an evidence artifact.
    # Activates when compiled scenarios are available (compiler stage ran).
    stage = "data_contract_compile"
    _sc_scenarios_for_contract = (
        (compiler_result.get("scenarios") or [])
        if "compiler" not in skip_stages else []
    )
    _data_contracts: list = []  # list of DataContractResult objects
    if stage in skip_stages or not _sc_scenarios_for_contract:
        stages[stage] = {"ok": True, "skipped": True,
                         "reason": "no_compiled_scenarios"}
    else:
        try:
            from uat_data_contract_compiler import compile_all_contracts as _compile_contracts
            _t0_dcc = _exec_log_stage_start(exec_log, stage)
            _data_contracts = _compile_contracts(
                scenarios=_sc_scenarios_for_contract,
                ticket_id=ticket_id,
                exec_logger=exec_log,
                evidence_dir=evidence_dir,
                run_id=str(ticket_id),
            )
            _dcc_total = len(_data_contracts)
            _dcc_with_reqs = sum(1 for c in _data_contracts if c.requirements)
            _dcc_blocking = sum(len(c.blocking_requirements) for c in _data_contracts)
            stages[stage] = {
                "ok": True,
                "skipped": False,
                "contracts_compiled": _dcc_total,
                "contracts_with_requirements": _dcc_with_reqs,
                "total_blocking_requirements": _dcc_blocking,
            }
            _exec_log_stage_end(exec_log, stage, _t0_dcc, ok=True, summary=stages[stage])
            logger.info(
                "Sprint 8b: data contracts compiled: total=%d with_reqs=%d blocking=%d",
                _dcc_total, _dcc_with_reqs, _dcc_blocking,
            )
        except ImportError:
            logger.debug("uat_data_contract_compiler unavailable — skipping Sprint 8b stage")
            stages[stage] = {"ok": True, "skipped": True, "reason": "module_not_found"}
        except Exception as _dcc_exc:  # noqa: BLE001
            logger.warning("data_contract_compile failed (non-fatal): %s", _dcc_exc)
            stages[stage] = {"ok": True, "skipped": True, "reason": f"error:{_dcc_exc}"}

    # ── Stage S8b-readiness: data_readiness_v2 (Sprint 8b) ──────────────────
    # Check whether the data contracts compiled above are satisfiable.
    # If any BLOCKING requirement is MISSING, the stage records resolution_options
    # so the operator or Data Resolution Broker (Sprint 9) knows what to do next.
    #
    # Behaviour: NON-BLOCKING by default — the stage records missing requirements
    # as evidence but does NOT block the pipeline unless env var
    # QA_UAT_BLOCK_ON_MISSING_DATA_CONTRACT=true is set (operator opt-in).
    # This avoids false positives when DB is unavailable in CI environments.
    stage = "data_readiness_v2"
    _block_on_missing_contract = (
        os.environ.get("QA_UAT_BLOCK_ON_MISSING_DATA_CONTRACT", "false").lower() == "true"
    )
    if stage in skip_stages or not _data_contracts:
        stages[stage] = {"ok": True, "skipped": True,
                         "reason": "no_data_contracts"}
    else:
        try:
            from data_readiness_checker import check_readiness as _check_readiness_v2
            _t0_drv2 = _exec_log_stage_start(exec_log, stage)
            _drv2_results: list = []
            _drv2_missing_count = 0
            _drv2_blocking_missing_count = 0

            for _dc in _data_contracts:
                if not _dc.requirements:
                    continue
                _drv2_res = _check_readiness_v2(
                    contract=_dc,
                    exec_logger=exec_log,
                    evidence_dir=evidence_dir,
                    run_id=str(ticket_id),
                )
                _drv2_results.append({
                    "scenario_id": _drv2_res.scenario_id,
                    "ready": _drv2_res.ready,
                    "decision": _drv2_res.decision,
                    "blocking_missing_count": _drv2_res.blocking_missing_count,
                    "missing": [m.to_dict() for m in _drv2_res.missing],
                    "artifact_path": _drv2_res.artifact_path,
                })
                _drv2_missing_count += len(_drv2_res.missing)
                _drv2_blocking_missing_count += _drv2_res.blocking_missing_count

            stages[stage] = {
                "ok": True,
                "skipped": False,
                "scenarios_checked": len(_drv2_results),
                "missing_count": _drv2_missing_count,
                "blocking_missing_count": _drv2_blocking_missing_count,
                "results": _drv2_results,
            }
            _exec_log_stage_end(exec_log, stage, _t0_drv2, ok=True, summary=stages[stage])

            if _drv2_blocking_missing_count > 0:
                logger.warning(
                    "Sprint 8b: data_readiness_v2 found %d blocking missing requirement(s) "
                    "across %d scenario(s). Resolution options are in evidence artifacts.",
                    _drv2_blocking_missing_count, len(_drv2_results),
                )
                _exec_log_event(exec_log, "data_missing_resolution_required", {
                    "blocking_missing_count": _drv2_blocking_missing_count,
                    "scenarios": [
                        {"scenario_id": r["scenario_id"],
                         "missing": r["missing"]}
                        for r in _drv2_results if r["blocking_missing_count"] > 0
                    ],
                    "human_action": (
                        "Review data_readiness_v2_*.json in evidence directory. "
                        "For each missing requirement, choose from resolution_options: "
                        "ASK_USER_FOR_VALUE | RUN_DISCOVERY_QUERY | GENERATE_SQL_SEED | MARK_MANUAL_REVIEW"
                    ),
                })
                # Optionally block the pipeline (operator opt-in only)
                if _block_on_missing_contract:
                    _drv2_fail = {
                        "ok": False,
                        "verdict": "BLOCKED",
                        "category": "DATA",
                        "reason": "DATA_CONTRACT_MISSING_REQUIREMENTS",
                        "error": "data_contract_missing_requirements",
                        "failed_stage": "data_readiness_v2",
                        "message": (
                            f"Sprint 8b data readiness check: {_drv2_blocking_missing_count} "
                            "blocking requirement(s) cannot be satisfied. "
                            "Check data_readiness_v2_*.json for resolution options."
                        ),
                        "human_action_required": (
                            "Provide required data or generate a SQL seed proposal. "
                            "See resolution_options in data_readiness_v2_*.json artifacts."
                        ),
                        "data_readiness_v2_results": _drv2_results,
                    }
                    if exec_log is not None:
                        try:
                            exec_log.pipeline_verdict(
                                verdict="BLOCKED",
                                category="DATA",
                                reason="DATA_CONTRACT_MISSING_REQUIREMENTS",
                                failed_stage="data_readiness_v2",
                                confidence=1.0,
                                evidence_refs=["data_readiness_v2"],
                                human_action_required=_drv2_fail["human_action_required"],
                            )
                            exec_log.session_end(_drv2_fail)
                            exec_log.close()
                        except Exception:  # noqa: BLE001
                            pass
                    return _build_output(ticket_id, stages, _drv2_fail, started)
        except ImportError:
            logger.debug("data_readiness_checker unavailable — skipping Sprint 8b readiness check")
            stages[stage] = {"ok": True, "skipped": True, "reason": "module_not_found"}
        except Exception as _drv2_exc:  # noqa: BLE001
            logger.warning("data_readiness_v2 failed (non-fatal): %s", _drv2_exc)
            stages[stage] = {"ok": True, "skipped": True, "reason": f"error:{_drv2_exc}"}

    # ── Stage S9-broker: data_resolution_broker (Sprint 9) ──────────────────
    # If data_readiness_v2 found blocking missing requirements, invoke the
    # Data Resolution Broker to create structured decision requests for the
    # human operator.  This stage is always non-blocking (the pipeline
    # continues after creating the requests).  If QA_UAT_BLOCK_ON_MISSING_DATA_CONTRACT
    # is true and there are pending requests, the pipeline emits BLOCKED.
    stage = "data_resolution_broker"
    _drv2_stage_result = stages.get("data_readiness_v2", {})
    _drv2_blocking_count = _drv2_stage_result.get("blocking_missing_count", 0)
    if stage in skip_stages or _drv2_blocking_count == 0:
        stages[stage] = {"ok": True, "skipped": True,
                         "reason": "no_blocking_missing_requirements"}
    else:
        try:
            from data_resolution_broker import run as _broker_run
            _t0_broker = _exec_log_stage_start(exec_log, stage)
            _broker_results = []
            _drv2_results_for_broker = _drv2_stage_result.get("results", [])
            for _drv2_r in _drv2_results_for_broker:
                if _drv2_r.get("blocking_missing_count", 0) == 0:
                    continue
                _broker_res = _broker_run(
                    readiness_result=_drv2_r,
                    run_id=str(ticket_id),
                    exec_logger=exec_log,
                    evidence_dir=evidence_dir,
                )
                _broker_results.append({
                    "scenario_id": _broker_res.scenario_id,
                    "pending_request_ids": _broker_res.pending_request_ids,
                    "decisions_count": len(_broker_res.decisions),
                    "artifact_path": _broker_res.artifact_path,
                })
            stages[stage] = {
                "ok": True,
                "skipped": False,
                "scenarios_with_requests": len(_broker_results),
                "total_requests": sum(
                    len(r["pending_request_ids"]) for r in _broker_results
                ),
                "results": _broker_results,
            }
            _exec_log_stage_end(exec_log, stage, _t0_broker, ok=True, summary=stages[stage])
            logger.info(
                "Sprint 9: data_resolution_broker created %d pending request(s)",
                stages[stage]["total_requests"],
            )
            # If blocking and policy demands it, emit BLOCKED
            if _block_on_missing_contract and stages[stage]["total_requests"] > 0:
                _broker_fail = {
                    "ok": False,
                    "verdict": "BLOCKED",
                    "category": "DATA",
                    "reason": "USER_DATA_REQUIRED",
                    "error": "user_data_required",
                    "failed_stage": stage,
                    "message": (
                        f"Sprint 9: {stages[stage]['total_requests']} data request(s) created. "
                        "Operator must resolve before pipeline can continue."
                    ),
                    "human_action_required": (
                        "Review data_resolution_request_*.json in evidence directory. "
                        "Resolve each pending request via the UI or "
                        "POST /api/qa-uat/data-request/<request_id>/resolve"
                    ),
                    "data_resolution_results": _broker_results,
                }
                if exec_log is not None:
                    try:
                        exec_log.pipeline_verdict(
                            verdict="BLOCKED",
                            category="DATA",
                            reason="USER_DATA_REQUIRED",
                            failed_stage=stage,
                            confidence=1.0,
                            evidence_refs=["data_resolution_broker"],
                            human_action_required=_broker_fail["human_action_required"],
                        )
                        exec_log.session_end(_broker_fail)
                        exec_log.close()
                    except Exception:  # noqa: BLE001
                        pass
                return _build_output(ticket_id, stages, _broker_fail, started)
        except ImportError:
            logger.debug("data_resolution_broker unavailable — skipping Sprint 9 stage")
            stages[stage] = {"ok": True, "skipped": True, "reason": "module_not_found"}
        except Exception as _broker_exc:  # noqa: BLE001
            logger.warning("data_resolution_broker failed (non-fatal): %s", _broker_exc)
            stages[stage] = {"ok": True, "skipped": True, "reason": f"error:{_broker_exc}"}

    # ── Stage S10-seed-proposal: sql_seed_generator (Sprint 10) ─────────────
    # If the broker produced decisions that chose 'generate_sql_seed', invoke
    # sql_seed_generator + sql_safety_validator.
    #
    # Behaviour:
    #   - If safety FAILS → BLOCKED SEC SQL_SEED_SAFETY_FAILED.
    #   - If safety PASSES → emit sql_seed_proposal_generated and pause pipeline
    #     with SQL_SEED_APPROVAL_REQUIRED (blocking if opt-in, else warn only).
    #   - If no broker results chose generate_sql_seed → skip.
    stage = "sql_seed_proposal"
    _broker_stage = stages.get("data_resolution_broker", {})
    _broker_skipped = _broker_stage.get("skipped", True)
    # Check whether any decision chose generate_sql_seed
    _has_seed_decisions = False
    if not _broker_skipped:
        for _br in _broker_stage.get("results", []):
            if _br.get("decisions_count", 0) > 0:
                _has_seed_decisions = True
                break

    if stage in skip_stages or not _has_seed_decisions or not _data_contracts:
        stages[stage] = {"ok": True, "skipped": True,
                         "reason": "no_seed_decisions"}
    else:
        try:
            from sql_seed_generator import generate as _seed_generate
            _t0_seed = _exec_log_stage_start(exec_log, stage)
            _seed_results = []
            _seed_safety_failed = False
            for _dc in _data_contracts:
                if not _dc.requirements:
                    continue
                _seed_res = _seed_generate(
                    data_contract=_dc,
                    exec_logger=exec_log,
                    evidence_dir=evidence_dir,
                    run_id=str(ticket_id),
                )
                _seed_results.append({
                    "scenario_id": _seed_res.scenario_id,
                    "verdict": _seed_res.verdict,
                    "reason": _seed_res.reason,
                    "script_path": _seed_res.script_path,
                    "cleanup_path": _seed_res.cleanup_path,
                    "script_sha256": _seed_res.script_sha256,
                    "safety_safe": (
                        (_seed_res.safety_result or {}).get("safe", True)
                    ),
                })
                if _seed_res.verdict == "BLOCKED" and _seed_res.reason == "SQL_SEED_SAFETY_FAILED":
                    _seed_safety_failed = True
                    break

            stages[stage] = {
                "ok": not _seed_safety_failed,
                "skipped": False,
                "seed_results": _seed_results,
            }
            _exec_log_stage_end(exec_log, stage, _t0_seed, ok=not _seed_safety_failed,
                                summary=stages[stage])

            if _seed_safety_failed:
                _seed_fail = {
                    "ok": False,
                    "verdict": "BLOCKED",
                    "category": "SEC",
                    "reason": "SQL_SEED_SAFETY_FAILED",
                    "error": "sql_seed_safety_failed",
                    "failed_stage": stage,
                    "message": "SQL seed proposal failed safety validation. Review blocking_findings.",
                    "human_action_required": "Review sql_seed_safety_result events in execution.jsonl.",
                    "seed_results": _seed_results,
                }
                if exec_log is not None:
                    try:
                        exec_log.pipeline_verdict(
                            verdict="BLOCKED",
                            category="SEC",
                            reason="SQL_SEED_SAFETY_FAILED",
                            failed_stage=stage,
                            confidence=1.0,
                            evidence_refs=["sql_seed_safety_result"],
                            human_action_required=_seed_fail["human_action_required"],
                        )
                        exec_log.session_end(_seed_fail)
                        exec_log.close()
                    except Exception:  # noqa: BLE001
                        pass
                return _build_output(ticket_id, stages, _seed_fail, started)

            # Safety passed — pause and ask for approval
            generated_count = sum(
                1 for r in _seed_results if r["verdict"] == "GENERATED"
            )
            if generated_count > 0:
                logger.info(
                    "Sprint 10: sql_seed_proposal_generated for %d scenario(s). "
                    "Awaiting human approval.",
                    generated_count,
                )
                _exec_log_event(exec_log, "sql_seed_approval_required", {
                    "generated_count": generated_count,
                    "seed_results": _seed_results,
                    "human_action": (
                        "Review seed_proposal_*.sql in evidence directory. "
                        "Un-comment COMMIT TRANSACTION and obtain human approval before executing. "
                        "NEVER execute in production."
                    ),
                })
                if _block_on_missing_contract:
                    _approval_fail = {
                        "ok": False,
                        "verdict": "BLOCKED",
                        "category": "DATA",
                        "reason": "SQL_SEED_APPROVAL_REQUIRED",
                        "error": "sql_seed_approval_required",
                        "failed_stage": stage,
                        "message": (
                            f"Sprint 10: {generated_count} seed proposal(s) require human approval. "
                            "Review seed_proposal_*.sql in evidence directory."
                        ),
                        "human_action_required": (
                            "Review and approve seed scripts. "
                            "Un-comment COMMIT TRANSACTION after approval."
                        ),
                        "seed_results": _seed_results,
                    }
                    if exec_log is not None:
                        try:
                            exec_log.pipeline_verdict(
                                verdict="BLOCKED",
                                category="DATA",
                                reason="SQL_SEED_APPROVAL_REQUIRED",
                                failed_stage=stage,
                                confidence=1.0,
                                evidence_refs=["sql_seed_proposal_generated"],
                                human_action_required=_approval_fail["human_action_required"],
                            )
                            exec_log.session_end(_approval_fail)
                            exec_log.close()
                        except Exception:  # noqa: BLE001
                            pass
                    return _build_output(ticket_id, stages, _approval_fail, started)
        except ImportError:
            logger.debug("sql_seed_generator unavailable — skipping Sprint 10 stage")
            stages[stage] = {"ok": True, "skipped": True, "reason": "module_not_found"}
        except Exception as _seed_exc:  # noqa: BLE001
            logger.warning("sql_seed_proposal failed (non-fatal): %s", _seed_exc)
            stages[stage] = {"ok": True, "skipped": True, "reason": f"error:{_seed_exc}"}

    # ── Stage S12-catalog: catalog_readiness_checker (Sprint 12) ─────────────
    # Check that catalog tables required by the scenario have enough rows before
    # test generation begins. Empty catalogs cause silent NAV timeouts rather
    # than explicit errors. This stage is non-blocking: empty catalogs produce
    # a CATALOG_EMPTY event and a seed proposal, but do not stop the pipeline.
    stage = "catalog_readiness"
    try:
        from catalog_readiness_checker import (  # type: ignore[import]
            check_catalog_readiness,
        )

        # Infer required catalogs from compiler_result (from stage 3)
        _required_catalogs: list[str] = []
        if isinstance(compiler_result, dict):
            for _sc in compiler_result.get("scenarios", []):
                _required_catalogs.extend(_sc.get("required_catalogs", []))
        elif hasattr(compiler_result, "scenarios"):
            for _sc in compiler_result.scenarios:
                _cats = getattr(_sc, "required_catalogs", [])
                _required_catalogs.extend(_cats if _cats else [])

        # Remove duplicates while preserving order
        _seen: set[str] = set()
        _unique_catalogs: list[str] = []
        for _c in _required_catalogs:
            if _c not in _seen:
                _seen.add(_c)
                _unique_catalogs.append(_c)

        if not _unique_catalogs:
            stages[stage] = {"ok": True, "skipped": True, "reason": "no_catalogs_required"}
        else:
            _fixtures_path = Path(__file__).parent / "fixtures" / "catalog_fixtures.yml"
            _cat_result = check_catalog_readiness(
                scenario_id=str(ticket_id),
                required_catalogs=_unique_catalogs,
                db_url=None,  # read-only; env var for write not used here
                exec_logger=exec_log,
                evidence_dir=evidence_dir,
                run_id=str(ticket_id),
                ticket_id=ticket_id,
                fixtures_path=_fixtures_path,
                dry_run=True,  # always dry-run in pipeline
            )
            stages[stage] = {
                "ok": _cat_result.ok,
                "skipped": False,
                "total": _cat_result.total,
                "ok_count": _cat_result.ok_count,
                "empty_count": _cat_result.empty_count,
                "unverified_count": _cat_result.unverified_count,
                "blocking_empty_count": _cat_result.blocking_empty_count,
                "seed_proposed_count": _cat_result.seed_proposed_count,
            }
            if not _cat_result.ok:
                _exec_log_event(exec_log, "catalog_readiness_warning", {
                    "blocking_empty_count": _cat_result.blocking_empty_count,
                    "empty_catalogs": [
                        r["catalog_name"] for r in _cat_result.to_dict()["catalog_results"]
                        if r["status"] in ("EMPTY", "SEED_REQUIRED")
                    ],
                })
    except ImportError:
        logger.debug("catalog_readiness_checker unavailable — skipping Sprint 12 stage")
        stages[stage] = {"ok": True, "skipped": True, "reason": "module_not_found"}
    except Exception as _cat_exc:  # noqa: BLE001
        logger.warning("catalog_readiness stage failed (non-fatal): %s", _cat_exc)
        stages[stage] = {"ok": True, "skipped": True, "reason": f"error:{_cat_exc}"}

    # ── Stage S11-cleanup: cleanup_manager (Sprint 11) ────────────────────────    # After a seed was applied (verdict=APPLIED via seed_executor), check if
    # cleanup_policy=after_run so we auto-clean seeded rows before the run ends.
    # This stage is non-blocking: if cleanup fails, it is logged but does not
    # fail the whole pipeline — evidence is written regardless.
    stage = "seed_cleanup"
    try:
        from cleanup_manager import cleanup as _cleanup, check_cleanup_policy  # type: ignore[import]

        # Find all seed_execution_result artifacts in this run
        _cleanup_count = 0
        _cleanup_results = []
        _run_dir = evidence_dir / str(ticket_id)
        for _exec_artifact in sorted(_run_dir.glob("seed_execution_result_*.json")) if _run_dir.is_dir() else []:
            try:
                import json as _json
                _exec_data = _json.loads(_exec_artifact.read_text(encoding="utf-8"))
                _scenario_id_c = _exec_data.get("scenario_id", "unknown")
                _seed_run_id_c = _exec_data.get("seed_run_id", "")
                _script_path_c = _exec_data.get("script_path") or ""
                # Only auto-cleanup if seed was actually APPLIED
                if _exec_data.get("verdict") != "APPLIED":
                    continue
                # Determine cleanup policy from config
                _cleanup_policy_c = "after_run"  # default from policy
                _cleanup_script_path_c = str(_exec_artifact).replace(
                    "seed_execution_result_", "cleanup_proposal_"
                ).replace(".json", ".sql")
                if not __import__("os").path.exists(_cleanup_script_path_c):
                    logger.debug("S11-cleanup: no cleanup script for %s — skipping", _scenario_id_c)
                    continue
                if not check_cleanup_policy(_cleanup_policy_c):
                    logger.info("S11-cleanup: policy=%s skips auto-cleanup for %s", _cleanup_policy_c, _scenario_id_c)
                    continue
                _cr = _cleanup(
                    cleanup_script_path=_cleanup_script_path_c,
                    seed_run_id=_seed_run_id_c,
                    scenario_id=_scenario_id_c,
                    run_id=str(ticket_id),
                    ticket_id=ticket_id,
                    cleanup_policy=_cleanup_policy_c,
                    exec_logger=exec_log,
                    evidence_dir=evidence_dir,
                    dry_run=True,  # always dry_run in pipeline; real cleanup triggered by operator
                )
                _cleanup_results.append(_cr.to_dict())
                _cleanup_count += 1
            except Exception as _ce:
                logger.warning("S11-cleanup: error processing %s: %s", _exec_artifact.name, _ce)

        stages[stage] = {
            "ok": True,
            "skipped": _cleanup_count == 0,
            "reason": "no_applied_seeds" if _cleanup_count == 0 else None,
            "cleanup_count": _cleanup_count,
        }
        if _cleanup_count > 0:
            _exec_log_event(exec_log, "seed_cleanup_summary", {
                "cleanup_count": _cleanup_count,
                "results": _cleanup_results,
            })
    except ImportError:
        logger.debug("cleanup_manager unavailable — skipping Sprint 11 stage")
        stages[stage] = {"ok": True, "skipped": True, "reason": "module_not_found"}
    except Exception as _cleanup_exc:  # noqa: BLE001
        logger.warning("seed_cleanup stage failed (non-fatal): %s", _cleanup_exc)
        stages[stage] = {"ok": True, "skipped": True, "reason": f"error:{_cleanup_exc}"}

    # ── Stage 4: generator ───────────────────────────────────────────────────
    stage = "generator"
    tests_dir = evidence_dir / "tests"
    if stage in skip_stages:
        stages[stage] = {"ok": True, "skipped": True}
        _persist_json(evidence_dir / "scenarios.json", compiler_result)
    else:
        # Fase 4 — apply approved learnings before generating specs so that
        # human-reviewed selector fixes take effect without manual cache edits.
        _session_id = str(ticket_id)
        try:
            from learning_store import apply_approved_learnings_to_selectors
            _learn_result = apply_approved_learnings_to_selectors(
                ticket_id=ticket_id,
                run_id=_session_id,
            )
            if _learn_result.get("applied_count", 0) > 0:
                _exec_log_event(exec_log, "approved_learnings_applied", _learn_result)
        except Exception as _learn_exc:  # noqa: BLE001
            logger.debug("apply_approved_learnings skipped: %s", _learn_exc)

        from playwright_test_generator import run as generator_run
        _log_stage(stage)
        _t0 = _exec_log_stage_start(exec_log, stage)
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
        _exec_log_stage_end(exec_log, stage, _t0, ok=generator_result.get("ok", False),
                            summary={"generated": generator_result.get("generated", 0),
                                     "blocked": generator_result.get("blocked", 0)})
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

    # ── Stage 4b: spec_linter ────────────────────────────────────────────────
    # Lint every generated .spec.ts BEFORE opening a browser.
    # If any spec contains login logic, block immediately.
    stage = "spec_linter"
    if stage not in skip_stages and "generator" not in skip_stages:
        try:
            from spec_linter import lint_directory as _lint_directory
            _log_stage(stage)
            lint_result = _lint_directory(tests_dir)
            stages[stage] = {
                "ok": lint_result.get("ok"),
                "skipped": False,
                "checked": lint_result.get("checked", 0),
                "violations": lint_result.get("violations", []),
            }
            if not lint_result.get("ok"):
                logger.error("Spec linter BLOCKED: %s violations found", len(lint_result.get("violations", [])))
                return _build_output(ticket_id, stages, {
                    **lint_result,
                    "ticket_id": ticket_id,
                    "stage": stage,
                }, started)
        except ImportError:
            stages[stage] = {"ok": True, "skipped": True, "reason": "spec_linter_not_found"}
        except Exception as _lint_exc:
            logger.warning("Spec linter failed (non-fatal): %s", _lint_exc)
            stages[stage] = {"ok": True, "skipped": True, "reason": f"linter_error: {_lint_exc}"}
    else:
        stages[stage] = {"ok": True, "skipped": True}

    # ── Stage S8-budget: budget_check (Sprint 8) ────────────────────────────
    # Estimate run cost and check against monthly budget BEFORE opening any browser.
    # "block" from budget_enforcer blocks lane full-uat/nightly-regression.
    # "warn" is logged but pipeline continues.
    # "preflight" and "compile-only" lanes are always allowed.
    _lane = os.environ.get("QA_UAT_LANE", "full-uat")
    _scenario_count_for_budget = stages.get("compiler", {}).get("scenario_count", 0)
    try:
        from budget_enforcer import check_budget as _check_budget
        _budget_result = _check_budget(
            lane=_lane,
            ticket_id=ticket_id if isinstance(ticket_id, int) else 0,
            scenario_count=_scenario_count_for_budget,
            exec_logger=exec_log,
        )
        if _budget_result.decision == "block":
            _budget_blocked = {
                "ok": False,
                "verdict": "BLOCKED",
                "category": "OPS",
                "reason": "BUDGET_EXCEEDED",
                "error": "budget_block",
                "message": (
                    f"Budget enforcement blocked run: lane={_lane} "
                    f"used={_budget_result.used_usd:.2f}/{_budget_result.budget_total_usd:.2f} USD. "
                    f"{_budget_result.reason}"
                ),
                "budget_check": {
                    "lane": _lane,
                    "decision": _budget_result.decision,
                    "reason": _budget_result.reason,
                    "used_usd": _budget_result.used_usd,
                    "budget_total_usd": _budget_result.budget_total_usd,
                },
                "human_action_required": (
                    "Review budget usage at /api/qa-uat/dashboard and wait until next period, "
                    "or increase QA_UAT_BUDGET_MONTHLY_USD."
                ),
                "ticket_id": ticket_id,
                "stages": stages,
                "elapsed_s": round(time.time() - started, 2),
            }
            if exec_log is not None:
                try:
                    exec_log.pipeline_verdict(
                        verdict="BLOCKED",
                        category="OPS",
                        reason="BUDGET_EXCEEDED",
                        failed_stage="budget_check",
                        confidence=1.0,
                        evidence_refs=["budget_check"],
                        human_action_required=_budget_blocked["human_action_required"],
                    )
                    exec_log.session_end(_budget_blocked)
                    exec_log.close()
                except Exception:  # noqa: BLE001
                    pass
            return _budget_blocked
        elif _budget_result.decision == "warn":
            logger.warning(
                "budget_check WARN: lane=%s used=%.2f/%.2f USD reason=%s",
                _lane, _budget_result.used_usd, _budget_result.budget_total_usd,
                _budget_result.reason,
            )
    except ImportError:
        logger.debug("budget_enforcer module unavailable — skipping Sprint 8 budget check")
    except Exception as _budget_exc:  # noqa: BLE001
        logger.warning("budget_check failed (non-fatal): %s", _budget_exc)

    # ── Stage S8-prio: test_prioritizer (Sprint 8) ──────────────────────────
    # Order compiled scenarios by priority score before sending to the runner.
    # Only effective when compiled scenarios are available (compiler ran).
    # Does NOT block — exclusions by time budget are logged but pipeline continues.
    try:
        from test_prioritizer import prioritize_scenarios as _prioritize
        _raw_scenarios: list = []
        _scenarios_file = evidence_dir / "scenarios.json"
        if _scenarios_file.is_file():
            _sc_data = json.loads(_scenarios_file.read_text(encoding="utf-8"))
            _raw_scenarios = _sc_data.get("scenarios", [])
        if _raw_scenarios:
            _time_budget_s = int(os.environ.get("QA_UAT_SCENARIO_TIME_BUDGET_S", "720"))
            _changed_screens_str = os.environ.get("QA_UAT_CHANGED_SCREENS", "")
            _changed_screens = [s.strip() for s in _changed_screens_str.split(",") if s.strip()]
            _prio_result = _prioritize(
                scenarios=_raw_scenarios,
                changed_screens=_changed_screens or None,
                time_budget_seconds=_time_budget_s,
                exec_logger=exec_log,
            )
            if _prio_result.selected:
                # Rewrite scenarios.json with prioritized order
                import copy as _copy2
                _sc_reordered = _copy2.deepcopy(_sc_data)
                _sc_reordered["scenarios"] = [
                    ps.original_scenario for ps in _prio_result.selected
                ]
                _sc_reordered["prioritization"] = {
                    "total_candidates": len(_raw_scenarios),
                    "selected": len(_prio_result.selected),
                    "excluded": len(_prio_result.excluded),
                    "time_budget_seconds": _prio_result.time_budget_seconds,
                    "estimated_total_seconds": _prio_result.estimated_total_seconds,
                }
                _persist_json(_scenarios_file, _sc_reordered)
                logger.info(
                    "test_prioritizer: reordered %d scenarios (excluded %d beyond time budget %ds)",
                    len(_prio_result.selected), len(_prio_result.excluded), _time_budget_s,
                )
    except ImportError:
        logger.debug("test_prioritizer module unavailable — skipping Sprint 8 prioritization")
    except Exception as _prio_exc:  # noqa: BLE001
        logger.warning("test_prioritizer failed (non-fatal): %s", _prio_exc)

    # ── Stage S13-oracle: oracle_engine + weak_assertion_detector (Sprint 13) ─
    # Evaluate oracle contracts and detect weak assertions in generated spec files.
    # Non-blocking: weak assertions lower confidence but do not stop the pipeline.
    # P0 scenarios without any oracle set human_action_required flag.
    stage = "oracle_evaluation"
    try:
        from oracle_engine import evaluate as _oracle_evaluate  # type: ignore[import]
        from weak_assertion_detector import detect as _weak_detect  # type: ignore[import]

        _scenarios_path_o = evidence_dir / "scenarios.json"
        _runner_output_path_o = evidence_dir / "runner_output.json"
        _oracle_contracts_dir_o = evidence_dir / "oracle_contracts"
        _fixtures_path_o = Path(__file__).parent / "fixtures" / "catalog_fixtures.yml"

        # Collect generated spec files for weak assertion analysis
        _spec_files_o = sorted(tests_dir.glob("**/*.spec.ts")) if tests_dir.is_dir() else []
        _spec_files_o += sorted(tests_dir.glob("**/*.spec.js")) if tests_dir.is_dir() else []

        _oracle_result = _oracle_evaluate(
            scenarios_path=_scenarios_path_o if _scenarios_path_o.exists() else None,
            runner_output_path=_runner_output_path_o if _runner_output_path_o.exists() else None,
            oracle_contracts_dir=_oracle_contracts_dir_o if _oracle_contracts_dir_o.is_dir() else None,
            exec_logger=exec_log,
            evidence_dir=evidence_dir,
            run_id=str(ticket_id),
            ticket_id=ticket_id,
            fixtures_path=_fixtures_path_o if _fixtures_path_o.exists() else None,
        )

        _weak_report = _weak_detect(
            spec_files=_spec_files_o,
            exec_logger=exec_log,
            evidence_dir=evidence_dir,
            run_id=str(ticket_id),
            ticket_id=ticket_id,
            block_on_no_strong=False,  # non-blocking in pipeline — emit warning only
        )

        stages[stage] = {
            "ok": True,
            "skipped": False,
            "oracle_publish_blocked": _oracle_result.publish_blocked,
            "p0_blocked_count": _oracle_result.p0_blocked_count,
            "no_oracle_count": _oracle_result.no_oracle_count,
            "weak_only_count": _oracle_result.weak_only_count,
            "oracle_fail_count": _oracle_result.fail_count,
            "weak_files": _weak_report.files_analyzed,
            "weak_tests": _weak_report.weak_tests,
            "no_assertion_tests": _weak_report.no_assertion_tests,
            "strong_tests": _weak_report.strong_tests,
        }

        if _oracle_result.publish_blocked:
            _exec_log_event(exec_log, "oracle_weak_warning", {
                "p0_blocked_count": _oracle_result.p0_blocked_count,
                "no_oracle_count": _oracle_result.no_oracle_count,
                "human_action_required": True,
            })

    except ImportError:
        logger.debug("oracle_engine or weak_assertion_detector unavailable — skipping Sprint 13 stage")
        stages[stage] = {"ok": True, "skipped": True, "reason": "module_not_found"}
    except Exception as _oracle_exc:  # noqa: BLE001
        logger.warning("oracle_evaluation stage failed (non-fatal): %s", _oracle_exc)
        stages[stage] = {"ok": True, "skipped": True, "reason": f"error:{_oracle_exc}"}

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
        # Deadline check — do not open browser if we are already over time
        if _dl := _check_deadline(stage):
            return _dl

        from uat_test_runner import run as runner_run
        _log_stage(stage)
        _t0 = _exec_log_stage_start(exec_log, stage, {"tests_dir": str(tests_dir)})
        runner_result = runner_run(
            tests_dir=tests_dir,
            evidence_out=evidence_dir,
            headed=headed,
            timeout_ms=timeout_ms,
            verbose=verbose,
        )
        stages[stage] = _summarise_runner(runner_result)
        _exec_log_stage_end(exec_log, stage, _t0, ok=runner_result.get("ok", False),
                            summary={
                                "pass": runner_result.get("pass", 0),
                                "fail": runner_result.get("fail", 0),
                                "blocked": runner_result.get("blocked", 0),
                                "total": runner_result.get("total", 0),
                                # Sprint 5 — classification in stage summary
                                "verdict":  runner_result.get("verdict"),
                                "category": runner_result.get("category"),
                                "reason":   runner_result.get("reason"),
                            })
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

    # ── Stage 6-triage: failure_triage (Sprint 6 — post-runner) ────────────
    # Runs for all non-PASS verdicts. PASS runs get a lightweight triage confirming
    # the verdict. Non-fatal — a triage failure never blocks downstream stages.
    _triage_result: Optional[dict] = None
    try:
        from failure_triage import run_failure_triage as _run_triage
        _runner_verdict = runner_result.get("verdict", "")
        _runner_classification = runner_result.get("runner_summary")
        # Build execution_log list from JSONL file (if available)
        _exec_log_events: list = []
        _exec_log_path = evidence_dir / "execution.jsonl"
        if _exec_log_path.is_file():
            try:
                for _line in _exec_log_path.read_text(encoding="utf-8").splitlines():
                    _line = _line.strip()
                    if _line:
                        try:
                            import json as _json_inner
                            _exec_log_events.append(_json_inner.loads(_line))
                        except Exception:
                            pass
            except Exception:
                pass
        _triage = _run_triage(
            ticket_id=ticket_id if isinstance(ticket_id, int) else 0,
            run_id=str(ticket_id),
            result_json=runner_result,
            execution_log=_exec_log_events,
            runner_classification=_runner_classification,
            exec_logger=exec_log,
            evidence_dir=str(evidence_dir),
        )
        _triage_result = _triage.to_dict()
        stages["triage"] = {
            "ok": True,
            "skipped": False,
            "verdict": _triage.verdict,
            "category": _triage.category,
            "reason": _triage.reason,
            "confidence": _triage.confidence,
            "owner": _triage.owner,
            "human_approval_required": _triage.human_approval_required,
            "artifact_path": _triage.artifact_path,
        }
        # Sprint 6 — selector_healing_advisor for NAV/GEN BLOCKED runs
        if _triage.verdict == "BLOCKED" and _triage.category in ("NAV", "GEN"):
            try:
                from selector_healing_advisor import suggest_selector_healing as _suggest_healing
                from selector_healing_advisor import emit_healing_suggestion as _emit_healing
                # Find the screen from triage evidence or ticket result
                _heal_screen = (
                    _extract_screen_from_ticket(ticket_result) or "unknown_screen"
                )
                # Find missing alias from runner_result or triage
                _missing_alias = runner_result.get("reason", _triage.reason or "unknown_alias")
                _ui_map_file = str(evidence_dir.parent / "cache" / "ui_maps" / f"{_heal_screen}.json")
                _heal = _suggest_healing(
                    screen=_heal_screen,
                    missing_alias=_missing_alias,
                    ui_map_path=_ui_map_file,
                    execution_log=_exec_log_events,
                )
                if exec_log is not None:
                    _emit_healing(exec_log, _heal)
                stages["triage"]["healing_suggestion"] = {
                    "candidate_alias": _heal.candidate_alias,
                    "confidence": _heal.confidence,
                    "status": _heal.status,  # always "suggested"
                    "requires_human_approval": _heal.requires_human_approval,  # always True
                }
            except ImportError:
                pass
            except Exception as _heal_exc:
                logger.debug("selector_healing_advisor failed (non-fatal): %s", _heal_exc)

        # Sprint 6 — when triage confidence >= 0.85, prefer triage verdict over runner
        if _triage.confidence >= 0.85 and _triage.verdict != runner_result.get("verdict"):
            logger.info(
                "Sprint 6: triage overrides runner verdict %s→%s (confidence=%.2f)",
                runner_result.get("verdict"), _triage.verdict, _triage.confidence,
            )
            runner_result = {
                **runner_result,
                "verdict": _triage.verdict,
                "category": _triage.category,
                "reason": _triage.reason,
                "_triage_override": True,
            }

    except ImportError:
        logger.debug("failure_triage module unavailable — skipping Sprint 6 triage stage")
        stages["triage"] = {"ok": True, "skipped": True, "reason": "module_unavailable"}
    except Exception as _triage_exc:
        logger.warning("failure_triage stage failed (non-fatal): %s", _triage_exc)
        stages["triage"] = {"ok": True, "skipped": True, "reason": f"triage_error: {_triage_exc}"}

    # ── Stage 7.1: quarantine_check (Sprint 7 — post-triage) ────────────────
    # Verify if any scenario in the runner result is actively quarantined.
    # Quarantined scenarios are skipped from gate decisions.
    # Expired quarantines fail the gate (not renewed automatically).
    _quarantine_flags: dict[str, bool] = {}  # scenario_id -> is_quarantined
    try:
        from quarantine_registry import get_registry as _get_qr
        _qr = _get_qr()
        _qr.expire_old_quarantines()  # force expiry sweep before check
        _runner_scenarios = (
            (runner_result.get("runner_summary") or {}).get("scenario_results") or []
        )
        _quarantine_checked: list[dict] = []
        for _sc_res in _runner_scenarios:
            _sc_id = _sc_res.get("scenario_id") or _sc_res.get("id") or ""
            _is_q = _qr.is_quarantined(_sc_id) if _sc_id else False
            _quarantine_flags[_sc_id] = _is_q
            _quarantine_checked.append({
                "scenario_id": _sc_id,
                "quarantined": _is_q,
            })
        stages["quarantine_check"] = {
            "ok": True,
            "skipped": not bool(_runner_scenarios),
            "checked_count": len(_quarantine_checked),
            "quarantined_count": sum(1 for c in _quarantine_checked if c["quarantined"]),
            "results": _quarantine_checked,
        }
        _exec_log_event(exec_log, "quarantine_check_complete", {
            "ticket_id": ticket_id,
            "checked_count": len(_quarantine_checked),
            "quarantined_count": stages["quarantine_check"]["quarantined_count"],
        })
    except ImportError:
        logger.debug("quarantine_registry unavailable — skipping Sprint 7 quarantine_check")
        stages["quarantine_check"] = {"ok": True, "skipped": True, "reason": "module_unavailable"}
    except Exception as _qr_exc:
        logger.warning("quarantine_check failed (non-fatal): %s", _qr_exc)
        stages["quarantine_check"] = {"ok": True, "skipped": True, "reason": f"error:{_qr_exc}"}

    # ── Stage 7.2: run_metrics_summary (Sprint 7 — post-quarantine) ──────────
    # Collect sprint-7 metrics from the execution.jsonl events, persist to
    # run_metrics.jsonl, and emit run_metrics_summary event.
    try:
        from metrics_collector import (
            collect_run_metrics as _collect_sprint7_metrics,
            build_run_metrics_summary_event as _build_metrics_event,
            persist_run_metrics as _persist_run_metrics,
        )
        # Load execution events so far (flush exec_log if needed)
        _exec_events_for_metrics: list[dict] = []
        _exec_log_path_for_metrics = evidence_dir / "execution.jsonl"
        if _exec_log_path_for_metrics.is_file():
            try:
                for _line in _exec_log_path_for_metrics.read_text(encoding="utf-8").splitlines():
                    _line = _line.strip()
                    if _line:
                        try:
                            _exec_events_for_metrics.append(json.loads(_line))
                        except Exception:
                            pass
            except Exception:
                pass
        _lane_name = os.environ.get("QA_UAT_LANE")
        _sprint7_metrics = _collect_sprint7_metrics(
            execution_log=_exec_events_for_metrics,
            run_id=str(ticket_id),
            ticket_id=ticket_id,
            lane=_lane_name,
        )
        _persist_run_metrics(_sprint7_metrics)
        _metrics_event = _build_metrics_event(_sprint7_metrics)
        _exec_log_event(exec_log, "run_metrics_summary", {
            k: v for k, v in _metrics_event.items() if k != "event"
        })
        stages["run_metrics_summary"] = {
            "ok": True,
            "skipped": False,
            "unknown_count": _sprint7_metrics.signal.unknown_verdict_count,
            "lane": _lane_name,
        }
    except ImportError:
        logger.debug("metrics_collector (sprint 7) unavailable — skipping run_metrics_summary")
        stages["run_metrics_summary"] = {"ok": True, "skipped": True, "reason": "module_unavailable"}
    except Exception as _ms_exc:
        logger.warning("run_metrics_summary failed (non-fatal): %s", _ms_exc)
        stages["run_metrics_summary"] = {"ok": True, "skipped": True, "reason": f"error:{_ms_exc}"}

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

    # ── Stage S14-confidence: test_confidence_scorer + data_lineage_builder (Sprint 14) ──
    # Score each scenario based on evidence quality (oracle, seed, cleanup, assertions, etc.).
    # Non-blocking by default: low confidence emits a warning and sets human_action_required
    # but does not stop the pipeline. Gate is enforced at publish time.
    # Also builds data_lineage.json tracing all test data back to its origin.
    stage = "test_confidence"
    try:
        from test_confidence_scorer import score_all as _score_all  # type: ignore[import]
        from data_lineage_builder import build as _lineage_build      # type: ignore[import]

        # Load scenarios list
        _scenarios_conf: list[dict] = []
        _scenarios_file_conf = evidence_dir / "scenarios.json"
        if _scenarios_file_conf.is_file():
            try:
                _sc_raw = json.loads(_scenarios_file_conf.read_text(encoding="utf-8"))
                _scenarios_conf = _sc_raw.get("scenarios", []) if isinstance(_sc_raw, dict) else _sc_raw
            except Exception:
                pass

        # Deployment fingerprint result from earlier stage
        _fingerprint_matched: bool | None = None
        _fp_stage = stages.get("deployment_fingerprint_check", {})
        if not _fp_stage.get("skipped"):
            _fingerprint_matched = _fp_stage.get("matched")

        _conf_result = _score_all(
            scenarios=_scenarios_conf,
            evidence_dir=evidence_dir,
            run_id=str(ticket_id),
            ticket_id=ticket_id,
            deployment_matched=_fingerprint_matched,
            min_confidence=60,  # configurable gate threshold
            exec_logger=exec_log,
        )

        _lineage_result = _lineage_build(
            evidence_dir=evidence_dir,
            run_id=str(ticket_id),
            ticket_id=ticket_id,
            exec_logger=exec_log,
        )

        stages[stage] = {
            "ok": True,           # non-blocking in pipeline; gate at publish
            "skipped": False,
            "total_scenarios": _conf_result.total_scenarios,
            "high_count": _conf_result.high_count,
            "medium_count": _conf_result.medium_count,
            "low_count": _conf_result.low_count,
            "blocked_count": _conf_result.blocked_count,
            "publish_blocked": _conf_result.publish_blocked,
            "lineage_entries": _lineage_result.total_entries,
            "lineage_seeded": _lineage_result.seeded_count,
        }

        if _conf_result.publish_blocked:
            _exec_log_event(exec_log, "confidence_gate_warning", {
                "blocked_count": _conf_result.blocked_count,
                "min_confidence": _conf_result.min_confidence,
                "human_action_required": True,
            })

    except ImportError:
        logger.debug("test_confidence_scorer or data_lineage_builder unavailable — skipping Sprint 14 stage")
        stages[stage] = {"ok": True, "skipped": True, "reason": "module_not_found"}
    except Exception as _conf_exc:  # noqa: BLE001
        logger.warning("test_confidence stage failed (non-fatal): %s", _conf_exc)
        stages[stage] = {"ok": True, "skipped": True, "reason": f"error:{_conf_exc}"}

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
        _t0 = _exec_log_stage_start(exec_log, stage)
        evaluations_result = evaluator_run(
            scenarios_path=evidence_dir / "scenarios.json",
            runner_output_path=evidence_dir / "runner_output.json",
            verbose=verbose,
        )
        stages[stage] = _summarise_evaluator(evaluations_result)
        _exec_log_stage_end(exec_log, stage, _t0, ok=evaluations_result.get("ok", False))
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
        _t0 = _exec_log_stage_start(exec_log, stage)
        analyzer_result = analyzer_run(
            evaluations_path=evidence_dir / "evaluations.json",
            runner_output_path=evidence_dir / "runner_output.json",
            verbose=verbose,
        )
        stages[stage] = _summarise_failure_analyzer(analyzer_result)
        _exec_log_stage_end(exec_log, stage, _t0, ok=analyzer_result.get("ok", False))
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

    FORENSIC-20260508 | FIX-1 | Also scans analisis_tecnico for screen names.
    Tickets whose plan items don't mention screen names explicitly (e.g.
    MantenedorDirecciones → FrmDetalleClie) previously fell back to
    FrmAgenda.aspx, causing the compiler to build the wrong UI map and
    silently drop all LLM-generated scenarios (scope_screen mismatch).
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

    # FORENSIC-20260508 | FIX-1 | Also scan analisis_tecnico — the technical
    # analysis often names the target screen explicitly (e.g. "FrmDetalleClie.aspx")
    # even when plan item texts don't. This is the most reliable signal for
    # tickets about child screens (MantenedorDirecciones, FrmGestion, etc.).
    analisis = ticket_result.get("analisis_tecnico") or ""
    if analisis:
        lower_analisis = analisis.lower()
        for screen in SUPPORTED_SCREENS:
            if screen.lower() in lower_analisis:
                found.add(screen)

    # Also scan the ticket description itself
    # FASE1/GEN/FIX-1: Fixed operator precedence bug — previously only ticket.description
    # was concatenated when it was non-empty (description_md was silently dropped).
    desc_text = (
        ((ticket_result.get("ticket") or {}).get("description") or "")
        + " "
        + (ticket_result.get("description_md") or "")
    ).lower()
    for screen in SUPPORTED_SCREENS:
        if screen.lower() in desc_text:
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
    # P0/PIP/OBS: always propagate verdict/category/reason/failed_stage so
    # session_end never has null verdict and log_analyzer never produces UNKNOWN.
    verdict  = failed_result.get("verdict", "BLOCKED")
    category = failed_result.get("category", "PIP")
    reason   = failed_result.get("reason") or failed_result.get("error", "pipeline_error")
    failed_stage = (
        failed_result.get("failed_stage")
        or failed_result.get("stage")
        or "unknown"
    )
    human_action = failed_result.get("human_action_required")

    # P0/OBS — emit pipeline_verdict_decision for every failed exit (roadmap Cambio 1.3).
    # Uses get_active_logger() so callers don't need to thread the log object through.
    _active_log = _get_active_exec_logger()
    if _active_log is not None:
        try:
            _active_log.pipeline_verdict(
                verdict=verdict,
                category=category,
                reason=reason,
                failed_stage=failed_stage,
                confidence=failed_result.get("confidence", 1.0),
                evidence_refs=failed_result.get("evidence_refs", []),
                human_action_required=human_action,
            )
        except Exception:  # noqa: BLE001
            pass

    output = {
        "ok": False,
        "ticket_id": ticket_id,
        "verdict": verdict,
        "category": category,
        "reason": reason,
        "failed_stage": failed_stage,
        "stage": failed_stage,
        "error": failed_result.get("error", "pipeline_error"),
        "message": failed_result.get("message", ""),
        "stages": stages,
        "elapsed_s": round(time.time() - started, 2),
    }
    if human_action:
        output["human_action_required"] = human_action
    return output


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
        # FORENSIC-20260508 | FIX-4 | The compiler output contract has 'compiled' (int)
        # and 'out_of_scope_items' (list). The old code filtered r['scenarios'] for
        # items with out_of_scope=True — but compiled scenarios never have that flag.
        # Out-of-scope items live in r['out_of_scope_items']. This always produced
        # out_of_scope_count=0 in the pipeline summary.
        base["scenario_count"] = r.get("compiled", len(r.get("scenarios") or []))
        base["out_of_scope_count"] = r.get("out_of_scope", len(r.get("out_of_scope_items") or []))
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


def _extract_screen_from_ticket(ticket_result: dict) -> Optional[str]:
    """Extract the first .aspx screen name from a ticket result dict (Sprint 6 helper)."""
    try:
        nav_path = ticket_result.get("navigation_path") or []
        for item in nav_path:
            if isinstance(item, str) and item.endswith(".aspx"):
                return item
            if isinstance(item, dict):
                s = item.get("screen") or item.get("url") or ""
                if s.endswith(".aspx"):
                    return s
        # Fallback: search all string values
        for val in str(ticket_result).split():
            if val.endswith(".aspx"):
                return val.strip("\"'[](){},")
    except Exception:
        pass
    return None


def _summarise_runner(r: dict) -> dict:
    base = {"ok": r.get("ok", False), "skipped": False}
    if r.get("ok"):
        base["pass"] = r.get("pass", r.get("pass_count", 0))
        base["fail"] = r.get("fail", r.get("fail_count", 0))
        base["blocked"] = r.get("blocked", r.get("blocked_count", 0))
        base["total"] = r.get("total", r.get("total_count", 0))
        # Sprint 5 — propagate classification from runner_summary
        base["verdict"]  = r.get("verdict")
        base["category"] = r.get("category")
        base["reason"]   = r.get("reason")
        runner_summary = r.get("runner_summary")
        if runner_summary:
            base["runner_summary"] = {
                "verdict":  runner_summary.get("verdict"),
                "category": runner_summary.get("category"),
                "reason":   runner_summary.get("reason"),
                "artifacts": runner_summary.get("artifacts", {}),
            }
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


# ── Fase 4b: Command handlers ─────────────────────────────────────────────────

def _cmd_analytics_report(days: int = 7) -> dict:
    """Generar reporte analítico + KPIs."""
    try:
        from metrics_collector import MetricsCollector
        from analytics_builder import AnalyticsBuilder
        from kpi_builder import KPIBuilder

        mc = MetricsCollector(evidence_dir=_TOOL_ROOT / "evidence")
        ab = AnalyticsBuilder(metrics_collector=mc)
        kb = KPIBuilder(ab)

        report = ab.full_report(days=days)
        kpis = kb.build_kpis(days=days)

        return {
            "ok": True,
            "days": days,
            "kpis": kpis,
            "report": report,
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _cmd_replay_run(ticket_id: int, run_id: str) -> dict:
    """Reproducir un run desde su event log."""
    try:
        from replay_run import ReplayRun
        run_dir = _TOOL_ROOT / "evidence" / str(ticket_id) / run_id
        if not run_dir.exists():
            return {
                "ok": False,
                "error": f"run_dir no existe: {run_dir}",
                "hint": f"Verifica que el run_id '{run_id}' existe en evidence/{ticket_id}/",
            }
        rr = ReplayRun(run_id=run_id, run_dir=run_dir)
        return rr.replay()
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _cmd_validate_observability(ticket_id: int) -> dict:
    """Validar observabilidad de todos los runs de un ticket."""
    try:
        from observability_validator import ObservabilityValidator
        evidence_dir = _TOOL_ROOT / "evidence" / str(ticket_id)
        if not evidence_dir.exists():
            return {
                "ok": False,
                "error": f"evidence/{ticket_id}/ no existe",
            }

        results = []
        run_dirs = [d for d in evidence_dir.iterdir() if d.is_dir() and d.name.startswith("uat-")]
        if not run_dirs:
            return {
                "ok": False,
                "ticket_id": ticket_id,
                "error": "No se encontraron run dirs (uat-*) en evidence/" + str(ticket_id),
            }

        for run_dir in sorted(run_dirs):
            ov = ObservabilityValidator(run_dir=run_dir, run_id=run_dir.name)
            result = ov.validate()
            results.append(result)

        all_ok = all(r.get("ok") for r in results)
        return {
            "ok": all_ok,
            "ticket_id": ticket_id,
            "runs_checked": len(results),
            "results": results,
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _cmd_list_blockers(ticket_id: int, run_id: str) -> dict:
    """Listar blockers de un run."""
    try:
        from human_unlock import HumanUnlock
        run_dir = _TOOL_ROOT / "evidence" / str(ticket_id) / run_id
        blockers = HumanUnlock.list_blockers(run_dir=run_dir, run_id=run_id)
        return {
            "ok": True,
            "run_id": run_id,
            "ticket_id": ticket_id,
            "blockers": blockers,
            "total": len(blockers),
            "pending": sum(1 for b in blockers if b.get("status") == "pending"),
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _cmd_resolve_blocker(ticket_id: int, run_id: str, blocker_id: str, answer: str) -> dict:
    """Resolver un blocker desde CLI."""
    try:
        from human_unlock import HumanUnlock
        run_dir = _TOOL_ROOT / "evidence" / str(ticket_id) / run_id
        return HumanUnlock.resolve_from_cli(
            run_dir=run_dir,
            run_id=run_id,
            blocker_id=blocker_id,
            answer=answer,
        )
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


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
    # Fase 4b — Human Unlock, analytics, replay
    p.add_argument(
        "--replay-run", dest="replay_run", default=None, metavar="RUN_ID",
        help="[Fase 4b] Reproducir un run desde su event log. "
             "Requiere --ticket para resolver el run_dir. "
             "Ejemplo: --ticket 70 --replay-run uat-70-20260101-120000",
    )
    p.add_argument(
        "--validate-observability", dest="validate_observability", action="store_true",
        help="[Fase 4b] Validar cobertura forense de todos los runs de un ticket. "
             "Requiere --ticket. Devuelve JSON con score y checks.",
    )
    p.add_argument(
        "--analytics-report", dest="analytics_report", action="store_true",
        help="[Fase 4b] Generar reporte analítico de runs históricos.",
    )
    p.add_argument(
        "--days", type=int, default=7,
        help="[Fase 4b] Período en días para --analytics-report (default: 7).",
    )
    p.add_argument(
        "--list-blockers", dest="list_blockers", default=None, metavar="RUN_ID",
        help="[Fase 4b] Listar blockers de un run. Requiere --ticket.",
    )
    p.add_argument(
        "--resolve-blocker", dest="resolve_blocker", default=None, metavar="BLOCKER_ID",
        help="[Fase 4b] Resolver un blocker. Requiere --ticket, --run-id y --answer.",
    )
    p.add_argument(
        "--run-id", dest="run_id", default=None, metavar="RUN_ID",
        help="[Fase 4b] Run ID para operaciones de blocker.",
    )
    p.add_argument(
        "--answer", default=None,
        help="[Fase 4b] Respuesta del operador para --resolve-blocker.",
    )
    args = p.parse_args()
    if args.detect_screen_errors_vision:
        args.detect_screen_errors = True
    return args


if __name__ == "__main__":
    main()
