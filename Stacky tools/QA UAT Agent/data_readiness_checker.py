"""
data_readiness_checker.py — UAT Data Readiness Checker (Sprint 8b).

Takes a compiled DataContract and verifies whether the required data exists and
is ready for the UAT scenario to execute.  If data is missing, it returns
structured resolution_options so the downstream Data Resolution Broker
(Sprint 9) or the human operator knows exactly what actions are available.

KEY DIFFERENCE from uat_precondition_checker.py (Sprint 3):
  - Sprint 3 checker: verifies existing preconditions in scenarios.json (grid/record/user).
  - This module: verifies requirements from the NEW DataContract (Sprint 8b),
    produces resolution_options per missing requirement, and plugs into the new
    DATA_MISSING → resolution flow described in Roadmap v2.0.

PRINCIPLES:
  - Strictly READ-ONLY: never executes DML against any DB.
  - NEVER returns PII in artifacts — resolved_data fields are masked before logging.
  - When DB is unavailable, marks status as UNVERIFIED (not BLOCKED) —
    the pipeline may still proceed; the runner will discover the issue.
  - Produces resolution_options for every missing requirement:
    ASK_USER_FOR_VALUE, RUN_DISCOVERY_QUERY, GENERATE_SQL_SEED, MARK_MANUAL_REVIEW.

PUBLIC API:
  check_readiness(contract: DataContractResult, ...) -> DataReadinessCheckResult
  DataReadinessCheckResult.to_dict() -> dict
  DataReadinessCheckResult.to_event() -> dict

EVIDENCE ARTIFACT:
  evidence/<ticket_id>/<run_id>/data_readiness_v2.json  (schema data_readiness_v2/1.0)

EVENT EMITTED:
  event: data_readiness_v2_checked
  fields: scenario_id, ready, missing_count, blocking_missing_count, resolution_options
"""
from __future__ import annotations

import datetime
import json
import logging
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger("stacky.qa_uat.data_readiness_checker")

_TOOL_VERSION = "1.0.0"
_SCHEMA_VERSION = "data_readiness_v2/1.0"

# ── Resolution option codes ───────────────────────────────────────────────────

class ResolutionOption:
    ASK_USER_FOR_VALUE = "ASK_USER_FOR_VALUE"
    RUN_DISCOVERY_QUERY = "RUN_DISCOVERY_QUERY"
    GENERATE_SQL_SEED = "GENERATE_SQL_SEED"
    MARK_MANUAL_REVIEW = "MARK_MANUAL_REVIEW"


# Reason codes for missing data
class MissingReason:
    NO_CLIENT_WITH_ACTIVE_OBLIGATIONS = "NO_CLIENT_WITH_ACTIVE_OBLIGATIONS"
    GRID_EMPTY = "GRID_EMPTY"
    CATALOG_EMPTY = "CATALOG_EMPTY"
    TEST_ENTITY_NOT_FOUND = "TEST_ENTITY_NOT_FOUND"
    DB_UNAVAILABLE = "DB_UNAVAILABLE"
    SCHEMA_UNKNOWN = "SCHEMA_UNKNOWN"
    NO_CANDIDATE_DATA_FOUND = "NO_CANDIDATE_DATA_FOUND"
    USER_DATA_REQUIRED = "USER_DATA_REQUIRED"
    RIDIOMA_SCRIPT_MISSING = "RIDIOMA_SCRIPT_MISSING"


# ── Resolution option rules ───────────────────────────────────────────────────
#
# Maps (entity, reason) → ordered list of resolution options.
# More specific rules override generic ones (entity takes priority).

_RESOLUTION_RULES: dict[tuple[str, str], list[str]] = {
    # Entities where SQL seed is permitted and useful
    ("Obligacion", MissingReason.GRID_EMPTY): [
        ResolutionOption.ASK_USER_FOR_VALUE,
        ResolutionOption.RUN_DISCOVERY_QUERY,
        ResolutionOption.GENERATE_SQL_SEED,
    ],
    ("Obligacion", MissingReason.NO_CANDIDATE_DATA_FOUND): [
        ResolutionOption.ASK_USER_FOR_VALUE,
        ResolutionOption.RUN_DISCOVERY_QUERY,
        ResolutionOption.GENERATE_SQL_SEED,
    ],
    ("Obligacion", MissingReason.NO_CLIENT_WITH_ACTIVE_OBLIGATIONS): [
        ResolutionOption.ASK_USER_FOR_VALUE,
        ResolutionOption.RUN_DISCOVERY_QUERY,
        ResolutionOption.GENERATE_SQL_SEED,
    ],
    ("Cliente", MissingReason.TEST_ENTITY_NOT_FOUND): [
        ResolutionOption.ASK_USER_FOR_VALUE,
        ResolutionOption.RUN_DISCOVERY_QUERY,
        ResolutionOption.GENERATE_SQL_SEED,
    ],
    ("Lote", MissingReason.TEST_ENTITY_NOT_FOUND): [
        ResolutionOption.ASK_USER_FOR_VALUE,
        ResolutionOption.RUN_DISCOVERY_QUERY,
    ],
    ("Catalogo", MissingReason.CATALOG_EMPTY): [
        ResolutionOption.RUN_DISCOVERY_QUERY,
        ResolutionOption.GENERATE_SQL_SEED,
        ResolutionOption.MARK_MANUAL_REVIEW,
    ],
    ("RidiomaScript", MissingReason.RIDIOMA_SCRIPT_MISSING): [
        ResolutionOption.MARK_MANUAL_REVIEW,
    ],
    # Generic fallback for unknown schema — cannot auto-seed
    ("__schema_unknown__", MissingReason.SCHEMA_UNKNOWN): [
        ResolutionOption.ASK_USER_FOR_VALUE,
        ResolutionOption.MARK_MANUAL_REVIEW,
    ],
    # User/permission entities — DB seed not appropriate
    ("UsuarioQA", MissingReason.USER_DATA_REQUIRED): [
        ResolutionOption.ASK_USER_FOR_VALUE,
        ResolutionOption.MARK_MANUAL_REVIEW,
    ],
    # Generic DB unavailable
    ("__any__", MissingReason.DB_UNAVAILABLE): [
        ResolutionOption.MARK_MANUAL_REVIEW,
    ],
}

_GENERIC_RESOLUTION_OPTIONS = [
    ResolutionOption.ASK_USER_FOR_VALUE,
    ResolutionOption.RUN_DISCOVERY_QUERY,
    ResolutionOption.MARK_MANUAL_REVIEW,
]


# ── Dataclasses ──────────────────────────────────────────────────────────────

@dataclass
class MissingRequirement:
    """A data requirement that could not be satisfied."""
    requirement_id: str
    entity: str
    alias: str
    reason: str
    blocking: bool
    resolution_options: List[str]
    db_table: Optional[str] = None
    schema_known: bool = False
    notes: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ResolvedRequirement:
    """A data requirement that was successfully verified."""
    requirement_id: str
    entity: str
    alias: str
    source: str              # "live_db_readonly" | "user_input" | "unverified"
    resolved_fields: dict = field(default_factory=dict)   # MASKED before persistence
    confidence: float = 1.0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DataReadinessCheckResult:
    """Result of check_readiness() for a single scenario's data contract."""
    ready: bool
    scenario_id: str
    ticket_id: object
    checked_at: str
    missing: List[MissingRequirement]
    resolved: List[ResolvedRequirement]
    decision: str              # "READY" | "MISSING" | "UNVERIFIED"
    blocking_missing_count: int
    artifact_path: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "schema_version": _SCHEMA_VERSION,
            "ready": self.ready,
            "scenario_id": self.scenario_id,
            "ticket_id": self.ticket_id,
            "checked_at": self.checked_at,
            "decision": self.decision,
            "missing": [m.to_dict() for m in self.missing],
            "resolved": [r.to_dict() for r in self.resolved],
            "blocking_missing_count": self.blocking_missing_count,
            "artifact_path": self.artifact_path,
        }

    def to_event(self) -> dict:
        """Produce the data_readiness_v2_checked event dict for execution.jsonl."""
        return {
            "event": "data_readiness_v2_checked",
            "scenario_id": self.scenario_id,
            "ticket_id": self.ticket_id,
            "ready": self.ready,
            "decision": self.decision,
            "missing_count": len(self.missing),
            "blocking_missing_count": self.blocking_missing_count,
            "resolved_count": len(self.resolved),
            "resolution_options_by_entity": {
                m.entity: m.resolution_options
                for m in self.missing
            },
            "artifact_path": self.artifact_path,
        }


# ── Public API ────────────────────────────────────────────────────────────────

def check_readiness(
    contract,   # DataContractResult from uat_data_contract_compiler
    exec_logger=None,
    evidence_dir: Optional[Path] = None,
    run_id: Optional[str] = None,
    _db_connector=None,      # injectable for testing
) -> DataReadinessCheckResult:
    """
    Check whether the data requirements in the given contract are satisfied.

    Parameters
    ----------
    contract : DataContractResult
        Output of uat_data_contract_compiler.compile_data_contract().
    exec_logger : ExecutionLogger | None
        If provided, emits data_readiness_v2_checked event.
    evidence_dir : Path | None
        If provided, writes data_readiness_v2.json artifact.
    run_id : str | None
        Sub-directory for artifact placement.
    _db_connector : callable | None
        Injectable DB connector factory (for unit tests; never used in DML).

    Returns
    -------
    DataReadinessCheckResult
        .ready = True when ALL blocking requirements are satisfied or unverifiable.
        .missing = list of MissingRequirement (only blocking ones affect .ready).
        .decision = "READY" | "MISSING" | "UNVERIFIED"
    """
    from uat_data_contract_compiler import DataContractResult
    if not isinstance(contract, DataContractResult):
        # Accept raw dict (e.g. loaded from artifact)
        contract = _dict_to_contract(contract)

    checked_at = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
    missing: List[MissingRequirement] = []
    resolved: List[ResolvedRequirement] = []

    for req in contract.requirements:
        check_outcome = _check_single_requirement(req, _db_connector)
        if check_outcome["status"] == "resolved":
            resolved.append(ResolvedRequirement(
                requirement_id=req.requirement_id,
                entity=req.entity,
                alias=req.alias,
                source=check_outcome["source"],
                resolved_fields=_mask_pii(check_outcome.get("resolved_fields", {})),
                confidence=check_outcome.get("confidence", 1.0),
            ))
        elif check_outcome["status"] == "unverified":
            # DB unavailable — mark as unverified, not missing (don't block)
            resolved.append(ResolvedRequirement(
                requirement_id=req.requirement_id,
                entity=req.entity,
                alias=req.alias,
                source="unverified",
                resolved_fields={},
                confidence=0.0,
            ))
            logger.debug(
                "data_readiness_v2: requirement %s unverified (DB unavailable)",
                req.requirement_id,
            )
        else:
            # missing
            reason = check_outcome.get("reason", MissingReason.NO_CANDIDATE_DATA_FOUND)
            resolution_opts = _get_resolution_options(req.entity, reason, req.schema_known)
            missing.append(MissingRequirement(
                requirement_id=req.requirement_id,
                entity=req.entity,
                alias=req.alias,
                reason=reason,
                blocking=req.blocking,
                resolution_options=resolution_opts,
                db_table=req.db_table,
                schema_known=req.schema_known,
                notes=req.notes,
            ))

    blocking_missing = [m for m in missing if m.blocking]
    blocking_missing_count = len(blocking_missing)

    if blocking_missing_count > 0:
        decision = "MISSING"
        ready = False
    elif len(missing) > 0:
        # Non-blocking missing: still ready to proceed, warn
        decision = "READY"
        ready = True
    else:
        # Check if any were unverified
        unverified = [r for r in resolved if r.source == "unverified"]
        if unverified and len(unverified) == len(contract.requirements):
            decision = "UNVERIFIED"
        else:
            decision = "READY"
        ready = True

    result = DataReadinessCheckResult(
        ready=ready,
        scenario_id=contract.scenario_id,
        ticket_id=contract.ticket_id,
        checked_at=checked_at,
        missing=missing,
        resolved=resolved,
        decision=decision,
        blocking_missing_count=blocking_missing_count,
    )

    # Write artifact
    artifact_path = _write_artifact(result, evidence_dir, run_id, contract.scenario_id)
    if artifact_path:
        result.artifact_path = str(artifact_path)

    # Emit event
    _emit_event(exec_logger, result)

    if decision == "MISSING":
        logger.warning(
            "data_readiness_v2 MISSING: scenario=%s blocking=%d options=%s",
            contract.scenario_id,
            blocking_missing_count,
            [m.resolution_options for m in blocking_missing],
        )
    else:
        logger.info(
            "data_readiness_v2 %s: scenario=%s resolved=%d",
            decision, contract.scenario_id, len(resolved),
        )

    return result


# ── Single-requirement checker ────────────────────────────────────────────────

def _check_single_requirement(
    req,  # DataRequirement
    _db_connector=None,
) -> dict:
    """
    Check a single data requirement.  Returns:
      {"status": "resolved", "source": "live_db_readonly"|"unverified", "confidence": ...}
      {"status": "unverified"}
      {"status": "missing", "reason": "<reason_code>"}

    STRICTLY READ-ONLY.  No DML ever executed here.
    """
    entity = req.entity
    db_table = req.db_table
    schema_known = req.schema_known
    candidate_sources = req.candidate_sources

    # If user_input is the only source — always missing (must be provided by user)
    if candidate_sources == ["user_input"]:
        return {"status": "missing", "reason": MissingReason.USER_DATA_REQUIRED}

    # If schema unknown — cannot auto-verify, mark as schema-unknown missing
    if not schema_known and "live_db_readonly" in candidate_sources:
        return {"status": "missing", "reason": MissingReason.SCHEMA_UNKNOWN}

    # If no DB table known — unverified
    if not db_table:
        return {"status": "unverified"}

    # Try DB check
    conn = _get_connection(_db_connector)
    if conn is None:
        return {"status": "unverified"}

    try:
        count = _query_count(conn, db_table)
        if count is None:
            return {"status": "unverified"}
        if count == 0:
            reason = MissingReason.GRID_EMPTY if entity in ("Obligacion",) else MissingReason.TEST_ENTITY_NOT_FOUND
            return {"status": "missing", "reason": reason}
        return {
            "status": "resolved",
            "source": "live_db_readonly",
            "confidence": 0.9,
            "resolved_fields": {},
        }
    except Exception as exc:
        logger.warning("data_readiness_v2: DB check error for %s: %s", entity, exc)
        return {"status": "unverified"}
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _query_count(conn, table: str) -> Optional[int]:
    """SELECT COUNT(*) FROM table (read-only). Returns None on error."""
    # Security: table comes from DataRequirement.db_table (compiler-internal, not user input)
    safe_table = re.sub(r"[^A-Za-z0-9_]", "", table)
    if not safe_table:
        return None
    try:
        cursor = conn.cursor()
        cursor.execute(f"SELECT COUNT(*) FROM {safe_table}")  # nosec
        row = cursor.fetchone()
        cursor.close()
        return int(row[0]) if row else 0
    except Exception as exc:
        logger.warning("data_readiness_v2: COUNT query error for %s: %s", table, exc)
        return None


def _get_connection(_db_connector=None):
    """Get a read-only DB connection. Returns None if unavailable."""
    if _db_connector is not None:
        try:
            return _db_connector()
        except Exception:
            return None
    # Check env vars
    _DB_ENV_VARS = ("RS_QA_DB_USER", "RS_QA_DB_PASS", "RS_QA_DB_DSN")
    missing = [v for v in _DB_ENV_VARS if not os.getenv(v)]
    if missing:
        return None
    try:
        import importlib
        pyodbc = importlib.import_module("pyodbc")
        dsn = os.environ["RS_QA_DB_DSN"]
        user = os.environ["RS_QA_DB_USER"]
        password = os.environ["RS_QA_DB_PASS"]
        conn_str = f"{dsn};UID={user};PWD={password};ApplicationIntent=ReadOnly"
        conn = pyodbc.connect(conn_str, timeout=10)
        conn.autocommit = True
        return conn
    except Exception as exc:
        logger.warning("data_readiness_v2: cannot connect to DB: %s", exc)
        return None


# ── Resolution options lookup ─────────────────────────────────────────────────

def _get_resolution_options(entity: str, reason: str, schema_known: bool) -> List[str]:
    """
    Return the ordered list of resolution options for a missing requirement.

    Lookup order:
      1. Exact (entity, reason) match
      2. Schema-unknown generic
      3. Generic fallback
    """
    # Exact match
    opts = _RESOLUTION_RULES.get((entity, reason))
    if opts:
        return list(opts)

    # Schema-unknown — cannot seed without a human mapping
    if not schema_known:
        return [ResolutionOption.ASK_USER_FOR_VALUE, ResolutionOption.MARK_MANUAL_REVIEW]

    # DB unavailable
    if reason == MissingReason.DB_UNAVAILABLE:
        return list(_RESOLUTION_RULES.get(("__any__", MissingReason.DB_UNAVAILABLE),
                                           _GENERIC_RESOLUTION_OPTIONS))

    return list(_GENERIC_RESOLUTION_OPTIONS)


# ── PII masking helper ────────────────────────────────────────────────────────

def _mask_pii(data: dict) -> dict:
    """Mask PII values in resolved_fields before writing to artifacts."""
    if not data:
        return {}
    try:
        from artifact_security import mask_pii as _mask
        masked = {}
        for k, v in data.items():
            if isinstance(v, str):
                clean, _ = _mask(v)
                masked[k] = clean
            else:
                masked[k] = v
        return masked
    except ImportError:
        # Fallback: replace all values with [MASKED]
        return {k: "[MASKED]" for k in data}


# ── Artifact & event ──────────────────────────────────────────────────────────

def _write_artifact(
    result: DataReadinessCheckResult,
    evidence_dir: Optional[Path],
    run_id: Optional[str],
    scenario_id: str,
) -> Optional[Path]:
    """Write data_readiness_v2.json artifact; returns path or None."""
    if evidence_dir is None:
        return None
    try:
        if run_id:
            artifact_dir = evidence_dir / str(run_id)
        else:
            artifact_dir = evidence_dir
        artifact_dir.mkdir(parents=True, exist_ok=True)
        safe_id = re.sub(r"[^a-zA-Z0-9_\-]", "_", scenario_id)
        artifact_path = artifact_dir / f"data_readiness_v2_{safe_id}.json"
        artifact_path.write_text(
            json.dumps(result.to_dict(), ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        logger.debug("data_readiness_v2 artifact written: %s", artifact_path)
        return artifact_path
    except Exception as exc:  # noqa: BLE001
        logger.warning("data_readiness_v2: cannot write artifact: %s", exc)
        return None


def _emit_event(exec_logger, result: DataReadinessCheckResult) -> None:
    """Emit data_readiness_v2_checked event to execution.jsonl."""
    if exec_logger is None:
        return
    try:
        exec_logger.event("data_readiness_v2_checked", result.to_event())
    except Exception as exc:  # noqa: BLE001
        logger.debug("data_readiness_v2: cannot emit event: %s", exc)


# ── Dict → DataContractResult adapter ────────────────────────────────────────

def _dict_to_contract(d: dict):
    """
    Convert a raw dict (e.g. loaded from data_contract.json) to a DataContractResult.
    Only used when caller passes a dict instead of a DataContractResult object.
    """
    from uat_data_contract_compiler import DataContractResult, DataRequirement
    reqs = []
    for r in d.get("requirements", []):
        reqs.append(DataRequirement(
            requirement_id=r.get("requirement_id", "data.req.unknown"),
            entity=r.get("entity", "Unknown"),
            alias=r.get("alias", "unknown"),
            required_fields=r.get("required_fields", []),
            constraints=r.get("constraints", []),
            candidate_sources=r.get("candidate_sources", ["user_input"]),
            blocking=r.get("blocking", True),
            inferred_from=r.get("inferred_from", "step_keywords"),
            schema_known=r.get("schema_known", False),
            db_table=r.get("db_table"),
            db_key_column=r.get("db_key_column"),
            notes=r.get("notes"),
        ))
    return DataContractResult(
        ok=d.get("ok", True),
        scenario_id=d.get("scenario_id", "unknown"),
        ticket_id=d.get("ticket_id", 0),
        feature=d.get("feature"),
        screen=d.get("screen"),
        data_contract_version=d.get("data_contract_version", "1.0"),
        compiled_at=d.get("compiled_at", ""),
        compiled_by=d.get("compiled_by", ""),
        requirements=reqs,
    )
