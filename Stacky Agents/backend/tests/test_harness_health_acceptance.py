"""Tests A2.2 — KPIs del contrato de aceptación en harness_health.

Verifica:
- tasa_contrato_derivable (no-n/a / total)
- tasa_cumplido_a_la_primera (satisfied sin repair / con contrato)
- tasa_recuperacion (repair.recovered/attempted)
- calidad_del_examen (1 - vacuos_descartados/generados)
- intentos_de_gameo_atrapados (mutated_checks no vacío)
- fuente ausente → degrada
- flag OFF → sin bloque (acceptance_contract_kpis={})
"""
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta

import pytest

_BACKEND = Path(__file__).parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_execution(
    project: str = "proj_a",
    n_a: bool = False,
    satisfied: bool | None = True,
    repair_attempted: bool = False,
    repair_recovered: bool = False,
    vacuous_discarded: int = 0,
    no_assert_discarded: int = 0,
    mutated_checks: list | None = None,
    checks_kept: int = 2,
    status: str = "completed",
):
    ex = MagicMock()
    ex.status = status
    ex.ticket_id = 1
    ex.agent_type = "developer"
    ex.contract_result = None
    ex.started_at = datetime.utcnow() - timedelta(days=1)

    ticket_mock = MagicMock()
    ticket_mock.project = project
    ex.ticket = ticket_mock

    ac_data: dict = {
        "n_a": n_a,
        "checks_kept": [{"kind": "command", "artifact": f"cmd {i}"} for i in range(checks_kept)] if not n_a else [],
        "vacuous_discarded": vacuous_discarded,
        "no_assert_discarded": no_assert_discarded,
        "complexity": "M",
    }

    if satisfied is not None:
        ac_data["result"] = {
            "satisfied": satisfied,
            "failed_checks": [] if satisfied else [{"artifact": "cmd 0"}],
        }
        if repair_attempted:
            ac_data["result"]["repair"] = {
                "attempted": True,
                "recovered": repair_recovered,
            }

    if mutated_checks is not None:
        ac_data["integrity"] = {
            "mutated_checks": mutated_checks,
            "restored": len(mutated_checks) > 0,
        }

    ex.metadata_dict = {
        "runtime": "claude_code_cli",
        "acceptance_contract": ac_data,
    }
    return ex


def _mock_session(rows):
    from unittest.mock import MagicMock
    mock_scope = MagicMock()
    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_session.query.return_value.options.return_value.filter.return_value.all.return_value = rows
    mock_scope.return_value = mock_session
    return mock_scope


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_tasa_contrato_derivable():
    """2 de 3 runs tienen contrato (n_a=False) → tasa_contrato_derivable = 2/3."""
    rows = [
        _make_execution(n_a=False, checks_kept=2),
        _make_execution(n_a=False, checks_kept=1),
        _make_execution(n_a=True),
    ]

    with patch("services.harness_health.session_scope", _mock_session(rows)):
        from services.harness_health import _compute_acceptance_contract_kpis
        result = _compute_acceptance_contract_kpis(14)

    assert result["total"] == 3
    assert result["con_contrato"] == 2
    assert result["tasa_contrato_derivable"] == round(2 / 3, 4)


def test_tasa_cumplido_a_la_primera():
    """Run satisfecho sin repair → cumplido_a_la_primera."""
    rows = [
        _make_execution(n_a=False, satisfied=True, repair_attempted=False),
        _make_execution(n_a=False, satisfied=True, repair_attempted=True, repair_recovered=True),
        _make_execution(n_a=False, satisfied=False, repair_attempted=True, repair_recovered=False),
    ]

    with patch("services.harness_health.session_scope", _mock_session(rows)):
        from services.harness_health import _compute_acceptance_contract_kpis
        result = _compute_acceptance_contract_kpis(14)

    # Solo el primero cumplió sin repair
    assert result["cumplido_a_la_primera"] == 1
    assert result["tasa_cumplido_a_la_primera"] == round(1 / 3, 4)  # 1 de 3 con contrato


def test_tasa_recuperacion():
    """repair.attempted=2, repair.recovered=1 → tasa_recuperacion=0.5."""
    rows = [
        _make_execution(n_a=False, satisfied=True, repair_attempted=True, repair_recovered=True),
        _make_execution(n_a=False, satisfied=False, repair_attempted=True, repair_recovered=False),
    ]

    with patch("services.harness_health.session_scope", _mock_session(rows)):
        from services.harness_health import _compute_acceptance_contract_kpis
        result = _compute_acceptance_contract_kpis(14)

    assert result["repair_attempted"] == 2
    assert result["repair_recovered"] == 1
    assert result["tasa_recuperacion"] == 0.5


def test_calidad_del_examen():
    """vacuous_discarded=2, checks_kept=2 → calidad = 1 - 2/4 = 0.5."""
    rows = [
        _make_execution(n_a=False, checks_kept=2, vacuous_discarded=2),
    ]

    with patch("services.harness_health.session_scope", _mock_session(rows)):
        from services.harness_health import _compute_acceptance_contract_kpis
        result = _compute_acceptance_contract_kpis(14)

    # checks_kept=2, vacuos=2 → generados=4, calidad = 1 - 2/4 = 0.5
    assert result["calidad_del_examen"] == 0.5


def test_gameo_atrapado():
    """mutated_checks no vacío → intentos_de_gameo_atrapados incrementado."""
    rows = [
        _make_execution(n_a=False, mutated_checks=["test_login.py"]),
        _make_execution(n_a=False, mutated_checks=[]),
    ]

    with patch("services.harness_health.session_scope", _mock_session(rows)):
        from services.harness_health import _compute_acceptance_contract_kpis
        result = _compute_acceptance_contract_kpis(14)

    assert result["intentos_de_gameo_atrapados"] == 1


def test_sin_acceptance_contract_degrada():
    """Runs sin metadata acceptance_contract → total=0, degrada con gracia."""
    rows = [
        MagicMock(
            status="completed",
            ticket_id=1,
            agent_type="developer",
            contract_result=None,
            started_at=datetime.utcnow() - timedelta(days=1),
            ticket=MagicMock(project="proj_none"),
            metadata_dict={"runtime": "claude_code_cli"},
        ),
    ]

    with patch("services.harness_health.session_scope", _mock_session(rows)):
        from services.harness_health import _compute_acceptance_contract_kpis
        result = _compute_acceptance_contract_kpis(14)

    assert result["total"] == 0
    assert result["con_contrato"] == 0
    assert result["tasa_contrato_derivable"] == "--"


def test_flag_off_sin_bloque():
    """Flag OFF → acceptance_contract_kpis={} en to_dict()."""
    from services.harness_health import HarnessHealth
    h = HarnessHealth(window_days=7)
    d = h.to_dict()
    assert d["acceptance_contract_kpis"] == {}
