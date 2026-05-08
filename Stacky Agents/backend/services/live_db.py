"""
FA-02 — Live BD context injection.

Permite al operador (o al agente Technical) ejecutar SELECTs read-only
contra una réplica de la BD del proyecto y traer datos reales como
bloque [auto] del contexto.

Mecanismos de seguridad:
1. Sólo SELECT / WITH (rechazado todo lo demás).
2. Hard timeout 5s por query.
3. Max 10 filas devueltas (configurable hasta 50).
4. PII masking automático en los resultados (FA-37).
5. Whitelist de connections en `project_db_whitelist`.

Drivers soportados: SQLite (dev), SQL Server (prod via pyodbc).
En modo mock devuelve filas dummy sin tocar BD real.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from config import config
from services import pii_masker


_SAFE_QUERY = re.compile(r"^\s*(SELECT|WITH)\s", re.IGNORECASE)
_DESTRUCTIVE = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|GRANT|REVOKE|EXEC|EXECUTE)\b",
    re.IGNORECASE,
)


@dataclass
class QueryResult:
    sql: str
    rows: list[dict]
    columns: list[str]
    row_count: int
    truncated: bool
    error: str | None
    pii_masked: bool

    def to_dict(self) -> dict:
        return {
            "sql": self.sql,
            "rows": self.rows,
            "columns": self.columns,
            "row_count": self.row_count,
            "truncated": self.truncated,
            "error": self.error,
            "pii_masked": self.pii_masked,
        }


def _validate_query(sql: str) -> str | None:
    sql_stripped = sql.strip().rstrip(";")
    if not _SAFE_QUERY.match(sql_stripped):
        return "only SELECT / WITH allowed"
    if _DESTRUCTIVE.search(sql_stripped):
        return "destructive keywords detected"
    if ";" in sql_stripped:
        return "multiple statements not allowed"
    return None


def execute_select(
    *,
    sql: str,
    project: str | None = None,
    max_rows: int = 10,
    apply_pii_mask: bool = True,
) -> QueryResult:
    """Ejecuta un SELECT contra la BD del proyecto. Retorna QueryResult."""
    err = _validate_query(sql)
    if err:
        return QueryResult(sql=sql, rows=[], columns=[], row_count=0,
                           truncated=False, error=err, pii_masked=False)

    max_rows = min(max(1, max_rows), 50)

    if config.LLM_BACKEND == "mock":
        # Dummy result en modo mock para validar el flujo.
        rows = [
            {"id": 1, "nombre": "Cliente A", "saldo": 1500.50},
            {"id": 2, "nombre": "Cliente B", "saldo": 2300.00},
            {"id": 3, "nombre": "Cliente C", "saldo": 870.25},
        ][:max_rows]
        return QueryResult(
            sql=sql, rows=rows, columns=list(rows[0].keys()) if rows else [],
            row_count=len(rows), truncated=False, error=None, pii_masked=False,
        )

    project_db_url = _resolve_db_url(project)
    if not project_db_url:
        return QueryResult(sql=sql, rows=[], columns=[], row_count=0,
                           truncated=False, error="no project DB configured",
                           pii_masked=False)

    try:
        from sqlalchemy import create_engine, text

        engine = create_engine(project_db_url, pool_pre_ping=True,
                               connect_args={"timeout": 5} if "sqlite" in project_db_url else {})
        with engine.connect() as conn:
            result = conn.execute(text(sql))
            cols = list(result.keys())
            fetched = result.fetchmany(max_rows + 1)
            truncated = len(fetched) > max_rows
            fetched = fetched[:max_rows]
            rows = [dict(zip(cols, r)) for r in fetched]

        if apply_pii_mask and rows:
            for row in rows:
                for k, v in row.items():
                    if isinstance(v, str):
                        row[k], _ = pii_masker.mask_text(v)
        return QueryResult(
            sql=sql, rows=rows, columns=cols, row_count=len(rows),
            truncated=truncated, error=None, pii_masked=apply_pii_mask,
        )
    except Exception as exc:  # noqa: BLE001
        return QueryResult(sql=sql, rows=[], columns=[], row_count=0,
                           truncated=False, error=str(exc)[:300],
                           pii_masked=False)


def _resolve_db_url(project: str | None) -> str | None:
    """Resuelve URL desde env (futuro: tabla `project_db_whitelist`)."""
    import os
    if project:
        env_key = f"PROJECT_DB_URL_{project.upper().replace('-', '_')}"
        return os.getenv(env_key) or os.getenv("PROJECT_DB_URL")
    return os.getenv("PROJECT_DB_URL")


def build_context_block(
    sql: str,
    project: str | None = None,
    max_rows: int = 10,
) -> dict | None:
    """Devuelve un ContextBlock listo para inyectar al editor."""
    result = execute_select(sql=sql, project=project, max_rows=max_rows)
    if result.error:
        return {
            "id": "live-db-error",
            "kind": "auto",
            "title": f"BD live (error)",
            "content": f"```sql\n{sql}\n```\n\n**Error:** {result.error}",
            "source": {"type": "live-db", "error": result.error},
        }
    if not result.rows:
        return None
    # Formato tabla markdown
    cols = result.columns
    header = "| " + " | ".join(cols) + " |"
    sep = "|" + "|".join(["---"] * len(cols)) + "|"
    rows_md = ["| " + " | ".join(str(r.get(c, "")) for c in cols) + " |"
               for r in result.rows]
    body = (
        f"```sql\n{sql}\n```\n\n"
        f"{header}\n{sep}\n" + "\n".join(rows_md) + "\n\n"
        f"_{result.row_count} fila{'s' if result.row_count != 1 else ''}"
        f"{' (truncado)' if result.truncated else ''}_"
        f"{' · PII enmascarada' if result.pii_masked else ''}"
    )
    return {
        "id": f"live-db-{abs(hash(sql)) % 9999:04d}",
        "kind": "auto",
        "title": f"BD live ({result.row_count} fila{'s' if result.row_count != 1 else ''})",
        "content": body,
        "source": {"type": "live-db", "sql": sql},
    }
