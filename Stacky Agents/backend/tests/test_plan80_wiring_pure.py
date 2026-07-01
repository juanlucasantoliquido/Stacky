"""Plan 80 F1 — Funciones puras de merge del server MCP externo codebase-memory-mcp.

Casos:
  1. build_external_server_entry("") -> None.
  2. build_external_server_entry("   ") -> None.
  3. build_external_server_entry(path) -> dict con command/args.
  3b. Path traversal: paths con ".." -> None.
  4. merge_external_server external_enabled=False -> idéntico al input.
  5. merge_external_server external_enabled=True, binary_path="" -> idéntico al input.
  6. merge_external_server ambos ON -> tiene "stacky" y "codebase-memory-mcp".
  7. No-mutación del dict base.
  8. Pureza: sin red (monkeypatch socket.socket).
  9. EXTERNAL_MCP_KEY == "codebase-memory-mcp" y != "stacky".
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

from services.codebase_memory_mcp_wiring import (  # noqa: E402
    EXTERNAL_MCP_KEY,
    build_external_server_entry,
    merge_external_server,
)


def test_build_entry_empty_string():
    assert build_external_server_entry("") is None


def test_build_entry_whitespace():
    assert build_external_server_entry("   ") is None


def test_build_entry_valid_path():
    entry = build_external_server_entry("C:\\tools\\cbm.exe")
    assert entry == {"command": "C:\\tools\\cbm.exe", "args": []}


def test_build_entry_rejects_path_traversal():
    assert build_external_server_entry("C:\\tools\\..\\cbm.exe") is None
    assert build_external_server_entry("..\\cbm.exe") is None


def test_merge_external_disabled_returns_unchanged():
    base = {"stacky": {"command": "x"}}
    result = merge_external_server(base, external_enabled=False, binary_path="C:\\x.exe")
    assert result == base
    assert EXTERNAL_MCP_KEY not in result


def test_merge_external_enabled_but_no_binary_path():
    base = {"stacky": {"command": "x"}}
    result = merge_external_server(base, external_enabled=True, binary_path="")
    assert result == base
    assert EXTERNAL_MCP_KEY not in result


def test_merge_external_enabled_with_binary_path():
    base = {"stacky": {"command": "x"}}
    result = merge_external_server(base, external_enabled=True, binary_path="C:\\x.exe")
    assert "stacky" in result
    assert EXTERNAL_MCP_KEY in result
    assert result["stacky"] == {"command": "x"}


def test_merge_does_not_mutate_base():
    base = {"stacky": {"command": "x"}}
    merge_external_server(base, external_enabled=True, binary_path="C:\\x.exe")
    assert base == {"stacky": {"command": "x"}}
    assert len(base) == 1


def test_pure_functions_no_network(monkeypatch):
    def _raise(*args, **kwargs):
        raise AssertionError("no debería abrir sockets")

    monkeypatch.setattr("socket.socket", _raise)
    assert build_external_server_entry("C:\\x.exe") is not None
    result = merge_external_server({"stacky": {}}, external_enabled=True, binary_path="C:\\x.exe")
    assert EXTERNAL_MCP_KEY in result


def test_external_mcp_key_contract():
    assert EXTERNAL_MCP_KEY == "codebase-memory-mcp"
    assert EXTERNAL_MCP_KEY != "stacky"
