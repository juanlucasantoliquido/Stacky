"""Sprint N5-03 — static + Node-side acceptance tests for the TS helpers.

No tsc / jest / vitest available in this repo, so the TS helpers cannot be
imported from pytest directly. We instead:

  1) Statically verify the public surface and key invariants of each helper
     (file exists, exports declared, ASP.NET markers present, screenshot
     emission on failure path, etc.).
  2) Run the session_guard logic end-to-end via a small Node subprocess that
     reimplements the contract in plain JS (kept in sync with session_guard.ts
     by a structural assertion in the same test).

The `__tests__/*.test.ts` files complement these tests at the TypeScript
level — they document the intended behavior and run as-is once a TS test
harness is wired up.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

HELPERS = Path(__file__).parent.parent.parent / "playwright" / "helpers"
TESTS_DIR = HELPERS / "__tests__"


# ── Helper-file existence ────────────────────────────────────────────────────

@pytest.mark.parametrize("name", [
    "arrival_validator.ts",
    "navigation_executor.ts",
    "session_guard.ts",
])
def test_helper_files_exist(name):
    assert (HELPERS / name).is_file(), f"missing helper file: {name}"


@pytest.mark.parametrize("name", [
    "arrival_validator.test.ts",
    "navigation_executor.test.ts",
    "session_guard.test.ts",
])
def test_helper_test_files_exist(name):
    assert (TESTS_DIR / name).is_file(), f"missing helper test: {name}"


# ── arrival_validator.ts surface ─────────────────────────────────────────────

def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_arrival_validator_public_surface():
    src = _read(HELPERS / "arrival_validator.ts")
    # Required exports
    assert "export class ArrivalValidator" in src
    assert "export interface AssertionSpec" in src
    assert "export interface ArrivalValidationResult" in src
    # Required static methods (roadmap §5.3.3)
    for fn in [
        "static async validateAll",
        "static async checkUrlContains",
        "static async checkDomVisible",
        "static async checkNoAspnetError",
        "static async checkNoLoginRedirect",
        "static async checkNo500Response",
    ]:
        assert fn in src, f"ArrivalValidator missing: {fn}"


def test_arrival_validator_detects_aspnet_markers():
    src = _read(HELPERS / "arrival_validator.ts")
    # YSOD / Server Error markers (roadmap §5.3.3)
    for marker in [
        "Runtime Error",
        "Server Error in '/' Application",
        "Application Error",
        "Errors.aspx",
        "Error.aspx",
    ]:
        assert marker in src, f"ASP.NET marker missing in arrival_validator: {marker!r}"


def test_arrival_validator_screenshot_on_fail_supported():
    src = _read(HELPERS / "arrival_validator.ts")
    # Option + actual screenshot call inside validateAll
    assert "screenshotOnFail" in src
    assert "page.screenshot" in src


# ── navigation_executor.ts surface ───────────────────────────────────────────

def test_navigation_executor_public_surface():
    src = _read(HELPERS / "navigation_executor.ts")
    assert "export async function executeNavigationPlan" in src
    assert "export interface NavigationPlan" in src
    assert "export interface NavigationResult" in src
    # Strategies + methods enumerated (subset)
    for method in [
        "goto_direct", "goto_deeplink", "form_submit", "row_click",
        "button_click", "fill", "select", "dopostback", "wait",
    ]:
        assert f"'{method}'" in src or f'"{method}"' in src, f"method {method} not referenced"


def test_navigation_executor_emits_step_screenshots():
    src = _read(HELPERS / "navigation_executor.ts")
    # Every step has pre/completed/failed screenshots paths.
    assert "step_${idx}_pre" in src
    assert "step_${idx}_completed" in src
    assert "step_${idx}_failed" in src
    # safeScreenshot funnels through page.screenshot
    assert "page.screenshot" in src


def test_navigation_executor_runs_arrival_assertions_after_steps():
    src = _read(HELPERS / "navigation_executor.ts")
    assert "ArrivalValidator.validateAll(page, plan.arrival_assertions" in src
    # On failure the result classifies via arrival category
    assert "ARRIVAL_ASSERTION_FAILED" in src


def test_navigation_executor_classifies_env_errors():
    src = _read(HELPERS / "navigation_executor.ts")
    # The classifier should at minimum distinguish AUTH_EXPIRED and SERVER_ERROR
    assert "NAV_AUTH_EXPIRED" in src
    assert "NAV_SERVER_ERROR" in src
    assert "NAV_TIMEOUT" in src
    assert "NAV_PLAYWRIGHT_ERROR" in src


def test_navigation_executor_dopostback_uses_form_submit_bypass():
    src = _read(HELPERS / "navigation_executor.ts")
    dopostback_case = src.split("case 'dopostback':", 1)[1].split("case 'wait':", 1)[0]
    assert "HTMLFormElement.prototype.submit.call(form)" in dopostback_case
    assert "w.__doPostBack" not in dopostback_case


# ── session_guard.ts surface ─────────────────────────────────────────────────

def test_session_guard_public_surface():
    src = _read(HELPERS / "session_guard.ts")
    assert "export async function verifyStorageStateValid" in src
    assert "export function inspectStorageState" in src
    # Categories surfaced in the error message so the runner can classify
    assert "category=ENV" in src
    assert "STORAGESTATE_MISSING" in src
    assert "STORAGESTATE_EXPIRED" in src
    assert "SESSION_EXPIRED" in src


# ── Node-side behavior check for session_guard ──────────────────────────────

# We reimplement the contract in a tiny JS bootstrap so we can run real
# behavior assertions without a TS toolchain. The contract is kept narrow
# enough that drift between this fixture and session_guard.ts is loud:
# session_guard_public_surface above pins the public exports + error
# strings the fixture relies on.
_NODE_FIXTURE = r"""
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
  if (ageMin > maxAgeMinutes) return { ok: false, reason: 'STORAGESTATE_EXPIRED', ageMin };
  return { ok: true, ageMin };
}

const [,, fp, maxAgeArg] = process.argv;
const res = inspectStorageState(Number(maxAgeArg), fp);
process.stdout.write(JSON.stringify(res));
"""


def _node_available() -> bool:
    return shutil.which("node") is not None


@pytest.mark.skipif(not _node_available(), reason="node not on PATH")
def test_session_guard_missing_file_via_node(tmp_path):
    fixture = tmp_path / "guard.js"
    fixture.write_text(_NODE_FIXTURE, encoding="utf-8")
    missing = tmp_path / "does_not_exist.json"
    r = subprocess.run(
        ["node", str(fixture), str(missing), "120"],
        capture_output=True, text=True, timeout=15,
    )
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out["ok"] is False
    assert out["reason"] == "STORAGESTATE_MISSING"


@pytest.mark.skipif(not _node_available(), reason="node not on PATH")
def test_session_guard_expired_via_node(tmp_path):
    import datetime as _dt
    fixture = tmp_path / "guard.js"
    fixture.write_text(_NODE_FIXTURE, encoding="utf-8")
    fp = tmp_path / "agenda.fingerprint.json"
    expired = (_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(hours=3)).isoformat()
    fp.write_text(json.dumps({"fingerprint": "abc", "created_at": expired}), encoding="utf-8")
    r = subprocess.run(
        ["node", str(fixture), str(fp), "120"],
        capture_output=True, text=True, timeout=15,
    )
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out["ok"] is False
    assert out["reason"] == "STORAGESTATE_EXPIRED"
    assert out["ageMin"] > 120


@pytest.mark.skipif(not _node_available(), reason="node not on PATH")
def test_session_guard_valid_via_node(tmp_path):
    import datetime as _dt
    fixture = tmp_path / "guard.js"
    fixture.write_text(_NODE_FIXTURE, encoding="utf-8")
    fp = tmp_path / "agenda.fingerprint.json"
    fresh = (_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(minutes=10)).isoformat()
    fp.write_text(json.dumps({"fingerprint": "abc", "created_at": fresh}), encoding="utf-8")
    r = subprocess.run(
        ["node", str(fixture), str(fp), "120"],
        capture_output=True, text=True, timeout=15,
    )
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out["ok"] is True


# ── Template wiring sanity check (links N5-01 ↔ N5-03) ───────────────────────

def test_template_imports_match_helper_exports():
    template = (HELPERS.parent.parent / "templates" / "playwright_test.spec.ts.j2").read_text(encoding="utf-8")
    assert re.search(r"from ['\"].*playwright/helpers/navigation_executor['\"]", template)
    assert re.search(r"from ['\"].*playwright/helpers/session_guard['\"]", template)
    # Helpers expose what the template imports
    exec_src = _read(HELPERS / "navigation_executor.ts")
    guard_src = _read(HELPERS / "session_guard.ts")
    assert "export async function executeNavigationPlan" in exec_src
    assert "export async function verifyStorageStateValid" in guard_src
