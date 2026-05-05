"""
path_planner.py — Navigation path planner for Agenda Web.

Fase 2 of the QA UAT Agent free-form improvement plan.

Given a goal (target screen or goal_action label) and an optional entry screen,
computes the optimal navigation_path[] to inject into intent_spec.json.

The planner uses BFS over the static navigation_graph so that:
  1. The path is always the SHORTEST sequence of screens.
  2. FrmLogin.aspx is automatically prepended when no session is assumed.
  3. PopUp screens are included in the path when the goal IS a popup
     (the compiler needs to know the parent screen to navigate first).
  4. If the target is not reachable from the entry, the planner falls back
     to heuristic defaults per screen category.

PUBLIC API:
  plan(goal_action, entry_screen, assume_logged_in) -> PlanResult
  plan_from_target(target_screen, entry_screen, assume_logged_in) -> PlanResult

CLI:
  python path_planner.py --goal crear_compromiso_pago [--entry FrmBusqueda.aspx]
  python path_planner.py --target PopUpCompromisos.aspx
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from navigation_graph import (
    GRAPH,
    NavEdge,
    GOAL_ACTION_TARGETS,
    get_edges,
    target_for_goal,
)

logger = logging.getLogger("stacky.qa_uat.path_planner")

_TOOL_VERSION = "1.0.0"

# Default entry point after login — first screen most users see.
_DEFAULT_POST_LOGIN = "FrmAgenda.aspx"
_LOGIN_SCREEN = "FrmLogin.aspx"


@dataclass
class PlanResult:
    """Output of a planning request."""
    ok: bool
    path: list[str]                 # ordered navigation_path
    target_screen: str              # the resolved goal/target screen
    entry_screen: str               # the effective entry screen used
    goal_action: str = ""           # the goal_action that triggered the plan
    source: str = "graph_bfs"       # "graph_bfs" | "heuristic" | "direct"
    hops: int = 0                   # number of navigation steps
    edges: list[dict] = field(default_factory=list)  # edge labels along path
    warning: str = ""               # non-empty when a fallback was used

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "path": self.path,
            "target_screen": self.target_screen,
            "entry_screen": self.entry_screen,
            "goal_action": self.goal_action,
            "source": self.source,
            "hops": self.hops,
            "edges": self.edges,
            "warning": self.warning,
        }


# ── Public API ────────────────────────────────────────────────────────────────

def plan(
    goal_action: str,
    entry_screen: Optional[str] = None,
    assume_logged_in: bool = False,
) -> PlanResult:
    """Plan a navigation path for a given goal_action.

    Resolves goal_action → target_screen via GOAL_ACTION_TARGETS, then calls
    plan_from_target().

    Args:
        goal_action:       Normalized label from intent_spec.goal_action.
        entry_screen:      Where the session starts (post-login). None = default.
        assume_logged_in:  If True, skip login screen in the path.

    Returns:
        PlanResult with the full navigation_path[].
    """
    target = target_for_goal(goal_action)
    if target is None:
        # Unknown goal — return minimal path with a warning
        logger.warning(
            "path_planner: unknown goal_action %r — using default path", goal_action
        )
        effective_entry = entry_screen or _DEFAULT_POST_LOGIN
        path = _prepend_login(
            [effective_entry], assume_logged_in
        )
        return PlanResult(
            ok=True,
            path=path,
            target_screen=effective_entry,
            entry_screen=effective_entry,
            goal_action=goal_action,
            source="heuristic",
            hops=0,
            warning=f"Unknown goal_action '{goal_action}' — no mapping in GOAL_ACTION_TARGETS. "
                    f"Using entry screen as both start and target. "
                    f"Add the mapping to navigation_graph.GOAL_ACTION_TARGETS.",
        )

    result = plan_from_target(
        target_screen=target,
        entry_screen=entry_screen,
        assume_logged_in=assume_logged_in,
    )
    result.goal_action = goal_action
    return result


def plan_from_target(
    target_screen: str,
    entry_screen: Optional[str] = None,
    assume_logged_in: bool = False,
) -> PlanResult:
    """Plan the shortest navigation path to reach `target_screen`.

    The BFS starts from `entry_screen` (default: FrmAgenda.aspx).
    FrmLogin.aspx is prepended unless `assume_logged_in=True`.

    If target is already the entry screen, returns a single-element path.
    If no path is found via BFS, falls back to the heuristic default.
    """
    effective_entry = entry_screen or _DEFAULT_POST_LOGIN

    # Trivial case: already there
    if effective_entry == target_screen:
        path = _prepend_login([effective_entry], assume_logged_in)
        return PlanResult(
            ok=True,
            path=path,
            target_screen=target_screen,
            entry_screen=effective_entry,
            source="direct",
            hops=0,
        )

    # BFS
    bfs_path, bfs_edges = _bfs(effective_entry, target_screen)
    if bfs_path:
        full_path = _prepend_login(bfs_path, assume_logged_in)
        return PlanResult(
            ok=True,
            path=full_path,
            target_screen=target_screen,
            entry_screen=effective_entry,
            source="graph_bfs",
            hops=len(bfs_path) - 1,
            edges=bfs_edges,
        )

    # Fallback: heuristic — try standard hub screens
    fallback_path = _heuristic_path(effective_entry, target_screen)
    full_path = _prepend_login(fallback_path, assume_logged_in)
    return PlanResult(
        ok=True,
        path=full_path,
        target_screen=target_screen,
        entry_screen=effective_entry,
        source="heuristic",
        hops=len(fallback_path) - 1,
        warning=f"No BFS path found from '{effective_entry}' to '{target_screen}'. "
                f"Using heuristic fallback. Verify navigation_graph.py has the correct edges.",
    )


# ── BFS ───────────────────────────────────────────────────────────────────────

def _bfs(
    start: str,
    goal: str,
    max_depth: int = 8,
) -> tuple[list[str], list[dict]]:
    """BFS from start to goal in the navigation graph.

    Returns (path_of_screens, list_of_edge_dicts) or ([], []) if not found.
    `max_depth` guards against very long paths (login flows create cycles).
    """
    # (current_screen, path_so_far, edges_so_far)
    queue: deque[tuple[str, list[str], list[dict]]] = deque()
    queue.append((start, [start], []))
    visited: set[str] = {start}

    while queue:
        current, path, edges = queue.popleft()
        if len(path) > max_depth:
            continue

        for edge in get_edges(current):
            nxt = edge.target
            if nxt == goal:
                return path + [nxt], edges + [_edge_to_dict(edge)]
            if nxt not in visited:
                visited.add(nxt)
                queue.append((
                    nxt,
                    path + [nxt],
                    edges + [_edge_to_dict(edge)],
                ))

    return [], []


def _edge_to_dict(edge: NavEdge) -> dict:
    return {
        "target": edge.target,
        "action": edge.action,
        "label": edge.label,
        "is_popup": edge.is_popup,
    }


# ── Heuristics ────────────────────────────────────────────────────────────────

# Hub screens that many flows pass through. Used as intermediate waypoints
# when BFS can't find a direct path (typically for screens not yet in the graph).
_HUBS = [
    "FrmAgenda.aspx",
    "FrmBusqueda.aspx",
    "FrmDetalleClie.aspx",
    "FrmDetalleLote.aspx",
    "Default.aspx",
]

def _heuristic_path(entry: str, target: str) -> list[str]:
    """Build a heuristic path for unknown/disconnected target screens.

    Strategy:
    1. Try BFS from each hub to the target.
    2. If none work, return [entry, target] as a 2-step guess.
    """
    # Try direct from entry via one hub
    for hub in _HUBS:
        if hub == entry:
            continue
        hub_to_target, _ = _bfs(hub, target)
        if hub_to_target:
            entry_to_hub, _ = _bfs(entry, hub)
            if entry_to_hub:
                # Merge: entry → … → hub → … → target (deduplicate hub)
                return entry_to_hub + hub_to_target[1:]
            # Can't reach hub from entry — just use hub directly
            return [hub] + hub_to_target[1:]

    # Last resort: assume 2-step path
    return [entry, target]


def _prepend_login(path: list[str], assume_logged_in: bool) -> list[str]:
    """Prepend the login screen unless already present or assume_logged_in."""
    if assume_logged_in:
        return path
    if path and path[0] in (_LOGIN_SCREEN, "Login.aspx"):
        return path
    return [_LOGIN_SCREEN] + path


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    args = _parse_args()
    logging.basicConfig(
        level=logging.DEBUG if not args.background else logging.WARNING,
        stream=sys.stderr,
        format="%(levelname)s %(name)s: %(message)s",
    )

    if args.goal:
        result = plan(
            goal_action=args.goal,
            entry_screen=args.entry or None,
            assume_logged_in=args.assume_logged_in,
        )
    elif args.target:
        result = plan_from_target(
            target_screen=args.target,
            entry_screen=args.entry or None,
            assume_logged_in=args.assume_logged_in,
        )
    else:
        sys.stderr.write("error: --goal or --target required\n")
        sys.exit(1)

    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    sys.exit(0 if result.ok else 1)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Navigation path planner for Agenda Web (Fase 2)."
    )
    source = p.add_mutually_exclusive_group()
    source.add_argument("--goal", default=None,
                        help="Goal action label (e.g. crear_compromiso_pago).")
    source.add_argument("--target", default=None,
                        help="Target screen filename (e.g. PopUpCompromisos.aspx).")
    p.add_argument("--entry", default=None,
                   help="Entry screen after login (default: FrmAgenda.aspx).")
    p.add_argument("--assume-logged-in", action="store_true",
                   help="Omit FrmLogin.aspx from the path.")
    p.add_argument("--background", action="store_true",
                   help="Suppress verbose output.")
    return p.parse_args()


if __name__ == "__main__":
    main()
