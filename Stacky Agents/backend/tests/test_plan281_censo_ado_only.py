"""Plan 281 F0 — ANDAMIO: el censo tiene que ver el defecto MIENTRAS está vivo.

Este archivo es TEMPORAL por diseño. Su caso `test_censo_reproduce_la_foto_vieja`
asserta los números del código SIN ARREGLAR (§4.5 Alcance B del plan) y se vuelve
falso en cuanto F7 erradica las violaciones. F9.1 lo borra y MIGRA los otros 5
casos a `test_plan281_ratchet_ado_only.py`.

Por eso NO se registra en `scripts/run_harness_tests.{sh,ps1}`.

Un censo escrito DESPUÉS del fix no prueba nada: reporta 0 porque ya no hay nada
que contar. Si algún conteo de acá da distinto, el detector está mal — se corrige
el DETECTOR, nunca el número esperado.
"""
from __future__ import annotations

from services.provider_coupling_audit import (
    ADO_ONLY_JUSTIFICADOS,
    scan_ado_only_sites,
)


def test_censo_reproduce_la_foto_vieja():
    """La foto vieja, medida 2026-08-01 sobre el código sin arreglar: 32 = 18/4/10."""
    s = scan_ado_only_sites()
    assert s["con_seam_count"] == 18, s["con_seam"]
    assert s["gateados_count"] == 4, s["gateados"]
    assert s["ado_only_count"] == 10, s["ado_only"]
    assert s["violaciones_count"] == 8, s["violaciones"]
    assert s["ciegos_count"] == 4, s["ciegos_a_gitlab"]


def test_app_py_es_gateado_pero_ciego_a_gitlab():
    """C1 — `_startup_sync` NO es ado_only (la heurística lo perdona por partida
    doble: nombra jira/mantis Y llama resolve_project_context). La señal que SÍ lo
    atrapa es `ciegos_a_gitlab`. Este caso fija por escrito esa clasificación y
    guarda el alcance ampliado de §4.6 (app.py dentro del censo)."""
    s = scan_ado_only_sites()
    assert "app.py::_startup_sync" in s["gateados"]
    assert "app.py::_startup_sync" in s["ciegos_a_gitlab"]
    assert "app.py::_startup_sync" not in s["ado_only"]


def test_censo_detecta_llamada_por_alias():
    """R2 — `completion_sync` llama `project_context.build_ado_client(...)` por
    ALIAS de módulo. Un censo que sólo mirara `ast.Name` daría CERO ahí."""
    s = scan_ado_only_sites()
    todos = set(s["con_seam"]) | set(s["gateados"]) | set(s["ado_only"])
    assert "services/completion_sync.py::_do_project_sync" in s["gateados"]
    assert "services/completion_sync.py::_do_project_sync" in todos


def test_censo_excluye_familia_ado():
    """Un adaptador ADO tiene derecho a ser ADO-only."""
    s = scan_ado_only_sites()
    todos = set(s["con_seam"]) | set(s["gateados"]) | set(s["ado_only"])
    assert not [k for k in todos if k.startswith("services/ado_")]


def test_censo_es_determinista():
    """Dos llamadas seguidas devuelven exactamente lo mismo (listas ordenadas)."""
    assert scan_ado_only_sites() == scan_ado_only_sites()


def test_justificados_son_subconjunto_de_ado_only():
    """Impide que una justificación quede huérfana y esconda un sitio que ya no existe."""
    s = scan_ado_only_sites()
    faltantes = [k for k in ADO_ONLY_JUSTIFICADOS if k not in s["ado_only"]]
    assert not faltantes, faltantes
