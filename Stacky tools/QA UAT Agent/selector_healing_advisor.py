"""
selector_healing_advisor.py — Sprint 6.4: Assisted selector healing suggestions.

PURPOSE
-------
When a selector alias is missing or broken, this module suggests candidate
selectors from the UI map by similarity analysis.

CRITICAL INVARIANT
------------------
The `status` field of a SelectorHealingSuggestion is ALWAYS "suggested".
This module NEVER promotes a suggestion to "applied" — that requires explicit
human approval outside this module.

SIMILARITY STRATEGY
-------------------
Candidates are ranked by:
  1. Exact alias match (confidence=1.0)
  2. Label/text similarity to missing alias (cosine on word tokens)
  3. Same role/kind as expected
  4. Proximity by DOM position (if position data available in UI map)
  5. Fallback: first interactive element

VERSION
-------
1.0 — Sprint 6
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.qa_uat.selector_healing_advisor")

_MODULE_VERSION = "1.0"


# ── Dataclass ─────────────────────────────────────────────────────────────────

@dataclass
class SelectorHealingSuggestion:
    screen: str
    missing_alias: str
    candidate_alias: Optional[str]
    candidate_selector: Optional[str]
    confidence: float
    basis: list         # reasoning for the suggestion
    requires_human_approval: bool   # ALWAYS True — invariant
    status: str         # ALWAYS "suggested" — invariant


# ── Main function ─────────────────────────────────────────────────────────────

def suggest_selector_healing(
    screen: str,
    missing_alias: str,
    ui_map_path: str,
    execution_log: Optional[list] = None,
) -> SelectorHealingSuggestion:
    """
    Suggest a candidate selector for a missing or broken alias.

    Parameters
    ----------
    screen : str
        The .aspx screen name (e.g. "FrmDetalleClie.aspx").
    missing_alias : str
        The alias that was not found in the UI map.
    ui_map_path : str
        Path to the UI map JSON file for the screen.
    execution_log : list | None
        Events from execution.jsonl (used for additional context).

    Returns
    -------
    SelectorHealingSuggestion
        Always has status="suggested" and requires_human_approval=True.
    """
    # Load UI map
    elements = _load_ui_map_elements(ui_map_path)

    if not elements:
        return SelectorHealingSuggestion(
            screen=screen,
            missing_alias=missing_alias,
            candidate_alias=None,
            candidate_selector=None,
            confidence=0.0,
            basis=["ui_map_not_found_or_empty"],
            requires_human_approval=True,
            status="suggested",
        )

    # ── Scoring pipeline ──────────────────────────────────────────────────────
    scored: list[tuple[float, dict, list]] = []  # (score, element, basis_list)

    for el in elements:
        if el.get("is_decorative", False):
            continue  # skip decorative elements

        el_alias = el.get("alias_semantic", "")
        el_label = el.get("label", "") or el.get("text", "") or ""
        el_role  = el.get("role", "") or el.get("kind", "")

        score, basis = _score_element(
            missing_alias=missing_alias,
            el_alias=el_alias,
            el_label=el_label,
            el_role=el_role,
            el=el,
        )
        if score > 0:
            scored.append((score, el, basis))

    if not scored:
        # No candidates found — return None with low confidence
        return SelectorHealingSuggestion(
            screen=screen,
            missing_alias=missing_alias,
            candidate_alias=None,
            candidate_selector=None,
            confidence=0.0,
            basis=["no_candidate_found_in_ui_map"],
            requires_human_approval=True,
            status="suggested",
        )

    # Sort by score descending; ties broken by alias alphabetically
    scored.sort(key=lambda t: (-t[0], t[1].get("alias_semantic", "")))
    best_score, best_el, best_basis = scored[0]

    candidate_alias    = best_el.get("alias_semantic", "")
    candidate_selector = best_el.get("selector_recommended") or best_el.get("selector", "")

    # Clamp confidence to [0, 1]
    confidence = min(1.0, max(0.0, best_score))

    # ── INVARIANT ENFORCEMENT ─────────────────────────────────────────────────
    # status is ALWAYS "suggested" — never "applied", never "approved"
    return SelectorHealingSuggestion(
        screen=screen,
        missing_alias=missing_alias,
        candidate_alias=candidate_alias,
        candidate_selector=candidate_selector,
        confidence=confidence,
        basis=best_basis,
        requires_human_approval=True,   # invariant: always True
        status="suggested",             # invariant: always "suggested"
    )


# ── Scoring helpers ────────────────────────────────────────────────────────────

def _score_element(
    missing_alias: str,
    el_alias: str,
    el_label: str,
    el_role: str,
    el: dict,
) -> tuple[float, list]:
    """
    Score a UI map element as a healing candidate for missing_alias.
    Returns (score [0.0, 1.0], basis_list).
    """
    score = 0.0
    basis: list[str] = []

    # Normalize inputs
    ma_lower  = missing_alias.lower()
    al_lower  = el_alias.lower()
    lab_lower = el_label.lower()

    # ── Rule 1: Exact alias match (score 1.0) ─────────────────────────────────
    if al_lower == ma_lower:
        return 1.0, ["exact_alias_match"]

    # ── Rule 2: Alias substring / prefix match ────────────────────────────────
    ma_tokens = _tokenize(missing_alias)
    al_tokens = _tokenize(el_alias)
    lab_tokens = _tokenize(el_label)

    alias_similarity = _jaccard_similarity(ma_tokens, al_tokens)
    if alias_similarity > 0:
        score += alias_similarity * 0.6
        basis.append(f"alias_similarity={alias_similarity:.2f}")

    # ── Rule 3: Label / text similarity ──────────────────────────────────────
    label_similarity = _jaccard_similarity(ma_tokens, lab_tokens)
    if label_similarity > 0:
        score += label_similarity * 0.3
        basis.append(f"label_similarity={label_similarity:.2f}")

    # ── Rule 4: Role/kind matching ────────────────────────────────────────────
    expected_role = _infer_expected_role(missing_alias)
    if expected_role and expected_role.lower() in el_role.lower():
        score += 0.1
        basis.append(f"role={el_role}")

    # ── Rule 5: near_text match (alias contains label words) ─────────────────
    if lab_lower and any(w in ma_lower for w in lab_lower.split() if len(w) > 2):
        score += 0.1
        basis.append(f"near_text_{el_label[:20]!r}")

    if score <= 0:
        return 0.0, []

    return min(1.0, score), basis


def _tokenize(text: str) -> set:
    """Split a CamelCase or underscore_case alias into lowercase word tokens."""
    if not text:
        return set()
    # Split camelCase
    text = re.sub(r'([A-Z])', r' \1', text)
    # Split on non-alphanumeric
    tokens = re.split(r'[^a-zA-Z0-9]+', text.lower())
    return {t for t in tokens if len(t) > 1}


def _jaccard_similarity(a: set, b: set) -> float:
    """Compute Jaccard similarity between two token sets."""
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    if union == 0:
        return 0.0
    return inter / union


def _infer_expected_role(alias: str) -> Optional[str]:
    """Infer expected element role from naming conventions."""
    lower = alias.lower()
    if lower.startswith("ddl") or lower.startswith("cmb") or lower.startswith("drp"):
        return "combobox"
    if lower.startswith("txt") or lower.startswith("inp") or lower.startswith("fld"):
        return "textbox"
    if lower.startswith("btn") or lower.startswith("cmd"):
        return "button"
    if lower.startswith("chk"):
        return "checkbox"
    if lower.startswith("rad"):
        return "radio"
    if lower.startswith("grd") or lower.startswith("grid"):
        return "grid"
    if lower.startswith("lnk") or lower.startswith("lbl"):
        return "link"
    return None


# ── UI map loader ─────────────────────────────────────────────────────────────

def _load_ui_map_elements(ui_map_path: str) -> list:
    """Load elements from a UI map JSON file."""
    try:
        p = Path(ui_map_path)
        if not p.is_file():
            logger.debug("selector_healing_advisor: UI map not found: %s", ui_map_path)
            return []
        data = json.loads(p.read_text(encoding="utf-8"))
        # Support both direct elements list and ui_map/1.1 schema
        elements = data.get("elements") or []
        if isinstance(elements, list):
            return elements
        return []
    except Exception as exc:
        logger.debug("selector_healing_advisor: could not load UI map %s: %s", ui_map_path, exc)
        return []


# ── Event builder ─────────────────────────────────────────────────────────────

def build_healing_suggestion_event(suggestion: SelectorHealingSuggestion) -> dict:
    """
    Build a selector_healing_suggestion event dict for emission to execution.jsonl.

    The event always has status="suggested" — invariant enforced here.
    """
    return {
        "event": "selector_healing_suggestion",
        "screen": suggestion.screen,
        "missing_alias": suggestion.missing_alias,
        "candidate_alias": suggestion.candidate_alias,
        "candidate_selector": suggestion.candidate_selector,
        "confidence": round(suggestion.confidence, 4),
        "basis": suggestion.basis,
        "requires_human_approval": True,   # invariant
        "status": "suggested",             # invariant
    }


def emit_healing_suggestion(exec_logger, suggestion: SelectorHealingSuggestion) -> None:
    """Emit selector_healing_suggestion event to execution.jsonl."""
    try:
        payload = build_healing_suggestion_event(suggestion)
        exec_logger.event("selector_healing_suggestion", payload)
    except Exception as exc:  # noqa: BLE001
        logger.debug(
            "selector_healing_advisor: could not emit healing suggestion event: %s", exc
        )
