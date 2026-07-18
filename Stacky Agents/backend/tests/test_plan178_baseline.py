"""Plan 178 F4 — Baseline v1: pin autocontenido + diff-contra-baseline sin conexión.

Ver Stacky Agents/docs/178_PLAN_RADAR_DE_AMBIENTES_...md §F4.
"""
from __future__ import annotations

import json
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

import pytest

import services.dbcompare_baseline as dbcompare_baseline
import services.dbcompare_snapshot as dbcompare_snapshot
import services.dbcompare_watch as dbcompare_watch
import services.dbcompare_diff as dbcompare_diff


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(dbcompare_baseline, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(dbcompare_snapshot, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(dbcompare_watch, "data_dir", lambda: tmp_path)
    return tmp_path


def _write_snap(tmp, alias, sid, content_hash, tables, taken_at="2026-07-18T10:00:00Z"):
    d = tmp / "db_compare" / "snapshots" / alias
    d.mkdir(parents=True, exist_ok=True)
    snap = {
        "version": 1, "id": sid, "alias": alias, "engine": "mssql",
        "taken_at": taken_at, "duration_ms": 0,
        "schemas": {"dbo": {"tables": tables, "views": {}, "sequences": []}},
        "counts": {}, "content_hash": content_hash,
    }
    (d / f"{sid}.json").write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8")
    return snap


def _snap_path(tmp, alias, sid):
    return tmp / "db_compare" / "snapshots" / alias / f"{sid}.json"


def test_pin_ok_y_get(store):
    _write_snap(store, "PROD", "snapB", "hashBASE", {"T1": {}})
    doc = dbcompare_baseline.pin_baseline("PROD", "snapB", note="release 3.2")
    assert doc["alias"] == "PROD" and doc["snapshot_id"] == "snapB"
    assert dbcompare_baseline.get_baseline("PROD")["snapshot_id"] == "snapB"
    assert (store / "db_compare" / "baselines" / "PROD.snapshot.json").exists()


def test_pin_snapshot_inexistente_lanza(store):
    with pytest.raises(dbcompare_baseline.DbCompareBaselineError):
        dbcompare_baseline.pin_baseline("PROD", "nope")


def test_pin_snapshot_de_otro_alias_lanza(store):
    _write_snap(store, "PROD", "snapB", "hashBASE", {"T1": {}})
    with pytest.raises(dbcompare_baseline.DbCompareBaselineError):
        dbcompare_baseline.pin_baseline("TEST", "snapB")


def test_unpin_true_false(store):
    _write_snap(store, "PROD", "snapB", "hashBASE", {"T1": {}})
    dbcompare_baseline.pin_baseline("PROD", "snapB")
    assert dbcompare_baseline.unpin_baseline("PROD") is True
    assert not (store / "db_compare" / "baselines" / "PROD.json").exists()
    assert not (store / "db_compare" / "baselines" / "PROD.snapshot.json").exists()
    assert dbcompare_baseline.unpin_baseline("PROD") is False


def test_list_baselines_marca_broken(store):
    _write_snap(store, "PROD", "snapB", "hashBASE", {"T1": {}})
    dbcompare_baseline.pin_baseline("PROD", "snapB")
    # broken == False mientras exista original o copia
    assert dbcompare_baseline.list_baselines()[0]["broken"] is False
    # borrar AMBOS → broken True
    _snap_path(store, "PROD", "snapB").unlink()
    (store / "db_compare" / "baselines" / "PROD.snapshot.json").unlink()
    assert dbcompare_baseline.list_baselines()[0]["broken"] is True


def test_list_baselines_ignora_copias(store):
    _write_snap(store, "PROD", "snapB", "hashBASE", {"T1": {}})
    dbcompare_baseline.pin_baseline("PROD", "snapB")
    baselines = dbcompare_baseline.list_baselines()
    assert len(baselines) == 1  # la copia .snapshot.json NO cuenta como baseline


def test_baseline_sobrevive_prune_de_snapshots(store):
    # KPI-8 / fix C2: pin → borrar el original → baseline_diff sigue desde la copia.
    _write_snap(store, "PROD", "snapB", "hashBASE", {"T1": {}}, taken_at="2026-07-18T09:00:00Z")
    dbcompare_baseline.pin_baseline("PROD", "snapB")
    _write_snap(store, "PROD", "snapF", "hashFRESH", {"T1": {}, "T2": {}}, taken_at="2026-07-18T12:00:00Z")
    _snap_path(store, "PROD", "snapB").unlink()  # simula prune_snapshots
    diff = dbcompare_baseline.baseline_diff("PROD")
    assert diff["version"] == dbcompare_diff.DIFF_VERSION
    assert diff["items"]
    assert dbcompare_baseline.list_baselines()[0]["broken"] is False


def test_baseline_diff_reusa_schema_diff_v1(store, monkeypatch):
    # KPI-6: cero conexión (centinela take_snapshot).
    def _boom(*a, **k):
        raise AssertionError("baseline_diff no debe abrir conexión")

    monkeypatch.setattr(dbcompare_snapshot, "take_snapshot", _boom)
    _write_snap(store, "PROD", "snapB", "hashBASE", {"T1": {}}, taken_at="2026-07-18T09:00:00Z")
    dbcompare_baseline.pin_baseline("PROD", "snapB")
    _write_snap(store, "PROD", "snapF", "hashFRESH", {"T1": {}, "T2": {}}, taken_at="2026-07-18T12:00:00Z")
    diff = dbcompare_baseline.baseline_diff("PROD")
    assert diff["version"] == dbcompare_diff.DIFF_VERSION
    assert diff["items"]
    assert "by_severity" in diff["summary"]


def test_baseline_diff_sin_baseline_lanza(store):
    with pytest.raises(dbcompare_baseline.DbCompareBaselineError):
        dbcompare_baseline.baseline_diff("NOPE")


def test_sin_snapshots_lanza(store):
    _write_snap(store, "PROD", "snapB", "hashBASE", {"T1": {}})
    dbcompare_baseline.pin_baseline("PROD", "snapB")
    _snap_path(store, "PROD", "snapB").unlink()  # copia queda, pero no hay latest
    with pytest.raises(dbcompare_baseline.DbCompareBaselineError):
        dbcompare_baseline.baseline_diff("PROD")


def test_mark_alerted_sin_baseline_no_crashea(store):
    dbcompare_baseline.mark_alerted("NOPE", "h")  # no lanza


_W = {"watch_id": "PROD__TEST", "source_alias": "PROD", "target_alias": "TEST"}


def test_violacion_emite_evento_y_dedup_por_hash(store):
    _write_snap(store, "PROD", "snapB", "hashBASE", {"T1": {}}, taken_at="2026-07-18T09:00:00Z")
    dbcompare_baseline.pin_baseline("PROD", "snapB")
    _write_snap(store, "PROD", "snapF", "hashFRESH", {"T1": {}, "T2": {}}, taken_at="2026-07-18T12:00:00Z")
    run = {"run_id": "rV", "source_snapshot_id": "snapF", "target_snapshot_id": "snapT_x"}

    dbcompare_watch._check_baselines_for_run(dict(_W), run)
    events = dbcompare_watch.list_events(50)
    assert len(events) == 1 and events[0]["kind"] == "baseline_violation"
    assert dbcompare_baseline.get_baseline("PROD")["last_alerted_content_hash"] == "hashFRESH"

    # Segunda cosecha con el MISMO hash → dedup, 0 nuevos.
    dbcompare_watch._check_baselines_for_run(dict(_W), run)
    assert len(dbcompare_watch.list_events(50)) == 1


def test_snapshot_igual_al_baseline_no_emite(store):
    _write_snap(store, "PROD", "snapB", "hashSAME", {"T1": {}}, taken_at="2026-07-18T09:00:00Z")
    dbcompare_baseline.pin_baseline("PROD", "snapB")
    _write_snap(store, "PROD", "snapF", "hashSAME", {"T1": {}}, taken_at="2026-07-18T12:00:00Z")
    run = {"run_id": "rV", "source_snapshot_id": "snapF", "target_snapshot_id": "snapT_x"}
    dbcompare_watch._check_baselines_for_run(dict(_W), run)
    assert dbcompare_watch.list_events(50) == []


def test_modulo_baseline_no_importa_conexion_ni_watch():
    src = os.path.join(os.path.dirname(dbcompare_baseline.__file__), "dbcompare_baseline.py")
    text = open(src, encoding="utf-8").read()
    assert "import sqlalchemy" not in text
    assert "dbcompare_connect" not in text
    assert "import dbcompare_watch" not in text
    assert "from services import dbcompare_watch" not in text
