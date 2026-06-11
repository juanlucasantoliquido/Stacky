"""Tests de F2.3 (resume command wiring) y F2.1 (mcp-config writer)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_build_command_adds_resume_and_mcp():
    from services import claude_code_cli_runner as r

    cmd = r._build_command(
        model_override=None,
        mcp_config_file=Path("run/mcp-config.json"),
        resume_session_id="sess-abc",
    )
    assert "--mcp-config" in cmd
    assert "--resume" in cmd
    assert "sess-abc" in cmd
    # skip-permissions sigue activo (§5.3).
    assert "--dangerously-skip-permissions" in cmd


def test_build_command_no_resume_no_mcp_by_default():
    from services import claude_code_cli_runner as r

    cmd = r._build_command(model_override=None)
    assert "--resume" not in cmd
    assert "--mcp-config" not in cmd


def test_mcp_config_off_returns_none(tmp_path):
    from services import stacky_mcp

    # Flag OFF default → no escribe config.
    out = stacky_mcp.maybe_write_mcp_config(
        tmp_path,
        project_name="Pacifico",
        ticket_id=1,
        ado_id=206,
        execution_id=42,
        port=5050,
    )
    assert out is None
    assert not (tmp_path / "mcp-config.json").exists()


def test_mcp_config_written_when_enabled(tmp_path, monkeypatch):
    from config import config
    from services import stacky_mcp

    monkeypatch.setattr(config, "CLAUDE_CODE_CLI_MCP_ENABLED", True, raising=False)
    monkeypatch.setattr(config, "CLAUDE_CODE_CLI_MCP_PROJECTS", "", raising=False)

    out = stacky_mcp.maybe_write_mcp_config(
        tmp_path,
        project_name="Pacifico",
        ticket_id=7,
        ado_id=206,
        execution_id=42,
        port=5050,
        agent_type="functional",
    )
    assert out is not None
    cfg = json.loads(out.read_text(encoding="utf-8"))
    server = cfg["mcpServers"]["stacky"]
    assert server["args"][0].endswith("stacky_mcp_server.py")
    env = server["env"]
    assert env["STACKY_MCP_ADO_ID"] == "206"
    assert env["STACKY_MCP_TICKET_ID"] == "7"
    assert env["STACKY_MCP_EXECUTION_ID"] == "42"
    assert env["STACKY_MCP_PROJECT"] == "Pacifico"
