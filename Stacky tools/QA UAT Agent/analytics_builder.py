"""
analytics_builder.py — Análisis histórico de runs QA UAT.

Construye reportes analíticos a partir de las métricas históricas
(data/metrics.jsonl) generadas por MetricsCollector.

REPORTES:
  - pass_rate(days=7)       → tasa de PASS por día
  - top_failures(days=7)    → categorías/stages con más fallos
  - duration_trends(days=7) → evolución de duración promedio
  - blocker_analysis(days=7)→ blockers más frecuentes por razón
  - full_report(days=7)     → dict completo con todos los análisis

Salida siempre en dict serializable JSON.
"""
from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Optional

from metrics_collector import MetricsCollector

_py_logger = logging.getLogger("stacky.qa_uat.analytics_builder")


class AnalyticsBuilder:
    """
    Construye reportes analíticos a partir del histórico de métricas.

    Uso:
        ab = AnalyticsBuilder()
        report = ab.full_report(days=7)
    """

    def __init__(self, metrics_collector: Optional[MetricsCollector] = None) -> None:
        self._mc = metrics_collector or MetricsCollector(
            evidence_dir=Path(__file__).parent / "evidence"
        )

    # ── API ────────────────────────────────────────────────────────────────────

    def pass_rate(self, days: int = 7) -> dict:
        """Tasa de PASS por día en el período dado."""
        records = self._mc.load_since(days=days)
        by_day: dict[str, dict[str, int]] = defaultdict(lambda: {"pass": 0, "fail": 0, "blocked": 0, "total": 0})

        for r in records:
            verdict = (r.get("run") or {}).get("verdict", "UNKNOWN")
            collected_at = r.get("collected_at", "")
            day = collected_at[:10] if collected_at else "unknown"
            by_day[day]["total"] += 1
            key = verdict.lower() if verdict.lower() in ("pass", "fail", "blocked") else "fail"
            by_day[day][key] += 1

        result = []
        for day in sorted(by_day.keys()):
            d = dict(by_day[day])
            d["day"] = day
            d["pass_rate"] = round(d["pass"] / d["total"], 3) if d["total"] > 0 else 0.0
            result.append(d)

        total_runs = len(records)
        total_pass = sum(1 for r in records if (r.get("run") or {}).get("verdict") == "PASS")
        overall_rate = round(total_pass / total_runs, 3) if total_runs > 0 else 0.0

        return {
            "days": days,
            "total_runs": total_runs,
            "total_pass": total_pass,
            "overall_pass_rate": overall_rate,
            "by_day": result,
        }

    def top_failures(self, days: int = 7, limit: int = 10) -> dict:
        """
        Top N categorías/stages con más fallos en el período.
        """
        records = self._mc.load_since(days=days)

        stage_failures: dict[str, int] = defaultdict(int)
        category_failures: dict[str, int] = defaultdict(int)
        error_counts: dict[str, int] = defaultdict(int)

        for r in records:
            # Stage failures
            stages = r.get("stages") or {}
            for stage in stages.get("failed", []):
                stage_failures[stage] += 1

            # Category failures from events
            events_stats = r.get("events") or {}
            by_cat = events_stats.get("by_category") or {}
            # We can't distinguish pass/fail per category from aggregated stats alone,
            # but we count categories in failed runs as a proxy
            verdict = (r.get("run") or {}).get("verdict", "UNKNOWN")
            if verdict in ("FAIL", "BLOCKED", "MIXED"):
                for cat, count in by_cat.items():
                    if "fail" in cat.lower() or cat in ("page_assertion", "page_click", "page_fill"):
                        category_failures[cat] += count

        return {
            "days": days,
            "top_stage_failures": sorted(
                [{"stage": k, "count": v} for k, v in stage_failures.items()],
                key=lambda x: x["count"],
                reverse=True,
            )[:limit],
            "top_category_failures": sorted(
                [{"category": k, "count": v} for k, v in category_failures.items()],
                key=lambda x: x["count"],
                reverse=True,
            )[:limit],
        }

    def duration_trends(self, days: int = 7) -> dict:
        """Evolución de duración promedio de runs por día."""
        records = self._mc.load_since(days=days)
        by_day: dict[str, list[int]] = defaultdict(list)

        for r in records:
            collected_at = r.get("collected_at", "")
            day = collected_at[:10] if collected_at else "unknown"
            duration = (r.get("run") or {}).get("duration_ms")
            if duration is not None:
                by_day[day].append(int(duration))

        result = []
        for day in sorted(by_day.keys()):
            durations = by_day[day]
            if durations:
                result.append({
                    "day": day,
                    "count": len(durations),
                    "avg_ms": round(sum(durations) / len(durations)),
                    "min_ms": min(durations),
                    "max_ms": max(durations),
                })

        return {"days": days, "by_day": result}

    def blocker_analysis(self, days: int = 7) -> dict:
        """Análisis de blockers: frecuencia por run, tasa de resolución."""
        records = self._mc.load_since(days=days)
        total_blockers = 0
        total_resolved = 0
        total_pending = 0

        for r in records:
            bs = r.get("blockers_summary") or {}
            total_blockers += bs.get("total", 0)
            total_resolved += bs.get("resolved", 0)
            total_pending += bs.get("pending", 0)

        runs_with_blockers = sum(
            1 for r in records
            if (r.get("blockers_summary") or {}).get("total", 0) > 0
        )

        return {
            "days": days,
            "total_blockers": total_blockers,
            "total_resolved": total_resolved,
            "total_pending": total_pending,
            "resolution_rate": round(total_resolved / total_blockers, 3) if total_blockers > 0 else 1.0,
            "runs_with_blockers": runs_with_blockers,
            "total_runs": len(records),
        }

    def playwright_stats(self, days: int = 7) -> dict:
        """Stats agregados de Playwright en el período."""
        records = self._mc.load_since(days=days)
        total_scenarios = 0
        total_pass = 0
        total_fail = 0
        total_assertions = 0
        total_assertion_pass = 0
        total_network_errors = 0

        for r in records:
            pw = r.get("playwright") or {}
            total_scenarios += pw.get("scenarios", 0)
            total_pass += pw.get("pass", 0)
            total_fail += pw.get("fail", 0)
            total_assertions += pw.get("assertions_total", 0)
            total_assertion_pass += pw.get("assertions_pass", 0)
            total_network_errors += pw.get("network_errors", 0)

        return {
            "days": days,
            "total_scenarios": total_scenarios,
            "total_pass": total_pass,
            "total_fail": total_fail,
            "scenario_pass_rate": round(total_pass / total_scenarios, 3) if total_scenarios > 0 else 0.0,
            "total_assertions": total_assertions,
            "assertion_pass_rate": round(total_assertion_pass / total_assertions, 3) if total_assertions > 0 else 0.0,
            "total_network_errors": total_network_errors,
        }

    def learning_stats(self, days: int = 7) -> dict:
        """Estadísticas de learnings generados en el período."""
        records = self._mc.load_since(days=days)
        total_candidates = sum(
            (r.get("learnings") or {}).get("candidates_generated", 0)
            for r in records
        )
        total_approved = sum(
            (r.get("learnings") or {}).get("approved", 0)
            for r in records
        )
        return {
            "days": days,
            "total_candidates": total_candidates,
            "total_approved": total_approved,
            "approval_rate": round(total_approved / total_candidates, 3) if total_candidates > 0 else 0.0,
        }

    def full_report(self, days: int = 7) -> dict:
        """Reporte completo con todos los análisis."""
        return {
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            "period_days": days,
            "pass_rate": self.pass_rate(days),
            "top_failures": self.top_failures(days),
            "duration_trends": self.duration_trends(days),
            "blocker_analysis": self.blocker_analysis(days),
            "playwright_stats": self.playwright_stats(days),
            "learning_stats": self.learning_stats(days),
        }
