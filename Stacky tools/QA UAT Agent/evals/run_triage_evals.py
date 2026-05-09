"""
evals/run_triage_evals.py — Sprint 6.2: Eval runner for failure_triage.py.

Loads eval fixtures from evals/qa_uat_triage/ and runs each through
failure_triage.run_failure_triage(), then asserts expected fields.

Usage:
    python evals/run_triage_evals.py [--evals-dir <path>] [--verbose]

Exit code 0 = all evals passed.
Exit code 1 = one or more evals failed.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path

# Ensure tool root on sys.path (evals/ lives one level below tool root)
_TOOL_ROOT = Path(__file__).parent.parent
if str(_TOOL_ROOT) not in sys.path:
    sys.path.insert(0, str(_TOOL_ROOT))

logger = logging.getLogger("stacky.qa_uat.evals.triage")


# ── Dataclasses ────────────────────────────────────────────────────────────────

@dataclass
class EvalResult:
    eval_id: str
    passed: bool
    failures: list   # list of str describing field mismatches


@dataclass
class EvalSuiteResult:
    total: int
    passed: int
    failed: int
    failures: list   # list of EvalResult where passed=False


# ── Eval runner ────────────────────────────────────────────────────────────────

def run_all_evals(evals_dir: str) -> EvalSuiteResult:
    """
    Load all .json eval fixtures from evals_dir and run each through triage.

    Returns EvalSuiteResult with total, passed, failed counts and failure details.
    """
    from failure_triage import run_failure_triage

    eval_path = Path(evals_dir)
    fixtures = sorted(eval_path.glob("*.json"))

    if not fixtures:
        logger.warning("run_triage_evals: no eval fixtures found in %s", evals_dir)
        return EvalSuiteResult(total=0, passed=0, failed=0, failures=[])

    results: list[EvalResult] = []

    for fixture_path in fixtures:
        result = _run_single_eval(fixture_path, run_failure_triage)
        results.append(result)

    total   = len(results)
    passed  = sum(1 for r in results if r.passed)
    failed  = total - passed
    failures = [r for r in results if not r.passed]

    return EvalSuiteResult(
        total=total,
        passed=passed,
        failed=failed,
        failures=failures,
    )


def _run_single_eval(fixture_path: Path, run_failure_triage_fn) -> EvalResult:
    """Run a single eval fixture through triage and compare against expected."""
    eval_id = fixture_path.stem

    try:
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return EvalResult(
            eval_id=eval_id,
            passed=False,
            failures=[f"could not load fixture: {exc}"],
        )

    inp = fixture.get("input", {})
    expected = fixture.get("expected", {})

    try:
        triage = run_failure_triage_fn(
            ticket_id=inp.get("ticket_id", 0),
            run_id=inp.get("run_id", "eval-run"),
            result_json=inp.get("result_json", {}),
            execution_log=inp.get("execution_log") or [],
            runner_classification=inp.get("runner_classification"),
            exec_logger=None,
            evidence_dir=None,   # no disk writes during evals
        )
    except Exception as exc:
        return EvalResult(
            eval_id=eval_id,
            passed=False,
            failures=[f"run_failure_triage raised exception: {exc}"],
        )

    # ── Compare against expected ──────────────────────────────────────────────
    field_failures: list[str] = []

    # verdict
    exp_verdict = expected.get("verdict")
    if exp_verdict and triage.verdict != exp_verdict:
        field_failures.append(
            f"verdict: expected={exp_verdict!r}, got={triage.verdict!r}"
        )

    # category
    if "category" in expected:
        exp_cat = expected["category"]
        if triage.category != exp_cat:
            field_failures.append(
                f"category: expected={exp_cat!r}, got={triage.category!r}"
            )

    # reason (optional)
    if "reason" in expected and expected["reason"] is not None:
        exp_reason = expected["reason"]
        if triage.reason != exp_reason:
            field_failures.append(
                f"reason: expected={exp_reason!r}, got={triage.reason!r}"
            )

    # owner
    if "owner" in expected:
        exp_owner = expected["owner"]
        if triage.owner != exp_owner:
            field_failures.append(
                f"owner: expected={exp_owner!r}, got={triage.owner!r}"
            )

    # min_confidence
    if "min_confidence" in expected:
        min_conf = expected["min_confidence"]
        if triage.confidence < min_conf:
            field_failures.append(
                f"confidence: expected>={min_conf}, got={triage.confidence:.3f}"
            )

    # evidence is non-empty
    if not triage.evidence:
        field_failures.append("evidence: must be non-empty list")

    # owner is set
    if not triage.owner:
        field_failures.append("owner: must not be empty")

    # next_action is non-trivial
    if not triage.next_action or len(triage.next_action) < 10:
        field_failures.append(
            f"next_action: must have len>=10, got={triage.next_action!r}"
        )

    passed = len(field_failures) == 0
    return EvalResult(eval_id=eval_id, passed=passed, failures=field_failures)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="run_triage_evals — Sprint 6.2 eval suite runner"
    )
    parser.add_argument(
        "--evals-dir",
        default=str(Path(__file__).parent / "qa_uat_triage"),
        help="Directory containing eval fixtures (.json)"
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, stream=sys.stderr)
    else:
        logging.basicConfig(level=logging.INFO, stream=sys.stderr)

    suite = run_all_evals(args.evals_dir)

    # ── Print summary ─────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"Triage Eval Suite — {suite.total} total, {suite.passed} passed, {suite.failed} failed")
    print(f"{'='*60}")

    if suite.failures:
        for r in suite.failures:
            print(f"\nFAIL: {r.eval_id}")
            for f in r.failures:
                print(f"  - {f}")
    else:
        print("All evals PASSED.")

    print(f"{'='*60}\n")

    # Machine-readable summary
    summary = {
        "ok": suite.failed == 0,
        "total": suite.total,
        "passed": suite.passed,
        "failed": suite.failed,
        "failures": [
            {"eval_id": r.eval_id, "failures": r.failures}
            for r in suite.failures
        ],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    sys.exit(0 if suite.failed == 0 else 1)


if __name__ == "__main__":
    main()
