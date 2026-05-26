"""
deployment_fingerprint.py — Sprint 3: Blocking deployment check before runner.

PURPOSE
-------
Verify that the running build of AgendaWeb matches what the ticket was written
against BEFORE opening any browser.  If the build is wrong, every Playwright
failure is meaningless — they test the wrong code.

DESIGN CHANGE from advisory (pre-Sprint 3) to BLOCKING
-------------------------------------------------------
Pre-Sprint 3: fingerprint was advisory-only and never stopped the pipeline.
Sprint 3: introduces check_deployment_fingerprint() which returns a
DeploymentFingerprintResult with BLOCKED | WARN | ALLOW semantics and a
typed dataclass that the pipeline uses to gate execution.

The original check_deployment() function is preserved for backwards compat
(used by environment_preflight.py's advisory path).

SOURCES (in priority order)
---------------------------
1. health_endpoint  — GET /health/version or /api/version
2. file_manifest    — read build-manifest.json deployed next to the app
3. page_meta        — <meta name="x-build-id"> in FrmLogin.aspx HTML
4. dll_hash         — mtime/hash of DLLs (when filesystem access exists)
5. manual_config    — build id set via QA_UAT_EXPECTED_BUILD_ID env var

DECISION RULES
--------------
| Condition                       | Mode    | Decision |
|---------------------------------|---------|----------|
| fingerprint match               | any     | ALLOW    |
| mismatch                        | any     | BLOCKED  |
| no source available             | publish | BLOCKED  |
| no source available             | dry-run | WARN     |
| error querying source           | publish | BLOCKED  |
| error querying source           | dry-run | WARN     |
| no expected build defined       | any     | WARN (skipped=True) |

ARTIFACT
--------
Writes deployment_fingerprint.json to evidence_dir/<run_id>/ when
evidence_dir is provided.

EVENT
-----
Emits deployment_fingerprint_check to execution.jsonl via exec_logger.

ENV VARS
--------
QA_UAT_FINGERPRINT_SOURCE   override source priority (e.g. "health_endpoint")
QA_UAT_HEALTH_ENDPOINT      health URL path (default: /health/version)
QA_UAT_EXPECTED_BUILD_ID    expected build_id (alias: QA_EXPECTED_BUILD_ID)
QA_UAT_EXPECTED_BRANCH      expected git branch
AGENDA_WEB_BASE_URL         base URL of the app under test

USAGE (Sprint 3)
----------------
    from deployment_fingerprint import check_deployment_fingerprint

    result = check_deployment_fingerprint(
        ticket_id=120,
        expected={"build_id": "Task-120", "branch": "feature/RF-007"},
        base_url="http://localhost:35017/AgendaWeb/",
        sources=["health_endpoint", "file_manifest", "manual_config"],
        mode="publish",
        evidence_dir=Path("evidence/120"),
        run_id="120",
    )
    if result.decision == "BLOCKED":
        # return early from pipeline — do NOT open browser
        ...

BACKWARDS COMPAT (pre-Sprint 3 advisory)
-----------------------------------------
    from deployment_fingerprint import check_deployment

    fp = check_deployment()   # returns DeploymentFingerprint (advisory, never blocks)
"""
from __future__ import annotations

import hashlib
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
# File written by deploy scripts to record the active build id.
_BUILD_ID_FILE = _TOOL_ROOT / "data" / ".active_build_id"
_BUILD_MANIFEST_FILE = _TOOL_ROOT / "data" / "build-manifest.json"

_HTTP_TIMEOUT_S: float = 5.0

# Known health endpoint path candidates (tried in order).
_DEFAULT_HEALTH_PATHS = [
    "health/version",
    "api/version",
    "health.json",
    "health",
    "_health",
]

_META_BUILD_ID   = "x-build-id"
_META_BUILD_HASH = "x-build-commit"
_META_BRANCH     = "x-build-branch"

# Source labels
_SOURCE_HEALTH   = "health_endpoint"
_SOURCE_MANIFEST = "file_manifest"
_SOURCE_META     = "page_meta"
_SOURCE_DLL      = "dll_hash"
_SOURCE_MANUAL   = "manual_config"
_SOURCE_NONE     = "unavailable"

_ALL_SOURCES = [_SOURCE_HEALTH, _SOURCE_MANIFEST, _SOURCE_META, _SOURCE_DLL, _SOURCE_MANUAL]


# ── Sprint 3 blocking dataclass ───────────────────────────────────────────────

@dataclass
class DeploymentFingerprintResult:
    """Result of the blocking Sprint 3 fingerprint check."""
    matched: bool
    source: str                  # which source was used
    expected: dict               # build_id, commit, branch expected
    active: dict                 # build_id, commit, branch detected
    decision: str                # "ALLOW" | "BLOCKED" | "WARN"
    category: Optional[str]      # "ENV" if blocked
    reason: Optional[str]        # "DEPLOYMENT_MISMATCH" | "FINGERPRINT_SOURCE_MISSING" | None
    skipped: bool                # True when no expected build is defined
    elapsed_ms: int
    artifact_path: Optional[str]

    def to_dict(self) -> dict:
        return asdict(self)


# ── Sprint 3 main API ─────────────────────────────────────────────────────────

def check_deployment_fingerprint(
    ticket_id: int,
    expected: Optional[dict],        # build_id, commit, branch expected; None = skip
    base_url: str,
    sources: Optional[list] = None,  # sources to try in order; None = use defaults
    mode: str = "dry-run",           # "dry-run" | "publish"
    policy: Optional[str] = None,    # Sprint 2: "off" | "soft" | "hard" — overrides mode-based logic
    exec_logger=None,
    evidence_dir: Optional[Path] = None,
    run_id: Optional[str] = None,
) -> DeploymentFingerprintResult:
    """Check that the running build matches what the ticket expects.

    Sprint 2 — policy parameter:
    - "off"  : skip gate entirely (always ALLOW, no matter what)
    - "soft" : WARN on mismatch or missing source, never blocks
    - "hard" : BLOCK on mismatch AND on missing source (BUILD_UNVERIFIABLE)
    - None   : use pre-Sprint 2 behavior (bound to mode=dry-run/publish)

    The policy can also be set via QA_UAT_DEPLOYMENT_POLICY env var.
    Explicit `policy` parameter takes precedence over env var.

    Parameters
    ----------
    ticket_id : int
        ADO work item ID (for logging).
    expected : dict | None
        Expected fingerprint keys: build_id, commit, branch.
        None means no expected build is defined — result will be WARN/skipped.
    base_url : str
        AgendaWeb base URL (must end with '/').
    sources : list[str] | None
        Source names to try in order.  Defaults to all sources.
    mode : str
        "dry-run" or "publish".  Used for pre-Sprint 2 behavior when policy=None.
    policy : str | None
        Sprint 2 gate policy. Reads QA_UAT_DEPLOYMENT_POLICY if None.
    exec_logger : ExecutionLogger | None
        If provided, emits deployment_fingerprint_check event.
    evidence_dir : Path | None
        If provided, writes deployment_fingerprint.json artifact.
    run_id : str | None
        Run identifier for artifact path.

    Returns
    -------
    DeploymentFingerprintResult
        decision = "ALLOW" | "BLOCKED" | "WARN"
    """
    started = time.time()
    base_url = _normalize_base_url(base_url)
    sources = sources or _resolve_sources_from_env(_ALL_SOURCES)

    # Sprint 2 — resolve effective policy
    _policy = policy or os.environ.get("QA_UAT_DEPLOYMENT_POLICY", "").strip().lower()
    if _policy not in ("off", "soft", "hard"):
        _policy = None  # fall back to pre-Sprint 2 mode-based logic

    # ── Case: no expected build defined ─────────────────────────────────────
    if not expected:
        elapsed = int((time.time() - started) * 1000)
        # Sprint 2 — policy=off → skip entirely even without expected
        decision = "ALLOW" if _policy == "off" else "WARN"
        result = DeploymentFingerprintResult(
            matched=True,
            source=_SOURCE_NONE,
            expected={},
            active={},
            decision=decision,
            category=None,
            reason="NO_EXPECTED_BUILD_DEFINED",
            skipped=True,
            elapsed_ms=elapsed,
            artifact_path=None,
        )
        _emit_event(exec_logger, ticket_id, result)
        _write_artifact(result, evidence_dir, run_id)
        logger.info(
            "deployment_fingerprint: skipped (no expected build defined) for ticket %s",
            ticket_id,
        )
        return result

    # ── Case: policy=off — skip gate ─────────────────────────────────────────
    if _policy == "off":
        elapsed = int((time.time() - started) * 1000)
        result = DeploymentFingerprintResult(
            matched=True,
            source="policy_off",
            expected=expected or {},
            active={},
            decision="ALLOW",
            category=None,
            reason="POLICY_OFF",
            skipped=True,
            elapsed_ms=elapsed,
            artifact_path=None,
        )
        _emit_event(exec_logger, ticket_id, result)
        _write_artifact(result, evidence_dir, run_id)
        logger.info("deployment_fingerprint: gate disabled by policy=off for ticket %s", ticket_id)
        return result

    # ── Probe sources ────────────────────────────────────────────────────────
    active, source_used, probe_error = _probe_sources(base_url, sources)

    elapsed = int((time.time() - started) * 1000)

    # ── Determine decision ──────────────────────────────────────────────────
    # Sprint 2: policy=soft/hard takes precedence over mode-based logic.
    if source_used == _SOURCE_NONE:
        # No source produced data
        if _policy == "hard":
            decision = "BLOCKED"
            category = "ENV"
            reason = "BUILD_UNVERIFIABLE"   # Sprint 2 reason code (harder than FINGERPRINT_SOURCE_MISSING)
            matched = False
        elif _policy == "soft":
            decision = "WARN"
            category = None
            reason = "FINGERPRINT_SOURCE_MISSING"
            matched = True
        elif mode == "publish":
            decision = "BLOCKED"
            category = "ENV"
            reason = "FINGERPRINT_SOURCE_MISSING"
            matched = False
        else:
            # dry-run without explicit policy: warn but continue
            decision = "WARN"
            category = None
            reason = "FINGERPRINT_SOURCE_MISSING"
            matched = True  # treat as no mismatch when we can't check
    elif _fingerprints_match(expected, active):
        decision = "ALLOW"
        category = None
        reason = None
        matched = True
    else:
        # Mismatch detected
        if _policy == "soft":
            decision = "WARN"
            category = None
            reason = "DEPLOYMENT_MISMATCH"
            matched = False
        else:
            # hard or legacy behavior: always block on mismatch
            decision = "BLOCKED"
            category = "ENV"
            reason = "DEPLOYMENT_MISMATCH"
            matched = False

    result = DeploymentFingerprintResult(
        matched=matched,
        source=source_used,
        expected=expected,
        active=active,
        decision=decision,
        category=category,
        reason=reason,
        skipped=False,
        elapsed_ms=elapsed,
        artifact_path=None,
    )

    # ── Artifact ─────────────────────────────────────────────────────────────
    artifact_path = _write_artifact(result, evidence_dir, run_id)
    if artifact_path:
        result.artifact_path = str(artifact_path)

    # ── Event ────────────────────────────────────────────────────────────────
    _emit_event(exec_logger, ticket_id, result)

    if decision == "BLOCKED":
        logger.warning(
            "deployment_fingerprint BLOCKED ticket=%s reason=%s expected=%s active=%s source=%s",
            ticket_id, reason, expected, active, source_used,
        )
    elif decision == "WARN":
        logger.warning(
            "deployment_fingerprint WARN ticket=%s reason=%s source=%s probe_error=%s",
            ticket_id, reason, source_used, probe_error,
        )
    else:
        logger.info(
            "deployment_fingerprint ALLOW ticket=%s source=%s build_id=%s",
            ticket_id, source_used, active.get("build_id"),
        )

    return result


# ── Source probing ────────────────────────────────────────────────────────────

def _resolve_sources_from_env(defaults: list) -> list:
    """Allow QA_UAT_FINGERPRINT_SOURCE to override source priority."""
    override = os.environ.get("QA_UAT_FINGERPRINT_SOURCE", "").strip()
    if override:
        return [s.strip() for s in override.split(",") if s.strip()]
    return defaults


def _probe_sources(base_url: str, sources: list) -> tuple:
    """Try each source in order. Returns (active_dict, source_name, error_msg)."""
    active: dict = {}
    last_error: str = ""

    for source in sources:
        try:
            if source == _SOURCE_HEALTH:
                data = _probe_health_endpoint(base_url)
                if data is not None:
                    active = data
                    return (active, _SOURCE_HEALTH, "")

            elif source == _SOURCE_MANIFEST:
                data = _probe_file_manifest()
                if data is not None:
                    active = data
                    return (active, _SOURCE_MANIFEST, "")

            elif source == _SOURCE_META:
                data = _probe_html_meta(base_url)
                if data is not None:
                    active = data
                    return (active, _SOURCE_META, "")

            elif source == _SOURCE_DLL:
                data = _probe_dll_hash()
                if data is not None:
                    active = data
                    return (active, _SOURCE_DLL, "")

            elif source == _SOURCE_MANUAL:
                data = _probe_manual_config()
                if data is not None:
                    active = data
                    return (active, _SOURCE_MANUAL, "")

        except Exception as exc:  # noqa: BLE001
            last_error = f"{source}: {exc}"
            logger.debug("deployment_fingerprint source %s error: %s", source, exc)
            continue

    return ({}, _SOURCE_NONE, last_error)


def _probe_health_endpoint(base_url: str) -> Optional[dict]:
    """GET health endpoint; return normalized dict or None."""
    health_path = os.environ.get("QA_UAT_HEALTH_ENDPOINT", "").strip()
    candidates = [health_path] if health_path else _DEFAULT_HEALTH_PATHS

    for path in candidates:
        url = base_url + path.lstrip("/")
        data = _try_health_endpoint(url)
        if data is not None:
            return _normalize_active(
                build_id=data.get("build_id") or data.get("version") or data.get("build"),
                commit=data.get("commit") or data.get("git_sha") or data.get("sha"),
                branch=data.get("branch") or data.get("git_branch"),
            )
    return None


def _probe_file_manifest() -> Optional[dict]:
    """Read build-manifest.json from data/ directory."""
    for path in [_BUILD_MANIFEST_FILE, _BUILD_ID_FILE]:
        if path.is_file():
            try:
                raw = path.read_text(encoding="utf-8").strip()
                if not raw:
                    continue
                try:
                    data = json.loads(raw)
                    if isinstance(data, dict):
                        return _normalize_active(
                            build_id=data.get("build_id") or data.get("version"),
                            commit=data.get("commit"),
                            branch=data.get("branch"),
                        )
                except json.JSONDecodeError:
                    # Plain text — treat as build_id only
                    return _normalize_active(build_id=raw[:100])
            except OSError:
                continue
    return None


def _probe_html_meta(base_url: str) -> Optional[dict]:
    """Parse <meta> tags from the login page."""
    login_url = base_url + "FrmLogin.aspx"
    meta = _try_html_meta(login_url)
    if not meta:
        return None
    build_id = meta.get(_META_BUILD_ID)
    if not build_id:
        return None
    return _normalize_active(
        build_id=build_id,
        commit=meta.get(_META_BUILD_HASH),
        branch=meta.get(_META_BRANCH),
    )


def _probe_dll_hash() -> Optional[dict]:
    """Compute hash of key DLL/bundle files if accessible."""
    # Attempt common locations — this is best-effort
    candidates = [
        _TOOL_ROOT.parent.parent / "AgendaWeb" / "bin" / "AgendaWeb.dll",
        _TOOL_ROOT / "data" / ".dll_build_marker",
    ]
    for path in candidates:
        if path.is_file():
            try:
                stat = path.stat()
                # Use mtime + size as a cheap "hash"
                fingerprint = f"mtime:{int(stat.st_mtime)},size:{stat.st_size}"
                return _normalize_active(build_id=fingerprint)
            except OSError:
                continue
    return None


def _probe_manual_config() -> Optional[dict]:
    """Read build id from env vars (manual config)."""
    build_id = (
        os.environ.get("QA_UAT_EXPECTED_BUILD_ID", "").strip()
        or os.environ.get("QA_EXPECTED_BUILD_ID", "").strip()
    )
    branch = os.environ.get("QA_UAT_EXPECTED_BRANCH", "").strip()
    if build_id:
        return _normalize_active(build_id=build_id, branch=branch or None)
    return None


def _normalize_active(
    build_id: Optional[str] = None,
    commit: Optional[str] = None,
    branch: Optional[str] = None,
) -> dict:
    return {
        "build_id": (build_id or "").strip() or None,
        "commit": (commit or "").strip() or None,
        "branch": (branch or "").strip() or None,
    }


def _fingerprints_match(expected: dict, active: dict) -> bool:
    """Compare expected vs active fingerprint.

    Only compares keys that have a non-empty value in expected.
    Missing keys in active are treated as mismatch.
    """
    for key in ("build_id", "commit", "branch"):
        exp_val = (expected.get(key) or "").strip()
        if not exp_val:
            continue  # key not constrained
        act_val = (active.get(key) or "").strip()
        if exp_val != act_val:
            return False
    return True


# ── Artifact & event ──────────────────────────────────────────────────────────

def _write_artifact(
    result: DeploymentFingerprintResult,
    evidence_dir: Optional[Path],
    run_id: Optional[str],
) -> Optional[Path]:
    """Write deployment_fingerprint.json artifact; return path or None."""
    if evidence_dir is None:
        return None
    try:
        if run_id:
            artifact_dir = evidence_dir / str(run_id)
        else:
            artifact_dir = evidence_dir
        artifact_dir.mkdir(parents=True, exist_ok=True)
        artifact_path = artifact_dir / "deployment_fingerprint.json"
        data = {
            "schema_version": "deployment_fingerprint/1.0",
            **result.to_dict(),
        }
        artifact_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        logger.debug("deployment_fingerprint artifact: %s", artifact_path)
        return artifact_path
    except Exception as exc:  # noqa: BLE001
        logger.warning("deployment_fingerprint: cannot write artifact: %s", exc)
        return None


def _emit_event(exec_logger, ticket_id: int, result: DeploymentFingerprintResult) -> None:
    """Emit deployment_fingerprint_check event to execution.jsonl."""
    if exec_logger is None:
        return
    try:
        exec_logger.event("deployment_fingerprint_check", {
            "ticket_id": ticket_id,
            "expected": result.expected,
            "active": result.active,
            "source": result.source,
            "matched": result.matched,
            "decision": result.decision,
            "category": result.category,
            "reason": result.reason,
            "skipped": result.skipped,
            "elapsed_ms": result.elapsed_ms,
            "artifact_path": result.artifact_path,
        })
    except Exception as exc:  # noqa: BLE001
        logger.debug("deployment_fingerprint: cannot emit event: %s", exc)


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def _normalize_base_url(url: str) -> str:
    return url.rstrip("/") + "/"


def _try_health_endpoint(url: str) -> Optional[dict]:
    """GET url, return parsed JSON dict if successful, else None."""
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
        self.metas: dict = {}

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag.lower() != "meta":
            return
        attr_dict = {k.lower(): v for k, v in attrs if v is not None}
        name = attr_dict.get("name", "").lower()
        content = attr_dict.get("content", "")
        if name and content:
            self.metas[name] = content


def _try_html_meta(url: str) -> Optional[dict]:
    """GET url and parse <meta> tags. Returns None on error."""
    try:
        req = urllib.request.Request(url, headers={"Accept": "text/html"})
        with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT_S) as resp:
            body = resp.read(16 * 1024).decode("utf-8", errors="replace")
        parser = _MetaTagParser()
        parser.feed(body)
        relevant = {
            k: v for k, v in parser.metas.items()
            if k in (_META_BUILD_ID, _META_BUILD_HASH, _META_BRANCH)
        }
        return relevant if relevant else None
    except (urllib.error.URLError, OSError, Exception):
        return None


# ═════════════════════════════════════════════════════════════════════════════
# BACKWARDS COMPAT — pre-Sprint 3 advisory API (used by environment_preflight)
# ═════════════════════════════════════════════════════════════════════════════

@dataclass
class DeploymentFingerprint:
    """Advisory fingerprint — pre-Sprint 3. Never blocks the pipeline."""
    ok: bool
    source: str
    active_build_id: Optional[str]
    active_commit: Optional[str]
    expected_build_id: Optional[str]
    matched: bool
    mismatch_reason: Optional[str]
    elapsed_ms: int

    def to_dict(self) -> dict:
        return asdict(self)


def check_deployment(
    base_url: Optional[str] = None,
    expected_build_id: Optional[str] = None,
) -> DeploymentFingerprint:
    """Advisory deployment check (pre-Sprint 3). Never blocks. Returns DeploymentFingerprint.

    Kept for backwards compatibility with environment_preflight.py.
    New code should use check_deployment_fingerprint() instead.
    """
    started = time.time()

    base_url = _normalize_base_url(
        base_url or os.environ.get("AGENDA_WEB_BASE_URL", "http://localhost:35017/AgendaWeb/")
    )
    expected = expected_build_id or os.environ.get("QA_EXPECTED_BUILD_ID", "").strip() or None

    active_build_id: Optional[str] = None
    active_commit: Optional[str] = None
    source = _SOURCE_NONE

    # Strategy 1: Health endpoint
    for path in _DEFAULT_HEALTH_PATHS:
        health_url = base_url + path
        data = _try_health_endpoint(health_url)
        if data is not None:
            active_build_id = data.get("build_id") or data.get("version") or data.get("build")
            active_commit   = data.get("commit") or data.get("git_sha") or data.get("sha")
            source = _SOURCE_HEALTH
            break

    # Strategy 2: HTML meta tag
    if active_build_id is None:
        login_url = base_url + "FrmLogin.aspx"
        meta = _try_html_meta(login_url)
        if meta:
            active_build_id = meta.get(_META_BUILD_ID)
            active_commit   = meta.get(_META_BUILD_HASH)
            source = _SOURCE_META

    # Strategy 3: Local file manifest
    if active_build_id is None and _BUILD_ID_FILE.is_file():
        try:
            raw = _BUILD_ID_FILE.read_text(encoding="utf-8").strip()
            if raw:
                active_build_id = raw
                source = _SOURCE_MANIFEST
        except OSError:
            pass

    # Strategy 4: Manual
    if active_build_id is None and expected:
        source = _SOURCE_MANUAL

    ok = active_build_id is not None
    elapsed = int((time.time() - started) * 1000)

    if expected is None:
        matched = True
        mismatch_reason = None
    elif active_build_id is None:
        matched = False
        mismatch_reason = (
            f"No se pudo determinar el build activo. Expected={expected!r}. "
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
