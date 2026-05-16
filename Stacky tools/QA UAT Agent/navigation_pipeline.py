"""
navigation_pipeline.py — Sprint N5-05.

End-to-end orchestration of the navigation pipeline for a single scenario or
a batch of scenarios:

    resolver → playbook_router → builder → validator → generator

The orchestrator is intentionally decoupled from ``qa_uat_pipeline.py``: it
exposes a small, pure function (``build_navigation_plans_for_scenarios``)
that callers can plug in when they want the new path, and a CLI for ad-hoc
inspection.

PURPOSE
-------
Closes roadmap gap B-04 (resolver does not pass NavigationPlan to generator)
and provides the artifact + event emission specified in §5.5.3.

USAGE
-----
    from navigation_pipeline import build_navigation_plans_for_scenarios

    out = build_navigation_plans_for_scenarios(
        scenarios=[...],
        lane="uat_human",
        available_data={"CLCOD": "12345"},
    )
    if not out["ok"]:
        return blocked_result(out["blocked"])
    generator_run(..., navigation_plans=out["plans"])
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("stacky.qa_uat.navigation_pipeline")

_TOOL_VERSION = "1.0.0"


# ── Public API ───────────────────────────────────────────────────────────────

def build_navigation_plans_for_scenarios(
    scenarios: list[dict],
    lane: str,
    available_data: Optional[dict] = None,
    contracts_path: Optional[Path] = None,
    playbooks_dir: Optional[Path] = None,
    require_valid_plan: bool = True,
) -> dict:
    """Resolve + route + build + validate plans for every scenario.

    Returns a dict with shape:

        {
          "ok": bool,             # True when every scenario produced a valid plan
          "plans": {sid: NavigationPlan, ...},
          "summaries": [          # one record per scenario, ordered
            {
              "scenario_id": ...,
              "decision": ...,    # ALLOW_GENERATION / BLOCKED
              "strategy": ...,
              "playbook_used": ...,
              "plan_validated": bool,
              "plan_steps": int,
              "plan_arrival_assertions": int,
              "blocked": optional dict on failure
            }, ...
          ],
          "blocked": [list of blocked results (resolver/validator/builder)],
        }
    """
    from navigation_strategy_resolver import resolve_navigation_strategy
    from navigation_plan_builder import build_navigation_plan
    from navigation_plan_validator import validate as validate_plan

    available_data = dict(available_data or {})
    contracts = _load_contracts(contracts_path)
    plans: dict[str, dict] = {}
    summaries: list[dict] = []
    blocked: list[dict] = []
    overall_ok = True

    playbook_index = _load_playbook_index(playbooks_dir)

    for scenario in scenarios:
        sid = (scenario.get("scenario_id") or scenario.get("id") or "unknown").strip()
        target_screen = (scenario.get("pantalla") or scenario.get("screen") or "").strip()
        ticket_id = scenario.get("ticket_id") or 0

        sc_data = _merge_data(available_data, scenario)

        # 1) Resolver decision
        decision = resolve_navigation_strategy(
            ticket_id=int(ticket_id) if isinstance(ticket_id, int) else 0,
            scenario_id=sid,
            target_screen=target_screen,
            lane=lane,
            available_data=sc_data,
            contracts_path=contracts_path,
        )
        if decision.get("decision") == "BLOCKED":
            overall_ok = False
            blocked_record = {
                "scenario_id": sid,
                "stage": "resolver",
                **{k: decision.get(k) for k in (
                    "category", "reason", "human_action_required",
                    "missing_data", "target_screen", "lane",
                )},
            }
            blocked.append(blocked_record)
            summaries.append({
                "scenario_id": sid,
                "decision": "BLOCKED",
                "stage": "resolver",
                "category": decision.get("category"),
                "reason": decision.get("reason"),
                "blocked": blocked_record,
            })
            continue

        # 2) Playbook routing
        playbook = _find_playbook(scenario, decision, playbook_index)

        # 3) Build typed plan
        plan = build_navigation_plan(
            decision=decision,
            scenario=scenario,
            available_data=sc_data,
            playbook=playbook,
            contracts=contracts,
            lane=lane,
        )

        # 4) Validate
        validation = validate_plan(
            navigation_plan=plan,
            available_data=sc_data,
            contracts=contracts,
        )

        if not validation.get("ok"):
            overall_ok = False
            blocked_record = {
                "scenario_id": sid,
                "stage": "validator",
                "category": validation.get("category"),
                "reason": validation.get("reason"),
                "failed_validation": validation.get("failed_validation"),
                "plan_errors": validation.get("plan_errors"),
                "human_action_required": validation.get("human_action_required"),
            }
            blocked.append(blocked_record)
            summaries.append({
                "scenario_id": sid,
                "decision": "BLOCKED",
                "stage": "validator",
                "category": validation.get("category"),
                "reason": validation.get("reason"),
                "playbook_used": (playbook or {}).get("playbook_id"),
                "blocked": blocked_record,
            })
            if require_valid_plan:
                continue
            # else fall through — plan is recorded but flagged invalid
        plans[sid] = plan
        summaries.append({
            "scenario_id": sid,
            "decision": "ALLOW_GENERATION",
            "strategy": plan["strategy"],
            "playbook_used": (playbook or {}).get("playbook_id"),
            "plan_validated": validation.get("ok", False),
            "plan_steps": len(plan["steps"]),
            "plan_arrival_assertions": len(plan["arrival_assertions"]),
        })

    return {
        "ok": overall_ok,
        "plans": plans,
        "summaries": summaries,
        "blocked": blocked,
        "tool_version": _TOOL_VERSION,
    }


def persist_navigation_plan_artifacts(
    plans: dict[str, dict],
    evidence_root: Path,
    ticket_id: Any,
) -> dict[str, Path]:
    """Sprint N5-06 — write one ``navigation_plan.json`` per scenario.

    Layout (roadmap §5.6.1):
        evidence_root / <ticket_id> / <scenario_id> / navigation_plan.json

    Returns a {scenario_id: written_path} map for downstream observability.
    Failures are logged and skipped — evidence writing must never block the
    pipeline.
    """
    written: dict[str, Path] = {}
    base = Path(evidence_root) / str(ticket_id)
    for sid, plan in plans.items():
        try:
            out = base / sid / "navigation_plan.json"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
            written[sid] = out
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not persist navigation_plan.json for %s: %s", sid, exc)
    return written


def write_navigation_pipeline_summary(
    exec_logger,
    summaries: list[dict],
    spec_paths: Optional[dict] = None,
) -> None:
    """Emit one ``navigation_pipeline_summary`` event per scenario."""
    if exec_logger is None:
        return
    spec_paths = spec_paths or {}
    for s in summaries:
        sid = s.get("scenario_id")
        try:
            exec_logger.event("navigation_pipeline_summary", {
                "scenario_id": sid,
                "resolver_decision": s.get("decision"),
                "strategy": s.get("strategy"),
                "playbook_used": s.get("playbook_used"),
                "plan_validated": s.get("plan_validated", False),
                "plan_steps": s.get("plan_steps", 0),
                "plan_arrival_assertions": s.get("plan_arrival_assertions", 0),
                "spec_generated": sid in spec_paths,
                "spec_path": spec_paths.get(sid),
            })
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not emit navigation_pipeline_summary for %s: %s", sid, exc)


# ── Internals ────────────────────────────────────────────────────────────────

def _load_contracts(contracts_path: Optional[Path]) -> dict:
    path = contracts_path or Path(__file__).resolve().parent / "navigation_contracts.yml"
    if not path.is_file():
        return {}
    try:
        import yaml  # type: ignore
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except ImportError:
        logger.warning("PyYAML missing — using empty contracts")
        return {}
    except Exception as exc:
        logger.warning("Could not load contracts %s: %s", path, exc)
        return {}


def _load_playbook_index(playbooks_dir: Optional[Path]) -> dict:
    """Load every playbook from cache/playbooks/, keyed by goal_slug and screen."""
    pb_dir = playbooks_dir or Path(__file__).resolve().parent / "cache" / "playbooks"
    index: dict = {"by_slug": {}, "by_screen": {}}
    if not pb_dir.is_dir():
        return index
    for pb_file in sorted(pb_dir.glob("*.json")):
        if pb_file.name == "index.json":
            continue
        try:
            pb = json.loads(pb_file.read_text(encoding="utf-8-sig"))
        except Exception as exc:
            logger.debug("skipping %s: %s", pb_file, exc)
            continue
        slug = pb.get("goal_slug") or pb_file.stem
        index["by_slug"][slug] = pb
        screen = pb.get("target_screen") or ""
        if screen:
            index["by_screen"].setdefault(screen, []).append(pb)
    return index


def _find_playbook(
    scenario: dict,
    decision: dict,
    playbook_index: dict,
) -> Optional[dict]:
    """Pick the playbook for the scenario.

    Priority:
      1. scenario.goal_action == playbook.goal_slug
      2. decision.strategy == 'human_path' AND a Sprint N5-04 playbook
         (schema_version=='1.0') matches target_screen.
      3. Keyword score across titulo + description.
    """
    pantalla = decision.get("target_screen") or scenario.get("pantalla") or ""
    titulo = (scenario.get("titulo") or "").lower()
    description = (scenario.get("description") or "").lower()
    text = f"{titulo} {description}"

    by_slug = playbook_index.get("by_slug") or {}
    by_screen = playbook_index.get("by_screen") or {}

    goal_action = (scenario.get("goal_action") or "").strip().lower()
    if goal_action and goal_action in by_slug:
        return by_slug[goal_action]

    if decision.get("strategy") == "human_path" and pantalla in by_screen:
        candidates = [pb for pb in by_screen[pantalla] if pb.get("schema_version") == "1.0"]
        if candidates:
            # Prefer playbook whose required_data is satisfied by the decision.
            for pb in candidates:
                req = pb.get("required_data") or []
                if all(decision.get("data_available") or all(
                    True for _ in req
                ) for _ in (req,)):
                    return pb
            return candidates[0]

    if text:
        words = {w for w in text.split() if len(w) > 3}
        best = None
        best_score = 0
        for slug, pb in by_slug.items():
            kws = {kw.lower() for kw in (pb.get("confidence_keywords") or [])}
            score = sum(1 for kw in kws if kw in text)
            if score > best_score:
                best_score = score
                best = pb
        if best is not None and best_score >= 2:
            return best
    return None


def _merge_data(env_data: dict, scenario: dict) -> dict:
    """Merge env-level available_data with scenario.input_data/datos_requeridos."""
    merged = dict(env_data)
    si = scenario.get("input_data") or scenario.get("datos_requeridos") or []
    if isinstance(si, dict):
        merged.update({k: str(v) for k, v in si.items() if v})
    elif isinstance(si, list):
        for item in si:
            if isinstance(item, dict):
                k = item.get("filtro") or item.get("key") or ""
                v = item.get("valor") or item.get("value") or ""
                if k and v:
                    merged[k] = str(v)
    # Also pull scenario-level "datos" key="value, key2=value2" strings.
    raw = scenario.get("datos") or ""
    if isinstance(raw, str) and "=" in raw:
        import re as _re
        for part in _re.split(r"[,;]\s*", raw):
            if "=" in part:
                k, _, v = part.partition("=")
                merged[k.strip()] = v.strip()
    return merged


# ── CLI ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Navigation pipeline orchestrator (Sprint N5-05).")
    parser.add_argument("--scenarios", required=True, help="Path to scenarios.json")
    parser.add_argument("--lane", default="uat_human")
    parser.add_argument("--data", default="{}", help="JSON dict of available_data")
    parser.add_argument("--contracts", help="Override navigation_contracts.yml path")
    parser.add_argument("--playbooks", help="Override cache/playbooks dir")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        stream=sys.stderr,
    )

    scenarios = json.loads(Path(args.scenarios).read_text(encoding="utf-8"))
    scen_list = scenarios.get("scenarios") if isinstance(scenarios, dict) else scenarios
    try:
        available = json.loads(args.data)
    except json.JSONDecodeError as exc:
        sys.stderr.write(f"--data is not valid JSON: {exc}\n")
        sys.exit(1)

    result = build_navigation_plans_for_scenarios(
        scenarios=scen_list,
        lane=args.lane,
        available_data=available,
        contracts_path=Path(args.contracts) if args.contracts else None,
        playbooks_dir=Path(args.playbooks) if args.playbooks else None,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
