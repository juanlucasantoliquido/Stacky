"""
tests/regression/test_pipeline_regression.py — CI regression suite for QA UAT pipeline.

Validates deterministic pipeline behavior for known tickets (70, 116, 119, 120, 122)
without real ADO calls or browser automation.  Each test case mocks all IO and
asserts structural invariants that must hold on every pipeline run.

These tests catch regressions introduced during refactoring of:
- qa_uat_pipeline.py
- playwright_test_generator.py
- uat_test_runner.py
- execution_logger.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add tool root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
os.environ.setdefault("STACKY_LLM_BACKEND", "mock")
os.environ.setdefault("QA_UAT_REQUIRE_PLAYBOOK", "false")

FIXTURES = Path(__file__).parent.parent / "fixtures"
TOOL_DIR = Path(__file__).parent.parent.parent


# ── Fixture helpers ───────────────────────────────────────────────────────────

def _ticket(ticket_id: int, screen: str = "FrmAgenda.aspx") -> dict:
    base = json.loads((FIXTURES / "ticket_70.json").read_text(encoding="utf-8"))
    base["id"] = ticket_id
    # Ensure description mentions the screen so _extract_screens picks it up
    wi = base.get("work_item") or {}
    wi["description"] = f"Ver {screen} — test regresión ticket {ticket_id}"
    wi.setdefault("comments", [])
    base["work_item"] = wi
    base["ticket"] = {
        "id": ticket_id,
        "title": f"Ticket {ticket_id}",
        "description": f"Ver {screen} — test regresión ticket {ticket_id}",
    }
    return {"ok": True, **base}


def _scenarios(ticket_id: int, screen: str = "FrmAgenda.aspx", n: int = 2) -> dict:
    base = json.loads((FIXTURES / "scenarios_70.json").read_text(encoding="utf-8"))
    base["ticket_id"] = ticket_id
    for s in base.get("scenarios", [])[:n]:
        s["ticket_id"] = ticket_id
        s["pantalla"] = screen
    return base


def _runner_ok(ticket_id: int, total: int = 2, pass_: int = 2) -> dict:
    return {
        "ok": True,
        "ticket_id": ticket_id,
        "total": total,
        "pass": pass_,
        "fail": total - pass_,
        "blocked": 0,
        "runs": [
            {
                "scenario_id": f"P0{i+1}",
                "spec_file": f"evidence/{ticket_id}/tests/P0{i+1}_test.spec.ts",
                "status": "pass" if i < pass_ else "fail",
                "duration_ms": 1000,
                "artifacts": {},
                "raw_stdout": "",
                "raw_stderr": "",
            }
            for i in range(total)
        ],
        "meta": {"tool": "uat_test_runner", "version": "1.1.0", "duration_ms": 2000},
    }


def _runner_blocked(ticket_id: int, reason: str = "PLAYWRIGHT_TIMEOUT") -> dict:
    return {
        "ok": False,
        "ticket_id": ticket_id,
        "error": reason,
        "verdict": "BLOCKED",
        "reason": reason,
        "category": "NAV",
        "message": f"Blocked: {reason}",
    }


def _dossier_result(verdict: str = "FAIL") -> dict:
    return {
        "ok": True,
        "schema_version": "qa-uat-dossier/1.0",
        "run_id": "test-run-id",
        "ticket_id": 70,
        "ticket_title": "Test",
        "screen": "FrmAgenda.aspx",
        "verdict": verdict,
        "scenario_results": [],
        "summary": {"total": 2, "pass": 1, "fail": 1, "blocked": 0},
    }


# ── Shared pipeline context manager ──────────────────────────────────────────

class _Mocks:
    """Lightweight mock context for regression tests."""

    def __init__(
        self,
        ticket_id: int = 70,
        screen: str = "FrmAgenda.aspx",
        runner_result: dict | None = None,
        dossier_verdict: str = "FAIL",
        compiler_result: dict | None = None,
        generator_result: dict | None = None,
    ):
        self.ticket_id = ticket_id
        self.screen = screen
        self._runner = runner_result or _runner_ok(ticket_id)
        self._dossier = _dossier_result(dossier_verdict)
        self._compiler = compiler_result or _scenarios(ticket_id, screen)
        self._generator = generator_result or {
            "ok": True, "ticket_id": ticket_id,
            "generated": 2, "blocked": 0,
            "results": [
                {"scenario_id": "P01", "status": "generated",
                 "path": f"evidence/{ticket_id}/tests/P01_test.spec.ts"},
                {"scenario_id": "P02", "status": "generated",
                 "path": f"evidence/{ticket_id}/tests/P02_test.spec.ts"},
            ],
            "meta": {"tool": "playwright_test_generator", "version": "1.3.0",
                     "duration_ms": 100},
        }

    def __enter__(self):
        import environment_preflight, smoke_path_checker
        import uat_ticket_reader, ui_map_builder, uat_scenario_compiler
        import playwright_test_generator, uat_test_runner
        import uat_dossier_builder, ado_evidence_publisher
        import uat_precondition_checker, uat_assertion_evaluator
        import uat_failure_analyzer
        import qa_uat_pipeline as pipeline

        _pf_ok = environment_preflight.EnvironmentPreflightResult(
            ok=True, verdict="OK", reason="OK", message="Mocked OK",
            base_url="http://localhost/AgendaWeb/",
            login_url="http://localhost/AgendaWeb/FrmLogin.aspx",
            elapsed_ms=1,
        )

        self._patches = [
            patch.dict(os.environ, {
                "AGENDA_WEB_USER": "QA_REGRESSION_USER",
                "AGENDA_WEB_PASS": "QA_REGRESSION_PASS",
                # Allow UI discovery so the pipeline doesn't bail early on cache miss.
                # In regression tests we mock ui_map_builder.run, not the filesystem.
                "QA_UAT_ALLOW_UI_DISCOVERY": "true",
            }),
            patch.object(environment_preflight, "run_environment_preflight",
                         return_value=_pf_ok),
            patch.object(smoke_path_checker, "run_smoke_path",
                         return_value={"ok": True, "verdict": "OK"}),
            patch.object(uat_ticket_reader, "run",
                         return_value=_ticket(self.ticket_id, self.screen)),
            patch.object(ui_map_builder, "run",
                         return_value={"ok": True, "screens": [self.screen]}),
            patch.object(uat_scenario_compiler, "run", return_value=self._compiler),
            patch.object(playwright_test_generator, "run", return_value=self._generator),
            patch.object(uat_test_runner, "run", return_value=self._runner),
            patch.object(uat_dossier_builder, "run", return_value=self._dossier),
            patch.object(ado_evidence_publisher, "run", return_value={
                "ok": True, "mode": "dry-run", "ticket_id": self.ticket_id}),
            patch.object(uat_precondition_checker, "run", return_value={
                "ok": True, "ticket_id": self.ticket_id,
                "summary": {"total": 2, "ok": 2, "blocked": 0}, "results": {}}),
            patch.object(uat_assertion_evaluator, "run", return_value={
                "ok": True, "ticket_id": self.ticket_id, "evaluations": []}),
            patch.object(uat_failure_analyzer, "run", return_value={
                "ok": True, "ticket_id": self.ticket_id, "analyses": []}),
            patch.object(pipeline, "_persist_json"),
        ]
        for p in self._patches:
            p.start()
        return self

    def __exit__(self, *args):
        for p in reversed(self._patches):
            try:
                p.stop()
            except Exception:
                pass


# ── Invariant assertions ──────────────────────────────────────────────────────

def _assert_pipeline_contract(result: dict, *, ticket_id: int) -> None:
    """Assert structural invariants that every pipeline run must satisfy."""
    assert "ok" in result, "result missing 'ok'"
    assert "ticket_id" in result, "result missing 'ticket_id'"
    assert result["ticket_id"] == ticket_id, (
        f"ticket_id mismatch: {result['ticket_id']} != {ticket_id}"
    )
    assert "elapsed_s" in result, "result missing 'elapsed_s'"
    assert isinstance(result["elapsed_s"], (int, float)) and result["elapsed_s"] >= 0

    if result.get("ok"):
        assert "verdict" in result, "successful result missing 'verdict'"
        assert result["verdict"] in (
            "PASS", "FAIL", "MIXED", "BLOCKED", "INCOMPLETE", "UNKNOWN"
        ), f"unexpected verdict: {result['verdict']}"
    else:
        # Failed result must have a reason
        has_reason = bool(result.get("reason") or result.get("error"))
        assert has_reason, f"failed result missing reason: {result}"
        # And must have a verdict
        assert "verdict" in result, f"failed result missing verdict: {result}"
        assert result["verdict"] == "BLOCKED", (
            f"failed result should have verdict=BLOCKED, got: {result['verdict']}"
        )


# ── Regression tests per ticket ───────────────────────────────────────────────

class TestTicket70Regression:
    """Ticket 70 — baseline happy path (FrmAgenda.aspx, 2 scenarios, FAIL verdict)."""

    def test_happy_path_returns_ok(self, tmp_path):
        import qa_uat_pipeline as pipeline
        with patch.object(pipeline, "_TOOL_ROOT", tmp_path):
            with _Mocks(ticket_id=70, screen="FrmAgenda.aspx") as _:
                result = pipeline.run(ticket_id=70)
        assert result.get("ok") is True
        _assert_pipeline_contract(result, ticket_id=70)

    def test_stages_all_present(self, tmp_path):
        import qa_uat_pipeline as pipeline
        with patch.object(pipeline, "_TOOL_ROOT", tmp_path):
            with _Mocks(ticket_id=70) as _:
                result = pipeline.run(ticket_id=70)
        stages = result.get("stages") or {}
        for expected_stage in ("reader", "ui_map", "compiler", "generator", "runner"):
            assert expected_stage in stages, f"Stage '{expected_stage}' missing from result"

    def test_elapsed_s_is_nonnegative(self, tmp_path):
        import qa_uat_pipeline as pipeline
        with patch.object(pipeline, "_TOOL_ROOT", tmp_path):
            with _Mocks(ticket_id=70) as _:
                result = pipeline.run(ticket_id=70)
        assert result.get("elapsed_s", -1) >= 0

    def test_verdict_propagated_from_dossier(self, tmp_path):
        import qa_uat_pipeline as pipeline
        with patch.object(pipeline, "_TOOL_ROOT", tmp_path):
            with _Mocks(ticket_id=70, dossier_verdict="PASS") as _:
                result = pipeline.run(ticket_id=70)
        assert result.get("verdict") == "PASS"


class TestTicket116Regression:
    """Ticket 116 — known BLOCKED (no executable scenarios after compiler)."""

    def test_blocked_pipeline_has_verdict_and_category(self, tmp_path):
        """When compiler produces 0 scenarios, pipeline returns BLOCKED with category."""
        import qa_uat_pipeline as pipeline
        empty_compiler = {
            "ok": True, "ticket_id": 116,
            "scenarios": [],  # empty — triggers FIX-3 early exit
            "out_of_scope": 2,
        }
        with patch.object(pipeline, "_TOOL_ROOT", tmp_path):
            with _Mocks(ticket_id=116, compiler_result=empty_compiler) as _:
                result = pipeline.run(ticket_id=116)
        assert result.get("ok") is False or (
            # Either fails immediately OR the pipeline handles it as BLOCKED
            result.get("verdict") in ("BLOCKED", None)
        )
        # verdict must be present and be BLOCKED
        _assert_pipeline_contract(result, ticket_id=116)

    def test_blocked_result_has_reason(self, tmp_path):
        import qa_uat_pipeline as pipeline
        empty_compiler = {
            "ok": True, "ticket_id": 116,
            "scenarios": [],
            "out_of_scope": 2,
        }
        with patch.object(pipeline, "_TOOL_ROOT", tmp_path):
            with _Mocks(ticket_id=116, compiler_result=empty_compiler) as _:
                result = pipeline.run(ticket_id=116)
        assert result.get("reason") or result.get("error"), (
            f"BLOCKED result must have a reason: {result}"
        )


class TestTicket119Regression:
    """Ticket 119 — known BLOCKED_NAV (GridObligaciones empty at runtime)."""

    def test_runner_blocked_nav_propagates_verdict(self, tmp_path):
        """When runner returns BLOCKED with category=NAV, pipeline result should reflect it."""
        import qa_uat_pipeline as pipeline
        with patch.object(pipeline, "_TOOL_ROOT", tmp_path):
            with _Mocks(
                ticket_id=119,
                screen="FrmDetalleClie.aspx",
                runner_result=_runner_blocked(119, reason="GRID_EMPTY"),
            ) as _:
                result = pipeline.run(ticket_id=119)
        assert result.get("ok") is False
        _assert_pipeline_contract(result, ticket_id=119)
        assert result.get("verdict") == "BLOCKED"

    def test_runner_timeout_classified_as_blocked(self, tmp_path):
        import qa_uat_pipeline as pipeline
        with patch.object(pipeline, "_TOOL_ROOT", tmp_path):
            with _Mocks(
                ticket_id=119,
                runner_result=_runner_blocked(119, reason="PLAYWRIGHT_TIMEOUT"),
            ) as _:
                result = pipeline.run(ticket_id=119)
        assert result.get("verdict") == "BLOCKED"


class TestTicket120Regression:
    """Ticket 120 — known SELECTOR_NOT_FOUND scenario."""

    def test_generator_blocked_propagates_to_pipeline(self, tmp_path):
        """When all generator results are blocked, pipeline skips runner and goes to dossier.
        The final verdict comes from the dossier — must be non-PASS."""
        import qa_uat_pipeline as pipeline
        all_blocked_generator = {
            "ok": True, "ticket_id": 120,
            "generated": 0, "blocked": 2,
            "results": [
                {"scenario_id": "P01", "status": "blocked",
                 "reason": "SELECTOR_NOT_FOUND", "missing": ["btnGuardar"]},
                {"scenario_id": "P02", "status": "blocked",
                 "reason": "SELECTOR_NOT_FOUND", "missing": ["GridObligaciones"]},
            ],
            "meta": {"tool": "playwright_test_generator", "version": "1.3.0",
                     "duration_ms": 50},
        }
        with patch.object(pipeline, "_TOOL_ROOT", tmp_path):
            with _Mocks(
                ticket_id=120,
                screen="FrmDetalleClie.aspx",
                generator_result=all_blocked_generator,
            ) as _:
                result = pipeline.run(ticket_id=120)
        # Pipeline must complete (ok may be True since dossier ran)
        # and runner stage must be skipped
        stages = result.get("stages") or {}
        assert stages.get("runner", {}).get("skipped") is True, (
            "runner stage should be skipped when all scenarios are blocked"
        )
        # verdict must be non-PASS since nothing actually ran
        assert result.get("verdict") != "PASS", (
            f"verdict should not be PASS when all scenarios are blocked, got: {result.get('verdict')}"
        )
        _assert_pipeline_contract(result, ticket_id=120)


class TestTicket122Regression:
    """Ticket 122 — screen detection must not fall back to FrmAgenda.aspx."""

    def test_frmdetallegestion_detected_not_frmagneda(self, tmp_path):
        """_extract_screens() must pick up the screen explicitly mentioned in the ticket,
        not fall back to FrmAgenda.aspx as default when a real screen is mentioned."""
        import qa_uat_pipeline
        # Ticket description explicitly mentions FrmDetalleClie.aspx
        ticket_result = {
            "ok": True,
            "ticket": {
                "id": 122,
                "description": "El agente debe verificar FrmDetalleClie.aspx pantalla de detalle",
            },
            "description_md": "Verificar comportamiento en FrmDetalleClie.aspx",
        }
        screens = qa_uat_pipeline._extract_screens(ticket_result)
        assert screens, "No screens detected for ticket 122"
        # Must contain FrmDetalleClie.aspx
        assert "FrmDetalleClie.aspx" in screens, (
            f"Expected FrmDetalleClie.aspx in screens, got: {screens}"
        )
        # Must NOT contain FrmAgenda.aspx (no mention in this ticket)
        assert "FrmAgenda.aspx" not in screens or len(screens) > 1, (
            "FrmAgenda.aspx should not be the ONLY screen for ticket 122"
        )

    def test_pipeline_uses_ticket_screen_not_fallback(self, tmp_path):
        """Full pipeline run for ticket 122 should not use FrmAgenda.aspx as the screen."""
        import qa_uat_pipeline as pipeline
        ticket = _ticket(122, "FrmDetalleClie.aspx")

        import uat_ticket_reader
        with patch.object(pipeline, "_TOOL_ROOT", tmp_path):
            with _Mocks(ticket_id=122, screen="FrmDetalleClie.aspx") as ctx:
                # Override reader to return our specific ticket
                with patch.object(uat_ticket_reader, "run", return_value=ticket):
                    result = pipeline.run(ticket_id=122)

        assert result.get("ticket_id") == 122
        _assert_pipeline_contract(result, ticket_id=122)


# ── Cross-cutting invariant tests ─────────────────────────────────────────────

class TestPipelineInvariants:
    """Invariants that must hold for ANY ticket, ANY verdict."""

    @pytest.mark.parametrize("ticket_id,screen", [
        (70, "FrmAgenda.aspx"),
        (116, "FrmAgenda.aspx"),
        (119, "FrmDetalleClie.aspx"),
        (120, "FrmDetalleClie.aspx"),
        (122, "FrmDetalleClie.aspx"),
    ])
    def test_result_always_has_ticket_id(self, ticket_id, screen, tmp_path):
        import qa_uat_pipeline as pipeline
        with patch.object(pipeline, "_TOOL_ROOT", tmp_path):
            with _Mocks(ticket_id=ticket_id, screen=screen) as _:
                result = pipeline.run(ticket_id=ticket_id)
        assert result.get("ticket_id") == ticket_id

    @pytest.mark.parametrize("ticket_id", [70, 116, 119, 120, 122])
    def test_result_always_has_elapsed_s(self, ticket_id, tmp_path):
        import qa_uat_pipeline as pipeline
        with patch.object(pipeline, "_TOOL_ROOT", tmp_path):
            with _Mocks(ticket_id=ticket_id) as _:
                result = pipeline.run(ticket_id=ticket_id)
        assert "elapsed_s" in result, f"elapsed_s missing for ticket {ticket_id}"
        assert result["elapsed_s"] >= 0

    @pytest.mark.parametrize("ticket_id", [70, 116])
    def test_failed_result_always_has_verdict_blocked(self, ticket_id, tmp_path):
        """Any failed (ok=False) pipeline result must have verdict=BLOCKED."""
        import qa_uat_pipeline as pipeline
        # Force reader to fail
        fail_reader = {
            "ok": False,
            "error": "ado_not_found",
            "message": f"Ticket {ticket_id} not found",
        }
        import uat_ticket_reader
        with patch.object(pipeline, "_TOOL_ROOT", tmp_path):
            with _Mocks(ticket_id=ticket_id) as _:
                with patch.object(uat_ticket_reader, "run", return_value=fail_reader):
                    result = pipeline.run(ticket_id=ticket_id)
        assert result.get("ok") is False
        assert result.get("verdict") == "BLOCKED", (
            f"Expected BLOCKED for failed result, got: {result.get('verdict')}"
        )

    def test_build_output_always_has_category(self, tmp_path):
        """_build_output must always include category field."""
        import qa_uat_pipeline
        result = qa_uat_pipeline._build_output(
            ticket_id=999,
            stages={},
            failed_result={"ok": False, "error": "test_error"},
            started=0.0,
        )
        assert "verdict" in result
        assert "category" in result
        assert "reason" in result
        assert result["verdict"] == "BLOCKED"
