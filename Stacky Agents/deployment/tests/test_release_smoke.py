from __future__ import annotations

import json
import os
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=5) as response:
        assert response.status == 200
        return json.loads(response.read().decode("utf-8"))


def _get_text(url: str) -> str:
    with urllib.request.urlopen(url, timeout=5) as response:
        assert response.status == 200
        return response.read().decode("utf-8", errors="replace")


def _wait_for_backend(base_url: str, process: subprocess.Popen, timeout_s: int = 45) -> None:
    deadline = time.time() + timeout_s
    last_error: Exception | None = None
    while time.time() < deadline:
        if process.poll() is not None:
            stdout, stderr = process.communicate(timeout=5)
            raise AssertionError(
                "stacky-backend.exe exited early\n"
                f"stdout:\n{stdout}\n\nstderr:\n{stderr}"
            )
        try:
            if _get_json(f"{base_url}/api/health") == {"ok": True}:
                return
        except (urllib.error.URLError, TimeoutError, AssertionError) as exc:
            last_error = exc
            time.sleep(0.5)
    raise AssertionError(f"backend did not become healthy: {last_error}")


def test_installed_release_serves_api_and_frontend(tmp_path: Path) -> None:
    release_root_raw = os.environ.get("STACKY_RELEASE_ROOT")
    assert release_root_raw, "STACKY_RELEASE_ROOT must point to the packaged release folder"

    release_root = Path(release_root_raw).resolve()
    backend_exe = release_root / "backend" / "stacky-backend.exe"
    frontend_index = release_root / "frontend" / "dist" / "index.html"

    assert backend_exe.exists(), f"missing backend executable: {backend_exe}"
    assert frontend_index.exists(), f"missing built frontend: {frontend_index}"

    port = _free_port()
    data_dir = tmp_path / "data"
    projects_dir = tmp_path / "projects"
    data_dir.mkdir()
    projects_dir.mkdir()

    env = os.environ.copy()
    env.update(
        {
            "PORT": str(port),
            "DATABASE_URL": f"sqlite:///{(data_dir / 'stacky_agents.db').as_posix()}",
            "LLM_BACKEND": "mock",
            "STACKY_APP_ROOT": str(release_root),
            "STACKY_DATA_DIR": str(data_dir),
            "STACKY_PROJECTS_DIR": str(projects_dir),
            "STACKY_FRONTEND_DIST": str(release_root / "frontend" / "dist"),
            "STACKY_REAPER_ENABLED": "false",
            "STACKY_MANIFEST_WATCHER_ENABLED": "false",
            "STACKY_OUTPUT_WATCHER_ENABLED": "false",
            "STACKY_RECOVERY_ON_STARTUP": "false",
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUNBUFFERED": "1",
        }
    )

    process = subprocess.Popen(
        [str(backend_exe)],
        cwd=str(release_root),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    base_url = f"http://127.0.0.1:{port}"
    try:
        _wait_for_backend(base_url, process)

        assert _get_json(f"{base_url}/api/health") == {"ok": True}

        projects = _get_json(f"{base_url}/api/projects")
        assert projects["ok"] is True
        assert isinstance(projects["projects"], list)

        html = _get_text(f"{base_url}/")
        assert "<!doctype html>" in html.lower()
        assert 'id="root"' in html
        assert "Stacky Agents" in html
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)
