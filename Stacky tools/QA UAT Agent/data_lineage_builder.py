"""
data_lineage_builder.py — Data Lineage Builder (Sprint 14).

Builds a `data_lineage.json` artifact that traces every piece of test data
used in a QA UAT run back to its origin:

  LINEAGE SOURCES
  ───────────────
  SEEDED       — Row inserted via seed_executor (traceable via SeedRunId)
  USER_SUPPLIED — Value provided by the operator via data_request resolution
  ENVIRONMENT  — Value read from environment/config (CLCOD from env var, etc.)
  FIXTURE      — Catalog row from catalog_fixtures.yml
  DISCOVERED   — Value found in existing DB data (via hint_query resolution)
  UNKNOWN      — Cannot trace origin

LINEAGE ENTRY:
  {
      "field": "CLCOD",
      "value": "123456",
      "source": "SEEDED",
      "seed_run_id": "seed-120-ABC123",
      "scenario_id": "RF-007-CA-01",
      "seed_script": "seed_proposal_RF-007-CA-01.sql",
      "seeded_at": "2026-05-01T12:00:00Z",
      "cleaned_up": true,
      "cleanup_at": "2026-05-01T12:05:00Z",
      "evidence_refs": ["seed_execution_result_RF-007-CA-01.json"]
  }

PUBLIC API:
  build(evidence_dir, run_id, ticket_id, exec_logger) -> DataLineageResult
  DataLineageResult.to_dict() -> dict

EVIDENCE ARTIFACT:
  evidence/<ticket_id>/<run_id>/data_lineage.json

EVENTS EMITTED:
  data_lineage_built  — summary counts

SECURITY:
  - Read-only: reads existing evidence artifacts only.
  - Does not execute SQL or make HTTP requests.
  - Field values stored only for non-PII fields (no passwords, no personal data).
  - Values are truncated to 200 chars in the artifact.
"""
from __future__ import annotations

import datetime
import json
import logging
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Optional, Dict, Any

logger = logging.getLogger("stacky.qa_uat.data_lineage_builder")

_TOOL_VERSION = "1.0.0"
_SCHEMA_VERSION = "data_lineage/1.0"

# Max chars per field value stored in lineage (security: prevent large data leakage)
_MAX_VALUE_LEN = 200

# PII-adjacent field names that should NOT have their values stored
_REDACTED_FIELDS = frozenset({
    "password", "pass", "passwd", "pwd", "secret", "token",
    "dni", "cuil", "cuit", "documento", "doc_numero",
    "email", "correo", "telefono", "celular", "phone",
})


# ── Lineage source codes ───────────────────────────────────────────────────────

class LineageSource:
    SEEDED         = "SEEDED"
    USER_SUPPLIED  = "USER_SUPPLIED"
    ENVIRONMENT    = "ENVIRONMENT"
    FIXTURE        = "FIXTURE"
    DISCOVERED     = "DISCOVERED"
    UNKNOWN        = "UNKNOWN"


# ── Dataclasses ────────────────────────────────────────────────────────────────

@dataclass
class LineageEntry:
    """Lineage record for a single data field used in a scenario."""
    field: str
    value: Optional[str]           # truncated, may be None if redacted
    source: str                    # LineageSource.*
    scenario_id: str
    seed_run_id: Optional[str] = None
    seed_script: Optional[str] = None
    seeded_at: Optional[str] = None
    cleaned_up: bool = False
    cleanup_at: Optional[str] = None
    origin_note: Optional[str] = None    # human-readable origin description
    evidence_refs: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DataLineageResult:
    """Aggregated data lineage for a full pipeline run."""
    ok: bool
    run_id: str
    ticket_id: object
    total_entries: int
    seeded_count: int
    user_supplied_count: int
    fixture_count: int
    discovered_count: int
    unknown_count: int
    entries: List[LineageEntry] = field(default_factory=list)
    evidence_path: Optional[str] = None
    built_at: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "schema_version": _SCHEMA_VERSION,
            "ok": self.ok,
            "run_id": self.run_id,
            "ticket_id": self.ticket_id,
            "total_entries": self.total_entries,
            "seeded_count": self.seeded_count,
            "user_supplied_count": self.user_supplied_count,
            "fixture_count": self.fixture_count,
            "discovered_count": self.discovered_count,
            "unknown_count": self.unknown_count,
            "entries": [e.to_dict() for e in self.entries],
            "evidence_path": self.evidence_path,
            "built_at": self.built_at,
        }

    def to_event(self) -> dict:
        return {
            "event_type": "data_lineage_built",
            "run_id": self.run_id,
            "ticket_id": self.ticket_id,
            "ok": self.ok,
            "total_entries": self.total_entries,
            "seeded_count": self.seeded_count,
            "user_supplied_count": self.user_supplied_count,
            "unknown_count": self.unknown_count,
        }


# ── Value sanitizer ────────────────────────────────────────────────────────────

def _safe_value(field_name: str, raw_value: Any) -> Optional[str]:
    """
    Sanitize a field value for storage in lineage artifact.

    Returns None for PII-adjacent fields; truncated string otherwise.
    """
    field_lower = str(field_name).lower()
    for pii in _REDACTED_FIELDS:
        if pii in field_lower:
            return None  # redacted

    if raw_value is None:
        return None
    value_str = str(raw_value)[:_MAX_VALUE_LEN]
    return value_str


# ── Artifact readers ───────────────────────────────────────────────────────────

def _read_seed_execution_artifacts(run_dir: Path) -> List[Dict[str, Any]]:
    results = []
    for f in sorted(run_dir.glob("seed_execution_result_*.json")):
        try:
            results.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            pass
    return results


def _read_cleanup_artifacts(run_dir: Path) -> Dict[str, Dict[str, Any]]:
    """Dict keyed by scenario_id."""
    results: Dict[str, Dict[str, Any]] = {}
    for f in sorted(run_dir.glob("seed_cleanup_result_*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            scenario_id = data.get("scenario_id", "")
            if scenario_id:
                results[scenario_id] = data
        except Exception:
            pass
    return results


def _read_data_request_artifacts(run_dir: Path) -> List[Dict[str, Any]]:
    results = []
    for f in sorted(run_dir.glob("data_request_*.json")):
        try:
            results.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            pass
    return results


def _read_catalog_readiness_artifacts(run_dir: Path) -> List[Dict[str, Any]]:
    results = []
    for f in sorted(run_dir.glob("catalog_readiness_*.json")):
        try:
            results.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            pass
    return results


def _extract_seed_fields_from_sql(sql_content: str) -> Dict[str, str]:
    """
    Extract field=value pairs from a seed INSERT SQL script.

    Heuristic: looks for INSERT INTO ... VALUES (...) patterns.
    Returns {field_name: value} pairs found.
    Limited parsing — not a full SQL parser.
    """
    fields: Dict[str, str] = {}

    # Match: INSERT INTO Table (col1, col2, ...) VALUES (val1, val2, ...)
    insert_pattern = re.compile(
        r"INSERT\s+INTO\s+\w+\s*\(([^)]+)\)\s*VALUES\s*\(([^)]+)\)",
        re.IGNORECASE | re.DOTALL,
    )
    for m in insert_pattern.finditer(sql_content):
        col_str = m.group(1)
        val_str = m.group(2)
        cols = [c.strip().strip("[]\"'`") for c in col_str.split(",")]
        # Simple value splitting (doesn't handle nested quotes/commas)
        vals = [v.strip().strip("'\"") for v in val_str.split(",")]
        for col, val in zip(cols, vals):
            if col and len(col) < 50:
                fields[col] = val[:_MAX_VALUE_LEN]

    return fields


# ── Main public function ───────────────────────────────────────────────────────

def build(
    evidence_dir: Path,
    run_id: str = "unknown",
    ticket_id: object = 0,
    exec_logger=None,
) -> DataLineageResult:
    """
    Build data_lineage.json by aggregating all evidence artifacts for a run.

    Reads from evidence_dir/<ticket_id>/<run_id>/:
      seed_execution_result_*.json   → SEEDED entries
      seed_cleanup_result_*.json     → marks cleaned_up on SEEDED entries
      data_request_*.json            → USER_SUPPLIED entries
      catalog_readiness_*.json       → FIXTURE entries

    Parameters
    ----------
    evidence_dir : Base evidence directory
    run_id       : Pipeline run ID
    ticket_id    : ADO ticket ID
    exec_logger  : Optional event logger

    Returns
    -------
    DataLineageResult
    """
    built_at = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
    run_dir = Path(evidence_dir) / str(ticket_id) / str(run_id)
    entries: List[LineageEntry] = []

    # ── SEEDED entries ──────────────────────────────────────────────────────
    seed_artifacts = _read_seed_execution_artifacts(run_dir)
    cleanup_by_scenario = _read_cleanup_artifacts(run_dir)

    for seed_data in seed_artifacts:
        scenario_id = seed_data.get("scenario_id", "unknown")
        seed_run_id = seed_data.get("seed_run_id", "")
        script_path = seed_data.get("script_path", "")
        verdict = seed_data.get("verdict", "")
        seeded_at = seed_data.get("applied_at") or seed_data.get("executed_at")

        # Try to extract fields from SQL script
        sql_fields: Dict[str, str] = {}
        if script_path:
            try:
                sql_content = Path(script_path).read_text(encoding="utf-8", errors="replace")
                sql_fields = _extract_seed_fields_from_sql(sql_content)
            except Exception:
                pass

        cleanup = cleanup_by_scenario.get(scenario_id, {})
        cleaned_up = cleanup.get("verdict") == "CLEANED"
        cleanup_at = cleanup.get("cleaned_at")

        script_name = Path(script_path).name if script_path else None

        if sql_fields:
            for field_name, raw_val in sql_fields.items():
                safe_val = _safe_value(field_name, raw_val)
                entry = LineageEntry(
                    field=field_name,
                    value=safe_val,
                    source=LineageSource.SEEDED if verdict == "APPLIED" else LineageSource.UNKNOWN,
                    scenario_id=scenario_id,
                    seed_run_id=seed_run_id or None,
                    seed_script=script_name,
                    seeded_at=seeded_at,
                    cleaned_up=cleaned_up,
                    cleanup_at=cleanup_at,
                    origin_note=f"seed_executor verdict={verdict}",
                    evidence_refs=[f"seed_execution_result_{scenario_id}.json"],
                )
                entries.append(entry)
        else:
            # No fields extracted — create one SEEDED entry for the script
            entry = LineageEntry(
                field="seed_script",
                value=script_name,
                source=LineageSource.SEEDED if verdict == "APPLIED" else LineageSource.UNKNOWN,
                scenario_id=scenario_id,
                seed_run_id=seed_run_id or None,
                seed_script=script_name,
                seeded_at=seeded_at,
                cleaned_up=cleaned_up,
                cleanup_at=cleanup_at,
                origin_note=f"seed_executor verdict={verdict}",
                evidence_refs=[f"seed_execution_result_{scenario_id}.json"],
            )
            entries.append(entry)

    # ── USER_SUPPLIED entries ───────────────────────────────────────────────
    data_requests = _read_data_request_artifacts(run_dir)
    for dr in data_requests:
        scenario_id = dr.get("scenario_id", "unknown")
        resolution_type = dr.get("resolution_type", "")
        supplied_fields = dr.get("supplied_fields", {})
        resolved_at = dr.get("resolved_at")

        if resolution_type == "user_supplied" and isinstance(supplied_fields, dict):
            for field_name, raw_val in supplied_fields.items():
                safe_val = _safe_value(field_name, raw_val)
                entry = LineageEntry(
                    field=field_name,
                    value=safe_val,
                    source=LineageSource.USER_SUPPLIED,
                    scenario_id=scenario_id,
                    seeded_at=resolved_at,
                    origin_note="Operator-supplied via data_request resolution",
                    evidence_refs=[f"data_request_{scenario_id}.json"],
                )
                entries.append(entry)
        elif resolution_type == "auto_resolved":
            entry = LineageEntry(
                field="auto_resolved",
                value=str(supplied_fields)[:_MAX_VALUE_LEN] if supplied_fields else None,
                source=LineageSource.DISCOVERED,
                scenario_id=scenario_id,
                seeded_at=resolved_at,
                origin_note="Auto-resolved via hint_query",
                evidence_refs=[f"data_request_{scenario_id}.json"],
            )
            entries.append(entry)

    # ── FIXTURE entries ─────────────────────────────────────────────────────
    catalog_artifacts = _read_catalog_readiness_artifacts(run_dir)
    for cat_data in catalog_artifacts:
        scenario_id = cat_data.get("scenario_id", "unknown")
        for cat_result in cat_data.get("catalog_results", []):
            catalog_name = cat_result.get("catalog_name", "")
            if cat_result.get("status") == "OK":
                entry = LineageEntry(
                    field=catalog_name,
                    value=None,  # catalog value not stored individually
                    source=LineageSource.FIXTURE,
                    scenario_id=scenario_id,
                    origin_note=f"Catalog fixture: {catalog_name} ({cat_result.get('row_count', '?')} rows)",
                    evidence_refs=[f"catalog_readiness_{scenario_id}.json"],
                )
                entries.append(entry)

    # ── Aggregate counts ────────────────────────────────────────────────────
    total = len(entries)
    seeded_count   = sum(1 for e in entries if e.source == LineageSource.SEEDED)
    user_count     = sum(1 for e in entries if e.source == LineageSource.USER_SUPPLIED)
    fixture_count  = sum(1 for e in entries if e.source == LineageSource.FIXTURE)
    discovered     = sum(1 for e in entries if e.source == LineageSource.DISCOVERED)
    unknown        = sum(1 for e in entries if e.source == LineageSource.UNKNOWN)

    result = DataLineageResult(
        ok=True,
        run_id=str(run_id),
        ticket_id=ticket_id,
        total_entries=total,
        seeded_count=seeded_count,
        user_supplied_count=user_count,
        fixture_count=fixture_count,
        discovered_count=discovered,
        unknown_count=unknown,
        entries=entries,
        built_at=built_at,
    )

    # Write evidence artifact
    if run_dir is not None:
        run_dir.mkdir(parents=True, exist_ok=True)
        artifact_path = run_dir / "data_lineage.json"
        try:
            artifact_path.write_text(
                json.dumps(result.to_dict(), indent=2), encoding="utf-8"
            )
            result.evidence_path = str(artifact_path)
        except Exception as exc:
            logger.warning("data_lineage_builder: could not write artifact: %s", exc)

    # Emit event
    if exec_logger:
        try:
            exec_logger("data_lineage_built", result.to_event())
        except Exception:
            pass

    logger.info(
        "data_lineage_builder: total=%d seeded=%d user_supplied=%d fixture=%d",
        total, seeded_count, user_count, fixture_count,
    )

    return result
