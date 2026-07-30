"""Plan 264 F2 — paridad real de Codex: el effort llega al call site VIVO.

`agent_runner.py:_start_cli_runtime` (rama codex, la que REALMENTE corre por el
return temprano de `run_agent`) recibía `effort_override` y no lo reenviaba a
`start_codex_cli_run`. El "fix" del Plan 196 vivía en la rama MUERTA
(`agent_runner.py:227-300`). Este archivo blinda el call site vivo.

Gotcha del repo (SQLITE_LOCKED): los tests que tocan la DB son flaky bajo el
shared-cache de pytest. Correr este archivo SOLO, varias veces seguidas.
"""
from __future__ import annotations

import inspect
import itertools
import os
import shutil
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

import config  # noqa: E402
import agent_runner  # noqa: E402
from services.codex_cli_runner import start_codex_cli_run  # noqa: E402
from services.runtime_capabilities import EFFORTS, codex_turn_budget  # noqa: E402

_ADO_ID_COUNTER = itertools.count(264200)


@pytest.fixture(autouse=True, scope="module")
def _init_database():
    from db import init_db

    init_db()


def _mk_ticket() -> int:
    from db import session_scope
    from models import Ticket

    with session_scope() as session:
        t = Ticket(
            ado_id=next(_ADO_ID_COUNTER),
            project="RSPacifico",
            title="plan264 codex effort parity",
            ado_state="Active",
        )
        session.add(t)
        session.flush()
        return t.id


def _mk_execution(ticket_id: int, agent_type: str = "developer") -> int:
    """Fila de ejecución mínima, sin pasar por start_codex_cli_run (que lanza
    un thread): _run_in_background se llama directo y sincrónico en el test."""
    from datetime import datetime

    from db import session_scope
    from models import AgentExecution

    with session_scope() as session:
        row = AgentExecution(
            ticket_id=ticket_id, agent_type=agent_type, status="preparing",
            started_by="test", started_at=datetime.utcnow(),
        )
        row.input_context = []
        session.add(row)
        session.flush()
        return row.id


class _BudgetCaptured(Exception):
    """Sentinel para cortar `_run_in_background` justo DESPUÉS de construir
    `RunLimits` (que ya corre después del trace y de la zona de esfuerzo), sin
    llegar a leer stdout/esperar el proceso/notificar. El propio try/except
    de `_run_in_background` la atrapa y marca la ejecución 'error' — eso ya
    está probado en otros tests de este repo; acá sólo nos importa lo que
    capturamos ANTES de la excepción deliberada."""


def _run_codex_and_capture(
    monkeypatch,
    *,
    effort_override: str | None,
    cap_turns: int,
    adaptive_effort_enabled: bool = False,
    complexity_estimation_enabled: bool = False,
    parity_enabled: bool = True,
) -> tuple[int | None, dict | None, str]:
    """Corre _run_in_background de verdad hasta justo después de RunLimits,
    con el subprocess mockeado (nunca spawnea un `codex` real). Devuelve
    (max_turns_capturado, trace_persistido, mensaje_de_error_terminal)."""
    monkeypatch.setattr(config.config, "STACKY_RUNAWAY_MAX_TURNS", cap_turns)
    monkeypatch.setattr(config.config, "STACKY_ADAPTIVE_EFFORT_ENABLED", adaptive_effort_enabled)
    monkeypatch.setattr(config.config, "STACKY_COMPLEXITY_ESTIMATION_ENABLED", complexity_estimation_enabled)
    monkeypatch.setattr(config.config, "STACKY_CODEX_EFFORT_PARITY_ENABLED", parity_enabled)

    ticket_id = _mk_ticket()
    execution_id = _mk_execution(ticket_id)

    import harness.runaway_guard as runaway_guard_mod
    import services.codex_cli_runner as codex_mod

    captured: dict = {}

    def _spy_run_limits(*args, **kwargs):
        captured["max_turns"] = kwargs.get("max_turns")
        raise _BudgetCaptured("corte deliberado del test tras capturar RunLimits")

    calls: dict = {"terminal_error": None}
    real_mark_terminal = codex_mod._mark_terminal

    def _spy_mark_terminal(execution_id_, *, status, output=None, error=None, metadata=None):
        if status == "error":
            calls["terminal_error"] = error
        return real_mark_terminal(
            execution_id_, status=status, output=output, error=error, metadata=metadata
        )

    fake_proc = MagicMock()
    fake_proc.pid = 999001

    monkeypatch.setattr(runaway_guard_mod, "RunLimits", _spy_run_limits)
    monkeypatch.setattr(codex_mod.subprocess, "Popen", lambda *a, **kw: fake_proc)
    monkeypatch.setattr(codex_mod, "_mark_terminal", _spy_mark_terminal)

    codex_mod._run_in_background(
        execution_id,
        ticket_message="plan264 test message",
        vscode_agent_filename="Developer.agent.md",  # agente real, sin stacky_required_blocks
        workspace_root=None,
        model_override=None,
        effort_override=effort_override,
    )

    from db import session_scope
    from models import AgentExecution

    with session_scope() as session:
        row = session.get(AgentExecution, execution_id)
        trace = (row.metadata_dict or {}).get("model_effort") if row else None

    shutil.rmtree(ROOT / "data" / "codex_runs" / str(execution_id), ignore_errors=True)

    terminal_error = calls["terminal_error"] or ""
    assert terminal_error.startswith("corte deliberado"), (
        f"_run_in_background falló ANTES de llegar a RunLimits (no es el corte "
        f"deliberado del test): {terminal_error!r}"
    )
    return captured.get("max_turns"), trace, terminal_error


# ---------------------------------------------------------------------------
# 1 — la firma acepta effort_override
# ---------------------------------------------------------------------------

def test_01_signature_accepts_effort_override():
    assert "effort_override" in inspect.signature(start_codex_cli_run).parameters


# ---------------------------------------------------------------------------
# 2 / 2b — el camino real (vía _start_cli_runtime) propaga effort_override
# ---------------------------------------------------------------------------

def test_02_run_agent_propagates_effort_to_codex(monkeypatch):
    # G0.1 (services/run_preflight.py) es un gate AJENO a este plan que exige
    # repo_path resolvible; en este worktree no hay proyecto activo. Confirmado
    # como deuda preexistente corriendo tests/test_runtime_dispatch.py sin
    # tocar nada de Plan 264 (3 failed/7 passed, mismo "repo_missing").
    monkeypatch.setattr(config.config, "STACKY_RUN_PREFLIGHT_GATE_ENABLED", False)
    ticket_id = _mk_ticket()
    with patch(
        "services.codex_cli_runner.start_codex_cli_run", return_value=999
    ) as mock_start:
        agent_runner.run_agent(
            agent_type="developer",
            ticket_id=ticket_id,
            context_blocks=[],
            user="test",
            runtime="codex_cli",
            vscode_agent_filename="Developer.agent.md",
            effort_override="high",
        )
    mock_start.assert_called_once()
    assert mock_start.call_args.kwargs["effort_override"] == "high"


def test_02b_start_cli_runtime_direct_propagates_effort():
    """Blinda el call site vivo aunque run_agent cambie de forma."""
    import agents as agents_registry

    ticket_id = _mk_ticket()
    agent = agents_registry.get("developer")
    with patch(
        "services.codex_cli_runner.start_codex_cli_run", return_value=999
    ) as mock_start:
        agent_runner._start_cli_runtime(
            runtime="codex_cli",
            agent=agent,
            agent_type="developer",
            ticket_id=ticket_id,
            context_blocks=[],
            user="test",
            vscode_agent_filename="Developer.agent.md",
            model_override=None,
            effort_override="high",
            project_name=None,
        )
    mock_start.assert_called_once()
    assert mock_start.call_args.kwargs["effort_override"] == "high"


def test_03_without_effort_override_mock_gets_none(monkeypatch):
    monkeypatch.setattr(config.config, "STACKY_RUN_PREFLIGHT_GATE_ENABLED", False)
    ticket_id = _mk_ticket()
    with patch(
        "services.codex_cli_runner.start_codex_cli_run", return_value=999
    ) as mock_start:
        agent_runner.run_agent(
            agent_type="developer",
            ticket_id=ticket_id,
            context_blocks=[],
            user="test",
            runtime="codex_cli",
            vscode_agent_filename="Developer.agent.md",
        )
    mock_start.assert_called_once()
    assert mock_start.call_args.kwargs["effort_override"] is None


# ---------------------------------------------------------------------------
# 4 — metadata_dict guarda el effort_override crudo
# ---------------------------------------------------------------------------

def test_04_metadata_dict_stores_effort_override():
    ticket_id = _mk_ticket()
    with patch("services.codex_cli_runner._run_in_background"):
        exec_id = start_codex_cli_run(
            ticket_id=ticket_id,
            agent_type="developer",
            context_blocks=[],
            user="test",
            vscode_agent_filename="Developer.agent.md",
            ticket_message="test message",
            effort_override="max",
        )

    from db import session_scope
    from models import AgentExecution

    with session_scope() as session:
        row = session.get(AgentExecution, exec_id)
        assert row.metadata_dict["effort_override"] == "max"


# ---------------------------------------------------------------------------
# 5 — cap=0 (default real): el override NUNCA convierte "sin límite" en límite
# ---------------------------------------------------------------------------

def test_05_zero_cap_stays_unlimited_even_with_max_effort(monkeypatch):
    max_turns, _trace, _err = _run_codex_and_capture(
        monkeypatch, effort_override="max", cap_turns=0,
    )
    assert max_turns == 0


# ---------------------------------------------------------------------------
# 6 — [FIX C7] equivalencia EXACTA con la fórmula de hoy, para los 5 efforts
# ---------------------------------------------------------------------------

def test_06_budget_matches_todays_formula_for_all_efforts(monkeypatch):
    for effort in EFFORTS:
        max_turns, _trace, _err = _run_codex_and_capture(
            monkeypatch, effort_override=effort, cap_turns=40,
        )
        expected = codex_turn_budget(effort, 40)
        assert max_turns == expected, (effort, max_turns, expected)
    # Ancla literal del plan: 20 para low, 40 para el resto.
    assert codex_turn_budget("low", 40) == 20


# ---------------------------------------------------------------------------
# 7 — el override explícito se honra AUNQUE adaptativo/complejidad estén OFF
# ---------------------------------------------------------------------------

def test_07_explicit_override_honored_with_adaptive_and_complexity_off(monkeypatch):
    max_turns, _trace, _err = _run_codex_and_capture(
        monkeypatch, effort_override="low", cap_turns=40,
        adaptive_effort_enabled=False, complexity_estimation_enabled=False,
    )
    assert max_turns == 20, "el effort se descartó fuera del bloque adaptativo"


# ---------------------------------------------------------------------------
# 8 — el trace registra requested_effort aunque las dos flags ajenas estén OFF
# ---------------------------------------------------------------------------

def test_08_trace_keeps_requested_effort_with_adaptive_and_complexity_off(monkeypatch):
    _max_turns, trace, _err = _run_codex_and_capture(
        monkeypatch, effort_override="high", cap_turns=40,
        adaptive_effort_enabled=False, complexity_estimation_enabled=False,
    )
    assert trace is not None, "el trace de model_effort no se persistió"
    assert trace["requested_effort"] == "high"


# ---------------------------------------------------------------------------
# 9 / 9b — flag STACKY_CODEX_EFFORT_PARITY_ENABLED
# ---------------------------------------------------------------------------

def test_09_flag_off_ignores_override_pre264_behavior(monkeypatch):
    max_turns, _trace, _err = _run_codex_and_capture(
        monkeypatch, effort_override="low", cap_turns=40,
        parity_enabled=False,
    )
    assert max_turns == 40, "con la flag OFF el comportamiento debe ser el de antes del 264"


def test_09b_flag_on_real_module_no_attribute_error(monkeypatch):
    """Control del binding de `config` (C2): con `config.config.X` este test
    explota (el error terminal contendría 'AttributeError', no el sentinel)."""
    max_turns, _trace, err = _run_codex_and_capture(
        monkeypatch, effort_override="low", cap_turns=40,
        parity_enabled=True,
    )
    assert "AttributeError" not in err
    assert max_turns == 20


# ---------------------------------------------------------------------------
# 10 — regresión Plan 196: Claude sigue recibiendo effort_override
# ---------------------------------------------------------------------------

def test_10_claude_regression_still_receives_effort_override(monkeypatch):
    monkeypatch.setattr(config.config, "STACKY_RUN_PREFLIGHT_GATE_ENABLED", False)
    ticket_id = _mk_ticket()
    with patch(
        "services.claude_code_cli_runner.start_claude_code_cli_run", return_value=999
    ) as mock_start:
        agent_runner.run_agent(
            agent_type="developer",
            ticket_id=ticket_id,
            context_blocks=[],
            user="test",
            runtime="claude_code_cli",
            vscode_agent_filename="Developer.agent.md",
            effort_override="high",
        )
    mock_start.assert_called_once()
    assert mock_start.call_args.kwargs["effort_override"] == "high"
