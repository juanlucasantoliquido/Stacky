"""Tests Q1.1 — Pase correctivo de criterios de aceptación incumplidos.

TDD para `harness/criteria_repair.py`.
Sin binarios reales; mockea runner y review_artifact.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_review(score, checklist=None, skipped=None):
    from services.self_review import SelfReviewResult
    return SelfReviewResult(
        score=score,
        checklist=checklist or [],
        skipped_reason=skipped,
    )


def _unmet_review():
    return _make_review(
        score=0.5,
        checklist=[
            {"criterion": "Criterio A", "met": False, "evidence": ""},
            {"criterion": "Criterio B", "met": True, "evidence": "ok"},
        ],
    )


def _met_review():
    return _make_review(score=1.0, checklist=[{"criterion": "A", "met": True, "evidence": "ok"}])


# ---------------------------------------------------------------------------
# attempt_criteria_repair
# ---------------------------------------------------------------------------

def test_disabled_returns_none():
    """Flag OFF → None (byte-idéntico)."""
    from harness.criteria_repair import attempt_criteria_repair
    result = attempt_criteria_repair(
        execution_id=1,
        artifact_text="output",
        runtime="claude_code_cli",
        retries_budget=1,
        retries_used=0,
        send_fn=lambda msg: True,
        enabled=False,
    )
    assert result is None


def test_no_resume_support_returns_none():
    """Runtime sin supports_resume → None."""
    from harness.criteria_repair import attempt_criteria_repair
    result = attempt_criteria_repair(
        execution_id=1,
        artifact_text="output",
        runtime="github_copilot",
        retries_budget=1,
        retries_used=0,
        send_fn=lambda msg: True,
        enabled=True,
    )
    assert result is None


def test_budget_exhausted_returns_none():
    """retries_used >= retries_budget → None."""
    from harness.criteria_repair import attempt_criteria_repair
    result = attempt_criteria_repair(
        execution_id=1,
        artifact_text="output",
        runtime="claude_code_cli",
        retries_budget=2,
        retries_used=2,
        send_fn=lambda msg: True,
        enabled=True,
    )
    assert result is None


def test_no_send_fn_returns_none():
    """send_fn=None → None."""
    from harness.criteria_repair import attempt_criteria_repair
    result = attempt_criteria_repair(
        execution_id=1,
        artifact_text="output",
        runtime="claude_code_cli",
        retries_budget=1,
        retries_used=0,
        send_fn=None,
        enabled=True,
    )
    assert result is None


def test_all_criteria_met_returns_none():
    """Todos los criterios cumplidos → no hay pase correctivo."""
    with patch("services.self_review.review_artifact", return_value=_met_review()):
        from harness.criteria_repair import attempt_criteria_repair
        result = attempt_criteria_repair(
            execution_id=1,
            artifact_text="output",
            runtime="claude_code_cli",
            retries_budget=1,
            retries_used=0,
            send_fn=lambda msg: True,
            enabled=True,
        )
    assert result is None


def test_unmet_criteria_sends_message():
    """Criterios incumplidos + send_fn acepta → pase intentado, unmet_before correcto."""
    received_msgs: list[str] = []

    def _send(msg: str) -> bool:
        received_msgs.append(msg)
        return True

    with patch("services.self_review.review_artifact", return_value=_unmet_review()):
        from harness.criteria_repair import attempt_criteria_repair
        result = attempt_criteria_repair(
            execution_id=1,
            artifact_text="output",
            runtime="claude_code_cli",
            retries_budget=1,
            retries_used=0,
            send_fn=_send,
            enabled=True,
            min_score=0.7,
        )

    assert result is not None
    assert result["attempted"] is True
    assert "Criterio A" in result["unmet_before"]
    assert "Criterio B" not in result["unmet_before"]
    assert len(received_msgs) == 1
    assert "Criterio A" in received_msgs[0]
    assert "Corregí SOLO eso" in received_msgs[0]


def test_send_fn_rejected_sets_attempted_false():
    """send_fn devuelve False → attempted=False, recovered=False."""
    with patch("services.self_review.review_artifact", return_value=_unmet_review()):
        from harness.criteria_repair import attempt_criteria_repair
        result = attempt_criteria_repair(
            execution_id=2,
            artifact_text="output",
            runtime="claude_code_cli",
            retries_budget=1,
            retries_used=0,
            send_fn=lambda msg: False,
            enabled=True,
        )
    assert result is not None
    assert result["attempted"] is False
    assert result["recovered"] is False


def test_skipped_reason_returns_none():
    """review_artifact devuelve skipped → None."""
    review = _make_review(score=1.0, skipped="no_acceptance_criteria")
    with patch("services.self_review.review_artifact", return_value=review):
        from harness.criteria_repair import attempt_criteria_repair
        result = attempt_criteria_repair(
            execution_id=3,
            artifact_text="output",
            runtime="claude_code_cli",
            retries_budget=1,
            retries_used=0,
            send_fn=lambda msg: True,
            enabled=True,
        )
    assert result is None


# ---------------------------------------------------------------------------
# Caché de review
# ---------------------------------------------------------------------------

def test_cache_populated_after_attempt():
    """Después de attempt_criteria_repair, get_cached_review devuelve el resultado."""
    from harness.criteria_repair import _REVIEW_CACHE
    _REVIEW_CACHE.clear()
    review = _unmet_review()
    with patch("services.self_review.review_artifact", return_value=review):
        from harness.criteria_repair import attempt_criteria_repair, get_cached_review
        attempt_criteria_repair(
            execution_id=99,
            artifact_text="output",
            runtime="claude_code_cli",
            retries_budget=2,
            retries_used=0,
            send_fn=lambda msg: True,
            enabled=True,
        )
        cached = get_cached_review(99)
    assert cached is review


def test_apply_to_execution_reuses_cache():
    """apply_to_execution con caché → review_artifact no se vuelve a llamar."""
    from harness.criteria_repair import _REVIEW_CACHE
    _REVIEW_CACHE.clear()
    _REVIEW_CACHE[777] = _met_review()

    mock_row = MagicMock()
    mock_row.status = "completed"
    mock_row.output = "output text"
    mock_session = MagicMock()
    mock_session.__enter__ = lambda s: mock_session
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_session.get.return_value = mock_row

    with (
        patch("services.self_review.session_scope", return_value=mock_session),
        patch("services.self_review.config") as mock_cfg,
        patch("services.self_review.review_artifact") as mock_ra,
    ):
        mock_cfg.STACKY_SELF_REVIEW_MODE = "annotate"
        mock_cfg.STACKY_SELF_REVIEW_MIN_SCORE = 0.7

        # mock_row.metadata_dict get/set
        mock_row.metadata_dict = {}

        from services.self_review import apply_to_execution
        apply_to_execution(execution_id=777)

    # review_artifact NO debe haberse llamado (caché hit)
    mock_ra.assert_not_called()


# ---------------------------------------------------------------------------
# mark_recovery
# ---------------------------------------------------------------------------

def test_mark_recovery_updates_db():
    """mark_recovery setea recovered=True en metadata."""
    mock_row = MagicMock()
    mock_row.metadata_dict = {"criteria_repair": {"attempted": True, "recovered": None}}
    mock_session = MagicMock()
    mock_session.__enter__ = lambda s: mock_session
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_session.get.return_value = mock_row

    with patch("db.session_scope", return_value=mock_session):
        from harness.criteria_repair import mark_recovery
        mark_recovery(10, recovered=True)

    assert mock_row.metadata_dict["criteria_repair"]["recovered"] is True
