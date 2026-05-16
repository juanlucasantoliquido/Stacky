"""
evals/run_scenario_compiler_evals.py — Runner de evals para uat_scenario_compiler.py v1.3.0.

Valida la emisión dual de campos v2 (screen + steps[].alias_semantic) junto
con el formato legacy (pantalla + pasos). También valida el override
QA_UAT_COMPILER_LEGACY_ONLY=1 y el comportamiento ante pantallas irresoluble.

Fixture schema:
  input.ticket_json       : ticket JSON válido con ok=true y plan_pruebas
  input.ui_aliases        : list[str] | null — aliases disponibles en el UI map
  input.legacy_only_env   : bool — si true, simula QA_UAT_COMPILER_LEGACY_ONLY=1
  expected_output         : dict de campos esperados en el resultado
  assertions              : list[str] — expresiones Python evaluadas contra `result`

Usage:
    cd "Tools/Stacky/Stacky tools/QA UAT Agent"
    python evals/run_scenario_compiler_evals.py [--evals-dir evals/scenario_compiler] [--verbose]

Exit code 0 = todos los evals pasaron.
Exit code 1 = uno o más fallaron.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path

_TOOL_ROOT = Path(__file__).parent.parent
if str(_TOOL_ROOT) not in sys.path:
    sys.path.insert(0, str(_TOOL_ROOT))

logger = logging.getLogger("stacky.qa_uat.evals.scenario_compiler")


@dataclass
class EvalResult:
    eval_id: str
    passed: bool
    failures: list


@dataclass
class EvalSuiteResult:
    total: int
    passed: int
    failed: int
    failures: list


def run_single_eval(fixture_path: Path) -> EvalResult:
    eval_id = fixture_path.stem
    try:
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return EvalResult(eval_id=eval_id, passed=False, failures=[f"fixture parse error: {exc}"])

    fixture_input = fixture.get("input", {})
    expected = fixture.get("expected_output", {})
    assertions = fixture.get("assertions", [])

    ticket_json = fixture_input.get("ticket_json", {})
    ui_aliases = fixture_input.get("ui_aliases")  # list or null
    legacy_only = fixture_input.get("legacy_only_env", False)

    # Set / clear env var for legacy mode
    env_key = "QA_UAT_COMPILER_LEGACY_ONLY"
    original_env = os.environ.get(env_key)
    try:
        if legacy_only:
            os.environ[env_key] = "1"
        elif env_key in os.environ:
            del os.environ[env_key]

        from uat_scenario_compiler import run as compiler_run
        result = compiler_run(
            ticket_json=ticket_json,
            ui_aliases=ui_aliases or None,
            verbose=False,
        )
    except Exception as exc:
        return EvalResult(eval_id=eval_id, passed=False, failures=[f"compiler raised: {exc}"])
    finally:
        # Restore env
        if original_env is not None:
            os.environ[env_key] = original_env
        elif env_key in os.environ:
            del os.environ[env_key]

    return _check_assertions(eval_id, result, expected, assertions)


def _check_assertions(
    eval_id: str,
    result: dict,
    expected: dict,
    assertions: list,
) -> EvalResult:
    failures: list[str] = []

    for key, exp_val in expected.items():
        got = result.get(key)
        if got != exp_val:
            failures.append(f"expected[{key!r}]: expected={exp_val!r} got={got!r}")

    ns = {
        "result": result,
        "any": any, "all": all, "len": len,
        "isinstance": isinstance, "list": list, "dict": dict,
    }
    if isinstance(result, dict):
        ns.update(result)
    for assertion in assertions:
        try:
            if not eval(assertion, {"__builtins__": {}}, ns):  # noqa: S307
                failures.append(f"assertion failed: {assertion!r}")
        except Exception as exc:
            failures.append(f"assertion error ({assertion!r}): {exc}")

    return EvalResult(eval_id=eval_id, passed=len(failures) == 0, failures=failures)


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


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run scenario_compiler evals")
    parser.add_argument(
        "--evals-dir",
        default=str(Path(__file__).parent / "scenario_compiler"),
        help="Directory with fixture JSON files (default: evals/scenario_compiler)",
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

    print(f"\nRunning scenario_compiler evals from {evals_dir}")
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
