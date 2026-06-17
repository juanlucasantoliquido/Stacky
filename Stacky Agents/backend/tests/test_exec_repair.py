"""Tests E1.1 — Gate + pase correctivo ante fallo ejecutable.

TDD: tests antes de la implementación.
Mock del runner y de E0.1 verify.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_BACKEND = Path(__file__).parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


@pytest.fixture(autouse=True)
def reset_cache():
    from services import exec_verification as _ev
    _ev._CACHE.clear()
    yield
    _ev._CACHE.clear()


def _make_hard_failed(name="PyCompile", detail="SyntaxError: bad syntax"):
    from services.exec_verification import VerifierResult
    return VerifierResult(name=name, status="hard", detail=detail)


# ── 1. Flag OFF → not attempted ──────────────────────────────────────────────

def test_flag_off_not_attempted(tmp_path):
    from config import Config
    from harness.exec_repair import attempt_exec_repair
    with patch.object(Config, "STACKY_EXEC_REPAIR_ENABLED", False):
        result = attempt_exec_repair(
            run_id=1,
            workspace=str(tmp_path),
            runtime="claude_code_cli",
            hard_failed=[_make_hard_failed()],
            budget_remaining=300,
            send_fn=lambda msg: "fixed output",
            changed_files=["test_foo.py"],
        )
    assert result.attempted is False
    assert result.skip_reason == "flag OFF"


# ── 2. Runtime sin resume → not attempted ────────────────────────────────────

def test_no_resume_runtime_not_attempted(tmp_path):
    from config import Config
    from harness.exec_repair import attempt_exec_repair
    with patch.object(Config, "STACKY_EXEC_REPAIR_ENABLED", True), \
         patch.object(Config, "STACKY_EXEC_REPAIR_MAX_RETRIES", 1):
        result = attempt_exec_repair(
            run_id=1,
            workspace=str(tmp_path),
            runtime="github_copilot",  # supports_resume=False
            hard_failed=[_make_hard_failed()],
            budget_remaining=300,
            send_fn=lambda msg: "fixed",
            changed_files=["test_foo.py"],
        )
    assert result.attempted is False
    assert "supports_resume" in (result.skip_reason or "")


# ── 3. send_fn None → not attempted ─────────────────────────────────────────

def test_no_send_fn_not_attempted(tmp_path):
    from config import Config
    from harness.exec_repair import attempt_exec_repair
    with patch.object(Config, "STACKY_EXEC_REPAIR_ENABLED", True), \
         patch.object(Config, "STACKY_EXEC_REPAIR_MAX_RETRIES", 1):
        result = attempt_exec_repair(
            run_id=1,
            workspace=str(tmp_path),
            runtime="claude_code_cli",
            hard_failed=[_make_hard_failed()],
            budget_remaining=300,
            send_fn=None,
            changed_files=["test_foo.py"],
        )
    assert result.attempted is False
    assert "send_fn" in (result.skip_reason or "")


# ── 4. Presupuesto agotado → not attempted ───────────────────────────────────

def test_budget_exhausted_not_attempted(tmp_path):
    from config import Config
    from harness.exec_repair import attempt_exec_repair
    with patch.object(Config, "STACKY_EXEC_REPAIR_ENABLED", True), \
         patch.object(Config, "STACKY_EXEC_REPAIR_MAX_RETRIES", 1):
        result = attempt_exec_repair(
            run_id=1,
            workspace=str(tmp_path),
            runtime="claude_code_cli",
            hard_failed=[_make_hard_failed()],
            budget_remaining=0,
            send_fn=lambda msg: "fixed",
            changed_files=["test_foo.py"],
        )
    assert result.attempted is False
    assert "presupuesto" in (result.skip_reason or "").lower()


# ── 5. Sin hard_failed → not attempted ──────────────────────────────────────

def test_no_hard_failed_not_attempted(tmp_path):
    from config import Config
    from harness.exec_repair import attempt_exec_repair
    with patch.object(Config, "STACKY_EXEC_REPAIR_ENABLED", True), \
         patch.object(Config, "STACKY_EXEC_REPAIR_MAX_RETRIES", 1):
        result = attempt_exec_repair(
            run_id=1,
            workspace=str(tmp_path),
            runtime="claude_code_cli",
            hard_failed=[],
            budget_remaining=300,
            send_fn=lambda msg: "output",
            changed_files=["foo.py"],
        )
    assert result.attempted is False
    assert "hard_failed" in (result.skip_reason or "")


# ── 6. Recuperación exitosa → recovered=True ────────────────────────────────

def test_recovery_success(tmp_path):
    from config import Config
    from harness.exec_repair import attempt_exec_repair
    from services.exec_verification import VerificationReport

    messages_sent = []

    def mock_send(msg: str) -> str:
        messages_sent.append(msg)
        return "fixed output"

    # Mock de la re-verificación que devuelve passed=True
    mock_report = VerificationReport(passed=True, ran=["PyCompile"])

    with patch.object(Config, "STACKY_EXEC_REPAIR_ENABLED", True), \
         patch.object(Config, "STACKY_EXEC_REPAIR_MAX_RETRIES", 1), \
         patch("services.exec_verification.verify", return_value=mock_report), \
         patch("services.exec_verification.invalidate_cache"):
        result = attempt_exec_repair(
            run_id=42,
            workspace=str(tmp_path),
            runtime="claude_code_cli",
            hard_failed=[_make_hard_failed("PyCompile", "SyntaxError at line 5")],
            budget_remaining=300,
            send_fn=mock_send,
            changed_files=["bad.py"],
        )

    assert result.attempted is True
    assert result.recovered is True
    assert "PyCompile" in result.failed_before
    assert len(messages_sent) == 1
    # El mensaje debe contener excerpt del fallo
    assert "PyCompile" in messages_sent[0]
    assert "SyntaxError at line 5" in messages_sent[0]


# ── 7. No recuperado → recovered=False ──────────────────────────────────────

def test_recovery_failure(tmp_path):
    from config import Config
    from harness.exec_repair import attempt_exec_repair
    from services.exec_verification import VerificationReport, VerifierResult

    # Re-verificación también falla
    mock_report = VerificationReport(
        passed=False,
        ran=["PyCompile"],
        hard_failed=[VerifierResult(name="PyCompile", status="hard", detail="still broken")],
    )

    with patch.object(Config, "STACKY_EXEC_REPAIR_ENABLED", True), \
         patch.object(Config, "STACKY_EXEC_REPAIR_MAX_RETRIES", 1), \
         patch("services.exec_verification.verify", return_value=mock_report), \
         patch("services.exec_verification.invalidate_cache"):
        result = attempt_exec_repair(
            run_id=99,
            workspace=str(tmp_path),
            runtime="claude_code_cli",
            hard_failed=[_make_hard_failed()],
            budget_remaining=300,
            send_fn=lambda msg: "still broken",
            changed_files=["bad.py"],
        )

    assert result.attempted is True
    assert result.recovered is False


# ── 8. send_fn lanza excepción → attempted=True, recovered=False ─────────────

def test_send_fn_exception(tmp_path):
    from config import Config
    from harness.exec_repair import attempt_exec_repair

    def bad_send(msg):
        raise RuntimeError("connection lost")

    with patch.object(Config, "STACKY_EXEC_REPAIR_ENABLED", True), \
         patch.object(Config, "STACKY_EXEC_REPAIR_MAX_RETRIES", 1):
        result = attempt_exec_repair(
            run_id=1,
            workspace=str(tmp_path),
            runtime="claude_code_cli",
            hard_failed=[_make_hard_failed()],
            budget_remaining=300,
            send_fn=bad_send,
            changed_files=["bad.py"],
        )

    assert result.attempted is True
    assert result.recovered is False
    assert result.skip_reason is not None


# ── 9. to_metadata shape ─────────────────────────────────────────────────────

def test_repair_result_to_metadata():
    from harness.exec_repair import RepairResult
    r = RepairResult(attempted=True, recovered=False, failed_before=["PyCompile"])
    md = r.to_metadata()
    assert "attempted" in md
    assert "recovered" in md
    assert "failed_before" in md
    assert md["failed_before"] == ["PyCompile"]


# ── 10. codex_cli con resume → sí intenta ────────────────────────────────────

def test_codex_cli_with_resume_attempts(tmp_path):
    from config import Config
    from harness.exec_repair import attempt_exec_repair
    from services.exec_verification import VerificationReport

    mock_report = VerificationReport(passed=True, ran=["JsonYamlParser"])

    with patch.object(Config, "STACKY_EXEC_REPAIR_ENABLED", True), \
         patch.object(Config, "STACKY_EXEC_REPAIR_MAX_RETRIES", 1), \
         patch("services.exec_verification.verify", return_value=mock_report), \
         patch("services.exec_verification.invalidate_cache"):
        result = attempt_exec_repair(
            run_id=10,
            workspace=str(tmp_path),
            runtime="codex_cli",  # supports_resume=True
            hard_failed=[_make_hard_failed("JsonYamlParser", "invalid json")],
            budget_remaining=300,
            send_fn=lambda msg: "fixed",
            changed_files=["bad.json"],
        )

    assert result.attempted is True
