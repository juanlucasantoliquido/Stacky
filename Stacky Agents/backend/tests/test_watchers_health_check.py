import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # backend/ (C4: redundante con conftest.py, ver test_completion_preflight.py)

import services.local_diagnostics as ld

def test_no_active_project_warns(monkeypatch, tmp_path):
    monkeypatch.delenv("STACKY_WATCHERS_HEALTH_CHECK", raising=False)
    monkeypatch.setattr(ld, "get_active_project", lambda: None)
    monkeypatch.setattr("runtime_paths.repo_root", lambda: tmp_path)
    monkeypatch.setattr("services.agent_html_output.outputs_dir",
                        lambda: tmp_path / "Agentes" / "outputs")
    r = ld._check_watchers_active()
    assert r["id"] == "watchers" and r["status"] == "warning"

def test_active_project_with_dir_ok(monkeypatch, tmp_path):
    monkeypatch.delenv("STACKY_WATCHERS_HEALTH_CHECK", raising=False)
    od = tmp_path / "Agentes" / "outputs"; od.mkdir(parents=True)
    monkeypatch.setattr(ld, "get_active_project", lambda: "RSPACIFICO")
    monkeypatch.setattr("runtime_paths.repo_root", lambda: tmp_path)
    monkeypatch.setattr("services.agent_html_output.outputs_dir", lambda: od)
    r = ld._check_watchers_active()
    assert r["status"] == "ok"

def test_kill_switch_disables(monkeypatch):
    monkeypatch.setenv("STACKY_WATCHERS_HEALTH_CHECK", "false")
    monkeypatch.setattr(ld, "get_active_project", lambda: None)
    r = ld._check_watchers_active()
    assert r["status"] == "ok"
