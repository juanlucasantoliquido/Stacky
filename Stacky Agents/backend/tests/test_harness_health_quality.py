"""Tests Q2.2 — KPIs de calidad 'aprobado a la primera' en harness_health.

TDD para `_compute_quality_kpis` en `services/harness_health.py`.
Runs sintéticos (aprobados, needs_review, criteria_repair recuperados/no,
con/sin few-shot). Sin DB real.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_exec(status: str, metadata: dict):
    """Crea una row simulada de AgentExecution."""
    return (status, json.dumps(metadata))


def _runs_to_rows(runs: list[tuple[str, dict]]):
    return [_make_exec(s, m) for s, m in runs]


def _mock_session(rows):
    mock_q = MagicMock()
    mock_q.filter.return_value = mock_q
    mock_q.all.return_value = rows
    mock_session = MagicMock()
    mock_session.query.return_value = mock_q
    mock_session.__enter__ = lambda s: mock_session
    mock_session.__exit__ = MagicMock(return_value=False)
    return mock_session


# ---------------------------------------------------------------------------
# _compute_quality_kpis
# ---------------------------------------------------------------------------

def _call_quality_kpis(rows):
    with patch("services.harness_health.session_scope", return_value=_mock_session(rows)):
        from services.harness_health import _compute_quality_kpis
        return _compute_quality_kpis(window_days=14)


def test_all_completed_first_pass():
    """Todos completed, sin criteria_repair → tasa = 1.0."""
    rows = _runs_to_rows([
        ("completed", {}),
        ("completed", {}),
    ])
    result = _call_quality_kpis(rows)
    assert result["tasa_aprobado_a_la_primera"] == 1.0
    assert result["needs_review_por_criterio"] == 0


def test_needs_review_with_gate_counted():
    """needs_review con self_review.mode=gate → needs_review_por_criterio."""
    rows = _runs_to_rows([
        ("completed", {}),
        ("needs_review", {"self_review": {"mode": "gate"}}),
    ])
    result = _call_quality_kpis(rows)
    assert result["needs_review_por_criterio"] == 1
    # 1 de 2 completados a la primera
    assert result["tasa_aprobado_a_la_primera"] == 0.5


def test_criteria_repair_attempted_counted():
    """criteria_repair attempted=True → contado; recovered=True → recovered."""
    rows = _runs_to_rows([
        ("completed", {"criteria_repair": {"attempted": True, "recovered": True}}),
        ("completed", {"criteria_repair": {"attempted": True, "recovered": False}}),
        ("completed", {}),
    ])
    result = _call_quality_kpis(rows)
    assert result["criteria_repair_attempted"] == 2
    assert result["criteria_repair_recovered"] == 1
    assert result["tasa_recuperacion_criteria_repair"] == 0.5
    # El completed con criteria_repair attempted no cuenta como "a la primera"
    # → solo el tercero sin criteria_repair
    assert result["tasa_aprobado_a_la_primera"] == round(1 / 3, 4)


def test_fewshot_corte():
    """Corte con few_shot_count >= 1: solo los runs con few-shot."""
    rows = _runs_to_rows([
        ("completed", {"few_shot_count": 2}),     # con few-shot, primera vez
        ("completed", {"few_shot_count": 0}),     # sin few-shot
        ("needs_review", {"few_shot_count": 1, "criteria_repair": {"attempted": True, "recovered": False}}),
    ])
    result = _call_quality_kpis(rows)
    corte = result["corte_con_fewshot"]
    assert corte["total"] == 2  # 2 runs con few_shot >= 1
    # De esos 2: 1 completed sin repair, 1 needs_review con repair
    assert corte["tasa_primera_vez"] == 0.5


def test_ac_injected_corte():
    """Corte con acceptance_criteria_injected=True."""
    rows = _runs_to_rows([
        ("completed", {"acceptance_criteria_injected": True}),
        ("completed", {"acceptance_criteria_injected": True}),
        ("needs_review", {"acceptance_criteria_injected": True, "self_review": {"mode": "gate"}}),
        ("completed", {"acceptance_criteria_injected": False}),
    ])
    result = _call_quality_kpis(rows)
    corte = result["corte_con_criterios_inyectados"]
    assert corte["total"] == 3  # los 3 con AC=True
    assert corte["tasa_primera_vez"] == round(2 / 3, 4)


def test_flag_off_no_quality_block():
    """Flag OFF → harness_health.to_dict() no incluye bloque quality (o incluye {})."""
    mock_config = MagicMock()
    mock_config.STACKY_RELIABILITY_KPIS_ENABLED = False
    mock_config.STACKY_QUALITY_KPIS_ENABLED = False

    with (
        patch("config.config", mock_config),
        patch("services.harness_health.session_scope", return_value=_mock_session([])),
        patch("services.run_slots.active_count", return_value=0, create=True),
    ):
        from services.harness_health import compute_health
        h = compute_health(window_days=1)

    d = h.to_dict()
    # quality debe existir como clave (aditiva) pero vacío
    assert "quality" in d
    assert d["quality"] == {}


def test_missing_source_degrades_gracefully():
    """Si session_scope lanza → result contiene 'error': '--'."""
    from unittest.mock import patch

    with patch("services.harness_health.session_scope", side_effect=RuntimeError("db down")):
        from services.harness_health import _compute_quality_kpis
        result = _compute_quality_kpis(window_days=14)
    assert result.get("error") == "--"


def test_error_rows_not_counted():
    """Runs en estado 'error' no son terminal para esta métrica si no corresponde."""
    rows = _runs_to_rows([
        ("error", {}),
        ("completed", {}),
    ])
    result = _call_quality_kpis(rows)
    # error SÍ es terminal (está en _TERMINAL)
    assert result["total_terminal"] == 2
    # pero tasa_aprobado incluye solo completed sin repair
    assert result["tasa_aprobado_a_la_primera"] == 0.5
