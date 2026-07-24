"""tests/test_mg_mapping_status.py — Plan 217 F3.

Valida `tools/migrar_mantis_gitlab/mapping/status_map.map_status`: mapeo
explícito, fallback a `_unmapped_fallback` con `used_fallback=True`,
insensibilidad a mayúsculas/espacios.
"""
from __future__ import annotations

from tools.migrar_mantis_gitlab.mapping.status_map import map_status

_FIELD_MAPPING_STATUS = {
    "new": {"gitlab_state": "opened", "label": "status::new"},
    "resolved": {"gitlab_state": "closed", "label": "status::resolved"},
    "closed": {"gitlab_state": "closed", "label": "status::closed"},
    "_unmapped_fallback": {"gitlab_state": "opened", "label": "status::sin_mapear"},
}


def test_status_mapeado_explicitamente_no_usa_fallback():
    gitlab_state, label, used_fallback = map_status("new", _FIELD_MAPPING_STATUS)
    assert gitlab_state == "opened"
    assert label == "status::new"
    assert used_fallback is False


def test_status_resolved_mapea_a_closed():
    gitlab_state, label, used_fallback = map_status("resolved", _FIELD_MAPPING_STATUS)
    assert gitlab_state == "closed"
    assert label == "status::resolved"
    assert used_fallback is False


def test_status_no_mapeado_usa_unmapped_fallback():
    gitlab_state, label, used_fallback = map_status("estado_inventado_xyz", _FIELD_MAPPING_STATUS)
    assert gitlab_state == "opened"
    assert label == "status::sin_mapear"
    assert used_fallback is True


def test_status_es_case_insensitive_y_tolera_espacios():
    gitlab_state, label, used_fallback = map_status("  RESOLVED  ", _FIELD_MAPPING_STATUS)
    assert gitlab_state == "closed"
    assert label == "status::resolved"
    assert used_fallback is False


def test_status_vacio_usa_unmapped_fallback():
    gitlab_state, label, used_fallback = map_status("", _FIELD_MAPPING_STATUS)
    assert used_fallback is True
    assert label == "status::sin_mapear"
