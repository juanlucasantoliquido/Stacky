"""
evals/run_rerun_guard_evals.py — Runner de evals para rerun_guard.py.

Carga fixtures de evals/rerun_guard/*.json y corre cada uno contra
rerun_guard.run_rerun_guard() con mocks de filesystem.

Mocking strategy:
  Los fixtures declaran "mock_latest" (o null) que este runner inyecta vía
  monkeypatching de _read_latest_result. Las fechas con __NOW_MINUS_<N>S__
  se resuelven en tiempo de ejecución para que los asserts de TTL sean estables.
  No se toca el filesystem real de evidence/.

Usage:
    cd "Tools/Stacky/Stacky tools/QA UAT Agent"
    python evals/run_rerun_guard_evals.py [--evals-dir evals/rerun_guard] [--verbose]

Exit code 0 = todos los evals pasaron.
Exit code 1 = uno o más evals fallaron.
"""
from __future__ import annotations

import argparse
import datetime
import json
import logging
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

# Asegurar tool root en sys.path
_TOOL_ROOT = Path(__file__).parent.parent
if str(_TOOL_ROOT) not in sys.path:
    sys.path.insert(0, str(_TOOL_ROOT))

logger = logging.getLogger("stacky.qa_uat.evals.rerun_guard")

# Regex para detectar marcadores de tiempo dinámico en fixtures
_NOW_MINUS_RE = re.compile(r"__NOW_MINUS_(\d+)S__")


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


# ── Helpers de resolución de fixtures ─────────────────────────────────────────

def _resolve_timestamps(obj, now_utc: datetime.datetime):
    """Reemplaza __NOW_MINUS_<N>S__ por un ISO 8601 UTC real calculado desde now_utc.

    Trabaja recursivamente sobre dicts y listas.
    """
    if isinstance(obj, str):
        m = _NOW_MINUS_RE.fullmatch(obj.strip())
        if m:
            delta_s = int(m.group(1))
            resolved = now_utc - datetime.timedelta(seconds=delta_s)
            return resolved.isoformat().replace("+00:00", "Z")
        return obj
    if isinstance(obj, dict):
        return {k: _resolve_timestamps(v, now_utc) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_resolve_timestamps(item, now_utc) for item in obj]
    return obj


# ── Mock de _read_latest_result ────────────────────────────────────────────────

def _make_latest_mock(mock_latest: dict | None):
    """Retorna una función que simula _read_latest_result para el ticket."""
    def _mock_read(ticket_id: int, evidence_root=None) -> dict:
        if mock_latest is None:
            return {}
        return mock_latest
    return _mock_read


# ── Corrida de un eval ────────────────────────────────────────────────────────

def run_single_eval(fixture_path: Path) -> EvalResult:
    """Corre un único eval fixture y retorna EvalResult."""
    eval_id = fixture_path.stem
    try:
        raw = fixture_path.read_text(encoding="utf-8")
        fixture = json.loads(raw)
    except Exception as exc:
        return EvalResult(eval_id=eval_id, passed=False, failures=[f"fixture parse error: {exc}"])

    now_utc = datetime.datetime.now(datetime.timezone.utc)

    # Resolver marcadores de tiempo en todo el fixture
    fixture = _resolve_timestamps(fixture, now_utc)

    fixture_input = fixture.get("input", {})
    expected = fixture.get("expected_output", {})

    ticket_id = fixture_input.get("ticket_id", 999)
    force_rerun = fixture_input.get("force_rerun", False)
    current_fingerprint = fixture_input.get("current_fingerprint")
    mock_latest = fixture_input.get("mock_latest")  # None o dict resuelto
    mock_cooldown_ttl_s = fixture_input.get("mock_cooldown_ttl_s")

    import rerun_guard as rg

    latest_mock = _make_latest_mock(mock_latest)

    # Parchar QA_UAT_RERUN_COOLDOWN_S si el fixture lo especifica
    saved_env: dict[str, str | None] = {}
    if mock_cooldown_ttl_s is not None:
        saved_env["QA_UAT_RERUN_COOLDOWN_S"] = os.environ.get("QA_UAT_RERUN_COOLDOWN_S")
        os.environ["QA_UAT_RERUN_COOLDOWN_S"] = str(mock_cooldown_ttl_s)

    failures: list[str] = []
    try:
        with patch.object(rg, "_read_latest_result", side_effect=latest_mock):
            result = rg.run_rerun_guard(
                ticket_id=ticket_id,
                force_rerun=force_rerun,
                current_fingerprint=current_fingerprint,
            )

        # Verificar campos del expected_output
        for field, exp_val in expected.items():
            if field.startswith("_"):  # comentarios en el fixture
                continue
            if field.endswith("_contains"):
                real_field = field[: -len("_contains")]
                actual = getattr(result, real_field, None)
                if actual is None or str(exp_val) not in str(actual):
                    failures.append(
                        f"{real_field} should contain '{exp_val}' but got: {actual!r}"
                    )
            else:
                actual = getattr(result, field, "__MISSING__")
                if actual == "__MISSING__":
                    failures.append(f"campo '{field}' ausente en el resultado")
                elif actual != exp_val:
                    failures.append(f"{field}: esperado {exp_val!r}, obtenido {actual!r}")

        # Correr asserts declarativos del fixture (expresiones Python evaluadas)
        for assertion_str in fixture.get("assertions", []):
            try:
                # Variables disponibles en el assert: 'result'
                if not eval(assertion_str, {"result": result}):  # noqa: S307
                    failures.append(f"assertion falló: {assertion_str!r}")
            except Exception as exc:
                failures.append(f"assertion error ({assertion_str!r}): {exc}")

    except Exception as exc:
        failures.append(f"excepción durante eval: {exc}")
    finally:
        # Restaurar env
        for k, old_val in saved_env.items():
            if old_val is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = old_val

    return EvalResult(eval_id=eval_id, passed=len(failures) == 0, failures=failures)


# ── Suite ─────────────────────────────────────────────────────────────────────

def run_all_evals(evals_dir: str) -> EvalSuiteResult:
    eval_path = Path(evals_dir)
    fixtures = sorted(eval_path.glob("*.json"))
    if not fixtures:
        logger.warning("No se encontraron fixtures en %s", evals_dir)
        return EvalSuiteResult(total=0, passed=0, failed=0, failures=[])

    results = [run_single_eval(f) for f in fixtures]
    passed = sum(1 for r in results if r.passed)
    failed_results = [r for r in results if not r.passed]

    return EvalSuiteResult(
        total=len(results),
        passed=passed,
        failed=len(failed_results),
        failures=failed_results,
    )


# ── CLI ────────────────────────────────────────────────────────────────────────

def main() -> None:
    p = argparse.ArgumentParser(description="Eval runner para rerun_guard.py")
    p.add_argument(
        "--evals-dir",
        default=str(Path(__file__).parent / "rerun_guard"),
        dest="evals_dir",
        help="Directorio de fixtures (default: evals/rerun_guard/)",
    )
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args()

    if args.verbose:
        logging.basicConfig(
            level=logging.DEBUG,
            stream=sys.stderr,
            format="%(levelname)s %(name)s: %(message)s",
        )
    else:
        logging.basicConfig(level=logging.WARNING, stream=sys.stderr)

    suite = run_all_evals(args.evals_dir)

    print(f"\n{'=' * 60}")
    print(f"rerun_guard evals: {suite.passed}/{suite.total} passed")
    if suite.failures:
        print(f"\nFAILURES ({suite.failed}):")
        for ef in suite.failures:
            print(f"  FAIL [{ef.eval_id}]:")
            for fl in ef.failures:
                print(f"    - {fl}")
    else:
        print("  Todos los evals PASARON.")
    print(f"{'=' * 60}\n")

    sys.exit(0 if suite.failed == 0 else 1)


if __name__ == "__main__":
    main()
