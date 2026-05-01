"""
rollback_execution_verifier.py — Rollback Execution Verifier.

Executes DDL forward, then rollback, and verifies schema returns to original state.

Uso:
    from rollback_execution_verifier import RollbackExecutionVerifier
    verifier = RollbackExecutionVerifier()
    result = verifier.verify(ticket_folder, conn)
"""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.rollback_verify")


@dataclass
class RollbackTestResult:
    passed: bool
    schema_reverted: bool = True
    data_reverted: bool = True
    schema_diff: str = ""
    issues: list[str] = field(default_factory=list)


class RollbackExecutionVerifier:
    def __init__(self, db_inspector=None):
        self.inspector = db_inspector

    def verify(self, ticket_folder: str, conn) -> RollbackTestResult:
        rollback_file = Path(ticket_folder) / "ROLLBACK_SCRIPT.sql"
        if not rollback_file.exists():
            return RollbackTestResult(
                passed=False,
                issues=["ROLLBACK_SCRIPT.sql doesn't exist — deploy without rollback is blocking"]
            )

        tables = self._extract_affected_tables(ticket_folder)
        if not tables:
            return RollbackTestResult(
                passed=False,
                issues=["No affected tables detected"]
            )

        # Capture schema before
        schema_before = self._capture_schema(conn, tables)
        data_before = self._capture_data_sample(conn, tables)

        # Apply forward scripts
        fwd_scripts = self._find_forward_scripts(ticket_folder)
        issues = []

        for script_path in fwd_scripts:
            try:
                script = script_path.read_text(encoding="utf-8", errors="replace")
                self._execute_sql(conn, script)
            except Exception as e:
                issues.append(f"Forward script {script_path.name} failed: {str(e)[:200]}")
                return RollbackTestResult(passed=False, issues=issues)

        # Execute rollback
        try:
            rollback_sql = rollback_file.read_text(encoding="utf-8", errors="replace")
            self._execute_sql(conn, rollback_sql)
        except Exception as e:
            issues.append(f"Rollback script failed: {str(e)[:200]}")
            return RollbackTestResult(passed=False, issues=issues)

        # Verify schema reverted
        schema_after = self._capture_schema(conn, tables)
        data_after = self._capture_data_sample(conn, tables)

        schema_match = (schema_before == schema_after)
        data_match = (data_before == data_after)

        diff = ""
        if not schema_match:
            diff = self._diff_schemas(schema_before, schema_after)
            issues.append(f"Schema mismatch after rollback: {diff[:300]}")

        if not data_match:
            issues.append("Data mismatch after rollback")

        return RollbackTestResult(
            passed=(schema_match and data_match),
            schema_reverted=schema_match,
            data_reverted=data_match,
            schema_diff=diff,
            issues=issues,
        )

    def _extract_affected_tables(self, ticket_folder: str) -> list[str]:
        folder = Path(ticket_folder)
        tables = set()
        for sql_file in folder.glob("*.sql"):
            if "rollback" in sql_file.name.lower():
                continue
            content = sql_file.read_text(encoding="utf-8", errors="replace")
            for m in re.finditer(r"(?:ALTER|CREATE|DROP)\s+TABLE\s+\[?(\w+)\]?",
                                  content, re.IGNORECASE):
                tables.add(m.group(1))
        return list(tables)

    def _find_forward_scripts(self, ticket_folder: str) -> list[Path]:
        folder = Path(ticket_folder)
        return [
            f for f in sorted(folder.glob("*.sql"))
            if "rollback" not in f.name.lower()
        ]

    def _execute_sql(self, conn, sql: str):
        cursor = conn.cursor()
        for stmt in re.split(r"\bGO\b", sql, flags=re.IGNORECASE | re.MULTILINE):
            stripped = stmt.strip()
            if stripped:
                cursor.execute(stripped)
        conn.commit()

    def _capture_schema(self, conn, tables: list[str]) -> dict:
        if self.inspector:
            return self.inspector.capture_schema(tables)
        schema = {}
        cursor = conn.cursor()
        for table in tables:
            try:
                cursor.execute(
                    "SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH "
                    "FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = ?",
                    (table,)
                )
                schema[table] = sorted(
                    [{"col": r[0], "type": r[1], "len": r[2]} for r in cursor.fetchall()],
                    key=lambda x: x["col"]
                )
            except Exception:
                schema[table] = []
        return schema

    def _capture_data_sample(self, conn, tables: list[str]) -> dict:
        if self.inspector and hasattr(self.inspector, "capture_data_sample"):
            return self.inspector.capture_data_sample(tables)
        return {}

    def _diff_schemas(self, before: dict, after: dict) -> str:
        diffs = []
        all_tables = set(list(before.keys()) + list(after.keys()))
        for table in sorted(all_tables):
            b = before.get(table, [])
            a = after.get(table, [])
            if b != a:
                diffs.append(f"{table}: before={len(b)} cols, after={len(a)} cols")
        return "; ".join(diffs)
