"""Tests R0.2 — Persistencia incremental de logs.

TDD: flush() persiste eventos no flusheados; doble flush no duplica;
flag OFF → solo en close().
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch, call


def _make_event(msg: str = "test"):
    """Crea un LogEvent minimal."""
    from log_streamer import LogEvent
    return LogEvent(timestamp=datetime.utcnow(), level="info", message=msg)


def test_flush_flag_off_returns_zero():
    """Con flag OFF, flush() retorna 0 sin tocar la DB."""
    import log_streamer

    with patch("config.config") as mock_cfg:
        mock_cfg.STACKY_LOG_FLUSH_INCREMENTAL_ENABLED = False
        log_streamer.open(9001)
        log_streamer.push(9001, "info", "mensaje")
        result = log_streamer.flush(9001)

    assert result == 0

    # Cleanup
    log_streamer._drop(9001)


def test_flush_persists_new_events():
    """flush() persiste los eventos no flusheados aun."""
    import log_streamer

    execution_id = 9002
    log_streamer.open(execution_id)
    log_streamer.push(execution_id, "info", "evento-1")
    log_streamer.push(execution_id, "info", "evento-2")

    persisted = []

    def fake_session():
        class FakeSession:
            def __enter__(self):
                return self
            def __exit__(self, *a):
                pass
            def add(self, obj):
                persisted.append(obj.message)
        return FakeSession()

    with patch("config.config") as mock_cfg:
        mock_cfg.STACKY_LOG_FLUSH_INCREMENTAL_ENABLED = True
        with patch("log_streamer.session_scope", fake_session):
            n = log_streamer.flush(execution_id)

    assert n == 2
    assert "evento-1" in persisted
    assert "evento-2" in persisted

    log_streamer._drop(execution_id)


def test_double_flush_no_duplicates():
    """Doble flush → sin duplicados (flushed_idx avanza)."""
    import log_streamer

    execution_id = 9003
    log_streamer.open(execution_id)
    log_streamer.push(execution_id, "info", "ev-a")

    persisted: list[str] = []

    def fake_session():
        class FakeSession:
            def __enter__(self):
                return self
            def __exit__(self, *a):
                pass
            def add(self, obj):
                persisted.append(obj.message)
        return FakeSession()

    with patch("config.config") as mock_cfg:
        mock_cfg.STACKY_LOG_FLUSH_INCREMENTAL_ENABLED = True
        with patch("log_streamer.session_scope", fake_session):
            n1 = log_streamer.flush(execution_id)
            # Segundo flush: sin eventos nuevos
            n2 = log_streamer.flush(execution_id)

    assert n1 == 1
    assert n2 == 0  # sin duplicados
    assert persisted.count("ev-a") == 1

    log_streamer._drop(execution_id)


def test_close_after_flush_no_duplicates():
    """close() después de flush() solo persiste los eventos no flusheados."""
    import log_streamer

    execution_id = 9004
    log_streamer.open(execution_id)
    log_streamer.push(execution_id, "info", "before-flush")

    persisted_flush: list[str] = []
    persisted_close: list[str] = []

    def flush_session():
        class FakeSession:
            def __enter__(self):
                return self
            def __exit__(self, *a):
                pass
            def add(self, obj):
                persisted_flush.append(obj.message)
        return FakeSession()

    def close_session():
        class FakeSession:
            def __enter__(self):
                return self
            def __exit__(self, *a):
                pass
            def add(self, obj):
                persisted_close.append(obj.message)
        return FakeSession()

    with patch("config.config") as mock_cfg:
        mock_cfg.STACKY_LOG_FLUSH_INCREMENTAL_ENABLED = True
        with patch("log_streamer.session_scope", flush_session):
            log_streamer.flush(execution_id)

        log_streamer.push(execution_id, "info", "after-flush")
        with patch("log_streamer.session_scope", close_session):
            log_streamer.close(execution_id)

    # flush persistio "before-flush"; close solo persistio "after-flush"
    assert "before-flush" in persisted_flush
    assert "after-flush" in persisted_close
    assert "before-flush" not in persisted_close  # sin duplicados


def test_flush_no_op_if_buffer_closed():
    """flush() es no-op si el buffer ya fue cerrado."""
    import log_streamer

    execution_id = 9005
    log_streamer.open(execution_id)
    log_streamer.push(execution_id, "info", "msg")

    persisted: list = []

    def fake_session():
        class FakeSession:
            def __enter__(self):
                return self
            def __exit__(self, *a):
                pass
            def add(self, obj):
                persisted.append(obj)
        return FakeSession()

    with patch("config.config") as mock_cfg:
        mock_cfg.STACKY_LOG_FLUSH_INCREMENTAL_ENABLED = True
        # Marcar el buffer como cerrado manualmente
        buf = log_streamer._get(execution_id)
        with buf.lock:
            buf.closed = True
        with patch("log_streamer.session_scope", fake_session):
            n = log_streamer.flush(execution_id)

    assert n == 0
    assert persisted == []

    log_streamer._drop(execution_id)
