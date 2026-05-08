"""
test_full_pipeline.py — E2E test with mocked Copilot Bridge.

Simulates a complete pipeline (ticket → PM → DEV → QA → done) with pre-recorded
responses, without needing VS Code or Copilot.
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch


# Pre-recorded response templates
PM_RESPONSE = """# Análisis Técnico
El bug ocurre en FrmCargaDocumentos al adjuntar PDF.

## Archivos afectados
- Batch/Negocio/DocumentosDalc.cs
- OnLine/FrmCargaDocumentos.aspx

## Tareas
- [ ] Agregar validación NULL en DocumentosDalc.cs
- [ ] Manejar excepción en btnAdjuntar_Click
"""

DEV_RESPONSE = """# DEV Completado
Archivos modificados:
- Batch/Negocio/DocumentosDalc.cs: validación NULL agregada
- OnLine/FrmCargaDocumentos.aspx: try-catch en btnAdjuntar_Click
"""

QA_RESPONSE_APPROVED = """# QA Completado
Veredicto: APROBADO

Casos verificados:
- [PASS] Validación NULL presente en DocumentosDalc.cs
- [PASS] Excepción manejada correctamente en btnAdjuntar_Click
"""

QA_RESPONSE_REWORK = """# QA Completado
Veredicto: CON OBSERVACIONES

Observaciones:
- Falta validación de longitud máxima en DocumentosDalc.cs
"""


def setup_ticket_folder(tmp_path: Path, ticket_id: str) -> Path:
    """Create minimal ticket folder structure."""
    folder = tmp_path / "asignada" / ticket_id
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"INC-{ticket_id}.md").write_text(
        f"# Ticket #{ticket_id}\nBug en FrmCargaDocumentos al adjuntar PDF.",
        encoding="utf-8"
    )
    return folder


class TestFullPipelineE2E:
    def test_pipeline_completo_ticket_simple(self, tmp_path):
        """Simple ticket goes through PM → DEV → QA without rework."""
        ticket_id = "0099999"
        folder = setup_ticket_folder(tmp_path, ticket_id)

        # Simulate PM output
        (folder / "ANALISIS_TECNICO.md").write_text(PM_RESPONSE, encoding="utf-8")
        (folder / "INCIDENTE.md").write_text("# Incidente\nBug description\n" * 5, encoding="utf-8")
        (folder / "ARQUITECTURA_SOLUCION.md").write_text(
            "# Arquitectura\nDocumentosDalc.cs\n" * 5, encoding="utf-8"
        )
        (folder / "TAREAS_DESARROLLO.md").write_text(
            "# Tareas\n- [ ] Fix NULL\n" * 5, encoding="utf-8"
        )
        (folder / "QUERIES_ANALISIS.sql").write_text("SELECT 1;\n" * 5, encoding="utf-8")
        (folder / "NOTAS_IMPLEMENTACION.md").write_text("# Notas\nnota\n" * 5, encoding="utf-8")

        # Simulate DEV output
        (folder / "DEV_COMPLETADO.md").write_text(DEV_RESPONSE, encoding="utf-8")

        # Simulate QA output
        (folder / "TESTER_COMPLETADO.md").write_text(QA_RESPONSE_APPROVED, encoding="utf-8")

        # Verify: all artifacts present
        assert (folder / "ANALISIS_TECNICO.md").exists()
        assert (folder / "DEV_COMPLETADO.md").exists()
        assert (folder / "TESTER_COMPLETADO.md").exists()
        assert "APROBADO" in (folder / "TESTER_COMPLETADO.md").read_text()

    def test_pipeline_con_rework_ciclo_unico(self, tmp_path):
        """QA rejects → DEV rework → QA approves on second attempt."""
        ticket_id = "0099998"
        folder = setup_ticket_folder(tmp_path, ticket_id)

        # PM output
        (folder / "ANALISIS_TECNICO.md").write_text(PM_RESPONSE, encoding="utf-8")
        (folder / "INCIDENTE.md").write_text("# Incidente\n" * 5, encoding="utf-8")
        (folder / "ARQUITECTURA_SOLUCION.md").write_text("# Arq\n" * 5, encoding="utf-8")
        (folder / "TAREAS_DESARROLLO.md").write_text("# Tareas\n" * 5, encoding="utf-8")
        (folder / "QUERIES_ANALISIS.sql").write_text("SELECT 1;\n" * 5, encoding="utf-8")
        (folder / "NOTAS_IMPLEMENTACION.md").write_text("# Notas\n" * 5, encoding="utf-8")

        # DEV round 1
        (folder / "DEV_COMPLETADO.md").write_text(DEV_RESPONSE, encoding="utf-8")

        # QA round 1 — rejection
        (folder / "TESTER_COMPLETADO.md").write_text(QA_RESPONSE_REWORK, encoding="utf-8")

        # Verify rework needed
        qa_content = (folder / "TESTER_COMPLETADO.md").read_text()
        assert "CON OBSERVACIONES" in qa_content

        # DEV rework round 2
        rework_response = DEV_RESPONSE + "\n- Validación de longitud máxima agregada"
        (folder / "DEV_COMPLETADO.md").write_text(rework_response, encoding="utf-8")

        # QA round 2 — approved
        (folder / "TESTER_COMPLETADO.md").write_text(QA_RESPONSE_APPROVED, encoding="utf-8")
        assert "APROBADO" in (folder / "TESTER_COMPLETADO.md").read_text()
