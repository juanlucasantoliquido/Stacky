"""test_plan241_assertion_catalog.py — Plan 241 F1.

Cada `kind` de criterio se traduce a una asercion CONCRETA y discriminante, no a
un oraculo de texto generico. Incluye `attribute_equals`, que no existia.
"""
import pytest

from assertion_catalog import build_assertions, SUPPORTED_KINDS
from uat_assertion_evaluator import _evaluate_deterministic


# ── ui_maps de los casos reales ──────────────────────────────────────────────

_UI_MAP_367 = {
    "c_abfCodObligacion": {"selector": "#c_abfCodObligacion", "label": "Póliza"},
    "btn_buscar": {"selector": "#btn_buscar", "label": "Buscar"},
}

_UI_MAP_366 = {
    "select_tipo_telefono": {"selector": "#c_ddlTipoTelefono",
                             "label": "Tipo Telefono"},
}

_UI_MAP_387 = {
    "grid_contactos": {"selector": "#gvContactos", "label": "Medio de Contacto"},
}


def test_maxlength_del_367():
    criterion = {
        "id": "CA-01", "kind": "maxlength", "expected": "50",
        "text": "El campo Póliza admite hasta 50 caracteres",
        "tokens": [],
    }
    oracles = build_assertions(criterion, _UI_MAP_367, "FrmBusqueda.aspx")
    assert len(oracles) == 1
    o = oracles[0]
    assert o["tipo"] == "attribute_equals"
    assert o["target"] == "c_abfCodObligacion"
    assert o["atributo"] == "maxlength"
    assert str(o["valor"]) == "50"


def test_catalog_del_366():
    criterion = {
        "id": "CA-01", "kind": "catalog", "expected": None,
        "text": 'El combo Tipo Telefono debe incluir las opciones "Laboral" y "Particular"',
        "tokens": ["Laboral", "Particular"],
    }
    oracles = build_assertions(criterion, _UI_MAP_366, "FrmDetalleClie.aspx")
    assert len(oracles) == 2
    assert all(o["tipo"] == "contains_literal" for o in oracles)
    assert all(o["target"] == "select_tipo_telefono" for o in oracles)
    assert [o["valor"] for o in oracles] == ["Laboral", "Particular"]


def test_absence_del_387():
    criterion = {
        "id": "CA-02", "kind": "absence", "expected": None,
        "text": 'La columna "Medio de Contacto" no debe aparecer duplicada',
        "tokens": ["Medio de Contacto"],
    }
    oracles = build_assertions(criterion, _UI_MAP_387, "FrmDetalleClie.aspx")
    assert len(oracles) == 1
    assert oracles[0]["tipo"] == "count_eq"
    assert oracles[0]["target"] == "grid_contactos"
    assert int(oracles[0]["valor"]) == 1


def test_target_no_resuelto_devuelve_vacio():
    """Un token que no matchea nada del ui_map NO inventa un alias."""
    criterion = {
        "id": "CA-09", "kind": "maxlength", "expected": "50",
        "text": 'El campo "Inexistente Total" admite hasta 50 caracteres',
        "tokens": ["Inexistente Total"],
    }
    assert build_assertions(criterion, _UI_MAP_367, "FrmBusqueda.aspx") == []


def test_alias_fuera_del_ui_map_devuelve_vacio():
    """(C2) target_alias explicito que NO es clave del ui_map => [].

    El template resuelve el selector con ui_map[oracle.target]: un alias
    inexistente emite `selector: undefined`, el probe captura actual=null y el
    evaluador devuelve "review" => el criterio se pierde EN SILENCIO.
    """
    criterion = {
        "id": "CA-10", "kind": "maxlength", "expected": "50",
        "target_alias": "alias_que_no_existe",
        "text": "El campo Póliza admite hasta 50 caracteres", "tokens": [],
    }
    oracles = build_assertions(criterion, {"otro_alias": "#otro"}, "FrmBusqueda.aspx")
    assert oracles == []


def test_evaluator_attribute_equals():
    assert _evaluate_deterministic("attribute_equals", "50", "50") == "pass"
    assert _evaluate_deterministic("attribute_equals", "50", "20") == "fail"
    assert _evaluate_deterministic("attribute_equals", "50", None) == "review"


def test_evaluator_ordered_by_asc_y_desc():
    assert _evaluate_deterministic("ordered_by", "asc", ["a", "b", "c"]) == "pass"
    assert _evaluate_deterministic("ordered_by", "asc", ["c", "b", "a"]) == "fail"
    assert _evaluate_deterministic("ordered_by", "desc", ["c", "b", "a"]) == "pass"
    assert _evaluate_deterministic("ordered_by", "desc", ["a", "b", "c"]) == "fail"
    assert _evaluate_deterministic("ordered_by", "asc", None) == "review"


def test_evaluator_no_console_error():
    assert _evaluate_deterministic("no_console_error", None, []) == "pass"
    assert _evaluate_deterministic("no_console_error", None, ["Uncaught TypeError"]) == "fail"


def test_template_emite_getattribute():
    """Anti-regresion: el .j2 debe capturar el atributo real del DOM."""
    from pathlib import Path
    tpl = (Path(__file__).resolve().parents[2]
           / "templates" / "playwright_test.spec.ts.j2").read_text(encoding="utf-8")
    assert "getAttribute(" in tpl
    assert "atributo" in tpl
    assert "maxlength" in SUPPORTED_KINDS


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-q"])
