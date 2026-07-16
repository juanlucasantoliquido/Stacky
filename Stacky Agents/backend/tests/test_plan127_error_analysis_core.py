"""Plan 127 F2 — Núcleo puro services/error_analysis.py (C1).

Prompt determinista desde el snapshot forense de api.diag (F1). Sin Flask,
sin red, sin ORM.
"""
from __future__ import annotations

from services.error_analysis import (
    ANALYSIS_MAX,
    build_error_analysis_prompt,
    cap_analysis,
    is_analyzable,
)


def _snapshot(**overrides) -> dict:
    base = {
        "ok": True,
        "execution": {
            "id": 1,
            "agent_type": "developer",
            "status": "error",
            "started_by": "operator",
            "started_at": "2026-07-12T10:00:00",
            "completed_at": "2026-07-12T10:05:00",
            "error_message": "boom: connection refused",
            "completion_source": "runner",
        },
        "ticket": None,
        "manifest": {"status": "error"},
        "heartbeat": {"exists": True},
        "recovery_history": [
            {"old_status": "running", "new_status": "error", "changed_by": "system", "changed_at": "2026-07-12T10:05:00", "reason": "crash"},
        ],
        "diagnosis": "terminal_error",
        "recommended_action": "revisar logs del runner",
        "thresholds": {"pre_run_timeout_seconds": 60, "heartbeat_timeout_minutes": 5, "startup_grace_seconds": 30},
    }
    base.update(overrides)
    return base


def test_is_analyzable_error_y_needs_review():
    assert is_analyzable("error", "") is True
    assert is_analyzable("needs_review", "") is True


def test_is_analyzable_completed_con_error_message():
    assert is_analyzable("completed", "algo raro pasó") is True


def test_is_analyzable_completed_limpio():
    assert is_analyzable("completed", "") is False


def test_is_analyzable_running_false():
    """H7 — los zombies se diagnostican con diag/recovery, no con el LLM."""
    assert is_analyzable("running", "") is False


def test_prompt_incluye_diagnosis_y_error():
    snapshot = _snapshot()
    _, user = build_error_analysis_prompt(snapshot, "output de prueba")
    assert "terminal_error" in user
    assert "revisar logs del runner" in user
    assert "boom: connection refused" in user


def test_prompt_redacta_secretos():
    snapshot = _snapshot(execution={
        **_snapshot()["execution"],
        "error_message": "fallo con password=hunter2",
    })
    _, user = build_error_analysis_prompt(snapshot, "")
    assert "hunter2" not in user
    assert "REDACTED" in user


def test_prompt_trunca_output_largo():
    snapshot = _snapshot()
    output_text = "x" * 20000
    _, user = build_error_analysis_prompt(snapshot, output_text)
    assert "[recortado]" in user
    assert len(user) < len(output_text) + 6000


def test_prompt_tolera_snapshot_incompleto():
    snapshot = {"execution": {"id": 1}}
    system, user = build_error_analysis_prompt(snapshot, "")
    assert system
    assert user


def test_cap_analysis():
    text = "y" * 10000
    capped = cap_analysis(text)
    assert len(capped) <= ANALYSIS_MAX + 20
    assert capped.endswith("[recortado]")
