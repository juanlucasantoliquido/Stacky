"""Plan 179 — Diff v2 quirúrgico + normalización endurecida de defaults.

Cubre F1 (normalización v2 de defaults, funciones puras) y F3 (diff pasivo por
versión con changed_fields). Todos los snapshots son dicts armados a mano — sin
BD. Ver Stacky Agents/docs/179_PLAN_FIDELIDAD_SNAPSHOT_V2_*.md
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

from services import dbcompare_diff as diff


# ---------------------------------------------------------------------------
# F1 — Normalización v2 de defaults (función pura)
# ---------------------------------------------------------------------------

def test_norm_v2_parens_heredado():
    assert diff._normalize_default_v2("((0))") == diff._normalize_default_v2("(0)") == "0"


def test_norm_v2_case_funciones():
    assert diff._normalize_default_v2("GETDATE()") == diff._normalize_default_v2("getdate()")


def test_norm_v2_espacios_comas():
    assert diff._normalize_default_v2("CONVERT(bit, 0)") == diff._normalize_default_v2("CONVERT(BIT,0)")


def test_norm_v2_literal_string_conservador_total():
    # case DENTRO de literal NO se foldea
    assert diff._normalize_default_v2("('Abc')") != diff._normalize_default_v2("('ABC')")
    # coma/espacio DENTRO del literal NO se poda
    assert diff._normalize_default_v2("('a, b')") != diff._normalize_default_v2("('a,b')")
    # whitespace interno del literal intacto
    assert diff._normalize_default_v2("('A  B')") != diff._normalize_default_v2("('A B')")


def test_norm_v2_funcion_con_literal_no_foldea():
    # presencia de literal suspende TODA normalización extra (C10, falso positivo residual)
    assert diff._normalize_default_v2("CONVERT(varchar,'x')") != diff._normalize_default_v2("convert(VARCHAR,'x')")


def test_norm_v2_distintos_reales():
    assert diff._normalize_default_v2("0") != diff._normalize_default_v2("1")
    assert diff._normalize_default_v2(None) != diff._normalize_default_v2("0")
    assert diff._normalize_default_v2(None) is None


# ---------------------------------------------------------------------------
# Helpers para F3 (snapshots dict armados a mano)
# ---------------------------------------------------------------------------

def _td(base="NUMERIC", precision=None, scale=None, length=None, collation=None,
        timezone=None, identity=None, computed=None):
    return {
        "base": base, "precision": precision, "scale": scale, "length": length,
        "collation": collation, "timezone": timezone, "identity": identity, "computed": computed,
    }


def _col(name, type_str, *, default=None, nullable=True, autoincrement=False, type_detail=None):
    c = {"name": name, "type": type_str, "nullable": nullable,
         "default": default, "autoincrement": autoincrement}
    if type_detail is not None:
        c["type_detail"] = type_detail
    return c


def _snap(version, cols, *, engine="sqlite", alias="a", schema="s"):
    return {
        "version": version,
        "engine": engine,
        "alias": alias,
        "id": f"{alias}_id",
        "content_hash": "h",
        "schemas": {schema: {
            "tables": {"t": {
                "columns": cols,
                "primary_key": {"name": None, "columns": []},
                "foreign_keys": [],
                "indexes": [],
                "unique_constraints": [],
                "check_constraints": [],
            }},
            "views": {},
            "sequences": [],
        }},
    }


def _type_changes(result):
    return [c for it in result["items"] for c in it["changes"] if c["kind"] == "column_type_changed"]


def _default_changes(result):
    return [c for it in result["items"] for c in it["changes"] if c["kind"] == "column_default_changed"]


# ---------------------------------------------------------------------------
# F3 — Diff v2 pasivo + quirúrgico
# ---------------------------------------------------------------------------

def test_precision_scale_quirurgico():
    s = _snap(2, [_col("importe", "NUMERIC(10, 2)", type_detail=_td(precision=10, scale=2))])
    t = _snap(2, [_col("importe", "NUMERIC(12, 4)", type_detail=_td(precision=12, scale=4))])
    result = diff.diff_snapshots(s, t)
    tc = _type_changes(result)
    assert len(tc) == 1
    assert tc[0]["detail"]["changed_fields"] == ["precision", "scale"]


def test_mezcla_v1_v2_sin_falsos_diffs():
    v1 = _snap(1, [_col("importe", "NUMERIC(10, 2)")])
    v2 = _snap(2, [_col("importe", "NUMERIC(10, 2)", type_detail=_td(precision=10, scale=2))])
    r1 = diff.diff_snapshots(v1, v2)
    assert r1["items"] == []
    assert r1["summary"]["parity_score"] == 100.0
    r2 = diff.diff_snapshots(v2, v1)
    assert r2["items"] == []
    assert r2["summary"]["parity_score"] == 100.0


def test_v1_vs_v1_identico_a_main():
    s = _snap(1, [_col("importe", "NUMERIC(10, 2)")])
    t = _snap(1, [_col("importe", "NUMERIC(12, 4)")])
    result = diff.diff_snapshots(s, t)
    tc = _type_changes(result)
    assert len(tc) == 1
    assert "changed_fields" not in tc[0]["detail"]


def test_render_cosmetico_no_emite():
    td = _td(precision=10, scale=2)
    s = _snap(2, [_col("importe", "NUMERIC(10, 2)", type_detail=dict(td))])
    t = _snap(2, [_col("importe", "NUMERIC(10,2)", type_detail=dict(td))])
    result = diff.diff_snapshots(s, t)
    assert _type_changes(result) == []


def test_tipo_opaco_red_de_seguridad():
    s = _snap(2, [_col("x", "TEXT", type_detail=_td(base="TEXT"))])
    t = _snap(2, [_col("x", "VARCHAR", type_detail=_td(base="TEXT"))])
    result = diff.diff_snapshots(s, t)
    tc = _type_changes(result)
    assert len(tc) == 1
    assert tc[0]["detail"]["changed_fields"] == ["type"]


def test_identity_detectada_quirurgica():
    s = _snap(2, [_col("id", "INTEGER", type_detail=_td(base="INTEGER", identity=None))])
    t = _snap(2, [_col("id", "INTEGER", type_detail=_td(base="INTEGER", identity={"start": 1, "increment": 1}))])
    result = diff.diff_snapshots(s, t)
    tc = _type_changes(result)
    assert len(tc) == 1
    assert "identity" in tc[0]["detail"]["changed_fields"]


def test_collation_detectada():
    s = _snap(2, [_col("nombre", "VARCHAR(50)", type_detail=_td(base="VARCHAR", length=50, collation="Latin1_General_CI_AS"))])
    t = _snap(2, [_col("nombre", "VARCHAR(50)", type_detail=_td(base="VARCHAR", length=50, collation="Modern_Spanish_CI_AS"))])
    result = diff.diff_snapshots(s, t)
    tc = _type_changes(result)
    assert len(tc) == 1
    assert tc[0]["detail"]["changed_fields"] == ["collation"]


def test_collation_timezone_null_asimetrico_no_emite():
    # collation null vs valor -> NO cuenta
    s = _snap(2, [_col("nombre", "VARCHAR(50)", type_detail=_td(base="VARCHAR", length=50, collation=None))])
    t = _snap(2, [_col("nombre", "VARCHAR(50)", type_detail=_td(base="VARCHAR", length=50, collation="Latin1_General_CI_AS"))])
    assert _type_changes(diff.diff_snapshots(s, t)) == []

    # timezone null vs False -> NO cuenta
    s2 = _snap(2, [_col("ts", "DATETIME", type_detail=_td(base="DATETIME", timezone=None))])
    t2 = _snap(2, [_col("ts", "DATETIME", type_detail=_td(base="DATETIME", timezone=False))])
    assert _type_changes(diff.diff_snapshots(s2, t2)) == []


def test_defaults_normalizados_v2():
    # v2: GETDATE() vs getdate() -> 0
    s = _snap(2, [_col("a", "DATETIME", default="GETDATE()", type_detail=_td(base="DATETIME"))])
    t = _snap(2, [_col("a", "DATETIME", default="getdate()", type_detail=_td(base="DATETIME"))])
    assert _default_changes(diff.diff_snapshots(s, t)) == []

    # v2: CONVERT(bit, 0) vs CONVERT(BIT,0) -> 0
    s = _snap(2, [_col("a", "BIT", default="CONVERT(bit, 0)", type_detail=_td(base="BIT"))])
    t = _snap(2, [_col("a", "BIT", default="CONVERT(BIT,0)", type_detail=_td(base="BIT"))])
    assert _default_changes(diff.diff_snapshots(s, t)) == []

    # v2: 0 vs 1 -> 1
    s = _snap(2, [_col("a", "INT", default="0", type_detail=_td(base="INT"))])
    t = _snap(2, [_col("a", "INT", default="1", type_detail=_td(base="INT"))])
    assert len(_default_changes(diff.diff_snapshots(s, t))) == 1

    # v1 (main): GETDATE() vs getdate() SÍ emite (antes/después)
    s = _snap(1, [_col("a", "DATETIME", default="GETDATE()")])
    t = _snap(1, [_col("a", "DATETIME", default="getdate()")])
    assert len(_default_changes(diff.diff_snapshots(s, t))) == 1


def test_scripts_no_rompen_con_detail_v2():
    from services import dbcompare_scripts as scripts

    s = _snap(2, [_col("importe", "NUMERIC(10, 2)", nullable=False, type_detail=_td(precision=10, scale=2))],
              engine="sqlserver", schema="dbo")
    t = _snap(2, [_col("importe", "NUMERIC(12, 4)", nullable=False, type_detail=_td(precision=12, scale=4))],
              engine="sqlserver", schema="dbo")
    d = diff.diff_snapshots(s, t)

    # flatten_diff conserva el detail de column_type_changed
    pieces = scripts.flatten_diff(d)
    type_pieces = [p for p in pieces if p["kind"] == "column_type_changed"]
    assert len(type_pieces) == 1
    det = type_pieces[0]["detail"]
    assert det["column"] == "importe"
    assert det["source"] is not None and det["target"] is not None
    assert "changed_fields" in det  # aditivo, no rompe

    # camino de bundle no lanza ValueError (setup literal de test_plan125_dbcompare_bundle)
    import services.dbcompare_scripts as sc

    manifest = sc.generate_parity_bundle_from_diff(d, "run_plan179", s, t, "sqlserver", ts="20260718_120000")
    assert manifest["run_id"] == "run_plan179"
    type_entries = [e for e in manifest["entries"] if e["action"] == "column_type_changed"]
    assert len(type_entries) == 1
    assert type_entries[0]["backup_file"]  # backup pareado conservado (KPI-1)


@pytest.fixture(autouse=True)
def _isolated_data_dir(tmp_path, monkeypatch):
    import services.dbcompare_scripts as scripts

    monkeypatch.setattr(scripts, "data_dir", lambda: tmp_path)
    return tmp_path
