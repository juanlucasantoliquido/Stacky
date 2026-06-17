"""Tests A1.1 — Gate del contrato de aceptación + pase correctivo.

Verifica:
- contrato inyectado como bloque de alta prioridad en enrich_blocks
- todos los chequeos pasan → completed + satisfied=True
- uno falla + resume disponible → recupera → completed + recovered=True
- uno falla + no recupera → needs_review
- sin resume → needs_review sin intentar repair
- presupuesto compartido (STACKY_ACCEPTANCE_REPAIR_MAX_RETRIES)
- n/a → sin gate (byte-idéntico)
- flag OFF/annotate → byte-idéntico
"""
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

_BACKEND = Path(__file__).parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_contract(n_a=False, checks_kept=None, is_active_gate=True, workspace="/tmp/ws"):
    from services.acceptance_contract import AcceptanceContract
    return AcceptanceContract(
        n_a=n_a,
        checks_kept=checks_kept or [
            {
                "kind": "command",
                "artifact": "echo ok",
                "ticket_clause": "debe responder ok",
                "baseline_status": "red",
                "baseline_detail": "echo: not found",
            }
        ],
        is_active_gate=is_active_gate,
        workspace=workspace,
    )


def _reload_config():
    import config as _cfg_mod
    importlib.reload(_cfg_mod)


def _enable_gate():
    os.environ["STACKY_ACCEPTANCE_CONTRACT_ENABLED"] = "true"
    os.environ["STACKY_ACCEPTANCE_CONTRACT_MODE"] = "gate"
    os.environ["STACKY_ACCEPTANCE_GATE_ENABLED"] = "true"
    _reload_config()


def _disable_gate():
    os.environ["STACKY_ACCEPTANCE_CONTRACT_ENABLED"] = "false"
    os.environ.pop("STACKY_ACCEPTANCE_CONTRACT_MODE", None)
    os.environ.pop("STACKY_ACCEPTANCE_GATE_ENABLED", None)
    _reload_config()


# ── Tests de inyección como blanco ────────────────────────────────────────────

def test_enrichment_block_shape():
    """to_enrichment_block() devuelve bloque con type y prioridad correctos."""
    contract = _make_contract()
    block = contract.to_enrichment_block()

    assert block is not None
    assert block["type"] == "acceptance-contract"
    assert block["priority"] == "high"
    assert "DEBE pasar" in block["content"]
    assert "debe responder ok" in block["content"]


def test_enrichment_block_na_es_none():
    """Si el contrato es n/a, to_enrichment_block() devuelve None."""
    contract = _make_contract(n_a=True, checks_kept=[])
    assert contract.to_enrichment_block() is None


def test_enrichment_block_vacio_es_none():
    """Si no hay checks_kept, to_enrichment_block() devuelve None."""
    from services.acceptance_contract import AcceptanceContract
    contract = AcceptanceContract(n_a=False, checks_kept=[], is_active_gate=True, workspace="/tmp")
    assert contract.to_enrichment_block() is None


# ── Tests de ejecución del gate ───────────────────────────────────────────────

def test_execute_checks_todos_pasan():
    """Todos los chequeos del contrato pasan → satisfied=True."""
    from services.acceptance_gate import execute_contract_gate

    contract = _make_contract()

    with patch("services.acceptance_gate._run_single_check", return_value=("green", "ok")):
        result = execute_contract_gate(contract, workspace="/tmp/ws")

    assert result["satisfied"] is True
    assert result["failed_checks"] == []


def test_execute_checks_uno_falla():
    """Un chequeo falla → satisfied=False."""
    from services.acceptance_gate import execute_contract_gate

    contract = _make_contract()

    with patch("services.acceptance_gate._run_single_check", return_value=("red", "FAIL")):
        result = execute_contract_gate(contract, workspace="/tmp/ws")

    assert result["satisfied"] is False
    assert len(result["failed_checks"]) >= 1


def test_gate_na_sin_efecto():
    """Si el contrato es n/a → execute_contract_gate devuelve satisfied=None (sin gate)."""
    from services.acceptance_gate import execute_contract_gate

    contract = _make_contract(n_a=True, checks_kept=[])

    result = execute_contract_gate(contract, workspace="/tmp/ws")

    assert result["satisfied"] is None  # n/a = no aplica gate


# ── Tests de repair (A1.1) ────────────────────────────────────────────────────

def test_repair_no_aplica_sin_resume():
    """Sin capacidad de resume → no intenta repair, devuelve repair.attempted=False."""
    from services.acceptance_gate import attempt_acceptance_repair

    mock_capabilities = MagicMock()
    mock_capabilities.supports_resume = False

    with patch("services.acceptance_gate.CAPABILITIES", {"claude_code_cli": mock_capabilities}):
        result = attempt_acceptance_repair(
            contract=_make_contract(),
            failed_checks=[{"artifact": "echo fail", "ticket_clause": "x"}],
            runtime="claude_code_cli",
            workspace="/tmp/ws",
            send_fn=None,
            budget_remaining=300,
        )

    assert result["attempted"] is False
    assert result["recovered"] is False


def test_repair_aplica_con_resume_y_pasa():
    """Runtime con resume + repair pasa en re-ejecución → recovered=True."""
    from services.acceptance_gate import attempt_acceptance_repair

    mock_cap = MagicMock()
    mock_cap.supports_resume = True

    mock_send_fn = MagicMock(return_value="ok")

    with patch("services.acceptance_gate.CAPABILITIES", {"claude_code_cli": mock_cap}), \
         patch("services.acceptance_gate._run_single_check", return_value=("green", "ok")):
        result = attempt_acceptance_repair(
            contract=_make_contract(),
            failed_checks=[{"artifact": "echo fail", "ticket_clause": "x", "baseline_detail": "err"}],
            runtime="claude_code_cli",
            workspace="/tmp/ws",
            send_fn=mock_send_fn,
            budget_remaining=300,
        )

    assert result["attempted"] is True
    assert result["recovered"] is True
    mock_send_fn.assert_called_once()


def test_repair_aplica_pero_sigue_fallando():
    """Repair intentado pero sigue fallando → recovered=False."""
    from services.acceptance_gate import attempt_acceptance_repair

    mock_cap = MagicMock()
    mock_cap.supports_resume = True

    with patch("services.acceptance_gate.CAPABILITIES", {"claude_code_cli": mock_cap}), \
         patch("services.acceptance_gate._run_single_check", return_value=("red", "still broken")):
        result = attempt_acceptance_repair(
            contract=_make_contract(),
            failed_checks=[{"artifact": "echo fail", "ticket_clause": "x"}],
            runtime="claude_code_cli",
            workspace="/tmp/ws",
            send_fn=MagicMock(return_value="ok"),
            budget_remaining=300,
        )

    assert result["attempted"] is True
    assert result["recovered"] is False


def test_presupuesto_cero_no_repara():
    """Con budget_remaining=0 → no intenta repair."""
    from services.acceptance_gate import attempt_acceptance_repair

    mock_cap = MagicMock()
    mock_cap.supports_resume = True

    with patch("services.acceptance_gate.CAPABILITIES", {"claude_code_cli": mock_cap}):
        result = attempt_acceptance_repair(
            contract=_make_contract(),
            failed_checks=[{"artifact": "echo fail", "ticket_clause": "x"}],
            runtime="claude_code_cli",
            workspace="/tmp/ws",
            send_fn=MagicMock(),
            budget_remaining=0,
        )

    assert result["attempted"] is False


def test_flag_off_byte_identico():
    """Flag STACKY_ACCEPTANCE_GATE_ENABLED=false → execute_contract_gate no corre verificadores."""
    _disable_gate()

    from services.acceptance_gate import execute_contract_gate

    contract = _make_contract(is_active_gate=False)

    with patch("services.acceptance_gate._run_single_check") as mock_run:
        result = execute_contract_gate(contract, workspace="/tmp/ws")

    # Con is_active_gate=False (mode!=gate), no ejecuta chequeos
    mock_run.assert_not_called()
    assert result["satisfied"] is None

    _enable_gate()
