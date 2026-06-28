"""Plan 70 F9 -- Grupo helpers: _parent_exists_preflight usa provider.get_item.

Sites migrados:
  - _parent_exists_preflight: acepta provider=TrackerProvider; usa get_item(str(id))
    cuando provider no es None (GAP-B: get_work_item → get_item).

Sites ADO-only (allowlistados en F12, NO migrados):
  - 3864: _consumed_task_ado_status(ado=idempotency_ado) — idempotencia ADO.
  - 3939: _consumed_task_ado_status(ado=eq_ado) — equivalencia ADO.
  - 6364: _rev_client = _ado_client_for_ticket() — rev System.Rev ADO learning.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch


def test_parent_preflight_with_provider_calls_get_item():
    """Flag ON: _parent_exists_preflight usa provider.get_item(str(epic_ado_id))."""
    import api.tickets as tickets

    mock_provider = MagicMock(name="gitlab")
    mock_provider.get_item.return_value = {
        "id": 10,
        "fields": {"System.WorkItemType": "Epic"},
    }

    with patch.dict("os.environ", {"STACKY_PARENT_PREFLIGHT": "on"}):
        result = tickets._parent_exists_preflight(
            ado=None,
            epic_ado_id=10,
            operation_id="op-1",
            provider=mock_provider,
        )

    mock_provider.get_item.assert_called_once_with("10")
    assert result is not None
    assert result.get("ok") is True
    assert result.get("parent_type") == "Epic"


def test_parent_preflight_with_provider_not_found_returns_error():
    """Provider lanza excepcion 'not found' → _parent_exists_preflight devuelve error."""
    import api.tickets as tickets

    mock_provider = MagicMock(name="gitlab")
    exc = Exception("issue not found")
    mock_provider.get_item.side_effect = exc

    with patch.dict("os.environ", {"STACKY_PARENT_PREFLIGHT": "on"}):
        result = tickets._parent_exists_preflight(
            ado=None,
            epic_ado_id=999,
            operation_id="op-2",
            provider=mock_provider,
        )

    # "not found" en el mensaje → ADO_PARENT_NOT_FOUND
    assert result is not None
    assert result.get("ok") is False
    assert result.get("reason") == "ADO_PARENT_NOT_FOUND"


def test_parent_preflight_without_provider_uses_ado_get_work_item():
    """Flag OFF (provider=None): _parent_exists_preflight usa ado.get_work_item (legacy)."""
    import api.tickets as tickets

    mock_ado = MagicMock()
    mock_ado.get_work_item.return_value = {
        "id": 5,
        "fields": {"System.WorkItemType": "Epic"},
    }

    with patch.dict("os.environ", {"STACKY_PARENT_PREFLIGHT": "on"}):
        result = tickets._parent_exists_preflight(
            ado=mock_ado,
            epic_ado_id=5,
            operation_id="op-3",
            provider=None,  # flag OFF → fallback ADO
        )

    mock_ado.get_work_item.assert_called_once_with(5, ["System.Id", "System.WorkItemType", "System.Title"])
    assert result is not None
    assert result.get("ok") is True


def test_parent_preflight_flag_off_skips_all():
    """STACKY_PARENT_PREFLIGHT=off → retorna None sin llamar nada."""
    import api.tickets as tickets

    mock_provider = MagicMock(name="gitlab")
    mock_ado = MagicMock()

    with patch.dict("os.environ", {"STACKY_PARENT_PREFLIGHT": "off"}):
        result = tickets._parent_exists_preflight(
            ado=mock_ado,
            epic_ado_id=1,
            operation_id="op-4",
            provider=mock_provider,
        )

    assert result is None
    mock_provider.get_item.assert_not_called()
    mock_ado.get_work_item.assert_not_called()


def test_parent_preflight_ado_only_calls_stay_for_idempotency():
    """_consumed_task_ado_status sigue usando ado.get_work_item (ADO-only, no migrado)."""
    import api.tickets as tickets

    # Verificacion estatica: _consumed_task_ado_status usa getattr(ado, "get_work_item")
    import pathlib
    src = (pathlib.Path(__file__).resolve().parents[1] / "api" / "tickets.py").read_text(
        encoding="utf-8"
    )
    assert 'getattr(ado, "get_work_item"' in src, (
        "F9: _consumed_task_ado_status debe seguir usando getattr(ado, 'get_work_item') "
        "para idempotencia ADO-only"
    )
