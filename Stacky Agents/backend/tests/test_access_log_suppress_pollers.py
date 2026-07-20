"""Plan 156 F5 — Tests del filtro de access-log ampliado.

Verifica que los pollers 200 de no-op (diag/local, cost-cap, streak) + el nuevo
/api/executions/summary se descarten del FileHandler, sin sobre-suprimir
/api/executions/history ni /api/executions/<id>, respetando otros loggers y el
mecanismo env STACKY_ACCESS_LOG_SUPPRESS_PATHS.

Unitario del filtro, sin red: construye LogRecord de nombre "werkzeug" con
mensajes de acceso simulados.
"""
import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

from services.local_file_logging import (  # noqa: E402
    _AccessLogNoiseFilter,
    _suppressed_paths,
)


def _werkzeug_record(access_line: str) -> logging.LogRecord:
    return logging.LogRecord(
        name="werkzeug",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg='%s - - "%s" 200 -',
        args=("127.0.0.1", access_line),
        exc_info=None,
    )


def test_suprime_pollers_nuevos():
    f = _AccessLogNoiseFilter(_suppressed_paths())
    for path in (
        "GET /api/diag/local HTTP/1.1",
        "GET /api/cost-cap HTTP/1.1",
        "GET /api/streak HTTP/1.1",
        "GET /api/executions/summary?scope=all_projects HTTP/1.1",
    ):
        assert f.filter(_werkzeug_record(path)) is False, path


def test_no_suprime_history_ni_id():
    f = _AccessLogNoiseFilter(_suppressed_paths())
    assert f.filter(_werkzeug_record("GET /api/executions/history HTTP/1.1")) is True
    assert f.filter(_werkzeug_record("GET /api/executions/42 HTTP/1.1")) is True


def test_no_suprime_otros_loggers():
    f = _AccessLogNoiseFilter(_suppressed_paths())
    rec = logging.LogRecord(
        name="stacky",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="algo sobre /api/diag/local que NO es un access-log de werkzeug",
        args=None,
        exc_info=None,
    )
    assert f.filter(rec) is True


def test_env_extra_sigue_funcionando(monkeypatch):
    monkeypatch.setenv("STACKY_ACCESS_LOG_SUPPRESS_PATHS", "/api/foo")
    paths = _suppressed_paths()
    assert "/api/foo" in paths
    # El default nuevo sigue presente además del extra del operador.
    assert "/api/diag/local" in paths
    assert "/api/executions/summary" in paths
    f = _AccessLogNoiseFilter(paths)
    assert f.filter(_werkzeug_record("GET /api/foo HTTP/1.1")) is False
