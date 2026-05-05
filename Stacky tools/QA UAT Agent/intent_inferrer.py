"""
intent_inferrer.py — Inverse navigation→goal_action mapper (Fase 7).

Given a navigation_path[] observed during a QA run or a recorded session,
uses a lightweight LLM call to infer the most likely ``goal_action`` label
from the GOAL_ACTION_TARGETS vocabulary.

Design from ROADMAP.md (Fase 7).  Companion to:
  * navigation_graph.py        (source of GOAL_ACTION_TARGETS vocabulary)
  * intent_parser.py           (calls this as a fallback when goal_action absent)
  * session_recorder.py        (calls this post-recording to annotate session.json)

WHY THIS EXISTS
  The orchestrator agent writes intent_spec.json with a ``goal_action`` when the
  operator's request is unambiguous.  But two situations break that:
    1. A recorded session from session_recorder.py was produced without --goal.
    2. The operator wrote something ambiguous and the LLM couldn't pick a label.
  In both cases ``navigation_path`` is already known.  This module inverts the
  mapping: given the path, guess the label.

CONFIDENCE
  ``InferResult.confidence`` is the inferrer's own confidence, unrelated to the
  Fase-6 edge confidence:
    "high"    — LLM returned a label that exactly matches GOAL_ACTION_TARGETS.
    "low"     — LLM returned a close match after lowercase/strip normalisation.
    "unknown" — LLM returned "unknown" or the response could not be matched.
  Callers should treat "low" as a suggestion requiring human confirmation and
  "unknown" as a non-result (skip, don't override existing state).

PUBLIC API
  infer_goal_from_path(nav_path: list[str]) -> InferResult
  infer_from_session_file(session_file: Path) -> InferResult   # convenience

CLI
  python intent_inferrer.py --path "FrmLogin.aspx,FrmBusqueda.aspx,FrmDetalleClie.aspx,PopUpCompromisos.aspx"
  python intent_inferrer.py --session evidence/recordings/20260505_123456/session.json
  python intent_inferrer.py --session evidence/recordings/latest.txt
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.qa_uat.intent_inferrer")

_TOOL_VERSION = "1.0.0"
_TOOL_ROOT = Path(__file__).resolve().parent

# Lightweight model — fast + cheap; inference prompt is short.
_MODEL = "gpt-4.1-mini"
# Absolute cap on LLM output tokens; we only need a single label word.
_MAX_TOKENS = 32
# Minimum number of distinct screens in the path before we attempt inference.
# A 1-screen path (just FrmLogin.aspx) is too short to infer anything useful.
_MIN_PATH_LENGTH = 2


@dataclass
class InferResult:
    """Output of a goal_action inference request."""
    ok: bool
    goal_action: str        # matched label from GOAL_ACTION_TARGETS, or ""
    confidence: str         # "high" | "low" | "unknown"
    raw_response: str       # LLM text as-returned (for debugging)
    model: str              # model ID used
    duration_ms: int
    error: str = ""         # non-empty only when ok=False

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "goal_action": self.goal_action,
            "confidence": self.confidence,
            "raw_response": self.raw_response,
            "model": self.model,
            "duration_ms": self.duration_ms,
            "error": self.error,
        }


# ── Prompt construction ───────────────────────────────────────────────────────

def _build_vocabulary() -> list[str]:
    """Return the deduplicated sorted list of known goal_action labels."""
    try:
        from navigation_graph import GOAL_ACTION_TARGETS
        return sorted(set(GOAL_ACTION_TARGETS.keys()))
    except ImportError:
        logger.warning("intent_inferrer: navigation_graph unavailable — empty vocabulary")
        return []


def _build_system_prompt(vocabulary: list[str]) -> str:
    labels = "\n".join(f"  {label}" for label in vocabulary)
    return (
        "You are a navigation intent classifier for the Agenda Web application "
        "(RS Pacífico debt collection platform).\n\n"
        "Given a sequence of screens the operator navigated through, output the "
        "SINGLE best-matching goal_action label from the vocabulary below.\n\n"
        "Rules:\n"
        "  - Respond with ONLY the exact label. No explanation. No punctuation.\n"
        "  - If no label fits the path, respond with the single word: unknown\n"
        "  - Do NOT invent labels outside the vocabulary.\n\n"
        "Valid goal_action labels:\n"
        f"{labels}"
    )


def _build_user_prompt(nav_path: list[str]) -> str:
    path_str = " → ".join(nav_path)
    return (
        f"Navigation path: {path_str}\n\n"
        "Respond with ONLY the goal_action label."
    )


# ── Label matching ────────────────────────────────────────────────────────────

def _match_label(raw: str, vocabulary: list[str]) -> tuple[str, str]:
    """Try to match the LLM's raw text to a vocabulary entry.

    Returns (goal_action, confidence):
      - Exact match   → ("some_label", "high")
      - Normalised    → ("some_label", "low")    (strip/lower/replace spaces→_)
      - "unknown"     → ("", "unknown")
      - No match      → ("", "unknown")
    """
    cleaned = (raw or "").strip().strip('"\'.,;').strip()

    if not cleaned:
        return ("", "unknown")

    if cleaned.lower() == "unknown":
        return ("", "unknown")

    # Exact match
    if cleaned in vocabulary:
        return (cleaned, "high")

    # Case-insensitive + normalise spaces/dashes
    normalised = cleaned.lower().replace(" ", "_").replace("-", "_")
    for label in vocabulary:
        if label.lower() == normalised:
            return (label, "low")

    # Prefix match: sometimes the model writes the label + trailing garbage
    for label in vocabulary:
        if normalised.startswith(label.lower()) or label.lower().startswith(normalised):
            return (label, "low")

    return ("", "unknown")


# ── Public API ────────────────────────────────────────────────────────────────

def infer_goal_from_path(nav_path: list[str]) -> InferResult:
    """Infer the most likely goal_action from a navigation_path.

    Args:
        nav_path: Ordered list of screen filenames, e.g.
                  ["FrmLogin.aspx", "FrmBusqueda.aspx", "FrmDetalleClie.aspx",
                   "PopUpCompromisos.aspx"].

    Returns:
        InferResult.  ``ok=True`` even when ``confidence="unknown"`` —
        the caller decides whether to use the suggestion.
        ``ok=False`` only when the LLM call itself failed.
    """
    started = time.time()

    # Dedupe the path preserving order (a screen repeated is noise)
    seen: set[str] = set()
    deduped_path: list[str] = []
    for screen in (nav_path or []):
        if screen not in seen:
            seen.add(screen)
            deduped_path.append(screen)

    if len(deduped_path) < _MIN_PATH_LENGTH:
        elapsed = int((time.time() - started) * 1000)
        return InferResult(
            ok=True,
            goal_action="",
            confidence="unknown",
            raw_response="",
            model="",
            duration_ms=elapsed,
            error=f"Path too short ({len(deduped_path)} unique screens, min {_MIN_PATH_LENGTH})",
        )

    vocabulary = _build_vocabulary()
    if not vocabulary:
        elapsed = int((time.time() - started) * 1000)
        return InferResult(
            ok=False,
            goal_action="",
            confidence="unknown",
            raw_response="",
            model="",
            duration_ms=elapsed,
            error="GOAL_ACTION_TARGETS vocabulary is empty (navigation_graph not importable)",
        )

    system_prompt = _build_system_prompt(vocabulary)
    user_prompt = _build_user_prompt(deduped_path)

    try:
        from llm_client import call_llm, LLMError
    except ImportError as exc:
        elapsed = int((time.time() - started) * 1000)
        return InferResult(
            ok=False,
            goal_action="",
            confidence="unknown",
            raw_response="",
            model="",
            duration_ms=elapsed,
            error=f"llm_client not importable: {exc}",
        )

    try:
        llm_result = call_llm(
            model=_MODEL,
            system=system_prompt,
            user=user_prompt,
            max_tokens=_MAX_TOKENS,
        )
    except Exception as exc:
        elapsed = int((time.time() - started) * 1000)
        logger.warning("intent_inferrer: LLM call failed: %s", exc)
        return InferResult(
            ok=False,
            goal_action="",
            confidence="unknown",
            raw_response="",
            model=_MODEL,
            duration_ms=elapsed,
            error=str(exc),
        )

    raw_text = llm_result.get("text") or ""
    model_used = llm_result.get("model") or _MODEL
    goal_action, confidence = _match_label(raw_text, vocabulary)

    elapsed = int((time.time() - started) * 1000)
    logger.info(
        "intent_inferrer: path=%s → %r (conf=%s, model=%s, %dms)",
        deduped_path, goal_action, confidence, model_used, elapsed,
    )

    return InferResult(
        ok=True,
        goal_action=goal_action,
        confidence=confidence,
        raw_response=raw_text,
        model=model_used,
        duration_ms=elapsed,
    )


def infer_from_session_file(session_file: Path) -> InferResult:
    """Convenience wrapper: read navigation_path from session.json and infer.

    Args:
        session_file: Path to a session.json produced by session_recorder.py.
                      May also be the parent directory — will look for
                      session.json inside.

    Returns:
        InferResult (same semantics as infer_goal_from_path).
    """
    if session_file.is_dir():
        session_file = session_file / "session.json"

    if not session_file.is_file():
        return InferResult(
            ok=False,
            goal_action="",
            confidence="unknown",
            raw_response="",
            model="",
            duration_ms=0,
            error=f"session.json not found: {session_file}",
        )

    try:
        data = json.loads(session_file.read_text(encoding="utf-8"))
    except Exception as exc:
        return InferResult(
            ok=False,
            goal_action="",
            confidence="unknown",
            raw_response="",
            model="",
            duration_ms=0,
            error=f"Cannot parse {session_file}: {exc}",
        )

    nav_path = data.get("navigation_path") or []
    if not nav_path:
        return InferResult(
            ok=True,
            goal_action="",
            confidence="unknown",
            raw_response="",
            model="",
            duration_ms=0,
            error="navigation_path is empty in session.json",
        )

    return infer_goal_from_path(nav_path)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    args = _parse_args()
    logging.basicConfig(
        level=logging.WARNING if args.background else logging.INFO,
        stream=sys.stderr,
        format="%(levelname)s %(name)s: %(message)s",
    )

    if args.path:
        nav_path = [s.strip() for s in args.path.split(",") if s.strip()]
        result = infer_goal_from_path(nav_path)
    elif args.session:
        session_path = Path(args.session)
        # Support "latest.txt" pointer written by session_recorder on Windows
        if session_path.name == "latest" and not session_path.exists():
            pointer = session_path.parent / "latest.txt"
            if pointer.is_file():
                session_path = Path(pointer.read_text(encoding="utf-8").strip())
        result = infer_from_session_file(session_path)
    else:
        sys.stderr.write("error: --path or --session required\n")
        sys.exit(1)

    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    sys.exit(0 if result.ok else 1)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Infer goal_action from a navigation path (Fase 7 — Intent Inference). "
            "Uses a lightweight LLM to map the sequence of screens to a known "
            "goal_action label from GOAL_ACTION_TARGETS."
        )
    )
    source = p.add_mutually_exclusive_group()
    source.add_argument(
        "--path",
        default=None,
        help=(
            "Comma-separated list of screen filenames, e.g. "
            "'FrmLogin.aspx,FrmBusqueda.aspx,FrmDetalleClie.aspx,PopUpCompromisos.aspx'"
        ),
    )
    source.add_argument(
        "--session",
        default=None,
        help=(
            "Path to a session.json file (or its parent directory) produced by "
            "session_recorder.py. navigation_path will be extracted from it."
        ),
    )
    p.add_argument(
        "--background",
        action="store_true",
        help="Suppress INFO log output (JSON only on stdout).",
    )
    return p.parse_args()


if __name__ == "__main__":
    main()
