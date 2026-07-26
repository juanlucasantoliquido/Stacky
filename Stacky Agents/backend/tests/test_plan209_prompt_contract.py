"""Plan 209 F1 — Enfoque A: la instrucción viaja en el system prompt.

Gateada por flag + allowlist de agentes user-facing: los agentes no-producto no
pagan input tokens por una guía que no aplica.
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

from agents.base import RunContext  # noqa: E402
from agents.devops import DevOpsAgent  # noqa: E402
from agents.functional import FunctionalAgent  # noqa: E402
from services.validation_playbook import SECTION_MARKER, SECTION_TITLE  # noqa: E402


@pytest.fixture
def ctx():
    # use_few_shot/anti_patterns/decisions en False: aísla la composición del
    # prompt de otros inyectores (y evita I/O innecesario en el test).
    return RunContext(use_few_shot=False, use_anti_patterns=False, use_decisions=False)


def test_instruction_presente_flag_on(ctx):
    prompt, _meta = FunctionalAgent().compose_system_prompt(ctx)

    assert SECTION_TITLE in prompt
    assert SECTION_MARKER in prompt
    assert "NO lo inventes" in prompt, "la regla anti-alucinación debe estar en la instrucción"


def test_instruction_ausente_flag_off(ctx, monkeypatch):
    from config import config as cfg

    monkeypatch.setattr(cfg, "STACKY_VALIDATION_PLAYBOOK_ENABLED", False, raising=False)
    prompt, meta = FunctionalAgent().compose_system_prompt(ctx)

    assert SECTION_TITLE not in prompt
    assert SECTION_MARKER not in prompt
    assert meta.get("validation_playbook_prompt") is not True


def test_instruction_ausente_agente_no_user_facing(ctx):
    prompt, meta = DevOpsAgent().compose_system_prompt(ctx)

    assert SECTION_TITLE not in prompt, "devops no es user-facing: no debe recibir la instrucción"
    assert meta.get("validation_playbook_prompt") is not True


def test_override_no_inyecta():
    prompt, meta = FunctionalAgent().compose_system_prompt(
        RunContext(system_prompt_override="X")
    )

    assert prompt == "X"
    assert meta["system_prompt_source"] == "override"


def test_meta_flag(ctx):
    _prompt, meta = FunctionalAgent().compose_system_prompt(ctx)

    assert meta.get("validation_playbook_prompt") is True


def test_prompt_base_intacto(ctx, monkeypatch):
    """Backward-compat: con flag OFF el prompt es exactamente el de hoy."""
    from config import config as cfg

    agent = FunctionalAgent()
    con_flag, _ = agent.compose_system_prompt(ctx)
    monkeypatch.setattr(cfg, "STACKY_VALIDATION_PLAYBOOK_ENABLED", False, raising=False)
    sin_flag, _ = agent.compose_system_prompt(ctx)

    assert sin_flag == agent.system_prompt() or agent.system_prompt() in sin_flag
    assert len(con_flag) > len(sin_flag)


def test_validation_prompt_block_gate(monkeypatch):
    from config import config as cfg
    from services.validation_playbook import validation_prompt_block

    assert validation_prompt_block("functional") != ""
    assert validation_prompt_block("devops") == ""
    assert validation_prompt_block(None) == ""

    monkeypatch.setattr(cfg, "STACKY_VALIDATION_PLAYBOOK_ENABLED", False, raising=False)
    assert validation_prompt_block("functional") == ""
