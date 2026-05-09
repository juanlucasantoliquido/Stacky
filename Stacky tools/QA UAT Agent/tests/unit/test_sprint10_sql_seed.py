"""
tests/unit/test_sprint10_sql_seed.py — Sprint 10 tests.

Tests:
  sql_safety_validator.py
    1.  test_validator_accepts_valid_seed_script
    2.  test_validator_blocks_drop
    3.  test_validator_blocks_truncate
    4.  test_validator_blocks_active_commit
    5.  test_validator_blocks_missing_rollback
    6.  test_validator_blocks_missing_begin_transaction
    7.  test_validator_blocks_missing_seed_run_id
    8.  test_validator_blocks_missing_verification_select
    9.  test_validator_blocks_delete_without_seed_marker
    10. test_validator_blocks_alter
    11. test_validator_commented_commit_is_allowed
    12. test_validator_safe_result_always_requires_human_approval

  sql_seed_generator.py
    13. test_generator_blocked_when_no_schema
    14. test_generator_produces_scripts_with_schema_mapping
    15. test_generator_script_contains_rollback
    16. test_generator_script_contains_begin_transaction
    17. test_generator_script_contains_seed_run_id
    18. test_generator_script_contains_anti_prod_guard
    19. test_generator_script_contains_verification_select
    20. test_generator_script_passes_safety_validator
    21. test_generator_writes_evidence_files
    22. test_generator_cleanup_script_has_rollback

  GET /api/qa-uat/seed-proposal (Flask)
    23. test_seed_proposal_endpoint_empty_when_no_files
    24. test_seed_proposal_endpoint_returns_proposals
    25. test_seed_proposal_endpoint_missing_params_returns_400

  POST /api/qa-uat/seed-proposal/validate (Flask)
    26. test_validate_endpoint_accepts_safe_script
    27. test_validate_endpoint_blocks_drop_script
    28. test_validate_endpoint_empty_sql_returns_400

All tests run without infrastructure (DB, network, filesystem IO except tmp_path).
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

TOOL_DIR = Path(__file__).parent.parent.parent
sys.path.insert(0, str(TOOL_DIR))

# ─────────────────────────────────────────────────────────────────────────────
# Helpers / fixtures
# ─────────────────────────────────────────────────────────────────────────────

def _minimal_valid_sql(scenario_id: str = "RF-007-CA-01") -> str:
    """Return a SQL script that passes ALL safety validator rules."""
    return f"""\
/* QA_UAT_SEED_PROPOSAL — Ticket: 120, Scenario: {scenario_id} */

BEGIN TRANSACTION;

DECLARE @SeedRunId VARCHAR(64) = 'seed-120-ABCDEF';
DECLARE @CreatedBy NVARCHAR(64) = 'QA_UAT_AGENT';

-- Anti-PROD guard
IF DB_NAME() LIKE '%PROD%'
BEGIN
    RAISERROR('Seed rejected in PROD.', 16, 1);
    ROLLBACK TRANSACTION;
    RETURN;
END

IF NOT EXISTS (SELECT 1 FROM Clientes WHERE CLCOD = 99999 AND SeedRunId = @SeedRunId)
BEGIN
    INSERT INTO Clientes (CLCOD, Nombre, SeedRunId, CreatedBy)
    VALUES (99999, 'Cliente Seed', @SeedRunId, @CreatedBy);
END

-- Verification SELECT
SELECT COUNT(*) AS RowsInserted FROM Clientes WHERE SeedRunId = @SeedRunId;
-- Expected: 1

ROLLBACK TRANSACTION;
-- COMMIT TRANSACTION;  -- Un-comment after human review and approval
"""


def _make_data_contract_dict(schema_mapping: dict | None = None, ticket_id: int = 120) -> dict:
    return {
        "ticket_id": ticket_id,
        "scenario_id": "RF-007-CA-01",
        "requirements": [
            {
                "requirement_id": "data.req.001",
                "entity": "Clientes",
                "alias": "cliente_con_obligaciones",
                "required_fields": ["CLCOD"],
                "constraints": ["tiene al menos 1 obligacion activa"],
                "schema_known": False,
                "db_table": None,
            }
        ],
    }


def _make_schema_mapping() -> dict:
    return {
        "Clientes": {
            "table": "dbo.Clientes",
            "columns": {
                "CLCOD": {"type": "INT"},
                "Nombre": {"type": "NVARCHAR(100)"},
                "SeedRunId": {"type": "VARCHAR(64)"},
                "CreatedBy": {"type": "NVARCHAR(64)"},
            },
        }
    }


# ─────────────────────────────────────────────────────────────────────────────
# Module 1 — sql_safety_validator.py
# ─────────────────────────────────────────────────────────────────────────────

class TestSqlSafetyValidator:

    def test_validator_accepts_valid_seed_script(self):
        """A script that follows all rules passes safety validation."""
        from sql_safety_validator import validate
        result = validate(_minimal_valid_sql(), source="test:valid")
        assert result.safe is True
        assert result.risk_level == "low"
        assert result.blocking_findings == []

    def test_validator_blocks_drop(self):
        """Script with DROP TABLE is rejected."""
        from sql_safety_validator import validate
        sql = _minimal_valid_sql() + "\nDROP TABLE Clientes;"
        result = validate(sql, source="test:drop")
        assert result.safe is False
        rules = [f.rule for f in result.blocking_findings]
        assert "NO_DROP_ALLOWED" in rules

    def test_validator_blocks_truncate(self):
        """Script with TRUNCATE is rejected."""
        from sql_safety_validator import validate
        sql = _minimal_valid_sql() + "\nTRUNCATE TABLE Clientes;"
        result = validate(sql, source="test:truncate")
        assert result.safe is False
        rules = [f.rule for f in result.blocking_findings]
        assert "NO_TRUNCATE_ALLOWED" in rules

    def test_validator_blocks_active_commit(self):
        """Script with active (non-commented) COMMIT TRANSACTION is rejected."""
        from sql_safety_validator import validate
        sql = _minimal_valid_sql().replace(
            "-- COMMIT TRANSACTION;  -- Un-comment after human review and approval",
            "COMMIT TRANSACTION;"
        )
        result = validate(sql, source="test:commit")
        assert result.safe is False
        rules = [f.rule for f in result.blocking_findings]
        assert "ACTIVE_COMMIT" in rules

    def test_validator_blocks_missing_rollback(self):
        """Script without ROLLBACK TRANSACTION is rejected."""
        from sql_safety_validator import validate
        sql = _minimal_valid_sql().replace("ROLLBACK TRANSACTION;", "")
        result = validate(sql, source="test:no_rollback")
        assert result.safe is False
        rules = [f.rule for f in result.blocking_findings]
        assert "MISSING_ROLLBACK_DEFAULT" in rules

    def test_validator_blocks_missing_begin_transaction(self):
        """Script without BEGIN TRANSACTION is rejected."""
        from sql_safety_validator import validate
        sql = _minimal_valid_sql().replace("BEGIN TRANSACTION;", "")
        result = validate(sql, source="test:no_begin")
        assert result.safe is False
        rules = [f.rule for f in result.blocking_findings]
        assert "MISSING_BEGIN_TRANSACTION" in rules

    def test_validator_blocks_missing_seed_run_id(self):
        """Script without @SeedRunId is rejected."""
        from sql_safety_validator import validate
        sql = _minimal_valid_sql().replace("@SeedRunId", "@RunId_WRONG")
        result = validate(sql, source="test:no_seed_run_id")
        assert result.safe is False
        rules = [f.rule for f in result.blocking_findings]
        assert "MISSING_SEED_RUN_ID" in rules

    def test_validator_blocks_missing_verification_select(self):
        """Script without a SELECT after INSERT is rejected."""
        from sql_safety_validator import validate
        # Remove all SELECT lines
        lines = [l for l in _minimal_valid_sql().splitlines()
                 if "SELECT" not in l.upper()]
        sql = "\n".join(lines)
        result = validate(sql, source="test:no_select")
        assert result.safe is False
        rules = [f.rule for f in result.blocking_findings]
        assert "MISSING_VERIFICATION_SELECT" in rules

    def test_validator_blocks_delete_without_seed_marker(self):
        """DELETE without SeedRunId in WHERE is rejected."""
        from sql_safety_validator import validate
        sql = _minimal_valid_sql() + "\nDELETE FROM Clientes WHERE CLCOD = 99999;"
        result = validate(sql, source="test:delete_no_marker")
        assert result.safe is False
        rules = [f.rule for f in result.blocking_findings]
        assert "DELETE_WITHOUT_SEED_MARKER" in rules

    def test_validator_blocks_alter(self):
        """Script with ALTER TABLE is rejected."""
        from sql_safety_validator import validate
        sql = _minimal_valid_sql() + "\nALTER TABLE Clientes ADD COLUMN X INT;"
        result = validate(sql, source="test:alter")
        assert result.safe is False
        rules = [f.rule for f in result.blocking_findings]
        assert "NO_ALTER_ALLOWED" in rules

    def test_validator_commented_commit_is_allowed(self):
        """A commented-out COMMIT TRANSACTION is NOT a violation."""
        from sql_safety_validator import validate
        # Ensure COMMIT is only in comment form (already so in _minimal_valid_sql)
        sql = _minimal_valid_sql()
        assert "-- COMMIT TRANSACTION;" in sql
        result = validate(sql, source="test:commented_commit")
        assert result.safe is True

    def test_validator_safe_result_always_requires_human_approval(self):
        """Even when safe=True, requires_human_approval must be True."""
        from sql_safety_validator import validate
        result = validate(_minimal_valid_sql(), source="test:approval")
        assert result.requires_human_approval is True


# ─────────────────────────────────────────────────────────────────────────────
# Module 2 — sql_seed_generator.py
# ─────────────────────────────────────────────────────────────────────────────

class TestSqlSeedGenerator:

    def test_generator_blocked_when_no_schema(self):
        """When contract has no schema and no schema_mapping, verdict=BLOCKED."""
        from sql_seed_generator import generate
        contract = _make_data_contract_dict()
        result = generate(contract)
        assert result.ok is False
        assert result.verdict == "BLOCKED"
        assert result.reason == "DB_SCHEMA_UNKNOWN_FOR_SEED"

    def test_generator_produces_scripts_with_schema_mapping(self):
        """With a schema_mapping provided, generator produces a GENERATED result."""
        from sql_seed_generator import generate
        contract = _make_data_contract_dict()
        result = generate(contract, schema_mapping=_make_schema_mapping())
        assert result.verdict == "GENERATED"
        assert result.ok is True

    def test_generator_script_contains_rollback(self):
        """Generated seed script contains ROLLBACK TRANSACTION."""
        from sql_seed_generator import generate
        contract = _make_data_contract_dict()
        result = generate(contract, schema_mapping=_make_schema_mapping())
        assert result.verdict == "GENERATED"
        # Get safety result checks
        assert result.safety_result is not None
        assert result.safety_result["checks"]["rollback_default"] is True

    def test_generator_script_contains_begin_transaction(self):
        """Generated seed script contains BEGIN TRANSACTION."""
        from sql_seed_generator import generate
        contract = _make_data_contract_dict()
        result = generate(contract, schema_mapping=_make_schema_mapping())
        assert result.safety_result is not None
        assert result.safety_result["checks"]["transaction_present"] is True

    def test_generator_script_contains_seed_run_id(self):
        """Generated seed script contains @SeedRunId variable."""
        from sql_seed_generator import generate
        contract = _make_data_contract_dict()
        result = generate(contract, schema_mapping=_make_schema_mapping())
        assert result.safety_result is not None
        assert result.safety_result["checks"]["seed_run_id_present"] is True

    def test_generator_script_contains_anti_prod_guard(self):
        """Generated seed script contains anti-PROD DB_NAME() guard."""
        from sql_seed_generator import generate
        contract = _make_data_contract_dict()
        result = generate(contract, schema_mapping=_make_schema_mapping())
        assert result.safety_result is not None
        assert result.safety_result["checks"]["prod_guard_present"] is True

    def test_generator_script_contains_verification_select(self):
        """Generated seed script has a SELECT after the INSERT block."""
        from sql_seed_generator import generate
        contract = _make_data_contract_dict()
        result = generate(contract, schema_mapping=_make_schema_mapping())
        assert result.safety_result is not None
        assert result.safety_result["checks"]["verification_select_present"] is True

    def test_generator_script_passes_safety_validator(self):
        """Generated script passes the embedded safety validator (safe=True)."""
        from sql_seed_generator import generate
        contract = _make_data_contract_dict()
        result = generate(contract, schema_mapping=_make_schema_mapping())
        assert result.verdict == "GENERATED"
        assert result.safety_result is not None
        assert result.safety_result["safe"] is True

    def test_generator_writes_evidence_files(self, tmp_path):
        """When evidence_dir is provided, seed and cleanup .sql files are written."""
        from sql_seed_generator import generate
        contract = _make_data_contract_dict()
        result = generate(
            contract,
            schema_mapping=_make_schema_mapping(),
            evidence_dir=tmp_path,
            run_id="120",
        )
        assert result.verdict == "GENERATED"
        assert result.script_path is not None
        assert Path(result.script_path).exists()
        assert result.cleanup_path is not None
        assert Path(result.cleanup_path).exists()

    def test_generator_cleanup_script_has_rollback(self, tmp_path):
        """Cleanup script also uses ROLLBACK TRANSACTION by default."""
        from sql_seed_generator import generate
        contract = _make_data_contract_dict()
        result = generate(
            contract,
            schema_mapping=_make_schema_mapping(),
            evidence_dir=tmp_path,
            run_id="120",
        )
        cleanup_path = Path(result.cleanup_path)
        cleanup_sql = cleanup_path.read_text(encoding="utf-8")
        assert "ROLLBACK TRANSACTION" in cleanup_sql


# ─────────────────────────────────────────────────────────────────────────────
# Module 3 — Flask GET /api/qa-uat/seed-proposal (Sprint 10 endpoint)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def flask_app():
    ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
    backend_root = ROOT.parent / "Stacky Agents" / "backend"
    sys.path.insert(0, str(backend_root))
    os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
    os.environ.setdefault("LLM_BACKEND", "mock")
    from app import create_app  # type: ignore[import]
    application = create_app()
    application.config.update(TESTING=True)
    return application


@pytest.fixture
def flask_client(flask_app):
    with flask_app.test_client() as c:
        yield c


class TestGetSeedProposalEndpoint:

    def test_empty_when_no_files(self, flask_client, tmp_path):
        """Returns ok=True with empty proposals list when no seed files exist."""
        with patch("api.qa_uat._PIPELINE_ROOT", tmp_path):
            r = flask_client.get("/api/qa-uat/seed-proposal?run_id=120&ticket_id=120")
        assert r.status_code == 200
        body = r.get_json()
        assert body["ok"] is True
        assert body["proposals"] == []
        assert body["total"] == 0

    def test_returns_proposals_from_evidence(self, flask_client, tmp_path):
        """When seed files exist, returns their content and safety result."""
        seed_dir = tmp_path / "evidence" / "120" / "120"
        seed_dir.mkdir(parents=True)

        seed_sql = _minimal_valid_sql("RF-007-CA-01")
        (seed_dir / "seed_proposal_RF-007-CA-01.sql").write_text(seed_sql, encoding="utf-8")
        (seed_dir / "cleanup_proposal_RF-007-CA-01.sql").write_text(
            "BEGIN TRANSACTION;\n-- cleanup\nROLLBACK TRANSACTION;\n", encoding="utf-8"
        )

        with patch("api.qa_uat._PIPELINE_ROOT", tmp_path):
            r = flask_client.get("/api/qa-uat/seed-proposal?run_id=120&ticket_id=120")
        assert r.status_code == 200
        body = r.get_json()
        assert body["ok"] is True
        assert body["total"] == 1
        assert body["proposals"][0]["scenario_id"] == "RF-007-CA-01"
        assert body["proposals"][0]["script_content"] is not None
        assert "ROLLBACK TRANSACTION" in body["proposals"][0]["script_content"]

    def test_missing_run_id_returns_400(self, flask_client):
        r = flask_client.get("/api/qa-uat/seed-proposal?ticket_id=120")
        assert r.status_code == 400

    def test_missing_ticket_id_returns_400(self, flask_client):
        r = flask_client.get("/api/qa-uat/seed-proposal?run_id=120")
        assert r.status_code == 400


class TestValidateSeedProposalEndpoint:

    def test_accepts_safe_script(self, flask_client):
        """POST with valid SQL returns safe=True."""
        r = flask_client.post(
            "/api/qa-uat/seed-proposal/validate",
            json={"sql_text": _minimal_valid_sql(), "source": "test"},
            content_type="application/json",
        )
        assert r.status_code == 200
        body = r.get_json()
        assert body["ok"] is True
        assert body["result"]["safe"] is True

    def test_blocks_drop_script(self, flask_client):
        """POST with DROP TABLE returns safe=False."""
        sql = _minimal_valid_sql() + "\nDROP TABLE Clientes;"
        r = flask_client.post(
            "/api/qa-uat/seed-proposal/validate",
            json={"sql_text": sql},
            content_type="application/json",
        )
        assert r.status_code == 200
        body = r.get_json()
        assert body["ok"] is True
        assert body["result"]["safe"] is False
        rules = [f["rule"] for f in body["result"]["blocking_findings"]]
        assert "NO_DROP_ALLOWED" in rules

    def test_empty_sql_returns_400(self, flask_client):
        """POST with empty sql_text returns 400."""
        r = flask_client.post(
            "/api/qa-uat/seed-proposal/validate",
            json={"sql_text": ""},
            content_type="application/json",
        )
        assert r.status_code == 400
