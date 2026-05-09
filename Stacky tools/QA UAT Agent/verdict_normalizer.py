"""
verdict_normalizer.py — Sprint 5: Normalizar veredictos, reason codes y categorías.

PURPOSE
-------
Every pipeline exit — success or failure — must produce a verdict that:
  1. Is never null / UNKNOWN.
  2. Belongs to the canonical VERDICT_SET.
  3. Has a reason code from the canonical REASON_CODES registry.
  4. Has a category from the canonical CATEGORY_SET.

This module is the single source of truth for reason codes and normalization logic.

USAGE
-----
  from verdict_normalizer import normalize, is_publishable, REASON_CODES
  norm = normalize(verdict="BLOCKED", category="PIP", reason="compiler_empty")
  if not is_publishable(norm):
      ...

PUBLIC API
----------
  normalize(verdict, category, reason, failed_stage, confidence, run_id) -> NormalizedVerdict
  is_publishable(norm) -> bool
  check_publish_readiness(norm, evidence_manifest) -> PublishReadinessResult
  NormalizedVerdict.to_dict()
  PublishReadinessResult.to_dict()
  REASON_CODES: dict[str, ReasonCodeMeta]
  VERDICT_SET: frozenset
  CATEGORY_SET: frozenset
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("stacky.qa_uat.verdict_normalizer")

_SCHEMA_VERSION = "verdict_normalization/1.0"


# ── Canonical sets ────────────────────────────────────────────────────────────

VERDICT_SET = frozenset({"PASS", "FAIL", "BLOCKED", "MIXED", "SKIPPED"})

CATEGORY_SET = frozenset({
    "APP",   # Bug real del producto
    "ENV",   # Ambiente, build, deploy o configuración incorrecta
    "DATA",  # Datos de prueba insuficientes o inconsistentes
    "PIP",   # Pipeline, stage contract o compilación de escenarios rota
    "GEN",   # Generación inválida, UI map faltante, alias inventado
    "NAV",   # Navegación, selector, frame o timeout real
    "OBS",   # Evidencia, logging o artifact incompleto
    "SEC",   # Seguridad, PII, secrets, egress o prompt injection
    "OPS",   # Runners, CI, infraestructura o dependencias
})


@dataclass
class ReasonCodeMeta:
    """Metadata for a canonical reason code."""
    code: str
    category: str
    description: str
    publish_allowed: bool = False  # Whether pipeline can proceed to publish with this reason


# ── Canonical reason codes registry ──────────────────────────────────────────

REASON_CODES: dict[str, ReasonCodeMeta] = {
    # ENV
    "MISSING_CREDENTIALS":             ReasonCodeMeta("MISSING_CREDENTIALS", "ENV", "AGENDA_WEB_USER/PASS not set"),
    "BUILD_MISMATCH":                  ReasonCodeMeta("BUILD_MISMATCH", "ENV", "Deployed build differs from expected"),
    "BUILD_UNVERIFIABLE":              ReasonCodeMeta("BUILD_UNVERIFIABLE", "ENV", "Build version could not be determined"),
    "DEPLOYMENT_MISMATCH":             ReasonCodeMeta("DEPLOYMENT_MISMATCH", "ENV", "Deployment fingerprint mismatch"),
    "ENV_PREFLIGHT_FAILED":            ReasonCodeMeta("ENV_PREFLIGHT_FAILED", "ENV", "Environment preflight check failed"),
    "DATA_SOURCE_UNREACHABLE":         ReasonCodeMeta("DATA_SOURCE_UNREACHABLE", "ENV", "DB or data source unreachable"),
    "POLICY_OFF":                      ReasonCodeMeta("POLICY_OFF", "ENV", "Deployment policy set to off"),
    # DATA
    "GRID_EMPTY":                      ReasonCodeMeta("GRID_EMPTY", "DATA", "Grid/table returned 0 rows"),
    "CATALOG_MISSING":                 ReasonCodeMeta("CATALOG_MISSING", "DATA", "Required catalog not found in DB"),
    "CATALOG_EMPTY":                   ReasonCodeMeta("CATALOG_EMPTY", "DATA", "Required catalog has no entries"),
    "TEST_ENTITY_NOT_FOUND":           ReasonCodeMeta("TEST_ENTITY_NOT_FOUND", "DATA", "Test entity does not exist in DB"),
    "DATA_READINESS_FAILED":           ReasonCodeMeta("DATA_READINESS_FAILED", "DATA", "Data readiness check failed"),
    "DATA_CONTRACT_MISSING_REQUIREMENTS": ReasonCodeMeta("DATA_CONTRACT_MISSING_REQUIREMENTS", "DATA", "Data contract requirements not satisfied"),
    # PIP
    "COMPILER_EMPTY":                  ReasonCodeMeta("COMPILER_EMPTY", "PIP", "Compiler produced no scenarios and no out_of_scope items"),
    "NO_EXECUTABLE_SCENARIOS":         ReasonCodeMeta("NO_EXECUTABLE_SCENARIOS", "PIP", "All scenarios discarded by compiler"),
    "COMPILER_CONTRACT_INVALID":       ReasonCodeMeta("COMPILER_CONTRACT_INVALID", "PIP", "Compiler output failed schema validation"),
    "GENERATOR_CONTRACT_INVALID":      ReasonCodeMeta("GENERATOR_CONTRACT_INVALID", "PIP", "Generator output failed schema validation"),
    "CONTRACT_INVALID":                ReasonCodeMeta("CONTRACT_INVALID", "PIP", "Output failed contract validation"),
    "SCREEN_AMBIGUOUS":                ReasonCodeMeta("SCREEN_AMBIGUOUS", "PIP", "Screen detection returned multiple ambiguous screens"),
    "SCREEN_DETECTION_EMPTY":          ReasonCodeMeta("SCREEN_DETECTION_EMPTY", "PIP", "Screen detection returned no screens"),
    "NO_EXECUTABLE_SCENARIOS_EMPTY":   ReasonCodeMeta("NO_EXECUTABLE_SCENARIOS_EMPTY", "PIP", "No scenarios for screen"),
    "PIPELINE_CRASH":                  ReasonCodeMeta("PIPELINE_CRASH", "OPS", "Unexpected pipeline crash"),
    "SPEC_LINT_FAILURE":               ReasonCodeMeta("SPEC_LINT_FAILURE", "PIP", "Spec linter found violations"),
    "BUDGET_EXCEEDED":                 ReasonCodeMeta("BUDGET_EXCEEDED", "OPS", "Run budget exceeded"),
    # GEN
    "UI_MAP_MISSING":                  ReasonCodeMeta("UI_MAP_MISSING", "GEN", "UI map file not found for screen"),
    "SELECTOR_ALIAS_NOT_IN_UI_MAP":    ReasonCodeMeta("SELECTOR_ALIAS_NOT_IN_UI_MAP", "GEN", "Alias requested by compiler not in UI map"),
    "SELECTOR_IS_DECORATIVE":          ReasonCodeMeta("SELECTOR_IS_DECORATIVE", "GEN", "Alias targets a decorative element"),
    "DECORATIVE_ELEMENT_ACTION":       ReasonCodeMeta("DECORATIVE_ELEMENT_ACTION", "GEN", "Action on decorative element"),
    # NAV
    "SELECTOR_TIMEOUT":                ReasonCodeMeta("SELECTOR_TIMEOUT", "NAV", "Playwright selector timed out"),
    "SELECTOR_NOT_FOUND":              ReasonCodeMeta("SELECTOR_NOT_FOUND", "NAV", "Playwright selector not found"),
    "NAVIGATION_TIMEOUT":              ReasonCodeMeta("NAVIGATION_TIMEOUT", "NAV", "Page navigation timed out"),
    # APP
    "ASSERTION_FAILED":                ReasonCodeMeta("ASSERTION_FAILED", "APP", "One or more test assertions failed"),
    "RUNNER_CRASH":                    ReasonCodeMeta("RUNNER_CRASH", "APP", "Test runner crashed during execution"),
    # OBS
    "EVIDENCE_INCOMPLETE":             ReasonCodeMeta("EVIDENCE_INCOMPLETE", "OBS", "Required evidence artifacts missing"),
    "UNKNOWN":                         ReasonCodeMeta("UNKNOWN", "OPS", "Unclassified failure — must open bug P0"),
    # OPS
    "EXCEEDED_REASONABLE_RUNTIME":     ReasonCodeMeta("EXCEEDED_REASONABLE_RUNTIME", "OPS", "Pipeline exceeded max runtime"),
    # Success
    "PASS":                            ReasonCodeMeta("PASS", "APP", "All scenarios passed", publish_allowed=True),
    "MIXED":                           ReasonCodeMeta("MIXED", "APP", "Some passed, some failed", publish_allowed=True),
    "FAIL":                            ReasonCodeMeta("FAIL", "APP", "One or more scenarios failed", publish_allowed=True),
    "PARTIAL_PASS":                    ReasonCodeMeta("PARTIAL_PASS", "APP", "Partial scenarios passed", publish_allowed=True),
}

# Aliases from legacy/raw error strings to canonical codes
_REASON_ALIASES: dict[str, str] = {
    "compiler_empty":                  "COMPILER_EMPTY",
    "no_executable_scenarios":         "NO_EXECUTABLE_SCENARIOS",
    "all_scenarios_out_of_scope":      "NO_EXECUTABLE_SCENARIOS",
    "pipeline_error":                  "PIPELINE_CRASH",
    "no_tests_found":                  "COMPILER_EMPTY",
    "ui_map_missing":                  "UI_MAP_MISSING",
    "selector_alias_not_in_ui_map":    "SELECTOR_ALIAS_NOT_IN_UI_MAP",
    "missing_credentials":             "MISSING_CREDENTIALS",
    "grid_empty":                      "GRID_EMPTY",
    "test_entity_not_found":           "TEST_ENTITY_NOT_FOUND",
    "data_readiness_failed":           "DATA_READINESS_FAILED",
    "compiler_contract_invalid":       "COMPILER_CONTRACT_INVALID",
    "generator_contract_invalid":      "GENERATOR_CONTRACT_INVALID",
}


# ── Result dataclasses ────────────────────────────────────────────────────────

@dataclass
class NormalizedVerdict:
    """Canonical, fully validated verdict from any pipeline exit."""
    verdict: str
    category: str
    reason: str
    failed_stage: Optional[str]
    confidence: float
    run_id: Optional[str]
    is_known_reason: bool
    is_publishable: bool
    publish_blocked_reason: Optional[str]

    def to_dict(self) -> dict:
        return {
            "schema_version": _SCHEMA_VERSION,
            "verdict": self.verdict,
            "category": self.category,
            "reason": self.reason,
            "failed_stage": self.failed_stage,
            "confidence": self.confidence,
            "run_id": self.run_id,
            "is_known_reason": self.is_known_reason,
            "is_publishable": self.is_publishable,
            "publish_blocked_reason": self.publish_blocked_reason,
        }


@dataclass
class PublishReadinessResult:
    """Result of checking whether a run is ready to publish to ADO."""
    ok: bool                          # True = publish allowed
    verdict: str
    category: str
    reason: str
    run_id: Optional[str]
    blockers: list = field(default_factory=list)   # list of string messages
    evidence_complete: bool = True
    missing_artifacts: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "schema_version": _SCHEMA_VERSION,
            "ok": self.ok,
            "verdict": self.verdict,
            "category": self.category,
            "reason": self.reason,
            "run_id": self.run_id,
            "blockers": self.blockers,
            "evidence_complete": self.evidence_complete,
            "missing_artifacts": self.missing_artifacts,
        }


# ── Public API ────────────────────────────────────────────────────────────────

def normalize(
    verdict: Optional[str] = None,
    category: Optional[str] = None,
    reason: Optional[str] = None,
    failed_stage: Optional[str] = None,
    confidence: float = 1.0,
    run_id: Optional[str] = None,
) -> NormalizedVerdict:
    """Normalize a raw verdict/category/reason triple to canonical form.

    Rules:
      - verdict=None → "BLOCKED"
      - verdict not in VERDICT_SET → "BLOCKED"
      - reason lowercase alias → canonical REASON_CODE
      - unknown reason → kept as-is with is_known_reason=False
      - category corrected from REASON_CODES if known reason found

    Returns
    -------
    NormalizedVerdict
    """
    # Normalize verdict
    raw_verdict = (verdict or "BLOCKED").upper().strip()
    norm_verdict = raw_verdict if raw_verdict in VERDICT_SET else "BLOCKED"

    # Normalize reason: try alias table first, then uppercase.
    # When reason is empty and verdict is a known canonical, use verdict as reason
    # (e.g., verdict=PASS, reason="" → reason=PASS which self-describes the outcome).
    raw_reason = (reason or "").strip()
    if not raw_reason and norm_verdict in VERDICT_SET:
        canon_reason = norm_verdict  # PASS/FAIL/MIXED are valid reason codes
    else:
        canon_reason = _REASON_ALIASES.get(raw_reason.lower(), raw_reason.upper() or "UNKNOWN")

    # Lookup in registry
    meta = REASON_CODES.get(canon_reason)
    is_known = meta is not None
    if not is_known:
        logger.warning(
            "verdict_normalizer: unknown reason code %r — using as-is. "
            "Add to REASON_CODES if this is a new permanent code.",
            canon_reason,
        )

    # Derive category: from meta if known, else normalize raw category
    if meta:
        norm_category = meta.category
    else:
        raw_cat = (category or "OPS").upper().strip()
        norm_category = raw_cat if raw_cat in CATEGORY_SET else "OPS"

    # Compute publish_allowed — check in priority order (UNKNOWN > missing run_id > BLOCKED)
    publish_blocked: Optional[str] = None
    if canon_reason == "UNKNOWN":
        publish_blocked = "UNKNOWN reason code is never publishable — open bug P0"
    elif not run_id:
        publish_blocked = "Missing run_id — cannot publish without run identity"
    elif norm_verdict == "BLOCKED":
        if not (meta and meta.publish_allowed):
            publish_blocked = f"BLOCKED verdict with reason {canon_reason} is not publishable"

    is_pub = publish_blocked is None and norm_verdict in ("PASS", "FAIL", "MIXED", "PARTIAL_PASS")

    result = NormalizedVerdict(
        verdict=norm_verdict,
        category=norm_category,
        reason=canon_reason,
        failed_stage=failed_stage,
        confidence=max(0.0, min(1.0, confidence)),
        run_id=run_id,
        is_known_reason=is_known,
        is_publishable=is_pub,
        publish_blocked_reason=publish_blocked,
    )

    if norm_verdict == "BLOCKED":
        logger.debug(
            "verdict_normalizer: BLOCKED %s/%s stage=%s",
            norm_category, canon_reason, failed_stage,
        )
    elif norm_verdict in ("FAIL", "MIXED"):
        logger.warning(
            "verdict_normalizer: %s %s/%s — publish_allowed=%s",
            norm_verdict, norm_category, canon_reason, is_pub,
        )

    return result


def is_publishable(norm: NormalizedVerdict) -> bool:
    """Return True if the normalized verdict can be published to ADO."""
    return norm.is_publishable


def check_publish_readiness(
    norm: NormalizedVerdict,
    evidence_manifest: Optional[dict] = None,
) -> PublishReadinessResult:
    """Check whether a run is ready to publish, given its normalized verdict and evidence.

    Parameters
    ----------
    norm : NormalizedVerdict
        Result of normalize().
    evidence_manifest : dict | None
        Optional dict from evidence_bundle_checker.check_bundle().
        Keys: complete, missing_artifacts, present_artifacts.

    Returns
    -------
    PublishReadinessResult
    """
    blockers: list[str] = []
    missing_artifacts: list[str] = []
    evidence_complete = True

    # Verdict-level blockers
    if norm.verdict == "BLOCKED":
        blockers.append(
            f"verdict=BLOCKED cannot be published (reason={norm.reason})"
        )
    if norm.reason == "UNKNOWN":
        blockers.append("UNKNOWN reason code — open bug P0 before publishing")
    if not norm.run_id:
        blockers.append("run_id is missing — cannot guarantee idempotent publish")

    # Evidence-level blockers
    if evidence_manifest is not None:
        if not evidence_manifest.get("complete"):
            evidence_complete = False
            missing_artifacts = evidence_manifest.get("missing_artifacts", [])
            blockers.append(
                f"Evidence bundle incomplete — missing: {', '.join(missing_artifacts)}"
            )

    ok = len(blockers) == 0

    if not ok:
        logger.warning(
            "publish_readiness: BLOCKED — %d blockers: %s",
            len(blockers), "; ".join(blockers[:3]),
        )

    return PublishReadinessResult(
        ok=ok,
        verdict=norm.verdict,
        category=norm.category,
        reason=norm.reason,
        run_id=norm.run_id,
        blockers=blockers,
        evidence_complete=evidence_complete,
        missing_artifacts=missing_artifacts,
    )


# ── Utility: normalize from pipeline result dict ──────────────────────────────

def normalize_from_result(result: dict) -> NormalizedVerdict:
    """Convenience: normalize directly from a pipeline result dict."""
    return normalize(
        verdict=result.get("verdict"),
        category=result.get("category"),
        reason=result.get("reason") or result.get("error"),
        failed_stage=result.get("failed_stage") or result.get("stage"),
        confidence=result.get("confidence", 1.0),
        run_id=result.get("run_id"),
    )
