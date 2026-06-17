"""V2.4 — Cache/dedup de runs CLI (services/run_cache.py)."""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")


@pytest.fixture(autouse=True)
def _db_ready():
    from db import init_db, session_scope
    from models import AgentExecution, Ticket

    init_db()
    with session_scope() as session:
        session.query(AgentExecution).delete()
        session.query(Ticket).delete()
    yield


# ── compute_fingerprint ──────────────────────────────────────────────────────


def test_fingerprint_stable_for_same_inputs():
    from services import run_cache

    blocks = [{"role": "ctx", "text": "hola"}, {"role": "ctx", "text": "chau"}]
    a = run_cache.compute_fingerprint(prompt_sha="abc", model="claude-sonnet-4-6", context_blocks=blocks)
    b = run_cache.compute_fingerprint(prompt_sha="abc", model="claude-sonnet-4-6", context_blocks=blocks)
    assert a == b and a is not None


def test_fingerprint_ignores_key_order_within_block():
    from services import run_cache

    a = run_cache.compute_fingerprint(prompt_sha="abc", model="m", context_blocks=[{"x": 1, "y": 2}])
    b = run_cache.compute_fingerprint(prompt_sha="abc", model="m", context_blocks=[{"y": 2, "x": 1}])
    assert a == b


def test_fingerprint_changes_on_prompt_model_or_context():
    from services import run_cache

    base = run_cache.compute_fingerprint(prompt_sha="abc", model="m1", context_blocks=[{"t": 1}])
    assert run_cache.compute_fingerprint(prompt_sha="DIFF", model="m1", context_blocks=[{"t": 1}]) != base
    assert run_cache.compute_fingerprint(prompt_sha="abc", model="m2", context_blocks=[{"t": 1}]) != base
    assert run_cache.compute_fingerprint(prompt_sha="abc", model="m1", context_blocks=[{"t": 2}]) != base


def test_fingerprint_none_without_prompt_sha():
    from services import run_cache

    assert run_cache.compute_fingerprint(prompt_sha=None, model="m", context_blocks=[{"t": 1}]) is None
    assert run_cache.compute_fingerprint(prompt_sha="", model="m", context_blocks=[{"t": 1}]) is None


# ── find_cached_candidate ────────────────────────────────────────────────────


def _seed_completed(fingerprint: str | None, started_at: datetime) -> int:
    from db import session_scope
    from models import AgentExecution, Ticket

    with session_scope() as session:
        t = Ticket(ado_id=70001, project="TEST", title="t", ado_state="Active")
        session.add(t)
        session.flush()
        e = AgentExecution(
            ticket_id=t.id,
            agent_type="developer",
            status="completed",
            input_context_json="[]",
            started_by="test",
            started_at=started_at,
        )
        if fingerprint is not None:
            e.metadata_dict = {"run_fingerprint": fingerprint}
        session.add(e)
        session.flush()
        return e.id


def test_candidate_found_within_window():
    from db import session_scope
    from services import run_cache

    seeded = _seed_completed("fp-1", datetime.utcnow() - timedelta(days=1))
    with session_scope() as session:
        got = run_cache.find_cached_candidate(session=session, fingerprint="fp-1", days=7)
    assert got == seeded


def test_candidate_excluded_outside_window():
    from db import session_scope
    from services import run_cache

    _seed_completed("fp-1", datetime.utcnow() - timedelta(days=30))
    with session_scope() as session:
        got = run_cache.find_cached_candidate(session=session, fingerprint="fp-1", days=7)
    assert got is None


def test_cache_off_when_days_zero():
    from db import session_scope
    from services import run_cache

    _seed_completed("fp-1", datetime.utcnow())
    with session_scope() as session:
        assert run_cache.find_cached_candidate(session=session, fingerprint="fp-1", days=0) is None


def test_no_candidate_for_different_fingerprint():
    from db import session_scope
    from services import run_cache

    _seed_completed("fp-1", datetime.utcnow())
    with session_scope() as session:
        assert run_cache.find_cached_candidate(session=session, fingerprint="fp-OTHER", days=7) is None


def test_exclude_self():
    from db import session_scope
    from services import run_cache

    seeded = _seed_completed("fp-1", datetime.utcnow())
    with session_scope() as session:
        got = run_cache.find_cached_candidate(
            session=session, fingerprint="fp-1", days=7, exclude_execution_id=seeded
        )
    assert got is None
