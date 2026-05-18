"""Tests de integración del blueprint /api/pm — sin ADO real.

Inserta directamente en pm_risk_items y pm_sprint_snapshots para verificar
que los endpoints respetan el contrato definido en docs/11_PM_INTELLIGENCE_SUITE.md.
"""
from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")


@pytest.fixture(autouse=True)
def _clean_pm_tables():
    """Limpia state de PM pre-test para evitar cross-file pollution.

    Solo limpia ANTES del test. El cleanup post-test puede colisionar con
    el writer thread de stacky_logger (lock contention en SQLite shared cache).
    """
    import time
    from sqlalchemy.exc import OperationalError
    from db import init_db, session_scope
    from services.pm.models import PmRiskItem, PmSprintSnapshot, PmWorkItemComment

    init_db()
    for attempt in range(5):
        try:
            with session_scope() as session:
                session.query(PmRiskItem).delete()
                session.query(PmSprintSnapshot).delete()
                session.query(PmWorkItemComment).delete()
            break
        except OperationalError:
            time.sleep(0.1 * (2 ** attempt))
    yield


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("STACKY_REAPER_ENABLED", "false")
    monkeypatch.setenv("STACKY_MANIFEST_WATCHER_ENABLED", "false")
    monkeypatch.setenv("STACKY_OUTPUT_WATCHER_ENABLED", "false")

    from app import create_app
    from services.ticket_status import stop_stale_recovery
    from services.manifest_watcher import stop_manifest_watcher

    app = create_app()
    app.config.update(TESTING=True)
    stop_stale_recovery()
    stop_manifest_watcher()
    with app.test_client() as c:
        yield c
    stop_stale_recovery()
    stop_manifest_watcher()


def _insert_test_project_config(name: str = "TestPM", tracker_type: str = "azure_devops"):
    """Crea un config.json mínimo en backend/projects/<name> y lo deja activo."""
    from project_manager import PROJECTS_DIR, ACTIVE_FILE
    import json

    proj_dir = PROJECTS_DIR / name
    proj_dir.mkdir(parents=True, exist_ok=True)
    (proj_dir / "config.json").write_text(
        json.dumps({
            "name": name,
            "display_name": name,
            "issue_tracker": {"type": tracker_type, "organization": "x", "project": "y"},
        }),
        encoding="utf-8",
    )
    ACTIVE_FILE.parent.mkdir(parents=True, exist_ok=True)
    ACTIVE_FILE.write_text(json.dumps({"active": name}), encoding="utf-8")
    return name


def _cleanup_project(name: str = "TestPM"):
    from project_manager import PROJECTS_DIR, ACTIVE_FILE
    import shutil
    from db import session_scope
    from services.pm.models import PmRiskItem, PmSprintSnapshot

    with session_scope() as session:
        session.query(PmRiskItem).filter(PmRiskItem.project == name).delete()
        session.query(PmSprintSnapshot).filter(PmSprintSnapshot.project == name).delete()
    try:
        shutil.rmtree(PROJECTS_DIR / name)
    except FileNotFoundError:
        pass
    try:
        ACTIVE_FILE.unlink()
    except FileNotFoundError:
        pass


def _insert_risk(project: str, risk_id: str, **overrides):
    from db import session_scope
    from services.pm.models import PmRiskItem

    with session_scope() as session:
        r = PmRiskItem(
            project=project,
            sprint_id=overrides.get("sprint_id", "sprint-x"),
            risk_id=risk_id,
            category=overrides.get("category", "DELAY"),
            severity=overrides.get("severity", "MEDIUM"),
            description=overrides.get("description", "test risk"),
            rule=overrides.get("rule", "test_rule"),
        )
        r.affected_items = overrides.get("affected_items", [1, 2])
        session.add(r)


def _insert_snapshot(project: str, sprint_id: str = "sprint-x"):
    from db import session_scope
    from services.pm.models import PmSprintSnapshot

    with session_scope() as session:
        s = PmSprintSnapshot(
            project=project,
            sprint_id=sprint_id,
            sprint_name="Sprint Test",
            start_date=date(2026, 5, 1),
            end_date=date(2026, 5, 19),
            source="ado_live",
        )
        s.snapshot = {"kpis": {"total_items": 5}, "risks": []}
        session.add(s)


# ── tests ──────────────────────────────────────────────────────────────────────

def test_sprint_current_returns_404_when_no_snapshot(client):
    try:
        _insert_test_project_config("TestPM")
        r = client.get("/api/pm/sprint/current?project=TestPM")
        assert r.status_code == 404
        body = r.get_json()
        assert body["ok"] is False
        assert body["error"] == "NO_SNAPSHOT"
    finally:
        _cleanup_project("TestPM")


def test_sprint_current_returns_latest_snapshot(client):
    try:
        _insert_test_project_config("TestPM")
        _insert_snapshot("TestPM")
        r = client.get("/api/pm/sprint/current?project=TestPM")
        assert r.status_code == 200
        body = r.get_json()
        assert body["ok"] is True
        assert body["result"]["project"] == "TestPM"
        assert body["result"]["snapshot"]["sprint_name"] == "Sprint Test"
        assert body["result"]["ai_enriched"] is False
    finally:
        _cleanup_project("TestPM")


def test_risks_endpoint_lists_inserted_risks(client):
    try:
        _insert_test_project_config("TestPM")
        _insert_risk("TestPM", "RSK-aaa", severity="HIGH", rule="high_aging_item")
        _insert_risk("TestPM", "RSK-bbb", severity="MEDIUM", rule="data_quality_missing_points")
        r = client.get("/api/pm/risks?project=TestPM")
        assert r.status_code == 200
        body = r.get_json()
        assert body["ok"] is True
        assert body["result"]["count"] == 2
        ids = {x["risk_id"] for x in body["result"]["risks"]}
        assert ids == {"RSK-aaa", "RSK-bbb"}
        assert body["result"]["ai_enriched"] is False
    finally:
        _cleanup_project("TestPM")


def test_risks_endpoint_filters_by_severity(client):
    try:
        _insert_test_project_config("TestPM")
        _insert_risk("TestPM", "RSK-h1", severity="HIGH")
        _insert_risk("TestPM", "RSK-m1", severity="MEDIUM")
        r = client.get("/api/pm/risks?project=TestPM&severity=HIGH")
        assert r.status_code == 200
        ids = {x["risk_id"] for x in r.get_json()["result"]["risks"]}
        assert ids == {"RSK-h1"}
    finally:
        _cleanup_project("TestPM")


def test_risks_endpoint_filters_unacknowledged(client):
    try:
        _insert_test_project_config("TestPM")
        _insert_risk("TestPM", "RSK-pending")
        _insert_risk("TestPM", "RSK-done")
        # ack one
        client.post("/api/pm/risks/RSK-done/acknowledge", json={"acknowledged_by": "pm@e.com"})
        r = client.get("/api/pm/risks?project=TestPM&acknowledged=false")
        assert r.status_code == 200
        ids = {x["risk_id"] for x in r.get_json()["result"]["risks"]}
        assert ids == {"RSK-pending"}
    finally:
        _cleanup_project("TestPM")


def test_acknowledge_risk_marks_as_acknowledged(client):
    try:
        _insert_test_project_config("TestPM")
        _insert_risk("TestPM", "RSK-ack-1")
        r = client.post(
            "/api/pm/risks/RSK-ack-1/acknowledge",
            json={"acknowledged_by": "pm@empresa.com"},
        )
        assert r.status_code == 200
        body = r.get_json()
        assert body["ok"] is True
        assert body["result"]["acknowledged"] is True
        assert body["result"]["acknowledged_by"] == "pm@empresa.com"
        assert body["result"]["acknowledged_at"] is not None
    finally:
        _cleanup_project("TestPM")


def test_acknowledge_risk_idempotent(client):
    try:
        _insert_test_project_config("TestPM")
        _insert_risk("TestPM", "RSK-idem")
        r1 = client.post("/api/pm/risks/RSK-idem/acknowledge", json={"acknowledged_by": "a@e.com"})
        assert r1.status_code == 200
        r2 = client.post("/api/pm/risks/RSK-idem/acknowledge", json={"acknowledged_by": "b@e.com"})
        assert r2.status_code == 200
        body = r2.get_json()
        assert body["result"].get("already_acknowledged") is True
        # No debe sobrescribir el original
        assert body["result"]["acknowledged_by"] == "a@e.com"
    finally:
        _cleanup_project("TestPM")


def test_acknowledge_unknown_risk_returns_404(client):
    r = client.post("/api/pm/risks/RSK-does-not-exist/acknowledge")
    assert r.status_code == 404
    assert r.get_json()["error"] == "RISK_NOT_FOUND"


def test_pm_endpoints_reject_non_ado_projects(client):
    try:
        _insert_test_project_config("TestPM", tracker_type="jira")
        r = client.get("/api/pm/sprint/current?project=TestPM")
        assert r.status_code == 400
        assert r.get_json()["error"] == "TRACKER_NOT_SUPPORTED"
    finally:
        _cleanup_project("TestPM")

