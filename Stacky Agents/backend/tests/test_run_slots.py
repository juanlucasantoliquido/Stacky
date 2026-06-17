"""V0.3 — Tests del cap de concurrencia (services/run_slots.py)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")


@pytest.fixture(autouse=True)
def _reset():
    from services import run_slots

    run_slots._reset_for_tests()
    yield
    run_slots._reset_for_tests()


def _set_limit(monkeypatch, n: int):
    from config import config

    monkeypatch.setattr(config, "STACKY_MAX_CONCURRENT_RUNS", n, raising=False)


def test_unlimited_never_rejects(monkeypatch):
    from services import run_slots

    _set_limit(monkeypatch, 0)
    for _ in range(10):
        assert run_slots.try_acquire() is True
    assert run_slots.active_count() == 10


def test_limit_rejects_over_cap(monkeypatch):
    from services import run_slots

    _set_limit(monkeypatch, 2)
    assert run_slots.try_acquire() is True
    assert run_slots.try_acquire() is True
    assert run_slots.try_acquire() is False  # tercero rechazado
    assert run_slots.active_count() == 2


def test_release_frees_slot(monkeypatch):
    from services import run_slots

    _set_limit(monkeypatch, 2)
    run_slots.try_acquire()
    run_slots.try_acquire()
    assert run_slots.try_acquire() is False
    run_slots.release()
    assert run_slots.try_acquire() is True


def test_release_idempotent_floor():
    from services import run_slots

    run_slots.release()
    run_slots.release()
    assert run_slots.active_count() == 0


def test_active_count_tracks(monkeypatch):
    from services import run_slots

    _set_limit(monkeypatch, 0)
    run_slots.try_acquire()
    run_slots.try_acquire()
    assert run_slots.active_count() == 2
    run_slots.release()
    assert run_slots.active_count() == 1
