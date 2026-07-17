"""Plan 133 F5 — Contrato declarativo 'stacky_required_blocks' (garantía pre-spawn)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

AGENT_MD_PATH = (
    Path(__file__).resolve().parent.parent
    / "Stacky" / "agents" / "FunctionalAnalyst.agent.md"
)


def test_parse_vacio_y_ausente():
    from services import agent_contract

    assert agent_contract.parse_required_blocks("") == []
    assert agent_contract.parse_required_blocks("---\nfoo: bar\n---\nbody") == []


def test_parse_and_or():
    from services import agent_contract

    text = '---\nstacky_required_blocks: "a|b, c"\n---\nbody'
    assert agent_contract.parse_required_blocks(text) == [["a", "b"], ["c"]]

    text2 = "---\nstacky_required_blocks: ' a | b ,  c '\n---\nbody"
    assert agent_contract.parse_required_blocks(text2) == [["a", "b"], ["c"]]


def test_enforce_flag_off_noop(monkeypatch):
    from config import config
    from services import agent_contract

    monkeypatch.setattr(config, "STACKY_REQUIRED_BLOCKS_ENABLED", False)
    monkeypatch.setattr(
        agent_contract, "resolve_agent_md_text",
        lambda filename: '---\nstacky_required_blocks: "a"\n---\n',
    )
    agent_contract.enforce(vscode_agent_filename="X.agent.md", blocks=[])


def test_enforce_ok_con_alternativa(monkeypatch):
    from config import config
    from services import agent_contract

    monkeypatch.setattr(config, "STACKY_REQUIRED_BLOCKS_ENABLED", True)
    monkeypatch.setattr(
        agent_contract, "resolve_agent_md_text",
        lambda filename: (
            '---\nstacky_required_blocks: "ado-epic-structured|ado-blocker, client-profile"\n---\n'
        ),
    )
    agent_contract.enforce(
        vscode_agent_filename="X.agent.md",
        blocks=[{"id": "ado-blocker"}, {"id": "client-profile"}],
    )


def test_enforce_falta_grupo_levanta(monkeypatch):
    from config import config
    from services import agent_contract

    monkeypatch.setattr(config, "STACKY_REQUIRED_BLOCKS_ENABLED", True)
    monkeypatch.setattr(
        agent_contract, "resolve_agent_md_text",
        lambda filename: (
            '---\nstacky_required_blocks: "ado-epic-structured|ado-blocker, client-profile"\n---\n'
        ),
    )
    with pytest.raises(agent_contract.AgentContractError) as exc_info:
        agent_contract.enforce(
            vscode_agent_filename="X.agent.md", blocks=[{"id": "client-profile"}],
        )
    assert "ado-epic-structured|ado-blocker" in str(exc_info.value)


def test_archivo_ausente_noop(monkeypatch):
    from config import config
    from services import agent_contract

    monkeypatch.setattr(config, "STACKY_REQUIRED_BLOCKS_ENABLED", True)
    monkeypatch.setattr(agent_contract, "resolve_agent_md_text", lambda filename: None)
    agent_contract.enforce(vscode_agent_filename="Inexistente.agent.md", blocks=[])


def test_filename_none_o_vacio_noop(monkeypatch):
    from config import config
    from services import agent_contract

    monkeypatch.setattr(config, "STACKY_REQUIRED_BLOCKS_ENABLED", True)

    def _boom(filename):
        raise AssertionError("no debería leer disco con filename None/vacío")

    monkeypatch.setattr(agent_contract, "resolve_agent_md_text", _boom)
    agent_contract.enforce(vscode_agent_filename=None, blocks=[])
    agent_contract.enforce(vscode_agent_filename="", blocks=[])


def test_functional_agent_md_declara_contrato():
    from services import agent_contract

    text = AGENT_MD_PATH.read_text(encoding="utf-8")
    parsed = agent_contract.parse_required_blocks(text)
    assert parsed == [
        ["ado-epic-structured", "ado-blocker", "run-directive"],
        ["client-profile"],
    ]
