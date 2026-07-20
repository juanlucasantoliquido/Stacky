"""G0.1 — Tests del gate de precondiciones pre-run.

Tests TDD para services/run_preflight.py.
Valida: predicados duros, predicados blandos, flag OFF (byte-idéntico).
"""
from __future__ import annotations

import importlib
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ticket(project: str | None = "test_project"):
    t = MagicMock()
    t.project = project
    return t


def _reload_preflight():
    """Fuerza recarga del módulo para que el flag se lea de os.environ actual."""
    import services.run_preflight as _mod
    importlib.reload(_mod)
    return _mod


# ---------------------------------------------------------------------------
# Fixture: parchear el flag directamente en config (evita contaminación de caché)
# ---------------------------------------------------------------------------

@pytest.fixture
def preflight_enabled(monkeypatch):
    """Activa el gate de precondiciones para el test."""
    import config as _cfg_mod
    monkeypatch.setattr(_cfg_mod.config, "STACKY_RUN_PREFLIGHT_GATE_ENABLED", True)
    # También env para el path sin config
    monkeypatch.setenv("STACKY_RUN_PREFLIGHT_GATE_ENABLED", "true")


@pytest.fixture
def preflight_disabled(monkeypatch):
    """Desactiva el gate de precondiciones para el test."""
    import config as _cfg_mod
    monkeypatch.setattr(_cfg_mod.config, "STACKY_RUN_PREFLIGHT_GATE_ENABLED", False)
    monkeypatch.setenv("STACKY_RUN_PREFLIGHT_GATE_ENABLED", "false")


# ---------------------------------------------------------------------------
# Flag OFF — byte-idéntico
# ---------------------------------------------------------------------------

class TestPreflightFlagOff:
    def test_flag_off_always_ok(self, tmp_path, preflight_disabled):
        """Con flag OFF, check() devuelve ok=True sin verificar nada."""
        from services.run_preflight import check
        result = check(
            ticket=_make_ticket(),
            runtime="claude_code_cli",
            project=None,
        )
        assert result.ok is True
        assert result.failure_check is None


# ---------------------------------------------------------------------------
# Predicado duro 1: outputs_dir
# ---------------------------------------------------------------------------

class TestPreflightOutputsDir:
    def test_outputs_dir_missing_blocks(self, tmp_path, preflight_enabled):
        """outputs_dir inexistente → bloqueado con outputs_dir_missing."""
        nonexistent = tmp_path / "no_existe"
        with patch("services.run_preflight._resolve_outputs_dir", return_value=nonexistent):
            from services.run_preflight import check
            result = check(
                ticket=_make_ticket(),
                runtime="github_copilot",
                project=None,
            )
        assert result.ok is False
        assert result.failure_check == "outputs_dir_missing"

    def test_outputs_dir_not_writable_blocks(self, tmp_path, preflight_enabled):
        """outputs_dir no escribible → bloqueado con outputs_dir_not_writable."""
        locked_dir = tmp_path / "locked"
        locked_dir.mkdir()
        with (
            patch("services.run_preflight._resolve_outputs_dir", return_value=locked_dir),
            patch("services.run_preflight._is_writable", return_value=False),
        ):
            from services.run_preflight import check
            result = check(
                ticket=_make_ticket(),
                runtime="github_copilot",
                project=None,
            )
        assert result.ok is False
        assert result.failure_check == "outputs_dir_not_writable"


# ---------------------------------------------------------------------------
# Predicado duro 3: PAT ausente + auto-create ON
# ---------------------------------------------------------------------------

class TestPreflightPatMissing:
    def test_pat_missing_auto_create_on_blocks(self, tmp_path, preflight_enabled, monkeypatch):
        """PAT ausente + auto-create ON → bloqueado con ado_pat_missing."""
        writable = tmp_path / "outputs"
        writable.mkdir()
        monkeypatch.setenv("STACKY_OUTPUT_WATCHER_AUTO_CREATE_TASKS", "true")
        monkeypatch.setenv("ADO_PAT", "")
        with (
            patch("services.run_preflight._resolve_outputs_dir", return_value=writable),
            patch("services.run_preflight._is_writable", return_value=True),
            patch("services.run_preflight._resolve_repo_root", return_value=None),
            patch("services.ado_client.ado_pat_present", return_value=False),
        ):
            from services.run_preflight import check
            result = check(
                ticket=_make_ticket(),
                runtime="github_copilot",  # no requiere repo
                project=None,
            )
        assert result.ok is False
        assert result.failure_check == "ado_pat_missing"

    def test_pat_via_project_auth_ok(self, tmp_path, preflight_enabled, monkeypatch):
        """PAT ausente en env pero resoluble vía proyecto activo → no bloquea.

        Regresión: el gate solo miraba env/config y bloqueaba con ado_pat_missing
        aunque el operador tuviera el PAT configurado por proyecto vía UI.
        """
        writable = tmp_path / "outputs"
        writable.mkdir()
        monkeypatch.setenv("STACKY_OUTPUT_WATCHER_AUTO_CREATE_TASKS", "true")
        monkeypatch.setenv("ADO_PAT", "")
        with (
            patch("services.run_preflight._resolve_outputs_dir", return_value=writable),
            patch("services.run_preflight._is_writable", return_value=True),
            patch("services.run_preflight._resolve_repo_root", return_value=None),
            patch("services.ado_client.ado_pat_present", return_value=True),
            patch("services.run_preflight._binary_resolvable", return_value=True),
        ):
            from services.run_preflight import check
            result = check(
                ticket=_make_ticket(),
                runtime="github_copilot",
                project=None,
            )
        assert result.ok is True
        assert result.failure_check is None

    def test_pat_missing_auto_create_off_ok(self, tmp_path, preflight_enabled, monkeypatch):
        """PAT ausente + auto-create OFF → no bloquea."""
        writable = tmp_path / "outputs"
        writable.mkdir()
        monkeypatch.setenv("STACKY_OUTPUT_WATCHER_AUTO_CREATE_TASKS", "false")
        monkeypatch.setenv("ADO_PAT", "")
        with (
            patch("services.run_preflight._resolve_outputs_dir", return_value=writable),
            patch("services.run_preflight._is_writable", return_value=True),
            patch("services.run_preflight._resolve_repo_root", return_value=None),
            patch("services.run_preflight._binary_resolvable", return_value=True),
        ):
            from services.run_preflight import check
            result = check(
                ticket=_make_ticket(),
                runtime="github_copilot",
                project=None,
            )
        # github_copilot no requiere repo ni binario → ok
        assert result.ok is True


# ---------------------------------------------------------------------------
# Predicado duro 2: repo ausente para runtime que lo exige
# ---------------------------------------------------------------------------

class TestPreflightRepoMissing:
    def test_repo_missing_for_cli_blocks(self, tmp_path, preflight_enabled, monkeypatch):
        """repo ausente para runtime cli → bloqueado con repo_missing."""
        writable = tmp_path / "outputs"
        writable.mkdir()
        monkeypatch.setenv("STACKY_OUTPUT_WATCHER_AUTO_CREATE_TASKS", "false")
        with (
            patch("services.run_preflight._resolve_outputs_dir", return_value=writable),
            patch("services.run_preflight._is_writable", return_value=True),
            patch("services.run_preflight._resolve_repo_root", return_value=None),
        ):
            from services.run_preflight import check
            result = check(
                ticket=_make_ticket(),
                runtime="claude_code_cli",
                project=None,
            )
        assert result.ok is False
        assert result.failure_check == "repo_missing"


# ---------------------------------------------------------------------------
# Predicado duro 4: binario no resolvible
# ---------------------------------------------------------------------------

class TestPreflightBinaryMissing:
    def test_binary_missing_blocks(self, tmp_path, preflight_enabled, monkeypatch):
        """Binario no resolvible → bloqueado con runtime_binary_missing."""
        writable = tmp_path / "outputs"
        writable.mkdir()
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / ".git").mkdir()
        monkeypatch.setenv("STACKY_OUTPUT_WATCHER_AUTO_CREATE_TASKS", "false")
        monkeypatch.setenv("ADO_PAT", "fake_pat")
        with (
            patch("services.run_preflight._resolve_outputs_dir", return_value=writable),
            patch("services.run_preflight._is_writable", return_value=True),
            patch("services.run_preflight._resolve_repo_root", return_value=repo),
            patch("services.run_preflight._binary_resolvable", return_value=False),
        ):
            from services.run_preflight import check
            result = check(
                ticket=_make_ticket(),
                runtime="claude_code_cli",
                project=None,
            )
        assert result.ok is False
        assert result.failure_check == "runtime_binary_missing"


# ---------------------------------------------------------------------------
# Todo OK → procede igual que hoy
# ---------------------------------------------------------------------------

class TestPreflightAllOk:
    def test_all_ok_returns_ok_true(self, tmp_path, preflight_enabled, monkeypatch):
        """Con todos los predicados OK → ok=True, sin failure_check."""
        writable = tmp_path / "outputs"
        writable.mkdir()
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / ".git").mkdir()
        monkeypatch.setenv("STACKY_OUTPUT_WATCHER_AUTO_CREATE_TASKS", "false")
        with (
            patch("services.run_preflight._resolve_outputs_dir", return_value=writable),
            patch("services.run_preflight._is_writable", return_value=True),
            patch("services.run_preflight._resolve_repo_root", return_value=repo),
            patch("services.run_preflight._binary_resolvable", return_value=True),
        ):
            from services.run_preflight import check
            result = check(
                ticket=_make_ticket(),
                runtime="claude_code_cli",
                project=None,
            )
        assert result.ok is True
        assert result.failure_check is None

    def test_all_ok_to_metadata_empty(self):
        """ok=True → to_metadata() devuelve dict vacío."""
        from services.run_preflight import PreflightResult
        r = PreflightResult(ok=True)
        assert r.to_metadata() == {}

    def test_failure_to_metadata_has_precondition_failure(self):
        """ok=False → to_metadata() tiene 'precondition_failure' con check y detail."""
        from services.run_preflight import PreflightResult
        r = PreflightResult(ok=False, failure_check="ado_pat_missing", failure_detail="sin PAT")
        meta = r.to_metadata()
        assert "precondition_failure" in meta
        assert meta["precondition_failure"]["check"] == "ado_pat_missing"


# ---------------------------------------------------------------------------
# Predicado blando: solo warning, sin bloqueo
# ---------------------------------------------------------------------------

class TestPreflightSoftWarning:
    def test_repo_without_git_is_warning_not_block(self, tmp_path, preflight_enabled, monkeypatch):
        """repo_root sin .git → warning en result.warnings, no bloquea."""
        writable = tmp_path / "outputs"
        writable.mkdir()
        repo = tmp_path / "repo_no_git"
        repo.mkdir()  # sin .git
        monkeypatch.setenv("STACKY_OUTPUT_WATCHER_AUTO_CREATE_TASKS", "false")
        monkeypatch.setenv("ADO_PAT", "fake_pat")
        with (
            patch("services.run_preflight._resolve_outputs_dir", return_value=writable),
            patch("services.run_preflight._is_writable", return_value=True),
            patch("services.run_preflight._resolve_repo_root", return_value=repo),
            patch("services.run_preflight._binary_resolvable", return_value=True),
        ):
            from services.run_preflight import check
            result = check(
                ticket=_make_ticket(),
                runtime="claude_code_cli",
                project=None,
            )
        # No debe bloquear (es predicado blando)
        assert result.ok is True
        assert len(result.warnings) > 0
