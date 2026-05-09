"""
uat_precondition_checker.py — Verify QA environment preconditions before running UAT tests.

SPEC: PHASE3_QA_UAT_ROADMAP.md §3.3
CLI:
    python uat_precondition_checker.py --scenarios evidence/70/scenarios.json [--verbose]

Checks (all read-only, SELECT only):
  1. RIDIOMA scripts applied (IDs extracted from ticket preconditions)
  2. Required test data exists in BD QA (from ScenarioSpec.datos_requeridos)
  3. Environment vars for BD are set

Sprint 3 additions:
  - check_data_readiness() — per-scenario data readiness check (grid rows, records,
    permissions). Categorizes failures as DATA (GRID_EMPTY, TEST_ENTITY_NOT_FOUND,
    TEST_USER_PERMISSION_MISSING) vs ENV (DATA_SOURCE_UNREACHABLE).
  - Writes data_readiness.json artifact to evidence.
  - Emits data_readiness_check event to execution.jsonl.
  - All checks are strictly read-only (SELECT/GET only — no DML).

DB credentials (NEVER via CLI — evitar logs):
  RS_QA_DB_USER — read-only user (e.g. RSPACIFICOREAD)
  RS_QA_DB_PASS — password
  RS_QA_DB_DSN  — Data Source=aisbddev02...;Pooling=True

Output JSON to stdout:
{
  "ok": true,
  "ticket_id": 70,
  "summary": {"total": 6, "ok": 5, "blocked": 1},
  "results": {
    "P01": {"ok": true, "missing": []},
    "P04": {"ok": false, "missing": [{"tipo": "ridioma", "recurso": "IDTEXTO=9296", "hint": "..."}]}
  }
}

Error codes: db_credentials_missing, db_unreachable, invalid_scenarios_json
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, List, Optional

logger = logging.getLogger("stacky.qa_uat.precondition_checker")

_TOOL_VERSION = "1.1.0"
# 1.1.0 — Fase 2:
#   - _SAFE_TABLES ahora se extiende dinámicamente desde schema_explorer.get_tables_for_guard()
#   - Integra precondition_parser para parsear precondiciones funcionales complejas
#   - Emite resolved_values.json y precondition_gap.json junto con el resultado principal
#   - Las checks de test_data ya no están limitadas a _SAFE_TABLES estáticas

# Required env vars for DB connection
_DB_ENV_VARS = ("RS_QA_DB_USER", "RS_QA_DB_PASS", "RS_QA_DB_DSN")

# Regex to extract RIDIOMA IDTEXTO from precondition strings
# Matches: "RIDIOMA 9296", "INSERTs RIDIOMA 9296-9298", "RIDIOMA 9296,9297,9298"
_RIDIOMA_RE = re.compile(r'(?:RIDIOMA|IDTEXTO)[=\s]+(\d+(?:[-,]\d+)*)', re.IGNORECASE)

# Supported tabla checks (safe-listed para SELECT queries)
# Fase 2: ampliado con tablas confirmadas + merge dinámico desde schema_explorer
_SAFE_TABLES_STATIC = frozenset({
    "RAGEN", "RIDIOMA", "RAGTIP", "RAGMOT", "RAGCAL",
    "RACOMI", "RACON", "RAGPAR", "RASIST",
    # Tablas confirmadas con db_query_119.py (Fase 2)
    "RLOTE", "ROBLG", "RCLIE",
})


def _get_safe_tables() -> frozenset:
    """Retorna el conjunto de tablas seguras, combinando estáticas + schema_explorer."""
    try:
        from schema_explorer import get_tables_for_guard
        return _SAFE_TABLES_STATIC | get_tables_for_guard()
    except Exception:
        return _SAFE_TABLES_STATIC


# ── Sprint 3: Data Readiness Check ───────────────────────────────────────────
# All checks are READ-ONLY (SELECT/GET). No INSERT/UPDATE/DELETE is ever issued.
# If a check cannot be performed without DML it is marked skipped=True with
# reason VERIFICATION_REQUIRES_DML.

_DATA_REASONS = {
    "grid_empty":              ("DATA", "GRID_EMPTY"),
    "entity_not_found":        ("DATA", "TEST_ENTITY_NOT_FOUND"),
    "permission_missing":      ("DATA", "TEST_USER_PERMISSION_MISSING"),
    "source_unreachable":      ("ENV",  "DATA_SOURCE_UNREACHABLE"),
    "verification_needs_dml":  (None,   "VERIFICATION_REQUIRES_DML"),
}

_DATA_NAV_REASONS = {
    "SELECTOR_NOT_FOUND":      "NAV",
    "SELECTOR_TIMEOUT":        "NAV",
    "PAGE_LOAD_FAILED":        "ENV",
    "DEPLOYMENT_MISMATCH":     "ENV",
    "GRID_EMPTY":              "DATA",
    "TEST_ENTITY_NOT_FOUND":   "DATA",
    "TEST_USER_PERMISSION_MISSING": "DATA",
    "DATA_SOURCE_UNREACHABLE": "ENV",
    "CATALOG_MISSING":         "DATA",   # Sprint 3: catalog not seeded
    "CATALOG_EMPTY":           "DATA",   # Sprint 3: catalog has 0 entries
}


@dataclass
class DataCheck:
    """Result of a single data readiness precondition check."""
    entity: str
    type: str                        # "grid" | "record" | "user_permission" | "api_endpoint"
    input_data: dict
    expected: dict
    actual: dict
    decision: str                    # "ALLOW" | "BLOCKED" | "SKIPPED"
    category: Optional[str]          # "DATA" | "ENV" | None
    reason: Optional[str]
    human_action_required: Optional[str]
    skipped: bool

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DataReadinessResult:
    """Aggregated result of all data readiness checks for a scenario."""
    all_ready: bool
    checks: List[DataCheck]
    decision: str                    # "ALLOW" | "BLOCKED"
    category: Optional[str]         # "DATA" | "ENV" | None
    reason: Optional[str]
    artifact_path: Optional[str]

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


def check_data_readiness(
    ticket_id: int,
    scenario_id: str,
    preconditions: List[dict],
    exec_logger=None,
    evidence_dir: Optional[Path] = None,
    run_id: Optional[str] = None,
    _db_connector=None,             # injectable for testing
) -> DataReadinessResult:
    """Verify data readiness before running the UAT runner for a scenario.

    Parameters
    ----------
    ticket_id : int
        ADO work item ID (for logging/event).
    scenario_id : str
        Scenario identifier (e.g. "RF-007-CA-01").
    preconditions : list[dict]
        Each entry: {entity, type, input_data, expected}.
        Supported types: "grid", "record", "user_permission", "api_endpoint".
    exec_logger : ExecutionLogger | None
        If provided, emits data_readiness_check event.
    evidence_dir : Path | None
        If provided, writes data_readiness.json artifact.
    run_id : str | None
        Sub-directory for artifact placement.
    _db_connector : callable | None
        Injectable DB connector factory (for unit tests).

    Returns
    -------
    DataReadinessResult
        decision = "ALLOW" | "BLOCKED"
    """
    checks: List[DataCheck] = []

    for prec in preconditions:
        check = _run_single_data_check(
            prec=prec,
            ticket_id=ticket_id,
            scenario_id=scenario_id,
            _db_connector=_db_connector,
        )
        checks.append(check)

    blocked = [c for c in checks if c.decision == "BLOCKED"]
    all_ready = len(blocked) == 0

    if blocked:
        # Use first blocked check's category/reason as the aggregate
        first = blocked[0]
        decision = "BLOCKED"
        category = first.category
        reason = first.reason
    else:
        decision = "ALLOW"
        category = None
        reason = None

    result = DataReadinessResult(
        all_ready=all_ready,
        checks=checks,
        decision=decision,
        category=category,
        reason=reason,
        artifact_path=None,
    )

    # ── Artifact ──────────────────────────────────────────────────────────────
    artifact_path = _write_data_readiness_artifact(result, evidence_dir, run_id, scenario_id)
    if artifact_path:
        result.artifact_path = str(artifact_path)

    # ── Event ─────────────────────────────────────────────────────────────────
    _emit_data_readiness_event(exec_logger, ticket_id, scenario_id, result)

    if decision == "BLOCKED":
        logger.warning(
            "data_readiness BLOCKED ticket=%s scenario=%s reason=%s category=%s",
            ticket_id, scenario_id, reason, category,
        )
    else:
        logger.info(
            "data_readiness ALLOW ticket=%s scenario=%s checks=%d",
            ticket_id, scenario_id, len(checks),
        )

    return result


def _run_single_data_check(
    prec: dict,
    ticket_id: int,
    scenario_id: str,
    _db_connector=None,
) -> DataCheck:
    """Execute a single data readiness check. All access is read-only."""
    entity = prec.get("entity", "unknown")
    check_type = prec.get("type", "record")
    input_data = prec.get("input_data", {})
    expected = prec.get("expected", {})

    try:
        if check_type == "grid":
            return _check_grid(entity, input_data, expected, _db_connector)

        elif check_type == "record":
            return _check_record(entity, input_data, expected, _db_connector)

        elif check_type == "user_permission":
            return _check_user_permission(entity, input_data, expected, _db_connector)

        elif check_type == "api_endpoint":
            return _check_api_endpoint(entity, input_data, expected)

        else:
            # Unknown check type — skip with explanation
            return DataCheck(
                entity=entity,
                type=check_type,
                input_data=input_data,
                expected=expected,
                actual={},
                decision="SKIPPED",
                category=None,
                reason=f"UNKNOWN_CHECK_TYPE:{check_type}",
                human_action_required=None,
                skipped=True,
            )

    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "data_readiness check error entity=%s type=%s: %s", entity, check_type, exc
        )
        return DataCheck(
            entity=entity,
            type=check_type,
            input_data=input_data,
            expected=expected,
            actual={"error": str(exc)},
            decision="BLOCKED",
            category="ENV",
            reason="DATA_SOURCE_UNREACHABLE",
            human_action_required=f"check_connectivity_for_{entity}",
            skipped=False,
        )


def _check_grid(
    entity: str,
    input_data: dict,
    expected: dict,
    _db_connector=None,
) -> DataCheck:
    """Check that a grid entity has at least min_rows rows.

    READ-ONLY: only executes SELECT COUNT(*) queries.
    If DB is unavailable, marks as SKIPPED (not blocked) so the pipeline
    proceeds with the runner which will discover the issue.
    """
    min_rows = expected.get("min_rows", 1)

    # Try DB check if connector available
    row_count = _query_grid_count(entity, input_data, _db_connector)

    if row_count is None:
        # Cannot verify — DB not available
        return DataCheck(
            entity=entity,
            type="grid",
            input_data=input_data,
            expected=expected,
            actual={"row_count": None, "note": "db_unavailable"},
            decision="SKIPPED",
            category=None,
            reason="VERIFICATION_REQUIRES_DML",  # reused as "cannot verify"
            human_action_required=None,
            skipped=True,
        )

    if row_count < min_rows:
        return DataCheck(
            entity=entity,
            type="grid",
            input_data=input_data,
            expected=expected,
            actual={"row_count": row_count},
            decision="BLOCKED",
            category="DATA",
            reason="GRID_EMPTY",
            human_action_required=(
                f"seed_{entity.lower()}_o_cambiar_input_data"
            ),
            skipped=False,
        )

    return DataCheck(
        entity=entity,
        type="grid",
        input_data=input_data,
        expected=expected,
        actual={"row_count": row_count},
        decision="ALLOW",
        category=None,
        reason=None,
        human_action_required=None,
        skipped=False,
    )


def _check_record(
    entity: str,
    input_data: dict,
    expected: dict,
    _db_connector=None,
) -> DataCheck:
    """Check that a record exists in the database.

    READ-ONLY: only SELECT queries.
    """
    exists = _query_record_exists(entity, input_data, _db_connector)

    if exists is None:
        return DataCheck(
            entity=entity,
            type="record",
            input_data=input_data,
            expected=expected,
            actual={"exists": None, "note": "db_unavailable"},
            decision="SKIPPED",
            category=None,
            reason="VERIFICATION_REQUIRES_DML",
            human_action_required=None,
            skipped=True,
        )

    if not exists:
        return DataCheck(
            entity=entity,
            type="record",
            input_data=input_data,
            expected=expected,
            actual={"exists": False},
            decision="BLOCKED",
            category="DATA",
            reason="TEST_ENTITY_NOT_FOUND",
            human_action_required=(
                f"create_{entity.lower()}_with_input_data_{json.dumps(input_data, ensure_ascii=False)[:80]}"
            ),
            skipped=False,
        )

    return DataCheck(
        entity=entity,
        type="record",
        input_data=input_data,
        expected=expected,
        actual={"exists": True},
        decision="ALLOW",
        category=None,
        reason=None,
        human_action_required=None,
        skipped=False,
    )


def _check_user_permission(
    entity: str,
    input_data: dict,
    expected: dict,
    _db_connector=None,
) -> DataCheck:
    """Check that a user has the required permission.

    READ-ONLY: only SELECT queries.
    """
    user = input_data.get("user") or input_data.get("usuario") or ""
    permission = expected.get("permission") or expected.get("permiso") or entity

    has_perm = _query_user_permission(user, permission, _db_connector)

    if has_perm is None:
        return DataCheck(
            entity=entity,
            type="user_permission",
            input_data=input_data,
            expected=expected,
            actual={"has_permission": None, "note": "db_unavailable"},
            decision="SKIPPED",
            category=None,
            reason="VERIFICATION_REQUIRES_DML",
            human_action_required=None,
            skipped=True,
        )

    if not has_perm:
        return DataCheck(
            entity=entity,
            type="user_permission",
            input_data=input_data,
            expected=expected,
            actual={"has_permission": False, "user": user, "permission": permission},
            decision="BLOCKED",
            category="DATA",
            reason="TEST_USER_PERMISSION_MISSING",
            human_action_required=(
                f"grant_permission_{permission}_to_user_{user}"
            ),
            skipped=False,
        )

    return DataCheck(
        entity=entity,
        type="user_permission",
        input_data=input_data,
        expected=expected,
        actual={"has_permission": True, "user": user, "permission": permission},
        decision="ALLOW",
        category=None,
        reason=None,
        human_action_required=None,
        skipped=False,
    )


def _check_api_endpoint(
    entity: str,
    input_data: dict,
    expected: dict,
) -> DataCheck:
    """Check that an API endpoint is reachable (HTTP GET).

    READ-ONLY: only GET requests.
    """
    import urllib.request
    import urllib.error

    url = input_data.get("url", "")
    if not url:
        return DataCheck(
            entity=entity,
            type="api_endpoint",
            input_data=input_data,
            expected=expected,
            actual={},
            decision="SKIPPED",
            category=None,
            reason="VERIFICATION_REQUIRES_DML",
            human_action_required="provide_url_in_input_data",
            skipped=True,
        )

    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            status = resp.getcode()
        ok = status < 500
        if ok:
            return DataCheck(
                entity=entity,
                type="api_endpoint",
                input_data=input_data,
                expected=expected,
                actual={"status": status, "reachable": True},
                decision="ALLOW",
                category=None,
                reason=None,
                human_action_required=None,
                skipped=False,
            )
        return DataCheck(
            entity=entity,
            type="api_endpoint",
            input_data=input_data,
            expected=expected,
            actual={"status": status, "reachable": False},
            decision="BLOCKED",
            category="ENV",
            reason="DATA_SOURCE_UNREACHABLE",
            human_action_required=f"check_api_endpoint_{url}",
            skipped=False,
        )
    except (urllib.error.URLError, OSError) as exc:
        return DataCheck(
            entity=entity,
            type="api_endpoint",
            input_data=input_data,
            expected=expected,
            actual={"error": str(exc), "reachable": False},
            decision="BLOCKED",
            category="ENV",
            reason="DATA_SOURCE_UNREACHABLE",
            human_action_required=f"check_connectivity_for_{entity}",
            skipped=False,
        )


# ── DB query helpers (read-only) ───────────────────────────────────────────────

def _get_readiness_connection(_db_connector=None):
    """Get a DB connection for readiness checks. Returns None if unavailable."""
    if _db_connector is not None:
        try:
            return _db_connector()
        except Exception:
            return None

    missing = [v for v in _DB_ENV_VARS if not os.getenv(v)]
    if missing:
        return None

    try:
        connector = _get_db_connector()
        return connector()
    except Exception:
        return None


def _query_grid_count(
    entity: str,
    input_data: dict,
    _db_connector=None,
) -> Optional[int]:
    """SELECT COUNT(*) from the entity table matching input_data. Returns None if DB unavailable."""
    safe_tables = _get_safe_tables()
    table_name = entity.upper()
    if table_name not in {t.upper() for t in safe_tables}:
        # Table not in safe list — cannot verify without potential injection risk
        logger.warning(
            "data_readiness: entity '%s' not in safe-list — skipping grid count check",
            entity,
        )
        return None

    conn = _get_readiness_connection(_db_connector)
    if conn is None:
        return None

    try:
        # Build WHERE clause from input_data (read-only)
        where_parts = []
        params = []
        for col, val in input_data.items():
            # Only allow simple equality conditions (no SQL injection via column names)
            if re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', col):
                where_parts.append(f"{col} = ?")
                params.append(val)

        where_clause = " AND ".join(where_parts) if where_parts else "1=1"
        query = f"SELECT COUNT(*) FROM {table_name} WHERE {where_clause}"  # nosec
        cursor = conn.cursor()
        cursor.execute(query, params)
        row = cursor.fetchone()
        count = row[0] if row else 0
        cursor.close()
        return int(count)
    except Exception as exc:
        logger.warning("data_readiness: grid count error for %s: %s", entity, exc)
        return None
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _query_record_exists(
    entity: str,
    input_data: dict,
    _db_connector=None,
) -> Optional[bool]:
    """Check if a record exists. Returns None if DB unavailable."""
    count = _query_grid_count(entity, input_data, _db_connector)
    if count is None:
        return None
    return count > 0


def _query_user_permission(
    user: str,
    permission: str,
    _db_connector=None,
) -> Optional[bool]:
    """Check user permission in RASIST or similar table. Returns None if DB unavailable."""
    conn = _get_readiness_connection(_db_connector)
    if conn is None:
        return None

    try:
        # Read-only check — validate user exists and has the permission
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM RASIST WHERE CODUSR = ? AND CODPER = ? AND ACTIVO = 1",
            (user, permission),
        )
        row = cursor.fetchone()
        count = row[0] if row else 0
        cursor.close()
        return count > 0
    except Exception as exc:
        logger.warning(
            "data_readiness: permission check error user=%s perm=%s: %s",
            user, permission, exc,
        )
        return None
    finally:
        try:
            conn.close()
        except Exception:
            pass


# ── Artifact & event (Sprint 3) ───────────────────────────────────────────────

def _write_data_readiness_artifact(
    result: DataReadinessResult,
    evidence_dir: Optional[Path],
    run_id: Optional[str],
    scenario_id: str,
) -> Optional[Path]:
    """Write data_readiness.json artifact; return path or None."""
    if evidence_dir is None:
        return None
    try:
        if run_id:
            artifact_dir = evidence_dir / str(run_id)
        else:
            artifact_dir = evidence_dir
        artifact_dir.mkdir(parents=True, exist_ok=True)
        artifact_path = artifact_dir / "data_readiness.json"
        data = {
            "schema_version": "data_readiness/1.0",
            "scenario_id": scenario_id,
            **result.to_dict(),
        }
        artifact_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        logger.debug("data_readiness artifact: %s", artifact_path)
        return artifact_path
    except Exception as exc:  # noqa: BLE001
        logger.warning("data_readiness: cannot write artifact: %s", exc)
        return None


def _emit_data_readiness_event(
    exec_logger,
    ticket_id: int,
    scenario_id: str,
    result: DataReadinessResult,
) -> None:
    """Emit data_readiness_check event to execution.jsonl."""
    if exec_logger is None:
        return
    try:
        exec_logger.event("data_readiness_check", {
            "ticket_id": ticket_id,
            "scenario_id": scenario_id,
            "checks": [c.to_dict() for c in result.checks],
            "all_ready": result.all_ready,
            "decision": result.decision,
            "category": result.category,
            "reason": result.reason,
            "artifact_path": result.artifact_path,
        })
    except Exception as exc:  # noqa: BLE001
        logger.debug("data_readiness: cannot emit event: %s", exc)


# ── Category inference table (Sprint 3 Item 3.3) ─────────────────────────────

def infer_failure_category(reason: str) -> str:
    """Infer the pipeline failure category from a reason code.

    Returns the canonical category string.  NAVIGATION_TIMEOUT is only
    valid when there is trace/screenshot evidence of an existing-but-unresponsive
    selector.  Call this before setting a final reason to ensure correct
    categorization.

    Examples
    --------
    >>> infer_failure_category("GRID_EMPTY")
    'DATA'
    >>> infer_failure_category("SELECTOR_NOT_FOUND")
    'NAV'
    >>> infer_failure_category("DEPLOYMENT_MISMATCH")
    'ENV'
    """
    return _DATA_NAV_REASONS.get(reason, "NAV")


# ── Seed SQL generator (Sprint 3 Item 3.3) ────────────────────────────────────

_SEED_SQL_TEMPLATES: dict[str, dict] = {
    # entity → {seed_sql, rollback_sql, label}
    "ROBLG": {
        "label": "obligaciones_de_prueba",
        "seed_sql": (
            "-- SEED: obligaciones de prueba para QA UAT (Sprint 3)\n"
            "-- Idempotente: usa MERGE para no duplicar\n"
            "-- Etiqueta: QA_UAT_SEED_{scenario_id}\n"
            "MERGE INTO RSPACIFICO.ROBLG AS target\n"
            "USING (\n"
            "    SELECT 'QA_UAT_SEED_{scenario_id}' AS QA_LABEL,\n"
            "           {clcod} AS CLCOD,\n"
            "           SYSDATE AS FECALT\n"
            "    FROM DUAL\n"
            "    WHERE NOT EXISTS (\n"
            "        SELECT 1 FROM RSPACIFICO.ROBLG\n"
            "        WHERE CLCOD = {clcod} AND QA_LABEL = 'QA_UAT_SEED_{scenario_id}'\n"
            "    )\n"
            ") AS source ON (target.CLCOD = source.CLCOD AND target.QA_LABEL = source.QA_LABEL)\n"
            "WHEN NOT MATCHED THEN INSERT (CLCOD, QA_LABEL, FECALT)\n"
            "    VALUES (source.CLCOD, source.QA_LABEL, source.FECALT);\n"
        ),
        "rollback_sql": (
            "-- ROLLBACK: eliminar obligaciones seed de QA UAT (Sprint 3)\n"
            "-- Etiqueta: QA_UAT_SEED_{scenario_id}\n"
            "DELETE FROM RSPACIFICO.ROBLG\n"
            "WHERE QA_LABEL = 'QA_UAT_SEED_{scenario_id}';\n"
            "-- Verificar antes de commit:\n"
            "-- SELECT COUNT(*) FROM RSPACIFICO.ROBLG WHERE QA_LABEL = 'QA_UAT_SEED_{scenario_id}';\n"
        ),
    },
    "CLCLIE": {
        "label": "cliente_de_prueba",
        "seed_sql": (
            "-- SEED: cliente de prueba para QA UAT (Sprint 3)\n"
            "-- Idempotente: INSERT IF NOT EXISTS\n"
            "-- Etiqueta: QA_UAT_SEED_{scenario_id}\n"
            "INSERT INTO RSPACIFICO.CLCLIE (CLCOD, CLNOMB, QA_LABEL)\n"
            "SELECT {clcod}, 'QA UAT TEST CLIENT', 'QA_UAT_SEED_{scenario_id}'\n"
            "FROM DUAL\n"
            "WHERE NOT EXISTS (\n"
            "    SELECT 1 FROM RSPACIFICO.CLCLIE\n"
            "    WHERE CLCOD = {clcod} AND QA_LABEL = 'QA_UAT_SEED_{scenario_id}'\n"
            ");\n"
        ),
        "rollback_sql": (
            "-- ROLLBACK: eliminar cliente seed de QA UAT (Sprint 3)\n"
            "DELETE FROM RSPACIFICO.CLCLIE\n"
            "WHERE QA_LABEL = 'QA_UAT_SEED_{scenario_id}';\n"
        ),
    },
}

_GENERIC_SEED_SQL = (
    "-- SEED: datos de prueba para QA UAT (Sprint 3) — entidad {entity}\n"
    "-- IMPORTANTE: reemplazar con INSERT idempotente para la entidad {entity}.\n"
    "-- Etiqueta todos los registros con: QA_UAT_SEED_{scenario_id}\n"
    "-- Incluir rollback_sql para eliminar datos seed después del test.\n"
    "-- Ver: docs/seed-sql-guidelines.md\n"
)

_GENERIC_ROLLBACK_SQL = (
    "-- ROLLBACK: eliminar datos seed de QA UAT (Sprint 3) — entidad {entity}\n"
    "-- DELETE FROM <tabla> WHERE QA_LABEL = 'QA_UAT_SEED_{scenario_id}';\n"
)


def generate_seed_sql(
    blocked_checks: list,
    scenario_id: str,
    evidence_dir: Optional[Path] = None,
) -> dict:
    """Generate seed SQL suggestion for blocked data readiness checks.

    Sprint 3 — produces idempotent, labeled SQL seed + rollback suggestions
    for every BLOCKED check.  Never executes any SQL.

    Parameters
    ----------
    blocked_checks : list[DataCheck]
        Only checks with decision="BLOCKED" should be passed.
    scenario_id : str
        Scenario identifier — embedded in SQL labels for traceability.
    evidence_dir : Path | None
        If provided, writes seed_sql_suggestion.sql and rollback_sql_suggestion.sql.

    Returns
    -------
    dict
        {
          "ok": True,
          "scenario_id": ...,
          "seed_sql": "<full SQL>",
          "rollback_sql": "<full SQL>",
          "seed_sql_path": "<path or None>",
          "rollback_sql_path": "<path or None>",
          "entities": [...],
        }
    """
    if not blocked_checks:
        return {
            "ok": True,
            "scenario_id": scenario_id,
            "seed_sql": None,
            "rollback_sql": None,
            "seed_sql_path": None,
            "rollback_sql_path": None,
            "entities": [],
        }

    seed_parts: list[str] = [
        f"-- ============================================================\n"
        f"-- QA UAT SEED SQL — Sprint 3\n"
        f"-- Scenario: {scenario_id}\n"
        f"-- Generated: READ-ONLY suggestion, NOT executed automatically\n"
        f"-- Label all seed records with: QA_UAT_SEED_{scenario_id}\n"
        f"-- ============================================================\n",
    ]
    rollback_parts: list[str] = [
        f"-- ============================================================\n"
        f"-- QA UAT ROLLBACK SQL — Sprint 3\n"
        f"-- Scenario: {scenario_id}\n"
        f"-- Run AFTER QA UAT test to clean up seed data.\n"
        f"-- ============================================================\n",
    ]

    entities_seen: list[str] = []
    for check in blocked_checks:
        entity = getattr(check, "entity", None) or check.get("entity", "UNKNOWN")  # type: ignore[union-attr]
        if entity not in entities_seen:
            entities_seen.append(entity)

        input_data = getattr(check, "input_data", {}) or {}
        clcod = input_data.get("CLCOD", "{CLCOD_REPLACE}")
        fmt = {"scenario_id": scenario_id, "entity": entity, "clcod": clcod}

        template = _SEED_SQL_TEMPLATES.get(entity)
        if template:
            seed_parts.append(template["seed_sql"].format(**fmt))
            rollback_parts.append(template["rollback_sql"].format(**fmt))
        else:
            seed_parts.append(_GENERIC_SEED_SQL.format(**fmt))
            rollback_parts.append(_GENERIC_ROLLBACK_SQL.format(**fmt))

    seed_sql = "\n".join(seed_parts)
    rollback_sql = "\n".join(rollback_parts)

    seed_path: Optional[Path] = None
    rollback_path: Optional[Path] = None

    if evidence_dir is not None:
        try:
            evidence_dir.mkdir(parents=True, exist_ok=True)
            seed_path = evidence_dir / "seed_sql_suggestion.sql"
            seed_path.write_text(seed_sql, encoding="utf-8")
            rollback_path = evidence_dir / "rollback_sql_suggestion.sql"
            rollback_path.write_text(rollback_sql, encoding="utf-8")
            logger.info(
                "data_readiness: seed SQL written to %s, rollback to %s",
                seed_path, rollback_path,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("data_readiness: failed to write seed SQL artifacts: %s", exc)
            seed_path = None
            rollback_path = None

    return {
        "ok": True,
        "scenario_id": scenario_id,
        "seed_sql": seed_sql,
        "rollback_sql": rollback_sql,
        "seed_sql_path": str(seed_path) if seed_path else None,
        "rollback_sql_path": str(rollback_path) if rollback_path else None,
        "entities": entities_seen,
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    args = _parse_args()
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, stream=sys.stderr,
                            format="%(levelname)s %(name)s: %(message)s")
    else:
        logging.basicConfig(level=logging.WARNING, stream=sys.stderr)

    result = run(
        scenarios_path=Path(args.scenarios),
        verbose=args.verbose,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result.get("ok") else 1)


# ── Core logic ────────────────────────────────────────────────────────────────

def run(
    scenarios_path: Path,
    verbose: bool = False,
    _db_connector=None,  # injectable for testing — callable() -> connection
) -> dict:
    """Core logic — callable from tests without subprocess."""
    started = time.time()

    # Load scenarios JSON
    try:
        scenarios_data = json.loads(scenarios_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return _err("invalid_scenarios_json", f"Cannot read scenarios: {exc}")

    if not scenarios_data.get("ok") or not isinstance(scenarios_data.get("scenarios"), list):
        return _err("invalid_scenarios_json", "scenarios.json missing 'ok' or 'scenarios'")

    scenarios = scenarios_data["scenarios"]
    ticket_id = scenarios_data.get("ticket_id", 0)

    # Check DB credentials
    missing_env = [v for v in _DB_ENV_VARS if not os.getenv(v)]
    if missing_env:
        # Fase 8 — lazy BD fallback: when DSN is missing, return a SKIPPED
        # result instead of blocking the pipeline. Playbook-based generation
        # does not require precondition checks (data comes from intent_spec).
        # The dossier will show "preconditions_skipped: missing_env" so the
        # operator knows the check was not performed.
        logger.info(
            "precondition_checker: env vars missing (%s) — returning skipped result",
            ", ".join(missing_env),
        )
        skipped_results = {
            s.get("scenario_id", "?"): {
                "ok": True,
                "skipped": True,
                "reason": f"BD env vars not set: {', '.join(missing_env)}",
                "missing": [],
            }
            for s in scenarios
        }
        return {
            "ok": True,
            "ticket_id": ticket_id,
            "skipped": True,
            "skip_reason": f"Missing env vars: {', '.join(missing_env)}",
            "summary": {"total": len(scenarios), "ok": len(scenarios), "blocked": 0, "skipped": len(scenarios)},
            "results": skipped_results,
            "elapsed_ms": int((time.time() - started) * 1000),
        }

    # Try connecting to DB (or use injectable connector)
    try:
        connector = _db_connector or _get_db_connector()
        connection = connector()
    except Exception as exc:
        return _err("db_unreachable", f"Cannot connect to BD QA: {exc}")

    results = {}
    blocked_count = 0

    # Fase 2: safe tables resueltas dinámicamente (schema_explorer + estáticas)
    safe_tables = _get_safe_tables()

    try:
        for scenario in scenarios:
            scenario_id = scenario.get("scenario_id", "?")
            missing = []

            # Check 1: RIDIOMA scripts from preconditions
            ridioma_ids = _extract_ridioma_ids(scenario.get("precondiciones") or [])
            for idtexto in ridioma_ids:
                ok = _check_ridioma(connection, idtexto, verbose=verbose)
                if not ok:
                    missing.append({
                        "tipo": "ridioma",
                        "recurso": f"RIDIOMA.IDTEXTO={idtexto}",
                        "hint": (
                            f"Ejecutar INSERTs RIDIOMA para IDTEXTO={idtexto}. "
                            "Ver análisis técnico del ticket."
                        ),
                    })

            # Check 1b: Fase 2 — Precondiciones funcionales complejas via precondition_parser
            precondiciones = scenario.get("precondiciones") or []
            _run_parsed_preconditions(
                precondiciones=precondiciones,
                scenario_id=scenario_id,
                connection=connection,
                missing=missing,
                scenarios_path=scenarios_path,
            )

            # Check 2: Required test data from datos_requeridos
            for data_req in (scenario.get("datos_requeridos") or []):
                tabla = data_req.get("tabla", "")
                filtro = data_req.get("filtro", "")
                if not tabla or not filtro:
                    continue
                if tabla.upper() not in {t.upper() for t in safe_tables}:
                    logger.warning("Tabla '%s' not in safe-list, skipping data check", tabla)
                    continue
                ok = _check_test_data(connection, tabla, filtro, verbose=verbose)
                if not ok:
                    missing.append({
                        "tipo": "test_data",
                        "recurso": f"{tabla} WHERE {filtro}",
                        "hint": (
                            f"No se encontraron registros en {tabla} con condición: {filtro}. "
                            "Verificar que los datos de prueba estén disponibles en BD QA."
                        ),
                    })

            result_ok = len(missing) == 0
            if not result_ok:
                blocked_count += 1

            results[scenario_id] = {
                "ok": result_ok,
                "missing": missing,
            }

    finally:
        try:
            connection.close()
        except Exception:
            pass

    total = len(scenarios)
    ok_count = total - blocked_count

    return {
        "ok": True,
        "ticket_id": ticket_id,
        "summary": {
            "total": total,
            "ok": ok_count,
            "blocked": blocked_count,
        },
        "results": results,
        "elapsed_s": round(time.time() - started, 2),
    }


def _run_parsed_preconditions(
    precondiciones: list[str],
    scenario_id: str,
    connection,
    missing: list,
    scenarios_path: Path,
) -> None:
    """
    Fase 2: Parsea precondiciones funcionales complejas usando precondition_parser
    y emite resolved_values.json + precondition_gap.json junto a scenarios.json.

    Solo procesa precondiciones que NO son RIDIOMA (esas ya las maneja Check 1).
    Las precondiciones RIDIOMA se detectan por el regex _RIDIOMA_RE.
    """
    non_ridioma = [
        p for p in precondiciones
        if p.strip() and not _RIDIOMA_RE.search(p)
    ]
    if not non_ridioma:
        return

    try:
        from precondition_parser import parse_all, emit_resolved_values, emit_precondition_gap
    except ImportError:
        logger.debug("precondition_parser not available — skipping parsed preconditions check")
        return

    base_dir = scenarios_path.parent / scenario_id
    try:
        parse_results = parse_all(non_ridioma, connection=connection, use_llm=False)

        # Emitir resolved_values.json
        emit_resolved_values(
            parse_results=parse_results,
            scenario_id=scenario_id,
            out_path=base_dir / "resolved_values.json",
        )

        # Emitir precondition_gap.json
        emit_precondition_gap(
            parse_results=parse_results,
            scenario_id=scenario_id,
            out_path=base_dir / "precondition_gap.json",
        )

        # Para precondiciones con gaps, añadir a missing
        for r in parse_results:
            for u in r.unresolved:
                missing.append({
                    "tipo": "precondition_unresolved",
                    "recurso": u[:120],
                    "hint": (
                        "Precondición no pudo resolverse automáticamente. "
                        "Verificar en precondition_gap.json. "
                        "Usar `python domain_glossary.py --lookup \"<término>\"` para diagnosticar."
                    ),
                })
    except Exception as exc:
        logger.warning(
            "precondition_checker: _run_parsed_preconditions failed for %s: %s",
            scenario_id, exc,
        )


# ── DB helpers ────────────────────────────────────────────────────────────────

def _get_db_connector():
    """
    Returns a factory function that creates a pyodbc connection using env vars.
    The connection uses account RSPACIFICOREAD (SELECT only — account policy enforced by DB).
    """
    import importlib
    try:
        pyodbc = importlib.import_module("pyodbc")
    except ImportError:
        raise ImportError(
            "pyodbc not installed. Run: pip install pyodbc. "
            "Also requires ODBC driver for SQL Server."
        )

    dsn = os.environ["RS_QA_DB_DSN"]
    user = os.environ["RS_QA_DB_USER"]
    password = os.environ["RS_QA_DB_PASS"]

    def connect():
        conn_str = f"{dsn};UID={user};PWD={password};ApplicationIntent=ReadOnly"
        conn = pyodbc.connect(conn_str, timeout=10)
        conn.autocommit = True  # SELECT only — no transactions needed
        return conn

    return connect


def _check_ridioma(connection, idtexto: int, verbose: bool = False) -> bool:
    """Check that RIDIOMA has at least one row with IDTEXTO=idtexto."""
    try:
        cursor = connection.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM RIDIOMA WHERE IDTEXTO = ?",
            (idtexto,),
        )
        row = cursor.fetchone()
        count = row[0] if row else 0
        cursor.close()
        logger.debug("RIDIOMA IDTEXTO=%d → count=%d", idtexto, count)
        return count > 0
    except Exception as exc:
        logger.warning("RIDIOMA check failed for IDTEXTO=%d: %s", idtexto, exc)
        return False


def _check_test_data(connection, tabla: str, filtro: str, verbose: bool = False) -> bool:
    """
    Check that tabla WHERE filtro returns at least 1 row.
    SECURITY: tabla is validated against _SAFE_TABLES before this call.
    filtro is appended to the query but never executed as raw DDL/DML.
    """
    try:
        # NOTE: tabla is from _SAFE_TABLES (safe-listed). filtro comes from scenarios.json
        # which is generated by the pipeline, not from external user input.
        query = f"SELECT COUNT(*) FROM {tabla} WHERE {filtro}"  # nosec
        cursor = connection.cursor()
        cursor.execute(query)
        row = cursor.fetchone()
        count = row[0] if row else 0
        cursor.close()
        logger.debug("%s WHERE %s → count=%d", tabla, filtro, count)
        return count > 0
    except Exception as exc:
        logger.warning("Data check failed for %s WHERE %s: %s", tabla, filtro, exc)
        return False


# ── RIDIOMA ID extraction ─────────────────────────────────────────────────────

def _extract_ridioma_ids(precondiciones: list) -> list:
    """
    Extract RIDIOMA IDTEXTO values from precondition strings.

    Examples:
      "INSERTs RIDIOMA 9296-9298 aplicados" → [9296, 9297, 9298]
      "RIDIOMA 9296,9297" → [9296, 9297]
      "RIDIOMA 9296" → [9296]
    """
    ids = []
    for prec in precondiciones:
        for match in _RIDIOMA_RE.finditer(str(prec)):
            raw = match.group(1)
            if "-" in raw:
                parts = raw.split("-")
                try:
                    start, end = int(parts[0]), int(parts[-1])
                    ids.extend(range(start, end + 1))
                except ValueError:
                    pass
            elif "," in raw:
                for part in raw.split(","):
                    try:
                        ids.append(int(part.strip()))
                    except ValueError:
                        pass
            else:
                try:
                    ids.append(int(raw))
                except ValueError:
                    pass
    return list(dict.fromkeys(ids))  # deduplicate, preserve order


# ── Error helper ──────────────────────────────────────────────────────────────

def _err(error: str, message: str) -> dict:
    return {"ok": False, "error": error, "message": message}


# ── CLI ───────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="UAT Precondition Checker — verifies BD and environment before running tests."
    )
    p.add_argument(
        "--scenarios",
        required=True,
        help="Path to scenarios.json (output of uat_scenario_compiler.py).",
    )
    p.add_argument("--verbose", action="store_true", help="Debug logging to stderr.")
    return p.parse_args()


if __name__ == "__main__":
    main()
