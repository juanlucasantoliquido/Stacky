"""
navigation_plan_validator.py — Sprint N5-02.

Validates a NavigationPlan (NavigationPlan/1.0) before the generator emits
TypeScript. Acts as a hard gate between the resolver/builder and the
playwright_test_generator, preventing the family of bugs where a plan with
a missing selector / direct goto to a session screen / unresolved
data_binding slips through and produces a spec that fails at runtime with
an opaque error.

The validator enforces the eight rules listed in roadmap §5.2.3:

  R1. Plan has at least one step.
  R2. Each step has a valid enum `method`.
  R3. Steps with `method=fill` have non-empty `selector` and `data_bindings`.
  R4. Steps with `method=form_submit` have `eventtarget` and `wait_url_contains`.
  R5. Steps with `method=goto_direct` or `goto_deeplink` have `target_url`.
  R6. `arrival_assertions` includes at least `no_aspnet_error` and `url_contains`.
  R7. Every `data_bindings` value resolves against `available_data`.
  R8. No `method=goto_direct` step targets a screen with
      direct_entry_allowed: false in navigation_contracts.yml.

USAGE
-----
    from navigation_plan_validator import validate

    result = validate(
        navigation_plan=plan,
        available_data={"CLCOD": "12345"},
        contracts_path=Path(".../navigation_contracts.yml"),
    )
    if not result["ok"]:
        # BLOCKED — propagate result["category"], result["reason"],
        # result["plan_errors"] to execution.jsonl + result.json.
        ...

CLI
---
    python navigation_plan_validator.py \\
        --plan plan.json \\
        --data data.json \\
        [--contracts navigation_contracts.yml] \\
        [--schema schemas/NavigationPlan.schema.json]

VERSION
-------
1.0 — Initial implementation (Sprint N5-02).
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("stacky.qa_uat.navigation_plan_validator")

_TOOL_VERSION = "1.0.0"
_DEFAULT_SCHEMA_PATH = Path(__file__).resolve().parent / "schemas" / "NavigationPlan.schema.json"
_DEFAULT_CONTRACTS_PATH = Path(__file__).resolve().parent / "navigation_contracts.yml"

# Methods enumerated by NavigationPlan/1.0 — kept in sync with the JSON schema.
_VALID_METHODS: frozenset[str] = frozenset({
    "goto_direct",
    "goto_deeplink",
    "form_submit",
    "dopostback",
    "link_click",
    "menu_click",
    "row_click",
    "tab_click",
    "button_click",
    "fill",
    "select",
    "check",
    "wait",
})

# Minimum arrival_assertion types every plan must declare. See R6.
_REQUIRED_ARRIVAL_TYPES: frozenset[str] = frozenset({
    "no_aspnet_error",
    "no_login_redirect",
    "url_contains",
})


# ── Public API ───────────────────────────────────────────────────────────────

def validate(
    navigation_plan: dict,
    available_data: Optional[dict] = None,
    contracts: Optional[dict] = None,
    contracts_path: Optional[Path] = None,
    schema_path: Optional[Path] = None,
) -> dict:
    """Validate a NavigationPlan against the schema and the eight rules.

    Returns the same shape regardless of outcome — callers must inspect
    ``result["ok"]``. Successful output (roadmap §5.2.2):

        {
          "ok": true,
          "plan_id": "120_P02",
          "validation_version": "1.0",
          "steps_validated": 4,
          "data_bindings_resolved": {...},
          "assertions_declared": 5,
          "warnings": []
        }

    Blocking output:

        {
          "ok": false,
          "verdict": "BLOCKED",
          "category": "PIP",
          "reason": "INVALID_NAV_PLAN",
          "failed_validation": "step_index_2_missing_selector",
          "plan_errors": [...],
          "human_action_required": "..."
        }
    """
    available_data = available_data or {}
    plan_errors: list[dict] = []
    warnings: list[str] = []

    # ── Schema validation (jsonschema). Soft fallback when lib missing. ──
    schema_errors = _validate_against_schema(navigation_plan, schema_path)
    if schema_errors:
        return _blocked(
            navigation_plan,
            reason="INVALID_NAV_PLAN",
            failed_validation="schema_validation",
            plan_errors=schema_errors,
            human_action_required=(
                "El NavigationPlan no cumple con NavigationPlan/1.0. "
                "Revisar los campos requeridos / tipos antes de regenerar."
            ),
        )

    # Pull primitives for the rule checks (already shape-validated).
    steps = navigation_plan.get("steps") or []
    assertions = navigation_plan.get("arrival_assertions") or []

    # ── R1: at least one step ─────────────────────────────────────────────
    if not steps:
        plan_errors.append({
            "rule": "R1_AT_LEAST_ONE_STEP",
            "error": "navigation_plan.steps is empty",
        })

    # ── R2..R5: per-step structural rules ─────────────────────────────────
    for step in steps:
        _check_step_rules(step, plan_errors)

    # ── R6: arrival_assertions completeness ───────────────────────────────
    seen_types = {a.get("type") for a in assertions if isinstance(a, dict)}
    missing_required = _REQUIRED_ARRIVAL_TYPES - seen_types
    if missing_required:
        plan_errors.append({
            "rule": "R6_ARRIVAL_ASSERTIONS_INCOMPLETE",
            "missing_required_types": sorted(missing_required),
            "error": (
                "arrival_assertions must include at least: "
                + ", ".join(sorted(_REQUIRED_ARRIVAL_TYPES))
            ),
        })

    # ── R7: data_bindings resolution ──────────────────────────────────────
    data_bindings_resolved, unresolved_bindings = _collect_data_bindings(
        steps, available_data,
    )
    for missing in unresolved_bindings:
        plan_errors.append({
            "rule": "R7_DATA_BINDING_MISSING",
            "step_index": missing["step_index"],
            "field": missing["field"],
            "data_key": missing["data_key"],
            "error": (
                f"step_index={missing['step_index']} field={missing['field']!r} "
                f"references available_data[{missing['data_key']!r}] which is not provided"
            ),
        })

    # ── R8: goto_direct against direct_entry_allowed: false ───────────────
    contracts = _resolve_contracts(contracts, contracts_path)
    for step in steps:
        if step.get("method") == "goto_direct":
            target_url = step.get("target_url") or ""
            screen = _target_url_to_screen(target_url)
            if screen and _screen_forbids_direct_entry(screen, contracts):
                plan_errors.append({
                    "rule": "R8_DIRECT_GOTO_FORBIDDEN",
                    "step_index": step.get("step_index"),
                    "target_url": target_url,
                    "screen": screen,
                    "error": (
                        f"step_index={step.get('step_index')} method=goto_direct "
                        f"target screen {screen!r} has direct_entry_allowed: false"
                    ),
                })

    # ── Emit blocking result, or success ──────────────────────────────────
    if plan_errors:
        first = plan_errors[0]
        return _blocked(
            navigation_plan,
            reason="INVALID_NAV_PLAN",
            failed_validation=_pick_failed_validation_label(first),
            plan_errors=plan_errors,
            human_action_required=_human_action_for(first, navigation_plan),
        )

    return {
        "ok": True,
        "plan_id": _plan_id(navigation_plan),
        "validation_version": _TOOL_VERSION,
        "steps_validated": len(steps),
        "data_bindings_resolved": data_bindings_resolved,
        "assertions_declared": len(assertions),
        "warnings": warnings,
    }


def validate_file(
    plan_path: Path,
    data_path: Optional[Path] = None,
    contracts_path: Optional[Path] = None,
    schema_path: Optional[Path] = None,
) -> dict:
    """File-based wrapper for CLI use."""
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    data = {}
    if data_path and data_path.is_file():
        data = json.loads(data_path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "values" in data and isinstance(data["values"], dict):
            data = data["values"]
    return validate(
        navigation_plan=plan,
        available_data=data,
        contracts_path=contracts_path,
        schema_path=schema_path,
    )


# ── Internals ────────────────────────────────────────────────────────────────

def _check_step_rules(step: dict, plan_errors: list[dict]) -> None:
    """Apply rules R2..R5 to a single step. Mutates plan_errors in-place."""
    if not isinstance(step, dict):
        plan_errors.append({
            "rule": "R2_STEP_NOT_OBJECT",
            "error": f"step is not an object: {type(step).__name__}",
        })
        return

    idx = step.get("step_index")
    method = step.get("method")

    # R2: method enum
    if method not in _VALID_METHODS:
        plan_errors.append({
            "rule": "R2_INVALID_METHOD",
            "step_index": idx,
            "method": method,
            "error": (
                f"step_index={idx} method={method!r} not in NavigationPlan/1.0 enum "
                f"(allowed: {sorted(_VALID_METHODS)})"
            ),
        })
        return  # downstream rules need a valid method to be meaningful

    # R3: fill requires selector + data_bindings
    if method == "fill":
        if not (step.get("selector") or "").strip():
            plan_errors.append({
                "rule": "R3_FILL_MISSING_SELECTOR",
                "step_index": idx,
                "field": "selector",
                "error": f"step_index={idx} method=fill requires non-empty selector",
            })
        bindings = step.get("data_bindings")
        if not isinstance(bindings, dict) or not bindings:
            plan_errors.append({
                "rule": "R3_FILL_MISSING_DATA_BINDINGS",
                "step_index": idx,
                "field": "data_bindings",
                "error": f"step_index={idx} method=fill requires non-empty data_bindings",
            })

    # R4: form_submit requires eventtarget + wait_url_contains
    if method == "form_submit":
        if not (step.get("eventtarget") or "").strip():
            plan_errors.append({
                "rule": "R4_FORM_SUBMIT_MISSING_EVENTTARGET",
                "step_index": idx,
                "field": "eventtarget",
                "error": f"step_index={idx} method=form_submit requires eventtarget",
            })
        if not (step.get("wait_url_contains") or "").strip():
            plan_errors.append({
                "rule": "R4_FORM_SUBMIT_MISSING_WAIT_URL",
                "step_index": idx,
                "field": "wait_url_contains",
                "error": f"step_index={idx} method=form_submit requires wait_url_contains",
            })

    # R5: goto_* requires target_url
    if method in ("goto_direct", "goto_deeplink"):
        if not (step.get("target_url") or "").strip():
            plan_errors.append({
                "rule": "R5_GOTO_MISSING_TARGET_URL",
                "step_index": idx,
                "field": "target_url",
                "error": f"step_index={idx} method={method} requires target_url",
            })


def _collect_data_bindings(
    steps: list,
    available_data: dict,
) -> tuple[dict, list[dict]]:
    """Resolve every data_binding value against available_data.

    Returns (resolved_map, unresolved_list). The resolved_map flattens all
    distinct data keys actually referenced by any step that the validator
    was able to satisfy from available_data.
    """
    resolved: dict[str, Any] = {}
    unresolved: list[dict] = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        bindings = step.get("data_bindings") or {}
        if not isinstance(bindings, dict):
            continue
        idx = step.get("step_index")
        for field, data_key in bindings.items():
            # data_bindings values point at available_data keys; the value
            # itself may also be a literal string. We treat any key that
            # exists in available_data as resolved; otherwise we still try
            # the literal value as a fallback.
            if data_key in available_data:
                resolved[data_key] = available_data[data_key]
            elif isinstance(data_key, str) and data_key.startswith("$"):
                unresolved.append({
                    "step_index": idx,
                    "field": field,
                    "data_key": data_key,
                })
            elif data_key not in available_data and field.lower() == "value":
                # The most common shape: data_bindings={"value": "CLCOD"}.
                # If the literal key is absent from available_data we mark
                # it unresolved — the spec needs a real value at runtime.
                unresolved.append({
                    "step_index": idx,
                    "field": field,
                    "data_key": data_key,
                })
            # else: arbitrary literal binding (e.g. "value": "static-text").
    return resolved, unresolved


def _resolve_contracts(
    contracts: Optional[dict],
    contracts_path: Optional[Path],
) -> dict:
    """Return the contracts dict, loading from disk if needed."""
    if contracts is not None:
        return contracts
    path = contracts_path or _DEFAULT_CONTRACTS_PATH
    if not path.is_file():
        return {}
    try:
        import yaml  # type: ignore
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except ImportError:
        logger.warning(
            "PyYAML missing — R8 (goto_direct vs direct_entry_allowed) cannot be enforced."
        )
        return {}
    except Exception as exc:
        logger.warning("Could not load contracts at %s: %s", path, exc)
        return {}


def _target_url_to_screen(target_url: str) -> Optional[str]:
    """Extract the screen filename from a target_url ('Foo.aspx?x=1' → 'Foo.aspx')."""
    if not isinstance(target_url, str) or not target_url:
        return None
    head = target_url.split("?", 1)[0].split("#", 1)[0]
    head = head.rstrip("/")
    if "/" in head:
        head = head.rsplit("/", 1)[-1]
    return head or None


def _screen_forbids_direct_entry(screen: str, contracts: dict) -> bool:
    if not contracts or not screen:
        return False
    contract = contracts.get(screen)
    if not isinstance(contract, dict):
        return False
    return contract.get("direct_entry_allowed") is False


def _plan_id(plan: dict) -> str:
    ticket = plan.get("ticket_id", "?")
    scenario = plan.get("scenario_id", "?")
    return f"{ticket}_{scenario}"


def _pick_failed_validation_label(err: dict) -> str:
    rule = err.get("rule", "UNKNOWN_RULE")
    idx = err.get("step_index")
    if idx is not None:
        return f"step_index_{idx}_{rule.lower()}"
    return rule.lower()


def _human_action_for(err: dict, plan: dict) -> str:
    rule = err.get("rule", "")
    plan_id = _plan_id(plan)
    base = f"NavigationPlan {plan_id} fallo de validación ({rule})."
    if rule == "R3_FILL_MISSING_SELECTOR":
        return base + " Completar el selector del paso en navigation_contracts.yml o en el playbook."
    if rule == "R3_FILL_MISSING_DATA_BINDINGS":
        return base + " Declarar data_bindings para el paso fill."
    if rule == "R4_FORM_SUBMIT_MISSING_EVENTTARGET":
        return base + " Definir eventtarget para el step form_submit."
    if rule == "R4_FORM_SUBMIT_MISSING_WAIT_URL":
        return base + " Definir wait_url_contains para el step form_submit."
    if rule == "R5_GOTO_MISSING_TARGET_URL":
        return base + " Definir target_url para el step goto_direct/goto_deeplink."
    if rule == "R6_ARRIVAL_ASSERTIONS_INCOMPLETE":
        return base + " Agregar al menos no_aspnet_error y url_contains en arrival_assertions."
    if rule == "R7_DATA_BINDING_MISSING":
        return base + (
            f" Proveer {err.get('data_key')!r} en available_data antes de regenerar."
        )
    if rule == "R8_DIRECT_GOTO_FORBIDDEN":
        return base + (
            f" La pantalla {err.get('screen')!r} declara direct_entry_allowed: false; "
            "usar human_path o deeplink en lugar de goto_direct."
        )
    if rule == "R2_INVALID_METHOD":
        return base + " Reemplazar el method por uno del enum NavigationPlan/1.0."
    if rule == "R1_AT_LEAST_ONE_STEP":
        return base + " El plan debe tener al menos un paso."
    return base + " Revisar plan_errors para detalle."


def _blocked(
    plan: dict,
    reason: str,
    failed_validation: str,
    plan_errors: list[dict],
    human_action_required: str,
) -> dict:
    return {
        "ok": False,
        "verdict": "BLOCKED",
        "category": "PIP",
        "reason": reason,
        "failed_validation": failed_validation,
        "human_action_required": human_action_required,
        "plan_id": _plan_id(plan),
        "validation_version": _TOOL_VERSION,
        "plan_errors": plan_errors,
    }


# ── Schema validation ────────────────────────────────────────────────────────

def _validate_against_schema(
    plan: dict,
    schema_path: Optional[Path],
) -> list[dict]:
    """Return a list of jsonschema errors (empty when valid).

    Falls back to a minimal manual check when the jsonschema lib is missing —
    enough to keep R1..R8 meaningful even in stripped-down environments.
    """
    path = schema_path or _DEFAULT_SCHEMA_PATH
    try:
        from jsonschema import Draft202012Validator  # type: ignore
    except ImportError:
        return _validate_against_schema_fallback(plan)
    if not path.is_file():
        return _validate_against_schema_fallback(plan)
    try:
        schema = json.loads(path.read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema)
    except Exception as exc:
        logger.warning("Could not load schema %s: %s", path, exc)
        return _validate_against_schema_fallback(plan)
    errors: list[dict] = []
    for err in sorted(validator.iter_errors(plan), key=lambda e: list(e.path)):
        errors.append({
            "rule": "SCHEMA_VIOLATION",
            "path": "/".join(str(p) for p in err.path) or "<root>",
            "error": err.message,
        })
    return errors


def _validate_against_schema_fallback(plan: dict) -> list[dict]:
    """Minimal structural validation used when jsonschema is unavailable."""
    errors: list[dict] = []
    if not isinstance(plan, dict):
        return [{"rule": "SCHEMA_VIOLATION", "path": "<root>", "error": "plan is not an object"}]
    required = [
        "plan_version", "ticket_id", "scenario_id", "target_screen",
        "lane", "strategy", "steps", "arrival_assertions",
    ]
    for field in required:
        if field not in plan:
            errors.append({
                "rule": "SCHEMA_VIOLATION",
                "path": field,
                "error": f"required field {field!r} is missing",
            })
    if plan.get("plan_version") and plan["plan_version"] != "1.0":
        errors.append({
            "rule": "SCHEMA_VIOLATION",
            "path": "plan_version",
            "error": f"plan_version must be '1.0' (got {plan.get('plan_version')!r})",
        })
    if "strategy" in plan and plan["strategy"] not in (
        "direct_entry", "deeplink", "human_path", "playbook",
    ):
        errors.append({
            "rule": "SCHEMA_VIOLATION",
            "path": "strategy",
            "error": f"invalid strategy {plan.get('strategy')!r}",
        })
    return errors


# ── Evidence writer ──────────────────────────────────────────────────────────

def write_navigation_plan_validation_event(
    exec_logger,
    validation_result: dict,
) -> None:
    """Emit ``navigation_plan_validation`` to execution.jsonl (roadmap §5.2.4)."""
    if exec_logger is None:
        return
    try:
        exec_logger.event("navigation_plan_validation", {
            "ok": validation_result.get("ok"),
            "plan_id": validation_result.get("plan_id"),
            "steps_validated": validation_result.get("steps_validated"),
            "assertions_declared": validation_result.get("assertions_declared"),
            "warnings": validation_result.get("warnings", []),
            "category": validation_result.get("category"),
            "reason": validation_result.get("reason"),
            "failed_validation": validation_result.get("failed_validation"),
        })
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to emit navigation_plan_validation event: %s", exc)


# ── CLI ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Validate a NavigationPlan.")
    parser.add_argument("--plan", required=True, help="Path to NavigationPlan JSON")
    parser.add_argument("--data", help="Path to available_data JSON (optional)")
    parser.add_argument("--contracts", help="Path to navigation_contracts.yml")
    parser.add_argument("--schema", help="Path to NavigationPlan.schema.json")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        stream=sys.stderr,
    )
    result = validate_file(
        plan_path=Path(args.plan),
        data_path=Path(args.data) if args.data else None,
        contracts_path=Path(args.contracts) if args.contracts else None,
        schema_path=Path(args.schema) if args.schema else None,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result.get("ok") else 1)


if __name__ == "__main__":
    main()
