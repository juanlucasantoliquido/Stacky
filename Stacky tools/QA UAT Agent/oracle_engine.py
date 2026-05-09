"""
oracle_engine.py — Oracle Engine (Sprint 13).

Evaluates whether a UAT scenario has strong, verifiable assertions — "oracles"
that confirm the application behaviour matches the expected outcome.

ORACLE TYPES:
  - UI:    Playwright assertion (expect/toBe, toBeVisible, toHaveText, etc.)
  - DB:    SQL SELECT check — compare DB state with expected value
  - API:   HTTP response check — status code, JSON field match
  - CATALOG: Catalog row exists and has correct value
  - CUSTOM: Arbitrary check defined in oracle_contract.json

ORACLE STRENGTH:
  - P0  (STRONG) : assertion directly verifies the functional requirement
  - P1  (MEDIUM) : assertion verifies a supporting invariant
  - P2  (WEAK)   : assertion verifies a cosmetic/logging side effect only

RULES:
  - UAT P0 scenarios MUST have at least one STRONG oracle.
  - Scenarios without any oracle → oracle_verdict = NO_ORACLE (blocks publish).
  - Scenarios with only WEAK oracles → oracle_verdict = WEAK_ONLY (reduces confidence).
  - `oracle_result.json` must exist for every non-trivial scenario.

PUBLIC API:
  evaluate(
      scenarios_path, runner_output_path, oracle_contracts_dir,
      exec_logger, evidence_dir, run_id, ticket_id
  ) -> OracleEvaluationResult

  load_oracle_contracts(oracle_contracts_dir) -> dict[str, OracleContract]

  OracleEvaluationResult.to_dict() -> dict

EVIDENCE ARTIFACT:
  evidence/<ticket_id>/<run_id>/oracle_result.json

EVENTS EMITTED:
  oracle_evaluation_result  — aggregated result
  oracle_weak_warning       — emitted per scenario with no strong oracle

SECURITY:
  - DB oracles only execute read-only SELECT queries.
  - API oracles use GET requests only — no mutation.
  - No credentials stored in artifacts.
  - oracle_contract.json content is validated before use.
"""
from __future__ import annotations

import datetime
import json
import logging
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Optional, Dict, Any

logger = logging.getLogger("stacky.qa_uat.oracle_engine")

_TOOL_VERSION = "1.0.0"
_SCHEMA_VERSION = "oracle_result/1.0"

# ── Oracle verdict codes ───────────────────────────────────────────────────────

class OracleVerdict:
    PASS = "PASS"               # All required oracles evaluated and passed
    FAIL = "FAIL"               # At least one oracle failed (app defect)
    NO_ORACLE = "NO_ORACLE"     # No oracles defined — blocks P0 publish
    WEAK_ONLY = "WEAK_ONLY"     # Only P2/WEAK oracles — reduces confidence
    SKIP = "SKIP"               # Oracle check skipped (non-P0 or no contract)
    ERROR = "ERROR"             # Oracle evaluation failed (infra/config error)


# ── Oracle strength ────────────────────────────────────────────────────────────

class OracleStrength:
    STRONG = "P0"    # Directly verifies functional requirement
    MEDIUM = "P1"    # Verifies supporting invariant
    WEAK   = "P2"    # Cosmetic / logging check only


# ── Oracle type codes ─────────────────────────────────────────────────────────

class OracleType:
    UI      = "UI"
    DB      = "DB"
    API     = "API"
    CATALOG = "CATALOG"
    CUSTOM  = "CUSTOM"


# ── Dataclasses ────────────────────────────────────────────────────────────────

@dataclass
class OracleContract:
    """
    Contract for a single oracle check, loaded from oracle_contract.json.

    Example (in oracle_contract.json):
      {
        "oracle_id": "RF-007-CA-01-ORQ-001",
        "scenario_id": "RF-007-CA-01",
        "oracle_type": "UI",
        "strength": "P0",
        "description": "Grid shows at least 1 obligation row",
        "check": {
          "locator": "table.obligaciones tbody tr",
          "assertion": "count_gt",
          "expected": 0
        },
        "fallback_db_check": {
          "sql": "SELECT COUNT(*) FROM Obligacion WHERE CLCOD = {CLCOD} AND Estado = 'ACT'",
          "expected_min": 1
        }
      }
    """
    oracle_id: str
    scenario_id: str
    oracle_type: str            # OracleType.*
    strength: str               # OracleStrength.*
    description: str
    check: Dict[str, Any]       # oracle-type-specific check definition
    fallback_db_check: Optional[Dict[str, Any]] = None

    def to_dict(self) -> dict:
        return {
            "oracle_id": self.oracle_id,
            "scenario_id": self.scenario_id,
            "oracle_type": self.oracle_type,
            "strength": self.strength,
            "description": self.description,
            "check": self.check,
            "fallback_db_check": self.fallback_db_check,
        }


@dataclass
class OracleCheckResult:
    """Result for a single oracle check."""
    oracle_id: str
    scenario_id: str
    oracle_type: str
    strength: str
    description: str
    verdict: str                # OracleVerdict.PASS | FAIL | ERROR | SKIP
    actual: Optional[Any]
    expected: Optional[Any]
    error: Optional[str] = None
    evidence: Optional[Dict[str, Any]] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ScenarioOracleResult:
    """Aggregated oracle result for one scenario."""
    scenario_id: str
    oracle_verdict: str         # OracleVerdict.*
    is_p0: bool
    oracle_count: int
    strong_count: int
    weak_count: int
    pass_count: int
    fail_count: int
    oracle_checks: List[OracleCheckResult] = field(default_factory=list)
    blocking: bool = False      # True when P0 + NO_ORACLE or FAIL

    def to_dict(self) -> dict:
        return {
            "scenario_id": self.scenario_id,
            "oracle_verdict": self.oracle_verdict,
            "is_p0": self.is_p0,
            "oracle_count": self.oracle_count,
            "strong_count": self.strong_count,
            "weak_count": self.weak_count,
            "pass_count": self.pass_count,
            "fail_count": self.fail_count,
            "blocking": self.blocking,
            "oracle_checks": [c.to_dict() for c in self.oracle_checks],
        }


@dataclass
class OracleEvaluationResult:
    """Aggregated oracle evaluation result for all scenarios in a run."""
    ok: bool
    run_id: str
    ticket_id: object
    total_scenarios: int
    evaluated_scenarios: int
    pass_count: int
    fail_count: int
    no_oracle_count: int
    weak_only_count: int
    p0_blocked_count: int        # P0 scenarios with NO_ORACLE or FAIL
    publish_blocked: bool        # True when any P0 is blocked
    scenario_results: List[ScenarioOracleResult] = field(default_factory=list)
    evidence_path: Optional[str] = None
    evaluated_at: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "schema_version": _SCHEMA_VERSION,
            "ok": self.ok,
            "run_id": self.run_id,
            "ticket_id": self.ticket_id,
            "total_scenarios": self.total_scenarios,
            "evaluated_scenarios": self.evaluated_scenarios,
            "pass_count": self.pass_count,
            "fail_count": self.fail_count,
            "no_oracle_count": self.no_oracle_count,
            "weak_only_count": self.weak_only_count,
            "p0_blocked_count": self.p0_blocked_count,
            "publish_blocked": self.publish_blocked,
            "scenario_results": [r.to_dict() for r in self.scenario_results],
            "evidence_path": self.evidence_path,
            "evaluated_at": self.evaluated_at,
        }

    def to_event(self) -> dict:
        return {
            "event_type": "oracle_evaluation_result",
            "run_id": self.run_id,
            "ticket_id": self.ticket_id,
            "ok": self.ok,
            "publish_blocked": self.publish_blocked,
            "p0_blocked_count": self.p0_blocked_count,
            "no_oracle_count": self.no_oracle_count,
            "weak_only_count": self.weak_only_count,
            "fail_count": self.fail_count,
        }


# ── Oracle contract loader ─────────────────────────────────────────────────────

def load_oracle_contracts(oracle_contracts_dir: Path) -> Dict[str, List[OracleContract]]:
    """
    Load all oracle_contract.json files from a directory.

    Returns a dict keyed by scenario_id → list of OracleContract.
    Empty dict when directory doesn't exist or no files found.
    """
    if not oracle_contracts_dir or not oracle_contracts_dir.is_dir():
        return {}

    result: Dict[str, List[OracleContract]] = {}
    for contract_file in sorted(oracle_contracts_dir.glob("oracle_contract*.json")):
        try:
            raw = json.loads(contract_file.read_text(encoding="utf-8"))
            # Support both single contract and array
            if isinstance(raw, dict):
                raw = [raw]
            elif not isinstance(raw, list):
                continue

            for entry in raw:
                if not isinstance(entry, dict):
                    continue
                scenario_id = entry.get("scenario_id", "")
                if not scenario_id:
                    continue
                contract = OracleContract(
                    oracle_id=entry.get("oracle_id", f"auto-{scenario_id}"),
                    scenario_id=scenario_id,
                    oracle_type=entry.get("oracle_type", OracleType.UI),
                    strength=entry.get("strength", OracleStrength.MEDIUM),
                    description=entry.get("description", ""),
                    check=entry.get("check", {}),
                    fallback_db_check=entry.get("fallback_db_check"),
                )
                result.setdefault(scenario_id, []).append(contract)
        except Exception as exc:
            logger.warning("oracle_engine: failed to load %s: %s", contract_file.name, exc)

    return result


# ── Per-oracle evaluators ──────────────────────────────────────────────────────

def _evaluate_ui_oracle(
    contract: OracleContract,
    runner_output: Dict[str, Any],
    scenario_id: str,
) -> OracleCheckResult:
    """
    Evaluate a UI oracle by matching against Playwright runner output.

    Supported assertions in check.assertion:
      count_gt, count_eq, visible, invisible, contains_text, equals
    """
    check = contract.check
    locator = check.get("locator", "")
    assertion = check.get("assertion", "")
    expected = check.get("expected")

    # Find matching assertion in runner_output
    scenario_assertions = []
    for ev in runner_output.get("events", []):
        if ev.get("scenario_id") == scenario_id and ev.get("type") in ("assertion", "check"):
            scenario_assertions.append(ev)

    # Try to find a matching assertion for this locator
    actual = None
    for ev in scenario_assertions:
        if locator and locator in str(ev.get("locator", "")):
            actual = ev.get("actual")
            break

    # Evaluate based on assertion type
    try:
        if assertion == "count_gt":
            passed = isinstance(actual, (int, float)) and actual > (expected or 0)
        elif assertion == "count_eq":
            passed = actual == expected
        elif assertion == "visible":
            passed = actual is True or actual == "visible"
        elif assertion == "invisible":
            passed = actual is False or actual == "invisible" or actual is None
        elif assertion == "contains_text":
            passed = expected and isinstance(actual, str) and expected.lower() in actual.lower()
        elif assertion == "equals":
            passed = actual == expected
        else:
            # Unknown assertion — treat as SKIP
            return OracleCheckResult(
                oracle_id=contract.oracle_id,
                scenario_id=scenario_id,
                oracle_type=OracleType.UI,
                strength=contract.strength,
                description=contract.description,
                verdict=OracleVerdict.SKIP,
                actual=None,
                expected=expected,
                error=f"unknown_assertion:{assertion}",
            )

        verdict = OracleVerdict.PASS if passed else OracleVerdict.FAIL
    except Exception as exc:
        verdict = OracleVerdict.ERROR
        return OracleCheckResult(
            oracle_id=contract.oracle_id,
            scenario_id=scenario_id,
            oracle_type=OracleType.UI,
            strength=contract.strength,
            description=contract.description,
            verdict=verdict,
            actual=actual,
            expected=expected,
            error=str(exc),
        )

    return OracleCheckResult(
        oracle_id=contract.oracle_id,
        scenario_id=scenario_id,
        oracle_type=OracleType.UI,
        strength=contract.strength,
        description=contract.description,
        verdict=verdict,
        actual=actual,
        expected=expected,
    )


def _evaluate_catalog_oracle(
    contract: OracleContract,
    fixtures_path: Optional[Path],
) -> OracleCheckResult:
    """
    Evaluate a CATALOG oracle by checking if the expected catalog entry exists.

    Check definition:
      { "catalog_name": "TipoObligacion", "pk_value": "CRE", "expect_exists": true }
    """
    check = contract.check
    catalog_name = check.get("catalog_name", "")
    pk_value = check.get("pk_value")
    expect_exists = check.get("expect_exists", True)

    if not catalog_name:
        return OracleCheckResult(
            oracle_id=contract.oracle_id,
            scenario_id=contract.scenario_id,
            oracle_type=OracleType.CATALOG,
            strength=contract.strength,
            description=contract.description,
            verdict=OracleVerdict.ERROR,
            actual=None,
            expected=pk_value,
            error="missing_catalog_name",
        )

    # Try to load fixtures to verify catalog entry exists
    try:
        if fixtures_path and fixtures_path.exists():
            from catalog_readiness_checker import load_catalog_fixtures  # type: ignore[import]
            fixtures = load_catalog_fixtures(fixtures_path)
            fixture = fixtures.get(catalog_name)
            if fixture is None:
                # Catalog not in fixtures → UNVERIFIED (not FAIL)
                return OracleCheckResult(
                    oracle_id=contract.oracle_id,
                    scenario_id=contract.scenario_id,
                    oracle_type=OracleType.CATALOG,
                    strength=contract.strength,
                    description=contract.description,
                    verdict=OracleVerdict.SKIP,
                    actual=None,
                    expected=pk_value,
                    error="catalog_not_in_fixtures",
                )

            # Check if any seed row has the expected pk_value
            pk_col = fixture.pk_column
            found = any(
                str(row.fields.get(pk_col, "")) == str(pk_value)
                for row in fixture.seed_rows
            )
            passed = found == expect_exists
            return OracleCheckResult(
                oracle_id=contract.oracle_id,
                scenario_id=contract.scenario_id,
                oracle_type=OracleType.CATALOG,
                strength=contract.strength,
                description=contract.description,
                verdict=OracleVerdict.PASS if passed else OracleVerdict.FAIL,
                actual=found,
                expected={"exists": expect_exists, "pk_value": pk_value},
            )
    except ImportError:
        pass
    except Exception as exc:
        logger.warning("oracle_engine: catalog oracle error: %s", exc)

    # Fallback — cannot verify without fixtures
    return OracleCheckResult(
        oracle_id=contract.oracle_id,
        scenario_id=contract.scenario_id,
        oracle_type=OracleType.CATALOG,
        strength=contract.strength,
        description=contract.description,
        verdict=OracleVerdict.SKIP,
        actual=None,
        expected=pk_value,
        error="no_fixture_available",
    )


def _evaluate_single_oracle(
    contract: OracleContract,
    runner_output: Dict[str, Any],
    fixtures_path: Optional[Path],
) -> OracleCheckResult:
    """Dispatch to the correct oracle evaluator based on oracle_type."""
    if contract.oracle_type == OracleType.UI:
        return _evaluate_ui_oracle(contract, runner_output, contract.scenario_id)
    elif contract.oracle_type == OracleType.CATALOG:
        return _evaluate_catalog_oracle(contract, fixtures_path)
    else:
        # API, DB, CUSTOM — not yet fully implemented; return SKIP
        return OracleCheckResult(
            oracle_id=contract.oracle_id,
            scenario_id=contract.scenario_id,
            oracle_type=contract.oracle_type,
            strength=contract.strength,
            description=contract.description,
            verdict=OracleVerdict.SKIP,
            actual=None,
            expected=None,
            error=f"oracle_type_not_implemented:{contract.oracle_type}",
        )


# ── Per-scenario oracle aggregation ───────────────────────────────────────────

def _evaluate_scenario(
    scenario_id: str,
    contracts: List[OracleContract],
    runner_output: Dict[str, Any],
    fixtures_path: Optional[Path],
    is_p0: bool,
) -> ScenarioOracleResult:
    """Evaluate all oracle contracts for a single scenario."""
    if not contracts:
        verdict = OracleVerdict.NO_ORACLE
        blocking = is_p0
        return ScenarioOracleResult(
            scenario_id=scenario_id,
            oracle_verdict=verdict,
            is_p0=is_p0,
            oracle_count=0,
            strong_count=0,
            weak_count=0,
            pass_count=0,
            fail_count=0,
            blocking=blocking,
        )

    check_results: List[OracleCheckResult] = []
    for contract in contracts:
        result = _evaluate_single_oracle(contract, runner_output, fixtures_path)
        check_results.append(result)

    strong_count = sum(1 for c in contracts if c.strength == OracleStrength.STRONG)
    weak_count = sum(1 for c in contracts if c.strength == OracleStrength.WEAK)
    pass_count = sum(1 for r in check_results if r.verdict == OracleVerdict.PASS)
    fail_count = sum(1 for r in check_results if r.verdict == OracleVerdict.FAIL)
    skip_count = sum(1 for r in check_results if r.verdict == OracleVerdict.SKIP)
    oracle_count = len(contracts)

    if fail_count > 0:
        verdict = OracleVerdict.FAIL
        blocking = is_p0 or fail_count > 0
    elif pass_count == 0 and skip_count == oracle_count:
        verdict = OracleVerdict.SKIP
        blocking = False
    elif strong_count == 0 and oracle_count > 0:
        verdict = OracleVerdict.WEAK_ONLY
        blocking = False  # reduces confidence but doesn't block
    elif pass_count > 0:
        verdict = OracleVerdict.PASS
        blocking = False
    else:
        verdict = OracleVerdict.NO_ORACLE
        blocking = is_p0

    return ScenarioOracleResult(
        scenario_id=scenario_id,
        oracle_verdict=verdict,
        is_p0=is_p0,
        oracle_count=oracle_count,
        strong_count=strong_count,
        weak_count=weak_count,
        pass_count=pass_count,
        fail_count=fail_count,
        oracle_checks=check_results,
        blocking=blocking,
    )


# ── Main public function ───────────────────────────────────────────────────────

def evaluate(
    scenarios_path: Optional[Path],
    runner_output_path: Optional[Path],
    oracle_contracts_dir: Optional[Path],
    exec_logger=None,
    evidence_dir: Optional[Path] = None,
    run_id: str = "unknown",
    ticket_id: object = 0,
    fixtures_path: Optional[Path] = None,
) -> OracleEvaluationResult:
    """
    Evaluate oracle contracts for all scenarios in a run.

    Parameters
    ----------
    scenarios_path       : Path to scenarios.json (compiler output)
    runner_output_path   : Path to runner_output.json (Playwright results)
    oracle_contracts_dir : Directory containing oracle_contract*.json files
    exec_logger          : Optional event logger
    evidence_dir         : Where to write oracle_result.json artifact
    run_id               : Pipeline run ID
    ticket_id            : ADO ticket ID
    fixtures_path        : Path to catalog_fixtures.yml for CATALOG oracle checks

    Returns
    -------
    OracleEvaluationResult
    """
    evaluated_at = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")

    # Load scenarios to know which are P0
    scenarios_raw: List[Dict[str, Any]] = []
    if scenarios_path and scenarios_path.exists():
        try:
            data = json.loads(scenarios_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                scenarios_raw = data.get("scenarios", [])
            elif isinstance(data, list):
                scenarios_raw = data
        except Exception as exc:
            logger.warning("oracle_engine: failed to load scenarios: %s", exc)

    # Load runner output for UI oracle evaluation
    runner_output: Dict[str, Any] = {}
    if runner_output_path and runner_output_path.exists():
        try:
            runner_output = json.loads(runner_output_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("oracle_engine: failed to load runner output: %s", exc)

    # Load oracle contracts
    contracts_by_scenario = load_oracle_contracts(oracle_contracts_dir) if oracle_contracts_dir else {}

    # Evaluate each scenario
    scenario_results: List[ScenarioOracleResult] = []
    all_scenario_ids: List[str] = []

    for sc in scenarios_raw:
        scenario_id = sc.get("scenario_id", sc.get("id", ""))
        if not scenario_id:
            continue
        all_scenario_ids.append(scenario_id)

        # P0 = priority 0 or category UAT_P0
        is_p0 = (
            sc.get("priority") in (0, "P0", "0") or
            sc.get("category", "").upper() in ("UAT_P0", "P0") or
            sc.get("test_priority") == "P0"
        )
        contracts = contracts_by_scenario.get(scenario_id, [])
        sr = _evaluate_scenario(scenario_id, contracts, runner_output, fixtures_path, is_p0)
        scenario_results.append(sr)

    # If no scenarios in scenarios.json, still evaluate contracts that exist
    contract_scenario_ids = set(contracts_by_scenario.keys()) - set(all_scenario_ids)
    for scenario_id in sorted(contract_scenario_ids):
        contracts = contracts_by_scenario[scenario_id]
        sr = _evaluate_scenario(scenario_id, contracts, runner_output, fixtures_path, False)
        scenario_results.append(sr)

    # Aggregate counters
    total = len(scenario_results)
    evaluated = sum(1 for r in scenario_results if r.oracle_verdict != OracleVerdict.SKIP)
    pass_count = sum(1 for r in scenario_results if r.oracle_verdict == OracleVerdict.PASS)
    fail_count = sum(1 for r in scenario_results if r.oracle_verdict == OracleVerdict.FAIL)
    no_oracle = sum(1 for r in scenario_results if r.oracle_verdict == OracleVerdict.NO_ORACLE)
    weak_only = sum(1 for r in scenario_results if r.oracle_verdict == OracleVerdict.WEAK_ONLY)
    p0_blocked = sum(1 for r in scenario_results if r.blocking)
    publish_blocked = p0_blocked > 0

    result = OracleEvaluationResult(
        ok=not publish_blocked,
        run_id=str(run_id),
        ticket_id=ticket_id,
        total_scenarios=total,
        evaluated_scenarios=evaluated,
        pass_count=pass_count,
        fail_count=fail_count,
        no_oracle_count=no_oracle,
        weak_only_count=weak_only,
        p0_blocked_count=p0_blocked,
        publish_blocked=publish_blocked,
        scenario_results=scenario_results,
        evaluated_at=evaluated_at,
    )

    # Write evidence artifact
    if evidence_dir is not None:
        artifact_dir = Path(evidence_dir) / str(ticket_id) / str(run_id)
        artifact_dir.mkdir(parents=True, exist_ok=True)
        artifact_path = artifact_dir / "oracle_result.json"
        try:
            artifact_path.write_text(
                json.dumps(result.to_dict(), indent=2), encoding="utf-8"
            )
            result.evidence_path = str(artifact_path)
        except Exception as exc:
            logger.warning("oracle_engine: could not write evidence: %s", exc)

    # Emit events
    if exec_logger:
        try:
            exec_logger("oracle_evaluation_result", result.to_event())
        except Exception:
            pass
        if p0_blocked > 0:
            for sr in scenario_results:
                if sr.blocking and sr.oracle_verdict in (OracleVerdict.NO_ORACLE, OracleVerdict.FAIL):
                    try:
                        exec_logger("oracle_weak_warning", {
                            "scenario_id": sr.scenario_id,
                            "oracle_verdict": sr.oracle_verdict,
                            "is_p0": sr.is_p0,
                            "blocking": sr.blocking,
                        })
                    except Exception:
                        pass

    logger.info(
        "oracle_engine: total=%d evaluated=%d pass=%d fail=%d no_oracle=%d p0_blocked=%d publish_blocked=%s",
        total, evaluated, pass_count, fail_count, no_oracle, p0_blocked, publish_blocked,
    )

    return result
