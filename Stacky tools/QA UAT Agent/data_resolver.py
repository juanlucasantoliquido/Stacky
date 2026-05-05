"""
data_resolver.py — Automated data resolver for the QA UAT Data Request Protocol.

Fase 3 of the QA UAT Agent free-form improvement plan.

Reads a data_request.json emitted by the pipeline (exit code 2 / PENDING_DATA),
validates each hint_query via sql_query_guard, executes safe queries against the
read-only BD (RSPACIFICOREAD) using sqlcmd, and writes resolved_data.json.

This eliminates the orchestrator's manual resolution step: instead of copy-pasting
queries into sqlcmd one by one, the orchestrator simply runs:

    python data_resolver.py --request evidence/freeform-xxx/data_request.json

The resolver reports what it auto-resolved and what still needs human input.

PUBLIC API:
  resolve(data_request_path, output_path=None, verbose=True) -> ResolveResult
  resolve_fields(requests, verbose=True) -> ResolveResult
  FIELD_HINTS: dict — extended field → (query, tables) mappings

CLI:
  python data_resolver.py --request <data_request.json> [--output resolved_data.json] [--background]
  python data_resolver.py --field CLIENTE_ID  # preview the hint_query for a field

ENV VARS required at runtime:
  RS_QA_DB_USER   — DB username (default: RSPACIFICOREAD)
  RS_QA_DB_PASS   — DB password
  RS_QA_DB_SERVER — DB server hostname (default: aisbddev02.cloud.ais-int.net)
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from sql_query_guard import validate as guard_validate, WHITELISTED_TABLES

logger = logging.getLogger("stacky.qa_uat.data_resolver")

_TOOL_VERSION = "1.0.0"

# ── DB configuration ─────────────────────────────────────────────────────────
_DB_SERVER_DEFAULT = "aisbddev02.cloud.ais-int.net"
_DB_USER_DEFAULT = "RSPACIFICOREAD"

# ── Extended field → hint_query mapping ──────────────────────────────────────
#
# Add entries here when the pipeline needs to auto-resolve new placeholder types.
# Key:   placeholder token name (uppercase, no braces)
# Value: (sql_query, [tables_referenced])
#
# Rules for hint_queries:
#   - SELECT only
#   - TOP N (N ≤ 5 for safety)
#   - Only WHITELISTED_TABLES
#   - ORDER BY NEWID() for random but reproducible selection
FIELD_HINTS: dict[str, tuple[str, list[str]]] = {
    # ── Cliente / Deudor ──────────────────────────────────────────────────────
    # NOTE: RIDIOMA table in dev DB contains language codes (IDIDIOMA: ENG, etc.),
    # not client IDs. CLIENTE_ID typically requires manual resolution by the
    # orchestrator who knows which specific client is needed for the test case.
    # When --auto-resolve is used, this field will be reported as "unresolved"
    # so the orchestrator can provide it manually.
    "CLIENTE_ID": (
        "-- CLIENTE_ID requires manual resolution. "
        "Use: SELECT TOP 1 IDIDIOMA FROM RIDIOMA ORDER BY NEWID()",
        ["RIDIOMA"],
    ),
    "RUT_CLIENTE": (
        "-- RUT_CLIENTE requires manual resolution by the orchestrator.",
        [],
    ),
    "ID_CLIENTE": (
        "-- ID_CLIENTE requires manual resolution by the orchestrator.",
        [],
    ),

    # ── Lote / Obligación ────────────────────────────────────────────────────
    # Verified 2026-05-04: RAGEN.AGLOTE is the lote identifier column.
    "LOTE_ID": (
        "SELECT TOP 1 AGLOTE FROM RAGEN WHERE AGPERFIL IS NOT NULL ORDER BY NEWID()",
        ["RAGEN"],
    ),
    "ID_LOTE": (
        "SELECT TOP 1 AGLOTE FROM RAGEN WHERE AGPERFIL IS NOT NULL ORDER BY NEWID()",
        ["RAGEN"],
    ),
    "RAGEN": (
        "SELECT TOP 1 AGLOTE FROM RAGEN WHERE AGPERFIL IS NOT NULL ORDER BY NEWID()",
        ["RAGEN"],
    ),

    # ── Agente ────────────────────────────────────────────────────────────────
    # RAGEN.AGPERFIL = numeric profile/agent ID
    "AGENTE_ID": (
        "SELECT TOP 1 AGPERFIL FROM RAGEN WHERE AGPERFIL IS NOT NULL ORDER BY NEWID()",
        ["RAGEN"],
    ),
    "ID_AGENTE": (
        "SELECT TOP 1 AGPERFIL FROM RAGEN WHERE AGPERFIL IS NOT NULL ORDER BY NEWID()",
        ["RAGEN"],
    ),

    # ── Motivo de gestión ────────────────────────────────────────────────────
    "MOTIVO_ID": (
        "-- MOTIVO_ID: RAGMOT table not confirmed accessible via RSPACIFICOREAD. Manual resolution required.",
        [],
    ),
    "ID_MOTIVO": (
        "-- MOTIVO_ID: RAGMOT table not confirmed accessible via RSPACIFICOREAD. Manual resolution required.",
        [],
    ),
    "CODIGO_MOTIVO": (
        "-- CODIGO_MOTIVO: RAGMOT table not confirmed accessible via RSPACIFICOREAD. Manual resolution required.",
        [],
    ),

    # ── Calidad de gestión ───────────────────────────────────────────────────
    "CALIDAD_ID": (
        "-- CALIDAD_ID: RAGCAL table not confirmed accessible via RSPACIFICOREAD. Manual resolution required.",
        [],
    ),
    "ID_CALIDAD": (
        "-- CALIDAD_ID: RAGCAL table not confirmed accessible via RSPACIFICOREAD. Manual resolution required.",
        [],
    ),
    "CODIGO_CALIDAD": (
        "-- CODIGO_CALIDAD: RAGCAL table not confirmed accessible via RSPACIFICOREAD. Manual resolution required.",
        [],
    ),

    # ── Contacto ─────────────────────────────────────────────────────────────
    "CONTACTO_ID": (
        "-- CONTACTO_ID: RACON table not confirmed accessible via RSPACIFICOREAD. Manual resolution required.",
        [],
    ),
    "ID_CONTACTO": (
        "-- CONTACTO_ID: RACON table not confirmed accessible via RSPACIFICOREAD. Manual resolution required.",
        [],
    ),

    # ── Comisión ─────────────────────────────────────────────────────────────
    "COMISION_ID": (
        "-- COMISION_ID: RACOMI table not confirmed accessible via RSPACIFICOREAD. Manual resolution required.",
        [],
    ),

    # ── Parámetro de agente ──────────────────────────────────────────────────
    "PARAMETRO_ID": (
        "-- PARAMETRO_ID: RAGPAR table not confirmed accessible via RSPACIFICOREAD. Manual resolution required.",
        [],
    ),

    # ── Sistema ───────────────────────────────────────────────────────────────
    "SISTEMA_ID": (
        "-- SISTEMA_ID: RASIST table not confirmed accessible via RSPACIFICOREAD. Manual resolution required.",
        [],
    ),
    "ID_SISTEMA": (
        "-- SISTEMA_ID: RASIST table not confirmed accessible via RSPACIFICOREAD. Manual resolution required.",
        [],
    ),
}


# ── Result dataclass ─────────────────────────────────────────────────────────

@dataclass
class ResolveResult:
    """Output of a data resolution run."""
    ok: bool
    resolved: dict[str, str] = field(default_factory=dict)
    unresolved: list[dict] = field(default_factory=list)
    blocked: list[dict] = field(default_factory=list)   # guard violations
    auto_count: int = 0
    manual_count: int = 0
    blocked_count: int = 0
    run_id: str = ""
    resolved_data_path: str = ""
    resume_command: str = ""
    elapsed_ms: int = 0

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "resolved": self.resolved,
            "unresolved": self.unresolved,
            "blocked": self.blocked,
            "auto_count": self.auto_count,
            "manual_count": self.manual_count,
            "blocked_count": self.blocked_count,
            "run_id": self.run_id,
            "resolved_data_path": self.resolved_data_path,
            "resume_command": self.resume_command,
            "elapsed_ms": self.elapsed_ms,
        }


# ── Public API ────────────────────────────────────────────────────────────────

def resolve(
    data_request_path: Path,
    output_path: Optional[Path] = None,
    verbose: bool = True,
) -> ResolveResult:
    """Read data_request.json, auto-resolve all safe hint_queries, write resolved_data.json.

    Args:
        data_request_path: Path to the data_request.json emitted by the pipeline.
        output_path:       Where to write resolved_data.json.
                           Defaults to same dir as data_request.json.
        verbose:           If True, log DEBUG details.

    Returns:
        ResolveResult with .resolved dict (already written to disk),
        .unresolved list (fields still needing human input),
        .blocked list (fields whose hint_query failed the SQL guard).
    """
    started = time.time()

    # Load data_request.json
    try:
        raw = data_request_path.read_text(encoding="utf-8")
        data_request = json.loads(raw)
    except FileNotFoundError:
        return ResolveResult(ok=False, unresolved=[{
            "field": "_system",
            "reason": f"data_request.json not found: {data_request_path}",
        }])
    except json.JSONDecodeError as exc:
        return ResolveResult(ok=False, unresolved=[{
            "field": "_system",
            "reason": f"Cannot parse data_request.json: {exc}",
        }])

    run_id = data_request.get("run_id", "")
    requests: list[dict] = data_request.get("requests") or []
    resume_command = data_request.get("resume_command", "")

    if output_path is None:
        output_path = data_request_path.parent / "resolved_data.json"

    # Load existing resolved_data if present (merge mode)
    existing: dict = {}
    if output_path.is_file():
        try:
            existing = json.loads(output_path.read_text(encoding="utf-8"))
            logger.debug("data_resolver: loaded %d existing resolved values", len(existing))
        except Exception as exc:
            logger.warning("data_resolver: could not load existing resolved_data: %s", exc)

    result = resolve_fields(requests=requests, verbose=verbose)
    result.run_id = run_id
    result.resume_command = resume_command

    # Merge with existing resolved values
    merged = {**existing, **result.resolved}
    result.resolved = merged

    # Write resolved_data.json
    output_path.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    result.resolved_data_path = str(output_path)
    result.elapsed_ms = int((time.time() - started) * 1000)

    logger.info(
        "data_resolver: resolved=%d unresolved=%d blocked=%d → %s",
        result.auto_count, result.manual_count, result.blocked_count, output_path,
    )
    return result


def resolve_fields(
    requests: list[dict],
    verbose: bool = True,
) -> ResolveResult:
    """Resolve a list of field-request dicts (from data_request.requests[]).

    Each dict must have at least 'field'. Optionally has 'hint_query' and
    'hint_tables'. If no hint_query is present, the resolver checks FIELD_HINTS
    for a known mapping.

    Does NOT write anything to disk — use resolve() for full file I/O.
    """
    resolved: dict[str, str] = {}
    unresolved: list[dict] = []
    blocked: list[dict] = []

    db_server, db_user, db_pass = _get_db_creds()
    db_available = bool(db_server and db_user and db_pass)
    if not db_available:
        logger.warning(
            "data_resolver: DB credentials not set (RS_QA_DB_USER/RS_QA_DB_PASS/RS_QA_DB_SERVER) "
            "— all fields will be marked as unresolved."
        )

    for req in requests:
        field_name: str = req.get("field", "UNKNOWN")
        description: str = req.get("description", "")
        in_cases: list = req.get("in_case_ids") or []

        # Determine hint_query: use provided one, fall back to FIELD_HINTS, else None
        hint_query: Optional[str] = req.get("hint_query") or None
        hint_tables: list = req.get("hint_tables") or []

        if not hint_query:
            if field_name in FIELD_HINTS:
                hint_query, hint_tables = FIELD_HINTS[field_name]
                logger.debug(
                    "data_resolver: field %r — using FIELD_HINTS query: %s",
                    field_name, hint_query,
                )
            else:
                unresolved.append({
                    "field": field_name,
                    "reason": "No hint_query available and field not in FIELD_HINTS. Manual resolution required.",
                    "description": description,
                    "in_case_ids": in_cases,
                })
                continue

        # Skip comment-only hints (manual-resolution markers from FIELD_HINTS)
        if hint_query.strip().startswith("--"):
            unresolved.append({
                "field": field_name,
                "reason": hint_query.strip().lstrip("- "),
                "description": description,
                "in_case_ids": in_cases,
            })
            continue

        # Validate the query before executing
        guard = guard_validate(hint_query)
        if not guard.safe:
            logger.warning(
                "data_resolver: field %r — hint_query blocked by SQL guard: %s",
                field_name, guard.violations,
            )
            blocked.append({
                "field": field_name,
                "hint_query": hint_query,
                "violations": guard.violations,
                "description": description,
                "in_case_ids": in_cases,
            })
            continue

        if guard.warnings:
            logger.debug(
                "data_resolver: field %r — guard warnings: %s", field_name, guard.warnings
            )

        # Execute the query
        if not db_available:
            unresolved.append({
                "field": field_name,
                "reason": "DB credentials not configured in environment.",
                "hint_query": hint_query,
                "description": description,
                "in_case_ids": in_cases,
            })
            continue

        value, exec_error = _run_sqlcmd(hint_query, db_server, db_user, db_pass)
        if exec_error:
            logger.warning(
                "data_resolver: field %r — query execution failed: %s", field_name, exec_error
            )
            unresolved.append({
                "field": field_name,
                "reason": f"Query execution failed: {exec_error}",
                "hint_query": hint_query,
                "description": description,
                "in_case_ids": in_cases,
            })
            continue

        if value is None:
            logger.warning(
                "data_resolver: field %r — query returned no rows. "
                "Manual resolution required.", field_name,
            )
            unresolved.append({
                "field": field_name,
                "reason": "Query returned no rows. No valid data found in the DB for this field.",
                "hint_query": hint_query,
                "description": description,
                "in_case_ids": in_cases,
            })
            continue

        resolved[field_name] = value
        logger.debug("data_resolver: field %r → %r", field_name, value)

    auto_count = len(resolved)
    manual_count = len(unresolved)
    blocked_count = len(blocked)

    return ResolveResult(
        ok=(blocked_count == 0),  # ok=False only when guard violations block a field
        resolved=resolved,
        unresolved=unresolved,
        blocked=blocked,
        auto_count=auto_count,
        manual_count=manual_count,
        blocked_count=blocked_count,
    )


def get_field_hint(field_name: str) -> Optional[tuple[str, list[str]]]:
    """Return (hint_query, hint_tables) for a known field, or None."""
    return FIELD_HINTS.get(field_name)


# ── DB execution ─────────────────────────────────────────────────────────────

def _get_db_creds() -> tuple[str, str, str]:
    """Read DB credentials from environment variables."""
    server = os.environ.get("RS_QA_DB_SERVER", _DB_SERVER_DEFAULT)
    user = os.environ.get("RS_QA_DB_USER", _DB_USER_DEFAULT)
    password = os.environ.get("RS_QA_DB_PASS", "")
    return server, user, password


def _run_sqlcmd(
    query: str,
    server: str,
    user: str,
    password: str,
    timeout_s: int = 15,
) -> tuple[Optional[str], Optional[str]]:
    """Execute a SELECT query via sqlcmd and return (first_value, error_or_None).

    Uses subprocess to invoke sqlcmd:
      sqlcmd -S <server> -U <user> -P <password> -Q <query> -h -1 -W

    Flags:
      -h -1  : suppress column headers
      -W     : strip trailing spaces from column values

    Returns:
      (value_str, None) on success
      (None, error_msg) on failure or empty result
    """
    cmd = [
        "sqlcmd",
        "-S", server,
        "-U", user,
        "-P", password,
        "-Q", query,
        "-h", "-1",
        "-W",
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except FileNotFoundError:
        return None, "sqlcmd not found. Install SQL Server Command Line Tools."
    except subprocess.TimeoutExpired:
        return None, f"sqlcmd timed out after {timeout_s}s."
    except Exception as exc:
        return None, f"Unexpected error running sqlcmd: {exc}"

    if result.returncode != 0:
        # Try to extract the error message from stderr or stdout
        stderr_text = (result.stderr or "").strip()
        stdout_text = (result.stdout or "").strip()
        error_detail = stderr_text or stdout_text or f"exit code {result.returncode}"
        # Common auth error: "Login failed for user"
        if "Login failed" in error_detail:
            return None, f"DB authentication failed: {error_detail}"
        return None, f"sqlcmd error (exit {result.returncode}): {error_detail[:200]}"

    # Parse the output: first non-empty, non-separator line after stripping
    raw_output = result.stdout or ""
    value, parse_error = _parse_sqlcmd_output(raw_output)
    if parse_error:
        return None, f"SQL error in query output: {parse_error}"
    return value, None


def _parse_sqlcmd_output(output: str) -> tuple[Optional[str], Optional[str]]:
    """Extract the first data value from sqlcmd -h -1 -W output.

    Returns (value, None) on success or (None, error_message) when the output
    contains a SQL error message.

    sqlcmd with -h -1 -W outputs:
      <value>
      (<N> rows affected)

    For query errors (even when returncode=0), sqlcmd writes to stdout:
      Msg 207, Level 16, State 1, Server ..., Line 1
      Invalid column name 'XYZ'.
    """
    _SEPARATOR_RE = re.compile(r"^-+$")
    _ROWS_AFFECTED_RE = re.compile(r"^\(\d+\s+rows?\s+affected\)", re.IGNORECASE)
    # sqlcmd SQL error messages start with "Msg N, Level N" or "Sqlcmd: Error:"
    _SQL_ERROR_RE = re.compile(
        r"^(Msg\s+\d+,|Sqlcmd:\s*Error:|Error:)", re.IGNORECASE
    )

    lines = output.splitlines()
    # First pass: check for SQL error messages
    for line in lines:
        stripped = line.strip()
        if _SQL_ERROR_RE.match(stripped):
            # Collect the full error (this line + next non-empty line)
            return None, stripped

    # Second pass: extract the first data value
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if _SEPARATOR_RE.match(stripped):
            continue
        if _ROWS_AFFECTED_RE.match(stripped):
            continue
        # This is the value
        return stripped, None

    return None, None  # empty result set


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    args = _parse_args()
    logging.basicConfig(
        level=logging.DEBUG if not args.background else logging.WARNING,
        stream=sys.stderr,
        format="%(levelname)s %(name)s: %(message)s",
    )

    if args.field:
        # Preview mode: show hint for a single field
        hint = get_field_hint(args.field.upper())
        if hint:
            q, tables = hint
            guard = guard_validate(q)
            print(json.dumps({
                "field": args.field.upper(),
                "hint_query": q,
                "hint_tables": tables,
                "guard": guard.to_dict(),
            }, ensure_ascii=False, indent=2))
            sys.exit(0)
        else:
            sys.stderr.write(
                f"No FIELD_HINTS entry for '{args.field.upper()}'. "
                f"Manual resolution required.\n"
            )
            sys.exit(1)

    if not args.request:
        sys.stderr.write("error: --request or --field is required\n")
        sys.exit(1)

    request_path = Path(args.request)
    output_path = Path(args.output) if args.output else None

    result = resolve(
        data_request_path=request_path,
        output_path=output_path,
        verbose=not args.background,
    )

    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))

    if result.unresolved or result.blocked:
        # Non-zero but not fatal — caller must handle remaining fields manually
        sys.exit(2)
    sys.exit(0 if result.ok else 1)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Auto-resolve data_request.json using hint_queries (Fase 3)."
    )
    p.add_argument("--request", default=None,
                   help="Path to data_request.json emitted by the pipeline (exit code 2).")
    p.add_argument("--output", default=None,
                   help="Path to write resolved_data.json (default: same dir as --request).")
    p.add_argument("--field", default=None,
                   help="Preview the hint_query for a single field name (e.g. CLIENTE_ID).")
    p.add_argument("--background", action="store_true",
                   help="Suppress verbose output.")
    return p.parse_args()


if __name__ == "__main__":
    main()
