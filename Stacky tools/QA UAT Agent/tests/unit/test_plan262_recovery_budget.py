"""Plan 262 F5 — recovery_budget: el presupuesto anti-bucle. Techo, nunca piso.

16 casos. Los gates son test_presupuesto_no_se_reinicia_entre_casos y
test_segundo_service_down_no_arranca_de_nuevo: una implementacion con contador por
caso pero SIN contador de run pasa 14 de 16 y permite el bucle infinito.
"""
from __future__ import annotations

import json

import pytest

import recovery_budget as rb
from recovery_classifier import (
    FUNCTIONAL_ERROR,
    ROUTE_ERROR,
    SERVICE_DOWN,
)


@pytest.fixture(autouse=True)
def _entorno_limpio(monkeypatch):
    for k in ("STACKY_QA_UAT_HOT_RECOVERY_ENABLED",
              "STACKY_QA_UAT_RECOVERY_MAX_PER_RUN",
              "STACKY_QA_UAT_RECOVERY_MAX_PER_CASE"):
        monkeypatch.delenv(k, raising=False)


def test_build_lee_la_config(monkeypatch):
    monkeypatch.setenv("STACKY_QA_UAT_RECOVERY_MAX_PER_RUN", "9")
    monkeypatch.setenv("STACKY_QA_UAT_RECOVERY_MAX_PER_CASE", "2")
    b = rb.build_budget()
    assert b.max_per_run == 9
    assert b.max_per_case == 2


def test_per_case_se_clampea_al_per_run(monkeypatch):
    """Un caso no puede reintentar mas veces que el run entero."""
    monkeypatch.setenv("STACKY_QA_UAT_RECOVERY_MAX_PER_RUN", "2")
    monkeypatch.setenv("STACKY_QA_UAT_RECOVERY_MAX_PER_CASE", "9")
    assert rb.build_budget().max_per_case == 2


def test_service_starts_es_uno_con_flag_on():
    """INV-7: el techo NO puede exceder lo que el plan 240 ya autoriza."""
    assert rb.build_budget().max_service_starts == 1


def test_service_starts_es_cero_con_flag_off(monkeypatch):
    monkeypatch.setenv("STACKY_QA_UAT_HOT_RECOVERY_ENABLED", "false")
    assert rb.build_budget().max_service_starts == 0


def test_flag_off_nunca_recupera(monkeypatch):
    monkeypatch.setenv("STACKY_QA_UAT_HOT_RECOVERY_ENABLED", "false")
    b = rb.RecoveryBudget(6, 1, 0)
    ok, why = b.can_recover("caso1", ROUTE_ERROR)
    assert ok is False
    assert why == "hot_recovery_off"


def test_functional_error_nunca_consume():
    """INV-2: reintentar una asercion que fallo es la definicion de falso verde."""
    b = rb.RecoveryBudget(6, 1, 1)
    ok, why = b.can_recover("caso1", FUNCTIONAL_ERROR)
    assert ok is False
    assert why == "clase_no_recuperable"
    b.consume("caso1", FUNCTIONAL_ERROR)
    assert b.attempts_for("caso1") == 0
    assert b._used_run == 0


def test_agota_per_run():
    b = rb.RecoveryBudget(6, 6, 1)
    for i in range(6):
        assert b.can_recover(f"caso{i}", ROUTE_ERROR)[0] is True
        b.consume(f"caso{i}", ROUTE_ERROR)
    ok, why = b.can_recover("caso7", ROUTE_ERROR)
    assert ok is False
    assert why == "presupuesto_de_run_agotado"


def test_agota_per_case():
    b = rb.RecoveryBudget(10, 1, 1)
    b.consume("caso1", ROUTE_ERROR)
    ok, why = b.can_recover("caso1", ROUTE_ERROR)
    assert ok is False
    assert why == "presupuesto_del_caso_agotado"


def test_dos_casos_no_comparten_el_contador_por_caso():
    b = rb.RecoveryBudget(10, 1, 1)
    b.consume("caso1", ROUTE_ERROR)
    assert b.can_recover("caso2", ROUTE_ERROR)[0] is True


def test_dos_casos_si_comparten_el_de_run():
    b = rb.RecoveryBudget(1, 1, 1)
    b.consume("caso1", ROUTE_ERROR)
    ok, why = b.can_recover("caso2", ROUTE_ERROR)
    assert ok is False
    assert why == "presupuesto_de_run_agotado"


def test_segundo_service_down_no_arranca_de_nuevo():
    """GATE ANTI-BUCLE: SERVICE_DOWN -> arrancar -> probe -> SERVICE_DOWN -> ..."""
    b = rb.RecoveryBudget(10, 10, 1)
    assert b.can_recover("caso1", SERVICE_DOWN)[0] is True
    b.consume("caso1", SERVICE_DOWN)
    ok, why = b.can_recover("caso2", SERVICE_DOWN)
    assert ok is False
    assert why == "arranques_de_servicio_agotados"


def test_max_cero_es_modo_observacion():
    """Se clasifica y se registra, pero no se recupera nada. Puesta en marcha honesta."""
    b = rb.RecoveryBudget(0, 0, 0)
    assert b.can_recover("caso1", ROUTE_ERROR)[0] is False
    b.consume("caso1", ROUTE_ERROR)
    assert len(b._ledger) == 1, "en modo observacion el ledger igual tiene que crecer"


def test_case_id_vacio_no_crea_clave_none():
    b = rb.RecoveryBudget(6, 6, 1)
    b.consume(None, ROUTE_ERROR)
    b.consume("", ROUTE_ERROR)
    assert None not in b._used_by_case
    assert "" not in b._used_by_case
    assert b.attempts_for(None) == 2


def test_presupuesto_no_se_reinicia_entre_casos():
    """GATE ANTI-BUCLE: un contador que se resetea no es un presupuesto."""
    b = rb.RecoveryBudget(3, 3, 1)
    b.consume("caso1", ROUTE_ERROR)
    b.consume("caso2", ROUTE_ERROR)
    b.consume("caso3", ROUTE_ERROR)
    assert b._used_run == 3
    ok, why = b.can_recover("caso4", ROUTE_ERROR)
    assert ok is False, "el presupuesto de run se reinicio al cambiar de caso"
    assert why == "presupuesto_de_run_agotado"


def test_ledger_registra_las_no_recuperables():
    """El reporte necesita saber que paso, aunque no se haya gastado nada."""
    b = rb.RecoveryBudget(6, 6, 1)
    b.consume("caso1", FUNCTIONAL_ERROR, detail="app viva, ruta legal")
    assert len(b._ledger) == 1
    assert b._ledger[0]["recovery_class"] == FUNCTIONAL_ERROR
    assert b._ledger[0]["consumed"] is False


def test_as_dict_es_json_serializable():
    b = rb.RecoveryBudget(6, 1, 1)
    b.consume("caso1", ROUTE_ERROR)
    json.dumps(b.as_dict())        # no debe levantar
