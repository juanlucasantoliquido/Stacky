"""Tests de estimation_store."""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path, monkeypatch):
    import estimation_store as es
    monkeypatch.setattr(es, "_DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(es, "_STORE_PATH", tmp_path / "data" / "estimations.json")
    yield


def _make_scoring(**overrides):
    from ticket_scoring import TicketScoring, ScoringFactors
    base = TicketScoring(
        score=50,
        complexity="medio",
        factors=ScoringFactors(tech_complexity=55, uncertainty=30, impact=40,
                               files_affected=25, functional_risk=35, external_dep=15),
        modules_detected=["batch_negocio"],
        similar_tickets_count=2,
        estimated_minutes=40,
        delta_pct_applied=15.0,
        delta_source="global",
        per_stage_minutes={"pm": 10, "dev": 20, "tester": 10},
    )
    for k, v in overrides.items():
        setattr(base, k, v)
    return base


class TestRecordEstimate:
    def test_crea_entry_nueva(self):
        import estimation_store as es
        entry = es.record_estimate("T-001", _make_scoring(), project="RSPACIFICO")
        assert entry["ticket_id"] == "T-001"
        assert entry["score"] == 50
        assert entry["estimated_minutes"] == 40
        assert entry["per_stage"]["pm"]["estimated"] == 10

    def test_upsert_preserva_actuals(self):
        import estimation_store as es
        es.record_estimate("T-002", _make_scoring(), project="RSPACIFICO")
        es.record_actual("T-002", actual_minutes=60,
                         per_stage_actual={"pm": 15, "dev": 30, "tester": 15})
        # Re-record estimate con nuevo score → no debe perder actuals
        new = es.record_estimate("T-002", _make_scoring(score=70))
        assert new["score"] == 70
        assert new["actual_minutes"] == 60
        assert new["per_stage"]["pm"]["actual"] == 15


class TestRecordActual:
    def test_actualiza_deviation_pct(self):
        import estimation_store as es
        es.record_estimate("T-003", _make_scoring())
        entry = es.record_actual("T-003", actual_minutes=50)
        # est=40, act=50 → +25%
        assert entry["deviation_pct"] == 25.0

    def test_retorna_none_si_no_existe_entry(self):
        import estimation_store as es
        result = es.record_actual("NO-EXISTE", actual_minutes=100)
        assert result is None

    def test_first_attempt_approved_persiste(self):
        import estimation_store as es
        es.record_estimate("T-004", _make_scoring())
        entry = es.record_actual("T-004", first_attempt_approved=True, actual_minutes=42)
        assert entry["first_attempt_approved"] is True


class TestComputeAccuracy:
    def test_vacio_retorna_zero_samples(self):
        import estimation_store as es
        acc = es.compute_accuracy(days=30)
        assert acc["samples"] == 0

    def test_calcula_mean_abs_deviation(self):
        import estimation_store as es
        # 3 tickets: +25% / -10% / +40%  → mean abs = 25
        for tid, actual in [("A", 50), ("B", 36), ("C", 56)]:
            es.record_estimate(tid, _make_scoring())
            es.record_actual(tid, actual_minutes=actual)
        acc = es.compute_accuracy(days=30)
        assert acc["samples"] == 3
        assert acc["mean_abs_deviation_pct"] == pytest.approx(25.0, abs=0.5)


class TestSuggestDelta:
    def test_pocos_samples_devuelve_none(self):
        import estimation_store as es
        es.record_estimate("X", _make_scoring())
        es.record_actual("X", actual_minutes=50)
        sug = es.suggest_delta_calibration(min_samples=5)
        assert sug["suggested_delta_pct"] is None
        assert "Insuficientes" in sug["reason"]

    def test_suficientes_samples_retorna_mean_signed(self):
        import estimation_store as es
        # Crear 5 tickets con deviation +20% cada uno
        for i in range(5):
            tid = f"CAL-{i}"
            es.record_estimate(tid, _make_scoring())
            es.record_actual(tid, actual_minutes=48)  # 48 sobre 40 → +20%
        sug = es.suggest_delta_calibration(min_samples=5)
        assert sug["suggested_delta_pct"] == pytest.approx(20.0, abs=0.5)


class TestCalibrationPersistence:
    def test_apply_calibration_guarda_delta_por_proyecto(self):
        import estimation_store as es
        result = es.apply_calibration(project_deltas={"RSPACIFICO": 18.4})
        assert result["by_project"]["RSPACIFICO"]["suggested_delta_pct"] == 18.4
        # Persistencia
        loaded = es.load_calibration()
        assert loaded["by_project"]["RSPACIFICO"]["suggested_delta_pct"] == 18.4
