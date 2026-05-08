"""Tests de estimation_model (F2 Fase 2 — regresión lineal)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


@pytest.fixture(autouse=True)
def _isolated_paths(tmp_path, monkeypatch):
    """Aísla estimation_store y estimation_model a un tmp_path."""
    import estimation_store as es
    import estimation_model as em

    data_dir = tmp_path / "data"
    monkeypatch.setattr(es, "_DATA_DIR", data_dir)
    monkeypatch.setattr(es, "_STORE_PATH", data_dir / "estimations.json")
    monkeypatch.setattr(em, "_DATA_DIR", data_dir)
    monkeypatch.setattr(em, "_MODEL_PATH", data_dir / "estimation_model.json")
    monkeypatch.setattr(em, "_STORE_PATH", data_dir / "estimations.json")
    yield data_dir


def _seed_entries(n: int, *, noise: float = 0.0) -> None:
    """
    Carga N entries cerradas en el store aislado. El target ``actual_minutes``
    es una función lineal determinística de los factores, así la regresión
    puede recuperar los coeficientes con error bajo.
    """
    import estimation_store as es
    from ticket_scoring import TicketScoring, ScoringFactors

    # True coefs (aprox): est ≈ 0.2*tech + 0.3*unc + 0.1*impact + 0.2*files + 0.3*fr + 0.2*ext + 0.5*sim + 5
    true_c = [0.2, 0.3, 0.1, 0.2, 0.3, 0.2, 0.5]
    intercept = 5.0

    for i in range(n):
        # Variabilidad determinística (no random, para reproducibilidad)
        f = ScoringFactors(
            tech_complexity=(i * 7) % 100,
            uncertainty=(i * 11) % 100,
            impact=(i * 13) % 100,
            files_affected=(i * 17) % 100,
            functional_risk=(i * 19) % 100,
            external_dep=(i * 23) % 100,
        )
        sim = (i * 3) % 10
        row = [f.tech_complexity, f.uncertainty, f.impact,
               f.files_affected, f.functional_risk, f.external_dep, sim]
        actual = intercept + sum(c * v for c, v in zip(true_c, row))
        # Añadir ruido opcional determinístico
        actual += ((i % 5) - 2) * noise

        scoring = TicketScoring(
            score=50, complexity="medio", factors=f,
            modules_detected=[], similar_tickets_count=sim,
            estimated_minutes=int(max(1, round(actual * 0.9))),  # estimación levemente baja
            delta_pct_applied=15.0, delta_source="global",
            per_stage_minutes={"pm": 5, "dev": 10, "tester": 5},
        )
        tid = f"T-{i:03d}"
        es.record_estimate(tid, scoring, project="TEST")
        es.record_actual(tid, actual_minutes=actual)


class TestTrainModel:
    def test_menos_de_min_samples_retorna_none(self):
        import estimation_model as em
        _seed_entries(10)  # por debajo del umbral (20)
        assert em.train_model() is None

    def test_con_20_samples_entrena_y_persiste(self):
        import estimation_model as em
        _seed_entries(22)
        stats = em.train_model()
        assert stats is not None
        assert stats.n_samples >= 20
        # RMSE debe ser bajo (datos sintéticos sin ruido)
        assert stats.rmse < 5.0
        assert len(stats.coefficients) == len(em.FEATURE_ORDER)

        # Persistencia
        loaded = em.load_model()
        assert loaded is not None
        assert loaded["n_samples"] == stats.n_samples


class TestPredict:
    def test_sin_modelo_devuelve_none(self):
        import estimation_model as em
        # Sin entrenar previamente
        from ticket_scoring import ScoringFactors
        f = ScoringFactors(tech_complexity=50, uncertainty=50, impact=50,
                           files_affected=50, functional_risk=50, external_dep=50)
        assert em.predict(f, 2) is None

    def test_con_modelo_entrenado_devuelve_entero_positivo(self):
        import estimation_model as em
        from ticket_scoring import ScoringFactors
        _seed_entries(25)
        em.train_model()
        f = ScoringFactors(tech_complexity=70, uncertainty=40, impact=60,
                           files_affected=50, functional_risk=30, external_dep=20)
        pred = em.predict(f, 3)
        assert pred is not None
        assert isinstance(pred, int)
        assert pred > 0

    def test_modelo_incompatible_devuelve_none(self):
        """Si el modelo persistido tiene features distintas al orden actual, ignorar."""
        import estimation_model as em
        from ticket_scoring import ScoringFactors
        _seed_entries(25)
        em.train_model()
        # Corrompemos el modelo guardado
        data = json.loads(em._MODEL_PATH.read_text(encoding="utf-8"))
        data["features"] = ["otro_order"] + data["features"][1:]
        em._MODEL_PATH.write_text(json.dumps(data), encoding="utf-8")

        f = ScoringFactors(tech_complexity=70, uncertainty=40, impact=60,
                           files_affected=50, functional_risk=30, external_dep=20)
        assert em.predict(f, 3) is None


class TestMaybeRetrain:
    def test_dispara_cada_5_cierres(self, monkeypatch):
        import estimation_model as em
        called = {"n": 0}

        def fake_train(*a, **k):
            called["n"] += 1
            return em.ModelStats(
                coefficients=[0.0] * len(em.FEATURE_ORDER),
                intercept=0.0, trained_at="x", n_samples=20, rmse=0.0,
                features=list(em.FEATURE_ORDER),
            )
        monkeypatch.setattr(em, "train_model", fake_train)

        # Below threshold → no dispara
        assert em.maybe_retrain_after_close(10) is False
        # Threshold exacto pero no múltiplo de 5 → no dispara si el umbral es 20
        # (20 % 5 == 0, sí dispara). 21 % 5 != 0 → no.
        assert em.maybe_retrain_after_close(20) is True  # 20%5==0
        assert em.maybe_retrain_after_close(21) is False
        assert em.maybe_retrain_after_close(25) is True
        assert called["n"] == 2


class TestLinAlg:
    """Smoke tests del álgebra lineal en Python puro."""

    def test_inversa_identidad(self):
        import estimation_model as em
        I = [[1.0, 0.0], [0.0, 1.0]]
        inv = em._invert(I)
        assert inv == I

    def test_inversa_simple(self):
        import estimation_model as em
        # A = [[2,0],[0,4]] → A^-1 = [[0.5,0],[0,0.25]]
        A = [[2.0, 0.0], [0.0, 4.0]]
        inv = em._invert(A)
        assert abs(inv[0][0] - 0.5) < 1e-9
        assert abs(inv[1][1] - 0.25) < 1e-9

    def test_fit_recupera_relacion_lineal_simple(self):
        import estimation_model as em
        # y = 2*x1 + 1*x2 + 3  (2 features, ambas con varianza)
        X = [[1.0, 2.0], [2.0, 3.0], [3.0, 1.0], [4.0, 5.0], [5.0, 4.0],
             [6.0, 6.0], [7.0, 3.0], [8.0, 7.0]]
        y = [2*r[0] + 1*r[1] + 3.0 for r in X]
        coeffs, intercept = em._fit_least_squares(X, y, ridge=1e-6)
        # Ridge 1e-6 introduce un sesgo ínfimo; tolerancia amplia.
        assert abs(coeffs[0] - 2.0) < 0.05
        assert abs(coeffs[1] - 1.0) < 0.05
        assert abs(intercept - 3.0) < 0.2
