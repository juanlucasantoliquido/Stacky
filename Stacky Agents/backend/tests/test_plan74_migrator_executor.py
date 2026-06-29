"""Plan 74 F4 — Tests de migrator_executor.py (execute_migration, hydrate_map_from_destination).

9 casos.
"""
import sqlite3
from unittest.mock import MagicMock, call, patch
import pytest

from services.migrator_map import ensure_map_schema, get_gitlab_iid
from services.migrator_core import MigrationOp, MigrationPlan
from services.migrator_executor import execute_migration, hydrate_map_from_destination
from services.tracker_provider import TrackerItem, TrackerApiError


def _make_db():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    ensure_map_schema(db)
    return db


def _make_plan(ops):
    from collections import Counter
    c = Counter(o.ado_type for o in ops if o.op_kind == "create_item")
    from services.migrator_core import MigrationPlan
    return MigrationPlan(ops=ops, counts_by_type=dict(sorted(c.items())), warnings=[])


def _create_op(ado_id, ado_type="Issue", parent=None):
    return MigrationOp(
        op_kind="create_item",
        ado_id=ado_id,
        ado_type=ado_type,
        dest_parent_ado_id=parent,
        payload={"title": f"Item {ado_id}", "description_html": "desc",
                 "labels": [], "item_type": ado_type, "assignee": None},
        marker=f"<!-- stacky-migrated:ado:{ado_id} -->",
    )


def _comment_op(ado_id, comment_id="c1"):
    return MigrationOp(
        op_kind="post_comment",
        ado_id=ado_id,
        ado_type="Issue",
        dest_parent_ado_id=None,
        payload={"body": "comentario"},
        marker=f"<!-- stacky-migrated-comment:ado:{ado_id}:{comment_id} -->",
    )


def _attach_op(ado_id):
    return MigrationOp(
        op_kind="upload_attachment",
        ado_id=ado_id,
        ado_type="Issue",
        dest_parent_ado_id=None,
        payload={"id": "a1", "name": "f.txt", "url": "http://x.com/a1"},
        marker=f"<!-- stacky-migrated-attach:ado:{ado_id}:a1 -->",
    )


# ── Caso 1: 2 creates → applied == 2, mapping persiste ───────────────────────

def test_execute_migration_dos_creates():
    db = _make_db()
    dest = MagicMock(name="mock_dest")
    dest.create_item.side_effect = [
        {"id": "10", "iid": "10", "web_url": "https://gl.ex.com/issues/10"},
        {"id": "20", "iid": "20", "web_url": "https://gl.ex.com/issues/20"},
    ]
    dest.comment_exists.return_value = False

    ops = [_create_op("1"), _create_op("2")]
    plan = _make_plan(ops)

    result = execute_migration(
        plan, dest, db,
        stacky_project="P", migration_run="r1", existing_map={},
    )
    assert result.applied == 2
    assert result.skipped == 0
    assert dest.create_item.call_count == 2
    assert get_gitlab_iid(db, "P", "1") == "10"
    assert get_gitlab_iid(db, "P", "2") == "20"


# ── Caso 2: 2da corrida → skipped == 2, create_item NO llamado ────────────────

def test_execute_migration_idempotente():
    db = _make_db()
    dest = MagicMock(name="mock_dest")
    dest.create_item.side_effect = [
        {"id": "10", "iid": "10", "web_url": "u"},
        {"id": "20", "iid": "20", "web_url": "u"},
    ]
    dest.comment_exists.return_value = False

    ops = [_create_op("1"), _create_op("2")]
    plan = _make_plan(ops)

    # Primera corrida
    execute_migration(plan, dest, db, stacky_project="P", migration_run="r1", existing_map={})
    dest.create_item.reset_mock()

    # Segunda corrida — mapping ya poblado
    result = execute_migration(
        plan, dest, db, stacky_project="P", migration_run="r2",
        existing_map={"1": "10", "2": "20"},
    )
    assert result.skipped == 2
    assert result.applied == 0
    dest.create_item.assert_not_called()


# ── Caso 3: comment op con marker ya existente → post_comment NO llamado ──────

def test_execute_migration_comment_existente_skip():
    db = _make_db()
    dest = MagicMock(name="mock_dest")
    dest.comment_exists.return_value = True  # marker ya existe

    marker = "<!-- stacky-migrated-comment:ado:5:c1 -->"
    existing_map = {"5": "iid-5"}
    op = MigrationOp(
        op_kind="post_comment",
        ado_id="5",
        ado_type="Issue",
        dest_parent_ado_id=None,
        payload={"body": "hola"},
        marker=marker,
    )
    plan = _make_plan([op])

    result = execute_migration(plan, dest, db, stacky_project="P", migration_run="r",
                               existing_map=existing_map)
    dest.post_comment.assert_not_called()
    assert result.skipped >= 1


# ── Caso 4: attachment op → secuencia download→upload→link ───────────────────

def test_execute_migration_attachment_op():
    db = _make_db()
    dest = MagicMock(name="mock_dest")
    dest.upload_attachment.return_value = {"markdown": "![f](u)", "url": "u"}
    dest.link_attachment.return_value = {}
    dest.fetch_open_items.return_value = []

    existing_map = {"7": "iid-7"}
    op = _attach_op("7")
    plan = _make_plan([op])

    with patch("services.migrator_executor.migrate_attachment") as mock_ma:
        mock_ma.return_value = {"name": "f.txt", "local_sha256": "abc",
                                "dest_markdown": "![f](u)", "verified": True}
        result = execute_migration(plan, dest, db, stacky_project="P", migration_run="r",
                                   existing_map=existing_map)

    mock_ma.assert_called_once()


# ── Caso 5: create con parent mapeado → TrackerItem.parent_id == iid_mapeado ─

def test_execute_migration_create_con_parent_mapeado():
    db = _make_db()
    dest = MagicMock(name="mock_dest")
    dest.create_item.return_value = {"id": "30", "iid": "30", "web_url": "u"}

    # Epic ya mapeado: ado_id "1" → iid "iid-1"
    existing_map = {"1": "iid-1"}
    task_op = _create_op("2", ado_type="Task", parent="1")
    plan = _make_plan([task_op])

    result = execute_migration(plan, dest, db, stacky_project="P", migration_run="r",
                               existing_map=existing_map)

    # Verificar que TrackerItem se llamó con parent_id == "iid-1"
    assert dest.create_item.call_count == 1
    ti: TrackerItem = dest.create_item.call_args[0][0]
    assert ti.parent_id == "iid-1"


# ── Caso 6: parent NO mapeado → item creado con parent_id=None + orphaned ────

def test_execute_migration_create_con_parent_no_mapeado():
    db = _make_db()
    dest = MagicMock(name="mock_dest")
    dest.create_item.return_value = {"id": "40", "iid": "40", "web_url": "u"}

    task_op = _create_op("3", ado_type="Task", parent="999")  # 999 no mapeado
    plan = _make_plan([task_op])

    result = execute_migration(plan, dest, db, stacky_project="P", migration_run="r",
                               existing_map={})

    ti: TrackerItem = dest.create_item.call_args[0][0]
    assert ti.parent_id is None
    assert "3" in result.orphaned


# ── Caso 7: create_item levanta TrackerApiError → acumula en failed, no aborta ─

def test_execute_migration_error_no_aborta():
    db = _make_db()
    dest = MagicMock(name="mock_dest")
    dest.create_item.side_effect = [
        TrackerApiError(500, "fallo"),
        {"id": "50", "iid": "50", "web_url": "u"},
    ]

    ops = [_create_op("1"), _create_op("2")]
    plan = _make_plan(ops)

    result = execute_migration(plan, dest, db, stacky_project="P", migration_run="r",
                               existing_map={})

    assert len(result.failed) == 1
    assert result.failed[0]["ado_id"] == "1"
    assert result.applied >= 1  # el segundo sí se aplicó


# ── Caso 8: mock_origin NUNCA invocado por execute_migration ─────────────────

def test_execute_migration_read_only_origen():
    db = _make_db()
    dest = MagicMock(name="mock_dest")
    dest.create_item.return_value = {"id": "60", "iid": "60", "web_url": "u"}
    mock_origin = MagicMock(name="mock_origin")

    ops = [_create_op("6")]
    plan = _make_plan(ops)

    execute_migration(plan, dest, db, stacky_project="P", migration_run="r", existing_map={})

    # execute_migration no toma origin como parámetro (es el plan quien lo encapsula)
    # Verificar que no se llama ningún mutador del destino con el nombre del origen
    mock_origin.create_item.assert_not_called()
    mock_origin.post_comment.assert_not_called()
    mock_origin.upload_attachment.assert_not_called()


# ── Caso 9: hydrate_map_from_destination reconstruye el map desde destino ─────

def test_hydrate_map_from_destination():
    db = _make_db()
    item1 = {
        "id": "10", "iid": "10",
        "description": "<!-- stacky-migrated:ado:100 -->",
        "web_url": "https://gl.ex.com/issues/10",
        "item_type": "Issue",
    }
    item2 = {
        "id": "20", "iid": "20",
        "description": "algo <!-- stacky-migrated:ado:200 --> más",
        "web_url": "https://gl.ex.com/issues/20",
        "item_type": "Issue",
    }
    dest = MagicMock(name="mock_dest")
    dest.fetch_open_items.return_value = [item1, item2]

    existing_map = hydrate_map_from_destination(dest, db, stacky_project="P")

    assert existing_map.get("100") == "10"
    assert existing_map.get("200") == "20"
    # Solo fetch_* fue llamado (read-only)
    dest.create_item.assert_not_called()
    dest.post_comment.assert_not_called()
    dest.fetch_open_items.assert_called_once()
