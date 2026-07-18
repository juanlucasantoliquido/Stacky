"""Tests Plan 153 — publish_ledger transaccional + reconciliación."""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

# OBLIGATORIO antes de cualquier import de módulos de la app:
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")


# ── Fixtures / helpers ────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _fresh_db():
    """DB in-memory compartida: aislar cada test limpiando las tablas relevantes."""
    from db import init_db, session_scope
    init_db()
    from services.publish_ledger import PublishLedgerEntry
    from services.ado_publisher import AgentHtmlPublish
    from models import AgentExecution, Ticket
    with session_scope() as s:
        s.query(PublishLedgerEntry).delete()
        s.query(AgentHtmlPublish).delete()
        s.query(AgentExecution).delete()
        s.query(Ticket).delete()
    with session_scope() as s:
        s.add(Ticket(id=1, ado_id=1, project="p", title="t"))
    yield


def _add_execution(exec_id: int, marker: str | None = "pending"):
    from db import session_scope
    from models import AgentExecution
    md = json.dumps({"publish_intent": {"marker": marker}}) if marker else None
    with session_scope() as s:
        s.add(AgentExecution(
            id=exec_id, ticket_id=1, agent_type="business", status="completed",
            input_context_json="{}", started_by="test", metadata_json=md,
        ))


def _add_html_publish(exec_id: int, ado_id: int, status: str = "ok"):
    from db import session_scope
    from services.ado_publisher import AgentHtmlPublish
    with session_scope() as s:
        s.add(AgentHtmlPublish(
            execution_id=exec_id, ticket_id=1, ado_id=ado_id, html_path="x",
            html_sha256=f"sha{exec_id}", status=status, triggered_by="test",
        ))


def _ledger_row(exec_id: int):
    from db import session_scope
    from services.publish_ledger import PublishLedgerEntry
    with session_scope() as s:
        r = s.query(PublishLedgerEntry).filter(
            PublishLedgerEntry.execution_id == exec_id
        ).one_or_none()
        return r.to_dict() if r is not None else None


def _ok_publish_result(execution_id: int = 7):
    from services.ado_publisher import PublishResult
    return PublishResult(
        ok=True, status="ok", reason=None, ado_id=99, execution_id=execution_id,
        html_sha256="h", ado_response={}, record_id=5,
    )


# ── F0 (actualizado F1 paso 4) ────────────────────────────────────────────────

def test_replay_pending_bloquea_retry_sin_repost():
    """Un replay del ledger (pending) devuelve idempotent_replay y NO re-postea."""
    from services.agent_completion_internal import _attempt_publish

    post_calls = []
    with patch("config.config") as mock_cfg:
        mock_cfg.STACKY_PUBLISH_IDEMPOTENT_GUARD_ENABLED = True
        with patch("services.publish_ledger.try_acquire", return_value="replay_pending"):
            with patch(
                "services.ado_publisher.publish_from_execution",
                side_effect=lambda *a, **k: post_calls.append(1),
            ):
                result = _attempt_publish(execution_id=338, triggered_by="retry")

    assert result.get("event") == "publish.idempotent_replay"
    assert post_calls == []  # el retry queda bloqueado sin re-POST


def test_ledger_module_existe():
    from services.publish_ledger import migrate_legacy_markers, try_acquire
    assert callable(try_acquire)
    assert callable(migrate_legacy_markers)


# ── F1 — ledger transaccional ─────────────────────────────────────────────────

def test_try_acquire_gana_y_duplicado_clasifica():
    from services.publish_ledger import try_acquire
    assert try_acquire(1001) == "acquired"
    assert try_acquire(1001) == "replay_pending"


def test_lifecycle_posted():
    from services.publish_ledger import try_acquire, mark_posted
    assert try_acquire(1002) == "acquired"
    assert mark_posted(1002, ado_id=99, record_id=5) is True
    row = _ledger_row(1002)
    assert row["status"] == "posted"
    assert row["ado_ids"] == [99]
    assert try_acquire(1002) == "replay_posted"


def test_lifecycle_failed():
    from services.publish_ledger import try_acquire, mark_failed
    assert try_acquire(1003) == "acquired"
    assert mark_failed(1003, "boom") is True
    row = _ledger_row(1003)
    assert row["status"] == "failed"
    assert row["error"] == "boom"
    assert try_acquire(1003) == "replay_failed"


def test_release_borra_y_permite_reacquire():
    from services.publish_ledger import try_acquire, release
    assert try_acquire(1004) == "acquired"
    assert release(1004) is True
    assert try_acquire(1004) == "acquired"


def test_carrera_dos_attempt_publish_solo_un_post():
    from services.agent_completion_internal import _attempt_publish

    counter = {"n": 0}

    def _fake_publish(*a, **k):
        counter["n"] += 1
        return _ok_publish_result(execution_id=7)

    with patch("config.config") as mock_cfg:
        mock_cfg.STACKY_PUBLISH_IDEMPOTENT_GUARD_ENABLED = True
        with patch("services.ado_publisher.publish_from_execution", side_effect=_fake_publish):
            r1 = _attempt_publish(execution_id=7, triggered_by="run")
            r2 = _attempt_publish(execution_id=7, triggered_by="retry")

    assert counter["n"] == 1
    assert r1.get("ok") is True
    assert r2.get("event") == "publish.idempotent_replay"
    assert r2.get("ledger") == "replay_posted"


def test_publish_skipped_no_deja_fantasma():
    from services.agent_completion_internal import _attempt_publish
    from services.ado_publisher import PublishResult

    skipped = PublishResult(
        ok=False, status="skipped", reason="dup", ado_id=None, execution_id=8,
        html_sha256=None, ado_response=None, record_id=None,
    )
    with patch("config.config") as mock_cfg:
        mock_cfg.STACKY_PUBLISH_IDEMPOTENT_GUARD_ENABLED = True
        with patch("services.ado_publisher.publish_from_execution", return_value=skipped):
            _attempt_publish(execution_id=8, triggered_by="run")

    assert _ledger_row(8) is None  # release aplicado: sin fantasma pending


def test_ledger_roto_fallback_procede_sin_guardia():
    from services.agent_completion_internal import _attempt_publish

    counter = {"n": 0}

    def _fake_publish(*a, **k):
        counter["n"] += 1
        return _ok_publish_result(execution_id=9)

    with patch("config.config") as mock_cfg:
        mock_cfg.STACKY_PUBLISH_IDEMPOTENT_GUARD_ENABLED = True
        with patch("services.publish_ledger.try_acquire", side_effect=RuntimeError("ledger down")):
            with patch("services.ado_publisher.publish_from_execution", side_effect=_fake_publish):
                _attempt_publish(execution_id=9, triggered_by="run")

    assert counter["n"] == 1  # el POST ocurre igual (fallback sin guardia)


def test_flag_off_no_toca_ledger():
    from services.agent_completion_internal import _attempt_publish
    from services.publish_ledger import PublishLedgerEntry
    from db import session_scope

    with patch("config.config") as mock_cfg:
        mock_cfg.STACKY_PUBLISH_IDEMPOTENT_GUARD_ENABLED = False
        with patch("services.ado_publisher.publish_from_execution", return_value=_ok_publish_result(10)):
            _attempt_publish(execution_id=10, triggered_by="run")

    with session_scope() as s:
        assert s.query(PublishLedgerEntry).count() == 0


# ── F2 — migración + sweep + endpoints + métrica ──────────────────────────────

def test_migracion_marker_pending_sin_publicacion_queda_pending():
    from services.publish_ledger import migrate_legacy_markers
    _add_execution(2001, marker="pending")
    res = migrate_legacy_markers()
    assert res["migrated_pending"] == 1
    row = _ledger_row(2001)
    assert row["status"] == "pending"
    assert row["source"] == "migration"


def test_migracion_marker_con_publicacion_ok_queda_posted():
    from services.publish_ledger import migrate_legacy_markers
    _add_execution(2002, marker="pending")
    _add_html_publish(2002, ado_id=77, status="ok")
    res = migrate_legacy_markers()
    assert res["migrated_posted"] == 1
    row = _ledger_row(2002)
    assert row["status"] == "posted"
    assert row["ado_ids"] == [77]


def test_migracion_idempotente():
    from services.publish_ledger import migrate_legacy_markers
    _add_execution(2003, marker="pending")
    first = migrate_legacy_markers()
    assert first["migrated_pending"] == 1
    second = migrate_legacy_markers()
    assert second.get("migrated_pending", 0) == 0
    assert second.get("migrated_posted", 0) == 0


def test_migracion_sentinel_short_circuita():
    from services.publish_ledger import migrate_legacy_markers, _MIGRATION_SENTINEL_ID
    _add_execution(2004, marker="pending")
    migrate_legacy_markers()
    sentinel = _ledger_row(_MIGRATION_SENTINEL_ID)
    assert sentinel is not None
    assert sentinel["source"] == "migration_sentinel"
    second = migrate_legacy_markers()
    assert second.get("sentinel_skip") is True


def test_snapshot_y_metrica_ignoran_sentinel():
    from services.publish_ledger import (
        migrate_legacy_markers, snapshot_stuck, count_persist_failures,
    )
    # Sin markers: la migracion sella solo el centinela (posted).
    migrate_legacy_markers()
    snap = snapshot_stuck()
    assert snap["pending_stale"] == []
    assert snap["failed"] == []
    assert snap["counts"]["posted"] >= 1  # incluye al centinela
    assert count_persist_failures(datetime.utcnow() - timedelta(hours=1)) == 0


def test_migracion_no_muta_metadata():
    from services.publish_ledger import migrate_legacy_markers
    from db import session_scope
    from models import AgentExecution
    _add_execution(2005, marker="pending")
    with session_scope() as s:
        before = s.query(AgentExecution).filter(AgentExecution.id == 2005).one().metadata_json
    migrate_legacy_markers()
    with session_scope() as s:
        after = s.query(AgentExecution).filter(AgentExecution.id == 2005).one().metadata_json
    assert before == after


def test_snapshot_stuck_clasifica():
    from db import session_scope
    from services.publish_ledger import PublishLedgerEntry, snapshot_stuck, STATUS_PENDING, STATUS_FAILED, STATUS_POSTED
    old = datetime.utcnow() - timedelta(minutes=31)
    with session_scope() as s:
        s.add(PublishLedgerEntry(execution_id=3001, status=STATUS_PENDING, created_at=old, updated_at=old))
        s.add(PublishLedgerEntry(execution_id=3002, status=STATUS_FAILED, error="x"))
        s.add(PublishLedgerEntry(execution_id=3003, status=STATUS_POSTED))
    snap = snapshot_stuck()
    stale_ids = [r["execution_id"] for r in snap["pending_stale"]]
    failed_ids = [r["execution_id"] for r in snap["failed"]]
    assert 3001 in stale_ids
    assert 3002 in failed_ids
    assert 3003 not in stale_ids and 3003 not in failed_ids
    assert snap["counts"]["posted"] >= 1


# ── F2 endpoints (app Flask minimal que replica el nesting real bajo /api) ─────

def _make_client():
    from flask import Flask, Blueprint
    from api.publish_ledger import bp as pl_bp
    app = Flask(__name__)
    parent = Blueprint("api", __name__, url_prefix="/api")
    parent.register_blueprint(pl_bp)
    app.register_blueprint(parent)
    return app.test_client()


def test_endpoint_get_lista():
    client = _make_client()
    resp = client.get("/api/publish-ledger")
    assert resp.status_code == 200
    body = resp.get_json()
    assert "enabled" in body
    assert "pending_stale" in body
    assert "failed" in body
    assert "counts" in body


def test_endpoint_republish_desbloquea():
    from db import session_scope
    from services.publish_ledger import PublishLedgerEntry, STATUS_PENDING
    old = datetime.utcnow() - timedelta(minutes=31)
    with session_scope() as s:
        s.add(PublishLedgerEntry(execution_id=200, status=STATUS_PENDING, created_at=old, updated_at=old))

    client = _make_client()
    with patch("services.agent_completion_internal._attempt_publish") as mock_ap:
        mock_ap.return_value = {"ok": True, "event": "publish.succeeded"}
        resp = client.post("/api/publish-ledger/200/republish")

    assert resp.status_code == 200
    assert mock_ap.call_count == 1
    assert mock_ap.call_args.kwargs["triggered_by"] == "operator_republish"
    assert mock_ap.call_args.kwargs["execution_id"] == 200
    # la fila vieja fue liberada antes del reintento (patched _attempt_publish no recrea)
    assert _ledger_row(200) is None


def test_endpoint_republish_rechaza_posted():
    from services.publish_ledger import try_acquire, mark_posted
    try_acquire(201)
    mark_posted(201, ado_id=5)

    client = _make_client()
    with patch("services.agent_completion_internal._attempt_publish") as mock_ap:
        resp = client.post("/api/publish-ledger/201/republish")

    assert resp.status_code == 409
    assert mock_ap.call_count == 0


def test_endpoint_discard_marca_failed():
    from services.publish_ledger import try_acquire
    try_acquire(202)

    client = _make_client()
    resp = client.post("/api/publish-ledger/202/discard")
    assert resp.status_code == 200
    row = _ledger_row(202)
    assert row["status"] == "failed"
    assert row["error"] == "descartado por el operador"


def test_harness_health_persist_failure_count_exacto():
    from services.publish_ledger import try_acquire, mark_posted, count_persist_failures
    since = datetime.utcnow() - timedelta(hours=1)
    try_acquire(400)  # pending
    try_acquire(401)  # pending
    try_acquire(402)
    mark_posted(402, ado_id=1)  # posted (no cuenta)
    assert count_persist_failures(since) == 2
