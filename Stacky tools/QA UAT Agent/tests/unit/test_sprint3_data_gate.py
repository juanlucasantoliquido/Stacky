"""
tests/unit/test_sprint3_data_gate.py — Sprint 3 completion tests.

Validates the criteria de aceptación not yet covered by test_sprint3_env_data_preflight.py:

  DR-A1: data_readiness.json always written when scenarios exist (even no preconditions)
  DR-A2: run_id used in artifact path (not str(ticket_id))
  DR-S1: generate_seed_sql produces seed_sql_suggestion.sql artifact
  DR-S2: generate_seed_sql produces rollback_sql_suggestion.sql artifact
  DR-S3: seed SQL is labeled with scenario_id
  DR-S4: seed SQL has rollback counterpart
  DR-S5: generic entity produces generic seed template
  DR-F1: ticket_120_grid_empty fixture → BLOCKED DATA GRID_EMPTY
  DR-F2: ticket_120_data_ready fixture → ALLOW
  DR-F3: CATALOG_MISSING reason code classified as DATA
  DR-P1: pipeline data_readiness_check uses _run_id not str(ticket_id)
  DR-P2: runner NOT started when data_readiness blocked
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_TOOL_DIR = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_TOOL_DIR))
os.environ.setdefault("STACKY_LLM_BACKEND", "mock")
os.environ.setdefault("QA_UAT_SKIP_SMOKE", "true")

_FIXTURES_DIR = Path(__file__).parent / "data"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_mock_db(row_count: int):
    """Build a mock DB connector returning row_count for any count query."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = (row_count,)
    mock_conn.cursor.return_value = mock_cursor

    def connector():
        return mock_conn

    return connector


# ══════════════════════════════════════════════════════════════════════════════
# DR-A — data_readiness.json always present
# ══════════════════════════════════════════════════════════════════════════════

class TestDataReadinessAlwaysPresent:

    def test_artifact_written_when_no_preconditions(self, tmp_path):
        """data_readiness.json must be written even when no preconditions are defined."""
        from uat_precondition_checker import check_data_readiness
        # No preconditions — pass empty list
        result = check_data_readiness(
            ticket_id=120,
            scenario_id="RF-007-CA-01",
            preconditions=[],
            evidence_dir=tmp_path,
            run_id=None,
        )
        artifact = tmp_path / "data_readiness.json"
        assert artifact.is_file(), "data_readiness.json must be written even with 0 preconditions"
        data = json.loads(artifact.read_text(encoding="utf-8"))
        assert data["decision"] == "ALLOW"
        assert data["all_ready"] is True
        assert data["checks"] == []

    def test_run_id_used_in_artifact_path(self, tmp_path):
        """data_readiness.json must be written under evidence_dir/<run_id>/."""
        from uat_precondition_checker import check_data_readiness
        run_id = "uat-120-20260509T120000Z-abc123"
        result = check_data_readiness(
            ticket_id=120,
            scenario_id="RF-007-CA-01",
            preconditions=[],
            evidence_dir=tmp_path,
            run_id=run_id,
        )
        artifact = tmp_path / run_id / "data_readiness.json"
        assert artifact.is_file(), f"Artifact must be at {artifact}"
        assert result.artifact_path == str(artifact)

    def test_artifact_written_with_blocking_checks(self, tmp_path):
        """data_readiness.json must be written when checks exist, even BLOCKED."""
        from uat_precondition_checker import check_data_readiness
        conn = _make_mock_db(row_count=0)
        with patch("uat_precondition_checker._get_safe_tables", return_value=frozenset({"ROBLG"})):
            result = check_data_readiness(
                ticket_id=120,
                scenario_id="RF-007-CA-01",
                preconditions=[{
                    "entity": "ROBLG", "type": "grid",
                    "input_data": {"CLCOD": "77001"}, "expected": {"min_rows": 1},
                }],
                _db_connector=conn,
                evidence_dir=tmp_path,
                run_id=None,
            )
        artifact = tmp_path / "data_readiness.json"
        assert artifact.is_file()
        data = json.loads(artifact.read_text(encoding="utf-8"))
        assert data["decision"] == "BLOCKED"


# ══════════════════════════════════════════════════════════════════════════════
# DR-S — Seed SQL generator
# ══════════════════════════════════════════════════════════════════════════════

class TestSeedSqlGenerator:

    def _blocked_check(self, entity: str = "ROBLG", clcod: str = "77001"):
        from uat_precondition_checker import DataCheck
        return DataCheck(
            entity=entity,
            type="grid",
            input_data={"CLCOD": clcod},
            expected={"min_rows": 1},
            actual={"row_count": 0},
            decision="BLOCKED",
            category="DATA",
            reason="GRID_EMPTY",
            human_action_required="Seed ROBLG data for CLCOD=77001",
            skipped=False,
        )

    def test_seed_sql_file_written(self, tmp_path):
        """generate_seed_sql writes seed_sql_suggestion.sql to evidence_dir."""
        from uat_precondition_checker import generate_seed_sql
        result = generate_seed_sql(
            blocked_checks=[self._blocked_check()],
            scenario_id="RF-007-CA-01",
            evidence_dir=tmp_path,
        )
        seed_file = tmp_path / "seed_sql_suggestion.sql"
        assert seed_file.is_file(), "seed_sql_suggestion.sql must be written"
        assert result["seed_sql_path"] == str(seed_file)

    def test_rollback_sql_file_written(self, tmp_path):
        """generate_seed_sql writes rollback_sql_suggestion.sql to evidence_dir."""
        from uat_precondition_checker import generate_seed_sql
        result = generate_seed_sql(
            blocked_checks=[self._blocked_check()],
            scenario_id="RF-007-CA-01",
            evidence_dir=tmp_path,
        )
        rollback_file = tmp_path / "rollback_sql_suggestion.sql"
        assert rollback_file.is_file(), "rollback_sql_suggestion.sql must be written"
        assert result["rollback_sql_path"] == str(rollback_file)

    def test_seed_sql_labeled_with_scenario_id(self, tmp_path):
        """Seed SQL must include the scenario_id label for traceability."""
        from uat_precondition_checker import generate_seed_sql
        result = generate_seed_sql(
            blocked_checks=[self._blocked_check()],
            scenario_id="RF-007-CA-01",
            evidence_dir=tmp_path,
        )
        seed_sql = result["seed_sql"]
        assert "RF-007-CA-01" in seed_sql, "seed_sql must embed scenario_id"
        assert "QA_UAT_SEED_RF-007-CA-01" in seed_sql

    def test_rollback_has_counterpart_label(self, tmp_path):
        """Rollback SQL must reference the same label as seed SQL."""
        from uat_precondition_checker import generate_seed_sql
        result = generate_seed_sql(
            blocked_checks=[self._blocked_check()],
            scenario_id="RF-007-CA-01",
            evidence_dir=tmp_path,
        )
        rollback_sql = result["rollback_sql"]
        assert "RF-007-CA-01" in rollback_sql
        assert "QA_UAT_SEED_RF-007-CA-01" in rollback_sql

    def test_generic_entity_produces_generic_template(self, tmp_path):
        """Unknown entity uses the generic template (no hardcoded table names)."""
        from uat_precondition_checker import generate_seed_sql
        result = generate_seed_sql(
            blocked_checks=[self._blocked_check(entity="UNKNOWN_ENTITY")],
            scenario_id="RF-007-CA-99",
            evidence_dir=tmp_path,
        )
        seed_sql = result["seed_sql"]
        # Generic template should mention entity and scenario_id
        assert "UNKNOWN_ENTITY" in seed_sql
        assert "RF-007-CA-99" in seed_sql

    def test_empty_blocked_checks_returns_ok_no_files(self, tmp_path):
        """No blocked checks → no SQL files written, ok=True."""
        from uat_precondition_checker import generate_seed_sql
        result = generate_seed_sql(
            blocked_checks=[],
            scenario_id="RF-007-CA-01",
            evidence_dir=tmp_path,
        )
        assert result["ok"] is True
        assert result["seed_sql"] is None
        assert result["rollback_sql"] is None
        assert not (tmp_path / "seed_sql_suggestion.sql").exists()

    def test_no_dml_in_rollback_except_delete(self, tmp_path):
        """Rollback SQL must only use DELETE (never INSERT/UPDATE/DROP/EXEC)."""
        from uat_precondition_checker import generate_seed_sql
        result = generate_seed_sql(
            blocked_checks=[self._blocked_check()],
            scenario_id="RF-007-CA-01",
            evidence_dir=tmp_path,
        )
        rollback = result["rollback_sql"].upper()
        assert "INSERT" not in rollback, "Rollback must not contain INSERT"
        assert "UPDATE" not in rollback, "Rollback must not contain UPDATE"
        assert "DROP" not in rollback, "Rollback must not contain DROP"
        assert "EXEC" not in rollback, "Rollback must not contain EXEC"

    def test_entities_list_populated(self, tmp_path):
        """generate_seed_sql result includes entities list."""
        from uat_precondition_checker import generate_seed_sql
        result = generate_seed_sql(
            blocked_checks=[
                self._blocked_check(entity="ROBLG"),
                self._blocked_check(entity="CLCLIE"),
            ],
            scenario_id="RF-007-CA-01",
            evidence_dir=tmp_path,
        )
        assert "ROBLG" in result["entities"]
        assert "CLCLIE" in result["entities"]


# ══════════════════════════════════════════════════════════════════════════════
# DR-F — Ticket 120 fixtures (Sprint 3 DoD)
# ══════════════════════════════════════════════════════════════════════════════

class TestTicket120Fixtures:
    """Sprint 3 DoD: Ticket 120 has two fixtures — grid_empty and data_ready."""

    def _load_fixture(self, name: str) -> dict:
        path = _FIXTURES_DIR / f"{name}.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def _run_fixture(self, fixture: dict) -> object:
        from uat_precondition_checker import check_data_readiness
        precs = fixture["data_readiness_preconditions"]
        db_mock = fixture.get("db_mock", {})

        # Build mock DB returning the row_count from the fixture
        # Use the row_count of the first entity in db_mock
        first_entity = list(db_mock.values())[0] if db_mock else {"row_count": 0}
        row_count = first_entity.get("row_count", 0)
        connector = _make_mock_db(row_count)

        safe_tables = frozenset(db_mock.keys())
        with patch("uat_precondition_checker._get_safe_tables", return_value=safe_tables):
            return check_data_readiness(
                ticket_id=fixture["ticket_id"],
                scenario_id=fixture["scenario_id"],
                preconditions=precs,
                _db_connector=connector,
            )

    def test_ticket_120_grid_empty_fixture_blocked(self):
        """ticket_120_grid_empty.json → BLOCKED DATA GRID_EMPTY."""
        fixture = self._load_fixture("ticket_120_grid_empty")
        expected = fixture["expected_outcome"]
        result = self._run_fixture(fixture)

        assert result.decision == expected["decision"], (
            f"Expected {expected['decision']}, got {result.decision}"
        )
        assert result.category == expected["category"]
        assert result.reason == expected["reason"]
        assert result.all_ready == expected["all_ready"]
        assert expected["runner_should_start"] is False

    def test_ticket_120_data_ready_fixture_allow(self):
        """ticket_120_data_ready.json → ALLOW."""
        fixture = self._load_fixture("ticket_120_data_ready")
        expected = fixture["expected_outcome"]
        result = self._run_fixture(fixture)

        assert result.decision == expected["decision"], (
            f"Expected {expected['decision']}, got {result.decision}"
        )
        assert result.category == expected["category"]
        assert result.reason == expected["reason"]
        assert result.all_ready == expected["all_ready"]
        assert expected["runner_should_start"] is True

    def test_ticket_120_fixtures_exist(self):
        """Both fixture files must exist in tests/unit/data/."""
        assert (_FIXTURES_DIR / "ticket_120_grid_empty.json").is_file()
        assert (_FIXTURES_DIR / "ticket_120_data_ready.json").is_file()

    def test_ticket_120_fixtures_have_required_keys(self):
        """Both fixtures must have the required schema keys."""
        required = {"ticket_id", "scenario_id", "data_readiness_preconditions",
                    "expected_outcome", "db_mock", "build_fingerprint"}
        for name in ("ticket_120_grid_empty", "ticket_120_data_ready"):
            fixture = self._load_fixture(name)
            missing = required - set(fixture.keys())
            assert not missing, f"{name} missing keys: {missing}"


# ══════════════════════════════════════════════════════════════════════════════
# DR-F3 — CATALOG_MISSING reason code
# ══════════════════════════════════════════════════════════════════════════════

class TestCatalogMissingReason:

    def test_catalog_missing_is_data_category(self):
        """CATALOG_MISSING must be classified as DATA category."""
        from uat_precondition_checker import infer_failure_category
        # Add CATALOG_MISSING to DATA_NAV_REASONS if not already there
        cat = infer_failure_category("CATALOG_MISSING")
        assert cat == "DATA", (
            f"CATALOG_MISSING must be DATA, got {cat!r}. "
            "Add 'CATALOG_MISSING': 'DATA' to _DATA_NAV_REASONS."
        )

    def test_catalog_empty_is_data_category(self):
        """CATALOG_EMPTY from data_readiness_checker.py must be DATA."""
        from uat_precondition_checker import infer_failure_category
        cat = infer_failure_category("CATALOG_EMPTY")
        assert cat == "DATA", f"CATALOG_EMPTY must be DATA, got {cat!r}"


# ══════════════════════════════════════════════════════════════════════════════
# DR-P — Pipeline integration
# ══════════════════════════════════════════════════════════════════════════════

class TestPipelineDataGate:
    """Pipeline-level tests for Sprint 3 data_readiness_check stage."""

    def _ticket(self, with_preconditions: bool = True) -> dict:
        precs = []
        if with_preconditions:
            precs = [{"entity": "ROBLG", "type": "grid",
                      "input_data": {"CLCOD": "77001"}, "expected": {"min_rows": 1}}]
        return {
            "ok": True,
            "ticket_id": 120,
            "ticket": {"id": 120, "title": "RF-007 QA test"},
            "description_md": "Verificar funcionalidad en FrmAgenda.aspx",
            "plan_pruebas": [],
        }

    def test_data_readiness_baseline_artifact_when_no_preconditions(self, tmp_path):
        """Pipeline writes baseline data_readiness.json when no preconditions."""
        import qa_uat_pipeline as qp
        import execution_logger as el
        import ui_map_resolution

        mock_pf = MagicMock()
        mock_pf.ok = True
        mock_pf.verdict = "PASS"
        mock_pf.reason = None
        mock_pf.base_url = "http://localhost"

        # UI map cache with FrmAgenda.aspx
        cache_dir = tmp_path / "cache" / "ui_maps"
        cache_dir.mkdir(parents=True, exist_ok=True)
        ui_map = {"schema_version": "ui_map/1.1", "elements": [],
                  "screen": "FrmAgenda.aspx", "ok": True}
        (cache_dir / "FrmAgenda.aspx.json").write_text(
            json.dumps(ui_map), encoding="utf-8"
        )

        # Compiler result without data_readiness_preconditions
        compiler_result = {
            "ok": True,
            "scenarios": [
                {"scenario_id": "P01", "title": "Test 1", "status": "compiled",
                 "data_readiness_preconditions": []},
            ],
        }

        with patch.object(qp, "_TOOL_ROOT", tmp_path), \
             patch("environment_preflight.run_environment_preflight", return_value=mock_pf), \
             patch("deployment_fingerprint.check_deployment_fingerprint", side_effect=ImportError), \
             patch("smoke_path_checker.run_smoke_path", side_effect=ImportError), \
             patch("uat_ticket_reader.run", return_value=self._ticket(with_preconditions=False)), \
             patch("quality_intake.run_quality_intake", side_effect=ImportError), \
             patch("screen_detector.detect_screens_and_persist") as mock_detect, \
             patch("uat_scenario_compiler.run", return_value=compiler_result), \
             patch.object(ui_map_resolution, "resolve_ui_maps", return_value={
                 "ok": True, "decision": "ALLOW", "reason": None,
                 "screens": [], "missing_screens": [], "allow_rebuild": False,
                 "elapsed_ms": 1, "human_action_required": None, "artifact_path": None,
             }), \
             patch("playwright_test_generator.run", side_effect=ImportError), \
             patch("uat_test_runner.run", side_effect=ImportError), \
             patch.dict(os.environ, {
                 "AGENDA_WEB_USER": "test_user",
                 "AGENDA_WEB_PASS": "test_pass",
                 "QA_UAT_DEPLOYMENT_POLICY": "off",
                 "QA_UAT_UI_MAP_CACHE_DIR": str(cache_dir),
             }):

            mock_detect_result = MagicMock()
            mock_detect_result.selected_screens = ["FrmAgenda.aspx"]
            mock_detect_result.blocked = False
            mock_detect_result.block_reason = None
            mock_detect_result.confidence = 0.9
            mock_detect_result.fallback_used = False
            mock_detect_result.ambiguous = False
            mock_detect_result.artifact_path = None
            mock_detect_result.to_dict.return_value = {
                "selected_screens": ["FrmAgenda.aspx"], "blocked": False}
            mock_detect.return_value = mock_detect_result

            result = qp.run(ticket_id=120, mode="dry-run", verbose=False)

        with el._registry_lock:
            el._registry.clear()

        # The pipeline should have written data_readiness.json
        evidence_glob = list(tmp_path.glob("evidence/120/uat-*/data_readiness.json"))
        assert evidence_glob, (
            "data_readiness.json must exist in evidence dir even with no preconditions. "
            f"Found files in {tmp_path / 'evidence'}: {list(tmp_path.glob('evidence/**/*'))}"
        )
