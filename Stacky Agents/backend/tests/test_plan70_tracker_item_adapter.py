"""Plan 70 F1-B — Adapter puro _tracker_item_from_kwargs (GAP-E).

Normaliza las dos firmas usadas por callers ADO (kwargs-style y fields-style)
al dataclass TrackerItem del puerto, SIN tocar el puerto.
"""
from __future__ import annotations

from services.tracker_provider import TrackerItem


def test_kwargs_style_basic():
    from api.tickets import _tracker_item_from_kwargs

    item = _tracker_item_from_kwargs(work_item_type="Task", title="x", description="y")
    assert isinstance(item, TrackerItem)
    assert item.item_type == "Task"
    assert item.title == "x"
    assert item.description_html == "y"
    assert item.parent_id is None


def test_fields_style_with_parent():
    from api.tickets import _tracker_item_from_kwargs

    item = _tracker_item_from_kwargs(
        work_item_type="Task",
        fields={"System.Title": "x", "System.Description": "y"},
        parent_ado_id=42,
    )
    assert item.item_type == "Task"
    assert item.title == "x"
    assert item.description_html == "y"
    assert item.parent_id == "42"


def test_non_standard_fields_preserved():
    from api.tickets import _tracker_item_from_kwargs

    item = _tracker_item_from_kwargs(
        work_item_type="Issue",
        fields={"System.Title": "t", "Custom.Foo": "bar", "System.Tags": "a; b"},
    )
    assert item.title == "t"
    # Los campos no extraídos viajan en .fields
    assert item.fields.get("Custom.Foo") == "bar"
    assert item.fields.get("System.Tags") == "a; b"


def test_missing_description_defaults_to_empty_string():
    from api.tickets import _tracker_item_from_kwargs

    item = _tracker_item_from_kwargs(work_item_type="Task", title="only-title")
    assert item.description_html == ""
    assert item.title == "only-title"


def test_parent_id_as_string_already():
    from api.tickets import _tracker_item_from_kwargs

    item = _tracker_item_from_kwargs(
        work_item_type="Epic", title="t", parent_ado_id="99"
    )
    assert item.parent_id == "99"
