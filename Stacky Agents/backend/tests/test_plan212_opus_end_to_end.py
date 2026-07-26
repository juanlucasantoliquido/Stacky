"""Plan 212 F1 — Elegir Opus 4.8 ejecuta Opus 4.8 (fin de la degradación silenciosa).

El permiso que el endpoint ya otorgaba moría antes de llegar al router del runner.
Acá se verifica la cadena completa: política → gate del runner → `--model` del CLI.
"""
from __future__ import annotations

import ast
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

from services import claude_code_cli_runner as runner  # noqa: E402
from services import llm_router  # noqa: E402

_RUNNER_SRC = (ROOT / "services" / "claude_code_cli_runner.py").read_text(encoding="utf-8")


def _decide(override: str, allow_opus: bool) -> str:
    return llm_router.decide(
        agent_type="business", blocks=[], override=override,
        backend="anthropic", allow_opus=allow_opus,
    ).model


# ---------------------------------------------------------------------------
# La política: qué desbloquea el permiso y qué NO
# ---------------------------------------------------------------------------

def test_decide_allow_opus_true_keeps_opus():
    assert _decide("claude-opus-4-8", True) == "claude-opus-4-8"


def test_decide_allow_opus_false_clamps():
    assert _decide("claude-opus-4-8", False) == "claude-sonnet-5"


def test_decide_allow_opus_true_still_blocks_fable():
    assert _decide("claude-fable-5", True) == "claude-sonnet-5"


def test_decide_allow_opus_true_still_blocks_opus_47():
    """El permiso es por id exacto, no por familia: un Opus fuera de la allowlist cae."""
    assert _decide("claude-opus-4-7", True) == "claude-sonnet-5"


def test_is_opus_allowlisted():
    assert llm_router.is_opus_allowlisted("claude-opus-4-8") is True
    for otro in (None, "", "claude-sonnet-5", "claude-opus-4-7", "claude-fable-5"):
        assert llm_router.is_opus_allowlisted(otro) is False, otro


# ---------------------------------------------------------------------------
# El gate del runner: solo override explícito, nunca DevOps
# ---------------------------------------------------------------------------

def test_runner_passes_allow_opus_only_for_explicit_override(monkeypatch):
    from config import config as cfg

    assert runner.allow_opus_for_run("claude-opus-4-8", "developer") is True

    monkeypatch.setattr(cfg, "CLAUDE_CODE_CLI_MODEL", "claude-opus-4-8", raising=False)
    assert runner.allow_opus_for_run(None, "developer") is False, \
        "el default global NO puede desbloquear Opus para todo el sistema"


def test_runner_never_allows_opus_for_devops_agent_type():
    """Guardarraíl 11: el agente que toca deploys no escala de tier solo."""
    for tipo in ("devops", "DevOps", "  DEVOPS  "):
        assert runner.allow_opus_for_run("claude-opus-4-8", tipo) is False, tipo


def test_runner_gate_is_wired_into_decide():
    """El helper no sirve de nada si el call site no lo usa: se verifica por AST."""
    arbol = ast.parse(_RUNNER_SRC)
    llamadas = [
        n for n in ast.walk(arbol)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute) and n.func.attr == "decide"
    ]
    assert llamadas, "no se encontró la llamada a llm_router.decide en el runner"

    for llamada in llamadas:
        kw = {k.arg for k in llamada.keywords}
        assert "allow_opus" in kw, "decide() se invoca sin propagar el permiso"

    asignaciones = [
        n for n in ast.walk(arbol)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
        and n.func.id == "allow_opus_for_run"
    ]
    assert asignaciones, "el gate se declaró pero nunca se invoca"


# ---------------------------------------------------------------------------
# KPI-1: el modelo elegido llega al argumento del CLI
# ---------------------------------------------------------------------------

def _pares(cmd: list[str], flag: str) -> list[str]:
    return [cmd[i + 1] for i, tok in enumerate(cmd) if tok == flag and i + 1 < len(cmd)]


def test_build_command_receives_opus():
    cmd = runner._build_command(
        model_override="claude-opus-4-8",
        effort_override="high",
    )

    assert _pares(cmd, "--model") == ["claude-opus-4-8"], cmd
