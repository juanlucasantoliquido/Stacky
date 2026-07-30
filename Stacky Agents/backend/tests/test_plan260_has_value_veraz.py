"""Plan 260 F1 — La verdad sobre has_value (tri-estado), y quien gana cuando
una key trae, a la vez, una entrada "*" (comodin) y una de scope exacto.

has_value: True -> el proveedor confirma que hay un valor cargado.
           False -> el proveedor confirma que el valor esta VACIO.
           None  -> el proveedor NO puede saberlo (ADO + isSecret) -> DESCONOCIDO.

KPI-5 (control negativo): el VALOR nunca sale del proveedor, solo su bool().
KPI-2: declarar un nombre sin valor sigue contando como pendiente VISIBLE.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest import mock

import pytest

from services.pipeline_environments import (
    PROVIDER_ADO,
    PROVIDER_GITLAB,
    Requirement,
    SOURCES,
    build_matrix,
)
from services.pipeline_env_resolver import _elegir_entrada, _resolver_celda

CORPUS_DIR = Path(__file__).resolve().parent / "plan260_corpus"


def _declare_matrix() -> list[dict]:
    return json.loads((CORPUS_DIR / "declare_matrix.json").read_text(encoding="utf-8"))["rows"]


def _scope_conflict_rows() -> list[dict]:
    data = json.loads((CORPUS_DIR / "scope_conflict_matrix.json").read_text(encoding="utf-8"))
    return data["rows"]


def _requirement(kind: str, is_secret: bool, provider: str) -> Requirement:
    return Requirement(
        name="ALGUN_VALOR", kind=kind, provider=provider, is_secret=is_secret,
        declared_default=None, per_environment=False, confidence="alta", evidence=(),
    )


def _has_value_ado(provider_devuelve: dict) -> object:
    from services.ado_variables import AdoVariablesProvider

    var_def = {"isSecret": provider_devuelve["is_secret"]}
    if "value" in provider_devuelve:
        var_def["value"] = provider_devuelve["value"]
    get_response = {"id": 1, "variables": {"K": var_def}}
    with mock.patch("services.ado_variables.find_yaml_definition", return_value={"id": 1}):
        with mock.patch("services.ado_variables.AdoClient._request",
                        return_value=(get_response, 200)):
            provider = AdoVariablesProvider(project="p")
            result = provider.list_variables()
    assert len(result) == 1
    assert "value" not in result[0], "KPI-5: el value NUNCA sale del proveedor"
    return result[0]["has_value"]


def _has_value_gitlab(provider_devuelve: dict, scoped: bool = False) -> object:
    from services.gitlab_variables import GitLabVariablesProvider

    item = {"key": "K", "masked": provider_devuelve.get("masked", False), "protected": False}
    if "value" in provider_devuelve:
        item["value"] = provider_devuelve["value"]
    if scoped:
        item["environment_scope"] = provider_devuelve.get("environment_scope", "*")
    os.environ.setdefault("GITLAB_TOKEN", "t0k3n-de-test")
    with mock.patch("services.gitlab_provider.GitLabClient") as mock_cls:
        mock_client = mock.MagicMock()
        mock_client._project_path.return_value = "g/p"
        mock_client._request_paginated.return_value = [item]
        mock_cls.return_value = mock_client
        provider = GitLabVariablesProvider(project="p")
        result = provider.list_variables_scoped() if scoped else provider.list_variables()
    assert len(result) == 1
    assert "value" not in result[0], "KPI-5: el value NUNCA sale del proveedor"
    return result[0]["has_value"]


def _has_value_from_provider(row: dict) -> object:
    if row["provider"] == "azure_devops":
        return _has_value_ado(row["provider_devuelve"])
    return _has_value_gitlab(row["provider_devuelve"])


# ── §4.6 ADICIÓN ARQUITECTO 4 — corpus proveedor x kind (4 filas) ────────────
@pytest.mark.parametrize("row", _declare_matrix(), ids=lambda r: f"{r['provider']}-{r['kind']}")
def test_f1_tabla_de_verdad_declare(row):
    has_value = _has_value_from_provider(row)
    assert has_value == row["has_value"], (
        f"{row['provider']}/{row['kind']}: has_value real={has_value!r}, "
        f"esperado={row['has_value']!r}"
    )

    req = _requirement(row["kind"], row["declared_secret"], row["provider"])
    por_key = {req.name: [("*", has_value)]}
    entrada = _resolver_celda(req, "prod", row["provider"], por_key, {}, [])
    assert entrada is not None
    state, source, _note = entrada
    assert state == row["state"]
    assert source == row["source"]


def test_f1_ado_secreto_declarado_no_queda_como_caja_fuerte():
    has_value = _has_value_ado({"is_secret": True, "value": None})
    assert has_value is None
    req = _requirement("secret", True, PROVIDER_ADO)
    por_key = {req.name: [("*", has_value)]}
    _state, source, _note = _resolver_celda(req, "prod", PROVIDER_ADO, por_key, {}, [])
    assert source == "declarada_sin_valor_verificable"
    assert source != "caja_fuerte"


def test_f1_ado_secreto_es_desconocido():
    assert _has_value_ado({"is_secret": True, "value": None}) is None


def test_f1_ado_valor_vacio_es_false():
    assert _has_value_ado({"is_secret": False, "value": ""}) is False


def test_f1_ado_sin_clave_value_es_none():
    assert _has_value_ado({"is_secret": False}) is None


def test_f1_gitlab_valor_vacio_es_false():
    assert _has_value_gitlab({"masked": False, "value": ""}) is False


def test_f1_gitlab_con_valor_es_true():
    assert _has_value_gitlab({"masked": False, "value": "algo"}) is True


def test_f1_gitlab_scoped_tambien_es_veraz():
    """El camino que usa la matriz (list_variables_scoped) tambien es veraz —
    cambiar solo list_variables() dejaria vivo el bug por este camino."""
    assert _has_value_gitlab({"masked": False, "value": ""}, scoped=True) is False
    assert _has_value_gitlab({"masked": False, "value": "algo"}, scoped=True) is True


def test_f1_ningun_value_sale_del_provider():
    """CONTROL NEGATIVO KPI-5: se inyecta un valor real y no aparece en repr()."""
    from services.ado_variables import AdoVariablesProvider
    from services.gitlab_variables import GitLabVariablesProvider

    secreto = "Xk7#pQ2mZr9Lw4Tv"

    with mock.patch("services.ado_variables.find_yaml_definition", return_value={"id": 1}):
        get_response = {"id": 1, "variables": {"K": {"isSecret": False, "value": secreto}}}
        with mock.patch("services.ado_variables.AdoClient._request",
                        return_value=(get_response, 200)):
            provider = AdoVariablesProvider(project="p")
            assert secreto not in repr(provider.list_variables())
            assert secreto not in repr(provider.list_variables_scoped())

    os.environ.setdefault("GITLAB_TOKEN", "t0k3n-de-test")
    with mock.patch("services.gitlab_provider.GitLabClient") as mock_cls:
        mock_client = mock.MagicMock()
        mock_client._project_path.return_value = "g/p"
        mock_client._request_paginated.return_value = [
            {"key": "K", "masked": False, "protected": False, "value": secreto},
        ]
        mock_cls.return_value = mock_client
        provider = GitLabVariablesProvider(project="p")
        assert secreto not in repr(provider.list_variables())
        assert secreto not in repr(provider.list_variables_scoped())


def test_f1_declarada_sin_valor_sigue_contando_como_falta():
    """KPI-2 — el test que da vuelta la medicion de §2.3."""
    req = _requirement("variable", False, PROVIDER_GITLAB)
    por_key = {req.name: [("*", False)]}
    entrada = _resolver_celda(req, "prod", PROVIDER_GITLAB, por_key, {}, [])
    assert entrada[:2] == ("falta", "declarada_sin_valor")
    resolutions = {(req.name, "prod"): entrada}
    matrix = build_matrix((req,), ("prod",), resolutions, PROVIDER_GITLAB)
    assert matrix.pending_count == 1


def test_f1_desconocido_cae_en_manual_no_en_definido():
    req = _requirement("secret", True, PROVIDER_ADO)
    por_key = {req.name: [("*", None)]}
    state, _source, _note = _resolver_celda(req, "prod", PROVIDER_ADO, por_key, {}, [])
    assert state == "manual"
    assert state != "definido"


def test_f1_sources_solo_crecio():
    old_prefix = ("predefinida", "yaml_variables", "yaml_parameter_default",
                  "caja_fuerte", "registro_servidores", "scope_proveedor", "ninguna")
    assert SOURCES[:7] == old_prefix
    assert len(SOURCES) == 9
    assert "declarada_sin_valor" in SOURCES
    assert "declarada_sin_valor_verificable" in SOURCES


def test_f1_mismo_key_distinto_has_value_por_entorno():
    """(v4, C3) GitLab scopea la MISMA key a dev (cargada) y prod (vacia), SIN
    ninguna entrada "*". Cada celda resuelve con el valor de SU PROPIO entorno."""
    req = _requirement("variable", False, PROVIDER_GITLAB)
    por_key = {req.name: [("dev", True), ("prod", False)]}
    dev_entry = _resolver_celda(req, "dev", PROVIDER_GITLAB, por_key, {}, [])
    prod_entry = _resolver_celda(req, "prod", PROVIDER_GITLAB, por_key, {}, [])
    assert dev_entry[0] == "definido"
    assert prod_entry[0] == "falta"
    assert prod_entry[1] == "declarada_sin_valor"


# ── §4.7 ADICIÓN ARQUITECTO 7 — corpus de precedencia scope exacto vs comodin (4 filas) ──
@pytest.mark.parametrize("row", _scope_conflict_rows(), ids=lambda r: r["caso"])
def test_f1_precedencia_scope_exacto_vs_comodin(row):
    """El test que se cae si _elegir_entrada vuelve a mirar '*' antes que el
    scope exacto — el bug concreto que hundio la v4 (reabre KPI-2 por precedencia)."""
    entries = [tuple(e) for e in row["entries"]]
    elegida = _elegir_entrada(entries, row["env"])
    assert elegida is not None
    scope, hv = elegida
    assert scope == row["gana_scope"]
    assert hv == row["has_value_esperado"]


def test_f1_scope_conflict_corpus_no_esta_vacio():
    """4 filas, ni una menos: solo_comodin, exacto_gana_al_comodin_cargado,
    comodin_es_fallback_de_otro_entorno y solo_exacto_sin_comodin son las 4
    formas de entrada que _elegir_entrada puede recibir."""
    rows = _scope_conflict_rows()
    assert {r["caso"] for r in rows} == {
        "solo_comodin", "exacto_gana_al_comodin_cargado",
        "comodin_es_fallback_de_otro_entorno", "solo_exacto_sin_comodin"}
