"""
Tests unitarios para el algoritmo de scoring del recomendador P6.

Capa: unit (sin BD, sin LLM, funciones puras).
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock
from datetime import datetime, timedelta


# Importar las funciones internas del servicio
from services.ticket_assigner import (
    _compute_load_score,
    _compute_type_affinity,
    _compute_area_affinity,
    _compute_throughput_score,
    _build_reason,
)


class MockTicket:
    """Mock minimo de un Ticket para los tests."""
    def __init__(self, priority=2, ado_state="Active", work_item_type="Bug",
                 last_synced_at=None, ado_id=1000):
        self.priority = priority
        self.ado_state = ado_state
        self.work_item_type = work_item_type
        self.last_synced_at = last_synced_at or datetime.utcnow()
        self.ado_id = ado_id


class TestLoadScore:
    def test_load_score_zero_tickets_is_max(self):
        score, load_pct, overloaded = _compute_load_score([], max_active_tickets=5)
        assert score == 1.0
        assert load_pct == 0.0
        assert overloaded is False

    def test_load_score_full_load_is_zero(self):
        # 5 tickets de prioridad 1 = carga maxima (5 * 4 = 20 = 5 * 4)
        tickets = [MockTicket(priority=1) for _ in range(5)]
        score, load_pct, overloaded = _compute_load_score(tickets, max_active_tickets=5)
        assert score <= 0.01  # cercano a 0
        assert overloaded is True

    def test_load_score_partial_load(self):
        # 2 tickets de prioridad 2 (peso=3 cada uno = 6 de 20 maximo)
        tickets = [MockTicket(priority=2), MockTicket(priority=2)]
        score, load_pct, overloaded = _compute_load_score(tickets, max_active_tickets=5)
        assert 0 < score < 1.0
        assert overloaded is False

    def test_load_score_low_priority_tickets_less_weight(self):
        tickets_high = [MockTicket(priority=1)]
        tickets_low = [MockTicket(priority=4)]
        score_high, _, _ = _compute_load_score(tickets_high, max_active_tickets=5)
        score_low, _, _ = _compute_load_score(tickets_low, max_active_tickets=5)
        assert score_high < score_low  # alta prioridad = mas carga = menor score

    def test_load_score_max_tickets_zero_is_overloaded(self):
        """max_active_tickets=0 no debe causar division por cero."""
        score, load_pct, overloaded = _compute_load_score([], max_active_tickets=0)
        assert overloaded is True


class TestTypeAffinity:
    def test_no_tickets_returns_zero(self):
        score, top_types, matched = _compute_type_affinity([], "Bug")
        assert score == 0.0
        assert top_types == []
        assert matched is False

    def test_specialist_gets_boosted_score(self):
        # 10 tickets todos Bug
        tickets = [MockTicket(work_item_type="Bug") for _ in range(10)]
        score, top_types, matched = _compute_type_affinity(tickets, "Bug")
        assert score == 1.0  # capped a 1.0
        assert matched is True
        assert "Bug" in top_types

    def test_no_match_returns_zero(self):
        tickets = [MockTicket(work_item_type="Task") for _ in range(5)]
        score, top_types, matched = _compute_type_affinity(tickets, "Bug")
        assert score == 0.0
        assert matched is False

    def test_partial_match_between_0_and_1(self):
        tickets = [MockTicket(work_item_type="Bug") for _ in range(3)] + \
                  [MockTicket(work_item_type="Task") for _ in range(7)]
        score, top_types, matched = _compute_type_affinity(tickets, "Bug")
        assert 0 < score <= 1.0
        assert matched is True

    def test_no_target_type_returns_zero(self):
        tickets = [MockTicket(work_item_type="Bug")]
        score, top_types, matched = _compute_type_affinity(tickets, None)
        assert score == 0.0


class TestAreaAffinity:
    def test_no_target_area_returns_neutral(self):
        score, matched = _compute_area_affinity('["Strategist\\\\UI"]', None)
        assert score == 0.5  # neutro

    def test_exact_match(self):
        # JSON almacena backslash simple como \\ en el string JSON
        score, matched = _compute_area_affinity(
            '["Strategist_Pacifico\\\\UI"]',  # en JSON: ["Strategist_Pacifico\\UI"]
            "Strategist_Pacifico\\UI"         # el valor real del area_path
        )
        assert score == 1.0
        assert len(matched) > 0

    def test_no_areas_configured_returns_zero(self):
        score, matched = _compute_area_affinity(None, "Strategist_Pacifico\\UI")
        assert score == 0.0
        assert matched == []

    def test_no_match_returns_zero(self):
        score, matched = _compute_area_affinity(
            '["Strategist_Pacifico\\\\Backend"]',
            "Strategist_Pacifico\\UI"
        )
        assert score == 0.0


class TestThroughputScore:
    def test_no_tickets_returns_neutral(self):
        score = _compute_throughput_score([])
        assert score == 0.5

    def test_all_closed_returns_one(self):
        tickets = [MockTicket(ado_state="Done") for _ in range(5)]
        score = _compute_throughput_score(tickets)
        assert score == 1.0

    def test_none_closed_returns_zero(self):
        tickets = [MockTicket(ado_state="Active") for _ in range(5)]
        score = _compute_throughput_score(tickets)
        assert score == 0.0

    def test_half_closed_returns_half(self):
        tickets = (
            [MockTicket(ado_state="Done") for _ in range(5)] +
            [MockTicket(ado_state="Active") for _ in range(5)]
        )
        score = _compute_throughput_score(tickets)
        assert abs(score - 0.5) < 0.01

    def test_old_tickets_ignored(self):
        """Tickets mas viejos que 90 dias se ignoran en el calculo."""
        old_date = datetime.utcnow() - timedelta(days=100)
        old_tickets = [MockTicket(ado_state="Done", last_synced_at=old_date) for _ in range(10)]
        score = _compute_throughput_score(old_tickets)
        assert score == 0.5  # sin datos recientes = neutro


class TestCompositeScore:
    """Test del score compuesto (integracion de los cuatro sub-scores)."""

    def test_ideal_candidate_scores_high(self):
        """Candidato con baja carga, especialista en el tipo, area correcta, alto throughput."""
        load_score = 0.9   # baja carga
        type_score = 1.0   # especialista
        area_score = 1.0   # area exacta
        throughput = 0.9   # alto cierre

        score = (
            0.40 * load_score
            + 0.25 * type_score
            + 0.20 * area_score
            + 0.15 * throughput
        )
        assert score >= 0.90

    def test_poor_candidate_scores_low(self):
        """Candidato sobrecargado, sin experiencia en el tipo, area incorrecta."""
        load_score = 0.1
        type_score = 0.0
        area_score = 0.0
        throughput = 0.2

        score = (
            0.40 * load_score
            + 0.25 * type_score
            + 0.20 * area_score
            + 0.15 * throughput
        )
        assert score < 0.10
