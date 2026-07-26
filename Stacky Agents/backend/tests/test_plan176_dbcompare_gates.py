"""Plan 176 F4 — Gates de precondición derivadas del diff (parte pura).

El replay de Pacífico hacía a mano, en PowerShell, lo obvio: contar NULLs antes
de poner un NOT NULL, buscar duplicados antes de crear una PK. Si no lo hacías,
el ALTER fallaba a mitad de la migración. Esto lo deriva del propio diff.

Nada acá ejecuta SQL: derivar y exportar son puros. Ejecutar es otra cosa y solo
pasa cuando el operador aprieta el botón.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

from services import dbcompare_gates as G  # noqa: E402


def _diff(items: list, engine: str = "sqlserver") -> dict:
    return {"version": 1, "engine": engine, "items": items}


def _item(kind: str, detail: dict, name: str = "CLIENTES") -> dict:
    return {
        "object_type": "table", "schema": "dbo", "name": name,
        "action": "changed", "severity": "danger",
        "changes": [{"kind": kind, "severity": "danger", "detail": detail}],
    }


# ---------------------------------------------------------------------------
# Anti-drift: los nombres de kind no se inventan
# ---------------------------------------------------------------------------

def test_gate_kinds_existen_en_kind_severity():
    """BLOQUEANTE: un kind mal copiado deriva cero gates y nadie se entera."""
    from services.dbcompare_diff import _KIND_SEVERITY

    desconocidos = [k for k in G._GATE_RULES if k not in _KIND_SEVERITY]

    assert not desconocidos, f"kinds inexistentes en el diff real: {desconocidos}"


def test_tabla_de_reglas_es_cerrada():
    assert set(G._GATE_RULES.values()) <= {"null_count", "duplicate_key", "rowcount"}


# ---------------------------------------------------------------------------
# Derivación
# ---------------------------------------------------------------------------

def test_nullability_deriva_gate_null_count():
    gates = G.derive_gates(_diff([
        _item("column_nullable_tightened", {"column": "RUT"})]), "TEST")

    assert len(gates) == 1
    g = gates[0]
    assert g["kind"] == "null_count"
    assert g["check"] == "expect_zero"
    assert g["sql"] == 'SELECT COUNT(*) FROM [dbo].[CLIENTES] WHERE [RUT] IS NULL'
    assert g["target_alias"] == "TEST"
    assert g["item_key"] == "table:dbo.CLIENTES"


def test_pk_deriva_duplicate_key_con_alias_en_sqlserver():
    gates = G.derive_gates(_diff([
        _item("pk_changed", {"source": ["ID"], "target": ["ID", "TIPO"]})]), "TEST")

    assert gates[0]["kind"] == "duplicate_key"
    assert gates[0]["sql"] == (
        'SELECT COUNT(*) FROM (SELECT [ID], [TIPO] FROM [dbo].[CLIENTES] '
        'GROUP BY [ID], [TIPO] HAVING COUNT(*) > 1) t'
    )


def test_pk_en_oracle_omite_el_alias():
    """Oracle no acepta alias de subconsulta con AS ni suelto en este contexto."""
    gates = G.derive_gates(_diff([
        _item("pk_changed", {"source": [], "target": ["ID"]})], engine="oracle"), "TEST")

    assert gates[0]["sql"].endswith("HAVING COUNT(*) > 1)")
    assert not gates[0]["sql"].endswith(") t")


def test_unique_added_deriva_duplicate_key():
    gates = G.derive_gates(_diff([
        _item("unique_added", {"source": None, "target": {"columns": ["EMAIL"]}})]), "TEST")

    assert gates[0]["kind"] == "duplicate_key"
    assert "[EMAIL]" in gates[0]["sql"]


def test_table_removed_deriva_info_rowcount():
    """Cuántas filas se van a perder es información, no un fallo."""
    gates = G.derive_gates(_diff([{
        "object_type": "table", "schema": "dbo", "name": "VIEJA",
        "action": "removed", "severity": "danger", "changes": [],
    }]), "TEST")

    assert gates[0]["kind"] == "rowcount"
    assert gates[0]["check"] == "info_rowcount"
    assert gates[0]["sql"] == 'SELECT COUNT(*) FROM [dbo].[VIEJA]'


def test_kind_no_listado_no_deriva_gate():
    assert G.derive_gates(_diff([_item("column_default_changed", {"column": "X"})]), "TEST") == []


def test_pk_sin_columnas_destino_no_deriva():
    """Sin columnas no hay consulta posible: mejor ninguna gate que una rota."""
    assert G.derive_gates(_diff([_item("pk_changed", {"source": ["ID"], "target": []})]),
                          "TEST") == []


def test_derivacion_determinista():
    diff = _diff([
        _item("column_nullable_tightened", {"column": "A"}),
        _item("pk_changed", {"source": [], "target": ["ID"]}, name="OTRA"),
    ])

    assert G.derive_gates(diff, "TEST") == G.derive_gates(diff, "TEST")


def test_gate_ids_son_estables_y_ordenados():
    gates = G.derive_gates(_diff([
        _item("column_nullable_tightened", {"column": "A"}),
        _item("column_nullable_tightened", {"column": "B"}, name="OTRA"),
    ]), "TEST")

    assert [g["gate_id"] for g in gates] == [
        "g001_null_count_dbo.CLIENTES", "g002_null_count_dbo.OTRA"]


def test_identificadores_siempre_citados():
    """Un nombre con espacio o palabra reservada rompe el SQL si no se cita."""
    gates = G.derive_gates(_diff([{
        "object_type": "table", "schema": "dbo", "name": "ORDER",
        "action": "changed", "severity": "danger",
        "changes": [{"kind": "column_nullable_tightened",
                     "severity": "danger", "detail": {"column": "GROUP"}}],
    }]), "TEST")

    assert "[ORDER]" in gates[0]["sql"] and "[GROUP]" in gates[0]["sql"]


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def test_export_sql_determinista_y_comentado():
    diff = _diff([
        _item("column_nullable_tightened", {"column": "RUT"}),
        _item("pk_changed", {"source": [], "target": ["ID"]}, name="OTRA"),
    ])

    sql = G.gates_export_sql(diff, "TEST", "sqlserver")

    assert sql == G.gates_export_sql(diff, "TEST", "sqlserver")
    assert "-- GATE g001_null_count_dbo.CLIENTES" in sql
    assert "-- esperado: 0" in sql
    assert "SELECT COUNT(*)" in sql


def test_export_sin_gates_lo_dice():
    sql = G.gates_export_sql(_diff([]), "TEST", "sqlserver")

    assert "Sin precondiciones" in sql


def test_export_solo_lleva_selects():
    """El archivo que el operador se lleva no puede traer nada que mute."""
    diff = _diff([_item("column_nullable_tightened", {"column": "RUT"})])

    sql = G.gates_export_sql(diff, "TEST", "sqlserver").upper()

    for verbo in ("INSERT ", "UPDATE ", "DELETE ", "ALTER ", "DROP "):
        assert verbo not in sql, verbo


def test_derivacion_no_ejecuta_sql():
    """Derivar y exportar son puros: la ejecución es otra fase y otro permiso.

    Se mira por AST el cuerpo de esas dos funciones (y solo esas), no un corte
    textual del archivo: el helper de ejecución vive en el mismo módulo y un
    split por texto lo metería del lado equivocado.
    """
    import ast

    arbol = ast.parse((ROOT / "services" / "dbcompare_gates.py").read_text(encoding="utf-8"))
    puras = {"derive_gates", "gates_export_sql"}
    nodos = [n for n in arbol.body
             if isinstance(n, ast.FunctionDef) and n.name in puras]

    assert len(nodos) == len(puras), "faltan las funciones puras"
    for nodo in nodos:
        cuerpo = ast.dump(nodo)
        for prohibido in ("open_engine", "connect", "execute", "session_scope"):
            assert prohibido not in cuerpo, \
                f"{nodo.name} no puede tocar la base ({prohibido})"
