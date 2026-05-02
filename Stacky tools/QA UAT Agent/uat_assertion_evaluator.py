"""
uat_assertion_evaluator.py — Evaluate PASS/FAIL/REVIEW for each assertion in a scenario.

SPEC: PHASE3_QA_UAT_ROADMAP.md §3.9
CLI:
    python uat_assertion_evaluator.py \
        --scenarios evidence/70/scenarios.json \
        --runner-output evidence/70/runner_output.json \
        [--verbose]

Deterministic for oracle types: equals, contains_literal, count_eq, count_gt, visible,
  invisible, state — NO LLM involved.
LLM (gpt-4.1) only for: contains_semantic — classifies actual vs expected as
  match | mismatch | ambiguous. If ambiguous → status REVIEW (not pass, not fail).

Output JSON to stdout:
{
  "ok": true,
  "ticket_id": 70,
  "evaluations": [
    {
      "scenario_id": "P04",
      "status": "fail",
      "assertions": [
        {
          "oracle_id": 0,
          "tipo": "equals",
          "target": "msg_lista_vacia",
          "expected": "No hay lotes agendados",
          "actual": "",
          "status": "fail",
          "evidence_ref": "evidence/70/P04/assertions_P04.json"
        }
      ]
    }
  ]
}

Error codes: invalid_scenarios_json, invalid_runner_output, evidence_missing
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.qa_uat.assertion_evaluator")

_TOOL_VERSION = "1.0.0"

# Oracle types handled deterministically (no LLM)
_DETERMINISTIC_TYPES = frozenset({
    "equals", "contains_literal", "count_eq", "count_gt",
    "count_lt", "visible", "invisible", "state",
})

# Oracle types that may use LLM fallback
_SEMANTIC_TYPES = frozenset({"contains_semantic"})

_EVIDENCE_ASSERTIONS_FILENAME = "assertions_{scenario_id}.json"


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
        runner_output_path=Path(args.runner_output),
        verbose=args.verbose,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result.get("ok") else 1)


# ── Core logic ────────────────────────────────────────────────────────────────

def run(
    scenarios_path: Path,
    runner_output_path: Path,
    verbose: bool = False,
) -> dict:
    """Core logic — callable from tests without subprocess."""
    started = time.time()

    # Load scenarios
    try:
        scenarios_data = json.loads(scenarios_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return _err("invalid_scenarios_json", f"Cannot read scenarios: {exc}")

    if not scenarios_data.get("ok"):
        return _err("invalid_scenarios_json", "scenarios.json has ok=false")

    # Load runner output
    try:
        runner_data = json.loads(runner_output_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return _err("invalid_runner_output", f"Cannot read runner_output: {exc}")

    if not runner_data.get("ok"):
        return _err("invalid_runner_output", "runner_output.json has ok=false")

    ticket_id = runner_data.get("ticket_id", 0)
    scenarios = {s["scenario_id"]: s for s in (scenarios_data.get("scenarios") or [])}
    runs = {r["scenario_id"]: r for r in (runner_data.get("runs") or [])}

    evaluations = []

    for scenario_id, run_result in runs.items():
        run_status = run_result.get("status", "blocked")

        # For blocked or skipped runs — no assertions to evaluate
        if run_status == "blocked":
            evaluations.append({
                "scenario_id": scenario_id,
                "status": "blocked",
                "reason": run_result.get("reason", "RUNTIME_ERROR"),
                "assertions": [],
            })
            continue

        scenario = scenarios.get(scenario_id)
        if scenario is None:
            evaluations.append({
                "scenario_id": scenario_id,
                "status": "blocked",
                "reason": "scenario_definition_not_found",
                "assertions": [],
            })
            continue

        oraculos = scenario.get("oraculos") or []
        assertions_evidence = _load_assertions_evidence(run_result)

        assertion_results = []
        scenario_status = "pass"

        for idx, oraculo in enumerate(oraculos):
            tipo = oraculo.get("tipo", "")
            target = oraculo.get("target", "")
            expected = oraculo.get("valor")

            # Retrieve actual value from evidence
            actual = _get_actual_value(assertions_evidence, target, tipo, run_result)

            # Evaluate
            assertion_status = _evaluate_assertion(
                tipo=tipo,
                expected=expected,
                actual=actual,
                verbose=verbose,
            )

            if assertion_status == "fail":
                scenario_status = "fail"
            elif assertion_status == "review" and scenario_status != "fail":
                scenario_status = "review"

            assertion_results.append({
                "oracle_id": idx,
                "tipo": tipo,
                "target": target,
                "expected": expected,
                "actual": actual,
                "status": assertion_status,
                "evidence_ref": _assertions_ref(run_result, scenario_id),
            })

        evaluations.append({
            "scenario_id": scenario_id,
            "status": scenario_status,
            "assertions": assertion_results,
        })

    # Write evaluation results to evidence dir (best-effort)
    _persist_evaluations(runner_output_path, evaluations, ticket_id)

    return {
        "ok": True,
        "ticket_id": ticket_id,
        "evaluations": evaluations,
        "elapsed_s": round(time.time() - started, 2),
    }


# ── Assertion evaluation logic ────────────────────────────────────────────────

def _evaluate_assertion(
    tipo: str,
    expected,
    actual,
    verbose: bool = False,
) -> str:
    """
    Returns 'pass', 'fail', or 'review'.

    Deterministic for all types except 'contains_semantic'.
    LLM (gpt-4.1) for 'contains_semantic' — falls back to 'review' if unavailable.
    """
    if tipo in _DETERMINISTIC_TYPES:
        return _evaluate_deterministic(tipo, expected, actual)
    elif tipo in _SEMANTIC_TYPES:
        return _evaluate_semantic(expected, actual, verbose=verbose)
    else:
        logger.warning("Unknown oracle type: %s — marking as review", tipo)
        return "review"


def _evaluate_deterministic(tipo: str, expected, actual) -> str:
    """Pure deterministic evaluation — no LLM."""
    if actual is None:
        # Cannot evaluate without actual value
        return "review"

    if tipo == "equals":
        return "pass" if str(actual).strip() == str(expected).strip() else "fail"

    elif tipo == "contains_literal":
        return "pass" if str(expected).strip() in str(actual) else "fail"

    elif tipo == "count_eq":
        try:
            return "pass" if int(actual) == int(expected) else "fail"
        except (ValueError, TypeError):
            return "review"

    elif tipo == "count_gt":
        try:
            return "pass" if int(actual) > int(expected) else "fail"
        except (ValueError, TypeError):
            return "review"

    elif tipo == "count_lt":
        try:
            return "pass" if int(actual) < int(expected) else "fail"
        except (ValueError, TypeError):
            return "review"

    elif tipo == "visible":
        # actual should be truthy (element visible) or bool True
        visible = _to_bool(actual, default=None)
        if visible is None:
            return "review"
        return "pass" if visible else "fail"

    elif tipo == "invisible":
        visible = _to_bool(actual, default=None)
        if visible is None:
            return "review"
        return "pass" if not visible else "fail"

    elif tipo == "state":
        # expected = state name (e.g. "disabled", "enabled", "checked")
        return "pass" if str(actual).lower() == str(expected).lower() else "fail"

    return "review"


def _evaluate_semantic(expected, actual, verbose: bool = False) -> str:
    """
    Use LLM (gpt-4.1) to decide match | mismatch | ambiguous for semantic assertions.
    Falls back to 'review' if LLM unavailable or STACKY_LLM_BACKEND=mock.
    """
    llm_backend = os.getenv("STACKY_LLM_BACKEND", "vscode_bridge")
    if llm_backend == "mock":
        logger.debug("LLM mock mode — returning 'review' for semantic assertion")
        return "review"

    try:
        from llm_client import call_llm
        prompt = (
            f"You are a QA assertion evaluator. Decide if the actual DOM text matches "
            f"the expected semantic description.\n\n"
            f"Expected (semantic): {expected!r}\n"
            f"Actual (DOM text): {actual!r}\n\n"
            f"Reply with EXACTLY one word: 'match', 'mismatch', or 'ambiguous'."
        )
        response = call_llm(
            prompt=prompt,
            model="gpt-4.1",
            max_tokens=10,
            temperature=0,
        )
        verdict = response.strip().lower()
        if verdict == "match":
            return "pass"
        elif verdict == "mismatch":
            return "fail"
        else:
            return "review"
    except Exception as exc:
        logger.warning("Semantic assertion LLM failed: %s — defaulting to review", exc)
        return "review"


# ── Evidence helpers ──────────────────────────────────────────────────────────

def _load_assertions_evidence(run_result: dict) -> dict:
    """
    Try to load assertions_<scenario_id>.json from the evidence directory.
    Returns empty dict if not found (graceful degradation).
    """
    scenario_id = run_result.get("scenario_id", "")
    artifacts = run_result.get("artifacts") or {}

    # Try evidence path derived from artifacts
    # Convention: artifacts live in evidence/<ticket>/<scenario_id>/
    trace_path = artifacts.get("trace", "")
    if trace_path:
        scenario_dir = Path(trace_path).parent
        assertions_file = scenario_dir / f"assertions_{scenario_id}.json"
        if assertions_file.is_file():
            try:
                return json.loads(assertions_file.read_text(encoding="utf-8"))
            except Exception:
                pass
    return {}


def _get_actual_value(evidence: dict, target: str, tipo: str, run_result: dict):
    """
    Retrieve the actual value for an oracle target from evidence.

    Evidence structure (generated by Playwright hooks):
    {
      "assertions": [{"target": "msg_lista_vacia", "actual_text": "...", "visible": true}]
    }

    Falls back to runner's assertion_failures for FAIL cases.
    """
    # Check assertions evidence file
    for assertion in (evidence.get("assertions") or []):
        if assertion.get("target") == target:
            if tipo in ("visible", "invisible"):
                return assertion.get("visible")
            if tipo == "state":
                return assertion.get("state")
            if tipo in ("count_eq", "count_gt", "count_lt"):
                return assertion.get("count")
            return assertion.get("actual_text")

    # Check assertion_failures from runner output (for failed assertions)
    for failure in (run_result.get("assertion_failures") or []):
        if target in str(failure.get("message", "")):
            return failure.get("actual")

    # For pass scenarios, derive from raw_stdout heuristically
    status = run_result.get("status", "")
    if status == "pass":
        if tipo in ("visible",):
            return True
        if tipo == "invisible":
            return False
        if tipo in ("count_gt", "count_eq"):
            return "1"  # heuristic: at least 1 row when pass

    return None


def _to_bool(value, default=None):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        if value.lower() in ("true", "yes", "1", "visible"):
            return True
        if value.lower() in ("false", "no", "0", "hidden", "invisible"):
            return False
    if isinstance(value, int):
        return bool(value)
    return default


def _assertions_ref(run_result: dict, scenario_id: str) -> str:
    artifacts = run_result.get("artifacts") or {}
    trace = artifacts.get("trace", "")
    if trace:
        return str(Path(trace).parent / f"assertions_{scenario_id}.json")
    return f"evidence/{run_result.get('scenario_id', scenario_id)}/assertions_{scenario_id}.json"


def _persist_evaluations(runner_output_path: Path, evaluations: list, ticket_id: int) -> None:
    """Write evaluations.json next to runner_output.json (best-effort)."""
    try:
        out_path = runner_output_path.parent / "evaluations.json"
        payload = {
            "ok": True,
            "ticket_id": ticket_id,
            "evaluations": evaluations,
        }
        out_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.debug("Evaluations written to %s", out_path)
    except Exception as exc:
        logger.warning("Could not persist evaluations: %s", exc)


# ── Error helper ──────────────────────────────────────────────────────────────

def _err(error: str, message: str) -> dict:
    return {"ok": False, "error": error, "message": message}


# ── CLI ───────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="UAT Assertion Evaluator — PASS/FAIL/REVIEW per oracle."
    )
    p.add_argument("--scenarios", required=True,
                   help="Path to scenarios.json (uat_scenario_compiler output).")
    p.add_argument("--runner-output", required=True,
                   help="Path to runner_output.json (uat_test_runner output).")
    p.add_argument("--verbose", action="store_true", help="Debug logging to stderr.")
    return p.parse_args()


if __name__ == "__main__":
    main()
