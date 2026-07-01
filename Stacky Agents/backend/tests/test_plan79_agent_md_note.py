"""Plan 79 — F7: nota de estados deterministas presente en los .agent.md (3 runtimes)."""
from __future__ import annotations

import os
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
AGENT_FILES = [
    BACKEND_ROOT / "Stacky" / "agents" / "FunctionalAnalyst.agent.md",
    BACKEND_ROOT / "Stacky" / "agents" / "TechnicalAnalyst.v2.agent.md",
    BACKEND_ROOT / "Stacky" / "agents" / "Developer.agent.md",
]


def test_agent_md_files_exist():
    for path in AGENT_FILES:
        assert path.is_file(), f"No existe {path}"


def test_agent_md_contains_deterministic_states_note():
    for path in AGENT_FILES:
        text = path.read_text(encoding="utf-8")
        assert "estados deterministas" in text.lower(), f"{path.name} no menciona 'estados deterministas'"
