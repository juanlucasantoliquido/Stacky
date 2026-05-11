"""
navigation_strategy_resolver.py — Resolves the navigation strategy for each
QA UAT scenario before Playwright test generation.

PURPOSE
-------
Prevents the generator from emitting unguarded `page.goto(screen)` calls
against session-dependent screens (e.g. FrmDetalleClie.aspx).

The resolver reads `navigation_contracts.yml`, checks the lane, inspects
available test data, and returns either:

  ALLOW_GENERATION — strategy, path or deeplink URL resolved
  BLOCKED          — category + reason + human_action_required

CATEGORIES USED
---------------
  NAV   — missing nav path, invalid direct navigation, deeplink context not reconstructed
  DATA  — missing required navigation data (CLCOD, etc.)
  PIP   — strategy forbidden for this lane

USAGE
-----
    from navigation_strategy_resolver import resolve_navigation_strategy

    decision = resolve_navigation_strategy(
        ticket_id=120,
        scenario_id="P02",
        target_screen="FrmDetalleClie.aspx",
        lane="uat_human",
        available_data={"CLCOD": "12345"},
    )
    if decision["decision"] == "BLOCKED":
        # Emit blocked event, skip generation
        ...

CLI (standalone validation):
    python navigation_strategy_resolver.py \
        --ticket 120 --scenario P02 \
        --screen FrmDetalleClie.aspx \
        --lane uat_human \
        --data '{"CLCOD": "12345"}' \
        [--contracts navigation_contracts.yml]

VERSION
-------
1.0 — Initial implementation (Sprint: navigation contracts cuarta parte)
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("stacky.qa_uat.navigation_strategy_resolver")

_TOOL_VERSION = "1.0.0"
_DEFAULT_CONTRACTS_PATH = Path(__file__).resolve().parent / "navigation_contracts.yml"

# ── Lanes that require human path (may NOT use deeplink unless override) ──────
_HUMAN_ONLY_LANES: frozenset[str] = frozenset({
    "uat_human",
    "uat_human_simulation",
    "full-uat",   # full UAT uses human path by default
})

# ── Lanes where deeplink IS preferred ────────────────────────────────────────
_DEEPLINK_PREFERRED_LANES: frozenset[str] = frozenset({
    "smoke_deeplink",
    "regression_deeplink",
    "diagnostic",
    "forensic_rerun",
    "smoke-uat",       # smoke uses deeplink for speed
    "nightly-regression",
})


# ── Contract loader ────────────────────────────────────────────────────────────

def _load_contracts(contracts_path: Optional[Path] = None) -> dict[str, Any]:
    """Load navigation_contracts.yml. Returns empty dict on failure."""
    path = contracts_path or _DEFAULT_CONTRACTS_PATH
    if not path.is_file():
        logger.warning("navigation_contracts.yml not found at %s", path)
        return {}
    try:
        import yaml  # type: ignore
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return data or {}
    except ImportError:
        # Fallback: parse simplified YAML by reading JSON-ish structure
        logger.warning("PyYAML not installed — using simplified contract loader")
        return _load_contracts_fallback(path)
    except Exception as exc:
        logger.error("Failed to load navigation_contracts.yml: %s", exc)
        return {}


def _load_contracts_fallback(path: Path) -> dict[str, Any]:
    """Minimal YAML parser for navigation_contracts without PyYAML dependency.

    Supports only the top-level screen → bool/string/list keys used in this file.
    Falls back to empty dict if the file cannot be parsed.
    """
    try:
        # Try importing yaml again (may have been installed after initial check)
        import yaml  # type: ignore
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        pass
    # Truly minimal: parse only top-level keys and known boolean fields
    # This is only used as last resort.
    result: dict = {}
    current_screen: Optional[str] = None
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not line.startswith(" ") and line.rstrip().endswith(":"):
            current_screen = line.rstrip()[:-1].strip()
            result[current_screen] = {}
        elif current_screen and ":" in stripped and not stripped.startswith("-"):
            key, _, val = stripped.partition(":")
            val = val.strip()
            if val.lower() in ("true", "yes"):
                result[current_screen][key.strip()] = True
            elif val.lower() in ("false", "no"):
                result[current_screen][key.strip()] = False
            elif val:
                result[current_screen][key.strip()] = val
    return result


def get_screen_contract(
    screen: str,
    contracts: Optional[dict] = None,
    contracts_path: Optional[Path] = None,
) -> Optional[dict]:
    """Return the contract dict for a given screen, or None if not found."""
    if contracts is None:
        contracts = _load_contracts(contracts_path)
    return contracts.get(screen)


# ── Core resolver ──────────────────────────────────────────────────────────────

def resolve_navigation_strategy(
    ticket_id: int,
    scenario_id: str,
    target_screen: str,
    lane: str,
    available_data: Optional[dict] = None,
    contracts_path: Optional[Path] = None,
    allow_deeplink_override: bool = False,
) -> dict:
    """
    Resolve the navigation strategy for a single scenario.

    Parameters
    ----------
    ticket_id : int
        ADO ticket identifier (for logging / evidence).
    scenario_id : str
        Scenario identifier within the ticket.
    target_screen : str
        Target screen filename (e.g. "FrmDetalleClie.aspx").
    lane : str
        Execution lane (e.g. "uat_human", "smoke_deeplink", "forensic_rerun").
    available_data : dict | None
        Test data available for this run (e.g. {"CLCOD": "12345"}).
    contracts_path : Path | None
        Override path to navigation_contracts.yml.
    allow_deeplink_override : bool
        If True, allows deeplink even in human-only lanes (must be explicitly
        requested by operator — not set automatically).

    Returns
    -------
    dict — navigation strategy decision:
      {
        "decision": "ALLOW_GENERATION" | "BLOCKED",
        "strategy": "human_path" | "deeplink" | "direct_entry",
        ...
      }
      See module docstring for full examples.
    """
    available_data = available_data or {}
    contracts = _load_contracts(contracts_path)
    contract = contracts.get(target_screen)

    # ── No contract found ────────────────────────────────────────────────────
    if contract is None:
        # Unknown screen — apply safe defaults
        logger.warning(
            "No navigation contract for %s — applying safe defaults (direct_entry_allowed=False)",
            target_screen,
        )
        # Safe default: if lane is human-only, block; otherwise warn and allow
        if lane in _HUMAN_ONLY_LANES:
            return _blocked(
                ticket_id=ticket_id,
                scenario_id=scenario_id,
                target_screen=target_screen,
                lane=lane,
                category="NAV",
                reason="NAV_CONTRACT_MISSING",
                human_action_required=(
                    f"Add a navigation contract for '{target_screen}' in navigation_contracts.yml. "
                    f"Declare whether direct_entry_allowed, deeplink_allowed, and human_paths."
                ),
                extra={
                    "direct_goto_allowed": False,
                    "deeplink_available": False,
                },
            )
        else:
            # Non-human lanes get a best-effort direct entry with warning
            return _allow(
                strategy="direct_entry",
                target_screen=target_screen,
                lane=lane,
                extra={
                    "warning": "NAV_CONTRACT_MISSING — contract not defined, using direct_entry as fallback",
                    "direct_goto_allowed": True,
                    "deeplink_available": False,
                },
            )

    screen_type = contract.get("screen_type", "unknown")
    direct_entry_allowed = bool(contract.get("direct_entry_allowed", False))
    deeplink_allowed = bool(contract.get("deeplink_allowed", False))
    human_path_required = bool(contract.get("human_path_required_for_uat", False))
    deeplink_cfg = contract.get("deeplink") or {}
    human_paths = contract.get("human_paths") or {}

    # ── Determine effective strategy ─────────────────────────────────────────
    is_human_lane = lane in _HUMAN_ONLY_LANES
    is_deeplink_lane = lane in _DEEPLINK_PREFERRED_LANES

    # Check if deeplink is explicitly forbidden for this lane
    deeplink_forbidden_lanes: list = deeplink_cfg.get("forbidden_lanes", [])
    deeplink_allowed_lanes: list = deeplink_cfg.get("allowed_lanes", [])

    deeplink_forbidden_for_lane = lane in deeplink_forbidden_lanes
    deeplink_allowed_for_lane = (
        deeplink_allowed
        and (not deeplink_allowed_lanes or lane in deeplink_allowed_lanes or allow_deeplink_override)
        and (not deeplink_forbidden_for_lane or allow_deeplink_override)
    )

    # ── Case 0: direct entry screens bypass lane restrictions ────────────────
    # Screens like FrmLogin or Default.aspx can always be reached by direct goto.
    if direct_entry_allowed and not human_path_required:
        return _allow(
            strategy="direct_entry",
            target_screen=target_screen,
            lane=lane,
            extra={
                "direct_goto_allowed": True,
                "deeplink_available": deeplink_allowed_for_lane,
            },
        )

    # ── Case 1: human-only lane ───────────────────────────────────────────────
    if is_human_lane and not allow_deeplink_override:
        # Human lane MUST use human path
        if not human_paths:
            return _blocked(
                ticket_id=ticket_id,
                scenario_id=scenario_id,
                target_screen=target_screen,
                lane=lane,
                category="NAV",
                reason="NAV_PATH_MISSING",
                human_action_required=(
                    f"Define a human_path for '{target_screen}' in navigation_contracts.yml. "
                    f"No approved human navigation path exists for lane '{lane}'."
                ),
                extra={
                    "direct_goto_allowed": direct_entry_allowed,
                    "deeplink_available": deeplink_allowed_for_lane,
                    "deeplink_rejected_reason": "lane_requires_human_simulation",
                },
            )
        # Pick the first available human path
        path_id, path_cfg = next(iter(human_paths.items()))
        required_data: list[str] = path_cfg.get("required_data", [])
        missing_data = [k for k in required_data if not available_data.get(k)]
        if missing_data:
            return _blocked(
                ticket_id=ticket_id,
                scenario_id=scenario_id,
                target_screen=target_screen,
                lane=lane,
                category="DATA",
                reason="NAVIGATION_DATA_MISSING",
                human_action_required=(
                    f"Proveer datos faltantes: {missing_data}. "
                    f"Son necesarios para navegar via '{path_id}' a '{target_screen}'."
                ),
                extra={
                    "missing_data": missing_data,
                    "path_id": path_id,
                    "direct_goto_allowed": False,
                    "deeplink_available": deeplink_allowed_for_lane,
                    "deeplink_rejected_reason": "lane_requires_human_simulation",
                },
            )
        return _allow(
            strategy="human_path",
            target_screen=target_screen,
            lane=lane,
            extra={
                "path_id": path_id,
                "entrypoint": path_cfg.get("entrypoint", target_screen),
                "requires_data": required_data,
                "data_available": True,
                "deeplink_available": deeplink_allowed_for_lane,
                "deeplink_rejected_reason": "lane_requires_human_simulation",
                "required_assertions": path_cfg.get("required_assertions", []),
                "direct_goto_allowed": False,
            },
        )

    # ── Case 2: deeplink lane or override ─────────────────────────────────────
    if is_deeplink_lane or (allow_deeplink_override and deeplink_allowed):
        if not deeplink_allowed_for_lane:
            if not deeplink_allowed:
                return _blocked(
                    ticket_id=ticket_id,
                    scenario_id=scenario_id,
                    target_screen=target_screen,
                    lane=lane,
                    category="NAV",
                    reason="DEEPLINK_NOT_SUPPORTED_FOR_SCREEN",
                    human_action_required=(
                        f"Screen '{target_screen}' does not support deeplink. "
                        f"Add a human_path or enable direct_entry_allowed."
                    ),
                    extra={"direct_goto_allowed": direct_entry_allowed},
                )
            if deeplink_forbidden_for_lane:
                return _blocked(
                    ticket_id=ticket_id,
                    scenario_id=scenario_id,
                    target_screen=target_screen,
                    lane=lane,
                    category="PIP",
                    reason="INVALID_NAVIGATION_STRATEGY_FOR_LANE",
                    human_action_required=(
                        f"Lane '{lane}' is in forbidden_lanes for deeplink of '{target_screen}'. "
                        f"Use a human_path or switch to an allowed lane: "
                        f"{deeplink_cfg.get('allowed_lanes', [])}."
                    ),
                    extra={
                        "direct_goto_allowed": direct_entry_allowed,
                        "forbidden_lanes": deeplink_forbidden_lanes,
                    },
                )
        # Validate deeplink params
        required_params: list[str] = deeplink_cfg.get("required_params", [])
        missing_params = [p for p in required_params if not available_data.get(p)]
        if missing_params:
            return _blocked(
                ticket_id=ticket_id,
                scenario_id=scenario_id,
                target_screen=target_screen,
                lane=lane,
                category="DATA",
                reason="DEEPLINK_PARAM_MISSING",
                human_action_required=(
                    f"Deeplink params missing: {missing_params}. "
                    f"Pattern: {deeplink_cfg.get('pattern', target_screen)}. "
                    f"Proveer estos valores en los datos de prueba."
                ),
                extra={
                    "missing_data": missing_params,
                    "deeplink_pattern": deeplink_cfg.get("pattern"),
                    "direct_goto_allowed": False,
                },
            )
        # Build deeplink URL
        pattern = deeplink_cfg.get("pattern", target_screen)
        try:
            url = pattern
            for param in required_params:
                url = url.replace(f"{{{param}}}", str(available_data[param]))
        except Exception:
            url = pattern
        return _allow(
            strategy="deeplink",
            target_screen=target_screen,
            lane=lane,
            extra={
                "url": url,
                "deeplink_pattern": pattern,
                "required_context_assertions": deeplink_cfg.get("required_assertions", []),
                "reconstructs_context": deeplink_cfg.get("reconstructs_context", []),
                "direct_goto_allowed": False,
                "human_path_available": bool(human_paths),
                "human_path_used": False,
            },
        )

    # ── Case 3: direct entry (entrypoint screens) ─────────────────────────────
    if direct_entry_allowed:
        return _allow(
            strategy="direct_entry",
            target_screen=target_screen,
            lane=lane,
            extra={
                "direct_goto_allowed": True,
                "deeplink_available": deeplink_allowed_for_lane,
            },
        )

    # ── Case 4: nothing works — screen requires context but no strategy viable ─
    return _blocked(
        ticket_id=ticket_id,
        scenario_id=scenario_id,
        target_screen=target_screen,
        lane=lane,
        category="NAV",
        reason="INVALID_DIRECT_NAVIGATION_TO_SESSION_DEPENDENT_SCREEN",
        human_action_required=(
            f"Screen '{target_screen}' is session-dependent and cannot be reached by direct goto. "
            f"Define a human_path or enable deeplink in navigation_contracts.yml."
        ),
        extra={
            "direct_goto_allowed": False,
            "deeplink_available": deeplink_allowed_for_lane,
            "screen_type": screen_type,
        },
    )


# ── Builder helpers ───────────────────────────────────────────────────────────

def _allow(strategy: str, target_screen: str, lane: str, extra: dict) -> dict:
    """Build an ALLOW_GENERATION result."""
    return {
        "decision": "ALLOW_GENERATION",
        "strategy": strategy,
        "target_screen": target_screen,
        "lane": lane,
        **extra,
    }


def _blocked(
    ticket_id: int,
    scenario_id: str,
    target_screen: str,
    lane: str,
    category: str,
    reason: str,
    human_action_required: str,
    extra: Optional[dict] = None,
) -> dict:
    """Build a BLOCKED result."""
    result = {
        "decision": "BLOCKED",
        "verdict": "BLOCKED",
        "ticket_id": ticket_id,
        "scenario_id": scenario_id,
        "target_screen": target_screen,
        "lane": lane,
        "category": category,
        "reason": reason,
        "human_action_required": human_action_required,
    }
    if extra:
        result.update(extra)
    return result


# ── Evidence writer ────────────────────────────────────────────────────────────

def write_navigation_contract_validation_event(
    exec_logger,
    ticket_id: int,
    scenario_id: str,
    decision: dict,
) -> None:
    """Write navigation_contract_validation event to execution.jsonl."""
    if exec_logger is None:
        return
    try:
        event_data = {
            "ticket_id": ticket_id,
            "scenario_id": scenario_id,
            "target_screen": decision.get("target_screen"),
            "lane": decision.get("lane"),
            "strategy": decision.get("strategy"),
            "path_id": decision.get("path_id"),
            "direct_goto_allowed": decision.get("direct_goto_allowed", False),
            "deeplink_available": decision.get("deeplink_available", False),
            "deeplink_used": decision.get("strategy") == "deeplink",
            "requires_data": decision.get("requires_data", []),
            "data_available": decision.get("data_available"),
            "decision": decision.get("decision"),
            "category": decision.get("category"),
            "reason": decision.get("reason"),
            "human_action_required": decision.get("human_action_required"),
        }
        exec_logger.event("navigation_contract_validation", event_data)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to emit navigation_contract_validation event: %s", exc)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Resolve navigation strategy for a QA UAT scenario."
    )
    parser.add_argument("--ticket", type=int, required=True)
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--screen", required=True)
    parser.add_argument("--lane", default="uat_human")
    parser.add_argument("--data", default="{}", help="JSON dict of available test data")
    parser.add_argument("--contracts", help="Path to navigation_contracts.yml")
    parser.add_argument(
        "--allow-deeplink-override",
        action="store_true",
        default=False,
        help="Allow deeplink even in human-only lanes (operator override)",
    )
    args = parser.parse_args()

    try:
        available_data = json.loads(args.data)
    except json.JSONDecodeError as exc:
        sys.stderr.write(f"error: --data is not valid JSON: {exc}\n")
        sys.exit(1)

    contracts_path = Path(args.contracts) if args.contracts else None
    decision = resolve_navigation_strategy(
        ticket_id=args.ticket,
        scenario_id=args.scenario,
        target_screen=args.screen,
        lane=args.lane,
        available_data=available_data,
        contracts_path=contracts_path,
        allow_deeplink_override=args.allow_deeplink_override,
    )
    print(json.dumps(decision, ensure_ascii=False, indent=2))
    sys.exit(0 if decision.get("decision") == "ALLOW_GENERATION" else 1)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    main()
