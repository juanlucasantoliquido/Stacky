"""
playbook_performance.py — Per-playbook execution metrics for QA UAT Agent.

Tracks avg/p95 duration, flake rate, and last failure reason per playbook.
Used to:
  - Adjust timeouts dynamically per playbook.
  - Detect flaky playbooks early.
  - Surface slowest steps in evidence reports.

Metrics stored at: cache/playbook_perf/<playbook_id>.json

Schema:
    {
        "playbook_id": "agregar_usuario_nuevo",
        "run_count": 10,
        "pass_count": 9,
        "fail_count": 1,
        "flake_rate": 0.1,
        "avg_duration_ms": 18400,
        "p95_duration_ms": 24000,
        "min_duration_ms": 12000,
        "max_duration_ms": 28000,
        "last_run_at": "2026-05-07T10:00:00",
        "last_verdict": "PASS",
        "last_fail_reason": "",
        "slowest_step": "ASSERTIONS",
        "durations": [18000, 17500, ..., 28000]   // up to 50 samples, FIFO
    }

Usage:
    from playbook_performance import record_run, get_metrics, recommend_timeout_ms

    record_run("agregar_usuario_nuevo", verdict="PASS", duration_ms=18400, slowest_step="ASSERTIONS")
    metrics = get_metrics("agregar_usuario_nuevo")
    timeout = recommend_timeout_ms("agregar_usuario_nuevo")  # e.g. 36000

CLI:
    python playbook_performance.py --show
    python playbook_performance.py --show-playbook agregar_usuario_nuevo
    python playbook_performance.py --reset-playbook agregar_usuario_nuevo
"""
from __future__ import annotations

import json
import logging
import math
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.qa_uat.playbook_performance")

_PERF_DIR = Path(__file__).parent / "cache" / "playbook_perf"
_PERF_DIR.mkdir(parents=True, exist_ok=True)

_MAX_SAMPLES = 50
# Recommend timeout = p95 * 1.5, capped between 60s and 10min
_TIMEOUT_FLOOR_MS = 60_000
_TIMEOUT_CEILING_MS = 600_000
_TIMEOUT_MULTIPLIER = 1.5


def _perf_file(playbook_id: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "_-" else "_" for c in playbook_id)
    return _PERF_DIR / f"{safe}.json"


def _load(playbook_id: str) -> dict:
    f = _perf_file(playbook_id)
    if f.is_file():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "playbook_id": playbook_id,
        "run_count": 0,
        "pass_count": 0,
        "fail_count": 0,
        "flake_rate": 0.0,
        "avg_duration_ms": 0,
        "p95_duration_ms": 0,
        "min_duration_ms": 0,
        "max_duration_ms": 0,
        "last_run_at": "",
        "last_verdict": "",
        "last_fail_reason": "",
        "slowest_step": "",
        "durations": [],
    }


def _save(data: dict) -> None:
    try:
        _perf_file(data["playbook_id"]).write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception as exc:
        logger.warning("Could not save perf data for %s: %s", data.get("playbook_id"), exc)


def _percentile(values: list, p: float) -> int:
    if not values:
        return 0
    sorted_v = sorted(values)
    idx = math.ceil(p / 100.0 * len(sorted_v)) - 1
    return int(sorted_v[max(0, min(idx, len(sorted_v) - 1))])


# ── Public API ─────────────────────────────────────────────────────────────────

def record_run(
    playbook_id: str,
    verdict: str,
    duration_ms: int,
    slowest_step: str = "",
    fail_reason: str = "",
) -> dict:
    """Record a run result and update rolling statistics."""
    data = _load(playbook_id)

    data["run_count"] += 1
    if verdict == "PASS":
        data["pass_count"] += 1
    else:
        data["fail_count"] += 1
        data["last_fail_reason"] = fail_reason

    # Rolling window of durations
    data["durations"].append(duration_ms)
    if len(data["durations"]) > _MAX_SAMPLES:
        data["durations"] = data["durations"][-_MAX_SAMPLES:]

    durs = data["durations"]
    data["avg_duration_ms"] = int(sum(durs) / len(durs))
    data["p95_duration_ms"] = _percentile(durs, 95)
    data["min_duration_ms"] = min(durs)
    data["max_duration_ms"] = max(durs)
    data["flake_rate"] = round(data["fail_count"] / data["run_count"], 4)
    data["last_run_at"] = datetime.utcnow().isoformat()
    data["last_verdict"] = verdict
    if slowest_step:
        data["slowest_step"] = slowest_step

    _save(data)
    logger.debug(
        "Perf recorded for %s: %s %dms (avg=%d p95=%d flake=%.2f)",
        playbook_id, verdict, duration_ms,
        data["avg_duration_ms"], data["p95_duration_ms"], data["flake_rate"],
    )
    return data


def get_metrics(playbook_id: str) -> dict:
    """Return current metrics for a playbook (empty baseline if no data)."""
    return _load(playbook_id)


def recommend_timeout_ms(playbook_id: str, default_ms: int = 120_000) -> int:
    """Return a recommended per-spec timeout based on p95 * 1.5.

    Falls back to `default_ms` when no data is available.
    """
    data = _load(playbook_id)
    p95 = data.get("p95_duration_ms", 0)
    if p95 <= 0:
        return default_ms
    rec = int(p95 * _TIMEOUT_MULTIPLIER)
    return max(_TIMEOUT_FLOOR_MS, min(rec, _TIMEOUT_CEILING_MS))


def list_all_metrics() -> list:
    """Return metrics for all playbooks that have recorded data."""
    result = []
    for f in sorted(_PERF_DIR.glob("*.json")):
        try:
            result.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            pass
    return result


def reset_playbook(playbook_id: str) -> bool:
    """Delete performance data for a specific playbook."""
    f = _perf_file(playbook_id)
    if f.is_file():
        f.unlink()
        return True
    return False


# ── CLI ────────────────────────────────────────────────────────────────────────

def main() -> None:
    import argparse
    import sys

    p = argparse.ArgumentParser(description="Playbook performance profiler")
    p.add_argument("--show", action="store_true", help="Show all playbook metrics")
    p.add_argument("--show-playbook", metavar="ID", help="Show metrics for one playbook")
    p.add_argument("--reset-playbook", metavar="ID", help="Reset metrics for one playbook")
    p.add_argument("--recommend-timeout", metavar="ID",
                   help="Print recommended timeout_ms for one playbook")
    args = p.parse_args()

    if args.show:
        metrics = list_all_metrics()
        print(json.dumps({"ok": True, "count": len(metrics), "metrics": metrics},
                         ensure_ascii=False, indent=2))
    elif args.show_playbook:
        print(json.dumps(get_metrics(args.show_playbook), ensure_ascii=False, indent=2))
    elif args.reset_playbook:
        removed = reset_playbook(args.reset_playbook)
        print(json.dumps({"ok": True, "removed": removed}))
    elif args.recommend_timeout:
        t = recommend_timeout_ms(args.recommend_timeout)
        print(json.dumps({"ok": True, "playbook_id": args.recommend_timeout,
                          "recommended_timeout_ms": t}, indent=2))
    else:
        p.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
