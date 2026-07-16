import logging
import sys
from pathlib import Path

# Bootstrap sys.path (C4): backend/tests/conftest.py YA agrega backend/ a
# sys.path y setea STACKY_TEST_MODE (plan 145), pero se mantiene este bootstrap
# manual explícito por consistencia con el patrón preexistente del repo
# (test_diag_endpoint.py:22-24, test_runtime_paths.py:17-18) — es redundante
# con conftest.py pero inofensivo y robusto ante otros cwd / plain pytest.
ROOT = Path(__file__).resolve().parent.parent  # backend/
sys.path.insert(0, str(ROOT))

import app  # noqa: E402  (módulo backend)

def test_preflight_no_active_project_logs_info_not_warning(monkeypatch, caplog, tmp_path):
    missing = tmp_path / "no_existe" / "Agentes" / "outputs"
    monkeypatch.setattr("runtime_paths.repo_root", lambda: tmp_path / "no_existe")
    monkeypatch.setattr("services.agent_html_output.outputs_dir", lambda: missing)
    monkeypatch.setattr("services.ado_client.ado_pat_present", lambda: True)
    monkeypatch.setattr("project_manager.get_active_project", lambda: None)
    logger = logging.getLogger("stacky_agents.app")
    with caplog.at_level(logging.INFO, logger="stacky_agents.app"):
        app._log_completion_preflight(logger)
    msgs = [r for r in caplog.records if "outputs_dir" in r.getMessage()]
    assert msgs, "esperaba al menos un mensaje de preflight"
    assert not any(r.levelno == logging.WARNING and "NO existe" in r.getMessage()
                   for r in caplog.records)

def test_preflight_active_project_missing_dir_warns(monkeypatch, caplog, tmp_path):
    missing = tmp_path / "ws" / "Agentes" / "outputs"
    monkeypatch.setattr("runtime_paths.repo_root", lambda: tmp_path / "ws")
    monkeypatch.setattr("services.agent_html_output.outputs_dir", lambda: missing)
    monkeypatch.setattr("services.ado_client.ado_pat_present", lambda: True)
    monkeypatch.setattr("project_manager.get_active_project", lambda: "RSPACIFICO")
    logger = logging.getLogger("stacky_agents.app")
    with caplog.at_level(logging.WARNING, logger="stacky_agents.app"):
        app._log_completion_preflight(logger)
    assert any(r.levelno == logging.WARNING and "NO existe" in r.getMessage()
               for r in caplog.records)
