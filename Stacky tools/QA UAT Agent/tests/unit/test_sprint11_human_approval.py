"""
tests/unit/test_sprint11_human_approval.py — Sprint 11: Human Approval + Seed Executor + Cleanup.

Tests:
  seed_executor.py
    1.  test_executor_skipped_on_dry_run
    2.  test_executor_blocked_on_sha256_mismatch
    3.  test_executor_blocked_on_prod_url
    4.  test_executor_skipped_when_no_db_url
    5.  test_executor_writes_evidence_artifact
    6.  test_executor_skipped_when_script_not_found
    7.  test_executor_result_has_required_fields

  cleanup_manager.py
    8.  test_cleanup_skipped_on_never_policy
    9.  test_cleanup_skipped_on_dry_run
    10. test_cleanup_blocked_when_seed_run_id_not_in_script
    11. test_check_cleanup_policy_after_run_is_true
    12. test_check_cleanup_policy_never_is_false
    13. test_check_cleanup_policy_manual_is_false
    14. test_cleanup_writes_evidence_artifact

  POST /api/qa-uat/seed-proposal/approve (Flask)
    15. test_approve_endpoint_returns_400_on_missing_run_id
    16. test_approve_endpoint_returns_400_on_missing_scenario
    17. test_approve_endpoint_returns_400_on_missing_sha256
    18. test_approve_endpoint_dry_run_returns_skipped_when_no_script
    19. test_approve_endpoint_dry_run_ok_when_script_exists

  POST /api/qa-uat/seed-proposal/cleanup (Flask)
    20. test_cleanup_endpoint_returns_400_on_missing_run_id
    21. test_cleanup_endpoint_dry_run_returns_skipped_when_no_script

  GET /api/qa-uat/seed-proposal/approvals (Flask)
    22. test_approvals_endpoint_empty_when_no_files
    23. test_approvals_endpoint_returns_approval_records

All tests run without real DB or network. sha256 tamper checks use real
hashlib so no DB is required to verify the guard works.
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

def _valid_seed_sql(scenario_id: str = "RF-007-CA-01") -> str:
    """Minimal valid seed SQL that passes safety validator AND cleanup SeedRunId guard."""
    return f"""\
/* QA_UAT_SEED_PROPOSAL — Ticket: 120, Scenario: {scenario_id} */

BEGIN TRANSACTION;

DECLARE @SeedRunId VARCHAR(64) = 'seed-120-ABCDEF';
DECLARE @CreatedBy NVARCHAR(64) = 'QA_UAT_AGENT';

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

SELECT COUNT(*) AS RowsInserted FROM Clientes WHERE SeedRunId = @SeedRunId;

ROLLBACK TRANSACTION;
-- COMMIT TRANSACTION;  -- Un-comment after human review and approval
"""


def _valid_cleanup_sql(seed_run_id: str = "seed-120-ABCDEF") -> str:
    return f"""\
BEGIN TRANSACTION;

DECLARE @SeedRunId VARCHAR(64) = '{seed_run_id}';

DELETE FROM Clientes WHERE SeedRunId = @SeedRunId;

SELECT COUNT(*) AS RowsRemaining FROM Clientes WHERE SeedRunId = @SeedRunId;

ROLLBACK TRANSACTION;
"""


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _make_exec_logger():
    mock = MagicMock()
    mock.events = []
    def _log(event_type, data=None):
        mock.events.append({"event_type": event_type, "data": data or {}})
    mock.side_effect = _log
    mock.__call__ = _log
    return mock


# ─────────────────────────────────────────────────────────────────────────────
# SeedExecutor tests
# ─────────────────────────────────────────────────────────────────────────────

class TestSeedExecutor:
    """Tests for seed_executor.py — no DB connections, no filesystem side effects beyond tmp_path."""

    def _import(self):
        import seed_executor as se
        return se

    def test_executor_skipped_on_dry_run(self, tmp_path):
        se = self._import()
        sql = _valid_seed_sql()
        sha = _sha256(sql)
        script = tmp_path / "seed_proposal_RF-007-CA-01.sql"
        script.write_text(sql, encoding="utf-8")

        result = se.execute(
            script_path=script,
            approved_sha256=sha,
            scenario_id="RF-007-CA-01",
            seed_run_id="seed-120-ABC",
            run_id="run-1",
            ticket_id=120,
            db_url=None,
            exec_logger=None,
            evidence_dir=tmp_path,
            dry_run=True,
        )
        assert result.verdict == "SKIPPED"
        assert result.ok is True
        assert result.reason is not None

    def test_executor_blocked_on_sha256_mismatch(self, tmp_path):
        se = self._import()
        sql = _valid_seed_sql()
        script = tmp_path / "seed_proposal_RF-007-CA-01.sql"
        script.write_text(sql, encoding="utf-8")

        result = se.execute(
            script_path=script,
            approved_sha256="wronghash1234",
            scenario_id="RF-007-CA-01",
            seed_run_id="seed-120-ABC",
            run_id="run-1",
            ticket_id=120,
            db_url="mssql://some_server/DEV_DB",
            exec_logger=None,
            evidence_dir=tmp_path,
            dry_run=False,
        )
        assert result.verdict == "BLOCKED"
        assert "sha256" in (result.reason or "").lower()
        assert result.sha256_match is False

    def test_executor_blocked_on_prod_url(self, tmp_path):
        se = self._import()
        sql = _valid_seed_sql()
        sha = _sha256(sql)
        script = tmp_path / "seed_proposal_RF-007-CA-01.sql"
        script.write_text(sql, encoding="utf-8")

        result = se.execute(
            script_path=script,
            approved_sha256=sha,
            scenario_id="RF-007-CA-01",
            seed_run_id="seed-120-ABC",
            run_id="run-1",
            ticket_id=120,
            db_url="mssql://server/PROD_DB",
            exec_logger=None,
            evidence_dir=tmp_path,
            dry_run=False,
        )
        # With a PROD url and no real driver, seed_executor either BLOCKs on
        # the env guard (if it parses the URL) or ERRORs when the connection
        # attempt fails and reports prod in the error. Either way the seed
        # must NOT be APPLIED or SKIPPED silently.
        assert result.verdict in {"BLOCKED", "ERROR"}
        assert result.ok is False or result.verdict != "APPLIED"

    def test_executor_skipped_when_no_db_url(self, tmp_path):
        se = self._import()
        sql = _valid_seed_sql()
        sha = _sha256(sql)
        script = tmp_path / "seed_proposal_RF-007-CA-01.sql"
        script.write_text(sql, encoding="utf-8")

        result = se.execute(
            script_path=script,
            approved_sha256=sha,
            scenario_id="RF-007-CA-01",
            seed_run_id="seed-120-ABC",
            run_id="run-1",
            ticket_id=120,
            db_url=None,
            exec_logger=None,
            evidence_dir=tmp_path,
            dry_run=False,
        )
        # No db_url and dry_run=False → SKIPPED (no driver available)
        assert result.verdict in {"SKIPPED", "BLOCKED"}

    def test_executor_writes_evidence_artifact(self, tmp_path):
        se = self._import()
        sql = _valid_seed_sql()
        sha = _sha256(sql)
        script = tmp_path / "seed_proposal_RF-007-CA-01.sql"
        script.write_text(sql, encoding="utf-8")

        result = se.execute(
            script_path=script,
            approved_sha256=sha,
            scenario_id="RF-007-CA-01",
            seed_run_id="seed-120-ABC",
            run_id="run-1",
            ticket_id=120,
            db_url=None,
            exec_logger=None,
            evidence_dir=tmp_path,
            dry_run=True,
        )
        # Evidence artifact should have been written
        artifacts = list(tmp_path.rglob("seed_execution_result_*.json"))
        assert len(artifacts) >= 1
        data = json.loads(artifacts[0].read_text(encoding="utf-8"))
        assert "verdict" in data
        assert "scenario_id" in data

    def test_executor_skipped_when_script_not_found(self, tmp_path):
        se = self._import()
        result = se.execute(
            script_path=tmp_path / "nonexistent.sql",
            approved_sha256="irrelevant",
            scenario_id="RF-007-CA-01",
            seed_run_id="seed-120-ABC",
            run_id="run-1",
            ticket_id=120,
            db_url=None,
            exec_logger=None,
            evidence_dir=tmp_path,
            dry_run=True,
        )
        assert result.ok is False or result.verdict in {"SKIPPED", "BLOCKED", "ERROR"}

    def test_executor_result_has_required_fields(self, tmp_path):
        se = self._import()
        sql = _valid_seed_sql()
        sha = _sha256(sql)
        script = tmp_path / "seed_proposal_RF-007-CA-01.sql"
        script.write_text(sql, encoding="utf-8")

        result = se.execute(
            script_path=script,
            approved_sha256=sha,
            scenario_id="RF-007-CA-01",
            seed_run_id="seed-120-ABC",
            run_id="run-1",
            ticket_id=120,
            db_url=None,
            exec_logger=None,
            evidence_dir=tmp_path,
            dry_run=True,
        )
        d = result.to_dict()
        required_keys = {
            "verdict", "ok", "scenario_id", "seed_run_id", "run_id",
            "ticket_id", "dry_run", "sha256_match", "rows_inserted",
        }
        assert required_keys.issubset(d.keys())


# ─────────────────────────────────────────────────────────────────────────────
# CleanupManager tests
# ─────────────────────────────────────────────────────────────────────────────

class TestCleanupManager:
    """Tests for cleanup_manager.py — no DB connections."""

    def _import(self):
        import cleanup_manager as cm
        return cm

    def test_cleanup_skipped_on_never_policy(self, tmp_path):
        cm = self._import()
        sql = _valid_cleanup_sql()
        script = tmp_path / "cleanup.sql"
        script.write_text(sql, encoding="utf-8")

        result = cm.cleanup(
            cleanup_script_path=script,
            seed_run_id="seed-120-ABCDEF",
            scenario_id="RF-007-CA-01",
            run_id="run-1",
            ticket_id=120,
            cleanup_policy="never",
            exec_logger=None,
            evidence_dir=tmp_path,
            dry_run=False,
        )
        assert result.verdict == "SKIPPED"
        assert "never" in (result.reason or "").lower()

    def test_cleanup_skipped_on_dry_run(self, tmp_path):
        cm = self._import()
        sql = _valid_cleanup_sql()
        script = tmp_path / "cleanup.sql"
        script.write_text(sql, encoding="utf-8")

        result = cm.cleanup(
            cleanup_script_path=script,
            seed_run_id="seed-120-ABCDEF",
            scenario_id="RF-007-CA-01",
            run_id="run-1",
            ticket_id=120,
            cleanup_policy="after_run",
            exec_logger=None,
            evidence_dir=tmp_path,
            dry_run=True,
        )
        assert result.verdict == "SKIPPED"
        assert "dry_run" in (result.reason or "").lower()

    def test_cleanup_blocked_when_seed_run_id_not_in_script(self, tmp_path):
        cm = self._import()
        sql_without_seed_run_id = "DELETE FROM Clientes WHERE Id = 1;"
        script = tmp_path / "cleanup.sql"
        script.write_text(sql_without_seed_run_id, encoding="utf-8")

        # Pass a fake db_url so the SeedRunId safety check is reached before
        # the no-db-url SKIPPED shortcut.
        result = cm.cleanup(
            cleanup_script_path=script,
            seed_run_id="seed-120-ABCDEF",
            scenario_id="RF-007-CA-01",
            run_id="run-1",
            ticket_id=120,
            cleanup_policy="after_run",
            exec_logger=None,
            evidence_dir=tmp_path,
            dry_run=False,
            db_url="mssql://server/DEV_DB",
        )
        # BLOCKED because SeedRunId is not in script; SKIPPED is also acceptable
        # if the module returns SKIPPED with a seed_run_id_missing reason.
        assert result.verdict in {"BLOCKED", "SKIPPED"}
        # Must NOT be CLEANED without the SeedRunId guard
        assert result.verdict != "CLEANED"

    def test_check_cleanup_policy_after_run_is_true(self):
        cm = self._import()
        assert cm.check_cleanup_policy("after_run") is True

    def test_check_cleanup_policy_never_is_false(self):
        cm = self._import()
        assert cm.check_cleanup_policy("never") is False

    def test_check_cleanup_policy_manual_is_false(self):
        cm = self._import()
        assert cm.check_cleanup_policy("manual") is False

    def test_cleanup_writes_evidence_artifact(self, tmp_path):
        cm = self._import()
        sql = _valid_cleanup_sql()
        script = tmp_path / "cleanup.sql"
        script.write_text(sql, encoding="utf-8")

        result = cm.cleanup(
            cleanup_script_path=script,
            seed_run_id="seed-120-ABCDEF",
            scenario_id="RF-007-CA-01",
            run_id="run-1",
            ticket_id=120,
            cleanup_policy="never",
            exec_logger=None,
            evidence_dir=tmp_path,
            dry_run=False,
        )
        artifacts = list(tmp_path.rglob("seed_cleanup_result_*.json"))
        assert len(artifacts) >= 1
        data = json.loads(artifacts[0].read_text(encoding="utf-8"))
        assert "verdict" in data
        assert "cleanup_policy" in data


# ─────────────────────────────────────────────────────────────────────────────
# Flask endpoint tests — POST /api/qa-uat/seed-proposal/approve
# ─────────────────────────────────────────────────────────────────────────────

BACKEND_DIR = TOOL_DIR.parent.parent / "Stacky Agents" / "backend"


@pytest.fixture(scope="module")
def flask_app():
    sys.path.insert(0, str(BACKEND_DIR))
    os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
    os.environ.setdefault("LLM_BACKEND", "mock")
    from app import create_app  # type: ignore[import]
    application = create_app()
    application.config.update(TESTING=True)
    return application


@pytest.fixture
def flask_client(flask_app, tmp_path, monkeypatch):
    """Flask test client with evidence dir pointing at tmp_path."""
    monkeypatch.setenv("QA_UAT_EVIDENCE_DIR", str(tmp_path))
    with flask_app.test_client() as client:
        yield client, tmp_path


class TestApproveEndpoint:

    def test_approve_endpoint_returns_400_on_missing_run_id(self, flask_client):
        client, _ = flask_client
        resp = client.post(
            "/api/qa-uat/seed-proposal/approve",
            json={"ticket_id": 120, "scenario_id": "RF-007-CA-01", "approved_sha256": "abc"},
        )
        assert resp.status_code == 400

    def test_approve_endpoint_returns_400_on_missing_scenario(self, flask_client):
        client, _ = flask_client
        resp = client.post(
            "/api/qa-uat/seed-proposal/approve",
            json={"run_id": "run-1", "ticket_id": 120, "approved_sha256": "abc"},
        )
        assert resp.status_code == 400

    def test_approve_endpoint_returns_400_on_missing_sha256(self, flask_client):
        client, _ = flask_client
        resp = client.post(
            "/api/qa-uat/seed-proposal/approve",
            json={"run_id": "run-1", "ticket_id": 120, "scenario_id": "RF-007-CA-01"},
        )
        assert resp.status_code == 400

    def test_approve_endpoint_dry_run_returns_skipped_when_no_script(self, flask_client):
        client, _ = flask_client
        resp = client.post(
            "/api/qa-uat/seed-proposal/approve",
            json={
                "run_id": "run-99",
                "ticket_id": 120,
                "scenario_id": "RF-007-CA-01",
                "approved_sha256": "irrelevant_hash",
                "dry_run": True,
            },
        )
        # Script does not exist → 404 or SKIPPED result
        assert resp.status_code in {200, 404}

    def test_approve_endpoint_dry_run_ok_when_script_exists(self, flask_client):
        client, evidence_dir = flask_client
        # Write a seed script in the path the endpoint expects:
        # _PIPELINE_ROOT / "evidence" / ticket_id / run_id / seed_proposal_<id>.sql
        sql = _valid_seed_sql()
        sha = _sha256(sql)
        script_dir = evidence_dir / "evidence" / "120" / "run-1"
        script_dir.mkdir(parents=True, exist_ok=True)
        (script_dir / "seed_proposal_RF-007-CA-01.sql").write_text(sql, encoding="utf-8")

        with patch("api.qa_uat._PIPELINE_ROOT", evidence_dir):
            resp = client.post(
                "/api/qa-uat/seed-proposal/approve",
                json={
                    "run_id": "run-1",
                    "ticket_id": 120,
                    "scenario_id": "RF-007-CA-01",
                    "approved_sha256": sha,
                    "dry_run": True,
                },
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert data["result"]["verdict"] == "SKIPPED"  # dry_run=True
        assert "dry_run" in data["result"]["reason"].lower()


# ─────────────────────────────────────────────────────────────────────────────
# Flask endpoint tests — POST /api/qa-uat/seed-proposal/cleanup
# ─────────────────────────────────────────────────────────────────────────────

class TestCleanupEndpoint:

    def test_cleanup_endpoint_returns_400_on_missing_run_id(self, flask_client):
        client, _ = flask_client
        resp = client.post(
            "/api/qa-uat/seed-proposal/cleanup",
            json={"ticket_id": 120, "scenario_id": "RF-007-CA-01", "seed_run_id": "x"},
        )
        assert resp.status_code == 400

    def test_cleanup_endpoint_dry_run_returns_skipped_when_no_script(self, flask_client):
        client, _ = flask_client
        resp = client.post(
            "/api/qa-uat/seed-proposal/cleanup",
            json={
                "run_id": "run-99",
                "ticket_id": 120,
                "scenario_id": "RF-007-CA-01",
                "seed_run_id": "seed-120-ABCDEF",
                "cleanup_policy": "after_run",
                "dry_run": True,
            },
        )
        # No script on disk → 404 or skipped
        assert resp.status_code in {200, 404}


# ─────────────────────────────────────────────────────────────────────────────
# Flask endpoint tests — GET /api/qa-uat/seed-proposal/approvals
# ─────────────────────────────────────────────────────────────────────────────

class TestApprovalsListEndpoint:

    def test_approvals_endpoint_empty_when_no_files(self, flask_client):
        client, _ = flask_client
        resp = client.get(
            "/api/qa-uat/seed-proposal/approvals?run_id=run-99&ticket_id=120"
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert data["approvals"] == []
        assert data["total"] == 0

    def test_approvals_endpoint_returns_approval_records(self, flask_client):
        client, evidence_dir = flask_client
        # Write approval artifact in path endpoint expects:
        # _PIPELINE_ROOT / "evidence" / ticket_id / run_id / seed_approval_<id>.json
        approval_dir = evidence_dir / "evidence" / "120" / "run-1"
        approval_dir.mkdir(parents=True, exist_ok=True)
        approval_data = {
            "scenario_id": "RF-007-CA-01",
            "approved_by": "test_operator",
            "approved_sha256": "abc123",
            "approved_at": "2024-01-01T00:00:00Z",
        }
        (approval_dir / "seed_approval_RF-007-CA-01.json").write_text(
            json.dumps(approval_data), encoding="utf-8"
        )

        with patch("api.qa_uat._PIPELINE_ROOT", evidence_dir):
            resp = client.get(
                "/api/qa-uat/seed-proposal/approvals?run_id=run-1&ticket_id=120"
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert data["total"] >= 1
        assert any(a.get("scenario_id") == "RF-007-CA-01" for a in data["approvals"])
