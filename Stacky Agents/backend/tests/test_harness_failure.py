"""V0.4 — Tests de la taxonomía de fallos (harness/failure.py)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")


@pytest.mark.parametrize(
    "return_code,error_message,metadata,expected",
    [
        # runaway gana sobre todo
        (1, "whatever", {"runaway": {"reason": "max_turns"}}, "runaway"),
        (None, None, {"runaway": {"reason": "cost"}}, "runaway"),
        # cancelación explícita
        (None, None, {"cancelled": True}, "cancelled"),
        (1, None, {"cancelled_by": "operator"}, "cancelled"),
        (1, "run cancelled by user", {}, "cancelled"),
        # timeout
        (1, "session timeout after 7200s", {}, "timeout"),
        (None, "process timed out", {}, "timeout"),
        # spawn error
        (None, "FileNotFoundError: codex", {}, "spawn_error"),
        (None, "no such file or directory", {}, "spawn_error"),
        (1, None, {"spawn_failed": True}, "spawn_error"),
        # contract failed
        (0, None, {"contract_result": {"passed": False}, "status": "needs_review"},
         "contract_failed"),
        # crash genérico
        (2, "boom", {}, "crash"),
        (None, "unexpected error happened", {}, "crash"),
        # ok → None
        (0, None, {}, None),
        (0, None, {"contract_result": {"passed": True}, "status": "completed"}, None),
    ],
)
def test_classify_table(return_code, error_message, metadata, expected):
    from harness.failure import classify

    assert classify(
        return_code=return_code, error_message=error_message, metadata=metadata
    ) == expected


def test_kinds_are_exhaustive():
    from harness.failure import KINDS

    assert set(KINDS) == {
        "spawn_error", "timeout", "runaway", "contract_failed", "cancelled", "crash",
    }
