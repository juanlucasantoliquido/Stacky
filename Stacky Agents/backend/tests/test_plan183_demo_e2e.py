"""Plan 183 F5 — E2E integral con el MOTOR REAL sqlite (snapshot/diff/data sin mock).

Ver Stacky Agents/docs/183_PLAN_SANDBOX_DEMO_DEL_COMPARADOR_*.md §F5.

Aislamiento: archivos sqlite reales bajo tmp_path — cero red, cero egress. El
thread de create_run es el del motor y termina solo; se espera con poll de
timeout corto (mismo patrón que los E2E sqlite del 122/126).
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

import pytest


@pytest.fixture
def demo_env(monkeypatch, tmp_path):
    import services.dbcompare_registry as reg
    import services.dbcompare_demo as demo
    import services.dbcompare_snapshot as snap
    import services.dbcompare_runs as runs
    import services.dbcompare_data as data

    store: dict[tuple[str, str], str] = {}

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
    for mod in (reg, demo, snap, runs):
        monkeypatch.setattr(mod, "data_dir", lambda: tmp_path)
    # dbcompare_data no importa data_dir directamente (usa snapshot/runs), pero
    # lo dejamos en la lista por claridad de perímetro.
    _ = data
    return tmp_path, store


def _wait_run(run_id: str, timeout: float = 20.0) -> dict:
    from services import dbcompare_runs

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        run = dbcompare_runs.get_run(run_id)
        if run and run.get("status") in ("done", "error"):
            return run
        time.sleep(0.05)
    raise AssertionError(f"run {run_id} no terminó en {timeout}s")


def test_ciclo_completo_sqlite(demo_env):
    """KPI-1 — seed → create_run real → done con items; data-candidates: RPARAM
    comparable, RLOG no comparable (sin PK)."""
    from services import dbcompare_demo as demo
    from services import dbcompare_runs, dbcompare_snapshot

    demo.seed_demo_environments()
    run = dbcompare_runs.create_run(demo.DEMO_DEV_ALIAS, demo.DEMO_TEST_ALIAS, mode="fresh")
    done = _wait_run(run["run_id"])

    assert done["status"] == "done"
    assert done["summary"]["parity_score"] < 100
    items = done["diff"]["items"]
    assert len(items) > 0

    # data-candidates (equivalente al de api/db_compare.py:388-406): PK en el
    # snapshot de ORIGEN decide comparabilidad.
    src_snap = dbcompare_snapshot.latest_snapshot(demo.DEMO_DEV_ALIAS)
    tables = src_snap["schemas"]["main"]["tables"]
    assert tables["RPARAM"]["primary_key"]["columns"] == ["CLAVE"]  # comparable
    assert (tables["RLOG"]["primary_key"].get("columns") or []) == []  # no comparable (sin PK)


def test_catalogo_severidades(demo_env):
    """KPI-5 (fix C2) — severidades de ITEMS == {info,warn,danger} + kinds esperados."""
    from services import dbcompare_demo as demo
    from services import dbcompare_runs

    demo.seed_demo_environments()
    run = dbcompare_runs.create_run(demo.DEMO_DEV_ALIAS, demo.DEMO_TEST_ALIAS, mode="fresh")
    done = _wait_run(run["run_id"])
    items = done["diff"]["items"]

    severities = {it["severity"] for it in items}
    assert severities == {"info", "warn", "danger"}

    kinds = {c["kind"] for it in items for c in it.get("changes", [])}
    assert {
        "column_removed",
        "column_nullable_tightened",
        "column_default_changed",
        "index_added",
        "view_definition_changed",
    } <= kinds

    actions_by_type = {(it["object_type"], it["action"]) for it in items}
    assert ("table", "added") in actions_by_type   # RSOLO_DEV solo en origen
    assert ("table", "removed") in actions_by_type  # RSOLO_TEST solo en destino

    # El item `info` lo garantiza RESTILO (única diferencia = DEFAULT).
    restilo = next(it for it in items if it["name"] == "RESTILO")
    assert restilo["severity"] == "info"
    assert [c["kind"] for c in restilo["changes"]] == ["column_default_changed"]


def test_base_comun_smokes(demo_env):
    """KPI-6 — data-diff de RPARAM (1 insert + 2 update + 1 delete) y RCREDENCIAL
    (1 update): los counts EXACTOS de §4.3 fila por fila."""
    from services import dbcompare_demo as demo
    from services import dbcompare_data, dbcompare_runs

    demo.seed_demo_environments()
    # El run fresco persiste los snapshots que diff_table_data necesita.
    run = dbcompare_runs.create_run(demo.DEMO_DEV_ALIAS, demo.DEMO_TEST_ALIAS, mode="fresh")
    _wait_run(run["run_id"])

    rparam = dbcompare_data.diff_table_data(
        demo.DEMO_DEV_ALIAS, demo.DEMO_TEST_ALIAS, "main", "RPARAM"
    )
    assert len(rparam["only_source"]) == 1   # insert: MAX_REINTENTOS
    assert len(rparam["changed"]) == 2       # update: CONN_LEGACY, MONEDA_DEFECTO
    assert len(rparam["only_target"]) == 1   # delete: PARAM_HUERFANO

    rcred = dbcompare_data.diff_table_data(
        demo.DEMO_DEV_ALIAS, demo.DEMO_TEST_ALIAS, "main", "RCREDENCIAL"
    )
    assert len(rcred["only_source"]) == 0
    assert len(rcred["only_target"]) == 0
    assert len(rcred["changed"]) == 1        # update: PASSWORD difiere
