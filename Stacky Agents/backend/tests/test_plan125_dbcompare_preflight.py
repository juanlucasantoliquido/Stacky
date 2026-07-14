"""Tests F0 (Plan 125): preflight de dependencias 122/123/124 sin importarlas de verdad."""
from __future__ import annotations

import pytest

from services import dbcompare_deps_preflight as preflight


def test_check_dependencies_reporta_bool_por_componente(monkeypatch):
    def fake_find_spec(name):
        mapping = {
            "services.dbcompare_diff": object(),
            "services.dbcompare_runs": None,
            "api.db_compare": None,
        }
        return mapping.get(name, None)

    monkeypatch.setattr(preflight.importlib.util, "find_spec", fake_find_spec)

    result = preflight.check_dependencies()

    assert result["diff_engine"] is True
    assert result["runs_store"] is False
    assert result["api_blueprint"] is False


def test_all_present_true_solo_si_los_tres_estan(monkeypatch):
    monkeypatch.setattr(preflight.importlib.util, "find_spec", lambda name: object())
    assert preflight.check_dependencies()["all_present"] is True

    monkeypatch.setattr(
        preflight.importlib.util,
        "find_spec",
        lambda name: None if name == "services.dbcompare_runs" else object(),
    )
    assert preflight.check_dependencies()["all_present"] is False


def test_no_importa_el_modulo_real(monkeypatch):
    calls = []

    def fake_find_spec(name):
        calls.append(name)
        return None

    monkeypatch.setattr(preflight.importlib.util, "find_spec", fake_find_spec)

    def fail_import(name, *a, **kw):
        raise AssertionError(f"no debe importar el modulo real: {name}")

    monkeypatch.setattr(preflight.importlib, "import_module", fail_import)

    preflight.check_dependencies()

    assert set(calls) == set(preflight.REQUIRED_MODULES.values())


def test_require_or_gap_componente_conocido_no_lanza():
    preflight.require_or_gap("diff_engine")
    preflight.require_or_gap("runs_store")
    preflight.require_or_gap("api_blueprint")


def test_require_or_gap_componente_desconocido_lanza():
    with pytest.raises(KeyError):
        preflight.require_or_gap("no_existe")
