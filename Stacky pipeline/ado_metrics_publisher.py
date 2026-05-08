"""
ado_metrics_publisher.py — Publish Stacky metrics to ADO as tags.

Tags completed work items with pipeline performance metrics for ADO Analytics.

Uso:
    from ado_metrics_publisher import ADOMetricsPublisher
    publisher = ADOMetricsPublisher()
    publisher.tag_with_metrics(work_item_id, pipeline_result)
"""

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.ado_metrics")

AUTH_FILE = Path(__file__).parent / "auth" / "ado_auth.json"


class ADOMetricsPublisher:
    def __init__(self, ado_client=None, config: Optional[dict] = None):
        self._ado_client = ado_client
        self._config = config or {}

    @property
    def ado_client(self):
        if self._ado_client is None:
            try:
                from ado_enricher import _get_ado_client
                self._ado_client = _get_ado_client()
            except Exception as e:
                logger.error("Cannot init ADO client: %s", e)
                raise
        return self._ado_client

    def tag_with_metrics(self, work_item_id: int, pipeline_result: dict):
        """
        Tag a work item with pipeline performance metrics.

        Args:
            work_item_id: ADO Work Item ID
            pipeline_result: dict with keys like duration_minutes, rework_cycles, etc.
        """
        tags = self._build_metric_tags(pipeline_result)
        if not tags:
            return

        try:
            # Get current tags
            ops = [
                {
                    "op": "add",
                    "path": "/fields/System.Tags",
                    "value": "; ".join(tags),
                }
            ]
            self.ado_client.update_work_item(work_item_id, ops)
            logger.info("[MetricsPub] Tagged WI#%d with %d metrics tags",
                         work_item_id, len(tags))
        except Exception as e:
            logger.error("[MetricsPub] Failed to tag WI#%d: %s", work_item_id, e)

    def publish_daily_summary(self) -> dict:
        """Publish daily summary metrics (for use in scheduled tasks)."""
        summary = {}
        try:
            from metrics_collector import MetricsCollector
            mc = MetricsCollector()
            if hasattr(mc, "get_daily_stats"):
                summary = mc.get_daily_stats()
        except ImportError:
            pass
        return summary

    def _build_metric_tags(self, result: dict) -> list[str]:
        tags = ["stacky:done"]

        duration = result.get("duration_minutes")
        if duration is not None:
            tags.append(f"stacky:time_{int(duration)}min")

        rework = result.get("rework_cycles")
        if rework is not None:
            tags.append(f"stacky:rework_{rework}")

        pm_time = result.get("pm_duration_min")
        if pm_time is not None:
            tags.append(f"stacky:pm_{int(pm_time)}min")

        dev_time = result.get("dev_duration_min")
        if dev_time is not None:
            tags.append(f"stacky:dev_{int(dev_time)}min")

        qa_time = result.get("qa_duration_min")
        if qa_time is not None:
            tags.append(f"stacky:qa_{int(qa_time)}min")

        complexity = result.get("complexity")
        if complexity:
            tags.append(f"stacky:complexity_{complexity}")

        return tags
