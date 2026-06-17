"""TDD — I1.1: needs_repair en harness/run_repair.py.

Criterios de aceptación:
- output vacío → "empty_output"
- artefacto malformado (existe pero JSON inválido o clave faltante) → "malformed_artifact"
- output presente + artefacto válido → None
- fallo de criterio (contract gate) → NO dispara repair
- runtime sin resume (github_copilot) → no repara, sin fallback silencioso
- presupuesto compartido con autocorrect (tope respetado)
- flag OFF → comportamiento actual byte-idéntico
- un único reintento
- recovered=True si reintento produce output no-vacío
- recovered=False si reintento produce output vacío/malformado
- metadata["run_repair"] contiene attempted/reason/recovered
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Tests de needs_repair (función pura)
# ---------------------------------------------------------------------------

class TestNeedsRepair:
    def test_empty_output_returns_empty_output(self):
        from harness.run_repair import needs_repair
        assert needs_repair(output_text="", artifacts=[]) == "empty_output"

    def test_whitespace_only_returns_empty_output(self):
        from harness.run_repair import needs_repair
        assert needs_repair(output_text="   \n\t\n", artifacts=[]) == "empty_output"

    def test_valid_output_no_artifacts_returns_none(self):
        from harness.run_repair import needs_repair
        assert needs_repair(output_text="Salida del agente OK", artifacts=[]) is None

    def test_malformed_json_artifact_returns_malformed(self, tmp_path):
        from harness.run_repair import needs_repair
        art = tmp_path / "pending-task.json"
        art.write_text("{not valid json", encoding="utf-8")
        assert needs_repair(output_text="algo", artifacts=[str(art)]) == "malformed_artifact"

    def test_valid_json_artifact_returns_none(self, tmp_path):
        from harness.run_repair import needs_repair
        art = tmp_path / "pending-task.json"
        art.write_text(json.dumps({"status": "pending_manual_creation", "title": "x"}), encoding="utf-8")
        assert needs_repair(output_text="algo", artifacts=[str(art)]) is None

    def test_missing_structural_key_returns_malformed(self, tmp_path):
        from harness.run_repair import needs_repair
        art = tmp_path / "pending-task.json"
        # JSON válido pero sin "status" (clave estructural)
        art.write_text(json.dumps({"title": "x"}), encoding="utf-8")
        assert needs_repair(output_text="algo", artifacts=[str(art)]) == "malformed_artifact"

    def test_nonexistent_artifact_path_ignored(self):
        from harness.run_repair import needs_repair
        # Artefacto que no existe → no cuenta como malformado
        result = needs_repair(output_text="algo", artifacts=["/no/existe/pending-task.json"])
        assert result is None

    def test_non_json_artifact_ignored(self, tmp_path):
        from harness.run_repair import needs_repair
        art = tmp_path / "output.txt"
        art.write_text("texto libre", encoding="utf-8")
        # Archivos que no son .json no se validan como JSON
        assert needs_repair(output_text="algo", artifacts=[str(art)]) is None


# ---------------------------------------------------------------------------
# Tests de integración: flag OFF = byte-idéntico
# ---------------------------------------------------------------------------

class TestFlagOff:
    def test_flag_off_no_repair_attempted(self):
        """Con flag OFF, attempt_repair no hace nada y no muta metadata."""
        from harness.run_repair import attempt_repair

        metadata = {}
        result = attempt_repair(
            output_text="",
            artifacts=[],
            runtime="claude_code_cli",
            retries_budget=2,
            retries_used=0,
            send_fn=None,
            enabled=False,  # FLAG OFF
        )
        assert result is None
        # metadata no se toca desde afuera (attempt_repair retorna None)
        assert metadata == {}


# ---------------------------------------------------------------------------
# Tests de attempt_repair (lógica de reintento)
# ---------------------------------------------------------------------------

class TestAttemptRepair:
    def test_no_resume_runtime_not_repaired(self):
        """github_copilot no tiene resume → attempt_repair retorna None."""
        from harness.run_repair import attempt_repair

        result = attempt_repair(
            output_text="",
            artifacts=[],
            runtime="github_copilot",
            retries_budget=2,
            retries_used=0,
            send_fn=MagicMock(return_value="nueva salida"),
            enabled=True,
        )
        assert result is None

    def test_budget_exhausted_not_repaired(self):
        """Si retries_used >= retries_budget, no repara."""
        from harness.run_repair import attempt_repair

        result = attempt_repair(
            output_text="",
            artifacts=[],
            runtime="claude_code_cli",
            retries_budget=1,
            retries_used=1,  # presupuesto agotado
            send_fn=MagicMock(return_value="nueva salida"),
            enabled=True,
        )
        assert result is None

    def test_recovered_true_when_send_returns_content(self):
        """Un reintento que produce output no-vacío → recovered=True."""
        from harness.run_repair import attempt_repair

        send_fn = MagicMock(return_value="Artefacto regenerado correctamente.")
        result = attempt_repair(
            output_text="",
            artifacts=[],
            runtime="claude_code_cli",
            retries_budget=2,
            retries_used=0,
            send_fn=send_fn,
            enabled=True,
        )
        assert result is not None
        assert result["attempted"] is True
        assert result["recovered"] is True
        assert result["reason"] == "empty_output"
        send_fn.assert_called_once()

    def test_recovered_false_when_send_returns_empty(self):
        """Un reintento que produce output vacío → recovered=False."""
        from harness.run_repair import attempt_repair

        send_fn = MagicMock(return_value="")
        result = attempt_repair(
            output_text="",
            artifacts=[],
            runtime="claude_code_cli",
            retries_budget=2,
            retries_used=0,
            send_fn=send_fn,
            enabled=True,
        )
        assert result is not None
        assert result["attempted"] is True
        assert result["recovered"] is False

    def test_only_one_retry_made(self):
        """Exactamente un reintento, no más."""
        from harness.run_repair import attempt_repair

        send_fn = MagicMock(return_value="")
        attempt_repair(
            output_text="",
            artifacts=[],
            runtime="claude_code_cli",
            retries_budget=5,
            retries_used=0,
            send_fn=send_fn,
            enabled=True,
        )
        assert send_fn.call_count == 1

    def test_contract_fail_not_repaired(self):
        """Fallo de criterio (contract_failed=True) NO dispara repair."""
        from harness.run_repair import attempt_repair

        send_fn = MagicMock(return_value="algo")
        result = attempt_repair(
            output_text="",
            artifacts=[],
            runtime="claude_code_cli",
            retries_budget=2,
            retries_used=0,
            send_fn=send_fn,
            enabled=True,
            contract_failed=True,  # fallo de criterio
        )
        assert result is None
        send_fn.assert_not_called()

    def test_codex_runtime_supported(self):
        """codex_cli tiene resume → attempt_repair funciona."""
        from harness.run_repair import attempt_repair

        send_fn = MagicMock(return_value="output regenerado")
        result = attempt_repair(
            output_text="",
            artifacts=[],
            runtime="codex_cli",
            retries_budget=2,
            retries_used=0,
            send_fn=send_fn,
            enabled=True,
        )
        assert result is not None
        assert result["attempted"] is True

    def test_no_repair_when_output_not_empty_and_artifacts_ok(self, tmp_path):
        """Output presente y artifacts OK → None (no repara)."""
        from harness.run_repair import attempt_repair

        art = tmp_path / "pending-task.json"
        art.write_text(
            json.dumps({"status": "pending_manual_creation", "title": "x"}),
            encoding="utf-8",
        )
        send_fn = MagicMock()
        result = attempt_repair(
            output_text="Salida completa del agente.",
            artifacts=[str(art)],
            runtime="claude_code_cli",
            retries_budget=2,
            retries_used=0,
            send_fn=send_fn,
            enabled=True,
        )
        assert result is None
        send_fn.assert_not_called()
