"""
evals/run_deployment_fingerprint_evals.py — Runner de evals para deployment_fingerprint.py.

Valida la función resolve_expected_build() (resolver de ticket_config.json + env var)
y la función check_deployment_fingerprint() con fuentes mockeadas.

Fixture schema:
  input.ticket_id          : int
  input.ticket_config      : dict | null — contenido del ticket_config.json a escribir
  input.env_override       : str | null — valor JSON para QA_UAT_EXPECTED_BUILD
  input.mock_active        : dict | null — {build_id, commit, branch} que simula la fuente
  input.mode               : str — "publish" | "dry-run" (default: "dry-run")
  expected_output          : dict de campos esperados en el resultado
  assertions               : list[str] — expresiones Python evaluadas contra `result`

Test types:
  - Si assertions usan "result is None" → test de resolve_expected_build()
  - Si expected_output tiene "decision" → test de check_deployment_fingerprint()
  - Si expected_output tiene "commit" / "build_id" → test de resolve_expected_build()

Usage:
    cd "Tools/Stacky/Stacky tools/QA UAT Agent"
    python evals/run_deployment_fingerprint_evals.py [--evals-dir evals/deployment_fingerprint] [--verbose]

Exit code 0 = todos los evals pasaron.
Exit code 1 = uno o más fallaron.
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

_TOOL_ROOT = Path(__file__).parent.parent
if str(_TOOL_ROOT) not in sys.path:
    sys.path.insert(0, str(_TOOL_ROOT))

logger = logging.getLogger("stacky.qa_uat.evals.deployment_fingerprint")

_ENV_OVERRIDE_KEY = "QA_UAT_EXPECTED_BUILD"


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

    ticket_id = fixture_input.get("ticket_id", 0)
    ticket_config = fixture_input.get("ticket_config")
    env_override = fixture_input.get("env_override")
    mock_active = fixture_input.get("mock_active")
    mode = fixture_input.get("mode", "dry-run")

    # Determine which function to test based on expected keys
    test_resolve_only = (
        "decision" not in expected
        and not any("decision" in a for a in assertions)
    )

    original_env = os.environ.get(_ENV_OVERRIDE_KEY)
    try:
        # Set env override if provided
        if env_override is not None:
            os.environ[_ENV_OVERRIDE_KEY] = env_override
        elif _ENV_OVERRIDE_KEY in os.environ:
            del os.environ[_ENV_OVERRIDE_KEY]

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)

            # Write ticket_config.json if provided
            if ticket_config is not None:
                ticket_dir = tmp_root / str(ticket_id)
                ticket_dir.mkdir(parents=True, exist_ok=True)
                (ticket_dir / "ticket_config.json").write_text(
                    json.dumps(ticket_config, ensure_ascii=False),
                    encoding="utf-8",
                )

            from deployment_fingerprint import resolve_expected_build, check_deployment_fingerprint

            if test_resolve_only:
                # Test resolve_expected_build only
                result = resolve_expected_build(
                    ticket_id=ticket_id,
                    evidence_root=tmp_root,
                )
            else:
                # Test check_deployment_fingerprint with mocked probing
                resolved = resolve_expected_build(
                    ticket_id=ticket_id,
                    evidence_root=tmp_root,
                )

                if mock_active is not None:
                    # Monkeypatch _probe_sources to return mock_active
                    import deployment_fingerprint as _df_mod
                    original_probe = _df_mod._probe_sources

                    def _mock_probe(base_url, sources):
                        return (mock_active, "mock_source", "")

                    _df_mod._probe_sources = _mock_probe
                    try:
                        fp_result = check_deployment_fingerprint(
                            ticket_id=ticket_id,
                            expected=resolved,
                            base_url="http://mock.local/",
                            mode=mode,
                        )
                    finally:
                        _df_mod._probe_sources = original_probe
                else:
                    # No mock — probe will fail (simulate unreachable server)
                    fp_result = check_deployment_fingerprint(
                        ticket_id=ticket_id,
                        expected=resolved,
                        base_url="http://127.0.0.1:19999/unreachable/",
                        mode=mode,
                    )

                result = fp_result.to_dict()

    except Exception as exc:
        return EvalResult(eval_id=eval_id, passed=False, failures=[f"module raised: {exc}"])
    finally:
        if original_env is not None:
            os.environ[_ENV_OVERRIDE_KEY] = original_env
        elif _ENV_OVERRIDE_KEY in os.environ:
            del os.environ[_ENV_OVERRIDE_KEY]

    return _check_assertions(eval_id, result, expected, assertions)


def _check_assertions(
    eval_id: str,
    result,
    expected: dict,
    assertions: list,
) -> EvalResult:
    failures: list[str] = []

    if isinstance(result, dict):
        for key, exp_val in expected.items():
            got = result.get(key)
            if got != exp_val:
                failures.append(f"expected[{key!r}]: expected={exp_val!r} got={got!r}")

    ns = {"result": result}
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
    parser = argparse.ArgumentParser(description="Run deployment_fingerprint evals")
    parser.add_argument(
        "--evals-dir",
        default=str(Path(__file__).parent / "deployment_fingerprint"),
        help="Directory with fixture JSON files (default: evals/deployment_fingerprint)",
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

    print(f"\nRunning deployment_fingerprint evals from {evals_dir}")
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
