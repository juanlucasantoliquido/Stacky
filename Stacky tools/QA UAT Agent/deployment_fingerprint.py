"""
deployment_fingerprint.py — Detect the build/version of the running AgendaWeb instance.

PURPOSE
-------
Before running QA UAT tests, it's important to know WHICH build of AgendaWeb is
being tested.  If the expected build differs from what's deployed, test failures
are not meaningful (they may test the wrong code).

This module probes the running AgendaWeb for version metadata and compares it
against an optional expected value set via the QA_EXPECTED_BUILD_ID env var.

PROBE STRATEGY (in order, first success wins)
----------------------------------------------
1. Health endpoint   → GET /AgendaWeb/health.json or /AgendaWeb/health
2. HTML meta tag     → GET /AgendaWeb/FrmLogin.aspx, parse <meta name="x-build-id">
3. File manifest     → Read _BUILD_ID_FILE if it exists locally (set by deploy script)
4. manual            → QA_EXPECTED_BUILD_ID is set but no probing succeeded → "unknown"

RESULT
------
DeploymentFingerprint dataclass — attached to the session_start event so every
execution.jsonl has an immutable record of what was deployed when the test ran.

INTEGRATION
-----------
Called from environment_preflight.py as an optional step AFTER the base URL
check succeeds.  Failure never blocks the pipeline (fingerprint ok=False just
means we can't verify the build).  A mismatch produces a warning in the result
that the pipeline can surface.

USAGE
-----
    from deployment_fingerprint import check_deployment

    fp = check_deployment()
    if not fp.matched and fp.mismatch_reason:
        logger.warning("Deployment mismatch: %s", fp.mismatch_reason)
    # Always continue — fingerprint is advisory, not blocking.
    session_start_data["deployment"] = fp.to_dict()
"""
from __future__ import annotations

import html.parser
import json
import logging
import os
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.qa_uat.deployment_fingerprint")

# ── Constants ─────────────────────────────────────────────────────────────────

_TOOL_ROOT = Path(__file__).parent
# Optional file written by deploy scripts to record the active build id.
_BUILD_ID_FILE = _TOOL_ROOT / "data" / ".active_build_id"

_HTTP_TIMEOUT_S: float = 5.0

# Known health endpoint candidates (tried in order).
_HEALTH_PATHS = [
    "health.json",
    "health",
    "_health",
]

# Meta tag name used by AgendaWeb to expose build info.
_META_BUILD_ID   = "x-build-id"
_META_BUILD_HASH = "x-build-commit"


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class DeploymentFingerprint:
    ok: bool
    source: str                    # "health_endpoint" | "html_meta" | "file_manifest" | "manual" | "unavailable"
    active_build_id: Optional[str] # build tag / version string from the running app
    active_commit: Optional[str]   # git commit sha, if available
    expected_build_id: Optional[str]  # from QA_EXPECTED_BUILD_ID env var
    matched: bool                  # True when expected == active OR no expected set
    mismatch_reason: Optional[str]
    elapsed_ms: int

    def to_dict(self) -> dict:
        return asdict(self)


# ── Public API ────────────────────────────────────────────────────────────────

def check_deployment(
    base_url: Optional[str] = None,
    expected_build_id: Optional[str] = None,
) -> DeploymentFingerprint:
    """Probe the running AgendaWeb and return a DeploymentFingerprint.

    Parameters
    ----------
    base_url : str, optional
        AgendaWeb base URL.  Defaults to AGENDA_WEB_BASE_URL env var or
        http://localhost:35017/AgendaWeb/.
    expected_build_id : str, optional
        Expected build id.  Defaults to QA_EXPECTED_BUILD_ID env var.
        When None/empty, matched=True always (no check performed).

    Returns
    -------
    DeploymentFingerprint
        Always returns a result — never raises.  ok=False means we could not
        determine the build id.  matched reflects the id comparison.
    """
    started = time.time()

    base_url = _normalize_base_url(
        base_url or os.environ.get("AGENDA_WEB_BASE_URL", "http://localhost:35017/AgendaWeb/")
    )
    expected = expected_build_id or os.environ.get("QA_EXPECTED_BUILD_ID", "").strip() or None

    # Probe in priority order
    active_build_id: Optional[str] = None
    active_commit: Optional[str] = None
    source = "unavailable"

    # Strategy 1: Health endpoint
    for path in _HEALTH_PATHS:
        health_url = base_url + path
        data = _try_health_endpoint(health_url)
        if data is not None:
            active_build_id = data.get("build_id") or data.get("version") or data.get("build")
            active_commit   = data.get("commit") or data.get("git_sha") or data.get("sha")
            source = "health_endpoint"
            logger.debug("DeploymentFingerprint: build_id=%r from %s", active_build_id, health_url)
            break

    # Strategy 2: HTML meta tag on FrmLogin.aspx
    if active_build_id is None:
        login_url = base_url + "FrmLogin.aspx"
        meta = _try_html_meta(login_url)
        if meta:
            active_build_id = meta.get(_META_BUILD_ID)
            active_commit   = meta.get(_META_BUILD_HASH)
            source = "html_meta"
            logger.debug("DeploymentFingerprint: build_id=%r from HTML meta", active_build_id)

    # Strategy 3: Local file manifest
    if active_build_id is None and _BUILD_ID_FILE.is_file():
        try:
            raw = _BUILD_ID_FILE.read_text(encoding="utf-8").strip()
            if raw:
                active_build_id = raw
                source = "file_manifest"
                logger.debug("DeploymentFingerprint: build_id=%r from file", active_build_id)
        except OSError as exc:
            logger.debug("DeploymentFingerprint: cannot read build id file: %s", exc)

    # Strategy 4: Manual — expected is set but we couldn't probe
    if active_build_id is None and expected:
        source = "manual"

    ok = active_build_id is not None
    elapsed = int((time.time() - started) * 1000)

    # Matching
    if expected is None:
        matched = True
        mismatch_reason = None
    elif active_build_id is None:
        matched = False
        mismatch_reason = (
            f"No se pudo determinar el build activo. "
            f"Expected={expected!r}. "
            "Verificá que AgendaWeb exponga /health.json o <meta name='x-build-id'>."
        )
    elif active_build_id.strip() != expected.strip():
        matched = False
        mismatch_reason = (
            f"Build activo ({active_build_id!r}) difiere del esperado ({expected!r}). "
            "Los tests pueden estar evaluando código incorrecto."
        )
    else:
        matched = True
        mismatch_reason = None

    return DeploymentFingerprint(
        ok=ok,
        source=source,
        active_build_id=active_build_id,
        active_commit=active_commit,
        expected_build_id=expected,
        matched=matched,
        mismatch_reason=mismatch_reason,
        elapsed_ms=elapsed,
    )


# ── Internal helpers ──────────────────────────────────────────────────────────

def _normalize_base_url(url: str) -> str:
    return url.rstrip("/") + "/"


def _try_health_endpoint(url: str) -> Optional[dict]:
    """GET url, return parsed JSON if the response is a dict, else None."""
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT_S) as resp:
            content_type = (resp.headers.get("Content-Type") or "").lower()
            body = resp.read(64 * 1024).decode("utf-8", errors="replace")
            if "json" not in content_type and not body.strip().startswith("{"):
                return None
            data = json.loads(body)
            if isinstance(data, dict):
                return data
    except (urllib.error.URLError, OSError, json.JSONDecodeError, ValueError):
        pass
    return None


class _MetaTagParser(html.parser.HTMLParser):
    """Minimal HTML parser that collects <meta name=X content=Y> values."""

    def __init__(self) -> None:
        super().__init__()
        self.metas: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag.lower() != "meta":
            return
        attr_dict = {k.lower(): v for k, v in attrs if v is not None}
        name = attr_dict.get("name", "").lower()
        content = attr_dict.get("content", "")
        if name and content:
            self.metas[name] = content


def _try_html_meta(url: str) -> Optional[dict[str, str]]:
    """GET url and parse <meta> tags from the HTML head.  Returns None on error."""
    try:
        req = urllib.request.Request(url, headers={"Accept": "text/html"})
        with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT_S) as resp:
            # Read only the first 16 KB — enough for the <head> section
            body = resp.read(16 * 1024).decode("utf-8", errors="replace")
        parser = _MetaTagParser()
        parser.feed(body)
        relevant = {
            k: v for k, v in parser.metas.items()
            if k in (_META_BUILD_ID, _META_BUILD_HASH)
        }
        return relevant if relevant else None
    except (urllib.error.URLError, OSError, html.parser.HTMLParseError):
        return None
