"""Tests R0.3 — Reaper de huerfanos + watchdog reconciliador."""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

# Forzar import de db antes de cualquier patch("config.config"), ya que db.py
# llama create_engine() al importarse. Si db se importa mientras config.config
# es un MagicMock, SQLAlchemy recibe una URL falsa y falla.
import db  # noqa: F401


def _make_exec(execution_id: int, status: str = "running", pid: int | None = 1234):
    row = MagicMock()
    row.id = execution_id
    row.status = status
    row.metadata_dict = {"runtime": "claude_code_cli", "pid": pid} if pid else {"runtime": "claude_code_cli"}
    return row


def _make_session_scope(rows):
    """Crea un context manager mock para session_scope que devuelve rows en query."""
    def make_ss():
        class CM:
            def __enter__(self):
                session = MagicMock()
                qr = MagicMock()
                qr.filter.return_value.all.return_value = rows
                session.query.return_value = qr
                return session
            def __exit__(self, *a):
                return False
        return CM()
    return make_ss


def test_flag_off_reconcile_is_no_op():
    """Con flag OFF (STACKY_RUNNER_REAP_ON_CLOSE_ENABLED), reconcile_once no reapea."""
    from services import orphan_reaper

    with patch("config.config") as mock_cfg:
        mock_cfg.STACKY_RUNNER_REAP_ON_CLOSE_ENABLED = False
        mock_cfg.STACKY_LOG_FLUSH_INCREMENTAL_ENABLED = False

        with patch("db.session_scope", _make_session_scope([])):
            result = orphan_reaper.reconcile_once()

    assert result["failed_orphans"] == 0
    assert result["reaped"] == 0


def test_stale_running_marked_failed():
    """run en estado running sin heartbeat reciente → failed + metadata reaped."""
    from services import orphan_reaper

    sealed_ids: list[int] = []

    with patch("config.config") as mock_cfg:
        mock_cfg.STACKY_RUNNER_REAP_ON_CLOSE_ENABLED = False
        mock_cfg.STACKY_LOG_FLUSH_INCREMENTAL_ENABLED = False

        exec_row = _make_exec(42, status="running")
        with patch("db.session_scope", _make_session_scope([exec_row])):
            with patch.object(orphan_reaper, "_seal_reaped_metadata",
                              side_effect=lambda eid, **kw: sealed_ids.append(eid)):
                result = orphan_reaper.reconcile_once()

    assert 42 in sealed_ids
    assert result["failed_orphans"] >= 1


def test_active_heartbeat_not_touched():
    """Query con resultados vacios → no reconcilia nada."""
    from services import orphan_reaper

    with patch("config.config") as mock_cfg:
        mock_cfg.STACKY_RUNNER_REAP_ON_CLOSE_ENABLED = False
        mock_cfg.STACKY_LOG_FLUSH_INCREMENTAL_ENABLED = False

        with patch("db.session_scope", _make_session_scope([])):
            with patch.object(orphan_reaper, "_seal_reaped_metadata") as mock_seal:
                result = orphan_reaper.reconcile_once()

    mock_seal.assert_not_called()
    assert result["failed_orphans"] == 0


def test_pid_not_registered_no_crash():
    """Run sin pid en metadata → no explota, igual se marca failed."""
    from services import orphan_reaper

    sealed_ids: list[int] = []

    with patch("config.config") as mock_cfg:
        mock_cfg.STACKY_RUNNER_REAP_ON_CLOSE_ENABLED = False
        mock_cfg.STACKY_LOG_FLUSH_INCREMENTAL_ENABLED = False

        exec_row = _make_exec(55, status="running", pid=None)
        with patch("db.session_scope", _make_session_scope([exec_row])):
            with patch.object(orphan_reaper, "_seal_reaped_metadata",
                              side_effect=lambda eid, **kw: sealed_ids.append(eid)):
                result = orphan_reaper.reconcile_once()

    assert 55 in sealed_ids
    assert result["errors"] == 0


def test_reap_called_when_enabled():
    """Con R0.1 habilitado, reconcile invoca reap_execution para runtime conocido."""
    from services import orphan_reaper

    with patch("config.config") as mock_cfg:
        mock_cfg.STACKY_RUNNER_REAP_ON_CLOSE_ENABLED = True
        mock_cfg.STACKY_LOG_FLUSH_INCREMENTAL_ENABLED = False

        exec_row = _make_exec(77, status="running", pid=9999)
        with patch("db.session_scope", _make_session_scope([exec_row])):
            with patch("services.runner_reap.reap_execution", return_value=True) as mock_reap:
                with patch.object(orphan_reaper, "_seal_reaped_metadata", lambda eid, **kw: None):
                    result = orphan_reaper.reconcile_once()

        mock_reap.assert_called_once_with(77, runtime="claude_code_cli")

    assert result["reaped"] == 1
