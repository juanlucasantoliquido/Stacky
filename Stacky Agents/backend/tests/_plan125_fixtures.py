"""Helper builders compartidos por los tests de emitters del Plan 125.

NO es un archivo de test (no matchea test_*.py como modulo raiz de pytest,
pero se importa desde los que si lo son). Construye snapshot_obj / tablas /
columnas minimas con la forma congelada en doc 122 F3 / doc 123 F1.
"""
from __future__ import annotations


def make_col(name, type_, nullable=True, default=None, autoincrement=False):
    return {
        "name": name,
        "type": type_,
        "nullable": nullable,
        "default": default,
        "autoincrement": autoincrement,
    }


def make_table(
    columns,
    pk_columns=None,
    pk_name=None,
    foreign_keys=None,
    indexes=None,
    unique_constraints=None,
    check_constraints=None,
):
    return {
        "columns": columns,
        "primary_key": {"name": pk_name, "columns": pk_columns or []},
        "foreign_keys": foreign_keys or [],
        "indexes": indexes or [],
        "unique_constraints": unique_constraints or [],
        "check_constraints": check_constraints or [],
    }


def make_view(definition=None, definition_sha256=None, error=None):
    return {"definition": definition, "definition_sha256": definition_sha256, "error": error}


def make_schema_obj(alias, schema, tables=None, views=None, sequences=None):
    return {
        "alias": alias,
        "schemas": {
            schema: {
                "tables": tables or {},
                "views": views or {},
                "sequences": sequences or [],
            }
        },
    }
