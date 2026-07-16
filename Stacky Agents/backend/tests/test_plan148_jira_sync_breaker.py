"""Plan 148 F4 — Circuit-breaker cableado en el sync Jira (V8: 448x "sync Jira
saltado" por credenciales ausentes). JiraConfigError es un fallo terminal de
config (abre el breaker); JiraApiError es un blip transitorio (sigue warneando,
no abre el breaker, para no silenciar una caida real de Jira).
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

import app as app_module  # noqa: E402
import services.jira_sync as jira_sync_module  # noqa: E402
from config import config as _cfg  # noqa: E402
from services import integration_breaker as brk  # noqa: E402
from services.jira_client import JiraApiError, JiraConfigError  # noqa: E402

_JIRA_PROJECT = "JIRAPROJ148"


@pytest.fixture(autouse=True)
def _isolated_breaker(tmp_path, monkeypatch):
    monkeypatch.setattr(brk, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(app_module, "get_active_project", lambda: "stacky-proj-148")
    monkeypatch.setattr(
        app_module, "get_project_config",
        lambda name: {"issue_tracker": {"type": "jira", "project": _JIRA_PROJECT}},
    )
    yield


def test_jira_missing_creds_opens_breaker(monkeypatch):
    def _raise(tracker_config=None):
        raise JiraConfigError("Credenciales Jira no encontradas. Configuralas en la Caja Fuerte.")

    monkeypatch.setattr(jira_sync_module, "sync_tickets", _raise)
    app_module._startup_sync(logging.getLogger("test.plan148.f4"))

    state = brk.get_state("jira_sync", _JIRA_PROJECT)
    assert state.open is True
    assert state.reason == brk.REASON_JIRA_NOT_CONFIGURED


def test_jira_skips_when_open(monkeypatch):
    brk.record_failure("jira_sync", _JIRA_PROJECT, brk.REASON_JIRA_NOT_CONFIGURED, "sin creds")

    called = {"n": 0}

    def _spy(tracker_config=None):
        called["n"] += 1
        return {"project": _JIRA_PROJECT, "fetched": 0, "created": 0, "updated": 0, "removed": 0}

    monkeypatch.setattr(jira_sync_module, "sync_tickets", _spy)
    app_module._startup_sync(logging.getLogger("test.plan148.f4"))

    assert called["n"] == 0


def test_jira_flag_off_legacy_warning(monkeypatch, caplog):
    monkeypatch.setattr(_cfg, "STACKY_INTEGRATION_DEGRADATION_ENABLED", False)

    def _raise(tracker_config=None):
        raise JiraConfigError("Credenciales Jira no encontradas.")

    monkeypatch.setattr(jira_sync_module, "sync_tickets", _raise)
    caplog.set_level(logging.WARNING)

    app_module._startup_sync(logging.getLogger("test.plan148.f4"))

    assert any("sync Jira saltado:" in r.message for r in caplog.records)
    assert brk.get_state("jira_sync", _JIRA_PROJECT).open is False


def test_jira_api_error_still_warns(monkeypatch, caplog):
    def _raise(tracker_config=None):
        raise JiraApiError("Jira 503 momentaneo")

    monkeypatch.setattr(jira_sync_module, "sync_tickets", _raise)
    caplog.set_level(logging.WARNING)

    app_module._startup_sync(logging.getLogger("test.plan148.f4"))

    assert any("sync Jira falló:" in r.message for r in caplog.records)
    assert brk.get_state("jira_sync", _JIRA_PROJECT).open is False
