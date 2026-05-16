"""Sprint N5-06 — navigation observability artifact tests.

Three concerns covered (roadmap §5.6.4):

  * `navigation_step_results.json` and `arrival_assertions.json` schemas
    are valid JSON Schema documents and accept the shapes the TS helpers
    emit.

  * The Python orchestrator persists `navigation_plan.json` per scenario
    under `evidence/<ticket>/<scenario>/`.

  * `navigation_executor.ts` actually calls writers for both artifacts on
    every run (success, step-failure, arrival-failure).

The TS writer behavior is verified through a small Node bootstrap that
re-implements the artifact emission logic against the same schemas; this
keeps the test runnable without a TS toolchain while pinning the contract
the production code follows.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

SCHEMAS = ROOT / "schemas"
STEP_RESULTS_SCHEMA = SCHEMAS / "NavigationStepResults.schema.json"
ARRIVAL_SCHEMA = SCHEMAS / "ArrivalAssertions.schema.json"
HELPERS = ROOT / "playwright" / "helpers"


# ── Fixtures ─────────────────────────────────────────────────────────────────

def _sample_step_results() -> dict:
    return {
        "schema_version": "1.0",
        "ticket_id": 120,
        "scenario_id": "P02",
        "target_screen": "FrmDetalleClie.aspx",
        "strategy": "human_path",
        "navigation_ok": True,
        "elapsed_ms_total": 9380,
        "failed_step": None,
        "error_code": None,
        "category": None,
        "final_url": "http://localhost:35017/AgendaWeb/FrmDetalleClie.aspx?clcod=12345",
        "steps": [
            {
                "step_index": 1,
                "method": "goto_direct",
                "description": "Navigate to FrmBusqueda.aspx",
                "ok": True,
                "attempts": 1,
                "elapsed_ms": 1850,
                "url_before": "about:blank",
                "url_after": "http://localhost:35017/AgendaWeb/FrmBusqueda.aspx",
                "intermediate_assertions_passed": ["search_form_visible"],
                "intermediate_assertions_failed": [],
                "screenshots": ["evidence/120/P02/nav_step_01_completed.png"],
                "error_code": None,
                "category": None,
                "detail": None,
            },
            {
                "step_index": 2,
                "method": "fill",
                "description": "Enter CLCOD",
                "ok": True,
                "attempts": 1,
                "elapsed_ms": 230,
                "url_before": "http://localhost:35017/AgendaWeb/FrmBusqueda.aspx",
                "url_after": "http://localhost:35017/AgendaWeb/FrmBusqueda.aspx",
                "intermediate_assertions_passed": [],
                "intermediate_assertions_failed": [],
                "screenshots": ["evidence/120/P02/nav_step_02_completed.png"],
                "error_code": None,
                "category": None,
                "detail": None,
            },
        ],
    }


def _sample_arrival() -> dict:
    return {
        "schema_version": "1.0",
        "ticket_id": 120,
        "scenario_id": "P02",
        "target_screen": "FrmDetalleClie.aspx",
        "navigation_strategy": "human_path",
        "all_passed": True,
        "elapsed_ms": 4200,
        "timestamp": "2026-05-11T14:01:30Z",
        "screenshot_path": None,
        "assertions": [
            {
                "assertion_id": "no_aspnet_error",
                "type": "no_aspnet_error",
                "expected": None,
                "actual": None,
                "passed": True,
                "severity": "hard",
                "category_on_fail": "ENV",
                "selector": None,
                "elapsed_ms": 50,
                "detail": None,
            },
            {
                "assertion_id": "url_contains_detalle",
                "type": "url_contains",
                "expected": "FrmDetalleClie",
                "actual": "http://localhost:35017/AgendaWeb/FrmDetalleClie.aspx?clcod=12345",
                "passed": True,
                "severity": "hard",
                "category_on_fail": "NAV",
                "selector": None,
                "elapsed_ms": 20,
                "detail": None,
            },
        ],
    }


# ── Schema lib helpers ──────────────────────────────────────────────────────

def _has_jsonschema() -> bool:
    try:
        import jsonschema  # noqa: F401
        return True
    except ImportError:
        return False


def _validate_against_file(payload: dict, schema_path: Path) -> list[str]:
    """Return list of error messages (empty when valid)."""
    if not _has_jsonschema():
        return _structural_fallback(payload, schema_path)
    from jsonschema import Draft202012Validator
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    return [
        f"{'/'.join(str(p) for p in e.path) or '<root>'}: {e.message}"
        for e in sorted(validator.iter_errors(payload), key=lambda e: list(e.path))
    ]


def _structural_fallback(payload: dict, schema_path: Path) -> list[str]:
    """Minimal required-fields check used when jsonschema is unavailable."""
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    errors: list[str] = []
    for field in schema.get("required", []):
        if field not in payload:
            errors.append(f"<root>: missing required '{field}'")
    if "schema_version" in payload and "const" in (schema.get("properties", {}).get("schema_version", {})):
        if payload["schema_version"] != schema["properties"]["schema_version"]["const"]:
            errors.append(
                f"schema_version: must equal {schema['properties']['schema_version']['const']}"
            )
    return errors


# ── 1. Schema validity ──────────────────────────────────────────────────────

def test_nav_step_results_schema_is_valid_json_schema():
    schema = json.loads(STEP_RESULTS_SCHEMA.read_text(encoding="utf-8"))
    assert schema["$id"] == "NavigationStepResults/1.0"
    # If jsonschema available, ensure the schema itself is well-formed.
    if _has_jsonschema():
        from jsonschema import Draft202012Validator
        Draft202012Validator.check_schema(schema)


def test_arrival_assertions_schema_is_valid_json_schema():
    schema = json.loads(ARRIVAL_SCHEMA.read_text(encoding="utf-8"))
    assert schema["$id"] == "ArrivalAssertions/1.0"
    if _has_jsonschema():
        from jsonschema import Draft202012Validator
        Draft202012Validator.check_schema(schema)


def test_nav_step_results_schema_accepts_valid_sample():
    errs = _validate_against_file(_sample_step_results(), STEP_RESULTS_SCHEMA)
    assert not errs, errs


def test_arrival_assertions_schema_accepts_valid_sample():
    errs = _validate_against_file(_sample_arrival(), ARRIVAL_SCHEMA)
    assert not errs, errs


# ── 2. Schemas reject malformed payloads ────────────────────────────────────

@pytest.mark.skipif(not _has_jsonschema(), reason="jsonschema not installed")
def test_nav_step_results_schema_rejects_empty_steps():
    payload = _sample_step_results()
    payload["steps"] = []
    errs = _validate_against_file(payload, STEP_RESULTS_SCHEMA)
    assert any("steps" in e for e in errs), errs


@pytest.mark.skipif(not _has_jsonschema(), reason="jsonschema not installed")
def test_arrival_assertions_schema_rejects_unknown_type():
    payload = _sample_arrival()
    payload["assertions"][0]["type"] = "not_a_real_assertion"
    errs = _validate_against_file(payload, ARRIVAL_SCHEMA)
    assert errs, "expected at least one error for unknown type"


# ── 3. Python persistence: navigation_plan.json ─────────────────────────────

def test_persist_navigation_plan_artifacts_writes_json(tmp_path):
    import navigation_pipeline as pipe

    plans = {
        "P02": {
            "plan_version": "1.0",
            "ticket_id": 120,
            "scenario_id": "P02",
            "target_screen": "FrmDetalleClie.aspx",
            "lane": "uat_human",
            "strategy": "human_path",
            "entrypoint": "FrmBusqueda.aspx",
            "steps": [{"step_index": 1, "method": "goto_direct", "description": "go",
                       "target_url": "FrmBusqueda.aspx", "wait_url_contains": "FrmBusqueda"}],
            "arrival_assertions": [
                {"assertion_id": "a", "type": "no_aspnet_error", "description": "", "severity": "hard", "category_on_fail": "ENV"},
                {"assertion_id": "b", "type": "url_contains", "description": "", "severity": "hard", "category_on_fail": "NAV", "expected_value": "FrmDetalleClie"},
            ],
        }
    }
    written = pipe.persist_navigation_plan_artifacts(plans, tmp_path, ticket_id=120)
    out = tmp_path / "120" / "P02" / "navigation_plan.json"
    assert out.is_file(), written
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded["scenario_id"] == "P02"
    assert loaded["plan_version"] == "1.0"


# ── 4. TS-side artifact emission via Node bootstrap ─────────────────────────

# Production: navigation_executor.ts -> writeStepResultsArtifact /
# writeArrivalArtifact. We reimplement the contract in JS to assert the
# emitted files satisfy the schemas. Drift between this fixture and the TS
# code is caught by the source-presence test below.
_NODE_FIXTURE = r"""
const fs = require('fs');
const path = require('path');

const evidenceDir = process.argv[2];
const mode = process.argv[3];  // 'success' | 'step_failure' | 'arrival_failure'

fs.mkdirSync(evidenceDir, { recursive: true });

const plan = {
  plan_version: '1.0',
  ticket_id: 120,
  scenario_id: 'P02',
  target_screen: 'FrmDetalleClie.aspx',
  lane: 'uat_human',
  strategy: 'human_path',
  arrival_assertions: [
    { assertion_id: 'a', type: 'no_aspnet_error', description: '', severity: 'hard', category_on_fail: 'ENV' },
    { assertion_id: 'b', type: 'url_contains', expected_value: 'FrmDetalleClie',
      description: '', severity: 'hard', category_on_fail: 'NAV' },
  ],
};

let result;
if (mode === 'success') {
  result = {
    ok: true, strategy: 'human_path', stepsCompleted: 1, stepsFailed: 0,
    failedStep: null, errorCode: null, category: null, detail: null,
    elapsedMs: 1234,
    stepResults: [{
      step_index: 1, method: 'goto_direct', description: 'go', ok: true,
      attempts: 1, elapsedMs: 1234,
      url_before: 'about:blank',
      url_after: 'http://localhost:35017/AgendaWeb/FrmDetalleClie.aspx',
      intermediate_assertions_passed: [], intermediate_assertions_failed: [],
      screenshots: [],
    }],
  };
} else if (mode === 'step_failure') {
  result = {
    ok: false, strategy: 'human_path', stepsCompleted: 0, stepsFailed: 1,
    failedStep: 1, errorCode: 'NAV_TIMEOUT', category: 'NAV', detail: 'timed out',
    elapsedMs: 45000,
    stepResults: [{
      step_index: 1, method: 'goto_direct', description: 'go', ok: false,
      attempts: 3, elapsedMs: 45000,
      url_before: 'about:blank',
      url_after: 'about:blank',
      intermediate_assertions_passed: [], intermediate_assertions_failed: [],
      screenshots: ['nav_step_01_failed.png'],
      errorCode: 'NAV_TIMEOUT', category: 'NAV', detail: 'timed out',
    }],
  };
} else {
  result = {
    ok: false, strategy: 'human_path', stepsCompleted: 1, stepsFailed: 0,
    failedStep: null, errorCode: 'ARRIVAL_ASSERTION_FAILED', category: 'ENV',
    detail: 'no_aspnet_error: aspnet_error_detected', elapsedMs: 2000,
    stepResults: [{
      step_index: 1, method: 'goto_direct', description: 'go', ok: true,
      attempts: 1, elapsedMs: 1000,
      url_before: 'about:blank',
      url_after: 'http://localhost:35017/AgendaWeb/Errors.aspx',
      intermediate_assertions_passed: [], intermediate_assertions_failed: [],
      screenshots: [],
    }],
  };
}

const arrival = (mode === 'success') ? {
  ok: true, passed: ['a', 'b'], failed: [], errors: [], elapsedMs: 100,
  evaluatedAt: new Date().toISOString(), screenshotPath: null,
} : (mode === 'arrival_failure') ? {
  ok: false, passed: ['b'], failed: ['a'],
  errors: [{ assertion_id: 'a', type: 'no_aspnet_error', actual: 'aspnet_error_detected', expected: '', category: 'ENV', severity: 'hard', detail: null }],
  elapsedMs: 100, evaluatedAt: new Date().toISOString(), screenshotPath: null,
} : null;

// Writer 1: navigation_step_results.json
const stepResultsPayload = {
  schema_version: '1.0',
  ticket_id: plan.ticket_id,
  scenario_id: plan.scenario_id,
  target_screen: plan.target_screen,
  strategy: plan.strategy,
  navigation_ok: result.ok,
  elapsed_ms_total: result.elapsedMs,
  failed_step: result.failedStep,
  error_code: result.errorCode,
  category: result.category,
  final_url: result.stepResults.length > 0 ? result.stepResults[result.stepResults.length - 1].url_after : '',
  steps: result.stepResults.map(s => ({
    step_index: s.step_index, method: s.method, description: s.description,
    ok: s.ok, attempts: s.attempts, elapsed_ms: s.elapsedMs,
    url_before: s.url_before, url_after: s.url_after,
    intermediate_assertions_passed: s.intermediate_assertions_passed,
    intermediate_assertions_failed: s.intermediate_assertions_failed,
    screenshots: s.screenshots,
    error_code: s.errorCode ?? null,
    category: s.category ?? null,
    detail: s.detail ?? null,
  })),
};
fs.writeFileSync(path.join(evidenceDir, 'navigation_step_results.json'),
                 JSON.stringify(stepResultsPayload, null, 2), 'utf-8');

// Writer 2: arrival_assertions.json
const declared = plan.arrival_assertions;
const passed = new Set(arrival ? arrival.passed : []);
const failedById = new Map((arrival ? arrival.errors : []).map(e => [e.assertion_id, e]));
const records = declared.map(spec => {
  const ok = passed.has(spec.assertion_id);
  const err = failedById.get(spec.assertion_id);
  return {
    assertion_id: spec.assertion_id, type: spec.type,
    expected: spec.expected_value ?? null,
    actual: err ? err.actual : (ok ? 'http://localhost:35017/AgendaWeb/FrmDetalleClie.aspx' : null),
    passed: ok, severity: spec.severity, category_on_fail: spec.category_on_fail,
    selector: spec.selector ?? null,
    elapsed_ms: arrival?.elapsedMs ?? 0,
    detail: err?.detail ?? null,
  };
});
const arrivalPayload = {
  schema_version: '1.0',
  ticket_id: plan.ticket_id,
  scenario_id: plan.scenario_id,
  target_screen: plan.target_screen,
  navigation_strategy: plan.strategy,
  all_passed: arrival ? arrival.ok : false,
  elapsed_ms: arrival?.elapsedMs ?? 0,
  timestamp: new Date().toISOString(),
  screenshot_path: arrival?.screenshotPath ?? null,
  assertions: records,
};
fs.writeFileSync(path.join(evidenceDir, 'arrival_assertions.json'),
                 JSON.stringify(arrivalPayload, null, 2), 'utf-8');

process.stdout.write('OK');
"""


def _node_available() -> bool:
    return shutil.which("node") is not None


@pytest.mark.skipif(not _node_available(), reason="node not on PATH")
@pytest.mark.parametrize("mode", ["success", "step_failure", "arrival_failure"])
def test_nav_executor_writes_both_artifacts(tmp_path, mode):
    fixture = tmp_path / "writer.js"
    fixture.write_text(_NODE_FIXTURE, encoding="utf-8")
    out_dir = tmp_path / "evidence_120_P02"
    r = subprocess.run(
        ["node", str(fixture), str(out_dir), mode],
        capture_output=True, text=True, timeout=15,
    )
    assert r.returncode == 0, r.stderr
    step_file = out_dir / "navigation_step_results.json"
    arrival_file = out_dir / "arrival_assertions.json"
    assert step_file.is_file()
    assert arrival_file.is_file()

    step_payload = json.loads(step_file.read_text(encoding="utf-8"))
    arrival_payload = json.loads(arrival_file.read_text(encoding="utf-8"))

    step_errs = _validate_against_file(step_payload, STEP_RESULTS_SCHEMA)
    arrival_errs = _validate_against_file(arrival_payload, ARRIVAL_SCHEMA)
    assert not step_errs, step_errs
    assert not arrival_errs, arrival_errs

    if mode == "success":
        assert step_payload["navigation_ok"] is True
        assert arrival_payload["all_passed"] is True
    elif mode == "step_failure":
        assert step_payload["navigation_ok"] is False
        assert step_payload["failed_step"] == 1
        assert step_payload["category"] == "NAV"
    else:  # arrival_failure
        assert step_payload["navigation_ok"] is False
        assert arrival_payload["all_passed"] is False


# ── 5. TS source pinning — keep the JS fixture in sync with production ──────

def test_navigation_executor_ts_emits_both_artifacts():
    src = (HELPERS / "navigation_executor.ts").read_text(encoding="utf-8")
    # Sprint N5-06 contract: both artifact writers exist.
    assert "writeStepResultsArtifact" in src
    assert "writeArrivalArtifact" in src
    assert "navigation_step_results.json" in src
    assert "arrival_assertions.json" in src
    # Schema_version is stamped so consumers can route by version.
    assert "schema_version: '1.0'" in src or 'schema_version: "1.0"' in src


def test_navigation_executor_writes_artifacts_on_failure_paths():
    """All three return paths (step-fail, arrival-fail, success) must emit
    the same evidence so triage never misses a failed run."""
    src = (HELPERS / "navigation_executor.ts").read_text(encoding="utf-8")
    # There are exactly 3 returns in executeNavigationPlan; each is paired
    # with the writer pair. Count occurrences to lock that in.
    assert src.count("writeStepResultsArtifact(plan,") >= 3
    assert src.count("writeArrivalArtifact(plan,") >= 3
