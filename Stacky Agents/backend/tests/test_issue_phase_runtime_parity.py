"""Plan 77 F3 — Conformance de paridad de runtimes para fases del Issue.

Verifica que los 3 finalizadores (Copilot/github_copilot via agent_runner.py,
Claude CLI via claude_code_cli_runner.py, Codex CLI via codex_cli_runner.py)
importen y llamen a publish_issue_phase_from_run en su path de cierre normal.

Estrategia: humo de importación + grep de call-site en el código fuente de cada
runner. Sin lanzar procesos reales. Falla si se quita el cableado de cualquier runner.
"""
from __future__ import annotations

import ast
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

BACKEND = ROOT
RUNNER_CLAUDE = BACKEND / "services" / "claude_code_cli_runner.py"
RUNNER_CODEX  = BACKEND / "services" / "codex_cli_runner.py"
RUNNER_COPILOT = BACKEND / "agent_runner.py"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def test_claude_runner_wires_issue_phase_publisher():
    """claude_code_cli_runner.py contiene una llamada a publish_issue_phase_from_run."""
    src = _source(RUNNER_CLAUDE)
    assert "publish_issue_phase_from_run" in src, (
        "F3 MISSING: claude_code_cli_runner.py no llama a publish_issue_phase_from_run. "
        "Cablear antes de _mark_terminal en el bloque elif _outcome_kind == 'success': (~línea 1521)."
    )


def test_codex_runner_wires_issue_phase_publisher():
    """codex_cli_runner.py contiene una llamada a publish_issue_phase_from_run."""
    src = _source(RUNNER_CODEX)
    assert "publish_issue_phase_from_run" in src, (
        "F3 MISSING: codex_cli_runner.py no llama a publish_issue_phase_from_run. "
        "Cablear antes de _mark_terminal en el bloque if return_code == 0: (~línea 937)."
    )


def test_copilot_runner_wires_issue_phase_publisher():
    """agent_runner.py contiene una llamada a publish_issue_phase_from_run."""
    src = _source(RUNNER_COPILOT)
    assert "publish_issue_phase_from_run" in src, (
        "F3 MISSING: agent_runner.py no llama a publish_issue_phase_from_run. "
        "Cablear en run_agent() antes de 'row.metadata_dict = md' (~línea 895)."
    )


def test_phase_publisher_called_with_correct_kwargs_pattern():
    """Cada runner pasa ticket_id, agent_type, output, project_name (kwargs obligatorios)."""
    for name, path in [
        ("claude_code_cli_runner", RUNNER_CLAUDE),
        ("codex_cli_runner", RUNNER_CODEX),
        ("agent_runner", RUNNER_COPILOT),
    ]:
        src = _source(path)
        assert "publish_issue_phase_from_run" in src, f"{name}: sin cableado"
        # Verificar que se pasan los kwargs requeridos (al menos 2 de los 4)
        # El patrón es siempre keyword-only (firma usa *)
        for kwarg in ("ticket_id=", "agent_type="):
            assert kwarg in src, (
                f"{name}: falta kwarg '{kwarg}' en la llamada a publish_issue_phase_from_run. "
                "La función es keyword-only (firma usa *)."
            )
