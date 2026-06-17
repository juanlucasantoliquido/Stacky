"""Tests A0.1 — Derivador de contrato + juez determinista.

Verifica:
- derivación con cap por complejidad (S→0-1, M→1-2, L/XL→2-4)
- fail-red conserva, pass-baseline descarta (vacuo)
- sin-assert descarta
- n/a cuando ningún chequeo sobrevive el juez
- could-not-baseline no gatea pero se anota
- annotate no inyecta ni gatea
- flag OFF → byte-idéntico (no llama LLM ni subprocess)

Todos los tests son unitarios con mocks de LLM + subprocess.
"""
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_BACKEND = Path(__file__).parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_ticket(title="Agregar login", description="", criteria=""):
    t = MagicMock()
    t.ado_id = 999
    t.project = "mi-proyecto"
    t.stacky_project_name = "mi-proyecto"
    t.title = title
    t.description = description
    t.acceptance_criteria = criteria
    return t


def _make_llm_response(checks: list[dict]) -> str:
    """Simula la respuesta LLM como JSON con una lista de chequeos."""
    import json
    return json.dumps({"checks": checks})


def _sample_check(kind="command", artifact="echo ok", ticket_clause="debe responder ok"):
    return {
        "kind": kind,
        "artifact": artifact,
        "ticket_clause": ticket_clause,
    }


def _enable():
    os.environ["STACKY_ACCEPTANCE_CONTRACT_ENABLED"] = "true"
    import config as _cfg_mod
    importlib.reload(_cfg_mod)


def _disable():
    os.environ["STACKY_ACCEPTANCE_CONTRACT_ENABLED"] = "false"
    import config as _cfg_mod
    importlib.reload(_cfg_mod)


# ── Tests de derivación ───────────────────────────────────────────────────────

def test_flag_off_byte_identico():
    """Con flag OFF, derive() devuelve AcceptanceContract con n_a=True sin llamar LLM."""
    _disable()

    from services.acceptance_contract import derive

    ticket = _make_ticket()
    with patch("services.acceptance_contract._call_llm") as mock_llm:
        result = derive(
            ticket=ticket,
            workspace="/tmp/ws",
            complexity="M",
            runtime="claude_code_cli",
        )

    mock_llm.assert_not_called()
    assert result.n_a is True
    assert result.checks_kept == []

    _enable()


def test_complejidad_S_cap_1():
    """Complejidad S → máx 1 chequeo derivado."""
    _enable()

    llm_checks = [
        _sample_check(artifact="echo 1"),
        _sample_check(artifact="echo 2"),
        _sample_check(artifact="echo 3"),
    ]

    from services.acceptance_contract import derive

    with patch("services.acceptance_contract._call_llm", return_value=_make_llm_response(llm_checks)), \
         patch("services.acceptance_contract._run_check_baseline") as mock_baseline:
        mock_baseline.return_value = ("red", "salida de fallo")
        result = derive(
            ticket=_make_ticket(),
            workspace="/tmp/ws",
            complexity="S",
            runtime="claude_code_cli",
        )

    assert len(result.checks_kept) <= 1


def test_complejidad_M_cap_2():
    """Complejidad M → máx 2 chequeos en el contrato."""
    _enable()

    llm_checks = [_sample_check(artifact=f"echo {i}") for i in range(4)]

    from services.acceptance_contract import derive

    with patch("services.acceptance_contract._call_llm", return_value=_make_llm_response(llm_checks)), \
         patch("services.acceptance_contract._run_check_baseline") as mock_baseline:
        mock_baseline.return_value = ("red", "fail")
        result = derive(
            ticket=_make_ticket(),
            workspace="/tmp/ws",
            complexity="M",
            runtime="claude_code_cli",
        )

    assert len(result.checks_kept) <= 2


def test_complejidad_L_cap_4():
    """Complejidad L → máx 4 chequeos en el contrato."""
    _enable()

    llm_checks = [_sample_check(artifact=f"echo {i}") for i in range(6)]

    from services.acceptance_contract import derive

    with patch("services.acceptance_contract._call_llm", return_value=_make_llm_response(llm_checks)), \
         patch("services.acceptance_contract._run_check_baseline") as mock_baseline:
        mock_baseline.return_value = ("red", "fail")
        result = derive(
            ticket=_make_ticket(),
            workspace="/tmp/ws",
            complexity="L",
            runtime="claude_code_cli",
        )

    assert len(result.checks_kept) <= 4


# ── Tests del juez determinista ───────────────────────────────────────────────

def test_fail_red_baseline_conserva():
    """Chequeo que falla en baseline (red) → se conserva en checks_kept."""
    _enable()

    llm_checks = [_sample_check(artifact="pytest tests/test_login.py")]

    from services.acceptance_contract import derive

    with patch("services.acceptance_contract._call_llm", return_value=_make_llm_response(llm_checks)), \
         patch("services.acceptance_contract._run_check_baseline", return_value=("red", "FAILED")):
        result = derive(ticket=_make_ticket(), workspace="/tmp/ws", complexity="M", runtime="claude_code_cli")

    assert len(result.checks_kept) == 1
    assert result.checks_kept[0]["baseline_status"] == "red"


def test_pass_baseline_descarta_vacuo():
    """Chequeo que pasa en baseline (green) → descartado (no constriñe nada)."""
    _enable()

    llm_checks = [_sample_check(artifact="echo ok")]

    from services.acceptance_contract import derive

    with patch("services.acceptance_contract._call_llm", return_value=_make_llm_response(llm_checks)), \
         patch("services.acceptance_contract._run_check_baseline", return_value=("green", "ok")):
        result = derive(ticket=_make_ticket(), workspace="/tmp/ws", complexity="M", runtime="claude_code_cli")

    assert result.checks_kept == []
    assert result.vacuous_discarded >= 1


def test_sin_assert_descarta():
    """Chequeo de tipo generated_test sin ningún assert en el artefacto → descartado."""
    _enable()

    artifact_code = "def test_foo():\n    pass\n"
    llm_checks = [{"kind": "generated_test", "artifact": artifact_code, "ticket_clause": "login ok"}]

    from services.acceptance_contract import derive

    with patch("services.acceptance_contract._call_llm", return_value=_make_llm_response(llm_checks)), \
         patch("services.acceptance_contract._run_check_baseline", return_value=("red", "no assert")):
        result = derive(ticket=_make_ticket(), workspace="/tmp/ws", complexity="M", runtime="claude_code_cli")

    assert result.checks_kept == []
    assert result.no_assert_discarded >= 1


def test_could_not_baseline_no_gatea():
    """Chequeo que no pudo ejecutarse en baseline → descartado para gate, anotado."""
    _enable()

    llm_checks = [_sample_check(artifact="pytest tests/test_x.py")]

    from services.acceptance_contract import derive

    with patch("services.acceptance_contract._call_llm", return_value=_make_llm_response(llm_checks)), \
         patch("services.acceptance_contract._run_check_baseline", return_value=("could-not-baseline", "timeout")):
        result = derive(ticket=_make_ticket(), workspace="/tmp/ws", complexity="M", runtime="claude_code_cli")

    assert result.checks_kept == []
    assert result.could_not_baseline >= 1


def test_na_cuando_nada_sobrevive():
    """Si ningún chequeo sobrevive el juez → n/a=True."""
    _enable()

    llm_checks = [_sample_check(artifact="echo ok")]

    from services.acceptance_contract import derive

    with patch("services.acceptance_contract._call_llm", return_value=_make_llm_response(llm_checks)), \
         patch("services.acceptance_contract._run_check_baseline", return_value=("green", "ok")):
        result = derive(ticket=_make_ticket(), workspace="/tmp/ws", complexity="M", runtime="claude_code_cli")

    assert result.n_a is True


def test_llm_invalido_na():
    """Si el LLM responde texto inválido → n/a sin error, sin checks."""
    _enable()

    from services.acceptance_contract import derive

    with patch("services.acceptance_contract._call_llm", return_value="texto roto sin json"), \
         patch("services.acceptance_contract._run_check_baseline", return_value=("red", "fail")):
        result = derive(ticket=_make_ticket(), workspace="/tmp/ws", complexity="M", runtime="claude_code_cli")

    assert result.n_a is True


def test_metadata_shape():
    """to_metadata() devuelve dict con claves correctas."""
    _enable()

    from services.acceptance_contract import derive

    with patch("services.acceptance_contract._call_llm", return_value=_make_llm_response([_sample_check()])), \
         patch("services.acceptance_contract._run_check_baseline", return_value=("red", "FAIL")):
        result = derive(ticket=_make_ticket(), workspace="/tmp/ws", complexity="M", runtime="claude_code_cli")

    md = result.to_metadata()
    assert "acceptance_contract" in md
    ac = md["acceptance_contract"]
    assert "n_a" in ac
    assert "checks_kept" in ac
    assert "vacuous_discarded" in ac
    assert "no_assert_discarded" in ac
    assert "could_not_baseline" in ac


def test_annotate_no_inyecta_ni_gatea():
    """En modo annotate, derive() devuelve result pero is_active_gate=False."""
    _enable()
    os.environ["STACKY_ACCEPTANCE_CONTRACT_MODE"] = "annotate"
    importlib.reload(sys.modules["config"])

    from services.acceptance_contract import derive

    with patch("services.acceptance_contract._call_llm", return_value=_make_llm_response([_sample_check()])), \
         patch("services.acceptance_contract._run_check_baseline", return_value=("red", "FAIL")):
        result = derive(ticket=_make_ticket(), workspace="/tmp/ws", complexity="M", runtime="claude_code_cli")

    assert result.is_active_gate is False

    os.environ.pop("STACKY_ACCEPTANCE_CONTRACT_MODE", None)
    importlib.reload(sys.modules["config"])


def test_clamp_model_nunca_opus():
    """_call_llm se invoca con modelo ya clampeado → sin opus/fable."""
    _enable()

    captured_model = []

    def _fake_call_llm(prompt, model):
        captured_model.append(model)
        return _make_llm_response([])

    from services import acceptance_contract as _ac_mod
    with patch.object(_ac_mod, "_call_llm", side_effect=_fake_call_llm):
        from services.acceptance_contract import derive
        derive(ticket=_make_ticket(), workspace="/tmp/ws", complexity="L", runtime="claude_code_cli")

    for m in captured_model:
        low = (m or "").lower()
        assert "opus" not in low
        assert "fable" not in low
