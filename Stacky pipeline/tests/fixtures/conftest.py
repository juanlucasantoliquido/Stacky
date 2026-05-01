import pytest
from pathlib import Path
from pipeline_state import save_state

FIXTURES_DIR = Path(__file__).parent


@pytest.fixture
def tmp_ticket(tmp_path):
    """Carpeta de ticket vacía con INC file mínimo."""
    folder = tmp_path / "asignada" / "0099999"
    folder.mkdir(parents=True)
    (folder / "INC-0099999.md").write_text("# Ticket de prueba\nDescripción del error.")
    return folder


@pytest.fixture
def valid_pm_output(tmp_ticket):
    """Ticket con output PM completo y válido (sin placeholders)."""
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
    """Ticket con output PM que tiene placeholders sin reemplazar."""
    (valid_pm_output / "ANALISIS_TECNICO.md").write_text(
        "# Análisis\n_A completar por PM_\nResto del contenido...", encoding="utf-8"
    )
    return valid_pm_output


@pytest.fixture
def mock_ado_work_item():
    """Work item ADO estándar para tests."""
    return {
        "id": 99999,
        "fields": {
            "System.Title": "Bug en FrmCargaDocumentos al adjuntar PDF",
            "System.State": "Active",
            "System.AssignedTo": {"displayName": "Juan Luca Santolíquido"},
            "System.Description": "<p>Error al adjuntar archivos PDF en el formulario de carga.</p>",
            "System.Tags": "bug; batch; documentos",
            "Microsoft.VSTS.Common.Priority": 2,
        }
    }
