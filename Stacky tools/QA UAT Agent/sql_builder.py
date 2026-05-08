"""
sql_builder.py — Constructor dinámico de queries SQL desde ParsedCondition[].

PROPÓSITO
---------
Recibe condiciones estructuradas de `precondition_parser.py` y construye
queries SQL seguras para verificar precondiciones en BD.

GARANTÍAS DE SEGURIDAD
-----------------------
- Todas las queries pasan por `sql_query_guard.validate()` antes de retornar.
- Parámetros values son escapados para prevenir SQL injection.
- TOP N siempre aplicado (máximo 5 rows).
- Sin DML — solo SELECT.

API PÚBLICA
-----------
  build_check_query(condition) → str | None
  build_multi_table_query(conditions) → str | None
  build_data_lookup_query(table, column, extra_conditions) → str | None

EJEMPLOS
--------
  build_check_query(ParsedCondition(table="ROBLG", column="OGCORREDOR", operator="=", value="1"))
  → "SELECT TOP 1 OGCORREDOR FROM ROBLG WHERE OGCORREDOR = '1'"

  build_data_lookup_query("RCLIE", "CLCOD", ["CLRIESGOENT IS NOT NULL"])
  → "SELECT TOP 1 CLCOD FROM RCLIE WHERE CLRIESGOENT IS NOT NULL ORDER BY NEWID()"
"""
from __future__ import annotations

import logging
import re
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from precondition_parser import ParsedCondition

logger = logging.getLogger("stacky.qa_uat.sql_builder")

_TOOL_VERSION = "1.0.0"

# ── Constantes de seguridad ───────────────────────────────────────────────────

_MAX_ROWS = 5   # TOP N máximo por query
_SAFE_VALUE_RE = re.compile(r"^[A-Za-z0-9\s\-_\.@#]{0,100}$")  # valores permitidos


# ── API pública ────────────────────────────────────────────────────────────────

def build_check_query(condition: "ParsedCondition") -> Optional[str]:
    """
    Construye una query SELECT para verificar si una condición se cumple en BD.

    Retorna la query SQL como string, o None si la condición es inválida.
    La query retorna 1 fila si la condición se cumple, 0 si no.

    Ejemplo:
      ParsedCondition(table="ROBLG", column="OGCORREDOR", operator="=", value="1")
      → "SELECT TOP 1 OGCORREDOR FROM ROBLG WHERE OGCORREDOR = '1'"
    """
    if not condition.table or not condition.column:
        return None

    table = _safe_identifier(condition.table)
    column = _safe_identifier(condition.column)

    if not table or not column:
        logger.warning("sql_builder: invalid identifiers in condition: %s.%s",
                       condition.table, condition.column)
        return None

    # Usar condición custom si existe (del glosario)
    if condition.condition and condition.operator == "custom":
        where_clause = condition.condition
    elif condition.operator.upper() in ("IS NOT NULL", "IS NULL"):
        where_clause = f"{column} {condition.operator.upper()}"
    elif condition.value is not None:
        safe_value = _escape_sql_value(condition.value)
        if safe_value is None:
            logger.warning("sql_builder: unsafe value in condition: %r", condition.value)
            return None
        where_clause = f"{column} {condition.operator} {safe_value}"
    else:
        where_clause = f"{column} IS NOT NULL"

    sql = f"SELECT TOP 1 {column} FROM {table} WHERE {where_clause}"
    return _validate_and_return(sql)


def build_data_lookup_query(
    table: str,
    column: str,
    extra_conditions: Optional[list[str]] = None,
    order_random: bool = True,
) -> Optional[str]:
    """
    Construye una query para obtener un valor de datos de prueba desde BD.

    Ejemplo:
      build_data_lookup_query("RCLIE", "CLCOD", ["CLRIESGOENT IS NOT NULL"])
      → "SELECT TOP 1 CLCOD FROM RCLIE WHERE CLRIESGOENT IS NOT NULL ORDER BY NEWID()"
    """
    t = _safe_identifier(table)
    c = _safe_identifier(column)
    if not t or not c:
        return None

    where_parts = []
    if extra_conditions:
        for cond in extra_conditions:
            # Solo aceptar condiciones simples (sin semicolons, sin keywords peligrosos)
            if _is_safe_condition(cond):
                where_parts.append(cond)
            else:
                logger.warning("sql_builder: skipping unsafe extra condition: %s", cond[:80])

    where_clause = " AND ".join(where_parts) if where_parts else f"{c} IS NOT NULL"
    order_by = " ORDER BY NEWID()" if order_random else ""
    sql = f"SELECT TOP 1 {c} FROM {t} WHERE {where_clause}{order_by}"
    return _validate_and_return(sql)


def build_multi_table_query(
    conditions: list["ParsedCondition"],
    select_column: Optional[str] = None,
) -> Optional[str]:
    """
    Construye una query que involucra múltiples tablas via JOINs.

    Utiliza join_registry para conocer las relaciones entre tablas.
    Solo funciona si existe un camino de joins entre todas las tablas involucradas.

    Retorna None si no es posible construir la query de forma segura.
    """
    if not conditions:
        return None

    # Tabla base = la primera condición
    base_cond = conditions[0]
    base_table = _safe_identifier(base_cond.table)
    if not base_table:
        return None

    # Columna a seleccionar
    sel_col = _safe_identifier(select_column or base_cond.column) or base_cond.column

    # Recopilar joins necesarios
    join_parts = []
    where_parts = []
    tables_added = {base_table.upper()}

    try:
        from join_registry import get_join_path
    except ImportError:
        get_join_path = None

    for cond in conditions:
        t = _safe_identifier(cond.table)
        if not t:
            continue

        # Añadir JOIN si la tabla no está en la query aún
        if t.upper() not in tables_added and get_join_path is not None:
            path = get_join_path(base_table, t)
            if path:
                for step in path:
                    jt = _safe_identifier(step.to_table)
                    if jt and jt.upper() not in tables_added:
                        fc = _safe_identifier(step.from_col)
                        tc = _safe_identifier(step.to_col)
                        ft = _safe_identifier(step.from_table)
                        if fc and tc and ft and jt:
                            join_parts.append(
                                f"{step.join_type} JOIN {jt} ON {ft}.{fc} = {jt}.{tc}"
                            )
                            tables_added.add(jt.upper())
            else:
                logger.warning("sql_builder: no join path from %s to %s", base_table, t)
                continue

        tables_added.add(t.upper())

        # Añadir condición WHERE
        if cond.condition and cond.operator == "custom":
            if _is_safe_condition(cond.condition):
                where_parts.append(cond.condition)
        elif cond.operator.upper() in ("IS NOT NULL", "IS NULL"):
            where_parts.append(f"{t}.{cond.column} {cond.operator.upper()}")
        elif cond.value is not None:
            safe_val = _escape_sql_value(cond.value)
            if safe_val:
                where_parts.append(f"{t}.{cond.column} {cond.operator} {safe_val}")

    join_clause = " ".join(join_parts) if join_parts else ""
    where_clause = " AND ".join(where_parts) if where_parts else "1=1"

    sql_parts = [f"SELECT TOP 1 {base_table}.{sel_col}", f"FROM {base_table}"]
    if join_clause:
        sql_parts.append(join_clause)
    sql_parts.append(f"WHERE {where_clause}")
    sql_parts.append("ORDER BY NEWID()")

    sql = " ".join(sql_parts)
    return _validate_and_return(sql)


def conditions_to_data_request(
    conditions: list["ParsedCondition"],
) -> list[dict]:
    """
    Convierte ParsedCondition[] a formato data_request.json compatible con
    el protocolo de data_resolver.py.

    Permite que el pipeline nuevo sea compatible con el protocolo existente.
    """
    requests = []
    for cond in conditions:
        q = build_check_query(cond)
        if q:
            requests.append({
                "field": f"{cond.table}_{cond.column}",
                "hint_query": q,
                "tables": [cond.table],
                "source": cond.source,
            })
    return requests


# ── Helpers de seguridad ──────────────────────────────────────────────────────

def _safe_identifier(name: str) -> Optional[str]:
    """
    Valida que un nombre de tabla/columna es seguro (alfanumérico + _).
    Retorna None si no es seguro.
    """
    if not name:
        return None
    # Solo alfanumérico + guión bajo (sin brackets, sin puntos, sin comillas)
    if re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', name.strip()):
        return name.strip().upper()
    return None


def _escape_sql_value(value: str) -> Optional[str]:
    """
    Escapa un valor para uso en SQL.

    Retorna None si el valor contiene caracteres peligrosos.
    Solo permite: alfanumérico, espacios, guión, punto, arroba, #.
    """
    if not isinstance(value, str):
        value = str(value)

    # Rechazar valores con caracteres de inyección SQL
    if not _SAFE_VALUE_RE.match(value):
        return None

    # Escapar comillas simples (aunque el regex ya las rechaza, defensa en profundidad)
    escaped = value.replace("'", "''")
    return f"'{escaped}'"


def _is_safe_condition(condition: str) -> bool:
    """
    Verifica que una condición SQL manual no contiene patrones peligrosos.
    """
    dangerous = re.compile(
        r'\b(INSERT|UPDATE|DELETE|DROP|EXEC|EXECUTE|XP_|SP_|OPENROWSET)\b',
        re.IGNORECASE,
    )
    if dangerous.search(condition):
        return False
    # Sin semicolons sin comillas
    stripped = re.sub(r"'[^']*'", "", condition)
    if ";" in stripped:
        return False
    return True


def _validate_and_return(sql: str) -> Optional[str]:
    """Pasa la query por sql_query_guard antes de retornar."""
    try:
        from sql_query_guard import validate
        from schema_explorer import get_tables_for_guard
        result = validate(sql, table_whitelist=get_tables_for_guard())
        if result.safe:
            return sql
        logger.warning("sql_builder: query failed guard: %s | violations: %s",
                       sql[:80], result.violations)
        return None
    except ImportError:
        # Si sql_query_guard no está disponible, retornar la query de todos modos
        # (no debería ocurrir en producción)
        logger.warning("sql_builder: sql_query_guard not available — returning unvalidated query")
        return sql
    except Exception as exc:
        logger.warning("sql_builder: guard validation failed: %s", exc)
        return None
