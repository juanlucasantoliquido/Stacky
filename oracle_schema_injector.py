"""
oracle_schema_injector.py — G-03: Inyección Live de Schema Oracle en Prompts.

Consulta el schema de Oracle (columnas, tipos, nullabilidad, constraints)
de las tablas mencionadas en el INC/ARQUITECTURA_SOLUCION del ticket,
y lo inyecta en el prompt del PM/DEV como contexto de base de datos.

Sin ORM — usa cx_Oracle o pyodbc (cx_Oracle preferido para Oracle).
Cachea resultados para evitar re-consultas frecuentes.

Uso:
    from oracle_schema_injector import OracleSchemaInjector
    inj = OracleSchemaInjector(connection_string)
    section = inj.build_schema_section(ticket_folder, ticket_id)
    prompt = base_prompt + section
"""

import json
import logging
import os
import re
import threading
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger("stacky.oracle_schema")

# TTL del cache de schema (en horas)
_CACHE_TTL_HOURS = 4

# Tablas a excluir del análisis (tablas del sistema)
_SYSTEM_TABLE_PREFIXES = {"ALL_", "DBA_", "USER_", "V$", "SYS.", "DUAL"}

# Max tablas a consultar por ticket
_MAX_TABLES_PER_TICKET = 8
_MAX_COLS_PER_TABLE    = 40


class OracleSchemaInjector:
    """
    Extrae el schema Oracle de las tablas relevantes al ticket.
    Usa cache en memoria + disco para evitar consultas repetidas.
    """

    def __init__(self, connection_string: str = "",
                 cache_dir: str = ""):
        self._conn_str  = connection_string
        self._cache_dir = cache_dir or os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "knowledge", "schema_cache"
        )
        os.makedirs(self._cache_dir, exist_ok=True)
        self._mem_cache: dict[str, dict] = {}
        self._lock = threading.RLock()

    # ── API pública ───────────────────────────────────────────────────────

    def build_schema_section(self, ticket_folder: str, ticket_id: str) -> str:
        """
        Extrae tablas del ticket y construye sección Markdown con su schema.
        Retorna string vacío si no hay tablas o no hay conexión.
        """
        tables = self._extract_table_names(ticket_folder)
        if not tables:
            return ""

        schemas = []
        for table in tables[:_MAX_TABLES_PER_TICKET]:
            schema = self._get_table_schema(table)
            if schema:
                schemas.append((table, schema))

        if not schemas:
            return ""

        return self._format_schema_section(schemas)

    def get_table_schema(self, table_name: str) -> dict | None:
        """Retorna el schema de una tabla específica (con cache)."""
        return self._get_table_schema(table_name)

    def invalidate_cache(self, table_name: str = "") -> None:
        """Invalida el cache de una tabla o de todo el schema."""
        with self._lock:
            if table_name:
                self._mem_cache.pop(table_name.upper(), None)
                cache_path = self._get_cache_path(table_name)
                try:
                    os.remove(cache_path)
                except Exception:
                    pass
            else:
                self._mem_cache.clear()

    # ── Internals ─────────────────────────────────────────────────────────

    def _extract_table_names(self, ticket_folder: str) -> list[str]:
        """Extrae nombres de tablas Oracle de los documentos del ticket."""
        tables: set[str] = set()

        for fname in ["INC-*.md", "ANALISIS_TECNICO.md",
                      "ARQUITECTURA_SOLUCION.md", "DEV_COMPLETADO.md"]:
            # Glob para INC-{id}.md
            if "*" in fname:
                try:
                    matches = [f for f in os.listdir(ticket_folder)
                               if f.startswith("INC-") and f.endswith(".md")]
                    files_to_read = [os.path.join(ticket_folder, m) for m in matches]
                except Exception:
                    files_to_read = []
            else:
                fpath = os.path.join(ticket_folder, fname)
                files_to_read = [fpath] if os.path.exists(fpath) else []

            for fpath in files_to_read:
                try:
                    content = Path(fpath).read_text(encoding="utf-8", errors="replace")
                    # Patrones de tablas Oracle:
                    # RST_XXX, RPL_XXX, nombres en mayúsculas de 3+ chars
                    for m in re.finditer(
                        r'\b((?:RST|RPL|RIP|RMB|RMS|RPY|RCT|'
                        r'[A-Z]{2,4})_[A-Z0-9_]{3,30})\b',
                        content
                    ):
                        t = m.group(1).upper()
                        if not any(t.startswith(p) for p in _SYSTEM_TABLE_PREFIXES):
                            tables.add(t)
                    # También buscar en FROM/JOIN clauses
                    for m in re.finditer(
                        r'(?:FROM|JOIN|UPDATE|INSERT\s+INTO|TABLE)\s+([A-Z][A-Z0-9_]{4,30})',
                        content, re.IGNORECASE
                    ):
                        t = m.group(1).upper()
                        if not any(t.startswith(p) for p in _SYSTEM_TABLE_PREFIXES):
                            tables.add(t)
                except Exception:
                    pass

        return list(tables)

    def _get_table_schema(self, table_name: str) -> dict | None:
        """Obtiene schema de tabla con cache multinivel."""
        table_upper = table_name.upper()

        # 1. Cache en memoria
        with self._lock:
            if table_upper in self._mem_cache:
                cached = self._mem_cache[table_upper]
                if self._is_fresh(cached.get("cached_at")):
                    return cached

        # 2. Cache en disco
        disk_cached = self._load_disk_cache(table_upper)
        if disk_cached and self._is_fresh(disk_cached.get("cached_at")):
            with self._lock:
                self._mem_cache[table_upper] = disk_cached
            return disk_cached

        # 3. Consultar Oracle
        schema = self._query_oracle(table_upper)
        if schema:
            schema["cached_at"] = datetime.now().isoformat()
            with self._lock:
                self._mem_cache[table_upper] = schema
            self._save_disk_cache(table_upper, schema)

        return schema

    def _query_oracle(self, table_name: str) -> dict | None:
        """Consulta ALL_TAB_COLUMNS + ALL_CONSTRAINTS en Oracle."""
        if not self._conn_str:
            return None

        try:
            import cx_Oracle  # type: ignore
            conn = cx_Oracle.connect(self._conn_str)
        except ImportError:
            logger.debug("[SCHEMA] cx_Oracle no disponible")
            return None
        except Exception as e:
            logger.warning("[SCHEMA] Error conectando a Oracle: %s", e)
            return None

        try:
            cursor = conn.cursor()

            # Columnas
            cursor.execute("""
                SELECT COLUMN_NAME, DATA_TYPE, DATA_LENGTH, DATA_PRECISION,
                       DATA_SCALE, NULLABLE, DATA_DEFAULT
                FROM   ALL_TAB_COLUMNS
                WHERE  TABLE_NAME = :1
                ORDER  BY COLUMN_ID
            """, [table_name])
            cols_rows = cursor.fetchall()

            if not cols_rows:
                return None

            columns = []
            for row in cols_rows[:_MAX_COLS_PER_TABLE]:
                col_name, dtype, length, prec, scale, nullable, default = row
                type_str = dtype
                if dtype in ("VARCHAR2", "CHAR", "NVARCHAR2"):
                    type_str = f"{dtype}({length})"
                elif dtype == "NUMBER" and prec:
                    type_str = f"NUMBER({prec},{scale or 0})"
                columns.append({
                    "name":     col_name,
                    "type":     type_str,
                    "nullable": nullable == "Y",
                    "default":  str(default).strip() if default else None,
                })

            # Primary keys
            cursor.execute("""
                SELECT cc.COLUMN_NAME
                FROM   ALL_CONSTRAINTS  c
                JOIN   ALL_CONS_COLUMNS cc ON cc.CONSTRAINT_NAME = c.CONSTRAINT_NAME
                                         AND cc.OWNER = c.OWNER
                WHERE  c.TABLE_NAME       = :1
                AND    c.CONSTRAINT_TYPE  = 'P'
                ORDER  BY cc.POSITION
            """, [table_name])
            pks = [r[0] for r in cursor.fetchall()]

            # Foreign keys
            cursor.execute("""
                SELECT cc.COLUMN_NAME, rc.TABLE_NAME
                FROM   ALL_CONSTRAINTS  c
                JOIN   ALL_CONS_COLUMNS cc ON cc.CONSTRAINT_NAME = c.CONSTRAINT_NAME
                JOIN   ALL_CONSTRAINTS  rc ON rc.CONSTRAINT_NAME = c.R_CONSTRAINT_NAME
                WHERE  c.TABLE_NAME      = :1
                AND    c.CONSTRAINT_TYPE = 'R'
            """, [table_name])
            fks = [{"column": r[0], "references": r[1]} for r in cursor.fetchall()]

            cursor.close()
            conn.close()

            return {
                "table":   table_name,
                "columns": columns,
                "pk":      pks,
                "fk":      fks,
            }

        except Exception as e:
            logger.warning("[SCHEMA] Error consultando schema de %s: %s", table_name, e)
            try:
                conn.close()
            except Exception:
                pass
            return None

    @staticmethod
    def _is_fresh(cached_at: str) -> bool:
        if not cached_at:
            return False
        try:
            cached_dt = datetime.fromisoformat(cached_at)
            return datetime.now() - cached_dt < timedelta(hours=_CACHE_TTL_HOURS)
        except Exception:
            return False

    def _get_cache_path(self, table_name: str) -> str:
        safe = re.sub(r'[^\w]', '_', table_name)
        return os.path.join(self._cache_dir, f"{safe}.json")

    def _load_disk_cache(self, table_name: str) -> dict | None:
        try:
            with open(self._get_cache_path(table_name), encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def _save_disk_cache(self, table_name: str, schema: dict) -> None:
        try:
            with open(self._get_cache_path(table_name), "w", encoding="utf-8") as f:
                json.dump(schema, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.debug("[SCHEMA] Error guardando cache de %s: %s", table_name, e)

    @staticmethod
    def _format_schema_section(schemas: list[tuple]) -> str:
        """Formatea el schema como sección Markdown para inyectar en prompts."""
        lines = [
            "",
            "---",
            "",
            "## Schema Oracle — Tablas relevantes al ticket",
            "",
            "_Schema en vivo desde ALL_TAB_COLUMNS. Usar para validar tipos y nulabilidad._",
            "",
        ]
        for table_name, schema in schemas:
            cols = schema.get("columns", [])
            pks  = schema.get("pk", [])
            fks  = schema.get("fk", [])

            lines.append(f"### `{table_name}`")
            lines.append("")
            if pks:
                lines.append(f"**PK:** {', '.join(pks)}")
                lines.append("")

            lines.append("| Columna | Tipo | Nullable | Default |")
            lines.append("|---------|------|----------|---------|")
            for col in cols:
                pk_marker = " 🔑" if col["name"] in pks else ""
                fk_refs   = [f["references"] for f in fks if f["column"] == col["name"]]
                fk_marker = f" → {fk_refs[0]}" if fk_refs else ""
                null_str  = "✓" if col["nullable"] else "✗"
                default   = col.get("default") or ""
                lines.append(
                    f"| `{col['name']}{pk_marker}{fk_marker}` "
                    f"| {col['type']} | {null_str} | {default[:30]} |"
                )
            lines.append("")

        return "\n".join(lines)


# ── Singleton por connection string ───────────────────────────────────────────

_injector_instance: OracleSchemaInjector | None = None


def get_schema_injector(connection_string: str = "") -> OracleSchemaInjector:
    """Retorna (y cachea) una instancia de OracleSchemaInjector."""
    global _injector_instance
    if _injector_instance is None:
        _injector_instance = OracleSchemaInjector(connection_string)
    return _injector_instance
