"""
Unit tests for services.stacky_logger.

Verifies: enqueue, persistence, PII masking, truncation,
          HTTP request logging, agent events, purge.
"""
import json
import os
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")


# ── helpers ────────────────────────────────────────────────────────────────

def _flush(syslog, timeout: float = 1.0) -> None:
    """Drain the logger queue and persist all pending events synchronously."""
    # Give the background writer a brief window to dequeue first
    deadline = time.monotonic() + timeout
    while not syslog._q.empty() and time.monotonic() < deadline:
        time.sleep(0.01)
    # Force-flush any remaining events from the calling thread
    syslog.flush_now()


# ── fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def app_ctx():
    from app import create_app
    app = create_app()
    with app.app_context():
        yield app


@pytest.fixture(scope="module")
def syslog(app_ctx):
    from services.stacky_logger import logger
    return logger


@pytest.fixture(scope="module")
def db_session(app_ctx):
    from db import session_scope
    return session_scope


@pytest.fixture(scope="module")
def SystemLog(app_ctx):
    from models import SystemLog as SL
    return SL


# ── tests ──────────────────────────────────────────────────────────────────

class TestBasicLogging:
    def test_info_persisted(self, syslog, db_session, SystemLog, app_ctx):
        syslog.info("test.module", "test_info_event", context_data={"key": "value"})
        _flush(syslog)
        with db_session() as session:
            row = session.query(SystemLog).filter_by(
                source="test.module", action="test_info_event"
            ).order_by(SystemLog.id.desc()).first()
        assert row is not None
        assert row.level == "INFO"

    def test_error_with_exception(self, syslog, db_session, SystemLog, app_ctx):
        try:
            raise ValueError("boom!")
        except ValueError as e:
            exc = e
        syslog.error("test.module", "test_error_event", exc=exc)
        _flush(syslog)
        with db_session() as session:
            row = session.query(SystemLog).filter_by(
                source="test.module", action="test_error_event"
            ).order_by(SystemLog.id.desc()).first()
        assert row is not None
        assert row.level == "ERROR"
        assert row.error_json is not None
        error_data = json.loads(row.error_json)
        assert "ValueError" in error_data["type"]
        assert "boom!" in error_data["message"]
        assert "traceback" in error_data

    def test_warning_level(self, syslog, db_session, SystemLog, app_ctx):
        syslog.warning("test.module", "test_warn_event")
        _flush(syslog)
        with db_session() as session:
            row = session.query(SystemLog).filter_by(
                source="test.module", action="test_warn_event"
            ).order_by(SystemLog.id.desc()).first()
        assert row is not None
        assert row.level == "WARNING"


class TestPIIMasking:
    def test_sensitive_key_redacted(self, syslog, db_session, SystemLog, app_ctx):
        syslog.info(
            "test.security",
            "test_pii_masking",
            input_data={"password": "super_secret_123", "name": "Alice"},
        )
        _flush(syslog)
        with db_session() as session:
            row = session.query(SystemLog).filter_by(
                source="test.security", action="test_pii_masking"
            ).order_by(SystemLog.id.desc()).first()
        assert row is not None
        assert "super_secret_123" not in (row.input_json or "")
        assert "***REDACTED***" in (row.input_json or "")
        assert "Alice" in (row.input_json or "")  # non-sensitive kept

    def test_nested_sensitive_key_redacted(self, syslog, db_session, SystemLog, app_ctx):
        syslog.info(
            "test.security",
            "test_pii_nested",
            input_data={"auth": {"token": "ghp_abc123", "user": "alice"}},
        )
        _flush(syslog)
        with db_session() as session:
            row = session.query(SystemLog).filter_by(
                source="test.security", action="test_pii_nested"
            ).order_by(SystemLog.id.desc()).first()
        assert row is not None
        assert "ghp_abc123" not in (row.input_json or "")
        assert "alice" in (row.input_json or "")


class TestTruncation:
    def test_large_input_truncated(self, syslog, db_session, SystemLog, app_ctx):
        from services.stacky_logger import INPUT_MAX_BYTES
        big_str = "x" * (INPUT_MAX_BYTES + 5_000)
        syslog.info("test.truncation", "test_truncation_event", input_data=big_str)
        _flush(syslog)
        with db_session() as session:
            row = session.query(SystemLog).filter_by(
                source="test.truncation", action="test_truncation_event"
            ).order_by(SystemLog.id.desc()).first()
        assert row is not None
        assert len(row.input_json.encode("utf-8")) <= INPUT_MAX_BYTES + 100  # small overhead for "…[truncated]"
        assert "[truncated]" in row.input_json


class TestHTTPLogging:
    def test_request_helper(self, syslog, db_session, SystemLog, app_ctx):
        syslog.request("GET", "/api/tickets", 200, 42, user="test@user.com", request_id="req-abc")
        _flush(syslog)
        with db_session() as session:
            row = session.query(SystemLog).filter_by(
                source="http.middleware", action="http_request", request_id="req-abc"
            ).order_by(SystemLog.id.desc()).first()
        assert row is not None
        assert row.method == "GET"
        assert row.endpoint == "/api/tickets"
        assert row.status_code == 200
        assert row.duration_ms == 42
        assert row.user == "test@user.com"
        assert row.level == "INFO"

    def test_server_error_level(self, syslog, db_session, SystemLog, app_ctx):
        syslog.request("POST", "/api/agents/run", 500, 999, request_id="req-500")
        _flush(syslog)
        with db_session() as session:
            row = session.query(SystemLog).filter_by(
                source="http.middleware", request_id="req-500"
            ).order_by(SystemLog.id.desc()).first()
        assert row is not None
        assert row.level == "ERROR"

    def test_client_error_level(self, syslog, db_session, SystemLog, app_ctx):
        syslog.request("GET", "/api/tickets/999", 404, 5, request_id="req-404")
        _flush(syslog)
        with db_session() as session:
            row = session.query(SystemLog).filter_by(
                source="http.middleware", request_id="req-404"
            ).order_by(SystemLog.id.desc()).first()
        assert row is not None
        assert row.level == "WARNING"


class TestAgentEvents:
    def test_agent_started(self, syslog, db_session, SystemLog, app_ctx):
        syslog.agent_event(
            "agent_started",
            execution_id=9001,
            ticket_id=42,
            user="dev@test.com",
            input_data={"agent_type": "developer", "context_blocks": 3},
        )
        _flush(syslog)
        with db_session() as session:
            row = session.query(SystemLog).filter_by(
                action="agent_started", execution_id=9001
            ).order_by(SystemLog.id.desc()).first()
        assert row is not None
        assert row.ticket_id == 42
        assert row.user == "dev@test.com"
        assert "agent" in (row.tags_json or "")

    def test_agent_failed(self, syslog, db_session, SystemLog, app_ctx):
        try:
            raise RuntimeError("LLM timeout")
        except RuntimeError as e:
            exc = e
        syslog.agent_event(
            "agent_failed",
            execution_id=9002,
            ticket_id=43,
            level="ERROR",
            error_exc=exc,
            tags=["agent", "error"],
        )
        _flush(syslog)
        with db_session() as session:
            row = session.query(SystemLog).filter_by(
                action="agent_failed", execution_id=9002
            ).order_by(SystemLog.id.desc()).first()
        assert row is not None
        assert row.level == "ERROR"
        assert "LLM timeout" in (row.error_json or "")


class TestIntegrationLogging:
    def test_integration_call(self, syslog, db_session, SystemLog, app_ctx):
        syslog.integration_call(
            "ado",
            "create_comment",
            ticket_id=55,
            duration_ms=300,
            input_data={"text": "analysis published"},
            output_data={"comment_id": 12345},
        )
        _flush(syslog)
        with db_session() as session:
            row = session.query(SystemLog).filter_by(
                source="integration.ado", action="create_comment", ticket_id=55
            ).order_by(SystemLog.id.desc()).first()
        assert row is not None
        assert row.duration_ms == 300
        assert "ado" in (row.tags_json or "")


class TestRequestCorrelation:
    def test_request_id_propagation(self, syslog, db_session, SystemLog, app_ctx):
        rid = syslog.new_request_id()
        assert len(rid) == 36  # UUID format
        syslog.info("test.correlation", "test_rid_event")
        _flush(syslog)
        with db_session() as session:
            row = session.query(SystemLog).filter_by(
                source="test.correlation", action="test_rid_event", request_id=rid
            ).order_by(SystemLog.id.desc()).first()
        assert row is not None
        assert row.request_id == rid


class TestPurge:
    def test_purge_old_logs(self, syslog, db_session, SystemLog, app_ctx):
        from datetime import datetime, timedelta
        # Insert an old record manually
        with db_session() as session:
            old = SystemLog(
                timestamp=datetime.utcnow() - timedelta(days=200),
                level="INFO",
                source="test.purge",
                action="old_event",
            )
            session.add(old)

        deleted = syslog.purge_old_logs(days=90)
        assert deleted >= 1


class TestAPIEndpoints:
    """Smoke-test the /api/logs REST endpoints."""

    @pytest.fixture(scope="class")
    def client(self, app_ctx):
        app_ctx.config["TESTING"] = True
        with app_ctx.test_client() as c:
            yield c

    def test_list_logs(self, client, syslog):
        syslog.info("api.test", "api_list_test")
        _flush(syslog)
        r = client.get("/api/logs")
        assert r.status_code == 200
        data = r.get_json()
        assert "total" in data
        assert "items" in data
        assert isinstance(data["items"], list)

    def test_filter_by_level(self, client, syslog):
        syslog.critical("api.test", "api_critical_test")
        _flush(syslog)
        r = client.get("/api/logs?level=CRITICAL&source=api.test")
        assert r.status_code == 200
        data = r.get_json()
        assert all(item["level"] == "CRITICAL" for item in data["items"])

    def test_stats(self, client):
        r = client.get("/api/logs/stats")
        assert r.status_code == 200
        data = r.get_json()
        assert "total" in data
        assert "by_level" in data
        assert "by_source" in data

    def test_export_json(self, client):
        r = client.get("/api/logs/export?format=json&limit=10")
        assert r.status_code == 200
        assert "application/json" in r.content_type

    def test_export_csv(self, client):
        r = client.get("/api/logs/export?format=csv&limit=10")
        assert r.status_code == 200
        assert "text/csv" in r.content_type

    def test_frontend_ingest(self, client, db_session, SystemLog):
        r = client.post(
            "/api/logs/frontend",
            json={
                "level": "ERROR",
                "source": "component.RunButton",
                "action": "unhandled_error",
                "message": "Cannot read property of undefined",
                "stack": "Error: ...\n  at RunButton.tsx:42",
                "url": "http://localhost:5173",
            },
            headers={"X-User-Email": "test@test.com"},
        )
        assert r.status_code == 200
        assert r.get_json() == {"ok": True}

    def test_get_log_by_id(self, client, syslog, db_session, SystemLog):
        syslog.info("api.test", "api_get_by_id_test")
        _flush(syslog)
        with db_session() as session:
            row = session.query(SystemLog).filter_by(
                action="api_get_by_id_test"
            ).order_by(SystemLog.id.desc()).first()
            assert row is not None
            log_id = row.id

        r = client.get(f"/api/logs/{log_id}")
        assert r.status_code == 200
        data = r.get_json()
        assert data["id"] == log_id

    def test_get_log_not_found(self, client):
        r = client.get("/api/logs/999999999")
        assert r.status_code == 404
