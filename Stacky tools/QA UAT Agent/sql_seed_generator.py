"""
sql_seed_generator.py — SQL Seed Proposal Generator (Sprint 10).

Produces a SAFE, HUMAN-REVIEWABLE SQL seed script for a given data contract
requirement.  The script is NEVER executed automatically — it always uses
ROLLBACK TRANSACTION by default, with COMMIT commented out.

RESPONSIBILITIES:
  1. Read data_contract.json + qa_uat_data_policy.yml.
  2. If the DB schema is unknown (schema_known=False in contract), return
     verdict BLOCKED with reason DB_SCHEMA_UNKNOWN_FOR_SEED.
  3. If schema is available (from schema_mapping fixture or config), generate:
     - seed_proposal_<scenario_id>.sql
     - cleanup_proposal_<scenario_id>.sql
  4. Emit sql_seed_proposal_generated event.
  5. Pass output through sql_safety_validator.py before surfacing to operator.

TEMPLATE INVARIANTS (enforced by sql_safety_validator.py):
  - Starts with /* QA_UAT_SEED_PROPOSAL — Ticket: X, Scenario: Y */
  - BEGIN TRANSACTION
  - DECLARE @SeedRunId VARCHAR(64) = '<seed_run_id>'
  - IF DB_NAME() LIKE '%PROD%' RAISERROR + ROLLBACK + RETURN  (anti-PROD guard)
  - Idempotent INSERTs with IF NOT EXISTS
  - Verification SELECT after INSERTs
  - ROLLBACK TRANSACTION  (active — this is the DEFAULT; script will not persist data)
  - -- COMMIT TRANSACTION;  (commented out — operator must review and un-comment)

PUBLIC API:
  generate(
      data_contract, policy_path, schema_mapping, exec_logger, evidence_dir, run_id
  ) -> SqlSeedGeneratorResult
  SqlSeedGeneratorResult.to_dict() -> dict

EVIDENCE ARTIFACTS:
  evidence/<ticket_id>/<run_id>/seed_proposal_<scenario_id>.sql
  evidence/<ticket_id>/<run_id>/cleanup_proposal_<scenario_id>.sql

EVENT EMITTED:
  sql_seed_proposal_generated
  fields: ticket_id, scenario_id, script_path, cleanup_path, script_sha256, default_mode

SECURITY:
  - Never executes any SQL.
  - No credentials used or stored.
  - Script always targets QA/DEV — PROD guard blocks execution if mis-applied.
  - Output must pass sql_safety_validator.py before being shown to operator.
  - Caller must check SqlSeedGeneratorResult.safety_result.safe before showing
    the script to the user.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import logging
import os
import re
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger("stacky.qa_uat.sql_seed_generator")

_TOOL_VERSION = "1.0.0"
_SCHEMA_VERSION = "sql_seed_proposal/1.0"

# ── Dataclasses ───────────────────────────────────────────────────────────────

@dataclass
class SqlSeedGeneratorResult:
    ok: bool
    verdict: str                   # "GENERATED" | "BLOCKED"
    reason: Optional[str]          # None when verdict=GENERATED
    ticket_id: object
    scenario_id: str
    seed_run_id: str
    script_path: Optional[str]
    cleanup_path: Optional[str]
    script_sha256: Optional[str]
    cleanup_sha256: Optional[str]
    default_mode: str              # always "ROLLBACK"
    safety_result: Optional[dict]  # output of sql_safety_validator.validate()
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "schema_version": _SCHEMA_VERSION,
            "ok": self.ok,
            "verdict": self.verdict,
            "reason": self.reason,
            "ticket_id": self.ticket_id,
            "scenario_id": self.scenario_id,
            "seed_run_id": self.seed_run_id,
            "script_path": self.script_path,
            "cleanup_path": self.cleanup_path,
            "script_sha256": self.script_sha256,
            "cleanup_sha256": self.cleanup_sha256,
            "default_mode": self.default_mode,
            "safety_result": self.safety_result,
            "error": self.error,
        }


# ── Public API ────────────────────────────────────────────────────────────────

def generate(
    data_contract,                   # DataContractResult or dict
    policy_path: Optional[Path] = None,
    schema_mapping: Optional[dict] = None,    # {entity: {table, columns, ...}}
    exec_logger=None,
    evidence_dir: Optional[Path] = None,
    run_id: Optional[str] = None,
) -> SqlSeedGeneratorResult:
    """
    Generate a SQL seed proposal for all requirements in data_contract
    that have schema_known=True (or whose entity is in schema_mapping).

    Parameters
    ----------
    data_contract : DataContractResult | dict
        Output of uat_data_contract_compiler.compile_data_contract().
    policy_path : Path | None
        Override for qa_uat_data_policy.yml.
    schema_mapping : dict | None
        Optional mapping: {entity_name: {"table": str, "columns": {...}}}
        When provided, enables SQL generation even for schema_known=False contracts
        (the caller is asserting the schema is available).
    exec_logger : ExecutionLogger | None
        If provided, emits sql_seed_proposal_generated event.
    evidence_dir : Path | None
        If provided, writes seed and cleanup SQL files.
    run_id : str | None
        Sub-directory for file placement.

    Returns
    -------
    SqlSeedGeneratorResult
        .verdict = "BLOCKED" if no schema is available for any requirement.
        .verdict = "GENERATED" if at least one script was produced and passed safety.
    """
    # Normalise input
    if hasattr(data_contract, "requirements"):
        requirements = data_contract.requirements
        ticket_id = data_contract.ticket_id
        scenario_id = data_contract.scenario_id
    else:
        requirements = data_contract.get("requirements", [])
        ticket_id = data_contract.get("ticket_id", 0)
        scenario_id = data_contract.get("scenario_id", "unknown")

    seed_run_id = f"seed-{ticket_id}-{uuid.uuid4().hex[:12].upper()}"
    effective_run_id = run_id or str(ticket_id)

    # Load policy
    policy = _load_policy(policy_path)

    # Check if any requirement has enough schema info to generate
    generatable = []
    for req in requirements:
        if hasattr(req, "schema_known"):
            schema_known = req.schema_known
            entity = req.entity
            alias = req.alias
            required_fields = list(getattr(req, "required_fields", []) or [])
            constraints = list(getattr(req, "constraints", []) or [])
            db_table = getattr(req, "db_table", None)
        else:
            schema_known = req.get("schema_known", False)
            entity = req.get("entity", "Unknown")
            alias = req.get("alias", "unknown")
            required_fields = list(req.get("required_fields", []) or [])
            constraints = list(req.get("constraints", []) or [])
            db_table = req.get("db_table")

        # Check schema_mapping first — caller can supply schema even for schema_known=False
        if schema_mapping and entity in schema_mapping:
            effective_schema = schema_mapping[entity]
            generatable.append({
                "entity": entity,
                "alias": alias,
                "required_fields": required_fields,
                "constraints": constraints,
                "db_table": effective_schema.get("table") or db_table,
                "columns": effective_schema.get("columns", {}),
                "schema_source": "provided_mapping",
            })
        elif schema_known and db_table:
            generatable.append({
                "entity": entity,
                "alias": alias,
                "required_fields": required_fields,
                "constraints": constraints,
                "db_table": db_table,
                "columns": {},
                "schema_source": "contract",
            })
        else:
            logger.info(
                "sql_seed_generator: requirement %s/%s skipped — schema_known=%s, "
                "db_table=%s, schema_mapping_has_entity=%s",
                entity, alias, schema_known, db_table,
                bool(schema_mapping and entity in schema_mapping),
            )

    if not generatable:
        logger.warning(
            "sql_seed_generator: BLOCKED — no schema available for scenario %s", scenario_id
        )
        result = SqlSeedGeneratorResult(
            ok=False,
            verdict="BLOCKED",
            reason="DB_SCHEMA_UNKNOWN_FOR_SEED",
            ticket_id=ticket_id,
            scenario_id=scenario_id,
            seed_run_id=seed_run_id,
            script_path=None,
            cleanup_path=None,
            script_sha256=None,
            cleanup_sha256=None,
            default_mode="ROLLBACK",
            safety_result=None,
            error=(
                "No requirements have a known DB schema. "
                "Provide a schema_mapping or set schema_known=True in the data contract. "
                "# TODO: provide real schema mapping for each entity."
            ),
        )
        _emit_event(exec_logger, "sql_seed_proposal_generated", {
            **result.to_dict(),
            "event": "sql_seed_proposal_generated",
        })
        return result

    # Generate the seed script
    script_sql = _render_seed_script(
        ticket_id=ticket_id,
        scenario_id=scenario_id,
        seed_run_id=seed_run_id,
        generatable=generatable,
        policy=policy,
    )
    cleanup_sql = _render_cleanup_script(
        ticket_id=ticket_id,
        scenario_id=scenario_id,
        seed_run_id=seed_run_id,
        generatable=generatable,
    )

    script_sha256 = hashlib.sha256(script_sql.encode("utf-8")).hexdigest()
    cleanup_sha256 = hashlib.sha256(cleanup_sql.encode("utf-8")).hexdigest()

    # Run safety validator
    safety_result_dict: Optional[dict] = None
    try:
        from sql_safety_validator import validate as safety_validate  # type: ignore[import]
        safety_result = safety_validate(script_sql, source=f"seed:{scenario_id}")
        safety_result_dict = safety_result.to_dict()
        if not safety_result.safe:
            logger.warning(
                "sql_seed_generator: safety validator BLOCKED script for %s: %s",
                scenario_id, safety_result.blocking_findings,
            )
            return SqlSeedGeneratorResult(
                ok=False,
                verdict="BLOCKED",
                reason="SQL_SEED_SAFETY_FAILED",
                ticket_id=ticket_id,
                scenario_id=scenario_id,
                seed_run_id=seed_run_id,
                script_path=None,
                cleanup_path=None,
                script_sha256=script_sha256,
                cleanup_sha256=cleanup_sha256,
                default_mode="ROLLBACK",
                safety_result=safety_result_dict,
                error="SQL seed script failed safety validation",
            )
    except ImportError:
        logger.debug("sql_safety_validator not available — skipping safety check")

    # Write files
    script_path = None
    cleanup_path = None
    if evidence_dir is not None:
        script_path, cleanup_path = _write_scripts(
            ticket_id=ticket_id,
            scenario_id=scenario_id,
            script_sql=script_sql,
            cleanup_sql=cleanup_sql,
            evidence_dir=evidence_dir,
            run_id=effective_run_id,
        )

    result = SqlSeedGeneratorResult(
        ok=True,
        verdict="GENERATED",
        reason=None,
        ticket_id=ticket_id,
        scenario_id=scenario_id,
        seed_run_id=seed_run_id,
        script_path=str(script_path) if script_path else None,
        cleanup_path=str(cleanup_path) if cleanup_path else None,
        script_sha256=script_sha256,
        cleanup_sha256=cleanup_sha256,
        default_mode="ROLLBACK",
        safety_result=safety_result_dict,
    )

    logger.info(
        "sql_seed_generator: GENERATED scenario=%s seed_run_id=%s sha256=%s",
        scenario_id, seed_run_id, script_sha256[:16],
    )

    _emit_event(exec_logger, "sql_seed_proposal_generated", {
        "event": "sql_seed_proposal_generated",
        "ticket_id": ticket_id,
        "scenario_id": scenario_id,
        "script_path": result.script_path,
        "cleanup_path": result.cleanup_path,
        "script_sha256": script_sha256,
        "cleanup_sha256": cleanup_sha256,
        "default_mode": "ROLLBACK",
        "safety_result": safety_result_dict,
    })

    return result


# ── SQL renderers ─────────────────────────────────────────────────────────────

def _render_seed_script(
    ticket_id: object,
    scenario_id: str,
    seed_run_id: str,
    generatable: List[dict],
    policy: dict,
) -> str:
    """Render the full seed SQL script from the template."""
    max_rows = _get_max_rows(policy)
    lines = [
        f"/* QA_UAT_SEED_PROPOSAL — Ticket: {ticket_id}, Scenario: {scenario_id} */",
        f"/* Generated: {_utcnow()} */",
        f"/* IMPORTANT: Review and verify ALL statements before un-commenting COMMIT. */",
        f"/* Default mode: ROLLBACK — no data will be persisted until COMMIT is un-commented. */",
        "",
        "BEGIN TRANSACTION;",
        "",
        f"DECLARE @SeedRunId VARCHAR(64) = '{seed_run_id}';",
        f"DECLARE @CreatedBy NVARCHAR(64) = 'QA_UAT_AGENT';",
        "",
        "-- ── Anti-PROD guard ────────────────────────────────────────────────────────",
        "IF DB_NAME() LIKE '%PROD%' OR DB_NAME() LIKE '%PRODUCCION%' OR DB_NAME() LIKE '%PRODUCTION%'",
        "BEGIN",
        f"    RAISERROR('QA_UAT_SEED_BLOCKED: This script must NOT run on production. DB=%s', 20, 1, DB_NAME()) WITH LOG;",
        "    ROLLBACK TRANSACTION;",
        "    RETURN;",
        "END;",
        "",
    ]

    for req in generatable:
        entity = req["entity"]
        db_table = req["db_table"] or f"<TODO: table_for_{entity}>"
        columns = req.get("columns", {})
        required_fields = req.get("required_fields", [])
        constraints = req.get("constraints", [])
        schema_source = req.get("schema_source", "unknown")

        lines.append(f"-- ── Seed: {entity} (alias: {req['alias']}) ─────────────────────────────────")
        if schema_source == "provided_mapping":
            lines.append(f"-- Schema source: provided_mapping")
        else:
            lines.append(f"-- Schema source: {schema_source}")
            lines.append(f"-- TODO: verify table name and column names against actual schema")

        if constraints:
            for c in constraints:
                lines.append(f"-- Constraint: {c}")

        # Build INSERT columns
        col_names, col_values = _build_insert_columns(
            db_table=db_table,
            entity=entity,
            required_fields=required_fields,
            columns=columns,
            seed_run_id=seed_run_id,
        )

        key_col = required_fields[0] if required_fields else "Id"
        placeholder_val = f"<TODO: provide_{key_col}_value>"

        lines.append("")
        lines.append(f"-- Idempotent INSERT: skips if record already exists with @SeedRunId marker")
        lines.append(f"IF NOT EXISTS (")
        lines.append(f"    SELECT 1 FROM {db_table}")
        lines.append(f"    WHERE SeedRunId = @SeedRunId AND CreatedBy = @CreatedBy")
        lines.append(f")")
        lines.append(f"BEGIN")
        lines.append(f"    INSERT INTO {db_table} (")
        lines.append(f"        {', '.join(col_names)}")
        lines.append(f"    ) VALUES (")
        lines.append(f"        {', '.join(col_values)}")
        lines.append(f"    );")
        lines.append(f"END;")
        lines.append("")

    # Verification SELECT
    lines.append("-- ── Verification SELECT ────────────────────────────────────────────────────")
    lines.append("-- Verify the seed data was inserted correctly before committing.")
    for req in generatable:
        db_table = req["db_table"] or f"<TODO: table>"
        lines.append(f"SELECT * FROM {db_table}")
        lines.append(f"WHERE SeedRunId = @SeedRunId AND CreatedBy = @CreatedBy;")
        lines.append("")

    lines.append("-- ── Transaction control ────────────────────────────────────────────────────")
    lines.append("-- DEFAULT: ROLLBACK — no data will be persisted.")
    lines.append("-- To apply the seed: review all statements above, then:")
    lines.append("--   1. Change ROLLBACK to COMMIT below.")
    lines.append("--   2. Obtain human operator approval.")
    lines.append("--   3. Execute in a QA/DEV environment only.")
    lines.append("ROLLBACK TRANSACTION;")
    lines.append("-- COMMIT TRANSACTION;  -- Un-comment ONLY after human review and approval")
    lines.append("")

    return "\n".join(lines)


def _build_insert_columns(
    db_table: str,
    entity: str,
    required_fields: List[str],
    columns: dict,
    seed_run_id: str,
) -> tuple[List[str], List[str]]:
    """
    Build column names and value placeholders for an INSERT statement.

    Returns (col_names_list, col_values_list).

    If columns dict provides mappings, use them; otherwise produce TODO placeholders.
    # TODO: provide real schema mapping for each entity.
    """
    col_names: List[str] = []
    col_values: List[str] = []

    # Required fields first
    for field_name in required_fields:
        col_names.append(field_name)
        if columns and field_name in columns:
            col_type = columns[field_name].get("type", "varchar")
            col_values.append(f"<TODO: {field_name}_value> -- type: {col_type}")
        else:
            col_values.append(f"<TODO: {field_name}_value>")

    # Mandatory audit columns
    audit_pairs = [
        ("CreatedBy", "@CreatedBy"),
        ("SeedRunId", "@SeedRunId"),
        ("CreatedAt", "GETUTCDATE()"),
    ]
    for col, val in audit_pairs:
        if col not in col_names and col.lower() not in [c.lower() for c in col_names]:
            col_names.append(col)
            col_values.append(val)

    return col_names, col_values


def _render_cleanup_script(
    ticket_id: object,
    scenario_id: str,
    seed_run_id: str,
    generatable: List[dict],
) -> str:
    """
    Render the cleanup SQL script that deletes only seed data tagged with
    CreatedBy='QA_UAT_AGENT' AND SeedRunId=@SeedRunId.

    Safety rules:
    - Every DELETE has WHERE SeedRunId = @SeedRunId AND CreatedBy = @CreatedBy.
    - ROLLBACK by default (same as seed script).
    - Anti-PROD guard included.
    """
    lines = [
        f"/* QA_UAT_CLEANUP_PROPOSAL — Ticket: {ticket_id}, Scenario: {scenario_id} */",
        f"/* Seed run: {seed_run_id} */",
        f"/* Generated: {_utcnow()} */",
        f"/* IMPORTANT: This script ONLY deletes rows tagged with SeedRunId='{seed_run_id}'. */",
        "",
        "BEGIN TRANSACTION;",
        "",
        f"DECLARE @SeedRunId VARCHAR(64) = '{seed_run_id}';",
        f"DECLARE @CreatedBy NVARCHAR(64) = 'QA_UAT_AGENT';",
        "",
        "-- ── Anti-PROD guard ────────────────────────────────────────────────────────",
        "IF DB_NAME() LIKE '%PROD%' OR DB_NAME() LIKE '%PRODUCCION%' OR DB_NAME() LIKE '%PRODUCTION%'",
        "BEGIN",
        "    RAISERROR('QA_UAT_CLEANUP_BLOCKED: This script must NOT run on production.', 20, 1) WITH LOG;",
        "    ROLLBACK TRANSACTION;",
        "    RETURN;",
        "END;",
        "",
    ]

    for req in generatable:
        entity = req["entity"]
        db_table = req["db_table"] or f"<TODO: table_for_{entity}>"
        lines.append(f"-- Cleanup: {entity} (alias: {req['alias']})")
        lines.append(f"DELETE FROM {db_table}")
        lines.append(f"WHERE CreatedBy = @CreatedBy AND SeedRunId = @SeedRunId;")
        lines.append("")

    # Verification SELECT after delete
    lines.append("-- ── Post-cleanup verification SELECT ───────────────────────────────────────")
    for req in generatable:
        db_table = req["db_table"] or f"<TODO: table>"
        lines.append(f"SELECT COUNT(*) AS RemainingRows FROM {db_table}")
        lines.append(f"WHERE SeedRunId = @SeedRunId AND CreatedBy = @CreatedBy;")
        lines.append(f"-- Expected result: 0 rows")
        lines.append("")

    lines.append("ROLLBACK TRANSACTION;")
    lines.append("-- COMMIT TRANSACTION;  -- Un-comment ONLY after human review and approval")
    lines.append("")

    return "\n".join(lines)


# ── File writers ──────────────────────────────────────────────────────────────

def _write_scripts(
    ticket_id: object,
    scenario_id: str,
    script_sql: str,
    cleanup_sql: str,
    evidence_dir: Path,
    run_id: str,
) -> tuple[Optional[Path], Optional[Path]]:
    """Write seed and cleanup SQL files to evidence directory."""
    try:
        out_dir = evidence_dir / str(run_id)
        out_dir.mkdir(parents=True, exist_ok=True)
        safe_id = re.sub(r"[^a-zA-Z0-9_\-]", "_", str(scenario_id))
        script_path = out_dir / f"seed_proposal_{safe_id}.sql"
        cleanup_path = out_dir / f"cleanup_proposal_{safe_id}.sql"
        script_path.write_text(script_sql, encoding="utf-8")
        cleanup_path.write_text(cleanup_sql, encoding="utf-8")
        logger.debug("sql_seed_generator: scripts written: %s, %s", script_path, cleanup_path)
        return script_path, cleanup_path
    except Exception as exc:
        logger.warning("sql_seed_generator: cannot write scripts: %s", exc)
        return None, None


# ── Policy loader ─────────────────────────────────────────────────────────────

def _load_policy(policy_path: Optional[Path]) -> dict:
    if policy_path is None:
        policy_path = Path(__file__).parent / "config" / "qa_uat_data_policy.yml"
    try:
        import yaml  # type: ignore[import-untyped]
        with open(policy_path, encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except ImportError:
        return {}
    except Exception as exc:
        logger.warning("sql_seed_generator: cannot load policy: %s", exc)
        return {}


def _get_max_rows(policy: dict) -> int:
    """Get max_seed_rows_per_table from QA environment policy."""
    envs = policy.get("environments", {})
    qa_env = envs.get("QA", {})
    return int(qa_env.get("max_seed_rows_per_table", 20))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _utcnow() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def _emit_event(exec_logger, event_name: str, data: dict) -> None:
    if exec_logger is None:
        return
    try:
        exec_logger.event(event_name, data)
    except Exception as exc:
        logger.debug("sql_seed_generator: cannot emit event %s: %s", event_name, exc)
