"""
environment_preflight.py — Pre-flight checks for QA UAT Agent.

Validates the environment BEFORE opening any browser or running any
costly pipeline stage.  Called at the very beginning of qa_uat_pipeline.run().

Checks (in order, fail-fast):
  1. Required credentials are set (AGENDA_WEB_USER, AGENDA_WEB_PASS).
  2. AgendaWeb base URL responds (HTTP GET, timeout=5s).
  3. FrmLogin.aspx responds (HTTP GET, timeout=5s).

Timeouts are intentionally short (≤5s each, ≤15s total) so a failed
preflight returns BLOCKED in well under 60 seconds.

QA UAT Agent NEVER manages the runtime of AgendaWeb.
If the app is not running, the correct action is to return BLOCKED and
ask the operator to start it manually.

Canonical URL helper
--------------------
    from environment_preflight import get_agenda_base_url
    url = get_agenda_base_url()   # always ends with "/"

Usage
-----
    from environment_preflight import run_environment_preflight

    result = run_environment_preflight()
    if not result.ok:
        return result.to_pipeline_dict()
    # ... continue pipeline ...
"""
from __future__ import annotations

import logging
import os
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

# Canonical default — must match docs / .env examples
_DEFAULT_BASE_URL = "http://localhost:35017/AgendaWeb/"
_LOGIN_PATH = "FrmLogin.aspx"

# Per-check HTTP timeout in seconds — short and intentional.
# If the app doesn't respond in 5s it is NOT running (IIS Express responds
# immediately when alive). We do NOT retry — fail fast.
_CHECK_TIMEOUT_S: float = 5.0

# HTTP status codes that prove the server is running even if they indicate
# auth/redirect (e.g., 302→login, 401, 403).  We only care that the process
# is alive and serving HTTP, not that the response is 200.
# 400 is included because IIS/IIS-Express may return it when the HTTP request
# uses 127.0.0.1 as the Host header instead of "localhost" (host-binding
# mismatch), which still proves the server process is running.
_ALIVE_STATUS_CODES = frozenset({200, 301, 302, 400, 401, 403})


# ── URL helper ─────────────────────────────────────────────────────────────────

def get_agenda_base_url() -> str:
    """Return the canonical AgendaWeb base URL, always ending with '/'.

    Reads AGENDA_WEB_BASE_URL from the environment.  Falls back to
    http://localhost:35017/AgendaWeb/ (the canonical development URL).

    ALL modules in QA UAT Agent must obtain the base URL via this function
    instead of hardcoding it — this is the single source of truth.
    """
    raw = os.environ.get("AGENDA_WEB_BASE_URL", _DEFAULT_BASE_URL)
    return raw.rstrip("/") + "/"


# ── Result dataclass ───────────────────────────────────────────────────────────

@dataclass
class EnvironmentPreflightResult:
    ok: bool
    verdict: str       # "OK" | "BLOCKED"
    reason: str        # machine-readable code
    message: str       # human-readable description
    base_url: str
    login_url: str
    elapsed_ms: int
    deployment: Optional[dict] = None  # DeploymentFingerprint.to_dict() — advisory, may be None

    def to_pipeline_dict(self) -> dict:
        """Convert to the standard BLOCKED pipeline response dict.

        The pipeline returns this directly when preflight fails so the
        caller gets a consistent structure.
        """
        d = {
            "ok": False,
            "verdict": self.verdict,
            "reason": self.reason,
            "message": self.message,
            "base_url": self.base_url,
            "login_url": self.login_url,
            "elapsed_ms": self.elapsed_ms,
            "stage": "environment_preflight",
        }
        if self.deployment is not None:
            d["deployment"] = self.deployment
        return d

    def to_dict(self) -> dict:
        return asdict(self)


# ── Main entry point ───────────────────────────────────────────────────────────

def run_environment_preflight(config: Optional[dict] = None) -> EnvironmentPreflightResult:
    """Run all pre-flight checks.

    Parameters
    ----------
    config : dict, optional
        Override keys: ``base_url``, ``user``, ``pass``.
        If omitted, values are read from env vars.

    Returns
    -------
    EnvironmentPreflightResult
        ok=True if all checks pass; ok=False with structured BLOCKED reason
        if any check fails.
    """
    started = time.time()
    config = config or {}

    base_url = (config.get("base_url") or get_agenda_base_url())
    login_url = base_url.rstrip("/") + "/" + _LOGIN_PATH

    # ── Check 1: credentials ─────────────────────────────────────────────────
    user = (config.get("user") or os.environ.get("AGENDA_WEB_USER", "")).strip()
    password = (config.get("pass") or os.environ.get("AGENDA_WEB_PASS", "")).strip()

    if not user or not password:
        missing = []
        if not user:
            missing.append("AGENDA_WEB_USER")
        if not password:
            missing.append("AGENDA_WEB_PASS")
        return EnvironmentPreflightResult(
            ok=False,
            verdict="BLOCKED",
            reason="MISSING_CREDENTIALS",
            message=(
                f"Credenciales faltantes: {', '.join(missing)}. "
                "Configurá las variables de entorno antes de correr QA UAT."
            ),
            base_url=base_url,
            login_url=login_url,
            elapsed_ms=int((time.time() - started) * 1000),
        )

    # ── Check 2: base URL reachable ──────────────────────────────────────────
    base_check = _http_get(base_url, timeout_s=_CHECK_TIMEOUT_S)
    if not base_check["ok"]:
        return EnvironmentPreflightResult(
            ok=False,
            verdict="BLOCKED",
            reason="APP_NOT_RUNNING",
            message=(
                f"AgendaWeb no responde en {base_url}. "
                "Levantá la aplicación manualmente y reintentá. "
                f"Error: {base_check['error']}"
            ),
            base_url=base_url,
            login_url=login_url,
            elapsed_ms=int((time.time() - started) * 1000),
        )

    # ── Check 3: login page reachable ────────────────────────────────────────
    login_check = _http_get(login_url, timeout_s=_CHECK_TIMEOUT_S)
    if not login_check["ok"]:
        return EnvironmentPreflightResult(
            ok=False,
            verdict="BLOCKED",
            reason="LOGIN_PAGE_UNREACHABLE",
            message=(
                f"FrmLogin.aspx no responde en {login_url}. "
                "La aplicación puede estar iniciando o en error. "
                f"Error: {login_check['error']}"
            ),
            base_url=base_url,
            login_url=login_url,
            elapsed_ms=int((time.time() - started) * 1000),
        )

    elapsed = int((time.time() - started) * 1000)

    # ── Check 4 (advisory): deployment fingerprint ───────────────────────────
    # Non-blocking — only warns when QA_EXPECTED_BUILD_ID is set and mismatches.
    fingerprint_dict: Optional[dict] = None
    try:
        from deployment_fingerprint import check_deployment
        fp = check_deployment(base_url=base_url)
        fingerprint_dict = fp.to_dict()
        if not fp.matched and fp.mismatch_reason:
            logger.warning("Deployment mismatch: %s", fp.mismatch_reason)
    except Exception as _fp_exc:  # noqa: BLE001
        logger.debug("DeploymentFingerprint unavailable: %s", _fp_exc)

    return EnvironmentPreflightResult(
        ok=True,
        verdict="OK",
        reason="PREFLIGHT_PASS",
        message=f"AgendaWeb disponible en {base_url} ({elapsed}ms)",
        base_url=base_url,
        login_url=login_url,
        elapsed_ms=elapsed,
        deployment=fingerprint_dict,
    )


# ── Internal HTTP helper ───────────────────────────────────────────────────────

def _http_get(url: str, timeout_s: float = 5.0) -> dict:
    """Minimal HTTP GET with timeout.

    Returns {"ok": bool, "status": int|None, "error": str}.
    Never raises — all exceptions are caught and mapped to ok=False.

    Considers 2xx, 3xx, 400, 401, 403 as "app is running" (ok=True) because
    IIS/IIS Express returns these immediately when alive.  Only network errors
    and 5xx (server crash) are treated as ok=False.

    IPv4 fallback: if ``url`` uses the hostname ``localhost`` and the initial
    request times-out (Python may resolve localhost to ::1 on some systems),
    retries once using 127.0.0.1 to force an IPv4 connection.
    """
    last_error: str = ""

    def _attempt(attempt_url: str, attempt_timeout: float) -> dict:
        try:
            req = urllib.request.Request(attempt_url, method="GET")
            with urllib.request.urlopen(req, timeout=attempt_timeout) as resp:
                return {"ok": True, "status": resp.getcode(), "error": ""}
        except urllib.error.HTTPError as exc:
            if exc.code in _ALIVE_STATUS_CODES:
                return {"ok": True, "status": exc.code, "error": ""}
            return {"ok": False, "status": exc.code,
                    "error": f"HTTP {exc.code}: {exc.reason}"}
        except urllib.error.URLError as exc:
            return {"ok": False, "status": None, "error": f"URLError: {exc.reason}"}
        except OSError as exc:
            return {"ok": False, "status": None, "error": f"OSError: {exc}"}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "status": None, "error": f"Unexpected: {exc}"}

    result = _attempt(url, timeout_s)
    if result["ok"]:
        return result

    # IPv4 fallback: if localhost timed-out, retry with 127.0.0.1.
    # Some Windows configurations resolve localhost to ::1 (IPv6), which may
    # timeout even when the server is listening on 127.0.0.1 (IPv4).
    if "localhost" in url and ("timed out" in result["error"] or "TimeoutError" in result["error"]):
        fallback_url = url.replace("localhost", "127.0.0.1", 1)
        fallback = _attempt(fallback_url, timeout_s)
        if fallback["ok"]:
            return fallback  # Server IS running; original URL fine for Playwright (Chromium handles IPv6)

    return result


# ── CLI (for manual testing) ───────────────────────────────────────────────────

def main() -> None:
    import json
    import sys
    result = run_environment_preflight()
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    sys.exit(0 if result.ok else 1)


if __name__ == "__main__":
    main()
