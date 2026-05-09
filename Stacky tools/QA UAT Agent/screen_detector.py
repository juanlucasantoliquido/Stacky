"""
screen_detector.py — Auditable screen detection for QA UAT pipeline.

Extracted from qa_uat_pipeline._extract_screens() as part of roadmap P0 /
Cambio 1.4 — so that every screen-detection decision is traceable, testable,
and never silently falls back to FrmAgenda.aspx for a child screen.

PUBLIC API
----------
    detect_screens(ticket_result) -> ScreenDetectionResult
    detect_screens_and_persist(ticket_result, evidence_dir, run_id) -> ScreenDetectionResult

The returned object contains:
    - selected_screens: list[str]   canonical screen filenames to test
    - matches: list[dict]           evidence per detected screen
    - fallback_used: bool           True when we returned the default fallback
    - ambiguous: bool               True when multiple screens have equal confidence
    - blocked: bool                 True when detection should block the pipeline
    - block_reason: str | None      "SCREEN_AMBIGUOUS" | "LOW_CONFIDENCE_SCREEN_DETECTION" | None
    - confidence: float             0.0–1.0 aggregate confidence
    - artifact_path: str | None     path to screen_detection.json artifact (set by persist)

BLOCKING RULES (roadmap Cambio 1.4)
------------------------------------
1. If multiple screens detected from reliable sources with confidence >= 0.7 → SCREEN_AMBIGUOUS
2. If no screen detected from any source and ticket has enough text to scan → LOW_CONFIDENCE_SCREEN_DETECTION
3. Fallback to FrmAgenda.aspx ONLY when the ticket itself explicitly mentions it.
   Never fall back silently for child-screen tickets.

SOURCES (priority order)
-------------------------
1. navigation_path field (freeform mode — explicit, most reliable)    confidence=1.0
2. analisis_tecnico field (technical analysis, explicit mentions)      confidence=0.95
3. plan_pruebas item texts (test plan — matches screen name directly)  confidence=0.85
4. ticket description / description_md                                 confidence=0.70
5. screen_aliases.yml keyword matching (heuristic)                    confidence=0.60

ARTIFACT (Sprint 2)
-------------------
detect_screens_and_persist() writes screen_detection.json to:
    evidence/<ticket_id>/<run_id>/screen_detection.json

This file is the auditable record of the detection decision for a specific run.
The execution.jsonl event screen_detection_result references this path via
the artifact_path field.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

_logger = logging.getLogger("stacky.qa_uat.screen_detector")

# ── Alias catalogue ───────────────────────────────────────────────────────────
# Loaded from screen_aliases.yml on first use.  Falls back to empty dict if
# the file is missing so the detector degrades gracefully.
_ALIASES_CACHE: Optional[dict] = None
_ALIASES_PATH = Path(__file__).parent / "screen_aliases.yml"


def _load_aliases() -> dict:
    """Load screen_aliases.yml once. Returns {screen: [alias, ...]} mapping."""
    global _ALIASES_CACHE  # noqa: PLW0603
    if _ALIASES_CACHE is not None:
        return _ALIASES_CACHE
    _ALIASES_CACHE = {}
    if not _ALIASES_PATH.is_file():
        _logger.debug("screen_aliases.yml not found at %s — alias matching disabled", _ALIASES_PATH)
        return _ALIASES_CACHE
    try:
        import yaml  # type: ignore[import]
        raw = yaml.safe_load(_ALIASES_PATH.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001
        _logger.warning("screen_aliases.yml load error: %s — alias matching disabled", exc)
        return _ALIASES_CACHE

    for screen, meta in raw.items():
        aliases = meta.get("aliases", []) if isinstance(meta, dict) else []
        if isinstance(aliases, list):
            _ALIASES_CACHE[screen] = [str(a).lower() for a in aliases]
    return _ALIASES_CACHE


# ── Result object ─────────────────────────────────────────────────────────────

@dataclass
class ScreenDetectionResult:
    """Immutable result of screen detection. Serialisable to dict for JSONL."""

    selected_screens: list = field(default_factory=list)
    matches: list = field(default_factory=list)
    fallback_used: bool = False
    ambiguous: bool = False
    blocked: bool = False
    block_reason: Optional[str] = None
    confidence: float = 0.0
    # Set by detect_screens_and_persist() after writing the artifact.
    artifact_path: Optional[str] = None

    def to_dict(self) -> dict:
        d = {
            "selected_screens": self.selected_screens,
            "matches": self.matches,
            "fallback_used": self.fallback_used,
            "ambiguous": self.ambiguous,
            "blocked": self.blocked,
            "block_reason": self.block_reason,
            "confidence": round(self.confidence, 4),
            "supported_screens_version": "screen_aliases.yml",
        }
        if self.artifact_path is not None:
            d["artifact_path"] = self.artifact_path
        return d


# ── Core detector ─────────────────────────────────────────────────────────────

def detect_screens(ticket_result: dict) -> ScreenDetectionResult:
    """
    Detect which screens are referenced in a ticket.

    Parameters
    ----------
    ticket_result : dict
        Output of uat_ticket_reader.run() — contains ticket, plan_pruebas,
        analisis_tecnico, navigation_path, description_md fields.

    Returns
    -------
    ScreenDetectionResult
        Structured result with evidence and blocking decision.
    """
    from agenda_screens import SUPPORTED_SCREENS

    # Screen → best match record for that screen
    best: dict[str, dict] = {}

    def _add(screen: str, source: str, match_type: str, confidence: float) -> None:
        """Register or upgrade a match for a screen."""
        existing = best.get(screen)
        if existing is None or confidence > existing["confidence"]:
            best[screen] = {
                "screen": screen,
                "source": source,
                "match_type": match_type,
                "confidence": confidence,
            }

    # ── Source 1: navigation_path (explicit, highest confidence) ─────────────
    for screen in ticket_result.get("navigation_path") or []:
        if screen in SUPPORTED_SCREENS:
            _add(screen, "navigation_path", "exact", 1.0)

    # ── Source 2: analisis_tecnico (explicit technical mention) ──────────────
    analisis = ticket_result.get("analisis_tecnico") or ""
    if analisis:
        lower_analisis = analisis.lower()
        for screen in SUPPORTED_SCREENS:
            if screen.lower() in lower_analisis:
                _add(screen, "analisis_tecnico", "exact", 0.95)

    # ── Source 3: plan_pruebas item texts ─────────────────────────────────────
    for item in ticket_result.get("plan_pruebas") or []:
        item_text = " ".join([
            item.get("title") or "",
            item.get("description") or "",
            item.get("descripcion") or "",
            item.get("datos") or "",
            item.get("esperado") or "",
        ]).lower()
        for screen in SUPPORTED_SCREENS:
            if screen.lower() in item_text:
                _add(screen, "plan_pruebas", "exact", 0.85)

    # ── Source 4: ticket description / description_md ────────────────────────
    desc_text = (
        ((ticket_result.get("ticket") or {}).get("description") or "")
        + " "
        + (ticket_result.get("description_md") or "")
    ).lower()
    if desc_text.strip():
        for screen in SUPPORTED_SCREENS:
            if screen.lower() in desc_text:
                _add(screen, "description", "exact", 0.70)

    # ── Source 5: alias keyword matching (screen_aliases.yml) ─────────────────
    aliases = _load_aliases()
    if aliases:
        # Aggregate all ticket text for alias scanning
        all_text = (
            analisis.lower()
            + " " + desc_text
            + " ".join(
                " ".join([
                    item.get("title") or "",
                    item.get("description") or "",
                    item.get("descripcion") or "",
                ]).lower()
                for item in ticket_result.get("plan_pruebas") or []
            )
        )
        for screen, screen_aliases in aliases.items():
            if screen not in SUPPORTED_SCREENS:
                continue
            for alias in screen_aliases:
                if alias and alias in all_text:
                    _add(screen, "screen_aliases.yml", "alias", 0.60)
                    break  # one alias match per screen is sufficient

    # ── Decision logic ────────────────────────────────────────────────────────

    if not best:
        # No screen detected from any source.
        # Check if the ticket has enough scannable text to justify blocking.
        total_text_chars = len(analisis) + len(desc_text) + sum(
            len(str(item)) for item in ticket_result.get("plan_pruebas") or []
        )
        if total_text_chars > 100:
            # Ticket has content but mentions no known screen → suspicious
            _logger.warning(
                "screen_detector: no known screen found in %d chars of ticket text — "
                "blocking with LOW_CONFIDENCE_SCREEN_DETECTION",
                total_text_chars,
            )
            return ScreenDetectionResult(
                selected_screens=[],
                matches=[],
                fallback_used=False,
                ambiguous=False,
                blocked=True,
                block_reason="LOW_CONFIDENCE_SCREEN_DETECTION",
                confidence=0.0,
            )
        # Very short ticket — fall back to FrmAgenda.aspx
        _logger.debug("screen_detector: empty ticket, using FrmAgenda.aspx fallback")
        return ScreenDetectionResult(
            selected_screens=["FrmAgenda.aspx"],
            matches=[],
            fallback_used=True,
            ambiguous=False,
            blocked=False,
            block_reason=None,
            confidence=0.0,
        )

    matches_list = sorted(best.values(), key=lambda m: -m["confidence"])
    top_confidence = matches_list[0]["confidence"]

    # High-confidence unique match → clean result
    if len(matches_list) == 1:
        screen = matches_list[0]["screen"]
        return ScreenDetectionResult(
            selected_screens=[screen],
            matches=matches_list,
            fallback_used=False,
            ambiguous=False,
            blocked=False,
            block_reason=None,
            confidence=top_confidence,
        )

    # Multiple screens found — check for ambiguity
    # Ambiguous: two or more screens with confidence >= 0.70 and within 0.15 of each other
    HIGH_CONF_THRESHOLD = 0.70
    AMBIGUITY_GAP = 0.15
    high_conf = [m for m in matches_list if m["confidence"] >= HIGH_CONF_THRESHOLD]

    if len(high_conf) >= 2:
        second_conf = high_conf[1]["confidence"]
        gap = top_confidence - second_conf
        if gap <= AMBIGUITY_GAP:
            _logger.warning(
                "screen_detector: ambiguous screen detection — top=%s (%.2f) vs second=%s (%.2f)",
                high_conf[0]["screen"], top_confidence,
                high_conf[1]["screen"], second_conf,
            )
            return ScreenDetectionResult(
                selected_screens=[m["screen"] for m in matches_list],
                matches=matches_list,
                fallback_used=False,
                ambiguous=True,
                blocked=True,
                block_reason="SCREEN_AMBIGUOUS",
                confidence=top_confidence,
            )

    # One clear winner (or multiple with large confidence gap) → return all sorted
    # but mark the highest-confidence one as primary (first in list)
    selected = sorted(best.keys())
    _logger.debug(
        "screen_detector: detected %d screen(s): %s (top confidence=%.2f)",
        len(selected), selected, top_confidence,
    )
    return ScreenDetectionResult(
        selected_screens=selected,
        matches=matches_list,
        fallback_used=False,
        ambiguous=False,
        blocked=False,
        block_reason=None,
        confidence=top_confidence,
    )


# ── Artifact persistence (Sprint 2) ──────────────────────────────────────────

def detect_screens_and_persist(
    ticket_result: dict,
    evidence_dir: Path,
    run_id: str,
) -> "ScreenDetectionResult":
    """Run detect_screens() and write screen_detection.json to evidence.

    The artifact is written to:
        evidence_dir / run_id / screen_detection.json

    The returned ScreenDetectionResult has artifact_path set to the absolute
    path of the written file (or None if write failed), so the caller can
    reference it in the execution.jsonl event.

    Parameters
    ----------
    ticket_result : dict
        Output of uat_ticket_reader.run().
    evidence_dir : Path
        Base evidence directory (e.g. evidence/<ticket_id>/).
    run_id : str
        Run identifier (e.g. ticket_id or freeform run_id).
    """
    result = detect_screens(ticket_result)

    artifact_dir = evidence_dir / str(run_id)
    artifact_path: Optional[str] = None
    try:
        artifact_dir.mkdir(parents=True, exist_ok=True)
        artifact_file = artifact_dir / "screen_detection.json"
        artifact_payload = {
            "schema_version": "screen_detection/1.0",
            "run_id": run_id,
            "selected_screens": result.selected_screens,
            "matches": result.matches,
            "fallback_used": result.fallback_used,
            "ambiguous": result.ambiguous,
            "blocked": result.blocked,
            "block_reason": result.block_reason,
            "confidence": round(result.confidence, 4),
            "supported_screens_version": "screen_aliases.yml",
        }
        artifact_file.write_text(
            json.dumps(artifact_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        artifact_path = str(artifact_file)
        _logger.debug("screen_detection.json written to %s", artifact_path)
    except Exception as exc:  # noqa: BLE001
        _logger.warning("screen_detector: could not write artifact: %s", exc)

    # Return a new result with artifact_path set (dataclass is mutable)
    result.artifact_path = artifact_path
    return result


__all__ = ["detect_screens", "detect_screens_and_persist", "ScreenDetectionResult"]
