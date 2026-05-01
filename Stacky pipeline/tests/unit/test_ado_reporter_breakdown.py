"""Tests del comentario único con breakdown de timing + iteraciones."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pytest

from ado_reporter import (
    ADOReporter,
    _format_duration,
    build_iteration_table,
    build_stage_breakdown,
)


def test_format_duration_seg_min_hora():
    assert _format_duration(0)      == "0s"
    assert _format_duration(45)     == "45s"
    assert _format_duration(125)    == "2m 05s"
    assert _format_duration(3_605)  == "1h 00m 05s"
    assert _format_duration(None)   == "N/A"


def test_stage_breakdown_ordena_y_totaliza():
    state = {
        "pm_started_at":    "2026-04-18T10:00:00",
        "pm_ended_at":      "2026-04-18T10:02:14",
        "pm_duration_sec":  134.0,
        "dev_started_at":   "2026-04-18T10:02:20",
        "dev_ended_at":     "2026-04-18T10:05:30",
        "dev_duration_sec": 190.0,
        "tester_started_at":   "2026-04-18T10:05:35",
        "tester_ended_at":     "2026-04-18T10:07:05",
        "tester_duration_sec": 90.0,
    }
    table, total = build_stage_breakdown(state)
    assert "| PM |"          in table
    assert "| DEV |"         in table
    assert "| QA / Tester |" in table
    assert "2m 14s"          in table
    assert total == pytest.approx(134.0 + 190.0 + 90.0)


def test_stage_breakdown_omite_stages_sin_datos():
    state = {"pm_duration_sec": 60.0, "pm_started_at": "2026-04-18T10:00:00"}
    table, _ = build_stage_breakdown(state)
    assert "| PM |"   in table
    assert "| DEV |"  not in table


def test_iteration_table_vacia_cuando_primer_intento_exitoso():
    txt = build_iteration_table({})
    assert "primera iteración" in txt.lower()


def test_iteration_table_incluye_cada_ciclo():
    state = {
        "iteration_history": [
            {"iteration": 1, "started_at": "2026-04-18T10:00:00",
             "ended_at": "2026-04-18T10:05:00", "duration_sec": 300,
             "qa_verdict": "CON OBSERVACIONES", "findings_count": 3},
            {"iteration": 2, "started_at": "2026-04-18T10:06:00",
             "ended_at": "2026-04-18T10:12:00", "duration_sec": 360,
             "qa_verdict": "RECHAZADO", "findings_count": 5},
            {"iteration": 3, "started_at": "2026-04-18T10:15:00",
             "ended_at": "2026-04-18T10:20:00", "duration_sec": 300,
             "qa_verdict": "APROBADO", "findings_count": 0},
        ]
    }
    table = build_iteration_table(state)
    assert "CON OBSERVACIONES" in table
    assert "RECHAZADO"         in table
    assert "APROBADO"          in table
    assert "5m 00s"            in table
    assert "6m 00s"            in table


class _FakeAdoClient:
    def __init__(self):
        self.comments: list[tuple[int, str]] = []
        self.updates:  list[tuple[int, dict]] = []

    def add_comment(self, wi_id, comment):
        self.comments.append((wi_id, comment))

    def update_work_item(self, wi_id, fields):
        self.updates.append((wi_id, fields))


def test_report_pipeline_complete_genera_un_solo_comentario():
    fake = _FakeAdoClient()
    reporter = ADOReporter(ado_client=fake, state_provider=None)

    ticket_state = {
        "pm_duration_sec":     120.0,
        "pm_started_at":       "2026-04-18T10:00:00",
        "pm_ended_at":         "2026-04-18T10:02:00",
        "dev_duration_sec":    300.0,
        "dev_started_at":      "2026-04-18T10:02:05",
        "dev_ended_at":        "2026-04-18T10:07:05",
        "tester_duration_sec": 60.0,
        "tester_started_at":   "2026-04-18T10:07:10",
        "tester_ended_at":     "2026-04-18T10:08:10",
        "iterations":          2,
        "cases_count":         5,
        "iteration_history": [
            {"iteration": 1, "duration_sec": 280, "qa_verdict": "CON OBSERVACIONES",
             "findings_count": 2, "started_at": "2026-04-18T10:02:05",
             "ended_at": "2026-04-18T10:06:45"},
            {"iteration": 2, "duration_sec": 300, "qa_verdict": "APROBADO",
             "findings_count": 0, "started_at": "2026-04-18T10:07:00",
             "ended_at": "2026-04-18T10:12:00"},
        ],
    }

    reporter.report_pipeline_complete(27698, ticket_state)

    assert len(fake.comments) == 1
    _, body = fake.comments[0]
    assert "QA APROBADO" in body
    assert "Total de iteraciones" in body
    assert "Desglose de tiempos por etapa" in body
    assert "Historial de iteraciones" in body
    assert "| PM |" in body
    assert "| DEV |" in body
    assert "| QA / Tester |" in body
    assert "CON OBSERVACIONES" in body
    # ADO state actualizado una vez a Resolved
    assert len(fake.updates) == 1
    assert fake.updates[0][1]["System.State"] == "Resolved"


def test_report_pipeline_complete_sin_historia_es_robusto():
    fake = _FakeAdoClient()
    reporter = ADOReporter(ado_client=fake, state_provider=None)
    reporter.report_pipeline_complete(100, ticket_state={"cases_count": 2})
    assert len(fake.comments) == 1
