"""Plan 80 F4 — Copilot Pro: sin auto-inyección, guía manual (centinela anti-promesa).

Casos:
  1. build_installation_guide("copilot_pro") retorna guía no vacía que menciona la
     clave namespaced "codebase-memory-mcp" (contrato Plan 76).
  2. Centinela: copilot_bridge.py NO contiene "codebase_memory_mcp_wiring" ni
     "mcp-config" — nadie agregó auto-inyección frágil a Copilot.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")


def test_install_guide_copilot_pro_mentions_namespaced_key():
    from services.codebase_memory_mcp_status import build_installation_guide

    guide = build_installation_guide("copilot_pro")
    assert guide and guide.strip()
    assert "codebase-memory-mcp" in guide


def test_copilot_bridge_has_no_auto_injection():
    bridge_path = ROOT / "copilot_bridge.py"
    content = bridge_path.read_text(encoding="utf-8")
    assert "codebase_memory_mcp_wiring" not in content
    assert "mcp-config" not in content
