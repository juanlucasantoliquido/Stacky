"""Plan 74 F6 — Tests del blueprint migrator (API HITL).

8 casos.
"""
import json
import sqlite3
import uuid
from unittest.mock import MagicMock, patch

import pytest

from services.migrator_core import MigrationPlan, MigrationOp
from services.migrator_map import ensure_map_schema, save_plan_snapshot
from services.migrator_executor import MigrationResult


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_in_memory_db():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    ensure_map_schema(db)
    return db


def _empty_plan():
    return MigrationPlan(ops=[], counts_by_type={}, warnings=[])


def _plan_with_items(n=2):
    ops = [
        MigrationOp(
            op_kind="create_item",
            ado_id=str(i),
            ado_type="Issue",
            dest_parent_ado_id=None,
            payload={"title": f"Item {i}", "description_html": "", "labels": [],
                     "item_type": "Issue", "assignee": None},
            marker=f"<!-- stacky-migrated:ado:{i} -->",
        )
        for i in range(n)
    ]
    return MigrationPlan(ops=ops, counts_by_type={"Issue": n}, warnings=[])


# ── Fixtures de app ──────────────────────────────────────────────────────────

@pytest.fixture
def app_flag_on():
    import config as cfg
    original = getattr(cfg.config, "STACKY_MIGRATOR_ADO_TO_GITLAB_ENABLED", False)
    cfg.config.STACKY_MIGRATOR_ADO_TO_GITLAB_ENABLED = True
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    yield app
    cfg.config.STACKY_MIGRATOR_ADO_TO_GITLAB_ENABLED = original


@pytest.fixture
def app_flag_off():
    import config as cfg
    original = getattr(cfg.config, "STACKY_MIGRATOR_ADO_TO_GITLAB_ENABLED", False)
    cfg.config.STACKY_MIGRATOR_ADO_TO_GITLAB_ENABLED = False
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    yield app
    cfg.config.STACKY_MIGRATOR_ADO_TO_GITLAB_ENABLED = original


# ── Caso 1: POST /plan con flag OFF → 503 ───────────────────────────────────

def test_post_plan_flag_off(app_flag_off):
    with app_flag_off.test_client() as c:
        r = c.post("/api/migrator/plan", json={"stacky_project": "proj"})
        assert r.status_code == 503


# ── Caso 2: POST /plan con flag ON → 200 + counts + plan_id ─────────────────

def test_post_plan_flag_on(app_flag_on):
    db = _make_in_memory_db()
    mock_origin = MagicMock()
    mock_dest = MagicMock()
    mock_origin.fetch_open_items.return_value = [
        {"id": "1", "title": "T1", "description": "d", "item_type": "Issue"}
    ]
    mock_origin.fetch_all_comments.return_value = []
    mock_origin.fetch_attachments.return_value = []
    mock_dest.fetch_open_items.return_value = []

    with patch("api.migrator._get_db", return_value=db), \
         patch("api.migrator._get_providers", return_value=(mock_origin, mock_dest)):
        with app_flag_on.test_client() as c:
            r = c.post("/api/migrator/plan", json={"stacky_project": "proj"})

    assert r.status_code == 200
    data = r.get_json()
    assert "plan_id" in data
    assert "counts_by_type" in data
    assert data["counts_by_type"].get("Issue") == 1


# ── Caso 3: POST /execute sin confirmed=true → 400 (HITL gate) ───────────────

def test_post_execute_sin_confirmed(app_flag_on):
    db = _make_in_memory_db()
    with patch("api.migrator._get_db", return_value=db):
        with app_flag_on.test_client() as c:
            r = c.post("/api/migrator/execute", json={"plan_id": "x"})
    assert r.status_code == 400
    assert "confirmed" in r.get_json().get("error", "").lower()


# ── Caso 4: POST /execute con origen cambiado → 409 ─────────────────────────

def test_post_execute_drift_409(app_flag_on):
    db = _make_in_memory_db()
    plan_id = str(uuid.uuid4())
    # Guardar snapshot con hash ficticio
    save_plan_snapshot(db, plan_id=plan_id, stacky_project="proj",
                       counts_json='{"Issue": 1}', plan_hash="old-hash-123",
                       created_at="2026-06-29T00:00:00Z")

    mock_origin = MagicMock()
    mock_dest = MagicMock()
    # Origen ahora tiene 2 items (drift: más de lo que había en el snapshot)
    mock_origin.fetch_open_items.return_value = [
        {"id": "1", "title": "T1", "description": "d", "item_type": "Issue"},
        {"id": "2", "title": "T2", "description": "d", "item_type": "Issue"},
    ]
    mock_origin.fetch_all_comments.return_value = []
    mock_origin.fetch_attachments.return_value = []
    mock_dest.fetch_open_items.return_value = []

    with patch("api.migrator._get_db", return_value=db), \
         patch("api.migrator._get_providers", return_value=(mock_origin, mock_dest)):
        with app_flag_on.test_client() as c:
            r = c.post("/api/migrator/execute",
                       json={"plan_id": plan_id, "confirmed": True})

    assert r.status_code == 409
    assert "cambió" in r.get_json().get("error", "") or "drift" in r.get_json().get("error", "").lower()


# ── Caso 5: POST /execute con plan válido (hash coincide) → 200 ──────────────

def test_post_execute_valido(app_flag_on):
    db = _make_in_memory_db()
    plan_id = str(uuid.uuid4())

    mock_origin = MagicMock()
    mock_dest = MagicMock()
    mock_origin.fetch_open_items.return_value = [
        {"id": "1", "title": "T1", "description": "d", "item_type": "Issue"}
    ]
    mock_origin.fetch_all_comments.return_value = []
    mock_origin.fetch_attachments.return_value = []
    mock_dest.fetch_open_items.return_value = []
    mock_dest.create_item.return_value = {"id": "10", "iid": "10", "web_url": "u"}

    # Calcular el hash real del plan que generaría la app
    import hashlib
    from services.migrator_core import plan_migration
    plan = plan_migration(mock_origin, mock_dest, stacky_project="proj", existing_map={})
    sorted_ids = sorted(op.ado_id for op in plan.ops if op.op_kind == "create_item")
    payload = json.dumps({"ids": sorted_ids, "counts": plan.counts_by_type}, sort_keys=True)
    real_hash = hashlib.sha256(payload.encode()).hexdigest()

    save_plan_snapshot(db, plan_id=plan_id, stacky_project="proj",
                       counts_json=json.dumps(plan.counts_by_type),
                       plan_hash=real_hash, created_at="2026-06-29T00:00:00Z")

    # Reset mocks para la segunda llamada (el execute re-corre plan_migration)
    mock_origin.fetch_open_items.return_value = [
        {"id": "1", "title": "T1", "description": "d", "item_type": "Issue"}
    ]
    mock_origin.fetch_all_comments.return_value = []
    mock_origin.fetch_attachments.return_value = []
    mock_dest.fetch_open_items.return_value = []

    with patch("api.migrator._get_db", return_value=db), \
         patch("api.migrator._get_providers", return_value=(mock_origin, mock_dest)):
        with app_flag_on.test_client() as c:
            r = c.post("/api/migrator/execute",
                       json={"plan_id": plan_id, "confirmed": True})

    assert r.status_code == 200
    data = r.get_json()
    assert "applied" in data
    assert "skipped" in data


# ── Caso 6: GET /mapping devuelve JSON ───────────────────────────────────────

def test_get_mapping_json(app_flag_on):
    db = _make_in_memory_db()
    from services.migrator_map import upsert_mapping
    upsert_mapping(db, stacky_project="proj", ado_id="1", ado_type="Issue",
                   gitlab_iid="10", gitlab_web_url="u", marker="m", migration_run="r")

    with patch("api.migrator._get_db", return_value=db):
        with app_flag_on.test_client() as c:
            r = c.get("/api/migrator/proj/mapping")

    assert r.status_code == 200
    data = r.get_json()
    assert data["total"] == 1
    assert data["mapping"][0]["ado_id"] == "1"


# ── Caso 7: GET /mapping con Accept: text/csv → CSV descargable ──────────────

def test_get_mapping_csv(app_flag_on):
    db = _make_in_memory_db()
    from services.migrator_map import upsert_mapping
    upsert_mapping(db, stacky_project="proj", ado_id="2", ado_type="Epic",
                   gitlab_iid="20", gitlab_web_url="u", marker="m", migration_run="r")

    with patch("api.migrator._get_db", return_value=db):
        with app_flag_on.test_client() as c:
            r = c.get("/api/migrator/proj/mapping",
                      headers={"Accept": "text/csv"})

    assert r.status_code == 200
    assert "text/csv" in r.content_type
    assert "ado_id" in r.data.decode()  # header CSV


# ── Caso 8: GET /runs lista corridas ordenadas por timestamp desc ─────────────

def test_get_runs(app_flag_on):
    db = _make_in_memory_db()
    from services.migrator_map import upsert_mapping
    upsert_mapping(db, stacky_project="proj", ado_id="1", ado_type="Issue",
                   gitlab_iid="10", gitlab_web_url="u", marker="m", migration_run="run-alpha")
    upsert_mapping(db, stacky_project="proj", ado_id="2", ado_type="Issue",
                   gitlab_iid="20", gitlab_web_url="u", marker="m", migration_run="run-beta")

    with patch("api.migrator._get_db", return_value=db):
        with app_flag_on.test_client() as c:
            r = c.get("/api/migrator/proj/runs")

    assert r.status_code == 200
    data = r.get_json()
    assert "runs" in data
    assert len(data["runs"]) >= 1
