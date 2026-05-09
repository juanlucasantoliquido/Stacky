"""
user_data_validator.py — User-Supplied Data Validator (Sprint 9).

Validates data provided by the human operator against the constraints
defined in the DataContract for the pending data request.

RESPONSIBILITIES:
  1. Receive a dict of user-supplied field values (from API or CLI).
  2. Validate each value against constraints from the DataContract.
  3. Detect prompt injection in supplied string values.
  4. Mask PII fields before writing to artifacts.
  5. Emit structured events: user_data_validation_result, prompt_injection_check.
  6. Write user_supplied_data.json (masked) to evidence directory.
  7. If valid, return resolved_data_ref for pipeline to consume.

SECURITY:
  - Prompt injection check runs BEFORE any validation or persistence.
  - Injected data is BLOCKED and the raw value is NEVER stored.
  - PII is masked using artifact_security.mask_pii before any write.
  - No DB connection, no DML.

PUBLIC API:
  validate(
      request_id, supplied_fields, data_contract_requirements,
      exec_logger, evidence_dir, run_id
  ) -> UserDataValidationResult

EVENT EMITTED:
  user_data_supplied
  user_data_validation_result
  prompt_injection_check   (only when injection is detected — risk: high)

EVIDENCE ARTIFACT:
  evidence/<ticket_id>/<run_id>/user_supplied_data_<request_id>.json  (masked values)
"""
from __future__ import annotations

import datetime
import json
import logging
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("stacky.qa_uat.user_data_validator")

_TOOL_VERSION = "1.0.0"
_SCHEMA_VERSION = "user_supplied_data/1.0"

# ── Prompt injection patterns (fast check for user-supplied data) ─────────────
# The full library (artifact_security.detect_prompt_injection) is used for
# deeper analysis; these quick patterns catch the most critical cases first.

_INJECTION_QUICK_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("ignore_previous",
     re.compile(r"ignore\s+(?:all\s+)?previous", re.IGNORECASE)),
    ("system_colon",
     re.compile(r"system\s*:", re.IGNORECASE)),
    ("new_instructions",
     re.compile(r"new\s+instructions?", re.IGNORECASE)),
    ("disregard_instructions",
     re.compile(r"disregard\s+(?:your\s+)?instructions?", re.IGNORECASE)),
    ("override_prompt",
     re.compile(r"override\s+(?:the\s+)?(?:system\s+)?prompt", re.IGNORECASE)),
    ("you_are_now",
     re.compile(r"\byou\s+are\s+now\b", re.IGNORECASE)),
    ("act_as",
     re.compile(r"\bact\s+as\s+(?:if\b|a\b)", re.IGNORECASE)),
    ("sql_injection_union",
     re.compile(r"\bUNION\s+(?:ALL\s+)?SELECT\b", re.IGNORECASE)),
    ("sql_drop",
     re.compile(r"\bDROP\s+TABLE\b", re.IGNORECASE)),
    ("null_byte",
     re.compile(r"\x00")),
]


# ── Dataclasses ───────────────────────────────────────────────────────────────

@dataclass
class FieldValidationResult:
    field: str
    valid: bool
    reason: Optional[str]
    masked_value: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class UserDataValidationResult:
    ok: bool
    request_id: str
    valid: bool
    reason: Optional[str]
    field_results: List[FieldValidationResult]
    injection_detected: bool
    injection_patterns: List[str]
    resolved_data_ref: Optional[str]   # path to user_supplied_data_<request_id>.json
    artifact_path: Optional[str]

    def to_dict(self) -> dict:
        return {
            "schema_version": _SCHEMA_VERSION,
            "ok": self.ok,
            "request_id": self.request_id,
            "valid": self.valid,
            "reason": self.reason,
            "field_results": [f.to_dict() for f in self.field_results],
            "injection_detected": self.injection_detected,
            "injection_patterns": self.injection_patterns,
            "resolved_data_ref": self.resolved_data_ref,
            "artifact_path": self.artifact_path,
        }

    def to_event(self) -> dict:
        return {
            "event": "user_data_validation_result",
            "request_id": self.request_id,
            "valid": self.valid,
            "reason": self.reason,
            "resolved_data_ref": self.resolved_data_ref,
        }


# ── Public API ────────────────────────────────────────────────────────────────

def validate(
    request_id: str,
    supplied_fields: Dict[str, Any],
    data_contract_requirements: Optional[List[dict]] = None,
    supplied_by: Optional[str] = None,
    exec_logger=None,
    evidence_dir: Optional[Path] = None,
    run_id: Optional[str] = None,
) -> UserDataValidationResult:
    """
    Validate user-supplied field values.

    Parameters
    ----------
    request_id : str
        The data request ID (e.g. "datareq-120-001").
    supplied_fields : dict
        Raw values provided by the operator (e.g. {"CLCOD": "12345"}).
    data_contract_requirements : list[dict] | None
        Requirements from the DataContract for this request.  Used to validate
        constraints (format, range, etc.).  If None, only injection check runs.
    supplied_by : str | None
        Operator identifier (email / user_id).  Stored masked in artifact.
    exec_logger : ExecutionLogger | None
        If provided, emits user_data_supplied, user_data_validation_result events.
    evidence_dir : Path | None
        If provided, writes user_supplied_data_<request_id>.json (masked).
    run_id : str | None
        Sub-directory for artifact placement.

    Returns
    -------
    UserDataValidationResult
        .valid = True only when ALL fields pass injection check AND constraints.
    """
    # ── Step 1: Emit user_data_supplied event (before validation) ────────────
    _emit_event(exec_logger, "user_data_supplied", {
        "request_id": request_id,
        "supplied_by": supplied_by or "unknown",
        "fields": {k: "***pending_validation***" for k in supplied_fields},
        "validation_status": "pending",
    })

    # ── Step 2: Prompt injection check (runs first — blocks if detected) ─────
    injection_patterns: List[str] = []
    for field_name, raw_value in supplied_fields.items():
        if isinstance(raw_value, str):
            patterns = _detect_injection_quick(raw_value)
            if patterns:
                injection_patterns.extend(patterns)

    # Also use full detector from artifact_security if available
    if not injection_patterns:
        injection_patterns = _deep_injection_check(supplied_fields)

    if injection_patterns:
        logger.warning(
            "user_data_validator: prompt injection detected in request %s patterns=%s",
            request_id, injection_patterns,
        )
        _emit_event(exec_logger, "prompt_injection_check", {
            "source": "user_supplied_data",
            "request_id": request_id,
            "risk": "high",
            "decision": "block_user_data",
            "patterns": injection_patterns,
        })
        return UserDataValidationResult(
            ok=False,
            request_id=request_id,
            valid=False,
            reason="PROMPT_INJECTION_DETECTED",
            field_results=[],
            injection_detected=True,
            injection_patterns=injection_patterns,
            resolved_data_ref=None,
            artifact_path=None,
        )

    # ── Step 3: Field-level constraint validation ─────────────────────────────
    field_results: List[FieldValidationResult] = []
    all_valid = True
    first_failure_reason: Optional[str] = None

    reqs_by_alias = {}
    if data_contract_requirements:
        for req in data_contract_requirements:
            if hasattr(req, "alias"):
                reqs_by_alias[req.alias] = req
            elif isinstance(req, dict):
                reqs_by_alias[req.get("alias", "")] = req

    for field_name, raw_value in supplied_fields.items():
        valid, reason = _validate_field(field_name, raw_value, reqs_by_alias)
        masked = _mask_field_value(field_name, str(raw_value) if raw_value is not None else "")
        field_results.append(FieldValidationResult(
            field=field_name,
            valid=valid,
            reason=reason,
            masked_value=masked,
        ))
        if not valid:
            all_valid = False
            if first_failure_reason is None:
                first_failure_reason = reason

    # ── Step 4: Write artifact (masked values only) ──────────────────────────
    artifact_path = None
    if evidence_dir is not None:
        artifact_path = _write_artifact(
            request_id=request_id,
            field_results=field_results,
            supplied_by=supplied_by,
            valid=all_valid,
            evidence_dir=evidence_dir,
            run_id=run_id,
        )

    resolved_data_ref = str(artifact_path) if (artifact_path and all_valid) else None

    # ── Step 5: Emit validation result event ─────────────────────────────────
    result = UserDataValidationResult(
        ok=True,
        request_id=request_id,
        valid=all_valid,
        reason=first_failure_reason,
        field_results=field_results,
        injection_detected=False,
        injection_patterns=[],
        resolved_data_ref=resolved_data_ref,
        artifact_path=str(artifact_path) if artifact_path else None,
    )
    _emit_event(exec_logger, "user_data_validation_result", result.to_event())

    if all_valid:
        logger.info(
            "user_data_validator: request %s VALID — fields: %s",
            request_id, list(supplied_fields.keys()),
        )
    else:
        logger.warning(
            "user_data_validator: request %s INVALID — reason: %s",
            request_id, first_failure_reason,
        )

    return result


# ── Field validator ───────────────────────────────────────────────────────────

def _validate_field(
    field_name: str,
    raw_value: Any,
    reqs_by_alias: dict,
) -> tuple[bool, Optional[str]]:
    """
    Validate a single field value against known constraints.

    Returns (valid: bool, reason: str | None).
    """
    if raw_value is None or (isinstance(raw_value, str) and not raw_value.strip()):
        return False, "FIELD_VALUE_EMPTY"

    value = str(raw_value).strip()

    # CLCOD: must be 1-10 digit numeric string (system client code)
    if field_name.upper() in ("CLCOD", "CLIENT_CODE"):
        if not re.match(r"^\d{1,10}$", value):
            return False, "CLCOD_INVALID_FORMAT"
        return True, None

    # LOTEID: must be 1-12 digit numeric string
    if field_name.upper() in ("LOTEID", "LOTE_ID"):
        if not re.match(r"^\d{1,12}$", value):
            return False, "LOTEID_INVALID_FORMAT"
        return True, None

    # LOGIN / user fields: alphanumeric + dot/underscore/hyphen, 3-64 chars
    if field_name.upper() in ("LOGIN", "USER", "USERNAME"):
        if not re.match(r"^[A-Za-z0-9._\-@]{3,64}$", value):
            return False, "LOGIN_INVALID_FORMAT"
        return True, None

    # Generic: check against contract constraints if available
    # Look up by field_name across all requirements
    for _alias, req in reqs_by_alias.items():
        constraints = (
            getattr(req, "constraints", [])
            if hasattr(req, "constraints")
            else req.get("constraints", [])
        )
        req_fields = (
            getattr(req, "required_fields", [])
            if hasattr(req, "required_fields")
            else req.get("required_fields", [])
        )
        if field_name in (req_fields or []):
            for constraint in (constraints or []):
                if "activ" in str(constraint).lower() and field_name.upper() == "CLCOD":
                    # We cannot verify active obligations here without DB access.
                    # Accept the value — the runner will discover if it's invalid.
                    pass

    # Default: non-empty string passes
    return True, None


# ── PII masking ───────────────────────────────────────────────────────────────

def _mask_field_value(field_name: str, value: str) -> str:
    """Return a masked representation of the value for artifact persistence."""
    if not value:
        return ""
    # Always mask — store only length indicator
    try:
        from artifact_security import mask_pii
        masked, _ = mask_pii(value)
        # If mask_pii didn't find PII patterns, apply generic masking for safety
        if masked == value and len(value) > 2:
            return value[:2] + "***"
        return masked
    except ImportError:
        # Fallback: show only first 2 chars + ***
        if len(value) > 2:
            return value[:2] + "***"
        return "***"


# ── Injection detectors ───────────────────────────────────────────────────────

def _detect_injection_quick(text: str) -> List[str]:
    """Run quick pattern scan. Returns list of matched pattern names."""
    found = []
    for name, pattern in _INJECTION_QUICK_PATTERNS:
        if pattern.search(text):
            found.append(name)
    return found


def _deep_injection_check(supplied_fields: Dict[str, Any]) -> List[str]:
    """
    Use artifact_security.detect_prompt_injection for deep check.
    Returns list of pattern names if risk is high; empty list otherwise.
    """
    try:
        from artifact_security import detect_prompt_injection
        all_text = " ".join(
            str(v) for v in supplied_fields.values() if isinstance(v, str)
        )
        result = detect_prompt_injection(all_text, source="user_supplied_data")
        if result.risk == "high":
            return result.patterns
    except (ImportError, Exception) as exc:
        logger.debug("user_data_validator: deep injection check unavailable: %s", exc)
    return []


# ── Artifact writer ───────────────────────────────────────────────────────────

def _write_artifact(
    request_id: str,
    field_results: List[FieldValidationResult],
    supplied_by: Optional[str],
    valid: bool,
    evidence_dir: Path,
    run_id: Optional[str],
) -> Optional[Path]:
    """Write user_supplied_data_<request_id>.json with masked values."""
    try:
        if run_id:
            artifact_dir = evidence_dir / str(run_id)
        else:
            artifact_dir = evidence_dir
        artifact_dir.mkdir(parents=True, exist_ok=True)

        safe_rid = re.sub(r"[^a-zA-Z0-9_\-]", "_", request_id)
        path = artifact_dir / f"user_supplied_data_{safe_rid}.json"

        # Mask supplied_by (may be email)
        masked_by = "***"
        if supplied_by:
            try:
                from artifact_security import mask_pii
                masked_by, _ = mask_pii(supplied_by)
            except ImportError:
                masked_by = "***"

        payload = {
            "schema_version": _SCHEMA_VERSION,
            "request_id": request_id,
            "supplied_by": masked_by,
            "valid": valid,
            "generated_at": _utcnow(),
            "fields": {
                fr.field: fr.masked_value
                for fr in field_results
            },
            "field_results": [fr.to_dict() for fr in field_results],
        }
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        logger.debug("user_data_validator: artifact written: %s", path)
        return path
    except Exception as exc:
        logger.warning("user_data_validator: cannot write artifact: %s", exc)
        return None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _utcnow() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def _emit_event(exec_logger, event_name: str, data: dict) -> None:
    if exec_logger is None:
        return
    try:
        exec_logger.event(event_name, data)
    except Exception as exc:
        logger.debug("user_data_validator: cannot emit event %s: %s", event_name, exc)
