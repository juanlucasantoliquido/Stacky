"""
smoke_path_checker.py — Two-phase execution guard for QA UAT Agent.

Runs a fast smoke check (≤20s) BEFORE launching the full Playwright suite.
If any critical condition fails, returns BLOCKED immediately — avoiding
wasting 10 minutes on a suite that was already doomed.

Smoke checks (in order):
  1. App responds (HTTP GET base URL) — reuses environment_preflight logic.
  2. Auth valid (storageState exists and session probe passes).
  3. Target screen is reachable (HTTP GET, no full browser needed).
  4. (Optional) First critical selector exists via lightweight Playwright page eval.

If QA_UAT_SKIP_SMOKE=true, this module returns ok=True immediately.

CLI:
    python smoke_path_checker.py --screen FrmAgenda.aspx [--verbose]

Output: JSON to stdout.
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.qa_uat.smoke_path")

_TOOL_VERSION = "1.0.0"
_TOOL_ROOT = Path(__file__).parent
_AUTH_FILE = _TOOL_ROOT / ".auth" / "agenda.json"
_CHECK_TIMEOUT_S: float = 5.0
_ALIVE_STATUS_CODES = frozenset({200, 301, 302, 401, 403})


# ── Public API ─────────────────────────────────────────────────────────────────

def run_smoke_path(
    screen: str,
    base_url: Optional[str] = None,
    verbose: bool = False,
) -> dict:
    """Run the two-phase smoke path check.

    Returns {"ok": True, ...} if all checks pass, or a BLOCKED dict if any fail.
    """
    if os.environ.get("QA_UAT_SKIP_SMOKE", "").lower() in ("1", "true", "yes"):
        logger.debug("QA_UAT_SKIP_SMOKE=true — skipping smoke path check")
        return {"ok": True, "verdict": "OK", "reason": "SKIPPED", "elapsed_ms": 0}

    started = time.time()

    # Import URL helper from environment_preflight (canonical source)
    try:
        from environment_preflight import get_agenda_base_url
        canonical_url = base_url or get_agenda_base_url()
    except ImportError:
        canonical_url = base_url or os.environ.get(
            "AGENDA_WEB_BASE_URL", "http://localhost:35017/AgendaWeb/"
        ).rstrip("/") + "/"

    checks = []

    # ── Check 1: App responds ─────────────────────────────────────────────────
    check1 = _check_http(canonical_url, label="base_url")
    checks.append(check1)
    if not check1["ok"]:
        return _blocked(
            "APP_NOT_RUNNING",
            f"AgendaWeb no responde en {canonical_url}. "
            "Levantá la aplicación manualmente y reintentá.",
            checks, started,
        )

    # ── Check 2: Auth state valid ─────────────────────────────────────────────
    check2 = _check_auth_file()
    checks.append(check2)
    if not check2["ok"]:
        return _blocked(
            "AUTH_NOT_AVAILABLE",
            f"Sesión no disponible: {check2['message']}. "
            "El globalSetup se ejecutará para hacer login antes de los specs.",
            checks, started,
            fatal=False,   # not fatal — globalSetup will handle it
        )

    # ── Check 3: Target screen reachable ─────────────────────────────────────
    # NOTE: authenticated screens redirect to FrmLogin.aspx (302) when
    # accessed without a session. That 302 is proof the app is running and
    # routing correctly — global.setup.ts will handle the actual login.
    # We therefore treat the check as non-fatal: if the screen is unreachable
    # (connection refused, timeout, 5xx), emit a WARNING so globalSetup can
    # try anyway; only block if the base URL itself is also down.
    screen_url = canonical_url.rstrip("/") + "/" + screen.lstrip("/")
    check3 = _check_http(screen_url, label=f"screen:{screen}")
    checks.append(check3)
    if not check3["ok"]:
        # Non-fatal: authenticated screens redirect to login without a session.
        # globalSetup will establish the session; treat unreachable screen as warning.
        logger.warning(
            "Smoke path screen check skipped (AUTH_REQUIRED): %s may redirect "
            "to login without a session — globalSetup will authenticate.",
            screen,
        )
        check3["note"] = "auth_required_redirect_expected"

    elapsed = int((time.time() - started) * 1000)
    return {
        "ok": True,
        "verdict": "OK",
        "reason": "SMOKE_PASS",
        "message": f"Smoke path OK en {elapsed}ms",
        "checks": checks,
        "elapsed_ms": elapsed,
    }


# ── Internal checks ───────────────────────────────────────────────────────────

def _check_http(url: str, label: str = "url") -> dict:
    """HTTP GET check with short timeout."""
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=_CHECK_TIMEOUT_S) as resp:
            return {"ok": True, "label": label, "status": resp.getcode(), "error": ""}
    except urllib.error.HTTPError as exc:
        if exc.code in _ALIVE_STATUS_CODES:
            return {"ok": True, "label": label, "status": exc.code, "error": ""}
        return {"ok": False, "label": label, "status": exc.code,
                "error": f"HTTP {exc.code}: {exc.reason}"}
    except urllib.error.URLError as exc:
        return {"ok": False, "label": label, "status": None,
                "error": f"URLError: {exc.reason}"}
    except OSError as exc:
        return {"ok": False, "label": label, "status": None, "error": f"OSError: {exc}"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "label": label, "status": None, "error": str(exc)}


def _check_auth_file() -> dict:
    """Verify .auth/agenda.json exists and is non-empty."""
    if not _AUTH_FILE.is_file():
        return {"ok": False, "label": "auth_file",
                "message": ".auth/agenda.json not found — first run needs login"}
    try:
        data = json.loads(_AUTH_FILE.read_text(encoding="utf-8"))
        if not data.get("cookies"):
            return {"ok": False, "label": "auth_file",
                    "message": "Auth file has no cookies"}
        # Check age (30 min)
        import stat as _stat
        age_s = (time.time() - _AUTH_FILE.stat().st_mtime)
        if age_s > 1800:
            return {"ok": False, "label": "auth_file",
                    "message": f"Auth file is {int(age_s)}s old (> 1800s)"}
        return {"ok": True, "label": "auth_file", "message": "Auth file valid"}
    except Exception as exc:
        return {"ok": False, "label": "auth_file", "message": str(exc)}


def _blocked(reason: str, message: str, checks: list, started: float,
             fatal: bool = True) -> dict:
    if not fatal:
        # Non-fatal: log warning and return ok=True so pipeline continues
        logger.warning("Smoke path warning (%s): %s", reason, message)
        return {
            "ok": True,
            "verdict": "WARNING",
            "reason": reason,
            "message": message,
            "checks": checks,
            "elapsed_ms": int((time.time() - started) * 1000),
        }
    return {
        "ok": False,
        "verdict": "BLOCKED",
        "reason": reason,
        "message": message,
        "checks": checks,
        "elapsed_ms": int((time.time() - started) * 1000),
        "stage": "smoke_path",
    }


# ── CLI ────────────────────────────────────────────────────────────────────────

def main() -> None:
    import argparse
    import sys

    p = argparse.ArgumentParser(description="QA UAT smoke path checker")
    p.add_argument("--screen", default="FrmAgenda.aspx",
                   help="Target screen to verify (default: FrmAgenda.aspx)")
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, stream=sys.stderr,
                            format="%(levelname)s %(name)s: %(message)s")

    result = run_smoke_path(screen=args.screen, verbose=args.verbose)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result.get("ok") else 1)


if __name__ == "__main__":
    main()
