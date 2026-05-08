"""
kpi_builder.py — KPIs del proceso QA UAT para reportes operacionales.

Construye KPIs a partir de AnalyticsBuilder. Cada KPI tiene:
  - id, name, value, unit, trend, status (green/yellow/red), threshold_green, threshold_yellow

KPIS DEFINIDOS:
  KPI-01 pass_rate_7d         → % runs PASS en últimos 7 días
  KPI-02 avg_duration_7d      → Duración promedio de run (ms) en 7 días
  KPI-03 blocker_resolution   → % blockers resueltos en 7 días
  KPI-04 assertion_pass_rate  → % assertions Playwright que pasan en 7 días
  KPI-05 learning_adoption    → % candidatos de learning aprobados en 7 días
  KPI-06 runs_last_7d         → Total de runs ejecutados en 7 días
"""
from __future__ import annotations

from typing import Any


def _status(value: float, green: float, yellow: float, higher_is_better: bool = True) -> str:
    """Clasificar valor en green/yellow/red según umbrales."""
    if higher_is_better:
        if value >= green:
            return "green"
        if value >= yellow:
            return "yellow"
        return "red"
    else:
        # lower is better (e.g. duration)
        if value <= green:
            return "green"
        if value <= yellow:
            return "yellow"
        return "red"


def _trend(current: float, previous: float) -> str:
    """Calcular tendencia entre dos valores."""
    if previous == 0:
        return "stable"
    delta = (current - previous) / abs(previous)
    if delta > 0.05:
        return "up"
    if delta < -0.05:
        return "down"
    return "stable"


class KPIBuilder:
    """
    Calcula KPIs del proceso QA UAT.

    Uso:
        from analytics_builder import AnalyticsBuilder
        ab = AnalyticsBuilder()
        kb = KPIBuilder(ab)
        kpis = kb.build_kpis(days=7)
    """

    def __init__(self, analytics_builder: Any) -> None:
        self._ab = analytics_builder

    def build_kpis(self, days: int = 7) -> dict:
        """Calcular todos los KPIs para el período dado."""
        report = self._ab.full_report(days=days)
        prev_report = self._ab.full_report(days=days * 2) if days <= 30 else None

        kpis = []

        # KPI-01: pass_rate_7d
        pr = report["pass_rate"]
        prev_pr = (prev_report or {}).get("pass_rate", {})
        pass_rate_val = pr.get("overall_pass_rate", 0.0)
        prev_pass_rate = prev_pr.get("overall_pass_rate", pass_rate_val)
        kpis.append({
            "id": "KPI-01",
            "name": f"Pass Rate ({days}d)",
            "value": round(pass_rate_val * 100, 1),
            "unit": "%",
            "trend": _trend(pass_rate_val, prev_pass_rate),
            "status": _status(pass_rate_val, green=0.8, yellow=0.6),
            "threshold_green": ">=80%",
            "threshold_yellow": ">=60%",
            "raw": pass_rate_val,
        })

        # KPI-02: avg_duration
        dt = report["duration_trends"]
        all_durations = [d.get("avg_ms", 0) for d in dt.get("by_day", [])]
        avg_duration = sum(all_durations) / len(all_durations) if all_durations else 0
        prev_dt = (prev_report or {}).get("duration_trends", {})
        prev_durations = [d.get("avg_ms", 0) for d in prev_dt.get("by_day", [])]
        prev_avg_dur = sum(prev_durations) / len(prev_durations) if prev_durations else avg_duration
        kpis.append({
            "id": "KPI-02",
            "name": f"Avg Duration ({days}d)",
            "value": round(avg_duration / 1000, 1),  # en segundos
            "unit": "s",
            "trend": _trend(avg_duration, prev_avg_dur),
            "status": _status(avg_duration, green=120_000, yellow=300_000, higher_is_better=False),
            "threshold_green": "<=120s",
            "threshold_yellow": "<=300s",
            "raw": avg_duration,
        })

        # KPI-03: blocker_resolution_rate
        ba = report["blocker_analysis"]
        bloc_rate = ba.get("resolution_rate", 1.0)
        prev_ba = (prev_report or {}).get("blocker_analysis", {})
        prev_bloc_rate = prev_ba.get("resolution_rate", bloc_rate)
        kpis.append({
            "id": "KPI-03",
            "name": f"Blocker Resolution Rate ({days}d)",
            "value": round(bloc_rate * 100, 1),
            "unit": "%",
            "trend": _trend(bloc_rate, prev_bloc_rate),
            "status": _status(bloc_rate, green=0.9, yellow=0.7),
            "threshold_green": ">=90%",
            "threshold_yellow": ">=70%",
            "raw": bloc_rate,
        })

        # KPI-04: assertion_pass_rate
        ps = report["playwright_stats"]
        assert_rate = ps.get("assertion_pass_rate", 0.0)
        prev_ps = (prev_report or {}).get("playwright_stats", {})
        prev_assert_rate = prev_ps.get("assertion_pass_rate", assert_rate)
        kpis.append({
            "id": "KPI-04",
            "name": f"Assertion Pass Rate ({days}d)",
            "value": round(assert_rate * 100, 1),
            "unit": "%",
            "trend": _trend(assert_rate, prev_assert_rate),
            "status": _status(assert_rate, green=0.85, yellow=0.7),
            "threshold_green": ">=85%",
            "threshold_yellow": ">=70%",
            "raw": assert_rate,
        })

        # KPI-05: learning_adoption
        ls = report["learning_stats"]
        learn_rate = ls.get("approval_rate", 0.0)
        kpis.append({
            "id": "KPI-05",
            "name": f"Learning Adoption Rate ({days}d)",
            "value": round(learn_rate * 100, 1),
            "unit": "%",
            "trend": "stable",  # sin comparación previa en este KPI
            "status": _status(learn_rate, green=0.5, yellow=0.2),
            "threshold_green": ">=50%",
            "threshold_yellow": ">=20%",
            "raw": learn_rate,
        })

        # KPI-06: runs_last_Nd
        total_runs = pr.get("total_runs", 0)
        kpis.append({
            "id": "KPI-06",
            "name": f"Runs Executed ({days}d)",
            "value": total_runs,
            "unit": "runs",
            "trend": "stable",
            "status": "green" if total_runs > 0 else "yellow",
            "threshold_green": ">0",
            "threshold_yellow": "0",
            "raw": total_runs,
        })

        summary_status = "green"
        if any(k["status"] == "red" for k in kpis):
            summary_status = "red"
        elif any(k["status"] == "yellow" for k in kpis):
            summary_status = "yellow"

        return {
            "generated_at": report.get("generated_at", ""),
            "period_days": days,
            "summary_status": summary_status,
            "kpis": kpis,
        }
