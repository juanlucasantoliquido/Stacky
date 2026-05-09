"""
sql_safety_validator.py — SQL Seed Safety Validator (Sprint 10).

Validates a SQL seed proposal script against a strict set of P0 safety rules
before it is surfaced to the human operator for review.

If ANY P0 rule is violated, the result is: safe=False, risk_level="critical".
A "safe" result still requires human approval — this module is a pre-filter,
not an authorisation gate.

P0 BLOCKING RULES (safe=False, risk_level=critical if any triggered):
  1.  NO_DROP_ALLOWED             — script contains DROP keyword
  2.  NO_TRUNCATE_ALLOWED         — script contains TRUNCATE keyword
  3.  DELETE_WITHOUT_SEED_MARKER  — DELETE without WHERE containing SeedRunId or CreatedBy='QA_UAT_AGENT'
  4.  UPDATE_WITHOUT_SEED_MARKER  — UPDATE without WHERE containing SeedRunId or CreatedBy='QA_UAT_AGENT'
  5.  MISSING_BEGIN_TRANSACTION   — no BEGIN TRANSACTION present
  6.  MISSING_ROLLBACK_DEFAULT    — ROLLBACK TRANSACTION not present as active (non-commented) statement
  7.  ACTIVE_COMMIT               — COMMIT TRANSACTION present as active (non-commented) statement
  8.  PROD_REFERENCE_IN_LITERALS  — literal production server/db names in string constants
  9.  MISSING_VERIFICATION_SELECT — no SELECT after the INSERT block
  10. MISSING_SEED_RUN_ID         — @SeedRunId variable not declared
  11. NO_ALTER_ALLOWED            — script contains ALTER statement
  12. NO_DISABLE_TRIGGER          — script contains DISABLE TRIGGER
  13. NO_DROP_CONSTRAINT          — script contains DROP CONSTRAINT

APPROVED OUTPUT:
  {
      "safe": true,
      "risk_level": "low",
      "requires_human_approval": true,
      "checks": {
          "transaction_present": true,
          "rollback_default": true,
          "prod_guard_present": true,
          "seed_run_id_present": true,
          "verification_select_present": true,
          "dangerous_keywords": []
      }
  }

BLOCKED OUTPUT:
  {
      "safe": false,
      "risk_level": "critical",
      "blocking_findings": [
          {"rule": "NO_DROP_ALLOWED", "detail": "El script contiene DROP TABLE"}
      ]
  }

PUBLIC API:
  validate(sql_text: str, source: str = "") -> SqlSafetyResult
  SqlSafetyResult.to_dict() -> dict

EVENT EMITTED:
  sql_seed_safety_result
  fields: script_sha256, safe, risk_level, requires_human_approval, blocking_findings

USAGE:
  from sql_safety_validator import validate
  result = validate(my_sql_script, source="seed:RF-007-CA-01")
  if not result.safe:
      raise ValueError("Seed script failed safety validation")
"""
from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import asdict, dataclass, field
from typing import List, Optional

logger = logging.getLogger("stacky.qa_uat.sql_safety_validator")

_TOOL_VERSION = "1.0.0"
_SCHEMA_VERSION = "sql_safety_result/1.0"

# ── Dangerous keyword patterns ─────────────────────────────────────────────────
# Each tuple: (rule_name, regex, detail_template)
# Patterns operate on the ACTIVE (non-commented) lines only — see _active_lines().

_DANGEROUS_KEYWORD_RULES: list[tuple[str, re.Pattern, str]] = [
    (
        "NO_DROP_ALLOWED",
        re.compile(r"\bDROP\b", re.IGNORECASE),
        "El script contiene DROP (DROP TABLE, DROP INDEX, etc.)",
    ),
    (
        "NO_TRUNCATE_ALLOWED",
        re.compile(r"\bTRUNCATE\b", re.IGNORECASE),
        "El script contiene TRUNCATE",
    ),
    (
        "NO_ALTER_ALLOWED",
        re.compile(r"\bALTER\b", re.IGNORECASE),
        "El script contiene ALTER",
    ),
    (
        "NO_DISABLE_TRIGGER",
        re.compile(r"\bDISABLE\s+TRIGGER\b", re.IGNORECASE),
        "El script contiene DISABLE TRIGGER",
    ),
    (
        "NO_DROP_CONSTRAINT",
        re.compile(r"\bDROP\s+CONSTRAINT\b", re.IGNORECASE),
        "El script contiene DROP CONSTRAINT",
    ),
]

# Production environment indicator strings (literal substrings in SQL strings)
_PROD_INDICATOR_PATTERNS: list[re.Pattern] = [
    re.compile(r"(?i)['\"]\s*(?:PROD|PRODUCCION|PRODUCTION|LIVE|PRD)\s*['\"]"),
    re.compile(r"(?i)(?:catalog|database|use)\s+(?:PROD|PRODUCCION|PRODUCTION|PRD)\b"),
]

# Seed marker required in DELETE / UPDATE WHERE clauses
_SEED_MARKER_PATTERN = re.compile(
    r"(?:SeedRunId|CreatedBy\s*=\s*['\"]?QA_UAT_AGENT['\"]?)",
    re.IGNORECASE,
)


# ── Dataclasses ───────────────────────────────────────────────────────────────

@dataclass
class SafetyFinding:
    rule: str
    detail: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SqlSafetyChecks:
    transaction_present: bool
    rollback_default: bool
    prod_guard_present: bool
    seed_run_id_present: bool
    verification_select_present: bool
    dangerous_keywords: List[str]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SqlSafetyResult:
    safe: bool
    risk_level: str                    # "low" | "medium" | "high" | "critical"
    requires_human_approval: bool
    blocking_findings: List[SafetyFinding]
    checks: SqlSafetyChecks
    script_sha256: str
    source: str

    def to_dict(self) -> dict:
        return {
            "schema_version": _SCHEMA_VERSION,
            "safe": self.safe,
            "risk_level": self.risk_level,
            "requires_human_approval": self.requires_human_approval,
            "blocking_findings": [f.to_dict() for f in self.blocking_findings],
            "checks": self.checks.to_dict(),
            "script_sha256": self.script_sha256,
            "source": self.source,
        }

    def to_event(self) -> dict:
        return {
            "event": "sql_seed_safety_result",
            "script_sha256": self.script_sha256,
            "safe": self.safe,
            "risk_level": self.risk_level,
            "requires_human_approval": self.requires_human_approval,
            "blocking_findings": [f.to_dict() for f in self.blocking_findings],
        }


# ── Public API ────────────────────────────────────────────────────────────────

def validate(
    sql_text: str,
    source: str = "",
    exec_logger=None,
) -> SqlSafetyResult:
    """
    Validate a SQL seed proposal script against P0 safety rules.

    Parameters
    ----------
    sql_text : str
        The full content of the SQL script to validate.
    source : str
        Human-readable identifier (e.g. "seed:RF-007-CA-01") for logging.
    exec_logger : ExecutionLogger | None
        If provided, emits sql_seed_safety_result event.

    Returns
    -------
    SqlSafetyResult
        .safe = False if ANY P0 rule is violated.
        Always sets requires_human_approval = True regardless of safe value.
    """
    if not isinstance(sql_text, str):
        sql_text = str(sql_text)

    script_sha256 = hashlib.sha256(sql_text.encode("utf-8")).hexdigest()
    active_lines = _active_lines(sql_text)
    active_text = "\n".join(active_lines)

    blocking_findings: List[SafetyFinding] = []
    dangerous_kwds: List[str] = []

    # ── Rule 1-5, 11-13: Dangerous keywords ──────────────────────────────────
    for rule_name, pattern, detail in _DANGEROUS_KEYWORD_RULES:
        if pattern.search(active_text):
            blocking_findings.append(SafetyFinding(rule=rule_name, detail=detail))
            dangerous_kwds.append(rule_name)

    # ── Rule 3: DELETE without seed marker ───────────────────────────────────
    _check_dml_without_marker(
        "DELETE",
        re.compile(r"\bDELETE\b", re.IGNORECASE),
        active_lines,
        blocking_findings,
        "DELETE_WITHOUT_SEED_MARKER",
        "DELETE encontrado sin WHERE que incluya SeedRunId o CreatedBy='QA_UAT_AGENT'",
    )

    # ── Rule 4: UPDATE without seed marker ───────────────────────────────────
    _check_dml_without_marker(
        "UPDATE",
        re.compile(r"\bUPDATE\b", re.IGNORECASE),
        active_lines,
        blocking_findings,
        "UPDATE_WITHOUT_SEED_MARKER",
        "UPDATE encontrado sin WHERE que incluya SeedRunId o CreatedBy='QA_UAT_AGENT'",
    )

    # ── Rule 5: BEGIN TRANSACTION ────────────────────────────────────────────
    transaction_present = bool(
        re.search(r"\bBEGIN\s+TRANSACTION\b", active_text, re.IGNORECASE)
    )
    if not transaction_present:
        blocking_findings.append(SafetyFinding(
            rule="MISSING_BEGIN_TRANSACTION",
            detail="El script no contiene BEGIN TRANSACTION",
        ))

    # ── Rule 6: ROLLBACK default (active, not commented) ─────────────────────
    rollback_default = bool(
        re.search(r"\bROLLBACK\s+TRANSACTION\b", active_text, re.IGNORECASE)
    )
    if not rollback_default:
        blocking_findings.append(SafetyFinding(
            rule="MISSING_ROLLBACK_DEFAULT",
            detail=(
                "El script no contiene ROLLBACK TRANSACTION activo (no comentado). "
                "El modo por defecto debe ser ROLLBACK."
            ),
        ))

    # ── Rule 7: No active COMMIT ──────────────────────────────────────────────
    active_commit = bool(
        re.search(r"\bCOMMIT\s+TRANSACTION\b", active_text, re.IGNORECASE)
    )
    if active_commit:
        blocking_findings.append(SafetyFinding(
            rule="ACTIVE_COMMIT",
            detail=(
                "El script contiene COMMIT TRANSACTION activo (no comentado). "
                "COMMIT debe estar comentado por defecto hasta recibir aprobación humana."
            ),
        ))

    # ── Rule 8: Prod references in string literals ────────────────────────────
    for pat in _PROD_INDICATOR_PATTERNS:
        if pat.search(active_text):
            blocking_findings.append(SafetyFinding(
                rule="PROD_REFERENCE_IN_LITERALS",
                detail="El script contiene referencias a ambiente productivo en literales de string",
            ))
            break

    # ── Rule 9: Verification SELECT ───────────────────────────────────────────
    # Must have a SELECT after the last INSERT block
    verification_select_present = _has_verification_select(active_text)
    if not verification_select_present:
        blocking_findings.append(SafetyFinding(
            rule="MISSING_VERIFICATION_SELECT",
            detail="El script no contiene un SELECT de verificación después de los INSERTs",
        ))

    # ── Rule 10: @SeedRunId variable ─────────────────────────────────────────
    seed_run_id_present = bool(
        re.search(r"@SeedRunId", active_text, re.IGNORECASE)
    )
    if not seed_run_id_present:
        blocking_findings.append(SafetyFinding(
            rule="MISSING_SEED_RUN_ID",
            detail="El script no declara ni usa la variable @SeedRunId",
        ))

    # ── Check for anti-PROD guard (informational, not blocking alone) ─────────
    prod_guard_present = bool(
        re.search(r"DB_NAME\(\)\s+LIKE\s+['\"]%PROD%['\"]", active_text, re.IGNORECASE)
        or re.search(r"DB_NAME\(\)\s+LIKE\s+['\"]%PRODUCCION%['\"]", active_text, re.IGNORECASE)
    )

    # Determine overall safety
    safe = len(blocking_findings) == 0
    if safe:
        risk_level = "low"
    else:
        risk_level = "critical"

    checks = SqlSafetyChecks(
        transaction_present=transaction_present,
        rollback_default=rollback_default,
        prod_guard_present=prod_guard_present,
        seed_run_id_present=seed_run_id_present,
        verification_select_present=verification_select_present,
        dangerous_keywords=dangerous_kwds,
    )

    result = SqlSafetyResult(
        safe=safe,
        risk_level=risk_level,
        requires_human_approval=True,   # ALWAYS true — human must approve before execution
        blocking_findings=blocking_findings,
        checks=checks,
        script_sha256=script_sha256,
        source=source,
    )

    # Emit event
    if exec_logger is not None:
        try:
            exec_logger.event("sql_seed_safety_result", result.to_event())
        except Exception as exc:
            logger.debug("sql_safety_validator: cannot emit event: %s", exc)

    if safe:
        logger.info(
            "sql_safety_validator: SAFE source=%s sha256=%s",
            source, script_sha256[:16],
        )
    else:
        logger.warning(
            "sql_safety_validator: BLOCKED source=%s sha256=%s findings=%d: %s",
            source, script_sha256[:16],
            len(blocking_findings),
            [f.rule for f in blocking_findings],
        )

    return result


# ── Internal helpers ──────────────────────────────────────────────────────────

def _active_lines(sql_text: str) -> List[str]:
    """
    Return only the non-comment lines from sql_text.

    Strips:
    - Single-line comments: lines starting with -- (after stripping whitespace)
    - Inline comments: removes -- ... to end of line (but not inside strings)
    - Block comments: /* ... */ (single-line only; multi-line partially handled)

    NOTE: This is a heuristic stripper. It is NOT a full SQL parser.
    The primary goal is to distinguish active COMMIT vs commented-out COMMIT.
    """
    # First pass: strip block comments (simple single-line case)
    text = re.sub(r"/\*.*?\*/", " ", sql_text, flags=re.DOTALL)

    active = []
    for line in text.splitlines():
        # Strip inline -- comment (outside string literals — simplified)
        stripped = re.sub(r"--.*$", "", line).rstrip()
        if stripped.strip():
            active.append(stripped)
    return active


def _has_verification_select(active_text: str) -> bool:
    """
    Check that there is a SELECT statement appearing AFTER the last INSERT.

    Heuristic: find last INSERT position and last SELECT position;
    SELECT must appear after INSERT.
    """
    insert_matches = list(re.finditer(r"\bINSERT\b", active_text, re.IGNORECASE))
    select_matches = list(re.finditer(r"\bSELECT\b", active_text, re.IGNORECASE))

    if not insert_matches:
        # No INSERTs — seed script has no inserts at all. Consider it missing.
        return False
    if not select_matches:
        return False

    last_insert_pos = insert_matches[-1].start()
    last_select_pos = select_matches[-1].start()

    return last_select_pos > last_insert_pos


def _check_dml_without_marker(
    dml_keyword: str,
    dml_pattern: re.Pattern,
    active_lines: List[str],
    findings: List[SafetyFinding],
    rule_name: str,
    detail: str,
) -> None:
    """
    For each active line containing dml_keyword, check that the statement
    or its continuation contains a seed marker (SeedRunId or CreatedBy='QA_UAT_AGENT').

    Strategy: join lines around DML into a window and check for the marker.
    This handles multi-line WHERE clauses.
    """
    n = len(active_lines)
    for i, line in enumerate(active_lines):
        if not dml_pattern.search(line):
            continue

        # Gather a window of up to 10 lines after the DML for the WHERE clause
        window_end = min(i + 10, n)
        window = "\n".join(active_lines[i:window_end])

        if not _SEED_MARKER_PATTERN.search(window):
            # Check if the word is inside a comment-like context (already filtered — shouldn't happen)
            # Add finding only once per rule
            if not any(f.rule == rule_name for f in findings):
                findings.append(SafetyFinding(rule=rule_name, detail=detail))
            return   # one finding per rule is enough
