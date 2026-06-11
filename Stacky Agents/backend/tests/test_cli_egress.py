"""H3.3 — Egress check para runtimes CLI.

TDD: estos tests deben fallar antes de que se agregue el check en los runners.

Verifica que cuando STACKY_CLI_EGRESS_ENABLED=true y el prompt contiene una
clase bloqueada, el run NO llegue a spawnear el proceso.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


# ── Helpers ───────────────────────────────────────────────────────────────────

class _FakeEgressBlocked:
    allowed = False
    reason = "clase 'financial' bloqueada para este modelo"
    blocked_classes = ["financial"]
    warning_classes = []
    detected_classes = ["financial"]


class _FakeEgressAllowed:
    allowed = True
    reason = "no sensitive data classes detected"
    blocked_classes = []
    warning_classes = []
    detected_classes = []


# ── H3.3 — egress check en codex_cli_runner ──────────────────────────────────

def test_codex_egress_blocks_spawn_when_enabled_and_prompt_blocked(monkeypatch, tmp_path):
    """Con STACKY_CLI_EGRESS_ENABLED=true y prompt bloqueado → no spawnea."""
    monkeypatch.setenv("STACKY_CLI_EGRESS_ENABLED", "true")

    from services import codex_cli_runner
    from services import egress_policies

    with patch.object(egress_policies, "check", return_value=_FakeEgressBlocked()) as mock_check, \
         patch("subprocess.Popen") as mock_popen:

        # Invocamos la función que construye y corre el proceso.
        # Usamos la función interna _run_with_egress_check si existe,
        # o verificamos que Popen no se llame cuando egress bloquea.
        result = codex_cli_runner._check_cli_egress(
            prompt="CBU 1234567890123456789012 pago pendiente",
            project=None,
            model="gpt-4o",
        )

        assert result is not None, "Debe devolver la decisión de egress"
        assert result.allowed is False
        mock_popen.assert_not_called()


def test_codex_egress_allows_spawn_when_enabled_and_prompt_clean(monkeypatch):
    """Con STACKY_CLI_EGRESS_ENABLED=true y prompt limpio → _check_cli_egress devuelve allowed."""
    monkeypatch.setenv("STACKY_CLI_EGRESS_ENABLED", "true")

    from services import codex_cli_runner
    from services import egress_policies

    with patch.object(egress_policies, "check", return_value=_FakeEgressAllowed()):
        result = codex_cli_runner._check_cli_egress(
            prompt="tarea de refactor del módulo de usuarios",
            project=None,
            model="gpt-4o",
        )
        assert result.allowed is True


def test_codex_egress_skipped_when_disabled(monkeypatch):
    """Con STACKY_CLI_EGRESS_ENABLED=false → _check_cli_egress devuelve None (no corre check)."""
    monkeypatch.setenv("STACKY_CLI_EGRESS_ENABLED", "false")

    from services import codex_cli_runner

    result = codex_cli_runner._check_cli_egress(
        prompt="CBU 1234567890123456789012",
        project=None,
        model="gpt-4o",
    )
    assert result is None, "Cuando está OFF, debe devolver None sin correr egress"


def test_codex_egress_disabled_by_default(monkeypatch):
    """Sin la variable seteada, el flag es False por default."""
    monkeypatch.delenv("STACKY_CLI_EGRESS_ENABLED", raising=False)

    from services import codex_cli_runner

    result = codex_cli_runner._check_cli_egress(
        prompt="CBU 1234567890123456789012",
        project=None,
        model="gpt-4o",
    )
    assert result is None


# ── H3.3 — egress check en claude_code_cli_runner ─────────────────────────────

def test_claude_egress_blocks_when_enabled_and_prompt_blocked(monkeypatch):
    """Con STACKY_CLI_EGRESS_ENABLED=true y prompt bloqueado → blocked."""
    monkeypatch.setenv("STACKY_CLI_EGRESS_ENABLED", "true")

    from services import claude_code_cli_runner
    from services import egress_policies

    with patch.object(egress_policies, "check", return_value=_FakeEgressBlocked()):
        result = claude_code_cli_runner._check_cli_egress(
            prompt="CBU 1234567890123456789012 pago pendiente",
            project=None,
            model="claude-sonnet-4-6",
        )
        assert result is not None
        assert result.allowed is False


def test_claude_egress_skipped_when_disabled(monkeypatch):
    """Con STACKY_CLI_EGRESS_ENABLED=false → None."""
    monkeypatch.setenv("STACKY_CLI_EGRESS_ENABLED", "false")

    from services import claude_code_cli_runner

    result = claude_code_cli_runner._check_cli_egress(
        prompt="CBU 1234567890123456789012",
        project=None,
        model="claude-sonnet-4-6",
    )
    assert result is None


# ── H3.3 — FLAG_REGISTRY contiene STACKY_CLI_EGRESS_ENABLED ──────────────────

def test_flag_registry_has_cli_egress_flag():
    """STACKY_CLI_EGRESS_ENABLED debe estar en FLAG_REGISTRY."""
    from services.harness_flags import FLAG_REGISTRY
    keys = {s.key for s in FLAG_REGISTRY}
    assert "STACKY_CLI_EGRESS_ENABLED" in keys, (
        "STACKY_CLI_EGRESS_ENABLED no está en FLAG_REGISTRY — "
        "violación de la regla: todo flag nuevo se registra en el mismo PR"
    )
