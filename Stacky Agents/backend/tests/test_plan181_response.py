"""Plan 181 F3 — Transformación de salida: apply_to_run_response + hunk en
get_run_route + sellado de la lista (fix C1). Cliente Flask + run sembrado en
tmp_path con un data_diff que contiene la columna PASSWORD con valores reales.

Ver Stacky Agents/docs/181_PLAN_MASKING_DETERMINISTA_DE_SECRETOS_EN_EL_DATA_DIFF_*.md #F3.
"""
from __future__ import annotations

import json
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

import pytest

from tests._plan125_fixtures import make_schema_obj

RUN_ID = "run_181_test_001"
REAL_PW_ONLY_SRC = "supersecret42"
REAL_PW_ONLY_TGT = "hunter2zzzzz"
REAL_PW_CHG_SRC = "oldpass9988"
REAL_PW_CHG_TGT = "newpass7766"


def _table_diff():
    return {
        "version": 1,
        "schema": "dbo",
        "table": "RUSUARIOS",
        "pk_cols": ["ID"],
        "columns": ["ID", "NOMBRE", "PASSWORD"],
        "column_types": {"ID": "INT", "NOMBRE": "VARCHAR(50)", "PASSWORD": "VARCHAR(200)"},
        "columns_skipped": [],
        "only_source": [{"ID": "3", "NOMBRE": "carlos", "PASSWORD": REAL_PW_ONLY_SRC}],
        "only_target": [{"ID": "4", "NOMBRE": "diana", "PASSWORD": REAL_PW_ONLY_TGT}],
        "changed": [{"pk": {"ID": "2"}, "cells": {"PASSWORD": {"source": REAL_PW_CHG_SRC, "target": REAL_PW_CHG_TGT}}}],
        "row_counts": {"source": 3, "target": 3},
        "truncated": False,
        "identical": False,
    }


def _schema_diff():
    return {
        "version": 1,
        "engine": "sqlserver",
        "source": {"alias": "DEV", "snapshot_id": "DEV_snap", "content_hash": "h1"},
        "target": {"alias": "TEST", "snapshot_id": "TEST_snap", "content_hash": "h2"},
        "items": [],
        "summary": {},
    }


def _run(**over):
    run = {
        "run_id": RUN_ID,
        "source_alias": "DEV", "target_alias": "TEST",
        "engine": "sqlserver", "mode": "fresh", "status": "done", "phase": "done",
        "started_at": "2026-07-18T12:00:00Z", "finished_at": "2026-07-18T12:00:10Z",
        "duration_ms": 10,
        "source_snapshot_id": "DEV_snap", "target_snapshot_id": "TEST_snap",
        "summary": {}, "diff": _schema_diff(), "error": None,
        "data_diff": {
            "status": "done", "phase": "done",
            "tables": {"dbo.RUSUARIOS": _table_diff()},
            "started_at": "2026-07-18T12:00:05Z", "finished_at": "2026-07-18T12:00:09Z",
            "error": None,
        },
    }
    run.update(over)
    return run


@pytest.fixture
def app_masking(tmp_path, monkeypatch):
    import config as cfg
    import services.dbcompare_runs as runs
    import services.dbcompare_snapshot as snap
    import services.dbcompare_scripts as scripts
    import services.dbcompare_masking as masking

    orig_master = getattr(cfg.config, "STACKY_DB_COMPARE_ENABLED", False)
    orig_mask = getattr(cfg.config, "STACKY_DB_COMPARE_MASKING_ENABLED", False)
    orig_data = getattr(cfg.config, "STACKY_DB_COMPARE_DATA_DIFF_ENABLED", False)
    cfg.config.STACKY_DB_COMPARE_ENABLED = True
    cfg.config.STACKY_DB_COMPARE_MASKING_ENABLED = True
    cfg.config.STACKY_DB_COMPARE_DATA_DIFF_ENABLED = True
    for mod in (runs, snap, scripts, masking):
        monkeypatch.setattr(mod, "data_dir", lambda: tmp_path)

    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    app._tmp_path = tmp_path  # type: ignore[attr-defined]
    yield app
    cfg.config.STACKY_DB_COMPARE_ENABLED = orig_master
    cfg.config.STACKY_DB_COMPARE_MASKING_ENABLED = orig_mask
    cfg.config.STACKY_DB_COMPARE_DATA_DIFF_ENABLED = orig_data


def _seed_run(tmp_path, run):
    runs_dir = tmp_path / "db_compare" / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    (runs_dir / f"{run['run_id']}.json").write_text(json.dumps(run, indent=2, ensure_ascii=False), encoding="utf-8")


def _seed_snapshots(tmp_path):
    for alias, sid in (("DEV", "DEV_snap"), ("TEST", "TEST_snap")):
        d = tmp_path / "db_compare" / "snapshots" / alias
        d.mkdir(parents=True, exist_ok=True)
        obj = make_schema_obj(alias, "dbo")
        obj["id"] = sid
        obj["taken_at"] = "2026-07-18T11:00:00Z"
        obj["content_hash"] = "h" + alias
        (d / f"{sid}.json").write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")


def _c(app):
    return app.test_client()


# ---------------------------------------------------------------------------
# KPI-1 — enmascarada en la respuesta
# ---------------------------------------------------------------------------


def test_password_enmascarada_en_respuesta(app_masking):
    tmp = app_masking._tmp_path
    _seed_run(tmp, _run())
    resp = _c(app_masking).get(f"/api/db-compare/runs/{RUN_ID}")
    assert resp.status_code == 200
    td = resp.get_json()["data_diff"]["tables"]["dbo.RUSUARIOS"]
    assert td["only_source"][0]["PASSWORD"] == "••••42"
    assert td["only_target"][0]["PASSWORD"] == "••••zz"
    assert td["changed"][0]["cells"]["PASSWORD"]["source"] == "••••88"
    assert td["changed"][0]["cells"]["PASSWORD"]["target"] == "••••66"
    assert td["masked_columns"] == ["PASSWORD"]
    # NOMBRE (no sensible) intacto.
    assert td["only_source"][0]["NOMBRE"] == "carlos"


# ---------------------------------------------------------------------------
# KPI-2 — flag OFF byte-idéntico a main (identidad)
# ---------------------------------------------------------------------------


def test_off_byte_identico(app_masking, monkeypatch):
    import config as cfg
    import services.dbcompare_masking as masking
    tmp = app_masking._tmp_path
    _seed_run(tmp, _run())
    cfg.config.STACKY_DB_COMPARE_MASKING_ENABLED = False

    resp_off = _c(app_masking).get(f"/api/db-compare/runs/{RUN_ID}")
    # main = apply_to_run_response como identidad pura.
    monkeypatch.setattr(masking, "apply_to_run_response", lambda run: run)
    resp_id = _c(app_masking).get(f"/api/db-compare/runs/{RUN_ID}")

    assert resp_off.data == resp_id.data  # byte-idéntico al comportamiento de main
    assert b"masked_columns" not in resp_off.data
    assert REAL_PW_ONLY_SRC.encode() in resp_off.data  # crudo


# ---------------------------------------------------------------------------
# KPI-8 — la lista NUNCA sirve data_diff (fix C1); el POST es un ack sin filas
# ---------------------------------------------------------------------------


def test_list_runs_sin_data_diff(app_masking):
    import config as cfg
    tmp = app_masking._tmp_path
    _seed_run(tmp, _run())
    for flag in (True, False):  # la exclusión es INCONDICIONAL de la flag de masking
        cfg.config.STACKY_DB_COMPARE_MASKING_ENABLED = flag
        resp = _c(app_masking).get("/api/db-compare/runs")
        assert resp.status_code == 200
        runs = resp.get_json()["runs"]
        assert len(runs) == 1
        assert "data_diff" not in runs[0]
        assert "diff" not in runs[0]
        # y jamás viaja el secreto crudo por la lista
        assert REAL_PW_ONLY_SRC.encode() not in resp.data
    cfg.config.STACKY_DB_COMPARE_MASKING_ENABLED = True


def test_post_data_diff_no_sirve_filas(app_masking):
    tmp = app_masking._tmp_path
    _seed_run(tmp, _run(data_diff=None))
    resp = _c(app_masking).post(f"/api/db-compare/runs/{RUN_ID}/data-diff", json={"tables": []})
    assert resp.status_code == 202
    body = resp.get_json()
    assert body == {"ok": True}
    assert b"only_source" not in resp.data
    assert b"only_target" not in resp.data
    assert b"changed" not in resp.data


# ---------------------------------------------------------------------------
# El disco retiene los valores crudos
# ---------------------------------------------------------------------------


def test_disco_retiene_crudo(app_masking):
    tmp = app_masking._tmp_path
    _seed_run(tmp, _run())
    _c(app_masking).get(f"/api/db-compare/runs/{RUN_ID}")  # GET con ON
    raw = json.loads((tmp / "db_compare" / "runs" / f"{RUN_ID}.json").read_text(encoding="utf-8"))
    td = raw["data_diff"]["tables"]["dbo.RUSUARIOS"]
    assert td["only_source"][0]["PASSWORD"] == REAL_PW_ONLY_SRC  # crudo en disco


# ---------------------------------------------------------------------------
# KPI-4 (BLOQUEANTE) — bundle DML byte-idéntico con masking ON; orden GET->bundle
# ---------------------------------------------------------------------------


def _read_data_dml(tmp, manifest):
    bundle_dir = tmp / "db_compare" / "bundles" / RUN_ID
    out = {}
    for e in manifest["entries"]:
        if e["action"].startswith("data_"):
            out[e["file"]] = (bundle_dir / e["file"]).read_text(encoding="utf-8")
    return out


def test_bundle_dml_byte_identico_con_masking_on(app_masking):
    import config as cfg
    tmp = app_masking._tmp_path
    _seed_run(tmp, _run())
    _seed_snapshots(tmp)
    c = _c(app_masking)

    # (1) GET run con ON y assert de que la respuesta vino enmascarada.
    resp = c.get(f"/api/db-compare/runs/{RUN_ID}")
    td = resp.get_json()["data_diff"]["tables"]["dbo.RUSUARIOS"]
    assert td["only_source"][0]["PASSWORD"] == "••••42"

    # (2) RECIÉN ENTONCES generar el bundle (re-lee el run de disco).
    r_on = c.post(f"/api/db-compare/runs/{RUN_ID}/scripts")
    assert r_on.status_code == 200, r_on.get_json()
    dml_on = _read_data_dml(tmp, r_on.get_json()["manifest"])
    assert dml_on, "el bundle no produjo DML de datos"
    blob_on = "\n".join(dml_on[k] for k in sorted(dml_on))
    assert REAL_PW_ONLY_SRC in blob_on  # valor REAL en el DML
    assert "••••" not in blob_on  # jamás el placeholder

    # (3) Regenerar con masking OFF y comparar byte a byte.
    cfg.config.STACKY_DB_COMPARE_MASKING_ENABLED = False
    r_off = c.post(f"/api/db-compare/runs/{RUN_ID}/scripts")
    assert r_off.status_code == 200
    dml_off = _read_data_dml(tmp, r_off.get_json()["manifest"])
    cfg.config.STACKY_DB_COMPARE_MASKING_ENABLED = True

    assert dml_on == dml_off  # byte-idéntico: el masking NUNCA tocó el bundle


# ---------------------------------------------------------------------------
# Robustez — tabla con error pasa tal cual
# ---------------------------------------------------------------------------


def test_tabla_con_error_pasa_tal_cual(app_masking):
    tmp = app_masking._tmp_path
    run = _run()
    run["data_diff"]["tables"]["dbo.ROTA"] = {"error": "no se pudo comparar"}
    _seed_run(tmp, run)
    resp = _c(app_masking).get(f"/api/db-compare/runs/{RUN_ID}")
    assert resp.status_code == 200
    tables = resp.get_json()["data_diff"]["tables"]
    assert tables["dbo.ROTA"] == {"error": "no se pudo comparar"}
    # la buena sí quedó enmascarada
    assert tables["dbo.RUSUARIOS"]["masked_columns"] == ["PASSWORD"]
