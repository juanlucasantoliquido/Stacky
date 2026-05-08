"""Tests del field `duration_sec` en CorrectionMemory.add_cycle."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pytest

from correction_memory import CorrectionMemory


def test_add_cycle_persiste_duration(tmp_path):
    cm = CorrectionMemory(str(tmp_path))
    cm.add_cycle(1, ["issue A"], qa_verdict="CON OBSERVACIONES", duration_sec=182.3)

    cm2 = CorrectionMemory(str(tmp_path))
    cycles = cm2._data["cycles"]
    assert len(cycles) == 1
    assert cycles[0]["duration_sec"] == pytest.approx(182.3)
    assert cycles[0]["qa_verdict"]   == "CON OBSERVACIONES"


def test_add_cycle_sin_duration_es_valido(tmp_path):
    cm = CorrectionMemory(str(tmp_path))
    cm.add_cycle(1, ["x"], qa_verdict="RECHAZADO")
    assert cm._data["cycles"][0]["duration_sec"] is None


def test_multiples_ciclos_con_diferentes_verdicts(tmp_path):
    cm = CorrectionMemory(str(tmp_path))
    cm.add_cycle(1, ["a"], qa_verdict="CON OBSERVACIONES", duration_sec=100)
    cm.add_cycle(2, ["b"], qa_verdict="RECHAZADO",         duration_sec=200)
    cm.add_cycle(3, [],    qa_verdict="APROBADO",          duration_sec=150)
    verdicts = [c["qa_verdict"] for c in cm._data["cycles"]]
    assert verdicts == ["CON OBSERVACIONES", "RECHAZADO", "APROBADO"]
