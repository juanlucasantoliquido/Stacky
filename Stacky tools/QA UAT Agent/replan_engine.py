"""
replan_engine.py — Multi-round replanning for the QA UAT pipeline (Fase 9).

PROBLEM
    When a Playwright test fails (FAIL) or is blocked (SELECTOR_NOT_FOUND,
    missing precondition), the pipeline today stops and escalates to the
    operator.  For a large fraction of failures the root cause is
    diagnosable and the fix is mechanical:

      • Campo requerido visible   → add field to resolved_data, re-run
      • Pantalla incorrecta       → recalculate navigation_path, re-run
      • Selector missing          → look up discovered_selectors.json
      • Modal de error bloqueante → register as missing pre-condition

    This module provides the decision logic without touching Playwright or
    the browser.  The pipeline calls it between runner stages.

DESIGN
    Stateless function interface — no global mutable state.  The pipeline
    owns state and passes everything as arguments.

    replan_engine.analyze(
        runner_output:  dict,          # from uat_test_runner.run()
        evaluations:    dict | None,   # from uat_assertion_evaluator.run()
        intent_spec:    dict,          # current intent_spec.json contents
        evidence_dir:   Path,
        round_number:   int,           # 1-based replan attempt counter
    ) -> ReplanResult

    ReplanResult.action indicates what the pipeline should do next:
      "retry"          — intent_spec was patched; re-run generator+runner
      "escalate"       — cannot determine automated fix; hand off to operator
      "no_action"      — all tests passed / no failures to replan

MAX_REPLAN_ROUNDS = 3 — enforced by the pipeline, not by this module.

CONTRACT
    Public symbols:
      MAX_REPLAN_ROUNDS    int constant
      ReplanResult         dataclass
      analyze(...)         main entry point
      load_replan_log(...) helper to read persisted history

CLI (diagnostic / manual test)
    python replan_engine.py \\
        --runner-output  evidence/70/runner_output.json \\
        --evaluations    evidence/70/evaluations.json \\
        --intent-spec    evidence/70/intent_spec.json \\
        --evidence-dir   evidence/70/ \\
        [--round 1] [--dry-run] [--verbose]
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.qa_uat.replan_engine")

_TOOL_VERSION = "1.0.0"
MAX_REPLAN_ROUNDS = 3

# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class ReplanDecision:
    """Decision for a single failed/blocked scenario."""
    scenario_id: str
    replan_type: str        # "add_field" | "fix_selector" | "fix_navigation" |
                            # "dismiss_modal" | "escalate"
    description: str
    patch: dict = field(default_factory=dict)   # mutations applied to intent_spec
    confidence: str = "medium"                  # "high" | "medium" | "low"


@dataclass
class ReplanResult:
    """Overall replanning result returned to the pipeline."""
    action: str             # "retry" | "escalate" | "no_action"
    round_number: int
    decisions: list[ReplanDecision] = field(default_factory=list)
    patched_intent_spec: Optional[dict] = None
    escalation_reason: str = ""
    elapsed_ms: int = 0


# ── Error-pattern classifiers ─────────────────────────────────────────────────

# Text patterns that indicate a required-field validation error in the UI.
# The pattern is matched case-insensitively against the assertion failure
# message, console errors, and screen error text captured during the run.
_REQUIRED_FIELD_PATTERNS = (
    "requerido",
    "required",
    "obligatorio",
    "campo vacío",
    "campo vacio",
    "no puede estar vacío",
    "no puede estar vacio",
    "ingrese",
    "debe ingresar",
)

_SELECTOR_NOT_FOUND_PATTERNS = (
    "selector_not_found",
    "SELECTOR_NOT_FOUND",
    "locator.click: waiting for locator",
    "no element found for selector",
    "element not found",
    "selector.*not found",
    "timeout exceeded",
)

_WRONG_SCREEN_PATTERNS = (
    "unexpected url",
    "wrong screen",
    "pantalla incorrecta",
    "navigation failed",
    "page not found",
    "404",
    "urlmatch",
    "expected.*url.*received",
)


def _text_contains_any(text: str, patterns: tuple) -> bool:
    t = text.lower()
    return any(p.lower() in t for p in patterns)


# ── Core analysis ─────────────────────────────────────────────────────────────

def analyze(
    runner_output: dict,
    evaluations: Optional[dict],
    intent_spec: dict,
    evidence_dir: Path,
    round_number: int = 1,
    dry_run: bool = False,
) -> ReplanResult:
    """Analyze failures and produce a ReplanResult.

    Modifies *a deep copy* of intent_spec — never mutates the caller's dict.
    When action=="retry", the caller should replace intent_spec with
    result.patched_intent_spec and re-run the pipeline from the generator stage.

    Args:
        runner_output:  Output from uat_test_runner.run()
        evaluations:    Output from uat_assertion_evaluator.run() (can be None)
        intent_spec:    Current intent_spec dict (will NOT be mutated)
        evidence_dir:   Evidence directory for this run (reads discovered_selectors)
        round_number:   Which replan round this is (1-based, max MAX_REPLAN_ROUNDS)
        dry_run:        If True, compute decisions but do NOT write replan_log.json
    """
    started = time.time()
    import copy
    patched = copy.deepcopy(intent_spec)

    decisions: list[ReplanDecision] = []

    # Collect all failed/blocked runs
    failed_runs = _collect_failed_runs(runner_output, evaluations)
    if not failed_runs:
        return ReplanResult(
            action="no_action",
            round_number=round_number,
            elapsed_ms=int((time.time() - started) * 1000),
        )

    # Analyse each failure
    for fr in failed_runs:
        decision = _classify_failure(fr, patched, evidence_dir)
        if decision is not None:
            decisions.append(decision)
            _apply_patch(decision, patched)

    # Determine overall action
    actionable = [d for d in decisions if d.replan_type != "escalate"]
    if not actionable:
        escalation_reason = "; ".join(
            d.description for d in decisions if d.replan_type == "escalate"
        )
        result = ReplanResult(
            action="escalate",
            round_number=round_number,
            decisions=decisions,
            escalation_reason=escalation_reason or "No actionable fixes found",
            elapsed_ms=int((time.time() - started) * 1000),
        )
    else:
        result = ReplanResult(
            action="retry",
            round_number=round_number,
            decisions=decisions,
            patched_intent_spec=patched,
            elapsed_ms=int((time.time() - started) * 1000),
        )

    if not dry_run:
        _persist_replan_log(evidence_dir, result)

    return result


# ── Failure collection ────────────────────────────────────────────────────────

def _collect_failed_runs(runner_output: dict, evaluations: Optional[dict]) -> list[dict]:
    """Return list of enriched failure dicts, one per failed/blocked scenario."""
    runs_by_sid: dict[str, dict] = {}

    for run in (runner_output.get("runs") or []):
        sid = run.get("scenario_id", "")
        status = run.get("status", "")
        if status in ("fail", "blocked", "error"):
            runs_by_sid[sid] = {
                "scenario_id": sid,
                "runner_status": status,
                "runner_reason": run.get("reason", ""),
                "error_message": run.get("error_message", ""),
                "console_errors": run.get("console_errors") or [],
                "screen_errors": run.get("screen_errors") or [],
                "failed_step": run.get("failed_step"),
                "current_screen": run.get("current_screen", ""),
                "assertion_failures": run.get("assertion_failures") or [],
            }

    # Enrich with evaluator data
    if evaluations:
        for ev in (evaluations.get("evaluations") or []):
            sid = ev.get("scenario_id", "")
            if ev.get("status") == "fail":
                if sid not in runs_by_sid:
                    runs_by_sid[sid] = {
                        "scenario_id": sid,
                        "runner_status": "fail",
                        "runner_reason": "",
                        "error_message": "",
                        "console_errors": [],
                        "screen_errors": [],
                        "failed_step": None,
                        "current_screen": "",
                        "assertion_failures": [],
                    }
                runs_by_sid[sid]["evaluator_assertions"] = ev.get("assertions") or []

    return list(runs_by_sid.values())


# ── Failure classification ────────────────────────────────────────────────────

def _classify_failure(failure: dict, intent_spec: dict, evidence_dir: Path) -> Optional[ReplanDecision]:
    """Classify a single failure and return the corresponding ReplanDecision."""
    sid = failure["scenario_id"]

    # Aggregate all text signals for pattern matching
    all_text = " ".join([
        failure.get("runner_reason", ""),
        failure.get("error_message", ""),
        " ".join(failure.get("console_errors", [])),
        " ".join(str(e) for e in failure.get("screen_errors", [])),
        " ".join(
            str(a.get("actual", "")) + " " + str(a.get("expected", ""))
            for a in failure.get("assertion_failures", [])
        ),
        " ".join(
            str(a.get("actual", "")) + " " + str(a.get("expected", ""))
            for a in (failure.get("evaluator_assertions") or [])
            if a.get("status") == "fail"
        ),
    ])

    # ── Priority 1: required-field error ────────────────────────────────────
    if _text_contains_any(all_text, _REQUIRED_FIELD_PATTERNS):
        missing_field = _extract_required_field(all_text, failure)
        if missing_field:
            return ReplanDecision(
                scenario_id=sid,
                replan_type="add_field",
                description=f"Campo requerido detectado para {sid}: añadiendo placeholder {missing_field!r}",
                patch={"add_required_field": missing_field, "scenario_id": sid},
                confidence="high",
            )
        # Can't identify which field — escalate
        return ReplanDecision(
            scenario_id=sid,
            replan_type="escalate",
            description=f"Campo requerido en {sid} pero no se pudo identificar qué campo. Revisión manual requerida.",
            confidence="low",
        )

    # ── Priority 2: selector not found (BLOCKED) ─────────────────────────────
    if (
        failure.get("runner_status") == "blocked"
        or _text_contains_any(all_text, _SELECTOR_NOT_FOUND_PATTERNS)
    ):
        # Check if discovered_selectors.json might help
        disc_path = evidence_dir.parent.parent / "cache" / "discovered_selectors.json"
        if not disc_path.is_file():
            # Try relative to evidence_dir
            disc_path = Path(__file__).parent / "cache" / "discovered_selectors.json"
        has_discovered = disc_path.is_file() and disc_path.stat().st_size > 100
        if has_discovered:
            return ReplanDecision(
                scenario_id=sid,
                replan_type="fix_selector",
                description=(
                    f"Selector no encontrado en {sid}. "
                    f"discovered_selectors.json disponible — re-generando con cache activado."
                ),
                patch={"enable_discovered_selectors": True, "scenario_id": sid},
                confidence="medium",
            )
        return ReplanDecision(
            scenario_id=sid,
            replan_type="escalate",
            description=(
                f"Selector no encontrado en {sid} y discovered_selectors.json no disponible. "
                "Grabá una sesión con session_recorder.py para capturar los selectores."
            ),
            confidence="low",
        )

    # ── Priority 3: wrong screen / navigation failure ────────────────────────
    if _text_contains_any(all_text, _WRONG_SCREEN_PATTERNS):
        return ReplanDecision(
            scenario_id=sid,
            replan_type="fix_navigation",
            description=(
                f"Pantalla incorrecta detectada en {sid}. "
                "Recalculando navigation_path desde path_planner."
            ),
            patch={"recalculate_navigation_path": True, "scenario_id": sid},
            confidence="medium",
        )

    # ── Priority 4: modal de error bloqueante ────────────────────────────────
    modal_patterns = ("modal", "popup", "popupcompromisos", "alert", "dialog")
    if _text_contains_any(all_text, modal_patterns) and failure.get("runner_status") == "fail":
        return ReplanDecision(
            scenario_id=sid,
            replan_type="dismiss_modal",
            description=(
                f"Modal de error detectado bloqueando {sid}. "
                "Registrando como precondición faltante."
            ),
            patch={"register_precondition_failure": True, "scenario_id": sid},
            confidence="medium",
        )

    # ── Fallback: escalate ───────────────────────────────────────────────────
    return ReplanDecision(
        scenario_id=sid,
        replan_type="escalate",
        description=(
            f"No se pudo clasificar automáticamente el fallo de {sid}. "
            "Se requiere revisión manual del operador."
        ),
        confidence="low",
    )


def _extract_required_field(text: str, failure: dict) -> Optional[str]:
    """Attempt to identify which field triggered the required-field validation error.

    Looks at assertion failures for a target that maps to a form field name.
    Returns a placeholder field name (e.g. "PROYECTADO") or None if not found.
    """
    import re as _re
    # Look in assertion failures for a non-empty target
    for af in failure.get("assertion_failures", []):
        target = str(af.get("target", "")).strip()
        if target and target not in ("body", "page", ""):
            # Convert alias to placeholder-style name
            return target.upper().replace("INPUT_", "").replace("SELECT_", "")

    # Look for quoted field names in error text
    m = _re.search(r'"([A-Za-z_]{3,30})"', text)
    if m:
        return m.group(1).upper()

    # Look for Spanish-style "El campo X es requerido"
    m = _re.search(
        r'(?:el campo|campo|field)\s+["\']?([A-Za-z_\s]{2,30}?)["\']?\s+'
        r'(?:es|is|está|esta)\s+(?:requerido|required|obligatorio)',
        text,
        _re.IGNORECASE,
    )
    if m:
        return m.group(1).strip().upper().replace(" ", "_")

    return None


# ── Patch application ─────────────────────────────────────────────────────────

def _apply_patch(decision: ReplanDecision, intent_spec: dict) -> None:
    """Mutate intent_spec in-place based on decision.patch."""
    patch = decision.patch
    replan_type = decision.replan_type
    sid = patch.get("scenario_id", "")

    if replan_type == "add_field":
        field_name = patch.get("add_required_field", "")
        if field_name:
            # Add to resolved_data as an explicit placeholder so the operator
            # sees it on the next data_request prompt. The actual value will
            # come from the operator or data_resolver on the subsequent run.
            resolved = intent_spec.setdefault("resolved_data", {})
            if field_name not in resolved:
                resolved[field_name] = f"<REPLAN_REQUIRED:{field_name}>"
            # Also tag the test case so the data_request is targeted
            for tc in (intent_spec.get("test_cases") or []):
                if tc.get("id") == sid or not sid:
                    placeholders = tc.setdefault("placeholders", [])
                    if field_name not in placeholders:
                        placeholders.append(field_name)
            logger.info("replan_engine: added required field %r to resolved_data", field_name)

    elif replan_type == "fix_navigation":
        # Reset navigation_path so intent_parser recomputes it via path_planner
        # on the next round. We only clear it for the affected test case.
        for tc in (intent_spec.get("test_cases") or []):
            if tc.get("id") == sid or not sid:
                tc.pop("navigation_path", None)
                logger.info(
                    "replan_engine: cleared navigation_path for %s — will be recomputed", sid
                )

    elif replan_type == "fix_selector":
        # Signal playwright_test_generator to use discovered_selectors.json.
        # We do this by setting a flag in the intent_spec meta block.
        meta = intent_spec.setdefault("_replan_meta", {})
        meta["use_discovered_selectors"] = True
        logger.info("replan_engine: enabled discovered_selectors lookup for %s", sid)

    elif replan_type == "dismiss_modal":
        # Register the scenario as having a known pre-condition failure.
        # This prevents the analyzer from counting it as a regression.
        meta = intent_spec.setdefault("_replan_meta", {})
        missing_precs = meta.setdefault("missing_preconditions", [])
        if sid and sid not in missing_precs:
            missing_precs.append(sid)
        logger.info(
            "replan_engine: registered modal precondition failure for %s", sid
        )

    # "escalate" → no patch applied


# ── Persistence ───────────────────────────────────────────────────────────────

def _persist_replan_log(evidence_dir: Path, result: ReplanResult) -> None:
    """Append replan round to evidence_dir/replan_log.json."""
    log_path = evidence_dir / "replan_log.json"
    history: list = []
    if log_path.is_file():
        try:
            history = json.loads(log_path.read_text(encoding="utf-8"))
        except Exception:
            history = []

    entry = {
        "round": result.round_number,
        "action": result.action,
        "decisions": [
            {
                "scenario_id": d.scenario_id,
                "replan_type": d.replan_type,
                "description": d.description,
                "confidence": d.confidence,
            }
            for d in result.decisions
        ],
        "escalation_reason": result.escalation_reason,
        "elapsed_ms": result.elapsed_ms,
    }
    history.append(entry)
    log_path.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("replan_engine: replan_log.json updated (round %d)", result.round_number)


def load_replan_log(evidence_dir: Path) -> list:
    """Read replan history for a run. Returns [] if not yet created."""
    log_path = evidence_dir / "replan_log.json"
    if not log_path.is_file():
        return []
    try:
        return json.loads(log_path.read_text(encoding="utf-8"))
    except Exception:
        return []


# ── CLI ───────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="replan_engine — Analyse failures and compute replanning actions"
    )
    parser.add_argument("--runner-output", required=True,
                        help="Path to runner_output.json")
    parser.add_argument("--evaluations", default=None,
                        help="Path to evaluations.json (optional)")
    parser.add_argument("--intent-spec", required=True,
                        help="Path to intent_spec.json")
    parser.add_argument("--evidence-dir", required=True,
                        help="Path to evidence directory for this run")
    parser.add_argument("--round", type=int, default=1,
                        help="Replan round number (1-based, default: 1)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Compute decisions but do not write replan_log.json")
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, stream=sys.stderr,
                            format="%(levelname)s %(name)s: %(message)s")
    else:
        logging.basicConfig(level=logging.WARNING, stream=sys.stderr)

    runner_output = json.loads(Path(args.runner_output).read_text(encoding="utf-8"))
    evaluations = (
        json.loads(Path(args.evaluations).read_text(encoding="utf-8"))
        if args.evaluations and Path(args.evaluations).is_file()
        else None
    )
    intent_spec = json.loads(Path(args.intent_spec).read_text(encoding="utf-8"))

    result = analyze(
        runner_output=runner_output,
        evaluations=evaluations,
        intent_spec=intent_spec,
        evidence_dir=Path(args.evidence_dir),
        round_number=args.round,
        dry_run=args.dry_run,
    )

    output = {
        "ok": True,
        "action": result.action,
        "round": result.round_number,
        "decisions": [
            {
                "scenario_id": d.scenario_id,
                "replan_type": d.replan_type,
                "description": d.description,
                "confidence": d.confidence,
            }
            for d in result.decisions
        ],
        "escalation_reason": result.escalation_reason,
        "elapsed_ms": result.elapsed_ms,
        "version": _TOOL_VERSION,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    sys.exit(0 if result.action != "escalate" else 2)


if __name__ == "__main__":
    main()
