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


# ---------------------------------------------------------------------------
# F2 — el corto-circuito por flag aplica SOLO cuando el tracker es Azure DevOps
# ---------------------------------------------------------------------------
#
# `STACKY_TICKETS_PROVIDER_ENABLED` está BLOQUEADA desde 2026-07-15, y el motivo
# documentado en su propio registro de arnés es ENTERAMENTE sobre el provider de
# ADO: «AdoTrackerProvider (services/ado_provider.py) construye su cliente ADO
# llamando build_ado_client() DIRECTO ... 27 tests en 8 archivos mockean _ado».
# La rama GitLab no tiene esa deuda, y mantenerla apagada dejaba a los proyectos
# GitLab sin publicador de épica.
#
# Medido en vivo (ejecución 210, proyecto RIPLEY): el post-hook del Plan 278
# corrió, pero `_publish_epic_to_ado` (api/tickets.py:7105-7118) recibió
# provider=None y cayó al camino ADO, sellando
# `epic_publish_error = "El proyecto 'RIPLEY' no usa Azure DevOps (tracker_type=gitlab)."`


def _cfg_tracker(tracker_type: str | None) -> dict:
    tracker: dict = {}
    if tracker_type is not None:
        tracker["type"] = tracker_type
    return {"name": "PROY", "issue_tracker": tracker}


def test_flag_off_tracker_gitlab_igual_devuelve_provider(monkeypatch):
    """Tracker GitLab + flag OFF → el provider SE RESUELVE (no corta)."""
    import api.tickets as tickets
    import config
    import project_manager

    monkeypatch.setattr(config.config, "STACKY_TICKETS_PROVIDER_ENABLED", False)
    monkeypatch.setattr(
        project_manager, "get_project_config", lambda name: _cfg_tracker("gitlab")
    )

    class _FakeGitlab:
        name = "gitlab"

    monkeypatch.setattr(tickets, "get_tracker_provider", lambda project=None: _FakeGitlab())
    prov = tickets._provider_for_ticket(project_name="PROY")
    assert prov is not None
    assert prov.name == "gitlab"


def test_flag_off_tracker_ado_sigue_devolviendo_none(monkeypatch):
    """REGRESIÓN DURA: tracker ADO + flag OFF → None, byte-idéntico a hoy.

    Además se asegura que el camino ADO ni siquiera consulta la fábrica de
    providers: si `get_tracker_provider` llegara a invocarse, el corto-circuito
    dejó de aplicar donde la deuda del Plan 70 sigue viva.
    """
    import api.tickets as tickets
    import config
    import project_manager

    monkeypatch.setattr(config.config, "STACKY_TICKETS_PROVIDER_ENABLED", False)
    monkeypatch.setattr(
        project_manager, "get_project_config", lambda name: _cfg_tracker("azure_devops")
    )

    llamadas: list[str | None] = []

    def _spy(project=None):
        llamadas.append(project)
        raise AssertionError("get_tracker_provider NO debe invocarse con tracker ADO y flag OFF")

    monkeypatch.setattr(tickets, "get_tracker_provider", _spy)
    assert tickets._provider_for_ticket(project_name="PROY") is None
    assert llamadas == []


def test_flag_off_tracker_no_resoluble_falla_cerrado(monkeypatch):
    """Sin `issue_tracker.type` → se asume ADO → None (comportamiento de hoy)."""
    import api.tickets as tickets
    import config
    import project_manager

    monkeypatch.setattr(config.config, "STACKY_TICKETS_PROVIDER_ENABLED", False)
    monkeypatch.setattr(
        project_manager, "get_project_config", lambda name: _cfg_tracker(None)
    )
    monkeypatch.setattr(
        tickets, "get_tracker_provider",
        lambda project=None: (_ for _ in ()).throw(
            AssertionError("no debe resolverse con tracker desconocido")
        ),
    )
    assert tickets._provider_for_ticket(project_name="PROY") is None


def test_flag_off_gitlab_sin_gitlab_enabled_no_propaga(monkeypatch):
    """Tracker GitLab + flag OFF + GitLab deshabilitado → None, sin propagar."""
    import api.tickets as tickets
    import config
    import project_manager

    monkeypatch.setattr(config.config, "STACKY_TICKETS_PROVIDER_ENABLED", False)
    monkeypatch.setattr(
        project_manager, "get_project_config", lambda name: _cfg_tracker("gitlab")
    )

    def _raise(project=None):
        raise TrackerConfigError("issue_tracker.type=gitlab pero STACKY_GITLAB_ENABLED=false")

    monkeypatch.setattr(tickets, "get_tracker_provider", _raise)
    assert tickets._provider_for_ticket(project_name="PROY") is None


def test_flag_off_gitlab_resuelve_por_ticket_no_por_tracker_type_de_la_fila(monkeypatch):
    """El `tracker_type` de la FILA del ticket no decide; manda el config.

    Espejo del mismo riesgo cerrado en F1: el Brief Pool Ticket 1167 tiene
    `tracker_type='azure_devops'` con `stacky_project_name='RIPLEY'` (GitLab).
    """
    import api.tickets as tickets
    import config
    import project_manager

    monkeypatch.setattr(config.config, "STACKY_TICKETS_PROVIDER_ENABLED", False)
    monkeypatch.setattr(
        project_manager, "get_project_config", lambda name: _cfg_tracker("gitlab")
    )

    class _FakeTicket:
        stacky_project_name = "PROY"
        tracker_type = "azure_devops"  # mentira heredada del default de la columna

    class _FakeGitlab:
        name = "gitlab"

    monkeypatch.setattr(tickets, "get_tracker_provider", lambda project=None: _FakeGitlab())
    prov = tickets._provider_for_ticket(ticket=_FakeTicket())
    assert prov is not None
    assert prov.name == "gitlab"
