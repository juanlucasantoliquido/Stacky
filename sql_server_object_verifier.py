"""
sql_server_object_verifier.py — SQL Server Identity, Trigger & Linked Server Verification.

Checks IDENTITY columns, trigger state, and linked server connectivity.

Uso:
    from sql_server_object_verifier import SQLServerObjectVerifier
    verifier = SQLServerObjectVerifier()
    cases = verifier.verify(ticket_folder, conn)
"""

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.sql_objects")


@dataclass
class SQLServerObjectTestCase:
    name: str
    passed: bool
    evidence: str = ""


class SQLServerObjectVerifier:
    def verify(self, ticket_folder: str, conn) -> list[SQLServerObjectTestCase]:
        cases = []
        sql_files = list(Path(ticket_folder).glob("**/*.sql"))

        if not sql_files:
            return cases

        for sql_file in sql_files:
            try:
                content = sql_file.read_text(encoding="utf-8", errors="replace").upper()
            except Exception:
                continue

            # 1. IDENTITY columns
            insert_tables = set(re.findall(r"INSERT\s+(?:INTO\s+)?\[?(\w+)\]?", content))
            for table in insert_tables:
                try:
                    cursor = conn.cursor()
                    cursor.execute(
                        f"SELECT IDENT_CURRENT('{table}')"
                    )
                    row = cursor.fetchone()
                    if row and row[0] is not None:
                        ident_val = row[0]
                        cases.append(SQLServerObjectTestCase(
                            name=f"IDENTITY in {table} has valid value",
                            passed=(ident_val >= 0),
                            evidence=f"IDENT_CURRENT={ident_val}"
                        ))
                except Exception:
                    pass  # table may not have identity

            # 2. Triggers
            all_tables = set(re.findall(
                r"(?:INSERT|UPDATE|DELETE)\s+(?:INTO\s+|FROM\s+)?\[?(\w+)\]?",
                content
            ))
            for table in all_tables:
                try:
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT t.name, t.is_disabled "
                        "FROM sys.triggers t "
                        "INNER JOIN sys.tables tb ON t.parent_id = tb.object_id "
                        f"WHERE tb.name = '{table}'"
                    )
                    triggers = cursor.fetchall()
                    if triggers:
                        disabled = [t[0] for t in triggers if t[1] == 1]
                        if disabled:
                            cases.append(SQLServerObjectTestCase(
                                name=f"Disabled triggers on {table}",
                                passed=False,
                                evidence=f"Disabled: {', '.join(disabled)}"
                            ))
                        else:
                            cases.append(SQLServerObjectTestCase(
                                name=f"Triggers enabled on {table}",
                                passed=True,
                                evidence=f"{len(triggers)} trigger(s) active"
                            ))
                except Exception:
                    pass

            # 3. Linked Servers
            linked_servers = set(re.findall(r"\[(\w+)\]\.\.\.", content))
            for srv in linked_servers:
                try:
                    cursor = conn.cursor()
                    cursor.execute(f"EXEC sp_testlinkedserver @servername = N'{srv}'")
                    cases.append(SQLServerObjectTestCase(
                        name=f"Linked Server {srv} responds",
                        passed=True,
                    ))
                except Exception as e:
                    cases.append(SQLServerObjectTestCase(
                        name=f"Linked Server {srv} responds",
                        passed=False,
                        evidence=str(e)[:200]
                    ))

        return cases
