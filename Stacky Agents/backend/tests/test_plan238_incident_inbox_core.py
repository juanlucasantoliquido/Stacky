"""tests/test_plan238_incident_inbox_core.py -- Plan 238 F1: nucleo puro."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from services.incident_inbox import (  # noqa: E402
    DEFAULT_CLOSED_STATES, DEFAULT_INCIDENT_TYPES, build_counts, is_incident_type,
    is_open_state, normalize_scope, resolve_closed_states, resolve_incident_types,
)


def test_defaults_espejan_el_frontend():
    assert DEFAULT_INCIDENT_TYPES == ("issue", "bug")
    assert DEFAULT_CLOSED_STATES == ("Done", "Closed", "Resolved", "Removed", "Completed")


def test_perfil_none_usa_default():
    assert resolve_incident_types(None) == (("issue", "bug"), "default")
    assert resolve_closed_states(None)[1] == "default"


def test_perfil_sin_secciones_usa_default():
    assert resolve_closed_states({"otra_cosa": 1})[1] == "default"


def test_incident_inbox_tiene_maxima_precedencia():
    perfil = {
        "incident_inbox": {"closed_states": ["Cerrado"]},
        "state_flow": {"closed_states": ["X"]},
    }
    assert resolve_closed_states(perfil) == (("Cerrado",), "profile_incident_inbox")


def test_state_flow_closed_states_tiene_precedencia_sobre_default():
    """Congela el LECTOR de 238 (no el comportamiento del 216 -- ver el test siguiente)."""
    perfil = {"state_flow": {"version": "1.0", "rules": [], "closed_states": ["Terminado", "Cancelado"]}}
    assert resolve_closed_states(perfil) == (("Terminado", "Cancelado"), "profile_state_flow")


def test_216_check_state_flow_no_rechaza_closed_states():
    """[ADICION A3] Guard cruzado REAL con el plan 216.

    Mientras 216 no exista, hace skip explicito. El dia que aterrice y su
    validador rechace la key aditiva `closed_states`, este test se pone ROJO.
    """
    try:
        from services.client_profile import _check_state_flow  # type: ignore[attr-defined]
    except ImportError:
        pytest.skip("Plan 216 sin implementar: no hay validador que probar")
    errores = _check_state_flow({"version": "1.0", "rules": [], "closed_states": ["Terminado"]})
    assert errores == [], f"el plan 216 rechaza la key aditiva closed_states: {errores}"


def test_state_flow_sin_closed_states_cae_a_default():
    perfil = {"state_flow": {"version": "1.0", "rules": []}}
    assert resolve_closed_states(perfil)[1] == "default"


def test_listas_corruptas_caen_al_siguiente_nivel():
    for corrupta in ([], ["", "  "], [1, 2], "Done", None):
        perfil = {"incident_inbox": {"closed_states": corrupta, "incident_types": corrupta}}
        assert resolve_closed_states(perfil)[1] == "default"
        assert resolve_incident_types(perfil)[1] == "default"


def test_is_incident_type_case_insensitive():
    tipos = DEFAULT_INCIDENT_TYPES
    for si in ("Issue", "ISSUE", " bug "):
        assert is_incident_type(si, tipos) is True
    for no in ("Task", "Epic", "", None):
        assert is_incident_type(no, tipos) is False


def test_is_open_state_case_insensitive():
    cerrados = DEFAULT_CLOSED_STATES
    for abierta in ("Active", "New", "En Progreso"):
        assert is_open_state(abierta, cerrados) is True
    for cerrada in ("Done", "closed", " Resolved "):
        assert is_open_state(cerrada, cerrados) is False


def test_gitlab_states_opened_closed():
    """Paridad de proveedor: GitLab usa opened/closed."""
    assert is_open_state("opened", DEFAULT_CLOSED_STATES) is True
    assert is_open_state("closed", DEFAULT_CLOSED_STATES) is False


def test_estado_vacio_es_abierta():
    assert is_open_state(None, DEFAULT_CLOSED_STATES) is True
    assert is_open_state("", DEFAULT_CLOSED_STATES) is True


def test_build_counts():
    assert build_counts(19, 12) == {"open": 7, "closed": 12, "total": 19}
    assert build_counts(0, 0) == {"open": 0, "closed": 0, "total": 0}
    assert build_counts(5, 99) == {"open": 0, "closed": 5, "total": 5}


def test_normalize_scope():
    for todas in ("all", "ALL", "todas"):
        assert normalize_scope(todas) == "all"
    for abierta in ("open", None, "", "basura"):
        assert normalize_scope(abierta) == "open"
