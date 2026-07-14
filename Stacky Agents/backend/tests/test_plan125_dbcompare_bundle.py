"""Tests F3 (Plan 125): bundle + manifest con emparejamiento 1:1 (KPI-1)."""
from __future__ import annotations

import zipfile
from io import BytesIO

import pytest

from services import dbcompare_scripts as scripts
from tests._plan125_fixtures import make_col, make_schema_obj, make_table

TS = "20260714_120000"
RUN_ID = "run_test_001"


def _diff():
    return {
        "version": 1,
        "engine": "sqlserver",
        "source": {"alias": "DEV", "snapshot_id": "s1", "content_hash": "h1"},
        "target": {"alias": "TEST", "snapshot_id": "s2", "content_hash": "h2"},
        "items": [
            {"object_type": "table", "schema": "dbo", "name": "NUEVA", "action": "added", "severity": "warn", "changes": []},
            {
                "object_type": "table",
                "schema": "dbo",
                "name": "CLIENTES",
                "action": "changed",
                "severity": "danger",
                "changes": [
                    {"kind": "column_removed", "severity": "danger", "detail": {"column": "OBSOLETA"}},
                    {"kind": "index_removed", "severity": "warn", "detail": {"name": "IX_DOC"}},
                ],
            },
            {"object_type": "table", "schema": "dbo", "name": "VIEJA", "action": "removed", "severity": "danger", "changes": []},
        ],
        "summary": {},
    }


def _source():
    return make_schema_obj(
        "DEV", "dbo", tables={"NUEVA": make_table(columns=[make_col("ID", "INT", nullable=False)], pk_columns=["ID"], pk_name="PK_NUEVA")}
    )


def _target():
    return make_schema_obj(
        "TEST",
        "dbo",
        tables={
            "CLIENTES": make_table(columns=[], indexes=[{"name": "IX_DOC", "columns": ["DOCUMENTO"], "unique": False}]),
            "VIEJA": make_table(columns=[make_col("ID", "INT", nullable=False)], pk_columns=["ID"], pk_name="PK_VIEJA"),
        },
    )


@pytest.fixture(autouse=True)
def _isolated_data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(scripts, "data_dir", lambda: tmp_path)
    return tmp_path


def test_bundle_layout_y_numeracion(tmp_path):
    manifest = scripts.generate_parity_bundle_from_diff(_diff(), RUN_ID, _source(), _target(), "sqlserver", ts=TS)

    bundle_dir = tmp_path / "db_compare" / "bundles" / RUN_ID
    expected_files = {
        "README.md",
        "MANIFEST.json",
        "01_backups/001_table_backup_dbo_CLIENTES.sql",
        "01_backups/002_table_backup_dbo_VIEJA.sql",
        "01_backups/003_rollback_index_removed_dbo_CLIENTES.sql",
        "01_backups/004_rollback_table_removed_dbo_VIEJA.sql",
        "02_paridad/201_table_added_dbo_NUEVA.sql",
        "02_paridad/202_index_removed_dbo_CLIENTES.sql",
        "09_destructivo/901_column_removed_dbo_CLIENTES.sql",
        "09_destructivo/902_table_removed_dbo_VIEJA.sql",
    }
    actual_files = {str(p.relative_to(bundle_dir)).replace("\\", "/") for p in bundle_dir.rglob("*") if p.is_file()}
    assert actual_files == expected_files

    assert manifest["counts"] == {"backups": 4, "parity": 2, "destructive": 2}
    entry_files = {e["file"] for e in manifest["entries"]}
    assert entry_files == {
        "02_paridad/201_table_added_dbo_NUEVA.sql",
        "02_paridad/202_index_removed_dbo_CLIENTES.sql",
        "09_destructivo/901_column_removed_dbo_CLIENTES.sql",
        "09_destructivo/902_table_removed_dbo_VIEJA.sql",
    }


def test_invariante_pareo_kpi1():
    manifest = scripts.generate_parity_bundle_from_diff(_diff(), RUN_ID, _source(), _target(), "sqlserver", ts=TS)
    for entry in manifest["entries"]:
        if entry["destructive"]:
            assert entry["backup_file"] or entry["rollback_file"], entry
    column_removed = next(e for e in manifest["entries"] if e["action"] == "column_removed")
    assert column_removed["backup_file"] == "01_backups/001_table_backup_dbo_CLIENTES.sql"
    index_removed = next(e for e in manifest["entries"] if e["action"] == "index_removed")
    assert index_removed["rollback_file"] == "01_backups/003_rollback_index_removed_dbo_CLIENTES.sql"
    table_removed = next(e for e in manifest["entries"] if e["action"] == "table_removed")
    assert table_removed["backup_file"] and table_removed["rollback_file"]


def test_manifest_backup_null_en_aditivas():
    manifest = scripts.generate_parity_bundle_from_diff(_diff(), RUN_ID, _source(), _target(), "sqlserver", ts=TS)
    table_added = next(e for e in manifest["entries"] if e["action"] == "table_added")
    assert table_added["backup_file"] is None
    assert table_added["rollback_file"] is None


def test_regenerar_idempotente(tmp_path):
    m1 = scripts.generate_parity_bundle_from_diff(_diff(), RUN_ID, _source(), _target(), "sqlserver", ts=TS)
    m2 = scripts.generate_parity_bundle_from_diff(_diff(), RUN_ID, _source(), _target(), "sqlserver", ts=TS)
    # generated_at usa wall-clock real (no `ts`, que solo fija los nombres de
    # backup); dos corridas legitimamente difieren ahi. El resto del bundle
    # (layout, entries, counts) debe ser identico -> regenerar es idempotente.
    assert {**m1, "generated_at": None} == {**m2, "generated_at": None}
    bundle_dir = tmp_path / "db_compare" / "bundles" / RUN_ID
    assert not (tmp_path / "db_compare" / "bundles" / f"{RUN_ID}.tmp").exists()
    assert bundle_dir.exists()


def test_zip_contiene_todo(tmp_path):
    scripts.generate_parity_bundle_from_diff(_diff(), RUN_ID, _source(), _target(), "sqlserver", ts=TS)
    zip_bytes = scripts.bundle_zip_bytes(RUN_ID)
    with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
        namelist = set(zf.namelist())
    bundle_dir = tmp_path / "db_compare" / "bundles" / RUN_ID
    disk_files = {str(p.relative_to(bundle_dir)).replace("\\", "/") for p in bundle_dir.rglob("*") if p.is_file()}
    assert namelist == disk_files


def test_load_manifest_none_si_no_generado():
    assert scripts.load_manifest("run_inexistente") is None


def test_load_manifest_devuelve_lo_persistido(tmp_path):
    scripts.generate_parity_bundle_from_diff(_diff(), RUN_ID, _source(), _target(), "sqlserver", ts=TS)
    loaded = scripts.load_manifest(RUN_ID)
    assert loaded["run_id"] == RUN_ID
    assert len(loaded["entries"]) == 4


def test_invariante_invalida_no_deja_archivos_parciales(tmp_path, monkeypatch):
    """[FIX C4] Si la invariante KPI-1 dispara, CERO bytes deben tocarse en disco."""

    def _broken_emit_resguardo(piece, *a, **kw):
        return []  # nunca resguarda nada => viola el invariante para piezas destructivas

    monkeypatch.setattr(scripts, "emit_resguardo", _broken_emit_resguardo)

    with pytest.raises(scripts.DbCompareRunError):
        scripts.generate_parity_bundle_from_diff(_diff(), RUN_ID, _source(), _target(), "sqlserver", ts=TS)

    bundles_root = tmp_path / "db_compare" / "bundles"
    assert not bundles_root.exists() or list(bundles_root.iterdir()) == []
