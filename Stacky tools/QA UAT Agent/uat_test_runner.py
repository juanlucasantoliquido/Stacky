"""
uat_test_runner.py — Execute .spec.ts Playwright tests and capture structured evidence.

SPEC: SPEC/uat_test_runner.md
CLI:
    python uat_test_runner.py \
        --tests-dir evidence/70/tests/ \
        --evidence-out evidence/70/ \
        [--headed] [--timeout-ms 30000] [--verbose]

Required env vars (inherited by the .spec.ts):
    AGENDA_WEB_BASE_URL, AGENDA_WEB_USER, AGENDA_WEB_PASS

Output: JSON to stdout following runner_output.schema.json
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
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.qa_uat.test_runner")

# v1.2.0 — Sprint 5: industrial Playwright runner.
# - playwright_config_writer generates playwright.config.ts before run (no hardcoded timeouts).
# - playwright_result_classifier classifies results into APP/NAV/ENV/DATA/OPS/OBS/PIP.
# - runner_summary event emitted to execution.jsonl with verdict/category/reason/artifacts.
# - retry_decision event emitted per retry.
# - nav_precheck_result events enriched with category/screen.
# - total=0 always BLOCKED PIP NO_TESTS_FOUND.
# v1.1.0 — harvests Playwright JSON reporter `attachments[]` (trace.zip,
# video.webm, error-context.md, screenshots) into evidence/<ticket>/<sid>/
# so the dossier and failure_analyzer have real artefact paths instead of
# null. Pre-1.1 the runner only scanned evidence/<sid>/ by extension and
# missed everything Playwright leaves under test-results/.
_TOOL_VERSION = "1.2.0"
# Default per-test timeout in ms.
# 90s acomoda: login ASP.NET WebForms (~10-25s) + 2-3 navegaciones a FrmAgenda
# (~5-15s c/u) + steps + screenshots. El default anterior de 30s reventaba
# escenarios que de otro modo eran PASS (ej: P01/P05 ticket 70).
_DEFAULT_TIMEOUT_MS = 90_000

# Assertion failure patterns in Playwright output
_ASSERTION_FAILURE_RE = re.compile(
    r'Error:\s*(.*?Expected.*?Received.*?)(?=\n\s{4}at |\Z)',
    re.DOTALL,
)
_EXPECTED_RE = re.compile(r'Expected[:\s]+(.+?)(?=Received|$)', re.DOTALL)
_RECEIVED_RE = re.compile(r'Received[:\s]+(.+?)(?=\n\s{4}at |\Z)', re.DOTALL)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    args = _parse_args()
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, stream=sys.stderr,
                            format="%(levelname)s %(name)s: %(message)s")
    else:
        logging.basicConfig(level=logging.WARNING, stream=sys.stderr)

    result = run(
        tests_dir=Path(args.tests_dir),
        evidence_out=Path(args.evidence_out),
        headed=args.headed,
        timeout_ms=args.timeout_ms,
        verbose=args.verbose,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result.get("ok") else 1)


def run(
    tests_dir: Path,
    evidence_out: Path,
    headed: bool = False,
    timeout_ms: int = _DEFAULT_TIMEOUT_MS,
    verbose: bool = False,
    # Fase 3: forensic bridge (opcionales — backward compatible)
    run_dir: Optional[Path] = None,
    forensic_log: Optional[object] = None,
    artifact_registry: Optional[object] = None,
) -> dict:
    """Core logic — callable from tests with subprocess mocking."""
    started = time.time()

    # Obtener el ExecutionLogger activo (inyectado por el pipeline) si existe.
    try:
        from execution_logger import get_active_logger as _get_active_logger
        _exec_log = _get_active_logger()
    except ImportError:
        _exec_log = None

    # ── Sprint 5.1: Generate playwright.config.ts from env vars ─────────────
    # Always regenerate before running so timeouts/reporters are always consistent
    # with the current environment.  Failure is non-fatal (best-effort).
    try:
        from playwright_config_writer import generate_config as _gen_config
        _cfg_result = _gen_config(output_dir=Path(__file__).parent)
        if not _cfg_result.get("ok"):
            logger.warning("playwright_config_writer failed (non-fatal): %s",
                           _cfg_result.get("message"))
        else:
            logger.debug("playwright.config.ts regenerated: %s", _cfg_result.get("config_path"))
    except ImportError:
        logger.debug("playwright_config_writer unavailable — config.ts not regenerated")
    except Exception as _cfg_exc:
        logger.warning("playwright_config_writer error (non-fatal): %s", _cfg_exc)

    # Check node/npx available
    if not _check_node_available():
        return _err("playwright_not_available",
                    "node or npx not found in PATH. Install Node.js.")

    # Find spec files
    spec_files = sorted(tests_dir.glob("*.spec.ts"))
    if not spec_files:
        return _err("no_tests_found",
                    f"No .spec.ts files found in {tests_dir}")

    evidence_out.mkdir(parents=True, exist_ok=True)

    # Extract ticket_id from path heuristic
    ticket_id = _extract_ticket_id(tests_dir)

    # ── Guardrails ────────────────────────────────────────────────────────────
    max_browser_launches = int(os.environ.get("QA_UAT_MAX_BROWSER_LAUNCHES", "1"))
    max_login_attempts   = int(os.environ.get("QA_UAT_MAX_LOGIN_ATTEMPTS", "1"))
    max_nav_retries      = int(os.environ.get("QA_UAT_MAX_NAVIGATION_RETRIES", "1"))
    # Default 6 minutes (3× the expected 2-minute human flow).
    # Operators can raise/lower via QA_UAT_MAX_TOTAL_MINUTES.
    max_total_min        = int(os.environ.get("QA_UAT_MAX_TOTAL_MINUTES", "6"))
    max_total_s          = max_total_min * 60

    # ── Fase 1: Navigation strategy env vars ─────────────────────────────────
    # QA_NAV_STRATEGY controls which mechanism navigate_webforms uses in specs.
    # "form_submit" (default) — HTMLFormElement.prototype.submit() bypass ScriptManager
    # "dopostback"            — window.__doPostBack() fallback for UpdatePanel controls
    # "link_click"            — anchor/button click for direct navigation
    nav_strategy  = os.environ.get("QA_NAV_STRATEGY", "form_submit")
    nav_retries   = int(os.environ.get("QA_NAV_RETRIES", "3"))
    nav_timeout   = int(os.environ.get("QA_NAV_TIMEOUT_MS", "45000"))

    # ── Fase 3: Forensic bridge setup (opcional) ────────────────────────────
    _bridge = None
    _bridge_env: dict = {}
    if run_dir is not None:
        try:
            from playwright_forensic_bridge import PlaywrightForensicBridge
            from forensic_event_logger import make_run_id as _make_run_id
            _run_id = _make_run_id(ticket_id) if forensic_log is None else getattr(forensic_log, "run_id", _make_run_id(ticket_id))
            _bridge = PlaywrightForensicBridge(
                run_dir=run_dir,
                run_id=_run_id,
                ticket_id=ticket_id,
                forensic_log=forensic_log,
                artifact_registry=artifact_registry,
            )
            _bridge.prepare()
            _bridge_env = _bridge.get_env_vars()
        except Exception as _bex:
            logger.warning("PlaywrightForensicBridge init failed (skipped): %s", _bex)

    # ── Run ALL specs in a SINGLE Playwright invocation ──────────────────────
    runs, browser_launches, login_count = _run_all_specs_once(
        spec_files=spec_files,
        evidence_out=evidence_out,
        ticket_id=ticket_id,
        headed=headed,
        timeout_ms=timeout_ms,
        max_total_s=max_total_s,
        verbose=verbose,
        exec_log=_exec_log,
        extra_env=_bridge_env,
    )

    # ── Fase 3: Import Playwright forensic events post-run ────────────────────
    if _bridge is not None:
        try:
            _bridge_summary = _bridge.import_playwright_events()
            logger.debug("Forensic bridge summary: %s", _bridge_summary)
        except Exception as _biex:
            logger.warning("PlaywrightForensicBridge import failed (skipped): %s", _biex)

    # ── Enforce browser launch limit ─────────────────────────────────────────
    if browser_launches > max_browser_launches:
        _blocked = {
            "ok": False,
            "error": "max_browser_launches_exceeded",
            "verdict": "BLOCKED",
            "reason": "MAX_BROWSER_LAUNCHES_EXCEEDED",
            "message": (
                f"QA UAT superó el máximo permitido de aperturas de navegador "
                f"({browser_launches} > {max_browser_launches})."
            ),
            "browser_launch_count": browser_launches,
            "max_browser_launches": max_browser_launches,
        }
        if exec_log is not None:
            try:
                exec_log.stage_end("runner", ok=False, duration_ms=0,
                                   result_summary=_blocked)
            except Exception:  # noqa: BLE001
                pass
        return _blocked

    # ── Enforce login attempt limit ──────────────────────────────────────────
    if login_count > max_login_attempts:
        _blocked = {
            "ok": False,
            "error": "max_login_attempts_exceeded",
            "verdict": "BLOCKED",
            "reason": "MAX_LOGIN_ATTEMPTS_EXCEEDED",
            "message": (
                f"QA UAT superó el máximo permitido de intentos de login "
                f"({login_count} > {max_login_attempts})."
            ),
            "login_count": login_count,
            "max_login_attempts": max_login_attempts,
        }
        if exec_log is not None:
            try:
                exec_log.stage_end("runner", ok=False, duration_ms=0,
                                   result_summary=_blocked)
            except Exception:  # noqa: BLE001
                pass
        return _blocked

    pass_count    = sum(1 for r in runs if r.get("status") == "pass")
    fail_count    = sum(1 for r in runs if r.get("status") == "fail")
    blocked_count = sum(1 for r in runs if r.get("status") == "blocked")
    duration_ms   = int((time.time() - started) * 1000)

    import hashlib as _hashlib
    _user = os.environ.get("AGENDA_WEB_USER", "")
    _pass = os.environ.get("AGENDA_WEB_PASS", "")
    _pass_hash = _hashlib.sha256(_pass.encode()).hexdigest()[:8] if _pass else ""

    # ── Sprint 5.2/5.3: Classify results and emit runner_summary ─────────────
    tool_dir = Path(__file__).parent
    _json_report_path = str(tool_dir / "reports" / "playwright-results.json")
    _junit_report_path = str(tool_dir / "reports" / "junit.xml")
    _exec_log_path = str(evidence_out / "execution.jsonl")

    classification = _classify_and_emit_runner_summary(
        runs=runs,
        total=len(runs),
        pass_count=pass_count,
        fail_count=fail_count,
        blocked_count=blocked_count,
        duration_ms=duration_ms,
        json_report_path=_json_report_path,
        junit_report_path=_junit_report_path,
        exec_log_path=_exec_log_path,
        exec_log=_exec_log,
        evidence_out=evidence_out,
    )

    return {
        "ok": True,
        "ticket_id": ticket_id,
        "total": len(runs),
        "pass": pass_count,
        "fail": fail_count,
        "blocked": blocked_count,
        # Sprint 5 — classification propagated to pipeline output
        "verdict": classification.get("verdict", "PASS" if len(runs) > 0 and fail_count == 0 and blocked_count == 0 else "BLOCKED"),
        "category": classification.get("category"),
        "reason": classification.get("reason"),
        "runs": runs,
        "runner_summary": classification,
        "meta": {
            "tool": "uat_test_runner",
            "version": _TOOL_VERSION,
            "duration_ms": duration_ms,
            "browser_launch_count": browser_launches,
            "login_count": login_count,
            "base_url": os.environ.get("AGENDA_WEB_BASE_URL", "http://localhost:35017/AgendaWeb/"),
            "managed_app": False,
            # Credential audit (no password in plain text)
            "credentials_source": "env",
            "username": _user or "MISSING",
            "password_present": bool(_pass),
            "password_hash_prefix": _pass_hash,
            "max_total_minutes": max_total_min,
            "max_login_attempts": max_login_attempts,
            "max_browser_launches": max_browser_launches,
        },
    }


# ── Single Playwright invocation (all specs at once) ─────────────────────────

def _run_all_specs_once(
    spec_files: list,
    evidence_out: Path,
    ticket_id: int,
    headed: bool,
    timeout_ms: int,
    max_total_s: int,
    verbose: bool,
    exec_log=None,
    extra_env: Optional[dict] = None,
) -> tuple:
    """Run every spec in tests_dir with a SINGLE 'npx playwright test <dir>' call.

    Returns (runs, browser_launch_count, login_count).
    - browser_launch_count is always 1 (globalSetup handles auth caching).
    - login_count is 0 if cached auth was used, 1 if a fresh login was done.
    """
    import sys as _sys
    started = time.time()
    tool_dir = Path(__file__).parent
    config_path = tool_dir / "playwright.config.ts"

    # Create per-spec scenario dirs before running
    for spec_file in spec_files:
        scenario_id = _scenario_id_from_filename(spec_file.name)
        (evidence_out / scenario_id).mkdir(parents=True, exist_ok=True)

    # Build Playwright command targeting the whole tests directory
    tests_dir = spec_files[0].parent
    try:
        tests_rel = tests_dir.relative_to(tool_dir)
        tests_arg = str(tests_rel).replace("\\", "/")
    except ValueError:
        tests_arg = str(tests_dir).replace("\\", "/")

    headless_flag = os.environ.get("STACKY_QA_UAT_HEADLESS", "0" if headed else "1")
    env = {**os.environ, "STACKY_QA_UAT_HEADLESS": headless_flag}
    if headed and "STACKY_QA_UAT_SLOW_MO" not in env:
        env["STACKY_QA_UAT_SLOW_MO"] = "500"
    # Fase 1 — Forward navigation strategy to the Playwright subprocess.
    # navigate_webforms steps in generated specs read these vars.
    env.setdefault("QA_NAV_STRATEGY",        os.environ.get("QA_NAV_STRATEGY",        "form_submit"))
    env.setdefault("QA_NAV_RETRIES",         os.environ.get("QA_NAV_RETRIES",         "3"))
    env.setdefault("QA_NAV_TIMEOUT_MS",      os.environ.get("QA_NAV_TIMEOUT_MS",      "45000"))
    # Fase 3: configurable timeouts for grid visibility and per-action waits.
    env.setdefault("QA_UAT_GRID_TIMEOUT_MS",   os.environ.get("QA_UAT_GRID_TIMEOUT_MS",   "5000"))
    env.setdefault("QA_UAT_ACTION_TIMEOUT_MS",  os.environ.get("QA_UAT_ACTION_TIMEOUT_MS",  "30000"))
    if extra_env:
        env.update(extra_env)

    cmd = [
        "npx", "playwright", "test",
        tests_arg,
        f"--timeout={timeout_ms}",
        "--workers=1",
    ]
    if headed:
        cmd.append("--headed")
    if config_path.is_file():
        cmd += ["--config", str(config_path)]

    use_shell = _sys.platform == "win32"
    cmd_arg = subprocess.list2cmdline(cmd) if use_shell else cmd

    # Remove stale JSON report before running
    pw_report_path = tool_dir / "evidence" / ".playwright-report.json"
    try:
        if pw_report_path.is_file():
            pw_report_path.unlink()
    except OSError:
        pass

    # Total timeout = per-test * number of specs + 120s overhead
    total_timeout_s = min(
        max_total_s,
        timeout_ms * len(spec_files) // 1000 + 120,
    )

    logger.debug("Running all specs: %s", " ".join(cmd))
    print(f"\n[uat_test_runner] ▶ Single invocation: {len(spec_files)} spec(s), timeout={total_timeout_s}s", flush=True)

    if exec_log is not None:
        try:
            exec_log.playwright_run_start(
                scenario_id="all_specs",
                spec_file=tests_arg,
                headed=headed,
                timeout_ms=timeout_ms,
            )
        except Exception:  # noqa: BLE001
            pass

    captured_lines: list = []
    try:
        proc = subprocess.Popen(
            cmd_arg,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env=env,
            cwd=str(tool_dir),
            shell=use_shell,
        )
    except FileNotFoundError:
        runs = [
            _blocked_result(sf, _scenario_id_from_filename(sf.name),
                            "npx not found in PATH")
            for sf in spec_files
        ]
        return runs, 0, 0

    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            print(line, end="", flush=True)
            captured_lines.append(line)
        proc.wait(timeout=total_timeout_s)
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            proc.wait(timeout=10)
        except Exception:  # noqa: BLE001
            pass
        stdout = "".join(captured_lines)
        _persist_playwright_stdout(evidence_out, stdout)
        runs = [
            _timeout_result(sf, _scenario_id_from_filename(sf.name), timeout_ms)
            for sf in spec_files
        ]
        return runs, 1, 0

    stdout = "".join(captured_lines)
    _persist_playwright_stdout(evidence_out, stdout)

    pw_report = _read_playwright_json_report(pw_report_path)
    returncode = proc.returncode if proc.returncode is not None else 1

    # Determine if globalSetup performed a real login (heuristic: "Logging into" in output)
    login_count = 1 if "Logging into" in stdout else 0

    # Parse per-spec results from the combined JSON report
    runs = _parse_per_spec_results(
        spec_files=spec_files,
        pw_report=pw_report,
        evidence_out=evidence_out,
        combined_stdout=stdout,
        overall_returncode=returncode,
        exec_log=exec_log,
    )

    # Fase 3: Collect nav_precheck_result.json files written by precheckGrid()
    # TypeScript helper and emit them as structured events in execution.jsonl.
    _collect_nav_precheck_events(evidence_out, ticket_id, exec_log)

    return runs, 1, login_count


def _parse_per_spec_results(
    spec_files: list,
    pw_report: dict,
    evidence_out: Path,
    combined_stdout: str,
    overall_returncode: int,
    exec_log=None,
) -> list:
    """Parse per-spec pass/fail status from the combined Playwright JSON report.

    Walks the nested suite tree to find each spec file's result.
    Falls back to BLOCKED if a spec is not found in the report.
    """

    # Build a flat map: spec_filename_stem → spec suite dict from Playwright report
    file_suites: dict[str, dict] = {}
    _collect_file_suites(pw_report.get("suites", []), file_suites)

    runs = []
    for spec_file in spec_files:
        scenario_id = _scenario_id_from_filename(spec_file.name)
        scenario_dir = evidence_out / scenario_id
        scenario_dir.mkdir(parents=True, exist_ok=True)

        started_spec = time.time()

        # Find the matching suite by filename
        spec_suite = _find_suite_for_file(file_suites, spec_file)

        if spec_suite is None:
            # Suite not matched by filename — fall back to stdout/returncode heuristics
            # and extract assertion failures the old way from the combined report.
            assertion_failures = _extract_assertion_failures(pw_report, combined_stdout)
            if overall_returncode == 0:
                status = "pass"
            elif "Error:" in combined_stdout or "error:" in combined_stdout.lower():
                status = "blocked"
            elif assertion_failures:
                status = "fail"
            else:
                status = "fail" if overall_returncode != 0 else "pass"

            result: dict = {
                "scenario_id": scenario_id,
                "spec_file": str(spec_file),
                "status": status,
                "duration_ms": int((time.time() - started_spec) * 1000),
                "artifacts": _collect_artifacts(scenario_dir),
                "raw_stdout": combined_stdout[:50000],
                "raw_stderr": "",
            }
            if status == "fail" and assertion_failures:
                result["assertion_failures"] = assertion_failures
            if status == "blocked":
                result["reason"] = "RUNTIME_ERROR"
            runs.append(result)
            continue

        # Extract all test results from the suite
        all_test_results = _collect_test_results(spec_suite)
        total_duration = sum(r.get("duration", 0) for r in all_test_results)

        # Determine aggregate status
        statuses = [r.get("status") for r in all_test_results]
        errors = [
            e for r in all_test_results for e in (r.get("errors") or [])
        ]
        error_messages = [e.get("message", "") or e.get("value", "") for e in errors]

        # ── Sprint 5.4: emit retry_decision for each retry attempt ────────────
        max_attempts = len(statuses)
        if max_attempts > 1:
            retry_reason = "PLAYWRIGHT_TIMEOUT" if any(s == "timedOut" for s in statuses) else "PLAYWRIGHT_FAILURE"
            trace_env = os.environ.get("QA_UAT_TRACE", "on-first-retry")
            trace_enabled = trace_env in ("always", "on-first-retry", "retain-on-failure")
            for attempt_idx in range(2, max_attempts + 1):
                _emit_retry_decision(
                    exec_log=exec_log,
                    scenario_id=scenario_id,
                    reason=retry_reason,
                    attempt=attempt_idx,
                    max_attempts=max_attempts,
                    trace_enabled=trace_enabled,
                )

        if all(s == "passed" for s in statuses) and statuses:
            status = "pass"
        elif any(s == "timedOut" for s in statuses):
            status = "blocked"
            # Fase 3: tag timed-out messages so _classify_blocked_reason picks PLAYWRIGHT_TIMEOUT.
            error_messages = [f"[PLAYWRIGHT_TIMEOUT] Timeout ({s})" for s in statuses if s == "timedOut"] + error_messages
        elif any(s == "failed" for s in statuses):
            status = "fail"
        elif any(s == "interrupted" for s in statuses):
            status = "blocked"
        else:
            status = "fail" if overall_returncode != 0 else "pass"

        # Build assertion failures from errors
        assertion_failures = []
        for msg in error_messages:
            if msg:
                entry = {"message": msg[:300]}
                expected = _extract_expected(msg)
                actual = _extract_actual(msg)
                if expected:
                    entry["expected"] = expected
                if actual:
                    entry["actual"] = actual
                assertion_failures.append(entry)

        # Harvest attachments (trace, video, screenshots) into scenario dir
        _harvest_pw_attachments({"suites": [spec_suite]}, scenario_dir)

        result: dict = {
            "scenario_id": scenario_id,
            "spec_file": str(spec_file),
            "status": status,
            "duration_ms": total_duration,
            "artifacts": _collect_artifacts(scenario_dir),
            "raw_stdout": combined_stdout[:50000],
            "raw_stderr": "",
        }
        if status == "fail" and assertion_failures:
            result["assertion_failures"] = assertion_failures
        if status == "blocked":
            # Fase 3: classify blocked reason granularly instead of always RUNTIME_ERROR.
            result["reason"] = _classify_blocked_reason(error_messages)
        if exec_log is not None:
            try:
                exec_log.playwright_run_end(
                    scenario_id=scenario_id,
                    status=status,
                    duration_ms=total_duration,
                    return_code=0 if status == "pass" else 1,
                    assertion_failures=assertion_failures,
                    reason=result.get("reason"),
                )
            except Exception:  # noqa: BLE001
                pass

        runs.append(result)

    return runs


def _collect_file_suites(suites: list, out: dict, depth: int = 0) -> None:
    """Recursively collect file-level suites from Playwright JSON report.

    Playwright JSON reporter hierarchy:
      [project] → [file] → [describe] → [spec]
    We collect suites at the file level (title ends with .spec.ts).
    """
    for suite in suites:
        title = suite.get("title", "") or suite.get("file", "")
        if title.endswith(".spec.ts"):
            # Normalize path separators for consistent lookup
            key = title.replace("\\", "/").split("/")[-1]  # just the filename
            out[key] = suite
        # Always recurse — file suites may be nested under project suites
        _collect_file_suites(suite.get("suites", []), out, depth + 1)


def _find_suite_for_file(file_suites: dict, spec_file: Path) -> Optional[dict]:
    """Find the Playwright suite for a given spec file path."""
    filename = spec_file.name
    # Direct key match
    if filename in file_suites:
        return file_suites[filename]
    # Partial match (path contains filename)
    for key, suite in file_suites.items():
        if key == filename or key.endswith(f"/{filename}"):
            return suite
    return None


def _collect_test_results(suite: dict) -> list:
    """Recursively collect all test result dicts from a suite."""
    results = []
    for spec in suite.get("specs", []):
        for test in spec.get("tests", []):
            results.extend(test.get("results", []))
    for sub in suite.get("suites", []):
        results.extend(_collect_test_results(sub))
    return results


def _classify_blocked_reason(error_messages: list) -> str:
    """Map Playwright error message text to a structured reason code.

    Priority: PLAYWRIGHT_TIMEOUT > GRID_EMPTY > ROW_NOT_FOUND >
              SELECTOR_NOT_FOUND > DEPLOYMENT_MISMATCH > RUNTIME_ERROR
    """
    combined = " ".join(str(m) for m in error_messages).lower()
    if "playwright_timeout" in combined or "timeout" in combined:
        return "PLAYWRIGHT_TIMEOUT"
    if "grid_empty" in combined:
        return "GRID_EMPTY"
    if "row_not_found" in combined or "row not found" in combined:
        return "ROW_NOT_FOUND"
    if "selector_not_found" in combined or "locator resolved to 0" in combined:
        return "SELECTOR_NOT_FOUND"
    if "deployment" in combined or "version mismatch" in combined:
        return "DEPLOYMENT_MISMATCH"
    return "RUNTIME_ERROR"


def _collect_nav_precheck_events(evidence_out: Path, ticket_id: int, exec_log) -> None:
    """Read nav_precheck_result.json files written by precheckGrid() TypeScript helper.

    Emits a nav_precheck_result event to the active ExecutionLogger for each file
    found in evidence_out/<scenario_id>/nav_precheck_result.json.

    Sprint 5.5 — enriches events with category and screen fields for classifier
    compatibility.  Visible = false → NAV/SELECTOR_NOT_FOUND; row_count = 0 → DATA/GRID_EMPTY.

    Called after all specs finish so events appear in execution.jsonl regardless
    of whether the spec passed or failed.
    """
    if exec_log is None:
        return
    for precheck_file in sorted(evidence_out.glob("*/nav_precheck_result.json")):
        try:
            data = json.loads(precheck_file.read_text(encoding="utf-8"))
            scenario_id = precheck_file.parent.name

            # Sprint 5.5 — resolve category/reason from precheck outcome
            visible = data.get("visible", data.get("found", True))
            row_count = data.get("row_count", 0)
            if not visible:
                decision  = "BLOCKED"
                category  = "NAV"
                reason    = "SELECTOR_NOT_FOUND"
            elif row_count == 0:
                decision  = "BLOCKED"
                category  = "DATA"
                reason    = "GRID_EMPTY"
            else:
                decision  = data.get("verdict", data.get("decision", "PASS"))
                category  = None
                reason    = None

            exec_log.event("nav_precheck_result", {
                "ticket_id": ticket_id,
                "scenario_id": scenario_id,
                "screen": data.get("screen"),
                "target_alias": data.get("target_alias") or data.get("grid_alias"),
                "selector": data.get("selector"),
                "visible": visible,
                "row_count": row_count,
                "timeout_ms": data.get("timeout_ms") or data.get("elapsed_ms"),
                "decision": decision,
                "category": category,
                "reason": reason,
            })
        except Exception:  # noqa: BLE001
            pass


# ── Sprint 5.3: runner_summary classification and event emission ──────────────

def _classify_and_emit_runner_summary(
    runs: list,
    total: int,
    pass_count: int,
    fail_count: int,
    blocked_count: int,
    duration_ms: int,
    json_report_path: str,
    junit_report_path: str,
    exec_log_path: str,
    exec_log,
    evidence_out: Path,
) -> dict:
    """
    Sprint 5.3 — Classify all results and emit runner_summary to execution.jsonl.

    Uses playwright_result_classifier if available; falls back to heuristic
    classification from the runs list when the module is unavailable.

    Returns the classification dict (subset of PlaywrightClassificationResult).
    """
    # ── Structural guard: total=0 is always BLOCKED PIP NO_TESTS_FOUND ────────
    if total == 0:
        summary = {
            "verdict": "BLOCKED",
            "category": "PIP",
            "reason": "NO_TESTS_FOUND",
            "total": 0,
            "passed": 0,
            "failed": 0,
            "blocked": 0,
            "skipped": 0,
            "retries": 0,
            "duration_ms": duration_ms,
            "artifacts": {},
            "scenario_results": [],
        }
        _emit_runner_summary(exec_log, summary)
        return summary

    # ── Try classifier ─────────────────────────────────────────────────────────
    try:
        from playwright_result_classifier import classify_playwright_results as _classify

        # Collect nav_precheck events from evidence dirs
        precheck_events = _collect_precheck_events_from_evidence(evidence_out)

        result = _classify(
            junit_path=junit_report_path if Path(junit_report_path).is_file() else None,
            json_path=json_report_path if Path(json_report_path).is_file() else None,
            execution_log_path=exec_log_path if Path(exec_log_path).is_file() else None,
            nav_precheck_results=precheck_events,
        )

        # Build artifact links including per-scenario counts
        artifacts = dict(result.artifacts)
        artifacts.update({
            "junit": junit_report_path if Path(junit_report_path).is_file() else None,
            "json_results": json_report_path if Path(json_report_path).is_file() else None,
        })
        tool_dir = Path(__file__).parent
        html_idx = tool_dir / "playwright-report" / "index.html"
        if html_idx.is_file():
            artifacts["html_report"] = str(html_idx)

        summary = {
            "verdict": result.verdict,
            "category": result.category,
            "reason": result.reason,
            "total": result.total if result.total > 0 else total,
            "passed": result.passed if result.total > 0 else pass_count,
            "failed": result.failed if result.total > 0 else fail_count,
            "blocked": result.blocked if result.total > 0 else blocked_count,
            "skipped": result.skipped,
            "retries": result.retries,
            "duration_ms": result.duration_ms or duration_ms,
            "artifacts": artifacts,
            "scenario_results": [
                {
                    "scenario_id": s.scenario_id,
                    "status": s.status,
                    "duration_ms": s.duration_ms,
                    "attempts": s.attempts,
                    "classification": s.classification,
                }
                for s in result.scenario_results
            ],
        }
        _emit_runner_summary(exec_log, summary)
        return summary

    except ImportError:
        logger.debug("playwright_result_classifier unavailable — using heuristic summary")
    except Exception as _cls_exc:
        logger.warning("playwright_result_classifier error (non-fatal): %s", _cls_exc)

    # ── Heuristic fallback (classifier unavailable) ────────────────────────────
    if pass_count == total:
        verdict, category, reason = "PASS", None, None
    elif fail_count > 0 and pass_count > 0:
        verdict, category, reason = "MIXED", "APP", "ASSERTION_FAILED"
    elif fail_count > 0:
        verdict, category, reason = "FAIL", "APP", "ASSERTION_FAILED"
    else:
        verdict, category, reason = "BLOCKED", "OPS", "WORKER_CRASH"

    summary = {
        "verdict": verdict,
        "category": category,
        "reason": reason,
        "total": total,
        "passed": pass_count,
        "failed": fail_count,
        "blocked": blocked_count,
        "skipped": 0,
        "retries": 0,
        "duration_ms": duration_ms,
        "artifacts": {
            "junit": junit_report_path if Path(junit_report_path).is_file() else None,
            "json_results": json_report_path if Path(json_report_path).is_file() else None,
            "html_report": None,
            "trace_count": 0,
            "screenshots_count": 0,
            "video_count": 0,
        },
        "scenario_results": [
            {
                "scenario_id": r.get("scenario_id", "unknown"),
                "status": r.get("status", "unknown"),
                "duration_ms": r.get("duration_ms", 0),
                "attempts": 1,
                "classification": {
                    "verdict": "PASS" if r.get("status") == "pass" else
                               "FAIL" if r.get("status") == "fail" else "BLOCKED",
                    "category": None if r.get("status") == "pass" else "APP",
                    "reason": None if r.get("status") == "pass" else "ASSERTION_FAILED",
                },
            }
            for r in runs
        ],
    }
    _emit_runner_summary(exec_log, summary)
    return summary


def _emit_runner_summary(exec_log, summary: dict) -> None:
    """Emit runner_summary event to execution.jsonl."""
    if exec_log is None:
        return
    try:
        exec_log.event("runner_summary", summary)
    except Exception as _ex:
        logger.debug("runner_summary event emit failed (non-fatal): %s", _ex)


def _collect_precheck_events_from_evidence(evidence_out: Path) -> list:
    """Read nav_precheck_result.json files from evidence dir and return as event list."""
    events: list = []
    if not evidence_out.is_dir():
        return events
    for precheck_file in sorted(evidence_out.glob("*/nav_precheck_result.json")):
        try:
            data = json.loads(precheck_file.read_text(encoding="utf-8"))
            scenario_id = precheck_file.parent.name
            events.append({
                "event": "nav_precheck_result",
                "scenario_id": data.get("scenario_id") or scenario_id,
                "grid_alias": data.get("grid_alias") or data.get("target_alias"),
                "selector": data.get("selector"),
                "row_count": data.get("row_count", 0),
                "decision": data.get("verdict") or data.get("decision"),
                "category": data.get("category"),
                "reason": data.get("reason"),
                "screen": data.get("screen"),
            })
        except Exception:  # noqa: BLE001
            pass
    return events


# ── Sprint 5.4: retry_decision event ─────────────────────────────────────────

def _emit_retry_decision(
    exec_log,
    scenario_id: str,
    reason: str,
    attempt: int,
    max_attempts: int,
    trace_enabled: bool,
) -> None:
    """
    Sprint 5.4 — Emit a retry_decision event to execution.jsonl.

    Called whenever Playwright re-runs a test (attempt > 1) so each retry
    is individually auditable.
    """
    if exec_log is None:
        return
    from datetime import datetime, timezone
    try:
        exec_log.event("retry_decision", {
            "scenario_id": scenario_id,
            "reason": reason,
            "attempt": attempt,
            "max_attempts": max_attempts,
            "trace_enabled": trace_enabled,
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        })
    except Exception as _ex:
        logger.debug("retry_decision event emit failed (non-fatal): %s", _ex)


def _blocked_result(spec_file: Path, scenario_id: str, reason: str) -> dict:
    return {
        "scenario_id": scenario_id,
        "spec_file": str(spec_file),
        "status": "blocked",
        "reason": "RUNTIME_ERROR",
        "duration_ms": 0,
        "artifacts": {},
        "raw_stdout": "",
        "raw_stderr": reason,
    }


def _timeout_result(spec_file: Path, scenario_id: str, timeout_ms: int) -> dict:
    return {
        "scenario_id": scenario_id,
        "spec_file": str(spec_file),
        "status": "blocked",
        "reason": "TIMEOUT",
        "duration_ms": timeout_ms,
        "artifacts": {},
        "raw_stdout": "",
        "raw_stderr": f"Process timed out after {timeout_ms}ms",
    }


# ── Single spec execution ──────────────────────────────────────────────────────

def _run_single_spec(
    spec_file: Path,
    scenario_id: str,
    scenario_dir: Path,
    ticket_id: int,
    headed: bool,
    timeout_ms: int,
    verbose: bool,
    exec_log=None,  # ExecutionLogger | None
) -> dict:
    """Run a single .spec.ts and return run result dict."""
    started = time.time()

    # Log inicio del spec
    if exec_log is not None:
        try:
            exec_log.playwright_run_start(
                scenario_id=scenario_id,
                spec_file=str(spec_file),
                headed=headed,
                timeout_ms=timeout_ms,
            )
        except Exception:  # noqa: BLE001
            pass

    headless_flag = os.environ.get("STACKY_QA_UAT_HEADLESS", "1" if not headed else "0")

    env = {**os.environ, "STACKY_QA_UAT_HEADLESS": headless_flag}
    # En modo headed, ralentizamos cada acción 500ms para que el operador
    # pueda seguir visualmente lo que hace Playwright. La env var la lee
    # playwright.config.ts y la pasa a launchOptions.slowMo.
    if headed and "STACKY_QA_UAT_SLOW_MO" not in env:
        env["STACKY_QA_UAT_SLOW_MO"] = "500"

    # Build playwright CLI command
    import sys as _sys
    # Use the actual file location (not resolved symlink) to avoid junction issues on Windows
    tool_dir = Path(__file__).parent
    config_path = tool_dir / "playwright.config.ts"
    # Make spec path relative to tool_dir so Playwright doesn't resolve via symlink.
    # Use forward slashes — Playwright treats the arg as a regex/glob and backslashes break it.
    try:
        spec_rel = spec_file.relative_to(tool_dir)
        spec_arg = str(spec_rel).replace("\\", "/")
    except ValueError:
        spec_arg = str(spec_file).replace("\\", "/")
    cmd = [
        "npx", "playwright", "test",
        spec_arg,
        f"--timeout={timeout_ms}",
    ]
    # NOTA: NO pasamos --reporter=json acá. El config ya define dos reporters:
    #   - 'list'  → output legible en stdout en vivo (paso a paso)
    #   - 'json'  → archivo evidence/.playwright-report.json (lo leemos al final)
    # Si pasáramos --reporter=json en CLI, Playwright sobreescribiría los del
    # config y perderíamos el list reporter (el operador no vería nada en vivo).
    if headed:
        cmd.append("--headed")
    if config_path.is_file():
        cmd += ["--config", str(config_path)]

    logger.debug("Running: %s", " ".join(cmd))

    # On Windows, .cmd/.ps1 files require shell=True (subprocess can't exec them directly)
    use_shell = _sys.platform == "win32"
    cmd_arg = subprocess.list2cmdline(cmd) if use_shell else cmd

    # Path donde el JSON reporter del config deja el reporte estructurado.
    # Lo borramos antes de correr para no leer un reporte stale si Playwright
    # falla antes de escribirlo.
    pw_report_path = tool_dir / "evidence" / ".playwright-report.json"
    try:
        if pw_report_path.is_file():
            pw_report_path.unlink()
    except OSError:
        pass

    # Streaming en vivo: en lugar de subprocess.run con capture_output, usamos
    # Popen y leemos stdout línea por línea, imprimiendo al terminal del
    # operador a medida que Playwright avanza. Stderr se redirige a stdout
    # para preservar el orden cronológico de los mensajes.
    captured_lines: list = []
    timeout_seconds = timeout_ms * 5 // 1000 + 60  # 5x individual + 60s overhead
    try:
        proc = subprocess.Popen(
            cmd_arg,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,  # line-buffered
            env=env,
            cwd=str(tool_dir),
            shell=use_shell,
        )
    except FileNotFoundError:
        return {
            "scenario_id": scenario_id,
            "spec_file": str(spec_file),
            "status": "blocked",
            "reason": "RUNTIME_ERROR",
            "duration_ms": 0,
            "artifacts": {},
            "raw_stdout": "",
            "raw_stderr": "npx not found in PATH",
        }

    # Banner para que el operador identifique en qué escenario está.
    print(f"\n[uat_test_runner] ▶ {scenario_id} ({spec_file.name})", flush=True)

    try:
        assert proc.stdout is not None  # narrowing para type checkers
        for line in proc.stdout:
            print(line, end="", flush=True)
            captured_lines.append(line)
            # Log cada línea al execution_logger (solo si está en nivel DEBUG)
            if exec_log is not None:
                try:
                    exec_log.playwright_line(scenario_id, line)
                except Exception:  # noqa: BLE001
                    pass
        proc.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            proc.wait(timeout=10)
        except Exception:
            pass
        duration = int((time.time() - started) * 1000)
        raw_stdout = "".join(captured_lines)
        # Persistir stdout completo como archivo independiente (sin truncado)
        _persist_playwright_stdout(scenario_dir, raw_stdout)
        if exec_log is not None:
            try:
                exec_log.playwright_timeout(scenario_id, timeout_ms)
                exec_log.playwright_run_end(
                    scenario_id=scenario_id,
                    status="blocked",
                    duration_ms=duration,
                    return_code=-1,
                    reason="TIMEOUT",
                )
            except Exception:  # noqa: BLE001
                pass
        return {
            "scenario_id": scenario_id,
            "spec_file": str(spec_file),
            "status": "blocked",
            "reason": "TIMEOUT",
            "duration_ms": duration,
            "artifacts": _collect_artifacts(scenario_dir),
            "raw_stdout": raw_stdout[:50000],
            "raw_stderr": "Process timed out",
        }

    duration = int((time.time() - started) * 1000)
    stdout = "".join(captured_lines)
    # Persistir stdout completo como archivo independiente (sin truncado de 50k)
    _persist_playwright_stdout(scenario_dir, stdout)
    # stderr quedó merged en stdout (stderr=STDOUT), pero conservamos el campo
    # para no romper el contrato runner_output.schema.json.
    stderr = ""

    # El parse JSON ya no viene de stdout (ahora muestra el reporter 'list',
    # legible). Leemos el reporte estructurado del archivo que escribió el
    # json reporter del config.
    pw_results = _read_playwright_json_report(pw_report_path)
    # Mantenemos el parsing de stderr-style desde el stdout combinado como
    # fallback para extraer mensajes de assertion.
    assertion_failures = _extract_assertion_failures(pw_results, stdout)

    # Harvest attachments produced by Playwright into the evidence dir BEFORE
    # collecting artefacts — otherwise the JSON output reports trace/video
    # paths under test-results/ but the dossier has no copies.
    _harvest_pw_attachments(pw_results, scenario_dir)

    # Determine status
    returncode = proc.returncode if proc.returncode is not None else 1
    if returncode == 0:
        status = "pass"
    elif assertion_failures:
        status = "fail"
    elif returncode != 0 and ("Error:" in stdout or "error:" in stdout.lower()):
        status = "blocked"
    else:
        status = "fail"  # non-zero exit without assertion msg → treat as fail

    artifacts = _collect_artifacts(scenario_dir)

    result: dict = {
        "scenario_id": scenario_id,
        "spec_file": str(spec_file),
        "status": status,
        "duration_ms": duration,
        "artifacts": artifacts,
        "raw_stdout": stdout[:50000],
        "raw_stderr": stderr[:5000],
    }
    if status == "fail" and assertion_failures:
        result["assertion_failures"] = assertion_failures
    if status == "blocked":
        result["reason"] = "RUNTIME_ERROR"

    # Log resultado al execution_logger
    if exec_log is not None:
        try:
            for af in (assertion_failures or []):
                exec_log.playwright_assertion(
                    scenario_id=scenario_id,
                    expected=str(af.get("expected", ""))[:500],
                    received=str(af.get("actual", ""))[:500],
                    message=str(af.get("message", ""))[:2000],
                )
            exec_log.playwright_run_end(
                scenario_id=scenario_id,
                status=status,
                duration_ms=duration,
                return_code=returncode,
                assertion_failures=assertion_failures or [],
                reason=result.get("reason"),
            )
        except Exception:  # noqa: BLE001
            pass

    return result


# ── Helpers ───────────────────────────────────────────────────────────────────

def _persist_playwright_stdout(scenario_dir: Path, stdout: str) -> None:
    """Guardar el stdout completo de Playwright como archivo (sin truncado).

    Útil para debugging post-ejecución sin depender de raw_stdout (que está
    limitado a 50k chars en el runner_output.json).
    """
    try:
        out_file = scenario_dir / "playwright_output.txt"
        out_file.write_text(stdout, encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass  # Nunca interrumpir el pipeline por un fallo de logging


def _check_node_available() -> bool:
    import sys as _sys
    # On Windows, use shell=True so cmd.exe can resolve npx.cmd/.ps1
    use_shell = _sys.platform == "win32"
    for cmd in (["node", "--version"], ["npx", "--version"]):
        try:
            cmd_arg = subprocess.list2cmdline(cmd) if use_shell else cmd
            r = subprocess.run(cmd_arg, capture_output=True, timeout=10, check=False, shell=use_shell)
            if r.returncode == 0:
                return True
        except (FileNotFoundError, OSError):
            pass
    return False


def _scenario_id_from_filename(filename: str) -> str:
    """Extract P01 from 'P01_busqueda_sin_filtros.spec.ts'."""
    m = re.match(r'^(P\d{2,})', filename)
    return m.group(1) if m else filename.replace(".spec.ts", "")


def _extract_ticket_id(tests_dir: Path) -> int:
    """Heuristic: parent dir name is ticket id."""
    try:
        return int(tests_dir.parent.name)
    except (ValueError, AttributeError):
        return 0


def _parse_playwright_json_output(stdout: str) -> dict:
    """Try to parse Playwright's JSON reporter output from stdout (legacy path).

    Conservado por compatibilidad: tests existentes pueden seguir invocándolo
    contra una captura de stdout. El runtime actual usa
    `_read_playwright_json_report` para leer el archivo que escribe el json
    reporter del config — necesario porque ahora el stdout muestra el reporter
    `list` (output legible en vivo) en lugar del JSON.
    """
    try:
        # Playwright JSON reporter outputs the full JSON at end of stdout
        lines = stdout.strip().split("\n")
        for line in reversed(lines):
            line = line.strip()
            if line.startswith("{") and line.endswith("}"):
                return json.loads(line)
        # Try entire stdout
        return json.loads(stdout)
    except Exception:
        return {}


def _read_playwright_json_report(report_path: Path) -> dict:
    """Read the JSON report file produced by the `json` reporter in
    playwright.config.ts (`evidence/.playwright-report.json`).

    Devuelve {} si el archivo no existe o no es JSON válido. Usar esto en
    lugar de parsear stdout permite que el reporter `list` (output en vivo)
    coexista con el reporter estructurado.
    """
    try:
        if not report_path.is_file():
            return {}
        with report_path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as exc:
        logger.debug("Could not read Playwright JSON report at %s: %s", report_path, exc)
        return {}


def _extract_assertion_failures(pw_results: dict, stderr: str) -> list:
    """Extract assertion failures from Playwright output."""
    failures = []

    # From JSON reporter
    suites = pw_results.get("suites", [])
    for suite in suites:
        for spec in suite.get("specs", []):
            for test in spec.get("tests", []):
                for result in test.get("results", []):
                    for err in result.get("errors", []):
                        msg = err.get("message", "")
                        if msg:
                            expected = _extract_expected(msg)
                            actual = _extract_actual(msg)
                            entry = {"message": msg[:300]}
                            if expected:
                                entry["expected"] = expected
                            if actual:
                                entry["actual"] = actual
                            failures.append(entry)

    # Fallback: parse stderr
    if not failures and "Expected" in stderr and "Received" in stderr:
        for m in _ASSERTION_FAILURE_RE.finditer(stderr):
            full = m.group(0)
            expected = _extract_expected(full)
            actual = _extract_actual(full)
            entry = {"message": full[:300].strip()}
            if expected:
                entry["expected"] = expected
            if actual:
                entry["actual"] = actual
            failures.append(entry)

    return failures


def _extract_expected(text: str) -> Optional[str]:
    m = _EXPECTED_RE.search(text)
    return m.group(1).strip()[:100] if m else None


def _extract_actual(text: str) -> Optional[str]:
    m = _RECEIVED_RE.search(text)
    return m.group(1).strip()[:100] if m else None


def _collect_artifacts(scenario_dir: Path) -> dict:
    """Collect paths of evidence artifacts that exist in scenario_dir."""
    artifacts: dict = {
        "trace": None,
        "video": None,
        "screenshots": [],
        "console_log": None,
        "network_log": None,
        "error_context": None,
    }
    if not scenario_dir.is_dir():
        return artifacts

    for f in scenario_dir.iterdir():
        name = f.name
        if name.endswith(".zip"):
            artifacts["trace"] = str(f)
        elif name.endswith(".webm"):
            artifacts["video"] = str(f)
        elif name.endswith(".png"):
            artifacts["screenshots"].append(str(f))
        elif name == "console.json":
            artifacts["console_log"] = str(f)
        elif name == "network.json":
            artifacts["network_log"] = str(f)
        elif name == "error-context.md":
            artifacts["error_context"] = str(f)

    artifacts["screenshots"].sort()
    return artifacts


# Map of Playwright attachment.name → canonical filename inside scenario_dir.
# We rename so the dossier links are deterministic regardless of which
# test-results subfolder Playwright chose.
_ATTACHMENT_TARGET_NAMES = {
    "trace": "trace.zip",
    "video": "video.webm",
    "error-context": "error-context.md",
    # `screenshot` here is Playwright's auto-capture-on-failure (separate
    # from the explicit page.screenshot() calls in the spec). Saved as
    # test_failure.png so it's distinguishable from step screenshots.
    "screenshot": "test_failure.png",
}


def _harvest_pw_attachments(pw_results: dict, scenario_dir: Path) -> None:
    """Copy attachments reported by Playwright's JSON reporter into the
    scenario evidence directory under canonical names.

    Playwright leaves trace/video/error-context under
    test-results/<spec>-<project>/, which the original collector never
    scanned. With this harvest the dossier can link them and the failure
    analyzer can cite real paths.

    Failures are best-effort: if a path doesn't exist (test passed without
    tracing, or the attachment was skipped), we just skip it — never raise.
    """
    import shutil
    if not pw_results:
        return
    scenario_dir.mkdir(parents=True, exist_ok=True)
    seen_targets: set = set()
    for suite in pw_results.get("suites", []):
        _walk_suite_attachments(suite, scenario_dir, seen_targets, shutil)


def _walk_suite_attachments(suite: dict, scenario_dir: Path,
                             seen_targets: set, shutil_mod) -> None:
    """Recursively descend Playwright suite tree collecting attachments."""
    for nested in suite.get("suites", []) or []:
        _walk_suite_attachments(nested, scenario_dir, seen_targets, shutil_mod)
    for spec in suite.get("specs", []) or []:
        for test in spec.get("tests", []) or []:
            for result in test.get("results", []) or []:
                for att in result.get("attachments", []) or []:
                    _harvest_one_attachment(att, scenario_dir, seen_targets, shutil_mod)


def _harvest_one_attachment(att: dict, scenario_dir: Path,
                             seen_targets: set, shutil_mod) -> None:
    name = att.get("name") or ""
    src = att.get("path") or ""
    if not name or not src:
        return
    target_name = _ATTACHMENT_TARGET_NAMES.get(name)
    if not target_name:
        return
    # If the same attachment type appears multiple times (multi-retry), keep
    # the first one — Playwright reports retries in order.
    if target_name in seen_targets:
        return
    src_path = Path(src)
    if not src_path.is_file():
        logger.debug("Attachment src missing for %s: %s", name, src)
        return
    dst = scenario_dir / target_name
    try:
        shutil_mod.copyfile(str(src_path), str(dst))
        seen_targets.add(target_name)
        logger.debug("Harvested %s → %s", src, dst)
    except Exception as exc:
        logger.warning("Could not harvest attachment %s: %s", src, exc)


def _err(code: str, message: str) -> dict:
    return {"ok": False, "error": code, "message": message}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="uat_test_runner — Execute Playwright .spec.ts tests"
    )
    parser.add_argument("--tests-dir", required=True, dest="tests_dir",
                        help="Directory containing .spec.ts files")
    parser.add_argument("--evidence-out", required=True, dest="evidence_out",
                        help="Root directory for evidence output")
    parser.add_argument("--headed", action="store_true",
                        help="Run in headed mode (default: headless)")
    parser.add_argument("--timeout-ms", type=int, default=_DEFAULT_TIMEOUT_MS,
                        dest="timeout_ms", help="Per-test timeout in ms")
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    main()
