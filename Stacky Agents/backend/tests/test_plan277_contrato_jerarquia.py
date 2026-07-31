"""Plan 277 F1 — Centinelas del contrato de jerarquía de GitLab (24 casos).

Cero mocks: corren contra `services/gitlab_hierarchy.py` real, que es puro.
Cada test mata un defecto MEDIDO de los 4 motores divergentes que existían antes
(gitlab_provider.py:102-111, migrator_verify.py:69-77, migrator_epics.py:62,
incident_context.py:240).
"""
import pytest

from services.gitlab_hierarchy import (
    TIPOS_CANONICOS,
    TIPO_POR_DEFECTO,
    _MAX_TIPO,
    clasificar_issue,
    etiqueta_de_padre,
    etiqueta_de_tipo,
    normalizar_token,
    padre_desde_labels,
    tipo_desde_labels,
)


# ---------------------------------------------------------------------------
# 1-3 — normalizar_token: el espacio de create_item:314 y el acento que rompe \w+
# ---------------------------------------------------------------------------

def test_01_normalizar_token_pliega_acentos_a_ascii():
    assert normalizar_token("Implementación") == "implementacion"


def test_02_normalizar_token_colapsa_espacios_a_guion_bajo():
    # `migrator_verify.py:70` parsea con type::(\w+): un espacio pierde el token.
    assert normalizar_token("User Story") == "user_story"


def test_03_normalizar_token_recorta_y_baja():
    assert normalizar_token("  EPIC ") == "epic"
    assert normalizar_token(None) == ""


# ---------------------------------------------------------------------------
# 4-5 — etiqueta_de_tipo: nunca se escribe una etiqueta vacía en GitLab
# ---------------------------------------------------------------------------

def test_04_etiqueta_de_tipo_de_un_canonico():
    assert etiqueta_de_tipo("Epic") == "type::epic"
    assert etiqueta_de_tipo("Análisis Funcional") == "type::analisis_funcional"


def test_05_etiqueta_de_tipo_nunca_devuelve_el_prefijo_pelado():
    for vacio in (None, "", "   "):
        salida = etiqueta_de_tipo(vacio)
        assert salida != "type::", f"etiqueta pelada para {vacio!r}"
        assert salida == "type::issue"


# ---------------------------------------------------------------------------
# 6-7 — etiqueta_de_padre: va el iid, NUNCA el título (regla 4)
# ---------------------------------------------------------------------------

def test_06_etiqueta_de_padre_lleva_el_iid():
    assert etiqueta_de_padre(123) == "epic::123"
    assert etiqueta_de_padre("123") == "epic::123"


def test_07_etiqueta_de_padre_rechaza_lo_que_no_es_entero_positivo():
    for basura in ("abc", "", None, 0, -3, "Violeta Lugo", "12.5"):
        with pytest.raises(ValueError):
            etiqueta_de_padre(basura)


# ---------------------------------------------------------------------------
# 8-11 — tipo_desde_labels: una sola normalización, no tres
# ---------------------------------------------------------------------------

def test_08_tipo_desde_labels_cubre_los_ocho_canonicos():
    for token, esperado in TIPOS_CANONICOS.items():
        assert tipo_desde_labels([f"type::{token}"]) == esperado
    assert len(TIPOS_CANONICOS) == 8


def test_09_tipo_desde_labels_sin_senal_devuelve_none():
    for vacio in (None, [], "", "   ", ["otra", "workflow::doing"]):
        assert tipo_desde_labels(vacio) is None


def test_10_tipo_desde_labels_acepta_el_string_con_comas():
    # El migrador pasa las labels así (migrator_verify.py:46-47).
    assert tipo_desde_labels("otra, type::bug , workflow::doing") == "Bug"


def test_11_tipo_desde_labels_ignora_el_prefijo_sin_valor_y_no_mira_mayusculas():
    assert tipo_desde_labels(["type::"]) is None
    assert tipo_desde_labels(["type::", "type::bug"]) == "Bug"
    assert tipo_desde_labels(["TYPE::EPIC"]) == "Epic"


# ---------------------------------------------------------------------------
# 12 — EL GATE del determinismo: el orden del array NO decide
# ---------------------------------------------------------------------------

def test_12_multi_tipo_gana_el_alfabetico_en_CUALQUIER_orden():
    directo = ["type::tecnico", "type::epic"]
    invertido = ["type::epic", "type::tecnico"]
    # Si alguien vuelve a "el primero del array" (gitlab_provider.py:106-110),
    # una de las dos órdenes falla.
    assert tipo_desde_labels(directo) == "Epic"
    assert tipo_desde_labels(invertido) == "Epic"
    assert tipo_desde_labels(directo) == tipo_desde_labels(invertido)

    veredicto_directo = clasificar_issue({"labels": directo})
    veredicto_invertido = clasificar_issue({"labels": invertido})
    assert veredicto_directo["work_item_type"] == "Epic"
    assert veredicto_invertido["work_item_type"] == "Epic"
    assert len(veredicto_directo["avisos"]) == 1
    assert len(veredicto_invertido["avisos"]) == 1


# ---------------------------------------------------------------------------
# 13-15 — regla 5: no se pierde el dato del operador, pero entra en String(40)
# ---------------------------------------------------------------------------

def test_13_tipo_con_espacio_no_se_pierde():
    # `create_item` (gitlab_provider.py:314) escribe hoy "type::User Story".
    salida = tipo_desde_labels(["type::user story"])
    assert salida is not None
    assert salida != TIPO_POR_DEFECTO
    assert salida == "User Story"
    assert tipo_desde_labels(["type::User Story"]) == "User Story"


def test_14_token_desconocido_se_conserva_capitalizado():
    assert tipo_desde_labels(["type::spike"]) == "Spike"
    assert clasificar_issue({"labels": ["type::spike"]})["work_item_type"] == "Spike"


def test_15_token_de_200_chars_se_trunca_a_40_sin_reventar():
    largo = "x" * 200
    salida = tipo_desde_labels([f"type::{largo}"])          # Ticket.work_item_type es String(40)
    assert salida is not None
    assert len(salida) <= _MAX_TIPO
    veredicto = clasificar_issue({"labels": [f"type::{largo}"]})
    assert len(veredicto["work_item_type"]) <= _MAX_TIPO


# ---------------------------------------------------------------------------
# 16-18 — padre_desde_labels: un padre corrupto no revienta el int() del sync
# ---------------------------------------------------------------------------

def test_16_padre_desde_labels_lee_el_iid():
    assert padre_desde_labels(["epic::123"]) == 123
    assert padre_desde_labels("type::bug, epic::7") == 7


def test_17_padre_desde_labels_ignora_lo_que_no_es_iid_valido():
    for basura in (["epic::abc"], ["epic::-3"], ["epic::0"], ["epic::"], None, [], "", ["epic"]):
        assert padre_desde_labels(basura) is None, f"basura aceptada: {basura!r}"


def test_18_multi_padre_gana_el_menor_y_deja_aviso():
    assert padre_desde_labels(["epic::42", "epic::7"]) == 7
    assert padre_desde_labels(["epic::7", "epic::42"]) == 7
    veredicto = clasificar_issue({"labels": ["epic::42", "epic::7"]})
    assert veredicto["parent_iid"] == 7
    assert len(veredicto["avisos"]) == 1


# ---------------------------------------------------------------------------
# 19-24 — clasificar_issue sobre la forma LITERAL del payload de GitLab
# ---------------------------------------------------------------------------

def test_19_el_epic_nativo_no_contamina_parent_iid():
    # §3.2: el iid del epic vive en el namespace del GRUPO; parent_ado_id se
    # compara contra Ticket.ado_id, que lleva el iid dentro del PROYECTO.
    veredicto = clasificar_issue(
        {"id": 900, "iid": 12, "labels": ["type::epic"], "epic": {"id": 5, "iid": 9}}
    )
    assert veredicto["work_item_type"] == "Epic"
    assert veredicto["parent_iid"] is None
    assert veredicto["parent_native_epic_iid"] == 9
    assert veredicto["origen_padre"] == "ninguno"


def test_20_camino_feliz_del_contrato():
    veredicto = clasificar_issue(
        {"id": 901, "iid": 13, "labels": ["type::funcional", "epic::42"]}
    )
    assert veredicto["work_item_type"] == "Funcional"
    assert veredicto["parent_iid"] == 42
    assert veredicto["origen_tipo"] == "label"
    assert veredicto["origen_padre"] == "label"
    assert veredicto["avisos"] == []


def test_21_el_campo_nativo_type_se_usa_cuando_no_hay_etiqueta():
    veredicto = clasificar_issue({"iid": 14, "type": "task"})
    assert veredicto["work_item_type"] == "Task"
    assert veredicto["origen_tipo"] == "nativo"
    # GitLab >= 15.2 lo manda en mayúsculas en algunos endpoints.
    assert clasificar_issue({"type": "TASK"})["work_item_type"] == "Task"
    assert clasificar_issue({"issue_type": "incident"})["work_item_type"] == "Bug"


def test_22_el_type_issue_nativo_no_es_una_afirmacion():
    veredicto = clasificar_issue({"iid": 15, "type": "issue"})
    assert veredicto["work_item_type"] == "Issue"
    assert veredicto["origen_tipo"] == "defecto", "'issue' es el default de GitLab, no una señal"


def test_23_precedencia_la_etiqueta_gana_al_nativo_con_el_caso_contrario_sembrado():
    body = {"iid": 16, "labels": ["type::epic"], "type": "task"}
    con_etiqueta = clasificar_issue(body)
    assert con_etiqueta["work_item_type"] == "Epic"
    assert con_etiqueta["origen_tipo"] == "label"

    # Caso contrario SEMBRADO: el mismo body sin la etiqueta debe dar "Task".
    # Sin esto, el assert de arriba pasaría aunque el nativo nunca se leyera.
    sin_etiqueta = clasificar_issue({"iid": 16, "labels": [], "type": "task"})
    assert sin_etiqueta["work_item_type"] == "Task"
    assert sin_etiqueta["origen_tipo"] == "nativo"


def test_24_payload_parcial_no_revienta_y_devuelve_el_defecto():
    for parcial in ({}, {"epic": None}, {"epic": {}}, {"labels": None}, {"labels": ""}):
        veredicto = clasificar_issue(parcial)
        assert veredicto["work_item_type"] == TIPO_POR_DEFECTO
        assert veredicto["parent_iid"] is None
        assert veredicto["parent_native_epic_iid"] is None
        assert veredicto["origen_tipo"] == "defecto"
        assert veredicto["origen_padre"] == "ninguno"
        assert veredicto["avisos"] == []
        assert set(veredicto) == {
            "work_item_type",
            "parent_iid",
            "parent_native_epic_iid",
            "origen_tipo",
            "origen_padre",
            "avisos",
        }
