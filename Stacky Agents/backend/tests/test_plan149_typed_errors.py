"""Plan 149 — F0/F1/F2: contrato de errores tipados + handler transversal + endpoints."""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


# ── F0 — StackyApiError + build_error_envelope ──────────────────────────────


def test_stackyapierror_defaults():
    from api.errors import StackyApiError

    exc = StackyApiError("x")
    assert exc.http_status == 500
    assert exc.error_type == "internal"


def test_validation_error_maps_422():
    from api.errors import ValidationError

    exc = ValidationError("bad")
    assert exc.http_status == 422
    assert exc.error_type == "validation"


def test_build_error_envelope_shape():
    from api.errors import build_error_envelope

    env = build_error_envelope(
        error_type="internal", message="boom", request_id="rid-1",
        exec_id=None, endpoint="/api/x", method="GET",
    )
    assert set(env.keys()) == {
        "ok", "error", "error_type", "message", "request_id", "exec_id",
        "endpoint", "method",
    }
    assert env["ok"] is False
    assert env["error"] == env["message"]


def test_envelope_conserves_error_key_semantics():
    """C2 — `.error` es el mensaje humano (legacy), NO el token `error_type`."""
    from api.errors import build_error_envelope

    env = build_error_envelope(
        error_type="validation", message="campo x", request_id="rid-2",
        exec_id=None, endpoint="/api/x", method="POST",
    )
    assert env["error"] == "campo x"
    assert env["error_type"] == "validation"
    assert env["error"] != env["error_type"]


# ── F1 — handler transversal (app.py:508) emite envelope tipado ─────────────


import logging as _logging

import pytest


@pytest.fixture
def app():
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def test_handler_maps_stackyapierror(app, client):
    from api.errors import ValidationError

    @app.route("/__test_plan149_f1_validation")
    def _boom():
        raise ValidationError("campo x")

    resp = client.get("/__test_plan149_f1_validation")
    assert resp.status_code == 422
    body = resp.get_json()
    assert body["error_type"] == "validation"
    assert body["message"] == "campo x"
    assert body["error"] == "campo x"
    assert body["ok"] is False


def test_handler_typed_500_for_generic_exception(app, client):
    @app.route("/__test_plan149_f1_generic500")
    def _boom():
        raise RuntimeError("boom")

    resp = client.get("/__test_plan149_f1_generic500")
    assert resp.status_code == 500
    body = resp.get_json()
    assert body["error_type"] == "internal"
    assert body["message"] == "Internal server error"
    assert body["error"] == "Internal server error"
    assert "request_id" in body


def test_handler_5xx_logs_at_error_with_traceback(app, client, caplog):
    """C1 — 5xx tipado se loguea a ERROR (logger.exception, traceback); 4xx NO."""
    from api.errors import UpstreamError, ValidationError

    @app.route("/__test_plan149_f1_5xx_log")
    def _boom5xx():
        raise UpstreamError("db caída")

    @app.route("/__test_plan149_f1_4xx_log")
    def _boom4xx():
        raise ValidationError("x")

    with caplog.at_level(_logging.INFO):
        caplog.clear()
        resp5 = client.get("/__test_plan149_f1_5xx_log")
        assert resp5.status_code == 502
        error_records_5xx = [r for r in caplog.records if r.levelno >= _logging.ERROR]
        assert error_records_5xx, "un 5xx tipado DEBE loguear a ERROR (traceback), no quedar mudo"

        caplog.clear()
        resp4 = client.get("/__test_plan149_f1_4xx_log")
        assert resp4.status_code == 422
        error_records_4xx = [r for r in caplog.records if r.levelno >= _logging.ERROR]
        assert not error_records_4xx, "un 4xx (cliente) NO debe loguearse a ERROR, solo WARNING"


def test_handler_includes_exec_id_when_set(app, client):
    from api.errors import UpstreamError, set_exec_id

    @app.route("/__test_plan149_f1_exec_id")
    def _boom():
        set_exec_id(77)
        raise UpstreamError("x")

    resp = client.get("/__test_plan149_f1_exec_id")
    body = resp.get_json()
    assert body["exec_id"] == 77


def test_handler_legacy_shape_when_flag_off(app, client, monkeypatch):
    """Prueba de fuego: con la flag OFF, el body debe ser EXACTAMENTE
    {"error": ..., "request_id": ...} sin error_type, byte-a-byte igual al legacy."""
    import config as cfg
    monkeypatch.setattr(cfg.config, "STACKY_TYPED_ERROR_ENVELOPE_ENABLED", False)

    @app.route("/__test_plan149_f1_legacy_shape")
    def _boom():
        raise RuntimeError("boom")

    resp = client.get("/__test_plan149_f1_legacy_shape")
    assert resp.status_code == 500
    body = resp.get_json()
    assert set(body.keys()) == {"error", "request_id"}
    assert body["error"] == "Internal server error"


def test_http_exception_passthrough(app, client):
    from flask import abort

    @app.route("/__test_plan149_f1_abort404")
    def _boom():
        abort(404)

    resp = client.get("/__test_plan149_f1_abort404")
    assert resp.status_code == 404
    body = resp.get_json(silent=True) or {}
    assert "error_type" not in body


# ── F2 — endpoints objetivo: agents/run, devops/console/* ───────────────────


def _mute_run_side_effects(monkeypatch):
    """Aísla /api/agents/run de rutas laterales pesadas (auto-assign, run_guard)
    no relacionadas con F2, que golpean SQLAlchemy en threads separados y son
    causa conocida de crash nativo en este entorno de test (gotcha preexistente,
    no relacionado con el mapeo de excepciones que F2 instrumenta)."""
    import services.ticket_assigner as ta_mod
    monkeypatch.setattr(ta_mod, "auto_assign_on_run", lambda *a, **kw: None)
    import services.run_guard as rg_mod
    monkeypatch.setattr(rg_mod, "find_active_run", lambda *a, **kw: None)


def test_agents_run_typed_error_on_dispatch_failure(client, monkeypatch):
    """C1+C6 — fallo ESPERADO del dispatcher (RuntimeError) → 500 tipado."""
    _mute_run_side_effects(monkeypatch)
    import agent_runner

    def _boom(**kwargs):
        raise RuntimeError("dispatch failed")

    monkeypatch.setattr(agent_runner, "run_agent", _boom)

    resp = client.post("/api/agents/run", json={"agent_type": "developer", "ticket_id": 1})
    assert resp.status_code == 500
    body = resp.get_json()
    assert body["error_type"] == "internal"


def test_agents_run_bug_propagates_untyped_500(client, monkeypatch, caplog):
    """C1 — bug INESPERADO (AttributeError) NO se reetiqueta como fallo esperado:
    propaga a la rama unhandled_exception (ERROR + traceback), no typed_api_error."""
    _mute_run_side_effects(monkeypatch)
    import agent_runner

    def _boom(**kwargs):
        raise AttributeError("bug")

    monkeypatch.setattr(agent_runner, "run_agent", _boom)

    with caplog.at_level(_logging.INFO):
        caplog.clear()
        resp = client.post("/api/agents/run", json={"agent_type": "developer", "ticket_id": 1})
        assert resp.status_code == 500
        body = resp.get_json()
        assert body["error_type"] == "internal"
        messages = " ".join(r.getMessage() for r in caplog.records)
        assert "unhandled exception" in messages
        assert "typed 5xx" not in messages


def test_devops_console_exec_upstream_typed(app, client, monkeypatch):
    """C1 — fallo de transporte ESPERADO (ConnectionError) → 502 tipado 'upstream'."""
    import config as cfg
    monkeypatch.setattr(cfg.config, "STACKY_DEVOPS_REMOTE_CONSOLE_ENABLED", True)
    monkeypatch.setattr(cfg.config, "STACKY_DEVOPS_SERVERS_ENABLED", True)

    import services.remote_exec as remote_exec_mod

    def _boom(*a, **kw):
        raise ConnectionError("no route to host")

    monkeypatch.setattr(remote_exec_mod, "run_remote", _boom)

    resp = client.post("/api/devops/console/exec", json={"alias": "s1", "command": "Get-Process"})
    assert resp.status_code == 502
    body = resp.get_json()
    assert body["error_type"] == "upstream"


def test_devops_console_exec_bug_propagates_500(app, client, monkeypatch):
    """C1 — bug INESPERADO (TypeError) propaga a 500, NO se enmascara como 502."""
    import config as cfg
    monkeypatch.setattr(cfg.config, "STACKY_DEVOPS_REMOTE_CONSOLE_ENABLED", True)
    monkeypatch.setattr(cfg.config, "STACKY_DEVOPS_SERVERS_ENABLED", True)

    import services.remote_exec as remote_exec_mod

    def _boom(*a, **kw):
        raise TypeError("bug")

    monkeypatch.setattr(remote_exec_mod, "run_remote", _boom)

    resp = client.post("/api/devops/console/exec", json={"alias": "s1", "command": "Get-Process"})
    assert resp.status_code == 500
    body = resp.get_json()
    assert body["error_type"] == "internal"


def test_devops_console_conversations_list_typed_on_db_error(app, client, monkeypatch):
    from contextlib import contextmanager

    import config as cfg
    monkeypatch.setattr(cfg.config, "STACKY_DEVOPS_REMOTE_CONSOLE_ENABLED", True)

    @contextmanager
    def _boom_session_scope():
        raise RuntimeError("db boom")
        yield  # pragma: no cover — nunca se alcanza

    import db as db_mod
    monkeypatch.setattr(db_mod, "session_scope", _boom_session_scope)

    resp = client.get("/api/devops/console/conversations?server=s1")
    assert resp.status_code == 500
    body = resp.get_json()
    assert body["error_type"] == "internal"
    assert body["endpoint"] == "/api/devops/console/conversations"
