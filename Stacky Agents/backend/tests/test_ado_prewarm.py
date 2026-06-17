"""Tests TDD para I0.3 — Pre-warming del caché ADO.

Spec:
- Endpoint POST /tickets/<ado_id>/prewarm existe.
- Flag OFF → {"status": "disabled"} con 200.
- TTL 0 → {"status": "disabled"} (caché inactivo).
- Fire-and-forget: no bloquea (respuesta inmediata).
- Si ya está caliente → {"status": "skipped"}.
- Nunca crea executions.
- Ticket no encontrado → {"status": "skipped", "reason": "ticket_not_found"}.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _make_app():
    """Crea la app Flask mínima con solo el blueprint de tickets."""
    from flask import Flask
    app = Flask(__name__)
    app.config["TESTING"] = True
    from api.tickets import bp
    app.register_blueprint(bp, url_prefix="/tickets")
    return app


# ---------------------------------------------------------------------------
# Test 1: Flag OFF → {"status": "disabled"}
# ---------------------------------------------------------------------------

def test_prewarm_flag_off(monkeypatch):
    from config import config
    monkeypatch.setattr(config, "STACKY_ADO_PREWARM_ENABLED", False, raising=False)
    monkeypatch.setattr(config, "STACKY_ADO_READ_CACHE_TTL_SEC", 60, raising=False)

    app = _make_app()
    with app.test_client() as c:
        resp = c.post("/tickets/42/prewarm")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "disabled"


# ---------------------------------------------------------------------------
# Test 2: TTL = 0 → {"status": "disabled"}
# ---------------------------------------------------------------------------

def test_prewarm_ttl_zero(monkeypatch):
    from config import config
    monkeypatch.setattr(config, "STACKY_ADO_PREWARM_ENABLED", True, raising=False)
    monkeypatch.setattr(config, "STACKY_ADO_READ_CACHE_TTL_SEC", 0, raising=False)

    app = _make_app()
    with app.test_client() as c:
        resp = c.post("/tickets/42/prewarm")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "disabled"


# ---------------------------------------------------------------------------
# Test 3: Ticket no encontrado → {"status": "skipped", "reason": "ticket_not_found"}
# ---------------------------------------------------------------------------

def test_prewarm_ticket_not_found(monkeypatch):
    from config import config
    monkeypatch.setattr(config, "STACKY_ADO_PREWARM_ENABLED", True, raising=False)
    monkeypatch.setattr(config, "STACKY_ADO_READ_CACHE_TTL_SEC", 60, raising=False)

    # Mock session_scope para devolver None
    mock_ticket = None
    mock_query = MagicMock()
    mock_query.filter.return_value.first.return_value = mock_ticket
    mock_sess = MagicMock()
    mock_sess.query.return_value = mock_query

    from contextlib import contextmanager

    @contextmanager
    def _mock_scope():
        yield mock_sess

    import api.tickets as _tickets_mod
    with patch.object(_tickets_mod, "session_scope", _mock_scope):
        app = _make_app()
        with app.test_client() as c:
            resp = c.post("/tickets/9999/prewarm")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "skipped"
    assert "ticket_not_found" in data.get("reason", "")


# ---------------------------------------------------------------------------
# Test 4: Ya caliente → {"status": "skipped"}
# ---------------------------------------------------------------------------

def test_prewarm_already_warm(monkeypatch):
    from config import config
    monkeypatch.setattr(config, "STACKY_ADO_PREWARM_ENABLED", True, raising=False)
    monkeypatch.setattr(config, "STACKY_ADO_READ_CACHE_TTL_SEC", 60, raising=False)

    # Mock ticket en DB
    mock_ticket = MagicMock()
    mock_ticket.id = 1
    mock_ticket.project = "PROJ"
    mock_ticket.stacky_project_name = "PROJ"
    mock_ticket.title = "Test ticket"
    mock_query = MagicMock()
    mock_query.filter.return_value.first.return_value = mock_ticket
    mock_sess = MagicMock()
    mock_sess.query.return_value = mock_query

    from contextlib import contextmanager

    @contextmanager
    def _mock_scope():
        yield mock_sess

    # Mock cache que dice que todo está caliente
    mock_cache = MagicMock()
    mock_cache.is_warm.return_value = True

    import api.tickets as _tickets_mod
    with patch.object(_tickets_mod, "session_scope", _mock_scope):
        with patch("services.ado_read_cache._singleton", mock_cache):
            app = _make_app()
            with app.test_client() as c:
                resp = c.post("/tickets/42/prewarm")

    assert resp.status_code == 200
    assert resp.get_json()["status"] == "skipped"


# ---------------------------------------------------------------------------
# Test 5: Fire-and-forget → devuelve "warming" inmediatamente
# ---------------------------------------------------------------------------

def test_prewarm_returns_warming(monkeypatch):
    from config import config
    monkeypatch.setattr(config, "STACKY_ADO_PREWARM_ENABLED", True, raising=False)
    monkeypatch.setattr(config, "STACKY_ADO_READ_CACHE_TTL_SEC", 60, raising=False)

    # Mock ticket en DB
    mock_ticket = MagicMock()
    mock_ticket.id = 1
    mock_ticket.project = "PROJ"
    mock_ticket.stacky_project_name = "PROJ"
    mock_ticket.title = "Test ticket"
    mock_query = MagicMock()
    mock_query.filter.return_value.first.return_value = mock_ticket
    mock_sess = MagicMock()
    mock_sess.query.return_value = mock_query

    from contextlib import contextmanager

    @contextmanager
    def _mock_scope():
        yield mock_sess

    # Cache frío
    mock_cache = MagicMock()
    mock_cache.is_warm.return_value = False
    mock_cache.get_or_fetch.return_value = ([], {})

    import api.tickets as _tickets_mod
    with patch.object(_tickets_mod, "session_scope", _mock_scope):
        with patch("services.ado_read_cache._singleton", mock_cache):
            # No se parchean similar_tickets ni ado_context: el thread los importa
            # lazy y sus excepciones quedan silenciadas (except Exception: pass).
            # get_or_fetch ya está mockeado → el fetch_fn nunca se llama.
            app = _make_app()
            with app.test_client() as c:
                resp = c.post("/tickets/42/prewarm")

    assert resp.status_code == 200
    assert resp.get_json()["status"] == "warming"


# ---------------------------------------------------------------------------
# Test 6: Nunca crea executions
# ---------------------------------------------------------------------------

def test_prewarm_never_creates_execution(monkeypatch):
    """El endpoint prewarm NO debe llamar a crear AgentExecution."""
    from config import config
    monkeypatch.setattr(config, "STACKY_ADO_PREWARM_ENABLED", False, raising=False)

    # Mock de session_scope que detectaría si se intentara crear una execution
    created_execs = []

    mock_query = MagicMock()
    mock_query.filter.return_value.first.return_value = None
    mock_sess = MagicMock()
    mock_sess.query.return_value = mock_query

    original_add = mock_sess.add
    def _detecting_add(obj):
        # Si alguien intenta agregar algo, lo registramos
        from models import AgentExecution
        if isinstance(obj, AgentExecution):
            created_execs.append(obj)
        return original_add(obj)
    mock_sess.add = _detecting_add

    app = _make_app()
    with app.test_client() as c:
        resp = c.post("/tickets/42/prewarm")

    assert resp.status_code == 200
    assert created_execs == [], "Prewarm NO debe crear AgentExecution"
