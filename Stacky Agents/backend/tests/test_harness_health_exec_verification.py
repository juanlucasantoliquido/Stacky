"""Tests E2.2 — KPIs de verificación ejecutable en harness_health.

Usa runs sintéticos (sin DB real).
"""
from __future__ import annotations

import json
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
    passed: bool | None = True,
    hard_failed: list | None = None,
    fake_green: list | None = None,
    repair_attempted: bool = False,
    repair_recovered: bool = False,
    ran: list | None = None,
    duration_ms: int = 500,
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

    ev_data = {
        "mode": "gate",
        "ran": ran or ["PyCompile"],
        "hard_failed": hard_failed or [],
        "soft": [],
        "passed": passed,
        "skipped_reason": None,
        "duration_ms": duration_ms,
        "fake_green": fake_green or [],
    }
    if repair_attempted:
        ev_data["repair"] = {
            "attempted": True,
            "recovered": repair_recovered,
            "failed_before": ["PyCompile"],
        }

    ex.metadata_dict = {
        "runtime": "claude_code_cli",
        "exec_verification": ev_data,
    }
    return ex


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_verde_a_la_primera_sin_repair():
    """Runs que pasan sin repair → tasa_verde_a_la_primera = 1.0."""
    rows = [
        _make_execution(project="proj_a", passed=True, ran=["PyCompile"]),
        _make_execution(project="proj_a", passed=True, ran=["JsonYamlParser"]),
    ]

    with patch("services.harness_health.session_scope") as mock_scope:
        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_session.query.return_value.options.return_value.filter.return_value.all.return_value = rows
        mock_scope.return_value = mock_session

        from services.harness_health import _compute_exec_verification_kpis
        result = _compute_exec_verification_kpis(14)

    assert result["verificados"] == 2
    assert result["tasa_verde_a_la_primera"] == 1.0
    assert result["entregables_rotos_atrapados"] == 0


def test_roto_atrapado():
    """Run con hard_failed → entregables_rotos_atrapados incrementado."""
    rows = [
        _make_execution(
            project="proj_b",
            passed=False,
            hard_failed=[{"name": "PyCompile", "detail": "SyntaxError"}],
            ran=["PyCompile"],
        ),
        _make_execution(project="proj_b", passed=True, ran=["JsonYamlParser"]),
    ]

    with patch("services.harness_health.session_scope") as mock_scope:
        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_session.query.return_value.options.return_value.filter.return_value.all.return_value = rows
        mock_scope.return_value = mock_session

        from services.harness_health import _compute_exec_verification_kpis
        result = _compute_exec_verification_kpis(14)

    assert result["entregables_rotos_atrapados"] == 1
    assert result["verificados"] == 2


def test_verde_falso_atrapado():
    """Run con fake_green no vacío → verde_falso_atrapado incrementado."""
    rows = [
        _make_execution(
            project="proj_c",
            passed=True,
            fake_green=["test_foo.py: tests sin assert"],
            ran=["FakeGreenGuard", "PyCompile"],
        ),
    ]

    with patch("services.harness_health.session_scope") as mock_scope:
        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_session.query.return_value.options.return_value.filter.return_value.all.return_value = rows
        mock_scope.return_value = mock_session

        from services.harness_health import _compute_exec_verification_kpis
        result = _compute_exec_verification_kpis(14)

    assert result["verde_falso_atrapado"] == 1


def test_tasa_recuperacion_repair():
    """Repair attempted+recovered vs attempted → tasa correcta."""
    rows = [
        _make_execution(
            project="proj_d",
            passed=True,
            ran=["PyCompile"],
            repair_attempted=True,
            repair_recovered=True,
        ),
        _make_execution(
            project="proj_d",
            passed=False,
            ran=["PyCompile"],
            hard_failed=[{"name": "PyCompile", "detail": "still broken"}],
            repair_attempted=True,
            repair_recovered=False,
        ),
    ]

    with patch("services.harness_health.session_scope") as mock_scope:
        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_session.query.return_value.options.return_value.filter.return_value.all.return_value = rows
        mock_scope.return_value = mock_session

        from services.harness_health import _compute_exec_verification_kpis
        result = _compute_exec_verification_kpis(14)

    assert result["exec_repair_attempted"] == 2
    assert result["exec_repair_recovered"] == 1
    assert result["tasa_recuperacion_exec_repair"] == 0.5


def test_sin_exec_verification_degrada():
    """Runs sin metadata exec_verification → verificados=0, no error."""
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

    with patch("services.harness_health.session_scope") as mock_scope:
        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_session.query.return_value.options.return_value.filter.return_value.all.return_value = rows
        mock_scope.return_value = mock_session

        from services.harness_health import _compute_exec_verification_kpis
        result = _compute_exec_verification_kpis(14)

    assert result["verificados"] == 0
    assert result["tasa_verde_a_la_primera"] == "--"


def test_costo_medio_verificacion_ms():
    """duration_ms se promedia correctamente."""
    rows = [
        _make_execution(project="proj_e", passed=True, ran=["PyCompile"], duration_ms=200),
        _make_execution(project="proj_e", passed=True, ran=["PyCompile"], duration_ms=800),
    ]

    with patch("services.harness_health.session_scope") as mock_scope:
        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_session.query.return_value.options.return_value.filter.return_value.all.return_value = rows
        mock_scope.return_value = mock_session

        from services.harness_health import _compute_exec_verification_kpis
        result = _compute_exec_verification_kpis(14)

    assert result["costo_medio_verificacion_ms"] == 500.0


def test_flag_off_sin_bloque_en_compute_health():
    """Flag OFF → exec_verification_kpis en to_dict() es {} vacío."""
    from services.harness_health import HarnessHealth
    # Sin asignar _exec_verification → debe ser {}
    h = HarnessHealth(window_days=7)
    d = h.to_dict()
    assert d["exec_verification_kpis"] == {}


def test_by_project_breakdown():
    """KPIs desglosan por proyecto correctamente."""
    rows = [
        _make_execution(project="proj_x", passed=True, ran=["PyCompile"]),
        _make_execution(project="proj_y", passed=False, hard_failed=[{"name": "TscCheck", "detail": "err"}], ran=["TscCheck"]),
        _make_execution(project="proj_x", passed=True, ran=["JsonYamlParser"]),
    ]

    with patch("services.harness_health.session_scope") as mock_scope:
        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_session.query.return_value.options.return_value.filter.return_value.all.return_value = rows
        mock_scope.return_value = mock_session

        from services.harness_health import _compute_exec_verification_kpis
        result = _compute_exec_verification_kpis(14)

    assert "by_project" in result
    assert "proj_x" in result["by_project"]
    assert "proj_y" in result["by_project"]
    assert result["by_project"]["proj_x"]["verificados"] == 2
    assert result["by_project"]["proj_y"]["verificados"] == 1
    assert result["by_project"]["proj_y"]["entregables_rotos_atrapados"] == 1
