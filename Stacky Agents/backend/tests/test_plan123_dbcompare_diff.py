"""Plan 123 F1 — tests del núcleo puro de diff (services/dbcompare_diff.py).

Función pura: sin BD, sin red, sin config. Fixtures = dicts snapshot v1 inline mínimos
(contrato congelado en Stacky Agents/docs/122_PLAN_*.md §F3).
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


# --------------------------------------------------------------------------
# Helpers de fixture (snapshot v1 mínimo, SIN BD)
# --------------------------------------------------------------------------

def _col(name, type_="INT", nullable=True, default=None, autoincrement=False):
    return {
        "name": name,
        "type": type_,
        "nullable": nullable,
        "default": default,
        "autoincrement": autoincrement,
    }


def _table(columns=None, pk_name=None, pk_columns=None, fks=None, indexes=None,
           uniques=None, checks=None):
    return {
        "columns": columns or [],
        "primary_key": {"name": pk_name, "columns": pk_columns or []},
        "foreign_keys": fks or [],
        "indexes": indexes or [],
        "unique_constraints": uniques or [],
        "check_constraints": checks or [],
    }


def _snapshot(alias, engine="sqlserver", schema="dbo", tables=None, views=None,
              sequences=None, snapshot_id=None, content_hash=None):
    tables = tables or {}
    views = views or {}
    sequences = sequences or []
    return {
        "version": 1,
        "id": snapshot_id or f"{alias}_20260101T000000Z",
        "alias": alias,
        "engine": engine,
        "taken_at": "2026-01-01T00:00:00Z",
        "duration_ms": 5,
        "schemas": {
            schema: {
                "tables": tables,
                "views": views,
                "sequences": sequences,
            }
        },
        "counts": {
            "tables": len(tables),
            "views": len(views),
            "sequences": len(sequences),
            "columns": sum(len(t["columns"]) for t in tables.values()),
        },
        "content_hash": content_hash or f"hash-{alias}",
    }


# --------------------------------------------------------------------------
# Tests
# --------------------------------------------------------------------------

def test_identicos_score_100_sin_items():
    from services.dbcompare_diff import diff_snapshots

    t = _table(columns=[_col("id", "INT", nullable=False)], pk_columns=["id"])
    src = _snapshot("a", tables={"CLIENTES": t})
    tgt = _snapshot("b", tables={"CLIENTES": t})

    diff = diff_snapshots(src, tgt)

    assert diff["items"] == []
    assert diff["summary"]["objects_total"] == 1
    assert diff["summary"]["objects_unchanged"] == 1
    assert diff["summary"]["parity_score"] == 100.0
    assert diff["summary"]["by_severity"] == {"info": 0, "warn": 0, "danger": 0}


def test_tabla_added_removed_severidades():
    from services.dbcompare_diff import diff_snapshots

    t = _table(columns=[_col("id", "INT", nullable=False)], pk_columns=["id"])
    src = _snapshot("a", tables={"NUEVA": t})
    tgt = _snapshot("b", tables={"LEGACY": t})

    diff = diff_snapshots(src, tgt)

    by_name = {i["name"]: i for i in diff["items"]}
    assert by_name["NUEVA"]["action"] == "added"
    assert by_name["NUEVA"]["severity"] == "warn"
    assert by_name["NUEVA"]["changes"] == []
    assert by_name["LEGACY"]["action"] == "removed"
    assert by_name["LEGACY"]["severity"] == "danger"
    assert by_name["LEGACY"]["changes"] == []


def test_columna_tipo_nullable_default():
    from services.dbcompare_diff import diff_snapshots

    src_cols = [
        _col("id", "INT", nullable=False),
        _col("nombre", "VARCHAR(50)", nullable=True),
        _col("activo", "BIT", nullable=True, default="1"),
        _col("bloqueado", "BIT", nullable=False, default="0"),
        _col("etiqueta", "VARCHAR(10)", nullable=True, default="'A'"),
    ]
    tgt_cols = [
        _col("id", "INT", nullable=False),
        _col("nombre", "VARCHAR(100)", nullable=True),          # column_type_changed -> danger
        _col("activo", "BIT", nullable=False, default="1"),     # relaxed: src True -> tgt False -> warn
        _col("bloqueado", "BIT", nullable=True, default="0"),   # tightened: src False -> tgt True -> danger
        _col("etiqueta", "VARCHAR(10)", nullable=True, default="'B'"),  # column_default_changed -> info
    ]
    src = _snapshot("a", tables={"CLIENTES": _table(columns=src_cols, pk_columns=["id"])})
    tgt = _snapshot("b", tables={"CLIENTES": _table(columns=tgt_cols, pk_columns=["id"])})

    diff = diff_snapshots(src, tgt)

    item = diff["items"][0]
    assert item["name"] == "CLIENTES"
    assert item["action"] == "changed"
    assert item["severity"] == "danger"  # máxima de sus changes
    kinds = {c["kind"]: c["severity"] for c in item["changes"]}
    assert kinds["column_type_changed"] == "danger"
    assert kinds["column_nullable_relaxed"] == "warn"
    assert kinds["column_nullable_tightened"] == "danger"
    assert kinds["column_default_changed"] == "info"


def test_pk_e_indices():
    from services.dbcompare_diff import diff_snapshots

    src_table = _table(
        columns=[_col("id", "INT", nullable=False), _col("padre_id", "INT")],
        pk_columns=["id"],
        indexes=[{"name": "IX_PADRE", "columns": ["padre_id"], "unique": False}],
    )
    tgt_table = _table(
        columns=[_col("id", "INT", nullable=False), _col("padre_id", "INT")],
        pk_columns=["padre_id"],  # pk distinta -> pk_changed
        indexes=[],                # índice solo en origen -> index_added
    )
    src = _snapshot("a", tables={"HIJA": src_table})
    tgt = _snapshot("b", tables={"HIJA": tgt_table})

    diff = diff_snapshots(src, tgt)

    item = diff["items"][0]
    kinds = [c["kind"] for c in item["changes"]]
    assert "pk_changed" in kinds
    assert "index_added" in kinds


def test_firma_no_nombre():
    """Mismo índice/FK/check con NOMBRES autogenerados distintos en cada lado -> CERO items."""
    from services.dbcompare_diff import diff_snapshots

    src_table = _table(
        columns=[_col("id", "INT", nullable=False), _col("padre_id", "INT")],
        pk_name="PK__CLIE__A1", pk_columns=["id"],
        fks=[{"name": "FK__A1", "columns": ["padre_id"], "referred_schema": "dbo",
              "referred_table": "PADRE", "referred_columns": ["id"]}],
        indexes=[{"name": "IX_A1", "columns": ["padre_id"], "unique": False}],
        uniques=[{"name": "UQ_A1", "columns": ["padre_id"]}],
        checks=[{"name": "CK_A1", "sqltext": "[padre_id] > 0"}],
    )
    tgt_table = _table(
        columns=[_col("id", "INT", nullable=False), _col("padre_id", "INT")],
        pk_name="PK__CLIE__B2", pk_columns=["id"],
        fks=[{"name": "FK__B2", "columns": ["padre_id"], "referred_schema": "dbo",
              "referred_table": "PADRE", "referred_columns": ["id"]}],
        indexes=[{"name": "IX_B2", "columns": ["padre_id"], "unique": False}],
        uniques=[{"name": "UQ_B2", "columns": ["padre_id"]}],
        checks=[{"name": "CK_B2", "sqltext": "[PADRE_ID]   >   0"}],
    )
    src = _snapshot("a", tables={"HIJA": src_table})
    tgt = _snapshot("b", tables={"HIJA": tgt_table})

    diff = diff_snapshots(src, tgt)

    assert diff["items"] == []
    assert diff["summary"]["objects_unchanged"] == 1


def test_default_normalizado_parentesis():
    from services.dbcompare_diff import diff_snapshots

    src_table = _table(columns=[
        _col("id", "INT", nullable=False),
        _col("saldo", "INT", nullable=True, default="((0))"),
        _col("creado", "DATETIME", nullable=True, default="(getdate())"),
    ], pk_columns=["id"])
    tgt_table = _table(columns=[
        _col("id", "INT", nullable=False),
        _col("saldo", "INT", nullable=True, default="(0)"),
        _col("creado", "DATETIME", nullable=True, default="(0)"),
    ], pk_columns=["id"])
    src = _snapshot("a", tables={"CTA": src_table})
    tgt = _snapshot("b", tables={"CTA": tgt_table})

    diff = diff_snapshots(src, tgt)

    item = diff["items"][0]
    default_changes = [c for c in item["changes"] if c["kind"] == "column_default_changed"]
    assert len(default_changes) == 1
    assert default_changes[0]["detail"]["column"] == "creado"


def test_view_sha_y_unverifiable():
    from services.dbcompare_diff import diff_snapshots

    src = _snapshot("a", views={
        "V_OK": {"definition": "SELECT 1", "definition_sha256": "aaa", "error": None},
        "V_BAD": {"definition": None, "definition_sha256": None, "error": "sin permiso"},
    })
    tgt = _snapshot("b", views={
        "V_OK": {"definition": "SELECT 2", "definition_sha256": "bbb", "error": None},
        "V_BAD": {"definition": None, "definition_sha256": None, "error": "sin permiso"},
    })

    diff = diff_snapshots(src, tgt)

    by_name = {i["name"]: i for i in diff["items"]}
    assert by_name["V_OK"]["changes"][0]["kind"] == "view_definition_changed"
    bad_change = by_name["V_BAD"]["changes"][0]
    assert bad_change["kind"] == "view_definition_changed"
    assert bad_change["detail"]["unverifiable"] is True


def test_engines_distintos_lanza():
    from services.dbcompare_diff import diff_snapshots, DbCompareDiffError

    src = _snapshot("a", engine="sqlserver")
    tgt = _snapshot("b", engine="oracle")

    with pytest.raises(DbCompareDiffError):
        diff_snapshots(src, tgt)


def test_determinismo_json_byte_identico():
    """KPI-1."""
    from services.dbcompare_diff import diff_snapshots

    t = _table(columns=[_col("id", "INT", nullable=False)], pk_columns=["id"])
    src = _snapshot("a", tables={"CLIENTES": t, "NUEVA": t})
    tgt = _snapshot("b", tables={"CLIENTES": t})

    d1 = diff_snapshots(src, tgt)
    d2 = diff_snapshots(src, tgt)

    assert json.dumps(d1, sort_keys=True) == json.dumps(d2, sort_keys=True)


def test_kpis_summary_exactos():
    """KPI-2: tabla dropeada + columna con tipo cambiado + índice nuevo -> danger=2, warn=1."""
    from services.dbcompare_diff import diff_snapshots

    simple = _table(columns=[_col("id", "INT", nullable=False)], pk_columns=["id"])

    src_precios = _table(
        columns=[_col("id", "INT", nullable=False), _col("valor", "DECIMAL(10,2)")],
        pk_columns=["id"],
    )
    tgt_precios = _table(
        columns=[_col("id", "INT", nullable=False), _col("valor", "MONEY")],
        pk_columns=["id"],
    )

    src_auditoria = _table(
        columns=[_col("id", "INT", nullable=False)],
        pk_columns=["id"],
        indexes=[{"name": "IX_AUD", "columns": ["id"], "unique": False}],
    )
    tgt_auditoria = _table(columns=[_col("id", "INT", nullable=False)], pk_columns=["id"], indexes=[])

    src = _snapshot("a", tables={"PRECIOS": src_precios, "AUDITORIA": src_auditoria})
    tgt = _snapshot("b", tables={
        "PRECIOS": tgt_precios,
        "AUDITORIA": tgt_auditoria,
        "LEGADO": simple,
    })

    diff = diff_snapshots(src, tgt)

    assert diff["summary"]["by_severity"] == {"info": 0, "warn": 1, "danger": 2}
    assert diff["summary"]["by_action"] == {"added": 0, "removed": 1, "changed": 2}
