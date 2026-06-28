"""Plan 70 F2 — Wrapper _provider_for_ticket gateado por flag.

Usa el módulo config real (singleton Config()); parchea el atributo
STACKY_TICKETS_PROVIDER_ENABLED con monkeypatch.setattr (vuelve atrás solo
para el test). get_tracker_provider se mockea parcheando api.tickets.
"""
from __future__ import annotations

import pytest

from services.tracker_provider import TrackerConfigError


def test_flag_off_returns_none(monkeypatch):
    import api.tickets as tickets
    import config

    monkeypatch.setattr(config.config, "STACKY_TICKETS_PROVIDER_ENABLED", False)
    # Incluso si get_tracker_provider estuviera disponible, flag OFF retorna None
    assert tickets._provider_for_ticket(project_name="any") is None


def test_flag_on_azure_returns_provider(monkeypatch):
    import api.tickets as tickets
    import config

    monkeypatch.setattr(config.config, "STACKY_TICKETS_PROVIDER_ENABLED", True)

    class _FakeAzure:
        name = "azure_devops"

    monkeypatch.setattr(tickets, "get_tracker_provider", lambda project=None: _FakeAzure())
    prov = tickets._provider_for_ticket(project_name="p")
    assert prov is not None
    assert prov.name == "azure_devops"


def test_flag_on_gitlab_unenabled_returns_none(monkeypatch):
    import api.tickets as tickets
    import config

    monkeypatch.setattr(config.config, "STACKY_TICKETS_PROVIDER_ENABLED", True)

    def _raise(project=None):
        raise TrackerConfigError("issue_tracker.type=gitlab pero STACKY_GITLAB_ENABLED=false")

    monkeypatch.setattr(tickets, "get_tracker_provider", _raise)
    # No debe propagar: retorna None para que el caller caiga a ADO
    assert tickets._provider_for_ticket(project_name="p") is None


def test_flag_on_gitlab_enabled_returns_provider(monkeypatch):
    import api.tickets as tickets
    import config

    monkeypatch.setattr(config.config, "STACKY_TICKETS_PROVIDER_ENABLED", True)

    class _FakeGitlab:
        name = "gitlab"

    monkeypatch.setattr(tickets, "get_tracker_provider", lambda project=None: _FakeGitlab())
    prov = tickets._provider_for_ticket(project_name="p")
    assert prov is not None
    assert prov.name == "gitlab"
