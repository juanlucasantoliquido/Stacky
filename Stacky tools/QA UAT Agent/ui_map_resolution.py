"""
ui_map_resolution.py — Sprint 2: UI Map gate & resolution artifact.

PURPOSE
-------
Centralise the UI map readiness check for all screens detected by screen_detector.
For each screen, verifies whether a cached UI map exists (and optionally attempts
a rebuild).  Produces a consolidated ui_map_resolution.json artifact so the pipeline
has a single, auditable record of the UI map decision for every run.

GATE BEHAVIOR
-------------
- If ALL required screens have a valid cached UI map → ALLOW (ok=True)
- If ANY required screen is missing its UI map AND rebuild fails/not attempted:
    → BLOCKED GEN UI_MAP_MISSING

ARTIFACT (written to evidence_dir)
-----------------------------------
    ui_map_resolution.json
    {
      "ok": true|false,
      "screens": [
        {
          "screen": "FrmDetalleClie.aspx",
          "cache_hit": false,
          "rebuild_attempted": true,
          "rebuild_ok": false,
          "reason": "UI_MAP_MISSING",
          "cache_path": "cache/ui_maps/FrmDetalleClie.aspx.json"
        }
      ],
      "decision": "ALLOW"|"BLOCKED",
      "reason": "UI_MAP_MISSING"|null,
      "missing_screens": ["FrmDetalleClie.aspx"],
      "human_action_required": "...",
      "artifact_path": "evidence/122/<run_id>/ui_map_resolution.json"
    }

EVENT
-----
Emits ui_map_resolution event to execution.jsonl via exec_logger.

ENV VARS
--------
QA_UAT_ALLOW_UI_DISCOVERY   "true" to allow browser-based UI map rebuild (default: false)
QA_UAT_UI_MAP_CACHE_DIR     override cache dir (default: <tool_root>/cache/ui_maps)

USAGE
-----
    from ui_map_resolution import resolve_ui_maps

    result = resolve_ui_maps(
        screens=["FrmDetalleClie.aspx", "FrmAgenda.aspx"],
        evidence_dir=Path("evidence/122/uat-122-.../"),
        run_id="uat-122-...",
        exec_logger=_exec_log,
        verbose=False,
    )
    if result["decision"] == "BLOCKED":
        # return early — do NOT open browser, do NOT generate specs
        ...
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.qa_uat.ui_map_resolution")

_TOOL_ROOT = Path(__file__).parent
_DEFAULT_CACHE_DIR = _TOOL_ROOT / "cache" / "ui_maps"


# ── Public API ─────────────────────────────────────────────────────────────────

def resolve_ui_maps(
    screens: list[str],
    evidence_dir: Optional[Path] = None,
    run_id: Optional[str] = None,
    exec_logger=None,
    verbose: bool = False,
    allow_rebuild: Optional[bool] = None,
) -> dict:
    """Check UI map readiness for all required screens.

    Parameters
    ----------
    screens : list[str]
        Canonical screen filenames (e.g. ["FrmDetalleClie.aspx"]).
    evidence_dir : Path | None
        Run-specific evidence directory.  If provided, writes ui_map_resolution.json.
    run_id : str | None
        Run identifier for the artifact path.
    exec_logger : ExecutionLogger | None
        If provided, emits ui_map_resolution event to execution.jsonl.
    verbose : bool
        Enable debug logging.
    allow_rebuild : bool | None
        Override for QA_UAT_ALLOW_UI_DISCOVERY.  None reads from env.

    Returns
    -------
    dict
        ok, decision, reason, screens, missing_screens, human_action_required,
        artifact_path.
    """
    started = time.time()

    cache_dir = Path(
        os.environ.get("QA_UAT_UI_MAP_CACHE_DIR", "").strip()
        or str(_DEFAULT_CACHE_DIR)
    )

    if allow_rebuild is None:
        allow_rebuild = os.environ.get("QA_UAT_ALLOW_UI_DISCOVERY", "false").lower() in (
            "1", "true", "yes"
        )

    screen_results = []
    missing_screens = []

    for screen in screens:
        cache_path = cache_dir / f"{screen}.json"
        cache_hit = cache_path.is_file()

        rebuild_attempted = False
        rebuild_ok = False
        reason = None

        if cache_hit:
            # Validate schema version before accepting cache
            try:
                cached = json.loads(cache_path.read_text(encoding="utf-8"))
                schema_ver = cached.get("schema_version", "ui_map/1.0")
                # Accept 1.0 and 1.1 — reject anything unrecognised
                if not schema_ver.startswith("ui_map/"):
                    cache_hit = False
                    reason = "UI_MAP_SCHEMA_INVALID"
                    logger.warning(
                        "ui_map_resolution: cache for %s has invalid schema %s — treating as missing",
                        screen, schema_ver,
                    )
            except Exception as exc:  # noqa: BLE001
                cache_hit = False
                reason = "UI_MAP_CACHE_CORRUPT"
                logger.warning(
                    "ui_map_resolution: cache for %s is corrupt (%s) — treating as missing",
                    screen, exc,
                )

        if not cache_hit and allow_rebuild:
            rebuild_attempted = True
            try:
                from ui_map_builder import run as _ui_map_run
                _rebuild = _ui_map_run(screen=screen, rebuild=True, verbose=verbose)
                rebuild_ok = bool(_rebuild.get("ok"))
                if not rebuild_ok:
                    reason = "UI_MAP_REBUILD_FAILED"
                    logger.warning(
                        "ui_map_resolution: rebuild failed for %s: %s",
                        screen, _rebuild.get("message", _rebuild.get("error")),
                    )
            except Exception as exc:  # noqa: BLE001
                rebuild_ok = False
                reason = "UI_MAP_REBUILD_ERROR"
                logger.warning("ui_map_resolution: rebuild error for %s: %s", screen, exc)

        available = cache_hit or rebuild_ok

        if not available:
            reason = reason or "UI_MAP_MISSING"
            missing_screens.append(screen)

        screen_results.append({
            "screen": screen,
            "cache_hit": cache_hit,
            "rebuild_attempted": rebuild_attempted,
            "rebuild_ok": rebuild_ok,
            "available": available,
            "reason": reason,
            "cache_path": str(cache_path),
        })
        logger.debug(
            "ui_map_resolution: screen=%s cache_hit=%s rebuild=%s available=%s reason=%s",
            screen, cache_hit, rebuild_attempted, available, reason,
        )

    decision = "ALLOW" if not missing_screens else "BLOCKED"
    ok = decision == "ALLOW"
    primary_reason = "UI_MAP_MISSING" if missing_screens else None
    human_action = None
    if missing_screens:
        screens_str = ", ".join(missing_screens)
        human_action = (
            f"UI map missing for: {screens_str}. "
            f"Run: python ui_map_builder.py --screen <screen> --rebuild"
        )

    elapsed_ms = int((time.time() - started) * 1000)

    result = {
        "ok": ok,
        "decision": decision,
        "reason": primary_reason,
        "screens": screen_results,
        "missing_screens": missing_screens,
        "allow_rebuild": allow_rebuild,
        "elapsed_ms": elapsed_ms,
        "human_action_required": human_action,
        "artifact_path": None,
    }

    # ── Write artifact ─────────────────────────────────────────────────────
    if evidence_dir is not None:
        try:
            evidence_dir.mkdir(parents=True, exist_ok=True)
            artifact_path = evidence_dir / "ui_map_resolution.json"
            artifact_path.write_text(
                json.dumps(result, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            result["artifact_path"] = str(artifact_path)
        except Exception as exc:  # noqa: BLE001
            logger.warning("ui_map_resolution: failed to write artifact: %s", exc)

    # ── Emit event ─────────────────────────────────────────────────────────
    if exec_logger is not None:
        try:
            exec_logger.event("ui_map_resolution", {
                "ok": ok,
                "decision": decision,
                "reason": primary_reason,
                "missing_screens": missing_screens,
                "screens_checked": len(screens),
                "screens_available": len(screens) - len(missing_screens),
                "allow_rebuild": allow_rebuild,
                "elapsed_ms": elapsed_ms,
                "artifact_path": result.get("artifact_path"),
                "human_action_required": human_action,
            })
        except Exception:  # noqa: BLE001
            pass

    return result
