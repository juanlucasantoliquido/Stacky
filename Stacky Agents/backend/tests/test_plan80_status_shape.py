"""Plan 80 F6 — no-regresión del shape de GET /api/codebase-memory-mcp/status (Plan 76)
+ nueva clave "wiring".

Casos:
  1. Las 5 claves del 76 siguen presentes: enabled, installed_hint, flag, external_repo, guides.
  2. La clave nueva "wiring" tiene sub-claves binary_path_set (bool) e injects_external (bool).
  3. Con BINARY_PATH="" (default), ambas sub-claves son False.
  4. Con BINARY_PATH seteado y flag master ON, ambas sub-claves son True.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")


def _client():
    from app import create_app

    app = create_app()
    return app.test_client()


def test_status_keeps_plan76_keys():
    client = _client()
    resp = client.get("/api/codebase-memory-mcp/status")
    assert resp.status_code == 200
    body = resp.get_json()
    for key in ("enabled", "installed_hint", "flag", "external_repo", "guides"):
        assert key in body, f"clave faltante: {key}"


def test_status_has_wiring_subkeys():
    client = _client()
    resp = client.get("/api/codebase-memory-mcp/status")
    body = resp.get_json()
    assert "wiring" in body
    assert isinstance(body["wiring"]["binary_path_set"], bool)
    assert isinstance(body["wiring"]["injects_external"], bool)


def test_status_wiring_false_by_default():
    with patch("config.config.STACKY_CODEBASE_MEMORY_MCP_BINARY_PATH", ""):
        client = _client()
        resp = client.get("/api/codebase-memory-mcp/status")
        body = resp.get_json()
    assert body["wiring"]["binary_path_set"] is False
    assert body["wiring"]["injects_external"] is False


def test_status_wiring_true_when_configured():
    with patch("config.config.STACKY_CODEBASE_MEMORY_MCP_BINARY_PATH", "C:\\x.exe"), \
         patch("config.config.STACKY_CODEBASE_MEMORY_MCP_ENABLED", True), \
         patch("config.Config.STACKY_CODEBASE_MEMORY_MCP_ENABLED", True):
        client = _client()
        resp = client.get("/api/codebase-memory-mcp/status")
        body = resp.get_json()
    assert body["wiring"]["binary_path_set"] is True
    assert body["wiring"]["injects_external"] is True
