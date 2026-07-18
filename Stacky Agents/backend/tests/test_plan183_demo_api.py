"""Plan 183 — Sandbox de demostración del comparador: tests de flag (F0) y API (F3).

Ver Stacky Agents/docs/183_PLAN_SANDBOX_DEMO_DEL_COMPARADOR_*.md §F0 y §F3.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

import pytest

_DEMO_FLAG = "STACKY_DB_COMPARE_DEMO_ENABLED"


# ---------------------------------------------------------------------------
# F0 — Flag, config y arista (patrón determinista de la serie: isinstance,
# el valor efectivo del gate se prueba en F3 con monkeypatch)
# ---------------------------------------------------------------------------


def test_flag_registrada_bool_on_requires_master():
    from services import harness_flags

    spec = harness_flags._REGISTRY_INDEX.get(_DEMO_FLAG)
    assert spec is not None, f"{_DEMO_FLAG} no está en FLAG_REGISTRY"
    assert spec.type == "bool"
    assert spec.default is True  # default ON — curada en _CURATED_DEFAULTS_ON
    assert spec.requires == "STACKY_DB_COMPARE_ENABLED"  # requires plano, profundidad 1


def test_flag_en_categoria():
    from services import harness_flags

    assert harness_flags.categorize(_DEMO_FLAG) == "comparador_bd"


def test_config_attr_existe_bool():
    from config import Config

    assert isinstance(Config.STACKY_DB_COMPARE_DEMO_ENABLED, bool)


# ---------------------------------------------------------------------------
# F3 — API: blueprint db_compare_demo (doble gate de flags)
# ---------------------------------------------------------------------------


class _FakeKeyring:
    def __init__(self):
        self.store = {}

    def set_password(self, svc, key, val):
        self.store[(svc, key)] = val

    def get_password(self, svc, key):
        return self.store.get((svc, key))

    def delete_password(self, svc, key):
        self.store.pop((svc, key), None)


def _patch_data_dir(monkeypatch, tmp_path):
    import services.dbcompare_registry as reg
    import services.dbcompare_demo as demo
    import services.dbcompare_snapshot as snap
    import services.dbcompare_runs as runs

    monkeypatch.setattr(reg, "keyring", _FakeKeyring())
    for mod in (reg, demo, snap, runs):
        monkeypatch.setattr(mod, "data_dir", lambda: tmp_path)


def _make_app(master: bool, demo: bool):
    import config as cfg
    from app import create_app

    cfg.config.STACKY_DB_COMPARE_ENABLED = master
    cfg.config.STACKY_DB_COMPARE_DEMO_ENABLED = demo
    app = create_app()
    app.config["TESTING"] = True
    return app, cfg


@pytest.fixture
def app_on(tmp_path, monkeypatch):
    import config as cfg

    orig_m = getattr(cfg.config, "STACKY_DB_COMPARE_ENABLED", False)
    orig_d = getattr(cfg.config, "STACKY_DB_COMPARE_DEMO_ENABLED", False)
    _patch_data_dir(monkeypatch, tmp_path)
    app, _ = _make_app(True, True)
    yield app
    cfg.config.STACKY_DB_COMPARE_ENABLED = orig_m
    cfg.config.STACKY_DB_COMPARE_DEMO_ENABLED = orig_d


def test_403_flags_off(monkeypatch):
    """KPI-4 — con master OFF o demo OFF, las 3 rutas /demo/* dan 403."""
    import config as cfg

    orig_m = getattr(cfg.config, "STACKY_DB_COMPARE_ENABLED", False)
    orig_d = getattr(cfg.config, "STACKY_DB_COMPARE_DEMO_ENABLED", False)
    try:
        for master, demo in ((False, True), (True, False)):
            app, _ = _make_app(master, demo)
            c = app.test_client()
            assert c.post("/api/db-compare/demo/seed").status_code == 403
            assert c.get("/api/db-compare/demo/status").status_code == 403
            assert c.delete("/api/db-compare/demo").status_code == 403
    finally:
        cfg.config.STACKY_DB_COMPARE_ENABLED = orig_m
        cfg.config.STACKY_DB_COMPARE_DEMO_ENABLED = orig_d


def test_seed_status_delete_feliz(app_on):
    c = app_on.test_client()

    r_seed = c.post("/api/db-compare/demo/seed")
    assert r_seed.status_code == 200, r_seed.get_data(as_text=True)
    body = r_seed.get_json()
    assert body["ok"] is True
    assert body["aliases"] == ["test-demo-dev", "test-demo-test"]

    r_status = c.get("/api/db-compare/demo/status")
    assert r_status.status_code == 200
    st = r_status.get_json()["status"]
    assert st["registered"] is True and st["files_present"] is True

    r_del = c.delete("/api/db-compare/demo")
    assert r_del.status_code == 200
    assert r_del.get_json()["ok"] is True

    st2 = c.get("/api/db-compare/demo/status").get_json()["status"]
    assert st2["registered"] is False and st2["files_present"] is False


def test_seed_alias_ajeno_409(app_on):
    from services import dbcompare_registry as reg

    # Un alias test-demo-* ajeno (apunta fuera del sandbox) ⇒ 409 (fix C4).
    reg.upsert_environment(
        alias="test-demo-dev", engine="sqlite", host="", port=0,
        database="C:/otro/lado.db", username="demo",
    )
    r = app_on.test_client().post("/api/db-compare/demo/seed")
    assert r.status_code == 409
    assert r.get_json()["ok"] is False


def test_delete_lockeado_409(app_on, monkeypatch):
    import shutil

    from services import dbcompare_demo as demo  # noqa: F401 (asegura import antes del patch)

    c = app_on.test_client()
    assert c.post("/api/db-compare/demo/seed").status_code == 200

    def boom(path, *a, **k):
        raise PermissionError("archivo en uso")

    monkeypatch.setattr(shutil, "rmtree", boom)
    r = c.delete("/api/db-compare/demo")
    assert r.status_code == 409  # fix C3 — reportado, no 500
    body = r.get_json()
    assert body["ok"] is False and body["error"]


def test_delete_sin_demo_ok_vacio(app_on):
    # Sin demo sembrado, el delete es idempotente e inocuo.
    r = app_on.test_client().delete("/api/db-compare/demo")
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True
    assert body["removed_aliases"] == [] and body["files_removed"] is False
