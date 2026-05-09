"""
dashboard_builder.py — Dashboard Summary Builder for QA UAT Agent.

Generates a JSON or text health summary covering three panels:
  1. run_health      — verdicts breakdown over the last N days
  2. generation_health — UI map cache hit rate, missing selectors
  3. quarantine_health — active quarantines, expired unresolved

CLI:
    python dashboard_builder.py --period 7 --format json
    python dashboard_builder.py --period 7 --format text

Output contract (JSON):
    {
      "ok": true,
      "generated_at": "...",
      "period_days": 7,
      "panels": {
        "run_health": { ... },
        "generation_health": { ... },
        "quarantine_health": { ... }
      }
    }
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Optional

_logger = logging.getLogger("stacky.qa_uat.dashboard_builder")

_TOOL_ROOT = Path(__file__).parent
_UI_MAPS_DIR = _TOOL_ROOT / "cache" / "ui_maps"


def build_dashboard(period_days: int = 7) -> dict:
    """
    Build the full dashboard summary for the last `period_days` days.

    Returns a dict conforming to the API output contract.
    """
    try:
        from metrics_collector import get_dashboard_summary
        summary = get_dashboard_summary(since_days=period_days)
    except Exception as exc:
        _logger.warning("dashboard_builder: metrics unavailable: %s", exc)
        from metrics_collector import DashboardSummary, _utcnow
        summary = DashboardSummary(
            generated_at=_utcnow(),
            period_days=period_days,
            run_health={
                "panel": "run_health",
                "period_days": period_days,
                "total_runs": 0,
                "pass": 0, "fail_app": 0, "blocked": 0,
                "mixed": 0, "skipped": 0, "unknown": 0,
                "blocked_by_category": {
                    "ENV": 0, "DATA": 0, "GEN": 0, "NAV": 0,
                    "PIP": 0, "OBS": 0, "APP": 0, "OPS": 0, "SEC": 0,
                },
            },
            generation_health={
                "panel": "generation_health",
                "ui_map_cache_hit_rate": 0.0,
                "ui_map_stale_rate": 0.0,
                "selector_alias_missing_rate": 0.0,
                "screens_without_ui_map": [],
            },
            quarantine_health={
                "panel": "quarantine_health",
                "active_quarantines": 0,
                "expired_unresolved": 0,
                "oldest_quarantine_days": None,
            },
        )

    # Enrich generation_health with UI map directory scan
    _enrich_generation_health(summary.generation_health)

    return {
        "ok": True,
        "generated_at": summary.generated_at,
        "period_days": summary.period_days,
        "panels": {
            "run_health": summary.run_health,
            "generation_health": summary.generation_health,
            "quarantine_health": summary.quarantine_health,
        },
    }


def _enrich_generation_health(panel: dict) -> None:
    """
    Scan the UI maps directory to find screens without a cached UI map.
    Modifies panel in-place.
    """
    try:
        from agenda_screens import SUPPORTED_SCREENS
        if not _UI_MAPS_DIR.exists():
            panel["screens_without_ui_map"] = sorted(SUPPORTED_SCREENS)
            return

        cached = {f.stem for f in _UI_MAPS_DIR.glob("*.json")}
        missing = sorted(s for s in SUPPORTED_SCREENS if s not in cached)
        panel["screens_without_ui_map"] = missing

        # Recompute stale rate based on actual coverage
        total = len(SUPPORTED_SCREENS)
        if total > 0:
            panel["ui_map_stale_rate"] = round(len(missing) / total, 3)
    except ImportError:
        # agenda_screens.py not importable — leave as-is
        pass
    except Exception as exc:
        _logger.debug("dashboard_builder: enrich_generation_health error: %s", exc)


def format_text(dashboard: dict) -> str:
    """Format dashboard dict as human-readable text."""
    lines = []
    lines.append("=" * 60)
    lines.append("  QA UAT Agent — Dashboard Health Report")
    lines.append(f"  Generated: {dashboard.get('generated_at', 'unknown')}")
    lines.append(f"  Period:    last {dashboard.get('period_days', 7)} days")
    lines.append("=" * 60)

    panels = dashboard.get("panels", {})

    # Run health
    rh = panels.get("run_health", {})
    lines.append("")
    lines.append("[ Run Health ]")
    lines.append(f"  Total runs  : {rh.get('total_runs', 0)}")
    lines.append(f"  PASS        : {rh.get('pass', 0)}")
    lines.append(f"  FAIL (APP)  : {rh.get('fail_app', 0)}")
    lines.append(f"  BLOCKED     : {rh.get('blocked', 0)}")
    lines.append(f"  MIXED       : {rh.get('mixed', 0)}")
    lines.append(f"  SKIPPED     : {rh.get('skipped', 0)}")
    lines.append(f"  UNKNOWN     : {rh.get('unknown', 0)}")
    lines.append("")
    lines.append("  Blocked by category:")
    for cat, cnt in (rh.get("blocked_by_category") or {}).items():
        indicator = " [!]" if cnt > 0 else ""
        lines.append(f"    {cat:<5} : {cnt}{indicator}")

    # Signal indicators
    if rh.get("unknown", 0) == 0:
        lines.append("  STATUS: unknown_count=0 [GREEN]")
    else:
        lines.append(f"  STATUS: unknown_count={rh.get('unknown')} [WARN]")

    # Generation health
    gh = panels.get("generation_health", {})
    lines.append("")
    lines.append("[ Generation Health ]")
    lines.append(f"  UI map cache hit rate : {gh.get('ui_map_cache_hit_rate', 0):.1%}")
    lines.append(f"  UI map stale rate     : {gh.get('ui_map_stale_rate', 0):.1%}")
    lines.append(f"  Alias missing rate    : {gh.get('selector_alias_missing_rate', 0):.1%}")
    missing_maps = gh.get("screens_without_ui_map") or []
    if missing_maps:
        lines.append(f"  Screens without map   : {len(missing_maps)}")
        for s in missing_maps[:5]:
            lines.append(f"    - {s}")
        if len(missing_maps) > 5:
            lines.append(f"    ... and {len(missing_maps) - 5} more")
    else:
        lines.append("  Screens without map   : 0 [GREEN]")

    # Quarantine health
    qh = panels.get("quarantine_health", {})
    lines.append("")
    lines.append("[ Quarantine Health ]")
    lines.append(f"  Active quarantines    : {qh.get('active_quarantines', 0)}")
    expired = qh.get("expired_unresolved", 0)
    if expired > 0:
        lines.append(f"  Expired unresolved    : {expired} [WARN]")
    else:
        lines.append(f"  Expired unresolved    : {expired}")
    oldest = qh.get("oldest_quarantine_days")
    if oldest is not None:
        lines.append(f"  Oldest quarantine     : {oldest} days")
    else:
        lines.append("  Oldest quarantine     : N/A")

    lines.append("")
    lines.append("=" * 60)
    return "\n".join(lines)


# ── CLI entry point ───────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="QA UAT Agent — Dashboard Health Summary",
    )
    parser.add_argument("--period", type=int, default=7,
                        help="Days to include (default: 7)")
    parser.add_argument("--format", choices=["json", "text"], default="json",
                        help="Output format (default: json)")
    parser.add_argument("--indent", type=int, default=2,
                        help="JSON indent spaces (default: 2)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING, stream=sys.stderr)

    dashboard = build_dashboard(period_days=args.period)

    if args.format == "json":
        print(json.dumps(dashboard, ensure_ascii=False, indent=args.indent))
    else:
        print(format_text(dashboard))

    sys.exit(0 if dashboard.get("ok") else 1)


if __name__ == "__main__":
    main()
