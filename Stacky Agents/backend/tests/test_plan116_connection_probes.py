"""Plan 116 F1 — sondas + agregador (mocks en ORIGEN, cero red real)."""
from __future__ import annotations

import json
import os
import sys
import urllib.error
from pathlib import Path
from unittest import mock

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import connection_doctor as cd


def test_probe_tracker_no_active_project_warns():
    with mock.patch("project_manager.get_active_project", return_value=None):
        r = cd.probe_tracker()
    assert r["status"] == "warn" and r["code"] == "CONFIG_MISSING"


def test_probe_tracker_ado_401_maps_auth401():
    cfg = {"issue_tracker": {"type": "azure_devops", "organization": "myorg"}}
    err = urllib.error.HTTPError("u", 401, "unauth", {}, None)
    with mock.patch("project_manager.get_active_project", return_value="P"), \
         mock.patch("project_manager.get_project_config", return_value=cfg), \
         mock.patch("services.local_diagnostics._probe_ado", side_effect=err):
        r = cd.probe_tracker()
    assert r["status"] == "fail" and r["code"] == "AUTH_401"
    assert "_usersSettings/tokens" in r["remediation"]["action"]["url"]


def test_probe_tracker_gitlab_uses_own_probe():
    cfg = {"issue_tracker": {"type": "gitlab", "base_url": "https://gl.example"}}
    with mock.patch("project_manager.get_active_project", return_value="P"), \
         mock.patch("project_manager.get_project_config", return_value=cfg), \
         mock.patch("services.local_diagnostics._probe_ado") as m_ado, \
         mock.patch("services.connection_doctor._probe_gitlab", return_value=None):
        r = cd.probe_tracker()
    assert r["status"] == "ok"
    m_ado.assert_not_called()
    assert "GitLab" in r["target_label"] or "GitLab" in r["detail"]


def test_probe_servers_dns_fail_maps():
    servers = [{"alias": "s1", "host": "srv01", "has_password": True}]
    with mock.patch("services.server_registry.list_servers", return_value=servers), \
         mock.patch("services.server_registry.test_connectivity", return_value=(False, "DNS: no resuelve x")), \
         mock.patch("services.server_registry.keyring_available", return_value=True):
        out = cd.probe_servers()
    assert any(r["code"] == "DNS_FAIL" for r in out)


def test_probe_servers_ok_without_credential_warns_cred_missing():
    servers = [{"alias": "s1", "host": "srv01", "has_password": False}]
    with mock.patch("services.server_registry.list_servers", return_value=servers), \
         mock.patch("services.server_registry.test_connectivity", return_value=(True, "TCP 3389 OK")), \
         mock.patch("services.server_registry.keyring_available", return_value=True):
        out = cd.probe_servers()
    assert any(r["status"] == "ok" for r in out)
    cred = [r for r in out if r["code"] == "CRED_MISSING"]
    assert cred and cred[0]["remediation"]["action"]["section_id"] == "servidores"


def test_probe_clis_missing_codex_has_install_command():
    def fake_find(name, fallbacks):
        return None if name == "codex" else "/usr/bin/" + name
    with mock.patch("services.local_diagnostics._find_executable", side_effect=fake_find):
        out = cd.probe_clis()
    codex = [r for r in out if r["target"] == "cli:codex"][0]
    assert codex["code"] == "CLI_NOT_FOUND"
    assert codex["remediation"]["action"]["command"] == "npm install -g @openai/codex"


def test_probe_clis_copilot_always_skip():
    with mock.patch("services.local_diagnostics._find_executable", return_value="/x"):
        out = cd.probe_clis()
    cop = [r for r in out if r["target"] == "runtime:copilot"][0]
    assert cop["status"] == "skip"


def test_probe_keyring_unavailable_warns():
    with mock.patch("services.server_registry.keyring_available", return_value=False):
        r = cd.probe_keyring()
    assert r["status"] == "warn" and r["code"] == "KEYRING_UNAVAILABLE"


def test_run_connection_check_aggregates_and_survives_probe_crash():
    with mock.patch("services.connection_doctor.probe_tracker", side_effect=RuntimeError("boom")), \
         mock.patch("services.connection_doctor.probe_servers", return_value=[]), \
         mock.patch("services.connection_doctor.probe_clis", return_value=[]), \
         mock.patch("services.connection_doctor.probe_keyring",
                    return_value=cd.build_result(target="keyring", target_label="Keyring",
                                                 group="credentials", status="ok")):
        snap = cd.run_connection_check()
    assert any(r["target"] == "tracker" and r["code"] == "UNKNOWN" for r in snap["results"])
    assert sum(snap["summary"].values()) == len(snap["results"])


def test_no_secret_leaks_in_snapshot():
    """C4 [ADICIÓN ARQUITECTO] — el detail crudo NO se filtra a la remediación."""
    r = cd.build_result(
        target="tracker", target_label="GitLab", group="tracker", status="fail",
        code="AUTH_401", detail="token glpat-SECRET123 rechazado",
        fmt={"service": "GitLab",
             "token_url": "https://gl.example/-/user_settings/personal_access_tokens",
             "host": "", "status": 401})
    rem = json.dumps(r["remediation"])
    assert "glpat-SECRET123" not in rem  # el detail crudo no llega a la remediación
