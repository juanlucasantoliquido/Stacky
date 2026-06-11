"""H3.1 — Tests del texto canónico de reglas (harness/run_contract.py).

TDD: estos tests deben fallar ANTES de que exista run_contract.py y pasar
después de la implementación.

Casos:
1. El texto file-drop contiene las rutas y la regla de id real (ADO id, no ordinal).
2. La variante MCP menciona las tools submit_*.
3. _build_system_prompt (claude) incluye el texto canónico.
4. _build_codex_prompt (codex) incluye el texto canónico.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


# ── Helpers ──────────────────────────────────────────────────────────────────

class _FakeAgent:
    def __init__(self):
        self.name = "TestAgent"
        self.filename = "TestAgent.agent.md"
        self.description = "Agente de test"
        self.system_prompt = "Sos el agente de test."


def _agent():
    return _FakeAgent()


# ── H3.1.1 — Texto file-drop contiene rutas canónicas y regla de id real ─────

def test_rules_text_filedrop_contains_comment_html_path():
    from harness.run_contract import rules_text
    text = rules_text(runtime="claude", mcp_enabled=False)
    assert "Agentes/outputs/<ADO_ID>/comment.html" in text


def test_rules_text_filedrop_contains_pending_task_path():
    from harness.run_contract import rules_text
    text = rules_text(runtime="claude", mcp_enabled=False)
    assert "epic-<ADO_ID>" in text
    assert "pending-task.json" in text


def test_rules_text_filedrop_mentions_ado_real_not_ordinal():
    from harness.run_contract import rules_text
    text = rules_text(runtime="claude", mcp_enabled=False)
    # Debe mencionar que el id real jamás es ordinal
    assert "ordinal" in text or "ADO id real" in text


def test_rules_text_filedrop_forbids_touching_ado_directly():
    from harness.run_contract import rules_text
    text = rules_text(runtime="claude", mcp_enabled=False)
    assert "Azure DevOps" in text or "ADO" in text


# ── H3.1.2 — Variante MCP menciona las tools submit_* ─────────────────────

def test_rules_text_mcp_mentions_submit_tools():
    from harness.run_contract import rules_text
    text = rules_text(runtime="claude", mcp_enabled=True)
    assert "stacky_submit_comment" in text
    assert "stacky_submit_task" in text


def test_rules_text_mcp_mentions_filedrop_as_fallback():
    from harness.run_contract import rules_text
    text = rules_text(runtime="claude", mcp_enabled=True)
    # El file-drop es fallback en variante MCP
    assert "fallback" in text.lower() or "comment.html" in text


def test_rules_text_codex_filedrop_same_paths():
    """El runtime codex debe tener las mismas rutas canónicas."""
    from harness.run_contract import rules_text
    text = rules_text(runtime="codex", mcp_enabled=False)
    assert "Agentes/outputs/<ADO_ID>/comment.html" in text
    assert "pending-task.json" in text


# ── H3.1.3 — _build_system_prompt de claude incluye el texto canónico ────────

def test_claude_system_prompt_uses_canonical_rules():
    """_build_system_prompt debe obtener las reglas de run_contract, no de _STACKY_RULES local."""
    from services import claude_code_cli_runner
    from harness.run_contract import rules_text

    sp = claude_code_cli_runner._build_system_prompt(_agent())

    canonical = rules_text(runtime="claude", mcp_enabled=False)
    # El texto canónico entero debe estar embebido en el system prompt
    assert canonical.strip() in sp or all(
        line in sp for line in canonical.strip().splitlines() if line.strip()
    )


def test_claude_system_prompt_still_has_no_touches_ado():
    """Regresión: la regla ADO no debe desaparecer al migrar a run_contract."""
    from services import claude_code_cli_runner
    sp = claude_code_cli_runner._build_system_prompt(_agent())
    assert "Azure DevOps" in sp or "ADO" in sp


# ── H3.1.4 — _build_codex_prompt incluye el texto canónico ──────────────────

def test_codex_prompt_uses_canonical_rules():
    from services import codex_cli_runner
    from harness.run_contract import rules_text

    prompt = codex_cli_runner._build_codex_prompt(
        selected_agent=_agent(),
        all_agents=[_agent()],
        ticket_message="ADO-1\nTítulo: test",
        agent_bundle_dir=Path("/tmp/bundle"),
        agent_manifest_file=Path("/tmp/bundle/manifest.json"),
    )

    canonical = rules_text(runtime="codex", mcp_enabled=False)
    assert canonical.strip() in prompt or all(
        line in prompt for line in canonical.strip().splitlines() if line.strip()
    )


def test_codex_prompt_no_duplicate_ado_block():
    """No debe haber dos bloques idénticos de 'Regla absoluta: no toques Azure DevOps'."""
    from services import codex_cli_runner
    prompt = codex_cli_runner._build_codex_prompt(
        selected_agent=_agent(),
        all_agents=[_agent()],
        ticket_message="ADO-1\nTítulo: test",
        agent_bundle_dir=Path("/tmp/bundle"),
        agent_manifest_file=Path("/tmp/bundle/manifest.json"),
    )
    # La frase exacta de la regla debe aparecer exactamente una vez
    count = prompt.count("Regla absoluta: no toques Azure DevOps")
    assert count == 1, f"Regla ADO aparece {count} veces en el prompt (esperado: 1)"
