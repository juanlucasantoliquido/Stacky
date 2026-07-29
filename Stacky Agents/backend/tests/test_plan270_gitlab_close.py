"""Plan 270 F2 — GitLab deja de reabrir lo que se le pidio cerrar.

NO TOCA DB, NO TOCA RED: doble del cliente que captura el body del PUT.
6 casos (§4 F2 del plan 270).
"""
import pytest

import config
from services.close_intent import ADO_CLOSE_STATES, resolve_close_target
from services.gitlab_provider import GitLabTrackerProvider
from services.incident_inbox import DEFAULT_CLOSED_STATES
from services.tracker_provider import CapabilityUnavailable

FLAG = "STACKY_TRACKER_STATE_WRITE_ROUTING_ENABLED"


class _FakeClient:
    """Registra las llamadas y no hace red. Devuelve ({}, 200)."""

    def __init__(self):
        self.calls = []

    def _project_path(self):
        return "grupo%2Fproy"

    def _request(self, method, path, json_body=None, params=None):
        self.calls.append({
            "method": method, "path": path,
            "json_body": json_body, "params": params,
        })
        if method == "GET":
            return ({"labels": ["type::bug", "stacky::in_progress"]}, 200)
        return ({"id": "1", "iid": "7", "state": "closed"}, 200)

    @property
    def puts(self):
        return [c for c in self.calls if c["method"] == "PUT"]


def _provider():
    prov = object.__new__(GitLabTrackerProvider)
    prov._client = _FakeClient()
    prov._project = "grupo/proy"
    prov._group = ""
    prov._epics_native = False
    return prov


def test_1_accepted_cierra():
    p = _provider()
    p.update_item_state("7", "accepted")
    assert len(p._client.puts) == 1
    assert p._client.puts[0]["json_body"]["state_event"] == "close"


def test_2_in_progress_sigue_reabriendo_no_regresion():
    """Un estado que LEGITIMAMENTE reabre conserva su comportamiento."""
    p = _provider()
    p.update_item_state("7", "in_progress")
    assert p._client.puts[0]["json_body"]["state_event"] == "reopen"


def test_3_estado_no_mapeable_con_flag_on_no_emite_ningun_put():
    p = _provider()
    with pytest.raises(CapabilityUnavailable):
        p.update_item_state("7", "Done")
    assert p._client.puts == [], "se emitio un PUT con un estado no mapeable"


def test_4_estado_no_mapeable_con_flag_off_conserva_el_comportamiento_historico(monkeypatch):
    """El rollback por flag: vuelve al bug, byte-identico."""
    monkeypatch.setattr(config.config, FLAG, False)
    p = _provider()
    p.update_item_state("7", "Done")
    assert len(p._client.puts) == 1
    assert p._client.puts[0]["json_body"]["state_event"] == "reopen"


def test_5_centinela_anti_reopen_la_cadena_real_cierra_de_verdad():
    """El corazon del plan: lo que manda la bandeja => lo que recibe GitLab.

    Ata F0 con F2: los 3 estados de cierre que ofrece la bandeja, traducidos por
    resolve_close_target y pasados a update_item_state, deben emitir "close".
    NINGUNO puede emitir "reopen".
    """
    for s in ADO_CLOSE_STATES:
        target = resolve_close_target("gitlab", s, DEFAULT_CLOSED_STATES)
        p = _provider()
        p.update_item_state("7", target.native_state)
        eventos = [c["json_body"]["state_event"] for c in p._client.puts]
        assert eventos == ["close"], f"{s!r} produjo {eventos!r}"
        assert "reopen" not in eventos


def test_6_el_mensaje_de_la_excepcion_nombra_el_ofensor_y_los_soportados():
    p = _provider()
    with pytest.raises(CapabilityUnavailable) as exc:
        p.update_item_state("7", "Done")
    msg = exc.value.reason
    assert "Done" in msg
    for soportado in ("accepted", "functional", "in_progress", "rejected"):
        assert soportado in msg
    assert exc.value.capability == "tracker.items.update_state"
    assert exc.value.provider == "gitlab"
