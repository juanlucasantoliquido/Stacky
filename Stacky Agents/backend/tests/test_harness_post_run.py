"""H1.1 — Tests de harness.post_run.finalize_run.

Casos:
  1. output válido + gate OFF → status_suggestion="completed", contract_score presente
  2. output con failures + gate ON → status_suggestion="needs_review"
  3. output con failures + gate OFF → status_suggestion="completed" (validación corre igual)
  4. runtime sin writes_artifacts → artifacts is None
  5. runtime con writes_artifacts + ado_id=None → artifacts is None
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

_GOOD_OUTPUT = (
    "## Verdict\n\nPASS — la funcionalidad cumple los criterios.\n\n" + "detalle " * 100
)
_BAD_OUTPUT = "muy corto"  # sin verdict → errores duros de contrato para QA


def test_finalize_run_good_output_gate_off():
    from harness.post_run import finalize_run

    result = finalize_run(
        runtime="codex_cli",
        agent_type="qa",
        output_text=_GOOD_OUTPUT,
        gate_enabled=False,
    )
    assert result.status_suggestion == "completed"
    assert result.contract_score >= 0
    assert isinstance(result.metadata_patch, dict)
    assert "contract_score" in result.metadata_patch
    assert "confidence" in result.metadata_patch


def test_finalize_run_bad_output_gate_on_demotes():
    from harness.post_run import finalize_run

    result = finalize_run(
        runtime="codex_cli",
        agent_type="qa",
        output_text=_BAD_OUTPUT,
        gate_enabled=True,
    )
    assert result.status_suggestion == "needs_review"
    assert not result.contract_passed
    assert len(result.contract_failures) > 0


def test_finalize_run_bad_output_gate_off_stays_completed():
    from harness.post_run import finalize_run

    result = finalize_run(
        runtime="codex_cli",
        agent_type="qa",
        output_text=_BAD_OUTPUT,
        gate_enabled=False,
    )
    # Validación corre (failures presentes) pero status no degrada
    assert result.status_suggestion == "completed"
    assert not result.contract_passed


def test_finalize_run_no_writes_artifacts_runtime():
    """Runtime sin writes_artifacts → artifacts is None."""
    from harness.post_run import finalize_run

    # github_copilot tiene writes_artifacts=True pero para esta prueba
    # usamos "unknown_runtime" que no está en CAPABILITIES
    result = finalize_run(
        runtime="unknown_runtime_xyz",
        agent_type="dev",
        output_text="output de prueba sin contrato",
        ado_id=999,
        gate_enabled=False,
    )
    assert result.artifacts is None


def test_finalize_run_writes_artifacts_ado_id_none():
    """Runtime con writes_artifacts pero sin ado_id → artifacts is None."""
    from harness.post_run import finalize_run

    result = finalize_run(
        runtime="codex_cli",
        agent_type="qa",
        output_text=_GOOD_OUTPUT,
        ado_id=None,  # sin ado_id
        gate_enabled=False,
    )
    assert result.artifacts is None


def test_finalize_run_metadata_patch_keys():
    from harness.post_run import finalize_run

    result = finalize_run(
        runtime="claude_code_cli",
        agent_type="qa",
        output_text=_GOOD_OUTPUT,
        gate_enabled=False,
    )
    assert "contract_score" in result.metadata_patch
    assert "confidence" in result.metadata_patch
    assert isinstance(result.metadata_patch["confidence"], dict)
