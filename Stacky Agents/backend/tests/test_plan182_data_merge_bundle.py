"""Plan 182 F0 (flag) + F2 (wiring del bundle) — kwarg aditivo `data_merge_mode`
en `generate_parity_bundle_from_diff` (default False ⇒ byte-idéntico) y lectura
ÚNICA de la flag en el wrapper `generate_parity_bundle`.

Ver Stacky Agents/docs/182_PLAN_SCRIPTS_DE_DATOS_V2_MERGE_IDEMPOTENTE_*.md #F0/#F2
y la hoja de ruta 184 §2.5 (kwarg `data_merge_mode`).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

import pytest  # noqa: E402

from services import dbcompare_scripts as scripts  # noqa: E402
from tests._plan125_fixtures import make_schema_obj  # noqa: E402

TS = "20260714_120000"
FLAG = "STACKY_DB_COMPARE_DATA_MERGE_ENABLED"


def _dd(**ov):
    base = {
        "version": 1,
        "schema": "dbo",
        "table": "PARAMS",
        "pk_cols": ["ID"],
        "columns": ["ID", "NOMBRE", "VALOR"],
        "column_types": {"ID": "INT", "NOMBRE": "VARCHAR(50)", "VALOR": "INT"},
        "columns_skipped": [],
        "only_source": [{"ID": "1", "NOMBRE": "A", "VALOR": "10"}, {"ID": "3", "NOMBRE": "C", "VALOR": "30"}],
        "only_target": [{"ID": "4", "NOMBRE": "D", "VALOR": "40"}],
        "changed": [{"pk": {"ID": "2"}, "cells": {"NOMBRE": {"source": "B", "target": "B-mod"}}}],
        "row_counts": {"source": 3, "target": 3},
        "truncated": False,
        "identical": False,
    }
    base.update(ov)
    return base


def _schema_diff_sin_cambios():
    return {
        "version": 1,
        "engine": "sqlserver",
        "source": {"alias": "DEV", "snapshot_id": "s1", "content_hash": "h1"},
        "target": {"alias": "TEST", "snapshot_id": "s2", "content_hash": "h2"},
        "items": [],
        "summary": {},
    }


def _empty_schema_obj(alias):
    return make_schema_obj(alias, "dbo")


# ---------------------------------------------------------------------------
# F0 — Flag, config, categoría, arista
# ---------------------------------------------------------------------------


def test_flag_registrada_bool_on_requires_master():
    from services import harness_flags as hf

    spec = next((s for s in hf.FLAG_REGISTRY if s.key == FLAG), None)
    assert spec is not None, "FlagSpec de Plan 182 no registrada"
    assert spec.type == "bool"
    assert spec.default is True
    assert spec.requires == "STACKY_DB_COMPARE_ENABLED"


def test_flag_en_categoria():
    from services import harness_flags as hf

    assert hf.categorize(FLAG) == "comparador_bd"


def test_config_attr_existe_bool():
    import config

    assert isinstance(getattr(config.config, FLAG), bool)


# ---------------------------------------------------------------------------
# F2 — Wiring del bundle
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolated_data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(scripts, "data_dir", lambda: tmp_path)
    return tmp_path


def _read_bundle_files(tmp_path, run_id):
    base = tmp_path / "db_compare" / "bundles" / run_id
    out = {}
    for p in sorted(base.rglob("*")):
        if p.is_file():
            out[str(p.relative_to(base)).replace("\\", "/")] = p.read_text(encoding="utf-8")
    return out


def test_off_byte_identico(tmp_path):
    """KPI-1 (BLOQUEANTE): SIN kwarg y con data_merge_mode=False ⇒ byte-idéntico,
    y las actions son las de v1 (data_insert/update/delete, sin data_merge)."""
    data_diff = {"status": "done", "tables": {"dbo.PARAMS": _dd()}}
    m_default = scripts.generate_parity_bundle_from_diff(
        _schema_diff_sin_cambios(), "run_off", _empty_schema_obj("DEV"), _empty_schema_obj("TEST"),
        "sqlserver", ts=TS, data_diff=data_diff,
    )
    files_default = _read_bundle_files(tmp_path, "run_off")

    m_explicit = scripts.generate_parity_bundle_from_diff(
        _schema_diff_sin_cambios(), "run_off", _empty_schema_obj("DEV"), _empty_schema_obj("TEST"),
        "sqlserver", ts=TS, data_diff=data_diff, data_merge_mode=False,
    )
    files_explicit = _read_bundle_files(tmp_path, "run_off")

    assert m_default == m_explicit
    assert files_default == files_explicit
    actions = {e["action"] for e in m_default["entries"] if e["action"].startswith("data_")}
    assert actions == {"data_insert", "data_update", "data_delete"}


def test_on_emite_data_merge_en_03_datos(tmp_path):
    data_diff = {"status": "done", "tables": {"dbo.PARAMS": _dd()}}
    manifest = scripts.generate_parity_bundle_from_diff(
        _schema_diff_sin_cambios(), "run_on", _empty_schema_obj("DEV"), _empty_schema_obj("TEST"),
        "sqlserver", ts=TS, data_diff=data_diff, data_merge_mode=True,
    )
    by_action = {e["action"]: e for e in manifest["entries"]}
    assert "data_insert" not in by_action
    merge = by_action["data_merge"]
    assert merge["file"].startswith("03_datos/")
    assert merge["destructive"] is False
    assert merge["backup_file"] is not None
    assert "data_update" in by_action
    assert "data_delete" in by_action
    assert by_action["data_delete"]["file"].startswith("09_destructivo/")


def test_invariante_pareo_exige_backup_para_merge():
    """KPI-6: data_merge entra en el conjunto que exige resguardo; una entry
    data_merge sin backup_file ni rollback_file hace raise."""
    assert "data_merge" in scripts._DATA_DML_KINDS
    assert "data_merge" in scripts._REQUIRES_RESGUARDO_KINDS
    bad_entry = {
        "action": "data_merge", "schema": "dbo", "name": "PARAMS",
        "backup_file": None, "rollback_file": None,
    }
    with pytest.raises(scripts.DbCompareRunError):
        scripts._assert_pairing_invariant([bad_entry])
    # con backup NO hace raise
    ok_entry = dict(bad_entry, backup_file="01_backups/001_table_backup_dbo_PARAMS.sql")
    scripts._assert_pairing_invariant([ok_entry])


def test_wrapper_lee_flag(tmp_path, monkeypatch):
    """El wrapper generate_parity_bundle es el ÚNICO lector de la flag: manifest
    trae data_merge sii la flag está ON."""
    import config
    from services import dbcompare_runs, dbcompare_snapshot

    run = {
        "status": "done",
        "engine": "sqlserver",
        "diff": _schema_diff_sin_cambios(),
        "source_snapshot_id": "s1",
        "target_snapshot_id": "s2",
        "data_diff": {"status": "done", "tables": {"dbo.PARAMS": _dd()}},
    }
    monkeypatch.setattr(dbcompare_runs, "get_run", lambda rid: run)
    monkeypatch.setattr(
        dbcompare_snapshot, "load_snapshot",
        lambda sid: _empty_schema_obj("DEV") if sid == "s1" else _empty_schema_obj("TEST"),
    )

    monkeypatch.setattr(config.config, FLAG, True, raising=False)
    m_on = scripts.generate_parity_bundle("run_flag_on")
    assert any(e["action"] == "data_merge" for e in m_on["entries"])
    assert not any(e["action"] == "data_insert" for e in m_on["entries"])

    monkeypatch.setattr(config.config, FLAG, False, raising=False)
    m_off = scripts.generate_parity_bundle("run_flag_off")
    assert not any(e["action"] == "data_merge" for e in m_off["entries"])
    assert any(e["action"] == "data_insert" for e in m_off["entries"])


def test_visor_sirve_data_merge_sin_cambios(tmp_path):
    """Perímetro §9: la allowlist deriva 100% del manifest (api/db_compare.py sin
    editar) ⇒ el archivo data_merge se sirve por HTTP con 200."""
    import config as cfg

    data_diff = {"status": "done", "tables": {"dbo.PARAMS": _dd()}}
    manifest = scripts.generate_parity_bundle_from_diff(
        _schema_diff_sin_cambios(), "run_visor", _empty_schema_obj("DEV"), _empty_schema_obj("TEST"),
        "sqlserver", ts=TS, data_diff=data_diff, data_merge_mode=True,
    )
    merge_file = next(e["file"] for e in manifest["entries"] if e["action"] == "data_merge")

    orig = getattr(cfg.config, "STACKY_DB_COMPARE_ENABLED", False)
    cfg.config.STACKY_DB_COMPARE_ENABLED = True
    try:
        from app import create_app

        app = create_app()
        app.config["TESTING"] = True
        c = app.test_client()
        r = c.get(f"/api/db-compare/runs/run_visor/scripts/file?path={merge_file}")
        assert r.status_code == 200, r.get_data(as_text=True)
        assert "MERGE INTO" in r.get_data(as_text=True)
    finally:
        cfg.config.STACKY_DB_COMPARE_ENABLED = orig
