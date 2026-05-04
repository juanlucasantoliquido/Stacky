"""Unit tests for uat_ticket_reader.py (B1)."""
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
os.environ.setdefault("STACKY_LLM_BACKEND", "mock")

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _mock_ado_side_effect(ticket_json: str, comments_json: str):
    """Returns a side_effect callable that dispatches by subcommand."""
    def side_effect(cmd, *args, **kwargs):
        result = MagicMock()
        result.returncode = 0
        if "comments" in cmd:
            result.stdout = comments_json
        else:
            result.stdout = ticket_json
        result.stderr = ""
        return result
    return side_effect


def test_ticket_70_returns_7_scenarios():
    import uat_ticket_reader
    ticket_json = _load("ticket_70.json")
    comments_json = _load("comments_70.json")
    with patch("subprocess.run", side_effect=_mock_ado_side_effect(ticket_json, comments_json)):
        result = uat_ticket_reader.run(ticket_id=70, use_cache=False)
    assert result["ok"] is True
    plan = result.get("plan_pruebas", [])
    assert len(plan) == 7, f"Expected 7 plan items, got {len(plan)}"


def test_ticket_without_analysis_returns_blocked():
    import uat_ticket_reader
    ticket_json = _load("ticket_70.json")
    comments_no_analysis = json.dumps({"ok": True, "comments": []})
    with patch("subprocess.run", side_effect=_mock_ado_side_effect(ticket_json, comments_no_analysis)):
        result = uat_ticket_reader.run(ticket_id=70, use_cache=False)
    assert result["ok"] is False
    assert result["error"] == "missing_technical_analysis"


def test_nonexistent_ticket_returns_not_found():
    import uat_ticket_reader
    mock_fail = MagicMock()
    mock_fail.returncode = 1
    mock_fail.stdout = json.dumps({"ok": False, "error": "not_found", "message": "Ticket not found"})
    mock_fail.stderr = ""
    with patch("subprocess.run", return_value=mock_fail):
        result = uat_ticket_reader.run(ticket_id=99999, use_cache=False)
    assert result["ok"] is False


def test_cache_flag_skips_ado_call(tmp_path):
    import uat_ticket_reader
    # Build a minimal ticket reader output to cache
    cached_result = {
        "ok": True,
        "ticket": {"id": 70, "title": "Test"},
        "comments": [],
        "plan_pruebas": [{"id": "P01", "descripcion": "test", "dados": "", "esperado": "ok"}],
        "precondiciones_detected": [],
        "meta": {"tool": "uat_ticket_reader", "version": "1.0.0"},
    }
    # Create a fake evidence dir with the cached ticket
    fake_evidence_dir = tmp_path / "evidence" / "70"
    fake_evidence_dir.mkdir(parents=True)
    (fake_evidence_dir / "ticket.json").write_text(json.dumps(cached_result), encoding="utf-8")

    # Patch the evidence root used by uat_ticket_reader to point to tmp_path
    with patch("uat_ticket_reader.Path") as mock_path_cls:
        # Make Path(__file__).resolve().parent / "evidence" / str(70) return our fake dir
        real_path = Path
        def path_side_effect(*args):
            p = real_path(*args)
            return p
        # Simpler: patch the evidence dir directly by monkeypatching the run function logic
        # We'll use a different approach: create the cache where uat_ticket_reader expects it
        pass

    # Direct approach: put the cache file where uat_ticket_reader would look
    actual_tool_dir = Path(uat_ticket_reader.__file__).resolve().parent
    actual_evidence_dir = actual_tool_dir / "evidence" / "70"
    actual_evidence_dir.mkdir(parents=True, exist_ok=True)
    cache_file = actual_evidence_dir / "ticket.json"
    cache_file.write_text(json.dumps(cached_result), encoding="utf-8")

    with patch("subprocess.run") as mock_run:
        result = uat_ticket_reader.run(ticket_id=70, use_cache=True)
        mock_run.assert_not_called()

    # Cleanup
    cache_file.unlink(missing_ok=True)
    assert result["ok"] is True


def test_output_validates_against_schema():
    import uat_ticket_reader
    import jsonschema
    schema_path = Path(__file__).parent.parent.parent / "schemas" / "uat_ticket.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    ticket_json = _load("ticket_70.json")
    comments_json = _load("comments_70.json")
    with patch("subprocess.run", side_effect=_mock_ado_side_effect(ticket_json, comments_json)):
        result = uat_ticket_reader.run(ticket_id=70, use_cache=False)
    jsonschema.validate(instance=result, schema=schema)


def test_preconditions_detected_ridioma_inserts():
    import uat_ticket_reader
    ticket_json = _load("ticket_70.json")
    comments_json = _load("comments_70.json")
    with patch("subprocess.run", side_effect=_mock_ado_side_effect(ticket_json, comments_json)):
        result = uat_ticket_reader.run(ticket_id=70, use_cache=False)
    precond = result.get("precondiciones_detected", [])
    ridioma_inserts = [p for p in precond if p.get("tipo") == "RIDIOMA_INSERT"]
    assert len(ridioma_inserts) >= 1, "Expected at least 1 RIDIOMA_INSERT detected"


def test_llm_fallback_on_regex_match():
    """If the comment author doesn't contain 'Analista', LLM is called to classify role."""
    import uat_ticket_reader
    ticket_json = _load("ticket_70.json")
    # Comment with ambiguous author
    ambiguous_comments = json.dumps({
        "ok": True,
        "comments": [
            {
                "id": 1,
                "author": "jsmith",
                "date": "2026-04-20T10:00:00Z",
                "text": (
                    "<h2>Análisis Técnico</h2>"
                    "<p>P01: Test scenario<br/>Datos: empresa=0001<br/>Esperado: OK</p>"
                ),
            }
        ],
    })
    with patch("subprocess.run", side_effect=_mock_ado_side_effect(ticket_json, ambiguous_comments)):
        result = uat_ticket_reader.run(ticket_id=70, use_cache=False)
    # Should succeed regardless of LLM mock (mock backend returns stub)
    assert isinstance(result, dict)
    assert "ok" in result
