"""Plan 80 F2 — Cablear merge_external_server en maybe_write_mcp_config (Claude CLI).

Casos:
  1. Todo OFF (default) -> None, sin archivo.
  2. Solo interno ON -> mcpServers con solo "stacky" (comparación estructural).
  3. Interno ON + externo ON + binary_path -> "stacky" y "codebase-memory-mcp".
  4. Interno OFF + externo ON + binary_path -> solo "codebase-memory-mcp".
  5. Externo ON pero binary_path vacío -> degradación segura (como externo OFF).
  6. Externo ON pero proyecto no en allowlist -> no se inyecta.
  7. El bloque "stacky" conserva su env/command tras el merge.
  8. Catch monolítico suficiente: si write_text lanza, el writer propaga (no traga).
  9. Overhead de serialización < 5 ms con 2 servers vs 1.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

from services.stacky_mcp import maybe_write_mcp_config  # noqa: E402


def _base_kwargs():
    return dict(
        project_name="proj",
        ticket_id=1,
        ado_id=100,
        execution_id=1,
        port=5555,
        agent_type="Business",
    )


def test_all_off_returns_none(tmp_path):
    with patch("services.cli_feature_flags.mcp_enabled", return_value=False), \
         patch("services.cli_feature_flags.codebase_memory_mcp_enabled", return_value=False), \
         patch("config.config.STACKY_CODEBASE_MEMORY_MCP_BINARY_PATH", ""):
        result = maybe_write_mcp_config(tmp_path, **_base_kwargs())
    assert result is None
    assert not (tmp_path / "mcp-config.json").exists()


def test_only_internal_on_matches_historical_shape(tmp_path):
    with patch("services.cli_feature_flags.mcp_enabled", return_value=True), \
         patch("services.cli_feature_flags.codebase_memory_mcp_enabled", return_value=False), \
         patch("config.config.STACKY_CODEBASE_MEMORY_MCP_BINARY_PATH", ""):
        result = maybe_write_mcp_config(tmp_path, **_base_kwargs())
    assert result is not None
    actual = json.loads(result.read_text(encoding="utf-8"))
    assert set(actual["mcpServers"].keys()) == {"stacky"}
    assert actual["mcpServers"]["stacky"]["command"] == sys.executable
    assert "codebase-memory-mcp" not in actual["mcpServers"]


def test_both_on_with_binary_path(tmp_path):
    with patch("services.cli_feature_flags.mcp_enabled", return_value=True), \
         patch("services.cli_feature_flags.codebase_memory_mcp_enabled", return_value=True), \
         patch("config.config.STACKY_CODEBASE_MEMORY_MCP_BINARY_PATH", "C:\\tools\\cbm.exe"):
        result = maybe_write_mcp_config(tmp_path, **_base_kwargs())
    actual = json.loads(result.read_text(encoding="utf-8"))
    assert set(actual["mcpServers"].keys()) == {"stacky", "codebase-memory-mcp"}
    assert actual["mcpServers"]["codebase-memory-mcp"]["command"] == "C:\\tools\\cbm.exe"


def test_internal_off_external_on(tmp_path):
    with patch("services.cli_feature_flags.mcp_enabled", return_value=False), \
         patch("services.cli_feature_flags.codebase_memory_mcp_enabled", return_value=True), \
         patch("config.config.STACKY_CODEBASE_MEMORY_MCP_BINARY_PATH", "C:\\tools\\cbm.exe"):
        result = maybe_write_mcp_config(tmp_path, **_base_kwargs())
    assert result is not None
    actual = json.loads(result.read_text(encoding="utf-8"))
    assert set(actual["mcpServers"].keys()) == {"codebase-memory-mcp"}


def test_external_on_but_no_binary_path_degrades_safely(tmp_path):
    with patch("services.cli_feature_flags.mcp_enabled", return_value=True), \
         patch("services.cli_feature_flags.codebase_memory_mcp_enabled", return_value=True), \
         patch("config.config.STACKY_CODEBASE_MEMORY_MCP_BINARY_PATH", ""):
        result = maybe_write_mcp_config(tmp_path, **_base_kwargs())
    actual = json.loads(result.read_text(encoding="utf-8"))
    assert set(actual["mcpServers"].keys()) == {"stacky"}


def test_external_on_but_project_not_in_allowlist(tmp_path):
    # codebase_memory_mcp_enabled ya encapsula la allowlist; simulamos "no matchea".
    with patch("services.cli_feature_flags.mcp_enabled", return_value=True), \
         patch("services.cli_feature_flags.codebase_memory_mcp_enabled", return_value=False), \
         patch("config.config.STACKY_CODEBASE_MEMORY_MCP_BINARY_PATH", "C:\\tools\\cbm.exe"):
        result = maybe_write_mcp_config(tmp_path, **_base_kwargs())
    actual = json.loads(result.read_text(encoding="utf-8"))
    assert set(actual["mcpServers"].keys()) == {"stacky"}


def test_stacky_block_preserves_env_and_command(tmp_path):
    with patch("services.cli_feature_flags.mcp_enabled", return_value=True), \
         patch("services.cli_feature_flags.codebase_memory_mcp_enabled", return_value=True), \
         patch("config.config.STACKY_CODEBASE_MEMORY_MCP_BINARY_PATH", "C:\\tools\\cbm.exe"):
        result = maybe_write_mcp_config(tmp_path, **_base_kwargs())
    actual = json.loads(result.read_text(encoding="utf-8"))
    stacky_block = actual["mcpServers"]["stacky"]
    assert "command" in stacky_block
    assert "env" in stacky_block
    assert stacky_block["env"]["STACKY_MCP_EXECUTION_ID"] == "1"


def test_write_text_failure_propagates(tmp_path):
    with patch("services.cli_feature_flags.mcp_enabled", return_value=True), \
         patch("services.cli_feature_flags.codebase_memory_mcp_enabled", return_value=False), \
         patch("config.config.STACKY_CODEBASE_MEMORY_MCP_BINARY_PATH", ""), \
         patch("pathlib.Path.write_text", side_effect=OSError("disk full")):
        try:
            maybe_write_mcp_config(tmp_path, **_base_kwargs())
            assert False, "debería haber lanzado OSError"
        except OSError:
            pass


def test_serialization_overhead_under_5ms(tmp_path):
    dir_one = tmp_path / "one"
    dir_two = tmp_path / "two"
    dir_one.mkdir()
    dir_two.mkdir()

    with patch("services.cli_feature_flags.mcp_enabled", return_value=True), \
         patch("services.cli_feature_flags.codebase_memory_mcp_enabled", return_value=False), \
         patch("config.config.STACKY_CODEBASE_MEMORY_MCP_BINARY_PATH", ""):
        start = time.perf_counter()
        maybe_write_mcp_config(dir_one, **_base_kwargs())
        t_one = time.perf_counter() - start

    with patch("services.cli_feature_flags.mcp_enabled", return_value=True), \
         patch("services.cli_feature_flags.codebase_memory_mcp_enabled", return_value=True), \
         patch("config.config.STACKY_CODEBASE_MEMORY_MCP_BINARY_PATH", "C:\\tools\\cbm.exe"):
        start = time.perf_counter()
        maybe_write_mcp_config(dir_two, **_base_kwargs())
        t_two = time.perf_counter() - start

    assert (t_two - t_one) < 0.005
