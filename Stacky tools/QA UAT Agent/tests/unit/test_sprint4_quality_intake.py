"""
tests/unit/test_sprint4_quality_intake.py — Sprint 4 tests.

Validates:
 1.  test_quality_intake_splits_unit_and_uat_items
 2.  test_quality_intake_ticket_122_marks_browser_items_uat
 3.  test_quality_intake_no_uat_items_returns_skipped_not_error
 4.  test_quality_intake_manual_review_flagged_for_ambiguous
 5.  test_quality_intake_event_logged_to_execution_jsonl
 6.  test_quality_intake_artifact_written_to_evidence
 7.  test_test_portfolio_written_to_evidence
 8.  test_test_portfolio_has_all_layers_represented
 9.  test_compiler_receives_only_uat_and_smoke_items
10.  test_compiler_skips_when_no_uat_items
11.  test_data_preconditions_auto_added_for_uat_with_data_seed
12.  test_non_uat_items_preserved_in_portfolio_with_handoff
13.  test_intake_layer_router_unit_for_pure_rule
14.  test_intake_layer_router_uat_for_visual_interaction
15.  test_intake_layer_router_manual_review_for_ambiguous
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure tool root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
os.environ.setdefault("STACKY_LLM_BACKEND", "mock")
os.environ.setdefault("QA_UAT_REQUIRE_PLAYBOOK", "false")

TOOL_DIR = Path(__file__).parent.parent.parent


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _make_ticket(acceptance_criteria=None, plan_pruebas=None, description_md=None):
    """Build a minimal ticket_result dict for testing."""
    t = {
        "ok": True,
        "ticket_id": 122,
        "title": "RF-008 — Filtros de provincia/departamento",
        "description_md": description_md or "",
        "analisis_tecnico": "Se requiere filtrar en FrmDetalleClie.aspx al seleccionar provincia.",
        "plan_pruebas": plan_pruebas or [],
    }
    if acceptance_criteria is not None:
        t["acceptance_criteria"] = acceptance_criteria
    return t


_CA_UAT = "Validar que al seleccionar provincia se filtren departamentos en la pantalla"
_CA_UAT2 = "Navegar a la grilla de obligaciones y verificar que se carguen los datos"
_CA_UNIT = "Validar que al calcular el monto con impuesto el resultado sea correcto"
_CA_INTEGRATION = "Verificar que el servicio de base de datos registre correctamente el pago"
_CA_API = "Validar el endpoint de creación de cliente retorna response 201 con el DTO esperado"
_CA_AMBIGUOUS = "Revisar comportamiento del sistema en este escenario"


# ═══════════════════════════════════════════════════════════════════════════════
# 1. test_quality_intake_splits_unit_and_uat_items
# ═══════════════════════════════════════════════════════════════════════════════

def test_quality_intake_splits_unit_and_uat_items():
    """run_quality_intake classifies CAs into distinct layers correctly."""
    from quality_intake import run_quality_intake

    cas = [_CA_UAT, _CA_UNIT, _CA_INTEGRATION, _CA_API]

    with tempfile.TemporaryDirectory() as tmpdir:
        result = run_quality_intake(
            ticket_id=122,
            title="RF-008 test",
            description_md="",
            acceptance_criteria=cas,
            evidence_dir=Path(tmpdir),
            run_id="122",
        )

    assert result.items_total == 4
    layers = result.layer_counts()
    assert layers.get("uat", 0) >= 1, f"Expected >=1 UAT item, got {layers}"
    assert layers.get("unit", 0) >= 1, f"Expected >=1 unit item, got {layers}"
    assert layers.get("integration", 0) >= 1 or layers.get("api_contract", 0) >= 1, \
        f"Expected integration or api_contract, got {layers}"


# ═══════════════════════════════════════════════════════════════════════════════
# 2. test_quality_intake_ticket_122_marks_browser_items_uat
# ═══════════════════════════════════════════════════════════════════════════════

def test_quality_intake_ticket_122_marks_browser_items_uat():
    """UAT-classified items have needs_browser=True; unit/integration items do not."""
    from quality_intake import run_quality_intake

    cas = [_CA_UAT, _CA_UAT2, _CA_UNIT]

    with tempfile.TemporaryDirectory() as tmpdir:
        result = run_quality_intake(
            ticket_id=122,
            title="RF-008",
            description_md="",
            acceptance_criteria=cas,
            evidence_dir=Path(tmpdir),
            run_id="122",
        )

    browser_items = [i for i in result.items if i.needs_browser]
    non_browser_items = [i for i in result.items if not i.needs_browser]

    assert len(browser_items) >= 1, "Expected at least 1 item with needs_browser=True"
    assert any(i.layer_recommended == "unit" for i in non_browser_items), \
        "Expected at least 1 unit item with needs_browser=False"

    for item in browser_items:
        assert item.layer_recommended in ("uat", "smoke_e2e"), \
            f"Browser item has unexpected layer: {item.layer_recommended}"


# ═══════════════════════════════════════════════════════════════════════════════
# 3. test_quality_intake_no_uat_items_returns_skipped_not_error
# ═══════════════════════════════════════════════════════════════════════════════

def test_quality_intake_no_uat_items_returns_skipped_not_error():
    """
    When all CAs classify to non-browser layers, build_no_uat_skipped_result
    returns ok=True + verdict=SKIPPED + category=PIP, not an error.
    """
    from quality_intake import run_quality_intake, build_no_uat_skipped_result

    cas = [_CA_UNIT, _CA_INTEGRATION, _CA_API]

    with tempfile.TemporaryDirectory() as tmpdir:
        result = run_quality_intake(
            ticket_id=122,
            title="RF-008",
            description_md="",
            acceptance_criteria=cas,
            evidence_dir=Path(tmpdir),
            run_id="122",
        )
        assert result.uat_required is False, \
            f"Expected uat_required=False but got {result.uat_required}"
        assert not result.uat_items, "Expected no UAT items"

        skipped = build_no_uat_skipped_result(
            ticket_id=122,
            portfolio_path=result.artifact_path,
        )

    assert skipped["ok"] is True, "SKIPPED must be ok=True (not an error)"
    assert skipped["verdict"] == "SKIPPED"
    assert skipped["category"] == "PIP"
    assert skipped["reason"] == "NO_UAT_ITEMS"
    assert "human_action_required" in skipped


# ═══════════════════════════════════════════════════════════════════════════════
# 4. test_quality_intake_manual_review_flagged_for_ambiguous
# ═══════════════════════════════════════════════════════════════════════════════

def test_quality_intake_manual_review_flagged_for_ambiguous():
    """Ambiguous CAs with no clear signal are classified as manual_review."""
    from quality_intake import run_quality_intake

    cas = [_CA_AMBIGUOUS, "Evaluar el comportamiento general del módulo"]

    with tempfile.TemporaryDirectory() as tmpdir:
        result = run_quality_intake(
            ticket_id=122,
            title="RF-008",
            description_md="",
            acceptance_criteria=cas,
            evidence_dir=Path(tmpdir),
            run_id="122",
        )

    manual_items = [i for i in result.items if i.layer_recommended == "manual_review"]
    assert len(manual_items) >= 1, \
        f"Expected >=1 manual_review item for ambiguous CAs, got {result.layer_counts()}"
    assert result.manual_review_required is True


# ═══════════════════════════════════════════════════════════════════════════════
# 5. test_quality_intake_event_logged_to_execution_jsonl
# ═══════════════════════════════════════════════════════════════════════════════

def test_quality_intake_event_logged_to_execution_jsonl():
    """quality_intake emits quality_intake_result event to exec_logger."""
    from quality_intake import run_quality_intake

    mock_logger = MagicMock()
    cas = [_CA_UAT, _CA_UNIT]

    with tempfile.TemporaryDirectory() as tmpdir:
        run_quality_intake(
            ticket_id=122,
            title="RF-008",
            description_md="",
            acceptance_criteria=cas,
            exec_logger=mock_logger,
            evidence_dir=Path(tmpdir),
            run_id="122",
        )

    mock_logger.event.assert_called_once()
    call_args = mock_logger.event.call_args
    assert call_args[0][0] == "quality_intake_result", \
        f"Expected event name 'quality_intake_result', got {call_args[0][0]}"
    event_data = call_args[0][1]
    assert event_data["ticket_id"] == 122
    assert "items_total" in event_data
    assert "layers" in event_data
    assert "uat_required" in event_data
    assert "manual_review_required" in event_data


# ═══════════════════════════════════════════════════════════════════════════════
# 6. test_quality_intake_artifact_written_to_evidence
# ═══════════════════════════════════════════════════════════════════════════════

def test_quality_intake_artifact_written_to_evidence():
    """run_quality_intake writes test_portfolio.json to evidence/<run_id>/."""
    from quality_intake import run_quality_intake

    cas = [_CA_UAT, _CA_UNIT]

    with tempfile.TemporaryDirectory() as tmpdir:
        evidence_dir = Path(tmpdir)
        result = run_quality_intake(
            ticket_id=122,
            title="RF-008",
            description_md="",
            acceptance_criteria=cas,
            evidence_dir=evidence_dir,
            run_id="122",
        )
        # Check inside the context manager so the tempdir still exists
        assert result.artifact_path is not None, "Expected artifact_path to be set"
        portfolio_file = Path(result.artifact_path)
        assert portfolio_file.exists(), f"test_portfolio.json not found at {portfolio_file}"
        assert portfolio_file.name == "test_portfolio.json"


# ═══════════════════════════════════════════════════════════════════════════════
# 7. test_test_portfolio_written_to_evidence
# ═══════════════════════════════════════════════════════════════════════════════

def test_test_portfolio_written_to_evidence():
    """test_portfolio.json has the expected schema and structure."""
    from quality_intake import run_quality_intake

    cas = [_CA_UAT, _CA_UNIT, _CA_INTEGRATION, _CA_API, _CA_AMBIGUOUS]

    with tempfile.TemporaryDirectory() as tmpdir:
        evidence_dir = Path(tmpdir)
        result = run_quality_intake(
            ticket_id=122,
            title="RF-008",
            description_md="",
            acceptance_criteria=cas,
            evidence_dir=evidence_dir,
            run_id="122",
        )
        portfolio = json.loads(Path(result.artifact_path).read_text(encoding="utf-8"))

    assert portfolio["ticket_id"] == 122
    assert portfolio["strategy"] == "layered_quality_portfolio"
    assert "generated_at" in portfolio
    assert isinstance(portfolio["items"], list)
    assert len(portfolio["items"]) == 5
    assert "summary" in portfolio
    assert portfolio["summary"]["total"] == 5

    # Each item must have required fields
    for item in portfolio["items"]:
        assert "id" in item
        assert "description" in item
        assert "layer" in item
        assert "business_risk" in item
        assert "needs_browser" in item
        assert "reason" in item
        assert "owner" in item


# ═══════════════════════════════════════════════════════════════════════════════
# 8. test_test_portfolio_has_all_layers_represented
# ═══════════════════════════════════════════════════════════════════════════════

def test_test_portfolio_has_all_layers_represented():
    """Portfolio summary contains a count for each layer present."""
    from quality_intake import run_quality_intake

    cas = [_CA_UAT, _CA_UNIT, _CA_INTEGRATION, _CA_API]

    with tempfile.TemporaryDirectory() as tmpdir:
        result = run_quality_intake(
            ticket_id=122,
            title="RF-008",
            description_md="",
            acceptance_criteria=cas,
            evidence_dir=Path(tmpdir),
            run_id="122",
        )
        portfolio = json.loads(Path(result.artifact_path).read_text(encoding="utf-8"))

    summary = portfolio["summary"]
    layer_total = summary["total"]
    # All layers in items must appear in summary
    item_layers = {item["layer"] for item in portfolio["items"]}
    for layer in item_layers:
        assert layer in summary, f"Layer '{layer}' not in summary: {summary}"
    assert sum(v for k, v in summary.items() if k != "total") == layer_total


# ═══════════════════════════════════════════════════════════════════════════════
# 9. test_compiler_receives_only_uat_and_smoke_items
# ═══════════════════════════════════════════════════════════════════════════════

def test_compiler_receives_only_uat_and_smoke_items():
    """
    When quality_intake classifies CAs, only UAT/smoke_e2e CAs are forwarded
    to the compiler (via _uat_cas list). Non-UAT items are preserved in portfolio.
    """
    from quality_intake import run_quality_intake, BROWSER_LAYERS

    cas = [_CA_UAT, _CA_UAT2, _CA_UNIT, _CA_INTEGRATION, _CA_API]

    with tempfile.TemporaryDirectory() as tmpdir:
        result = run_quality_intake(
            ticket_id=122,
            title="RF-008",
            description_md="",
            acceptance_criteria=cas,
            evidence_dir=Path(tmpdir),
            run_id="122",
        )

    uat_items = result.uat_items
    non_uat_items = result.non_uat_items

    # uat_items are the ones that would go to compiler
    for item in uat_items:
        assert item.layer_recommended in BROWSER_LAYERS, \
            f"uat_items contains non-browser item: {item.layer_recommended}"
        assert item.needs_browser is True

    # non_uat_items are preserved, not discarded
    assert len(non_uat_items) >= 1, "Expected non-UAT items to be preserved"
    # Total must equal original CA count
    assert len(uat_items) + len(non_uat_items) == len(cas)


# ═══════════════════════════════════════════════════════════════════════════════
# 10. test_compiler_skips_when_no_uat_items
# ═══════════════════════════════════════════════════════════════════════════════

def test_compiler_skips_when_no_uat_items():
    """
    When no CAs require browser, uat_items is empty and build_no_uat_skipped_result
    produces a SKIPPED PIP NO_UAT_ITEMS result (ok=True, not an error).
    """
    from quality_intake import run_quality_intake, build_no_uat_skipped_result

    # Only non-browser CAs
    cas = [_CA_UNIT, _CA_INTEGRATION]

    with tempfile.TemporaryDirectory() as tmpdir:
        result = run_quality_intake(
            ticket_id=122,
            title="RF-008",
            description_md="",
            acceptance_criteria=cas,
            evidence_dir=Path(tmpdir),
            run_id="122",
        )
        assert result.uat_items == [], f"Expected no UAT items, got {result.uat_items}"

        skipped = build_no_uat_skipped_result(122, result.artifact_path)

    assert skipped["ok"] is True
    assert skipped["verdict"] == "SKIPPED"
    assert skipped["category"] == "PIP"
    assert skipped["reason"] == "NO_UAT_ITEMS"
    # Must reference test_portfolio for human review
    assert skipped.get("test_portfolio_path") == result.artifact_path


# ═══════════════════════════════════════════════════════════════════════════════
# 11. test_data_preconditions_auto_added_for_uat_with_data_seed
# ═══════════════════════════════════════════════════════════════════════════════

def test_data_preconditions_auto_added_for_uat_with_data_seed():
    """
    For UAT items with needs_data_seed=True, _auto_data_preconditions returns
    a non-empty list with at least one 'grid' precondition.
    """
    from quality_intake import _auto_data_preconditions, QualityIntakeItem

    item = QualityIntakeItem(
        item_id="RF-008-CA-01",
        description="Navegar a la grilla de obligaciones y verificar que se carguen los datos con CLCOD",
        business_risk="high",
        layer_recommended="uat",
        needs_browser=True,
        needs_ui_map="FrmDetalleClie.aspx",
        needs_data_seed=True,
        reason="criterio implica interacción visual",
        owner="qa_automation",
        handoff=None,
    )

    precs = _auto_data_preconditions(item)

    assert len(precs) >= 1, "Expected at least one data_readiness_precondition"
    first = precs[0]
    assert first["type"] == "grid"
    assert "entity" in first
    assert "input_data" in first
    assert "expected" in first
    assert first["expected"]["min_rows"] >= 1


# ═══════════════════════════════════════════════════════════════════════════════
# 12. test_non_uat_items_preserved_in_portfolio_with_handoff
# ═══════════════════════════════════════════════════════════════════════════════

def test_non_uat_items_preserved_in_portfolio_with_handoff():
    """
    Non-UAT items (unit, integration, api_contract) appear in test_portfolio.json
    with an appropriate owner and handoff note.
    """
    from quality_intake import run_quality_intake

    cas = [_CA_UAT, _CA_UNIT, _CA_INTEGRATION]

    with tempfile.TemporaryDirectory() as tmpdir:
        result = run_quality_intake(
            ticket_id=122,
            title="RF-008",
            description_md="",
            acceptance_criteria=cas,
            evidence_dir=Path(tmpdir),
            run_id="122",
        )
        portfolio = json.loads(Path(result.artifact_path).read_text(encoding="utf-8"))

    non_uat_portfolio_items = [
        i for i in portfolio["items"]
        if i["layer"] not in ("uat", "smoke_e2e")
    ]
    assert len(non_uat_portfolio_items) >= 2, \
        f"Expected >=2 non-UAT items in portfolio, got {len(non_uat_portfolio_items)}"
    for item in non_uat_portfolio_items:
        # Must have owner
        assert item.get("owner") in ("developer", "qa_manual"), \
            f"Non-UAT item missing valid owner: {item}"
        # unit/integration should have a handoff note
        if item["layer"] in ("unit", "integration", "api_contract"):
            assert item.get("handoff"), \
                f"Expected handoff for {item['layer']} item: {item}"


# ═══════════════════════════════════════════════════════════════════════════════
# 13. test_intake_layer_router_unit_for_pure_rule
# ═══════════════════════════════════════════════════════════════════════════════

def test_intake_layer_router_unit_for_pure_rule():
    """Layer router classifies pure calculation/validation rules as 'unit'."""
    from quality_intake import _route_layer

    pure_rules = [
        "Validar que al calcular el impuesto el resultado sea positivo",
        "Campo obligatorio: el nombre no puede estar vacío",
        "Formato de fecha debe ser DD/MM/YYYY",
        "Validar regla de mapeo Provincia→Departamento",
        "La máscara del campo CLCOD debe aceptar solo numéricos",
    ]

    for ca in pure_rules:
        layer, needs_browser, reason = _route_layer(ca)
        assert layer == "unit", \
            f"Expected 'unit' for '{ca}', got '{layer}' (reason: {reason})"
        assert needs_browser is False


# ═══════════════════════════════════════════════════════════════════════════════
# 14. test_intake_layer_router_uat_for_visual_interaction
# ═══════════════════════════════════════════════════════════════════════════════

def test_intake_layer_router_uat_for_visual_interaction():
    """Layer router classifies visual navigation/interaction CAs as 'uat'."""
    from quality_intake import _route_layer

    visual_cas = [
        "Validar que al hacer clic en Aceptar se guarden los datos",
        "Navegar a la pantalla de detalle y verificar el formulario",
        "Seleccionar en pantalla el combo de provincias y validar que filtre",
        "Visualmente verificar que la grilla muestre los resultados",
        "El botón de búsqueda debe estar visible en la pantalla",
    ]

    for ca in visual_cas:
        layer, needs_browser, reason = _route_layer(ca)
        assert layer == "uat", \
            f"Expected 'uat' for '{ca}', got '{layer}' (reason: {reason})"
        assert needs_browser is True


# ═══════════════════════════════════════════════════════════════════════════════
# 15. test_intake_layer_router_manual_review_for_ambiguous
# ═══════════════════════════════════════════════════════════════════════════════

def test_intake_layer_router_manual_review_for_ambiguous():
    """Ambiguous CAs and production-related CAs route to manual_review."""
    from quality_intake import _route_layer

    ambiguous_cas = [
        "Revisar comportamiento del sistema",
        "Evaluar el módulo en producción",
        "Se requiere juicio experto para validar este escenario",
        "",  # empty CA
        "datos sensibles del cliente deben ser protegidos",
    ]

    for ca in ambiguous_cas:
        layer, needs_browser, reason = _route_layer(ca)
        assert layer == "manual_review", \
            f"Expected 'manual_review' for '{ca}', got '{layer}' (reason: {reason})"
        assert needs_browser is False


# ═══════════════════════════════════════════════════════════════════════════════
# Bonus: extract_acceptance_criteria helper
# ═══════════════════════════════════════════════════════════════════════════════

def test_extract_acceptance_criteria_from_list():
    """extract_acceptance_criteria reads from acceptance_criteria list field."""
    from quality_intake import extract_acceptance_criteria

    ticket = _make_ticket(acceptance_criteria=[_CA_UAT, _CA_UNIT])
    cas = extract_acceptance_criteria(ticket)
    assert len(cas) == 2
    assert _CA_UAT in cas


def test_extract_acceptance_criteria_from_plan_pruebas():
    """extract_acceptance_criteria falls back to plan_pruebas list."""
    from quality_intake import extract_acceptance_criteria

    ticket = _make_ticket(plan_pruebas=[_CA_UNIT, _CA_INTEGRATION])
    cas = extract_acceptance_criteria(ticket)
    assert len(cas) >= 2


def test_extract_acceptance_criteria_from_description_md():
    """extract_acceptance_criteria parses Markdown CA section."""
    from quality_intake import extract_acceptance_criteria

    md = """
## Descripción
El sistema debe filtrar departamentos.

## Criterios de Aceptación
- Validar que al seleccionar provincia se filtren departamentos
- Validar que al calcular el monto el resultado sea correcto

## Notas
Sin notas adicionales.
"""
    ticket = _make_ticket(description_md=md)
    cas = extract_acceptance_criteria(ticket)
    assert len(cas) == 2
    assert any("provincia" in c for c in cas)
    assert any("calcular" in c for c in cas)


def test_quality_intake_item_id_format():
    """Item IDs follow the RF-NNN-CA-NN pattern when title contains RF number."""
    from quality_intake import run_quality_intake

    with tempfile.TemporaryDirectory() as tmpdir:
        result = run_quality_intake(
            ticket_id=122,
            title="RF-008 — Filtros de provincia",
            description_md="",
            acceptance_criteria=[_CA_UAT, _CA_UNIT],
            evidence_dir=Path(tmpdir),
            run_id="122",
        )

    for item in result.items:
        assert item.item_id.startswith("RF-008-CA-"), \
            f"Expected item ID starting with RF-008-CA-, got {item.item_id}"


def test_quality_intake_uat_required_true_when_browser_items_present():
    """uat_required=True when at least one item has needs_browser=True."""
    from quality_intake import run_quality_intake

    with tempfile.TemporaryDirectory() as tmpdir:
        result = run_quality_intake(
            ticket_id=122,
            title="RF-008",
            description_md="",
            acceptance_criteria=[_CA_UAT, _CA_UNIT],
            evidence_dir=Path(tmpdir),
            run_id="122",
        )

    assert result.uat_required is True


def test_quality_intake_uat_required_false_when_no_browser_items():
    """uat_required=False when all items have needs_browser=False."""
    from quality_intake import run_quality_intake

    with tempfile.TemporaryDirectory() as tmpdir:
        result = run_quality_intake(
            ticket_id=122,
            title="RF-008",
            description_md="",
            acceptance_criteria=[_CA_UNIT, _CA_INTEGRATION],
            evidence_dir=Path(tmpdir),
            run_id="122",
        )

    assert result.uat_required is False


def test_quality_intake_api_contract_layer():
    """CAs with endpoint/API/DTO keywords are classified as api_contract."""
    from quality_intake import _route_layer

    layer, needs_browser, reason = _route_layer(
        "Validar el endpoint POST /api/clientes retorna DTO con status 201"
    )
    assert layer == "api_contract", f"Expected api_contract, got {layer}"
    assert needs_browser is False


def test_quality_intake_smoke_e2e_layer():
    """CAs with login/ruta crítica/smoke keywords are classified as smoke_e2e."""
    from quality_intake import _route_layer

    layer, needs_browser, reason = _route_layer(
        "Validar que el login del usuario funcione correctamente en la ruta crítica"
    )
    assert layer == "smoke_e2e", f"Expected smoke_e2e, got {layer}"
    assert needs_browser is True
