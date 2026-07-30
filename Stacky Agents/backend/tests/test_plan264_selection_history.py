"""Plan 264 F4 — persistencia por proyecto + historial en los 3 runtimes.

(a) La preferencia de runtime/modelo/effort se guarda por PROYECTO (mono-
operador, sin RBAC) vía el store de preferencias de UI ya existente.
(b) build_model_effort_trace/_persist_model_effort_trace se mudan a
runtime_capabilities.py (viven hoy en claude_code_cli_runner.py, Plan 212 F7),
CONSERVANDO el símbolo original como delegador (hay callers por nombre,
incluidos tests del 212). El trace gana claves (tool, effort_mode,
effort_effective_now, origen_*); downgraded/reason NUNCA se pierden.

Gotcha del repo (SQLITE_LOCKED): correr por archivo, 8-12 veces.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

import config  # noqa: E402
from services.runtime_capabilities import (  # noqa: E402
    load_run_preference,
    pref_key_for,
    save_run_preference,
)


@pytest.fixture(autouse=True)
def _prefs_store(tmp_path, monkeypatch):
    """Aísla el store real: _PREFS_FILE -> tmp_path, NUNCA el data/ del operador."""
    import api.preferences as prefs_mod

    monkeypatch.setattr(prefs_mod, "_PREFS_FILE", tmp_path / "preferences.json")
    monkeypatch.setattr(config.config, "STACKY_UI_SAVED_VIEWS_ENABLED", True)
    monkeypatch.setattr(config.config, "STACKY_RUN_SELECTION_PREFS_ENABLED", True)
    yield
    # El archivo real del operador nunca se tocó (monkeypatch de _PREFS_FILE).
    real_prefs = ROOT / "data" / "preferences.json"
    if real_prefs.exists():
        import json as _json
        doc = _json.loads(real_prefs.read_text(encoding="utf-8"))
        assert "runSelection." not in _json.dumps(doc), (
            "el test escribió en el archivo REAL de preferencias del operador"
        )


# ---------------------------------------------------------------------------
# 1-6 — persistencia por proyecto
# ---------------------------------------------------------------------------

def test_01_round_trip():
    save_run_preference("proyA", {"runtime": "claude_code_cli", "model": "claude-sonnet-5", "effort": "high"})
    loaded = load_run_preference("proyA")
    assert loaded is not None
    assert loaded["runtime"] == "claude_code_cli"
    assert loaded["model"] == "claude-sonnet-5"
    assert loaded["effort"] == "high"


def test_02_proyecto_inexistente_devuelve_none_no_lanza():
    assert load_run_preference("proyecto_inexistente_264") is None


def test_03_effort_invalido_se_guarda_clampeado():
    save_run_preference("proyA", {"runtime": "claude_code_cli", "model": "claude-sonnet-5", "effort": "turbo"})
    loaded = load_run_preference("proyA")
    assert loaded["effort"] != "turbo"
    assert loaded["effort"] in ("low", "medium", "high", "xhigh", "max")


def test_04_flag_prefs_off(monkeypatch):
    monkeypatch.setattr(config.config, "STACKY_RUN_SELECTION_PREFS_ENABLED", False)
    assert save_run_preference("proyA", {"runtime": "claude_code_cli", "effort": "low"}) is False
    assert load_run_preference("proyA") is None


def test_05_pref_key_for_nombre_con_espacios_y_acentos():
    key = pref_key_for("Stacky Agents (Pacífico)")
    import re

    assert re.match(r"^[A-Za-z0-9._-]{1,128}$", key)
    save_run_preference("Stacky Agents (Pacífico)", {"runtime": "codex_cli", "effort": "medium"})
    assert load_run_preference("Stacky Agents (Pacífico)")["effort"] == "medium"


def test_06_ui_saved_views_disabled(monkeypatch):
    monkeypatch.setattr(config.config, "STACKY_UI_SAVED_VIEWS_ENABLED", False)
    assert save_run_preference("proyA", {"runtime": "claude_code_cli", "effort": "low"}) is False
    assert load_run_preference("proyA") is None


# ---------------------------------------------------------------------------
# 7-9 — build_model_effort_trace (movido, con delegador conservado)
# ---------------------------------------------------------------------------

def test_07_trace_claude_effort_mode_nativo():
    from services.runtime_capabilities import build_model_effort_trace

    trace = build_model_effort_trace(
        requested_model="claude-sonnet-5", effective_model="claude-sonnet-5",
        requested_effort="high", effective_effort="high",
        runtime="claude_code_cli",
    )
    assert trace["tool"] == "claude_code_cli"
    assert trace["effort_mode"] == "nativo"


def test_08_trace_codex_effort_mode_presupuesto_turnos():
    from services.runtime_capabilities import build_model_effort_trace

    trace = build_model_effort_trace(
        requested_model=None, effective_model=None,
        requested_effort="low", effective_effort="low",
        runtime="codex_cli",
    )
    assert trace["tool"] == "codex_cli"
    assert trace["effort_mode"] == "presupuesto_turnos"


def test_09_trace_con_degradacion():
    from services.runtime_capabilities import build_model_effort_trace

    trace = build_model_effort_trace(
        requested_model="claude-opus-4-8", effective_model="claude-sonnet-5",
        requested_effort="max", effective_effort="max",
        runtime="claude_code_cli", reason="modelo degradado",
    )
    assert trace["downgraded"] is True
    assert trace["reason"]
    assert trace["requested_effort"] != "" and trace["requested_model"] != trace["effective_model"]


def test_09b_delegador_claude_code_cli_runner_conserva_downgraded_y_reason():
    """[C6 v1->v2] el delegador NO puede perder downgraded/reason: los usa
    test_plan212_requested_vs_effective.py como regresión."""
    from services.claude_code_cli_runner import build_model_effort_trace as _delegate

    trace = _delegate(
        requested_model="claude-opus-4-8", effective_model="claude-sonnet-5",
        requested_effort="max", effective_effort="high", reason="degradado por modelo",
    )
    assert trace["downgraded"] is True
    assert trace["reason"] == "degradado por modelo"
    assert trace["tool"] == "claude_code_cli"  # default del delegador


# ---------------------------------------------------------------------------
# 10 — metadata_dict["model_effort"] persiste tras start_codex_cli_run mockeado
# ---------------------------------------------------------------------------

def test_10_codex_metadata_dict_model_effort_present(monkeypatch):
    import itertools

    from db import init_db, session_scope
    from models import AgentExecution, Ticket
    import services.codex_cli_runner as codex_mod
    from unittest.mock import MagicMock

    init_db()
    counter = itertools.count(264900)
    with session_scope() as session:
        t = Ticket(ado_id=next(counter), project="RSPacifico", title="f4 test", ado_state="Active")
        session.add(t)
        session.flush()
        ticket_id = t.id

        row = AgentExecution(
            ticket_id=ticket_id, agent_type="developer", status="preparing",
            started_by="test",
        )
        row.input_context = []
        session.add(row)
        session.flush()
        execution_id = row.id

    monkeypatch.setattr(config.config, "STACKY_RUNAWAY_MAX_TURNS", 40)
    monkeypatch.setattr(config.config, "STACKY_CODEX_EFFORT_PARITY_ENABLED", True)
    monkeypatch.setattr(config.config, "STACKY_ADAPTIVE_EFFORT_ENABLED", False)
    monkeypatch.setattr(config.config, "STACKY_COMPLEXITY_ESTIMATION_ENABLED", False)

    fake_proc = MagicMock()
    fake_proc.pid = 999002

    class _StopEarly(Exception):
        pass

    def _spy_run_limits(*a, **kw):
        raise _StopEarly("corte deliberado, ya persistimos el trace antes de esto")

    import harness.runaway_guard as runaway_guard_mod

    monkeypatch.setattr(runaway_guard_mod, "RunLimits", _spy_run_limits)
    monkeypatch.setattr(codex_mod.subprocess, "Popen", lambda *a, **kw: fake_proc)

    codex_mod._run_in_background(
        execution_id,
        ticket_message="f4 test",
        vscode_agent_filename="Developer.agent.md",
        workspace_root=None,
        model_override=None,
        effort_override="high",
    )

    with session_scope() as session:
        row = session.get(AgentExecution, execution_id)
        trace = (row.metadata_dict or {}).get("model_effort")

    import shutil
    shutil.rmtree(ROOT / "data" / "codex_runs" / str(execution_id), ignore_errors=True)

    assert trace is not None
    assert trace["tool"] == "codex_cli"
    assert trace["effort_mode"] == "presupuesto_turnos"
    assert "effort_effective_now" in trace
    assert "downgraded" in trace


def test_11_effort_mode_covers_the_three_runtimes():
    from services.runtime_capabilities import EFFORT_MODE

    assert sorted(EFFORT_MODE) == ["claude_code_cli", "codex_cli", "github_copilot"]
