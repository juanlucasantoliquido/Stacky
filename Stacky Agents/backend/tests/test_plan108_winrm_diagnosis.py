"""tests/test_plan108_winrm_diagnosis.py — Plan 108 F1b: diagnóstico tipificado
+ remediación copy-paste del preflight WinRM (C9 v2). Stacky NUNCA ejecuta la
remediación: solo la clasifica y la muestra (HITL)."""
from __future__ import annotations

from unittest import mock

import services.remote_exec as _remote_exec


class TestClassifyWinrmFailure:
    """F1b.1 — classify_winrm_failure: matching tipificado por substring."""

    def test_classify_unreachable(self):
        assert _remote_exec.classify_winrm_failure(
            "connection to the remote host timed out"
        ) == "unreachable_or_disabled"
        assert _remote_exec.classify_winrm_failure(
            "the connection was actively refused"
        ) == "unreachable_or_disabled"

    def test_classify_auth_and_trust(self):
        assert _remote_exec.classify_winrm_failure("Access is denied") == "auth_denied"
        assert _remote_exec.classify_winrm_failure("Acceso denegado") == "auth_denied"
        assert _remote_exec.classify_winrm_failure(
            "The client cannot connect... check the TrustedHosts setting"
        ) == "trust_config"
        # Passthrough exacto (sin host): el detail viaja tal cual.
        assert _remote_exec.classify_winrm_failure("keyring_unavailable") == "keyring_unavailable"

    def test_classify_default_is_winrm_error(self):
        assert _remote_exec.classify_winrm_failure("algo raro que no matchea nada") == "winrm_error"


class TestBuildWinrmRemediation:
    """F1b.2 — build_winrm_remediation: pasos copy-paste, HITL (Stacky NUNCA ejecuta)."""

    def test_remediation_always_has_enable_psremoting(self):
        host = "srv-prod-01"
        for kind in ("unreachable_or_disabled", "trust_config", "auth_denied", "winrm_error"):
            steps = _remote_exec.build_winrm_remediation(host, kind)
            assert len(steps) >= 1, f"kind={kind} sin pasos"
            assert "Enable-PSRemoting -Force" in (steps[0]["command"] or "")
            # Ningún comando debe filtrar credenciales.
            for step in steps:
                cmd = (step.get("command") or "").lower()
                assert "password" not in cmd
                assert "sr_pass" not in cmd

    def test_remediation_trust_config_has_trustedhosts(self):
        host = "srv-workgroup-07"
        steps = _remote_exec.build_winrm_remediation(host, "trust_config")
        joined = " ".join(s.get("command") or "" for s in steps)
        assert "TrustedHosts" in joined
        assert host in joined

    def test_remediation_passthrough_kinds_are_empty(self):
        for kind in ("windows_only", "keyring_unavailable", "server_not_found", "server_missing_host"):
            assert _remote_exec.build_winrm_remediation("any-host", kind) == []


class TestCheckWinrmEnriches:
    """F1b.3 — check_winrm() enriquecido, backward-compatible (ok/detail no cambian)."""

    def test_check_winrm_enriches_failure(self, monkeypatch):
        monkeypatch.setattr("sys.platform", "win32")
        monkeypatch.setattr("services.server_registry.keyring_available", lambda: True)
        monkeypatch.setattr(
            "services.server_registry.get_server",
            lambda alias: {"alias": alias, "host": "srv1", "username": "u"},
        )
        mock_result = mock.Mock()
        mock_result.returncode = 1
        mock_result.stderr = "The client cannot process the request. TrustedHosts must be configured."
        with mock.patch("services.remote_exec.subprocess.run", return_value=mock_result):
            result = _remote_exec.check_winrm("srv1")

        assert result["ok"] is False
        assert result["kind"] == "trust_config"
        assert len(result["remediation"]) >= 1

    def test_check_winrm_ok_has_no_new_keys(self, monkeypatch):
        monkeypatch.setattr("sys.platform", "win32")
        monkeypatch.setattr("services.server_registry.keyring_available", lambda: True)
        monkeypatch.setattr(
            "services.server_registry.get_server",
            lambda alias: {"alias": alias, "host": "srv1", "username": "u"},
        )
        mock_result = mock.Mock()
        mock_result.returncode = 0
        mock_result.stderr = ""
        with mock.patch("services.remote_exec.subprocess.run", return_value=mock_result):
            result = _remote_exec.check_winrm("srv1")

        assert result["ok"] is True
        assert "kind" not in result
        assert "remediation" not in result

    def test_check_winrm_early_return_kind_is_detail_passthrough(self, monkeypatch):
        """Returns tempranos sin host (p.ej. keyring_unavailable) ⇒ kind == detail, remediation []."""
        monkeypatch.setattr("sys.platform", "win32")
        monkeypatch.setattr("services.server_registry.keyring_available", lambda: False)
        result = _remote_exec.check_winrm("srv1")
        assert result["ok"] is False
        assert result["detail"] == "keyring_unavailable"
        assert result["kind"] == "keyring_unavailable"
        assert result["remediation"] == []
