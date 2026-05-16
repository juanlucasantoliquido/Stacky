"""Tests para la correlación X-Request-ID frontend ↔ backend (Fase 2).

Verifica que:
  - api._helpers.get_request_id() devuelve el header del cliente cuando viene.
  - El middleware before_request propaga el X-Request-ID al stacky_logger y
    a flask.g, y el response carga el mismo ID en su header X-Request-ID.
  - Si el cliente NO envía X-Request-ID, el backend genera uno.
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


@pytest.fixture
def client():
    from app import create_app

    app = create_app()
    app.config.update(TESTING=True)
    # Apagar el guardian para no contaminar logs durante el test.
    from services.ticket_status import stop_stale_recovery
    stop_stale_recovery()
    with app.test_client() as c:
        yield c
    stop_stale_recovery()


def test_response_echoes_client_request_id(client):
    """Si el cliente manda X-Request-ID, la response lo devuelve sin tocar."""
    rid = "deadbeef-dead-4dad-beef-deadbeefdead"
    r = client.get("/api/tickets/", headers={"X-Request-ID": rid})
    # El endpoint puede responder con cualquier status válido (no nos importa
    # la lógica del listing — solo el middleware).
    assert r.status_code < 500
    assert r.headers.get("X-Request-ID") == rid


def test_response_generates_request_id_when_missing(client):
    """Sin X-Request-ID del cliente, el backend genera uno y lo expone.

    /api/health está en _SKIP_LOG_PATHS y no atraviesa el after_request que
    setea el header — por eso usamos /api/tickets/ que sí lo atraviesa.
    """
    r = client.get("/api/tickets/")
    assert r.status_code < 500
    server_rid = r.headers.get("X-Request-ID")
    assert server_rid is not None and len(server_rid) >= 16


def test_get_request_id_uses_client_header():
    """get_request_id() prioriza el header del cliente sobre flask.g."""
    from api._helpers import get_request_id
    from flask import Flask, g

    app = Flask(__name__)

    captured: dict = {}

    @app.route("/probe", methods=["POST"])
    def _probe():
        captured["rid"] = get_request_id()
        return {"ok": True}

    with app.test_client() as c:
        c.post("/probe", headers={"X-Request-ID": "abc-123"})

    assert captured["rid"] == "abc-123"


def test_get_request_id_falls_back_to_flask_g():
    """Sin header, get_request_id() usa flask.g.request_id si está seteado."""
    from api._helpers import get_request_id
    from flask import Flask, g

    app = Flask(__name__)

    captured: dict = {}

    @app.before_request
    def _bind_rid():
        g.request_id = "from-g-12345"

    @app.route("/probe", methods=["POST"])
    def _probe():
        captured["rid"] = get_request_id()
        return {"ok": True}

    with app.test_client() as c:
        c.post("/probe")  # sin X-Request-ID

    assert captured["rid"] == "from-g-12345"
