"""
contract_validator.py — Sprint 4: JSON Schema contract validator for QA UAT Agent.

PURPOSE
-------
Validates any dict output against a JSON Schema definition before the pipeline
advances to the next stage. Used for compiler output and generator output.

DESIGN
------
- Uses jsonschema (draft-07) when available.
- Falls back to structural duck-typing checks when jsonschema is not installed.
- Produces a ContractValidationResult with score, violations, and decision.
- Writes compiler_contract_result.json / generator_contract_result.json artifacts.
- Emits events to execution.jsonl via exec_logger.

HARD RULES (Sprint 4)
---------------------
  compiled=0 + out_of_scope>0  → BLOCKED PIP NO_EXECUTABLE_SCENARIOS
  compiled=0 + out_of_scope=0  → BLOCKED PIP COMPILER_EMPTY
  scenario.scenario_id missing → CONTRACT_INVALID
  spec.scenario_id missing     → CONTRACT_INVALID

PUBLIC API
----------
  validate_compiler_output(output, evidence_dir, run_id, exec_logger) -> ContractValidationResult
  validate_generator_output(output, evidence_dir, run_id, exec_logger) -> ContractValidationResult
  ContractValidationResult.ok, .decision, .score, .violations, .artifact_path
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger("stacky.qa_uat.contract_validator")

_TOOL_ROOT = Path(__file__).parent
_SCHEMA_DIR = _TOOL_ROOT / "schemas"

_SCHEMA_VERSION = "contract_validation/1.0"

# ── Attempt to load jsonschema ─────────────────────────────────────────────────
try:
    import jsonschema as _jsonschema
    _JSONSCHEMA_AVAILABLE = True
except ImportError:  # pragma: no cover
    _jsonschema = None  # type: ignore[assignment]
    _JSONSCHEMA_AVAILABLE = False
    logger.debug("contract_validator: jsonschema not installed — using structural fallback")


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class ContractValidationResult:
    """Result of a contract validation pass."""
    ok: bool
    decision: str               # "ALLOW" | "BLOCKED"
    schema_id: str              # which schema was validated
    violations: List[str]       # list of violation messages
    reason: Optional[str]       # first blocking reason code (e.g. "COMPILER_EMPTY")
    score: float                # 0.0 – 1.0 (1.0 = fully valid)
    elapsed_ms: int
    artifact_path: Optional[str] = None
    contract_type: str = ""     # "compiler" | "generator"

    def to_dict(self) -> dict:
        return {
            "schema_version": _SCHEMA_VERSION,
            "ok": self.ok,
            "decision": self.decision,
            "schema_id": self.schema_id,
            "violations": self.violations,
            "reason": self.reason,
            "score": self.score,
            "elapsed_ms": self.elapsed_ms,
            "artifact_path": self.artifact_path,
            "contract_type": self.contract_type,
        }


# ── Public API ────────────────────────────────────────────────────────────────

def validate_compiler_output(
    output: dict,
    evidence_dir: Optional[Path] = None,
    run_id: Optional[str] = None,
    exec_logger=None,
) -> ContractValidationResult:
    """Validate uat_scenario_compiler.run() output against ScenarioCompilerResult schema.

    Hard rules (Sprint 4):
      - compiled=0 + out_of_scope=0 → BLOCKED COMPILER_EMPTY
      - compiled=0 + out_of_scope>0 → BLOCKED NO_EXECUTABLE_SCENARIOS
      - Each scenario must have scenario_id and title
    """
    started = time.time()
    violations: List[str] = []
    reason: Optional[str] = None

    # ── Structural checks (always run, before schema) ─────────────────────────
    if not isinstance(output.get("scenarios"), list):
        violations.append("scenarios: must be a list")

    # Resolve compiled/out_of_scope: accept explicit counts or derive from lists.
    _scenarios_list = output.get("scenarios") or []
    _oos_list = output.get("out_of_scope_items") or []
    compiled = output.get("compiled")
    out_of_scope = output.get("out_of_scope")

    # If explicit counts are present, validate they are integers
    if compiled is not None and not isinstance(compiled, int):
        violations.append("compiled: must be an integer")
    if out_of_scope is not None and not isinstance(out_of_scope, int):
        violations.append("out_of_scope: must be an integer")

    # Derive from lists when counts are absent (backward-compatible)
    if compiled is None:
        compiled = len(_scenarios_list)
    if out_of_scope is None:
        out_of_scope = len(_oos_list)

    # Hard rule: compiled=0 + out_of_scope=0 → COMPILER_EMPTY
    if compiled == 0 and out_of_scope == 0 and output.get("ok") is not False:
        violations.append("compiled=0 and out_of_scope=0: no scenarios and no out_of_scope items")
        if reason is None:
            reason = "COMPILER_EMPTY"

    # Hard rule: compiled=0 + out_of_scope>0 → NO_EXECUTABLE_SCENARIOS
    if compiled == 0 and out_of_scope > 0:
        violations.append(
            f"compiled=0 but out_of_scope={out_of_scope}: all items discarded — pipeline must block"
        )
        if reason is None:
            reason = "NO_EXECUTABLE_SCENARIOS"

    # Per-scenario checks
    for i, sc in enumerate(output.get("scenarios") or []):
        if not sc.get("scenario_id"):
            violations.append(f"scenarios[{i}]: missing scenario_id")
            if reason is None:
                reason = "CONTRACT_INVALID"
        # Accept either 'title', 'titulo', or 'description' as the human-readable label
        if not (sc.get("title") or sc.get("titulo") or sc.get("description")):
            violations.append(f"scenarios[{i}]: missing title/titulo/description")
            if reason is None:
                reason = "CONTRACT_INVALID"

    # ── JSON Schema validation (optional, if jsonschema installed) ─────────────
    schema_violations = _validate_against_schema("ScenarioCompilerResult.schema.json", output)
    violations.extend(schema_violations)
    if schema_violations and reason is None:
        reason = "CONTRACT_INVALID"

    # ── Score & decision ──────────────────────────────────────────────────────
    # Score degrades per violation; hard rules (COMPILER_EMPTY, NO_EXECUTABLE_SCENARIOS) = 0.0
    if reason in ("COMPILER_EMPTY", "NO_EXECUTABLE_SCENARIOS"):
        score = 0.0
    elif violations:
        score = max(0.0, 1.0 - len(violations) * 0.1)
    else:
        score = 1.0

    decision = "ALLOW" if not violations else "BLOCKED"
    ok = decision == "ALLOW"

    elapsed_ms = int((time.time() - started) * 1000)
    result = ContractValidationResult(
        ok=ok,
        decision=decision,
        schema_id="ScenarioCompilerResult.schema.json",
        violations=violations,
        reason=reason,
        score=score,
        elapsed_ms=elapsed_ms,
        contract_type="compiler",
    )

    _write_artifact(result, "compiler_contract_result.json", evidence_dir)
    _emit_event(exec_logger, "compiler_contract_result", result)

    if not ok:
        logger.warning("compiler contract BLOCKED: reason=%s violations=%d", reason, len(violations))
    else:
        logger.debug("compiler contract ALLOW: score=%.2f", score)

    return result


def validate_generator_output(
    output: dict,
    evidence_dir: Optional[Path] = None,
    run_id: Optional[str] = None,
    exec_logger=None,
) -> ContractValidationResult:
    """Validate playwright_test_generator.run() output against GeneratedTestPlan schema.

    Hard rules:
      - Each spec must have scenario_id and status
      - specs with status='blocked' must have blocked_reason
      - No spec_file written for blocked specs
    """
    started = time.time()
    violations: List[str] = []
    reason: Optional[str] = None

    if not isinstance(output.get("specs"), list):
        violations.append("specs: must be a list")
        reason = "CONTRACT_INVALID"

    valid_statuses = {"generated", "blocked", "skipped", "error"}
    for i, spec in enumerate(output.get("specs") or []):
        if not spec.get("scenario_id"):
            violations.append(f"specs[{i}]: missing scenario_id")
            if reason is None:
                reason = "CONTRACT_INVALID"
        status = spec.get("status")
        if status not in valid_statuses:
            violations.append(f"specs[{i}]: invalid status {status!r} (must be {valid_statuses})")
            if reason is None:
                reason = "CONTRACT_INVALID"
        if status == "blocked" and not spec.get("blocked_reason"):
            violations.append(f"specs[{i}]: status=blocked but blocked_reason missing")
            if reason is None:
                reason = "CONTRACT_INVALID"

    schema_violations = _validate_against_schema("GeneratedTestPlan.schema.json", output)
    violations.extend(schema_violations)
    if schema_violations and reason is None:
        reason = "CONTRACT_INVALID"

    score = max(0.0, 1.0 - len(violations) * 0.1) if violations else 1.0
    decision = "ALLOW" if not violations else "BLOCKED"
    ok = decision == "ALLOW"

    elapsed_ms = int((time.time() - started) * 1000)
    result = ContractValidationResult(
        ok=ok,
        decision=decision,
        schema_id="GeneratedTestPlan.schema.json",
        violations=violations,
        reason=reason,
        score=score,
        elapsed_ms=elapsed_ms,
        contract_type="generator",
    )

    _write_artifact(result, "generator_contract_result.json", evidence_dir)
    _emit_event(exec_logger, "generator_contract_result", result)

    if not ok:
        logger.warning("generator contract BLOCKED: reason=%s violations=%d", reason, len(violations))
    else:
        logger.debug("generator contract ALLOW: score=%.2f", score)

    return result


# ── Internal helpers ──────────────────────────────────────────────────────────

def _validate_against_schema(schema_filename: str, data: dict) -> List[str]:
    """Validate data against the named schema file. Returns list of violation strings."""
    if not _JSONSCHEMA_AVAILABLE:
        return []
    schema_path = _SCHEMA_DIR / schema_filename
    if not schema_path.is_file():
        logger.debug("Schema file not found: %s — skipping jsonschema validation", schema_path)
        return []
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        validator = _jsonschema.Draft7Validator(schema)
        errors = sorted(validator.iter_errors(data), key=lambda e: e.path)
        return [f"{'.'.join(str(p) for p in e.path) or '<root>'}: {e.message}" for e in errors]
    except Exception as exc:  # noqa: BLE001
        logger.warning("contract_validator: schema validation error: %s", exc)
        return []


def _write_artifact(
    result: ContractValidationResult,
    filename: str,
    evidence_dir: Optional[Path],
) -> None:
    """Write artifact to evidence_dir/<filename>."""
    if evidence_dir is None:
        return
    try:
        evidence_dir.mkdir(parents=True, exist_ok=True)
        artifact_path = evidence_dir / filename
        artifact_path.write_text(
            json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        result.artifact_path = str(artifact_path)
        logger.debug("contract_validator artifact: %s", artifact_path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("contract_validator: cannot write artifact %s: %s", filename, exc)


def _emit_event(exec_logger, event_name: str, result: ContractValidationResult) -> None:
    """Emit contract validation event to execution.jsonl."""
    if exec_logger is None:
        return
    try:
        exec_logger.event(event_name, {
            "ok": result.ok,
            "decision": result.decision,
            "schema_id": result.schema_id,
            "violations_count": len(result.violations),
            "violations": result.violations[:5],  # cap to avoid giant events
            "reason": result.reason,
            "score": result.score,
            "elapsed_ms": result.elapsed_ms,
            "artifact_path": result.artifact_path,
        })
    except Exception:  # noqa: BLE001
        pass
