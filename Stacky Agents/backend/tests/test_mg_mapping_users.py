"""tests/test_mg_mapping_users.py — Plan 217 F3.

Valida `tools/migrar_mantis_gitlab/mapping/user_map.map_user`: los 3 casos
de `default_fallback` (`unassigned` | `assign_to:<user>` | `fail`), incluido
`"fail"` lanzando `UserMappingError`.
"""
from __future__ import annotations

import pytest

from tools.migrar_mantis_gitlab.mapping.user_map import UserMappingError, map_user


def test_usuario_mapeado_explicitamente_devuelve_username_gitlab():
    user_mapping = {
        "default_fallback": "unassigned",
        "map": {"jsantoliquido": "juanluca.santoliquido"},
    }
    assert map_user("jsantoliquido", user_mapping) == "juanluca.santoliquido"


def test_usuario_no_mapeado_default_fallback_unassigned():
    user_mapping = {"default_fallback": "unassigned", "map": {}}
    assert map_user("usuario_desconocido", user_mapping) == "unassigned"


def test_usuario_no_mapeado_default_fallback_assign_to():
    user_mapping = {"default_fallback": "assign_to:admin.gitlab", "map": {}}
    assert map_user("usuario_desconocido", user_mapping) == "assign_to:admin.gitlab"


def test_usuario_no_mapeado_default_fallback_fail_lanza_user_mapping_error():
    user_mapping = {"default_fallback": "fail", "map": {}}
    with pytest.raises(UserMappingError, match="usuario_desconocido"):
        map_user("usuario_desconocido", user_mapping)


def test_usuario_mapeado_explicitamente_no_lanza_aunque_fallback_sea_fail():
    user_mapping = {
        "default_fallback": "fail",
        "map": {"jsantoliquido": "juanluca.santoliquido"},
    }
    assert map_user("jsantoliquido", user_mapping) == "juanluca.santoliquido"
