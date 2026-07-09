"""tests/test_plan108_environment_remote.py — Plan 108 F5: plan/apply de
Ambientes contra el servidor (cierra RC3). Reusa el riel WinRM auditado del
Plan 105 (services/remote_exec.run_remote); mockea SIEMPRE ese origen."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

import services.environment_remote as env_remote
from services.environment_init import plan_environment


_FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "plan88_resolution_cases.json")
    .read_text(encoding="utf-8")
)
_CATALOG = _FIXTURE["catalog"]
_SETTINGS = {
    "environment_root": None,
    "folder_layout": {
        "entry": ["IN_"],
        "processing": ["productivas"],
        "output": ["salida"],
        "default": [],
    },
    "per_process_subfolder": False,
}


def _profile(root):
    settings = dict(_SETTINGS)
    settings["environment_root"] = root
    return {"process_catalog": _CATALOG, "devops_environment_settings": settings}


class TestBuildRemoteStatusCommand:
    """1-2. La sonda de estado es read-only y sin llaves (validador WinRM)."""

    def test_status_command_is_read_only(self):
        from services.remote_exec import is_read_only_command
        cmd = env_remote.build_remote_status_command(["D:\\Apps\\a", "D:\\Apps\\o'brien"])
        assert is_read_only_command(cmd) is True
        assert "''" in cmd  # comilla simple escapada de o'brien

    def test_status_command_has_no_braces(self):
        cmd = env_remote.build_remote_status_command(["D:\\Apps\\a", "D:\\Apps\\b"])
        assert "{" not in cmd and "}" not in cmd


class TestParseStatusOutput:
    """3. Parseo de pares True/False en el orden de abs_paths."""

    def test_parse_status_output_pairs(self):
        paths = ["D:\\a", "D:\\b", "D:\\c"]
        stdout = "True\nTrue\nTrue\nFalse\nFalse\nFalse\n"
        result = env_remote.parse_status_output(stdout, paths)
        assert result[0] == {"path": "D:\\a", "exists": True, "is_dir": True}
        assert result[1] == {"path": "D:\\b", "exists": True, "is_dir": False}
        assert result[2] == {"path": "D:\\c", "exists": False, "is_dir": False}

    def test_parse_status_output_wrong_line_count_raises(self):
        with pytest.raises(ValueError):
            env_remote.parse_status_output("True\nTrue\n", ["D:\\a", "D:\\b"])


class TestResolveRemoteLayout:
    """4. Layout puro con ntpath: fuera_de_root / path_demasiado_largo / normal."""

    def test_resolve_remote_layout_unsafe(self):
        root = "D:\\Apps\\Prod"
        long_rel = "x" * 250
        safe, unsafe = env_remote.resolve_remote_layout(root, ["..\\fuera", "IN_", long_rel])
        unsafe_map = dict(unsafe)
        assert unsafe_map["..\\fuera"] == "fuera_de_root"
        assert unsafe_map[long_rel] == "path_demasiado_largo"
        safe_map = dict(safe)
        assert safe_map["IN_"] == "D:\\Apps\\Prod\\IN_"


class TestPlanEnvironmentRemote:
    """5-6, 10-12. plan_environment_remote: mapeo de estados, propagación de
    error, paridad de shape con el local (C2 v2), path mutante no-fatal (C4
    v2), tope de chunks (C7 v2)."""

    def test_plan_remote_maps_statuses(self, monkeypatch):
        calls = []

        def fake_run_remote(alias, command, *, mode, conversation_id=None, user="", timeout_s=120):
            calls.append(mode)
            if len(calls) == 1:
                # Probe del root solo (1 path ⇒ 2 líneas). Existe como dir.
                return {"ok": True, "stdout": "True\nTrue\n", "stderr": "", "exit_code": 0, "duration_ms": 1}
            # Probe de a/b/c: a=to_create, b=exists_ok, c=conflict.
            return {
                "ok": True,
                "stdout": "False\nFalse\nTrue\nTrue\nTrue\nFalse\n",
                "stderr": "", "exit_code": 0, "duration_ms": 1,
            }

        monkeypatch.setattr("services.remote_exec.run_remote", fake_run_remote)
        result = env_remote.plan_environment_remote("srv1", "D:\\Apps\\Prod", ["a", "b", "c"])
        assert result["remote"] is True
        assert result["server_alias"] == "srv1"
        assert result["summary"] == {"to_create": 1, "exists_ok": 1, "conflict": 1, "unsafe": 0}

    def test_plan_remote_propagates_error(self, monkeypatch):
        def fake_run_remote(alias, command, *, mode, conversation_id=None, user="", timeout_s=120):
            return {"ok": False, "error": "no_password", "stdout": "", "stderr": "",
                    "exit_code": None, "duration_ms": 1}

        monkeypatch.setattr("services.remote_exec.run_remote", fake_run_remote)
        result = env_remote.plan_environment_remote("srv1", "D:\\Apps\\Prod", ["a"])
        assert result["ok"] is False
        assert result["error"] == "no_password"
        assert "to_create" not in result  # sin estados inventados

    def test_plan_remote_shape_parity_with_local(self, monkeypatch, tmp_path):
        def fake_run_remote(alias, command, *, mode, conversation_id=None, user="", timeout_s=120):
            n_paths = command.count("-PathType Container")
            return {"ok": True, "stdout": "False\nFalse\n" * n_paths, "stderr": "",
                    "exit_code": 0, "duration_ms": 1}

        monkeypatch.setattr("services.remote_exec.run_remote", fake_run_remote)
        remote_result = env_remote.plan_environment_remote("srv1", "D:\\Apps\\Prod", ["a", "b"])
        local_result = plan_environment(str(tmp_path), ["a", "b"])

        expected_keys = set(local_result.keys()) | {"remote", "server_alias"}
        assert set(remote_result.keys()) == expected_keys
        for entry in remote_result["entries"]:
            assert set(entry.keys()) == {"path", "status", "reason"}

    def test_mutant_token_path_marked_unsafe_not_fatal(self, monkeypatch):
        from services.remote_exec import is_read_only_command

        def fake_run_remote(alias, command, *, mode, conversation_id=None, user="", timeout_s=120):
            # C4 v2: TODO comando que efectivamente viaja a run_remote debe ser read-only.
            assert is_read_only_command(command) is True
            n_paths = command.count("-PathType Container")
            return {"ok": True, "stdout": "False\nFalse\n" * n_paths, "stderr": "",
                    "exit_code": 0, "duration_ms": 1}

        monkeypatch.setattr("services.remote_exec.run_remote", fake_run_remote)
        result = env_remote.plan_environment_remote("srv1", "D:\\Apps\\Prod", ["New-Releases", "normal"])
        by_path = {e["path"]: e for e in result["entries"]}
        assert by_path["New-Releases"]["status"] == "unsafe"
        assert by_path["New-Releases"]["reason"] == "path_no_verificable_remoto"
        assert by_path["normal"]["status"] == "to_create"

    def test_plan_remote_too_large(self, monkeypatch):
        calls = {"n": 0}

        def fake_run_remote(alias, command, *, mode, conversation_id=None, user="", timeout_s=120):
            calls["n"] += 1
            return {"ok": True, "stdout": "False\nFalse\n", "stderr": "", "exit_code": 0, "duration_ms": 1}

        monkeypatch.setattr("services.remote_exec.run_remote", fake_run_remote)
        rel_paths = [f"p{i}" for i in range(1001)]  # _CHUNK=50 ⇒ 21 chunks > 20
        result = env_remote.plan_environment_remote("srv1", "D:\\Apps\\Prod", rel_paths)
        assert result == {"ok": False, "error": "remote_plan_too_large", "remote": True}
        assert calls["n"] <= 1


class TestApplyEnvironmentRemote:
    """7. mkdir en modo write + verificación posterior en modo read_only."""

    def test_apply_remote_uses_write_mode_and_verifies(self, monkeypatch):
        calls = []
        state = {"wrote": False}

        def fake_run_remote(alias, command, *, mode, conversation_id=None, user="", timeout_s=120):
            calls.append(mode)
            if mode == "write":
                state["wrote"] = True
                return {"ok": True, "stdout": "", "stderr": "", "exit_code": 0, "duration_ms": 1}
            n_paths = command.count("-PathType Container")
            # Antes del write: "no existe" (fuerza to_create). Después: "existe como dir".
            line = ("True\nTrue\n" if state["wrote"] else "False\nFalse\n") * n_paths
            return {"ok": True, "stdout": line, "stderr": "", "exit_code": 0, "duration_ms": 1}

        monkeypatch.setattr("services.remote_exec.run_remote", fake_run_remote)
        approved = [("a", "D:\\Apps\\Prod\\a")]
        result = env_remote.apply_environment_remote("srv1", "D:\\Apps\\Prod", approved)

        assert "write" in calls
        assert calls[-1] == "read_only"  # verificación posterior
        assert result["created"] == ["a"]
        assert result["failed"] == []
        assert result["remote"] is True

    def test_apply_remote_empty_approved_no_calls(self, monkeypatch):
        def fake_run_remote(*a, **kw):
            raise AssertionError("no debería llamar a run_remote sin approved")

        monkeypatch.setattr("services.remote_exec.run_remote", fake_run_remote)
        result = env_remote.apply_environment_remote("srv1", "D:\\Apps\\Prod", [])
        assert result == {"created": [], "skipped_existing": [], "conflicts": [],
                           "unsafe": [], "failed": [], "remote": True}


class TestEnvironmentsRemoteEndpoints:
    """8-9. Wiring api/devops.py: gates de server_alias + byte-compat sin alias."""

    @pytest.fixture(autouse=True)
    def _flags(self):
        import config as cfg
        orig = {
            "STACKY_DEVOPS_ENVIRONMENTS_ENABLED": getattr(cfg.config, "STACKY_DEVOPS_ENVIRONMENTS_ENABLED", False),
            "STACKY_DEVOPS_REMOTE_TARGET_ENABLED": getattr(cfg.config, "STACKY_DEVOPS_REMOTE_TARGET_ENABLED", False),
            "STACKY_DEVOPS_SERVERS_ENABLED": getattr(cfg.config, "STACKY_DEVOPS_SERVERS_ENABLED", False),
            "STACKY_DEVOPS_REMOTE_CONSOLE_ENABLED": getattr(cfg.config, "STACKY_DEVOPS_REMOTE_CONSOLE_ENABLED", False),
        }
        cfg.config.STACKY_DEVOPS_ENVIRONMENTS_ENABLED = True
        yield
        for k, v in orig.items():
            setattr(cfg.config, k, v)

    def _client(self):
        from app import create_app
        app = create_app()
        app.config["TESTING"] = True
        return app.test_client()

    def test_endpoint_plan_with_alias_gates(self):
        import config as cfg
        client = self._client()
        root = "D:\\Apps\\Prod"
        with patch("api.devops.load_client_profile", return_value=_profile(root)):
            # Flag 108 OFF ⇒ 400 (remote_target_disabled).
            resp = client.post("/api/devops/environments/plan",
                                json={"project": "P", "server_alias": "srv1"})
            assert resp.status_code == 400

            # Flags ON + mocks ⇒ 200 y remote: True.
            cfg.config.STACKY_DEVOPS_REMOTE_TARGET_ENABLED = True
            cfg.config.STACKY_DEVOPS_SERVERS_ENABLED = True
            cfg.config.STACKY_DEVOPS_REMOTE_CONSOLE_ENABLED = True
            fake_result = {
                "root": root, "root_exists": True, "layout_fingerprint": "fp",
                "entries": [], "summary": {"to_create": 0, "exists_ok": 0, "conflict": 0, "unsafe": 0},
                "remote": True, "server_alias": "srv1",
            }
            with patch("services.server_registry.get_server", return_value={"alias": "srv1", "host": "h"}):
                with patch("services.environment_remote.plan_environment_remote", return_value=fake_result):
                    resp2 = client.post("/api/devops/environments/plan",
                                         json={"project": "P", "server_alias": "srv1"})
        assert resp2.status_code == 200
        assert resp2.get_json()["remote"] is True

    def test_endpoint_without_alias_byte_identical(self, tmp_path):
        client = self._client()
        with patch("api.devops.load_client_profile", return_value=_profile(str(tmp_path))):
            resp = client.post("/api/devops/environments/plan", json={"project": "P"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert "remote" not in data
        assert data["summary"]["to_create"] == 3
