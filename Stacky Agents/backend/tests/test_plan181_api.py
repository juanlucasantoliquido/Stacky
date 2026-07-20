"""Plan 181 F0 + F4 — Registro de la flag + API de prefs (blueprint
db_compare_masking): GET estado + POST override por columna, gate doble.

Ver Stacky Agents/docs/181_PLAN_MASKING_DETERMINISTA_DE_SECRETOS_EN_EL_DATA_DIFF_*.md #F0/#F4.
"""
from __future__ import annotations

import json
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

import pytest

from services import harness_flags

FLAG = "STACKY_DB_COMPARE_MASKING_ENABLED"


# ---------------------------------------------------------------------------
# F0 — flag registrada, categorizada, config attr
# ---------------------------------------------------------------------------


def test_flag_registrada_bool_on_requires_master():
    spec = harness_flags._REGISTRY_INDEX[FLAG]
    assert spec.type == "bool"
    assert spec.default is True
    assert spec.requires == "STACKY_DB_COMPARE_ENABLED"


def test_flag_en_categoria():
    assert harness_flags.categorize(FLAG) == "comparador_bd"


def test_config_attr_existe_bool():
    import config
    assert isinstance(config.config.STACKY_DB_COMPARE_MASKING_ENABLED, bool)


# ---------------------------------------------------------------------------
# F4 — API de prefs
# ---------------------------------------------------------------------------

RUN_ID = "run_181_api_001"
REAL_PW = "supersecret42"


def _run_with_password():
    return {
        "run_id": RUN_ID,
        "source_alias": "DEV", "target_alias": "TEST",
        "engine": "sqlserver", "mode": "fresh", "status": "done", "phase": "done",
        "started_at": "2026-07-18T12:00:00Z", "finished_at": "2026-07-18T12:00:10Z",
        "duration_ms": 10,
        "source_snapshot_id": None, "target_snapshot_id": None,
        "summary": {}, "diff": None, "error": None,
        "data_diff": {
            "status": "done", "phase": "done",
            "tables": {"dbo.RUSUARIOS": {
                "version": 1, "schema": "dbo", "table": "RUSUARIOS",
                "pk_cols": ["ID"], "columns": ["ID", "PASSWORD"],
                "column_types": {"ID": "INT", "PASSWORD": "VARCHAR(200)"},
                "columns_skipped": [],
                "only_source": [{"ID": "3", "PASSWORD": REAL_PW}],
                "only_target": [], "changed": [],
                "row_counts": {"source": 1, "target": 0},
                "truncated": False, "identical": False,
            }},
            "started_at": "2026-07-18T12:00:05Z", "finished_at": "2026-07-18T12:00:09Z",
            "error": None,
        },
    }


@pytest.fixture
def app_masking(tmp_path, monkeypatch):
    import config as cfg
    import services.dbcompare_runs as runs
    import services.dbcompare_masking as masking

    orig_master = getattr(cfg.config, "STACKY_DB_COMPARE_ENABLED", False)
    orig_mask = getattr(cfg.config, "STACKY_DB_COMPARE_MASKING_ENABLED", False)
    cfg.config.STACKY_DB_COMPARE_ENABLED = True
    cfg.config.STACKY_DB_COMPARE_MASKING_ENABLED = True
    for mod in (runs, masking):
        monkeypatch.setattr(mod, "data_dir", lambda: tmp_path)

    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    app._tmp_path = tmp_path  # type: ignore[attr-defined]
    yield app
    cfg.config.STACKY_DB_COMPARE_ENABLED = orig_master
    cfg.config.STACKY_DB_COMPARE_MASKING_ENABLED = orig_mask


def _c(app):
    return app.test_client()


def test_403_master_off_y_masking_off(app_masking):
    import config as cfg
    c = _c(app_masking)
    # master OFF
    cfg.config.STACKY_DB_COMPARE_ENABLED = False
    assert c.get("/api/db-compare/masking/prefs").status_code == 403
    assert c.post("/api/db-compare/masking/prefs", json={}).status_code == 403
    # master ON, masking OFF
    cfg.config.STACKY_DB_COMPARE_ENABLED = True
    cfg.config.STACKY_DB_COMPARE_MASKING_ENABLED = False
    assert c.get("/api/db-compare/masking/prefs").status_code == 403
    assert c.post("/api/db-compare/masking/prefs", json={}).status_code == 403
    cfg.config.STACKY_DB_COMPARE_MASKING_ENABLED = True


def test_get_prefs_vacias(app_masking):
    resp = _c(app_masking).get("/api/db-compare/masking/prefs")
    assert resp.status_code == 200
    assert resp.get_json() == {"ok": True, "prefs": {"version": 1, "overrides": {}}}


def test_post_visible_y_get_refleja(app_masking):
    c = _c(app_masking)
    r = c.post("/api/db-compare/masking/prefs", json={
        "schema": "dbo", "table": "RUSUARIOS", "column": "Password", "state": "visible",
    })
    assert r.status_code == 200
    assert r.get_json()["prefs"]["overrides"]["DBO.RUSUARIOS.PASSWORD"]["state"] == "visible"
    g = c.get("/api/db-compare/masking/prefs")
    assert "DBO.RUSUARIOS.PASSWORD" in g.get_json()["prefs"]["overrides"]


def test_post_auto_borra(app_masking):
    c = _c(app_masking)
    c.post("/api/db-compare/masking/prefs", json={
        "schema": "dbo", "table": "T", "column": "C", "state": "masked"})
    c.post("/api/db-compare/masking/prefs", json={
        "schema": "dbo", "table": "T", "column": "C", "state": "auto"})
    g = c.get("/api/db-compare/masking/prefs")
    assert "DBO.T.C" not in g.get_json()["prefs"]["overrides"]


def test_post_state_invalido_400(app_masking):
    r = _c(app_masking).post("/api/db-compare/masking/prefs", json={
        "schema": "dbo", "table": "T", "column": "C", "state": "nope"})
    assert r.status_code == 400


def test_post_campos_vacios_400(app_masking):
    r = _c(app_masking).post("/api/db-compare/masking/prefs", json={
        "schema": "dbo", "table": "", "column": "C", "state": "visible"})
    assert r.status_code == 400


def test_post_body_no_json_400(app_masking):
    r = _c(app_masking).post("/api/db-compare/masking/prefs",
                             data="no soy json", content_type="text/plain")
    assert r.status_code == 400


def test_post_luego_get_run_revela(app_masking):
    tmp = app_masking._tmp_path
    runs_dir = tmp / "db_compare" / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    (runs_dir / f"{RUN_ID}.json").write_text(
        json.dumps(_run_with_password(), ensure_ascii=False), encoding="utf-8")
    c = _c(app_masking)
    # sin override: enmascarado
    td = c.get(f"/api/db-compare/runs/{RUN_ID}").get_json()["data_diff"]["tables"]["dbo.RUSUARIOS"]
    assert td["only_source"][0]["PASSWORD"] == "••••42"
    # override visible -> crudo, masked_columns vacío
    c.post("/api/db-compare/masking/prefs", json={
        "schema": "dbo", "table": "RUSUARIOS", "column": "PASSWORD", "state": "visible"})
    td2 = c.get(f"/api/db-compare/runs/{RUN_ID}").get_json()["data_diff"]["tables"]["dbo.RUSUARIOS"]
    assert td2["only_source"][0]["PASSWORD"] == REAL_PW
    assert td2["masked_columns"] == []
