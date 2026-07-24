"""tests/test_mg_mapping_extra.py — Plan 217 F3 (no obligatorio, cobertura
liviana adicional pedida como "bienvenida" por el batch).

Valida `category_map`, `tag_map`, `version_map` y `custom_field_map`.
"""
from __future__ import annotations

from tools.migrar_mantis_gitlab.mapping.category_map import map_category
from tools.migrar_mantis_gitlab.mapping.custom_field_map import map_custom_fields
from tools.migrar_mantis_gitlab.mapping.tag_map import map_tags
from tools.migrar_mantis_gitlab.mapping.version_map import map_version


def test_map_category_label_simple():
    assert map_category("Backend") == "category::Backend"
    assert map_category("  Frontend  ", label_prefix="cat::") == "cat::Frontend"


def test_map_tags_uno_por_tag_y_descarta_vacios():
    assert map_tags(["urgente", "  ", "cliente-x"]) == ["tag::urgente", "tag::cliente-x"]
    assert map_tags([]) == []
    assert map_tags(None) == []


def test_map_version_target_a_milestone_y_resto_a_labels():
    field_mapping_version = {
        "target_version_as": "milestone",
        "fixed_in_version_as": "label:fixed_in::",
        "affects_version_as": "label:affects::",
    }
    result = map_version("2.5.0", "2.5.1", "2.4.0", field_mapping_version)
    assert result == {
        "milestone": "2.5.0",
        "labels": ["fixed_in::2.5.1", "affects::2.4.0"],
    }


def test_map_version_campos_vacios_no_agregan_nada():
    field_mapping_version = {
        "target_version_as": "milestone",
        "fixed_in_version_as": "label:fixed_in::",
        "affects_version_as": "label:affects::",
    }
    result = map_version(None, "", "   ", field_mapping_version)
    assert result == {"milestone": None, "labels": []}


def test_map_custom_fields_arma_tabla_markdown():
    custom_fields = [
        {"name": "Cliente", "value": "Empresa Demo"},
        {"name": "Ambiente", "value": "Produccion"},
    ]
    result = map_custom_fields(custom_fields)
    assert result.startswith("## Campos personalizados (Mantis)")
    assert "| Cliente | Empresa Demo |" in result
    assert "| Ambiente | Produccion |" in result


def test_map_custom_fields_vacio_devuelve_cadena_vacia():
    assert map_custom_fields([]) == ""
    assert map_custom_fields(None) == ""
