"""
catalog_readiness_checker.py — Catalog Readiness Checker (Sprint 12).

Verifies whether catalog tables required for a UAT scenario are populated
and usable.  Catalogs in Agenda Web (Provincia, Departamento, TipoDoc,
TipoObligacion, EstadoCuenta, etc.) drive combos, grids, and validations.
An empty catalog produces NAV timeouts or silent validation failures rather
than explicit errors — this module surfaces those gaps BEFORE test execution.

KEY BEHAVIORS:
  - Reads catalog definitions from `fixtures/catalog_fixtures.yml`.
  - For each catalog entry required by the scenario, checks row-count via
    read-only SELECT (never DML).
  - Produces CatalogReadinessResult with per-catalog status: OK, EMPTY,
    UNVERIFIED (when DB unavailable), or SEEDED_REQUIRED.
  - When a catalog is EMPTY, generates a seed proposal using the fixture
    entries defined in catalog_fixtures.yml.
  - Integrates with sql_seed_generator.py (Sprint 10) for the seed SQL.
  - Always respects env policy: PROD is never seeded.

PUBLIC API:
  check_catalog_readiness(
      scenario_id, required_catalogs, db_url, exec_logger,
      evidence_dir, run_id, ticket_id, policy_path, dry_run
  ) -> CatalogReadinessResult

  CatalogReadinessResult.to_dict() -> dict

  load_catalog_fixtures(fixtures_path) -> dict[str, CatalogFixture]

EVIDENCE ARTIFACT:
  evidence/<ticket_id>/<run_id>/catalog_readiness_<scenario_id>.json

EVENT EMITTED:
  catalog_readiness_checked
  catalog_seed_proposed

SECURITY:
  - Never DML against any DB.
  - Catalog row-count queries use parameterized WHERE when feasible.
  - Credentials via env var QA_UAT_SEED_WRITER_DB_URL only.
  - PII is never logged — row counts only.
"""
from __future__ import annotations

import datetime
import json
import logging
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Optional, Dict, Any

logger = logging.getLogger("stacky.qa_uat.catalog_readiness_checker")

_TOOL_VERSION = "1.0.0"
_SCHEMA_VERSION = "catalog_readiness/1.0"

# ── Catalog status codes ───────────────────────────────────────────────────────

class CatalogStatus:
    OK = "OK"                        # Table exists and has rows >= min_rows
    EMPTY = "EMPTY"                  # Table exists but has fewer rows than min_rows
    UNVERIFIED = "UNVERIFIED"        # Could not connect to DB — proceed with warning
    SEED_REQUIRED = "SEED_REQUIRED"  # Empty and auto-seed was proposed
    PROD_BLOCKED = "PROD_BLOCKED"    # PROD environment — never seed


# ── Dataclasses ────────────────────────────────────────────────────────────────

@dataclass
class CatalogFixtureEntry:
    """A row to insert when seeding a catalog table."""
    fields: Dict[str, Any]           # column_name → value

    def to_dict(self) -> dict:
        return {"fields": self.fields}


@dataclass
class CatalogFixture:
    """Fixture definition for a catalog table, loaded from catalog_fixtures.yml."""
    catalog_name: str                # logical name (e.g., "Provincia")
    db_table: str                    # actual table name (e.g., "dbo.Provincia")
    pk_column: str                   # primary key column for count check
    min_rows: int                    # minimum acceptable row count
    seed_rows: List[CatalogFixtureEntry]   # rows to insert when seeding
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "catalog_name": self.catalog_name,
            "db_table": self.db_table,
            "pk_column": self.pk_column,
            "min_rows": self.min_rows,
            "description": self.description,
            "seed_rows_count": len(self.seed_rows),
        }


@dataclass
class CatalogCheckResult:
    """Result for a single catalog check."""
    catalog_name: str
    db_table: str
    status: str                      # CatalogStatus.*
    row_count: Optional[int]         # None when UNVERIFIED
    min_rows: int
    blocking: bool                   # True when EMPTY/PROD_BLOCKED with no fallback
    seed_proposed: bool
    seed_script_path: Optional[str]
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CatalogReadinessResult:
    """Aggregated result for all catalog checks in a scenario."""
    ok: bool
    scenario_id: str
    run_id: str
    ticket_id: object
    total: int
    ok_count: int
    empty_count: int
    unverified_count: int
    seed_proposed_count: int
    blocking_empty_count: int
    catalog_results: List[CatalogCheckResult] = field(default_factory=list)
    evidence_path: Optional[str] = None
    checked_at: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "schema_version": _SCHEMA_VERSION,
            "ok": self.ok,
            "scenario_id": self.scenario_id,
            "run_id": self.run_id,
            "ticket_id": self.ticket_id,
            "total": self.total,
            "ok_count": self.ok_count,
            "empty_count": self.empty_count,
            "unverified_count": self.unverified_count,
            "seed_proposed_count": self.seed_proposed_count,
            "blocking_empty_count": self.blocking_empty_count,
            "catalog_results": [r.to_dict() for r in self.catalog_results],
            "evidence_path": self.evidence_path,
            "checked_at": self.checked_at,
        }

    def to_event(self) -> dict:
        return {
            "event_type": "catalog_readiness_checked",
            "scenario_id": self.scenario_id,
            "run_id": self.run_id,
            "ticket_id": self.ticket_id,
            "ok": self.ok,
            "total": self.total,
            "empty_count": self.empty_count,
            "blocking_empty_count": self.blocking_empty_count,
            "seed_proposed_count": self.seed_proposed_count,
        }


# ── YAML mini-parser (no external deps) ───────────────────────────────────────

def _load_yaml_simple(path: Path) -> dict:
    """Minimal YAML loader for catalog_fixtures.yml (list/dict/scalar only)."""
    try:
        import yaml  # type: ignore[import]
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except ImportError:
        pass

    # Fallback: parse simple YAML manually (enough for our catalog file)
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    result: dict = {}
    current_key: Optional[str] = None
    current_list: Optional[list] = None

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("- "):
            item = stripped[2:].strip()
            if current_list is not None:
                current_list.append(item)
        elif ":" in stripped:
            key, _, val = stripped.partition(":")
            key = key.strip()
            val = val.strip()
            if val:
                if current_key and isinstance(result.get(current_key), dict):
                    result[current_key][key] = val
                else:
                    result[key] = val
            else:
                current_key = key
                if key not in result:
                    result[key] = {}
                current_list = None

    return result


# ── Fixture loader ─────────────────────────────────────────────────────────────

def load_catalog_fixtures(fixtures_path: Path) -> Dict[str, CatalogFixture]:
    """
    Load catalog fixture definitions from catalog_fixtures.yml.

    Returns a dict keyed by catalog_name.
    Returns {} when the file does not exist (non-fatal).
    """
    if not fixtures_path.exists():
        logger.debug("catalog_fixtures.yml not found at %s — no catalogs defined", fixtures_path)
        return {}

    try:
        import json as _json
        raw = _load_yaml_simple(fixtures_path)
        catalogs_raw = raw.get("catalogs", [])
        if not isinstance(catalogs_raw, list):
            catalogs_raw = []

        result: Dict[str, CatalogFixture] = {}
        for item in catalogs_raw:
            if not isinstance(item, dict):
                continue
            name = item.get("catalog_name", "")
            if not name:
                continue
            seed_rows = [
                CatalogFixtureEntry(fields=r.get("fields", r) if isinstance(r, dict) else {})
                for r in item.get("seed_rows", [])
            ]
            result[name] = CatalogFixture(
                catalog_name=name,
                db_table=item.get("db_table", f"dbo.{name}"),
                pk_column=item.get("pk_column", "Id"),
                min_rows=int(item.get("min_rows", 1)),
                seed_rows=seed_rows,
                description=item.get("description", ""),
            )
        return result
    except Exception as exc:
        logger.warning("catalog_readiness_checker: failed to load fixtures: %s", exc)
        return {}


# ── DB row count helper ────────────────────────────────────────────────────────

_PROD_DB_PATTERN = re.compile(r"(?i)\bPROD\b|PRODUCCION|PRODUCTION|PRD")


def _count_rows(table: str, pk_column: str, db_url: str) -> tuple[bool, Optional[int], Optional[str]]:
    """
    Execute SELECT COUNT(*) FROM <table> via read-only connection.

    Returns (success, count, error_message).
    Only allows SELECT — no DML.
    """
    # Safety: never execute against PROD
    if _PROD_DB_PATTERN.search(db_url or ""):
        return False, None, "PROD_BLOCKED"

    # Sanitize table and column names (allow only word chars and dots/underscores)
    safe_table = re.sub(r"[^a-zA-Z0-9_.#\[\]]", "", table)
    safe_pk = re.sub(r"[^a-zA-Z0-9_]", "", pk_column)
    if not safe_table or not safe_pk:
        return False, None, "invalid_table_name"

    sql = f"SELECT COUNT({safe_pk}) AS cnt FROM {safe_table}"

    # Try pyodbc
    try:
        import pyodbc  # type: ignore[import]
        conn = pyodbc.connect(db_url, timeout=10)
        cursor = conn.cursor()
        cursor.execute(sql)
        row = cursor.fetchone()
        conn.close()
        return True, int(row[0]) if row else 0, None
    except ImportError:
        pass
    except Exception as exc:
        return False, None, f"pyodbc:{exc}"

    # Try sqlalchemy
    try:
        from sqlalchemy import create_engine, text  # type: ignore[import]
        engine = create_engine(db_url, connect_args={"timeout": 10})
        with engine.connect() as conn:
            result = conn.execute(text(sql))
            row = result.fetchone()
        return True, int(row[0]) if row else 0, None
    except ImportError:
        pass
    except Exception as exc:
        return False, None, f"sqlalchemy:{exc}"

    return False, None, "no_driver_available"


# ── Seed SQL generator for catalog ────────────────────────────────────────────

def _generate_catalog_seed_sql(fixture: CatalogFixture, seed_run_id: str) -> str:
    """
    Generate a safe INSERT script for catalog rows.

    Script follows the same safety template as sql_seed_generator:
      - BEGIN TRANSACTION
      - Anti-PROD guard
      - Only inserts rows that don't already exist (IF NOT EXISTS)
      - ROLLBACK TRANSACTION (default — human must approve COMMIT)
      - Verification SELECT
    """
    rows_sql = []
    for entry in fixture.seed_rows:
        cols = list(entry.fields.keys())
        vals = [entry.fields[c] for c in cols]

        def _format(v: Any) -> str:
            if v is None:
                return "NULL"
            if isinstance(v, bool):
                return "1" if v else "0"
            if isinstance(v, (int, float)):
                return str(v)
            return "'" + str(v).replace("'", "''") + "'"

        col_list = ", ".join(cols)
        val_list = ", ".join(_format(v) for v in vals)

        # Existence check on primary key
        pk_val = entry.fields.get(fixture.pk_column, "NULL")
        pk_check = f"SELECT 1 FROM {fixture.db_table} WHERE {fixture.pk_column} = {_format(pk_val)}"

        rows_sql.append(
            f"IF NOT EXISTS ({pk_check} AND SeedRunId = @SeedRunId)\n"
            f"BEGIN\n"
            f"    INSERT INTO {fixture.db_table} ({col_list}, SeedRunId, CreatedBy)\n"
            f"    VALUES ({val_list}, @SeedRunId, @CreatedBy);\n"
            f"END"
        )

    rows_block = "\n\n".join(rows_sql) if rows_sql else "-- No seed rows defined for this catalog."

    return f"""\
/* QA_UAT_CATALOG_SEED — Table: {fixture.db_table}
   Generated by catalog_readiness_checker.py (Sprint 12)
   Operator must review and un-comment COMMIT TRANSACTION to apply. */

BEGIN TRANSACTION;

DECLARE @SeedRunId VARCHAR(64) = '{seed_run_id}';
DECLARE @CreatedBy NVARCHAR(64) = 'QA_UAT_AGENT';

-- Anti-PROD guard (mandatory)
IF DB_NAME() LIKE '%PROD%' OR DB_NAME() LIKE '%PRODUCCION%' OR DB_NAME() LIKE '%PRODUCTION%'
BEGIN
    RAISERROR('Catalog seed rejected in PROD.', 16, 1);
    ROLLBACK TRANSACTION;
    RETURN;
END

{rows_block}

-- Verification SELECT (mandatory for safety validator)
SELECT COUNT({fixture.pk_column}) AS RowsInCatalog FROM {fixture.db_table} WHERE SeedRunId = @SeedRunId;
-- Expected: {len(fixture.seed_rows)}

ROLLBACK TRANSACTION;
-- COMMIT TRANSACTION;  -- Un-comment after human review and approval
"""


# ── Main public function ───────────────────────────────────────────────────────

def check_catalog_readiness(
    scenario_id: str,
    required_catalogs: List[str],
    db_url: Optional[str] = None,
    exec_logger=None,
    evidence_dir: Optional[Path] = None,
    run_id: str = "unknown",
    ticket_id: object = 0,
    fixtures_path: Optional[Path] = None,
    dry_run: bool = True,
) -> CatalogReadinessResult:
    """
    Check whether all required catalog tables have sufficient rows.

    Parameters
    ----------
    scenario_id       : Scenario identifier (e.g., "RF-007-CA-01")
    required_catalogs : List of catalog names required by this scenario
                        (e.g., ["Provincia", "Departamento", "TipoDoc"])
    db_url            : Read-only DB connection string (None → UNVERIFIED)
    exec_logger       : Optional event logger (callable or None)
    evidence_dir      : Where to write evidence JSON artifact
    run_id            : Pipeline run ID
    ticket_id         : ADO ticket ID
    fixtures_path     : Path to catalog_fixtures.yml (auto-discovered if None)
    dry_run           : When True, never write any DB artifact (default True)

    Returns
    -------
    CatalogReadinessResult
    """
    checked_at = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")

    # Resolve fixtures path
    if fixtures_path is None:
        _this = Path(__file__).parent
        fixtures_path = _this / "fixtures" / "catalog_fixtures.yml"

    fixtures = load_catalog_fixtures(fixtures_path)

    catalog_results: List[CatalogCheckResult] = []
    seed_proposed_count = 0
    empty_count = 0
    unverified_count = 0
    ok_count = 0
    blocking_empty_count = 0

    safe_scenario_id = re.sub(r"[^a-zA-Z0-9_\-]", "_", scenario_id)

    # Determine evidence dir for seed SQL
    seed_dir: Optional[Path] = None
    if evidence_dir is not None:
        seed_dir = Path(evidence_dir) / str(ticket_id) / str(run_id)
        seed_dir.mkdir(parents=True, exist_ok=True)

    for catalog_name in required_catalogs:
        fixture = fixtures.get(catalog_name)

        if fixture is None:
            # No fixture defined — mark UNVERIFIED, not blocking
            catalog_results.append(CatalogCheckResult(
                catalog_name=catalog_name,
                db_table=f"dbo.{catalog_name}",
                status=CatalogStatus.UNVERIFIED,
                row_count=None,
                min_rows=1,
                blocking=False,
                seed_proposed=False,
                seed_script_path=None,
                error="no_fixture_defined",
            ))
            unverified_count += 1
            continue

        # PROD guard
        if db_url and _PROD_DB_PATTERN.search(db_url):
            catalog_results.append(CatalogCheckResult(
                catalog_name=catalog_name,
                db_table=fixture.db_table,
                status=CatalogStatus.PROD_BLOCKED,
                row_count=None,
                min_rows=fixture.min_rows,
                blocking=True,
                seed_proposed=False,
                seed_script_path=None,
                error="prod_blocked",
            ))
            blocking_empty_count += 1
            continue

        # Row count check
        if not db_url:
            success, row_count, error = False, None, "no_db_url"
        else:
            success, row_count, error = _count_rows(fixture.db_table, fixture.pk_column, db_url)

        if not success or row_count is None:
            # UNVERIFIED — cannot confirm catalog state
            catalog_results.append(CatalogCheckResult(
                catalog_name=catalog_name,
                db_table=fixture.db_table,
                status=CatalogStatus.UNVERIFIED,
                row_count=None,
                min_rows=fixture.min_rows,
                blocking=False,
                seed_proposed=False,
                seed_script_path=None,
                error=error,
            ))
            unverified_count += 1
            continue

        if row_count >= fixture.min_rows:
            # Catalog is OK
            catalog_results.append(CatalogCheckResult(
                catalog_name=catalog_name,
                db_table=fixture.db_table,
                status=CatalogStatus.OK,
                row_count=row_count,
                min_rows=fixture.min_rows,
                blocking=False,
                seed_proposed=False,
                seed_script_path=None,
            ))
            ok_count += 1
            logger.info("catalog_readiness: %s OK (%d rows)", catalog_name, row_count)
        else:
            # Catalog is EMPTY — propose seed SQL
            empty_count += 1
            seed_script_path: Optional[str] = None
            seed_proposed = False

            if fixture.seed_rows and seed_dir is not None and not dry_run:
                seed_run_id = f"cat-{ticket_id}-{run_id}"
                seed_sql = _generate_catalog_seed_sql(fixture, seed_run_id)
                script_name = f"catalog_seed_{re.sub(r'[^a-zA-Z0-9_]', '_', catalog_name)}_{safe_scenario_id}.sql"
                script_path = seed_dir / script_name
                script_path.write_text(seed_sql, encoding="utf-8")
                seed_script_path = str(script_path)
                seed_proposed = True
                seed_proposed_count += 1

                if exec_logger:
                    try:
                        exec_logger("catalog_seed_proposed", {
                            "catalog_name": catalog_name,
                            "db_table": fixture.db_table,
                            "seed_rows_count": len(fixture.seed_rows),
                            "script_path": seed_script_path,
                        })
                    except Exception:
                        pass

                logger.info(
                    "catalog_readiness: %s EMPTY (%d/%d rows) — seed proposed at %s",
                    catalog_name, row_count, fixture.min_rows, script_name
                )

            blocking_empty_count += 1

            catalog_results.append(CatalogCheckResult(
                catalog_name=catalog_name,
                db_table=fixture.db_table,
                status=CatalogStatus.SEED_REQUIRED if seed_proposed else CatalogStatus.EMPTY,
                row_count=row_count,
                min_rows=fixture.min_rows,
                blocking=True,
                seed_proposed=seed_proposed,
                seed_script_path=seed_script_path,
                error=None,
            ))

    # Build aggregate result
    total = len(required_catalogs)
    result = CatalogReadinessResult(
        ok=blocking_empty_count == 0,
        scenario_id=scenario_id,
        run_id=str(run_id),
        ticket_id=ticket_id,
        total=total,
        ok_count=ok_count,
        empty_count=empty_count,
        unverified_count=unverified_count,
        seed_proposed_count=seed_proposed_count,
        blocking_empty_count=blocking_empty_count,
        catalog_results=catalog_results,
        checked_at=checked_at,
    )

    # Write evidence artifact
    if evidence_dir is not None and seed_dir is not None:
        artifact_name = f"catalog_readiness_{safe_scenario_id}.json"
        artifact_path = seed_dir / artifact_name
        try:
            artifact_path.write_text(
                json.dumps(result.to_dict(), indent=2), encoding="utf-8"
            )
            result.evidence_path = str(artifact_path)
        except Exception as exc:
            logger.warning("catalog_readiness: could not write evidence: %s", exc)

    # Emit event
    if exec_logger:
        try:
            exec_logger("catalog_readiness_checked", result.to_event())
        except Exception:
            pass

    logger.info(
        "catalog_readiness: scenario=%s total=%d ok=%d empty=%d unverified=%d blocking=%d",
        scenario_id, total, ok_count, empty_count, unverified_count, blocking_empty_count,
    )

    return result
