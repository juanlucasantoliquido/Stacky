"""
session_recorder.py — Demo-driven learning for the QA UAT Agent (Fase 5).

Records a free-form Playwright session driven by a human operator, capturing
navigation transitions, the clicked element selectors that produced each
transition, and a periodic snapshot of visible interactive elements per
screen. On exit (Ctrl+C / browser close) writes a structured ``session.json``
under ``evidence/recordings/<timestamp>/`` and (by default) feeds the result
into ``navigation_graph_learner.py --session`` so the path planner gains the
new edges immediately.

Design pitched in ROADMAP.md (Fase 5). Companion to:
  * navigation_graph_learner.py (consumes session.json)
  * navigation_graph.py         (loads cache/learned_edges.json at import)
  * cache/discovered_selectors.json (consumed by ui_map_builder downstream)

CLI:
    python session_recorder.py [--goal "panel administradores"]
                               [--url http://app/FrmLogin.aspx]
                               [--no-learn]
                               [--background]

Required env vars: AGENDA_WEB_BASE_URL, AGENDA_WEB_USER, AGENDA_WEB_PASS
Optional env vars: STACKY_QA_UAT_HEADLESS (default "0" = headed)

Output: prints the session.json path on stdout. Exit codes:
    0  → session recorded and (optionally) learned successfully
    1  → setup error (missing env, Playwright crash, login failure)
    2  → session recorded but learner returned no proposed edges (warning, not failure)

NOTE: This module is intentionally NOT importable as a library — it is a CLI
tool meant to be run interactively by the operator. The pure helpers below
(_extract_screen_from_url, _dedupe_consecutive, _best_selector_js) are
exposed for unit testing only.
"""
from __future__ import annotations

import argparse
import asyncio
import datetime
import json
import logging
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.qa_uat.session_recorder")

_TOOL_VERSION = "1.1.0"
# 1.1.0 = Fase 7 — intent_inferrer integration: after a session is recorded,
# infer_goal_from_path() is called on the navigation_path and the result is
# stored as "inferred_goal_action" in session.json.
_SCHEMA_VERSION = "1.0"
_TOOL_ROOT = Path(__file__).resolve().parent
_RECORDINGS_DIR = _TOOL_ROOT / "evidence" / "recordings"

# Login selectors mirror ui_map_builder.py — single source of truth would be
# nice but the recorder must stay decoupled to avoid pulling in ui_map_builder's
# Playwright sync stack. Bump in lockstep when AIS changes login DOM.
_LOGIN_URL_SUFFIX = "/FrmLogin.aspx"
_LOGIN_USER_SEL = "#c_abfUsuario"
_LOGIN_PASS_SEL = "#c_abfContrasena"
_LOGIN_BTN_SEL = "#c_btnOk"

# How often to snapshot visible interactive elements while the operator is
# navigating. 500ms balances coverage (catch dynamic content) against
# overhead (each snapshot is a JS evaluate roundtrip).
_SNAPSHOT_INTERVAL_S = 0.5

# Inline JS injected once per page navigation. Captures the best-effort
# selector for any element the operator interacts with via mousedown — we use
# mousedown instead of click because click bubbles AFTER the framework can
# preventDefault, while mousedown fires for every pointer interaction the
# user actually performs. The selector ranking mirrors Playwright's own
# heuristic: aria-label > id > text > css path.
_RECORDER_LISTENER_JS = """
(() => {
  if (window.__stackyRecorderInstalled) return;
  window.__stackyRecorderInstalled = true;
  window.__stackyRecorderEvents = [];

  function bestSelector(el) {
    if (!el || el.nodeType !== 1) return null;
    const aria = el.getAttribute && el.getAttribute('aria-label');
    if (aria && aria.trim()) return `[aria-label="${aria.replace(/"/g, '\\\\"')}"]`;
    if (el.id) return `#${el.id}`;
    const txt = (el.innerText || el.textContent || '').trim();
    if (txt && txt.length > 0 && txt.length <= 40) {
      const tag = el.tagName.toLowerCase();
      return `${tag}:has-text("${txt.replace(/"/g, '\\\\"')}")`;
    }
    const href = el.getAttribute && el.getAttribute('href');
    if (href) return `a[href="${href}"]`;
    const cls = (el.className && typeof el.className === 'string') ? el.className.split(/\\s+/).filter(Boolean).slice(0, 2).join('.') : '';
    return `${el.tagName.toLowerCase()}${cls ? '.' + cls : ''}`;
  }

  function bestLabel(el) {
    if (!el) return '';
    return (el.getAttribute && el.getAttribute('aria-label'))
      || (el.innerText || el.textContent || '').trim().slice(0, 80)
      || (el.getAttribute && el.getAttribute('title'))
      || '';
  }

  document.addEventListener('mousedown', (ev) => {
    const el = ev.target.closest('a, button, [role="button"], input[type="submit"], input[type="button"]');
    if (!el) return;
    window.__stackyRecorderEvents.push({
      ts: Date.now(),
      url: window.location.href,
      tag: el.tagName.toLowerCase(),
      selector: bestSelector(el),
      label: bestLabel(el),
    });
  }, true);
})();
"""

# Snapshot helper: enumerate visible interactive elements with their best
# selector. Filtered server-side here to keep payloads small.
_SNAPSHOT_JS = """
(() => {
  function bestSelector(el) {
    const aria = el.getAttribute('aria-label');
    if (aria && aria.trim()) return `[aria-label="${aria.replace(/"/g, '\\\\"')}"]`;
    if (el.id) return `#${el.id}`;
    const txt = (el.innerText || el.textContent || '').trim();
    if (txt && txt.length > 0 && txt.length <= 40) {
      return `${el.tagName.toLowerCase()}:has-text("${txt.replace(/"/g, '\\\\"')}")`;
    }
    const href = el.getAttribute('href');
    if (href) return `a[href="${href}"]`;
    return el.tagName.toLowerCase();
  }
  function visible(el) {
    const r = el.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) return false;
    const s = window.getComputedStyle(el);
    return s.visibility !== 'hidden' && s.display !== 'none';
  }
  const out = { buttons: {}, links: {}, inputs: {} };
  document.querySelectorAll('a, button, [role="button"], input').forEach(el => {
    if (!visible(el)) return;
    const sel = bestSelector(el);
    const label = (el.getAttribute('aria-label') || el.innerText || el.value || el.placeholder || '').trim().slice(0, 80);
    if (!label) return;
    const key = label.toLowerCase().replace(/[^a-z0-9]+/g, '_').slice(0, 60);
    if (!key) return;
    const tag = el.tagName.toLowerCase();
    if (tag === 'a') out.links[key] = sel;
    else if (tag === 'input') out.inputs[key] = sel;
    else out.buttons[key] = sel;
  });
  return out;
})();
"""


# ── Pure helpers (unit-tested) ───────────────────────────────────────────────

def _extract_screen_from_url(url: str) -> Optional[str]:
    """Return the .aspx screen name from a URL, or None for non-.aspx URLs.

    Examples (covered by tests):
      http://app/FrmAdministrador.aspx?q=1 → "FrmAdministrador.aspx"
      http://app/static/bundle.js          → None
      http://app/                          → None
    """
    if not url:
        return None
    # Strip query string and fragment
    clean = url.split("?", 1)[0].split("#", 1)[0]
    # Strip trailing slash
    clean = clean.rstrip("/")
    # Take the last path segment
    seg = clean.rsplit("/", 1)[-1]
    if seg.lower().endswith(".aspx"):
        return seg
    return None


def _dedupe_consecutive(items: list[str]) -> list[str]:
    """Collapse consecutive duplicates: ['A','A','B','B','C'] → ['A','B','C']."""
    out: list[str] = []
    for item in items:
        if not item:
            continue
        if not out or out[-1] != item:
            out.append(item)
    return out


def _now_iso() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def _build_session_payload(
    *,
    goal: str,
    started_at: str,
    navigation_path: list[str],
    transitions: list[dict],
    discovered_selectors: dict[str, dict[str, str]],
    form_fields: dict[str, dict[str, str]],
    request_log: list[dict],
    inferred_goal_action: str = "",
) -> dict:
    """Assemble the canonical session.json payload (also used by tests)."""
    return {
        "schema_version": _SCHEMA_VERSION,
        "tool_version": _TOOL_VERSION,
        "recorded_at": started_at,
        "goal": goal or "",
        "inferred_goal_action": inferred_goal_action,
        "navigation_path": navigation_path,
        "transitions": transitions,
        "discovered_selectors": discovered_selectors,
        "form_fields": form_fields,
        "request_log": request_log,
    }


# ── Recording session ────────────────────────────────────────────────────────

class _RecorderState:
    """Mutable state accumulated by Playwright event handlers during a run."""

    def __init__(self) -> None:
        self.navigation_path: list[str] = []
        self.transitions: list[dict] = []
        self.discovered_selectors: dict[str, dict[str, str]] = {}
        self.form_fields: dict[str, dict[str, str]] = {}
        self.request_log: list[dict] = []
        # Last interaction observed via the injected mousedown listener.
        # Consumed by the next framenavigated event to attribute the
        # transition to a (selector, label) pair.
        self.last_interaction: Optional[dict] = None
        self.stop_requested: bool = False

    def record_screen(self, screen: str) -> Optional[str]:
        prev = self.navigation_path[-1] if self.navigation_path else None
        if prev == screen:
            return None
        self.navigation_path.append(screen)
        return prev

    def record_transition(self, prev: str, curr: str) -> None:
        trigger_type = "navigation"
        trigger_selector = ""
        trigger_label = ""
        if self.last_interaction:
            trigger_type = "click"
            trigger_selector = self.last_interaction.get("selector") or ""
            trigger_label = self.last_interaction.get("label") or ""
            self.last_interaction = None
        self.transitions.append({
            "from": prev,
            "to": curr,
            "trigger_type": trigger_type,
            "trigger_selector": trigger_selector,
            "trigger_label": trigger_label,
        })

    def merge_snapshot(self, screen: str, snapshot: dict) -> None:
        bucket = self.discovered_selectors.setdefault(screen, {})
        for kind in ("buttons", "links"):
            for key, sel in (snapshot.get(kind) or {}).items():
                # Keep the first-seen selector (most stable: the one present
                # when the operator first landed on the screen).
                bucket.setdefault(key, sel)
        inputs = snapshot.get("inputs") or {}
        if inputs:
            self.form_fields.setdefault(screen, {}).update(inputs)


async def _run_recording(*, goal: str, base_url: str, user: str, password: str,
                         start_url: Optional[str], background: bool) -> Optional[dict]:
    """Drive a Playwright headed browser and accumulate state until Ctrl+C."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.error("playwright not installed. Run: pip install playwright && playwright install chromium")
        return None

    state = _RecorderState()
    started_at = _now_iso()
    headless = os.environ.get("STACKY_QA_UAT_HEADLESS", "0") != "0"

    # Wire SIGINT to flip stop flag rather than kill the process — we want to
    # close Playwright cleanly so the trace is flushed and JSON is written.
    loop = asyncio.get_event_loop()
    stop_event = asyncio.Event()

    def _request_stop(*_args) -> None:
        if not stop_event.is_set():
            sys.stderr.write("\n[recorder] Stop requested — closing browser and writing session.json...\n")
            stop_event.set()

    # On Windows, add_signal_handler is unsupported for SIGINT in ProactorLoop;
    # fall back to plain signal.signal which still triggers KeyboardInterrupt.
    try:
        loop.add_signal_handler(signal.SIGINT, _request_stop)
    except (NotImplementedError, RuntimeError):
        signal.signal(signal.SIGINT, lambda *_: _request_stop())

    target_url = start_url or (base_url.rstrip("/") + _LOGIN_URL_SUFFIX)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context()
        page = await context.new_page()

        # Re-inject the listener after every navigation; SPA-style navigations
        # would otherwise lose it, and ASP.NET full-page reloads always do.
        async def _on_dom_loaded() -> None:
            try:
                await page.evaluate(_RECORDER_LISTENER_JS)
            except Exception as exc:
                logger.debug("recorder: listener injection failed: %s", exc)

        page.on("domcontentloaded", lambda _: asyncio.create_task(_on_dom_loaded()))

        # Capture every navigation. Ignore non-aspx URLs (assets, API calls).
        def _on_framenavigated(frame) -> None:
            if frame != page.main_frame:
                return
            screen = _extract_screen_from_url(frame.url)
            if not screen:
                return
            prev = state.record_screen(screen)
            if prev:
                state.record_transition(prev, screen)

        page.on("framenavigated", _on_framenavigated)

        # POST requests = form submits. Useful for distinguishing real
        # navigations from incidental link clicks. We log URL+method only
        # (no body) to avoid leaking credentials/PII.
        def _on_request(request) -> None:
            if request.method == "POST":
                state.request_log.append({
                    "ts": int(time.time() * 1000),
                    "method": request.method,
                    "url": request.url,
                })

        page.on("request", _on_request)

        # Initial navigation + login
        try:
            await page.goto(target_url, wait_until="load", timeout=20000)
        except Exception as exc:
            logger.error("recorder: failed to open %s: %s", target_url, exc)
            await browser.close()
            return None

        # Auto-login if we landed on the login page (we usually do).
        if "FrmLogin" in (page.url or ""):
            try:
                await page.fill(_LOGIN_USER_SEL, user, timeout=10000)
                await page.fill(_LOGIN_PASS_SEL, password)
                await page.click(_LOGIN_BTN_SEL)
                await page.wait_for_load_state("load", timeout=20000)
            except Exception as exc:
                logger.error("recorder: login failed: %s", exc)
                await browser.close()
                return None

        # Ensure FrmLogin is the first hop in the path even if Playwright fired
        # the framenavigated event before we attached the listener.
        if not state.navigation_path or state.navigation_path[0] != "FrmLogin.aspx":
            state.navigation_path.insert(0, "FrmLogin.aspx")

        if not background:
            sys.stderr.write(
                "\n[recorder] Browser ready. Navegá libremente hasta el destino.\n"
                "[recorder] Cuando termines: cerrá la ventana o presioná Ctrl+C en esta terminal.\n\n"
            )

        # Background tasks: snapshot loop + interaction drain.
        async def _snapshot_loop() -> None:
            while not stop_event.is_set():
                try:
                    current_screen = _extract_screen_from_url(page.url) or ""
                    if current_screen:
                        snap = await page.evaluate(_SNAPSHOT_JS)
                        if isinstance(snap, dict):
                            state.merge_snapshot(current_screen, snap)
                        # Drain interaction events captured by the injected listener.
                        events = await page.evaluate(
                            "(() => { const e = window.__stackyRecorderEvents || []; window.__stackyRecorderEvents = []; return e; })()"
                        )
                        if events:
                            # Keep the most recent interaction — the one that
                            # most likely triggered the next navigation.
                            state.last_interaction = events[-1]
                except Exception as exc:
                    logger.debug("recorder: snapshot tick error: %s", exc)
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=_SNAPSHOT_INTERVAL_S)
                except asyncio.TimeoutError:
                    continue

        snapshot_task = asyncio.create_task(_snapshot_loop())

        # Detect manual browser close as a stop signal.
        page.on("close", lambda _: stop_event.set())
        context.on("close", lambda _: stop_event.set())

        try:
            await stop_event.wait()
        except KeyboardInterrupt:
            stop_event.set()

        snapshot_task.cancel()
        try:
            await snapshot_task
        except (asyncio.CancelledError, Exception):
            pass

        try:
            await browser.close()
        except Exception:
            pass

    # Final pass: dedupe path (snapshot loop may have raced consecutive duplicates).
    state.navigation_path = _dedupe_consecutive(state.navigation_path)

    return _build_session_payload(
        goal=goal,
        started_at=started_at,
        navigation_path=state.navigation_path,
        transitions=state.transitions,
        discovered_selectors=state.discovered_selectors,
        form_fields=state.form_fields,
        request_log=state.request_log,
    )


# ── Persistence + learner handoff ────────────────────────────────────────────

def _write_session(payload: dict) -> Path:
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = _RECORDINGS_DIR / ts
    out_dir.mkdir(parents=True, exist_ok=True)
    session_file = out_dir / "session.json"
    session_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    # Refresh the convenience pointer for `--session evidence/recordings/latest/`.
    latest = _RECORDINGS_DIR / "latest"
    try:
        if latest.is_symlink() or latest.exists():
            try:
                latest.unlink()
            except Exception:
                pass
        try:
            latest.symlink_to(out_dir, target_is_directory=True)
        except (OSError, NotImplementedError):
            # Windows without symlink privileges: write a plain pointer file.
            (latest.parent / "latest.txt").write_text(str(out_dir), encoding="utf-8")
    except Exception as exc:
        logger.debug("recorder: could not refresh 'latest' pointer: %s", exc)

    return session_file


def _invoke_learner(session_dir: Path, background: bool) -> int:
    """Forward the recorded session into navigation_graph_learner.py --session --apply."""
    cmd = [
        sys.executable,
        str(_TOOL_ROOT / "navigation_graph_learner.py"),
        "--session", str(session_dir),
        "--apply",
    ]
    if background:
        cmd.append("--background")
    logger.info("recorder: invoking learner: %s", " ".join(cmd))
    try:
        result = subprocess.run(cmd, cwd=str(_TOOL_ROOT))
        return result.returncode
    except Exception as exc:
        logger.error("recorder: learner invocation failed: %s", exc)
        return 1


# ── Main ──────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Record a free-form Agenda Web session for demo-driven learning "
            "(QA UAT Agent Fase 5)."
        ),
    )
    p.add_argument("--goal", default="",
                   help="Free-text description of what you intend to demo (saved into session.json).")
    p.add_argument("--url", default=None,
                   help="Initial URL. Defaults to AGENDA_WEB_BASE_URL + /FrmLogin.aspx.")
    p.add_argument("--no-learn", action="store_true",
                   help="Skip the post-recording navigation_graph_learner --session --apply call.")
    p.add_argument("--background", action="store_true",
                   help="Suppress operator instructions and reduce log verbosity.")
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    logging.basicConfig(
        level=logging.WARNING if args.background else logging.INFO,
        stream=sys.stderr,
        format="%(levelname)s %(name)s: %(message)s",
    )

    base_url = os.environ.get("AGENDA_WEB_BASE_URL", "").strip()
    user = os.environ.get("AGENDA_WEB_USER", "").strip()
    password = os.environ.get("AGENDA_WEB_PASS", "").strip()
    if not base_url or not user or not password:
        sys.stderr.write(
            "ERROR: required env vars AGENDA_WEB_BASE_URL, AGENDA_WEB_USER, AGENDA_WEB_PASS must be set.\n"
            "       Source Tools/Stacky/.secrets/agenda_web.env or export them in your shell.\n"
        )
        sys.exit(1)

    payload = asyncio.run(_run_recording(
        goal=args.goal,
        base_url=base_url,
        user=user,
        password=password,
        start_url=args.url,
        background=args.background,
    ))
    if payload is None:
        sys.exit(1)

    # [Fase 7] Infer goal_action from the recorded navigation_path when the
    # operator did not specify --goal or when the goal description is generic.
    # Stored in session.json as "inferred_goal_action" for downstream use by
    # navigation_graph_learner and the orchestrator agent.
    inferred_goal_action = ""
    nav_path = payload.get("navigation_path") or []
    if len(nav_path) >= 2:
        try:
            from intent_inferrer import infer_goal_from_path
            infer_result = infer_goal_from_path(nav_path)
            if infer_result.ok and infer_result.goal_action and infer_result.confidence != "unknown":
                inferred_goal_action = infer_result.goal_action
                logger.info(
                    "recorder: inferred goal_action=%r (conf=%s)",
                    inferred_goal_action, infer_result.confidence,
                )
            else:
                logger.debug(
                    "recorder: inferrer returned no usable label (conf=%s)",
                    getattr(infer_result, 'confidence', '?'),
                )
        except Exception as exc:
            logger.debug("recorder: intent_inferrer not available: %s", exc)

    # Inject inferred_goal_action into the payload before persisting.
    payload["inferred_goal_action"] = inferred_goal_action

    session_file = _write_session(payload)
    print(json.dumps({
        "ok": True,
        "session_file": str(session_file),
        "navigation_path": payload["navigation_path"],
        "transitions": len(payload["transitions"]),
        "discovered_selectors_screens": list(payload["discovered_selectors"].keys()),
    }, ensure_ascii=False, indent=2))

    if not args.no_learn:
        rc = _invoke_learner(session_file.parent, background=args.background)
        # Treat learner returning "no new edges" as a soft warning, not an error.
        sys.exit(0 if rc in (0, 2) else rc)
    sys.exit(0)


if __name__ == "__main__":
    main()
