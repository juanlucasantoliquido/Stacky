"""Plan 201 F2 — Catálogo persistido + selección del operador.

El riel duro: re-escanear NUNCA re-tilda lo que el operador destildó.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

from services import solution_store as st  # noqa: E402

_WS = "N:\\ws\\cliente"


@pytest.fixture(autouse=True)
def _tmp_store(tmp_path, monkeypatch):
    monkeypatch.setattr(st, "store_path", lambda: tmp_path / "build_solutions.json")


def _sol(slug, tipos=("web",)):
    return {
        "slug": slug,
        "sln_path": f"N:\\ws\\{slug}.sln",
        "sln_name": slug,
        "friendly_name": slug,
        "projects": [{"name": f"p-{t}", "csproj_path": "x.csproj", "type": t,
                      "target_framework": "net8.0"} for t in tipos],
    }


def _fake_scan(monkeypatch, solutions, truncated=False):
    monkeypatch.setattr(
        st, "scan_solutions_ex",
        lambda ws: {"solutions": [dict(s, projects=list(s["projects"])) for s in solutions],
                    "truncated": truncated},
        raising=True,
    )


def test_load_missing_returns_empty():
    assert st.load_catalog(_WS) == {"scanned_at": None, "truncated": False, "solutions": []}
    assert st.load_catalog("") == {"scanned_at": None, "truncated": False, "solutions": []}
    assert st.tracked_solutions(_WS) == []


def test_rescan_persists_and_reload_matches(monkeypatch):
    _fake_scan(monkeypatch, [_sol("uno"), _sol("dos", ("library",))])

    guardado = st.rescan_and_save(_WS)
    recargado = st.load_catalog(_WS)

    assert [s["slug"] for s in guardado["solutions"]] == ["uno", "dos"]
    assert recargado["solutions"] == guardado["solutions"]
    assert recargado["scanned_at"] == guardado["scanned_at"]
    assert st.store_path().exists()


def test_new_deployable_slug_autotracked(monkeypatch):
    _fake_scan(monkeypatch, [
        _sol("web-app", ("web",)),
        _sol("cli", ("console",)),
        _sol("worker", ("service",)),
        _sol("lib", ("library",)),
        _sol("raro", ("unknown",)),
    ])

    por_slug = {s["slug"]: s["tracked"] for s in st.rescan_and_save(_WS)["solutions"]}

    assert por_slug == {"web-app": True, "cli": True, "worker": True,
                        "lib": False, "raro": False}


def test_tracked_survives_rescan(monkeypatch):
    _fake_scan(monkeypatch, [_sol("lib", ("library",))])
    st.rescan_and_save(_WS)
    st.set_tracked(_WS, "lib", True)

    st.rescan_and_save(_WS)

    assert st.load_catalog(_WS)["solutions"][0]["tracked"] is True


def test_untracked_known_slug_stays_untracked_on_rescan(monkeypatch):
    """Reversibilidad: si el operador destilda un desplegable, el re-scan lo respeta."""
    _fake_scan(monkeypatch, [_sol("web-app", ("web",))])
    assert st.rescan_and_save(_WS)["solutions"][0]["tracked"] is True

    st.set_tracked(_WS, "web-app", False)
    st.rescan_and_save(_WS)

    assert st.load_catalog(_WS)["solutions"][0]["tracked"] is False, \
        "el re-scan NO puede re-tildar lo que el operador destildó"


def test_truncated_flag_persisted(monkeypatch):
    _fake_scan(monkeypatch, [_sol("uno")], truncated=True)

    assert st.rescan_and_save(_WS)["truncated"] is True
    assert st.load_catalog(_WS)["truncated"] is True


def test_slug_desaparecido_se_elimina(monkeypatch):
    _fake_scan(monkeypatch, [_sol("uno"), _sol("dos")])
    st.rescan_and_save(_WS)

    _fake_scan(monkeypatch, [_sol("uno")])
    st.rescan_and_save(_WS)

    assert [s["slug"] for s in st.load_catalog(_WS)["solutions"]] == ["uno"]


def test_set_tracked_toggles_and_persists(monkeypatch):
    _fake_scan(monkeypatch, [_sol("lib", ("library",))])
    st.rescan_and_save(_WS)

    st.set_tracked(_WS, "lib", True)
    assert st.tracked_solutions(_WS)[0]["slug"] == "lib"

    st.set_tracked(_WS, "lib", False)
    assert st.tracked_solutions(_WS) == []


def test_set_tracked_unknown_slug_is_noop(monkeypatch):
    _fake_scan(monkeypatch, [_sol("uno")])
    antes = st.rescan_and_save(_WS)

    despues = st.set_tracked(_WS, "fantasma", True)

    assert [s["slug"] for s in despues["solutions"]] == [s["slug"] for s in antes["solutions"]]


def test_set_tracked_workspace_desconocido_no_crashea():
    assert st.set_tracked("N:\\otro", "x", True) == {"scanned_at": None, "truncated": False,
                                                     "solutions": []}


def test_corrupt_json_degrades_to_empty(monkeypatch):
    st.store_path().parent.mkdir(parents=True, exist_ok=True)
    st.store_path().write_text("{{{ roto", encoding="utf-8")

    assert st.load_catalog(_WS) == {"scanned_at": None, "truncated": False, "solutions": []}

    _fake_scan(monkeypatch, [_sol("uno")])
    assert [s["slug"] for s in st.rescan_and_save(_WS)["solutions"]] == ["uno"]


def test_multi_workspace_no_se_pisan(monkeypatch):
    otro = "N:\\ws\\otro-cliente"
    _fake_scan(monkeypatch, [_sol("uno")])
    st.rescan_and_save(_WS)
    _fake_scan(monkeypatch, [_sol("dos")])
    st.rescan_and_save(otro)

    assert [s["slug"] for s in st.load_catalog(_WS)["solutions"]] == ["uno"]
    assert [s["slug"] for s in st.load_catalog(otro)["solutions"]] == ["dos"]
    doc = json.loads(st.store_path().read_text(encoding="utf-8"))
    assert set(doc.keys()) == {_WS, otro}
