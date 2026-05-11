"""
failure_triage.py — Sprint 6.1: Forensic failure triage for QA UAT Agent.

PURPOSE
-------
Receives artifacts from a completed run and emits `triage.json` with root cause,
owner and next actionable step. Operates as a post-runner stage in the pipeline.

Does NOT require a real LLM call — heuristic deterministic rules are applied first.
LLM enrichment is an optional extension point (not used in tests).

TRIAGE CATEGORIES
-----------------
APP   — Application defects (assertion failures, business logic errors)
ENV   — Environment failures (deployment mismatch, connectivity)
DATA  — Data precondition failures (empty grids, missing test entities)
PIP   — Pipeline meta failures (no tests, spec missing, stage contract broken)
GEN   — Generator issues (UI map missing, alias not found, code generation error)
NAV   — Navigation / selector failures (DOM drift, selector timeout)
OBS   — Observability gaps (missing trace, incomplete evidence)
SEC   — Security (blocked by auth, CSRF, access denied)
OPS   — Infrastructure failures (worker crash, browser crash, CI deps missing)

OWNER TABLE
-----------
Category | Owner          | Next action template
---------+----------------+--------------------------------------------
APP      | developer      | Revisar [módulo] con trace adjunto y reproducir localmente
ENV      | devops         | Verificar build activo y deployment en ambiente [env]
DATA     | data_owner     | Seedear datos para [entidad] o cambiar [parámetro]
PIP      | qa_automation  | Revisar contrato entre stages: [stage que falló]
GEN      | qa_automation  | Reconstruir UI map para [pantalla] o corregir aliases
NAV      | qa_automation  | Revisar selector [alias] en [pantalla] — posible drift de DOM
OBS      | qa_automation  | Verificar logger y pipeline — evidencia incompleta
SEC      | devops         | Verificar configuración de autenticación y permisos de acceso
OPS      | devops         | Verificar runner/browser deps en ambiente CI

VERSION
-------
1.0 — Sprint 6
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.qa_uat.failure_triage")

_TRIAGE_VERSION = "1.0"

# ── Official taxonomies ────────────────────────────────────────────────────────

VALID_VERDICTS = frozenset({"PASS", "FAIL", "BLOCKED", "MIXED", "SKIPPED"})
VALID_CATEGORIES = frozenset({"APP", "ENV", "DATA", "PIP", "GEN", "NAV", "OBS", "SEC", "OPS"})
VALID_OWNERS = frozenset({"developer", "qa_automation", "devops", "product", "data_owner"})

# ── Owner + next_action defaults per category ──────────────────────────────────

_CATEGORY_OWNER: dict[str, str] = {
    "APP": "developer",
    "ENV": "devops",
    "DATA": "data_owner",
    "PIP": "qa_automation",
    "GEN": "qa_automation",
    "NAV": "qa_automation",
    "OBS": "qa_automation",
    "SEC": "devops",
    "OPS": "devops",
}

_CATEGORY_NEXT_ACTION_TEMPLATE: dict[str, str] = {
    "APP": "Revisar módulo con trace adjunto y reproducir localmente",
    "ENV": "Verificar build activo y deployment en ambiente de pruebas",
    "DATA": "Seedear datos para la entidad requerida o cambiar el parámetro de datos",
    "PIP": "Revisar contrato entre stages del pipeline y corregir stage que falló",
    "GEN": "Reconstruir UI map para la pantalla afectada o corregir aliases de selectores",
    "NAV": "Revisar selector en la pantalla afectada — posible drift de DOM",
    "OBS": "Verificar logger y pipeline — evidencia incompleta o faltante",
    "SEC": "Verificar configuración de autenticación y permisos de acceso",
    "OPS": "Verificar runner/browser deps en ambiente CI",
}

# ── Deterministic heuristic rules ─────────────────────────────────────────────
# Each rule: (reason_pattern, category, reason, confidence, evidence_template)
# reason_pattern is matched against result_json["reason"] and execution_log events.

_REASON_RULES: list[tuple[str, str, str, float]] = [
    # GEN — generator/UI-map failures
    ("UI_MAP_MISSING",                    "GEN",  "UI_MAP_MISSING",                    1.0),
    ("SELECTOR_ALIAS_NOT_IN_UI_MAP",      "GEN",  "SELECTOR_ALIAS_NOT_IN_UI_MAP",      1.0),
    ("UI_MAP_SCHEMA_INVALID",             "GEN",  "UI_MAP_SCHEMA_INVALID",             0.95),
    ("CODE_GENERATION_FAILED",            "GEN",  "CODE_GENERATION_FAILED",            0.95),
    ("DECORATIVE_ELEMENT_ACTION",         "GEN",  "DECORATIVE_ELEMENT_ACTION",         0.90),
    # ENV — environment / deployment
    ("DEPLOYMENT_MISMATCH",               "ENV",  "DEPLOYMENT_MISMATCH",               1.0),
    ("DEPLOYMENT_FINGERPRINT",            "ENV",  "DEPLOYMENT_MISMATCH",               1.0),
    ("SMOKE_BLOCKED",                     "ENV",  "SMOKE_BLOCKED",                     0.95),
    ("ENVIRONMENT_NOT_READY",             "ENV",  "ENVIRONMENT_NOT_READY",             0.90),
    ("SERVER_UNREACHABLE_BEFORE_TEST",    "ENV",  "SERVER_UNREACHABLE_BEFORE_TEST",    1.0),
    ("APP_POOL_CRASH_AFTER_INVALID_NAVIGATION", "ENV", "APP_POOL_CRASH_AFTER_INVALID_NAVIGATION", 0.95),
    # PAGE_LOAD_FAILED is intentionally lower priority — causal analysis may
    # reclassify it as NAV/INVALID_DIRECT_NAVIGATION when login succeeded.
    ("PAGE_LOAD_FAILED",                  "ENV",  "PAGE_LOAD_FAILED",                  0.70),
    # DATA — data precondition failures
    ("GRID_EMPTY",                        "DATA", "GRID_EMPTY",                        1.0),
    ("TEST_ENTITY_NOT_FOUND",             "DATA", "TEST_ENTITY_NOT_FOUND",             1.0),
    ("TEST_USER_PERMISSION_MISSING",      "DATA", "TEST_USER_PERMISSION_MISSING",      0.95),
    ("DATA_SOURCE_UNREACHABLE",           "DATA", "DATA_SOURCE_UNREACHABLE",           0.95),
    ("DATA_BLOCKED",                      "DATA", "DATA_BLOCKED",                      0.90),
    ("NAVIGATION_DATA_MISSING",           "DATA", "NAVIGATION_DATA_MISSING",           1.0),
    ("DEEPLINK_PARAM_MISSING",            "DATA", "DEEPLINK_PARAM_MISSING",            1.0),
    ("DEEPLINK_ENTITY_NOT_FOUND",         "DATA", "DEEPLINK_ENTITY_NOT_FOUND",         1.0),
    ("DEEPLINK_PERMISSION_DENIED",        "DATA", "DEEPLINK_PERMISSION_DENIED",        0.90),
    ("HUMAN_PATH_GRID_EMPTY",             "DATA", "HUMAN_PATH_GRID_EMPTY",             1.0),
    # PIP — pipeline meta failures
    ("NO_TESTS_FOUND",                    "PIP",  "NO_TESTS_FOUND",                    1.0),
    ("SPEC_FILE_MISSING",                 "PIP",  "SPEC_FILE_MISSING",                 1.0),
    ("NO_UAT_ITEMS",                      "PIP",  "NO_UAT_ITEMS",                      1.0),
    ("LOW_CONFIDENCE_SCREEN_DETECTION",   "PIP",  "LOW_CONFIDENCE_SCREEN_DETECTION",   0.90),
    ("SCREEN_AMBIGUOUS",                  "PIP",  "SCREEN_AMBIGUOUS",                  0.90),
    ("SCREEN_DETECTION_FAILED",           "PIP",  "SCREEN_DETECTION_FAILED",           0.90),
    ("COMPILER_BLOCKED",                  "PIP",  "COMPILER_BLOCKED",                  0.85),
    ("INVALID_NAVIGATION_STRATEGY_FOR_LANE", "PIP", "INVALID_NAVIGATION_STRATEGY_FOR_LANE", 1.0),
    # NAV — navigation / selector failures
    # NAV rules have HIGH priority — they represent causal root causes of
    # symptoms that would otherwise be classified as ENV/PAGE_LOAD_FAILED.
    ("INVALID_DIRECT_NAVIGATION_TO_SESSION_DEPENDENT_SCREEN",
                                          "NAV",  "INVALID_DIRECT_NAVIGATION_TO_SESSION_DEPENDENT_SCREEN", 1.0),
    ("NAV_PATH_MISSING",                  "NAV",  "NAV_PATH_MISSING",                  1.0),
    ("NAV_CONTRACT_MISSING",              "NAV",  "NAV_CONTRACT_MISSING",              1.0),
    ("NAV_CONTRACT_BLOCKED",              "NAV",  "NAV_CONTRACT_BLOCKED",              1.0),
    ("DEEPLINK_CONTEXT_NOT_RECONSTRUCTED", "NAV", "DEEPLINK_CONTEXT_NOT_RECONSTRUCTED", 1.0),
    ("DEEPLINK_SERVER_ERROR",             "APP",  "DEEPLINK_SERVER_ERROR",             0.95),
    ("DEEPLINK_REDIRECTED_TO_LOGIN",      "SEC",  "DEEPLINK_REDIRECTED_TO_LOGIN",      0.95),
    ("DEEPLINK_HTTP_UNREACHABLE",         "ENV",  "DEEPLINK_HTTP_UNREACHABLE",         0.95),
    ("HUMAN_PATH_STEP_FAILED",            "NAV",  "HUMAN_PATH_STEP_FAILED",            0.95),
    ("SELECTOR_TIMEOUT",                  "NAV",  "SELECTOR_TIMEOUT",                  0.90),
    ("SELECTOR_NOT_FOUND",                "NAV",  "SELECTOR_NOT_FOUND",                0.90),
    ("BLOCKED_NAV_CONTEXT",               "NAV",  "DEEPLINK_CONTEXT_NOT_RECONSTRUCTED", 0.95),
    ("BLOCKED_NAV_GRID_EMPTY",            "DATA", "HUMAN_PATH_GRID_EMPTY",             0.95),
    ("BLOCKED_NAV_DATA",                  "DATA", "NAVIGATION_DATA_MISSING",           0.95),
    ("BLOCKED_SESSION_EXPIRED",           "SEC",  "AUTH_FAILED",                       0.90),
    ("BLOCKED_WRONG_SCREEN",              "NAV",  "INVALID_DIRECT_NAVIGATION_TO_SESSION_DEPENDENT_SCREEN", 0.90),
    # APP — application / assertion failures
    ("ASSERTION_FAILED",                  "APP",  "ASSERTION_FAILED",                  0.90),
    # OPS — infrastructure
    ("WORKER_CRASH",                      "OPS",  "WORKER_CRASH",                      0.95),
    # OBS — observability
    ("TRACE_MISSING",                     "OBS",  "TRACE_MISSING",                     0.90),
    # SEC — security
    ("ACCESS_DENIED",                     "SEC",  "ACCESS_DENIED",                     0.90),
    ("AUTH_FAILED",                       "SEC",  "AUTH_FAILED",                       0.90),
]


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── Result dataclass ───────────────────────────────────────────────────────────

@dataclass
class FailureTriageResult:
    triage_version: str
    ticket_id: int
    run_id: str
    verdict: str
    category: Optional[str]
    reason: Optional[str]
    confidence: float
    evidence: list
    owner: str
    next_action: str
    rerun_recommended: bool
    publish_recommended: bool
    human_approval_required: bool
    artifact_path: Optional[str]

    def to_dict(self) -> dict:
        d = asdict(self)
        # evidence is already a list of str
        return d


# ── Main entry point ───────────────────────────────────────────────────────────

def run_failure_triage(
    ticket_id: int,
    run_id: str,
    result_json: dict,
    execution_log: list,
    runner_classification: Optional[dict],
    exec_logger=None,
    evidence_dir: Optional[str] = None,
) -> FailureTriageResult:
    """
    Run failure triage on a completed run and return a FailureTriageResult.

    Parameters
    ----------
    ticket_id : int
        ADO ticket identifier.
    run_id : str
        Unique run identifier.
    result_json : dict
        result.json from the run (pipeline output or runner_output).
    execution_log : list[dict]
        Events from execution.jsonl.
    runner_classification : dict | None
        Output of playwright_result_classifier (may be None for pre-runner failures).
    exec_logger :
        ExecutionLogger instance (optional). Used to emit triage_result event.
    evidence_dir : str | None
        Directory where triage.json will be written.

    Returns
    -------
    FailureTriageResult
    """
    # ── Step 1: determine verdict ─────────────────────────────────────────────
    verdict = _determine_verdict(result_json, runner_classification, execution_log)

    # ── Step 2: determine category + reason + confidence ─────────────────────
    category, reason, confidence, evidence = _determine_category_reason(
        result_json, execution_log, runner_classification, verdict
    )

    # ── Step 3: determine owner + next_action ────────────────────────────────
    owner = _category_to_owner(category)
    next_action = _build_next_action(category, reason, result_json, execution_log)

    # ── Step 4: policy decisions ──────────────────────────────────────────────
    rerun_recommended = _should_rerun(verdict, category, reason)
    publish_recommended = verdict == "PASS" and confidence >= 0.85
    human_approval_required = _requires_human_approval(verdict, category, confidence)

    # ── Step 5: build result ──────────────────────────────────────────────────
    artifact_path: Optional[str] = None
    if evidence_dir:
        artifact_path = _write_triage_artifact(
            evidence_dir=Path(evidence_dir),
            ticket_id=ticket_id,
            run_id=run_id,
            verdict=verdict,
            category=category,
            reason=reason,
            confidence=confidence,
            evidence=evidence,
            owner=owner,
            next_action=next_action,
            rerun_recommended=rerun_recommended,
            publish_recommended=publish_recommended,
            human_approval_required=human_approval_required,
        )

    result = FailureTriageResult(
        triage_version=_TRIAGE_VERSION,
        ticket_id=ticket_id,
        run_id=run_id,
        verdict=verdict,
        category=category,
        reason=reason,
        confidence=confidence,
        evidence=evidence,
        owner=owner,
        next_action=next_action,
        rerun_recommended=rerun_recommended,
        publish_recommended=publish_recommended,
        human_approval_required=human_approval_required,
        artifact_path=artifact_path,
    )

    # ── Step 6: emit triage_result event ─────────────────────────────────────
    if exec_logger is not None:
        _emit_triage_event(exec_logger, result)

    return result


# ── Heuristic helpers ──────────────────────────────────────────────────────────

def _determine_verdict(
    result_json: dict,
    runner_classification: Optional[dict],
    execution_log: list,
) -> str:
    """
    Determine the verdict from available inputs.
    Priority: result_json verdict → runner_classification verdict → log events.
    """
    # Direct from result_json
    v = result_json.get("verdict", "")
    if v in VALID_VERDICTS:
        return v

    # From runner_classification
    if runner_classification:
        v = runner_classification.get("verdict", "")
        if v in VALID_VERDICTS:
            return v

    # From execution_log pipeline_verdict_decision event
    for evt in reversed(execution_log):
        if evt.get("event") == "pipeline_verdict_decision":
            v = (evt.get("verdict") or evt.get("data", {}).get("verdict") or "")
            if v in VALID_VERDICTS:
                return v

    # From result ok flag
    if result_json.get("ok") is True:
        return "PASS"
    if result_json.get("ok") is False:
        return "BLOCKED"

    return "BLOCKED"


def _determine_category_reason(
    result_json: dict,
    execution_log: list,
    runner_classification: Optional[dict],
    verdict: str,
) -> tuple[Optional[str], Optional[str], float, list]:
    """
    Apply deterministic heuristic rules to determine category, reason, confidence,
    and evidence chain.
    """
    evidence: list[str] = []

    if verdict == "PASS":
        evidence.append("verdict=PASS from result_json or runner_classification")
        return None, None, 1.0, evidence

    if verdict == "SKIPPED":
        evidence.append("verdict=SKIPPED — pipeline exit before runner")
        reason_from_result = result_json.get("reason", "")
        if reason_from_result == "NO_UAT_ITEMS":
            return "PIP", "NO_UAT_ITEMS", 1.0, evidence + ["reason=NO_UAT_ITEMS in result_json"]
        return "PIP", reason_from_result or "SKIPPED", 1.0, evidence

    # Collect candidate signals from all sources
    signals: list[tuple[str, str, float, str]] = []  # (category, reason, confidence, source)

    # 1. result_json.category + reason (highest trust for pre-runner failures)
    rj_category = result_json.get("category", "")
    rj_reason = result_json.get("reason", "")
    if rj_category in VALID_CATEGORIES and rj_reason:
        signals.append((rj_category, rj_reason, 1.0, "result_json.category+reason"))
        evidence.append(f"result_json.category={rj_category} reason={rj_reason}")

    # 2. result_json.reason (keyword match via rule table)
    if rj_reason and not any(s[0] for s in signals):
        matched = _match_reason_rule(rj_reason)
        if matched:
            cat, rsn, conf = matched
            signals.append((cat, rsn, conf, f"reason_rule:{rj_reason}"))
            evidence.append(f"reason rule matched: {rj_reason} → {cat}/{rsn}")

    # 3. failed_stage heuristic
    failed_stage = result_json.get("failed_stage", "")
    if failed_stage:
        stage_cat, stage_conf = _stage_to_category(failed_stage)
        if stage_cat:
            signals.append((stage_cat, rj_reason or failed_stage.upper(), stage_conf,
                            f"failed_stage:{failed_stage}"))
            evidence.append(f"failed_stage={failed_stage} → category={stage_cat}")

    # 4. runner_classification signals
    if runner_classification:
        rc_cat = runner_classification.get("category", "")
        rc_rsn = runner_classification.get("reason", "")
        rc_v   = runner_classification.get("verdict", "")
        if rc_cat in VALID_CATEGORIES:
            signals.append((rc_cat, rc_rsn, 0.90, "runner_classification"))
            evidence.append(f"runner_classification: {rc_v}/{rc_cat}/{rc_rsn}")

    # 5. execution_log — pipeline_verdict_decision event
    for evt in reversed(execution_log):
        if evt.get("event") == "pipeline_verdict_decision":
            data = evt.get("data") or evt
            ec = data.get("category", "")
            er = data.get("reason", "")
            if ec in VALID_CATEGORIES:
                signals.append((ec, er, 0.95, "pipeline_verdict_decision_event"))
                evidence.append(f"pipeline_verdict_decision: category={ec} reason={er}")
                break

    # 6. Scan execution_log for early-exit events (causal chain analysis)
    _login_succeeded = False
    _nav_contract_blocked = False
    _nav_contract_reason: Optional[str] = None
    for evt in execution_log:
        ev_type = evt.get("event", "")

        # Track login success (global.setup OK = login was fine)
        if ev_type in ("session_start", "globalsetup_success", "auth_state_created"):
            _login_succeeded = True

        if ev_type == "ui_map_cache_result":
            if not evt.get("cache_hit", True):
                screen = evt.get("screen", "unknown")
                signals.append(("GEN", "UI_MAP_MISSING", 1.0, "ui_map_cache_result"))
                evidence.append(f"ui_map_cache_result: screen={screen} cache_hit=False")

        elif ev_type == "deployment_fingerprint_check" or ev_type == "deployment_fingerprint_checked":
            data = evt.get("data") or evt
            if data.get("decision") == "BLOCKED":
                signals.append(("ENV", "DEPLOYMENT_MISMATCH", 1.0, "deployment_fingerprint_check"))
                evidence.append("deployment_fingerprint_check: decision=BLOCKED")

        elif ev_type == "data_readiness_check":
            data = evt.get("data") or evt
            if data.get("blocked", 0) > 0:
                signals.append(("DATA", "GRID_EMPTY", 0.95, "data_readiness_check"))
                evidence.append(f"data_readiness_check: blocked={data.get('blocked')}")

        elif ev_type == "screen_detection_result":
            data = evt.get("data") or evt
            reason_evt = data.get("reason", "")
            if reason_evt in ("LOW_CONFIDENCE_SCREEN_DETECTION", "SCREEN_AMBIGUOUS",
                              "SCREEN_DETECTION_FAILED"):
                signals.append(("PIP", reason_evt, 0.90, "screen_detection_result"))
                evidence.append(f"screen_detection_result: reason={reason_evt}")

        elif ev_type == "navigation_contract_validation":
            # Navigation contract validation event — HIGH PRIORITY causal signal
            data = evt.get("data") or evt
            decision = data.get("decision", "")
            nav_reason = data.get("reason", "")
            nav_category = data.get("category", "NAV")
            if decision == "BLOCKED" and nav_reason:
                _nav_contract_blocked = True
                _nav_contract_reason = nav_reason
                if nav_category in VALID_CATEGORIES:
                    signals.append((nav_category, nav_reason, 1.0, "navigation_contract_validation"))
                    evidence.append(
                        f"navigation_contract_validation: BLOCKED category={nav_category} reason={nav_reason}"
                    )

        elif ev_type == "deeplink_readiness_check":
            data = evt.get("data") or evt
            dr_decision = data.get("decision", "")
            dr_reason = data.get("reason", "")
            dr_category = data.get("category", "NAV")
            if dr_decision == "BLOCKED" and dr_reason:
                if dr_category in VALID_CATEGORIES:
                    signals.append((dr_category, dr_reason, 1.0, "deeplink_readiness_check"))
                    evidence.append(
                        f"deeplink_readiness_check: BLOCKED category={dr_category} reason={dr_reason}"
                    )

    # ── CAUSAL CHAIN RULE: Login OK + page.goto failure = NAV (not ENV) ─────
    # If the execution log shows that globalSetup/login succeeded, but the
    # runner failed at navigation/beforeEach, the root cause is NAV, not ENV.
    # The ENV signal (PAGE_LOAD_FAILED) is the symptom of invalid navigation.
    # Apply only when:
    #   a) we have a PAGE_LOAD_FAILED signal but no stronger NAV signal yet, AND
    #   b) there is evidence that login was successful before the failure.
    _has_page_load_failed = any(
        s[1] == "PAGE_LOAD_FAILED" for s in signals
    )
    _has_nav_signal = any(
        s[0] == "NAV" for s in signals
    )
    _login_ok_from_session = bool(
        # Look for evidence of successful login in log events or result
        _login_succeeded
        or any(
            evt.get("event") in ("globalsetup_ok", "auth_state_ok", "login_succeeded")
            for evt in execution_log
        )
        or result_json.get("globalsetup_ok") is True
    )
    if _has_page_load_failed and not _has_nav_signal and _login_ok_from_session:
        # Promote PAGE_LOAD_FAILED to INVALID_DIRECT_NAVIGATION_TO_SESSION_DEPENDENT_SCREEN
        # This is the ticket 120 pattern: login OK → direct goto → crash → ENV symptom
        # Remove PAGE_LOAD_FAILED signals so the NAV reclassification wins unconditionally.
        signals[:] = [
            s for s in signals
            if not (s[0] == "ENV" and s[1] == "PAGE_LOAD_FAILED")
        ]
        signals.append((
            "NAV",
            "INVALID_DIRECT_NAVIGATION_TO_SESSION_DEPENDENT_SCREEN",
            0.90,
            "causal_chain:login_ok+page_load_failed=nav_not_env",
        ))
        evidence.append(
            "CAUSAL CHAIN: login succeeded before test start, then page.goto failed. "
            "Root cause: invalid direct navigation to session-dependent screen (not ENV). "
            "Secondary cause: APP_POOL_CRASH_AFTER_INVALID_NAVIGATION."
        )

    if not signals:
        # Fallback: unknown classification — use BLOCKED APP as safe default
        evidence.append("no specific signal found — defaulting to APP")
        return "APP", "ASSERTION_FAILED", 0.50, evidence

    # Pick the highest-confidence signal
    best = max(signals, key=lambda s: s[2])
    if not evidence:
        evidence.append(f"best signal: {best[0]}/{best[1]} from {best[3]}")

    return best[0], best[1], best[2], evidence


def _match_reason_rule(reason: str) -> Optional[tuple[str, str, float]]:
    """Match a reason string against the deterministic rule table."""
    if not reason:
        return None
    upper_reason = reason.upper()
    for pattern, cat, rsn, conf in _REASON_RULES:
        if pattern.upper() in upper_reason or upper_reason in pattern.upper():
            return cat, rsn, conf
    return None


def _stage_to_category(failed_stage: str) -> tuple[Optional[str], float]:
    """Map a pipeline stage name to a category with confidence."""
    stage_map: dict[str, tuple[str, float]] = {
        "ui_map":                       ("GEN", 0.95),
        "ui_map_builder":               ("GEN", 0.95),
        "selector_contract":            ("GEN", 0.95),
        "generator":                    ("GEN", 0.90),
        "compiler":                     ("PIP", 0.90),
        "reader":                       ("PIP", 0.90),
        "intent_parser":                ("PIP", 0.90),
        "runner":                       ("APP", 0.75),
        "environment_preflight":        ("ENV", 0.95),
        "smoke_path":                   ("ENV", 0.90),
        "deployment_fingerprint":       ("ENV", 1.0),
        "deployment_fingerprint_check": ("ENV", 1.0),
        "data_readiness_check":         ("DATA", 0.95),
        "screen_detection":             ("PIP", 0.90),
        "quality_intake":               ("PIP", 0.85),
        "navigation_contract_validation": ("NAV", 1.0),
        "deeplink_readiness_check":     ("NAV", 0.95),
    }
    lower_stage = (failed_stage or "").lower()
    for key, val in stage_map.items():
        if key in lower_stage:
            return val
    return None, 0.0


def _category_to_owner(category: Optional[str]) -> str:
    """Return the default owner for a category."""
    if category is None:
        return "qa_automation"
    return _CATEGORY_OWNER.get(category, "qa_automation")


def _build_next_action(
    category: Optional[str],
    reason: Optional[str],
    result_json: dict,
    execution_log: list,
) -> str:
    """Build a concrete next_action string from category + reason + context."""
    if category is None:
        return "Revisar el run y confirmar que todos los tests pasaron correctamente"

    template = _CATEGORY_NEXT_ACTION_TEMPLATE.get(category, "Revisar el run y diagnosticar el fallo")

    # Enrich templates with specific context
    if category == "GEN" and reason == "UI_MAP_MISSING":
        # Find the screen name from execution_log
        screen = _extract_screen_from_log(execution_log) or result_json.get("screen", "la pantalla afectada")
        return f"run ui_map_builder.py --screen {screen} --rebuild"

    if category == "ENV" and reason == "DEPLOYMENT_MISMATCH":
        env = os.environ.get("QA_UAT_ENVIRONMENT", "test")
        return f"Verificar build activo y deployment en ambiente {env} — revisar deployment_fingerprint.json"

    if category == "DATA" and reason == "GRID_EMPTY":
        return "Seedear datos para la entidad requerida o verificar data_readiness.json con los parámetros actuales"

    if category == "PIP" and reason == "LOW_CONFIDENCE_SCREEN_DETECTION":
        return "Verificar screen_detection.json y ampliar screen_aliases.yml para la pantalla del ticket"

    if category == "NAV":
        if reason == "INVALID_DIRECT_NAVIGATION_TO_SESSION_DEPENDENT_SCREEN":
            screen = _extract_screen_from_log(execution_log) or "la pantalla afectada"
            return (
                f"Usar nav_path humano (open_from_busqueda) o deeplink gobernado para '{screen}'. "
                "NO usar page.goto() directo a pantallas session-dependientes. "
                "Revisar navigation_contracts.yml y navigation_contract_validation.json."
            )
        if reason == "NAV_PATH_MISSING":
            screen = _extract_screen_from_log(execution_log) or "la pantalla afectada"
            return (
                f"Definir un human_path para '{screen}' en navigation_contracts.yml. "
                "Agregar entrypoint, steps, required_data y required_assertions."
            )
        if reason == "NAV_CONTRACT_MISSING":
            screen = _extract_screen_from_log(execution_log) or "la pantalla afectada"
            return (
                f"Agregar un contrato de navegación para '{screen}' en navigation_contracts.yml. "
                "Declarar si direct_entry_allowed, deeplink_allowed y los human_paths."
            )
        if reason == "DEEPLINK_CONTEXT_NOT_RECONSTRUCTED":
            return (
                "El deeplink cargó la URL pero no reconstruyó el contexto esperado. "
                "Corregir el deeplink handler en la aplicación o usar human_path. "
                "Revisar deeplink_readiness_check en execution.jsonl."
            )
        if reason == "HUMAN_PATH_STEP_FAILED":
            return (
                "Un paso de la navegación humana falló (búsqueda, click, selección). "
                "Revisar el Flow Object ClienteFlow.openDetalleFromBusqueda en playwright/flows/. "
                "Verificar selectores en UI map y estado del ambiente."
            )
        alias = _extract_failed_alias_from_log(execution_log) or "el selector afectado"
        screen = _extract_screen_from_log(execution_log) or "la pantalla afectada"
        return f"Revisar selector {alias} en {screen} — posible drift de DOM — verificar selector_contract.json"

    if category == "APP":
        return "Revisar el trace adjunto y reproducir localmente — verificar la lógica de negocio del módulo"

    return template


def _extract_screen_from_log(execution_log: list) -> Optional[str]:
    """Extract the screen name from execution log events."""
    for evt in execution_log:
        ev_type = evt.get("event", "")
        if ev_type == "ui_map_cache_result":
            s = evt.get("screen")
            if s:
                return s
        elif ev_type == "screen_detection_result":
            data = evt.get("data") or evt
            screens = data.get("screens") or []
            if screens:
                return screens[0] if isinstance(screens[0], str) else screens[0].get("screen")
    return None


def _extract_failed_alias_from_log(execution_log: list) -> Optional[str]:
    """Extract the failed selector alias from execution log events."""
    for evt in execution_log:
        ev_type = evt.get("event", "")
        if ev_type == "selector_contract_validation":
            data = evt.get("data") or evt
            failures = data.get("failures") or []
            if failures:
                return failures[0].get("alias") or failures[0].get("alias_semantic")
    return None


def _should_rerun(verdict: str, category: Optional[str], reason: Optional[str]) -> bool:
    """Determine if a rerun is recommended based on verdict + category."""
    if verdict == "PASS":
        return False
    # Transient failures worth retrying
    if category in ("ENV", "OPS") and reason in (
        "PAGE_LOAD_FAILED", "WORKER_CRASH", "SMOKE_BLOCKED"
    ):
        return True
    if category == "DATA" and reason == "GRID_EMPTY":
        return False  # Data issue — rerun won't help without seeding
    if category == "NAV" and reason == "SELECTOR_TIMEOUT":
        return True  # Might be a flake
    # Navigation contract failures — do NOT rerun, they need structural fixes
    if category == "NAV" and reason in (
        "INVALID_DIRECT_NAVIGATION_TO_SESSION_DEPENDENT_SCREEN",
        "NAV_PATH_MISSING",
        "NAV_CONTRACT_MISSING",
        "DEEPLINK_CONTEXT_NOT_RECONSTRUCTED",
    ):
        return False
    if category == "DATA" and reason in (
        "NAVIGATION_DATA_MISSING",
        "DEEPLINK_PARAM_MISSING",
        "HUMAN_PATH_GRID_EMPTY",
    ):
        return False
    return False


def _requires_human_approval(verdict: str, category: Optional[str], confidence: float) -> bool:
    """Determine if human approval is required before proceeding."""
    if verdict == "PASS" and confidence >= 0.90:
        return False
    if category in ("APP", "DATA", "GEN", "PIP"):
        return True
    if confidence < 0.75:
        return True
    return verdict in ("FAIL", "BLOCKED", "MIXED")


# ── Artifact writer ────────────────────────────────────────────────────────────

def _write_triage_artifact(
    evidence_dir: Path,
    ticket_id: int,
    run_id: str,
    verdict: str,
    category: Optional[str],
    reason: Optional[str],
    confidence: float,
    evidence: list,
    owner: str,
    next_action: str,
    rerun_recommended: bool,
    publish_recommended: bool,
    human_approval_required: bool,
) -> str:
    """Write triage.json to evidence_dir. Returns the artifact path string."""
    evidence_dir.mkdir(parents=True, exist_ok=True)
    artifact = {
        "schema": "triage/1.0",
        "triage_version": _TRIAGE_VERSION,
        "ticket_id": ticket_id,
        "run_id": run_id,
        "timestamp": _utcnow(),
        "verdict": verdict,
        "category": category,
        "reason": reason,
        "confidence": confidence,
        "evidence": evidence,
        "owner": owner,
        "next_action": next_action,
        "rerun_recommended": rerun_recommended,
        "publish_recommended": publish_recommended,
        "human_approval_required": human_approval_required,
    }
    out_path = evidence_dir / "triage.json"
    out_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.debug("failure_triage: wrote %s", out_path)
    return str(out_path)


# ── Execution log event emitter ───────────────────────────────────────────────

def _emit_triage_event(exec_logger, result: FailureTriageResult) -> None:
    """Emit triage_result event to execution.jsonl."""
    try:
        payload = {
            "ticket_id": result.ticket_id,
            "run_id": result.run_id,
            "verdict": result.verdict,
            "category": result.category,
            "reason": result.reason,
            "confidence": result.confidence,
            "owner": result.owner,
            "next_action": result.next_action,
            "rerun_recommended": result.rerun_recommended,
            "publish_recommended": result.publish_recommended,
            "human_approval_required": result.human_approval_required,
            "artifact_path": result.artifact_path,
        }
        exec_logger.event("triage_result", payload)
    except Exception as exc:  # noqa: BLE001
        logger.debug("failure_triage: could not emit triage_result event: %s", exc)


# ── Schema validator (lightweight, no jsonschema dep required) ─────────────────

def validate_triage_dict(triage: dict) -> tuple[bool, list[str]]:
    """
    Validate a triage dict against the triage.schema.json contract.
    Returns (valid, errors_list).
    Does NOT require the jsonschema package.
    """
    errors: list[str] = []

    # Required fields
    required = ["verdict", "category", "reason", "confidence", "evidence",
                "owner", "next_action", "human_approval_required"]
    for f in required:
        if f not in triage:
            errors.append(f"missing required field: {f}")

    # verdict enum
    v = triage.get("verdict")
    if v and v not in VALID_VERDICTS:
        errors.append(f"verdict={v!r} not in {sorted(VALID_VERDICTS)}")

    # category enum (nullable)
    c = triage.get("category")
    if c is not None and c not in VALID_CATEGORIES:
        errors.append(f"category={c!r} not in {sorted(VALID_CATEGORIES)}")

    # confidence range
    conf = triage.get("confidence")
    if conf is not None:
        try:
            conf_f = float(conf)
            if conf_f < 0.0 or conf_f > 1.0:
                errors.append(f"confidence={conf_f} out of range [0, 1]")
        except (TypeError, ValueError):
            errors.append(f"confidence={conf!r} is not a number")

    # evidence: non-empty array of strings
    ev = triage.get("evidence")
    if ev is not None:
        if not isinstance(ev, list):
            errors.append("evidence must be an array")
        elif len(ev) == 0:
            errors.append("evidence must have at least 1 item")
        else:
            for i, item in enumerate(ev):
                if not isinstance(item, str):
                    errors.append(f"evidence[{i}] must be a string")

    # owner enum
    owner = triage.get("owner")
    if owner and owner not in VALID_OWNERS:
        errors.append(f"owner={owner!r} not in {sorted(VALID_OWNERS)}")

    # next_action minLength 10
    na = triage.get("next_action")
    if na is not None and (not isinstance(na, str) or len(na) < 10):
        errors.append(f"next_action must be a string with minLength=10, got: {na!r}")

    # human_approval_required: boolean
    har = triage.get("human_approval_required")
    if har is not None and not isinstance(har, bool):
        errors.append(f"human_approval_required must be boolean, got: {type(har).__name__}")

    return len(errors) == 0, errors


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="failure_triage — Sprint 6.1 triage for QA UAT Agent runs"
    )
    parser.add_argument("--ticket-id", type=int, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--result-json", required=True,
                        help="Path to result.json or runner_output.json")
    parser.add_argument("--execution-log", help="Path to execution.jsonl")
    parser.add_argument("--evidence-dir", help="Directory to write triage.json")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, stream=sys.stderr)

    result_data = json.loads(Path(args.result_json).read_text(encoding="utf-8"))

    exec_log_events: list = []
    if args.execution_log:
        p = Path(args.execution_log)
        if p.is_file():
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    try:
                        exec_log_events.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass

    triage = run_failure_triage(
        ticket_id=args.ticket_id,
        run_id=args.run_id,
        result_json=result_data,
        execution_log=exec_log_events,
        runner_classification=None,
        evidence_dir=args.evidence_dir,
    )
    print(json.dumps(triage.to_dict(), ensure_ascii=False, indent=2))
