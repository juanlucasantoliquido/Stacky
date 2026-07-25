"""Plan 70 F10 -- Grupo sync: branch provider/GAP-A para sync de tickets.

Sites migrados:
  - 569: sync_from_ado endpoint → _sync_via_provider_or_ado
  - 5425: sync-v2 endpoint → _sync_via_provider_or_ado

Comportamiento:
  - Flag OFF: _provider_for_ticket → None → sync_tickets(client=ado) (byte-identico)
  - Flag ON + ADO: provider.name == "azure_devops" → sync_tickets (identico)
  - Flag ON + GitLab: provider.name == "gitlab" → NotImplementedError ruidoso
    (GAP-A: sync GitLab diferido, Plan 71)

Regresion sync_tickets:
  - Llamar _sync_via_provider_or_ado(None) con flag OFF debe delegar a sync_tickets
    y devolver su resultado sin modificar.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch


def test_sync_helper_flag_off_calls_sync_tickets():
    """Flag OFF: _sync_via_provider_or_ado delega a sync_tickets (byte-identico)."""
    import api.tickets as tickets

    mock_result = {"created": 2, "updated": 1, "removed": 0}

    with patch("api.tickets._provider_for_ticket", return_value=None), \
         patch("api.tickets.sync_tickets", return_value=mock_result) as mock_sync, \
         patch("api.tickets._ado_client_for_ticket", return_value=MagicMock()):
        result = tickets._sync_via_provider_or_ado(project_name="p")

    mock_sync.assert_called_once()
    assert result == mock_result


def test_sync_helper_flag_on_ado_provider_calls_sync_tickets():
    """Flag ON + ADO provider: cae a sync_tickets (identico — ADO usa su propio sync)."""
    import api.tickets as tickets

    mock_provider = MagicMock()
    mock_provider.name = "azure_devops"
    mock_result = {"created": 0, "updated": 3, "removed": 1}

    with patch("api.tickets._provider_for_ticket", return_value=mock_provider), \
         patch("api.tickets.sync_tickets", return_value=mock_result) as mock_sync, \
         patch("api.tickets._ado_client_for_ticket", return_value=MagicMock()):
        result = tickets._sync_via_provider_or_ado(project_name="p")

    mock_sync.assert_called_once()
    assert result == mock_result


def test_sync_helper_flag_on_gitlab_declara_capacidad_ausente():
    """Flag ON + GitLab: la capacidad ausente se DECLARA (GAP-A, Plan 220 la implementa).

    Plan 218 F6 reemplazó el NotImplementedError ruidoso por `CapabilityUnavailable`:
    el hueco sigue siendo visible (nunca se silencia), pero ahora es un límite tipado
    que el endpoint traduce a un 200 accionable en vez de un 500 mudo.
    """
    import api.tickets as tickets
    import pytest
    from services.tracker_provider import CapabilityUnavailable

    mock_provider = MagicMock()
    mock_provider.name = "gitlab"

    with patch("api.tickets._provider_for_ticket", return_value=mock_provider):
        with pytest.raises(CapabilityUnavailable) as exc_info:
            tickets._sync_via_provider_or_ado(project_name="p")

    assert exc_info.value.capability == "tracker.sync.full"
    assert exc_info.value.provider == "gitlab"
    assert "gitlab" in str(exc_info.value).lower()


def test_sync_helper_is_idempotent_with_same_input():
    """_sync_via_provider_or_ado es pura respecto a su helper: mismo input → misma delegacion."""
    import api.tickets as tickets

    call_count = {"n": 0}

    def fake_sync_tickets(client=None, **kw):
        call_count["n"] += 1
        return {"created": call_count["n"]}

    with patch("api.tickets._provider_for_ticket", return_value=None), \
         patch("api.tickets.sync_tickets", side_effect=fake_sync_tickets), \
         patch("api.tickets._ado_client_for_ticket", return_value=MagicMock()):
        r1 = tickets._sync_via_provider_or_ado(project_name="p")
        r2 = tickets._sync_via_provider_or_ado(project_name="p")

    assert r1["created"] == 1
    assert r2["created"] == 2  # dos llamadas → dos resultados distintos (delegacion directa)


def test_sync_source_has_helper_function():
    """_sync_via_provider_or_ado existe en tickets.py (static analysis)."""
    import pathlib
    src = (pathlib.Path(__file__).resolve().parents[1] / "api" / "tickets.py").read_text(encoding="utf-8")
    assert "_sync_via_provider_or_ado" in src
    assert "sync_tickets(" in src  # delega a legacy
