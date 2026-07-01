"""Plan 80 F3 — Codex CLI: opción 3b (log informativo, sin auto-inyección).

Casos:
  1. Con flag externo OFF, el bloque de log de Plan 80 no se ejecuta.
  2. Con flag externo ON, se emite un log informativo con "MCP externo" y "manual".
  3. Byte-identidad: con flag OFF, el string de reglas construido no contiene
     "codebase-memory-mcp".
  4. build_installation_guide("codex") (del 76) retorna guía no vacía.
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


def _maybe_log_codex_mcp_block(log, project_name):
    """Réplica 1:1 del bloque cableado en codex_cli_runner.py (Plan 80 F3),
    aislado de la sesión de DB/runner para test unitario barato."""
    from services import cli_feature_flags as cff

    if cff.codebase_memory_mcp_enabled(project_name):
        log("info", "Codex: MCP externo activado (flag ON) pero requiere config manual. Ver install-codex.md (Plan 76/80).")


def test_flag_off_no_log_emitted():
    calls = []
    with patch("config.config.STACKY_CODEBASE_MEMORY_MCP_ENABLED", False):
        _maybe_log_codex_mcp_block(lambda *a, **k: calls.append(a), "proj")
    assert not any("MCP externo" in str(c) for c in calls)


def test_flag_on_log_emitted():
    calls = []
    with patch("config.config.STACKY_CODEBASE_MEMORY_MCP_ENABLED", True), \
         patch("config.config.STACKY_CODEBASE_MEMORY_MCP_PROJECTS", ""):
        _maybe_log_codex_mcp_block(lambda *a, **k: calls.append(a), "proj")
    joined = " ".join(str(c) for c in calls)
    assert "MCP externo" in joined
    assert "manual" in joined


def test_byte_identity_rules_text_no_mcp_mention_when_off():
    from harness.run_contract import rules_text

    rules = rules_text(runtime="codex", mcp_enabled=False)
    assert "codebase-memory-mcp" not in rules


def test_install_guide_codex_not_empty():
    from services.codebase_memory_mcp_status import build_installation_guide

    guide = build_installation_guide("codex")
    assert guide and guide.strip()
