"""Plan 120 F3 — deploy_store.py: apps CRUD + ledger + locks anti-concurrencia."""
from __future__ import annotations

import json
import os
import sys
import threading
from pathlib import Path

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
_BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

from services import deploy_store as store


def _app(app_id="miapp"):
    return {
        "id": app_id,
        "artifact": {"kind": "folder", "path": "C:\\build\\miapp\\out"},
        "targets": {
            "__local__": {
                "install_path": "D:\\apps\\miapp",
                "smoke": {"kind": "none", "url": None, "command": None},
                "pre_switch": None,
                "post_switch": None,
                "protected": False,
            },
        },
    }


@pytest.fixture()
def st(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "_apps_path", lambda: tmp_path / "deploy_apps.json")
    monkeypatch.setattr(store, "_ledger_path", lambda: tmp_path / "deploy_ledger.jsonl")
    store._RUN_LOCKS.clear()
    return store


def test_crud_apps_roundtrip(st):
    assert st.list_apps() == []
    st.upsert_app(_app())
    assert [a["id"] for a in st.list_apps()] == ["miapp"]
    assert st.get_app("miapp")["artifact"]["kind"] == "folder"
    assert st.get_app("nope") is None
    assert st.delete_app("miapp") is True
    assert st.delete_app("miapp") is False
    assert st.list_apps() == []


def test_upsert_valida(st):
    bad = _app()
    bad["id"] = "Bad Id!"
    with pytest.raises(ValueError):
        st.upsert_app(bad)


def test_apps_json_corrupto_degrada_a_vacio(st, tmp_path):
    (tmp_path / "deploy_apps.json").write_text("{not valid json", encoding="utf-8")
    assert st.list_apps() == []


def test_append_y_read_ledger_orden(st):
    st.append_ledger({"run_id": "dr-1", "app_id": "miapp", "target": "__local__", "status": "success"})
    st.append_ledger({"run_id": "dr-2", "app_id": "miapp", "target": "__local__", "status": "failed"})
    rows = st.read_ledger(app_id="miapp")
    assert [r["run_id"] for r in rows] == ["dr-2", "dr-1"]  # más recientes primero


def test_update_ledger_entry_por_run_id(st):
    st.append_ledger({"run_id": "dr-1", "app_id": "miapp", "target": "__local__", "status": "running"})
    st.update_ledger_entry("dr-1", {"status": "success"})
    rows = st.read_ledger(app_id="miapp")
    assert rows[0]["status"] == "success"


def test_ledger_linea_corrupta_se_salta(st, tmp_path):
    path = tmp_path / "deploy_ledger.jsonl"
    path.write_text('{"run_id":"dr-1","app_id":"a"}\nNOT JSON\n{"run_id":"dr-2","app_id":"a"}\n', encoding="utf-8")
    rows = st.read_ledger(app_id="a")
    assert [r["run_id"] for r in rows] == ["dr-2", "dr-1"]


def test_lock_409_semantica(st):
    run_id = st.acquire_run_lock("miapp", "__local__")
    assert run_id is not None
    assert run_id.startswith("dr-")
    assert st.acquire_run_lock("miapp", "__local__") is None  # ocupado
    st.release_run_lock("miapp", "__local__")
    assert st.acquire_run_lock("miapp", "__local__") is not None  # liberado


def test_last_success_y_retained(st):
    st.append_ledger({"run_id": "dr-1", "app_id": "miapp", "target": "__local__",
                       "action": "deploy", "status": "success", "version_id": "v1"})
    st.append_ledger({"run_id": "dr-2", "app_id": "miapp", "target": "__local__",
                       "action": "deploy", "status": "failed", "version_id": "v2"})
    st.append_ledger({"run_id": "dr-3", "app_id": "miapp", "target": "__local__",
                       "action": "deploy", "status": "success", "version_id": "v3"})
    assert st.last_success_version("miapp", "__local__") == "v3"
    assert st.retained_versions("miapp", "__local__") == ["v3", "v1"]


def test_update_concurrente_no_pierde_entradas(st):
    for i in range(50):
        st.append_ledger({"run_id": f"dr-{i}", "app_id": "miapp", "target": "__local__", "status": "running"})

    def _worker(start, end):
        for i in range(start, end):
            st.update_ledger_entry(f"dr-{i}", {"status": "success"})

    t1 = threading.Thread(target=_worker, args=(0, 25))
    t2 = threading.Thread(target=_worker, args=(25, 50))
    t1.start(); t2.start()
    t1.join(); t2.join()

    rows = st.read_ledger(app_id="miapp", limit=1000)
    assert len(rows) == 50
    assert all(r["status"] == "success" for r in rows)
