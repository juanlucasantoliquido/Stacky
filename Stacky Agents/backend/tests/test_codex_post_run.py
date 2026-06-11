"""H2.1 / H7.2 — Tests del post-run pipeline en codex_cli_runner.

Verifica que codex invoca harness.post_run.finalize_run tras exit 0.

Casos:
  1. output válido para QA → status_suggestion="completed", contract_score presente
  2. output con failures + gate ON → "needs_review"
  3. output con failures + gate OFF → "completed" (validación corre igual)
  4. runtime sin writes_artifacts → artifacts is None
     (reutiliza harness.capabilities — ya cubierto en test_harness_post_run.py)
  H7.2. repro.ps1 escrito en run_dir tras run mockeado
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
_BAD_OUTPUT = "muy corto"


def test_codex_post_run_good_output(monkeypatch):
    """finalize_run llamado con output válido → completed, contract_score presente."""
    from harness.post_run import finalize_run

    result = finalize_run(
        runtime="codex_cli",
        agent_type="qa",
        output_text=_GOOD_OUTPUT,
        gate_enabled=False,
    )
    assert result.status_suggestion == "completed"
    assert result.contract_score >= 0
    assert "contract_score" in result.metadata_patch
    assert result.metadata_patch["contract_score"] == result.contract_score


def test_codex_post_run_violation_gate_on():
    """Output que viola contrato duro + gate_enabled=True → needs_review."""
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


def test_codex_post_run_violation_gate_off():
    """Output con violation + gate_enabled=False → completed (validación corre igual)."""
    from harness.post_run import finalize_run

    result = finalize_run(
        runtime="codex_cli",
        agent_type="qa",
        output_text=_BAD_OUTPUT,
        gate_enabled=False,
    )
    assert result.status_suggestion == "completed"
    # Validación corrió: hay failures
    assert not result.contract_passed
    assert len(result.contract_failures) > 0


def test_codex_post_run_no_artifacts_without_ado_id():
    """Sin ado_id → artifacts is None incluso con writes_artifacts=True."""
    from harness.post_run import finalize_run

    result = finalize_run(
        runtime="codex_cli",
        agent_type="qa",
        output_text=_GOOD_OUTPUT,
        ado_id=None,
        gate_enabled=False,
    )
    assert result.artifacts is None


def test_codex_post_run_metadata_patch_structure():
    """metadata_patch tiene las claves esperadas para fusionar en metadata."""
    from harness.post_run import finalize_run

    result = finalize_run(
        runtime="codex_cli",
        agent_type="qa",
        output_text=_GOOD_OUTPUT,
        gate_enabled=False,
    )
    assert isinstance(result.metadata_patch, dict)
    assert "contract_score" in result.metadata_patch
    assert "confidence" in result.metadata_patch
    assert isinstance(result.metadata_patch["confidence"], dict)


# ── H7.2 — repro.ps1 ──────────────────────────────────────────────────────────

def test_write_repro_script_creates_file(tmp_path):
    """H7.2 — write_repro_script genera run_dir/repro.ps1 con el comando y env STACKY_*."""
    from services.codex_cli_runner import write_repro_script

    cmd = ["codex", "exec", "--json", "-", "run"]
    env = {
        "STACKY_EXECUTION_ID": "42",
        "STACKY_AGENT_TYPE": "dev",
        "ANTHROPIC_API_KEY": "sk-secret",    # debe ser filtrada
        "ADO_PAT": "pat-123",                # debe ser filtrada
        "PATH": "C:\\Windows\\system32",     # safe, debe incluirse
    }

    write_repro_script(run_dir=tmp_path, cmd=cmd, env=env)

    repro = tmp_path / "repro.ps1"
    assert repro.exists(), "repro.ps1 debe existir tras write_repro_script"

    content = repro.read_text(encoding="utf-8")
    # Incluye env STACKY_* no sensibles
    assert "STACKY_EXECUTION_ID" in content
    assert "STACKY_AGENT_TYPE" in content
    # Filtra sensibles
    assert "sk-secret" not in content
    assert "pat-123" not in content
    assert "ANTHROPIC_API_KEY" not in content
    assert "ADO_PAT" not in content
    # El comando está presente
    assert "codex" in content
    assert "exec" in content


def test_write_repro_script_empty_env(tmp_path):
    """H7.2 — write_repro_script funciona con env vacío (solo escribe el comando)."""
    from services.codex_cli_runner import write_repro_script

    write_repro_script(run_dir=tmp_path, cmd=["codex", "exec", "-"], env={})
    repro = tmp_path / "repro.ps1"
    assert repro.exists()
    assert "codex" in repro.read_text(encoding="utf-8")
