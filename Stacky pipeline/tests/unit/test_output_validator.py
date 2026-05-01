"""Tests unitarios para output_validator.py — el gatekeeper entre etapas del pipeline."""

import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from output_validator import validate_stage_output, ValidationResult


# ─── Helpers ────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_ticket(tmp_path):
    folder = tmp_path / "asignada" / "0099999"
    folder.mkdir(parents=True)
    (folder / "INC-0099999.md").write_text("# Ticket\nDescripción del error.")
    return folder


@pytest.fixture
def valid_pm_output(tmp_ticket):
    files = {
        "INCIDENTE.md": "# Incidente\n" + "\n".join(["línea"] * 10),
        "ANALISIS_TECNICO.md": "# Análisis\n" + "\n".join(["línea"] * 15),
        "ARQUITECTURA_SOLUCION.md": "# Arquitectura\nArchivo: Batch/Negocio/EjemploDalc.cs\n" + "\n".join(["línea"] * 10),
        "TAREAS_DESARROLLO.md": "# Tareas\n## PENDIENTE\n- [ ] Tarea 1\n" + "\n".join(["línea"] * 10),
        "QUERIES_ANALISIS.sql": "SELECT 1; -- query de prueba\n" * 5,
        "NOTAS_IMPLEMENTACION.md": "# Notas\n" + "\n".join(["nota"] * 8),
    }
    for fname, content in files.items():
        (tmp_ticket / fname).write_text(content, encoding="utf-8")
    return tmp_ticket


@pytest.fixture
def pm_output_with_placeholders(valid_pm_output):
    (valid_pm_output / "ANALISIS_TECNICO.md").write_text(
        "# Análisis\n_A completar por PM_\nResto del contenido...\n" + "\n".join(["x"] * 15),
        encoding="utf-8"
    )
    return valid_pm_output


# ─── Tests PM ───────────────────────────────────────────────────────────────

class TestValidatePM:
    def test_placeholder_bloqueante(self, pm_output_with_placeholders):
        result = validate_stage_output("pm", str(pm_output_with_placeholders))
        assert not result.ok
        assert any("placeholder" in i.lower() for i in result.issues)

    def test_archivo_requerido_faltante_bloquea(self, tmp_ticket):
        result = validate_stage_output("pm", str(tmp_ticket))
        assert not result.ok
        assert any("ANALISIS_TECNICO" in i for i in result.issues)

    def test_archivo_demasiado_corto_bloquea(self, tmp_ticket):
        (tmp_ticket / "ANALISIS_TECNICO.md").write_text("# ok", encoding="utf-8")
        (tmp_ticket / "INCIDENTE.md").write_text("# ok\n" * 6, encoding="utf-8")
        (tmp_ticket / "ARQUITECTURA_SOLUCION.md").write_text(
            "# Arq\nBatch/Negocio/X.cs\n" * 5, encoding="utf-8"
        )
        (tmp_ticket / "TAREAS_DESARROLLO.md").write_text(
            "# T\n## PENDIENTE\n" + "\n".join(["t"] * 12), encoding="utf-8"
        )
        result = validate_stage_output("pm", str(tmp_ticket))
        assert not result.ok

    def test_archivo_opcional_faltante_es_warning_no_error(self, valid_pm_output):
        (valid_pm_output / "QUERIES_ANALISIS.sql").unlink()
        result = validate_stage_output("pm", str(valid_pm_output))
        assert result.ok
        assert result.warnings

    def test_output_completo_sin_placeholders_pasa(self, valid_pm_output):
        result = validate_stage_output("pm", str(valid_pm_output))
        assert result.ok
        assert not result.issues

    def test_issues_str_format(self, pm_output_with_placeholders):
        result = validate_stage_output("pm", str(pm_output_with_placeholders))
        issues_text = result.issues_str()
        assert issues_text.startswith("-")

    def test_stage_is_pm(self, valid_pm_output):
        result = validate_stage_output("pm", str(valid_pm_output))
        assert result.stage == "pm"


# ─── Tests DEV ──────────────────────────────────────────────────────────────

class TestValidateDEV:
    def test_dev_completado_faltante_bloquea(self, valid_pm_output):
        result = validate_stage_output("dev", str(valid_pm_output))
        assert not result.ok

    def test_dev_completado_muy_corto_bloquea(self, valid_pm_output):
        (valid_pm_output / "DEV_COMPLETADO.md").write_text("# ok\n", encoding="utf-8")
        result = validate_stage_output("dev", str(valid_pm_output))
        assert not result.ok

    def test_dev_completado_sin_archivo_mencionado_bloquea(self, valid_pm_output):
        (valid_pm_output / "DEV_COMPLETADO.md").write_text(
            "# Dev\nSe hicieron cambios\n" * 5, encoding="utf-8"
        )
        result = validate_stage_output("dev", str(valid_pm_output))
        assert not result.ok

    def test_dev_completo_valido_pasa(self, valid_pm_output):
        (valid_pm_output / "DEV_COMPLETADO.md").write_text(
            "# Dev Completado\nModifiqué Batch/Negocio/EjemploDalc.cs\n"
            + "Cambio realizado línea 45\n" * 5,
            encoding="utf-8"
        )
        result = validate_stage_output("dev", str(valid_pm_output))
        assert result.ok


# ─── Tests TESTER ────────────────────────────────────────────────────────────

class TestValidateTester:
    def test_sin_tester_completado_bloquea(self, valid_pm_output):
        result = validate_stage_output("tester", str(valid_pm_output))
        assert not result.ok

    def test_tester_muy_corto_bloquea(self, valid_pm_output):
        (valid_pm_output / "TESTER_COMPLETADO.md").write_text(
            "# QA\nSe revisó\n", encoding="utf-8"
        )
        result = validate_stage_output("tester", str(valid_pm_output))
        assert not result.ok

    def test_sin_veredicto_bloquea(self, valid_pm_output):
        (valid_pm_output / "TESTER_COMPLETADO.md").write_text(
            "# Reporte QA\nSe revisaron los cambios.\n" * 12,
            encoding="utf-8"
        )
        result = validate_stage_output("tester", str(valid_pm_output))
        assert not result.ok

    def test_veredicto_aprobado_pasa(self, valid_pm_output):
        (valid_pm_output / "TESTER_COMPLETADO.md").write_text(
            "# Reporte QA\n## Veredicto: APROBADO\n" + "Caso de prueba: pasa\n" * 22,
            encoding="utf-8"
        )
        result = validate_stage_output("tester", str(valid_pm_output))
        assert result.ok


# ─── Tests de stage desconocido ──────────────────────────────────────────────

class TestUnknownStage:
    def test_stage_desconocido_retorna_ok_con_warning(self, tmp_ticket):
        result = validate_stage_output("unknown_stage", str(tmp_ticket))
        assert result.ok
        assert result.warnings
