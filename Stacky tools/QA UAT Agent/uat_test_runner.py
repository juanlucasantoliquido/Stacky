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

_TOOL_VERSION = "1.0.0"
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
) -> dict:
    """Core logic — callable from tests with subprocess mocking."""
    started = time.time()

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

    runs = []
    pass_count = 0
    fail_count = 0
    blocked_count = 0

    for spec_file in spec_files:
        scenario_id = _scenario_id_from_filename(spec_file.name)
        scenario_dir = evidence_out / scenario_id
        scenario_dir.mkdir(parents=True, exist_ok=True)

        run_result = _run_single_spec(
            spec_file=spec_file,
            scenario_id=scenario_id,
            scenario_dir=scenario_dir,
            ticket_id=ticket_id,
            headed=headed,
            timeout_ms=timeout_ms,
            verbose=verbose,
        )
        runs.append(run_result)
        status = run_result.get("status", "blocked")
        if status == "pass":
            pass_count += 1
        elif status == "fail":
            fail_count += 1
        else:
            blocked_count += 1

    return {
        "ok": True,
        "ticket_id": ticket_id,
        "total": len(runs),
        "pass": pass_count,
        "fail": fail_count,
        "blocked": blocked_count,
        "runs": runs,
        "meta": {
            "tool": "uat_test_runner",
            "version": _TOOL_VERSION,
            "duration_ms": int((time.time() - started) * 1000),
        },
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
) -> dict:
    """Run a single .spec.ts and return run result dict."""
    started = time.time()
    headless_flag = os.environ.get("STACKY_QA_UAT_HEADLESS", "1" if not headed else "0")

    env = {**os.environ, "STACKY_QA_UAT_HEADLESS": headless_flag}

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
        "--reporter=json",
        f"--timeout={timeout_ms}",
    ]
    if config_path.is_file():
        cmd += ["--config", str(config_path)]

    logger.debug("Running: %s", " ".join(cmd))

    # On Windows, .cmd/.ps1 files require shell=True (subprocess can't exec them directly)
    use_shell = _sys.platform == "win32"
    cmd_arg = subprocess.list2cmdline(cmd) if use_shell else cmd

    try:
        proc = subprocess.run(
            cmd_arg,
            capture_output=True,
            text=True,
            env=env,
            timeout=timeout_ms * 5 // 1000 + 60,  # global timeout = 5x individual + 60s overhead
            cwd=str(tool_dir),
            shell=use_shell,
        )
    except subprocess.TimeoutExpired:
        duration = int((time.time() - started) * 1000)
        return {
            "scenario_id": scenario_id,
            "spec_file": str(spec_file),
            "status": "blocked",
            "reason": "TIMEOUT",
            "duration_ms": duration,
            "artifacts": _collect_artifacts(scenario_dir),
            "raw_stdout": "",
            "raw_stderr": "Process timed out",
        }
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

    duration = int((time.time() - started) * 1000)
    stdout = proc.stdout or ""
    stderr = proc.stderr or ""

    # Parse playwright JSON reporter output
    pw_results = _parse_playwright_json_output(stdout)
    assertion_failures = _extract_assertion_failures(pw_results, stderr)

    # Determine status
    if proc.returncode == 0:
        status = "pass"
    elif assertion_failures:
        status = "fail"
    elif proc.returncode != 0 and ("Error:" in stderr or "error:" in stderr.lower()):
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

    return result


# ── Helpers ───────────────────────────────────────────────────────────────────

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
    """Try to parse Playwright's JSON reporter output."""
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

    artifacts["screenshots"].sort()
    return artifacts


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
