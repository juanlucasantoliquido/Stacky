"""Plan 79 — F3: aplicar estado-final al completar (determinista, ignora el del agente).

Testea el helper `_apply_task_state` de api/tickets.py directamente (unit),
sin levantar el endpoint Flask completo. El caso "flag OFF => legacy" a nivel
de endpoint completo (rama if/else de set_stacky_status_by_ado) se cubre en
test_plan79_centinela_estados.py, que sí monta la app Flask.
"""
from __future__ import annotations

import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _ticket(ado_id=555, project_name="demo"):
    return SimpleNamespace(ado_id=ado_id, stacky_project_name=project_name)


def _profile(next_state_ok="Done", in_progress=None, agent_type="developer"):
    machine = {}
    if in_progress is not None:
        machine["in_progress"] = in_progress
    if next_state_ok is not None:
        machine["next_state_ok"] = next_state_ok
    return {"tracker_state_machine": {agent_type: machine}}


def test_final_uses_config_not_agent_target():
    from api.tickets import _apply_task_state

    provider = MagicMock()
    provider.get_item.side_effect = Exception("no item")
    with patch("api.tickets.load_effective_client_profile", return_value=_profile(next_state_ok="Done")), \
         patch("api.tickets._provider_for_ticket", return_value=provider):
        result = _apply_task_state(
            ticket=_ticket(), agent_type="developer", phase="final",
            correlation_id="corr-1", publish_ok=True,
        )
    provider.update_item_state.assert_called_once_with("555", "Done")
    assert result.get("ok") is True
    assert result.get("to") == "Done"


def test_final_ignores_hallucinated_state():
    # target_ado_state del body NUNCA se pasa a _apply_task_state: el helper
    # solo conoce agent_type/phase y resuelve el target desde la config. Este
    # test prueba que, sin importar qué mande el body, el provider solo ve el
    # estado de la config.
    from api.tickets import _apply_task_state

    provider = MagicMock()
    provider.get_item.side_effect = Exception("no item")
    with patch("api.tickets.load_effective_client_profile", return_value=_profile(next_state_ok="Done")), \
         patch("api.tickets._provider_for_ticket", return_value=provider):
        _apply_task_state(
            ticket=_ticket(), agent_type="developer", phase="final",
            correlation_id="corr-2", publish_ok=True,
        )
    for call in provider.update_item_state.call_args_list:
        assert call.args[1] != "EstadoQueNoExiste"
        assert call.args[1] == "Done"


def test_final_skips_when_publish_failed():
    from api.tickets import _apply_task_state

    provider = MagicMock()
    with patch("api.tickets.load_effective_client_profile", return_value=_profile(next_state_ok="Done")), \
         patch("api.tickets._provider_for_ticket", return_value=provider):
        result = _apply_task_state(
            ticket=_ticket(), agent_type="developer", phase="final",
            correlation_id="corr-3", publish_ok=False,
        )
    provider.update_item_state.assert_not_called()
    assert result.get("skipped") is True
    assert result.get("reason") == "publish_not_ok"


def test_final_skips_without_config():
    from api.tickets import _apply_task_state

    provider = MagicMock()
    with patch("api.tickets.load_effective_client_profile", return_value=_profile(next_state_ok=None)), \
         patch("api.tickets._provider_for_ticket", return_value=provider):
        result = _apply_task_state(
            ticket=_ticket(), agent_type="developer", phase="final",
            correlation_id="corr-4", publish_ok=True,
        )
    provider.update_item_state.assert_not_called()
    assert result.get("skipped") is True


def test_final_provider_failure_does_not_raise():
    from api.tickets import _apply_task_state

    provider = MagicMock()
    provider.get_item.side_effect = Exception("no item")
    provider.update_item_state.side_effect = Exception("boom")
    with patch("api.tickets.load_effective_client_profile", return_value=_profile(next_state_ok="Done")), \
         patch("api.tickets._provider_for_ticket", return_value=provider):
        result = _apply_task_state(
            ticket=_ticket(), agent_type="developer", phase="final",
            correlation_id="corr-5", publish_ok=True,
        )
    assert result.get("ok") is False
    assert "error" in result


def test_final_noop_when_flag_off_is_endpoint_responsibility():
    # La decisión "si el flag está OFF, usar el target_ado_state legacy del
    # body" vive en el if/else de set_stacky_status_by_ado (tickets.py), NO en
    # _apply_task_state (que siempre aplica la config cuando el caller la
    # invoca). Ese comportamiento end-to-end lo prueba
    # test_plan79_centinela_estados.py::test_final_noop_when_flag_off contra
    # el endpoint Flask real. Este test documenta la separación de
    # responsabilidades para que no se intente duplicar el flag-check dentro
    # del helper.
    from harness.task_states import deterministic_task_states_enabled

    assert callable(deterministic_task_states_enabled)
