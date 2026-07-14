"""Plan 126 F4 — API + gate doble (api/db_compare.py: data-candidates, data-diff, /health).

Ver Stacky Agents/docs/126_PLAN_DB_COMPARE_PARIDAD_DE_DATOS_TABLAS_PARAMETRO.md #F4.
"""
from __future__ import annotations

import os
import time

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

import pytest
from sqlalchemy import create_engine, text


class _FakeKeyring:
    def __init__(self):
        self.store = {}

    def set_password(self, svc, key, val):
        self.store[(svc, key)] = val

    def get_password(self, svc, key):
        return self.store.get((svc, key))

    def delete_password(self, svc, key):
        self.store.pop((svc, key), None)


def _seed_params(path, rows):
    eng = create_engine(f"sqlite:///{path}")
    with eng.connect() as c:
        c.execute(text("CREATE TABLE PARAMS (ID INTEGER PRIMARY KEY, NOMBRE TEXT, VALOR REAL)"))
        for row in rows:
            c.execute(text("INSERT INTO PARAMS (ID, NOMBRE, VALOR) VALUES (:id,:n,:v)"), {"id": row[0], "n": row[1], "v": row[2]})
        c.commit()


@pytest.fixture
def app_master_only(tmp_path, monkeypatch):
    """Master ON, hija de datos OFF (default) — para probar el gate doble."""
    import config as cfg
    import services.dbcompare_registry as reg
    import services.dbcompare_runs as runs
    import services.dbcompare_snapshot as snap

    orig_master = getattr(cfg.config, "STACKY_DB_COMPARE_ENABLED", False)
    orig_data = getattr(cfg.config, "STACKY_DB_COMPARE_DATA_DIFF_ENABLED", False)
    cfg.config.STACKY_DB_COMPARE_ENABLED = True
    cfg.config.STACKY_DB_COMPARE_DATA_DIFF_ENABLED = False
    monkeypatch.setattr(reg, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(snap, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(runs, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(reg, "keyring", _FakeKeyring())

    from app import create_app

    app = create_app()
    app.config["TESTING"] = True
    yield app
    cfg.config.STACKY_DB_COMPARE_ENABLED = orig_master
    cfg.config.STACKY_DB_COMPARE_DATA_DIFF_ENABLED = orig_data


@pytest.fixture
def app_data_on(app_master_only):
    import config as cfg

    cfg.config.STACKY_DB_COMPARE_DATA_DIFF_ENABLED = True
    yield app_master_only


def _c(app):
    return app.test_client()


def _register_and_run(c, tmp_path, src_rows, tgt_rows):
    db_a = tmp_path / "a.db"
    db_b = tmp_path / "b.db"
    _seed_params(db_a, src_rows)
    _seed_params(db_b, tgt_rows)
    c.post("/api/db-compare/environments", json={
        "alias": "test-a", "engine": "sqlite", "host": "localhost", "port": 0,
        "database": str(db_a), "username": "user",
    })
    c.post("/api/db-compare/environments", json={
        "alias": "test-b", "engine": "sqlite", "host": "localhost", "port": 0,
        "database": str(db_b), "username": "user",
    })
    c.post("/api/db-compare/environments/test-a/password", json={"password": "unused"})
    c.post("/api/db-compare/environments/test-b/password", json={"password": "unused"})

    r = c.post("/api/db-compare/compare", json={"source_alias": "test-a", "target_alias": "test-b", "mode": "fresh"})
    run_id = r.get_json()["run"]["run_id"]
    _poll(c, f"/api/db-compare/runs/{run_id}", lambda b: b.get("status") in ("done", "error"))
    return run_id


def _poll(c, url, done_pred, timeout=5.0):
    deadline = time.monotonic() + timeout
    body = None
    while time.monotonic() < deadline:
        body = c.get(url).get_json()
        if body and done_pred(body):
            return body
        time.sleep(0.02)
    return body


def test_flag_hija_off_403_aunque_master_on(app_master_only, tmp_path):
    c = _c(app_master_only)
    run_id = _register_and_run(c, tmp_path, [(1, "A", 1.0)], [(1, "A", 1.0)])
    assert c.get(f"/api/db-compare/runs/{run_id}/data-candidates").status_code == 403
    assert c.post(f"/api/db-compare/runs/{run_id}/data-diff", json={"tables": []}).status_code == 403


def test_health_incluye_data_diff_enabled(app_data_on):
    c = _c(app_data_on)
    body = c.get("/api/db-compare/health").get_json()
    assert body["data_diff_enabled"] is True


def test_candidates_lista_y_reason_sin_pk(app_data_on, tmp_path):
    c = _c(app_data_on)
    run_id = _register_and_run(c, tmp_path, [(1, "A", 1.0)], [(1, "A", 1.0)])
    body = c.get(f"/api/db-compare/runs/{run_id}/data-candidates").get_json()
    assert body["ok"] is True
    cands = {cand["table"]: cand for cand in body["candidates"]}
    assert cands["PARAMS"]["comparable"] is True
    assert cands["PARAMS"]["has_pk"] is True
    assert cands["PARAMS"]["reason"] == ""


def test_candidates_incluye_row_counts_best_effort(app_data_on, tmp_path):
    c = _c(app_data_on)
    run_id = _register_and_run(c, tmp_path, [(1, "A", 1.0), (2, "B", 2.0)], [(1, "A", 1.0)])
    body = c.get(f"/api/db-compare/runs/{run_id}/data-candidates").get_json()
    cand = next(cand for cand in body["candidates"] if cand["table"] == "PARAMS")
    assert cand["row_count_source"] == 2
    assert cand["row_count_target"] == 1


def test_data_diff_202_polling_done_sqlite(app_data_on, tmp_path):
    c = _c(app_data_on)
    run_id = _register_and_run(c, tmp_path, [(1, "A", 1.0), (2, "B", 2.0)], [(1, "A", 1.0)])
    r = c.post(f"/api/db-compare/runs/{run_id}/data-diff", json={"tables": [{"schema": "main", "table": "PARAMS"}]})
    assert r.status_code == 202

    final = _poll(
        c, f"/api/db-compare/runs/{run_id}",
        lambda b: (b.get("data_diff") or {}).get("status") in ("done", "error"),
    )
    dd = final["data_diff"]
    assert dd["status"] == "done"
    assert "main.PARAMS" in dd["tables"]


def test_mas_de_20_tablas_400(app_data_on, tmp_path):
    c = _c(app_data_on)
    run_id = _register_and_run(c, tmp_path, [(1, "A", 1.0)], [(1, "A", 1.0)])
    tables = [{"schema": "main", "table": f"T{i}"} for i in range(21)]
    r = c.post(f"/api/db-compare/runs/{run_id}/data-diff", json={"tables": tables})
    assert r.status_code == 400


def test_run_no_done_409(app_data_on):
    c = _c(app_data_on)
    r = c.post("/api/db-compare/runs/run_no_existe/data-diff", json={"tables": [{"schema": "main", "table": "X"}]})
    assert r.status_code in (404, 409)


def test_busy_409(app_data_on, tmp_path):
    c = _c(app_data_on)
    run_id = _register_and_run(c, tmp_path, [(1, "A", 1.0)], [(1, "A", 1.0)])
    body = {"tables": [{"schema": "main", "table": "PARAMS"}]}
    r1 = c.post(f"/api/db-compare/runs/{run_id}/data-diff", json=body)
    assert r1.status_code == 202
    r2 = c.post(f"/api/db-compare/runs/{run_id}/data-diff", json=body)
    assert r2.status_code == 409
