"""Plan 213 F2 — La política de supuestos llega igual a los 3 runtimes.

Lo que se verifica no es que el texto exista, sino que **el mismo** texto llegue
por los tres caminos: claude y codex vía run_contract, copilot vía
compose_system_prompt. Un runtime con su propia copia es cómo se desincronizan.
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

from harness import run_contract  # noqa: E402

_KEY = "STACKY_ASSUMPTION_MODE_ENABLED"
_TYPES = "STACKY_ASSUMPTION_MODE_AGENT_TYPES"


@pytest.fixture
def modo_on(monkeypatch):
    from config import config as cfg

    monkeypatch.setattr(cfg, _KEY, True, raising=False)
    monkeypatch.setattr(cfg, _TYPES, "technical,functional", raising=False)
    return cfg


@pytest.fixture
def modo_off(monkeypatch):
    from config import config as cfg

    monkeypatch.setattr(cfg, _KEY, False, raising=False)
    return cfg


def test_assumption_rules_text_off_is_empty(modo_off):
    assert run_contract.assumption_rules_text() == ""


def test_assumption_rules_text_on_has_canonical_format(modo_on):
    texto = run_contract.assumption_rules_text()

    for marca in ("[SUPUESTO:", "base:", "impacto:", "[PENDIENTE:"):
        assert marca in texto, marca


def test_applies_to_allowlist(modo_on):
    for si in ("technical", "functional", "TECHNICAL"):
        assert run_contract.applies_to(si) is True, si
    for no in ("developer", "qa", "business", "", "incident_dev"):
        assert run_contract.applies_to(no) is False, no


def test_applies_to_empty_csv(monkeypatch):
    from config import config as cfg

    monkeypatch.setattr(cfg, _TYPES, "", raising=False)

    for tipo in ("technical", "functional", "developer"):
        assert run_contract.applies_to(tipo) is False


def test_with_assumption_policy_is_additive(modo_on):
    base = "REGLAS BASE"

    assert run_contract.with_assumption_policy(base, "developer") == base
    con = run_contract.with_assumption_policy(base, "technical")
    assert con.startswith(base) and "[SUPUESTO:" in con


# ---------------------------------------------------------------------------
# Los 3 runtimes
# ---------------------------------------------------------------------------

def _claude_prompt(agent_type: str) -> str:
    from services import claude_code_cli_runner as r
    from services.vscode_agents import VsCodeAgent

    agente = VsCodeAgent(name="Tec", filename="TechnicalAnalyst.agent.md",
                         description="analista tecnico", system_prompt="sp")
    return r._build_system_prompt(agente, agent_type=agent_type)


def _codex_prompt(agent_type: str) -> str:
    from services import codex_cli_runner as r
    from services.vscode_agents import VsCodeAgent

    agente = VsCodeAgent(name="Tec", filename="TechnicalAnalyst.agent.md",
                         description="analista tecnico", system_prompt="sp")
    return r._build_codex_prompt(
        selected_agent=agente, all_agents=[agente], ticket_message="msg",
        agent_bundle_dir=Path("."), agent_manifest_file=Path("manifest.json"),
        agent_type=agent_type,
    )


def _copilot_prompt() -> tuple[str, dict]:
    from agents.base import RunContext
    from agents.technical import TechnicalAgent

    return TechnicalAgent().compose_system_prompt(RunContext())


def test_claude_system_prompt_includes_policy_for_technical(modo_on):
    assert "[SUPUESTO:" in _claude_prompt("technical")


def test_claude_system_prompt_excludes_policy_for_developer(modo_on):
    """G6: el Developer construye, no declara supuestos. Protege el plan 210."""
    assert "[SUPUESTO:" not in _claude_prompt("developer")


def test_codex_prompt_includes_policy(modo_on):
    assert "[SUPUESTO:" in _codex_prompt("technical")
    assert "[SUPUESTO:" not in _codex_prompt("developer")


def test_copilot_compose_includes_policy(modo_on):
    full, meta = _copilot_prompt()

    assert "[SUPUESTO:" in full
    assert meta.get("assumption_policy_prompt") is True


def test_all_three_runtimes_share_the_same_text(modo_on):
    """Una sola fuente: si alguien copia el string, este test lo caza."""
    canonico = run_contract.assumption_rules_text()

    claude = _claude_prompt("technical")
    codex = _codex_prompt("technical")
    copilot, _ = _copilot_prompt()

    for nombre, prompt in (("claude", claude), ("codex", codex), ("copilot", copilot)):
        assert canonico in prompt, f"{nombre} no recibe el texto canónico íntegro"


def test_flag_off_prompts_are_byte_identical(modo_off):
    assert "[SUPUESTO:" not in _claude_prompt("technical")
    assert "[SUPUESTO:" not in _codex_prompt("technical")
    full, meta = _copilot_prompt()
    assert "[SUPUESTO:" not in full
    assert "assumption_policy_prompt" not in meta


def test_single_definition_of_the_policy_text():
    """El string vive en un solo archivo: grep-gate contra la duplicación."""
    marca = "_RULES_" + "ASSUMPTIONS"      # partido: si no, este test se cuenta solo
    hits = [
        p for p in ROOT.rglob("*.py")
        if ".venv" not in str(p) and "tests" not in p.parts
        and marca in p.read_text(encoding="utf-8", errors="ignore")
    ]

    assert [p.name for p in hits] == ["run_contract.py"], [str(p) for p in hits]
