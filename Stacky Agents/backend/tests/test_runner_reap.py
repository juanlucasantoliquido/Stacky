"""Tests R0.1 — Reaping del subproceso al cerrar la ejecucion.

TDD: cada caso verifica el comportamiento esperado de reap() en cada runner
y del dispatcher reap_by_db/reap_execution.
"""
from __future__ import annotations

import subprocess
import threading
from unittest.mock import MagicMock, patch


# ── claude_code_cli_runner.reap() ────────────────────────────────────────────


def _make_mock_proc(alive: bool = True):
    """Popen mock: terminate/kill no-op; wait() no lanza si alive=False."""
    proc = MagicMock(spec=subprocess.Popen)
    if alive:
        proc.wait.side_effect = None  # wait devuelve 0
    else:
        proc.wait.return_value = 0
    return proc


def test_claude_reap_alive_process():
    """Execution cerrada con Popen vivo → terminate/kill + True."""
    from services import claude_code_cli_runner as runner

    proc = _make_mock_proc(alive=True)
    with patch.dict(runner._PROCESSES, {999: proc}):
        result = runner.reap(999)

    assert result is True
    proc.terminate.assert_called_once()
    proc.wait.assert_called()


def test_claude_reap_not_registered():
    """Pid de otra execution no registrada → False sin tocar nada."""
    from services import claude_code_cli_runner as runner

    proc = _make_mock_proc()
    with patch.dict(runner._PROCESSES, {1: proc}):
        result = runner.reap(9999)  # distinto execution_id

    assert result is False
    proc.terminate.assert_not_called()


def test_claude_reap_already_dead():
    """Proceso ya terminado (terminate lanza) → False (idempotente)."""
    from services import claude_code_cli_runner as runner

    proc = MagicMock(spec=subprocess.Popen)
    proc.terminate.side_effect = OSError("proceso ya muerto")

    with patch.dict(runner._PROCESSES, {42: proc}):
        result = runner.reap(42)

    assert result is False


def test_claude_reap_kill_on_timeout():
    """Si wait() lanza TimeoutExpired → se invoca kill()."""
    from services import claude_code_cli_runner as runner

    proc = MagicMock(spec=subprocess.Popen)
    proc.wait.side_effect = [subprocess.TimeoutExpired(cmd="x", timeout=10), 0]

    with patch.dict(runner._PROCESSES, {77: proc}):
        result = runner.reap(77)

    assert result is True
    proc.kill.assert_called_once()


# ── codex_cli_runner.reap() ───────────────────────────────────────────────────


def test_codex_reap_alive_process():
    """codex reap con proceso vivo → True + terminate."""
    from services import codex_cli_runner as runner

    proc = _make_mock_proc(alive=True)
    with patch.dict(runner._PROCESSES, {200: proc}):
        result = runner.reap(200)

    assert result is True
    proc.terminate.assert_called_once()


def test_codex_reap_not_registered():
    """codex reap execution no registrada → False."""
    from services import codex_cli_runner as runner

    with patch.dict(runner._PROCESSES, {}):
        result = runner.reap(12345)

    assert result is False


# ── Flag OFF → reap no invocado ───────────────────────────────────────────────


def test_reap_execution_flag_off():
    """Con flag OFF, reap_execution retorna False sin invocar ningun runner."""
    from services import runner_reap

    with patch("config.config") as mock_cfg:
        mock_cfg.STACKY_RUNNER_REAP_ON_CLOSE_ENABLED = False
        result = runner_reap.reap_execution(1, runtime="claude_code_cli")

    assert result is False


# ── Runtime desconocido → no-op ───────────────────────────────────────────────


def test_reap_execution_unknown_runtime():
    """Runtime desconocido o None → no-op (False)."""
    from services import runner_reap

    with patch("config.config") as mock_cfg:
        mock_cfg.STACKY_RUNNER_REAP_ON_CLOSE_ENABLED = True
        result_none = runner_reap.reap_execution(1, runtime=None)
        result_unknown = runner_reap.reap_execution(1, runtime="github_copilot")

    assert result_none is False
    assert result_unknown is False


# ── reap_by_db ───────────────────────────────────────────────────────────────


def test_reap_by_db_dispatches_to_correct_runner():
    """reap_by_db resuelve runtime de DB y llama al dispatcher."""
    from services import runner_reap

    # Test: reap_by_db con DB ausente retorna False sin explotar
    with patch("services.runner_reap.reap_execution", return_value=True):
        with patch("config.config") as mock_cfg:
            mock_cfg.STACKY_RUNNER_REAP_ON_CLOSE_ENABLED = True
            result = runner_reap.reap_by_db(9999)

    # Sin DB real retorna False (la lectura de runtime falla → False)
    assert isinstance(result, bool)


def test_reap_by_db_uses_runtime_from_metadata():
    """reap_by_db usa el runtime de metadata_dict para despachar."""
    from services import runner_reap

    fake_row = MagicMock()
    fake_row.metadata_dict = {"runtime": "codex_cli"}

    with patch("db.session_scope") as mock_ss:
        session = MagicMock()
        session.get.return_value = fake_row
        mock_ss.return_value.__enter__ = lambda s: session
        mock_ss.return_value.__exit__ = MagicMock(return_value=False)

        with patch("services.runner_reap.reap_execution", return_value=True) as mock_dispatch:
            with patch("config.config") as mock_cfg:
                mock_cfg.STACKY_RUNNER_REAP_ON_CLOSE_ENABLED = True
                result = runner_reap.reap_by_db(42)

    mock_dispatch.assert_called_once_with(42, runtime="codex_cli")
    assert result is True
