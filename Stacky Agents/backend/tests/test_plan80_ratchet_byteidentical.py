"""Plan 80 F7 — Ratchet byte-idéntico + registro de tests (cierre y blindaje).

Casos:
  1. Byte-identidad del writer con flag externo OFF (interno ON): el JSON escrito
     tiene SOLO "stacky"; el token "codebase-memory-mcp" está ausente del archivo
     (token específico, NUNCA el genérico "mcpServers" — lección C10 del Plan 76).
  2. Todo OFF: maybe_write_mcp_config devuelve None (igual que hoy).
  3. Anti-promesa Copilot: centinela de F4 (referencia/re-afirmación).
  4. [C-RES-4] run_harness_tests.ps1 lista los 9 archivos test_plan80_*.py (sync con .sh).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

from services.stacky_mcp import maybe_write_mcp_config  # noqa: E402

_PLAN80_TEST_FILES = [
    "test_plan80_flags.py",
    "test_plan80_wiring_pure.py",
    "test_plan80_writer.py",
    "test_plan80_codex.py",
    "test_plan80_copilot.py",
    "test_plan80_savings.py",
    "test_plan80_status_shape.py",
    "test_plan80_ratchet_byteidentical.py",
    "test_plan80_routes_registered.py",
]


def test_writer_byte_identical_with_external_off(tmp_path):
    with patch("services.cli_feature_flags.mcp_enabled", return_value=True), \
         patch("services.cli_feature_flags.codebase_memory_mcp_enabled", return_value=False), \
         patch("config.config.STACKY_CODEBASE_MEMORY_MCP_BINARY_PATH", ""):
        result = maybe_write_mcp_config(
            tmp_path,
            project_name="proj",
            ticket_id=1,
            ado_id=100,
            execution_id=1,
            port=5555,
            agent_type="Business",
        )
    assert result is not None
    content = result.read_text(encoding="utf-8")
    parsed = json.loads(content)
    assert set(parsed["mcpServers"].keys()) == {"stacky"}
    assert "codebase-memory-mcp" not in content


def test_writer_all_off_returns_none(tmp_path):
    with patch("services.cli_feature_flags.mcp_enabled", return_value=False), \
         patch("services.cli_feature_flags.codebase_memory_mcp_enabled", return_value=False), \
         patch("config.config.STACKY_CODEBASE_MEMORY_MCP_BINARY_PATH", ""):
        result = maybe_write_mcp_config(
            tmp_path,
            project_name="proj",
            ticket_id=1,
            ado_id=100,
            execution_id=1,
            port=5555,
            agent_type="Business",
        )
    assert result is None


def test_anti_promise_copilot_sentinel_reference():
    bridge_path = ROOT / "copilot_bridge.py"
    content = bridge_path.read_text(encoding="utf-8")
    assert "codebase_memory_mcp_wiring" not in content
    assert "mcp-config" not in content


def test_ps1_ratchet_in_sync_with_sh():
    ps1_path = ROOT / "scripts" / "run_harness_tests.ps1"
    ps1_content = ps1_path.read_text(encoding="utf-8")
    missing = [f for f in _PLAN80_TEST_FILES if f not in ps1_content]
    assert not missing, f"Archivos test_plan80_*.py faltantes en run_harness_tests.ps1: {missing}"
