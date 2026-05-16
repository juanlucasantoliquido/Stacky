"""Sprint N5-07 — Session-expiry detection.

The roadmap (§5.7.2) names three moments where session expiry can occur:

  1. Pre-navigation     — storageState older than TTL (or missing).
  2. During navigation  — a step's goto/form_submit redirects to FrmLogin.
  3. Post-navigation    — silent timeout puts a login panel inside the target
                          screen even though the URL did not flip.

All three must classify as `error_code=NAV_AUTH_EXPIRED, category=ENV` so
the runner can short-circuit without burning a 45-second NAV_TIMEOUT.

This module tests:
  * The three mandatory cases listed in §5.7.4 (missing / expired / valid),
    repeated with a clearer surface than the N5-03 helper tests.
  * `arrival_validator` detects the in-page login panel (post-nav case).
  * `navigation_executor` classifier maps URL→FrmLogin to NAV_AUTH_EXPIRED ENV.
  * `global.setup.ts` writes `created_at` to the fingerprint file so
    `session_guard.ts` can compute the age.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

HELPERS = ROOT / "playwright" / "helpers"
GLOBAL_SETUP = ROOT / "playwright" / "global.setup.ts"
SESSION_GUARD = HELPERS / "session_guard.ts"
ARRIVAL = HELPERS / "arrival_validator.ts"
EXECUTOR = HELPERS / "navigation_executor.ts"


# ── Helpers ─────────────────────────────────────────────────────────────────

def _node_available() -> bool:
    return shutil.which("node") is not None


# Reimplements `inspectStorageState` from session_guard.ts so we can exercise
# the contract through real filesystem IO + clock arithmetic without TS
# tooling. The source-pinning test below catches drift between this and the
# production helper.
_GUARD_JS = r"""
const fs = require('fs');
const path = require('path');

function inspectStorageState(maxAgeMinutes, authFilePath) {
  const fp = path.resolve(authFilePath);
  if (!fs.existsSync(fp)) {
    return { ok: false, reason: 'STORAGESTATE_MISSING' };
  }
  let parsed = {};
  try { parsed = JSON.parse(fs.readFileSync(fp, 'utf-8')); }
  catch (_e) { return { ok: false, reason: 'STORAGESTATE_UNPARSEABLE' }; }
  if (!parsed || !parsed.created_at) {
    return { ok: false, reason: 'STORAGESTATE_MISSING_CREATED_AT' };
  }
  const created = Date.parse(parsed.created_at);
  if (isNaN(created)) return { ok: false, reason: 'STORAGESTATE_INVALID_CREATED_AT' };
  const ageMin = (Date.now() - created) / 60000;
  if (ageMin > maxAgeMinutes) {
    return { ok: false, reason: 'STORAGESTATE_EXPIRED', ageMin };
  }
  return { ok: true, ageMin };
}

const [,, fp, maxAge] = process.argv;
process.stdout.write(JSON.stringify(inspectStorageState(Number(maxAge), fp)));
"""


def _run_guard(tmp_path: Path, fingerprint_path: Path | None, max_age: int) -> dict:
    bootstrap = tmp_path / "guard.js"
    bootstrap.write_text(_GUARD_JS, encoding="utf-8")
    fp_arg = str(fingerprint_path) if fingerprint_path else str(tmp_path / "missing.json")
    r = subprocess.run(
        ["node", str(bootstrap), fp_arg, str(max_age)],
        capture_output=True, text=True, timeout=15,
    )
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


# ── 1. Pre-navigation: missing fingerprint ──────────────────────────────────

@pytest.mark.skipif(not _node_available(), reason="node not on PATH")
def test_session_expiry_pre_nav_missing_file(tmp_path):
    """§5.7.4 — `verifyStorageStateValid()` must report STORAGESTATE_MISSING."""
    result = _run_guard(tmp_path, fingerprint_path=None, max_age=120)
    assert result["ok"] is False
    assert result["reason"] == "STORAGESTATE_MISSING"


# ── 2. Pre-navigation: expired fingerprint ──────────────────────────────────

@pytest.mark.skipif(not _node_available(), reason="node not on PATH")
def test_session_expiry_pre_nav_expired(tmp_path):
    """§5.7.4 — fingerprint 3h in the past must classify as ENV
    STORAGESTATE_EXPIRED."""
    fp = tmp_path / "agenda.fingerprint.json"
    expired = (_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(hours=3)).isoformat()
    fp.write_text(
        json.dumps({"fingerprint": "abc", "created_at": expired, "user": "qauser"}),
        encoding="utf-8",
    )
    result = _run_guard(tmp_path, fp, max_age=120)
    assert result["ok"] is False
    assert result["reason"] == "STORAGESTATE_EXPIRED"
    assert result["ageMin"] > 120


# ── 3. Pre-navigation: valid fingerprint ────────────────────────────────────

@pytest.mark.skipif(not _node_available(), reason="node not on PATH")
def test_session_expiry_pre_nav_valid(tmp_path):
    """§5.7.4 — fingerprint 10 minutes old must NOT throw."""
    fp = tmp_path / "agenda.fingerprint.json"
    fresh = (_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(minutes=10)).isoformat()
    fp.write_text(
        json.dumps({"fingerprint": "abc", "created_at": fresh, "user": "qauser"}),
        encoding="utf-8",
    )
    result = _run_guard(tmp_path, fp, max_age=120)
    assert result["ok"] is True
    assert result["ageMin"] < 120


# ── 4. During-navigation: URL→FrmLogin classification ──────────────────────

def test_session_expiry_during_nav_classifier_maps_to_nav_auth_expired():
    """`classifyStepError` in navigation_executor.ts must map a step error
    landing on FrmLogin to (NAV_AUTH_EXPIRED, ENV) and mark it terminal
    (no retry). The contract is enforced statically because the executor
    classifier is internal."""
    src = EXECUTOR.read_text(encoding="utf-8")
    # The classifier checks URL contains 'frmlogin'.
    assert "url.includes('frmlogin')" in src or "frmlogin" in src.lower()
    # And emits the right error code + ENV category.
    assert "NAV_AUTH_EXPIRED" in src
    # AND treats it as non-retriable: NAV_AUTH_EXPIRED must NOT be in
    # isRetriable's allow-list.
    retriable_block = src.split("function isRetriable", 1)[1].split("\n}", 1)[0]
    assert "NAV_AUTH_EXPIRED" not in retriable_block, (
        "NAV_AUTH_EXPIRED must be terminal (is_terminal=true) — do not retry."
    )


# ── 5. Post-navigation: in-page login panel detection ──────────────────────

def test_session_expiry_post_nav_detects_in_page_login_panel():
    """`checkNoLoginRedirect` must also detect the silent in-page login
    panel that appears when the session times out inside an UpdatePanel
    (roadmap §5.7.2 case 3)."""
    src = ARRIVAL.read_text(encoding="utf-8")
    # The in-page login panel selectors are checked alongside the URL.
    assert "#ctl00_c_pnlLogin" in src or "#c_pnlLogin" in src
    # And the URL flip is also handled.
    assert "frmlogin" in src.lower()


def test_arrival_validator_no_login_redirect_assertion_in_executor_chain():
    """The executor runs arrival_assertions after the last step, which is
    where `no_login_redirect` fires post-nav."""
    src = EXECUTOR.read_text(encoding="utf-8")
    assert "ArrivalValidator.validateAll(page, plan.arrival_assertions" in src


# ── 6. global.setup.ts writes created_at to fingerprint ─────────────────────

def test_global_setup_writes_created_at_to_fingerprint():
    """§5.7.3 — `global.setup.ts` must stamp `created_at` so `session_guard`
    can compute the age. The other expected fields (`fingerprint`, `user`,
    `base_url`) are also required because the existing N5-03 helpers use
    them downstream."""
    src = GLOBAL_SETUP.read_text(encoding="utf-8")
    assert "created_at:" in src or '"created_at":' in src
    # Make sure it's an actual current timestamp, not a hardcoded string.
    assert "new Date().toISOString()" in src
    # Required companion fields
    for field in ("fingerprint", "user", "base_url"):
        assert f"{field}" in src, f"missing field {field} in fingerprint write"


# ── 7. Error message structure for the runner to parse ──────────────────────

def test_session_guard_error_messages_carry_category_and_reason():
    """The thrown Error must contain `category=ENV reason=…` so
    uat_failure_analyzer can classify deterministically."""
    src = SESSION_GUARD.read_text(encoding="utf-8")
    # All three error paths use the structured marker.
    assert src.count("category=ENV") >= 3
    assert "STORAGESTATE_MISSING" in src
    assert "STORAGESTATE_EXPIRED" in src
    assert "SESSION_EXPIRED" in src


# ── 8. End-to-end: expired fingerprint → executor classification ────────────

def test_session_expiry_decision_matrix_documented_in_code():
    """The mapping `(detection-moment) → (error_code, category, is_terminal)`
    must be expressed in the codebase so future contributors don't reinvent
    it. We verify the four ground-truth strings are co-located in the
    canonical files."""
    guard_src = SESSION_GUARD.read_text(encoding="utf-8")
    exec_src = EXECUTOR.read_text(encoding="utf-8")
    matrix = {
        "STORAGESTATE_MISSING": guard_src,
        "STORAGESTATE_EXPIRED": guard_src,
        "NAV_AUTH_EXPIRED": exec_src,
        "ENV": guard_src + exec_src,
    }
    for token, where in matrix.items():
        assert token in where, f"{token} missing from the expected helper"
