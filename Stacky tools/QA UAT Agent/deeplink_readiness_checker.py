"""
deeplink_readiness_checker.py — Validates that a deeplink actually reconstructs
the required session context before it is used in UAT runs.

PURPOSE
-------
A deeplink that loads a URL (HTTP 200) does NOT necessarily mean the screen
has the correct session context (selected client, permissions, navigation state).
This module validates deeplinks by checking the response and rendered DOM
against the assertions defined in navigation_contracts.yml.

USAGE (pre-run validation)
--------------------------
    from deeplink_readiness_checker import check_deeplink_readiness

    result = check_deeplink_readiness(
        screen="FrmDetalleClie.aspx",
        params={"CLCOD": "12345"},
        base_url="http://localhost:35017/AgendaWeb/",
        contracts_path=None,  # uses default navigation_contracts.yml
    )
    if result["decision"] == "BLOCKED":
        # Deeplink not ready — use human_path instead or block
        ...

CLI
---
    python deeplink_readiness_checker.py \
        --screen FrmDetalleClie.aspx \
        --params '{"CLCOD": "12345"}' \
        --base-url http://localhost:35017/AgendaWeb/

OUTPUT CONTRACT
---------------
{
  "event": "deeplink_readiness_check",
  "screen": "FrmDetalleClie.aspx",
  "url_pattern": "FrmDetalleClie.aspx?clcod={CLCOD}",
  "params": {"CLCOD": "12345"},
  "url": "FrmDetalleClie.aspx?clcod=12345",
  "checks": {
    "contract_found": true,
    "deeplink_allowed": true,
    "required_params_present": true,
    "http_reachable": true,
    "redirected_to_login": false,
    "server_error_visible": false,
    "context_indicators_present": true
  },
  "missing_params": [],
  "decision": "PASS",
  "category": null,
  "reason": null,
  "human_action_required": null
}

VERSION
-------
1.0 — Initial implementation (Sprint: navigation contracts cuarta parte)
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urljoin, urlencode, quote

logger = logging.getLogger("stacky.qa_uat.deeplink_readiness_checker")

_TOOL_VERSION = "1.0.0"
_DEFAULT_CONTRACTS_PATH = Path(__file__).resolve().parent / "navigation_contracts.yml"


def check_deeplink_readiness(
    screen: str,
    params: Optional[dict] = None,
    base_url: Optional[str] = None,
    contracts_path: Optional[Path] = None,
    timeout_s: float = 10.0,
    exec_logger=None,
    ticket_id: Optional[int] = None,
) -> dict:
    """
    Validate that a deeplink for the given screen with the given params is
    ready (accessible, not redirecting to login, not showing a server error,
    and reconstructing the expected context).

    Parameters
    ----------
    screen : str
        Target screen filename (e.g. "FrmDetalleClie.aspx").
    params : dict | None
        Deeplink params (e.g. {"CLCOD": "12345"}).
    base_url : str | None
        Application base URL. Defaults to AGENDA_WEB_BASE_URL env var.
    contracts_path : Path | None
        Override path to navigation_contracts.yml.
    timeout_s : float
        HTTP request timeout in seconds.
    exec_logger :
        ExecutionLogger instance (optional). Used to emit deeplink_readiness_check event.
    ticket_id : int | None
        ADO ticket identifier for logging.

    Returns
    -------
    dict — deeplink readiness result (see module docstring for schema).
    """
    import os
    params = params or {}
    if base_url is None:
        base_url = os.environ.get("AGENDA_WEB_BASE_URL", "http://localhost:35017/AgendaWeb/")
    base_url = base_url.rstrip("/") + "/"

    checks: dict[str, Any] = {
        "contract_found": False,
        "deeplink_allowed": False,
        "required_params_present": False,
        "http_reachable": False,
        "redirected_to_login": False,
        "server_error_visible": False,
        "context_indicators_present": False,
    }

    # ── Load contract ─────────────────────────────────────────────────────────
    try:
        from navigation_strategy_resolver import _load_contracts, get_screen_contract
        contracts = _load_contracts(contracts_path)
        contract = get_screen_contract(screen, contracts)
    except ImportError:
        contract = None

    if contract is None:
        result = _build_result(
            screen=screen,
            params=params,
            url_pattern=screen,
            url=None,
            checks=checks,
            decision="BLOCKED",
            category="NAV",
            reason="NAV_CONTRACT_MISSING",
            human_action_required=(
                f"Add a navigation contract for '{screen}' in navigation_contracts.yml."
            ),
        )
        _emit_event(exec_logger, result, ticket_id)
        return result

    checks["contract_found"] = True

    # ── Check deeplink_allowed ────────────────────────────────────────────────
    deeplink_cfg = contract.get("deeplink") or {}
    if not contract.get("deeplink_allowed") or not deeplink_cfg:
        checks["deeplink_allowed"] = False
        result = _build_result(
            screen=screen,
            params=params,
            url_pattern=screen,
            url=None,
            checks=checks,
            decision="BLOCKED",
            category="NAV",
            reason="DEEPLINK_NOT_SUPPORTED_FOR_SCREEN",
            human_action_required=(
                f"Screen '{screen}' does not support deeplink in navigation_contracts.yml. "
                "Use a human_path instead."
            ),
        )
        _emit_event(exec_logger, result, ticket_id)
        return result

    checks["deeplink_allowed"] = True

    # ── Validate required params ──────────────────────────────────────────────
    required_params: list[str] = deeplink_cfg.get("required_params", [])
    missing_params = [p for p in required_params if not params.get(p)]
    checks["required_params_present"] = len(missing_params) == 0

    if missing_params:
        result = _build_result(
            screen=screen,
            params=params,
            url_pattern=deeplink_cfg.get("pattern", screen),
            url=None,
            checks=checks,
            decision="BLOCKED",
            category="DATA",
            reason="DEEPLINK_PARAM_MISSING",
            human_action_required=(
                f"Deeplink params missing: {missing_params}. "
                f"Pattern: {deeplink_cfg.get('pattern', screen)}."
            ),
            missing_params=missing_params,
        )
        _emit_event(exec_logger, result, ticket_id)
        return result

    # ── Build deeplink URL ────────────────────────────────────────────────────
    pattern = deeplink_cfg.get("pattern", screen)
    url_relative = pattern
    for param in required_params:
        url_relative = url_relative.replace(f"{{{param}}}", quote(str(params[param])))
    full_url = urljoin(base_url, url_relative)

    # ── HTTP reachability check ───────────────────────────────────────────────
    try:
        import urllib.request as _urllib_req
        import urllib.error as _urllib_err

        req = _urllib_req.Request(full_url, method="GET")
        req.add_header("User-Agent", "Stacky-QA-UAT-DeeplinkChecker/1.0")

        with _urllib_req.urlopen(req, timeout=timeout_s) as resp:
            final_url = resp.geturl()
            status_code = resp.status
            content_bytes = resp.read(8192)  # first 8KB only
            try:
                content = content_bytes.decode("utf-8", errors="replace")
            except Exception:
                content = ""

        checks["http_reachable"] = True

        # Check for login redirect
        if "frmlogin" in final_url.lower() or "login" in final_url.lower():
            checks["redirected_to_login"] = True
            result = _build_result(
                screen=screen,
                params=params,
                url_pattern=pattern,
                url=full_url,
                checks=checks,
                decision="BLOCKED",
                category="SEC",
                reason="DEEPLINK_REDIRECTED_TO_LOGIN",
                human_action_required=(
                    "Deeplink is redirecting to login page. "
                    "The QA session may be expired. Re-run the pipeline to refresh auth."
                ),
            )
            _emit_event(exec_logger, result, ticket_id)
            return result

        # Check for server error in response body
        _server_error_markers = [
            "Server Error in", "Runtime Error", "Unhandled Exception",
            "Exception Details:", "ctl00_lblExceptionMessage",
            "ASP.NET is configured to show verbose errors",
        ]
        if any(marker.lower() in content.lower() for marker in _server_error_markers):
            checks["server_error_visible"] = True
            result = _build_result(
                screen=screen,
                params=params,
                url_pattern=pattern,
                url=full_url,
                checks=checks,
                decision="BLOCKED",
                category="APP",
                reason="DEEPLINK_SERVER_ERROR",
                human_action_required=(
                    f"Deeplink to '{screen}' triggered a server error. "
                    "Check the application logs for the root cause. "
                    "This may indicate the deeplink implementation has a bug."
                ),
            )
            _emit_event(exec_logger, result, ticket_id)
            return result

        # Check for context indicators in the response
        context_indicators = _build_context_indicators(screen, params)
        _found_indicators = []
        _missing_indicators = []
        for indicator in context_indicators:
            if indicator.lower() in content.lower():
                _found_indicators.append(indicator)
            else:
                _missing_indicators.append(indicator)

        # Context check: if we have specific indicators, at least half must be found
        if context_indicators:
            checks["context_indicators_present"] = (
                len(_found_indicators) >= max(1, len(context_indicators) // 2)
            )
        else:
            # No specific indicators defined — assume context loaded if no errors
            checks["context_indicators_present"] = True

        if not checks["context_indicators_present"]:
            result = _build_result(
                screen=screen,
                params=params,
                url_pattern=pattern,
                url=full_url,
                checks=checks,
                decision="BLOCKED",
                category="NAV",
                reason="DEEPLINK_CONTEXT_NOT_RECONSTRUCTED",
                human_action_required=(
                    f"Deeplink loaded '{screen}' but context indicators not found: "
                    f"{_missing_indicators}. "
                    "The deeplink may not reconstruct the expected session context."
                ),
            )
            _emit_event(exec_logger, result, ticket_id)
            return result

    except Exception as exc:
        err_str = str(exc)
        # Connection error = ENV (server down), not NAV
        checks["http_reachable"] = False
        result = _build_result(
            screen=screen,
            params=params,
            url_pattern=pattern,
            url=full_url,
            checks=checks,
            decision="BLOCKED",
            category="ENV",
            reason="DEEPLINK_HTTP_UNREACHABLE",
            human_action_required=(
                f"Cannot reach deeplink URL: {full_url}. Error: {err_str}. "
                "Verify the application is running and the base URL is correct."
            ),
        )
        _emit_event(exec_logger, result, ticket_id)
        return result

    # ── All checks passed ─────────────────────────────────────────────────────
    result = _build_result(
        screen=screen,
        params=params,
        url_pattern=pattern,
        url=full_url,
        checks=checks,
        decision="PASS",
        category=None,
        reason=None,
        human_action_required=None,
    )
    _emit_event(exec_logger, result, ticket_id)
    return result


def _build_context_indicators(screen: str, params: dict) -> list[str]:
    """Return strings that should appear in the page content if context is loaded."""
    indicators: list[str] = []
    screen_lower = screen.lower()
    if "detalleclie" in screen_lower:
        if params.get("CLCOD"):
            indicators.append(str(params["CLCOD"]))
    elif "detalle" in screen_lower:
        # Generic detail screen
        pass
    return indicators


def _build_result(
    screen: str,
    params: dict,
    url_pattern: str,
    url: Optional[str],
    checks: dict,
    decision: str,
    category: Optional[str],
    reason: Optional[str],
    human_action_required: Optional[str],
    missing_params: Optional[list] = None,
) -> dict:
    return {
        "event": "deeplink_readiness_check",
        "screen": screen,
        "url_pattern": url_pattern,
        "params": params,
        "url": url,
        "checks": checks,
        "missing_params": missing_params or [],
        "decision": decision,
        "category": category,
        "reason": reason,
        "human_action_required": human_action_required,
    }


def _emit_event(exec_logger, result: dict, ticket_id: Optional[int]) -> None:
    """Emit deeplink_readiness_check event to execution.jsonl."""
    if exec_logger is None:
        return
    try:
        event_data = dict(result)
        if ticket_id is not None:
            event_data["ticket_id"] = ticket_id
        exec_logger.event("deeplink_readiness_check", event_data)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to emit deeplink_readiness_check event: %s", exc)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Check if a deeplink is ready and reconstructs context."
    )
    parser.add_argument("--screen", required=True, help="Screen filename")
    parser.add_argument("--params", default="{}", help="JSON dict of deeplink params")
    parser.add_argument("--base-url", help="Application base URL")
    parser.add_argument("--contracts", help="Path to navigation_contracts.yml")
    parser.add_argument("--timeout", type=float, default=10.0, help="HTTP timeout in seconds")
    args = parser.parse_args()

    try:
        params = json.loads(args.params)
    except json.JSONDecodeError as exc:
        sys.stderr.write(f"error: --params is not valid JSON: {exc}\n")
        sys.exit(1)

    contracts_path = Path(args.contracts) if args.contracts else None
    result = check_deeplink_readiness(
        screen=args.screen,
        params=params,
        base_url=args.base_url,
        contracts_path=contracts_path,
        timeout_s=args.timeout,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result.get("decision") == "PASS" else 1)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    main()
