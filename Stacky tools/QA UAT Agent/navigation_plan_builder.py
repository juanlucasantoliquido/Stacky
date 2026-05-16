"""
navigation_plan_builder.py — Sprint N5-05.

Builds a typed NavigationPlan (NavigationPlan/1.0) from the upstream signals
produced by the resolver and the playbook router. Sits between
``navigation_strategy_resolver`` and ``navigation_plan_validator`` in the
pipeline:

    resolver.decide → builder.build → validator.validate → generator.run

INPUTS
------
* ``decision``       — output of ``resolve_navigation_strategy``.
* ``scenario``       — the compiled scenario dict (uses scenario_id, etc.).
* ``available_data`` — dict of CLCOD/OBLCOD/etc.
* ``playbook``       — Playbook/1.0 dict (when the router resolved one).
* ``contracts``      — parsed ``navigation_contracts.yml``.

OUTPUT
------
A NavigationPlan/1.0 dict ready for the validator. Never raises — invalid
inputs produce a plan with a ``BLOCKED`` strategy step that the validator
will reject deterministically.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("stacky.qa_uat.navigation_plan_builder")

_TOOL_VERSION = "1.0.0"

# Default arrival_assertions injected when neither the playbook nor the
# contract supplies them. Keeps R6 satisfiable for legacy contracts during
# the v1→v2 migration (Sprint N5-09).
_DEFAULT_ARRIVAL_TYPES = ("no_aspnet_error", "no_login_redirect", "url_contains")


# ── Public API ──────────────────────────────────────────────────────────────

def build_navigation_plan(
    decision: dict,
    scenario: Optional[dict] = None,
    available_data: Optional[dict] = None,
    playbook: Optional[dict] = None,
    contracts: Optional[dict] = None,
    lane: Optional[str] = None,
) -> dict:
    """Return a NavigationPlan/1.0 dict for the given decision + signals.

    Dispatch:
      * ``decision.strategy == "human_path"`` + playbook → build from playbook.
      * ``decision.strategy == "human_path"`` + no playbook → build from contract.
      * ``decision.strategy == "deeplink"`` → build deeplink plan.
      * ``decision.strategy == "direct_entry"`` → build single-step plan.
      * Anything else → produce a degenerate plan whose validator rejects R2.

    The result is intentionally permissive on input shape and strict on
    output shape (matches NavigationPlan/1.0).
    """
    scenario = scenario or {}
    available_data = available_data or {}
    contracts = contracts or {}
    lane = lane or decision.get("lane") or scenario.get("lane") or "uat_human"

    ticket_id = scenario.get("ticket_id") or decision.get("ticket_id") or 0
    scenario_id = scenario.get("scenario_id") or decision.get("scenario_id") or "unknown"
    target_screen = decision.get("target_screen") or scenario.get("pantalla") or ""

    strategy = (decision.get("strategy") or "").strip()

    if strategy == "human_path":
        plan = _build_from_playbook(
            playbook=playbook,
            decision=decision,
            available_data=available_data,
            ticket_id=ticket_id,
            scenario_id=scenario_id,
            target_screen=target_screen,
            lane=lane,
            contracts=contracts,
        ) if playbook else _build_from_contract_human_path(
            decision=decision,
            available_data=available_data,
            ticket_id=ticket_id,
            scenario_id=scenario_id,
            target_screen=target_screen,
            lane=lane,
            contracts=contracts,
        )
    elif strategy == "deeplink":
        plan = _build_deeplink(
            decision=decision,
            available_data=available_data,
            ticket_id=ticket_id,
            scenario_id=scenario_id,
            target_screen=target_screen,
            lane=lane,
            contracts=contracts,
        )
    elif strategy == "direct_entry":
        plan = _build_direct(
            decision=decision,
            ticket_id=ticket_id,
            scenario_id=scenario_id,
            target_screen=target_screen,
            lane=lane,
            contracts=contracts,
        )
    else:
        plan = _build_degenerate(
            decision=decision,
            ticket_id=ticket_id,
            scenario_id=scenario_id,
            target_screen=target_screen,
            lane=lane,
        )

    # Stamp metadata always present so downstream consumers can audit lineage.
    plan["resolved_at"] = datetime.now(timezone.utc).isoformat()
    plan["resolver_version"] = _TOOL_VERSION
    return plan


# ── Strategy-specific builders ──────────────────────────────────────────────

def _build_from_playbook(
    playbook: dict,
    decision: dict,
    available_data: dict,
    ticket_id: Any,
    scenario_id: str,
    target_screen: str,
    lane: str,
    contracts: dict,
) -> dict:
    """Use the playbook's typed navigation_steps + arrival_assertions verbatim."""
    steps = list(playbook.get("navigation_steps") or [])
    arrival = list(playbook.get("arrival_assertions") or [])
    arrival = _ensure_default_arrivals(arrival, target_screen, contracts)

    return {
        "plan_version": "1.0",
        "ticket_id": ticket_id,
        "scenario_id": scenario_id,
        "target_screen": target_screen,
        "lane": lane,
        "strategy": "human_path",
        "path_id": decision.get("path_id"),
        "playbook_id": playbook.get("playbook_id"),
        "entrypoint": playbook.get("entry_screen") or decision.get("entrypoint") or target_screen,
        "deeplink_url": None,
        "steps": steps,
        "arrival_assertions": arrival,
        "session_requirements": _default_session_requirements(target_screen, contracts),
    }


def _build_from_contract_human_path(
    decision: dict,
    available_data: dict,
    ticket_id: Any,
    scenario_id: str,
    target_screen: str,
    lane: str,
    contracts: dict,
) -> dict:
    """Synthesize a plan from the contract's `human_paths[path_id].steps` when
    no playbook is available."""
    path_id = decision.get("path_id")
    contract = contracts.get(target_screen) or {}
    human_paths = contract.get("human_paths") or {}
    path = human_paths.get(path_id) if path_id else None
    entrypoint = (path or {}).get("entrypoint") or target_screen

    # Contracts v1 store steps as plain strings (descriptive). Build a single
    # navigation step that goes to the entrypoint plus a marker step instructing
    # the executor to fall back to the recorded human path. Validator will
    # reject this if no playbook is available later, but it lets us flag the
    # gap deterministically.
    raw_steps = (path or {}).get("steps") or []
    steps: list[dict] = [
        {
            "step_index": 1,
            "method": "goto_direct",
            "description": f"Enter human_path via {entrypoint}",
            "target_url": entrypoint,
            "wait_url_contains": _bare_screen(entrypoint),
            "timeout_ms": 20_000,
            "retries": 0,
        },
    ]
    for i, raw in enumerate(raw_steps, start=2):
        steps.append({
            "step_index": i,
            "method": "wait",
            "description": str(raw),
        })

    arrival = _ensure_default_arrivals([], target_screen, contracts)

    return {
        "plan_version": "1.0",
        "ticket_id": ticket_id,
        "scenario_id": scenario_id,
        "target_screen": target_screen,
        "lane": lane,
        "strategy": "human_path",
        "path_id": path_id,
        "playbook_id": None,
        "entrypoint": entrypoint,
        "deeplink_url": None,
        "steps": steps,
        "arrival_assertions": arrival,
        "session_requirements": _default_session_requirements(target_screen, contracts),
    }


def _build_deeplink(
    decision: dict,
    available_data: dict,
    ticket_id: Any,
    scenario_id: str,
    target_screen: str,
    lane: str,
    contracts: dict,
) -> dict:
    url = decision.get("url") or decision.get("deeplink_url") or target_screen
    pattern = decision.get("deeplink_pattern") or target_screen
    steps = [
        {
            "step_index": 1,
            "method": "goto_deeplink",
            "description": f"Open via deeplink: {pattern}",
            "target_url": url,
            "wait_url_contains": _bare_screen(target_screen),
            "timeout_ms": 30_000,
            "retries": 0,
        },
    ]
    arrival = _ensure_default_arrivals([], target_screen, contracts)
    return {
        "plan_version": "1.0",
        "ticket_id": ticket_id,
        "scenario_id": scenario_id,
        "target_screen": target_screen,
        "lane": lane,
        "strategy": "deeplink",
        "path_id": None,
        "playbook_id": None,
        "entrypoint": target_screen,
        "deeplink_url": url,
        "steps": steps,
        "arrival_assertions": arrival,
        "session_requirements": _default_session_requirements(target_screen, contracts),
    }


def _build_direct(
    decision: dict,
    ticket_id: Any,
    scenario_id: str,
    target_screen: str,
    lane: str,
    contracts: dict,
) -> dict:
    steps = [
        {
            "step_index": 1,
            "method": "goto_direct",
            "description": f"Open {target_screen} via direct entry",
            "target_url": target_screen,
            "wait_url_contains": _bare_screen(target_screen),
            "timeout_ms": 20_000,
            "retries": 0,
        },
    ]
    arrival = _ensure_default_arrivals([], target_screen, contracts)
    return {
        "plan_version": "1.0",
        "ticket_id": ticket_id,
        "scenario_id": scenario_id,
        "target_screen": target_screen,
        "lane": lane,
        "strategy": "direct_entry",
        "path_id": None,
        "playbook_id": None,
        "entrypoint": target_screen,
        "deeplink_url": None,
        "steps": steps,
        "arrival_assertions": arrival,
        "session_requirements": _default_session_requirements(target_screen, contracts, allow_direct=True),
    }


def _build_degenerate(
    decision: dict,
    ticket_id: Any,
    scenario_id: str,
    target_screen: str,
    lane: str,
) -> dict:
    """Last-resort plan when strategy is unknown — validator will reject."""
    return {
        "plan_version": "1.0",
        "ticket_id": ticket_id,
        "scenario_id": scenario_id,
        "target_screen": target_screen,
        "lane": lane,
        "strategy": decision.get("strategy") or "human_path",
        "path_id": None,
        "playbook_id": None,
        "entrypoint": target_screen,
        "deeplink_url": None,
        "steps": [
            {
                "step_index": 1,
                "method": "wait",
                "description": "Unresolved navigation strategy — validator will block.",
            },
        ],
        "arrival_assertions": _ensure_default_arrivals([], target_screen, contracts={}),
        "session_requirements": _default_session_requirements(target_screen, {}),
    }


# ── Helpers ─────────────────────────────────────────────────────────────────

def _ensure_default_arrivals(
    existing: list[dict],
    target_screen: str,
    contracts: dict,
) -> list[dict]:
    """Guarantee at least `no_aspnet_error` and `url_contains` are present.

    Honors the screen's v2 ``arrival_assertions`` block from the contract when
    declared (Sprint N5-09); otherwise injects synthesized defaults so the
    plan satisfies R6 of navigation_plan_validator.
    """
    out: list[dict] = list(existing)
    # If the v2 contract declares arrival_assertions, merge them in.
    contract = (contracts or {}).get(target_screen) or {}
    contract_arrivals = contract.get("arrival_assertions") or []
    for ca in contract_arrivals:
        if isinstance(ca, dict) and not any(a.get("assertion_id") == ca.get("assertion_id") for a in out):
            out.append(dict(ca))

    seen_types = {a.get("type") for a in out if isinstance(a, dict)}

    for assertion in default_arrival_assertions_for_screen(target_screen):
        if assertion["type"] not in seen_types:
            out.append(assertion)
            seen_types.add(assertion["type"])
    return out


def default_arrival_assertions_for_screen(target_screen: str, timeout_ms: int = 5_000) -> list[dict]:
    """Backward-compatible v1 contract defaults required by Sprint N5-09."""
    bare = _bare_screen(target_screen)
    return [
        {
            "assertion_id": "no_aspnet_error_default",
            "type": "no_aspnet_error",
            "description": "Default: no YSOD nor Errors.aspx visible",
            "severity": "hard",
            "category_on_fail": "ENV",
            "timeout_ms": timeout_ms,
        },
        {
            "assertion_id": "no_login_redirect_default",
            "type": "no_login_redirect",
            "description": "Default: not redirected to FrmLogin",
            "severity": "hard",
            "category_on_fail": "ENV",
            "timeout_ms": timeout_ms,
        },
        {
            "assertion_id": "url_contains_default",
            "type": "url_contains",
            "expected_value": bare,
            "description": f"Default: URL contains {bare}",
            "severity": "hard",
            "category_on_fail": "NAV",
            "timeout_ms": timeout_ms,
        },
    ]


def _default_session_requirements(
    target_screen: str,
    contracts: dict,
    allow_direct: bool = False,
) -> dict:
    """Default session requirements per screen.

    Direct-entry screens that explicitly opt-out (e.g. FrmLogin) get no
    session requirement. All other screens require a fresh storageState.
    """
    contract = (contracts or {}).get(target_screen) or {}
    screen_type = contract.get("screen_type", "unknown")
    if allow_direct and screen_type == "entrypoint" and target_screen.lower().startswith("frmlogin"):
        return {"require_valid_storagestate": False, "storagestate_max_age_minutes": 120}
    return {"require_valid_storagestate": True, "storagestate_max_age_minutes": 120}


def _bare_screen(screen_or_url: str) -> str:
    """'FrmDetalleClie.aspx?clcod=1' → 'FrmDetalleClie'."""
    if not isinstance(screen_or_url, str) or not screen_or_url:
        return ""
    head = screen_or_url.split("?", 1)[0].split("#", 1)[0]
    head = head.rstrip("/")
    if "/" in head:
        head = head.rsplit("/", 1)[-1]
    return head.replace(".aspx", "").replace(".ASPX", "")
