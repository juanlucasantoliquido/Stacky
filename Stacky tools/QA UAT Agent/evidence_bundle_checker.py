"""
evidence_bundle_checker.py — Sprint 5: Verificar completeness del evidence bundle.

PURPOSE
-------
Every QA UAT run must produce a minimum set of artifacts before publish.
This module checks what's present, what's missing, and whether the bundle
meets the required threshold.

USAGE
-----
  from evidence_bundle_checker import check_bundle, REQUIRED_ARTIFACTS
  manifest = check_bundle(evidence_dir, run_id, exec_logger=exec_logger)
  if not manifest["complete"]:
      ...

PUBLIC API
----------
  check_bundle(evidence_dir, run_id, tier, exec_logger) -> dict
  REQUIRED_ARTIFACTS: dict[str, list[str]]   # per-tier required artifact names
  TIER_ALWAYS: str
  TIER_RAN_PLAYWRIGHT: str
  TIER_PREFLIGHT_ONLY: str
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.qa_uat.evidence_bundle_checker")

_SCHEMA_VERSION = "evidence_bundle/1.0"

# Evidence tiers — determines which artifacts are required
TIER_ALWAYS          = "always"        # Every single run, regardless of outcome
TIER_PREFLIGHT_ONLY  = "preflight"     # Run blocked at preflight (before Playwright)
TIER_RAN_PLAYWRIGHT  = "playwright"    # Run reached Playwright runner

# Minimum artifact set per tier
REQUIRED_ARTIFACTS: dict[str, list[str]] = {
    TIER_ALWAYS: [
        "execution.jsonl",
        "result.json",
        "effective_config.json",
    ],
    TIER_PREFLIGHT_ONLY: [
        "execution.jsonl",
        "result.json",
        "effective_config.json",
    ],
    TIER_RAN_PLAYWRIGHT: [
        "execution.jsonl",
        "result.json",
        "effective_config.json",
        "dossier.json",
    ],
}

# Optional artifacts — present in the manifest but not blocking publish
OPTIONAL_ARTIFACTS = [
    "environment_preflight.json",
    "deployment_fingerprint.json",
    "data_readiness.json",
    "screen_detection.json",
    "ui_map_used.json",
    "selector_contract.json",
    "compiler_contract_result.json",
    "generator_contract_result.json",
    "compiler_result.json",
    "runner_output.json",
    "evaluations.json",
    "dossier.json",
    "junit.xml",
    "triage.json",
    "publish_audit.json",
]


def check_bundle(
    evidence_dir: Path,
    run_id: Optional[str] = None,
    tier: str = TIER_ALWAYS,
    exec_logger=None,
) -> dict:
    """Check whether required evidence artifacts are present in evidence_dir.

    Parameters
    ----------
    evidence_dir : Path
        The run-specific evidence directory (e.g., evidence/<ticket>/<run_id>/).
    run_id : str | None
        The run identity. If None, inferred from evidence_dir.name if it looks like a run_id.
    tier : str
        One of TIER_ALWAYS, TIER_PREFLIGHT_ONLY, TIER_RAN_PLAYWRIGHT.
        Determines which artifacts are required.
    exec_logger : ExecutionLogger | None
        Optional logger; if provided, emits 'evidence_bundle_manifest' event.

    Returns
    -------
    dict with keys:
        complete (bool): True if all required artifacts are present.
        required (list[str]): Names of required artifacts.
        present (list[str]): Names of required artifacts that are present.
        missing (list[str]): Names of required artifacts that are absent.
        optional_present (list[str]): Optional artifacts that happen to be present.
        tier (str): The tier used.
        run_id (str | None): The run_id.
        evidence_dir (str): The evidence directory path as string.
        schema_version (str): Schema version.
    """
    t0 = time.monotonic()

    evidence_dir = Path(evidence_dir)
    effective_run_id = run_id or evidence_dir.name

    required = list(REQUIRED_ARTIFACTS.get(tier, REQUIRED_ARTIFACTS[TIER_ALWAYS]))

    present: list[str] = []
    missing: list[str] = []

    for artifact in required:
        p = evidence_dir / artifact
        if p.exists() and p.stat().st_size > 0:
            present.append(artifact)
        else:
            missing.append(artifact)

    optional_present: list[str] = []
    for artifact in OPTIONAL_ARTIFACTS:
        if artifact in required:
            continue
        p = evidence_dir / artifact
        if p.exists() and p.stat().st_size > 0:
            optional_present.append(artifact)

    complete = len(missing) == 0

    elapsed_ms = round((time.monotonic() - t0) * 1000, 1)

    manifest = {
        "schema_version": _SCHEMA_VERSION,
        "run_id": effective_run_id,
        "evidence_dir": str(evidence_dir),
        "tier": tier,
        "complete": complete,
        "required": required,
        "present": present,
        "missing": missing,
        "optional_present": optional_present,
        "elapsed_ms": elapsed_ms,
    }

    if not complete:
        logger.warning(
            "evidence_bundle_checker: incomplete bundle [%s] tier=%s missing=%s",
            effective_run_id, tier, missing,
        )
    else:
        logger.debug(
            "evidence_bundle_checker: bundle complete [%s] tier=%s required=%d optional=%d",
            effective_run_id, tier, len(required), len(optional_present),
        )

    # Write manifest to evidence_dir
    try:
        manifest_path = evidence_dir / "evidence_bundle_manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        manifest["manifest_path"] = str(manifest_path)
    except Exception as e:  # noqa: BLE001
        logger.warning("evidence_bundle_checker: could not write manifest: %s", e)

    # Emit execution.jsonl event if logger provided
    if exec_logger is not None:
        try:
            exec_logger.write({
                "event": "evidence_bundle_manifest",
                "run_id": effective_run_id,
                "tier": tier,
                "complete": complete,
                "required_count": len(required),
                "present_count": len(present),
                "missing": missing,
                "optional_present_count": len(optional_present),
                "elapsed_ms": elapsed_ms,
            })
        except Exception as e:  # noqa: BLE001
            logger.debug("evidence_bundle_checker: could not emit event: %s", e)

    return manifest


def build_blocked_result(manifest: dict) -> dict:
    """Build a BLOCKED OBS EVIDENCE_INCOMPLETE result dict from an incomplete manifest."""
    missing = manifest.get("missing_artifacts", []) or manifest.get("missing", [])
    return {
        "ok": False,
        "verdict": "BLOCKED",
        "category": "OBS",
        "reason": "EVIDENCE_INCOMPLETE",
        "failed_stage": "evidence_bundle",
        "message": f"Evidence bundle incomplete - missing: {', '.join(missing)}",
        "missing_artifacts": missing,
        "evidence_dir": manifest.get("evidence_dir"),
        "human_action_required": "Rerun pipeline to generate missing artifacts; check pipeline logs for early exits",
    }
