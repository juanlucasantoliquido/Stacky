"""
test_pipeline.py — Unit tests para el pipeline de Stacky.

Cubre:
  - pipeline_state: load/save/set/mark_error/priority
  - ticket_detector: placeholders, _has_inc_file, get_processable_tickets
  - dashboard_server: lógica de selección de etapa en full-pipeline
  - api_run_pipeline: determinación de first_stage por estado

Ejecutar:
    cd Tools/Stacky
    python -m pytest tests/ -v
"""

import json
import os
import sys
import tempfile
import pytest

# Agrega el directorio raíz del módulo al path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline_state import (
    load_state, save_state, set_ticket_state, mark_error,
    set_ticket_priority, get_ticket_priority, get_ticket_state,
    ESTADOS_VALIDOS,
)
from ticket_detector import (
    _has_placeholders, _has_inc_file, _dev_completed,
    get_processable_tickets, PLACEHOLDER,
)


# ─── Helpers ─────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_state(tmp_path):
    """State path temporal por test."""
    path = tmp_path / "state.json"
    return str(path)


@pytest.fixture
def ticket_folder(tmp_path):
    """Carpeta de ticket con archivos mínimos."""
    folder = tmp_path / "asignada" / "0012345"
    folder.mkdir(parents=True)
    (folder / "INC-0012345.md").write_text("# Ticket\nDescripción del ticket")
    return folder


def _make_pm_files(folder, with_placeholder=True):
    """Crea los 6 archivos PM en una carpeta."""
    content = f"# Archivo\n{PLACEHOLDER}" if with_placeholder else "# Archivo\nContenido real"
    for fname in ["INCIDENTE.md", "ANALISIS_TECNICO.md", "ARQUITECTURA_SOLUCION.md",
                  "TAREAS_DESARROLLO.md", "QUERIES_ANALISIS.sql", "NOTAS_IMPLEMENTACION.md"]:
        (folder / fname).write_text(content, encoding="utf-8")


# ─── Tests: pipeline_state ───────────────────────────────────────────────────

class TestLoadSaveState:
    def test_load_creates_empty_state_if_no_file(self, tmp_state):
        state = load_state(tmp_state)
        assert state == {"tickets": {}, "last_run": None}

    def test_save_and_reload(self, tmp_state):
        state = {"tickets": {"0001": {"estado": "pm_completado"}}, "last_run": None}
        save_state(tmp_state, state)
        loaded = load_state(tmp_state)
        assert loaded["tickets"]["0001"]["estado"] == "pm_completado"

    def test_save_updates_last_run_timestamp(self, tmp_state):
        state = {"tickets": {}, "last_run": None}
        save_state(tmp_state, state)
        loaded = load_state(tmp_state)
        assert loaded["last_run"] is not None
        assert "T" in loaded["last_run"]  # formato ISO

    def test_load_invalid_json_raises(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("{ invalid json", encoding="utf-8")
        with pytest.raises(Exception):
            load_state(str(bad))


class TestSetTicketState:
    def test_creates_entry_if_missing(self, tmp_state):
        state = load_state(tmp_state)
        set_ticket_state(state, "0001", "pm_en_proceso")
        assert state["tickets"]["0001"]["estado"] == "pm_en_proceso"

    def test_stores_at_timestamp(self, tmp_state):
        state = load_state(tmp_state)
        set_ticket_state(state, "0001", "pm_completado")
        assert "pm_completado_at" in state["tickets"]["0001"]

    def test_kwargs_stored(self, tmp_state):
        state = load_state(tmp_state)
        set_ticket_state(state, "0001", "pm_en_proceso", folder="/ruta/ticket", titulo="Bug X")
        assert state["tickets"]["0001"]["folder"] == "/ruta/ticket"
        assert state["tickets"]["0001"]["titulo"] == "Bug X"

    def test_all_valid_states_accepted(self, tmp_state):
        state = load_state(tmp_state)
        for est in ESTADOS_VALIDOS:
            set_ticket_state(state, "0001", est)
            assert state["tickets"]["0001"]["estado"] == est


class TestMarkError:
    def test_sets_error_estado(self, tmp_state):
        state = load_state(tmp_state)
        mark_error(state, "0001", "pm", "Falló la invocación")
        assert state["tickets"]["0001"]["estado"] == "error_pm"

    def test_stores_error_reason(self, tmp_state):
        state = load_state(tmp_state)
        mark_error(state, "0001", "dev", "Carpeta no encontrada")
        assert state["tickets"]["0001"]["error"] == "Carpeta no encontrada"

    def test_increments_intentos(self, tmp_state):
        state = load_state(tmp_state)
        mark_error(state, "0001", "pm", "err1")
        mark_error(state, "0001", "pm", "err2")
        assert state["tickets"]["0001"]["intentos_pm"] == 2

    def test_mark_error_dev(self, tmp_state):
        state = load_state(tmp_state)
        mark_error(state, "0001", "dev", "timeout")
        assert state["tickets"]["0001"]["estado"] == "error_dev"

    def test_mark_error_tester(self, tmp_state):
        state = load_state(tmp_state)
        mark_error(state, "0001", "tester", "QA falló")
        assert state["tickets"]["0001"]["estado"] == "error_tester"


class TestPriority:
    def test_default_priority_is_9999(self, tmp_state):
        state = load_state(tmp_state)
        assert get_ticket_priority(state, "9999") == 9999

    def test_set_and_get_priority(self, tmp_state):
        state = load_state(tmp_state)
        set_ticket_priority(state, "0001", 1)
        assert get_ticket_priority(state, "0001") == 1

    def test_priority_creates_entry(self, tmp_state):
        state = load_state(tmp_state)
        set_ticket_priority(state, "new", 5)
        assert "new" in state["tickets"]


class TestGetTicketState:
    def test_missing_ticket_returns_pendiente(self, tmp_state):
        state = load_state(tmp_state)
        assert get_ticket_state(state, "inexistente") == "pendiente_pm"

    def test_existing_ticket_returns_estado(self, tmp_state):
        state = {"tickets": {"0001": {"estado": "dev_completado"}}, "last_run": None}
        assert get_ticket_state(state, "0001") == "dev_completado"


# ─── Tests: ticket_detector ──────────────────────────────────────────────────

class TestHasPlaceholders:
    def test_detects_placeholder_text(self, ticket_folder):
        _make_pm_files(ticket_folder, with_placeholder=True)
        assert _has_placeholders(str(ticket_folder)) is True

    def test_no_placeholder_returns_false(self, ticket_folder):
        _make_pm_files(ticket_folder, with_placeholder=False)
        assert _has_placeholders(str(ticket_folder)) is False

    def test_missing_pm_files_returns_false(self, ticket_folder):
        # Carpeta sin archivos PM → no hay placeholders
        assert _has_placeholders(str(ticket_folder)) is False

    def test_partial_placeholder_detected(self, ticket_folder):
        # Solo un archivo con placeholder — debe detectar True
        (ticket_folder / "ANALISIS_TECNICO.md").write_text("Contenido real")
        (ticket_folder / "TAREAS_DESARROLLO.md").write_text(f"# Tareas\n{PLACEHOLDER}")
        assert _has_placeholders(str(ticket_folder)) is True

    def test_alternate_placeholder_text(self, ticket_folder):
        (ticket_folder / "INCIDENTE.md").write_text("A completar por PM en este campo", encoding="utf-8")
        assert _has_placeholders(str(ticket_folder)) is True


class TestHasIncFile:
    def test_present(self, ticket_folder):
        assert _has_inc_file(str(ticket_folder), "0012345") is True

    def test_missing(self, ticket_folder):
        os.remove(ticket_folder / "INC-0012345.md")
        assert _has_inc_file(str(ticket_folder), "0012345") is False

    def test_wrong_id(self, ticket_folder):
        assert _has_inc_file(str(ticket_folder), "9999999") is False


class TestDevCompleted:
    def test_false_if_no_file(self, ticket_folder):
        assert _dev_completed(str(ticket_folder)) is False

    def test_true_if_file_exists(self, ticket_folder):
        (ticket_folder / "DEV_COMPLETADO.md").write_text("# Dev completado")
        assert _dev_completed(str(ticket_folder)) is True


class TestGetProcessableTickets:
    def _make_ticket(self, base, estado, ticket_id, inc=True, placeholder=True):
        folder = base / estado / ticket_id
        folder.mkdir(parents=True, exist_ok=True)
        if inc:
            (folder / f"INC-{ticket_id}.md").write_text(f"# INC {ticket_id}")
        _make_pm_files(folder, with_placeholder=placeholder)
        return folder

    def test_returns_ticket_in_asignada_with_placeholder(self, tmp_path):
        self._make_ticket(tmp_path, "asignada", "0001")
        state = {"tickets": {}, "last_run": None}
        result = get_processable_tickets(str(tmp_path), state)
        assert any(t["ticket_id"] == "0001" for t in result)

    def test_ignores_ticket_without_inc_file(self, tmp_path):
        self._make_ticket(tmp_path, "asignada", "0002", inc=False)
        state = {"tickets": {}, "last_run": None}
        result = get_processable_tickets(str(tmp_path), state)
        assert not any(t["ticket_id"] == "0002" for t in result)

    def test_ignores_tickets_not_in_asignada(self, tmp_path):
        self._make_ticket(tmp_path, "confirmada", "0003")
        self._make_ticket(tmp_path, "nueva", "0004")
        state = {"tickets": {}, "last_run": None}
        result = get_processable_tickets(str(tmp_path), state)
        assert result == []

    def test_ignores_completed_ticket(self, tmp_path):
        self._make_ticket(tmp_path, "asignada", "0005", placeholder=False)
        state = {"tickets": {"0005": {"estado": "completado"}}, "last_run": None}
        result = get_processable_tickets(str(tmp_path), state)
        assert not any(t["ticket_id"] == "0005" for t in result)

    def test_ignores_en_proceso_ticket(self, tmp_path):
        self._make_ticket(tmp_path, "asignada", "0006")
        state = {"tickets": {"0006": {"estado": "pm_en_proceso"}}, "last_run": None}
        result = get_processable_tickets(str(tmp_path), state)
        assert not any(t["ticket_id"] == "0006" for t in result)

    def test_force_reprocess_includes_completado(self, tmp_path):
        self._make_ticket(tmp_path, "asignada", "0007", placeholder=False)
        state = {"tickets": {"0007": {"estado": "completado"}}, "last_run": None}
        result = get_processable_tickets(str(tmp_path), state, force_reprocess=["0007"])
        assert any(t["ticket_id"] == "0007" for t in result)

    def test_returns_empty_if_base_not_exists(self, tmp_path):
        result = get_processable_tickets(str(tmp_path / "noexiste"), {})
        assert result == []


# ─── Tests: lógica de first_stage en Full Pipeline ───────────────────────────

class TestFullPipelineFirstStage:
    """
    Verifica la lógica de determinación de first_stage implementada en
    api_run_pipeline (extracción pura de la lógica, sin HTTP).
    """

    def _first_stage(self, estado):
        """Replica exacta de la lógica en api_run_pipeline."""
        if estado in ("pendiente_pm", "error_pm"):
            return "pm"
        elif estado in ("pm_completado", "error_dev"):
            return "dev"
        elif estado in ("dev_completado", "error_tester"):
            return "tester"
        else:
            return "pm"

    def test_pendiente_pm_starts_pm(self):
        assert self._first_stage("pendiente_pm") == "pm"

    def test_error_pm_restarts_from_pm(self):
        assert self._first_stage("error_pm") == "pm"

    def test_pm_completado_starts_dev(self):
        assert self._first_stage("pm_completado") == "dev"

    def test_error_dev_restarts_from_dev(self):
        assert self._first_stage("error_dev") == "dev"

    def test_dev_completado_starts_tester(self):
        assert self._first_stage("dev_completado") == "tester"

    def test_error_tester_restarts_from_tester(self):
        assert self._first_stage("error_tester") == "tester"

    def test_unknown_state_defaults_to_pm(self):
        assert self._first_stage("estado_inventado") == "pm"

    def test_never_returns_invalid_stage(self):
        for est in ESTADOS_VALIDOS:
            stage = self._first_stage(est)
            assert stage in ("pm", "dev", "tester")


# ─── Tests: integración pipeline_state + ticket_detector ─────────────────────

class TestIntegration:
    def test_full_lifecycle(self, tmp_path, tmp_state):
        """Simula el ciclo completo de estados de un ticket."""
        state = load_state(tmp_state)

        # PM inicia
        set_ticket_state(state, "0099", "pm_en_proceso")
        assert get_ticket_state(state, "0099") == "pm_en_proceso"

        # PM completa
        set_ticket_state(state, "0099", "pm_completado")
        assert get_ticket_state(state, "0099") == "pm_completado"

        # Dev inicia
        set_ticket_state(state, "0099", "dev_en_proceso")

        # Dev falla — debe quedar error_dev con contador
        mark_error(state, "0099", "dev", "Timeout VS Code")
        assert state["tickets"]["0099"]["estado"] == "error_dev"
        assert state["tickets"]["0099"]["intentos_dev"] == 1

        # Dev reintenta — desde error_dev vuelve a dev_en_proceso
        set_ticket_state(state, "0099", "dev_en_proceso")
        set_ticket_state(state, "0099", "dev_completado")

        # Tester
        set_ticket_state(state, "0099", "tester_en_proceso")
        set_ticket_state(state, "0099", "completado")

        # Persist y recargar
        save_state(tmp_state, state)
        loaded = load_state(tmp_state)
        assert get_ticket_state(loaded, "0099") == "completado"

    def test_reset_clears_to_pendiente(self, tmp_state):
        """Simula el reset que hace el dashboard."""
        state = {"tickets": {"0001": {
            "estado": "pm_completado",
            "auto_advance": True,
            "pm_inicio_at": "2026-01-01T10:00:00",
            "last_invoke": {"stage": "pm", "ok": True},
        }}, "last_run": None}

        # Reset — solo quedar con identity fields + estado
        entry = state["tickets"]["0001"]
        keep_keys = {"asignado", "estado_base", "titulo", "folder", "priority"}
        clean = {k: entry[k] for k in keep_keys if k in entry}
        clean["estado"] = "pendiente_pm"
        state["tickets"]["0001"] = clean

        assert state["tickets"]["0001"]["estado"] == "pendiente_pm"
        assert "auto_advance" not in state["tickets"]["0001"]
        assert "pm_inicio_at" not in state["tickets"]["0001"]
        assert "last_invoke" not in state["tickets"]["0001"]
