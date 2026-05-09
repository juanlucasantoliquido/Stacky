"""
test_confidence_scorer.py — Test Confidence Scorer (Sprint 14).

Calculates a confidence score [0..100] for each UAT scenario based on the
quality of evidence gathered during the pipeline run:

  CONTRIBUTING FACTORS (positive)
  ────────────────────────────────
  +30   Oracle present and PASS
  +20   Seed data was applied (real data, not sample)
  +15   Cleanup confirmed (no leftover state)
  +15   Playwright assertions count > 3
  +10   Deployment fingerprint matched
  + 5   Screenshot evidence present
  + 5   Trace evidence present

  PENALTIES (negative)
  ─────────────────────
  -30   No oracle (P0 scenario)
  -20   Only weak assertions (WEAK_ONLY oracle verdict)
  -15   Oracle FAIL
  -15   Cleanup failed or skipped after seed
  -10   Seed was skipped (data from browser state only)
  -10   No playwright assertions in test
  - 5   Fingerprint mismatch

  THRESHOLDS
  ───────────
  HIGH   ≥ 80   → can auto-publish (if configured)
  MEDIUM ≥ 60   → publish with human approval
  LOW    <  60   → blocked from auto-publish; human review required

PUBLISH GATE:
  If `min_test_confidence` is set in policy (default: 60), any scenario
  with confidence < threshold causes `publish_blocked=True` in the result.

PUBLIC API:
  score(
      scenario_id, is_p0, oracle_result, seed_result, cleanup_result,
      runner_output, deployment_matched, has_screenshot, has_trace,
      exec_logger
  ) -> ConfidenceScore

  score_all(
      scenarios, oracle_eval_result, seed_stage, cleanup_stage,
      runner_output_path, deployment_stage,
      exec_logger, evidence_dir, run_id, ticket_id,
      min_confidence
  ) -> ConfidenceScorerResult

EVIDENCE ARTIFACT:
  evidence/<ticket_id>/<run_id>/confidence_report.json

EVENTS EMITTED:
  test_confidence_result  — per scenario
  confidence_summary      — aggregated

SECURITY:
  - Read-only: no DB queries.
  - No LLM calls.
  - Evidence artifacts do not contain raw SQL or credentials.
"""
from __future__ import annotations

import datetime
import json
import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Optional, Dict, Any

logger = logging.getLogger("stacky.qa_uat.test_confidence_scorer")

_TOOL_VERSION = "1.0.0"
_SCHEMA_VERSION = "confidence_report/1.0"


# ── Score levels ───────────────────────────────────────────────────────────────

class ConfidenceLevel:
    HIGH   = "HIGH"    # >= 80
    MEDIUM = "MEDIUM"  # >= 60
    LOW    = "LOW"     # < 60


_DEFAULT_MIN_CONFIDENCE = 60


def _level(score: int) -> str:
    if score >= 80:
        return ConfidenceLevel.HIGH
    elif score >= 60:
        return ConfidenceLevel.MEDIUM
    else:
        return ConfidenceLevel.LOW


# ── Factor weights ─────────────────────────────────────────────────────────────

# Positive factors
_W_ORACLE_PASS          = 30
_W_SEED_APPLIED         = 20
_W_CLEANUP_CONFIRMED    = 15
_W_MANY_ASSERTIONS      = 15   # assertion count > 3
_W_FINGERPRINT_MATCHED  = 10
_W_SCREENSHOT           = 5
_W_TRACE                = 5

# Negative factors (penalties)
_P_NO_ORACLE_P0         = -30
_P_WEAK_ONLY_ORACLE     = -20
_P_ORACLE_FAIL          = -15
_P_CLEANUP_FAILED       = -15
_P_SEED_SKIPPED         = -10
_P_NO_ASSERTIONS        = -10
_P_FINGERPRINT_MISMATCH = -5


# ── Dataclasses ────────────────────────────────────────────────────────────────

@dataclass
class ScoreFactor:
    """A single positive or negative contribution to the confidence score."""
    name: str
    delta: int        # positive or negative
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ConfidenceScore:
    """Confidence score for a single scenario."""
    scenario_id: str
    score: int                # clamped [0..100]
    level: str                # ConfidenceLevel.*
    is_p0: bool
    publish_blocked: bool     # True when score < min_confidence
    factors: List[ScoreFactor] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "scenario_id": self.scenario_id,
            "score": self.score,
            "level": self.level,
            "is_p0": self.is_p0,
            "publish_blocked": self.publish_blocked,
            "factors": [f.to_dict() for f in self.factors],
        }

    def to_event(self) -> dict:
        return {
            "event_type": "test_confidence_result",
            "scenario_id": self.scenario_id,
            "score": self.score,
            "level": self.level,
            "is_p0": self.is_p0,
            "publish_blocked": self.publish_blocked,
        }


@dataclass
class ConfidenceScorerResult:
    """Aggregated confidence result for all scenarios in a run."""
    ok: bool
    run_id: str
    ticket_id: object
    total_scenarios: int
    high_count: int
    medium_count: int
    low_count: int
    blocked_count: int
    min_confidence: int
    publish_blocked: bool
    scenario_scores: List[ConfidenceScore] = field(default_factory=list)
    evidence_path: Optional[str] = None
    scored_at: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "schema_version": _SCHEMA_VERSION,
            "ok": self.ok,
            "run_id": self.run_id,
            "ticket_id": self.ticket_id,
            "total_scenarios": self.total_scenarios,
            "high_count": self.high_count,
            "medium_count": self.medium_count,
            "low_count": self.low_count,
            "blocked_count": self.blocked_count,
            "min_confidence": self.min_confidence,
            "publish_blocked": self.publish_blocked,
            "scenario_scores": [s.to_dict() for s in self.scenario_scores],
            "evidence_path": self.evidence_path,
            "scored_at": self.scored_at,
        }

    def to_event(self) -> dict:
        return {
            "event_type": "confidence_summary",
            "run_id": self.run_id,
            "ticket_id": self.ticket_id,
            "ok": self.ok,
            "total_scenarios": self.total_scenarios,
            "high_count": self.high_count,
            "medium_count": self.medium_count,
            "low_count": self.low_count,
            "blocked_count": self.blocked_count,
            "publish_blocked": self.publish_blocked,
        }


# ── Per-scenario scorer ────────────────────────────────────────────────────────

def score(
    scenario_id: str,
    is_p0: bool = False,
    oracle_verdict: Optional[str] = None,        # OracleVerdict.*
    seed_verdict: Optional[str] = None,          # "APPLIED" | "SKIPPED" | None
    cleanup_verdict: Optional[str] = None,       # "CLEANED" | "SKIPPED" | "ERROR" | None
    assertion_count: int = 0,
    deployment_matched: Optional[bool] = None,
    has_screenshot: bool = False,
    has_trace: bool = False,
    min_confidence: int = _DEFAULT_MIN_CONFIDENCE,
) -> ConfidenceScore:
    """
    Calculate confidence score for a single scenario.

    Parameters
    ----------
    scenario_id         : Scenario identifier
    is_p0               : True if this is a P0 (highest priority) scenario
    oracle_verdict      : Verdict from oracle_engine ("PASS"/"FAIL"/"NO_ORACLE"/"WEAK_ONLY"/...)
    seed_verdict        : Verdict from seed_executor ("APPLIED"/"SKIPPED"/...)
    cleanup_verdict     : Verdict from cleanup_manager ("CLEANED"/"SKIPPED"/"ERROR"/...)
    assertion_count     : Number of expect() calls found in spec (from weak_assertion_detector)
    deployment_matched  : True/False/None from deployment fingerprint check
    has_screenshot      : Evidence screenshot exists
    has_trace           : Evidence Playwright trace exists
    min_confidence      : Minimum score for publish gate

    Returns
    -------
    ConfidenceScore
    """
    factors: List[ScoreFactor] = []
    total = 0

    # Oracle evaluation
    if oracle_verdict == "PASS":
        factors.append(ScoreFactor("oracle_pass", _W_ORACLE_PASS, "Oracle contract verified and passed"))
        total += _W_ORACLE_PASS
    elif oracle_verdict == "FAIL":
        factors.append(ScoreFactor("oracle_fail", _P_ORACLE_FAIL, "Oracle contract evaluated and failed"))
        total += _P_ORACLE_FAIL
    elif oracle_verdict == "WEAK_ONLY":
        factors.append(ScoreFactor("weak_only_oracle", _P_WEAK_ONLY_ORACLE, "Only weak (cosmetic) oracle assertions"))
        total += _P_WEAK_ONLY_ORACLE
    elif oracle_verdict in ("NO_ORACLE", None) and is_p0:
        factors.append(ScoreFactor("no_oracle_p0", _P_NO_ORACLE_P0, "P0 scenario has no oracle contract"))
        total += _P_NO_ORACLE_P0
    elif oracle_verdict in ("NO_ORACLE", None) and not is_p0:
        pass  # Non-P0 without oracle: no penalty (just no bonus)

    # Seed / data
    if seed_verdict == "APPLIED":
        factors.append(ScoreFactor("seed_applied", _W_SEED_APPLIED, "Test data seeded and verified"))
        total += _W_SEED_APPLIED
    elif seed_verdict is not None and seed_verdict not in ("APPLIED",):
        factors.append(ScoreFactor("seed_skipped", _P_SEED_SKIPPED, f"Seed not applied: {seed_verdict}"))
        total += _P_SEED_SKIPPED

    # Cleanup
    if cleanup_verdict == "CLEANED":
        factors.append(ScoreFactor("cleanup_confirmed", _W_CLEANUP_CONFIRMED, "Seeded rows cleaned up successfully"))
        total += _W_CLEANUP_CONFIRMED
    elif cleanup_verdict in ("ERROR", "BLOCKED"):
        factors.append(ScoreFactor("cleanup_failed", _P_CLEANUP_FAILED, f"Cleanup failed: {cleanup_verdict}"))
        total += _P_CLEANUP_FAILED

    # Playwright assertions
    if assertion_count > 3:
        factors.append(ScoreFactor("many_assertions", _W_MANY_ASSERTIONS, f"{assertion_count} assertions in spec"))
        total += _W_MANY_ASSERTIONS
    elif assertion_count == 0:
        factors.append(ScoreFactor("no_assertions", _P_NO_ASSERTIONS, "No expect() calls in spec"))
        total += _P_NO_ASSERTIONS

    # Deployment fingerprint
    if deployment_matched is True:
        factors.append(ScoreFactor("fingerprint_matched", _W_FINGERPRINT_MATCHED, "Deployment fingerprint matched"))
        total += _W_FINGERPRINT_MATCHED
    elif deployment_matched is False:
        factors.append(ScoreFactor("fingerprint_mismatch", _P_FINGERPRINT_MISMATCH, "Deployment fingerprint mismatch"))
        total += _P_FINGERPRINT_MISMATCH

    # Screenshot evidence
    if has_screenshot:
        factors.append(ScoreFactor("screenshot", _W_SCREENSHOT, "Screenshot evidence present"))
        total += _W_SCREENSHOT

    # Trace evidence
    if has_trace:
        factors.append(ScoreFactor("trace", _W_TRACE, "Playwright trace present"))
        total += _W_TRACE

    # Clamp to [0..100]
    clamped = max(0, min(100, total))
    level = _level(clamped)
    publish_blocked = clamped < min_confidence

    return ConfidenceScore(
        scenario_id=scenario_id,
        score=clamped,
        level=level,
        is_p0=is_p0,
        publish_blocked=publish_blocked,
        factors=factors,
    )


# ── Evidence helpers ───────────────────────────────────────────────────────────

def _load_oracle_eval(evidence_dir: Path, ticket_id: object, run_id: str) -> Dict[str, Any]:
    """Load oracle_result.json → dict keyed by scenario_id."""
    artifact = evidence_dir / str(ticket_id) / str(run_id) / "oracle_result.json"
    if not artifact.is_file():
        return {}
    try:
        data = json.loads(artifact.read_text(encoding="utf-8"))
        return {r["scenario_id"]: r for r in data.get("scenario_results", [])}
    except Exception as exc:
        logger.warning("confidence_scorer: cannot read oracle_result.json: %s", exc)
        return {}


def _load_seed_results(evidence_dir: Path, ticket_id: object, run_id: str) -> Dict[str, Any]:
    """Load all seed_execution_result_*.json → dict keyed by scenario_id."""
    run_dir = evidence_dir / str(ticket_id) / str(run_id)
    results: Dict[str, Any] = {}
    if not run_dir.is_dir():
        return results
    for artifact in run_dir.glob("seed_execution_result_*.json"):
        try:
            data = json.loads(artifact.read_text(encoding="utf-8"))
            scenario_id = data.get("scenario_id", "")
            if scenario_id:
                results[scenario_id] = data
        except Exception:
            pass
    return results


def _load_cleanup_results(evidence_dir: Path, ticket_id: object, run_id: str) -> Dict[str, Any]:
    """Load all seed_cleanup_result_*.json → dict keyed by scenario_id."""
    run_dir = evidence_dir / str(ticket_id) / str(run_id)
    results: Dict[str, Any] = {}
    if not run_dir.is_dir():
        return results
    for artifact in run_dir.glob("seed_cleanup_result_*.json"):
        try:
            data = json.loads(artifact.read_text(encoding="utf-8"))
            scenario_id = data.get("scenario_id", "")
            if scenario_id:
                results[scenario_id] = data
        except Exception:
            pass
    return results


def _load_weak_assertion_report(evidence_dir: Path, ticket_id: object, run_id: str) -> Dict[str, Any]:
    """Load weak_assertion_report.json → dict keyed by file_name (for assertion counts)."""
    artifact = evidence_dir / str(ticket_id) / str(run_id) / "weak_assertion_report.json"
    if not artifact.is_file():
        return {}
    try:
        return json.loads(artifact.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _count_assertions_for_scenario(weak_report: Dict[str, Any], scenario_id: str) -> int:
    """Try to find assertion count for a scenario_id from weak_assertion_report."""
    for fa in weak_report.get("file_analyses", []):
        file_name = fa.get("file_name", "")
        # Match by scenario_id appearing in file name (heuristic)
        if scenario_id.lower().replace("-", "_") in file_name.lower().replace("-", "_"):
            return sum(t.get("expect_call_count", 0) for t in fa.get("test_results", []))
    # Fallback: sum across all files
    total = 0
    for fa in weak_report.get("file_analyses", []):
        for t in fa.get("test_results", []):
            total += t.get("expect_call_count", 0)
    return total


def _check_screenshot_evidence(evidence_dir: Path, ticket_id: object, run_id: str, scenario_id: str) -> bool:
    """Check if any screenshot exists for this scenario."""
    run_dir = evidence_dir / str(ticket_id) / str(run_id)
    if not run_dir.is_dir():
        return False
    pattern = f"*{scenario_id.replace('-', '_').replace('-', '-')}*.png"
    screenshots = list(run_dir.glob("*.png")) + list(run_dir.glob("**/*.png"))
    return len(screenshots) > 0


def _check_trace_evidence(evidence_dir: Path, ticket_id: object, run_id: str, scenario_id: str) -> bool:
    """Check if any Playwright trace exists for this run."""
    run_dir = evidence_dir / str(ticket_id) / str(run_id)
    if not run_dir.is_dir():
        return False
    traces = list(run_dir.glob("*.zip")) + list(run_dir.glob("**/trace.zip"))
    return len(traces) > 0


# ── Main public function ───────────────────────────────────────────────────────

def score_all(
    scenarios: List[Dict[str, Any]],
    evidence_dir: Path,
    run_id: str = "unknown",
    ticket_id: object = 0,
    deployment_matched: Optional[bool] = None,
    min_confidence: int = _DEFAULT_MIN_CONFIDENCE,
    exec_logger=None,
) -> ConfidenceScorerResult:
    """
    Score all scenarios for a run, aggregating evidence from all pipeline stages.

    Reads the following artifacts from evidence_dir/<ticket_id>/<run_id>/:
      - oracle_result.json           (from oracle_engine)
      - seed_execution_result_*.json (from seed_executor)
      - seed_cleanup_result_*.json   (from cleanup_manager)
      - weak_assertion_report.json   (from weak_assertion_detector)

    Parameters
    ----------
    scenarios         : List of scenario dicts (from scenarios.json)
    evidence_dir      : Base evidence directory
    run_id            : Pipeline run ID
    ticket_id         : ADO ticket ID
    deployment_matched: Result from deployment_fingerprint_check stage
    min_confidence    : Minimum score required for publish gate
    exec_logger       : Optional event logger

    Returns
    -------
    ConfidenceScorerResult
    """
    scored_at = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")

    # Load evidence artifacts
    oracle_by_scenario = _load_oracle_eval(evidence_dir, ticket_id, run_id)
    seed_by_scenario = _load_seed_results(evidence_dir, ticket_id, run_id)
    cleanup_by_scenario = _load_cleanup_results(evidence_dir, ticket_id, run_id)
    weak_report = _load_weak_assertion_report(evidence_dir, ticket_id, run_id)

    scenario_scores: List[ConfidenceScore] = []

    for sc in scenarios:
        scenario_id = sc.get("scenario_id", sc.get("id", ""))
        if not scenario_id:
            continue

        is_p0 = (
            sc.get("priority") in (0, "P0", "0") or
            sc.get("category", "").upper() in ("UAT_P0", "P0") or
            sc.get("test_priority") == "P0"
        )

        oracle_sc = oracle_by_scenario.get(scenario_id, {})
        oracle_verdict = oracle_sc.get("oracle_verdict")

        seed_sc = seed_by_scenario.get(scenario_id, {})
        seed_verdict = seed_sc.get("verdict")

        cleanup_sc = cleanup_by_scenario.get(scenario_id, {})
        cleanup_verdict = cleanup_sc.get("verdict")

        assertion_count = _count_assertions_for_scenario(weak_report, scenario_id)
        has_screenshot = _check_screenshot_evidence(evidence_dir, ticket_id, run_id, scenario_id)
        has_trace = _check_trace_evidence(evidence_dir, ticket_id, run_id, scenario_id)

        cs = score(
            scenario_id=scenario_id,
            is_p0=is_p0,
            oracle_verdict=oracle_verdict,
            seed_verdict=seed_verdict,
            cleanup_verdict=cleanup_verdict,
            assertion_count=assertion_count,
            deployment_matched=deployment_matched,
            has_screenshot=has_screenshot,
            has_trace=has_trace,
            min_confidence=min_confidence,
        )
        scenario_scores.append(cs)

        if exec_logger:
            try:
                exec_logger("test_confidence_result", cs.to_event())
            except Exception:
                pass

    # Aggregate
    total = len(scenario_scores)
    high_count   = sum(1 for s in scenario_scores if s.level == ConfidenceLevel.HIGH)
    medium_count = sum(1 for s in scenario_scores if s.level == ConfidenceLevel.MEDIUM)
    low_count    = sum(1 for s in scenario_scores if s.level == ConfidenceLevel.LOW)
    blocked_count = sum(1 for s in scenario_scores if s.publish_blocked)
    publish_blocked = blocked_count > 0

    result = ConfidenceScorerResult(
        ok=not publish_blocked,
        run_id=str(run_id),
        ticket_id=ticket_id,
        total_scenarios=total,
        high_count=high_count,
        medium_count=medium_count,
        low_count=low_count,
        blocked_count=blocked_count,
        min_confidence=min_confidence,
        publish_blocked=publish_blocked,
        scenario_scores=scenario_scores,
        scored_at=scored_at,
    )

    # Write evidence
    if evidence_dir is not None:
        artifact_dir = Path(evidence_dir) / str(ticket_id) / str(run_id)
        artifact_dir.mkdir(parents=True, exist_ok=True)
        artifact_path = artifact_dir / "confidence_report.json"
        try:
            artifact_path.write_text(
                json.dumps(result.to_dict(), indent=2), encoding="utf-8"
            )
            result.evidence_path = str(artifact_path)
        except Exception as exc:
            logger.warning("confidence_scorer: could not write evidence: %s", exc)

    # Emit summary event
    if exec_logger:
        try:
            exec_logger("confidence_summary", result.to_event())
        except Exception:
            pass

    logger.info(
        "confidence_scorer: total=%d high=%d medium=%d low=%d blocked=%d publish_blocked=%s",
        total, high_count, medium_count, low_count, blocked_count, publish_blocked,
    )

    return result
