"""
ci_artifacts_publisher.py — CI Artifacts Publisher for QA UAT Agent.

Copies run artifacts to a CI output directory and enriches the JUnit XML
report with triage metadata (category, reason, owner, confidence, lane).

Artifacts published:
  ci_output/
    junit.xml              (enriched with triage <properties>)
    playwright-report/     (HTML report from Playwright)
    triage.json
    run_metrics.json
    execution.jsonl
    test_portfolio.json

Usage:
    from ci_artifacts_publisher import publish_ci_artifacts

    result = publish_ci_artifacts(
        evidence_dir="evidence/122",
        ci_output_dir="ci_output",
        triage_result={...},
        run_metrics={...},
        lane="smoke-uat",
        dry_run=False,
    )
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import xml.etree.ElementTree as ET
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_logger = logging.getLogger("stacky.qa_uat.ci_artifacts_publisher")


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class CIPublishResult:
    ok: bool
    dry_run: bool
    ci_output_dir: str
    published_files: list[str] = field(default_factory=list)
    skipped_files: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    junit_enriched: bool = False
    published_at: str = field(default_factory=_utcnow)

    def to_dict(self) -> dict:
        return asdict(self)

    def to_event(self) -> dict:
        return {
            "event": "ci_artifacts_published",
            "ok": self.ok,
            "dry_run": self.dry_run,
            "ci_output_dir": self.ci_output_dir,
            "files_published": len(self.published_files),
            "files_skipped": len(self.skipped_files),
            "junit_enriched": self.junit_enriched,
            "published_at": self.published_at,
            **({"errors": self.errors} if self.errors else {}),
        }


# ── Public API ────────────────────────────────────────────────────────────────

def publish_ci_artifacts(
    evidence_dir: str,
    ci_output_dir: str,
    triage_result: Optional[dict] = None,
    run_metrics: Optional[dict] = None,
    lane: Optional[str] = None,
    exec_logger=None,
    dry_run: bool = False,
) -> CIPublishResult:
    """
    Copy run artifacts to ci_output_dir and enrich JUnit XML with triage data.

    Parameters
    ----------
    evidence_dir   : Path to the evidence directory for this run.
    ci_output_dir  : Target CI output directory (created if absent).
    triage_result  : Triage dict (from failure_triage.py). Optional.
    run_metrics    : RunMetrics dict (from metrics_collector.py). Optional.
    lane           : Active lane name for JUnit enrichment. Optional.
    exec_logger    : ExecutionLogger for emitting ci_artifacts_published event.
    dry_run        : If True, log what would be copied but don't copy anything.

    Returns
    -------
    CIPublishResult
    """
    ev_path = Path(evidence_dir)
    ci_path = Path(ci_output_dir)

    result = CIPublishResult(
        ok=True,
        dry_run=dry_run,
        ci_output_dir=str(ci_path.resolve()),
    )

    if not ev_path.exists():
        result.ok = False
        result.errors.append(f"evidence_dir not found: {evidence_dir}")
        _emit_event(exec_logger, result)
        return result

    if dry_run:
        _logger.info("ci_artifacts_publisher: DRY-RUN mode — no files will be copied")

    if not dry_run:
        ci_path.mkdir(parents=True, exist_ok=True)

    # ── 1. JUnit XML ──────────────────────────────────────────────────────────
    junit_candidates = list(ev_path.rglob("results.xml")) + list(ev_path.rglob("junit*.xml"))
    if not junit_candidates:
        junit_candidates = list((ev_path / "test-results").glob("*.xml")) if (ev_path / "test-results").exists() else []

    junit_src: Optional[Path] = junit_candidates[0] if junit_candidates else None
    if junit_src and junit_src.exists():
        enriched_xml = _enrich_junit(junit_src, triage_result, lane)
        junit_dest = ci_path / "junit.xml"
        if dry_run:
            result.skipped_files.append(str(junit_dest))
            _logger.info("ci_artifacts_publisher: [dry-run] would write enriched %s", junit_dest)
        else:
            try:
                junit_dest.write_text(enriched_xml, encoding="utf-8")
                result.published_files.append(str(junit_dest))
                result.junit_enriched = True
                _logger.info("ci_artifacts_publisher: enriched JUnit written to %s", junit_dest)
            except Exception as exc:
                result.errors.append(f"junit enrichment failed: {exc}")
                _logger.warning("ci_artifacts_publisher: JUnit write error: %s", exc)
    else:
        _logger.debug("ci_artifacts_publisher: no JUnit XML found in %s", ev_path)

    # ── 2. Playwright HTML report ─────────────────────────────────────────────
    pw_report_src = ev_path / "playwright-report"
    if not pw_report_src.exists():
        # Also check tool-root-level playwright-report
        pw_report_src = Path(__file__).parent / "playwright-report"

    if pw_report_src.exists():
        pw_report_dest = ci_path / "playwright-report"
        _copy_tree(pw_report_src, pw_report_dest, result, dry_run)

    # ── 3. Artifact files ─────────────────────────────────────────────────────
    _artifact_files = {
        "triage.json": triage_result,
        "run_metrics.json": run_metrics,
    }
    for fname, data in _artifact_files.items():
        if data is not None:
            dest = ci_path / fname
            if dry_run:
                result.skipped_files.append(str(dest))
            else:
                try:
                    dest.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                    result.published_files.append(str(dest))
                except Exception as exc:
                    result.errors.append(f"{fname} write failed: {exc}")

    # ── 4. execution.jsonl ────────────────────────────────────────────────────
    _copy_file(ev_path / "execution.jsonl", ci_path / "execution.jsonl", result, dry_run)

    # ── 5. test_portfolio.json ────────────────────────────────────────────────
    # May be in run subdirectory
    portfolio_candidates = list(ev_path.rglob("test_portfolio.json"))
    if portfolio_candidates:
        _copy_file(portfolio_candidates[0], ci_path / "test_portfolio.json", result, dry_run)

    if result.errors:
        result.ok = False

    _emit_event(exec_logger, result)
    return result


# ── JUnit enrichment ──────────────────────────────────────────────────────────

def _enrich_junit(
    junit_path: Path,
    triage_result: Optional[dict],
    lane: Optional[str],
) -> str:
    """
    Parse a JUnit XML file and add <properties> to each <testcase> with
    triage metadata (category, reason, owner, confidence) and lane.

    Returns the enriched XML as a string.
    """
    try:
        tree = ET.parse(str(junit_path))
        root = tree.getroot()
    except Exception as exc:
        _logger.warning("ci_artifacts_publisher: cannot parse %s: %s", junit_path, exc)
        return junit_path.read_text(encoding="utf-8", errors="replace")

    # Build per-test triage lookup from triage_result
    # triage_result may have 'scenario_results' list or be a flat dict
    _triage_by_name: dict[str, dict] = {}
    if triage_result:
        for sr in (triage_result.get("scenario_results") or []):
            name = sr.get("scenario_id") or sr.get("test_id") or sr.get("name", "")
            if name:
                _triage_by_name[name] = sr

    # Walk all testcase elements
    for testcase in root.iter("testcase"):
        tc_name = testcase.get("name", "")
        tc_class = testcase.get("classname", "")

        # Find matching triage data
        triage_data = _triage_by_name.get(tc_name) or _triage_by_name.get(tc_class) or {}

        # If flat triage (single scenario) use it for all
        if not triage_data and triage_result:
            triage_data = triage_result

        props_el = testcase.find("properties")
        if props_el is None:
            props_el = ET.SubElement(testcase, "properties")

        def _add_prop(name: str, value) -> None:
            if value is not None:
                prop = ET.SubElement(props_el, "property")
                prop.set("name", name)
                prop.set("value", str(value))

        _add_prop("triage.category", triage_data.get("category"))
        _add_prop("triage.reason", triage_data.get("reason"))
        _add_prop("triage.owner", triage_data.get("owner"))
        _add_prop("triage.confidence", triage_data.get("confidence"))
        if lane:
            _add_prop("qa.lane", lane)

    ET.indent(root, space="  ")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode")


# ── Internal helpers ──────────────────────────────────────────────────────────

def _copy_file(src: Path, dest: Path, result: CIPublishResult, dry_run: bool) -> None:
    if not src.exists():
        return
    if dry_run:
        result.skipped_files.append(str(dest))
        return
    try:
        shutil.copy2(str(src), str(dest))
        result.published_files.append(str(dest))
    except Exception as exc:
        result.errors.append(f"copy {src.name} failed: {exc}")
        _logger.warning("ci_artifacts_publisher: copy error %s: %s", src.name, exc)


def _copy_tree(src: Path, dest: Path, result: CIPublishResult, dry_run: bool) -> None:
    if not src.exists():
        return
    if dry_run:
        result.skipped_files.append(str(dest))
        return
    try:
        if dest.exists():
            shutil.rmtree(str(dest))
        shutil.copytree(str(src), str(dest))
        result.published_files.append(str(dest))
    except Exception as exc:
        result.errors.append(f"copy tree {src.name} failed: {exc}")
        _logger.warning("ci_artifacts_publisher: copytree error %s: %s", src.name, exc)


def _emit_event(exec_logger, result: CIPublishResult) -> None:
    if exec_logger is None:
        return
    try:
        evt = result.to_event()
        exec_logger.event("ci_artifacts_published", {k: v for k, v in evt.items() if k != "event"})
    except Exception as exc:
        _logger.debug("ci_artifacts_publisher: emit event failed: %s", exc)
