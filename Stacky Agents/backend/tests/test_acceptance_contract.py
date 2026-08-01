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

import contextlib
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


# ── A0.1 — el derivador tiene CALL SITE de producción (Plan 32) ──────────────
#
# Gap detectado en el censo del 2026-08-01: `derive()` estaba completa y testeada,
# pero fuera de tests SOLO existían LECTORES de la clave que debía producir
# (harness/post_run.py:240, context_enrichment.py:1623, harness_health.py:400).
# Nadie escribía metadata["acceptance_contract"] antes del run ⇒ n_a=True siempre
# ⇒ gate, inyección de contexto y KPIs quedaban los tres INERTES.
# Estos tests prueban el CABLEADO, no la construcción.


@contextlib.contextmanager
def _fake_session_scope():
    """Sesión de mentira para los tests unitarios de A0.1 (este archivo no toca DB)."""

    class _FakeSession:
        def get(self, _model, _pk):
            return object()  # el ticket; el derivador está mockeado igual

    yield _FakeSession()


def test_a01_guarda_to_metadata_produce_la_clave_que_lee_post_run():
    """GUARDA anti-falso-verde: fija el contrato de datos productor↔lector.
    Si esto falla, los tests de abajo no prueban nada útil porque estarían
    comparando contra una forma que ningún lector consume."""
    from services.acceptance_contract import AcceptanceContract

    md = AcceptanceContract(n_a=False, checks_kept=[{"kind": "command"}]).to_metadata()

    assert "acceptance_contract" in md
    # Las dos claves EXACTAS que lee harness/post_run.py:244-245
    assert md["acceptance_contract"].get("n_a") is False
    assert md["acceptance_contract"].get("checks_kept") == [{"kind": "command"}]


def test_a01_agent_runner_expone_el_cableado():
    """El seam pre-run vive en agent_runner (punto único de los 3 runtimes)."""
    import agent_runner

    assert callable(getattr(agent_runner, "_derive_acceptance_contract_pre_run", None)), (
        "A0.1 sin cablear: agent_runner no deriva el contrato antes del run."
    )
    assert callable(getattr(agent_runner, "_persist_acceptance_contract", None))


def test_a01_flag_off_no_deriva_ni_escribe_la_clave(monkeypatch):
    """Flag OFF → byte-idéntico: no llama al derivador y no escribe metadata."""
    import agent_runner
    import config as cfg
    from services import acceptance_contract as ac

    llamadas = []
    monkeypatch.setattr(ac, "derive", lambda **kw: llamadas.append(kw))
    monkeypatch.setattr(cfg.config, "STACKY_ACCEPTANCE_CONTRACT_ENABLED", False, raising=False)

    patch_md = agent_runner._derive_acceptance_contract_pre_run(
        ticket_id=1, runtime="codex_cli", project_name=None, fingerprint_complexity="M"
    )

    assert patch_md is None
    assert llamadas == [], "con la flag OFF no se debe llamar al derivador (costo LLM)"


def test_a01_flag_on_deriva_contra_el_baseline_y_devuelve_el_patch(monkeypatch):
    """Flag ON → deriva y devuelve el patch con la forma que lee post_run."""
    import agent_runner
    import config as cfg
    from services import acceptance_contract as ac

    recibido = {}

    class _FakeContract:
        def to_metadata(self):
            return {"acceptance_contract": {"n_a": False, "checks_kept": [{"kind": "command"}]}}

    def _fake_derive(**kw):
        recibido.update(kw)
        return _FakeContract()

    monkeypatch.setattr(ac, "derive", _fake_derive)
    monkeypatch.setattr(cfg.config, "STACKY_ACCEPTANCE_CONTRACT_ENABLED", True, raising=False)
    # Unitario puro (como el resto de este archivo): sin DB real. Sin esto el
    # helper cae en su propio fail-open por "no such table: tickets" y el test
    # pasaría por la razón equivocada.
    monkeypatch.setattr(agent_runner, "session_scope", _fake_session_scope)
    monkeypatch.setattr(agent_runner, "resolve_project_context", lambda **kw: None)

    patch_md = agent_runner._derive_acceptance_contract_pre_run(
        ticket_id=1, runtime="codex_cli", project_name=None, fingerprint_complexity="L"
    )

    assert patch_md == {"acceptance_contract": {"n_a": False, "checks_kept": [{"kind": "command"}]}}
    # El juez de baseline necesita saber la complejidad y el runtime reales
    assert recibido.get("complexity") == "L"
    assert recibido.get("runtime") == "codex_cli"


def test_a01_el_derivador_falla_abierto_y_no_tumba_el_run(monkeypatch):
    """Si el derivador explota, el run continúa (fail-open), como el gate G0.1."""
    import agent_runner
    import config as cfg
    from services import acceptance_contract as ac

    def _boom(**kw):
        raise RuntimeError("toolchain ausente")

    monkeypatch.setattr(ac, "derive", _boom)
    monkeypatch.setattr(cfg.config, "STACKY_ACCEPTANCE_CONTRACT_ENABLED", True, raising=False)

    assert agent_runner._derive_acceptance_contract_pre_run(
        ticket_id=1, runtime="codex_cli", project_name=None, fingerprint_complexity="M"
    ) is None


def test_a01_run_agent_deriva_antes_de_lanzar_el_runtime(monkeypatch):
    """El gate REAL de A0.1: run_agent deriva ANTES de que el agente trabaje.
    El orden importa — el juez de baseline exige el workspace SIN tocar."""
    import agent_runner
    import config as cfg

    orden = []

    monkeypatch.setattr(cfg.config, "STACKY_ACCEPTANCE_CONTRACT_ENABLED", True, raising=False)
    monkeypatch.setattr(
        agent_runner, "_derive_acceptance_contract_pre_run",
        lambda **kw: (orden.append("derive"), {"acceptance_contract": {"n_a": True, "checks_kept": []}})[1],
    )
    monkeypatch.setattr(
        agent_runner, "_start_cli_runtime", lambda **kw: (orden.append("run"), 4242)[1]
    )
    monkeypatch.setattr(
        agent_runner, "_persist_acceptance_contract", lambda *a, **k: orden.append("persist")
    )
    # El preflight G0.1 no debe interferir con este test
    monkeypatch.setattr(agent_runner.agents, "get", lambda t: object())

    exec_id = agent_runner.run_agent(
        agent_type="developer", ticket_id=1, context_blocks=[], user="tester",
        runtime="codex_cli",
    )

    assert exec_id == 4242
    assert orden == ["derive", "run", "persist"], (
        f"orden incorrecto: {orden}. La derivación debe ocurrir ANTES del run "
        "(baseline sin tocar) y la persistencia DESPUÉS (necesita el execution_id)."
    )
