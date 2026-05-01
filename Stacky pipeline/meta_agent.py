"""
meta_agent.py — Autonomous Pipeline Self-Rewriting.

MetaAgent analiza métricas semanales y propone/aplica mejoras a los prompts.
El sistema se auto-optimiza sin intervención humana.

Uso:
    from meta_agent import MetaAgent
    agent = MetaAgent()
    agent.weekly_optimization_cycle()
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.meta_agent")

DATA_DIR = Path(__file__).parent / "data"
IMPROVEMENT_LOG = DATA_DIR / "meta_agent_improvements.json"


class MetaAgent:
    IMPROVEMENT_THRESHOLD = 0.05  # 5% improvement required

    def __init__(self, metrics_collector=None, copilot_bridge=None, ado_reporter=None):
        self._metrics = metrics_collector
        self._bridge = copilot_bridge
        self._ado_reporter = ado_reporter

    @property
    def metrics(self):
        if self._metrics is None:
            try:
                from metrics_collector import MetricsCollector
                self._metrics = MetricsCollector()
            except ImportError:
                pass
        return self._metrics

    def weekly_optimization_cycle(self) -> dict:
        results = {"proposals": [], "applied": [], "skipped": []}

        if not self.metrics:
            logger.warning("[MetaAgent] No metrics collector available")
            return results

        try:
            stats = self._get_weekly_stats()
        except Exception as e:
            logger.error("[MetaAgent] Failed to get weekly stats: %s", e)
            return results

        if stats.get("rework_rate", 0) > 0.3:
            proposal = self._propose_improvement("tester", stats, "High rework rate detected")
            results["proposals"].append(proposal)

        if stats.get("pm_placeholder_rate", 0) > 0.1:
            proposal = self._propose_improvement("pm", stats, "High placeholder rate in PM output")
            results["proposals"].append(proposal)

        if stats.get("dev_first_attempt_rate", 1.0) < 0.6:
            proposal = self._propose_improvement("dev", stats, "Low DEV first-attempt success rate")
            results["proposals"].append(proposal)

        self._log_cycle(results)
        return results

    def _propose_improvement(self, stage: str, stats: dict, reason: str) -> dict:
        proposal = {
            "stage": stage,
            "reason": reason,
            "timestamp": datetime.now().isoformat(),
            "stats_snapshot": stats,
            "status": "proposed",
        }
        logger.info("[MetaAgent] Proposed improvement for %s: %s", stage, reason)
        return proposal

    def _get_weekly_stats(self) -> dict:
        if hasattr(self.metrics, "get_weekly_stats"):
            return self.metrics.get_weekly_stats()
        return {
            "rework_rate": 0.0,
            "pm_placeholder_rate": 0.0,
            "dev_first_attempt_rate": 1.0,
            "total_tickets": 0,
        }

    def _log_cycle(self, results: dict):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        log = []
        if IMPROVEMENT_LOG.exists():
            try:
                log = json.loads(IMPROVEMENT_LOG.read_text(encoding="utf-8"))
            except Exception:
                pass
        log.append({
            "timestamp": datetime.now().isoformat(),
            "proposals_count": len(results["proposals"]),
            "applied_count": len(results["applied"]),
            "details": results,
        })
        if len(log) > 100:
            log = log[-100:]
        IMPROVEMENT_LOG.write_text(
            json.dumps(log, indent=2, ensure_ascii=False), encoding="utf-8"
        )
