"""
uat_failure_analyzer.py — Classify the root cause of UAT test failures.

SPEC: PHASE3_QA_UAT_ROADMAP.md §3.10
CLI:
    python uat_failure_analyzer.py \
        --evaluations evidence/70/evaluations.json \
        --runner-output evidence/70/runner_output.json \
        [--verbose]

Only invoked for scenarios with status=fail in the evaluation output.
LLM (gpt-4.1) classifies each failure into one of the taxonomy categories.
Falls back to category=unknown with confidence=low if LLM unavailable.

Failure taxonomy (enum):
  regression            — product worked before, now broken
  missing_precondition  — test data or RIDIOMA not applied
  data_drift            — expected data changed (RIDIOMA text, BD values)
  ui_change             — DOM structure changed, selector no longer valid
  wrong_expected_in_ticket — oracle in ticket is incorrect
  environment_issue     — deploy, network, config problem
  unknown               — cannot classify

Output JSON to stdout:
{
  "ok": true,
  "ticket_id": 70,
  "analyses": [
    {
      "scenario_id": "P04",
      "category": "data_drift",
      "hypothesis_md": "El texto del mensaje RIDIOMA 9296 difiere...",
      "confidence": "high",
      "evidence_links": ["evidence/70/P04/trace.zip"]
    }
  ]
}

Error codes: invalid_evaluations_json, invalid_runner_output
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

logger = logging.getLogger("stacky.qa_uat.failure_analyzer")

_TOOL_VERSION = "1.0.0"

_FAILURE_CATEGORIES = frozenset({
    "regression",
    "missing_precondition",
    "data_drift",
    "ui_change",
    "wrong_expected_in_ticket",
    "environment_issue",
    "unknown",
})

_LLM_PROMPT_TEMPLATE = """\
You are a QA failure analyst for a .NET WebForms application (RS Pacífico - Agenda Web).

A Playwright UAT test failed. Classify the root cause using ONLY one of these categories:
- regression: the product worked before and is now broken (code change broke it)
- missing_precondition: required test data or RIDIOMA script was not applied
- data_drift: the expected data in the oracle is correct but the actual data in DB/UI changed
- ui_change: the DOM structure changed, a selector no longer exists or moved
- wrong_expected_in_ticket: the expected value in the test plan is incorrect
- environment_issue: deploy issue, network problem, configuration mismatch
- unknown: cannot determine from available evidence

Scenario: {scenario_id}
Failed assertion: tipo={tipo}, target={target}, expected={expected!r}, actual={actual!r}
Console errors: {console_errors}
Raw test output: {raw_stdout}

Reply with a JSON object:
{{
  "category": "<one of the categories above>",
  "hypothesis": "<1-3 sentence human-readable explanation>",
  "confidence": "high|medium|low"
}}
Only the JSON object, no other text.
"""


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    args = _parse_args()
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, stream=sys.stderr,
                            format="%(levelname)s %(name)s: %(message)s")
    else:
        logging.basicConfig(level=logging.WARNING, stream=sys.stderr)

    result = run(
        evaluations_path=Path(args.evaluations),
        runner_output_path=Path(args.runner_output),
        verbose=args.verbose,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result.get("ok") else 1)


# ── Core logic ────────────────────────────────────────────────────────────────

def run(
    evaluations_path: Path,
    runner_output_path: Path,
    verbose: bool = False,
) -> dict:
    """Core logic — callable from tests without subprocess."""
    started = time.time()

    # Load evaluations
    try:
        eval_data = json.loads(evaluations_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return _err("invalid_evaluations_json", f"Cannot read evaluations: {exc}")

    if not eval_data.get("ok"):
        return _err("invalid_evaluations_json", "evaluations.json has ok=false")

    # Load runner output (for artifacts + raw output)
    try:
        runner_data = json.loads(runner_output_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return _err("invalid_runner_output", f"Cannot read runner_output: {exc}")

    ticket_id = eval_data.get("ticket_id", 0)
    runner_runs = {r["scenario_id"]: r for r in (runner_data.get("runs") or [])}

    analyses = []

    for evaluation in (eval_data.get("evaluations") or []):
        scenario_id = evaluation.get("scenario_id", "?")
        eval_status = evaluation.get("status", "pass")

        # Only analyze failures
        if eval_status != "fail":
            continue

        run_result = runner_runs.get(scenario_id, {})
        failed_assertions = [
            a for a in (evaluation.get("assertions") or [])
            if a.get("status") == "fail"
        ]

        analysis = _analyze_failure(
            scenario_id=scenario_id,
            failed_assertions=failed_assertions,
            run_result=run_result,
            verbose=verbose,
        )
        analyses.append(analysis)

    return {
        "ok": True,
        "ticket_id": ticket_id,
        "total_failures_analyzed": len(analyses),
        "analyses": analyses,
        "elapsed_s": round(time.time() - started, 2),
    }


# ── Failure analysis ──────────────────────────────────────────────────────────

def _analyze_failure(
    scenario_id: str,
    failed_assertions: list,
    run_result: dict,
    verbose: bool = False,
) -> dict:
    """
    Classify failure for a single scenario.
    Tries LLM first, falls back to heuristic, then to unknown.
    """
    artifacts = run_result.get("artifacts") or {}
    evidence_links = [
        v for v in [
            artifacts.get("trace"),
            artifacts.get("video"),
        ] if v
    ]

    # Pick the most significant failed assertion for LLM analysis
    primary = failed_assertions[0] if failed_assertions else {}
    tipo = primary.get("tipo", "")
    target = primary.get("target", "")
    expected = primary.get("expected")
    actual = primary.get("actual")

    raw_stdout = run_result.get("raw_stdout", "")
    console_errors = _extract_console_errors(artifacts)

    # Try heuristic first (fast, no LLM cost)
    heuristic_category = _heuristic_classify(
        tipo=tipo,
        target=target,
        expected=expected,
        actual=actual,
        raw_stdout=raw_stdout,
        console_errors=console_errors,
    )

    if heuristic_category:
        return {
            "scenario_id": scenario_id,
            "category": heuristic_category["category"],
            "hypothesis_md": heuristic_category["hypothesis"],
            "confidence": heuristic_category["confidence"],
            "evidence_links": evidence_links,
            "failed_assertions_count": len(failed_assertions),
            "classified_by": "heuristic",
        }

    # Fall back to LLM
    llm_backend = os.getenv("STACKY_LLM_BACKEND", "vscode_bridge")
    if llm_backend == "mock":
        return _unknown_analysis(scenario_id, evidence_links, failed_assertions)

    try:
        llm_result = _classify_via_llm(
            scenario_id=scenario_id,
            tipo=tipo,
            target=target,
            expected=expected,
            actual=actual,
            console_errors=console_errors,
            raw_stdout=raw_stdout,
        )
        return {
            "scenario_id": scenario_id,
            "category": llm_result["category"],
            "hypothesis_md": llm_result["hypothesis"],
            "confidence": llm_result["confidence"],
            "evidence_links": evidence_links,
            "failed_assertions_count": len(failed_assertions),
            "classified_by": "llm",
        }
    except Exception as exc:
        logger.warning("LLM failure analysis failed for %s: %s", scenario_id, exc)
        return _unknown_analysis(scenario_id, evidence_links, failed_assertions)


def _heuristic_classify(
    tipo: str,
    target: str,
    expected,
    actual,
    raw_stdout: str,
    console_errors: list,
) -> Optional[dict]:
    """
    Fast heuristic classification before calling LLM.
    Returns dict with category/hypothesis/confidence or None.
    """
    if actual is None and tipo in ("visible", "equals", "contains_literal"):
        return {
            "category": "missing_precondition",
            "hypothesis": (
                f"El elemento '{target}' no estuvo presente en el DOM. "
                "Probablemente la precondición (datos de prueba o RIDIOMA) no fue aplicada."
            ),
            "confidence": "medium",
        }

    if actual == "" and expected and tipo == "equals":
        return {
            "category": "data_drift",
            "hypothesis": (
                f"El elemento '{target}' existe pero su texto es vacío, "
                f"mientras se esperaba '{expected}'. "
                "El RIDIOMA podría no estar insertado o tener el texto incorrecto."
            ),
            "confidence": "high",
        }

    timeout_indicators = ["timeout", "TimeoutError", "waiting for"]
    if any(ind.lower() in raw_stdout.lower() for ind in timeout_indicators):
        return {
            "category": "environment_issue",
            "hypothesis": (
                "El test falló por timeout. La página o el elemento tardó más de lo esperado. "
                "Puede ser un problema de deploy, red, o la pantalla no cargó correctamente."
            ),
            "confidence": "medium",
        }

    if "selector" in raw_stdout.lower() or "locator" in raw_stdout.lower():
        return {
            "category": "ui_change",
            "hypothesis": (
                f"El selector para '{target}' no se resolvió correctamente. "
                "El DOM podría haber cambiado desde que se construyó el UI map."
            ),
            "confidence": "medium",
        }

    if actual is False and tipo == "visible":
        return {
            "category": "regression",
            "hypothesis": (
                f"El elemento '{target}' debería ser visible pero no lo es. "
                "Posiblemente la lógica de visibilidad cambió con la implementación."
            ),
            "confidence": "medium",
        }

    return None


def _classify_via_llm(
    scenario_id: str,
    tipo: str,
    target: str,
    expected,
    actual,
    console_errors: list,
    raw_stdout: str,
) -> dict:
    """Call LLM to classify the failure. Validates category against enum."""
    from llm_client import call_llm

    prompt = _LLM_PROMPT_TEMPLATE.format(
        scenario_id=scenario_id,
        tipo=tipo,
        target=target,
        expected=expected,
        actual=actual,
        console_errors="; ".join(console_errors[:3]) or "none",
        raw_stdout=raw_stdout[:500] if raw_stdout else "none",
    )

    response_text = call_llm(
        prompt=prompt,
        model="gpt-4.1",
        max_tokens=300,
        temperature=0,
    )

    # Parse JSON from LLM response
    llm_json = _extract_json(response_text)

    category = llm_json.get("category", "unknown")
    # Validate against enum
    if category not in _FAILURE_CATEGORIES:
        logger.warning("LLM returned unknown category '%s', retrying with feedback", category)
        # Retry once with schema feedback
        retry_prompt = (
            prompt + f"\n\nYour previous reply had invalid category: '{category}'. "
            f"Valid categories: {sorted(_FAILURE_CATEGORIES)}. Reply with valid JSON only."
        )
        response_text = call_llm(
            prompt=retry_prompt,
            model="gpt-4.1",
            max_tokens=300,
            temperature=0,
        )
        llm_json = _extract_json(response_text)
        category = llm_json.get("category", "unknown")
        if category not in _FAILURE_CATEGORIES:
            category = "unknown"

    confidence = llm_json.get("confidence", "low")
    if confidence not in ("high", "medium", "low"):
        confidence = "low"

    return {
        "category": category,
        "hypothesis": llm_json.get("hypothesis", "No se pudo inferir causa. Revisar manualmente."),
        "confidence": confidence,
    }


def _extract_json(text: str) -> dict:
    """Extract first JSON object from LLM response text."""
    import re
    match = re.search(r'\{[^{}]+\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return {}


def _extract_console_errors(artifacts: dict) -> list:
    """Load console.json and return error messages."""
    console_path = artifacts.get("console_log", "")
    if not console_path:
        return []
    try:
        data = json.loads(Path(console_path).read_text(encoding="utf-8"))
        return [
            e.get("message", "")
            for e in (data if isinstance(data, list) else [])
            if e.get("type") in ("error", "warn")
        ]
    except Exception:
        return []


def _unknown_analysis(scenario_id: str, evidence_links: list, failed_assertions: list) -> dict:
    return {
        "scenario_id": scenario_id,
        "category": "unknown",
        "hypothesis_md": (
            "No se pudo inferir la causa de la falla. Revisar manualmente el trace y los logs."
        ),
        "confidence": "low",
        "evidence_links": evidence_links,
        "failed_assertions_count": len(failed_assertions),
        "classified_by": "fallback",
    }


# ── Error helper ──────────────────────────────────────────────────────────────

def _err(error: str, message: str) -> dict:
    return {"ok": False, "error": error, "message": message}


# ── CLI ───────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="UAT Failure Analyzer — classify root cause of test failures."
    )
    p.add_argument("--evaluations", required=True,
                   help="Path to evaluations.json (uat_assertion_evaluator output).")
    p.add_argument("--runner-output", required=True,
                   help="Path to runner_output.json (uat_test_runner output).")
    p.add_argument("--verbose", action="store_true", help="Debug logging to stderr.")
    return p.parse_args()


if __name__ == "__main__":
    main()
