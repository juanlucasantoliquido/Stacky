"""Plan 183 F1 — seed determinista + status del sandbox de demostración.

Ver Stacky Agents/docs/183_PLAN_SANDBOX_DEMO_DEL_COMPARADOR_*.md §F1.
"""
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

import pytest


@pytest.fixture
def demo_env(monkeypatch, tmp_path):
    """Redirige data_dir de TODOS los módulos del motor a tmp_path + keyring fake
    (patrón del fixture del 122, tests/test_plan122_dbcompare_snapshot.py:22-42)."""
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


def test_seed_crea_archivos_registra_y_guarda_password(demo_env):
    """fix C1 — la cadena del motor completa: archivos + registro + password dummy."""
    from services import dbcompare_demo as demo
    from services import dbcompare_registry as reg

    tmp_path, _ = demo_env
    out = demo.seed_demo_environments()

    dev_db = tmp_path / "db_compare" / "demo" / "demo_dev.db"
    test_db = tmp_path / "db_compare" / "demo" / "demo_test.db"
    assert dev_db.exists() and test_db.exists()
    assert out["aliases"] == [demo.DEMO_DEV_ALIAS, demo.DEMO_TEST_ALIAS]

    aliases = {e["alias"]: e for e in reg.list_environments()}
    assert demo.DEMO_DEV_ALIAS in aliases and demo.DEMO_TEST_ALIAS in aliases
    for alias in (demo.DEMO_DEV_ALIAS, demo.DEMO_TEST_ALIAS):
        env = aliases[alias]
        assert env["engine"] == "sqlite"
        # database DENTRO de demo/
        assert Path(env["database"]).resolve().is_relative_to(
            (tmp_path / "db_compare" / "demo").resolve()
        )
        cred = reg.get_credential(alias)
        assert cred is not None and cred["password"] == demo.DEMO_DUMMY_PASSWORD


def test_seed_sin_keyring_falla_claro(demo_env, monkeypatch):
    """fix C1 — sin keyring, el seed falla ANTES de crear archivos, con mensaje accionable."""
    from services import dbcompare_demo as demo
    from services import dbcompare_registry as reg

    tmp_path, _ = demo_env
    monkeypatch.setattr(reg, "keyring_available", lambda: False)
    with pytest.raises(RuntimeError, match="keyring no disponible"):
        demo.seed_demo_environments()
    assert not (tmp_path / "db_compare" / "demo" / "demo_dev.db").exists()


def test_seed_alias_ajeno_aborta(demo_env):
    """fix C4 — un alias test-demo-* apuntando FUERA del sandbox aborta sin tocar nada."""
    from services import dbcompare_demo as demo
    from services import dbcompare_registry as reg

    tmp_path, _ = demo_env
    foreign_db = tmp_path / "otro" / "lado.db"
    reg.upsert_environment(
        alias=demo.DEMO_DEV_ALIAS, engine="sqlite", host="", port=0,
        database=str(foreign_db), username="demo",
    )
    with pytest.raises(ValueError, match="ocupado por un ambiente ajeno"):
        demo.seed_demo_environments()
    # No creó archivos del sandbox ni pisó el registro ajeno.
    assert not (tmp_path / "db_compare" / "demo" / "demo_dev.db").exists()
    env = reg.get_environment(demo.DEMO_DEV_ALIAS)
    assert Path(env["database"]) == foreign_db


def test_seed_sin_tmp_residual(demo_env):
    from services import dbcompare_demo as demo

    tmp_path, _ = demo_env
    demo.seed_demo_environments()
    residual = list((tmp_path / "db_compare" / "demo").glob("*.tmp"))
    assert residual == []


def test_reseed_determinista(demo_env):
    """KPI-2 — determinismo OBSERVABLE por el motor: content_hash y SELECTs idénticos."""
    from services import dbcompare_demo as demo
    from services import dbcompare_snapshot as snap

    tmp_path, _ = demo_env

    def _hashes_and_rows():
        h = {}
        rows = {}
        for alias in (demo.DEMO_DEV_ALIAS, demo.DEMO_TEST_ALIAS):
            result = snap.take_snapshot(alias)
            h[alias] = result["content_hash"]
        db_dev = tmp_path / "db_compare" / "demo" / "demo_dev.db"
        conn = sqlite3.connect(str(db_dev))
        try:
            rows["dev_rparam"] = conn.execute(
                "SELECT * FROM RPARAM ORDER BY CLAVE"
            ).fetchall()
        finally:
            conn.close()
        return h, rows

    demo.seed_demo_environments()
    h1, rows1 = _hashes_and_rows()
    demo.seed_demo_environments()
    h2, rows2 = _hashes_and_rows()

    assert h1 == h2
    assert rows1 == rows2


def test_status_estados(demo_env):
    from services import dbcompare_demo as demo

    tmp_path, _ = demo_env
    st0 = demo.demo_status()
    assert st0["registered"] is False and st0["files_present"] is False

    demo.seed_demo_environments()
    st1 = demo.demo_status()
    assert st1["registered"] is True and st1["files_present"] is True

    # Borrar 1 archivo a mano ⇒ estado "roto" detectable (alimenta demo-broken, C6).
    (tmp_path / "db_compare" / "demo" / "demo_dev.db").unlink()
    st2 = demo.demo_status()
    assert st2["registered"] is True and st2["files_present"] is False


def test_drift_fisico_sembrado(demo_env):
    """5 diferencias FÍSICAS puntuales entre los .db (incluye el DEFAULT de RESTILO, fix C2)."""
    from services import dbcompare_demo as demo

    tmp_path, _ = demo_env
    demo.seed_demo_environments()
    demo_dir = tmp_path / "db_compare" / "demo"

    def _cols(db, table):
        conn = sqlite3.connect(str(db))
        try:
            return {r[1]: r for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        finally:
            conn.close()

    def _index_names(db):
        conn = sqlite3.connect(str(db))
        try:
            return {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            ).fetchall()}
        finally:
            conn.close()

    def _rparam_keys(db):
        conn = sqlite3.connect(str(db))
        try:
            return {r[0] for r in conn.execute("SELECT CLAVE FROM RPARAM").fetchall()}
        finally:
            conn.close()

    dev = demo_dir / "demo_dev.db"
    test = demo_dir / "demo_test.db"

    # 1) MODULO existe solo en dev (RIDIOMA)
    assert "MODULO" in _cols(dev, "RIDIOMA")
    assert "MODULO" not in _cols(test, "RIDIOMA")
    # 2) índice IX_RTABL_DESCRIPCION solo en dev
    assert "IX_RTABL_DESCRIPCION" in _index_names(dev)
    assert "IX_RTABL_DESCRIPCION" not in _index_names(test)
    # 3) DESCRIPCION NOT NULL solo en dev (col[3] = notnull)
    assert _cols(dev, "RTABL")["DESCRIPCION"][3] == 1
    assert _cols(test, "RTABL")["DESCRIPCION"][3] == 0
    # 4) PARAM_HUERFANO solo en test
    assert "PARAM_HUERFANO" in _rparam_keys(test)
    assert "PARAM_HUERFANO" not in _rparam_keys(dev)
    # 5) DEFAULT de RESTILO.COLOR distinto (col[4] = dflt_value) — fix C2
    assert _cols(dev, "RESTILO")["COLOR"][4] == "'AZUL'"
    assert _cols(test, "RESTILO")["COLOR"][4] == "'ROJO'"
