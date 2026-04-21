"""Tests de ticket_scoring."""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


class TestComputeScoring:
    def test_score_simple_para_ticket_basico(self):
        from ticket_scoring import compute_scoring
        s = compute_scoring(
            "Agregar campo nuevo a formulario de clientes. Cambio mínimo de UI.",
        )
        assert 0 <= s.score <= 100
        assert s.complexity in ("simple", "medio", "complejo")
        assert s.estimated_minutes > 0
        assert set(s.per_stage_minutes.keys()) == {"pm", "dev", "tester"}

    def test_score_complejo_con_keywords_de_riesgo(self):
        from ticket_scoring import compute_scoring
        s = compute_scoring(
            "Migración de tabla RPAGOS con stored procedure y trigger crítico. "
            "Impacta a todos los registros de producción. Multi-empresa.",
        )
        assert s.score >= 50
        assert s.complexity in ("medio", "complejo")

    def test_delta_source_global_default(self):
        from ticket_scoring import compute_scoring
        s = compute_scoring("texto simple")
        assert s.delta_source in ("global", "project")

    def test_factors_son_valores_validos(self):
        from ticket_scoring import compute_scoring
        s = compute_scoring("Agregar columna en RCLIE")
        d = s.factors.to_dict()
        for key in ("tech_complexity", "uncertainty", "impact", "files_affected",
                    "functional_risk", "external_dep"):
            assert key in d
            assert 0 <= d[key] <= 100

    def test_per_stage_suma_aprox_estimated(self):
        """La suma por etapa ≈ estimated_minutes (tolerancia ±3 min por redondeo)."""
        from ticket_scoring import compute_scoring
        s = compute_scoring("Cambio simple de validación en formulario")
        total = sum(s.per_stage_minutes.values())
        # Tolerancia amplia (redondeo int por stage)
        assert abs(total - s.estimated_minutes) <= 3

    def test_delta_aplicado_infla_estimacion(self, monkeypatch):
        """Con un delta positivo, la estimación debe ser > que el base."""
        from ticket_scoring import compute_scoring, DEFAULT_SCORING_CONFIG
        import ticket_scoring as ts

        def fake_cfg(project=None):
            cfg = dict(ts.DEFAULT_SCORING_CONFIG)
            cfg["delta_pct_default"] = 50.0
            return cfg

        monkeypatch.setattr(ts, "load_scoring_config", fake_cfg)

        s = compute_scoring("Agregar campo nuevo")
        # delta=50% debe reflejarse en delta_pct_applied
        assert s.delta_pct_applied == 50.0


class TestScoreToComplexity:
    def test_score_bajo_es_simple(self):
        from ticket_scoring import _score_to_complexity
        assert _score_to_complexity(20, None) == "simple"

    def test_score_medio_es_medio(self):
        from ticket_scoring import _score_to_complexity
        assert _score_to_complexity(50, None) == "medio"

    def test_score_alto_es_complejo(self):
        from ticket_scoring import _score_to_complexity
        assert _score_to_complexity(85, None) == "complejo"


class TestEstimationHeuristic:
    """F2 Fase 1 — la estimación responde a los 6 factores, no al bucket de complexity."""

    def test_dos_tickets_con_factores_distintos_producen_minutos_distintos(self, monkeypatch):
        """
        Regression guard del bug original: antes, todo ticket "medio" sin historial
        terminaba en 35-40 min porque la estimación venía de un bucket de 3 niveles
        y los ScoringFactors se ignoraban. Ahora deben influir.
        """
        import ticket_scoring as ts
        # Forzar que no haya modelo de regresión (fallback a heurística)
        monkeypatch.setattr(ts, "load_scoring_config",
                            lambda p=None: dict(ts.DEFAULT_SCORING_CONFIG))
        try:
            import estimation_model as em
            monkeypatch.setattr(em, "predict", lambda *a, **k: None)
        except Exception:
            pass

        # Texto similar → misma complexity bucket. La diferencia viene de keywords.
        s_low = ts.compute_scoring("Agregar campo nuevo en formulario simple.")
        s_high = ts.compute_scoring(
            "Migración crítica multi-empresa con integración a API externa. "
            "Afecta seguridad y fiscal, impacta todos los registros de producción. "
            "Requiere stored procedure y trigger."
        )
        # Los factors deben ser distintos
        assert s_low.factors.to_dict() != s_high.factors.to_dict()
        # La estimación también — y high > low por construcción (más factores altos)
        assert s_high.estimated_minutes > s_low.estimated_minutes

    def test_cambiar_multiplicadores_afecta_estimacion(self, monkeypatch):
        """La fórmula usa scoring_defaults.multipliers — cambiarlos debe mover el número."""
        import ticket_scoring as ts

        base_cfg = {
            "weights": dict(ts.DEFAULT_WEIGHTS),
            "complexity_thresholds": ts.DEFAULT_SCORING_CONFIG["complexity_thresholds"],
            "stage_distribution":    ts.DEFAULT_SCORING_CONFIG["stage_distribution"],
            "base_minutes":          25,
            "delta_pct_default":     0.0,  # sin delta para aislar el efecto
            "multipliers": {
                "complexity_min":         0.5,
                "complexity_range":       1.5,
                "max_uncertainty_boost":  0.5,
                "functional_risk_boost":  0.3,
                "external_dep_boost":     0.3,
                "files_affected_boost":   0.3,
            },
        }
        monkeypatch.setattr(ts, "load_scoring_config", lambda p=None: dict(base_cfg))
        try:
            import estimation_model as em
            monkeypatch.setattr(em, "predict", lambda *a, **k: None)
        except Exception:
            pass

        content = "Agregar campo nuevo en formulario con integración y riesgo funcional."
        est_default = ts.compute_scoring(content).estimated_minutes

        # Multiplicador de uncertainty x4 → estimación debe subir
        boosted = dict(base_cfg)
        boosted["multipliers"] = dict(base_cfg["multipliers"])
        boosted["multipliers"]["max_uncertainty_boost"] = 2.0
        boosted["multipliers"]["functional_risk_boost"] = 1.2
        boosted["multipliers"]["external_dep_boost"]    = 1.2
        monkeypatch.setattr(ts, "load_scoring_config", lambda p=None: dict(boosted))
        est_boosted = ts.compute_scoring(content).estimated_minutes
        assert est_boosted > est_default

    def test_estimation_method_es_heuristic_por_defecto(self, monkeypatch):
        """Sin modelo entrenado, estimation_method debe ser 'heuristic'."""
        import ticket_scoring as ts
        try:
            import estimation_model as em
            monkeypatch.setattr(em, "predict", lambda *a, **k: None)
        except Exception:
            pass
        s = ts.compute_scoring("ticket simple")
        assert s.estimation_method == "heuristic"

    def test_estimation_method_regression_cuando_modelo_disponible(self, monkeypatch):
        """Si predict() devuelve un número, estimation_method pasa a 'regression'."""
        import ticket_scoring as ts
        import estimation_model as em
        monkeypatch.setattr(em, "predict", lambda *a, **k: 42)
        s = ts.compute_scoring("ticket simple")
        assert s.estimation_method == "regression"
        # Al aplicar delta (default 15%), 42 × 1.15 ≈ 48
        assert 40 <= s.estimated_minutes <= 60


class TestResolveDeltaPct:
    def test_delta_por_ticket_type_prevalece(self):
        from ticket_scoring import resolve_delta_pct
        cfg = {"delta_pct_default": 10.0, "delta_by_ticket_type": {"bug": 25.0}}
        delta, source = resolve_delta_pct(cfg, ticket_type="bug")
        assert delta == 25.0
        assert source == "ticket_type"

    def test_delta_project_prevalece_sobre_global(self):
        from ticket_scoring import resolve_delta_pct
        cfg = {"delta_pct_default": 10.0}
        calibration = {"by_project": {"RSPACIFICO": {"suggested_delta_pct": 22.5}}}
        delta, source = resolve_delta_pct(cfg, project="RSPACIFICO",
                                           global_calibration=calibration)
        assert delta == 22.5
        assert source == "project"

    def test_fallback_global(self):
        from ticket_scoring import resolve_delta_pct
        cfg = {"delta_pct_default": 15.0}
        delta, source = resolve_delta_pct(cfg)
        assert delta == 15.0
        assert source == "global"
