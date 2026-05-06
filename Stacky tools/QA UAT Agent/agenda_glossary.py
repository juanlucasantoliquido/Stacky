"""
agenda_glossary.py — Loader and view-builder for the Agenda domain glossary.

Centralises Spanish/business vocabulary (lote, póliza, corredor, débito
automático, …) previously hardcoded inside `uat_scenario_compiler` so that:
  - the scenario compiler post-processor (`_postprocess_compiled_spec`) reads
    the same filter keyword list from one place,
  - the LLM system prompt receives a curated domain glossary block, allowing
    the model to recognise non-trivial terms (RUC, débito automático, lote)
    even when the user phrases the test step in shorthand.

DATA SOURCE: `data/agenda_glossary.json` — versioned alongside this file.

PUBLIC API (stable):
  - `load_glossary(path=None) -> dict`: parsed glossary (cached after first
    call). Pass `path` only in tests to override the bundled file.
  - `glossary_for_screen(screen) -> dict`: per-screen view with
    {label, purpose, filter_keywords, filter_input_aliases,
     filter_action_button, common_misroutes, domain_terms}. The
    `domain_terms` list is filtered by `applies_to_screens`.
  - `domain_terms_for_prompt(screen=None) -> str`: Markdown-ish text block
    suitable for injection into an LLM system prompt. Capped at ~4000
    chars so it never blows the context budget.

DESIGN NOTES:
  - All matching is case-insensitive; consumers MUST lowercase input first.
  - `filter_keywords` is the merged set across the screen entry + domain
    terms tagged for that screen; this matches the legacy hardcoded list
    while expanding it through the structured catalogue.
  - Empty/missing screens return a benign empty view (no exception) so
    callers can chain `.get("filter_keywords") or default`.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.qa_uat.agenda_glossary")

_DEFAULT_PATH = Path(__file__).resolve().parent / "data" / "agenda_glossary.json"

# Hard cap on the prompt text returned by `domain_terms_for_prompt`. The QA
# UAT compiler ships ~600 tokens of system prompt before the glossary; 4000
# extra chars (~1000 tokens) keeps total well under the gpt-4o-mini context
# budget while leaving room for ui_elements hints + user prompt.
_PROMPT_CHAR_BUDGET = 4000


# Module-level cache keyed by absolute path. Tests pass a custom `path` to
# force a fresh load; production code calls with no args and reuses the cached
# parse to avoid re-reading the JSON file on every scenario.
_CACHE: "dict[str, dict]" = {}


# ── Public API ────────────────────────────────────────────────────────────────

def load_glossary(path: Optional[Path] = None) -> dict:
    """Return the parsed glossary JSON, loading and caching on first access.

    On parse / IO failure logs a warning and returns an empty-but-valid
    skeleton so downstream consumers can keep working with reduced
    functionality (the post-processor falls back to an empty keyword list,
    etc). This is intentional — a corrupt glossary must NEVER block the
    pipeline.
    """
    target = (path or _DEFAULT_PATH).resolve()
    key = str(target)
    if key in _CACHE:
        return _CACHE[key]

    try:
        data = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("glossary root must be a JSON object")
        _CACHE[key] = data
        return data
    except FileNotFoundError:
        logger.warning("Glossary file not found at %s — using empty fallback", target)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("Glossary parse error at %s: %s — using empty fallback", target, exc)
    except OSError as exc:
        logger.warning("Glossary IO error at %s: %s — using empty fallback", target, exc)

    fallback = {"schema_version": "glossary/1.0", "screens": {}, "domain_terms": []}
    _CACHE[key] = fallback
    return fallback


def glossary_for_screen(screen: str, path: Optional[Path] = None) -> dict:
    """Return a flat view of glossary entries relevant to `screen`.

    Output shape:
      {
        "screen": "FrmAgenda.aspx",
        "label": "Agenda Personal",
        "purpose": "...",
        "filter_keywords": [...],          # merged: screen entry + domain terms
        "filter_input_aliases": [...],     # screen-only (LLM target whitelist)
        "filter_action_button": "link_c_btnok" | None,
        "common_misroutes": {alias_wrong: alias_correct},
        "domain_terms": [{term, aliases, description}, ...]
      }

    Empty fields when the screen is not catalogued; never raises.
    """
    data = load_glossary(path)
    screens = data.get("screens") or {}
    entry = screens.get(screen) or {}

    # Filter domain terms by applies_to_screens (case-sensitive on screen
    # filename — the JSON is the source of truth).
    domain_terms = []
    for term in (data.get("domain_terms") or []):
        applies = term.get("applies_to_screens") or []
        if not isinstance(applies, list):
            continue
        if screen in applies:
            domain_terms.append({
                "term": term.get("term", ""),
                "aliases": term.get("aliases") or [],
                "description": term.get("description", ""),
            })

    # Merge filter_keywords from screen entry + domain term aliases. We
    # lowercase + dedupe + sort to give the post-processor a stable
    # comparable list.
    base_keywords = entry.get("filter_keywords") or []
    merged: "set[str]" = {str(k).lower() for k in base_keywords if k}
    for term in domain_terms:
        merged.add(str(term["term"]).lower())
        for alias in term["aliases"]:
            if alias:
                merged.add(str(alias).lower())

    return {
        "screen": screen,
        "label": entry.get("label", ""),
        "purpose": entry.get("purpose", ""),
        "filter_keywords": sorted(merged),
        "filter_input_aliases": list(entry.get("filter_input_aliases") or []),
        "filter_action_button": entry.get("filter_action_button"),
        "common_misroutes": dict(entry.get("common_misroutes") or {}),
        "domain_terms": domain_terms,
    }


def domain_terms_for_prompt(
    screen: Optional[str] = None,
    path: Optional[Path] = None,
    char_budget: int = _PROMPT_CHAR_BUDGET,
) -> str:
    """Render a domain glossary block ready to embed in an LLM system prompt.

    When `screen` is provided, only terms tagged for that screen are emitted.
    When `screen` is None, returns the full catalogue (used by tools that
    don't know which screen the LLM will pick).

    Output format (Markdown-ish, easy for the LLM to parse):

        DOMAIN GLOSSARY (Agenda Personal):
        - lote: Conjunto de pólizas agrupadas para procesamiento.
          aliases: lotes
        - corredor: Intermediario comercial. Filtro en Agenda Personal.
        ...

    The text is capped at `char_budget` chars; if the catalogue exceeds the
    budget it is truncated at a term boundary and a marker line is appended.
    Returns an empty string when the glossary is empty or load failed (so the
    caller can `f"...{domain_terms_for_prompt(...)}..."` without checks).
    """
    data = load_glossary(path)
    domain_terms = data.get("domain_terms") or []
    if not domain_terms:
        return ""

    if screen:
        domain_terms = [
            t for t in domain_terms
            if isinstance(t.get("applies_to_screens"), list)
            and screen in t["applies_to_screens"]
        ]
    if not domain_terms:
        return ""

    screens = data.get("screens") or {}
    label = (screens.get(screen) or {}).get("label", "") if screen else "Agenda Web"
    header = f"DOMAIN GLOSSARY ({label}):" if label else "DOMAIN GLOSSARY:"

    lines: "list[str]" = [header]
    truncated = False
    used = len(header) + 1  # +1 for trailing newline

    for term in domain_terms:
        name = term.get("term", "").strip()
        if not name:
            continue
        desc = (term.get("description") or "").strip()
        aliases = term.get("aliases") or []

        block_lines = [f"- {name}: {desc}" if desc else f"- {name}"]
        if aliases:
            alias_str = ", ".join(str(a) for a in aliases if a)
            if alias_str:
                block_lines.append(f"  aliases: {alias_str}")

        block_size = sum(len(l) + 1 for l in block_lines)  # +1 per newline
        if used + block_size > char_budget:
            truncated = True
            break
        lines.extend(block_lines)
        used += block_size

    if truncated:
        lines.append("(... glossary truncated for prompt budget ...)")

    return "\n".join(lines) + "\n"


def reset_cache() -> None:
    """Clear the module-level cache. Tests use this to reload after editing
    the JSON fixture in-place."""
    _CACHE.clear()


__all__ = [
    "load_glossary",
    "glossary_for_screen",
    "domain_terms_for_prompt",
    "reset_cache",
]
