"""Plan 163 F3 — evento de shutdown estructurado en system_logs.

log_shutdown escribe UNA fila idempotente; install_shutdown_hook es no-op bajo
STACKY_TEST_MODE (C2). DB real en memoria (shared-cache).
"""
import sys
import os
import json
import atexit
import signal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # backend/

import pytest

from db import session_scope, init_db
from models import SystemLog
import services.lifecycle_log as lifecycle_log


@pytest.fixture(autouse=True)
def _reset_state():
    init_db()
    # La DB in-memory es shared-cache y persiste entre tests: limpiar las filas
    # de shutdown para que el conteo "exactamente 1" sea deterministico.
    with session_scope() as s:
        s.query(SystemLog).filter_by(source="app_lifecycle", action="shutdown").delete()
    lifecycle_log._LOGGED = False
    lifecycle_log._INSTALLED = False
    yield


def _shutdown_rows():
    with session_scope() as s:
        return (
            s.query(SystemLog)
            .filter_by(source="app_lifecycle", action="shutdown")
            .all()
        )


def test_log_shutdown_escribe_fila():
    lifecycle_log._LOGGED = False
    lifecycle_log.log_shutdown("test")
    with session_scope() as s:
        rows = s.query(SystemLog).filter_by(source="app_lifecycle", action="shutdown").all()
        assert len(rows) == 1
        ctx = json.loads(rows[0].context_json)
    assert ctx["reason"] == "test"
    assert ctx["pid"] == os.getpid()


def test_log_shutdown_idempotente():
    lifecycle_log._LOGGED = False
    lifecycle_log.log_shutdown("a")
    lifecycle_log.log_shutdown("b")
    with session_scope() as s:
        rows = s.query(SystemLog).filter_by(source="app_lifecycle", action="shutdown").all()
        assert len(rows) == 1
        assert json.loads(rows[0].context_json)["reason"] == "a"


def test_install_es_noop_en_test_mode(monkeypatch):
    # STACKY_TEST_MODE=1 lo setea conftest; forzamos por las dudas.
    monkeypatch.setenv("STACKY_TEST_MODE", "1")
    lifecycle_log._INSTALLED = False
    calls = []
    monkeypatch.setattr(atexit, "register", lambda *a, **k: calls.append(a))
    lifecycle_log.install_shutdown_hook()
    assert lifecycle_log._INSTALLED is False
    assert calls == []


def test_install_idempotente(monkeypatch):
    monkeypatch.setattr(lifecycle_log, "_in_test_mode", lambda: False)
    atexit_calls = []
    signal_calls = []
    monkeypatch.setattr(atexit, "register", lambda *a, **k: atexit_calls.append(a))
    monkeypatch.setattr(signal, "signal", lambda *a, **k: signal_calls.append(a))
    lifecycle_log._INSTALLED = False
    lifecycle_log.install_shutdown_hook()
    lifecycle_log.install_shutdown_hook()
    assert len(atexit_calls) == 1
    assert lifecycle_log._INSTALLED is True


def test_log_shutdown_no_lanza_sin_db(monkeypatch):
    def _raising(*a, **k):
        raise RuntimeError("db down")

    monkeypatch.setattr("db.session_scope", _raising)
    lifecycle_log._LOGGED = False
    # No debe propagar la excepcion (nunca bloquear el apagado).
    lifecycle_log.log_shutdown("x")
