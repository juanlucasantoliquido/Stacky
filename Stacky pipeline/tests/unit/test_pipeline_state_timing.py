"""Tests de timing estructurado e iteraciones en pipeline_state."""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pytest

from pipeline_state import set_ticket_state, record_iteration_end


@pytest.fixture
def empty_state():
    return {"tickets": {}, "last_run": None}


class TestStageTiming:
    def test_en_proceso_escribe_started_at(self, empty_state):
        set_ticket_state(empty_state, "123", "pm_en_proceso")
        entry = empty_state["tickets"]["123"]
        assert entry["estado"] == "pm_en_proceso"
        assert "pm_started_at" in entry
        assert "invoking_pid" in entry

    def test_completado_escribe_ended_at_y_duration(self, empty_state):
        set_ticket_state(empty_state, "123", "pm_en_proceso")
        time.sleep(0.15)
        set_ticket_state(empty_state, "123", "pm_completado")
        entry = empty_state["tickets"]["123"]
        assert "pm_ended_at" in entry
        assert "pm_duration_sec" in entry
        assert entry["pm_duration_sec"] > 0

    def test_error_tambien_registra_fin(self, empty_state):
        set_ticket_state(empty_state, "123", "dev_en_proceso")
        time.sleep(0.15)
        set_ticket_state(empty_state, "123", "error_dev")
        entry = empty_state["tickets"]["123"]
        assert "dev_ended_at" in entry
        assert entry.get("dev_duration_sec") is not None

    def test_timing_independiente_por_stage(self, empty_state):
        set_ticket_state(empty_state, "123", "pm_en_proceso")
        time.sleep(0.15)
        set_ticket_state(empty_state, "123", "pm_completado")
        set_ticket_state(empty_state, "123", "dev_en_proceso")
        time.sleep(0.15)
        set_ticket_state(empty_state, "123", "dev_completado")
        e = empty_state["tickets"]["123"]
        assert e["pm_duration_sec"] > 0
        assert e["dev_duration_sec"] > 0
        assert e["pm_started_at"] != e["dev_started_at"]


class TestIterationTracking:
    def test_iteration_started_se_marca_en_dev(self, empty_state):
        set_ticket_state(empty_state, "123", "dev_en_proceso")
        assert "iteration_started_at" in empty_state["tickets"]["123"]

    def test_record_iteration_end_cierra_ciclo(self, empty_state):
        set_ticket_state(empty_state, "123", "dev_en_proceso")
        time.sleep(0.15)
        iter_num = record_iteration_end(empty_state, "123",
                                        qa_verdict="CON OBSERVACIONES",
                                        findings=["issue1", "issue2"])
        entry = empty_state["tickets"]["123"]
        assert iter_num == 1
        assert entry["iterations"] == 1
        assert entry["rework_count"] == 0
        assert len(entry["iteration_history"]) == 1
        h = entry["iteration_history"][0]
        assert h["iteration"] == 1
        assert h["qa_verdict"] == "CON OBSERVACIONES"
        assert h["findings_count"] == 2
        assert h["duration_sec"] is not None
        assert h["duration_sec"] > 0
        assert "iteration_started_at" not in entry  # se consume

    def test_iteraciones_sucesivas_incrementan(self, empty_state):
        set_ticket_state(empty_state, "123", "dev_en_proceso")
        record_iteration_end(empty_state, "123", "CON OBSERVACIONES", ["x"])
        set_ticket_state(empty_state, "123", "dev_rework_en_proceso")
        record_iteration_end(empty_state, "123", "RECHAZADO", ["y", "z"])
        set_ticket_state(empty_state, "123", "dev_rework_en_proceso")
        record_iteration_end(empty_state, "123", "APROBADO", [])
        entry = empty_state["tickets"]["123"]
        assert entry["iterations"] == 3
        assert entry["rework_count"] == 2
        assert [h["qa_verdict"] for h in entry["iteration_history"]] == [
            "CON OBSERVACIONES", "RECHAZADO", "APROBADO"
        ]

    def test_duration_sec_explicita_tiene_prioridad(self, empty_state):
        set_ticket_state(empty_state, "123", "dev_en_proceso")
        record_iteration_end(empty_state, "123", "APROBADO", [], duration_sec=42.5)
        h = empty_state["tickets"]["123"]["iteration_history"][0]
        assert h["duration_sec"] == 42.5
