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
