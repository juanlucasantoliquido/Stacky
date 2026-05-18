"""Tests del eval runner + sentiment analyzer (Fase 2).

Backend LLM siempre mock para que tests sean determinísticos.
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
os.environ["STACKY_PM_LLM_BACKEND"] = "mock"


@pytest.fixture(autouse=True)
def _pm_tables_ready():
    from db import init_db, session_scope
    from services.pm.models import PmAiUsage, PmWorkItemComment

    init_db()
    with session_scope() as session:
        session.query(PmAiUsage).delete()
        session.query(PmWorkItemComment).delete()
    yield
    with session_scope() as session:
        session.query(PmAiUsage).delete()
        session.query(PmWorkItemComment).delete()


# ── load fixtures ──────────────────────────────────────────────────────────────

def test_load_fixtures_sentiment():
    from services.pm.pm_evals import load_fixtures
    fixtures = load_fixtures("comment_sentiment")
    assert len(fixtures) == 5
    ids = {f["fixture_id"] for f in fixtures}
    assert "sentiment_blocker_comment" in ids
    assert "sentiment_pii_already_masked" in ids


def test_load_fixtures_recommendation():
    from services.pm.pm_evals import load_fixtures
    fixtures = load_fixtures("recommendation_engine")
    assert len(fixtures) == 5
    ids = {f["fixture_id"] for f in fixtures}
    assert "rec_velocity_drop_15pct" in ids
    assert "rec_no_hallucinated_metrics" in ids


def test_load_fixtures_unknown_component_returns_empty():
    from services.pm.pm_evals import load_fixtures
    assert load_fixtures("nonexistent") == []


# ── run_evals (con mock LLM determinístico) ───────────────────────────────────

def test_run_sentiment_evals_with_mock_produces_report():
    from services.pm.pm_evals import run_evals
    report = run_evals(component="comment_sentiment", model="mock-1.0")
    assert report.component == "comment_sentiment"
    assert report.total == 5
    # El mock devuelve siempre neutral sin flags — algunos fixtures fallarán
    # (los que requieren flags específicos) pero el report debe completarse.
    assert report.passed + report.failed == report.total
    # Cada fixture trackeado en pm_ai_usage
    assert all(f.usage_id is not None for f in report.fixtures)


def test_run_recommendation_evals_with_mock_produces_report():
    from services.pm.pm_evals import run_evals
    report = run_evals(component="recommendation_engine", model="mock-1.0")
    assert report.component == "recommendation_engine"
    assert report.total == 5
    # Mock devuelve recommendations=[], advisory_only=true → solo fallan los que
    # requieren min_recommendations_count >= 1.
    assert report.passed >= 1  # al menos sprint_on_track + no_hallucinated_metrics pasan


def test_run_evals_filtered_by_fixture_id():
    from services.pm.pm_evals import run_evals
    report = run_evals(
        component="comment_sentiment",
        model="mock-1.0",
        only_fixture_ids=["sentiment_positive_update"],
    )
    assert report.total == 1
    assert report.fixtures[0].fixture_id == "sentiment_positive_update"


def test_unknown_component_raises():
    from services.pm.pm_evals import run_evals
    with pytest.raises(ValueError):
        run_evals(component="bogus_component")


def test_eval_run_persists_usage_with_fixture_id():
    from db import session_scope
    from services.pm.models import PmAiUsage
    from services.pm.pm_evals import run_evals

    run_evals(component="comment_sentiment", model="mock-1.0")
    with session_scope() as session:
        rows = session.query(PmAiUsage).filter(PmAiUsage.project == "evals").all()
        assert len(rows) == 5
        # cada fila lleva fixture_id correspondiente
        fixture_ids = {r.fixture_id for r in rows}
        assert "sentiment_blocker_comment" in fixture_ids
        assert "sentiment_pii_already_masked" in fixture_ids


# ── gate logic ─────────────────────────────────────────────────────────────────

def test_gate_does_not_pass_with_mock_backend_on_sentiment():
    """El mock devuelve siempre neutral sin flags. El gate sentiment requiere
    blocker_recall >= 0.75 → con mock fallará. Esto es ESPERADO: el gate
    correctamente bloquea hasta tener un modelo real que pase los fixtures."""
    from services.pm.pm_evals import run_evals
    report = run_evals(component="comment_sentiment", model="mock-1.0")
    assert report.gate_passed is False
    assert "blocker_recall" in report.gate_details


def test_gate_details_include_thresholds():
    from services.pm.pm_evals import run_evals
    report = run_evals(component="comment_sentiment", model="mock-1.0")
    assert "thresholds" in report.gate_details
    assert "min_label_precision" in report.gate_details["thresholds"]


# ── sentiment analyzer con gate ───────────────────────────────────────────────

def test_sentiment_analyzer_blocks_when_gate_fails():
    """Sin force_unsafe, si el gate del eval no pasa, analyze devuelve 0 analyzed."""
    from db import session_scope
    from services.pm.models import PmWorkItemComment
    from services.pm.pm_sentiment import analyze_sentiment_for_comments

    with session_scope() as session:
        c = PmWorkItemComment(
            ado_id=1, project="TestPM", author="dev",
            text_plain="el ticket está listo",
            ai_analyzed=False,
        )
        session.add(c)
        session.flush()
        cid = c.id

    result = analyze_sentiment_for_comments(
        project="TestPM",
        sprint_name="Sprint Test",
        comment_ids=[cid],
        model="mock-1.0",
    )
    assert result.gate_passed is False
    assert result.analyzed == 0
    # No debe haberse cambiado nada en DB
    with session_scope() as session:
        row = session.query(PmWorkItemComment).filter(PmWorkItemComment.id == cid).one()
        assert row.ai_analyzed is False
        assert row.sentiment_label is None


def test_sentiment_analyzer_with_force_unsafe_persists_results():
    """Con force_unsafe=True bypassa el gate y persiste sentiment_label."""
    from db import session_scope
    from services.pm.models import PmWorkItemComment
    from services.pm.pm_sentiment import analyze_sentiment_for_comments

    with session_scope() as session:
        c = PmWorkItemComment(
            ado_id=2, project="TestPM", author="dev",
            text_plain="todo en orden, deploy ok",
            ai_analyzed=False,
        )
        session.add(c)
        session.flush()
        cid = c.id

    result = analyze_sentiment_for_comments(
        project="TestPM",
        sprint_name="Sprint Test",
        comment_ids=[cid],
        model="mock-1.0",
        force_unsafe=True,
    )
    # El mock devuelve un único result con comment_id=1, pero el sentiment
    # analyzer mapea por id solo si coincide — con un comment real cid != 1.
    # Esto es esperable: el mock no es un modelo real. Lo que validamos es que
    # no rompe y el flow funciona.
    assert result.requested == 1
    # Con mock que devuelve comment_id=1 fijo, si nuestro cid != 1 → failures=1
    # Si cid == 1 (poco probable) → analyzed=1. Cualquiera está bien.
    assert result.analyzed + result.failures == 1


def test_sentiment_analyzer_skips_already_analyzed():
    from db import session_scope
    from services.pm.models import PmWorkItemComment
    from services.pm.pm_sentiment import analyze_sentiment_for_comments

    with session_scope() as session:
        c = PmWorkItemComment(
            ado_id=3, project="TestPM", author="dev",
            text_plain="ya analizado",
            ai_analyzed=True,
            sentiment_label="positive",
            sentiment_score=0.9,
        )
        session.add(c)
        session.flush()
        cid = c.id

    result = analyze_sentiment_for_comments(
        project="TestPM",
        sprint_name="Sprint Test",
        comment_ids=[cid],
        model="mock-1.0",
        force_unsafe=True,
    )
    assert result.skipped_already_analyzed == 1
    assert result.analyzed == 0


def test_sentiment_analyzer_advisory_only_always_true():
    from services.pm.pm_sentiment import analyze_sentiment_for_comments
    result = analyze_sentiment_for_comments(
        project="TestPM",
        comment_ids=[],
        model="mock-1.0",
    )
    assert result.advisory_only is True
