"""Tests F4 (Plan 125): orden seguro por FKs para creates/drops del bundle."""
from __future__ import annotations

from services import dbcompare_scripts as scripts
from tests._plan125_fixtures import make_schema_obj, make_table


def _piece(schema, name):
    return {"action": "table_added", "object_type": "table", "schema": schema, "name": name, "sql": "x", "destructive": False, "modifies_table": False}


def _fk(name, referred_table, referred_schema="dbo"):
    return {"name": name, "columns": ["REF_ID"], "referred_schema": referred_schema, "referred_table": referred_table, "referred_columns": ["ID"]}


def test_create_padre_antes_que_hija():
    schema_obj = make_schema_obj(
        "DEV",
        "dbo",
        tables={
            "HIJA": make_table(columns=[], foreign_keys=[_fk("FK_HIJA_PADRE", "PADRE")]),
            "PADRE": make_table(columns=[]),
        },
    )
    pieces = [_piece("dbo", "HIJA"), _piece("dbo", "PADRE")]  # orden de entrada intencionalmente al reves

    ordered, cycle, warning = scripts.order_table_pieces(pieces, schema_obj, "create")

    assert [p["name"] for p in ordered] == ["PADRE", "HIJA"]
    assert cycle == []
    assert warning is None


def test_drop_hija_antes_que_padre():
    schema_obj = make_schema_obj(
        "TEST",
        "dbo",
        tables={
            "HIJA": make_table(columns=[], foreign_keys=[_fk("FK_HIJA_PADRE", "PADRE")]),
            "PADRE": make_table(columns=[]),
        },
    )
    pieces = [_piece("dbo", "PADRE"), _piece("dbo", "HIJA")]

    ordered, cycle, warning = scripts.order_table_pieces(pieces, schema_obj, "drop")

    assert [p["name"] for p in ordered] == ["HIJA", "PADRE"]
    assert cycle == []
    assert warning is None


def test_cadena_tres_niveles():
    schema_obj = make_schema_obj(
        "DEV",
        "dbo",
        tables={
            "C": make_table(columns=[], foreign_keys=[_fk("FK_C_B", "B")]),
            "B": make_table(columns=[], foreign_keys=[_fk("FK_B_A", "A")]),
            "A": make_table(columns=[]),
        },
    )
    pieces = [_piece("dbo", "C"), _piece("dbo", "A"), _piece("dbo", "B")]

    ordered, cycle, warning = scripts.order_table_pieces(pieces, schema_obj, "create")

    assert [p["name"] for p in ordered] == ["A", "B", "C"]
    assert cycle == []


def test_empates_por_nombre_asc():
    schema_obj = make_schema_obj("DEV", "dbo", tables={"ZETA": make_table(columns=[]), "ALFA": make_table(columns=[]), "BETA": make_table(columns=[])})
    pieces = [_piece("dbo", "ZETA"), _piece("dbo", "ALFA"), _piece("dbo", "BETA")]

    ordered, cycle, warning = scripts.order_table_pieces(pieces, schema_obj, "create")

    assert [p["name"] for p in ordered] == ["ALFA", "BETA", "ZETA"]


def test_ciclo_cae_a_alfabetico_con_warning():
    schema_obj = make_schema_obj(
        "DEV",
        "dbo",
        tables={
            "TABLA_B": make_table(columns=[], foreign_keys=[_fk("FK_B_A", "TABLA_A")]),
            "TABLA_A": make_table(columns=[], foreign_keys=[_fk("FK_A_B", "TABLA_B")]),
        },
    )
    pieces = [_piece("dbo", "TABLA_B"), _piece("dbo", "TABLA_A")]

    ordered, cycle, warning = scripts.order_table_pieces(pieces, schema_obj, "create")

    assert [p["name"] for p in ordered] == ["TABLA_A", "TABLA_B"]
    assert cycle == ["dbo.TABLA_A", "dbo.TABLA_B"]
    assert warning == "⚠ Ciclo de FKs detectado entre: dbo.TABLA_A, dbo.TABLA_B; revisá el orden manualmente."


def test_fk_hacia_tabla_fuera_del_conjunto_se_ignora():
    schema_obj = make_schema_obj(
        "DEV",
        "dbo",
        tables={"HIJA": make_table(columns=[], foreign_keys=[_fk("FK_HIJA_EXTERNA", "TABLA_YA_EXISTENTE")])},
    )
    pieces = [_piece("dbo", "HIJA")]

    ordered, cycle, warning = scripts.order_table_pieces(pieces, schema_obj, "create")

    assert [p["name"] for p in ordered] == ["HIJA"]
    assert cycle == []
