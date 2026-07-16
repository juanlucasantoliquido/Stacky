"""Plan 120 F2 — transporte WinRM del motor de deploy: fix §2.3 + run_deploy_step
+ push_file_winrm. Subprocess SIEMPRE mockeado; keyring/fs mockeados."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
_BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

import services.remote_exec as _remote_exec


@contextmanager
def _mock_flags(*, master=True, execute=True):
    import config as _config
    with mock.patch.object(_config.config, "STACKY_DEPLOYMENTS_ENABLED", master):
        with mock.patch.object(_config.config, "STACKY_DEPLOYMENTS_EXECUTE_ENABLED", execute):
            with mock.patch("sys.platform", "win32"):
                yield


def _mock_target(host="10.0.0.5", user="user", domain="DOM", password="s3cr3t"):
    return (
        mock.patch("services.server_registry.get_server", return_value={"host": host}),
        mock.patch("services.server_registry.get_credential", return_value=(user, domain, password)),
    )


class TestGetCredentialContractUnpack:
    def test_get_credential_contract_unpack(self, tmp_path, monkeypatch):
        """Fija el fix §2.3: el env del subprocess usa SR_HOST del server, SR_USER
        'DOM\\user', SR_PASS la password real — para run_remote Y run_deploy_step."""
        monkeypatch.setattr(_remote_exec, "_audit_dir", lambda: tmp_path)
        captured = {}

        def fake_run(*args, env=None, **kwargs):
            captured.update(env or {})
            m = mock.Mock(stdout="ok", stderr="", returncode=0)
            return m

        p_server, p_cred = _mock_target()
        with _mock_flags():
            with p_server, p_cred:
                with mock.patch("services.remote_exec.subprocess.run", side_effect=fake_run):
                    result = _remote_exec.run_deploy_step(
                        "srv1", "Get-ChildItem", timeout_s=30, read_only=True, run_id="dr-1",
                    )
        assert result["ok"] is True
        assert captured["SR_HOST"] == "10.0.0.5"
        assert captured["SR_USER"] == "DOM\\user"
        assert captured["SR_PASS"] == "s3cr3t"

    def test_sin_dominio_user_plano(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_remote_exec, "_audit_dir", lambda: tmp_path)
        captured = {}

        def fake_run(*args, env=None, **kwargs):
            captured.update(env or {})
            return mock.Mock(stdout="ok", stderr="", returncode=0)

        p_server, p_cred = _mock_target(domain="")
        with _mock_flags():
            with p_server, p_cred:
                with mock.patch("services.remote_exec.subprocess.run", side_effect=fake_run):
                    _remote_exec.run_deploy_step(
                        "srv1", "Get-ChildItem", timeout_s=30, read_only=True, run_id="dr-1",
                    )
        assert captured["SR_USER"] == "user"


class TestRunDeployStepGating:
    def test_run_deploy_step_gating(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_remote_exec, "_audit_dir", lambda: tmp_path)
        p_server, p_cred = _mock_target()

        # master OFF ⇒ deployments_disabled (aunque read_only=True)
        with _mock_flags(master=False, execute=False):
            with p_server, p_cred:
                result = _remote_exec.run_deploy_step(
                    "srv1", "Get-ChildItem", timeout_s=30, read_only=True, run_id="r1",
                )
        assert result["error"] == "deployments_disabled"

        # master ON + EXECUTE OFF + read_only=False ⇒ deployments_execute_disabled
        with _mock_flags(master=True, execute=False):
            with p_server, p_cred:
                result = _remote_exec.run_deploy_step(
                    "srv1", "cmd /c mklink /J a b", timeout_s=30, read_only=False, run_id="r2",
                )
        assert result["error"] == "deployments_execute_disabled"

        # master ON + read_only=True ⇒ ejecuta SIN necesitar EXECUTE
        with _mock_flags(master=True, execute=False):
            with p_server, p_cred:
                with mock.patch(
                    "services.remote_exec.subprocess.run",
                    return_value=mock.Mock(stdout="ok", stderr="", returncode=0),
                ):
                    result = _remote_exec.run_deploy_step(
                        "srv1", "Get-ChildItem", timeout_s=30, read_only=True, run_id="r3",
                    )
        assert result["ok"] is True

    def test_run_deploy_step_no_depende_de_consola(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_remote_exec, "_audit_dir", lambda: tmp_path)
        import config as _config
        p_server, p_cred = _mock_target()
        with mock.patch.object(_config.config, "STACKY_DEVOPS_REMOTE_CONSOLE_ENABLED", False):
            with _mock_flags(master=True, execute=True):
                with p_server, p_cred:
                    with mock.patch(
                        "services.remote_exec.subprocess.run",
                        return_value=mock.Mock(stdout="ok", stderr="", returncode=0),
                    ):
                        result = _remote_exec.run_deploy_step(
                            "srv1", "cmd /c mklink /J a b", timeout_s=30, read_only=False, run_id="r4",
                        )
        assert result["ok"] is True

    def test_read_only_valida_comando(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_remote_exec, "_audit_dir", lambda: tmp_path)
        p_server, p_cred = _mock_target()
        with _mock_flags():
            with p_server, p_cred:
                result = _remote_exec.run_deploy_step(
                    "srv1", "Remove-Item x", timeout_s=30, read_only=True, run_id="r5",
                )
        assert result["error"] == "command_not_read_only"

    def test_auditoria_kind_deploy(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_remote_exec, "_audit_dir", lambda: tmp_path)
        p_server, p_cred = _mock_target(password="S3cr3tXYZ")
        with _mock_flags():
            with p_server, p_cred:
                with mock.patch(
                    "services.remote_exec.subprocess.run",
                    return_value=mock.Mock(stdout="ok", stderr="", returncode=0),
                ):
                    _remote_exec.run_deploy_step(
                        "srv1", "Get-ChildItem", timeout_s=30, read_only=True, run_id="dr-42",
                    )
        audit_json = (tmp_path / "srv1.jsonl").read_text(encoding="utf-8")
        entry = json.loads(audit_json.splitlines()[0])
        assert entry["kind"] == "deploy"
        assert entry["run_id"] == "dr-42"
        assert "S3cr3tXYZ" not in audit_json
        assert "SR_PASS" not in audit_json

    def test_no_password_real(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_remote_exec, "_audit_dir", lambda: tmp_path)
        with _mock_flags():
            with mock.patch("services.server_registry.get_server", return_value={"host": "10.0.0.5"}):
                with mock.patch("services.server_registry.get_credential", return_value=("user", "", "")):
                    result = _remote_exec.run_deploy_step(
                        "srv1", "Get-ChildItem", timeout_s=30, read_only=True, run_id="r6",
                    )
        assert result["error"] == "no_password"


class TestPushFileWinrm:
    def test_push_file_valida_rutas(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_remote_exec, "_audit_dir", lambda: tmp_path)
        p_server, p_cred = _mock_target()

        with _mock_flags():
            with p_server, p_cred:
                with mock.patch("services.remote_exec.subprocess.run") as run_mock:
                    # local inexistente
                    r1 = _remote_exec.push_file_winrm(
                        "srv1", str(tmp_path / "no-existe.zip"), "D:\\apps\\x\\incoming\\v1.zip",
                        timeout_s=30, run_id="r1",
                    )
                    assert r1["error"] == "local_file_not_found"

                    local = tmp_path / "artifact.zip"
                    local.write_bytes(b"zip-bytes")

                    # remoto relativo
                    r2 = _remote_exec.push_file_winrm(
                        "srv1", str(local), "apps\\x\\incoming\\v1.zip", timeout_s=30, run_id="r2",
                    )
                    assert r2["error"] == "invalid_remote_path"

                    # remoto con comillas
                    r3 = _remote_exec.push_file_winrm(
                        "srv1", str(local), 'D:\\apps\\x"\\incoming\\v1.zip', timeout_s=30, run_id="r3",
                    )
                    assert r3["error"] == "invalid_remote_path"

                    run_mock.assert_not_called()

    def test_push_file_ok_audita_bytes_sin_secretos(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_remote_exec, "_audit_dir", lambda: tmp_path)
        local = tmp_path / "artifact.zip"
        local.write_bytes(b"0123456789")
        p_server, p_cred = _mock_target(password="Sup3rSecret")

        with _mock_flags():
            with p_server, p_cred:
                with mock.patch(
                    "services.remote_exec.subprocess.run",
                    return_value=mock.Mock(stdout="", stderr="", returncode=0),
                ):
                    result = _remote_exec.push_file_winrm(
                        "srv1", str(local), "D:\\apps\\x\\incoming\\v1.zip", timeout_s=30, run_id="r4",
                    )
        assert result["ok"] is True
        audit_json = (tmp_path / "srv1.jsonl").read_text(encoding="utf-8")
        entry = json.loads(audit_json.splitlines()[0])
        assert entry["kind"] == "deploy_transfer"
        assert entry["bytes"] == 10
        assert "Sup3rSecret" not in audit_json
