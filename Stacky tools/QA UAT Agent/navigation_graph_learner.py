"""
navigation_graph_learner.py — Automatic navigation graph expansion from test evidence.

Fase 4 of the QA UAT Agent free-form improvement plan, extended in Fase 5
with --session support to consume demo-recorded sessions.

Scans evidence directories produced by the QA UAT pipeline and extracts
navigation transitions observed during real Playwright test runs. Compares
observed transitions against the static navigation_graph.GRAPH and emits:

  1. cache/learned_edges.json  — all observed + proposed new edges (persisted).
     navigation_graph.py merges this file at import time when it exists.

  2. A summary report (stdout) with:
     - confirmed edges (already in static graph, count reinforced)
     - proposed edges (new transitions not in static graph)
     - unknown screens (observed in tests but not in SUPPORTED_SCREENS)

  3. (Fase 5 only, when --session is used) cache/discovered_selectors.json —
     element selectors captured during a recorded session, merged additively.

DESIGN:

  Static graph (navigation_graph.py) = hand-curated baseline.
  Learned edges (cache/learned_edges.json) = runtime observations, additive.

  The learner NEVER auto-modifies navigation_graph.py. Use --promote to
  generate a Python snippet you can paste into _RAW_GRAPH manually.

SOURCES (in priority order):
  1. session.json (Fase 5) — explicit transitions captured by session_recorder.py
  2. scenarios.json — compiled scenarios with explicit pantalla/navigation_path
  3. *.spec.ts files — page.goto() + waitForURL() patterns
  4. ticket.json — navigation_path field in synthetic tickets (free-form runs)
  5. intent_spec.json — navigation_path auto-computed by path_planner (free-form)

PUBLIC API:
  scan(evidence_root, apply=False) -> ScanResult
  scan_session(session_dir, apply=False) -> ScanResult  (Fase 5)
  load_learned_edges() -> dict[str, list[dict]]  — edges indexed by source screen

CLI:
  python navigation_graph_learner.py [--evidence-dir evidence/] [--apply] [--promote] [--background]
  python navigation_graph_learner.py --session evidence/recordings/<ts>/ [--apply] [--show]
  python navigation_graph_learner.py --show   # show current learned_edges.json
  python navigation_graph_learner.py --clear  # remove learned_edges.json (reset)
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.qa_uat.nav_learner")

_TOOL_VERSION = "2.0.0"
# Bump to 2.0.0 = added scan_session() + cache/discovered_selectors.json
# write path. Backwards-compatible: scan() output unchanged for callers that
# don't pass --session. Schema of learned_edges.json also unchanged.
_TOOL_ROOT = Path(__file__).parent
_CACHE_DIR = _TOOL_ROOT / "cache"
_LEARNED_EDGES_PATH = _CACHE_DIR / "learned_edges.json"
_DISCOVERED_SELECTORS_PATH = _CACHE_DIR / "discovered_selectors.json"
_EVIDENCE_DIR = _TOOL_ROOT / "evidence"

# ── Patterns for extracting URLs from spec.ts files ──────────────────────────
#
# page.goto(`${BASE_URL}FrmLogin.aspx`, ...)
_GOTO_RE = re.compile(
    r'page\.goto\s*\(\s*[`\'"]?\$\{BASE_URL\}([^`\'"}\s]+\.aspx)',
    re.IGNORECASE,
)
# await page.waitForURL(/FrmAgenda/, ...)
_WAIT_URL_RE = re.compile(
    r'waitForURL\s*\(\s*/([^/]+)/',
    re.IGNORECASE,
)
# Screen: FrmAgenda.aspx  (comment at top of spec file)
_SCREEN_COMMENT_RE = re.compile(
    r'//\s*Screen:\s*(Frm\w+\.aspx|PopUp\w+\.aspx|Login\.aspx|Default\.aspx)',
    re.IGNORECASE,
)


# ── Result dataclass ─────────────────────────────────────────────────────────

@dataclass
class ObservedEdge:
    """A navigation transition extracted from test evidence."""
    source: str
    target: str
    action: str = "observed_navigate"
    observed_count: int = 1
    evidence_runs: list[str] = field(default_factory=list)
    already_in_graph: bool = False
    in_supported_screens: bool = True  # False = new unknown screen
    status: str = "proposed"  # "confirmed" | "proposed" | "unknown_screen"

    def key(self) -> tuple:
        return (self.source, self.target)

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "target": self.target,
            "action": self.action,
            "observed_count": self.observed_count,
            "evidence_runs": self.evidence_runs,
            "already_in_graph": self.already_in_graph,
            "in_supported_screens": self.in_supported_screens,
            "status": self.status,
        }


@dataclass
class ScanResult:
    """Output of a learning scan."""
    ok: bool
    scanned_runs: list[str] = field(default_factory=list)
    total_transitions_seen: int = 0
    confirmed: list[ObservedEdge] = field(default_factory=list)   # already in static graph
    proposed: list[ObservedEdge] = field(default_factory=list)    # new, safe to learn
    unknown_screens: list[ObservedEdge] = field(default_factory=list)  # not in SUPPORTED_SCREENS
    learned_edges_path: str = ""
    elapsed_ms: int = 0

    @property
    def new_edge_count(self) -> int:
        return len(self.proposed)

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "scanned_runs": self.scanned_runs,
            "total_transitions_seen": self.total_transitions_seen,
            "confirmed_count": len(self.confirmed),
            "proposed_count": len(self.proposed),
            "unknown_screen_count": len(self.unknown_screens),
            "confirmed": [e.to_dict() for e in self.confirmed],
            "proposed": [e.to_dict() for e in self.proposed],
            "unknown_screens": [e.to_dict() for e in self.unknown_screens],
            "learned_edges_path": self.learned_edges_path,
            "elapsed_ms": self.elapsed_ms,
        }


# ── Public API ────────────────────────────────────────────────────────────────

def scan(
    evidence_root: Optional[Path] = None,
    apply: bool = False,
    verbose: bool = True,
) -> ScanResult:
    """Scan evidence directories and extract observed navigation transitions.

    Args:
        evidence_root: Root dir containing evidence subdirs (ticket IDs, run IDs).
                       Defaults to evidence/ in the tool root.
        apply:         If True, write/merge findings into cache/learned_edges.json.
                       If False (default), dry-run only (findings printed, not saved).
        verbose:       Enable DEBUG logging.

    Returns:
        ScanResult with confirmed/proposed/unknown_screen edges.
    """
    started = time.time()
    evidence_root = evidence_root or _EVIDENCE_DIR

    # Import graph + screen catalogue (lazy to avoid circular import issues)
    from navigation_graph import GRAPH, get_edges
    from agenda_screens import is_supported, normalize

    # Build a fast lookup: (source, target) → True if edge already in GRAPH
    _graph_edges: set[tuple[str, str]] = set()
    for src, edges in GRAPH.items():
        for e in edges:
            _graph_edges.add((src, e.target))

    # Accumulate observed (source, target) pairs with counts
    observed: dict[tuple, ObservedEdge] = {}
    scanned_runs: list[str] = []

    if not evidence_root.is_dir():
        return ScanResult(
            ok=False,
            elapsed_ms=int((time.time() - started) * 1000),
        )

    for run_dir in sorted(evidence_root.iterdir()):
        if not run_dir.is_dir():
            continue
        run_name = run_dir.name
        if run_name.startswith("."):
            continue

        run_transitions: list[tuple[str, str]] = []
        run_transitions += _extract_from_scenarios(run_dir)
        run_transitions += _extract_from_spec_ts(run_dir)
        run_transitions += _extract_from_ticket_json(run_dir)

        if run_transitions:
            scanned_runs.append(run_name)
            for src, tgt in run_transitions:
                key = (src, tgt)
                if key in observed:
                    observed[key].observed_count += 1
                    if run_name not in observed[key].evidence_runs:
                        observed[key].evidence_runs.append(run_name)
                else:
                    in_src_supported = is_supported(src)
                    in_tgt_supported = is_supported(tgt)
                    in_graph = key in _graph_edges
                    if in_graph:
                        status = "confirmed"
                    elif in_src_supported and in_tgt_supported:
                        status = "proposed"
                    else:
                        status = "unknown_screen"
                    observed[key] = ObservedEdge(
                        source=src,
                        target=tgt,
                        action="observed_navigate",
                        observed_count=1,
                        evidence_runs=[run_name],
                        already_in_graph=in_graph,
                        in_supported_screens=(in_src_supported and in_tgt_supported),
                        status=status,
                    )
            logger.debug(
                "nav_learner: run %s → %d transitions extracted", run_name, len(run_transitions)
            )

    # Classify
    confirmed = [e for e in observed.values() if e.status == "confirmed"]
    proposed = [e for e in observed.values() if e.status == "proposed"]
    unknown = [e for e in observed.values() if e.status == "unknown_screen"]

    # Sort by observed_count descending (most frequent first)
    proposed.sort(key=lambda e: -e.observed_count)

    logger.info(
        "nav_learner: scanned %d runs | confirmed=%d proposed=%d unknown=%d",
        len(scanned_runs), len(confirmed), len(proposed), len(unknown),
    )

    learned_edges_path = ""
    if apply and proposed:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        learned_edges_path = str(_LEARNED_EDGES_PATH)
        _write_learned_edges(proposed, learned_edges_path=_LEARNED_EDGES_PATH)
        logger.info("nav_learner: wrote %d proposed edges to %s", len(proposed), _LEARNED_EDGES_PATH)
    elif apply and not proposed:
        logger.info("nav_learner: no new proposed edges — learned_edges.json unchanged")

    return ScanResult(
        ok=True,
        scanned_runs=scanned_runs,
        total_transitions_seen=sum(e.observed_count for e in observed.values()),
        confirmed=confirmed,
        proposed=proposed,
        unknown_screens=unknown,
        learned_edges_path=learned_edges_path,
        elapsed_ms=int((time.time() - started) * 1000),
    )


def scan_session(
    session_dir: Path,
    apply: bool = False,
    verbose: bool = True,
) -> ScanResult:
    """Scan a single recording produced by session_recorder.py (Fase 5).

    Reads ``<session_dir>/session.json``, converts the explicit transitions
    into ObservedEdge entries (sharing the same dataclass + persistence path
    as scan()), and — if apply=True — also merges the recorded
    ``discovered_selectors`` into ``cache/discovered_selectors.json``.

    Args:
        session_dir: Directory containing session.json. Typically
                     ``evidence/recordings/<timestamp>/``.
        apply:       If True, write proposed edges to learned_edges.json AND
                     merge discovered_selectors.json. If False, dry-run only.
        verbose:     Enable DEBUG logging.

    Returns:
        ScanResult with confirmed/proposed/unknown_screen edges. The
        ``scanned_runs`` field contains the single session directory name.
    """
    started = time.time()
    session_file = session_dir / "session.json"
    if not session_file.is_file():
        logger.error("nav_learner: no session.json in %s", session_dir)
        return ScanResult(ok=False, elapsed_ms=int((time.time() - started) * 1000))

    try:
        session_data = json.loads(session_file.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.error("nav_learner: failed to parse %s: %s", session_file, exc)
        return ScanResult(ok=False, elapsed_ms=int((time.time() - started) * 1000))

    from navigation_graph import GRAPH
    from agenda_screens import is_supported

    _graph_edges: set[tuple[str, str]] = set()
    for src, edges in GRAPH.items():
        for e in edges:
            _graph_edges.add((src, e.target))

    run_name = session_dir.name
    observed: dict[tuple, ObservedEdge] = {}

    # Source 1: explicit transitions[] from session.json (preferred — has
    # trigger selector + label that we want to preserve in the action field).
    for tr in session_data.get("transitions") or []:
        src = tr.get("from")
        tgt = tr.get("to")
        if not src or not tgt:
            continue
        key = (src, tgt)
        if key in observed:
            observed[key].observed_count += 1
            continue
        in_src = is_supported(src)
        in_tgt = is_supported(tgt)
        in_graph = key in _graph_edges
        status = (
            "confirmed" if in_graph
            else "proposed" if (in_src and in_tgt)
            else "unknown_screen"
        )
        action = "observed_navigate"
        label = (tr.get("trigger_label") or "").strip()
        if label:
            # Embed the demo-recorded label so the human reviewer (and the
            # learned_edges.json reader) sees what the operator clicked.
            action = f"recorded:{label[:40]}"
        observed[key] = ObservedEdge(
            source=src,
            target=tgt,
            action=action,
            observed_count=1,
            evidence_runs=[run_name],
            already_in_graph=in_graph,
            in_supported_screens=(in_src and in_tgt),
            status=status,
        )

    # Source 2: navigation_path (covers the case where transitions[] is empty
    # — e.g. a recording where the operator clicked but framenavigated didn't
    # fire because the page used pushState).
    nav_path = session_data.get("navigation_path") or []
    for i in range(1, len(nav_path)):
        src, tgt = nav_path[i - 1], nav_path[i]
        key = (src, tgt)
        if key in observed:
            continue
        in_src = is_supported(src)
        in_tgt = is_supported(tgt)
        in_graph = key in _graph_edges
        status = (
            "confirmed" if in_graph
            else "proposed" if (in_src and in_tgt)
            else "unknown_screen"
        )
        observed[key] = ObservedEdge(
            source=src,
            target=tgt,
            action="observed_navigate",
            observed_count=1,
            evidence_runs=[run_name],
            already_in_graph=in_graph,
            in_supported_screens=(in_src and in_tgt),
            status=status,
        )

    confirmed = [e for e in observed.values() if e.status == "confirmed"]
    proposed = [e for e in observed.values() if e.status == "proposed"]
    unknown = [e for e in observed.values() if e.status == "unknown_screen"]
    proposed.sort(key=lambda e: -e.observed_count)

    logger.info(
        "nav_learner: session %s → confirmed=%d proposed=%d unknown=%d",
        run_name, len(confirmed), len(proposed), len(unknown),
    )

    learned_edges_path = ""
    if apply:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        if proposed:
            learned_edges_path = str(_LEARNED_EDGES_PATH)
            _write_learned_edges(proposed, learned_edges_path=_LEARNED_EDGES_PATH)
            logger.info("nav_learner: wrote %d edges from session to %s", len(proposed), _LEARNED_EDGES_PATH)
        # Always persist selectors if present — even when no NEW edges, the
        # operator may have re-demoed a known path to refresh selector hints.
        sel_map = session_data.get("discovered_selectors") or {}
        if sel_map:
            _write_discovered_selectors(sel_map)

    return ScanResult(
        ok=True,
        scanned_runs=[run_name],
        total_transitions_seen=sum(e.observed_count for e in observed.values()),
        confirmed=confirmed,
        proposed=proposed,
        unknown_screens=unknown,
        learned_edges_path=learned_edges_path,
        elapsed_ms=int((time.time() - started) * 1000),
    )


def load_learned_edges() -> dict[str, list[dict]]:
    """Load cache/learned_edges.json if it exists.

    Returns a dict indexed by source screen → list of edge dicts.
    Returns {} if the file doesn't exist or is malformed.
    """
    if not _LEARNED_EDGES_PATH.is_file():
        return {}
    try:
        raw = json.loads(_LEARNED_EDGES_PATH.read_text(encoding="utf-8"))
        return raw.get("by_source", {})
    except Exception as exc:
        logger.warning("nav_learner: failed to load learned_edges.json: %s", exc)
        return {}


# ── Extraction helpers ────────────────────────────────────────────────────────

def _extract_from_scenarios(run_dir: Path) -> list[tuple[str, str]]:
    """Extract transitions from scenarios.json in a run directory.

    scenarios.json has a `pantalla` per scenario = the target screen.
    We generate (FrmLogin.aspx → pantalla) as the minimal transition path.
    """
    scenarios_file = run_dir / "scenarios.json"
    if not scenarios_file.is_file():
        return []

    try:
        data = json.loads(scenarios_file.read_text(encoding="utf-8"))
    except Exception:
        return []

    transitions: list[tuple[str, str]] = []
    seen_screens: set[str] = set()
    login_screen = "FrmLogin.aspx"

    for scenario in (data.get("scenarios") or []):
        pantalla = scenario.get("pantalla", "")
        if pantalla and pantalla not in seen_screens:
            seen_screens.add(pantalla)
            # Implicit: login → pantalla is always a transition
            transitions.append((login_screen, pantalla))

    return transitions


def _extract_from_spec_ts(run_dir: Path) -> list[tuple[str, str]]:
    """Extract transitions from *.spec.ts files in a run directory.

    Parses page.goto() and waitForURL() calls to build a sequence of
    screen visits per test file, then emits (prev_screen → curr_screen) pairs.
    """
    tests_dir = run_dir / "tests"
    if not tests_dir.is_dir():
        # Some runs store tests directly in run_dir
        tests_dir = run_dir

    transitions: list[tuple[str, str]] = []

    for spec_file in sorted(tests_dir.glob("*.spec.ts")):
        content = spec_file.read_text(encoding="utf-8", errors="replace")
        screens_in_file: list[str] = []

        # Primary screen from comment
        for m in _SCREEN_COMMENT_RE.finditer(content):
            screens_in_file.append(_normalize_screen(m.group(1)))

        # page.goto() calls
        for m in _GOTO_RE.finditer(content):
            screens_in_file.append(_normalize_screen(m.group(1)))

        # waitForURL() patterns
        for m in _WAIT_URL_RE.finditer(content):
            # Pattern like /FrmAgenda/ — extract the identifier
            pat = m.group(1)
            # Try to find the full screen name from SUPPORTED_SCREENS
            resolved = _resolve_partial_screen(pat)
            if resolved:
                screens_in_file.append(resolved)

        # Deduplicate consecutive duplicates (same screen twice = no transition)
        deduped: list[str] = []
        for s in screens_in_file:
            if s and (not deduped or deduped[-1] != s):
                deduped.append(s)

        # Emit (prev, curr) pairs
        for i in range(1, len(deduped)):
            transitions.append((deduped[i - 1], deduped[i]))

    return transitions


def _extract_from_ticket_json(run_dir: Path) -> list[tuple[str, str]]:
    """Extract transitions from navigation_path in ticket.json or intent_spec.json."""
    transitions: list[tuple[str, str]] = []

    for filename in ("ticket.json", "intent_spec.json"):
        f = run_dir / filename
        if not f.is_file():
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            nav_path: list[str] = (
                data.get("navigation_path")
                or data.get("analisis_tecnico_parsed", {}).get("navigation_path")
                or []
            )
            for i in range(1, len(nav_path)):
                transitions.append((nav_path[i - 1], nav_path[i]))
        except Exception as exc:
            logger.debug("nav_learner: skipping %s (%s)", f, exc)

    return transitions


# ── Persistence ───────────────────────────────────────────────────────────────

def _write_learned_edges(
    proposed: list[ObservedEdge],
    learned_edges_path: Path,
) -> None:
    """Write/merge proposed edges into learned_edges.json."""
    # Load existing
    existing: dict = {}
    if learned_edges_path.is_file():
        try:
            existing = json.loads(learned_edges_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    existing_by_source: dict[str, list[dict]] = existing.get("by_source", {})

    # Merge proposed edges
    for edge in proposed:
        src = edge.source
        tgt = edge.target
        # Check if this exact edge already exists in learned_edges
        existing_edges = existing_by_source.setdefault(src, [])
        existing_entry = next((e for e in existing_edges if e.get("target") == tgt), None)
        if existing_entry:
            # Update count and evidence_runs
            existing_entry["observed_count"] = (
                existing_entry.get("observed_count", 0) + edge.observed_count
            )
            for run in edge.evidence_runs:
                if run not in existing_entry.get("evidence_runs", []):
                    existing_entry.setdefault("evidence_runs", []).append(run)
        else:
            existing_edges.append(edge.to_dict())

    # Rebuild output
    output = {
        "schema_version": "1.0",
        "generated_at": _now_iso(),
        "tool_version": _TOOL_VERSION,
        "description": (
            "Edges learned from QA UAT test evidence. "
            "Loaded by navigation_graph.py at import time to extend the static graph. "
            "Human-reviewed before promotion to navigation_graph._RAW_GRAPH."
        ),
        "by_source": existing_by_source,
        "total_learned": sum(len(v) for v in existing_by_source.values()),
    }
    learned_edges_path.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _write_discovered_selectors(by_screen: dict[str, dict[str, str]]) -> None:
    """Merge session-discovered selectors into cache/discovered_selectors.json.

    Schema:
      { "schema_version": "1.0",
        "generated_at": "...",
        "by_screen": { screen → { element_name → css_selector } } }

    Merge policy: existing selectors win (first-seen-stable). New element keys
    are added. This guards against a regressing recording where a stable
    selector gets overwritten by a flakier one.
    """
    existing: dict = {}
    if _DISCOVERED_SELECTORS_PATH.is_file():
        try:
            existing = json.loads(_DISCOVERED_SELECTORS_PATH.read_text(encoding="utf-8"))
        except Exception:
            existing = {}
    existing_by_screen: dict[str, dict[str, str]] = existing.get("by_screen", {})
    for screen, sel_map in by_screen.items():
        bucket = existing_by_screen.setdefault(screen, {})
        for key, sel in sel_map.items():
            bucket.setdefault(key, sel)

    output = {
        "schema_version": "1.0",
        "generated_at": _now_iso(),
        "tool_version": _TOOL_VERSION,
        "description": (
            "Element selectors captured by session_recorder.py during demo "
            "sessions. Merged additively: first-seen selector wins. Consumed "
            "by ui_map_builder/playwright_test_generator as a hint cache."
        ),
        "by_screen": existing_by_screen,
    }
    _DISCOVERED_SELECTORS_PATH.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info(
        "nav_learner: discovered selectors merged → %s (%d screens)",
        _DISCOVERED_SELECTORS_PATH, len(existing_by_screen),
    )


# ── Promote to navigation_graph.py ───────────────────────────────────────────

def promote_to_graph_snippet(proposed: list[ObservedEdge]) -> str:
    """Generate a Python code snippet for pasting into navigation_graph._RAW_GRAPH.

    This is for human review — the agent should NOT auto-patch navigation_graph.py.
    """
    if not proposed:
        return "# No proposed edges to promote."

    lines = ["# ── Learned edges (generated by navigation_graph_learner.py) ────────────"]
    by_source: dict[str, list[ObservedEdge]] = {}
    for edge in proposed:
        by_source.setdefault(edge.source, []).append(edge)

    for src, edges in sorted(by_source.items()):
        lines.append(f'    # {src}')
        lines.append(f'    "{src}": [')
        lines.append(f'        # ... (existing edges) ...')
        for e in edges:
            lines.append(
                f'        ("{e.target}", "observed_navigate", '
                f'"observed in {len(e.evidence_runs)} run(s)", False, '
                f'{"True" if "PopUp" in e.target else "False"}),  '
                f'# seen {e.observed_count}x'
            )
        lines.append(f'    ],')
    return "\n".join(lines)


# ── Screen normalization helpers ──────────────────────────────────────────────

def _normalize_screen(raw: str) -> str:
    """Normalize a screen name: strip whitespace, ensure .aspx suffix."""
    s = raw.strip()
    if s and not s.lower().endswith(".aspx"):
        s = s + ".aspx"
    return s


# Cache of partial name → full screen name built once from SUPPORTED_SCREENS
_PARTIAL_CACHE: dict[str, str] = {}

def _resolve_partial_screen(partial: str) -> Optional[str]:
    """Resolve a partial screen name (e.g. 'FrmAgenda') to full canonical name."""
    if not _PARTIAL_CACHE:
        try:
            from agenda_screens import SUPPORTED_SCREENS
            for screen in SUPPORTED_SCREENS:
                base = screen.lower().replace(".aspx", "")
                _PARTIAL_CACHE[base] = screen
                _PARTIAL_CACHE[screen.lower()] = screen
        except ImportError:
            pass

    key = partial.strip().lower().replace(".aspx", "")
    return _PARTIAL_CACHE.get(key)


def _now_iso() -> str:
    import datetime
    return datetime.datetime.now().isoformat(timespec="seconds")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    args = _parse_args()
    logging.basicConfig(
        level=logging.DEBUG if not args.background else logging.WARNING,
        stream=sys.stderr,
        format="%(levelname)s %(name)s: %(message)s",
    )

    if args.show and not args.session:
        if _LEARNED_EDGES_PATH.is_file():
            print(_LEARNED_EDGES_PATH.read_text(encoding="utf-8"))
        else:
            print('{"message": "No learned_edges.json found. Run --apply first."}')
        sys.exit(0)

    if args.clear:
        if _LEARNED_EDGES_PATH.is_file():
            _LEARNED_EDGES_PATH.unlink()
            print(f"Deleted: {_LEARNED_EDGES_PATH}")
        else:
            print("No learned_edges.json to clear.")
        sys.exit(0)

    if args.session:
        # Fase 5 path: consume a single recorded session instead of scanning
        # the whole evidence/ tree. Resolves the 'latest' convenience pointer
        # written by session_recorder.py if the user passed it.
        session_dir = Path(args.session)
        if session_dir.name == "latest" and not session_dir.exists():
            pointer = session_dir.parent / "latest.txt"
            if pointer.is_file():
                session_dir = Path(pointer.read_text(encoding="utf-8").strip())
        result = scan_session(
            session_dir=session_dir,
            apply=args.apply,
            verbose=not args.background,
        )
    else:
        evidence_root = Path(args.evidence_dir) if args.evidence_dir else _EVIDENCE_DIR
        result = scan(
            evidence_root=evidence_root,
            apply=args.apply,
            verbose=not args.background,
        )

    if args.promote and result.proposed:
        print("\n# ── PROMOTE SNIPPET ─────────────────────────────────────────────")
        print(promote_to_graph_snippet(result.proposed))
        print("# ── END SNIPPET ─────────────────────────────────────────────────\n")

    # Summary output
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))

    if not args.background:
        _print_summary(result)

    # Exit code semantics:
    #   0  → ok with at least one proposed edge (or confirmed-only scan)
    #   1  → hard error (could not parse session/evidence)
    #   2  → ok but no proposed/confirmed edges — soft warning consumed by
    #        session_recorder.py to surface "session yielded no learning"
    if not result.ok:
        sys.exit(1)
    if not result.proposed and not result.confirmed:
        sys.exit(2)
    sys.exit(0)


def _print_summary(result: ScanResult) -> None:
    """Print a human-readable summary to stderr."""
    sys.stderr.write("\n")
    sys.stderr.write(f"  Scanned runs:  {len(result.scanned_runs)}\n")
    sys.stderr.write(f"  Transitions:   {result.total_transitions_seen}\n")
    sys.stderr.write(f"  Confirmed:     {len(result.confirmed)} (already in static graph)\n")
    if result.proposed:
        sys.stderr.write(f"  Proposed NEW:  {len(result.proposed)}\n")
        for e in result.proposed[:10]:
            sys.stderr.write(
                f"    {e.source} → {e.target}  (seen {e.observed_count}x in {e.evidence_runs})\n"
            )
        if len(result.proposed) > 10:
            sys.stderr.write(f"    ... and {len(result.proposed) - 10} more\n")
    else:
        sys.stderr.write("  Proposed NEW:  0 (all observed transitions already in static graph)\n")
    if result.unknown_screens:
        sys.stderr.write(f"  Unknown screens: {len(result.unknown_screens)}\n")
        for e in result.unknown_screens[:5]:
            sys.stderr.write(f"    {e.source} → {e.target} (screen not in SUPPORTED_SCREENS)\n")
    if result.learned_edges_path:
        sys.stderr.write(f"\n  Learned edges written to: {result.learned_edges_path}\n")
    else:
        sys.stderr.write("\n  [Dry-run] Use --apply to save proposed edges to cache/learned_edges.json\n")


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Scan QA UAT evidence directories and learn new navigation edges. "
            "Fase 4 — Navigation Graph Auto-Expansion."
        )
    )
    p.add_argument("--evidence-dir", default=None,
                   help="Root directory containing evidence subdirs (default: evidence/).")
    p.add_argument("--session", default=None,
                   help=(
                       "Path to a recorded session directory containing session.json "
                       "(produced by session_recorder.py). Mutually exclusive with "
                       "--evidence-dir scan."
                   ))
    p.add_argument("--apply", action="store_true",
                   help="Write proposed new edges to cache/learned_edges.json.")
    p.add_argument("--promote", action="store_true",
                   help="Print a Python code snippet for pasting into navigation_graph._RAW_GRAPH.")
    p.add_argument("--show", action="store_true",
                   help="Print the current contents of cache/learned_edges.json.")
    p.add_argument("--clear", action="store_true",
                   help="Delete cache/learned_edges.json (reset learned state).")
    p.add_argument("--background", action="store_true",
                   help="Suppress verbose output.")
    return p.parse_args()


if __name__ == "__main__":
    main()
