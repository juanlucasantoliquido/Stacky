"""Plan 178 F1 — Watch v1: store de pares vigilados (CRUD atómico).

Ver Stacky Agents/docs/178_PLAN_RADAR_DE_AMBIENTES_...md §F1.
"""
from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

import pytest

import services.dbcompare_watch as dbcompare_watch
import services.dbcompare_registry as dbcompare_registry


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(dbcompare_watch, "data_dir", lambda: tmp_path)

    known = {"DEV", "TEST", "PROD", "A__B", "C"}

    def _fake_get_env(alias):
        if alias in known:
            return {"alias": alias, "engine": "mssql"}
        return None

    monkeypatch.setattr(dbcompare_registry, "get_environment", _fake_get_env)
    return tmp_path


def test_upsert_crea_watch_deshabilitado_no_existe_archivo_antes(store):
    assert dbcompare_watch.list_watches() == []
    w = dbcompare_watch.upsert_watch("DEV", "TEST", enabled=True)
    assert (store / "db_compare" / "watch" / "watches.json").exists()
    import json

    doc = json.loads((store / "db_compare" / "watch" / "watches.json").read_text(encoding="utf-8"))
    assert doc["version"] == 1
    assert len(doc["watches"]) == 1
    for field in (
        "watch_id", "source_alias", "target_alias", "enabled", "created_at",
        "last_attempt_at", "last_run_id", "last_done_run_id",
        "last_harvested_run_id", "last_summary", "consecutive_errors",
    ):
        assert field in w
    assert w["watch_id"] == "DEV__TEST"
    assert w["last_harvested_run_id"] is None
    assert w["enabled"] is True
    assert w["consecutive_errors"] == 0


def test_upsert_alias_desconocido_lanza(store):
    with pytest.raises(dbcompare_watch.DbCompareWatchError):
        dbcompare_watch.upsert_watch("NOPE", "TEST", enabled=True)


def test_upsert_alias_con_separador_lanza(store):
    with pytest.raises(dbcompare_watch.DbCompareWatchError):
        dbcompare_watch.upsert_watch("A__B", "C", enabled=True)


def test_upsert_mismo_par_actualiza_enabled_sin_duplicar(store):
    dbcompare_watch.upsert_watch("DEV", "TEST", enabled=True)
    w2 = dbcompare_watch.upsert_watch("DEV", "TEST", enabled=False)
    watches = dbcompare_watch.list_watches()
    assert len(watches) == 1
    assert w2["enabled"] is False


def test_source_igual_target_lanza(store):
    with pytest.raises(dbcompare_watch.DbCompareWatchError):
        dbcompare_watch.upsert_watch("DEV", "DEV", enabled=True)


def test_delete_watch_true_false(store):
    dbcompare_watch.upsert_watch("DEV", "TEST", enabled=True)
    assert dbcompare_watch.delete_watch("DEV__TEST") is True
    assert dbcompare_watch.delete_watch("DEV__TEST") is False
    assert dbcompare_watch.list_watches() == []


def test_escritura_atomica_no_deja_tmp(store):
    dbcompare_watch.upsert_watch("DEV", "TEST", enabled=True)
    watch_dir = store / "db_compare" / "watch"
    assert not (watch_dir / "watches.json.tmp").exists()


def test_modulo_no_importa_conexion():
    src = (
        os.path.join(os.path.dirname(dbcompare_watch.__file__), "dbcompare_watch.py")
    )
    text = open(src, encoding="utf-8").read()
    assert "import sqlalchemy" not in text
    assert "dbcompare_connect" not in text
