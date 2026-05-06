"""
graph_promoter.py — Promote stable learned edges to the static navigation graph.

Fase 6 of the QA UAT Agent autonomy roadmap.

Reads cache/learned_edges.json, identifies edges whose observed_count has
crossed the "stable" threshold (>= 5 by default), and generates a Python
snippet suitable for pasting into navigation_graph._RAW_GRAPH.

Optionally opens an Azure DevOps PR so a human can review and merge.
The tool NEVER modifies navigation_graph.py directly — human review is
always required.

CLI:
  python graph_promoter.py --show                  # list stable candidates
  python graph_promoter.py --snippet               # print Python snippet
  python graph_promoter.py --pr [--min-count N]    # open ADO PR with snippet
  python graph_promoter.py --all                   # all of the above
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.qa_uat.graph_promoter")

_TOOL_VERSION = "1.0.0"
_TOOL_ROOT = Path(__file__).parent
_CACHE_DIR = _TOOL_ROOT / "cache"
_LEARNED_EDGES_PATH = _CACHE_DIR / "learned_edges.json"

# Default observed_count threshold to promote; matches the "stable" bucket
# defined in navigation_graph_learner.compute_confidence().
_DEFAULT_MIN_COUNT = 5


@dataclass
class StableCandidate:
    """A learned edge that has crossed the stable threshold and is not yet
    in the static graph (i.e. ready for human-reviewed promotion)."""
    source: str
    target: str
    observed_count: int
    confidence: str
    first_seen: str = ""
    last_seen: str = ""
    action: str = "observed_navigate"
    evidence_runs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "target": self.target,
            "observed_count": self.observed_count,
            "confidence": self.confidence,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "action": self.action,
            "evidence_runs": self.evidence_runs,
        }


# ── Public API ────────────────────────────────────────────────────────────────

def get_stable_candidates(
    min_count: int = _DEFAULT_MIN_COUNT,
    learned_edges_path: Optional[Path] = None,
) -> list[StableCandidate]:
    """Return learned edges that are 'stable' AND not already in static GRAPH.

    Args:
        min_count: observed_count threshold. Edges below this are skipped
                   even if their persisted confidence is "stable" (defensive
                   filter in case threshold drifts between modules).
        learned_edges_path: override for testing. Defaults to
                            cache/learned_edges.json beside this script.

    Returns:
        List of StableCandidate, sorted by observed_count descending.
        Empty list if learned_edges.json does not exist or contains no
        stable candidates.
    """
    path = learned_edges_path or _LEARNED_EDGES_PATH
    if not path.is_file():
        return []

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("graph_promoter: failed to parse %s: %s", path, exc)
        return []

    # Lazy import: navigation_graph reads learned_edges.json at import time,
    # so importing it here is unavoidable but kept inside the function to
    # mirror the convention used elsewhere in the pipeline.
    try:
        from navigation_graph import GRAPH
        static_targets: dict[str, set[str]] = {
            src: {e.target for e in edges} for src, edges in GRAPH.items()
        }
    except Exception as exc:
        logger.warning("graph_promoter: could not load navigation_graph (%s); treating all stable edges as candidates", exc)
        static_targets = {}

    candidates: list[StableCandidate] = []
    for src, edges in (raw.get("by_source") or {}).items():
        for edge in edges:
            if edge.get("confidence") != "stable":
                continue
            count = edge.get("observed_count", 0)
            if count < min_count:
                continue
            target = edge.get("target", "")
            if not target:
                continue
            if target in static_targets.get(src, set()):
                # Already promoted in a previous round.
                continue
            candidates.append(StableCandidate(
                source=src,
                target=target,
                observed_count=count,
                confidence=edge.get("confidence", "stable"),
                first_seen=edge.get("first_seen", ""),
                last_seen=edge.get("last_seen", ""),
                action=edge.get("action", "observed_navigate"),
                evidence_runs=list(edge.get("evidence_runs", [])),
            ))

    candidates.sort(key=lambda c: -c.observed_count)
    return candidates


def generate_snippet(candidates: list[StableCandidate]) -> str:
    """Render a Python snippet for human review and paste into _RAW_GRAPH.

    The snippet groups candidates by source screen and emits one tuple per
    edge in the same shape navigation_graph._RAW_GRAPH expects:
        (target, action, label, is_external, is_popup)
    """
    if not candidates:
        return "# No stable candidates to promote."

    today = _today_iso()
    by_source: dict[str, list[StableCandidate]] = {}
    for c in candidates:
        by_source.setdefault(c.source, []).append(c)

    lines: list[str] = [
        "# " + "-" * 70,
        "# Learned edges promoted to static graph",
        f"# Generated by graph_promoter.py on {today}",
        "# Review and paste into navigation_graph._RAW_GRAPH manually.",
        "# " + "-" * 70,
    ]

    for src in sorted(by_source.keys()):
        lines.append(f'    "{src}": [')
        lines.append(f'        # ... (existing edges) ...')
        for c in by_source[src]:
            label_action = c.action if c.action.startswith("recorded:") else f"recorded:{c.action}"
            is_popup_literal = "True" if "PopUp" in c.target else "False"
            comment = (
                f"  # observed_count={c.observed_count} "
                f"(first_seen={c.first_seen or 'n/a'}, last_seen={c.last_seen or 'n/a'})"
            )
            lines.append(
                f'        ("{c.target}", "observed_navigate", "{label_action}", '
                f'False, {is_popup_literal}),{comment}'
            )
        lines.append(f'    ],')

    return "\n".join(lines)


def render_pr_body(candidates: list[StableCandidate], snippet: str) -> str:
    """Render the body of the ADO PR — table + snippet + reviewer guidance."""
    if not candidates:
        return "No stable candidates to promote."

    lines: list[str] = [
        "## Stable learned navigation edges ready for promotion",
        "",
        f"Generated by `graph_promoter.py` on {_today_iso()}.",
        "",
        f"`{len(candidates)}` edge(s) crossed the stable threshold and are not in the static graph.",
        "",
        "| Source | Target | observed_count | first_seen | last_seen |",
        "|---|---|---|---|---|",
    ]
    for c in candidates:
        lines.append(
            f"| `{c.source}` | `{c.target}` | {c.observed_count} | "
            f"{c.first_seen or 'n/a'} | {c.last_seen or 'n/a'} |"
        )
    lines.extend([
        "",
        "### Snippet to paste into `navigation_graph._RAW_GRAPH`",
        "",
        "```python",
        snippet,
        "```",
        "",
        "### Reviewer checklist",
        "",
        "- [ ] Each edge target is a real, supported screen (`agenda_screens.SUPPORTED_SCREENS`).",
        "- [ ] The edge label/action makes sense for the source screen.",
        "- [ ] No duplicates against existing `_RAW_GRAPH` entries.",
        "- [ ] After merging, run `python navigation_graph_learner.py --clear` to reset the learner cache.",
        "",
        "_This PR was opened automatically by `graph_promoter.py`. It is a draft —_",
        "_a human must review the snippet, edit `navigation_graph.py`, and mark ready._",
    ])
    return "\n".join(lines)


# ── ADO PR ────────────────────────────────────────────────────────────────────

def open_ado_pr(
    candidates: list[StableCandidate],
    snippet: str,
) -> dict:
    """Try to open a draft Azure DevOps PR via `az repos pr create`.

    Returns a dict describing what happened. Falls back to printing manual
    instructions if `az` isn't on PATH or the call fails for any reason.

    Always uses --draft so a human must promote the PR to ready before merge.
    """
    title = f"[auto] Promote {len(candidates)} learned navigation edge(s) to static graph"
    body = render_pr_body(candidates, snippet)

    cmd = ["az", "--version"]
    try:
        subprocess.run(cmd, capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        return {
            "ok": False,
            "reason": f"az CLI not available: {exc}",
            "title": title,
            "body": body,
            "instructions": _manual_pr_instructions(title, body),
        }

    # Body via temporary file — the az CLI accepts --description but multi-line
    # strings + Windows shells get mangled if passed inline.
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", delete=False, encoding="utf-8"
    )
    try:
        tmp.write(body)
        tmp.flush()
        tmp.close()

        pr_cmd = [
            "az", "repos", "pr", "create",
            "--title", title,
            "--description", body,
            "--draft", "true",
        ]
        result = subprocess.run(pr_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            return {
                "ok": False,
                "reason": f"az repos pr create failed (exit {result.returncode})",
                "stderr": result.stderr,
                "title": title,
                "body": body,
                "instructions": _manual_pr_instructions(title, body),
            }
        try:
            pr_info = json.loads(result.stdout)
        except Exception:
            pr_info = {"raw": result.stdout}
        return {
            "ok": True,
            "title": title,
            "pr": pr_info,
            "draft": True,
        }
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


def _manual_pr_instructions(title: str, body: str) -> str:
    return (
        "Manual steps:\n"
        "  1. Create a branch: git checkout -b auto/promote-learned-edges\n"
        "  2. Edit navigation_graph._RAW_GRAPH using the snippet below.\n"
        "  3. Run tests: python -m pytest tests/unit/ -v\n"
        "  4. Open a DRAFT PR titled:\n"
        f"     {title}\n"
        "  5. Paste the description below.\n"
        "  --- BODY ---\n"
        f"{body}\n"
        "  --- END BODY ---\n"
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _today_iso() -> str:
    import datetime
    return datetime.date.today().isoformat()


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    args = _parse_args()
    logging.basicConfig(
        level=logging.WARNING if args.background else logging.INFO,
        stream=sys.stderr,
        format="%(levelname)s %(name)s: %(message)s",
    )

    candidates = get_stable_candidates(min_count=args.min_count)
    snippet = generate_snippet(candidates)

    if not (args.show or args.snippet or args.pr or args.all):
        # No action selected — default to --show for discoverability.
        args.show = True

    output: dict = {
        "ok": True,
        "tool_version": _TOOL_VERSION,
        "min_count": args.min_count,
        "candidate_count": len(candidates),
    }

    if args.show or args.all:
        output["candidates"] = [c.to_dict() for c in candidates]
        if not args.background and not (args.snippet or args.pr or args.all):
            _print_human_summary(candidates)

    if args.snippet or args.all:
        output["snippet"] = snippet
        if not args.background:
            sys.stderr.write("\n# ── PROMOTE SNIPPET ──────────────────────\n")
            sys.stderr.write(snippet + "\n")
            sys.stderr.write("# ── END SNIPPET ──────────────────────────\n")

    if args.pr or args.all:
        if not candidates:
            output["pr"] = {
                "ok": False,
                "reason": "No stable candidates to promote — skipping PR.",
            }
        else:
            output["pr"] = open_ado_pr(candidates, snippet)

    print(json.dumps(output, ensure_ascii=False, indent=2))
    sys.exit(0)


def _print_human_summary(candidates: list[StableCandidate]) -> None:
    sys.stderr.write("\n")
    if not candidates:
        sys.stderr.write("  No stable candidates ready for promotion.\n")
        sys.stderr.write("  (Edges need observed_count >= 5 AND must be missing from the static graph.)\n")
        return
    sys.stderr.write(f"  Stable candidates ready for promotion: {len(candidates)}\n")
    for c in candidates[:15]:
        sys.stderr.write(
            f"    {c.source} -> {c.target}  "
            f"(seen {c.observed_count}x, since {c.first_seen or 'n/a'})\n"
        )
    if len(candidates) > 15:
        sys.stderr.write(f"    ... and {len(candidates) - 15} more\n")


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Promote stable learned edges to the static navigation graph. "
            "Fase 6 of the QA UAT Agent autonomy roadmap. "
            "Never modifies navigation_graph.py directly — human review required."
        )
    )
    p.add_argument("--show", action="store_true",
                   help="List stable candidates ready for promotion (default action).")
    p.add_argument("--snippet", action="store_true",
                   help="Print the Python snippet for pasting into _RAW_GRAPH.")
    p.add_argument("--pr", action="store_true",
                   help="Open a draft Azure DevOps PR with the snippet.")
    p.add_argument("--all", action="store_true",
                   help="Equivalent to --show --snippet --pr.")
    p.add_argument("--min-count", type=int, default=_DEFAULT_MIN_COUNT,
                   help=f"Minimum observed_count to promote (default {_DEFAULT_MIN_COUNT}).")
    p.add_argument("--background", action="store_true",
                   help="Suppress human-readable stderr output (JSON only on stdout).")
    return p.parse_args()


if __name__ == "__main__":
    main()
