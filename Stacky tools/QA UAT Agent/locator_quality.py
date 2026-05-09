"""locator_quality.py — Sprint 7: Locator quality scoring for UI map entries.

Scores each UI map alias by how robust/stable its locator strategy is.

Preferred strategies (highest score -> lowest):
  getByRole (1.0) > getByLabel (0.95) > getByTestId (0.90) >
  css_stable (0.75) > xpath (0.40) > css_position (0.30) > absolute_xpath (0.20)

Penalties applied per alias:
  hard_wait  (page.waitForTimeout): -0.30
  dynamic_text (${...} in selector): -0.15
  generated_id (ID with 3+ trailing digits): -0.10

Robustness:
  score >= 0.80 -> high
  score >= 0.60 -> medium
  score <  0.60 -> low

Usage:
  from locator_quality import score_alias, score_ui_map

  # Single alias
  entry = {"alias": "cmbProvincia", "selector": "#cmbProvincia"}
  ls = score_alias(entry)
  print(ls.score, ls.robustness)

  # Full UI map
  report = score_ui_map(ui_map_data, evidence_dir=Path("evidence/122/run-1"))
  # -> writes locator_quality_report.json
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import List, Optional

_TOOL_VERSION = "1.0.0"
_REPORT_SCHEMA = "locator-quality-report/1.0"

# ── Strategy base scores ──────────────────────────────────────────────────────

_STRATEGY_SCORES: dict[str, float] = {
    "role":           1.00,
    "label":          0.95,
    "testid":         0.90,
    "css_stable":     0.75,
    "xpath":          0.40,
    "css_position":   0.30,
    "absolute_xpath": 0.20,
    "unknown":        0.50,
}

# ── Detector patterns ─────────────────────────────────────────────────────────

_RE_GET_BY_ROLE    = re.compile(r"getByRole\s*\(", re.IGNORECASE)
_RE_GET_BY_LABEL   = re.compile(r"getByLabel\s*\(", re.IGNORECASE)
_RE_GET_BY_TESTID  = re.compile(r"getByTestId\s*\(|data-testid", re.IGNORECASE)
_RE_ABSOLUTE_XPATH = re.compile(r"^//|^\(/")
_RE_XPATH_FRAGMENT = re.compile(r"[@\[]|/\w")       # @ attr, [x], /tag
_RE_CSS_POSITION   = re.compile(
    r":nth-child\s*\(|:nth-of-type\s*\(|:eq\s*\(|:first-child|:last-child",
    re.IGNORECASE,
)
_RE_HARD_WAIT      = re.compile(r"waitForTimeout\s*\(|page\.wait\s*\(", re.IGNORECASE)
_RE_DYNAMIC_TEXT   = re.compile(r"\$\{|#\{|\{\{")   # ${x}, #{x}, {{x}}
_RE_GENERATED_ID   = re.compile(r"[#\.]\w*\d{3,}")  # e.g. #ctl00_btn1234

# ── Data classes ──────────────────────────────────────────────────────────────


@dataclass
class LocatorScore:
    """Score for a single locator alias."""

    alias: str
    selector: str
    locator_strategy: str
    score: float
    robustness: str            # high | medium | low
    warnings: List[str] = field(default_factory=list)
    penalties: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class LocatorQualityReport:
    """Aggregated quality report for all aliases in a UI map."""

    screen: str
    schema_version: str
    tool_version: str
    total_aliases: int
    high_count: int
    medium_count: int
    low_count: int
    avg_score: float
    items: List[LocatorScore]
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "tool_version":   self.tool_version,
            "screen":         self.screen,
            "total_aliases":  self.total_aliases,
            "high_count":     self.high_count,
            "medium_count":   self.medium_count,
            "low_count":      self.low_count,
            "avg_score":      self.avg_score,
            "warnings":       self.warnings,
            "items":          [i.to_dict() for i in self.items],
        }


# ── Public API ────────────────────────────────────────────────────────────────


def score_alias(alias_entry: dict) -> LocatorScore:
    """Score a single UI map alias entry.

    Parameters
    ----------
    alias_entry : dict
        UI map alias with at minimum {"alias": ..., "selector": ...}.
        May include "locator_strategy" to override auto-detection.

    Returns
    -------
    LocatorScore
    """
    alias    = alias_entry.get("alias", "")
    selector = alias_entry.get("selector", "")
    strategy = alias_entry.get("locator_strategy", "")

    # Auto-detect strategy if not provided
    if not strategy:
        strategy = _detect_strategy(selector)

    base_score = _STRATEGY_SCORES.get(strategy, _STRATEGY_SCORES["unknown"])

    warnings: list[str] = list(alias_entry.get("warnings") or [])
    penalties: list[str] = []
    penalty = 0.0

    # ── Penalties ─────────────────────────────────────────────────────────────
    if _RE_HARD_WAIT.search(selector):
        penalty += 0.30
        penalties.append("hard_wait")
        warnings.append(
            "Hard wait detected — use expect() or waitFor() instead of waitForTimeout"
        )

    if _RE_DYNAMIC_TEXT.search(selector):
        penalty += 0.15
        penalties.append("dynamic_text")
        warnings.append(
            "Dynamic text interpolation in selector — prefer stable identifiers"
        )

    if _RE_GENERATED_ID.search(selector):
        penalty += 0.10
        penalties.append("generated_id")
        warnings.append(
            "Possible generated ID — brittle to server-side ID generation (ASP.NET ClientID)"
        )

    # ── Strategy-specific warnings ─────────────────────────────────────────────
    if strategy == "absolute_xpath":
        warnings.append(
            "Absolute XPath is fragile — brittle to any DOM structure change"
        )
    elif strategy == "xpath":
        warnings.append(
            "XPath selector detected — prefer getByRole or getByLabel"
        )
    elif strategy == "css_position":
        warnings.append(
            "Position-based CSS selector is brittle — fragile to DOM reorder"
        )

    score = round(max(0.0, min(1.0, base_score - penalty)), 4)
    robustness = _compute_robustness(score)

    if robustness == "low":
        warnings.append(
            "Locator quality LOW — prefer getByRole, getByLabel or data-testid"
        )

    return LocatorScore(
        alias=alias,
        selector=selector,
        locator_strategy=strategy,
        score=score,
        robustness=robustness,
        warnings=warnings,
        penalties=penalties,
    )


def score_ui_map(
    ui_map_data: dict,
    evidence_dir: Optional[Path] = None,
    *,
    write_report: bool = True,
) -> LocatorQualityReport:
    """Score all locators in a UI map and optionally write the report.

    Parameters
    ----------
    ui_map_data : dict
        Parsed UI map JSON. Expected keys: "screen", "aliases" (list of alias dicts).
    evidence_dir : Path | None
        If set (and write_report=True), writes locator_quality_report.json here.
    write_report : bool
        Write the report JSON file to evidence_dir (default True).

    Returns
    -------
    LocatorQualityReport
    """
    screen      = ui_map_data.get("screen", "unknown")
    aliases_raw = ui_map_data.get("aliases") or []

    items: list[LocatorScore] = []
    for entry in aliases_raw:
        if isinstance(entry, dict):
            items.append(score_alias(entry))

    total  = len(items)
    high   = sum(1 for i in items if i.robustness == "high")
    medium = sum(1 for i in items if i.robustness == "medium")
    low    = sum(1 for i in items if i.robustness == "low")
    avg    = round(sum(i.score for i in items) / total, 4) if total else 0.0

    global_warnings: list[str] = []
    if total == 0:
        global_warnings.append("No aliases found in UI map — cannot score locators")
    elif low > 0:
        global_warnings.append(f"{low} low-quality locator(s) require attention")

    report = LocatorQualityReport(
        screen=screen,
        schema_version=_REPORT_SCHEMA,
        tool_version=_TOOL_VERSION,
        total_aliases=total,
        high_count=high,
        medium_count=medium,
        low_count=low,
        avg_score=avg,
        items=items,
        warnings=global_warnings,
    )

    if write_report and evidence_dir is not None:
        evidence_dir = Path(evidence_dir)
        evidence_dir.mkdir(parents=True, exist_ok=True)
        out = evidence_dir / "locator_quality_report.json"
        out.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    return report


# ── Internal helpers ───────────────────────────────────────────────────────────


def _detect_strategy(selector: str) -> str:
    """Infer locator strategy from selector string."""
    if not selector:
        return "unknown"
    if _RE_GET_BY_ROLE.search(selector):
        return "role"
    if _RE_GET_BY_LABEL.search(selector):
        return "label"
    if _RE_GET_BY_TESTID.search(selector):
        return "testid"
    if _RE_ABSOLUTE_XPATH.match(selector):
        return "absolute_xpath"
    if _RE_XPATH_FRAGMENT.search(selector):
        return "xpath"
    if _RE_CSS_POSITION.search(selector):
        return "css_position"
    return "css_stable"


def _compute_robustness(score: float) -> str:
    if score >= 0.80:
        return "high"
    if score >= 0.60:
        return "medium"
    return "low"
