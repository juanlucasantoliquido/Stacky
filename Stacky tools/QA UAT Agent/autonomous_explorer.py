"""
autonomous_explorer.py — Self-guided crawl of the Agenda Web (Fase 10).

PROBLEM
    Screens that are not in SUPPORTED_SCREENS or the navigation graph can
    never be reached by the QA UAT pipeline. The operator would have to
    manually add each screen to agenda_screens.py and navigation_graph.py.

SOLUTION
    autonomous_explorer performs a BFS-style read-only crawl of the app
    starting from a given entry screen. It discovers navigation edges by
    clicking safe links and buttons, records every (source, target, selector,
    label) tuple, and compares found URLs against SUPPORTED_SCREENS to
    surface previously unknown screens. The output feeds directly into
    navigation_graph_learner --apply.

DESIGN PRINCIPLES
    - Read-only: NEVER fills forms, submits data, or makes DML.
    - Safe actions only: clicks only <a> elements and <button> elements
      without type="submit". Blacklisted selectors are always skipped.
    - Bounded: MAX_CLICKS_PER_SCREEN prevents loops on dense link pages.
    - MAX_DEPTH limits the BFS traversal depth from the entry screen.
    - Human review required: unknown screens are written to
      unknown_screens.json and NOT automatically added to SUPPORTED_SCREENS.
      Operator must call `agenda_screens.add_discovered_screen()` explicitly.
    - Output feeds navigation_graph_learner: exploration_report.json
      follows the learned_edges schema so --apply works without conversion.

SAFETY GUARDRAILS
    SAFE_ACTIONS_ONLY = True
    MAX_CLICKS_PER_SCREEN = 10
    BLACKLIST_SELECTORS — never clicked:
        button[id*='Delete'], button[id*='Eliminar'], *[data-action='logout'],
        button[id*='Borrar'], button[id*='Cancel'], button[type='submit']

CLI
    python autonomous_explorer.py \\
        --entry Default.aspx \\
        --max-depth 3 \\
        [--max-clicks 10] \\
        [--read-only]       (default: True — included for explicitness) \\
        [--apply]           pass report to navigation_graph_learner --apply \\
        [--verbose]

Required env vars: AGENDA_WEB_BASE_URL, AGENDA_WEB_USER, AGENDA_WEB_PASS
Optional env vars: STACKY_QA_UAT_HEADLESS (default "1" = headless for explorer)

Output (stdout): exploration_report.json summary
Files written:
    evidence/explorations/<timestamp>/exploration_report.json
    evidence/explorations/<timestamp>/unknown_screens.json
"""
from __future__ import annotations

import argparse
import asyncio
import datetime
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.qa_uat.autonomous_explorer")

_TOOL_VERSION = "1.0.0"
_TOOL_ROOT = Path(__file__).resolve().parent
_EXPLORATIONS_DIR = _TOOL_ROOT / "evidence" / "explorations"

# ── Safety constants ──────────────────────────────────────────────────────────

#: Only click <a> and <button> without type="submit"
SAFE_ACTIONS_ONLY: bool = True

#: Hard limit on clicks per screen to prevent infinite loops
MAX_CLICKS_PER_SCREEN: int = 10

#: Default maximum BFS depth from the entry screen
DEFAULT_MAX_DEPTH: int = 3

#: CSS selectors that are NEVER clicked regardless of context
BLACKLIST_SELECTORS: list[str] = [
    "button[id*='Delete']",
    "button[id*='Eliminar']",
    "button[id*='Borrar']",
    "[data-action='logout']",
    "a[href*='logout']",
    "a[href*='Logout']",
    "button[type='submit']",
    "input[type='submit']",
    "button[id*='Cancel']",
    "button[id*='Cancelar']",
    "a[href*='FrmLogin']",      # avoid self-logout
]

# JS to extract clickable navigation elements from the current page.
# Returns a list of {selector, label, href, tagName} objects for elements
# that are safe to click (links and non-submit buttons, not blacklisted).
_COLLECT_NAV_ELEMENTS_JS = r"""
() => {
    const blacklistPatterns = [
        /Delete/i, /Eliminar/i, /Borrar/i, /logout/i, /Login/i,
        /Cancel/i, /Cancelar/i
    ];
    function isBlacklisted(el) {
        const id = (el.id || '');
        const href = (el.getAttribute('href') || '');
        const text = (el.textContent || '').trim();
        const dataAction = (el.getAttribute('data-action') || '');
        return blacklistPatterns.some(p =>
            p.test(id) || p.test(href) || p.test(dataAction)
        );
    }
    function bestSelector(el) {
        if (el.id) return '#' + el.id;
        if (el.getAttribute('data-testid')) return '[data-testid="' + el.getAttribute('data-testid') + '"]';
        const href = el.getAttribute('href');
        if (href && href.includes('.aspx')) {
            const m = href.match(/([A-Za-z0-9_]+\.aspx)/);
            if (m) return 'a[href*="' + m[1] + '"]';
        }
        return el.tagName.toLowerCase() + (el.className ? '.' + el.className.split(' ')[0] : '');
    }
    const results = [];
    // Collect <a> with href containing .aspx
    document.querySelectorAll('a[href*=".aspx"]').forEach(el => {
        if (!el.offsetParent) return;  // invisible
        if (isBlacklisted(el)) return;
        results.push({
            selector: bestSelector(el),
            label: el.textContent.trim().slice(0, 60),
            href: el.getAttribute('href') || '',
            tagName: 'a',
        });
    });
    // Collect <button> (excluding submit)
    document.querySelectorAll('button:not([type="submit"]):not([type="reset"])').forEach(el => {
        if (!el.offsetParent) return;  // invisible
        if (isBlacklisted(el)) return;
        results.push({
            selector: bestSelector(el),
            label: el.textContent.trim().slice(0, 60),
            href: '',
            tagName: 'button',
        });
    });
    return results.slice(0, 25);  // cap at 25 candidates per screen
}
"""

# ── Data structures ───────────────────────────────────────────────────────────

class ExploredEdge:
    """One discovered navigation edge."""
    __slots__ = ("source", "target", "selector", "label", "depth")

    def __init__(self, source: str, target: str, selector: str, label: str, depth: int):
        self.source = source
        self.target = target
        self.selector = selector
        self.label = label
        self.depth = depth

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "target": self.target,
            "selector": self.selector,
            "label": self.label,
            "depth": self.depth,
        }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_screen_from_url(url: str) -> Optional[str]:
    """Extract `Screen.aspx` from a URL string. Returns None if not found."""
    import re
    m = re.search(r'([A-Za-z0-9_]+\.aspx)', url)
    return m.group(1) if m else None


def _build_login_url(base_url: str) -> str:
    """Construct the login URL from base URL."""
    base = base_url.rstrip("/")
    return f"{base}/FrmLogin.aspx"


def _is_safe_to_click(selector: str) -> bool:
    """Return False if selector matches any blacklist pattern."""
    sel_lower = selector.lower()
    blacklist_keywords = [
        "delete", "eliminar", "borrar", "logout", "login",
        "cancel", "cancelar", "submit",
    ]
    return not any(kw in sel_lower for kw in blacklist_keywords)


# ── Core async crawler ────────────────────────────────────────────────────────

async def _crawl(
    entry_screen: str,
    base_url: str,
    username: str,
    password: str,
    max_depth: int,
    max_clicks: int,
    headless: bool,
) -> tuple[list[ExploredEdge], list[str]]:
    """BFS crawl returning (discovered_edges, unknown_screens).

    Performs a headless/headed Playwright session:
    1. Login via FrmLogin.aspx
    2. Navigate to entry_screen
    3. BFS: for each screen in the queue, collect clickable nav elements,
       click each one, record the resulting URL, go back, repeat.
    Never fills forms or submits data.
    """
    try:
        from playwright.async_api import async_playwright, TimeoutError as PWTimeoutError
    except ImportError:
        raise RuntimeError(
            "playwright not installed. Run: pip install playwright && playwright install chromium"
        )

    from agenda_screens import is_supported, SUPPORTED_SCREENS

    discovered_edges: list[ExploredEdge] = []
    unknown_screens: set[str] = set()
    visited: set[str] = set()  # screens already explored
    queue: list[tuple[str, int]] = [(entry_screen, 0)]  # (screen, depth)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=headless)
        context = await browser.new_context(ignore_https_errors=True)
        page = await context.new_page()

        # ── Login ────────────────────────────────────────────────────────
        login_url = _build_login_url(base_url)
        logger.info("autonomous_explorer: logging in via %s", login_url)
        try:
            await page.goto(login_url, wait_until="networkidle", timeout=30_000)
            # Standard ASP.NET WebForms login — try common field IDs
            for user_sel in ["#txtUsuario", "#txtUser", "#txtLogin", "input[name*='user' i]"]:
                try:
                    await page.fill(user_sel, username, timeout=2_000)
                    break
                except Exception:
                    pass
            for pass_sel in ["#txtContrasena", "#txtPassword", "#txtPass", "input[type='password']"]:
                try:
                    await page.fill(pass_sel, password, timeout=2_000)
                    break
                except Exception:
                    pass
            for btn_sel in ["#btnIngresar", "#btnLogin", "button[type='submit']", "input[type='submit']"]:
                try:
                    await page.click(btn_sel, timeout=2_000)
                    break
                except Exception:
                    pass
            await page.wait_for_load_state("networkidle", timeout=20_000)
        except Exception as exc:
            logger.error("autonomous_explorer: login failed: %s", exc)
            await browser.close()
            raise

        # ── BFS crawl ────────────────────────────────────────────────────
        while queue:
            current_screen, depth = queue.pop(0)
            if current_screen in visited:
                continue
            visited.add(current_screen)

            if depth >= max_depth:
                logger.debug("autonomous_explorer: max depth %d reached at %s", depth, current_screen)
                continue

            # Navigate to current screen
            screen_url = f"{base_url.rstrip('/')}/{current_screen}"
            logger.info("autonomous_explorer: exploring %s (depth=%d)", current_screen, depth)
            try:
                await page.goto(screen_url, wait_until="networkidle", timeout=20_000)
            except Exception as exc:
                logger.warning("autonomous_explorer: cannot navigate to %s: %s", current_screen, exc)
                continue

            # Collect clickable elements
            try:
                nav_elements = await page.evaluate(_COLLECT_NAV_ELEMENTS_JS)
            except Exception as exc:
                logger.warning("autonomous_explorer: JS eval failed on %s: %s", current_screen, exc)
                nav_elements = []

            click_count = 0
            for elem in nav_elements:
                if click_count >= max_clicks:
                    break
                selector = elem.get("selector", "")
                label = elem.get("label", "")
                href = elem.get("href", "")

                if not _is_safe_to_click(selector):
                    continue

                # Fast path: if href contains .aspx, we know the target without clicking
                target_from_href = _extract_screen_from_url(href) if href else None

                try:
                    pre_url = page.url
                    # Try to click and wait for navigation
                    async with page.expect_navigation(wait_until="networkidle", timeout=8_000):
                        await page.click(selector, timeout=5_000)
                    post_url = page.url
                    target_screen = _extract_screen_from_url(post_url) or target_from_href
                except Exception:
                    # Navigation did not happen (button maybe opened popup or AJAX)
                    # Use href-derived target if available, else skip
                    target_screen = target_from_href
                    if not target_screen:
                        continue
                    post_url = None

                if not target_screen or target_screen == current_screen:
                    # Navigate back to current screen to stay in BFS
                    try:
                        if post_url and post_url != screen_url:
                            await page.goto(screen_url, wait_until="networkidle", timeout=15_000)
                    except Exception:
                        pass
                    continue

                edge = ExploredEdge(
                    source=current_screen,
                    target=target_screen,
                    selector=selector,
                    label=label,
                    depth=depth + 1,
                )
                discovered_edges.append(edge)
                click_count += 1

                if not is_supported(target_screen):
                    logger.info(
                        "autonomous_explorer: discovered UNKNOWN screen: %s (from %s)",
                        target_screen, current_screen,
                    )
                    unknown_screens.add(target_screen)

                # Add to BFS queue if not yet visited
                if target_screen not in visited:
                    queue.append((target_screen, depth + 1))

                # Navigate back to the current screen for next element
                try:
                    await page.goto(screen_url, wait_until="networkidle", timeout=15_000)
                except Exception as exc:
                    logger.warning("autonomous_explorer: cannot return to %s: %s", current_screen, exc)
                    break

        await browser.close()

    return discovered_edges, sorted(unknown_screens)


# ── Output builders ───────────────────────────────────────────────────────────

def _build_report(
    entry_screen: str,
    edges: list[ExploredEdge],
    unknown_screens: list[str],
    elapsed_s: float,
    max_depth: int,
) -> dict:
    """Build the exploration_report.json dict."""
    from agenda_screens import is_supported

    # Deduplicate edges (same source+target may be reached via multiple selectors)
    seen: set[tuple] = set()
    unique_edges = []
    for e in edges:
        key = (e.source, e.target)
        if key not in seen:
            seen.add(key)
            unique_edges.append(e)

    known_screens = sorted({e.target for e in unique_edges if is_supported(e.target)})

    return {
        "schema_version": "1.0",
        "tool_version": _TOOL_VERSION,
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
        "entry_screen": entry_screen,
        "max_depth": max_depth,
        "elapsed_s": round(elapsed_s, 2),
        "summary": {
            "edges_discovered": len(unique_edges),
            "known_screens_reached": len(known_screens),
            "unknown_screens_found": len(unknown_screens),
        },
        # learned_edges schema — compatible with navigation_graph_learner --apply
        "learned_edges": [
            {
                "source": e.source,
                "target": e.target,
                "trigger_selector": e.selector,
                "trigger_label": e.label,
                "observed_count": 1,
                "confidence": "tentative",
                "source_type": "autonomous_explorer",
                "depth_discovered": e.depth,
            }
            for e in unique_edges
        ],
        "known_screens_reached": known_screens,
        "unknown_screens": unknown_screens,
    }


# ── Apply to learner ──────────────────────────────────────────────────────────

def _apply_to_learner(report_path: Path, verbose: bool) -> bool:
    """Pass exploration_report.json to navigation_graph_learner --apply.

    Creates a temporary session directory with the edges formatted as a
    session.json so the learner can ingest them without a dedicated code path.
    Returns True on success, False on any error.
    """
    import subprocess as _sp
    import tempfile
    import copy

    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.error("autonomous_explorer: cannot read report for --apply: %s", exc)
        return False

    # Build a minimal session.json that navigation_graph_learner accepts
    transitions = []
    for edge in report.get("learned_edges", []):
        transitions.append({
            "from": edge["source"],
            "to": edge["target"],
            "trigger_selector": edge.get("trigger_selector", ""),
            "trigger_label": edge.get("trigger_label", ""),
        })

    nav_path = []
    seen: set = set()
    for t in transitions:
        if t["from"] not in seen:
            nav_path.append(t["from"])
            seen.add(t["from"])
        if t["to"] not in seen:
            nav_path.append(t["to"])
            seen.add(t["to"])

    session_payload = {
        "schema_version": "1.0",
        "tool_version": _TOOL_VERSION,
        "recorded_at": report.get("generated_at", ""),
        "goal": f"autonomous_explorer — entry={report.get('entry_screen', '')}",
        "navigation_path": nav_path,
        "transitions": transitions,
        "discovered_selectors": {},
        "form_fields": {},
        "inferred_goal_action": "",
    }

    # Write to a temp session directory
    import tempfile as _tmp
    ts = datetime.datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    session_dir = _TOOL_ROOT / "evidence" / "recordings" / f"explorer-{ts}"
    session_dir.mkdir(parents=True, exist_ok=True)
    session_file = session_dir / "session.json"
    session_file.write_text(json.dumps(session_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    learner = _TOOL_ROOT / "navigation_graph_learner.py"
    cmd = [sys.executable, str(learner), "--session", str(session_dir), "--apply"]
    if verbose:
        cmd.append("--verbose")

    logger.info("autonomous_explorer: invoking navigation_graph_learner --apply")
    try:
        result = _sp.run(cmd, capture_output=not verbose, text=True, timeout=60)
        if result.returncode != 0:
            logger.warning(
                "autonomous_explorer: learner returned exit code %d", result.returncode
            )
        return result.returncode == 0
    except Exception as exc:
        logger.error("autonomous_explorer: failed to run learner: %s", exc)
        return False


# ── Main entry point ──────────────────────────────────────────────────────────

def run(
    entry_screen: str = "Default.aspx",
    max_depth: int = DEFAULT_MAX_DEPTH,
    max_clicks: int = MAX_CLICKS_PER_SCREEN,
    apply: bool = False,
    verbose: bool = False,
) -> dict:
    """Public entry point for programmatic use.

    Returns the exploration report dict.  Does NOT write files or run the
    learner — use the CLI for that.
    """
    base_url = os.environ.get("AGENDA_WEB_BASE_URL", "").rstrip("/")
    username = os.environ.get("AGENDA_WEB_USER", "")
    password = os.environ.get("AGENDA_WEB_PASS", "")
    headless = os.environ.get("STACKY_QA_UAT_HEADLESS", "1") == "1"

    if not base_url:
        return {
            "ok": False,
            "error": "missing_env",
            "message": "AGENDA_WEB_BASE_URL is not set",
        }
    if not username or not password:
        return {
            "ok": False,
            "error": "missing_credentials",
            "message": "AGENDA_WEB_USER and AGENDA_WEB_PASS must be set",
        }

    started = time.time()
    try:
        edges, unknown_screens = asyncio.run(
            _crawl(
                entry_screen=entry_screen,
                base_url=base_url,
                username=username,
                password=password,
                max_depth=max_depth,
                max_clicks=max_clicks,
                headless=headless,
            )
        )
    except Exception as exc:
        return {
            "ok": False,
            "error": "crawler_error",
            "message": str(exc),
        }

    elapsed = time.time() - started
    report = _build_report(entry_screen, edges, unknown_screens, elapsed, max_depth)
    report["ok"] = True
    return report


def main() -> None:
    args = _parse_args()
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, stream=sys.stderr,
                            format="%(levelname)s %(name)s: %(message)s")
    else:
        logging.basicConfig(level=logging.WARNING, stream=sys.stderr)

    base_url = os.environ.get("AGENDA_WEB_BASE_URL", "").rstrip("/")
    username = os.environ.get("AGENDA_WEB_USER", "")
    password = os.environ.get("AGENDA_WEB_PASS", "")
    headless = os.environ.get("STACKY_QA_UAT_HEADLESS", "1") == "1"

    missing = [v for v, k in [("AGENDA_WEB_BASE_URL", base_url),
                               ("AGENDA_WEB_USER", username),
                               ("AGENDA_WEB_PASS", password)] if not k]
    if missing:
        sys.stderr.write(f"error: missing env vars: {', '.join(missing)}\n")
        sys.exit(1)

    entry = args.entry
    if not entry.endswith(".aspx"):
        entry = entry + ".aspx"

    started = time.time()
    sys.stderr.write(
        f"autonomous_explorer v{_TOOL_VERSION} — entry={entry} "
        f"max_depth={args.max_depth} max_clicks={args.max_clicks}\n"
    )
    sys.stderr.write("Press Ctrl+C to stop early.\n")

    try:
        edges, unknown_screens = asyncio.run(
            _crawl(
                entry_screen=entry,
                base_url=base_url,
                username=username,
                password=password,
                max_depth=args.max_depth,
                max_clicks=args.max_clicks,
                headless=headless,
            )
        )
    except KeyboardInterrupt:
        sys.stderr.write("\nautonomous_explorer: interrupted — writing partial report\n")
        edges, unknown_screens = [], []
    except Exception as exc:
        sys.stderr.write(f"autonomous_explorer: crawler error: {exc}\n")
        sys.exit(1)

    elapsed = time.time() - started
    report = _build_report(entry, edges, unknown_screens, elapsed, args.max_depth)
    report["ok"] = True

    # Persist output
    ts = datetime.datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    out_dir = _EXPLORATIONS_DIR / ts
    out_dir.mkdir(parents=True, exist_ok=True)

    report_path = out_dir / "exploration_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    sys.stderr.write(f"autonomous_explorer: report written to {report_path}\n")

    if unknown_screens:
        unk_path = out_dir / "unknown_screens.json"
        unk_payload = {
            "schema_version": "1.0",
            "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
            "tool_version": _TOOL_VERSION,
            "description": (
                "Screens discovered by autonomous_explorer that are NOT in "
                "SUPPORTED_SCREENS. Human review required before adding."
            ),
            "unknown_screens": unknown_screens,
            "add_command": (
                "python agenda_screens.py --add-screen <ScreenName.aspx> "
                f"--from-exploration {report_path}"
            ),
        }
        unk_path.write_text(json.dumps(unk_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        sys.stderr.write(
            f"autonomous_explorer: {len(unknown_screens)} unknown screen(s) written to {unk_path}\n"
        )
        sys.stderr.write("  → Review and run: python agenda_screens.py --add-screen <Name.aspx>\n")

    if args.apply and edges:
        ok = _apply_to_learner(report_path, verbose=args.verbose)
        if ok:
            sys.stderr.write("autonomous_explorer: navigation_graph_learner applied successfully\n")
        else:
            sys.stderr.write("autonomous_explorer: learner apply had errors (check log)\n")
    elif args.apply and not edges:
        sys.stderr.write("autonomous_explorer: no edges discovered — skipping --apply\n")

    # Print report summary to stdout as JSON
    summary = {
        "ok": True,
        "entry_screen": entry,
        "edges_discovered": report["summary"]["edges_discovered"],
        "known_screens_reached": report["summary"]["known_screens_reached"],
        "unknown_screens_found": report["summary"]["unknown_screens_found"],
        "unknown_screens": unknown_screens,
        "report_path": str(report_path),
        "elapsed_s": report["elapsed_s"],
        "version": _TOOL_VERSION,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    sys.exit(0)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "autonomous_explorer — Self-guided read-only crawl of Agenda Web. "
            "Discovers navigation edges and unknown screens for the QA UAT Agent."
        )
    )
    parser.add_argument(
        "--entry",
        default="Default.aspx",
        help="Entry screen filename (default: Default.aspx)",
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=DEFAULT_MAX_DEPTH,
        dest="max_depth",
        help=f"BFS depth limit (default: {DEFAULT_MAX_DEPTH})",
    )
    parser.add_argument(
        "--max-clicks",
        type=int,
        default=MAX_CLICKS_PER_SCREEN,
        dest="max_clicks",
        help=f"Max clicks per screen (default: {MAX_CLICKS_PER_SCREEN})",
    )
    parser.add_argument(
        "--read-only",
        action="store_true",
        dest="read_only",
        default=True,
        help="Read-only mode (default: True — always read-only). Included for explicitness.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Pass discovered edges to navigation_graph_learner --apply after crawl.",
    )
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    main()
