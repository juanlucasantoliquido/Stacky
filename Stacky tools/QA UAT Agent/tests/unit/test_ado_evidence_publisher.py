"""Unit tests for ado_evidence_publisher.py (B8).

CRITICAL TEST: test_no_state_subcommand_in_codebase
  Scans all uat_*.py and ado_evidence_publisher.py source files for
  forbidden 'ado.py state' or 'update_state' usage.
"""
import json
import os
import re
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
os.environ.setdefault("STACKY_LLM_BACKEND", "mock")

FIXTURES = Path(__file__).parent.parent / "fixtures"
TOOL_DIR = Path(__file__).parent.parent.parent


def _make_dossier(tmp_path: Path, verdict: str = "FAIL", same_hash: bool = False) -> Path:
    """Create a minimal dossier.json + ado_comment.html for testing."""
    dossier_dir = tmp_path / "dossier"
    dossier_dir.mkdir(parents=True, exist_ok=True)

    run_id = "uat-70-20260502143200"
    # Use a fixed comment hash for idempotence tests
    html_no_marker = (
        "<html><body><table><tr><td>P01</td><td>pass</td></tr></table></body></html>"
    )
    import hashlib
    comment_hash = hashlib.sha256(html_no_marker.encode("utf-8")).hexdigest()

    if same_hash:
        # The dossier hash will match what the mock ADO returns
        pass

    html_with_marker = (
        f'<!-- stacky-qa-uat:run id="{run_id}" hash="{comment_hash}" -->\n'
        + html_no_marker
    )

    dossier = {
        "ok": True,
        "schema_version": "qa-uat-dossier/1.0",
        "run_id": run_id,
        "ticket_id": 70,
        "ticket_title": "RF-003",
        "screen": "FrmAgenda.aspx",
        "verdict": verdict,
        "executive_summary": "Test summary",
        "context": {"total": 6, "pass": 5, "fail": 1, "blocked": 0, "environment": "qa", "agent_version": "1.0.0"},
        "scenarios": [],
        "failures": [],
        "recommendation_for_human_qa": [],
        "next_steps": [],
        "generated_at": "2026-05-02T14:32:00Z",
        "comment_hash": comment_hash,
        "meta": {"tool": "uat_dossier_builder", "version": "1.0.0"},
    }

    (dossier_dir / "dossier.json").write_text(json.dumps(dossier), encoding="utf-8")
    (dossier_dir / "ado_comment.html").write_text(html_with_marker, encoding="utf-8")

    return dossier_dir / "dossier.json", comment_hash


def _mock_ado_comments_empty(ticket_id: int, ado_path) -> dict:
    return {}


def _mock_ado_comment_success() -> dict:
    return {"ok": True, "comment_id": 99}


def test_dry_run_generates_preview_without_touching_ado(tmp_path):
    import ado_evidence_publisher
    dossier_path, _ = _make_dossier(tmp_path)
    with patch("ado_evidence_publisher._post_comment") as mock_post:
        result = ado_evidence_publisher.run(
            ticket_id=70,
            dossier_path=dossier_path,
            mode="dry-run",
        )
    mock_post.assert_not_called()
    assert result["ok"] is True
    assert result["mode"] == "dry-run"
    assert result["action"] == "preview_only"


def test_first_publish_creates_comment(tmp_path):
    import ado_evidence_publisher
    dossier_path, _ = _make_dossier(tmp_path)
    with patch("ado_evidence_publisher._get_existing_comment", return_value={}):
        with patch("ado_evidence_publisher._post_comment", return_value={"ok": True}):
            result = ado_evidence_publisher.run(
                ticket_id=70,
                dossier_path=dossier_path,
                mode="publish",
            )
    assert result["ok"] is True
    assert result["action"] == "created"


def test_second_publish_same_hash_skipped_unchanged(tmp_path):
    import ado_evidence_publisher
    dossier_path, comment_hash = _make_dossier(tmp_path, same_hash=True)
    # Mock ADO returns same hash → skip
    with patch("ado_evidence_publisher._get_existing_comment",
               return_value={"run_id": "uat-70-old", "hash": comment_hash}):
        with patch("ado_evidence_publisher._post_comment") as mock_post:
            result = ado_evidence_publisher.run(
                ticket_id=70,
                dossier_path=dossier_path,
                mode="publish",
            )
    mock_post.assert_not_called()
    assert result["action"] == "skipped_unchanged"


def test_second_publish_different_hash_updated(tmp_path):
    import ado_evidence_publisher
    dossier_path, _ = _make_dossier(tmp_path)
    # ADO has a different hash → must update
    with patch("ado_evidence_publisher._get_existing_comment",
               return_value={"run_id": "uat-70-old", "hash": "different_hash_abc123"}):
        with patch("ado_evidence_publisher._post_comment", return_value={"ok": True}):
            result = ado_evidence_publisher.run(
                ticket_id=70,
                dossier_path=dossier_path,
                mode="publish",
            )
    assert result["action"] == "updated"


def test_ado_manager_failure_returns_error_dossier_stays(tmp_path):
    import ado_evidence_publisher
    dossier_path, _ = _make_dossier(tmp_path)
    with patch("ado_evidence_publisher._get_existing_comment", return_value={}):
        with patch("ado_evidence_publisher._post_comment",
                   return_value={"ok": False, "message": "ADO unavailable"}):
            result = ado_evidence_publisher.run(
                ticket_id=70,
                dossier_path=dossier_path,
                mode="publish",
            )
    assert result["ok"] is False
    assert result["error"] == "ado_manager_failure"
    # dossier.json must still exist
    assert dossier_path.is_file()


def test_audit_log_written_on_every_invocation(tmp_path):
    import ado_evidence_publisher
    dossier_path, _ = _make_dossier(tmp_path)
    audit_dir = tmp_path / "audit"
    with patch.object(ado_evidence_publisher, "_AUDIT_DIR", audit_dir):
        # dry-run invocation
        ado_evidence_publisher.run(ticket_id=70, dossier_path=dossier_path, mode="dry-run")
        # publish invocation
        with patch("ado_evidence_publisher._get_existing_comment", return_value={}):
            with patch("ado_evidence_publisher._post_comment", return_value={"ok": True}):
                ado_evidence_publisher.run(ticket_id=70, dossier_path=dossier_path, mode="publish")

    log_files = list(audit_dir.glob("*.jsonl"))
    assert len(log_files) >= 1
    rows = log_files[0].read_text(encoding="utf-8").strip().split("\n")
    assert len(rows) >= 2, "Expected at least 2 audit rows (1 dry-run + 1 publish)"


def test_missing_dossier_returns_error(tmp_path):
    import ado_evidence_publisher
    result = ado_evidence_publisher.run(
        ticket_id=70,
        dossier_path=tmp_path / "nonexistent_dossier.json",
        mode="dry-run",
    )
    assert result["ok"] is False
    assert result["error"] == "missing_dossier"


def test_marker_not_found_returns_error(tmp_path):
    import ado_evidence_publisher
    # Create dossier.json + ado_comment.html WITHOUT the marker
    dossier_dir = tmp_path / "dossier"
    dossier_dir.mkdir()
    dossier = {
        "ok": True, "schema_version": "qa-uat-dossier/1.0", "run_id": "550e8400-e29b-41d4-a716-446655440000",
        "ticket_id": 70, "ticket_title": "t", "screen": "FrmAgenda.aspx", "verdict": "PASS",
        "executive_summary": "s",
        "context": {"environment": "qa", "agent_version": "1.0.0"},
        "scenarios": [], "failures": [],
        "recommendation_for_human_qa": [], "next_steps": [], "generated_at": "2026-01-01T00:00:00Z",
        "comment_hash": "abc", "meta": {"tool": "uat_dossier_builder", "version": "1.0.0"},
    }
    (dossier_dir / "dossier.json").write_text(json.dumps(dossier), encoding="utf-8")
    # HTML without marker
    (dossier_dir / "ado_comment.html").write_text("<html>no marker here</html>", encoding="utf-8")
    result = ado_evidence_publisher.run(
        ticket_id=70,
        dossier_path=dossier_dir / "dossier.json",
        mode="dry-run",
    )
    assert result["ok"] is False
    assert result["error"] == "marker_not_found"


def _make_dossier_with_steps(tmp_path: Path) -> tuple:
    """Build a dossier whose ado_comment.html has ATTACH tokens + steps[].

    Returns (dossier_path, png_paths_by_token).
    """
    dossier_dir = tmp_path / "dossier"
    dossier_dir.mkdir(parents=True, exist_ok=True)
    # Create dummy PNGs (minimum 1-byte; ado.py treats them as binary blobs)
    png_a = dossier_dir / "step_00_setup.png"
    png_b = dossier_dir / "step_01_after.png"
    png_a.write_bytes(b"\x89PNG_dummy_a")
    png_b.write_bytes(b"\x89PNG_dummy_b")

    run_id = "uat-70-attachtest"
    html_no_marker = (
        "<html><body>"
        '<img src="{{ATTACH:P01:step_00_setup.png}}" alt="setup"/>'
        '<img src="{{ATTACH:P01:step_01_after.png}}" alt="after"/>'
        "</body></html>"
    )
    import hashlib
    comment_hash = hashlib.sha256(html_no_marker.encode("utf-8")).hexdigest()
    html = (
        f'<!-- stacky-qa-uat:run id="{run_id}" hash="{comment_hash}" -->\n'
        + html_no_marker
    )

    dossier = {
        "ok": True,
        "schema_version": "qa-uat-dossier/1.0",
        "run_id": run_id,
        "ticket_id": 70,
        "ticket_title": "RF-003",
        "screen": "FrmAgenda.aspx",
        "verdict": "PASS",
        "executive_summary": "test",
        "context": {"environment": "qa", "agent_version": "1.0.0"},
        "scenarios": [
            {
                "scenario_id": "P01",
                "titulo": "Title P01",
                "status": "pass",
                "duration_ms": 100,
                "artifacts": {"screenshots": [str(png_a), str(png_b)]},
                "assertion_failures": [],
                "steps": [
                    {
                        "screenshot_name": "step_00_setup.png",
                        "screenshot_path": str(png_a),
                        "step_index": "setup",
                        "description": "Setup",
                        "description_source": "deterministic",
                        "attachment_token": "{{ATTACH:P01:step_00_setup.png}}",
                    },
                    {
                        "screenshot_name": "step_01_after.png",
                        "screenshot_path": str(png_b),
                        "step_index": 1,
                        "description": "Click",
                        "description_source": "deterministic",
                        "attachment_token": "{{ATTACH:P01:step_01_after.png}}",
                    },
                ],
            }
        ],
        "failures": [],
        "recommendation_for_human_qa": [],
        "next_steps": [],
        "generated_at": "2026-05-02T14:32:00Z",
        "comment_hash": comment_hash,
        "meta": {"tool": "uat_dossier_builder", "version": "1.0.0"},
    }

    (dossier_dir / "dossier.json").write_text(json.dumps(dossier), encoding="utf-8")
    (dossier_dir / "ado_comment.html").write_text(html, encoding="utf-8")
    return dossier_dir / "dossier.json", {
        "P01:step_00_setup.png": str(png_a),
        "P01:step_01_after.png": str(png_b),
    }


def test_publish_uploads_attachments_and_replaces_tokens(tmp_path):
    """Each {{ATTACH:...}} token should be replaced by the URL returned by
    `ado.py attach`, and _post_comment should receive the rewritten HTML."""
    import ado_evidence_publisher
    dossier_path, png_map = _make_dossier_with_steps(tmp_path)

    # Track each attach call to fabricate distinct URLs
    upload_results = {
        "step_00_setup.png": {
            "ok": True,
            "result": {"id": "att-1", "url": "https://ado.example/att-1"},
        },
        "step_01_after.png": {
            "ok": True,
            "result": {"id": "att-2", "url": "https://ado.example/att-2"},
        },
    }

    def fake_attach(*, ticket_id, file_path, upload_name, comment, ado_path):
        # The screenshot filename is the second part of upload_name "P01_<file>"
        filename = file_path.name
        assert filename in upload_results
        return upload_results[filename]

    posted_html_holder = {}

    def fake_post(ticket_id, html, ado_path):
        posted_html_holder["html"] = html
        return {"ok": True, "result": {"id": 999, "text": html}}

    with patch("ado_evidence_publisher._get_existing_comment", return_value={}):
        with patch("ado_evidence_publisher._attach_file", side_effect=fake_attach):
            with patch("ado_evidence_publisher._post_comment", side_effect=fake_post):
                result = ado_evidence_publisher.run(
                    ticket_id=70,
                    dossier_path=dossier_path,
                    mode="publish",
                    attach_screenshots=True,
                )

    assert result["ok"] is True
    assert result["action"] == "created"
    assert result["attachments"]["uploaded"] == 2
    # No tokens left in the posted HTML
    posted = posted_html_holder["html"]
    assert "{{ATTACH:" not in posted
    assert "https://ado.example/att-1" in posted
    assert "https://ado.example/att-2" in posted


def test_publish_aborts_when_all_uploads_fail(tmp_path):
    """If all attachment uploads fail, the publisher must abort instead of
    posting broken image references."""
    import ado_evidence_publisher
    dossier_path, _ = _make_dossier_with_steps(tmp_path)

    with patch("ado_evidence_publisher._get_existing_comment", return_value={}):
        with patch("ado_evidence_publisher._attach_file",
                   return_value={"ok": False, "message": "ado offline"}):
            with patch("ado_evidence_publisher._post_comment") as mock_post:
                result = ado_evidence_publisher.run(
                    ticket_id=70,
                    dossier_path=dossier_path,
                    mode="publish",
                    attach_screenshots=True,
                )
    mock_post.assert_not_called()
    assert result["ok"] is False
    assert result["error"] == "attachment_upload_failed"


def test_no_attach_flag_preserves_legacy_behavior(tmp_path):
    """With attach_screenshots=False, tokens are left intact."""
    import ado_evidence_publisher
    dossier_path, _ = _make_dossier_with_steps(tmp_path)

    posted = {}

    def fake_post(ticket_id, html, ado_path):
        posted["html"] = html
        return {"ok": True, "result": {"id": 1}}

    with patch("ado_evidence_publisher._get_existing_comment", return_value={}):
        with patch("ado_evidence_publisher._attach_file") as mock_attach:
            with patch("ado_evidence_publisher._post_comment", side_effect=fake_post):
                result = ado_evidence_publisher.run(
                    ticket_id=70,
                    dossier_path=dossier_path,
                    mode="publish",
                    attach_screenshots=False,
                )
    mock_attach.assert_not_called()
    # Tokens remain intact (legacy path)
    assert "{{ATTACH:P01:" in posted["html"]
    assert result["ok"] is True


def test_replace_previous_deletes_old_comment(tmp_path):
    """When --replace-previous is set and a Stacky comment exists, delete it."""
    import ado_evidence_publisher
    dossier_path, _ = _make_dossier_with_steps(tmp_path)

    existing = {"run_id": "old-run", "hash": "different_hash", "comment_id": 555}

    deleted: list[int] = []

    def fake_delete(ticket_id, comment_id, ado_path):
        deleted.append(comment_id)
        return True

    def fake_attach(*, ticket_id, file_path, upload_name, comment, ado_path):
        return {"ok": True, "result": {"id": "x", "url": "https://ado.example/x"}}

    with patch("ado_evidence_publisher._get_existing_comment", return_value=existing):
        with patch("ado_evidence_publisher._delete_comment", side_effect=fake_delete):
            with patch("ado_evidence_publisher._attach_file", side_effect=fake_attach):
                with patch("ado_evidence_publisher._post_comment",
                           return_value={"ok": True, "result": {"id": 1000}}):
                    result = ado_evidence_publisher.run(
                        ticket_id=70,
                        dossier_path=dossier_path,
                        mode="publish",
                        attach_screenshots=True,
                        replace_previous=True,
                    )
    assert deleted == [555]
    assert result["deleted_previous"] is True
    # After deleting the previous comment, this counts as 'created', not 'updated'
    assert result["action"] == "created"


def test_no_state_subcommand_in_codebase():
    """
    CRITICAL SECURITY TEST.
    Scan all uat_*.py and ado_evidence_publisher.py source files for
    forbidden 'ado.py state' or 'update_state' subcommand usage.
    This test MUST NEVER be removed or weakened.
    """
    import ast as _ast

    # Match subprocess-style calls like: ["ado.py", "state"] or update_state()
    # Does NOT match dict key access like .get("state") or field assignments
    forbidden = re.compile(
        r'(?:\"ado\.py\"\s*,\s*\"state\"|'
        r"'ado\.py'\s*,\s*'state'|"
        r'update_state\s*\()',
        re.IGNORECASE,
    )
    files_to_scan = list(TOOL_DIR.glob("uat_*.py")) + [TOOL_DIR / "ado_evidence_publisher.py"]

    violations = []
    for path in files_to_scan:
        if not path.is_file():
            continue
        source = path.read_text(encoding="utf-8")
        lines = source.splitlines()

        # Use AST to identify lines that are inside string literals (docstrings)
        try:
            tree = _ast.parse(source)
        except SyntaxError:
            continue

        docstring_lines: set = set()
        for node in _ast.walk(tree):
            if isinstance(node, _ast.Constant) and isinstance(node.value, str):
                start = getattr(node, "lineno", None)
                end = getattr(node, "end_lineno", start)
                if start and end:
                    for ln in range(start, end + 1):
                        docstring_lines.add(ln)

        for lineno, line in enumerate(lines, start=1):
            stripped = line.strip()
            # Skip pure comment lines
            if stripped.startswith("#"):
                continue
            # Skip lines that are inside string literals/docstrings
            if lineno in docstring_lines:
                continue
            if forbidden.search(line):
                violations.append(f"{path.name}:{lineno}: {line.strip()}")

    assert not violations, (
        "SECURITY VIOLATION: Forbidden 'ado.py state' subcommand or 'update_state' found in:\n"
        + "\n".join(violations)
    )
