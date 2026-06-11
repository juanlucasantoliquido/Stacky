"""H2.3 — Tests del loop de autocorrección codex via exec resume.

Casos:
  1. artifacts válidos → 0 resumes lanzados
  2. inválido → válido en 1er resume → 1 resume, suggestion completed
  3. siempre inválido → corta en cap, suggestion needs_review si gate ON
  4. sin session_id → no intenta resume, log warn
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")


# ---------------------------------------------------------------------------
# Helper: simula la lógica de autocorrección codex
# ---------------------------------------------------------------------------

def _run_codex_autocorrect(
    *,
    session_id,
    artifacts_sequence,  # lista de listas de ArtifactValidation por intento
    ado_id=101,
    max_retries=2,
    gate_enabled=False,
):
    """Simula services.codex_autocorrect.run_autocorrect_loop sin invocar codex real."""
    from services.codex_autocorrect import run_autocorrect_loop
    from services import artifact_validator as av

    resumes_launched = []

    def fake_resume(sess_id, prompt):
        resumes_launched.append((sess_id, prompt))
        return True

    call_count = [0]

    def fake_validate(ado_id, check_db=False):
        idx = min(call_count[0], len(artifacts_sequence) - 1)
        call_count[0] += 1
        report = av.ArtifactReport()
        for a in artifacts_sequence[idx]:
            report.artifacts.append(a)
        return report

    result = run_autocorrect_loop(
        session_id=session_id,
        ado_id=ado_id,
        max_retries=max_retries,
        gate_enabled=gate_enabled,
        resume_fn=fake_resume,
        validate_fn=fake_validate,
        log=lambda l, m: None,
    )
    return result, resumes_launched


def _valid_art(path="a.json"):
    from services.artifact_validator import ArtifactValidation
    return ArtifactValidation(path=path, kind="pending_task", valid=True)


def _invalid_art(path="a.json", error="bad json"):
    from services.artifact_validator import ArtifactValidation
    return ArtifactValidation(path=path, kind="pending_task", valid=False, errors=[error])


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_valid_artifacts_no_resume():
    """Artifacts válidos → 0 resumes."""
    result, resumes = _run_codex_autocorrect(
        session_id="sess-1",
        artifacts_sequence=[[_valid_art()]],
    )
    assert resumes == []
    assert result.status_suggestion == "completed"


def test_invalid_then_valid_one_resume():
    """Inválido en 1er intento, válido tras resume → 1 resume, status completed."""
    result, resumes = _run_codex_autocorrect(
        session_id="sess-2",
        artifacts_sequence=[[_invalid_art()], [_valid_art()]],
        max_retries=2,
        gate_enabled=False,
    )
    assert len(resumes) == 1
    assert resumes[0][0] == "sess-2"
    assert result.status_suggestion == "completed"
    assert result.retries_used == 1


def test_always_invalid_caps_at_max_retries_gate_on():
    """Siempre inválido → corta en cap, needs_review si gate ON."""
    result, resumes = _run_codex_autocorrect(
        session_id="sess-3",
        artifacts_sequence=[[_invalid_art()]] * 5,
        max_retries=2,
        gate_enabled=True,
    )
    assert len(resumes) == 2
    assert result.status_suggestion == "needs_review"
    assert result.retries_used == 2


def test_always_invalid_gate_off_stays_completed():
    """Siempre inválido + gate OFF → completed (autocorrect corrió igual)."""
    result, resumes = _run_codex_autocorrect(
        session_id="sess-4",
        artifacts_sequence=[[_invalid_art()]] * 5,
        max_retries=2,
        gate_enabled=False,
    )
    assert len(resumes) == 2
    assert result.status_suggestion == "completed"


def test_no_session_id_skips_resume():
    """Sin session_id → no intenta resume, status completed."""
    from services.codex_autocorrect import run_autocorrect_loop
    from services import artifact_validator as av

    resumes_launched = []

    def fake_resume(sess_id, prompt):
        resumes_launched.append((sess_id, prompt))
        return True

    report = av.ArtifactReport()
    report.artifacts.append(_invalid_art())

    result = run_autocorrect_loop(
        session_id=None,
        ado_id=101,
        max_retries=2,
        gate_enabled=True,
        resume_fn=fake_resume,
        validate_fn=lambda ado_id, check_db=False: report,
        log=lambda l, m: None,
    )
    assert resumes_launched == []
    # Sin session_id no podemos corregir, pero status no se degrada (no hay retries)
    assert result.status_suggestion == "completed"


def test_no_artifacts_skips_autocorrect():
    """Sin artifacts en el run → skip, status completed."""
    from services.codex_autocorrect import run_autocorrect_loop
    from services import artifact_validator as av

    resumes_launched = []

    def fake_resume(sess_id, prompt):
        resumes_launched.append((sess_id, prompt))
        return True

    # Reporte vacío (0 artifacts)
    empty_report = av.ArtifactReport()

    result = run_autocorrect_loop(
        session_id="sess-5",
        ado_id=101,
        max_retries=2,
        gate_enabled=True,
        resume_fn=fake_resume,
        validate_fn=lambda ado_id, check_db=False: empty_report,
        log=lambda l, m: None,
    )
    assert resumes_launched == []
    assert result.status_suggestion == "completed"
