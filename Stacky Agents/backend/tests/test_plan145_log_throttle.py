"""Plan 145 F0 — helper de logging con dedup/rate-limit (services/log_throttle.py).

Contrato congelado para migración opcional de 147/148: log_state_change,
log_throttled, warn_once, reset. Ver docstring del módulo.
"""
from __future__ import annotations

import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import services.log_throttle as log_throttle  # noqa: E402


def _logger() -> logging.Logger:
    return logging.getLogger("test145.throttle")


def test_log_state_change_logs_first_then_suppresses_same_state(caplog):
    log_throttle.reset()
    lg = _logger()
    caplog.set_level(logging.INFO, logger="test145.throttle")

    first = log_throttle.log_state_change("k", "S", lg, logging.INFO, "msg")
    second = log_throttle.log_state_change("k", "S", lg, logging.INFO, "msg")

    records = [r for r in caplog.records if r.name == "test145.throttle"]
    assert len(records) == 1
    assert first is True
    assert second is False


def test_log_state_change_relogs_on_change(caplog):
    log_throttle.reset()
    lg = _logger()
    caplog.set_level(logging.INFO, logger="test145.throttle")

    log_throttle.log_state_change("k2", "A", lg, logging.INFO, "msg")
    log_throttle.log_state_change("k2", "B", lg, logging.INFO, "msg")

    records = [r for r in caplog.records if r.name == "test145.throttle"]
    assert len(records) == 2


def test_log_throttled_rate_limits(monkeypatch, caplog):
    log_throttle.reset()
    lg = _logger()
    caplog.set_level(logging.INFO, logger="test145.throttle")

    clock = {"t": 0.0}
    monkeypatch.setattr(log_throttle.time, "monotonic", lambda: clock["t"])

    clock["t"] = 0.0
    log_throttle.log_throttled("k3", lg, logging.INFO, "msg", min_interval_s=60.0)
    clock["t"] = 10.0
    log_throttle.log_throttled("k3", lg, logging.INFO, "msg", min_interval_s=60.0)

    records = [r for r in caplog.records if r.name == "test145.throttle"]
    assert len(records) == 1

    clock["t"] = 100.0
    log_throttle.log_throttled("k3", lg, logging.INFO, "msg", min_interval_s=60.0)

    records = [r for r in caplog.records if r.name == "test145.throttle"]
    assert len(records) == 2


def test_warn_once_logs_exactly_once(caplog):
    log_throttle.reset()
    lg = _logger()
    caplog.set_level(logging.WARNING, logger="test145.throttle")

    log_throttle.warn_once("k4", lg, "msg")
    log_throttle.warn_once("k4", lg, "msg")
    log_throttle.warn_once("k4", lg, "msg")

    records = [r for r in caplog.records if r.name == "test145.throttle"]
    assert len(records) == 1
    assert records[0].levelno == logging.WARNING


def test_reset_clears_state(caplog):
    log_throttle.reset()
    lg = _logger()
    caplog.set_level(logging.INFO, logger="test145.throttle")

    log_throttle.log_state_change("k5", "S", lg, logging.INFO, "msg")
    log_throttle.reset("k5")
    log_throttle.log_state_change("k5", "S", lg, logging.INFO, "msg")

    records = [r for r in caplog.records if r.name == "test145.throttle"]
    assert len(records) == 2


def test_public_surface_frozen():
    assert set(log_throttle.__all__) == {
        "log_state_change",
        "log_throttled",
        "warn_once",
        "reset",
    }
