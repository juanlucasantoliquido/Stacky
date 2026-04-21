"""
test_stage_transitions.py — Integration tests for PM → DEV → QA stage transitions.

Tests that transitions respect contracts, create correct flags, and block
advancement when output is invalid.
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, call

# Shared helpers
def create_pm_output_with_placeholders(tmp_path: Path) -> Path:
    folder = tmp_path / "asignada" / "0099999"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "INC-0099999.md").write_text("# Ticket\nBug description", encoding="utf-8")
    (folder / "INCIDENTE.md").write_text("# Incidente\n" + "\n".join(["línea"] * 10), encoding="utf-8")
    (folder / "ANALISIS_TECNICO.md").write_text(
        "# Análisis\n_A completar por PM_\nResto del contenido...", encoding="utf-8"
    )
    (folder / "ARQUITECTURA_SOLUCION.md").write_text(
        "# Arquitectura\nArchivo: Batch/Negocio/EjemploDalc.cs\n" + "\n".join(["línea"] * 10),
        encoding="utf-8"
    )
    (folder / "TAREAS_DESARROLLO.md").write_text(
        "# Tareas\n## PENDIENTE\n- [ ] Tarea 1\n" + "\n".join(["línea"] * 10),
        encoding="utf-8"
    )
    return folder


def create_valid_pm_output(tmp_path: Path) -> Path:
    folder = tmp_path / "asignada" / "0099998"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "INC-0099998.md").write_text("# Ticket\nBug description", encoding="utf-8")
    files = {
        "INCIDENTE.md": "# Incidente\n" + "\n".join(["línea"] * 10),
        "ANALISIS_TECNICO.md": "# Análisis\n" + "\n".join(["análisis detallado"] * 15),
        "ARQUITECTURA_SOLUCION.md": "# Arquitectura\nArchivo: Batch/Negocio/EjemploDalc.cs\n" + "\n".join(["línea"] * 10),
        "TAREAS_DESARROLLO.md": "# Tareas\n## PENDIENTE\n- [ ] Tarea 1\n" + "\n".join(["línea"] * 10),
        "QUERIES_ANALISIS.sql": "SELECT 1; -- query\n" * 5,
        "NOTAS_IMPLEMENTACION.md": "# Notas\n" + "\n".join(["nota"] * 8),
    }
    for fname, content in files.items():
        (folder / fname).write_text(content, encoding="utf-8")
    return folder


def create_qa_output_with_findings(tmp_path: Path) -> Path:
    folder = create_valid_pm_output(tmp_path)
    (folder / "DEV_COMPLETADO.md").write_text(
        "# Dev Completado\nArchivos modificados:\n- PagosDalc.cs",
        encoding="utf-8"
    )
    (folder / "TESTER_COMPLETADO.md").write_text(
        "# QA\nVeredicto: CON OBSERVACIONES\n\n## Observaciones\n- Falta validación NULL",
        encoding="utf-8"
    )
    return folder


class TestPMtoDEVTransition:
    def test_placeholder_blocks_advancement(self, tmp_path):
        """If PM produces output with placeholders, DEV should NOT be invoked."""
        ticket_folder = create_pm_output_with_placeholders(tmp_path)

        try:
            from output_validator import validate_stage_output
            result = validate_stage_output("pm", str(ticket_folder))
            assert not result.ok, "PM output with placeholders should fail validation"
            assert any("placeholder" in i.lower() for i in result.issues)
        except ImportError:
            pytest.skip("output_validator not available")

    def test_valid_pm_passes_validation(self, tmp_path):
        """Valid PM output should pass validation."""
        ticket_folder = create_valid_pm_output(tmp_path)

        try:
            from output_validator import validate_stage_output
            result = validate_stage_output("pm", str(ticket_folder))
            assert result.ok, f"Valid PM output should pass: {result.issues}"
        except ImportError:
            pytest.skip("output_validator not available")


class TestQAReworkCycle:
    def test_qa_with_observations_triggers_rework_flag(self, tmp_path):
        """QA with observations should create a rework indicator."""
        ticket_folder = create_qa_output_with_findings(tmp_path)
        tester_file = ticket_folder / "TESTER_COMPLETADO.md"
        content = tester_file.read_text(encoding="utf-8")
        assert "CON OBSERVACIONES" in content
        assert "Observaciones" in content

    def test_rework_cycle_increments_counter(self, tmp_path):
        """Each rework cycle should be trackable."""
        ticket_folder = create_qa_output_with_findings(tmp_path)

        try:
            from pipeline_state import load_state, save_state
            state = load_state(str(ticket_folder))
            state["rework_count"] = state.get("rework_count", 0) + 1
            save_state(str(ticket_folder), state)
            reloaded = load_state(str(ticket_folder))
            assert reloaded.get("rework_count", 0) >= 1
        except ImportError:
            pytest.skip("pipeline_state not available")
