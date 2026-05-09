"""
tests/unit/test_sprint2_screen_contract.py — Sprint 2 tests.

Validates:
1. screen_detection.json artifact written to evidence per run.
2. screen_detection_result event references artifact_path.
3. selector_contract_validator: ALLOW when all aliases present.
4. selector_contract_validator: BLOCKED when aliases missing.
5. selector_contract_validator: BLOCKED when decorative element action.
6. selector_contract_validator: BLOCKED when UI map missing.
7. selector_contract.json artifact written to evidence.
8. selector_contract_validation event logged to execution.jsonl.
9. No .spec.ts written when selector contract fails.
10. FrmDetalleClie.aspx fixture has valid schema ui_map/1.1.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure the tool root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
os.environ.setdefault("STACKY_LLM_BACKEND", "mock")
os.environ.setdefault("QA_UAT_REQUIRE_PLAYBOOK", "false")

TOOL_DIR = Path(__file__).parent.parent.parent
FIXTURES = Path(__file__).parent.parent / "fixtures"
UI_MAPS_DIR = TOOL_DIR / "cache" / "ui_maps"

# ── Helpers ────────────────────────────────────────────────────────────────────


def _minimal_ticket(screen: str = "FrmDetalleClie.aspx") -> dict:
    return {
        "ok": True,
        "analisis_tecnico": f"La pantalla objetivo es {screen}.",
        "plan_pruebas": [
            {"id": "P01", "descripcion": f"Verificar carga de {screen}",
             "datos": "", "esperado": "Pantalla cargada correctamente"},
        ],
        "ticket": {"description": f"Test para {screen}"},
        "description_md": f"Ver {screen}",
    }


def _make_ui_map(
    screen: str = "FrmDetalleClie.aspx",
    aliases: list = None,
    include_decorative: bool = False,
) -> dict:
    """Build a minimal UI map with the given alias list."""
    elements = []
    for alias in (aliases or []):
        elements.append({
            "alias_semantic": alias,
            "kind": "input",
            "role": "textbox",
            "asp_id": alias,
            "is_decorative": False,
            "is_interactive": True,
            "confidence": 0.95,
        })
    if include_decorative:
        elements.append({
            "alias_semantic": "msg_titulo",
            "kind": "div",
            "role": "heading",
            "asp_id": "lblTitulo",
            "is_decorative": True,
            "is_interactive": False,
            "confidence": 0.80,
        })
    return {
        "ok": True,
        "schema_version": "ui_map/1.1",
        "screen": screen,
        "elements": elements,
        "grids": [],
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 1. screen_detection.json artifact written to evidence per run
# ═══════════════════════════════════════════════════════════════════════════════

def test_screen_detection_artifact_written_to_evidence():
    """screen_detection.json must be created in evidence/<ticket_id>/<run_id>/."""
    from screen_detector import detect_screens_and_persist

    ticket = _minimal_ticket("FrmDetalleClie.aspx")

    with tempfile.TemporaryDirectory() as tmpdir:
        evidence_dir = Path(tmpdir) / "evidence" / "122"
        evidence_dir.mkdir(parents=True)

        result = detect_screens_and_persist(
            ticket_result=ticket,
            evidence_dir=evidence_dir,
            run_id="122",
        )

        artifact_file = evidence_dir / "122" / "screen_detection.json"
        assert artifact_file.exists(), (
            f"screen_detection.json must be written to {artifact_file}"
        )
        data = json.loads(artifact_file.read_text(encoding="utf-8"))
        assert data.get("schema_version") == "screen_detection/1.0"
        assert isinstance(data.get("selected_screens"), list)
        assert "FrmDetalleClie.aspx" in data["selected_screens"]
        assert result.artifact_path == str(artifact_file)


# ═══════════════════════════════════════════════════════════════════════════════
# 2. screen_detection_result event references artifact_path
# ═══════════════════════════════════════════════════════════════════════════════

def test_screen_detection_event_references_artifact_path():
    """ScreenDetectionResult.to_dict() must include artifact_path after persist."""
    from screen_detector import detect_screens_and_persist

    ticket = _minimal_ticket("FrmDetalleClie.aspx")

    with tempfile.TemporaryDirectory() as tmpdir:
        evidence_dir = Path(tmpdir) / "evidence" / "122"
        evidence_dir.mkdir(parents=True)

        result = detect_screens_and_persist(
            ticket_result=ticket,
            evidence_dir=evidence_dir,
            run_id="122",
        )

        d = result.to_dict()
        assert "artifact_path" in d, "to_dict() must include artifact_path"
        assert d["artifact_path"] is not None, "artifact_path must not be None after persist"
        assert "screen_detection.json" in d["artifact_path"]


# ═══════════════════════════════════════════════════════════════════════════════
# 3. selector_contract ALLOW when all aliases present
# ═══════════════════════════════════════════════════════════════════════════════

def test_selector_contract_allows_when_all_aliases_present():
    """validate_selector_contract returns ALLOW when every requested alias exists."""
    from selector_contract_validator import validate_selector_contract

    with tempfile.TemporaryDirectory() as tmpdir:
        ui_map_file = Path(tmpdir) / "FrmDetalleClie.aspx.json"
        ui_map = _make_ui_map(
            "FrmDetalleClie.aspx",
            aliases=["cmbProvincia", "cmbDepartamento", "btnGuardar"],
        )
        ui_map_file.write_text(json.dumps(ui_map), encoding="utf-8")

        result = validate_selector_contract(
            screen="FrmDetalleClie.aspx",
            aliases_requested=["cmbProvincia", "btnGuardar"],
            ui_map_path=str(ui_map_file),
        )

    assert result.decision == "ALLOW"
    assert result.valid is True
    assert result.missing_aliases == []
    assert result.reason is None
    assert result.category is None


# ═══════════════════════════════════════════════════════════════════════════════
# 4. selector_contract BLOCKED when aliases missing
# ═══════════════════════════════════════════════════════════════════════════════

def test_selector_contract_blocks_missing_aliases():
    """validate_selector_contract returns BLOCKED GEN SELECTOR_ALIAS_NOT_IN_UI_MAP."""
    from selector_contract_validator import validate_selector_contract

    with tempfile.TemporaryDirectory() as tmpdir:
        ui_map_file = Path(tmpdir) / "FrmDetalleClie.aspx.json"
        ui_map = _make_ui_map(
            "FrmDetalleClie.aspx",
            aliases=["cmbProvincia", "cmbDepartamento", "btnGuardar"],
        )
        ui_map_file.write_text(json.dumps(ui_map), encoding="utf-8")

        result = validate_selector_contract(
            screen="FrmDetalleClie.aspx",
            aliases_requested=["ddl_provincia", "link_agregar_domicilio"],
            ui_map_path=str(ui_map_file),
        )

    assert result.decision == "BLOCKED"
    assert result.valid is False
    assert result.category == "GEN"
    assert result.reason == "SELECTOR_ALIAS_NOT_IN_UI_MAP"
    assert "ddl_provincia" in result.missing_aliases
    assert "link_agregar_domicilio" in result.missing_aliases


# ═══════════════════════════════════════════════════════════════════════════════
# 5. selector_contract BLOCKED when decorative element action
# ═══════════════════════════════════════════════════════════════════════════════

def test_selector_contract_blocks_decorative_action():
    """validate_selector_contract returns BLOCKED GEN DECORATIVE_ELEMENT_ACTION
    when a click/fill is attempted on a decorative element."""
    from selector_contract_validator import validate_selector_contract

    with tempfile.TemporaryDirectory() as tmpdir:
        ui_map_file = Path(tmpdir) / "FrmDetalleClie.aspx.json"
        ui_map = _make_ui_map(
            "FrmDetalleClie.aspx",
            aliases=["cmbProvincia"],
            include_decorative=True,
        )
        ui_map_file.write_text(json.dumps(ui_map), encoding="utf-8")

        result = validate_selector_contract(
            screen="FrmDetalleClie.aspx",
            aliases_requested=["cmbProvincia", "msg_titulo"],
            ui_map_path=str(ui_map_file),
            action_map={
                "cmbProvincia": "select",
                "msg_titulo": "click",  # decorative → blocked
            },
        )

    assert result.decision == "BLOCKED"
    assert result.valid is False
    assert result.category == "GEN"
    assert result.reason == "DECORATIVE_ELEMENT_ACTION"
    assert any("msg_titulo" in v for v in result.decorative_action_attempts)


# ═══════════════════════════════════════════════════════════════════════════════
# 6. selector_contract BLOCKED when UI map missing
# ═══════════════════════════════════════════════════════════════════════════════

def test_selector_contract_blocks_when_ui_map_missing():
    """validate_selector_contract returns BLOCKED GEN UI_MAP_MISSING."""
    from selector_contract_validator import validate_selector_contract

    result = validate_selector_contract(
        screen="FrmDetalleClie.aspx",
        aliases_requested=["cmbProvincia", "btnGuardar"],
        ui_map_path="/nonexistent/path/FrmDetalleClie.aspx.json",
    )

    assert result.decision == "BLOCKED"
    assert result.valid is False
    assert result.category == "GEN"
    assert result.reason == "UI_MAP_MISSING"
    assert result.missing_aliases == ["cmbProvincia", "btnGuardar"]


# ═══════════════════════════════════════════════════════════════════════════════
# 7. selector_contract.json artifact written to evidence
# ═══════════════════════════════════════════════════════════════════════════════

def test_selector_contract_artifact_written_to_evidence():
    """selector_contract.json must be written to evidence_dir/run_id/."""
    from selector_contract_validator import validate_selector_contract

    with tempfile.TemporaryDirectory() as tmpdir:
        ui_map_file = Path(tmpdir) / "FrmDetalleClie.aspx.json"
        ui_map = _make_ui_map("FrmDetalleClie.aspx", aliases=["cmbProvincia"])
        ui_map_file.write_text(json.dumps(ui_map), encoding="utf-8")

        evidence_dir = Path(tmpdir) / "evidence"
        evidence_dir.mkdir()

        result = validate_selector_contract(
            screen="FrmDetalleClie.aspx",
            aliases_requested=["cmbProvincia"],
            ui_map_path=str(ui_map_file),
            scenario_id="RF-008-CA-01",
            evidence_dir=evidence_dir,
            run_id="122",
        )

        artifact_file = evidence_dir / "122" / "selector_contract_RF-008-CA-01.json"
        assert artifact_file.exists(), (
            f"selector_contract artifact must be written to {artifact_file}"
        )
        data = json.loads(artifact_file.read_text(encoding="utf-8"))
        assert data.get("schema_version") == "selector_contract/1.0"
        assert data.get("screen") == "FrmDetalleClie.aspx"
        assert data.get("decision") == "ALLOW"
        assert result.artifact_path == str(artifact_file)


# ═══════════════════════════════════════════════════════════════════════════════
# 8. selector_contract_validation event logged to execution.jsonl
# ═══════════════════════════════════════════════════════════════════════════════

def test_selector_contract_event_logged_to_execution_jsonl():
    """selector_contract_validation event must appear in execution.jsonl
    with the mandatory fields."""
    from execution_logger import get_logger, close_logger
    from selector_contract_validator import SelectorContractResult

    with tempfile.TemporaryDirectory() as tmpdir:
        evidence_dir = Path(tmpdir)
        log = get_logger("test_sc_event", evidence_dir=evidence_dir)
        log.session_start({
            "run_id": "test_sc_event",
            "ticket_id": 122,
            "mode": "dry-run",
            "tool": "qa_uat_agent",
            "tool_version": "test",
            "started_at": "2026-05-09T00:00:00Z",
        })

        # Simulate what the pipeline emits
        sc_result = SelectorContractResult(
            valid=False,
            screen="FrmDetalleClie.aspx",
            aliases_requested=["ddl_provincia", "link_agregar_domicilio"],
            aliases_available=["cmbProvincia", "cmbDepartamento", "btnGuardar"],
            missing_aliases=["ddl_provincia", "link_agregar_domicilio"],
            decision="BLOCKED",
            category="GEN",
            reason="SELECTOR_ALIAS_NOT_IN_UI_MAP",
            artifact_path="/tmp/selector_contract.json",
        )
        log.event("selector_contract_validation", {
            **sc_result.to_dict(),
            "artifact_path": sc_result.artifact_path,
        }, scenario_id="RF-008-CA-01")

        log.pipeline_verdict(
            verdict="BLOCKED",
            category="GEN",
            reason="SELECTOR_ALIAS_NOT_IN_UI_MAP",
            failed_stage="selector_contract",
            confidence=1.0,
        )
        log.session_end({
            "ok": False,
            "verdict": "BLOCKED",
            "category": "GEN",
            "reason": "SELECTOR_ALIAS_NOT_IN_UI_MAP",
            "elapsed_s": 0.2,
        })
        close_logger("test_sc_event")

        jsonl = evidence_dir / "execution.jsonl"
        events = [json.loads(line) for line in jsonl.read_text(encoding="utf-8").splitlines()]
        event_names = [e["event"] for e in events]

        assert "selector_contract_validation" in event_names, (
            f"selector_contract_validation event must be present. Got: {event_names}"
        )
        sc_events = [e for e in events if e["event"] == "selector_contract_validation"]
        assert sc_events, "At least one selector_contract_validation event required"
        sc_data = sc_events[0]["data"]
        assert sc_data.get("decision") == "BLOCKED"
        assert sc_data.get("reason") == "SELECTOR_ALIAS_NOT_IN_UI_MAP"
        assert sc_data.get("category") == "GEN"
        assert isinstance(sc_data.get("missing_aliases"), list)
        assert isinstance(sc_data.get("aliases_available"), list)


# ═══════════════════════════════════════════════════════════════════════════════
# 9. No .spec.ts written when selector contract fails
# ═══════════════════════════════════════════════════════════════════════════════

def test_no_spec_written_when_selector_contract_fails():
    """When selector contract is BLOCKED, validate_all_scenarios reports ok=False
    and no downstream generator call should be made."""
    from selector_contract_validator import validate_all_scenarios

    scenarios = [
        {
            "id": "RF-008-CA-01",
            "screen": "FrmDetalleClie.aspx",
            "steps": [
                {"alias_semantic": "ddl_provincia", "action": "select"},
                {"alias_semantic": "link_agregar_domicilio", "action": "click"},
            ],
        }
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        ui_maps_dir = Path(tmpdir)
        # Write UI map WITHOUT the requested aliases
        ui_map = _make_ui_map("FrmDetalleClie.aspx", aliases=["btnGuardar"])
        (ui_maps_dir / "FrmDetalleClie.aspx.json").write_text(
            json.dumps(ui_map), encoding="utf-8"
        )

        result = validate_all_scenarios(
            scenarios=scenarios,
            ui_maps_dir=ui_maps_dir,
        )

    assert result["ok"] is False, "validate_all_scenarios must return ok=False when blocked"
    assert result["blocked_count"] == 1
    assert result["allow_count"] == 0
    assert result["first_blocked_reason"] == "SELECTOR_ALIAS_NOT_IN_UI_MAP"


# ═══════════════════════════════════════════════════════════════════════════════
# 10. FrmDetalleClie.aspx fixture has valid schema ui_map/1.1
# ═══════════════════════════════════════════════════════════════════════════════

def test_ui_map_fixture_frm_detalle_clie_valid_schema():
    """cache/ui_maps/FrmDetalleClie.aspx.json must satisfy ui_map/1.1 contract."""
    fixture_path = UI_MAPS_DIR / "FrmDetalleClie.aspx.json"
    assert fixture_path.exists(), (
        f"Fixture must exist at {fixture_path}. Run Sprint 2 setup first."
    )

    data = json.loads(fixture_path.read_text(encoding="utf-8"))

    # Required top-level fields
    assert data.get("schema_version") == "ui_map/1.1", (
        f"schema_version must be 'ui_map/1.1', got: {data.get('schema_version')}"
    )
    assert data.get("screen") == "FrmDetalleClie.aspx"
    assert data.get("ok") is True
    assert isinstance(data.get("elements"), list)
    assert len(data["elements"]) > 0, "elements must not be empty"

    # Each element must have required fields
    required_element_keys = {
        "alias_semantic", "role", "is_decorative",
    }
    for el in data["elements"]:
        missing_keys = required_element_keys - set(el.keys())
        assert not missing_keys, (
            f"Element {el.get('alias_semantic', '?')} missing keys: {missing_keys}"
        )
        assert isinstance(el["is_decorative"], bool)

    # Must include at least the three fixture elements from spec
    aliases = {el["alias_semantic"] for el in data["elements"]}
    for expected in ("cmbProvincia", "cmbDepartamento", "btnGuardar"):
        assert expected in aliases, (
            f"Fixture must include alias '{expected}', got: {sorted(aliases)}"
        )

    # grids must be a list
    assert isinstance(data.get("grids", []), list)

    # GridObligaciones must be present
    grid_aliases = {g.get("alias_semantic") for g in data.get("grids", [])}
    assert "GridObligaciones" in grid_aliases, (
        f"GridObligaciones must be in grids, got: {grid_aliases}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Additional: to_dict contract on SelectorContractResult
# ═══════════════════════════════════════════════════════════════════════════════

def test_selector_contract_result_to_dict_contract():
    """SelectorContractResult.to_dict() must include all required keys."""
    from selector_contract_validator import SelectorContractResult

    result = SelectorContractResult(
        valid=False,
        screen="FrmDetalleClie.aspx",
        aliases_requested=["cmbProvincia"],
        aliases_available=[],
        missing_aliases=["cmbProvincia"],
        decision="BLOCKED",
        category="GEN",
        reason="SELECTOR_ALIAS_NOT_IN_UI_MAP",
    )
    d = result.to_dict()
    required = {
        "schema_version", "valid", "screen",
        "aliases_requested", "aliases_available",
        "missing_aliases", "decorative_action_attempts",
        "decision", "category", "reason",
    }
    missing = required - set(d.keys())
    assert not missing, f"to_dict() missing keys: {missing}"


def test_selector_contract_validate_all_allows_when_empty_scenarios():
    """validate_all_scenarios returns ok=True for an empty scenario list."""
    from selector_contract_validator import validate_all_scenarios

    with tempfile.TemporaryDirectory() as tmpdir:
        result = validate_all_scenarios(
            scenarios=[],
            ui_maps_dir=Path(tmpdir),
        )
    assert result["ok"] is True
    assert result["blocked_count"] == 0
    assert result["allow_count"] == 0


def test_selector_contract_batch_partial_block():
    """validate_all_scenarios correctly counts partial blocks
    (some scenarios OK, some blocked)."""
    from selector_contract_validator import validate_all_scenarios

    scenarios = [
        {
            "id": "CA-01",
            "screen": "FrmDetalleClie.aspx",
            "steps": [{"alias_semantic": "cmbProvincia", "action": "select"}],
        },
        {
            "id": "CA-02",
            "screen": "FrmDetalleClie.aspx",
            "steps": [{"alias_semantic": "nonexistent_alias", "action": "click"}],
        },
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        ui_maps_dir = Path(tmpdir)
        ui_map = _make_ui_map("FrmDetalleClie.aspx", aliases=["cmbProvincia"])
        (ui_maps_dir / "FrmDetalleClie.aspx.json").write_text(
            json.dumps(ui_map), encoding="utf-8"
        )

        result = validate_all_scenarios(
            scenarios=scenarios,
            ui_maps_dir=ui_maps_dir,
        )

    assert result["ok"] is False
    assert result["blocked_count"] == 1
    assert result["allow_count"] == 1
    assert result["first_blocked_reason"] == "SELECTOR_ALIAS_NOT_IN_UI_MAP"


# ═══════════════════════════════════════════════════════════════════════════════
# screen_aliases.yml Sprint 2 expansion tests
# ═══════════════════════════════════════════════════════════════════════════════

def test_screen_aliases_contains_sprint2_screens():
    """screen_aliases.yml must include alias entries for Sprint 2 new screens.

    Parses the YAML manually (without the yaml module, which may not be installed)
    by scanning for screen-name lines that mark a YAML mapping key.
    """
    aliases_file = TOOL_DIR / "screen_aliases.yml"
    assert aliases_file.exists(), "screen_aliases.yml must exist"

    # Parse without pyyaml: look for lines that start with a screen name followed by ':'
    content = aliases_file.read_text(encoding="utf-8")
    import re
    # Match lines like "FrmXxx.aspx:" or "PopUpXxx.aspx:" at column 0
    found_screens = set(re.findall(r'^((?:Frm|PopUp|Login|Default|Errors|Workflow)\S+\.aspx):', content, re.MULTILINE))

    expected_screens = [
        "FrmDetalleClie.aspx",
        "FrmAgenda.aspx",
        "FrmGestion.aspx",
        "FrmBusqueda.aspx",
        "FrmLiquidaciones.aspx",
        "FrmSimulacionUnitaria.aspx",
        "FrmAgendaEquipo.aspx",
        "PopUpDomicilios.aspx",
    ]
    for screen in expected_screens:
        assert screen in found_screens, (
            f"screen_aliases.yml must include an entry for {screen}. "
            f"Found screens: {sorted(found_screens)}"
        )


def test_screen_detector_uses_sprint2_aliases():
    """screen_detector must match 'agenda equipo' → FrmAgendaEquipo.aspx via aliases
    when pyyaml is installed. If pyyaml is absent, verifies graceful degradation.
    """
    from screen_detector import _load_aliases, _ALIASES_CACHE
    import screen_detector as _sd

    # Clear the alias cache to force reload
    _sd._ALIASES_CACHE = None

    try:
        import yaml  # type: ignore[import]
        _yaml_available = True
    except ImportError:
        _yaml_available = False

    if not _yaml_available:
        # Graceful degradation: when yaml is absent, aliases are disabled.
        # Verify the detector does not crash and returns a structured result.
        from screen_detector import detect_screens
        ticket = {
            "analisis_tecnico": "FrmAgendaEquipo.aspx es la pantalla objetivo.",
            "plan_pruebas": [],
            "ticket": {"description": ""},
            "description_md": "",
        }
        result = detect_screens(ticket)
        # Falls back to exact-match detection (analisis_tecnico contains the screen name)
        assert "FrmAgendaEquipo.aspx" in result.selected_screens, (
            "When yaml is unavailable, exact name match must still work. "
            f"Got: {result.selected_screens}"
        )
        return

    # yaml is available: test alias matching
    from screen_detector import detect_screens

    ticket = {
        "analisis_tecnico": "Se debe verificar la funcionalidad de agenda equipo del sistema.",
        "plan_pruebas": [
            {"id": "P01", "descripcion": "Verificar agenda equipo", "datos": "", "esperado": "OK"},
        ],
        "ticket": {"description": "Agenda del equipo"},
        "description_md": "Prueba en la vista de agenda equipo.",
    }
    result = detect_screens(ticket)
    assert "FrmAgendaEquipo.aspx" in result.selected_screens, (
        f"'agenda equipo' alias must resolve to FrmAgendaEquipo.aspx. "
        f"Got: {result.selected_screens}"
    )
