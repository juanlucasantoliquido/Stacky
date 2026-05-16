"""
evals/run_screenshot_budget_evals.py — Runner de evals para screenshot_budget.py.

Carga fixtures de evals/screenshot_budget/*.json y corre cada uno contra
screenshot_budget.should_capture() directamente (sin mocks de filesystem).

Los fixtures son puramente unit-level: expresan una secuencia de decisiones
should_capture() y verifican el output esperado.

Usage:
    cd "Tools/Stacky/Stacky tools/QA UAT Agent"
    python evals/run_screenshot_budget_evals.py [--evals-dir evals/screenshot_budget] [--verbose]

Exit code 0 = todos los evals pasaron.
Exit code 1 = uno o más evals fallaron.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path

# Asegurar tool root en sys.path
_TOOL_ROOT = Path(__file__).parent.parent
if str(_TOOL_ROOT) not in sys.path:
    sys.path.insert(0, str(_TOOL_ROOT))

logger = logging.getLogger("stacky.qa_uat.evals.screenshot_budget")


# ── Dataclasses ────────────────────────────────────────────────────────────────

@dataclass
class EvalResult:
    eval_id: str
    passed: bool
    failures: list  # list[str]


@dataclass
class EvalSuiteResult:
    total: int
    passed: int
    failed: int
    failures: list  # list[EvalResult]


# ── Eval runner ────────────────────────────────────────────────────────────────

def run_single_eval(fixture_path: Path) -> EvalResult:
    """Corre un único eval fixture y retorna EvalResult."""
    eval_id = fixture_path.stem
    try:
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return EvalResult(eval_id=eval_id, passed=False, failures=[f"fixture parse error: {exc}"])

    fixture_input = fixture.get("input", {})
    expected = fixture.get("expected_output", {})
    assertions = fixture.get("assertions", [])

    budget_dict = fixture_input.get("budget", {})
    steps = fixture_input.get("steps", [])

    from screenshot_budget import ScreenshotBudget, should_capture

    budget = ScreenshotBudget(
        on_success_per_step=budget_dict.get("on_success_per_step", 1),
        on_failure_per_step=budget_dict.get("on_failure_per_step", 3),
        max_total_per_scenario=budget_dict.get("max_total_per_scenario", 25),
        disabled=budget_dict.get("disabled", False),
    )

    captures: list[bool] = []
    reasons: list[str] = []
    running_taken = 0

    for step in steps:
        step_ok = step.get("step_ok", True)
        capture_index = step.get("capture_index", 0)
        # Fixtures can declare "taken_before" explicitly, otherwise use running count
        taken_before = step.get("taken_before", running_taken)

        ok, reason = should_capture(budget, step_ok=step_ok, taken_so_far=taken_before,
                                    step_capture_index=capture_index)
        captures.append(ok)
        reasons.append(reason)
        if ok:
            running_taken += 1

    # Build result summary for assertion evaluation
    captured = sum(1 for c in captures if c)
    skipped = sum(1 for c in captures if not c)
    exceeded = any(r == "max_total_per_scenario_exceeded" for r in reasons)

    result = {
        "captured": captured,
        "skipped": skipped,
        "exceeded": exceeded,
        "captures": captures,
        "reasons": reasons,
    }

    # Check expected keys
    failures: list[str] = []
    for key, exp_val in expected.items():
        got = result.get(key)
        if got != exp_val:
            failures.append(f"expected[{key!r}]: expected={exp_val!r} got={got!r}")

    # Evaluate assertion strings
    ns = {
        "result": result,
        "captures": captures,
        "reasons": reasons,
        "captured": captured,
        "skipped": skipped,
        "exceeded": exceeded,
        "all": all,
        "any": any,
    }
    for assertion in assertions:
        try:
            if not eval(assertion, {"__builtins__": {}, "all": all, "any": any}, ns):  # noqa: S307
                failures.append(f"assertion failed: {assertion!r}")
        except Exception as exc:
            failures.append(f"assertion error ({assertion!r}): {exc}")

    return EvalResult(eval_id=eval_id, passed=len(failures) == 0, failures=failures)


# ── Suite runner ───────────────────────────────────────────────────────────────

def run_suite(evals_dir: Path, verbose: bool) -> EvalSuiteResult:
    fixture_paths = sorted(evals_dir.glob("*.json"))
    if not fixture_paths:
        logger.warning("No fixtures found in %s", evals_dir)
        return EvalSuiteResult(total=0, passed=0, failed=0, failures=[])

    results = []
    for fp in fixture_paths:
        r = run_single_eval(fp)
        results.append(r)
        status = "PASS" if r.passed else "FAIL"
        print(f"  [{status}] {r.eval_id}")
        if not r.passed and verbose:
            for f in r.failures:
                print(f"         {f}")

    passed = sum(1 for r in results if r.passed)
    failed = len(results) - passed
    return EvalSuiteResult(
        total=len(results), passed=passed, failed=failed,
        failures=[r for r in results if not r.passed],
    )


# ── CLI ────────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run screenshot_budget evals")
    parser.add_argument(
        "--evals-dir",
        default=str(Path(__file__).parent / "screenshot_budget"),
        help="Directory with fixture JSON files (default: evals/screenshot_budget)",
    )
    parser.add_argument("--verbose", "-v", action="store_true", default=False)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        stream=sys.stderr,
        format="%(levelname)s %(name)s: %(message)s",
    )

    evals_dir = Path(args.evals_dir)
    if not evals_dir.is_dir():
        print(f"ERROR: evals dir not found: {evals_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"\nRunning screenshot_budget evals from {evals_dir}")
    suite = run_suite(evals_dir, verbose=args.verbose)

    print(f"\nResults: {suite.passed}/{suite.total} passed", end="")
    if suite.failed > 0:
        print(f" — {suite.failed} FAILED")
        if not args.verbose:
            print("  Re-run con --verbose para ver detalles.")
        for fr in suite.failures:
            print(f"\n  FAILED: {fr.eval_id}")
            for f in fr.failures:
                print(f"    {f}")
        sys.exit(1)
    else:
        print(" — ALL PASSED")
        sys.exit(0)


if __name__ == "__main__":
    main()
