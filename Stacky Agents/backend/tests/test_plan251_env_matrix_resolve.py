"""Plan 251 F3 — resolucion SOLO LECTURA. 12 tests. Proveedores mockeados, CERO red.

KPI-2: no se le pide al operador nada que Stacky ya sepa.
KPI-3: el VALOR nunca entra ni sale; ni siquiera en un mensaje de error.
"""
from __future__ import annotations

import json

import pytest

from services import ci_variables, pipeline_env_resolver as per, server_registry
from services import pipeline_environments as pe

ADO = pe.PROVIDER_ADO
GL = pe.PROVIDER_GITLAB


def _req(name, kind="variable", **kw):
    base = dict(provider=ADO, is_secret=False, declared_default=None,
                per_environment=True, confidence="alta", evidence=())
    base.update(kw)
    return pe.Requirement(name=name, kind=kind, **base)


class _ProviderFake:
    name = "fake"

    def __init__(self, items, scoped=True):
        self._items = items
        self.llamadas = 0
        if not scoped:
            del self.__class__.list_variables_scoped

    def list_variables(self):
        self.llamadas += 1
        return [{k: v for k, v in it.items() if k != "environment_scope"}
                for it in self._items]

    def list_variables_scoped(self):
        self.llamadas += 1
        return list(self._items)


class _ProviderSinScope:
    """Provider que NO implementa list_variables_scoped (degradacion honesta)."""

    name = "viejo"

    def __init__(self, items):
        self._items = items
        self.llamadas = 0

    def list_variables(self):
        self.llamadas += 1
        return list(self._items)


def _mockear(monkeypatch, provider):
    monkeypatch.setattr(ci_variables, "get_variables_provider",
                        lambda project=None: provider)
    return provider


# ── 1 ────────────────────────────────────────────────────────────────────────
def test_f3_no_pide_lo_que_ya_existe(monkeypatch):
    """KPI-2."""
    _mockear(monkeypatch, _ProviderFake([
        {"key": "DB_PASSWORD", "is_secret": True, "environment_scope": "*"}]))
    reqs = (_req("DB_PASSWORD", kind="secret", is_secret=True),
            _req("buildConfiguration"),
            _req("Build.BuildNumber"))
    resol, _deg = per.resolve(reqs, ("Test",), ADO, project="P",
                              yaml_text="variables:\n  buildConfiguration: 'Release'\n")
    m = pe.build_matrix(reqs, ("Test",), resol, ADO)
    assert m.pending_count == 0, [(c.requirement, c.state) for c in m.cells]


# ── 2 ────────────────────────────────────────────────────────────────────────
def test_f3_gitlab_scope_por_entorno(monkeypatch):
    # Plan 260: has_value=True explícito — antes del tri-estado, la mera PRESENCIA
    # de la key ya resolvía "definido"; ahora hace falta declarar que el proveedor
    # confirma un valor cargado (si no, sin la clave, resuelve "manual").
    _mockear(monkeypatch, _ProviderFake([
        {"key": "API_URL", "is_secret": False, "environment_scope": "Test",
         "has_value": True}]))
    reqs = (_req("API_URL", provider=GL),)
    resol, _d = per.resolve(reqs, ("Test", "Production"), GL, project="P")
    m = pe.build_matrix(reqs, ("Test", "Production"), resol, GL)
    estados = {c.environment: (c.state, c.source) for c in m.cells}
    assert estados["Test"] == ("definido", "scope_proveedor")
    assert estados["Production"][0] == "falta"


# ── 3 ────────────────────────────────────────────────────────────────────────
def test_f3_gitlab_scope_estrella_cubre_todo(monkeypatch):
    # Plan 260: has_value=True explícito (ver nota de test_f3_gitlab_scope_por_entorno).
    _mockear(monkeypatch, _ProviderFake([
        {"key": "API_URL", "is_secret": False, "environment_scope": "*",
         "has_value": True}]))
    reqs = (_req("API_URL", provider=GL),)
    resol, _d = per.resolve(reqs, ("Test", "Production"), GL, project="P")
    m = pe.build_matrix(reqs, ("Test", "Production"), resol, GL)
    assert {c.state for c in m.cells} == {"definido"}


# ── 4 ────────────────────────────────────────────────────────────────────────
def test_f3_ado_definido_en_todos_los_entornos_con_nota(monkeypatch):
    # Plan 260: has_value=True explícito (ver nota de test_f3_gitlab_scope_por_entorno).
    _mockear(monkeypatch, _ProviderFake([
        {"key": "API_URL", "is_secret": False, "environment_scope": "*",
         "has_value": True}]))
    reqs = (_req("API_URL"),)
    resol, _d = per.resolve(reqs, ("Test", "Production"), ADO, project="P")
    m = pe.build_matrix(reqs, ("Test", "Production"), resol, ADO)
    assert {c.state for c in m.cells} == {"definido"}
    for c in m.cells:
        assert "definition" in (c.note or "")


# ── 5 ────────────────────────────────────────────────────────────────────────
def test_f3_fallback_sin_list_variables_scoped(monkeypatch):
    prov = _mockear(monkeypatch, _ProviderSinScope([{"key": "API_URL", "is_secret": False}]))
    variables, scopes, degradaciones = per.list_scoped_variables("P")
    assert prov.llamadas == 1
    assert variables[0]["environment_scope"] == "*"
    assert scopes == ()
    assert degradaciones, "la degradacion se REPORTA, no se disimula"


# ── 6 ────────────────────────────────────────────────────────────────────────
def test_f3_servidor_resuelve_por_alias(monkeypatch):
    monkeypatch.setattr(server_registry, "list_servers", lambda: [
        {"alias": "test-server", "host": "10.0.0.5", "has_password": True}])
    reqs = (_req("TEST-Server", kind="server"),)
    resol, _d = per.resolve(reqs, ("Test",), ADO, use_provider=False)
    assert resol[("TEST-Server", "Test")] == (
        "definido", "registro_servidores", "credencial guardada")


# ── 7 ────────────────────────────────────────────────────────────────────────
def test_f3_servidor_resuelve_por_host(monkeypatch):
    monkeypatch.setattr(server_registry, "list_servers", lambda: [
        {"alias": "test-server", "host": "10.0.0.5", "has_password": False}])
    reqs = (_req("10.0.0.5", kind="server"),)
    resol, _d = per.resolve(reqs, ("Test",), ADO, use_provider=False)
    assert resol[("10.0.0.5", "Test")][0] == "definido"
    assert resol[("10.0.0.5", "Test")][2] == "sin credencial guardada"


# ── 8 ────────────────────────────────────────────────────────────────────────
def test_f3_servidor_desconocido_falta(monkeypatch):
    monkeypatch.setattr(server_registry, "list_servers", lambda: [
        {"alias": "test-server", "host": "10.0.0.5", "has_password": True}])
    reqs = (_req("PROD-Server", kind="server"),)
    resol, _d = per.resolve(reqs, ("Test",), ADO, use_provider=False)
    m = pe.build_matrix(reqs, ("Test",), resol, ADO)
    assert m.cells[0].state == "falta"


# ── 9 ────────────────────────────────────────────────────────────────────────
def test_f3_ado_sin_definition_degrada_409(monkeypatch):
    def _explota(project=None):
        raise ci_variables.VariablesUnavailableError("ADO sin pipeline definition")

    monkeypatch.setattr(ci_variables, "get_variables_provider", _explota)
    variables, scopes, degradaciones = per.list_scoped_variables("P")
    assert variables == [] and scopes == ()
    assert any("plan 95" in d for d in degradaciones)


# ── 10 ───────────────────────────────────────────────────────────────────────
def test_f3_error_inesperado_mensaje_fijo(monkeypatch):
    """El `str(e)` de una excepcion desconocida puede traer el cuerpo de la respuesta
    del proveedor, y ahi puede venir un valor."""
    def _explota(project=None):
        raise RuntimeError("boom S3cr3t!XYZ")

    monkeypatch.setattr(ci_variables, "get_variables_provider", _explota)
    salida = per.list_scoped_variables("P")
    assert salida[2] == [per._MSG_ERROR_INTERNO]
    assert "S3cr3t!XYZ" not in repr(salida)


# ── 11 ───────────────────────────────────────────────────────────────────────
def test_f3_use_provider_false_no_toca_red(monkeypatch):
    prov = _mockear(monkeypatch, _ProviderFake([{"key": "X", "environment_scope": "*"}]))
    per.resolve((_req("X"),), ("Test",), ADO, project="P", use_provider=False)
    assert prov.llamadas == 0


# ── 12 ───────────────────────────────────────────────────────────────────────
def test_f3_ningun_value_en_el_retorno(monkeypatch):
    """C3 — centinela. Con el dict de claves TUPLA de la v1 este test ni corria."""
    _mockear(monkeypatch, _ProviderFake([
        {"key": "DB_PASSWORD", "is_secret": True, "value": "S3cr3t!",
         "environment_scope": "*"}]))
    reqs = (_req("DB_PASSWORD", kind="secret", is_secret=True),)
    resol, deg = per.resolve(reqs, ("Test",), ADO, project="P")
    m = pe.build_matrix(reqs, ("Test",), resol, ADO, degraded=deg)
    crudo = json.dumps(pe.to_json_payload(m, ADO))
    assert "S3cr3t!" not in crudo
    assert '"value"' not in crudo


def test_f3_resolver_sin_logger_ni_print():
    import re as _re
    from pathlib import Path

    fuente = (Path(__file__).resolve().parent.parent / "services"
              / "pipeline_env_resolver.py").read_text(encoding="utf-8")
    assert _re.search(r"\blogger\.", fuente) is None
    assert _re.search(r"\bprint\(", fuente) is None


@pytest.mark.parametrize("provider", [ADO, GL])
def test_f3_parameter_con_default_no_es_trabajo(provider):
    reqs = (_req("targetEnvironment", kind="parameter", declared_default="Test"),)
    resol, _d = per.resolve(reqs, ("Test",), provider, use_provider=False)
    m = pe.build_matrix(reqs, ("Test",), resol, provider)
    assert m.cells[0].state == "default"
    assert m.pending_count == 0
