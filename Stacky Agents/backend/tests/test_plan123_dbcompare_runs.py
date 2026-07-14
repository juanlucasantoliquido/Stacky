"""Plan 123 F2 — Corridas comparativas (services/dbcompare_runs.py).

Ver Stacky Agents/docs/123_PLAN_DB_COMPARE_MOTOR_DIFF_SEVERIDADES_Y_CORRIDAS.md §F2.
"""
from __future__ import annotations

import os
import sys
import threading
import time
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

import pytest
from sqlalchemy import create_engine, text


@pytest.fixture
def fake_keyring(monkeypatch):
    import services.dbcompare_registry as reg

    store: dict = {}

    class _FakeKeyring:
        @staticmethod
        def set_password(service, alias, password):
            store[(service, alias)] = password

        @staticmethod
        def get_password(service, alias):
            return store.get((service, alias))

        @staticmethod
        def delete_password(service, alias):
            store.pop((service, alias), None)

    monkeypatch.setattr(reg, "keyring", _FakeKeyring())
    return store


def _seed_db(path: Path, with_index: bool = True):
    eng = create_engine(f"sqlite:///{path}")
    with eng.connect() as c:
        c.execute(text("CREATE TABLE padre (id INTEGER PRIMARY KEY, nombre TEXT NOT NULL)"))
        c.execute(text(
            "CREATE TABLE hija (id INTEGER PRIMARY KEY, "
            "padre_id INTEGER REFERENCES padre(id), valor REAL DEFAULT 0)"
        ))
        if with_index:
            c.execute(text("CREATE INDEX ix_hija_padre ON hija(padre_id)"))
        c.commit()
    return eng


@pytest.fixture
def two_envs(fake_keyring, tmp_path, monkeypatch):
    import services.dbcompare_registry as reg
    import services.dbcompare_runs as runs
    import services.dbcompare_snapshot as snap

    monkeypatch.setattr(reg, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(snap, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(runs, "data_dir", lambda: tmp_path)

    db_a = tmp_path / "a.db"
    db_b = tmp_path / "b.db"
    eng_a = _seed_db(db_a, with_index=True)
    eng_b = _seed_db(db_b, with_index=False)

    reg.upsert_environment("test-a", "sqlite", "localhost", 0, str(db_a), "user")
    reg.upsert_environment("test-b", "sqlite", "localhost", 0, str(db_b), "user")
    reg.set_password("test-a", "unused")
    reg.set_password("test-b", "unused")

    return {"eng_a": eng_a, "eng_b": eng_b, "tmp_path": tmp_path}


def _wait_done(runs_mod, run_id, timeout=5.0):
    deadline = time.monotonic() + timeout
    final = runs_mod.get_run(run_id)
    while time.monotonic() < deadline:
        final = runs_mod.get_run(run_id)
        if final and final["status"] in ("done", "error"):
            return final
        time.sleep(0.05)
    return final


def test_run_cached_done_con_diff(two_envs):
    import services.dbcompare_runs as runs
    import services.dbcompare_snapshot as snap

    snap.take_snapshot("test-a", engine=two_envs["eng_a"])
    snap.take_snapshot("test-b", engine=two_envs["eng_b"])

    run = runs.create_run("test-a", "test-b", mode="cached")
    assert run["status"] == "running"

    final = _wait_done(runs, run["run_id"])

    assert final["status"] == "done", final
    assert final["diff"]["summary"]["objects_total"] == 2
    assert final["summary"] == final["diff"]["summary"]
    assert final["source_snapshot_id"] is not None
    assert final["target_snapshot_id"] is not None


def test_run_fresh_sqlite_done(two_envs):
    import services.dbcompare_runs as runs

    run = runs.create_run("test-a", "test-b", mode="fresh")
    final = _wait_done(runs, run["run_id"])

    assert final["status"] == "done", final
    assert final["source_snapshot_id"] is not None
    assert final["target_snapshot_id"] is not None
    assert final["diff"]["engine"] == "sqlite"


def test_par_activo_409(two_envs):
    import services.dbcompare_runs as runs

    pair = frozenset({"test-a", "test-b"})
    with runs._ACTIVE_LOCK:
        runs._ACTIVE_PAIRS.add(pair)
    try:
        with pytest.raises(runs.DbCompareBusyError):
            runs.create_run("test-a", "test-b", mode="cached")
        with pytest.raises(runs.DbCompareBusyError):
            runs.create_run("test-b", "test-a", mode="cached")
    finally:
        with runs._ACTIVE_LOCK:
            runs._ACTIVE_PAIRS.discard(pair)


def test_par_activo_race_real(two_envs):
    """[FIX C2] Dos create_run() reales lanzados casi simultáneamente para el MISMO par:
    exactamente uno gana, el otro recibe DbCompareBusyError. El registro del par debe ser
    atómico bajo lock, no dentro del thread de fondo."""
    import services.dbcompare_runs as runs

    barrier = threading.Barrier(2)
    results = []
    lock = threading.Lock()

    def _call():
        barrier.wait()
        try:
            run = runs.create_run("test-a", "test-b", mode="cached")
            with lock:
                results.append(("ok", run))
        except runs.DbCompareBusyError:
            with lock:
                results.append(("busy", None))

    t1 = threading.Thread(target=_call)
    t2 = threading.Thread(target=_call)
    t1.start()
    t2.start()
    t1.join(timeout=5)
    t2.join(timeout=5)

    oks = [r for r in results if r[0] == "ok"]
    busies = [r for r in results if r[0] == "busy"]
    assert len(oks) == 1, results
    assert len(busies) == 1, results


def test_error_scrubbed(two_envs, monkeypatch):
    import services.dbcompare_runs as runs
    import services.dbcompare_snapshot as snap

    password = "s3cr3t-pw"
    monkeypatch.setattr(
        runs.dbcompare_registry, "get_credential",
        lambda alias: {"engine": "sqlite", "password": password},
    )

    def _boom(alias, engine=None):
        raise RuntimeError(f"conexion fallo con password={password}")

    monkeypatch.setattr(snap, "take_snapshot", _boom)

    run = runs.create_run("test-a", "test-b", mode="fresh")
    final = _wait_done(runs, run["run_id"])

    assert final["status"] == "error", final
    assert password not in final["error"]
    assert "***" in final["error"]


def test_scrub_defensivo_ante_credencial_rota(two_envs, monkeypatch):
    """[FIX C5] Si _scrub no puede resolver la credencial (get_credential lanza), el run
    igual debe llegar a status='error' — nunca quedar 'running' para siempre."""
    import services.dbcompare_runs as runs
    import services.dbcompare_snapshot as snap

    def _boom_cred(alias):
        raise RuntimeError("keyring roto")

    monkeypatch.setattr(runs.dbcompare_registry, "get_credential", _boom_cred)

    def _boom_snapshot(alias, engine=None):
        raise RuntimeError("fallo de conexion")

    monkeypatch.setattr(snap, "take_snapshot", _boom_snapshot)

    run = runs.create_run("test-a", "test-b", mode="fresh")
    final = _wait_done(runs, run["run_id"])

    assert final["status"] == "error", final
    assert final["error"]


def test_stale_marker(two_envs):
    import services.dbcompare_runs as runs

    old_started = runs._now() - timedelta(seconds=runs._STALE_AFTER_SEC + 60)
    run = {
        "run_id": "run_stale_test", "source_alias": "test-a", "target_alias": "test-b",
        "engine": "sqlite", "mode": "cached", "status": "running", "phase": "diff",
        "started_at": runs._iso(old_started), "finished_at": None, "duration_ms": 0,
        "source_snapshot_id": None, "target_snapshot_id": None,
        "summary": None, "diff": None, "error": None,
    }
    runs._write_run(run)

    fetched = runs.get_run("run_stale_test")
    assert fetched["stale"] is True

    on_disk = runs._read_run("run_stale_test")
    assert "stale" not in on_disk  # solo lectura: el archivo en disco no se muta


def test_prune_runs(two_envs):
    import services.dbcompare_runs as runs

    total = runs._MAX_RUNS_KEPT + 20
    for i in range(total):
        run = {
            "run_id": f"run_{i:04d}", "source_alias": "test-a", "target_alias": "test-b",
            "engine": "sqlite", "mode": "cached", "status": "done", "phase": "done",
            "started_at": runs._iso(runs._now()), "finished_at": runs._iso(runs._now()),
            "duration_ms": 1, "source_snapshot_id": None, "target_snapshot_id": None,
            "summary": {}, "diff": {}, "error": None,
        }
        runs._write_run(run)

    removed = runs.prune_runs()
    remaining = list(runs._runs_dir().glob("*.json"))

    assert removed == 20
    assert len(remaining) == runs._MAX_RUNS_KEPT
