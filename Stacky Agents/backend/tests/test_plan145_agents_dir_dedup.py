"""Plan 145 F4 — dedup del warning agents_dir (D7) vía log_state_change.
"""
from __future__ import annotations

import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
import services.log_throttle as log_throttle  # noqa: E402
import project_manager  # noqa: E402


def test_agents_dir_invalid_logs_once_for_same_path(monkeypatch, caplog):
    log_throttle.reset()
    caplog.set_level(logging.WARNING, logger="stacky.config")
    monkeypatch.setattr(project_manager, "get_active_project", lambda: "proj1")
    monkeypatch.setattr(
        project_manager, "get_project_config", lambda p: {"agents_dir": "Z:/no/existe"}
    )

    config._project_agents_dir_if_configured()
    config._project_agents_dir_if_configured()

    records = [
        r for r in caplog.records
        if r.name == "stacky.config" and "agents_dir configurado" in r.getMessage()
    ]
    assert len(records) == 1


def test_agents_dir_relogs_on_different_path(monkeypatch, caplog):
    log_throttle.reset()
    caplog.set_level(logging.WARNING, logger="stacky.config")
    monkeypatch.setattr(project_manager, "get_active_project", lambda: "proj1")

    monkeypatch.setattr(
        project_manager, "get_project_config", lambda p: {"agents_dir": "Z:/no/existe"}
    )
    config._project_agents_dir_if_configured()

    monkeypatch.setattr(
        project_manager, "get_project_config", lambda p: {"agents_dir": "Q:/otro/malo"}
    )
    config._project_agents_dir_if_configured()

    records = [
        r for r in caplog.records
        if r.name == "stacky.config" and "agents_dir configurado" in r.getMessage()
    ]
    assert len(records) == 2


def test_agents_dir_valid_logs_nothing(tmp_path, monkeypatch, caplog):
    log_throttle.reset()
    caplog.set_level(logging.WARNING, logger="stacky.config")
    monkeypatch.setattr(project_manager, "get_active_project", lambda: "proj1")
    monkeypatch.setattr(
        project_manager, "get_project_config", lambda p: {"agents_dir": str(tmp_path)}
    )

    result = config._project_agents_dir_if_configured()

    assert result == tmp_path.resolve()
    records = [r for r in caplog.records if r.name == "stacky.config"]
    assert len(records) == 0
