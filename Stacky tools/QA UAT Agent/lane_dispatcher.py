"""
lane_dispatcher.py — Lane Dispatcher for QA UAT Agent CI/CD.

Defines which stages are active for each named execution lane and
injects the correct env-var overrides before delegating to the pipeline.

Lanes:
  preflight        — env_preflight + fingerprint only (<20s)
  compile-only     — intake + screen + ui_map + compiler + selector_contract (<45s, no browser)
  smoke-uat        — full pipeline, P0 items only (<3min)
  full-uat         — complete pipeline, all items
  forensic-rerun   — full pipeline + trace=always + HAR + screenshots
  nightly-regression — full pipeline, all active tickets prioritized

Usage:
    from lane_dispatcher import dispatch, LANES

    result = dispatch(lane="smoke-uat", ticket_id=122, exec_logger=my_logger)
    if not result.ok:
        print(result.error)
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

_logger = logging.getLogger("stacky.qa_uat.lane_dispatcher")

# ── Lane definitions ──────────────────────────────────────────────────────────

_ALL_STAGES = [
    "env_preflight",
    "fingerprint",
    "intake",
    "screen",
    "ui_map",
    "compiler",
    "selector_contract",
    "data_readiness",
    "generator",
    "runner",
    "triage",
    "quarantine_check",
    "run_metrics_summary",
    "ci_artifacts_publish",
]

LANES: dict[str, dict] = {
    "preflight": {
        "description": "Environment preflight + fingerprint only. Always available. <20s.",
        "env": {
            "QA_UAT_LANE": "preflight",
            "QA_UAT_SKIP_COMPILER": "true",
            "QA_UAT_SKIP_GENERATOR": "true",
            "QA_UAT_SKIP_RUNNER": "true",
            "QA_UAT_TEST_TIMEOUT_MS": "20000",
        },
        "stages_active": ["env_preflight", "fingerprint"],
        "stages_skipped": [
            s for s in _ALL_STAGES if s not in ("env_preflight", "fingerprint")
        ],
        "timeout_target_s": 20,
    },
    "compile-only": {
        "description": "Dry-run without browser. intake + screen + ui_map + compiler + selector_contract. <45s.",
        "env": {
            "QA_UAT_LANE": "compile-only",
            "QA_UAT_SKIP_RUNNER": "true",
            "QA_UAT_SKIP_GENERATOR": "true",
            "QA_UAT_TEST_TIMEOUT_MS": "45000",
        },
        "stages_active": [
            "env_preflight", "fingerprint", "intake", "screen",
            "ui_map", "compiler", "selector_contract",
        ],
        "stages_skipped": [
            "data_readiness", "generator", "runner", "triage",
            "quarantine_check", "run_metrics_summary", "ci_artifacts_publish",
        ],
        "timeout_target_s": 45,
    },
    "smoke-uat": {
        "description": "PR/ticket-ready smoke. Full pipeline, P0 items only. <3min.",
        "env": {
            "QA_UAT_LANE": "smoke-uat",
            "QA_UAT_PRIORITY_FILTER": "P0",
            "QA_UAT_RETRIES": "1",
            "QA_UAT_TEST_TIMEOUT_MS": "180000",
        },
        "stages_active": list(_ALL_STAGES),
        "stages_skipped": [],
        "timeout_target_s": 180,
    },
    "full-uat": {
        "description": "Pre-release / manual. Complete pipeline, all items. Variable duration.",
        "env": {
            "QA_UAT_LANE": "full-uat",
        },
        "stages_active": list(_ALL_STAGES),
        "stages_skipped": [],
        "timeout_target_s": None,
    },
    "forensic-rerun": {
        "description": "Post-failure deep dive. Full pipeline + trace=always + HAR + screenshots.",
        "env": {
            "QA_UAT_LANE": "forensic-rerun",
            "QA_UAT_TRACE": "always",
            "QA_UAT_VIDEO": "on",
            "QA_UAT_SCREENSHOT": "on",
            "QA_UAT_HEADED": "false",
            "QA_UAT_RETRIES": "2",
        },
        "stages_active": list(_ALL_STAGES),
        "stages_skipped": [],
        "timeout_target_s": None,
    },
    "nightly-regression": {
        "description": "Nightly. Full pipeline, all active tickets prioritized. Variable duration.",
        "env": {
            "QA_UAT_LANE": "nightly-regression",
            "QA_UAT_RETRIES": "2",
        },
        "stages_active": list(_ALL_STAGES),
        "stages_skipped": [],
        "timeout_target_s": None,
    },
}


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class LaneDispatchResult:
    ok: bool
    lane: str
    ticket_id: Any
    stages_active: list[str]
    stages_skipped: list[str]
    config_applied: dict
    dispatched_at: str
    error: Optional[str] = None
    message: Optional[str] = None
    # The merged env dict that was applied (original OS env + overrides)
    env_snapshot: dict = field(default_factory=dict)

    def to_event(self) -> dict:
        """Return the execution.jsonl event dict for this dispatch."""
        return {
            "event": "lane_dispatched",
            "lane": self.lane,
            "ticket_id": self.ticket_id,
            "stages_active": self.stages_active,
            "stages_skipped": self.stages_skipped,
            "config_applied": self.config_applied,
            "dispatched_at": self.dispatched_at,
            "ok": self.ok,
            **({"error": self.error, "message": self.message} if not self.ok else {}),
        }

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "lane": self.lane,
            "ticket_id": self.ticket_id,
            "stages_active": self.stages_active,
            "stages_skipped": self.stages_skipped,
            "config_applied": self.config_applied,
            "dispatched_at": self.dispatched_at,
            **({"error": self.error, "message": self.message} if not self.ok else {}),
        }


# ── Public API ────────────────────────────────────────────────────────────────

def get_available_lanes() -> list[str]:
    """Return sorted list of valid lane names."""
    return sorted(LANES.keys())


def dispatch(
    lane: str,
    ticket_id: Any,
    config_overrides: Optional[dict] = None,
    exec_logger=None,
) -> LaneDispatchResult:
    """
    Validate the requested lane, apply env-var overrides to os.environ,
    emit a lane_dispatched event, and return a LaneDispatchResult.

    The caller is responsible for restoring the environment if needed.
    In practice the pipeline is forked per-ticket so this is safe.

    Parameters
    ----------
    lane            : One of the keys in LANES.
    ticket_id       : ADO ticket ID or run_id (used only for logging/event).
    config_overrides: Optional dict merged ON TOP of the lane defaults
                      (caller-supplied overrides win).
    exec_logger     : ExecutionLogger instance — if provided, lane_dispatched
                      event is emitted to execution.jsonl.

    Returns
    -------
    LaneDispatchResult — ok=True if lane was recognised and env was applied.
    """
    dispatched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

    if lane not in LANES:
        err = LaneDispatchResult(
            ok=False,
            lane=lane,
            ticket_id=ticket_id,
            stages_active=[],
            stages_skipped=[],
            config_applied={},
            dispatched_at=dispatched_at,
            error="UNKNOWN_LANE",
            message=(
                f"Lane '{lane}' is not defined. "
                f"Available lanes: {', '.join(get_available_lanes())}"
            ),
        )
        _logger.error("lane_dispatcher: unknown lane '%s'", lane)
        _emit_event(exec_logger, err.to_event())
        return err

    lane_def = LANES[lane]
    base_env: dict = dict(lane_def["env"])

    # Merge caller overrides (win over lane defaults)
    if config_overrides:
        base_env.update(config_overrides)

    # Apply to process environment
    for k, v in base_env.items():
        os.environ[k] = str(v)

    _logger.info(
        "lane_dispatcher: lane='%s' ticket=%s stages_active=%d config=%s",
        lane, ticket_id, len(lane_def["stages_active"]), list(base_env.keys()),
    )

    result = LaneDispatchResult(
        ok=True,
        lane=lane,
        ticket_id=ticket_id,
        stages_active=list(lane_def["stages_active"]),
        stages_skipped=list(lane_def["stages_skipped"]),
        config_applied=base_env,
        dispatched_at=dispatched_at,
    )

    _emit_event(exec_logger, result.to_event())
    return result


def is_stage_active(lane: str, stage: str) -> bool:
    """Return True if stage is active for the given lane."""
    if lane not in LANES:
        return True  # unknown lane — don't skip anything
    return stage in LANES[lane]["stages_active"]


def get_lane_env(lane: str, config_overrides: Optional[dict] = None) -> dict:
    """
    Return the env dict for the given lane WITHOUT applying it to os.environ.
    Useful for dry-run inspection or test assertions.
    """
    if lane not in LANES:
        return {}
    base = dict(LANES[lane]["env"])
    if config_overrides:
        base.update(config_overrides)
    return base


# ── Internal helpers ──────────────────────────────────────────────────────────

def _emit_event(exec_logger, event: dict) -> None:
    """Emit event to execution.jsonl if logger is available."""
    if exec_logger is None:
        return
    try:
        exec_logger.event("lane_dispatched", {k: v for k, v in event.items() if k != "event"})
    except Exception as exc:  # noqa: BLE001
        _logger.debug("lane_dispatcher: failed to emit event: %s", exc)
