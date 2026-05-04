"""Unit tests for uat_scenario_compiler.py (B4)."""
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
os.environ.setdefault("STACKY_LLM_BACKEND", "mock")

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _ticket_70_json() -> dict:
    # Build a valid uat_ticket_reader output from fixtures
    ticket = json.loads((FIXTURES / "ticket_70.json").read_text(encoding="utf-8"))
    return {
        "ok": True,
        "ticket": {"id": 70, "title": "RF-003 Validación del comportamiento de combinación de filtros"},
        "comments": [],
        "plan_pruebas": [
            {"id": "P01", "descripcion": "Búsqueda SIN filtros activos muestra todos los lotes",
             "datos": "usuario=PABLO, empresa=0001", "esperado": "Grid con >= 1 resultado"},
            {"id": "P02", "descripcion": "Búsqueda con filtro Empresa filtra correctamente",
             "datos": "empresa=0001", "esperado": "Solo lotes de empresa 0001"},
            {"id": "P03", "descripcion": "Búsqueda con filtro Fecha filtra por rango",
             "datos": "fecha_desde=01/01/2026, fecha_hasta=31/01/2026", "esperado": "Grid con lotes del rango"},
            {"id": "P04", "descripcion": "Búsqueda SIN resultados muestra mensaje vacío",
             "datos": "empresa=9999", "esperado": "Mensaje 'No hay lotes agendados' visible"},
            {"id": "P05", "descripcion": "Combinación de 2 filtros activos funciona correctamente",
             "datos": "empresa=0001, tipo_lote=CRED", "esperado": "Grid filtrado por ambos criterios"},
            {"id": "P06", "descripcion": "Combinación de 3 filtros activos funciona correctamente",
             "datos": "empresa=0001, tipo_lote=CRED, fecha_desde=01/2026", "esperado": "Grid filtrado"},
            {"id": "P07", "descripcion": "Performance con más de 3 filtros activos simultáneos",
             "datos": "5 filtros activos", "esperado": "Respuesta en menos de 3 segundos"},
        ],
        "precondiciones_detected": [],
        "meta": {"tool": "uat_ticket_reader", "version": "1.0.0"},
    }


def test_ticket_70_compiles_6_scenarios_and_1_out_of_scope():
    import uat_scenario_compiler
    result = uat_scenario_compiler.run(ticket_json=_ticket_70_json())
    assert result["ok"] is True
    assert result["compiled"] == 6, f"Expected 6 scenarios, got {result['compiled']}"
    assert result["out_of_scope"] == 1, f"Expected 1 out of scope, got {result['out_of_scope']}"


def test_each_scenario_has_required_fields():
    import uat_scenario_compiler
    result = uat_scenario_compiler.run(ticket_json=_ticket_70_json())
    for s in result["scenarios"]:
        for field in ("scenario_id", "pantalla", "titulo", "pasos", "oraculos"):
            assert field in s, f"Missing field {field!r} in scenario {s.get('scenario_id')}"
        assert len(s["pasos"]) >= 1
        assert len(s["oraculos"]) >= 1


def test_placeholder_scenario_rejected():
    import uat_scenario_compiler
    ticket = _ticket_70_json()
    ticket["plan_pruebas"].append({
        "id": "P08", "descripcion": "[completar] test", "datos": "", "esperado": "TBD"
    })
    result = uat_scenario_compiler.run(ticket_json=ticket)
    oos_ids = [o["id"] for o in result["out_of_scope_items"]]
    assert "P08" in oos_ids, "P08 with placeholder must be in out_of_scope"


def test_empty_plan_returns_error():
    import uat_scenario_compiler
    ticket = _ticket_70_json()
    ticket["plan_pruebas"] = []
    result = uat_scenario_compiler.run(ticket_json=ticket)
    assert result["ok"] is False
    assert result["error"] == "no_test_plan_in_ticket"


def test_unsupported_screen_marked_blocked():
    """Scenarios targeting unknown screen end up in out_of_scope."""
    import uat_scenario_compiler
    ticket = _ticket_70_json()
    # Force LLM to return unknown screen by patching it
    with patch("llm_client.call_llm") as mock_llm:
        mock_llm.return_value = {
            "text": json.dumps({
                "pantalla": "FrmUnknown.aspx",
                "precondiciones": [],
                "pasos": [{"accion": "click", "target": "btn_x", "valor": None}],
                "oraculos": [{"tipo": "visible", "target": "msg_x", "valor": None}],
                "datos_requeridos": [],
            }),
            "model": "mock",
            "duration_ms": 0,
        }
        result = uat_scenario_compiler.run(ticket_json=ticket)
    # At least the performance scenario must be out_of_scope
    assert result["out_of_scope"] >= 1


def test_llm_fallback_on_regex():
    """If LLM raises, heuristic fallback produces a scenario."""
    import uat_scenario_compiler
    with patch("llm_client.call_llm", side_effect=Exception("LLM unavailable")):
        result = uat_scenario_compiler.run(ticket_json=_ticket_70_json())
    assert result["ok"] is True
    assert result["compiled"] >= 1


def test_output_validates_against_schema():
    import uat_scenario_compiler
    import jsonschema
    schema_path = Path(__file__).parent.parent.parent / "schemas" / "scenario_spec.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    result = uat_scenario_compiler.run(ticket_json=_ticket_70_json())
    jsonschema.validate(instance=result, schema=schema)


# ── M2 — compiler guardrails: decorative target validation ───────────────────


def _ui_elements_with_decorative_label() -> list:
    """UI map slice that exposes one decorative element + one functional one,
    enough to exercise the M2 validator."""
    return [
        {
            "alias_semantic": "panel_c_lblagendausu",
            "kind": "div",
            "role": "div",
            "label": None,
            "input_type": None,
            "class_list": ["col", "s10", "input-field-label"],
            "is_decorative": True,  # the bug from ticket 70 P01
        },
        {
            "alias_semantic": "msg_lista_vacia",
            "kind": "div",
            "role": "alert",
            "label": "No hay lotes agendados",
            "input_type": None,
            "class_list": ["form-message", "alert"],
            "is_decorative": False,
        },
        {
            "alias_semantic": "select_empresa",
            "kind": "select",
            "role": "combobox",
            "label": "Empresa",
            "input_type": None,
            "class_list": [],
            "is_decorative": False,
        },
        {
            "alias_semantic": "btn_buscar",
            "kind": "button",
            "role": "button",
            "label": "Buscar",
            "input_type": None,
            "class_list": [],
            "is_decorative": False,
        },
    ]


def test_oracle_against_decorative_target_routed_to_out_of_scope():
    """The exact bug from ticket 70 P01: LLM picks a decorative label as
    target of an `invisible` oracle. The compiler MUST reject it instead of
    letting it reach the runner.
    """
    import uat_scenario_compiler
    ticket = _ticket_70_json()
    # Slim down to just one item so the assertion is unambiguous.
    ticket["plan_pruebas"] = [{
        "id": "P01_REPRO",
        "descripcion": "No debe aparecer mensaje de lista vacía al abrir la pantalla",
        "datos": "",
        "esperado": "Mensaje de lista vacía no visible",
    }]
    with patch("llm_client.call_llm") as mock_llm:
        mock_llm.return_value = {
            "text": json.dumps({
                "pantalla": "FrmAgenda.aspx",
                "precondiciones": ["Login como PABLO"],
                "pasos": [{"accion": "navigate", "target": "FrmAgenda.aspx", "valor": None}],
                # The exact bug: oracle on the decorative label.
                "oraculos": [{"tipo": "invisible", "target": "panel_c_lblagendausu", "valor": None}],
                "datos_requeridos": [],
            }),
            "model": "mock",
            "duration_ms": 0,
        }
        result = uat_scenario_compiler.run(
            ticket_json=ticket,
            ui_elements=_ui_elements_with_decorative_label(),
        )
    assert result["ok"] is True
    oos_ids = [o["id"] for o in result["out_of_scope_items"]]
    assert "P01_REPRO" in oos_ids, (
        "Scenario with oracle on decorative element must be routed to "
        "out_of_scope, got: " + json.dumps(result["out_of_scope_items"])
    )
    decorative_entry = next(o for o in result["out_of_scope_items"] if o["id"] == "P01_REPRO")
    assert decorative_entry["razon"] == "ORACLE_TARGETS_DECORATIVE_LAYOUT"


def test_oracle_against_functional_target_compiled_normally():
    """Sanity: non-decorative target with the same oracle type is accepted."""
    import uat_scenario_compiler
    ticket = _ticket_70_json()
    ticket["plan_pruebas"] = [{
        "id": "P_OK",
        "descripcion": "Mostrar mensaje de lista vacía",
        "datos": "",
        "esperado": "Mensaje visible",
    }]
    with patch("llm_client.call_llm") as mock_llm:
        mock_llm.return_value = {
            "text": json.dumps({
                "pantalla": "FrmAgenda.aspx",
                "precondiciones": ["Login como PABLO"],
                "pasos": [{"accion": "navigate", "target": "FrmAgenda.aspx", "valor": None}],
                "oraculos": [{"tipo": "visible", "target": "msg_lista_vacia", "valor": None}],
                "datos_requeridos": [],
            }),
            "model": "mock",
            "duration_ms": 0,
        }
        result = uat_scenario_compiler.run(
            ticket_json=ticket,
            ui_elements=_ui_elements_with_decorative_label(),
        )
    assert result["ok"] is True
    compiled_ids = [s["scenario_id"] for s in result["scenarios"]]
    assert "P_OK" in compiled_ids


def test_decorative_validation_disabled_when_no_ui_elements():
    """Backwards compat: without ui_elements the validator MUST NOT fire.

    Pre-1.1 callers (and tests using only ui_aliases) keep working.
    """
    import uat_scenario_compiler
    ticket = _ticket_70_json()
    ticket["plan_pruebas"] = [{
        "id": "P_LEGACY",
        "descripcion": "Cualquier escenario",
        "datos": "",
        "esperado": "OK",
    }]
    with patch("llm_client.call_llm") as mock_llm:
        mock_llm.return_value = {
            "text": json.dumps({
                "pantalla": "FrmAgenda.aspx",
                "precondiciones": [],
                "pasos": [{"accion": "click", "target": "btn_buscar", "valor": None}],
                "oraculos": [{"tipo": "invisible", "target": "panel_c_lblagendausu", "valor": None}],
                "datos_requeridos": [],
            }),
            "model": "mock",
            "duration_ms": 0,
        }
        # No ui_elements passed.
        result = uat_scenario_compiler.run(ticket_json=ticket)
    assert result["ok"] is True
    # Pre-1.1 behaviour: scenario goes through (no validation).
    assert result["compiled"] == 1


def test_build_ui_elements_hint_marks_decorative():
    """The hint string handed to the LLM must explicitly enumerate decorative
    aliases so the model can avoid them."""
    import uat_scenario_compiler
    hint = uat_scenario_compiler._build_ui_elements_hint(
        _ui_elements_with_decorative_label()
    )
    assert "panel_c_lblagendausu" in hint
    assert "is_decorative=true" in hint
    assert "DECORATIVE LAYOUT ELEMENTS" in hint
    # Functional element MUST NOT appear in the decorative blacklist line.
    decorative_line = [l for l in hint.splitlines() if l.startswith("DECORATIVE")][0]
    assert "msg_lista_vacia" not in decorative_line
    assert "btn_buscar" not in decorative_line
