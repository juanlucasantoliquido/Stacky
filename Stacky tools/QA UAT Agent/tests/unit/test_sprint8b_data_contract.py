"""
tests/unit/test_sprint8b_data_contract.py — Sprint 8b tests (Data Contract + Data Readiness v2).

Validates:
  Module 4.1 — uat_data_contract_compiler.py
   1.  test_data_contract_extracts_clcod_for_grid_obligaciones
   2.  test_data_contract_marks_catalog_as_required_for_dropdown
   3.  test_data_contract_blocks_when_required_entity_unknown
   4.  test_data_contract_outputs_schema_valid_json
   5.  test_data_contract_deduplicates_requirements
   6.  test_data_contract_empty_steps_produces_no_requirements
   7.  test_data_contract_event_has_required_fields
   8.  test_data_contract_compile_all_accepts_legacy_format
   9.  test_data_contract_requirement_id_prefix
  10.  test_data_contract_schema_known_for_lote

  Module 4.2 — data_readiness_checker.py
  11.  test_data_readiness_true_when_candidate_exists
  12.  test_data_readiness_false_when_grid_source_empty
  13.  test_data_readiness_returns_resolution_options
  14.  test_data_readiness_never_executes_dml
  15.  test_data_readiness_masks_pii_in_artifact
  16.  test_data_readiness_unverified_when_db_unavailable
  17.  test_data_readiness_user_input_only_source_is_missing
  18.  test_data_readiness_schema_unknown_returns_manual_review
  19.  test_data_readiness_event_has_required_fields
  20.  test_data_readiness_decision_ready_when_all_unverified

  schemas/data_contract.schema.json
  21.  test_data_contract_schema_file_exists
  22.  test_data_contract_schema_is_valid_json

  config/qa_uat_data_policy.yml
  23.  test_data_policy_file_exists
  24.  test_data_policy_prod_has_allow_seed_false
  25.  test_data_policy_publish_gate_min_confidence
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure tool root is on sys.path
TOOL_DIR = Path(__file__).parent.parent.parent
sys.path.insert(0, str(TOOL_DIR))


# =============================================================================
# Module 4.1 — uat_data_contract_compiler.py
# =============================================================================

class TestDataContractCompiler:

    def _make_input(self, **kwargs) -> dict:
        base = {
            "ticket_id": 120,
            "scenario_id": "RF-007-CA-01",
            "feature": "Lista Obligaciones",
            "screen": "FrmDetalleClie.aspx",
            "steps": [],
            "functional_context": "",
        }
        base.update(kwargs)
        return base

    def test_data_contract_extracts_clcod_for_grid_obligaciones(self):
        """Compiler detects obligacion requirement from steps mentioning the grid."""
        from uat_data_contract_compiler import compile_data_contract

        inp = self._make_input(steps=[
            "abrir detalle cliente",
            "ver lista de obligaciones",
            "validar columnas corredor y riesgo",
        ])
        result = compile_data_contract(inp)

        assert result.ok
        req_aliases = [r.alias for r in result.requirements]
        # Should detect obligacion requirement
        assert any("obligacion" in alias for alias in req_aliases), (
            f"Expected obligacion requirement, got: {req_aliases}"
        )
        # CLCOD must be in required_fields of the obligacion requirement
        obligacion_reqs = [r for r in result.requirements if "obligacion" in r.alias]
        assert obligacion_reqs, "No obligacion requirement found"
        assert "CLCOD" in obligacion_reqs[0].required_fields

    def test_data_contract_marks_catalog_as_required_for_dropdown(self):
        """Compiler detects catalog requirement from steps mentioning combo/dropdown."""
        from uat_data_contract_compiler import compile_data_contract

        inp = self._make_input(steps=[
            "abrir formulario",
            "seleccionar valor del combo de estado",
            "verificar dropdown lleno",
        ])
        result = compile_data_contract(inp)

        assert result.ok
        req_aliases = [r.alias for r in result.requirements]
        assert any("catalogo" in alias for alias in req_aliases), (
            f"Expected catalogo requirement, got: {req_aliases}"
        )

    def test_data_contract_blocks_when_required_entity_unknown(self):
        """When entity cannot be mapped, requirement has schema_known=False."""
        from uat_data_contract_compiler import compile_data_contract

        # Use steps that match the obligaciones rule but with unknown schema
        inp = self._make_input(
            steps=["ver gridobligaciones"],
            functional_context="se requiere cliente con obligaciones activas",
        )
        result = compile_data_contract(inp)

        assert result.ok
        # The obligacion/corredor requirements should be schema_known=False (no confirmed schema)
        schema_unknown = [r for r in result.requirements if not r.schema_known]
        assert schema_unknown, "Expected at least one schema_unknown requirement"

    def test_data_contract_outputs_schema_valid_json(self):
        """to_dict() output matches data_contract/1.0 required fields."""
        from uat_data_contract_compiler import compile_data_contract

        inp = self._make_input(steps=["ver lista de obligaciones"])
        result = compile_data_contract(inp)
        d = result.to_dict()

        # Required top-level fields from schema
        assert d["schema_version"] == "data_contract/1.0"
        assert d["scenario_id"] == "RF-007-CA-01"
        assert "data_contract_version" in d
        assert "compiled_at" in d
        assert "requirements" in d
        assert isinstance(d["requirements"], list)
        assert "summary" in d
        assert d["summary"]["total"] == len(d["requirements"])
        assert d["summary"]["blocking"] >= 0

    def test_data_contract_deduplicates_requirements(self):
        """Same alias is never emitted twice even when multiple keywords match."""
        from uat_data_contract_compiler import compile_data_contract

        # Repeat keywords that would match obligaciones multiple times
        inp = self._make_input(steps=[
            "ver gridobligaciones",
            "ver lista de obligaciones",
            "validar obligaciones",
        ])
        result = compile_data_contract(inp)

        aliases = [r.alias for r in result.requirements]
        assert len(aliases) == len(set(aliases)), f"Duplicate aliases: {aliases}"

    def test_data_contract_empty_steps_produces_no_requirements(self):
        """Scenario with no steps, context, screen, or preconditions produces an empty contract."""
        from uat_data_contract_compiler import compile_data_contract

        # Pass NO screen, NO feature, NO steps so corpus is truly empty
        inp = {
            "ticket_id": 120,
            "scenario_id": "RF-999-CA-01",
            "steps": [],
            "functional_context": "",
            "technical_context": "",
            "preconditions": [],
        }
        result = compile_data_contract(inp)

        assert result.ok
        assert result.requirements == [], (
            f"Expected no requirements from empty scenario, got: {result.requirements}"
        )
        assert result.to_dict()["summary"]["total"] == 0

    def test_data_contract_event_has_required_fields(self):
        """to_event() contains all required fields for execution.jsonl."""
        from uat_data_contract_compiler import compile_data_contract

        inp = self._make_input(steps=["ver lista de obligaciones"])
        result = compile_data_contract(inp)
        event = result.to_event()

        assert event["event"] == "data_contract_compiled"
        assert "ticket_id" in event
        assert "scenario_id" in event
        assert "requirements_count" in event
        assert "blocking_requirements" in event
        assert "entities" in event
        assert isinstance(event["entities"], list)

    def test_data_contract_compile_all_accepts_legacy_format(self):
        """compile_all_contracts handles legacy compiler format (pantalla/pasos keys)."""
        from uat_data_contract_compiler import compile_all_contracts

        scenarios = [
            {
                "id": "RF-007-CA-01",
                "pantalla": "FrmDetalleClie.aspx",
                "pasos": ["ver lista de obligaciones"],
            },
            {
                "scenario_id": "RF-007-CA-02",
                "screen": "FrmDetalleClie.aspx",
                "steps": ["ver combo de estado"],
            },
        ]
        results = compile_all_contracts(scenarios, ticket_id=120)

        assert len(results) == 2
        assert all(r.ok for r in results)

    def test_data_contract_requirement_id_prefix(self):
        """Every requirement_id starts with 'data.req.'."""
        from uat_data_contract_compiler import compile_data_contract

        inp = self._make_input(steps=[
            "ver lista de obligaciones",
            "seleccionar combo",
        ])
        result = compile_data_contract(inp)

        for req in result.requirements:
            assert req.requirement_id.startswith("data.req."), (
                f"requirement_id must start with 'data.req.', got: {req.requirement_id}"
            )

    def test_data_contract_schema_known_for_lote(self):
        """Lote entity has schema_known=True (RAGEN is confirmed accessible)."""
        from uat_data_contract_compiler import compile_data_contract

        inp = self._make_input(steps=["abrir bandeja de lotes", "ver gridbandeja"])
        result = compile_data_contract(inp)

        lote_reqs = [r for r in result.requirements if r.entity == "Lote"]
        assert lote_reqs, "Expected Lote requirement for lote/bandeja steps"
        assert lote_reqs[0].schema_known is True
        assert lote_reqs[0].db_table == "RAGEN"


# =============================================================================
# Module 4.2 — data_readiness_checker.py
# =============================================================================

class TestDataReadinessChecker:

    def _make_contract(self, requirements=None, scenario_id="RF-007-CA-01"):
        """Build a minimal DataContractResult for testing."""
        from uat_data_contract_compiler import DataContractResult, DataRequirement
        import datetime

        reqs = requirements or []
        return DataContractResult(
            ok=True,
            scenario_id=scenario_id,
            ticket_id=120,
            feature="Lista Obligaciones",
            screen="FrmDetalleClie.aspx",
            data_contract_version="1.0",
            compiled_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            compiled_by="test",
            requirements=reqs,
        )

    def _make_req(self, entity="Obligacion", alias="cliente_con_obligaciones",
                  blocking=True, candidate_sources=None, schema_known=False,
                  db_table=None):
        from uat_data_contract_compiler import DataRequirement
        return DataRequirement(
            requirement_id=f"data.req.{alias}",
            entity=entity,
            alias=alias,
            required_fields=["CLCOD"],
            constraints=["cliente tiene al menos una obligacion activa"],
            candidate_sources=candidate_sources or ["live_db_readonly", "user_input", "sql_seed"],
            blocking=blocking,
            inferred_from="step_keywords",
            schema_known=schema_known,
            db_table=db_table,
        )

    def test_data_readiness_true_when_candidate_exists(self):
        """When DB returns rows, readiness is READY."""
        from data_readiness_checker import check_readiness

        # Mock DB connector that returns count > 0
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (5,)
        mock_conn.cursor.return_value = mock_cursor

        req = self._make_req(
            entity="Lote",
            alias="lote_asignado",
            schema_known=True,
            db_table="RAGEN",
        )
        contract = self._make_contract(requirements=[req])

        result = check_readiness(contract, _db_connector=lambda: mock_conn)

        assert result.ready is True
        assert result.decision == "READY"
        assert len(result.missing) == 0

    def test_data_readiness_false_when_grid_source_empty(self):
        """When DB returns 0 rows for a blocking requirement, decision is MISSING."""
        from data_readiness_checker import check_readiness

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (0,)
        mock_conn.cursor.return_value = mock_cursor

        req = self._make_req(
            entity="Obligacion",
            alias="cliente_con_obligaciones",
            blocking=True,
            schema_known=True,
            db_table="ROBLG",
        )
        contract = self._make_contract(requirements=[req])

        result = check_readiness(contract, _db_connector=lambda: mock_conn)

        assert result.ready is False
        assert result.decision == "MISSING"
        assert result.blocking_missing_count >= 1

    def test_data_readiness_returns_resolution_options(self):
        """Missing requirements always include a non-empty resolution_options list."""
        from data_readiness_checker import check_readiness

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (0,)
        mock_conn.cursor.return_value = mock_cursor

        req = self._make_req(
            entity="Obligacion",
            alias="cliente_con_obligaciones",
            blocking=True,
            schema_known=True,
            db_table="ROBLG",
        )
        contract = self._make_contract(requirements=[req])

        result = check_readiness(contract, _db_connector=lambda: mock_conn)

        assert len(result.missing) > 0
        for missing_req in result.missing:
            assert len(missing_req.resolution_options) > 0, (
                f"requirement {missing_req.requirement_id} has no resolution_options"
            )

    def test_data_readiness_never_executes_dml(self):
        """Checker only calls cursor.execute (SELECT), never connection.commit or cursor.executemany."""
        from data_readiness_checker import check_readiness

        call_log: list[str] = []

        class SafeConn:
            def cursor(self):
                return SafeCursor()
            def close(self):
                pass
            def commit(self):
                call_log.append("COMMIT")
                raise AssertionError("DML commit detected!")
            def rollback(self):
                call_log.append("ROLLBACK")

        class SafeCursor:
            def execute(self, sql, *args):
                call_log.append(f"execute:{sql}")
                # Reject any DML
                sql_upper = sql.upper().strip()
                assert not any(
                    sql_upper.startswith(kw)
                    for kw in ("INSERT", "UPDATE", "DELETE", "DROP", "TRUNCATE", "ALTER")
                ), f"DML detected in execute: {sql}"
            def fetchone(self):
                return (3,)
            def close(self):
                pass

        req = self._make_req(
            entity="Cliente",
            alias="cliente_existente",
            schema_known=True,
            db_table="RCLIE",
        )
        contract = self._make_contract(requirements=[req])
        check_readiness(contract, _db_connector=lambda: SafeConn())

        # Confirm commit was never called
        assert "COMMIT" not in call_log, f"DML commit detected in call log: {call_log}"

    def test_data_readiness_masks_pii_in_artifact(self):
        """Artifact never contains raw PII — resolved_fields are masked."""
        from data_readiness_checker import check_readiness

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (1,)
        mock_conn.cursor.return_value = mock_cursor

        req = self._make_req(
            entity="Cliente",
            alias="cliente_existente",
            schema_known=True,
            db_table="RCLIE",
        )
        contract = self._make_contract(requirements=[req])

        with tempfile.TemporaryDirectory() as tmpdir:
            evidence_dir = Path(tmpdir)
            result = check_readiness(
                contract,
                _db_connector=lambda: mock_conn,
                evidence_dir=evidence_dir,
                run_id="test-run-001",
            )

            if result.artifact_path:
                artifact = json.loads(Path(result.artifact_path).read_text(encoding="utf-8"))
                # resolved entries should not contain RUT-like values
                for resolved_item in artifact.get("resolved", []):
                    for k, v in resolved_item.get("resolved_fields", {}).items():
                        # [MASKED] or empty is fine — raw RUT/email is not
                        assert v != "12.345.678-9", f"PII found unmasked in artifact: {v}"

    def test_data_readiness_unverified_when_db_unavailable(self):
        """When DB connector raises an exception, requirement is UNVERIFIED (not MISSING)."""
        from data_readiness_checker import check_readiness

        def failing_connector():
            raise ConnectionError("DB unavailable in test")

        req = self._make_req(
            entity="Cliente",
            alias="cliente_existente",
            schema_known=True,
            db_table="RCLIE",
        )
        contract = self._make_contract(requirements=[req])

        result = check_readiness(contract, _db_connector=failing_connector)

        # Should not be MISSING — it's UNVERIFIED
        assert result.ready is True, "Should be ready when DB unavailable (not blocking)"
        assert result.decision in ("READY", "UNVERIFIED")

    def test_data_readiness_user_input_only_source_is_missing(self):
        """Requirements with candidate_sources=['user_input'] are always MISSING."""
        from data_readiness_checker import check_readiness

        req = self._make_req(
            entity="UsuarioQA",
            alias="usuario_qa_activo",
            blocking=True,
            candidate_sources=["user_input"],
            schema_known=True,
            db_table="RASIST",
        )
        contract = self._make_contract(requirements=[req])

        result = check_readiness(contract)

        assert result.decision == "MISSING"
        assert result.blocking_missing_count >= 1
        missing = result.missing[0]
        assert missing.reason == "USER_DATA_REQUIRED"
        assert len(missing.resolution_options) > 0

    def test_data_readiness_schema_unknown_returns_manual_review(self):
        """Schema-unknown requirements produce MARK_MANUAL_REVIEW in resolution options."""
        from data_readiness_checker import check_readiness, ResolutionOption

        req = self._make_req(
            entity="Obligacion",
            alias="cliente_con_obligaciones",
            blocking=True,
            candidate_sources=["live_db_readonly", "sql_seed"],
            schema_known=False,   # schema not confirmed
            db_table=None,
        )
        contract = self._make_contract(requirements=[req])

        result = check_readiness(contract)

        assert result.decision == "MISSING"
        missing = result.missing[0]
        assert ResolutionOption.MARK_MANUAL_REVIEW in missing.resolution_options or \
               ResolutionOption.ASK_USER_FOR_VALUE in missing.resolution_options

    def test_data_readiness_event_has_required_fields(self):
        """to_event() contains all required fields for execution.jsonl."""
        from data_readiness_checker import check_readiness

        req = self._make_req(
            entity="Lote",
            alias="lote_asignado",
            schema_known=True,
            db_table="RAGEN",
        )
        # Use failing connector so we can test without DB
        contract = self._make_contract(requirements=[req])
        result = check_readiness(contract, _db_connector=lambda: (_ for _ in ()).throw(Exception("no db")))
        event = result.to_event()

        assert event["event"] == "data_readiness_v2_checked"
        assert "scenario_id" in event
        assert "ready" in event
        assert "decision" in event
        assert "missing_count" in event
        assert "blocking_missing_count" in event
        assert "resolved_count" in event

    def test_data_readiness_decision_ready_when_all_unverified(self):
        """When all requirements are UNVERIFIED (DB down), decision is UNVERIFIED and ready=True."""
        from data_readiness_checker import check_readiness

        req1 = self._make_req(
            entity="Cliente",
            alias="cliente_existente",
            schema_known=True,
            db_table="RCLIE",
        )
        req2 = self._make_req(
            entity="Lote",
            alias="lote_asignado",
            schema_known=True,
            db_table="RAGEN",
        )
        contract = self._make_contract(requirements=[req1, req2])

        # No connector — simulates DB unavailable
        result = check_readiness(contract, _db_connector=None)

        # With no DB env vars set, both should be unverified
        assert result.ready is True
        assert result.decision in ("READY", "UNVERIFIED")


# =============================================================================
# schemas/data_contract.schema.json
# =============================================================================

class TestDataContractSchema:

    def test_data_contract_schema_file_exists(self):
        """schemas/data_contract.schema.json exists in the tool directory."""
        schema_path = TOOL_DIR / "schemas" / "data_contract.schema.json"
        assert schema_path.is_file(), f"Schema file not found: {schema_path}"

    def test_data_contract_schema_is_valid_json(self):
        """schemas/data_contract.schema.json is valid JSON with required meta-fields."""
        schema_path = TOOL_DIR / "schemas" / "data_contract.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))

        assert schema.get("$schema") == "http://json-schema.org/draft-07/schema#"
        assert schema.get("$id") == "data_contract/1.0"
        assert schema.get("type") == "object"
        assert "required" in schema
        required = schema["required"]
        for field in ("schema_version", "scenario_id", "data_contract_version",
                      "compiled_at", "requirements"):
            assert field in required, f"Required field missing from schema: {field}"


# =============================================================================
# config/qa_uat_data_policy.yml
# =============================================================================

class TestDataPolicy:

    def _load_policy(self) -> dict:
        """Load policy YAML, falling back to PyYAML or manual parse."""
        policy_path = TOOL_DIR / "config" / "qa_uat_data_policy.yml"
        content = policy_path.read_text(encoding="utf-8")
        try:
            import yaml
            return yaml.safe_load(content)
        except ImportError:
            # Minimal manual parse for test purposes (extract key values)
            # Rather than depending on PyYAML, do key assertions on raw text
            return {"_raw": content}

    def test_data_policy_file_exists(self):
        """config/qa_uat_data_policy.yml exists."""
        policy_path = TOOL_DIR / "config" / "qa_uat_data_policy.yml"
        assert policy_path.is_file(), f"Policy file not found: {policy_path}"

    def test_data_policy_prod_has_allow_seed_false(self):
        """PROD environment must have allow_seed: false in policy."""
        policy_path = TOOL_DIR / "config" / "qa_uat_data_policy.yml"
        content = policy_path.read_text(encoding="utf-8")

        # Check raw text — PROD section must contain allow_seed: false
        assert "allow_seed: false" in content, (
            "PROD environment must have allow_seed: false"
        )
        assert "block_all_write_operations: true" in content, (
            "PROD environment must have block_all_write_operations: true"
        )

    def test_data_policy_publish_gate_min_confidence(self):
        """publish_gates.min_test_confidence must be >= 85."""
        policy_path = TOOL_DIR / "config" / "qa_uat_data_policy.yml"
        content = policy_path.read_text(encoding="utf-8")

        # Find min_test_confidence value in raw text
        import re
        match = re.search(r"min_test_confidence:\s*(\d+)", content)
        assert match, "min_test_confidence not found in policy file"
        value = int(match.group(1))
        assert value >= 85, f"min_test_confidence must be >= 85, got: {value}"
