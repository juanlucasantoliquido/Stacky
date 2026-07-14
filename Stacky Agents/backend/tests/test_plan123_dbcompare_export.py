"""Plan 123 F4 — Export Markdown determinista (services/dbcompare_runs.export_markdown).

Ver Stacky Agents/docs/123_PLAN_DB_COMPARE_MOTOR_DIFF_SEVERIDADES_Y_CORRIDAS.md §F4.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")


def _change(kind, severity, detail):
    return {"kind": kind, "severity": severity, "detail": detail}


def _item(object_type, schema, name, action, severity, changes=None):
    return {
        "object_type": object_type, "schema": schema, "name": name,
        "action": action, "severity": severity, "changes": changes or [],
    }


def _diff(items, by_severity, by_action, objects_total, objects_unchanged, parity_score):
    return {
        "version": 1, "engine": "sqlserver",
        "source": {"alias": "ORIGEN", "snapshot_id": "ORIGEN_20260101T000000Z", "content_hash": "aaaa1111bbbb2222"},
        "target": {"alias": "DESTINO", "snapshot_id": "DESTINO_20260101T000000Z", "content_hash": "cccc3333dddd4444"},
        "items": items,
        "summary": {
            "by_severity": by_severity, "by_action": by_action,
            "by_object_type": {"table": len(items), "view": 0, "sequence": 0},
            "objects_total": objects_total, "objects_unchanged": objects_unchanged,
            "parity_score": parity_score,
        },
    }


def _run(diff, run_id="run_20260101T000000Z_ORIGEN_vs_DESTINO"):
    return {
        "run_id": run_id, "source_alias": "ORIGEN", "target_alias": "DESTINO",
        "engine": "sqlserver", "mode": "fresh", "status": "done", "phase": "done",
        "started_at": "2026-01-01T00:00:00Z", "finished_at": "2026-01-01T00:00:05Z",
        "duration_ms": 5000,
        "source_snapshot_id": "ORIGEN_20260101T000000Z",
        "target_snapshot_id": "DESTINO_20260101T000000Z",
        "summary": diff["summary"], "diff": diff, "error": None,
    }


def test_export_contiene_lineas_exactas():
    from services.dbcompare_runs import export_markdown

    items = [
        _item("table", "dbo", "CLIENTES", "changed", "danger", [
            _change("column_type_changed", "danger", {"column": "DIRECCION"}),
            _change("column_removed", "danger", {"column": "FAX"}),
        ]),
        _item("table", "dbo", "LEGACY", "removed", "danger"),
        _item("table", "dbo", "NUEVA", "added", "warn"),
    ]
    diff = _diff(
        items,
        by_severity={"info": 0, "warn": 1, "danger": 2},
        by_action={"added": 1, "removed": 1, "changed": 1},
        objects_total=10, objects_unchanged=7, parity_score=70.0,
    )
    run = _run(diff)

    md = export_markdown(run)
    lines = md.splitlines()

    assert lines[0] == "# Comparación de BD: ORIGEN → DESTINO"
    assert "- **Motor:** sqlserver | **Corrida:** run_20260101T000000Z_ORIGEN_vs_DESTINO" in lines
    assert (
        "- **Snapshots:** origen `ORIGEN_20260101T000000Z` (`aaaa1111`) · "
        "destino `DESTINO_20260101T000000Z` (`cccc3333`)"
    ) in lines
    assert "- **Parity score:** 70.0% (7/10 objetos sin diferencias)" in lines
    assert "| 🔴 danger | 2 |" in lines
    assert "| 🟠 warn | 1 |" in lines
    assert "| 🔵 info | 0 |" in lines
    assert "| added | 1 |" in lines
    assert "| removed | 1 |" in lines
    assert "| changed | 1 |" in lines
    assert "### 🔴 danger" in lines
    assert "- `dbo.CLIENTES` (table, changed): column_type_changed [DIRECCION], column_removed [FAX]" in lines
    assert "- `dbo.LEGACY` (table, removed)" in lines
    assert "### 🟠 warn" in lines
    assert "- `dbo.NUEVA` (table, added)" in lines
    assert "### 🔵 info" not in lines  # sin items info -> sección omitida


def test_export_determinista():
    from services.dbcompare_runs import export_markdown

    items = [_item("table", "dbo", "CLIENTES", "changed", "warn", [
        _change("column_default_changed", "info", {"column": "NOTA"}),
    ])]
    diff = _diff(
        items, by_severity={"info": 0, "warn": 1, "danger": 0},
        by_action={"added": 0, "removed": 0, "changed": 1},
        objects_total=1, objects_unchanged=0, parity_score=0.0,
    )
    run = _run(diff)

    assert export_markdown(run) == export_markdown(run)


def test_export_omite_secciones_vacias():
    from services.dbcompare_runs import export_markdown

    items = [_item("table", "dbo", "NUEVA", "added", "warn")]
    diff = _diff(
        items, by_severity={"info": 0, "warn": 1, "danger": 0},
        by_action={"added": 1, "removed": 0, "changed": 0},
        objects_total=5, objects_unchanged=4, parity_score=80.0,
    )
    run = _run(diff)

    md = export_markdown(run)
    assert "### 🔴 danger" not in md
    assert "### 🔵 info" not in md
    assert "### 🟠 warn" in md
