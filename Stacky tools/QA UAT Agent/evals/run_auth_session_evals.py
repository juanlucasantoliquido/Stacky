"""
evals/run_auth_session_evals.py — Runner de evals para auth_session_factory.py.

Carga fixtures de evals/auth_session/*.json y corre cada uno contra
auth_session_factory.run_auth_session() con mocks de filesystem/playwright.

Mocking strategy:
  Los fixtures declaran "mock_*" keys que este runner convierte en patches.
  No se abre browser real — se parchean:
    - _load_existing_state  → controla si el auth file "existe/es válido"
    - _do_playwright_login  → simula login OK/FAIL sin browser real
  Los tests verifican el contrato de salida del stage.

Usage:
    cd "Tools/Stacky/Stacky tools/QA UAT Agent"
    python evals/run_auth_session_evals.py [--evals-dir evals/auth_session] [--verbose]

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
from typing import Any
from unittest.mock import patch

# Asegurar tool root en sys.path
_TOOL_ROOT = Path(__file__).parent.parent
if str(_TOOL_ROOT) not in sys.path:
    sys.path.insert(0, str(_TOOL_ROOT))

logger = logging.getLogger("stacky.qa_uat.evals.auth_session")


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


# ── Helpers de mocking ────────────────────────────────────────────────────────

def _make_load_existing_mock(fixture_input: dict):
    """Genera un mock de _load_existing_state basado en los campos mock_* del fixture."""
    exists = fixture_input.get("mock_auth_file_exists", False)
    age_s = fixture_input.get("mock_auth_file_age_s", 0)
    has_cookies = fixture_input.get("mock_auth_has_cookies", False)
    fp_matches = fixture_input.get("mock_fingerprint_matches", True)
    ttl_default = 1800

    def _mock_load(auth_file, fingerprint, ttl_s):
        if not exists:
            return {"ok": False, "reason": "AUTH_FILE_MISSING", "age_s": None, "data": None}
        if not fp_matches:
            return {"ok": False, "reason": "AUTH_FINGERPRINT_MISMATCH", "age_s": None, "data": None}
        if age_s > ttl_s:
            return {"ok": False, "reason": "AUTH_EXPIRED", "age_s": float(age_s), "data": None}
        if not has_cookies:
            return {"ok": False, "reason": "AUTH_NO_COOKIES", "age_s": float(age_s), "data": None}
        mock_data = {"cookies": [{"name": "ASP.NET_SessionId", "value": "fakesessionid"}]}
        return {"ok": True, "reason": "AUTH_VALID", "age_s": float(age_s), "data": mock_data}

    return _mock_load


def _make_pw_login_mock(fixture_input: dict):
    """Genera un mock de _do_playwright_login basado en mock_login_result del fixture."""
    login_result = fixture_input.get("mock_login_result", {"ok": True, "reason": "AUTH_LOGIN_OK", "error": None})

    def _mock_login(base_url, user, password, auth_file, fingerprint):
        # Si el login es exitoso, crear un archivo falso de storage_state
        if login_result.get("ok"):
            try:
                auth_file.parent.mkdir(parents=True, exist_ok=True)
                auth_file.write_text(
                    json.dumps({"cookies": [{"name": "ASP.NET_SessionId", "value": "newsessionid"}]}),
                    encoding="utf-8",
                )
                import time as _time
                fp_data = {
                    "fingerprint": fingerprint,
                    "user": user,
                    "base_url": base_url,
                    "created_at": _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime()),
                }
                import auth_session_factory as _asf
                _asf._FINGERPRINT_FILE.parent.mkdir(parents=True, exist_ok=True)
                _asf._FINGERPRINT_FILE.write_text(
                    json.dumps(fp_data, ensure_ascii=False, indent=2), encoding="utf-8"
                )
            except Exception:
                pass
        return login_result

    return _mock_login


def _patch_credentials(fixture_input: dict):
    """Parchea os.environ y env_preflight con las credenciales del fixture."""
    mock_creds = fixture_input.get("mock_credentials", {})
    return mock_creds


# ── Corrida de un eval ────────────────────────────────────────────────────────

def run_single_eval(fixture_path: Path) -> EvalResult:
    """Corre un único eval fixture y retorna EvalResult."""
    eval_id = fixture_path.stem
    try:
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return EvalResult(eval_id=eval_id, passed=False, failures=[f"fixture parse error: {exc}"])

    fixture_input = fixture.get("input", {})
    expected = fixture.get("expected_output", {})
    mode = fixture_input.get("mode", "normal")
    mock_creds = _patch_credentials(fixture_input)

    import auth_session_factory as asf

    load_mock = _make_load_existing_mock(fixture_input)
    login_mock = _make_pw_login_mock(fixture_input)

    # Parchar os.environ con las credenciales del fixture
    env_patch: dict = {}
    if "AGENDA_WEB_USER" in mock_creds:
        env_patch["AGENDA_WEB_USER"] = mock_creds["AGENDA_WEB_USER"]
    if "AGENDA_WEB_PASS" in mock_creds:
        env_patch["AGENDA_WEB_PASS"] = mock_creds["AGENDA_WEB_PASS"]
    if "AGENDA_WEB_BASE_URL" in mock_creds:
        env_patch["AGENDA_WEB_BASE_URL"] = mock_creds["AGENDA_WEB_BASE_URL"]

    import os

    # Guardar y sobrescribir env
    saved_env = {}
    for k, v in env_patch.items():
        saved_env[k] = os.environ.get(k)
        if v:
            os.environ[k] = v
        elif k in os.environ:
            del os.environ[k]

    failures: list[str] = []
    try:
        with patch.object(asf, "_load_existing_state", side_effect=load_mock), \
             patch.object(asf, "_do_playwright_login", side_effect=login_mock), \
             patch.object(asf, "_copy_to_evidence", return_value="/fake/evidence/auth/storage_state.json"):

            result = asf.run_auth_session(mode=mode, config=mock_creds or None)

        # Verificar campos del expected_output
        for field, exp_val in expected.items():
            if field.startswith("_"):  # comentarios
                continue
            if field.endswith("_contains"):
                # Verificación de substring
                real_field = field[:-len("_contains")]
                actual = getattr(result, real_field, None)
                if actual is None or exp_val not in str(actual):
                    failures.append(
                        f"{real_field} should contain '{exp_val}' but got: {actual!r}"
                    )
            else:
                actual = getattr(result, field, "__MISSING__")
                if actual == "__MISSING__":
                    failures.append(f"field '{field}' missing from result")
                elif actual != exp_val:
                    failures.append(
                        f"{field}: expected {exp_val!r} got {actual!r}"
                    )
    except Exception as exc:
        failures.append(f"exception during eval: {exc}")
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
    p = argparse.ArgumentParser(description="Eval runner para auth_session_factory")
    p.add_argument(
        "--evals-dir",
        default=str(Path(__file__).parent / "auth_session"),
        dest="evals_dir",
        help="Directorio de fixtures (default: evals/auth_session/)",
    )
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args()

    if args.verbose:
        logging.basicConfig(
            level=logging.DEBUG, stream=sys.stderr,
            format="%(levelname)s %(name)s: %(message)s",
        )
    else:
        logging.basicConfig(level=logging.WARNING, stream=sys.stderr)

    suite = run_all_evals(args.evals_dir)

    print(f"\n{'='*60}")
    print(f"auth_session evals: {suite.passed}/{suite.total} passed")
    if suite.failures:
        print(f"\nFAILURES ({suite.failed}):")
        for ef in suite.failures:
            print(f"  FAIL [{ef.eval_id}]:")
            for fl in ef.failures:
                print(f"    - {fl}")
    else:
        print("  All evals PASSED.")
    print(f"{'='*60}\n")

    sys.exit(0 if suite.failed == 0 else 1)


if __name__ == "__main__":
    main()
