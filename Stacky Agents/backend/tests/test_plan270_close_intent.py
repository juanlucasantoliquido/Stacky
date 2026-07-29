"""Plan 270 F0 — Tests del resolver puro de la intencion de cierre.

PURO: no toca DB, no toca red. Solo funciones deterministas sobre strings.
11 casos (§4 F0 del plan 270).
"""
import pytest

from services.close_intent import (
    ADO_CLOSE_STATES,
    GITLAB_CLOSE_STATE,
    GITLAB_CLOSING_LOGICAL_STATES,
    GITLAB_LOGICAL_STATES,
    CloseTarget,
    is_close_state,
    resolve_close_target,
)
from services.incident_inbox import DEFAULT_CLOSED_STATES


def test_1_ado_passthrough_done():
    t = resolve_close_target("azure_devops", "Done", DEFAULT_CLOSED_STATES)
    assert t.native_state == "Done"
    assert t.closes is True
    assert t.source == "passthrough"
    assert t.tracker_type == "azure_devops"
    # El CloseTarget es inmutable: nadie puede reescribir el destino resuelto.
    assert isinstance(t, CloseTarget)
    with pytest.raises(Exception):
        t.native_state = "otro"  # type: ignore[misc]
    # is_close_state normaliza igual que services/incident_inbox.py:23.
    assert is_close_state("  DONE ", DEFAULT_CLOSED_STATES) is True
    assert is_close_state("Active", DEFAULT_CLOSED_STATES) is False
    assert is_close_state(None, DEFAULT_CLOSED_STATES) is False


def test_2_tracker_none_estado_intermedio_no_cierra():
    t = resolve_close_target(None, "Reviewed by Dev", DEFAULT_CLOSED_STATES)
    assert t.native_state == "Reviewed by Dev"
    assert t.closes is False
    assert t.source == "passthrough"


def test_3_gitlab_done_se_mapea_a_accepted():
    t = resolve_close_target("gitlab", "Done", DEFAULT_CLOSED_STATES)
    assert t.native_state == "accepted"
    assert t.closes is True
    assert t.source == "mapped"
    assert t.tracker_type == "gitlab"


def test_4_gitlab_normaliza_espacios_y_mayusculas():
    t = resolve_close_target("gitlab", "  cLoSeD  ", DEFAULT_CLOSED_STATES)
    assert t.native_state == "accepted"
    assert t.closes is True


def test_5_gitlab_estado_logico_in_progress_no_cierra():
    """C8: in_progress ya es una clave logica y su mapping tiene closed=False."""
    t = resolve_close_target("gitlab", "in_progress", DEFAULT_CLOSED_STATES)
    assert t.native_state == "in_progress"
    assert t.source == "already_logical"
    assert t.closes is False


def test_6_gitlab_estado_no_mapeable_levanta():
    with pytest.raises(ValueError) as exc:
        resolve_close_target("gitlab", "Cualquier Cosa", DEFAULT_CLOSED_STATES)
    assert str(exc.value).startswith("unmappable_state:")

    # Casos borde declarados en la fase: vacio, None y closed_states vacio.
    # El modulo NO confia en su llamador ni inventa un default.
    for pedido in ("", None):
        with pytest.raises(ValueError) as exc2:
            resolve_close_target("gitlab", pedido, DEFAULT_CLOSED_STATES)  # type: ignore[arg-type]
        assert str(exc2.value).startswith("unmappable_state:")
    with pytest.raises(ValueError) as exc3:
        resolve_close_target("gitlab", "Done", ())
    assert str(exc3.value).startswith("unmappable_state:")
    assert is_close_state("done", ()) is False


def test_7_tracker_no_soportado_levanta():
    with pytest.raises(ValueError) as exc:
        resolve_close_target("jira", "Done", DEFAULT_CLOSED_STATES)
    assert str(exc.value).startswith("unsupported_tracker:")


def test_8_centinela_anti_reopen_todos_los_estados_de_cierre_ado_cierran_en_gitlab():
    """El corazon del plan: ninguno de los 3 estados que ofrece la bandeja puede
    terminar en un target que NO cierre (que es lo que producia el reopen)."""
    for s in ADO_CLOSE_STATES:
        t = resolve_close_target("gitlab", s, DEFAULT_CLOSED_STATES)
        assert t.closes is True, f"{s!r} no cierra en GitLab"
        assert t.native_state == GITLAB_CLOSE_STATE


def test_9_centinela_espejo_de_claves_logicas():
    """Si alguien agrega una clave a _state_map_for_gitlab y no aca, rojo."""
    from services.gitlab_provider import GitLabTrackerProvider

    prov = object.__new__(GitLabTrackerProvider)
    assert set(GITLAB_LOGICAL_STATES) == set(prov._state_map_for_gitlab().keys())


def test_10_centinela_espejo_de_cierre():
    """C8: los estados logicos cuyo mapping tiene closed=True son DOS."""
    from services.gitlab_provider import GitLabTrackerProvider

    prov = object.__new__(GitLabTrackerProvider)
    reales = {k for k, v in prov._state_map_for_gitlab().items() if v.get("closed")}
    assert set(GITLAB_CLOSING_LOGICAL_STATES) == reales
    assert reales == {"accepted", "rejected"}


def test_11_centinela_de_aridad_de_resolve_closed_states():
    """C1 — el bug de integracion, fijado por escrito.

    resolve_closed_states devuelve (estados, fuente): DOS elementos. Pasar la
    2-tupla entera hace que is_close_state nunca reconozca "Done" y todo cierre
    GitLab muera con unmappable_state.
    """
    from services.incident_inbox import resolve_closed_states

    res = resolve_closed_states(None)
    assert isinstance(res, tuple)
    assert len(res) == 2
    assert isinstance(res[0], tuple)
    assert isinstance(res[1], str)

    # Pasar la 2-tupla entera es un ERROR y debe fallar declarado.
    with pytest.raises(ValueError) as exc:
        resolve_close_target("gitlab", "Done", res)
    assert str(exc.value).startswith("unmappable_state:")

    # Desempaquetada, funciona.
    t = resolve_close_target("gitlab", "Done", res[0])
    assert t.native_state == "accepted"


