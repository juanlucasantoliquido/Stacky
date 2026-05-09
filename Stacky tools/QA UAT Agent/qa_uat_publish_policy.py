"""
qa_uat_publish_policy.py — Sprint 6: Policy-as-code para publicación QA UAT.

PURPOSE
-------
Centraliza las reglas de publish en un lugar único y auditable.
Ningún run QA UAT puede publicar a ADO sin pasar esta policy.

POLICY RULES (en orden de evaluación)
--------------------------------------
  P1. verdict must be in {PASS, FAIL, BLOCKED, MIXED}
  P2. verdict != UNKNOWN (signals tool bug — must be P0 first)
  P3. evidence_bundle_complete = true
  P4. run_id present
  P5. dossier present (dossier.json exists in evidence_dir)
  P6. human_approved = true   (when mode != "dry-run")

USAGE
-----
  from qa_uat_publish_policy import evaluate_policy, PublishPolicyResult
  result = evaluate_policy(
      verdict="PASS",
      run_id="uat-122-...",
      evidence_dir=Path("evidence/122/uat-122-..."),
      human_approved=True,
      mode="publish",
  )
  if not result.allowed:
      ...

PUBLIC API
----------
  evaluate_policy(verdict, run_id, evidence_dir, human_approved, mode,
                  evidence_manifest, reason, category) -> PublishPolicyResult
  PublishPolicyResult.to_dict()
  PublishPolicyResult.allowed: bool
  POLICY_VERSION: str
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.qa_uat.publish_policy")

POLICY_VERSION = "qa-uat-publish-policy/1.0"

_PUBLISHABLE_VERDICTS = frozenset({"PASS", "FAIL", "BLOCKED", "MIXED"})
_PROHIBITED_VERDICTS  = frozenset({"UNKNOWN", "ERROR", None, ""})


@dataclass
class PolicyViolation:
    rule: str           # P1..P6
    message: str
    severity: str = "blocking"  # blocking | warning


@dataclass
class PublishPolicyResult:
    allowed: bool
    verdict: Optional[str]
    run_id: Optional[str]
    mode: str
    human_approved: bool
    violations: list = field(default_factory=list)   # list[PolicyViolation]
    warnings: list = field(default_factory=list)     # list[str]
    evidence_complete: bool = True
    missing_artifacts: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "schema_version": POLICY_VERSION,
            "allowed": self.allowed,
            "verdict": self.verdict,
            "run_id": self.run_id,
            "mode": self.mode,
            "human_approved": self.human_approved,
            "evidence_complete": self.evidence_complete,
            "missing_artifacts": self.missing_artifacts,
            "violations": [
                {"rule": v.rule, "message": v.message, "severity": v.severity}
                for v in self.violations
            ],
            "warnings": self.warnings,
            "blocking_count": len([v for v in self.violations if v.severity == "blocking"]),
        }


def evaluate_policy(
    verdict: Optional[str],
    run_id: Optional[str],
    evidence_dir: Optional[Path],
    human_approved: bool = False,
    mode: str = "dry-run",
    evidence_manifest: Optional[dict] = None,
    reason: Optional[str] = None,
    category: Optional[str] = None,
) -> PublishPolicyResult:
    """Evaluate publish policy for a QA UAT run.

    Parameters
    ----------
    verdict : str | None
        Pipeline verdict from result dict.
    run_id : str | None
        Canonical run identity.
    evidence_dir : Path | None
        Run-specific evidence directory.
    human_approved : bool
        Whether the operator explicitly approved publish. Required for mode=publish.
    mode : str
        "dry-run" (default — never requires human approval) or "publish".
    evidence_manifest : dict | None
        Optional from evidence_bundle_checker.check_bundle().
    reason : str | None
        Reason code from pipeline result (informational).
    category : str | None
        Category from pipeline result (informational).

    Returns
    -------
    PublishPolicyResult
    """
    violations: list[PolicyViolation] = []
    warnings: list[str] = []
    evidence_complete = True
    missing_artifacts: list[str] = []

    _verdict = (verdict or "").strip()

    # P1: verdict must be in publishable set
    if _verdict not in _PUBLISHABLE_VERDICTS:
        violations.append(PolicyViolation(
            rule="P1",
            message=f"verdict={_verdict!r} is not in publishable set {sorted(_PUBLISHABLE_VERDICTS)}",
        ))

    # P2: verdict must not be UNKNOWN/ERROR/null
    if _verdict in _PROHIBITED_VERDICTS or not _verdict:
        violations.append(PolicyViolation(
            rule="P2",
            message=f"verdict={_verdict!r} is prohibited — indicates tool bug (open P0 before publishing)",
        ))

    # P3: evidence bundle complete
    if evidence_manifest is not None:
        if not evidence_manifest.get("complete"):
            evidence_complete = False
            missing_artifacts = evidence_manifest.get("missing_artifacts", []) or evidence_manifest.get("missing", [])
            violations.append(PolicyViolation(
                rule="P3",
                message=f"Evidence bundle incomplete — missing: {', '.join(missing_artifacts)}",
            ))
    elif evidence_dir is not None:
        # Quick check: at minimum result.json and execution.jsonl must exist
        _missing = []
        for fname in ("result.json", "execution.jsonl"):
            if not (evidence_dir / fname).exists():
                _missing.append(fname)
        if _missing:
            evidence_complete = False
            missing_artifacts = _missing
            violations.append(PolicyViolation(
                rule="P3",
                message=f"Critical evidence missing: {', '.join(_missing)}",
            ))
    else:
        warnings.append("P3: evidence_dir not provided — cannot verify bundle completeness")

    # P4: run_id present
    if not run_id:
        violations.append(PolicyViolation(
            rule="P4",
            message="run_id is missing — cannot guarantee idempotent publish",
        ))

    # P5: dossier.json present
    if evidence_dir is not None:
        _dossier = evidence_dir / "dossier.json"
        if not _dossier.exists():
            violations.append(PolicyViolation(
                rule="P5",
                message="dossier.json not found in evidence_dir — run qa_dossier_builder first",
            ))
    else:
        warnings.append("P5: evidence_dir not provided — cannot verify dossier presence")

    # P6: human_approved required for mode=publish
    if mode == "publish" and not human_approved:
        violations.append(PolicyViolation(
            rule="P6",
            message="human_approved=False — operator approval required before publishing to ADO",
        ))
    elif mode == "dry-run" and not human_approved:
        warnings.append("P6: dry-run mode — human approval not required but not given")

    blocking = [v for v in violations if v.severity == "blocking"]
    allowed = len(blocking) == 0

    if not allowed:
        logger.warning(
            "publish_policy: BLOCKED — %d violation(s): %s",
            len(blocking),
            "; ".join(v.message[:80] for v in blocking[:3]),
        )
    else:
        logger.info(
            "publish_policy: ALLOWED — verdict=%s run_id=%s mode=%s human_approved=%s",
            _verdict, run_id, mode, human_approved,
        )

    return PublishPolicyResult(
        allowed=allowed,
        verdict=_verdict or None,
        run_id=run_id,
        mode=mode,
        human_approved=human_approved,
        violations=violations,
        warnings=warnings,
        evidence_complete=evidence_complete,
        missing_artifacts=missing_artifacts,
    )


def write_policy_result(evidence_dir: Path, result: PublishPolicyResult) -> Path:
    """Write publish_policy_result.json to evidence_dir. Returns path."""
    path = evidence_dir / "publish_policy_result.json"
    try:
        evidence_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(result.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("publish_policy: could not write publish_policy_result.json: %s", e)
    return path
