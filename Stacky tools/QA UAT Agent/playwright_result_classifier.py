"""
playwright_result_classifier.py — Sprint 5.2: Classify Playwright results into pipeline categories.

PURPOSE
-------
Translate raw Playwright output (JUnit XML or JSON results) into the official
category/verdict/reason taxonomy used across the QA UAT Agent pipeline:

    APP   — Application defects (assertion failures)
    NAV   — Navigation/selector failures (UI structure issues)
    ENV   — Environment failures (page load, connection refused)
    DATA  — Data precondition failures (empty grids, missing test data)
    OPS   — Infrastructure failures (worker crash, browser crash)
    OBS   — Observability gaps (missing trace when expected)
    PIP   — Pipeline meta failures (no tests, spec file missing)

CLASSIFICATION TABLE
--------------------
Pattern                              | Category | Verdict  | Reason
-------------------------------------|----------|----------|-------------------
Assertion fails (expect/toBe etc.)   | APP      | FAIL     | ASSERTION_FAILED
locator timeout / selector not found | NAV      | BLOCKED  | SELECTOR_TIMEOUT
page.goto timeout / ERR_CONNECTION   | ENV      | BLOCKED  | PAGE_LOAD_FAILED
Grid precheck empty                  | DATA     | BLOCKED  | GRID_EMPTY
total == 0                           | PIP      | BLOCKED  | NO_TESTS_FOUND
Worker/browser crash                 | OPS      | BLOCKED  | WORKER_CRASH
Trace missing when expected          | OBS      | BLOCKED  | TRACE_MISSING
Spec file missing / import error     | PIP      | BLOCKED  | SPEC_FILE_MISSING
All pass                             | None     | PASS     | None

RULE
----
classify_playwright_results() NEVER returns verdict=UNKNOWN.
total=0 ALWAYS maps to BLOCKED PIP NO_TESTS_FOUND — never PASS.

VERSION
-------
1.0.0 — Sprint 5
"""
from __future__ import annotations

import json
import logging
import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.qa_uat.playwright_result_classifier")

_TOOL_VERSION = "1.0.0"

# ── Official verdict / category / reason values ────────────────────────────────

VALID_VERDICTS   = frozenset({"PASS", "FAIL", "BLOCKED", "MIXED"})
VALID_CATEGORIES = frozenset({"APP", "NAV", "ENV", "DATA", "OPS", "OBS", "PIP"})

# ── Classification patterns (priority order) ───────────────────────────────────
# Each entry: (verdict, category, reason, pattern_regex_or_None)
# Evaluated top-to-bottom; first match wins.
# Entries with pattern=None are structural (handled in code, not regex).

_CLASSIFICATION_RULES: list[tuple[str, str, str, Optional[str]]] = [
    # ── Structural rules (handled in code, pattern=None) ──────────────────────
    # total == 0 → PIP BLOCKED NO_TESTS_FOUND  [checked before regex]
    # all pass  → PASS null null               [checked after all rules]

    # ── Spec file / import errors ─────────────────────────────────────────────
    ("BLOCKED", "PIP",  "SPEC_FILE_MISSING",
     r"no\s+test\s+files?\s+found|ENOENT|cannot\s+find\s+module|import\s+error|"
     r"Could not find|spec.*not.*found|spec.*missing"),

    # ── Worker / browser crash ────────────────────────────────────────────────
    ("BLOCKED", "OPS",  "WORKER_CRASH",
     r"worker\s+(crashed|exited|killed)|browser\s+(crashed|closed\s+unexpectedly)|"
     r"Target closed|Target page.*closed|Protocol error.*Target closed"),

    # ── Environment failures ───────────────────────────────────────────────────
    ("BLOCKED", "ENV",  "PAGE_LOAD_FAILED",
     r"ERR_CONNECTION_REFUSED|ERR_NAME_NOT_RESOLVED|ERR_NETWORK|"
     r"net::ERR_|page\.goto.*timeout|navigation.*timeout|"
     r"Timeout.*waiting for.*navigation|waitForNavigation.*timeout"),

    # ── Navigation / selector failures ────────────────────────────────────────
    ("BLOCKED", "NAV",  "SELECTOR_TIMEOUT",
     r"locator\.(?:click|fill|type|check|uncheck|hover|tap|press|selectOption|"
     r"dragTo|focus|dispatchEvent).*timeout|"
     r"Timeout.*waiting for\s+(?:locator|selector)|"
     r"locator\s+resolved\s+to\s+0|"
     r"selector\s+not\s+found|SELECTOR_NOT_FOUND|"
     r"element\s+is\s+not\s+(?:attached|visible|enabled)|"
     r"waiting for\s+(?:.*)\s+to\s+be\s+(?:visible|attached|enabled|stable)"),

    # ── Data / grid precondition failures ────────────────────────────────────
    ("BLOCKED", "DATA", "GRID_EMPTY",
     r"GRID_EMPTY|grid\s+empty|no\s+rows?\s+(?:found|available)|"
     r"grid\s+has\s+0\s+rows?|row_count.*=.*0|DATA_BLOCKED"),

    # ── Application assertion failures ────────────────────────────────────────
    # Must come AFTER nav/env/ops to avoid misclassifying wrapped assertion errors
    ("FAIL",    "APP",  "ASSERTION_FAILED",
     r"expect\s*\(|\.toBe\b|\.toEqual\b|\.toHaveText\b|\.toBeVisible\b|"
     r"\.toContainText\b|\.toHaveValue\b|\.toHaveCount\b|\.toBeChecked\b|"
     r"\.toBeEnabled\b|\.toBeDisabled\b|\.toHaveURL\b|\.toHaveTitle\b|"
     r"AssertionError|Expected.*Received|expect.*received"),

    # ── Observability gap ─────────────────────────────────────────────────────
    ("BLOCKED", "OBS",  "TRACE_MISSING",
     r"TRACE_MISSING|trace.*not\s+found|trace.*missing|"
     r"expected\s+trace.*but.*none"),
]

_COMPILED_RULES: Optional[list[tuple[str, str, str, Optional[re.Pattern]]]] = None


def _get_compiled_rules() -> list[tuple[str, str, str, Optional[re.Pattern]]]:
    global _COMPILED_RULES
    if _COMPILED_RULES is None:
        _COMPILED_RULES = [
            (verdict, category, reason,
             re.compile(pattern, re.IGNORECASE | re.DOTALL) if pattern else None)
            for verdict, category, reason, pattern in _CLASSIFICATION_RULES
        ]
    return _COMPILED_RULES


# ── Dataclasses ────────────────────────────────────────────────────────────────

@dataclass
class ScenarioResult:
    scenario_id: str
    title: str
    screen: Optional[str]
    status: str           # passed | failed | blocked | skipped
    duration_ms: int
    attempts: int
    classification: dict  # verdict, category, reason
    artifacts: dict       # trace, screenshot, console, network


@dataclass
class PlaywrightClassificationResult:
    verdict: str          # PASS | FAIL | BLOCKED | MIXED
    category: Optional[str]
    reason: Optional[str]
    total: int
    passed: int
    failed: int
    blocked: int
    skipped: int
    retries: int
    duration_ms: int
    scenario_results: list[ScenarioResult] = field(default_factory=list)
    artifacts: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "verdict": self.verdict,
            "category": self.category,
            "reason": self.reason,
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "blocked": self.blocked,
            "skipped": self.skipped,
            "retries": self.retries,
            "duration_ms": self.duration_ms,
            "scenario_results": [
                {
                    "scenario_id": s.scenario_id,
                    "title": s.title,
                    "screen": s.screen,
                    "status": s.status,
                    "duration_ms": s.duration_ms,
                    "attempts": s.attempts,
                    "classification": s.classification,
                    "artifacts": s.artifacts,
                }
                for s in self.scenario_results
            ],
            "artifacts": self.artifacts,
        }


# ── Main classification function ───────────────────────────────────────────────

def classify_playwright_results(
    junit_path: Optional[str] = None,
    json_path: Optional[str] = None,
    execution_log_path: Optional[str] = None,
    nav_precheck_results: Optional[list] = None,
) -> PlaywrightClassificationResult:
    """
    Classify Playwright results from JUnit XML and/or JSON reporter output.

    At least one of `junit_path` or `json_path` must be provided.
    If both are provided, JSON takes precedence for detail; JUnit is used as fallback.

    Parameters
    ----------
    junit_path : str | None
        Path to reports/junit.xml produced by Playwright's JUnit reporter.
    json_path : str | None
        Path to reports/playwright-results.json produced by Playwright's JSON reporter.
    execution_log_path : str | None
        Path to execution.jsonl — used to pull nav_precheck_result events.
    nav_precheck_results : list | None
        Pre-parsed nav_precheck_result events (avoids re-reading execution.jsonl).

    Returns
    -------
    PlaywrightClassificationResult
    """
    # ── Load reports ──────────────────────────────────────────────────────────
    pw_json: dict = {}
    junit_data: Optional[ET.Element] = None

    if json_path:
        pw_json = _load_json_report(json_path)

    if junit_path and not pw_json:
        # Fall back to JUnit only when JSON is unavailable
        junit_data = _load_junit_report(junit_path)

    # ── Pull nav_precheck events from execution.jsonl if not provided ─────────
    precheck_events: list = nav_precheck_results or []
    if not precheck_events and execution_log_path:
        precheck_events = _load_precheck_events(execution_log_path)

    # ── Extract scenario-level data ───────────────────────────────────────────
    scenario_results: list[ScenarioResult] = []
    total_retries = 0

    if pw_json:
        scenario_results, total_retries = _parse_json_report(pw_json, precheck_events)
    elif junit_data is not None:
        scenario_results, total_retries = _parse_junit_report(junit_data, precheck_events)

    # ── Structural guard: total == 0 → BLOCKED PIP NO_TESTS_FOUND ─────────────
    total = len(scenario_results)
    if total == 0:
        return PlaywrightClassificationResult(
            verdict="BLOCKED",
            category="PIP",
            reason="NO_TESTS_FOUND",
            total=0,
            passed=0,
            failed=0,
            blocked=0,
            skipped=0,
            retries=0,
            duration_ms=0,
            scenario_results=[],
            artifacts=_collect_report_artifacts(junit_path, json_path),
        )

    # ── Aggregate counts ──────────────────────────────────────────────────────
    passed  = sum(1 for s in scenario_results if s.status == "passed")
    failed  = sum(1 for s in scenario_results if s.status == "failed")
    blocked = sum(1 for s in scenario_results if s.status == "blocked")
    skipped = sum(1 for s in scenario_results if s.status == "skipped")
    total_duration = sum(s.duration_ms for s in scenario_results)

    # ── Aggregate verdict ─────────────────────────────────────────────────────
    verdict, category, reason = _aggregate_verdict(scenario_results, passed, failed, blocked, total)

    # ── Artifact links ────────────────────────────────────────────────────────
    artifacts = _collect_report_artifacts(junit_path, json_path)
    _enrich_artifact_counts(artifacts, scenario_results)

    return PlaywrightClassificationResult(
        verdict=verdict,
        category=category,
        reason=reason,
        total=total,
        passed=passed,
        failed=failed,
        blocked=blocked,
        skipped=skipped,
        retries=total_retries,
        duration_ms=total_duration,
        scenario_results=scenario_results,
        artifacts=artifacts,
    )


# ── Classification helpers ─────────────────────────────────────────────────────

def classify_error_message(error_text: str) -> tuple[str, str, str]:
    """
    Classify a single error message string into (verdict, category, reason).

    Never returns UNKNOWN — falls back to FAIL/APP/ASSERTION_FAILED if no
    specific rule matches (conservative: assume it is an app-level defect).
    """
    if not error_text or not error_text.strip():
        return "BLOCKED", "OPS", "WORKER_CRASH"

    for verdict, category, reason, pattern in _get_compiled_rules():
        if pattern is not None and pattern.search(error_text):
            return verdict, category, reason

    # Safe fallback — never UNKNOWN
    return "FAIL", "APP", "ASSERTION_FAILED"


def _classify_scenario(status: str, error_messages: list[str], attempts: int,
                        precheck_data: Optional[dict] = None) -> dict:
    """
    Build a classification dict for one scenario.

    Parameters
    ----------
    status : str
        Playwright status: passed | failed | timedOut | interrupted | skipped
    error_messages : list[str]
        Collected error message strings from all test results.
    attempts : int
        Number of attempts (>1 = retried).
    precheck_data : dict | None
        nav_precheck_result event for this scenario (if any).
    """
    # ── Precheck override (DATA/NAV from precheck beats Playwright status) ────
    if precheck_data is not None:
        decision = precheck_data.get("decision", "")
        if decision == "BLOCKED":
            cat = precheck_data.get("category", "DATA")
            rsn = precheck_data.get("reason", "GRID_EMPTY")
            return {"verdict": "BLOCKED", "category": cat, "reason": rsn}

    # ── Structural status checks ───────────────────────────────────────────────
    if status == "passed":
        return {"verdict": "PASS", "category": None, "reason": None}
    if status == "skipped":
        return {"verdict": "SKIPPED", "category": "PIP", "reason": "SCENARIO_SKIPPED"}
    if status in ("timedOut", "interrupted"):
        # Timeout classification depends on error messages
        combined = " ".join(error_messages)
        if combined:
            v, c, r = classify_error_message(combined)
            # Force NAV for generic timeouts not matched by env/nav rules
            if c not in ("ENV", "NAV"):
                c = "NAV"
                r = "SELECTOR_TIMEOUT"
            return {"verdict": "BLOCKED", "category": c, "reason": r}
        return {"verdict": "BLOCKED", "category": "NAV", "reason": "SELECTOR_TIMEOUT"}

    # ── Classify by error messages ─────────────────────────────────────────────
    combined = " ".join(str(m) for m in error_messages)
    if combined.strip():
        v, c, r = classify_error_message(combined)
        return {"verdict": v, "category": c, "reason": r}

    # ── Status-based fallback ─────────────────────────────────────────────────
    if status == "failed":
        return {"verdict": "FAIL", "category": "APP", "reason": "ASSERTION_FAILED"}

    # Final safety net — never UNKNOWN
    return {"verdict": "BLOCKED", "category": "OPS", "reason": "WORKER_CRASH"}


# ── Aggregate verdict ─────────────────────────────────────────────────────────

def _aggregate_verdict(
    scenarios: list[ScenarioResult],
    passed: int,
    failed: int,
    blocked: int,
    total: int,
) -> tuple[str, Optional[str], Optional[str]]:
    """
    Compute aggregate (verdict, category, reason) from all scenario results.

    Rules:
    - All pass → PASS, None, None
    - Any fail + any pass → MIXED + dominant fail category/reason
    - All fail or any fail (no pass) → FAIL + dominant fail category/reason
    - All blocked → BLOCKED + dominant block category/reason
    - Any blocked (no pass/fail) → BLOCKED
    """
    if passed == total:
        return "PASS", None, None

    # Collect non-pass classifications
    non_pass = [
        s.classification
        for s in scenarios
        if s.status not in ("passed", "skipped")
    ]

    dominant = _dominant_classification(non_pass)

    if passed > 0 and (failed > 0 or blocked > 0):
        return "MIXED", dominant.get("category"), dominant.get("reason")

    if failed > 0:
        return "FAIL", dominant.get("category"), dominant.get("reason")

    if blocked > 0:
        return "BLOCKED", dominant.get("category"), dominant.get("reason")

    # Edge: only skipped
    return "BLOCKED", "PIP", "NO_TESTS_FOUND"


def _dominant_classification(classifications: list[dict]) -> dict:
    """
    Find the most common (category, reason) pair among non-pass classifications.
    Ties broken by first occurrence.
    """
    if not classifications:
        return {"category": "PIP", "reason": "NO_TESTS_FOUND"}

    counts: dict[tuple, int] = {}
    order: list[tuple] = []
    for c in classifications:
        key = (c.get("category", "OPS"), c.get("reason", "WORKER_CRASH"))
        if key not in counts:
            order.append(key)
        counts[key] = counts.get(key, 0) + 1

    best = max(order, key=lambda k: counts[k])
    return {"category": best[0], "reason": best[1]}


# ── JSON report parser ─────────────────────────────────────────────────────────

def _parse_json_report(
    pw_json: dict,
    precheck_events: list,
) -> tuple[list[ScenarioResult], int]:
    """Parse Playwright's JSON reporter output into ScenarioResult list."""
    scenarios: list[ScenarioResult] = []
    total_retries = 0

    # Build precheck lookup: scenario_id → event
    precheck_map = {e.get("scenario_id"): e for e in precheck_events if e.get("scenario_id")}

    # Walk suite tree
    for suite_or_spec in _iter_specs(pw_json.get("suites", [])):
        spec = suite_or_spec
        spec_title = spec.get("title", "") or spec.get("file", "")
        scenario_id = _extract_scenario_id(spec_title)
        screen = _extract_screen(spec)

        for test in spec.get("tests", []):
            test_title = test.get("title", spec_title)
            test_results = test.get("results", [])
            attempts = len(test_results)
            total_retries += max(0, attempts - 1)

            # Aggregate status from all attempts
            statuses = [r.get("status", "failed") for r in test_results]
            final_status = _aggregate_attempt_statuses(statuses)

            # Collect all error messages across all attempts
            error_msgs: list[str] = []
            for r in test_results:
                for err in (r.get("errors") or []):
                    msg = err.get("message") or err.get("value") or ""
                    if msg:
                        error_msgs.append(str(msg))

            duration = sum(r.get("duration", 0) for r in test_results)

            precheck = precheck_map.get(scenario_id)
            classification = _classify_scenario(
                status=final_status,
                error_messages=error_msgs,
                attempts=attempts,
                precheck_data=precheck,
            )

            # Collect artifact references from last attempt
            artifacts = _extract_artifacts_from_results(test_results)

            scenarios.append(ScenarioResult(
                scenario_id=scenario_id,
                title=test_title,
                screen=screen,
                status=_pw_status_to_pipeline(final_status),
                duration_ms=duration,
                attempts=attempts,
                classification=classification,
                artifacts=artifacts,
            ))

    return scenarios, total_retries


def _iter_specs(suites: list) -> list:
    """Recursively collect all spec-level entries from Playwright JSON report."""
    specs: list = []
    for suite in suites:
        specs.extend(suite.get("specs", []))
        specs.extend(_iter_specs(suite.get("suites", [])))
    return specs


def _aggregate_attempt_statuses(statuses: list[str]) -> str:
    """Playwright retries: final status is the last attempt's status."""
    if not statuses:
        return "failed"
    return statuses[-1]


def _pw_status_to_pipeline(pw_status: str) -> str:
    """Map Playwright test status to pipeline status vocabulary."""
    return {
        "passed": "passed",
        "failed": "failed",
        "timedOut": "blocked",
        "interrupted": "blocked",
        "skipped": "skipped",
    }.get(pw_status, "failed")


def _extract_scenario_id(title: str) -> str:
    """Extract P01/RF-008-CA-01 from spec title or filename."""
    m = re.match(r'^(P\d{2,})', title)
    if m:
        return m.group(1)
    m = re.search(r'(RF-\d{3}-CA-\d{2})', title, re.IGNORECASE)
    if m:
        return m.group(1)
    # Fallback: sanitize title as ID
    return re.sub(r'[^a-zA-Z0-9_-]', '_', title)[:30] or "unknown"


def _extract_screen(spec: dict) -> Optional[str]:
    """Try to find an .aspx screen reference in the spec title or file path."""
    text = f"{spec.get('title', '')} {spec.get('file', '')}"
    m = re.search(r'(Frm\w+\.aspx)', text, re.IGNORECASE)
    return m.group(1) if m else None


def _extract_artifacts_from_results(test_results: list) -> dict:
    """Extract artifact paths from Playwright test result attachments."""
    artifacts: dict = {
        "trace": None,
        "screenshot": None,
        "video": None,
        "console": None,
        "network": None,
    }
    for r in test_results:
        for att in (r.get("attachments") or []):
            name = att.get("name", "")
            path = att.get("path") or att.get("body") or ""
            if name == "trace" and not artifacts["trace"]:
                artifacts["trace"] = path
            elif name in ("screenshot", "test-failure-screenshot") and not artifacts["screenshot"]:
                artifacts["screenshot"] = path
            elif name == "video" and not artifacts["video"]:
                artifacts["video"] = path
    return artifacts


# ── JUnit XML parser ───────────────────────────────────────────────────────────

def _parse_junit_report(
    root: ET.Element,
    precheck_events: list,
) -> tuple[list[ScenarioResult], int]:
    """Parse JUnit XML into ScenarioResult list (fallback when JSON unavailable)."""
    scenarios: list[ScenarioResult] = []
    total_retries = 0
    precheck_map = {e.get("scenario_id"): e for e in precheck_events if e.get("scenario_id")}

    # JUnit: <testsuites> → <testsuite> → <testcase>
    for testsuite in root.iter("testsuite"):
        for testcase in testsuite.findall("testcase"):
            name = testcase.get("name", "")
            classname = testcase.get("classname", "")
            duration_s = float(testcase.get("time", "0") or "0")
            duration_ms = int(duration_s * 1000)

            scenario_id = _extract_scenario_id(name or classname)

            failure_el = testcase.find("failure")
            error_el = testcase.find("error")
            skipped_el = testcase.find("skipped")

            error_msgs: list[str] = []
            pw_status = "passed"
            if failure_el is not None:
                pw_status = "failed"
                msg = failure_el.get("message", "") or (failure_el.text or "")
                if msg:
                    error_msgs.append(msg)
            elif error_el is not None:
                pw_status = "failed"
                msg = error_el.get("message", "") or (error_el.text or "")
                if msg:
                    error_msgs.append(msg)
            elif skipped_el is not None:
                pw_status = "skipped"

            precheck = precheck_map.get(scenario_id)
            classification = _classify_scenario(
                status=pw_status,
                error_messages=error_msgs,
                attempts=1,
                precheck_data=precheck,
            )

            scenarios.append(ScenarioResult(
                scenario_id=scenario_id,
                title=name,
                screen=None,
                status=_pw_status_to_pipeline(pw_status),
                duration_ms=duration_ms,
                attempts=1,
                classification=classification,
                artifacts={},
            ))

    return scenarios, total_retries


# ── Artifact helpers ───────────────────────────────────────────────────────────

def _collect_report_artifacts(junit_path: Optional[str], json_path: Optional[str]) -> dict:
    """Build the top-level artifacts dict for runner_summary."""
    artifacts: dict = {
        "junit": junit_path,
        "json_results": json_path,
        "html_report": None,
        "trace_count": 0,
        "screenshots_count": 0,
        "video_count": 0,
    }
    # Try to detect html_report from known Playwright default location
    if json_path:
        reports_dir = Path(json_path).parent
        tool_dir = reports_dir.parent
        html_index = tool_dir / "playwright-report" / "index.html"
        if html_index.is_file():
            artifacts["html_report"] = str(html_index)
    return artifacts


def _enrich_artifact_counts(artifacts: dict, scenarios: list[ScenarioResult]) -> None:
    """Count trace/screenshot/video artifacts across all scenarios."""
    trace_count = 0
    screenshot_count = 0
    video_count = 0
    for s in scenarios:
        a = s.artifacts
        if a.get("trace"):
            trace_count += 1
        if a.get("screenshot"):
            screenshot_count += 1
        if a.get("video"):
            video_count += 1
    artifacts["trace_count"] = trace_count
    artifacts["screenshots_count"] = screenshot_count
    artifacts["video_count"] = video_count


# ── File loaders ───────────────────────────────────────────────────────────────

def _load_json_report(path: str) -> dict:
    """Load Playwright JSON reporter output. Returns {} on error."""
    try:
        p = Path(path)
        if not p.is_file():
            logger.debug("JSON report not found: %s", path)
            return {}
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.debug("Could not load JSON report %s: %s", path, exc)
        return {}


def _load_junit_report(path: str) -> Optional[ET.Element]:
    """Load JUnit XML. Returns None on error."""
    try:
        p = Path(path)
        if not p.is_file():
            logger.debug("JUnit report not found: %s", path)
            return None
        return ET.fromstring(p.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.debug("Could not parse JUnit XML %s: %s", path, exc)
        return None


def _load_precheck_events(execution_log_path: str) -> list:
    """Extract nav_precheck_result events from execution.jsonl."""
    events: list = []
    try:
        p = Path(execution_log_path)
        if not p.is_file():
            return events
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if obj.get("event") == "nav_precheck_result":
                    data = obj.get("data") or obj
                    events.append(data)
            except json.JSONDecodeError:
                pass
    except Exception as exc:
        logger.debug("Could not load execution log %s: %s", execution_log_path, exc)
    return events


# ── Precheck result for nav_precheck_result event ─────────────────────────────

def build_nav_precheck_result(
    ticket_id: int,
    scenario_id: str,
    screen: str,
    target_alias: str,
    selector: str,
    visible: bool,
    row_count: int,
    timeout_ms: int,
) -> dict:
    """
    Build a structured nav_precheck_result event dict.

    Called from the TypeScript bridge / execution logger when a grid precheck
    completes.  This function ensures consistent structure regardless of
    which code path generates the event.
    """
    if not visible:
        decision = "BLOCKED"
        category = "NAV"
        reason = "SELECTOR_NOT_FOUND"
    elif row_count == 0:
        decision = "BLOCKED"
        category = "DATA"
        reason = "GRID_EMPTY"
    else:
        decision = "PASS"
        category = None
        reason = None

    return {
        "event": "nav_precheck_result",
        "ticket_id": ticket_id,
        "scenario_id": scenario_id,
        "screen": screen,
        "target_alias": target_alias,
        "selector": selector,
        "visible": visible,
        "row_count": row_count,
        "timeout_ms": timeout_ms,
        "decision": decision,
        "category": category,
        "reason": reason,
    }


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="playwright_result_classifier — classify Playwright results into pipeline categories"
    )
    parser.add_argument("--junit", help="Path to JUnit XML report")
    parser.add_argument("--json", dest="json_path", help="Path to Playwright JSON report")
    parser.add_argument("--execution-log", help="Path to execution.jsonl")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, stream=sys.stderr)

    result = classify_playwright_results(
        junit_path=args.junit,
        json_path=args.json_path,
        execution_log_path=args.execution_log,
    )
    import json as _json
    print(_json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
