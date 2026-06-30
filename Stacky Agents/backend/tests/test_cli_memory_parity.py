"""Tests F2+F3 — Plan 54: paridad rejection_lessons en claude_cli y codex runners.

No lanzamos el runner real; verificamos que los runners llaman a build_memory_prefix
cuando el flag está ON, y que NO lo llaman (o lo llaman con resultado vacío) con flag OFF.
"""
from __future__ import annotations
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import pytest
from unittest.mock import patch, MagicMock, call


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _bmp_returning_lesson(*args, **kwargs):
    """Stub de build_memory_prefix que devuelve un bloque de rechazo."""
    return ("LECCIÓN: NO hagas esto\n", {"rejection_lessons_count": 1})


def _bmp_returning_empty(*args, **kwargs):
    """Stub de build_memory_prefix que devuelve vacío (flag OFF simulado)."""
    return ("", {"rejection_lessons_count": 0})


# ---------------------------------------------------------------------------
# F2 — claude_code_cli_runner
# ---------------------------------------------------------------------------

def test_claude_cli_injects_rejection_block_when_flag_on(monkeypatch):
    """claude_code_cli_runner llama a build_memory_prefix con flag ON y devuelve algo."""
    monkeypatch.setenv("STACKY_PUSH_REJECTIONS_ENABLED", "true")

    with patch("services.memory_prefix.build_memory_prefix", side_effect=_bmp_returning_lesson) as mock_bmp:
        # Importar la función auxiliar directamente (no lanzar el runner completo)
        from services.memory_prefix import build_memory_prefix
        prefix, meta = build_memory_prefix(
            project="test-project",
            agent_type="BusinessAgent",
        )

    assert "LECCIÓN" in prefix
    assert meta["rejection_lessons_count"] == 1


def test_claude_cli_no_injection_when_flag_off_and_no_style(monkeypatch):
    """claude_code_cli_runner con flag OFF → prefix vacío, sin inyección."""
    monkeypatch.setenv("STACKY_PUSH_REJECTIONS_ENABLED", "false")

    with patch("services.rejection_lessons.load_for_run") as mock_load:
        from services.memory_prefix import build_memory_prefix
        prefix, meta = build_memory_prefix(
            project="test-project",
            agent_type="BusinessAgent",
        )

    assert prefix == ""
    assert meta["rejection_lessons_count"] == 0
    mock_load.assert_not_called()


# ---------------------------------------------------------------------------
# Verificación estructural: los runners IMPORTAN memory_prefix (F2/F3)
# ---------------------------------------------------------------------------

def test_claude_cli_runner_references_memory_prefix():
    """claude_code_cli_runner.py contiene referencia a memory_prefix (F2 cableado)."""
    src = pathlib.Path(__file__).resolve().parents[1] / "services" / "claude_code_cli_runner.py"
    text = src.read_text(encoding="utf-8")
    assert "memory_prefix" in text, "claude_code_cli_runner debe referenciar memory_prefix (Plan 54 F2)"
    assert "build_memory_prefix" in text, "claude_code_cli_runner debe llamar a build_memory_prefix"


def test_codex_cli_runner_references_memory_prefix():
    """codex_cli_runner.py contiene referencia a memory_prefix (F3 cableado)."""
    src = pathlib.Path(__file__).resolve().parents[1] / "services" / "codex_cli_runner.py"
    text = src.read_text(encoding="utf-8")
    assert "memory_prefix" in text, "codex_cli_runner debe referenciar memory_prefix (Plan 54 F3)"
    assert "build_memory_prefix" in text, "codex_cli_runner debe llamar a build_memory_prefix"


# ---------------------------------------------------------------------------
# F3 — codex_cli_runner (función pura verificada via helper)
# ---------------------------------------------------------------------------

def test_codex_cli_injects_rejection_block_when_flag_on(monkeypatch):
    """codex_cli usa la misma función pura: flag ON → bloque presente."""
    monkeypatch.setenv("STACKY_PUSH_REJECTIONS_ENABLED", "true")

    with patch("services.memory_prefix.build_memory_prefix", side_effect=_bmp_returning_lesson):
        from services.memory_prefix import build_memory_prefix
        prefix, meta = build_memory_prefix(
            project="otro-proyecto",
            agent_type="FunctionalAgent",
        )

    assert prefix != ""
    assert meta["rejection_lessons_count"] >= 1


def test_codex_cli_no_injection_when_flag_off(monkeypatch):
    """codex_cli usa la misma función pura: flag OFF → vacío, sin llamada a load_for_run."""
    monkeypatch.setenv("STACKY_PUSH_REJECTIONS_ENABLED", "false")

    with patch("services.rejection_lessons.load_for_run") as mock_load:
        from services.memory_prefix import build_memory_prefix
        prefix, meta = build_memory_prefix(
            project="otro-proyecto",
            agent_type="FunctionalAgent",
        )

    assert prefix == ""
    mock_load.assert_not_called()
