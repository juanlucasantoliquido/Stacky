"""Validate navigation_contracts.yml against the Sprint N5-09 v2 contract.

The JSON schema is intentionally permissive for backward compatibility, so this
script adds the operational checks that matter for the navigation pipeline:

* v2 screens must declare arrival_assertions, timeouts, and aspnet_error_markers.
* v2 arrival_assertions must include no_aspnet_error, no_login_redirect, url_contains.
* legacy v1 screens are allowed, but receive warnings because the builder will
  inject default assertions at plan-build time.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REQUIRED_V2_ASSERTION_TYPES = {"no_aspnet_error", "no_login_redirect", "url_contains"}
VALID_ASSERTION_TYPES = {
    "url_contains",
    "url_not_contains",
    "dom_visible",
    "dom_not_visible",
    "dom_text_contains",
    "page_title_contains",
    "page_title_not_contains",
    "no_aspnet_error",
    "no_login_redirect",
    "no_500_response",
}
VALID_CATEGORIES = {"NAV", "ENV", "DATA", "APP"}
VALID_SEVERITIES = {"hard", "soft"}


def validate_contracts(contracts_path: Path, schema_path: Path | None = None) -> dict[str, Any]:
    contracts = _load_yaml(contracts_path)
    screens = {
        key: value for key, value in contracts.items()
        if isinstance(key, str) and key.endswith(".aspx") and isinstance(value, dict)
    }

    errors: list[str] = []
    warnings: list[str] = []
    screens_v2 = 0
    screens_v1 = 0

    meta = contracts.get("_meta") or {}
    if meta.get("schema") != "NavigationContracts/2.0":
        warnings.append("_meta.schema is not NavigationContracts/2.0")
    if schema_path and not schema_path.is_file():
        warnings.append(f"schema file not found: {schema_path}")

    for screen, contract in sorted(screens.items()):
        is_v2 = str(contract.get("schema_version", "")).strip() == "2.0"
        if is_v2:
            screens_v2 += 1
            errors.extend(_validate_v2_screen(screen, contract))
        else:
            screens_v1 += 1
            warnings.append(f"{screen} has no schema_version=2.0; default arrival_assertions will be injected")

    return {
        "ok": not errors,
        "contracts_path": str(contracts_path),
        "schema_path": str(schema_path) if schema_path else None,
        "screens_validated": len(screens),
        "screens_v2": screens_v2,
        "screens_v1_legacy": screens_v1,
        "errors": errors,
        "warnings": warnings,
    }


def _validate_v2_screen(screen: str, contract: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    arrivals = contract.get("arrival_assertions")
    if not isinstance(arrivals, list) or not arrivals:
        errors.append(f"{screen}: v2 screen must declare non-empty arrival_assertions")
    else:
        types = {a.get("type") for a in arrivals if isinstance(a, dict)}
        missing = REQUIRED_V2_ASSERTION_TYPES - types
        if missing:
            errors.append(f"{screen}: arrival_assertions missing required types {sorted(missing)}")
        for idx, assertion in enumerate(arrivals):
            errors.extend(_validate_assertion(screen, idx, assertion))

    timeouts = contract.get("timeouts")
    if not isinstance(timeouts, dict):
        errors.append(f"{screen}: v2 screen must declare timeouts")
    else:
        for key in ("navigation_timeout_ms", "arrival_assertion_timeout_ms"):
            value = timeouts.get(key)
            if not isinstance(value, int) or value <= 0:
                errors.append(f"{screen}: timeouts.{key} must be a positive integer")
        settle = timeouts.get("updatepanel_settle_ms")
        if settle is not None and (not isinstance(settle, int) or settle < 0):
            errors.append(f"{screen}: timeouts.updatepanel_settle_ms must be >= 0")

    markers = contract.get("aspnet_error_markers")
    if not isinstance(markers, dict):
        errors.append(f"{screen}: v2 screen must declare aspnet_error_markers")
    else:
        for key in ("title_contains", "url_contains", "body_contains"):
            values = markers.get(key)
            if not isinstance(values, list) or not all(isinstance(v, str) and v for v in values):
                errors.append(f"{screen}: aspnet_error_markers.{key} must be a non-empty string list")

    if contract.get("direct_entry_allowed") is False and not contract.get("human_paths") and not contract.get("deeplink_allowed"):
        errors.append(f"{screen}: context-dependent screen has no human_paths and no deeplink")

    return errors


def _validate_assertion(screen: str, idx: int, assertion: Any) -> list[str]:
    prefix = f"{screen}: arrival_assertions[{idx}]"
    if not isinstance(assertion, dict):
        return [f"{prefix} must be an object"]
    errors: list[str] = []
    for key in ("assertion_id", "type", "description"):
        if not assertion.get(key):
            errors.append(f"{prefix}.{key} is required")
    typ = assertion.get("type")
    if typ not in VALID_ASSERTION_TYPES:
        errors.append(f"{prefix}.type {typ!r} is not valid")
    if assertion.get("severity", "hard") not in VALID_SEVERITIES:
        errors.append(f"{prefix}.severity is not valid")
    if assertion.get("category_on_fail", "NAV") not in VALID_CATEGORIES:
        errors.append(f"{prefix}.category_on_fail is not valid")
    if typ in {"url_contains", "url_not_contains", "page_title_contains", "page_title_not_contains"}:
        if not assertion.get("expected_value"):
            errors.append(f"{prefix}.expected_value is required for type={typ}")
    if typ in {"dom_visible", "dom_not_visible", "dom_text_contains"}:
        if not assertion.get("selector"):
            errors.append(f"{prefix}.selector is required for type={typ}")
    timeout = assertion.get("timeout_ms")
    if timeout is not None and (not isinstance(timeout, int) or timeout <= 0):
        errors.append(f"{prefix}.timeout_ms must be a positive integer")
    return errors


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"contracts file not found: {path}")
    try:
        import yaml  # type: ignore
    except ImportError as exc:  # pragma: no cover - local env has PyYAML
        raise RuntimeError("PyYAML is required to validate navigation_contracts.yml") from exc
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("contracts file must contain a YAML object")
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate navigation_contracts.yml v2 migration.")
    parser.add_argument("--contracts", required=True, help="Path to navigation_contracts.yml")
    parser.add_argument("--schema", help="Path to NavigationContracts.v2.schema.json")
    args = parser.parse_args()

    try:
        result = validate_contracts(
            contracts_path=Path(args.contracts),
            schema_path=Path(args.schema) if args.schema else None,
        )
    except Exception as exc:  # noqa: BLE001
        result = {"ok": False, "errors": [str(exc)], "warnings": []}

    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result.get("ok") else 1)


if __name__ == "__main__":
    main()
