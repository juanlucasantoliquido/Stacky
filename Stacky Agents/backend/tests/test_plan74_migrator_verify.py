"""Plan 74 F8 — Tests de migrator_verify.py (verify_migration, VerificationResult).

4 casos.
"""
import sqlite3
from unittest.mock import MagicMock
import pytest

from services.migrator_map import ensure_map_schema
from services.migrator_core import MigrationPlan
from services.migrator_verify import verify_migration, VerificationResult


def _make_db():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    ensure_map_schema(db)
    return db


def _make_plan(counts: dict) -> MigrationPlan:
    return MigrationPlan(ops=[], counts_by_type=counts, warnings=[])


def _make_dest(items_by_type: dict):
    """Crea un mock de dest que devuelve items con markers según tipo."""
    dest = MagicMock(name="mock_dest")
    all_items = []
    for item_type, count in items_by_type.items():
        for i in range(count):
            all_items.append({
                "id": str(i),
                "iid": str(i),
                "description": f"<!-- stacky-migrated:ado:{item_type}_{i} -->",
                "item_type": item_type,
                "web_url": f"https://gl.ex.com/{i}",
                "labels": [f"type::{item_type}"],
            })
    dest.fetch_open_items.return_value = all_items
    return dest


def test_verify_migration_passed_todo_ok():
    """expected = {Epic:2, Issue:3}, actual = {Epic:2, Issue:3} → passed=True."""
    db = _make_db()
    dest = _make_dest({"Epic": 2, "Issue": 3})
    plan = _make_plan({"Epic": 2, "Issue": 3})

    result = verify_migration(plan, dest, stacky_project="P", db=db)
    assert result.passed is True
    assert not result.needs_review


def test_verify_migration_gap_epic():
    """actual = {Epic:1, Issue:3} (falta 1 epic) → passed=False, needs_review=['Epic']."""
    db = _make_db()
    dest = _make_dest({"Epic": 1, "Issue": 3})
    plan = _make_plan({"Epic": 2, "Issue": 3})

    result = verify_migration(plan, dest, stacky_project="P", db=db)
    assert result.passed is False
    assert "Epic" in result.needs_review
    assert result.gap_by_type["Epic"] == 1


def test_verify_migration_tipo_extra_no_rompe():
    """actual con tipo extra no esperado → no rompe, gap_by_type lo marca negativo."""
    db = _make_db()
    dest = _make_dest({"Epic": 2, "Issue": 3, "Task": 1})  # Task no esperado
    plan = _make_plan({"Epic": 2, "Issue": 3})

    result = verify_migration(plan, dest, stacky_project="P", db=db)
    # No debe lanzar; Task extra → gap negativo (más de lo esperado)
    assert "Task" in result.gap_by_type
    assert result.gap_by_type["Task"] <= 0


def test_verify_migration_read_only_destino():
    """verify_migration no escribe en destino — solo fetch_* llamados."""
    db = _make_db()
    dest = _make_dest({"Issue": 1})
    plan = _make_plan({"Issue": 1})

    verify_migration(plan, dest, stacky_project="P", db=db)

    dest.create_item.assert_not_called()
    dest.post_comment.assert_not_called()
    dest.upload_attachment.assert_not_called()
    dest.fetch_open_items.assert_called()
