"""Plan 183 F2 — DELETE con guard doble (§3.1), tolerante a locks (fix C3).

Ver Stacky Agents/docs/183_PLAN_SANDBOX_DEMO_DEL_COMPARADOR_*.md §F2.
"""
from __future__ import annotations

import os
import shutil
import sys
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
    return tmp_path, store


def test_delete_acotado_guard_doble(demo_env):
    """KPI-3 — el DELETE jamás sale del sandbox: señuelo y ambiente real intactos."""
    from services import dbcompare_demo as demo
    from services import dbcompare_registry as reg

    tmp_path, _ = demo_env
    demo.seed_demo_environments()
    # Ambiente real ajeno (NO test-demo-*): jamás debe desregistrarse.
    reg.upsert_environment(
        alias="prod-x", engine="sqlserver", host="dbhost", port=1433,
        database="MiBase", username="svc",
    )
    # Señuelo dentro de db_compare/ pero FUERA de demo/.
    decoy = tmp_path / "db_compare" / "decoy.txt"
    decoy.parent.mkdir(parents=True, exist_ok=True)
    decoy.write_text("no me borres", encoding="utf-8")

    res = demo.delete_demo()

    assert set(res["removed_aliases"]) == {demo.DEMO_DEV_ALIAS, demo.DEMO_TEST_ALIAS}
    assert res["files_removed"] is True and res["error"] is None
    assert reg.get_environment("prod-x") is not None  # ambiente real intacto
    assert decoy.exists()  # señuelo intacto
    assert not (tmp_path / "db_compare" / "demo").exists()
    assert reg.get_environment(demo.DEMO_DEV_ALIAS) is None


def test_delete_idempotente(demo_env):
    from services import dbcompare_demo as demo

    demo.seed_demo_environments()
    demo.delete_demo()
    res2 = demo.delete_demo()
    assert res2 == {"removed_aliases": [], "files_removed": False, "error": None}


def test_delete_archivos_lockeados_reporta(demo_env, monkeypatch):
    """fix C3 — .db lockeado (Windows): retorno con error, aliases YA desregistrados,
    sin excepción; un delete posterior (real) completa."""
    from services import dbcompare_demo as demo
    from services import dbcompare_registry as reg

    tmp_path, _ = demo_env
    demo.seed_demo_environments()

    real_rmtree = shutil.rmtree
    calls = {"n": 0}

    def flaky(path, *a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            raise PermissionError("archivo en uso")
        return real_rmtree(path, *a, **k)

    monkeypatch.setattr(shutil, "rmtree", flaky)

    res = demo.delete_demo()
    assert res["files_removed"] is False
    assert res["error"] is not None
    # aliases ya desregistrados (estado detectable por status: files sin registro)
    assert reg.get_environment(demo.DEMO_DEV_ALIAS) is None
    st = demo.demo_status()
    assert st["registered"] is False and st["files_present"] is True

    # Un delete posterior (rmtree real) completa.
    res2 = demo.delete_demo()
    assert res2["files_removed"] is True and res2["error"] is None
    assert not (tmp_path / "db_compare" / "demo").exists()


def test_delete_no_borra_snapshots_historicos(demo_env):
    from services import dbcompare_demo as demo

    tmp_path, _ = demo_env
    demo.seed_demo_environments()
    snap_dir = tmp_path / "db_compare" / "snapshots" / demo.DEMO_DEV_ALIAS
    snap_dir.mkdir(parents=True, exist_ok=True)
    snap_file = snap_dir / "snap_fake.json"
    snap_file.write_text("{}", encoding="utf-8")

    demo.delete_demo()
    assert snap_file.exists()  # decisión v1 §3.1: NO borra snapshots históricos


def test_seed_tras_delete_funciona(demo_env):
    from services import dbcompare_demo as demo

    demo.seed_demo_environments()
    demo.delete_demo()
    demo.seed_demo_environments()
    assert demo.demo_status()["registered"] is True


def test_interrupcion_archivos_sin_registro(demo_env):
    """Seed interrumpido (solo archivos, sin registro) ⇒ status detecta la
    desincronización; el seed completo repara."""
    from services import dbcompare_demo as demo

    tmp_path, _ = demo_env
    demo_root = tmp_path / "db_compare" / "demo"
    demo_root.mkdir(parents=True, exist_ok=True)
    demo._write_demo_db(demo_root / "demo_dev.db", demo._DEV_STATEMENTS)
    demo._write_demo_db(demo_root / "demo_test.db", demo._TEST_STATEMENTS)

    st = demo.demo_status()
    assert st["files_present"] is True and st["registered"] is False

    demo.seed_demo_environments()
    assert demo.demo_status()["registered"] is True
