"""
conftest.py — pytest configuration for QA UAT Agent unit tests.

Adds the tool directory to sys.path and sets STACKY_LLM_BACKEND=mock
for all tests so no real LLM calls are made.
"""
import os
import sys
from pathlib import Path

# Add the tool root to path so all tool modules are importable
TOOL_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOL_ROOT))

# Use mock LLM for all tests unless explicitly overridden
os.environ.setdefault("STACKY_LLM_BACKEND", "mock")


def pytest_configure(config):
    """Plan 241 F5 — marker `e2e`: tests que exigen AgendaWeb arriba."""
    config.addinivalue_line(
        "markers", "e2e: requiere AgendaWeb corriendo (no se ejecuta en CI)")
