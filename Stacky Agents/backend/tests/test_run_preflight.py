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
# Predicado duro 3 — el PAT de ADO SOLO aplica a proyectos cuyo tracker ES ADO
# ---------------------------------------------------------------------------

class TestPreflightPatTrackerAware:
    """El predicado 3 no debe exigir PAT de Azure DevOps a un proyecto no-ADO.

    Defecto reproducido en vivo (proyecto RIPLEY, tracker GitLab, 2026-08-01):
    el gate bloqueaba TODA corrida con `ado_pat_missing` antes del spawn, aunque
    el proyecto no use ADO y por lo tanto el auto-create de Tasks en ADO no
    pueda ocurrir jamás. Evidencia: `agent_executions` 206-209 en la DB del
    operador, todas `failed` con
    `metadata_json.precondition_failure.check == "ado_pat_missing"`.
    """

    @staticmethod
    def _cfg(tracker_type: str | None) -> dict:
        tracker: dict = {}
        if tracker_type is not None:
            tracker["type"] = tracker_type
            tracker["auth_file"] = f"auth/{tracker_type}_auth.json"
        return {"name": "PROY", "workspace_root": "C:/ws/proy", "issue_tracker": tracker}

    def test_gitlab_project_without_ado_pat_does_not_block(
        self, tmp_path, preflight_enabled, monkeypatch
    ):
        """Tracker GitLab + sin PAT de ADO + auto-create ON → NO bloquea."""
        writable = tmp_path / "outputs"
        writable.mkdir()
        monkeypatch.setenv("STACKY_OUTPUT_WATCHER_AUTO_CREATE_TASKS", "true")
        monkeypatch.setenv("ADO_PAT", "")
        with (
            patch("services.run_preflight._resolve_outputs_dir", return_value=writable),
            patch("services.run_preflight._is_writable", return_value=True),
            patch("services.run_preflight._resolve_repo_root", return_value=None),
            patch("project_manager.get_project_config", return_value=self._cfg("gitlab")),
            patch("services.run_preflight._binary_resolvable", return_value=True),
            patch("services.ado_client.ado_pat_present", return_value=False) as pat_probe,
        ):
            from services.run_preflight import check
            result = check(
                ticket=_make_ticket("PROY"),
                runtime="github_copilot",  # no requiere repo
                project="PROY",
            )
        assert result.ok is True
        assert result.failure_check is None
        # La cadena de resolución del PAT de ADO ni siquiera se consulta. Esto
        # cierra el riesgo de que `_auth_path_for` entregue el auth_file de OTRO
        # tracker (p. ej. auth/gitlab_auth.json) a `ado_client._read_pat_file`,
        # que lo abriría buscando el campo "pat".
        assert pat_probe.call_count == 0

    def test_ado_project_without_pat_still_blocks(
        self, tmp_path, preflight_enabled, monkeypatch
    ):
        """Regresión: tracker ADO + sin PAT → sigue bloqueando igual que antes."""
        writable = tmp_path / "outputs"
        writable.mkdir()
        monkeypatch.setenv("STACKY_OUTPUT_WATCHER_AUTO_CREATE_TASKS", "true")
        monkeypatch.setenv("ADO_PAT", "")
        with (
            patch("services.run_preflight._resolve_outputs_dir", return_value=writable),
            patch("services.run_preflight._is_writable", return_value=True),
            patch("services.run_preflight._resolve_repo_root", return_value=None),
            patch("project_manager.get_project_config", return_value=self._cfg("azure_devops")),
            patch("services.run_preflight._binary_resolvable", return_value=True),
            patch("services.ado_client.ado_pat_present", return_value=False) as pat_probe,
        ):
            from services.run_preflight import check
            result = check(
                ticket=_make_ticket("PROY"),
                runtime="github_copilot",
                project="PROY",
            )
        assert result.ok is False
        assert result.failure_check == "ado_pat_missing"
        assert pat_probe.call_count == 1

    def test_tracker_desconocido_falla_cerrado_y_bloquea(
        self, tmp_path, preflight_enabled, monkeypatch
    ):
        """Sin `issue_tracker.type` resoluble → se asume ADO y se bloquea.

        Fail-closed a propósito: el default histórico del repo es
        `azure_devops` (local_diagnostics.py:105). Si no sabemos el tracker,
        el gate se comporta EXACTAMENTE como antes del fix.
        """
        writable = tmp_path / "outputs"
        writable.mkdir()
        monkeypatch.setenv("STACKY_OUTPUT_WATCHER_AUTO_CREATE_TASKS", "true")
        monkeypatch.setenv("ADO_PAT", "")
        with (
            patch("services.run_preflight._resolve_outputs_dir", return_value=writable),
            patch("services.run_preflight._is_writable", return_value=True),
            patch("services.run_preflight._resolve_repo_root", return_value=None),
            patch("project_manager.get_project_config", return_value=self._cfg(None)),
            patch("services.run_preflight._binary_resolvable", return_value=True),
            patch("services.ado_client.ado_pat_present", return_value=False),
        ):
            from services.run_preflight import check
            result = check(
                ticket=_make_ticket("PROY"),
                runtime="github_copilot",
                project="PROY",
            )
        assert result.ok is False
        assert result.failure_check == "ado_pat_missing"

    def test_ticket_tracker_type_no_manda_sobre_el_config_del_proyecto(
        self, tmp_path, preflight_enabled, monkeypatch
    ):
        """El `tracker_type` de la FILA del ticket no decide: manda el config.

        El Brief Pool Ticket (`api/agents.py:777-785`) se crea sin pasar
        `tracker_type`, así que hereda el default `azure_devops` de la columna
        aunque el proyecto sea GitLab (verificado: tickets.id=1167, project
        RIPLEY, tracker_type='azure_devops'). Si el gate leyera el ticket, el
        proyecto GitLab seguiría bloqueado.
        """
        writable = tmp_path / "outputs"
        writable.mkdir()
        monkeypatch.setenv("STACKY_OUTPUT_WATCHER_AUTO_CREATE_TASKS", "true")
        monkeypatch.setenv("ADO_PAT", "")
        ticket = _make_ticket("PROY")
        ticket.tracker_type = "azure_devops"  # mentira heredada del default de la columna
        with (
            patch("services.run_preflight._resolve_outputs_dir", return_value=writable),
            patch("services.run_preflight._is_writable", return_value=True),
            patch("services.run_preflight._resolve_repo_root", return_value=None),
            patch("project_manager.get_project_config", return_value=self._cfg("gitlab")),
            patch("services.run_preflight._binary_resolvable", return_value=True),
            patch("services.ado_client.ado_pat_present", return_value=False),
        ):
            from services.run_preflight import check
            result = check(ticket=ticket, runtime="github_copilot", project="PROY")
        assert result.ok is True
        assert result.failure_check is None


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
