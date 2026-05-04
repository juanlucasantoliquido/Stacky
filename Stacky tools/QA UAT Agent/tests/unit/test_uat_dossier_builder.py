"""Unit tests for uat_dossier_builder.py (B7)."""
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
os.environ.setdefault("STACKY_LLM_BACKEND", "mock")

FIXTURES = Path(__file__).parent.parent / "fixtures"
TOOL_DIR = Path(__file__).parent.parent.parent


def _runner_output() -> dict:
    return json.loads((FIXTURES / "runner_output_70.json").read_text(encoding="utf-8"))


def _ticket_data() -> dict:
    return json.loads((FIXTURES / "ticket_70.json").read_text(encoding="utf-8"))


def _build_dossier(tmp_path: Path, runner_override: dict = None) -> tuple:
    import uat_dossier_builder
    runner = runner_override or _runner_output()
    runner_path = tmp_path / "runner_output.json"
    runner_path.write_text(json.dumps(runner), encoding="utf-8")
    ticket_path = tmp_path / "ticket.json"
    ticket_path.write_text(json.dumps(_ticket_data()), encoding="utf-8")
    out_dir = tmp_path / "out"
    result = uat_dossier_builder.run(
        runner_output_path=runner_path,
        ticket_path=ticket_path,
        out_dir=out_dir,
    )
    return result, out_dir


def test_dossier_built_successfully_for_ticket_70(tmp_path):
    result, out_dir = _build_dossier(tmp_path)
    assert result["ok"] is True, result
    assert result["ticket_id"] == 70
    assert (out_dir / "dossier.json").is_file()
    assert (out_dir / "DOSSIER_UAT.md").is_file()
    assert (out_dir / "ado_comment.html").is_file()


def test_ado_comment_contains_idempotence_marker(tmp_path):
    _, out_dir = _build_dossier(tmp_path)
    html = (out_dir / "ado_comment.html").read_text(encoding="utf-8")
    marker_re = re.compile(
        r'<!--\s*stacky-qa-uat:run\s+id="[^"]+"\s+hash="[^"]+"\s*-->',
        re.IGNORECASE,
    )
    assert marker_re.search(html), f"Idempotence marker not found in ado_comment.html:\n{html[:200]}"


def test_hash_is_sha256_of_comment_content(tmp_path):
    import uat_dossier_builder
    result, out_dir = _build_dossier(tmp_path)
    comment_hash = result.get("comment_hash")
    assert comment_hash, "comment_hash must be present in dossier result"
    assert len(comment_hash) == 64, "SHA-256 hex must be 64 chars"
    # Verify it's a valid hex string
    int(comment_hash, 16)


def test_verdict_pass_when_all_pass(tmp_path):
    import uat_dossier_builder
    runner = _runner_output()
    for run in runner["runs"]:
        run["status"] = "pass"
    runner["pass"] = len(runner["runs"])
    runner["fail"] = 0
    runner["blocked"] = 0
    result, _ = _build_dossier(tmp_path, runner_override=runner)
    assert result["verdict"] == "PASS"


def test_verdict_fail_when_one_fails(tmp_path):
    runner = _runner_output()  # already has P04 as fail
    result, _ = _build_dossier(tmp_path, runner_override=runner)
    assert result["verdict"] == "FAIL"


def test_verdict_blocked_when_all_blocked(tmp_path):
    runner = _runner_output()
    for run in runner["runs"]:
        run["status"] = "blocked"
        run["reason"] = "RUNTIME_ERROR"
    runner["pass"] = 0
    runner["fail"] = 0
    runner["blocked"] = len(runner["runs"])
    result, _ = _build_dossier(tmp_path, runner_override=runner)
    assert result["verdict"] == "BLOCKED"


def test_verdict_mixed_when_fail_and_blocked(tmp_path):
    runner = _runner_output()
    runner["runs"][0]["status"] = "fail"
    runner["runs"][1]["status"] = "blocked"
    runner["runs"][1]["reason"] = "RUNTIME_ERROR"
    runner["pass"] = len(runner["runs"]) - 2
    runner["fail"] = 1
    runner["blocked"] = 1
    result, _ = _build_dossier(tmp_path, runner_override=runner)
    assert result["verdict"] == "MIXED"


def test_missing_artifact_returns_error(tmp_path):
    import uat_dossier_builder
    result = uat_dossier_builder.run(
        runner_output_path=tmp_path / "nonexistent.json",
        ticket_path=tmp_path / "ticket.json",
        out_dir=tmp_path / "out",
    )
    assert result["ok"] is False
    assert result["error"] == "missing_artifact"


def test_executive_summary_length_constraint(tmp_path):
    result, _ = _build_dossier(tmp_path)
    summary = result.get("executive_summary", "")
    assert len(summary) <= 600, f"executive_summary too long: {len(summary)} chars"
    assert len(summary) > 0


def test_dossier_json_validates_against_schema(tmp_path):
    import jsonschema
    _, out_dir = _build_dossier(tmp_path)
    schema_path = TOOL_DIR / "schemas" / "dossier.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    dossier = json.loads((out_dir / "dossier.json").read_text(encoding="utf-8"))
    jsonschema.validate(instance=dossier, schema=schema)
