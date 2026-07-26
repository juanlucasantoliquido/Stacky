"""test_plan241_test_data_forge.py — Plan 241 F3.

El valor de prueba lo deriva el ARNES del propio criterio, garantizando que cruza
el umbral. El ADO-367 fallo exactamente en esto: uso el valor truncado del ticket
(20 chars) en vez de uno que probara el fix (>20).
"""
import pytest

from test_data_forge import forge

_CRIT_367 = {
    "id": "CA-01", "kind": "maxlength", "expected": "50",
    "text": ("El campo Póliza admite hasta 50 caracteres. "
             "Comportamiento previo: truncaba a 20."),
    "tokens": ["VM12-P-1816961389-60"],
}


def test_maxlength_forja_50_chars():
    res = forge(_CRIT_367)
    assert len(res["positivo"]) == 50


def test_maxlength_negativo_supera_el_umbral_previo():
    """El bug truncaba a 20 => el negativo mide 21: lo habria rechazado."""
    res = forge(_CRIT_367)
    assert len(res["negativo"]) == 21


def test_determinista():
    """Mismo criterio => MISMO valor. Cero random (los 3 runtimes iguales)."""
    a = forge(_CRIT_367)
    b = forge(dict(_CRIT_367))
    assert a["positivo"] == b["positivo"]
    assert a["negativo"] == b["negativo"]


def test_sin_expected_devuelve_none():
    crit = {"id": "CA-77", "kind": "maxlength", "expected": None,
            "text": "El campo debe comportarse bien", "tokens": []}
    res = forge(crit)
    assert res["positivo"] is None
    assert res["rationale"]
    assert "expected" in res["rationale"].lower() or "umbral" in res["rationale"].lower()


def test_rationale_no_vacio():
    for crit in (
        _CRIT_367,
        {"id": "A", "kind": "value", "expected": "OK", "text": "debe ser OK"},
        {"id": "B", "kind": "catalog", "expected": None,
         "text": 'incluye "Laboral"', "tokens": ["Laboral", "Particular"]},
        {"id": "C", "kind": "presence", "expected": None,
         "text": 'debe mostrar "Medio de Contacto"', "tokens": ["Medio de Contacto"]},
    ):
        res = forge(crit)
        assert isinstance(res["rationale"], str) and res["rationale"].strip(), crit["id"]


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-q"])
