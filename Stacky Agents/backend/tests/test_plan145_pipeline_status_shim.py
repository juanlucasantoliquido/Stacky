"""Plan 145 F3 — ruta shim GET /api/v1/pipeline/status (200 estable) + filtro
de access-log de werkzeug para esa ruta ruidosa en el FileHandler de archivo.
"""
from __future__ import annotations

import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402
from flask import Flask  # noqa: E402

from api import api_bp  # noqa: E402
import services.local_file_logging as lfl  # noqa: E402


@pytest.fixture
def client():
    app = Flask(__name__)
    app.register_blueprint(api_bp)
    return app.test_client()


def test_shim_returns_200_by_default(client, monkeypatch):
    monkeypatch.delenv("STACKY_PIPELINE_STATUS_SHIM", raising=False)
    resp = client.get("/api/v1/pipeline/status")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "unknown"


def test_shim_disabled_returns_404(client, monkeypatch):
    monkeypatch.setenv("STACKY_PIPELINE_STATUS_SHIM", "false")
    resp = client.get("/api/v1/pipeline/status")
    assert resp.status_code == 404


def test_access_filter_drops_noisy_werkzeug_record():
    rec = logging.LogRecord(
        "werkzeug", logging.INFO, "", 0,
        '127.0.0.1 - - [16/Jul/2026] "GET /api/v1/pipeline/status?project=X HTTP/1.1" 404 -',
        None, None,
    )
    flt = lfl._AccessLogNoiseFilter(lfl._suppressed_paths())
    assert flt.filter(rec) is False


def test_access_filter_keeps_other_paths():
    rec = logging.LogRecord(
        "werkzeug", logging.INFO, "", 0,
        '127.0.0.1 - - [16/Jul/2026] "GET /api/health HTTP/1.1" 200 -',
        None, None,
    )
    flt = lfl._AccessLogNoiseFilter(lfl._suppressed_paths())
    assert flt.filter(rec) is True


def test_access_filter_ignores_non_werkzeug():
    rec = logging.LogRecord(
        "stacky.config", logging.INFO, "", 0,
        "mentions /api/v1/pipeline/status but is not an access log",
        None, None,
    )
    flt = lfl._AccessLogNoiseFilter(lfl._suppressed_paths())
    assert flt.filter(rec) is True
