"""tests/test_mg_mapping_priority_severity.py — Plan 217 F3.

Valida `tools/migrar_mantis_gitlab/mapping/priority_severity_map.py`:
`map_priority` reusa `_PRIORITY_MAP` REAL de `services/mantis_client.py`
(no un mock) y `map_severity` es texto simple con prefijo.
"""
from __future__ import annotations

import pytest

from services.mantis_client import _PRIORITY_MAP
from tools.migrar_mantis_gitlab.mapping.priority_severity_map import (
    UnmappedPriorityError,
    map_priority,
    map_severity,
)

_SCALE = {
    "1": "P1-critica",
    "2": "P2-alta",
    "3": "P3-normal",
    "4": "P4-baja",
    "5": "P5-trivial",
}


def test_reusa_priority_map_real_no_mock():
    # Verificación explícita de que _PRIORITY_MAP real tiene el valor
    # esperado (no un mock/duplicado): 30 (normal) -> escala 3.
    assert _PRIORITY_MAP[30] == 3


def test_map_priority_normal_da_p3_normal():
    label = map_priority(30, _SCALE)
    assert label == "priority::P3-normal"


def test_map_priority_urgente_da_p1_critica():
    # 50 = urgent -> _PRIORITY_MAP[50] == 1
    assert _PRIORITY_MAP[50] == 1
    label = map_priority(50, _SCALE, label_prefix="priority::")
    assert label == "priority::P1-critica"


def test_map_priority_id_desconocido_lanza_unmapped_priority_error():
    with pytest.raises(UnmappedPriorityError):
        map_priority(999999, _SCALE)


def test_map_priority_none_scale_level_lanza_unmapped_priority_error():
    # 10 = "none" -> _PRIORITY_MAP[10] es None
    assert _PRIORITY_MAP[10] is None
    with pytest.raises(UnmappedPriorityError):
        map_priority(10, _SCALE)


def test_map_priority_escala_faltante_en_config_lanza_unmapped_priority_error():
    scale_incompleta = {"1": "P1-critica"}  # falta "3"
    with pytest.raises(UnmappedPriorityError):
        map_priority(30, scale_incompleta)


def test_map_severity_label_simple_con_prefijo():
    assert map_severity("major") == "severity::major"
    assert map_severity("  minor  ", label_prefix="sev::") == "sev::minor"


# ── Prioridad por NOMBRE (regresión: bug hallado en el smoke E2E) ────────


def test_map_priority_acepta_nombre_ademas_de_id_numerico():
    """El adapter de SCRAPING lee la prioridad de la tabla HTML, donde Mantis
    muestra el NOMBRE ("high"/"alta"), no el ID numérico que sí trae la API
    REST. `map_priority` solo aceptaba int, así que toda migración por
    scraping —el único camino viable contra la instancia de referencia—
    perdía el 100% de las prioridades."""
    scale = {
        "1": "P1-critica", "2": "P2-alta", "3": "P3-normal",
        "4": "P4-baja", "5": "P5-trivial",
    }

    # ID numérico (API REST) — comportamiento previo, intacto.
    assert map_priority(40, scale) == "priority::P2-alta"
    assert map_priority("40", scale) == "priority::P2-alta"

    # Nombre en inglés (scraping, instancia en inglés).
    assert map_priority("high", scale) == "priority::P2-alta"
    assert map_priority("normal", scale) == "priority::P3-normal"
    assert map_priority("urgent", scale) == "priority::P1-critica"

    # Nombre en español (la instancia de referencia está en español),
    # tolerante a mayúsculas y acentos.
    assert map_priority("alta", scale) == "priority::P2-alta"
    assert map_priority("Alta", scale) == "priority::P2-alta"
    assert map_priority("baja", scale) == "priority::P5-trivial"
    assert map_priority("Inmediata", scale) == "priority::P1-critica"


def test_map_priority_nombre_desconocido_sigue_lanzando():
    """No se adivina: un nombre no reconocido sigue siendo un gap explícito."""
    scale = {"1": "P1", "2": "P2", "3": "P3", "4": "P4", "5": "P5"}
    with pytest.raises(UnmappedPriorityError):
        map_priority("prioridad-inventada", scale)
