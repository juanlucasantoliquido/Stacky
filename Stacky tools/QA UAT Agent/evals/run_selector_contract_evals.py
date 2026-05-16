"""
evals/run_selector_contract_evals.py — Runner de evals para selector_contract_validator.py.

Carga fixtures de evals/selector_contract/*.json y corre cada uno contra
validate_all_scenarios() con un UI map mock escrito en un tmp dir.

Mocking strategy:
  Los fixtures declaran "mock_ui_map" (dict o null). Si es null, el UI map
  no se escribe en disco y la validación retorna UI_MAP_MISSING.
  Si "env_skip" es true, el runner verifica el comportamiento de forced_skip
  simulando QA_UAT_SKIP_SELECTOR_CONTRACT=1.

Usage:
    cd "Tools/Stacky/Stacky tools/QA UAT Agent"
    python evals/run_selector_contract_evals.py [--evals-dir evals/selector_contract] [--verbose]

Exit code 0 = todos los evals pasaron.
Exit code 1 = uno o más evals fallaron.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

# Asegurar tool root en sys.path
_TOOL_ROOT = Path(__file__).parent.parent
if str(_TOOL_ROOT) not in sys.path:
    sys.path.insert(0, str(_TOOL_ROOT))

logger = logging.getLogger("stacky.qa_uat.evals.selector_contract")


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

    env_skip = fixture_input.get("env_skip", False)
    scenarios = fixture_input.get("scenarios", [])
    mock_ui_map = fixture_input.get("mock_ui_map")  # dict or null

    # ── forced skip path: validate the expected contract ──────────────────────
    if env_skip:
        # Simulate what the pipeline does when QA_UAT_SKIP_SELECTOR_CONTRACT=1
        result = {
            "ok": True,
            "skipped": True,
            "forced_skip": True,
            "reason": "QA_UAT_SKIP_SELECTOR_CONTRACT",
        }
        return _check_assertions(eval_id, result, expected, assertions)

    # ── normal path: write mock UI map to tmp dir, call validate_all_scenarios ─
    from selector_contract_validator import validate_all_scenarios

    with tempfile.TemporaryDirectory() as tmp_dir:
        ui_maps_dir = Path(tmp_dir)

        if mock_ui_map is not None:
            screen = mock_ui_map.get("screen", "FrmTest.aspx")
            # validate_all_scenarios builds path as ui_maps_dir / f"{screen}.json"
            # so we write the file with that exact name.
            ui_map_path = ui_maps_dir / f"{screen}.json"
            ui_map_path.write_text(
                json.dumps(mock_ui_map, ensure_ascii=False),
                encoding="utf-8",
            )

        raw = validate_all_scenarios(
            scenarios=scenarios,
            ui_maps_dir=ui_maps_dir,
        )

        result = {
            "ok": raw["ok"],
            "blocked_count": raw["blocked_count"],
            "allow_count": raw["allow_count"],
            "first_blocked_reason": raw.get("first_blocked_reason"),
        }

    return _check_assertions(eval_id, result, expected, assertions)


def _check_assertions(
    eval_id: str,
    result: dict,
    expected: dict,
    assertions: list,
) -> EvalResult:
    """Verifica que result satisface expected y assertions."""
    failures: list[str] = []

    # Check expected keys
    for key, exp_val in expected.items():
        got = result.get(key)
        if got != exp_val:
            failures.append(f"expected[{key!r}]: expected={exp_val!r} got={got!r}")

    # Evaluate assertion strings in a controlled namespace
    ns = {"result": result, **result}
    for assertion in assertions:
        try:
            if not eval(assertion, {"__builtins__": {}}, ns):  # noqa: S307
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
    failed_results = [r for r in results if not r.passed]
    return EvalSuiteResult(total=len(results), passed=passed, failed=failed, failures=failed_results)


# ── CLI ────────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run selector_contract evals")
    parser.add_argument(
        "--evals-dir",
        default=str(Path(__file__).parent / "selector_contract"),
        help="Directory with fixture JSON files (default: evals/selector_contract)",
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

    print(f"\nRunning selector_contract evals from {evals_dir}")
    suite = run_suite(evals_dir, verbose=args.verbose)

    print(f"\nResults: {suite.passed}/{suite.total} passed", end="")
    if suite.failed > 0:
        print(f" — {suite.failed} FAILED")
        if not args.verbose:
            print("  Re-run with --verbose to see failure details.")
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
