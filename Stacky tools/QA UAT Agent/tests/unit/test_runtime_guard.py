from pathlib import Path

import pytest


def test_runtime_guard_blocks_iisexpress_command():
    from runtime_guard import RuntimeGuardError, validate_command

    with pytest.raises(RuntimeGuardError) as exc:
        validate_command(["iisexpress.exe", "/site:AgendaWebPacifico"])

    assert exc.value.reason == "FORBIDDEN_RUNTIME_MANAGEMENT"
    assert exc.value.token == "iisexpress.exe"


def test_runtime_guard_blocks_applicationhost_config_path():
    from runtime_guard import RuntimeGuardError, validate_path

    with pytest.raises(RuntimeGuardError) as exc:
        validate_path(Path(r"C:\Users\me\Documents\IISExpress\config\applicationhost.config"))

    assert exc.value.reason == "FORBIDDEN_RUNTIME_MANAGEMENT"


def test_runtime_guard_blocks_frt_iis_write_command():
    from runtime_guard import RuntimeGuardError, validate_command

    with pytest.raises(RuntimeGuardError) as exc:
        validate_command(["python", "server_exception_monitor.py", "--enable-frt"])

    assert exc.value.reason == "FORBIDDEN_RUNTIME_MANAGEMENT"
    assert exc.value.token == "--enable-frt"


def test_command_runner_returns_blocked_without_subprocess(tmp_path):
    from command_runner import CommandRunner

    runner = CommandRunner(run_dir=tmp_path, stage="unit")
    result = runner.run_logged(["taskkill", "/IM", "iisexpress.exe"], label="bad")

    assert result["ok"] is False
    assert result["returncode"] == 126
    assert result["guardrail"]["reason"] == "FORBIDDEN_RUNTIME_MANAGEMENT"
