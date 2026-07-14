"""Tests F2 (Plan 125) — flatten_diff: SchemaDiff v1 anidado -> piezas planas."""
from __future__ import annotations

from services import dbcompare_scripts as scripts


def _diff(items):
    return {
        "version": 1,
        "engine": "sqlserver",
        "source": {"alias": "DEV", "snapshot_id": "s1", "content_hash": "h1"},
        "target": {"alias": "TEST", "snapshot_id": "s2", "content_hash": "h2"},
        "items": items,
        "summary": {},
    }


def test_flatten_diff_added_removed_sintetiza_kind():
    diff = _diff(
        [
            {
                "object_type": "table",
                "schema": "dbo",
                "name": "NUEVA",
                "action": "added",
                "severity": "warn",
                "changes": [],
            },
            {
                "object_type": "view",
                "schema": "dbo",
                "name": "V_VIEJA",
                "action": "removed",
                "severity": "warn",
                "changes": [],
            },
        ]
    )

    pieces = scripts.flatten_diff(diff)

    assert pieces == [
        {"kind": "table_added", "object_type": "table", "schema": "dbo", "name": "NUEVA", "detail": {}},
        {"kind": "view_removed", "object_type": "view", "schema": "dbo", "name": "V_VIEJA", "detail": {}},
    ]


def test_flatten_diff_changed_hereda_schema_name_del_item():
    diff = _diff(
        [
            {
                "object_type": "table",
                "schema": "dbo",
                "name": "CLIENTES",
                "action": "changed",
                "severity": "danger",
                "changes": [
                    {"kind": "column_added", "severity": "warn", "detail": {"column": "EMAIL"}},
                    {"kind": "pk_changed", "severity": "danger", "detail": {"columns_source": ["ID"]}},
                ],
            }
        ]
    )

    pieces = scripts.flatten_diff(diff)

    assert len(pieces) == 2
    for p in pieces:
        assert p["schema"] == "dbo"
        assert p["name"] == "CLIENTES"
        assert p["object_type"] == "table"
    assert pieces[0]["kind"] == "column_added"
    assert pieces[0]["detail"] == {"column": "EMAIL"}
    assert pieces[1]["kind"] == "pk_changed"
    assert pieces[1]["detail"] == {"columns_source": ["ID"]}


def test_flatten_diff_orden_preservado():
    diff = _diff(
        [
            {"object_type": "sequence", "schema": "dbo", "name": "SEQ_A", "action": "added", "severity": "info", "changes": []},
            {
                "object_type": "table",
                "schema": "dbo",
                "name": "RBGES",
                "action": "changed",
                "severity": "warn",
                "changes": [
                    {"kind": "index_added", "severity": "warn", "detail": {"name": "IX_1"}},
                    {"kind": "index_removed", "severity": "warn", "detail": {"name": "IX_2"}},
                ],
            },
            {"object_type": "sequence", "schema": "dbo", "name": "SEQ_B", "action": "removed", "severity": "warn", "changes": []},
        ]
    )

    pieces = scripts.flatten_diff(diff)

    assert [p["kind"] for p in pieces] == [
        "sequence_added",
        "index_added",
        "index_removed",
        "sequence_removed",
    ]


def test_flatten_diff_vacio():
    assert scripts.flatten_diff(_diff([])) == []
