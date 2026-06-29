"""Plan 74 F2 — Tests de migrator_core.py (plan_migration, MigrationPlan, MigrationOp).

8 casos.
"""
from unittest.mock import MagicMock, call
import pytest

from services.migrator_core import plan_migration, MigrationOp, MigrationPlan, _TYPE_ORDER


def _make_item(ado_id: str, item_type: str, parent=None):
    return {
        "id": ado_id,
        "title": f"Item {ado_id}",
        "description": "<p>desc</p>",
        "item_type": item_type,
        "parent": parent,
    }


def _make_comment(ado_id: str, comment_id: str):
    return {"id": comment_id, "body": f"comentario {comment_id}"}


def _make_attachment(ado_id: str, attach_id: str):
    return {"id": attach_id, "name": f"file_{attach_id}.txt", "url": "http://example.com/attach"}


def _make_mock_origin(items, comments_map=None, attachments_map=None):
    origin = MagicMock(name="mock_origin")
    origin.fetch_open_items.return_value = items
    origin.fetch_all_comments.side_effect = lambda item_id: (comments_map or {}).get(item_id, [])
    origin.fetch_attachments.side_effect = lambda item_id: (attachments_map or {}).get(item_id, [])
    return origin


def test_plan_migration_counts_correctos():
    """plan_migration con 2 items + 3 comments + 1 attachment → counts correctos."""
    item1 = _make_item("1", "Issue")
    item2 = _make_item("2", "Task")
    origin = _make_mock_origin(
        [item1, item2],
        comments_map={"1": [_make_comment("1", "c1"), _make_comment("1", "c2")],
                      "2": [_make_comment("2", "c3")]},
        attachments_map={"1": [_make_attachment("1", "a1")]},
    )
    dest = MagicMock(name="mock_dest")

    plan = plan_migration(origin, dest, stacky_project="P", existing_map={})

    assert isinstance(plan, MigrationPlan)
    assert plan.counts_by_type.get("Issue", 0) == 1
    assert plan.counts_by_type.get("Task", 0) == 1
    # 2 create_item + 3 post_comment + 1 upload_attachment = 6 ops
    assert len(plan.ops) == 6


def test_item_en_existing_map_skip():
    """Item cuyo ado_id ya está en existing_map → no genera op."""
    item = _make_item("42", "Issue")
    origin = _make_mock_origin([item])
    dest = MagicMock()

    plan = plan_migration(origin, dest, stacky_project="P", existing_map={"42": "iid-99"})
    create_ops = [o for o in plan.ops if o.op_kind == "create_item"]
    assert not create_ops


def test_item_con_parent_lleva_dest_parent_ado_id():
    """Item con parent → la op create_item lleva dest_parent_ado_id (NO hay op link_parent)."""
    epic = _make_item("1", "Epic")
    task = _make_item("2", "Task", parent="1")
    origin = _make_mock_origin([epic, task])
    dest = MagicMock()

    plan = plan_migration(origin, dest, stacky_project="P", existing_map={})

    task_ops = [o for o in plan.ops if o.op_kind == "create_item" and o.ado_id == "2"]
    assert len(task_ops) == 1
    assert task_ops[0].dest_parent_ado_id == "1"
    # No hay ninguna op de tipo link_parent
    assert not any(o.op_kind == "link_parent" for o in plan.ops)


def test_parent_ausente_genera_warning_y_huerfano():
    """Item con parent cuyo ado_id no está en el plan ni en existing_map → warning + huérfano."""
    task = _make_item("2", "Task", parent="999")
    origin = _make_mock_origin([task])
    dest = MagicMock()

    plan = plan_migration(origin, dest, stacky_project="P", existing_map={})

    task_ops = [o for o in plan.ops if o.op_kind == "create_item" and o.ado_id == "2"]
    assert task_ops[0].dest_parent_ado_id == "999"  # se incluye; F4 lo trata como huérfano
    assert any("999" in w or "huérfano" in w.lower() or "orphan" in w.lower()
               for w in plan.warnings)


def test_orden_topologico():
    """Origen con 1 Task (parent=Epic) + 1 Epic → Epic precede a Task en ops."""
    epic = _make_item("1", "Epic")
    task = _make_item("2", "Task", parent="1")
    origin = _make_mock_origin([task, epic])  # orden inverso deliberado
    dest = MagicMock()

    plan = plan_migration(origin, dest, stacky_project="P", existing_map={})
    create_ops = [o for o in plan.ops if o.op_kind == "create_item"]
    types_in_order = [o.ado_type for o in create_ops]
    epic_idx = types_in_order.index("Epic")
    task_idx = types_in_order.index("Task")
    assert epic_idx < task_idx


def test_plan_migration_read_only_destino():
    """mock_dest NUNCA fue llamado por plan_migration."""
    items = [_make_item("1", "Issue")]
    origin = _make_mock_origin(items)
    dest = MagicMock(name="mock_dest")

    plan_migration(origin, dest, stacky_project="P", existing_map={})

    dest.create_item.assert_not_called()
    dest.post_comment.assert_not_called()
    dest.upload_attachment.assert_not_called()
    origin.fetch_open_items.assert_called_once()


def test_counts_by_type_determinista():
    """counts_by_type es determinista (ordenado por tipo alfabético)."""
    items = [_make_item("1", "Epic"), _make_item("2", "Issue"), _make_item("3", "Epic")]
    origin = _make_mock_origin(items)
    dest = MagicMock()

    plan = plan_migration(origin, dest, stacky_project="P", existing_map={})
    keys = list(plan.counts_by_type.keys())
    assert keys == sorted(keys)
    assert plan.counts_by_type["Epic"] == 2
    assert plan.counts_by_type["Issue"] == 1


def test_plan_migration_pura_mismo_output():
    """plan_migration es pura: 2 llamadas con mismo input → mismo plan."""
    items = [_make_item("1", "Issue"), _make_item("2", "Epic")]
    origin1 = _make_mock_origin(items)
    origin2 = _make_mock_origin(items)
    dest = MagicMock()

    plan1 = plan_migration(origin1, dest, stacky_project="P", existing_map={})
    plan2 = plan_migration(origin2, dest, stacky_project="P", existing_map={})

    assert plan1.counts_by_type == plan2.counts_by_type
    assert len(plan1.ops) == len(plan2.ops)
    # Mismo orden
    for o1, o2 in zip(plan1.ops, plan2.ops):
        assert o1.op_kind == o2.op_kind
        assert o1.ado_id == o2.ado_id
