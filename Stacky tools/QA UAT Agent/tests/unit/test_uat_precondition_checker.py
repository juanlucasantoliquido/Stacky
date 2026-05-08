"""Unit tests for uat_precondition_checker.py (E1).

Tests cover:
- Missing env vars return db_credentials_missing error
- Invalid scenarios file returns error
- All scenarios pass when DB returns positive counts
- RIDIOMA missing marks affected scenario BLOCKED
- Test data missing marks affected scenario BLOCKED
- Scenarios without RIDIOMA preconditions pass without DB check for RIDIOMA
- Unrecognized table is skipped (not in safe-list)
- Summary counts are correct
"""
import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
os.environ.setdefault("STACKY_LLM_BACKEND", "mock")

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _load_scenarios() -> dict:
    return json.loads((FIXTURES / "scenarios_70.json").read_text(encoding="utf-8"))


def _make_mock_connection(ridioma_count: int = 1, data_count: int = 1):
    """Create a mock pyodbc-like connection that returns specified counts."""
    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value = cursor
    cursor.fetchone.return_value = (max(ridioma_count, data_count),)
    return conn


def _mock_connector(connection):
    """Returns a connector factory that returns the given mock connection."""
    def connector():
        return connection
    return connector


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_missing_env_vars_returns_error(tmp_path):
    """If DB env vars are not set, return db_credentials_missing immediately."""
    import uat_precondition_checker

    scenarios_file = tmp_path / "scenarios.json"
    scenarios_file.write_text(json.dumps(_load_scenarios()), encoding="utf-8")

    # Remove env vars
    env_without_db = {
        k: v for k, v in os.environ.items()
        if k not in ("RS_QA_DB_USER", "RS_QA_DB_PASS", "RS_QA_DB_DSN")
    }
    with patch.dict(os.environ, env_without_db, clear=True):
        # Also remove just these vars if present
        for var in ("RS_QA_DB_USER", "RS_QA_DB_PASS", "RS_QA_DB_DSN"):
            os.environ.pop(var, None)
        result = uat_precondition_checker.run(scenarios_path=scenarios_file)

    assert result["ok"] is False
    assert result["error"] == "db_credentials_missing"
    assert "RS_QA_DB" in result["message"]


def test_invalid_scenarios_file_returns_error(tmp_path):
    """Malformed JSON in scenarios file returns invalid_scenarios_json error."""
    import uat_precondition_checker

    bad_file = tmp_path / "bad.json"
    bad_file.write_text("not json", encoding="utf-8")

    with patch.dict(os.environ, {
        "RS_QA_DB_USER": "user", "RS_QA_DB_PASS": "pass", "RS_QA_DB_DSN": "dsn"
    }):
        result = uat_precondition_checker.run(scenarios_path=bad_file)

    assert result["ok"] is False
    assert result["error"] == "invalid_scenarios_json"


def test_all_scenarios_pass_when_db_has_data(tmp_path):
    """When DB returns positive counts for all checks, all scenarios pass."""
    import uat_precondition_checker

    scenarios_file = tmp_path / "scenarios.json"
    scenarios_file.write_text(json.dumps(_load_scenarios()), encoding="utf-8")

    mock_conn = _make_mock_connection(ridioma_count=3, data_count=5)

    with patch.dict(os.environ, {
        "RS_QA_DB_USER": "user", "RS_QA_DB_PASS": "pass", "RS_QA_DB_DSN": "dsn"
    }):
        result = uat_precondition_checker.run(
            scenarios_path=scenarios_file,
            _db_connector=_mock_connector(mock_conn),
        )

    assert result["ok"] is True
    assert result["summary"]["blocked"] == 0
    assert result["summary"]["ok"] == result["summary"]["total"]


def test_ridioma_missing_marks_scenario_blocked(tmp_path):
    """When RIDIOMA count=0, scenario with that precondition is marked blocked."""
    import uat_precondition_checker

    scenarios_file = tmp_path / "scenarios.json"
    scenarios_file.write_text(json.dumps(_load_scenarios()), encoding="utf-8")

    # Return 0 count for all DB queries (simulates missing RIDIOMA)
    mock_conn = MagicMock()
    cursor = MagicMock()
    mock_conn.cursor.return_value = cursor
    cursor.fetchone.return_value = (0,)

    with patch.dict(os.environ, {
        "RS_QA_DB_USER": "user", "RS_QA_DB_PASS": "pass", "RS_QA_DB_DSN": "dsn"
    }):
        result = uat_precondition_checker.run(
            scenarios_path=scenarios_file,
            _db_connector=_mock_connector(mock_conn),
        )

    assert result["ok"] is True  # pipeline ok, individual results show missing
    # P04 has "INSERTs RIDIOMA 9296-9298 aplicados" precondition
    assert "P04" in result["results"]
    p04 = result["results"]["P04"]
    assert p04["ok"] is False
    ridioma_missing = [m for m in p04["missing"] if m["tipo"] == "ridioma"]
    assert len(ridioma_missing) > 0
    assert "9296" in ridioma_missing[0]["recurso"]


def test_test_data_missing_marks_scenario_blocked(tmp_path):
    """When required test data count=0, scenario is marked blocked."""
    import uat_precondition_checker

    # Create minimal scenarios with datos_requeridos
    scenarios = {
        "ok": True,
        "ticket_id": 70,
        "scenarios": [
            {
                "scenario_id": "P01",
                "pantalla": "FrmAgenda.aspx",
                "precondiciones": [],
                "oraculos": [],
                "pasos": [],
                "datos_requeridos": [{"tabla": "RAGEN", "filtro": "OGEMPRESA='0001'"}],
                "origem": {}
            }
        ]
    }
    scenarios_file = tmp_path / "scenarios.json"
    scenarios_file.write_text(json.dumps(scenarios), encoding="utf-8")

    mock_conn = MagicMock()
    cursor = MagicMock()
    mock_conn.cursor.return_value = cursor
    cursor.fetchone.return_value = (0,)  # no data found

    with patch.dict(os.environ, {
        "RS_QA_DB_USER": "user", "RS_QA_DB_PASS": "pass", "RS_QA_DB_DSN": "dsn"
    }):
        result = uat_precondition_checker.run(
            scenarios_path=scenarios_file,
            _db_connector=_mock_connector(mock_conn),
        )

    assert result["ok"] is True
    p01 = result["results"]["P01"]
    assert p01["ok"] is False
    data_missing = [m for m in p01["missing"] if m["tipo"] == "test_data"]
    assert len(data_missing) > 0
    assert "RAGEN" in data_missing[0]["recurso"]


def test_unsafe_table_is_skipped(tmp_path):
    """Tables not in the safe-list are not queried (security)."""
    import uat_precondition_checker

    scenarios = {
        "ok": True,
        "ticket_id": 70,
        "scenarios": [
            {
                "scenario_id": "P01",
                "pantalla": "FrmAgenda.aspx",
                "precondiciones": [],
                "oraculos": [],
                "pasos": [],
                "datos_requeridos": [{"tabla": "sys.tables", "filtro": "1=1"}],
                "origen": {}
            }
        ]
    }
    scenarios_file = tmp_path / "scenarios.json"
    scenarios_file.write_text(json.dumps(scenarios), encoding="utf-8")

    mock_conn = MagicMock()
    mock_conn.cursor.return_value = MagicMock()

    with patch.dict(os.environ, {
        "RS_QA_DB_USER": "user", "RS_QA_DB_PASS": "pass", "RS_QA_DB_DSN": "dsn"
    }):
        result = uat_precondition_checker.run(
            scenarios_path=scenarios_file,
            _db_connector=_mock_connector(mock_conn),
        )

    # sys.tables should not have been queried
    assert result["ok"] is True
    # sys.tables is not in _SAFE_TABLES so cursor.execute should not have been called
    mock_conn.cursor.return_value.execute.assert_not_called()


def test_ridioma_id_range_extraction():
    """RIDIOMA IDs are extracted correctly from range notation (9296-9298 → [9296,9297,9298])."""
    import uat_precondition_checker
    precs = ["INSERTs RIDIOMA 9296-9298 aplicados"]
    ids = uat_precondition_checker._extract_ridioma_ids(precs)
    assert ids == [9296, 9297, 9298]


def test_ridioma_id_comma_extraction():
    """RIDIOMA IDs are extracted from comma-separated notation."""
    import uat_precondition_checker
    precs = ["RIDIOMA 9296,9297,9298"]
    ids = uat_precondition_checker._extract_ridioma_ids(precs)
    assert set(ids) == {9296, 9297, 9298}


def test_summary_counts_correct(tmp_path):
    """Summary counts (total/ok/blocked) are consistent with results."""
    import uat_precondition_checker

    scenarios_file = tmp_path / "scenarios.json"
    scenarios_file.write_text(json.dumps(_load_scenarios()), encoding="utf-8")

    # Return 0 for RIDIOMA (blocks P04), positive for test data
    call_count = [0]
    def mock_fetchone_side_effect():
        call_count[0] += 1
        # First calls are for RIDIOMA (from P04 preconditions) → 0
        # Later calls for test data → 1
        return (0,) if call_count[0] <= 3 else (1,)

    mock_conn = MagicMock()
    cursor = MagicMock()
    mock_conn.cursor.return_value = cursor
    cursor.fetchone.side_effect = mock_fetchone_side_effect

    with patch.dict(os.environ, {
        "RS_QA_DB_USER": "user", "RS_QA_DB_PASS": "pass", "RS_QA_DB_DSN": "dsn"
    }):
        result = uat_precondition_checker.run(
            scenarios_path=scenarios_file,
            _db_connector=_mock_connector(mock_conn),
        )

    assert result["ok"] is True
    total = result["summary"]["total"]
    ok_count = result["summary"]["ok"]
    blocked = result["summary"]["blocked"]
    assert total == ok_count + blocked
    assert total == len(result["results"])
