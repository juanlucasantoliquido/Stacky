"""
ddl_test_executor.py — DDL Execution Sandbox.

Executes DDL scripts in a test DB, verifies schema changes, and validates rollback.

Uso:
    from ddl_test_executor import DDLTestExecutor
    executor = DDLTestExecutor(config)
    result = executor.run(ticket_folder, config)
"""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.ddl_test")


@dataclass
class DDLTestCase:
    name: str
    passed: bool
    evidence: str = ""


@dataclass
class DDLTestResult:
    cases: list[DDLTestCase] = field(default_factory=list)

    @property
    def passed(self):
        return all(c.passed for c in self.cases)


class DDLTestExecutor:
    def __init__(self, config: Optional[dict] = None, db_inspector=None):
        self.config = config or {}
        self.db_inspector = db_inspector

    def run(self, ticket_folder: str, config: Optional[dict] = None) -> DDLTestResult:
        cfg = config or self.config
        sql_files = self._find_sql_files(ticket_folder)
        cases = []

        if not sql_files:
            cases.append(DDLTestCase("No SQL files found", True, "Skipped"))
            return DDLTestResult(cases=cases)

        conn = self._get_connection(cfg)
        if conn is None:
            cases.append(DDLTestCase("DB connection", False, "Cannot connect to test DB"))
            return DDLTestResult(cases=cases)

        for sql_file in sql_files:
            try:
                script = sql_file.read_text(encoding="utf-8", errors="replace")
                tables = self._extract_tables_from_sql(script)

                # Capture schema before
                schema_before = self._capture_schema(conn, tables)

                # Execute DDL
                try:
                    self._execute_script(conn, script)
                    cases.append(DDLTestCase(
                        name=f"DDL {sql_file.name} executes without errors",
                        passed=True,
                    ))
                except Exception as e:
                    cases.append(DDLTestCase(
                        name=f"DDL {sql_file.name} executes without errors",
                        passed=False,
                        evidence=str(e)[:300]
                    ))
                    continue

                # Capture schema after
                schema_after = self._capture_schema(conn, tables)

                # Verify schema changed as expected
                if schema_before != schema_after:
                    cases.append(DDLTestCase(
                        name=f"DDL {sql_file.name} modified schema",
                        passed=True,
                        evidence=f"Tables changed: {', '.join(tables)}"
                    ))
                else:
                    cases.append(DDLTestCase(
                        name=f"DDL {sql_file.name} modified schema",
                        passed=False,
                        evidence="No schema changes detected"
                    ))

                # Test rollback
                rollback_file = self._find_rollback(ticket_folder, sql_file)
                if rollback_file:
                    try:
                        rollback_script = rollback_file.read_text(encoding="utf-8")
                        self._execute_script(conn, rollback_script)
                        schema_reverted = self._capture_schema(conn, tables)
                        cases.append(DDLTestCase(
                            name=f"Rollback of {sql_file.name} reverts correctly",
                            passed=(schema_reverted == schema_before),
                            evidence="Schema matches pre-DDL state" if schema_reverted == schema_before
                                else "Schema mismatch after rollback"
                        ))
                    except Exception as e:
                        cases.append(DDLTestCase(
                            name=f"Rollback of {sql_file.name}",
                            passed=False,
                            evidence=str(e)[:300]
                        ))
                else:
                    cases.append(DDLTestCase(
                        name=f"Rollback script for {sql_file.name} exists",
                        passed=False,
                        evidence="ROLLBACK_SCRIPT.sql not found"
                    ))

            except Exception as e:
                cases.append(DDLTestCase(
                    name=f"Processing {sql_file.name}",
                    passed=False,
                    evidence=str(e)[:300]
                ))

        return DDLTestResult(cases=cases)

    def _find_sql_files(self, ticket_folder: str) -> list[Path]:
        folder = Path(ticket_folder)
        return [
            f for f in folder.glob("*.sql")
            if "rollback" not in f.name.lower()
        ]

    def _extract_tables_from_sql(self, sql: str) -> list[str]:
        tables = set()
        for pattern in [
            r"ALTER\s+TABLE\s+\[?(\w+)\]?",
            r"CREATE\s+(?:TABLE|INDEX)\s+\[?(\w+)\]?",
            r"DROP\s+(?:TABLE|INDEX)\s+\[?(\w+)\]?",
        ]:
            for m in re.finditer(pattern, sql, re.IGNORECASE):
                tables.add(m.group(1))
        return list(tables)

    def _find_rollback(self, ticket_folder: str, sql_file: Path) -> Optional[Path]:
        folder = Path(ticket_folder)
        candidates = [
            folder / "ROLLBACK_SCRIPT.sql",
            folder / f"rollback_{sql_file.stem}.sql",
        ]
        for c in candidates:
            if c.exists():
                return c
        return None

    def _get_connection(self, config: dict):
        conn_str = config.get("test_db_connection_string")
        if not conn_str:
            return None
        try:
            import pyodbc
            return pyodbc.connect(conn_str)
        except ImportError:
            logger.error("pyodbc not installed")
            return None
        except Exception as e:
            logger.error("DB connection failed: %s", e)
            return None

    def _execute_script(self, conn, script: str):
        cursor = conn.cursor()
        for statement in self._split_statements(script):
            if statement.strip():
                cursor.execute(statement)
        conn.commit()

    def _split_statements(self, script: str) -> list[str]:
        return re.split(r"\bGO\b", script, flags=re.IGNORECASE | re.MULTILINE)

    def _capture_schema(self, conn, tables: list[str]) -> dict:
        if self.db_inspector:
            return self.db_inspector.capture_schema(tables)
        schema = {}
        cursor = conn.cursor()
        for table in tables:
            try:
                cursor.execute(
                    "SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH "
                    "FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = ?",
                    (table,)
                )
                schema[table] = [
                    {"name": row[0], "type": row[1], "max_len": row[2]}
                    for row in cursor.fetchall()
                ]
            except Exception:
                schema[table] = []
        return schema
