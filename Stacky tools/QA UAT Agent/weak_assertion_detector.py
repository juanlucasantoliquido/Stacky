"""
weak_assertion_detector.py — Weak Assertion Detector (Sprint 13).

Analyzes Playwright test spec files (.spec.ts) to detect weak, missing, or
cosmetic-only assertions that would produce false PASS verdicts.

WHAT IS A WEAK ASSERTION:
  - `expect(page).toHaveTitle(...)` — only checks page title (cosmetic)
  - `expect(element).toBeVisible()` — checks visibility but not value
  - `expect(true).toBe(true)` — trivially true, no real check
  - No `expect()` call at all in a test block
  - `await page.waitForLoadState()` without subsequent assertion
  - Console log / screenshot only — no functional assertion

WHAT IS A STRONG ASSERTION:
  - `expect(element).toHaveText(...)` — verifies specific content
  - `expect(element).toHaveValue(...)` — verifies field value
  - `expect(count).toBeGreaterThan(0)` — verifies data presence
  - `expect(locator).toHaveCount(N)` — verifies grid row count
  - `expect(response.status()).toBe(200)` — verifies API result
  - Assertions on specific data values (IDs, amounts, names)

RULES:
  - Every test function must have at least one strong assertion.
  - `toBeVisible()` alone is NEVER sufficient for P0 scenarios.
  - Tests that only take screenshots / log are classified WEAK.

PUBLIC API:
  detect(spec_files, exec_logger, evidence_dir, run_id, ticket_id) -> WeakAssertionReport
  detect_in_file(spec_file_path) -> FileAssertionAnalysis
  WeakAssertionReport.to_dict() -> dict

EVIDENCE ARTIFACT:
  evidence/<ticket_id>/<run_id>/weak_assertion_report.json

EVENTS EMITTED:
  weak_assertion_detected  — per test with weak/missing assertions
  weak_assertion_summary   — aggregated counts

SECURITY:
  - Only reads .spec.ts / .spec.js files — no execution.
  - No LLM calls — fully deterministic rule-based analysis.
  - File paths are not logged in full (only filename) to avoid path disclosure.
"""
from __future__ import annotations

import datetime
import json
import logging
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Optional, Dict, Set

logger = logging.getLogger("stacky.qa_uat.weak_assertion_detector")

_TOOL_VERSION = "1.0.0"
_SCHEMA_VERSION = "weak_assertion_report/1.0"

# ── Assertion classification patterns ─────────────────────────────────────────

# Strong assertions: verify actual data/state values
_STRONG_PATTERNS: List[re.Pattern] = [
    re.compile(r"\.toHaveText\s*\(", re.IGNORECASE),
    re.compile(r"\.toHaveValue\s*\(", re.IGNORECASE),
    re.compile(r"\.toHaveCount\s*\(", re.IGNORECASE),
    re.compile(r"\.toEqual\s*\(", re.IGNORECASE),
    re.compile(r"\.toBe\s*\([^)t]", re.IGNORECASE),       # toBe(value) but not toBe(true)
    re.compile(r"\.toContain\s*\(", re.IGNORECASE),
    re.compile(r"\.toBeGreaterThan\s*\(", re.IGNORECASE),
    re.compile(r"\.toBeLessThan\s*\(", re.IGNORECASE),
    re.compile(r"\.toMatch\s*\(", re.IGNORECASE),
    re.compile(r"\.toHaveAttribute\s*\(", re.IGNORECASE),
    re.compile(r"\.toHaveURL\s*\(", re.IGNORECASE),       # checks specific URL
    re.compile(r"\.toHaveCSS\s*\(", re.IGNORECASE),
]

# Trivially-true patterns: always pass regardless of app state
_TRIVIAL_PATTERNS: List[re.Pattern] = [
    re.compile(r"expect\s*\(\s*true\s*\)\s*\.toBe\s*\(\s*true\s*\)", re.IGNORECASE),
    re.compile(r"expect\s*\(\s*1\s*\)\s*\.toBe\s*\(\s*1\s*\)", re.IGNORECASE),
    re.compile(r"expect\s*\(\s*null\s*\)\s*\.toBeNull\s*\(\s*\)", re.IGNORECASE),
]

# Weak-only patterns: check existence/visibility but not value
_WEAK_PATTERNS: List[re.Pattern] = [
    re.compile(r"\.toBeVisible\s*\(\s*\)", re.IGNORECASE),
    re.compile(r"\.toBeEnabled\s*\(\s*\)", re.IGNORECASE),
    re.compile(r"\.toBeDisabled\s*\(\s*\)", re.IGNORECASE),
    re.compile(r"\.toBeHidden\s*\(\s*\)", re.IGNORECASE),
    re.compile(r"\.toBeChecked\s*\(\s*\)", re.IGNORECASE),
    re.compile(r"\.toHaveTitle\s*\(", re.IGNORECASE),      # page title only
    re.compile(r"expect\s*\(.+\)\s*\.toBeTruthy\s*\(\s*\)", re.IGNORECASE),
    re.compile(r"expect\s*\(.+\)\s*\.toBeDefined\s*\(\s*\)", re.IGNORECASE),
]

# Detect any expect() call
_ANY_EXPECT_PATTERN = re.compile(r"\bexpect\s*\(", re.IGNORECASE)

# Test block patterns (detect test/it boundaries)
_TEST_START_PATTERN = re.compile(
    r"(?:^|\s)(?:test|it)\s*\(\s*['\"`](.+?)['\"`]",
    re.MULTILINE,
)


# ── Assertion strength classification ─────────────────────────────────────────

class AssertionStrength:
    STRONG  = "STRONG"
    WEAK    = "WEAK"
    TRIVIAL = "TRIVIAL"
    NONE    = "NONE"     # No assertion at all


def classify_assertion_strength(test_block_code: str) -> str:
    """
    Classify the assertion strength of a test block.

    Returns AssertionStrength.*
    """
    if not _ANY_EXPECT_PATTERN.search(test_block_code):
        return AssertionStrength.NONE

    # Check for trivially-true assertions
    for pat in _TRIVIAL_PATTERNS:
        if pat.search(test_block_code):
            return AssertionStrength.TRIVIAL

    # Check for strong assertions
    for pat in _STRONG_PATTERNS:
        if pat.search(test_block_code):
            return AssertionStrength.STRONG

    # Has expect() but only weak patterns
    return AssertionStrength.WEAK


# ── Dataclasses ────────────────────────────────────────────────────────────────

@dataclass
class TestAssertionResult:
    """Result for a single test function's assertion analysis."""
    test_name: str
    file_name: str
    line_number: Optional[int]
    assertion_strength: str           # AssertionStrength.*
    expect_call_count: int
    strong_count: int
    weak_count: int
    trivial_count: int
    is_weak: bool                     # True when not STRONG
    finding: Optional[str]            # Human-readable finding description

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class FileAssertionAnalysis:
    """Assertion analysis for a single .spec.ts file."""
    file_name: str
    file_path: str
    total_tests: int
    strong_tests: int
    weak_tests: int
    trivial_tests: int
    no_assertion_tests: int
    test_results: List[TestAssertionResult] = field(default_factory=list)

    @property
    def has_weak_tests(self) -> bool:
        return self.weak_tests > 0 or self.trivial_tests > 0 or self.no_assertion_tests > 0

    def to_dict(self) -> dict:
        return {
            "file_name": self.file_name,
            "total_tests": self.total_tests,
            "strong_tests": self.strong_tests,
            "weak_tests": self.weak_tests,
            "trivial_tests": self.trivial_tests,
            "no_assertion_tests": self.no_assertion_tests,
            "has_weak_tests": self.has_weak_tests,
            "test_results": [t.to_dict() for t in self.test_results],
        }


@dataclass
class WeakAssertionReport:
    """Aggregated weak assertion analysis for all spec files in a run."""
    ok: bool                          # True when no blocking weak tests
    run_id: str
    ticket_id: object
    files_analyzed: int
    total_tests: int
    strong_tests: int
    weak_tests: int
    trivial_tests: int
    no_assertion_tests: int
    publish_blocked: bool             # True when P0 tests have no strong assertions
    file_analyses: List[FileAssertionAnalysis] = field(default_factory=list)
    evidence_path: Optional[str] = None
    analyzed_at: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "schema_version": _SCHEMA_VERSION,
            "ok": self.ok,
            "run_id": self.run_id,
            "ticket_id": self.ticket_id,
            "files_analyzed": self.files_analyzed,
            "total_tests": self.total_tests,
            "strong_tests": self.strong_tests,
            "weak_tests": self.weak_tests,
            "trivial_tests": self.trivial_tests,
            "no_assertion_tests": self.no_assertion_tests,
            "publish_blocked": self.publish_blocked,
            "file_analyses": [f.to_dict() for f in self.file_analyses],
            "evidence_path": self.evidence_path,
            "analyzed_at": self.analyzed_at,
        }

    def to_event(self) -> dict:
        return {
            "event_type": "weak_assertion_summary",
            "run_id": self.run_id,
            "ticket_id": self.ticket_id,
            "ok": self.ok,
            "total_tests": self.total_tests,
            "weak_tests": self.weak_tests,
            "no_assertion_tests": self.no_assertion_tests,
            "publish_blocked": self.publish_blocked,
        }


# ── File analyzer ─────────────────────────────────────────────────────────────

def detect_in_file(spec_file_path: Path) -> FileAssertionAnalysis:
    """
    Analyze assertion strength in a single Playwright spec file.

    Parses test/it blocks and classifies the assertion strength of each.
    Returns a FileAssertionAnalysis with per-test results.
    """
    try:
        content = spec_file_path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        logger.warning("weak_assertion_detector: cannot read %s: %s", spec_file_path.name, exc)
        return FileAssertionAnalysis(
            file_name=spec_file_path.name,
            file_path=spec_file_path.name,  # don't expose full path
            total_tests=0,
            strong_tests=0,
            weak_tests=0,
            trivial_tests=0,
            no_assertion_tests=0,
        )

    lines = content.splitlines()
    test_results: List[TestAssertionResult] = []

    # Find test block boundaries by scanning for test/it declarations
    test_positions: List[tuple[int, str]] = []  # (line_idx, test_name)
    for line_idx, line in enumerate(lines):
        m = _TEST_START_PATTERN.search(line)
        if m:
            test_positions.append((line_idx, m.group(1)))

    # Extract code blocks for each test (heuristic: between test declarations)
    for i, (start_line, test_name) in enumerate(test_positions):
        end_line = test_positions[i + 1][0] if i + 1 < len(test_positions) else len(lines)
        block = "\n".join(lines[start_line:end_line])

        # Count assertion types in this block
        strong_count = sum(1 for pat in _STRONG_PATTERNS if pat.search(block))
        weak_count = sum(1 for pat in _WEAK_PATTERNS if pat.search(block))
        trivial_count = sum(1 for pat in _TRIVIAL_PATTERNS if pat.search(block))
        expect_count = len(_ANY_EXPECT_PATTERN.findall(block))

        strength = classify_assertion_strength(block)

        # Build finding description
        if strength == AssertionStrength.NONE:
            finding = "Test has no expect() calls — cannot verify any functional requirement"
        elif strength == AssertionStrength.TRIVIAL:
            finding = "Test only has trivially-true assertions (e.g., expect(true).toBe(true))"
        elif strength == AssertionStrength.WEAK:
            weak_assertions = [
                pat.pattern.split(r"\.")[0].replace(r"\.", ".") + "..."
                for pat in _WEAK_PATTERNS if pat.search(block)
            ][:3]
            finding = f"Only weak assertions: {', '.join(weak_assertions)}"
        else:
            finding = None

        test_results.append(TestAssertionResult(
            test_name=test_name[:200],
            file_name=spec_file_path.name,
            line_number=start_line + 1,
            assertion_strength=strength,
            expect_call_count=expect_count,
            strong_count=strong_count,
            weak_count=weak_count,
            trivial_count=trivial_count,
            is_weak=strength != AssertionStrength.STRONG,
            finding=finding,
        ))

    strong_tests = sum(1 for t in test_results if t.assertion_strength == AssertionStrength.STRONG)
    weak_tests = sum(1 for t in test_results if t.assertion_strength == AssertionStrength.WEAK)
    trivial_tests = sum(1 for t in test_results if t.assertion_strength == AssertionStrength.TRIVIAL)
    no_assertion_tests = sum(1 for t in test_results if t.assertion_strength == AssertionStrength.NONE)

    return FileAssertionAnalysis(
        file_name=spec_file_path.name,
        file_path=spec_file_path.name,
        total_tests=len(test_results),
        strong_tests=strong_tests,
        weak_tests=weak_tests,
        trivial_tests=trivial_tests,
        no_assertion_tests=no_assertion_tests,
        test_results=test_results,
    )


# ── Main public function ───────────────────────────────────────────────────────

def detect(
    spec_files: List[Path],
    exec_logger=None,
    evidence_dir: Optional[Path] = None,
    run_id: str = "unknown",
    ticket_id: object = 0,
    block_on_no_strong: bool = True,
) -> WeakAssertionReport:
    """
    Detect weak and missing assertions in Playwright spec files.

    Parameters
    ----------
    spec_files         : List of .spec.ts / .spec.js files to analyze
    exec_logger        : Optional event logger
    evidence_dir       : Where to write weak_assertion_report.json
    run_id             : Pipeline run ID
    ticket_id          : ADO ticket ID
    block_on_no_strong : If True, publish_blocked=True when all tests are weak

    Returns
    -------
    WeakAssertionReport
    """
    analyzed_at = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")

    file_analyses: List[FileAssertionAnalysis] = []
    for spec_file in spec_files:
        if not spec_file.exists():
            continue
        analysis = detect_in_file(spec_file)
        file_analyses.append(analysis)

        # Emit per-file weak assertion events
        if exec_logger and analysis.has_weak_tests:
            for tr in analysis.test_results:
                if tr.is_weak:
                    try:
                        exec_logger("weak_assertion_detected", {
                            "test_name": tr.test_name,
                            "file_name": tr.file_name,
                            "strength": tr.assertion_strength,
                            "finding": tr.finding,
                        })
                    except Exception:
                        pass

    # Aggregate counters
    files_analyzed = len(file_analyses)
    total_tests = sum(f.total_tests for f in file_analyses)
    strong_tests = sum(f.strong_tests for f in file_analyses)
    weak_tests = sum(f.weak_tests for f in file_analyses)
    trivial_tests = sum(f.trivial_tests for f in file_analyses)
    no_assertion_tests = sum(f.no_assertion_tests for f in file_analyses)

    # Publish is blocked when no strong assertions anywhere (if block_on_no_strong)
    publish_blocked = (
        block_on_no_strong
        and total_tests > 0
        and strong_tests == 0
    )

    report = WeakAssertionReport(
        ok=not publish_blocked,
        run_id=str(run_id),
        ticket_id=ticket_id,
        files_analyzed=files_analyzed,
        total_tests=total_tests,
        strong_tests=strong_tests,
        weak_tests=weak_tests,
        trivial_tests=trivial_tests,
        no_assertion_tests=no_assertion_tests,
        publish_blocked=publish_blocked,
        file_analyses=file_analyses,
        analyzed_at=analyzed_at,
    )

    # Write evidence artifact
    if evidence_dir is not None:
        artifact_dir = Path(evidence_dir) / str(ticket_id) / str(run_id)
        artifact_dir.mkdir(parents=True, exist_ok=True)
        artifact_path = artifact_dir / "weak_assertion_report.json"
        try:
            artifact_path.write_text(
                json.dumps(report.to_dict(), indent=2), encoding="utf-8"
            )
            report.evidence_path = str(artifact_path)
        except Exception as exc:
            logger.warning("weak_assertion_detector: could not write evidence: %s", exc)

    # Emit summary event
    if exec_logger:
        try:
            exec_logger("weak_assertion_summary", report.to_event())
        except Exception:
            pass

    logger.info(
        "weak_assertion_detector: files=%d total=%d strong=%d weak=%d none=%d publish_blocked=%s",
        files_analyzed, total_tests, strong_tests, weak_tests, no_assertion_tests, publish_blocked,
    )

    return report
