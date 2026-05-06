"""
ui_map_builder.py — Inspect an Agenda Web screen and produce a UI map JSON.

SPEC: SPEC/ui_map_builder.md
CLI:
    python ui_map_builder.py --screen FrmAgenda.aspx [--rebuild] [--verbose]

Required env vars: AGENDA_WEB_BASE_URL, AGENDA_WEB_USER, AGENDA_WEB_PASS
Optional env vars: STACKY_QA_UAT_HEADLESS (default "0" = headed)

Output: JSON to stdout following ui_map.schema.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.qa_uat.ui_map_builder")

_TOOL_VERSION = "1.1.0"
# Bump = added input_type, class_list, accessible_name, is_decorative
# fields per element (M1 — UI map enriquecido). Backwards-compatible:
# downstream tools tolerate the absence of these fields.
_SCHEMA_VERSION = "ui_map/1.1"
_CACHE_DIR = Path(__file__).resolve().parent / "cache" / "ui_maps"
_ALIAS_PATTERN_RE_STR = r"^(select|input|btn|grid|panel|msg|link|table|checkbox|radio|text)_[a-zA-Z0-9_]+$"
_SUPPORTED_KINDS = ("input", "select", "button", "table", "div", "span", "a",
                    "checkbox", "radio", "textarea", "label", "grid", "panel", "other")

# CSS class fragments that mark a node as PURE LAYOUT/DECORATION (a section
# heading, column label, page title, breadcrumb…). These elements are NEVER
# valid targets for runtime-message oracles like `visible/invisible`. The
# scenario_compiler uses `is_decorative=true` to route oracles away from them.
# IMPORTANT: substring match (case-insensitive). Materialize/AIS labels are the
# main source — `input-field-label` is the title of a Materialize column, not
# a runtime message.
_DECORATIVE_CLASS_HINTS = (
    "input-field-label",
    "col-form-label",
    "page-title",
    "section-title",
    "breadcrumb",
    "card-title",
    "navbar-brand",
    "panel-heading",
)

# Login selectors for Agenda Web (FrmLogin.aspx rendered by AIS controls)
_LOGIN_URL_SUFFIX = "/FrmLogin.aspx"
_LOGIN_USER_SEL = "#c_abfUsuario"
_LOGIN_PASS_SEL = "#c_abfContrasena"
_LOGIN_BTN_SEL = "#c_btnOk"
_LOGIN_SUCCESS_INDICATOR = "FrmAgenda.aspx"


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    args = _parse_args()
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, stream=sys.stderr,
                            format="%(levelname)s %(name)s: %(message)s")
    else:
        logging.basicConfig(level=logging.WARNING, stream=sys.stderr)

    result = run(screen=args.screen, rebuild=args.rebuild, verbose=args.verbose)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result.get("ok") else 1)


def run(screen: str, rebuild: bool = False, verbose: bool = False) -> dict:
    """Core logic — callable from tests without subprocess."""
    started = time.time()

    # Fail-fast on unsupported screen — single source of truth in
    # `agenda_screens.SUPPORTED_SCREENS`. Returning a structured error here
    # avoids opening Playwright + logging into Agenda Web only to discover
    # we'd be inspecting a page the rest of the pipeline cannot consume.
    from agenda_screens import is_supported, SUPPORTED_SCREENS
    if not is_supported(screen):
        return {
            "ok": False,
            "error": "unsupported_screen",
            "screen": screen,
            "supported_screens": sorted(SUPPORTED_SCREENS),
            "message": (
                f"Screen {screen!r} is not in the supported catalogue. "
                f"Add it to agenda_screens.SUPPORTED_SCREENS first."
            ),
        }

    # Fail-fast on missing env vars (before opening browser)
    base_url = os.environ.get("AGENDA_WEB_BASE_URL", "").strip()
    user = os.environ.get("AGENDA_WEB_USER", "").strip()
    password = os.environ.get("AGENDA_WEB_PASS", "").strip()

    for var, val in [("AGENDA_WEB_BASE_URL", base_url),
                     ("AGENDA_WEB_USER", user),
                     ("AGENDA_WEB_PASS", password)]:
        if not val:
            return _err("missing_env_var", f"Required env var {var!r} is not set")

    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = _CACHE_DIR / f"{screen}.json"

    # Check cache (only if not rebuilding).
    # Cache is invalidated when the UI map schema version changes — older
    # caches lack input_type / is_decorative / class_list and would mislead
    # downstream tools.
    if not rebuild and cache_file.is_file():
        try:
            cached = json.loads(cache_file.read_text(encoding="utf-8"))
            cached_schema = cached.get("schema_version", "ui_map/1.0")
            if cached.get("ok") and cached.get("hash") and cached_schema == _SCHEMA_VERSION:
                logger.debug("cache hit for %s (hash=%s)", screen, cached["hash"])
                return cached
            if cached_schema != _SCHEMA_VERSION:
                logger.info(
                    "UI map schema bump for %s (cached=%s, current=%s) — rebuilding",
                    screen, cached_schema, _SCHEMA_VERSION,
                )
        except Exception as exc:
            logger.warning("cache corrupt for %s, rebuilding: %s", screen, exc)

    # Playwright inspection
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout
    except ImportError:
        return _err("playwright_not_installed",
                    "playwright not installed. Run: pip install playwright && playwright install chromium")

    headless = os.environ.get("STACKY_QA_UAT_HEADLESS", "0") != "0"
    url = base_url.rstrip("/") + "/" + screen.lstrip("/")

    elements = []
    dom_content = ""

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            context = browser.new_context()
            page = context.new_page()

            # Login
            try:
                login_url = base_url.rstrip("/") + _LOGIN_URL_SUFFIX
                page.goto(login_url, timeout=20000, wait_until="load")
                page.fill(_LOGIN_USER_SEL, user, timeout=10000)
                page.fill(_LOGIN_PASS_SEL, password)
                page.click(_LOGIN_BTN_SEL)
                page.wait_for_load_state("load", timeout=20000)
            except PwTimeout:
                browser.close()
                return _err("login_failed", f"Timeout during login at {login_url}")
            except Exception as exc:
                browser.close()
                return _err("login_failed", f"Login failed: {exc}")

            # Check login success (look for redirect or new page)
            if "FrmLogin" in page.url or "Login" in page.url:
                browser.close()
                return _err("login_failed", f"Login failed: still on login page at {page.url}")

            # Navigate to target screen
            try:
                page.goto(url, timeout=20000, wait_until="load")
                page.wait_for_load_state("domcontentloaded", timeout=10000)
            except PwTimeout:
                browser.close()
                return _err("screen_not_loaded", f"Timeout loading {url}")

            # Capture DOM content for hash
            dom_content = page.content()

            # Extract elements via accessibility tree + DOM
            elements = _extract_elements(page, verbose=verbose)

            browser.close()
    except Exception as exc:
        msg = str(exc)
        if "playwright" in msg.lower() or "chromium" in msg.lower():
            return _err("playwright_crash", f"Playwright error: {msg[:200]}")
        return _err("playwright_crash", f"Unexpected error: {msg[:200]}")

    if not elements:
        return _err("no_elements_found", f"No accessible elements found on {screen}")

    # Compute DOM hash
    dom_hash = "sha256:" + hashlib.sha256(dom_content.encode("utf-8")).hexdigest()

    # Rebuild-check: if hash matches cache, return cache
    if not rebuild and cache_file.is_file():
        try:
            cached = json.loads(cache_file.read_text(encoding="utf-8"))
            if cached.get("hash") == dom_hash:
                logger.debug("DOM unchanged for %s, returning cache", screen)
                return cached
        except Exception:
            pass

    # Add semantic aliases via LLM (with fallback)
    elements = _add_semantic_aliases(elements, verbose=verbose)

    # Build warnings
    warnings = []
    low_count = sum(1 for e in elements if e.get("robustness") == "low")
    if low_count:
        warnings.append(f"{low_count} elementos con robustness=low: requieren data-testid del dev")

    result: dict = {
        "ok": True,
        "schema_version": _SCHEMA_VERSION,
        "screen": screen,
        "hash": dom_hash,
        "captured_at": _now_iso(),
        "url": url,
        "elements": elements,
        "warnings": warnings,
        "meta": {
            "tool": "ui_map_builder",
            "version": _TOOL_VERSION,
            "duration_ms": int((time.time() - started) * 1000),
        },
    }

    # Persist cache
    try:
        cache_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.debug("UI map cached at %s", cache_file)
    except Exception as exc:
        logger.warning("Could not cache UI map: %s", exc)

    return result


# ── DOM extraction ─────────────────────────────────────────────────────────────

def _extract_elements(page, verbose: bool = False) -> list:
    """Extract accessible elements from the page using accessibility tree + DOM queries."""
    from selector_discovery import discover_selector

    elements = []

    # Query inputs, selects, buttons, tables, divs with IDs
    js = """
    () => {
        const results = [];
        const seen = new Set();

        function addEl(el, kind) {
            if (!el || seen.has(el)) return;
            seen.add(el);
            const id = el.id || null;
            // Native HTML5 input type — needed by playwright_test_generator
            // to decide value formatting (date → YYYY-MM-DD, time → HH:MM, etc).
            const inputType = (el.tagName === 'INPUT')
                ? (el.getAttribute('type') || 'text').toLowerCase()
                : null;
            const label = el.getAttribute('aria-label') ||
                          el.getAttribute('placeholder') ||
                          (() => {
                              const lbl = el.labels && el.labels[0];
                              return lbl ? lbl.textContent.trim() : null;
                          })() || null;
            // Accessible name from accessibility tree (more reliable than label
            // for buttons/links rendered with aria-labelledby).
            const accessibleName = (() => {
                if (el.getAttribute('aria-labelledby')) {
                    const refIds = el.getAttribute('aria-labelledby').split(/\\s+/);
                    return refIds.map(rid => {
                        const r = document.getElementById(rid);
                        return r ? r.textContent.trim() : '';
                    }).filter(Boolean).join(' ') || null;
                }
                return null;
            })();
            const role = el.getAttribute('role') || el.tagName.toLowerCase();
            const testid = el.getAttribute('data-testid') || null;
            const txt = el.value || el.textContent.trim().substring(0, 50) || null;
            const rect = el.getBoundingClientRect();
            // Class list (cap to 16 entries to keep the UI map JSON compact).
            const classList = Array.from(el.classList || []).slice(0, 16);
            results.push({
                kind: kind,
                role: role,
                label: label,
                accessible_name: accessibleName,
                asp_id: id,
                input_type: inputType,
                data_testid: testid,
                class_list: classList,
                text: (kind === 'button' || kind === 'a') ? txt : null,
                position: {x: Math.round(rect.left), y: Math.round(rect.top)}
            });
        }

        document.querySelectorAll('input:not([type=hidden])').forEach(e => addEl(e, 'input'));
        document.querySelectorAll('select').forEach(e => addEl(e, 'select'));
        document.querySelectorAll('input[type=submit], input[type=button], button').forEach(e => addEl(e, 'button'));
        document.querySelectorAll('table[id]').forEach(e => addEl(e, 'table'));
        document.querySelectorAll('div[id], span[id]').forEach(e => addEl(e, 'div'));
        document.querySelectorAll('a[id], a[href]').forEach(e => addEl(e, 'a'));

        return results;
    }
    """
    try:
        raw_elements = page.evaluate(js)
    except Exception as exc:
        logger.warning("JS extraction failed: %s", exc)
        return []

    for el in raw_elements:
        if not isinstance(el, dict):
            continue
        sel_result = discover_selector(el)
        class_list = el.get("class_list") or []
        if not isinstance(class_list, list):
            class_list = []
        element = {
            "kind": el.get("kind", "other"),
            "role": str(el.get("role") or ""),
            "label": el.get("label"),
            "accessible_name": el.get("accessible_name"),
            "asp_id": el.get("asp_id"),
            # Native HTML5 input type (text|date|time|month|number|color|email…)
            # or None for non-input elements. Consumed by the test generator to
            # transform fill values (e.g. dd/MM/yyyy → YYYY-MM-DD).
            "input_type": el.get("input_type"),
            "data_testid": el.get("data_testid"),
            "class_list": class_list,
            # is_decorative: true when CSS classes mark this node as a layout
            # heading / column label / page title and not a runtime message.
            # Compiler MUST NOT use these as targets of visible/invisible/equals
            # oracles for runtime messages (otherwise we get false FAILs like
            # P01 ticket 70: oracle hit `<div class="input-field-label">…
            # Agendados por Usuario</div>` which is permanent layout text).
            "is_decorative": _is_decorative(el.get("kind"), class_list),
            "selector_recommended": sel_result["selector"],
            "robustness": sel_result["robustness"],
            "alias_semantic": _default_alias(el),  # placeholder, overwritten by LLM
            "fallback_selectors": sel_result["fallbacks"],
            "position": el.get("position", {}),
            "warning": sel_result.get("warning"),
        }
        elements.append(element)

    return elements


def _is_decorative(kind: Optional[str], class_list: list) -> bool:
    """Return True if the CSS class list marks this element as pure layout
    decoration (section header, column label, page title…), making it an
    INVALID target for runtime message oracles.

    Only div / span / label nodes can be decorative; form controls (input,
    select, button…) and tables are always functional.
    """
    if kind not in ("div", "span", "label", "other", None):
        return False
    if not class_list:
        return False
    blob = " ".join(str(c) for c in class_list).lower()
    return any(hint in blob for hint in _DECORATIVE_CLASS_HINTS)


def _default_alias(el: dict) -> str:
    """Generate a fallback alias from element metadata."""
    import re
    kind = el.get("kind") or "input"
    label = el.get("label") or el.get("asp_id") or ""
    # Normalize to snake_case
    slug = re.sub(r'[^a-zA-Z0-9]', '_', label.lower())
    slug = re.sub(r'_+', '_', slug).strip('_')
    if not slug:
        slug = "element"

    # Map kind to prefix
    prefix_map = {
        "select": "select",
        "button": "btn",
        "table": "grid",
        "div": "panel",
        "span": "msg",
        "a": "link",
        "input": "input",
    }
    prefix = prefix_map.get(kind, "input")
    alias = f"{prefix}_{slug}"[:50]
    return alias


# ── LLM alias enrichment ───────────────────────────────────────────────────────

def _add_semantic_aliases(elements: list, verbose: bool = False) -> list:
    """Use LLM to suggest semantic aliases; fallback to default_alias."""
    import re
    try:
        from llm_client import call_llm, LLMError
        snippet = json.dumps(
            [{"kind": e["kind"], "role": e["role"], "label": e.get("label"),
              "asp_id": e.get("asp_id")}
             for e in elements],
            ensure_ascii=False,
        )[:3000]

        system_prompt = (
            "You are a UI test engineer. Given a list of web page elements, "
            "assign a semantic alias to each using snake_case with these prefixes: "
            "select_ input_ btn_ grid_ panel_ msg_ link_ table_ checkbox_ radio_ text_\n"
            "Rules: use the label or asp_id to create the alias. "
            "Return ONLY a JSON array: [{\"asp_id\": \"...\", \"alias_semantic\": \"...\"}, ...]"
        )
        result = call_llm(
            model="gpt-4o-mini",
            system=system_prompt,
            user=f"Elements:\n{snippet}",
            max_tokens=512,
        )
        # Parse LLM response
        raw = result["text"].strip()
        # Strip markdown code fences if present
        raw = re.sub(r'^```[a-z]*\n?', '', raw)
        raw = re.sub(r'\n?```$', '', raw)
        aliases = json.loads(raw)
        alias_map: dict = {}
        ALIAS_RE = re.compile(_ALIAS_PATTERN_RE_STR)
        for item in aliases:
            if isinstance(item, dict):
                asp_id = item.get("asp_id")
                alias = item.get("alias_semantic", "")
                if asp_id and ALIAS_RE.match(str(alias)):
                    alias_map[asp_id] = alias

        for el in elements:
            asp_id = el.get("asp_id")
            if asp_id and asp_id in alias_map:
                el["alias_semantic"] = alias_map[asp_id]
    except Exception as exc:
        logger.info("LLM alias enrichment failed, using default aliases: %s", exc)
        # Ensure all elements have valid aliases via default
        import re
        ALIAS_RE = re.compile(_ALIAS_PATTERN_RE_STR)
        for el in elements:
            if not el.get("alias_semantic") or not ALIAS_RE.match(el.get("alias_semantic", "")):
                el["alias_semantic"] = _default_alias(el)

    return elements


# ── Utilities ─────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    import datetime
    return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def _err(code: str, message: str) -> dict:
    return {"ok": False, "error": code, "message": message}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="ui_map_builder — Inspect Agenda Web screen and produce UI map"
    )
    parser.add_argument("--screen", required=True, help="Screen name, e.g. FrmAgenda.aspx")
    parser.add_argument("--rebuild", action="store_true",
                        help="Ignore cache and rebuild from scratch")
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    main()
