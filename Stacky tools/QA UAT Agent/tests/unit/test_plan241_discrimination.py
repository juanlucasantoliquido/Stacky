"""test_plan241_discrimination.py — Plan 241 F2.

LEY DE DISCRIMINACION: una asercion que no puede fallar no es una asercion.
Un criterio solo cuenta como `verified` si su asercion viene con un CONTROL
NEGATIVO contra el cual la MISMA asercion da `fail`.
"""
import pytest

from discrimination_prover import prove, requires_discrimination, negative_control_for
from functional_verdict import build_functional_verdict


def test_maxlength_367_discrimina():
    """EL TEST INSIGNIA: attribute_equals(maxlength=50) contra el pre-fix "20"."""
    criterion = {
        "id": "CA-01", "kind": "maxlength", "expected": "50",
        "text": "El campo Póliza admite hasta 50 caracteres (antes truncaba a 20)",
    }
    assertion = {"tipo": "attribute_equals", "target": "c_abfCodObligacion",
                 "atributo": "maxlength", "valor": "50"}
    res = prove(assertion, criterion)
    assert res["proven"] is True
    assert str(res["negative_control"]) == "20"
    assert res["code"] == ""


def test_maxlength_con_dato_de_20_no_discrimina():
    """El bug real del 240: tipear 20 chars contra un bug que truncaba a 20."""
    dato = "VM12-P-1816961389-60"          # exactamente 20 caracteres
    assert len(dato) == 20
    criterion = {
        "id": "CA-01", "kind": "maxlength", "expected": dato,
        "text": "El campo Póliza admite hasta 50 caracteres (antes truncaba a 20)",
        "negative_control": dato,
    }
    assertion = {"tipo": "equals", "target": "c_abfCodObligacion", "valor": dato}
    res = prove(assertion, criterion)
    assert res["proven"] is False
    assert res["code"] == "DISCRIMINATION_FAILED"


def test_catalog_366_discrimina():
    criterion = {
        "id": "CA-01", "kind": "catalog", "expected": None,
        "text": ('El combo Tipo Telefono debe incluir "Laboral" y "Particular". '
                 "Hoy solo ofrece No Identificado, Fijo, Movil y Trabajo."),
    }
    assertion = {"tipo": "contains_literal", "target": "select_tipo_telefono",
                 "valor": "Laboral"}
    res = prove(assertion, criterion)
    assert res["proven"] is True
    assert "Trabajo" in str(res["negative_control"])


def test_absence_387_discrimina():
    criterion = {
        "id": "CA-02", "kind": "absence", "expected": None,
        "text": 'La columna "Medio de Contacto" aparece duplicada',
    }
    assertion = {"tipo": "count_eq", "target": "grid_contactos", "valor": 1}
    res = prove(assertion, criterion)
    assert res["proven"] is True
    assert int(res["negative_control"]) == 2


def test_sin_control_negativo():
    criterion = {"id": "CA-03", "kind": "value", "expected": "OK",
                 "text": "El campo debe ser OK"}
    assertion = {"tipo": "equals", "target": "x", "valor": "OK"}
    res = prove(assertion, criterion)
    assert res["proven"] is False
    assert res["code"] == "NO_DISCRIMINATION"
    assert negative_control_for(criterion, assertion) is None


def test_kinds_que_no_requieren():
    assert requires_discrimination("presence") is False
    assert requires_discrimination("no_error") is False
    for k in ("maxlength", "value", "catalog", "absence", "ordering", "color"):
        assert requires_discrimination(k) is True, k


def test_verdict_degrada_sin_discriminacion():
    """Criterio `verified` sin discriminacion + strict ON => not_verifiable."""
    criteria = [{"id": "P01", "kind": "maxlength", "status": "verified"}]
    fv = build_functional_verdict(criteria, {"verdict": "PASS"}, strict=True)
    assert fv["verdict"] == "MIXED"
    assert fv["verified"] == 0
    assert fv["not_verifiable"] == 1
    assert criteria[0]["status"] == "verified"      # no muta la entrada del caller
    assert fv["criteria"][0]["downgrade_reason"] == "NO_DISCRIMINATION"


def test_flag_off_no_degrada():
    criteria = [{"id": "P01", "kind": "maxlength", "status": "verified"}]
    fv = build_functional_verdict(criteria, {"verdict": "PASS"}, strict=False)
    assert fv["verdict"] == "PASS"
    assert fv["verified"] == 1


def test_discrimination_failed_no_es_fail_del_desarrollo():
    """(C6) Un test que no discrimina es un BUG DEL ARNES, no del desarrollo:
    produce MIXED (nunca FAIL) y sale en `test_quality_issues`."""
    criteria = [{
        "id": "P01", "kind": "maxlength", "status": "verified",
        "discrimination": {"proven": False, "code": "DISCRIMINATION_FAILED",
                           "detail": "la asercion pasa igual contra el pre-fix"},
    }]
    fv = build_functional_verdict(criteria, {"verdict": "PASS"}, strict=True)
    assert fv["verdict"] == "MIXED"
    assert fv["verdict"] != "FAIL"
    issues = fv.get("test_quality_issues") or []
    assert len(issues) == 1
    assert issues[0]["code"] == "DISCRIMINATION_FAILED"
    assert issues[0]["criterio_id"] == "P01"
    assert issues[0]["fix_sugerido"]


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-q"])
