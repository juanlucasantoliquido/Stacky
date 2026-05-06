"""
sql_query_guard.py — SQL safety validator for the QA UAT Data Request Protocol.

Fase 3 of the QA UAT Agent free-form improvement plan.

Validates SQL strings before executing them against the DB, enforcing:
  1. Only SELECT statements allowed (no DML, DDL, or system-level calls).
  2. Only tables from the whitelisted set can be referenced.
  3. No multi-statement injections (unquoted semicolons).
  4. No dangerous patterns (xp_, sp_ calls, EXEC/EXECUTE, etc.).

Used by data_resolver.py and the orchestrator agent's auto-validation step.

PUBLIC API:
  validate(sql, table_whitelist=None) -> GuardResult
  WHITELISTED_TABLES: frozenset[str]  — the default allowed tables

CLI (for interactive debugging):
  python sql_query_guard.py "SELECT TOP 1 RIDIOMA FROM RIDIOMA WHERE ESTADO = 'A'"
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from typing import Optional

# ── Default table whitelist ───────────────────────────────────────────────────
#
# These are the read-only tables available to RSPACIFICOREAD in the dev DB.
# Kept as a module-level constant so both the agent and data_resolver import
# the same authoritative whitelist.
WHITELISTED_TABLES: frozenset[str] = frozenset({
    "RAGEN",
    "RIDIOMA",
    "RAGTIP",
    "RAGMOT",
    "RAGCAL",
    "RACOMI",
    "RACON",
    "RAGPAR",
    "RASIST",
})

# ── Forbidden SQL keywords (any of these = automatic block) ──────────────────
_FORBIDDEN_KEYWORD_RE = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|TRUNCATE|MERGE|"
    r"EXEC|EXECUTE|SP_EXECUTESQL|XP_CMDSHELL|XP_)\b",
    re.IGNORECASE,
)

# ── Dangerous stored procedure / extended proc patterns ──────────────────────
_DANGEROUS_PROC_RE = re.compile(
    r"\bXP_|SP_CONFIGURE|SP_ADDLOGIN|SP_PASSWORD|OPENROWSET|OPENQUERY\b",
    re.IGNORECASE,
)

# ── Multi-statement separator (unquoted semicolons) ──────────────────────────
# A semicolon inside a string literal ('...;...') is fine.  We strip string
# literals before checking for bare semicolons.
_STRIP_STRINGS_RE = re.compile(r"'[^']*'")

# ── Table reference extraction ────────────────────────────────────────────────
# Captures bare table identifiers after FROM / JOIN / INTO / UPDATE clauses.
# Also handles aliased references: FROM RIDIOMA r
_TABLE_REF_RE = re.compile(
    r"(?:FROM|JOIN|INTO|UPDATE)\s+\[?(\w+)\]?",
    re.IGNORECASE,
)


@dataclass
class GuardResult:
    """Result of validating a SQL string."""
    ok: bool                        # True = no hard errors (may still have warnings)
    safe: bool                      # True = passed all safety checks
    violations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    detected_tables: list[str] = field(default_factory=list)
    non_whitelisted_tables: list[str] = field(default_factory=list)
    clean_sql: str = ""             # SQL stripped of leading/trailing whitespace

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "safe": self.safe,
            "violations": self.violations,
            "warnings": self.warnings,
            "detected_tables": self.detected_tables,
            "non_whitelisted_tables": self.non_whitelisted_tables,
        }


# ── Public API ────────────────────────────────────────────────────────────────

def validate(
    sql: str,
    table_whitelist: Optional[frozenset] = None,
) -> GuardResult:
    """Validate a SQL string for safe execution against the QA read-only DB.

    Args:
        sql:             The SQL string to validate.
        table_whitelist: Set of allowed table names (case-insensitive).
                         Defaults to WHITELISTED_TABLES.

    Returns:
        GuardResult with .safe=True only when all checks pass.
    """
    if table_whitelist is None:
        table_whitelist = WHITELISTED_TABLES
    # Normalize whitelist to uppercase for case-insensitive comparison
    wl_upper: frozenset[str] = frozenset(t.upper() for t in table_whitelist)

    violations: list[str] = []
    warnings: list[str] = []

    clean = sql.strip()
    if not clean:
        return GuardResult(ok=False, safe=False, violations=["Empty SQL string"])

    # ── Check 1: must start with SELECT (after stripping SQL comments) ────────
    no_comments = _strip_sql_comments(clean)
    first_token = no_comments.lstrip().split()[0].upper() if no_comments.strip().split() else ""
    if first_token != "SELECT":
        violations.append(
            f"SQL must start with SELECT. Got: '{first_token}'. "
            f"DML, DDL, and system calls are not allowed."
        )

    # ── Check 2: forbidden keywords ───────────────────────────────────────────
    matches = _FORBIDDEN_KEYWORD_RE.findall(clean)
    if matches:
        unique = list(dict.fromkeys(m.upper() for m in matches))
        violations.append(
            f"Forbidden keywords detected: {', '.join(unique)}. "
            f"Only SELECT is allowed."
        )

    # ── Check 3: dangerous procedure patterns ────────────────────────────────
    if _DANGEROUS_PROC_RE.search(clean):
        violations.append(
            "Dangerous system procedure pattern detected (XP_, SP_CONFIGURE, "
            "OPENROWSET, etc.). Query blocked."
        )

    # ── Check 4: multi-statement injection (bare semicolons) ─────────────────
    stripped_of_strings = _STRIP_STRINGS_RE.sub("''", clean)
    # Check for semicolons that aren't in the middle of a commented-out section
    bare_semis = [i for i, c in enumerate(stripped_of_strings) if c == ";"]
    if bare_semis:
        violations.append(
            f"Bare semicolons detected at positions {bare_semis}. "
            f"Multi-statement queries are not allowed."
        )

    # ── Check 5: table whitelist ──────────────────────────────────────────────
    detected = _extract_tables(clean)
    non_wl = [t for t in detected if t.upper() not in wl_upper]
    if non_wl:
        violations.append(
            f"Non-whitelisted table(s) referenced: {', '.join(non_wl)}. "
            f"Allowed tables: {', '.join(sorted(wl_upper))}."
        )
    if not detected and first_token == "SELECT":
        warnings.append(
            "No table references detected. Verify the query references at least one whitelisted table."
        )

    # ── Check 6: TOP clause recommendation ───────────────────────────────────
    if "TOP" not in clean.upper() and "ROWNUM" not in clean.upper() and first_token == "SELECT":
        warnings.append(
            "No TOP N clause detected. Consider adding TOP 5 to avoid full scans on large tables."
        )

    safe = len(violations) == 0
    return GuardResult(
        ok=safe,
        safe=safe,
        violations=violations,
        warnings=warnings,
        detected_tables=detected,
        non_whitelisted_tables=non_wl,
        clean_sql=clean,
    )


# ── Internal helpers ─────────────────────────────────────────────────────────

def _strip_sql_comments(sql: str) -> str:
    """Remove single-line SQL comments (-- ...) from a SQL string."""
    lines = []
    for line in sql.splitlines():
        idx = line.find("--")
        if idx >= 0:
            line = line[:idx]
        lines.append(line)
    return "\n".join(lines)


def _extract_tables(sql: str) -> list[str]:
    """Extract table names referenced in FROM/JOIN/INTO/UPDATE clauses."""
    # Strip string literals first to avoid matching table names inside strings
    clean = _STRIP_STRINGS_RE.sub("''", sql)
    found = _TABLE_REF_RE.findall(clean)
    # Deduplicate while preserving order
    seen: set[str] = set()
    result: list[str] = []
    for t in found:
        upper = t.upper()
        if upper not in seen:
            seen.add(upper)
            result.append(t.upper())
    return result


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    import json
    if len(sys.argv) < 2:
        sys.stderr.write(
            "Usage: python sql_query_guard.py \"<SQL>\"\n"
            "       python sql_query_guard.py --stdin\n"
        )
        sys.exit(1)

    if sys.argv[1] == "--stdin":
        sql = sys.stdin.read()
    else:
        sql = " ".join(sys.argv[1:])

    result = validate(sql)
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    sys.exit(0 if result.safe else 1)


if __name__ == "__main__":
    main()
