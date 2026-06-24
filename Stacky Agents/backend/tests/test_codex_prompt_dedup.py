"""Tests de deduplicacion de prompts (Plan 69 v3)."""

from pathlib import Path
from unittest.mock import MagicMock


def _make_selected(name="TestAgent", filename="TestAgent.agent.md", description="Agente de prueba"):
    sel = MagicMock()
    sel.name = name
    sel.filename = filename
    sel.description = description
    return sel


_INVOC = (
    "## Agente Stacky seleccionado\n\n"
    "- Mention: @TestAgent\n"
    "- Nombre: TestAgent\n"
    "- Archivo agent.md: TestAgent.agent.md\n"
    "- Descripcion: Agente de prueba\n"
)


def test_dp01_codex_no_own_agent_stacky_header_outside_invocation():
    """La funcion no debe regenerar el header canonico fuera del invocation."""
    from services.codex_cli_runner import _build_codex_prompt

    sel = _make_selected()
    prompt = _build_codex_prompt(
        selected_agent=sel,
        all_agents=[],
        ticket_message="t",
        agent_bundle_dir=Path("/tmp/bundle"),
        agent_manifest_file=Path("/tmp/manifest.json"),
        invocation_block=_INVOC,
    )
    delta = prompt.replace(_INVOC, "")
    assert "## Agente Stacky seleccionado" not in delta
    assert prompt.count("## Agente Stacky seleccionado") == 1


def test_dp02_codex_no_duplicate_agent_block():
    from services.codex_cli_runner import _build_codex_prompt

    sel = _make_selected()
    prompt = _build_codex_prompt(
        selected_agent=sel,
        all_agents=[],
        ticket_message="t",
        agent_bundle_dir=Path("/tmp/bundle"),
        agent_manifest_file=Path("/tmp/manifest.json"),
        invocation_block=_INVOC,
    )
    assert "## Agente seleccionado\n" not in prompt


def test_dp03_codex_agent_info_present():
    from services.codex_cli_runner import _build_codex_prompt

    sel = _make_selected(
        name="FunctionalAnalyst",
        filename="FunctionalAnalyst.agent.md",
        description="Análisis funcional",
    )
    invoc = (
        "## Agente Stacky seleccionado\n"
        "- Mention: @FunctionalAnalyst\n"
        f"- Archivo agent.md: {sel.filename}\n"
        "- Descripcion: Análisis funcional\n"
    )
    prompt = _build_codex_prompt(
        selected_agent=sel,
        all_agents=[],
        ticket_message="t",
        agent_bundle_dir=Path("/tmp/bundle"),
        agent_manifest_file=Path("/tmp/manifest.json"),
        invocation_block=invoc,
    )
    assert "@FunctionalAnalyst" in prompt
    assert "Análisis funcional" in prompt


def test_dp04_codex_prompt_is_shorter_than_baseline():
    from services.codex_cli_runner import _build_codex_prompt

    sel = _make_selected()
    prompt_after = _build_codex_prompt(
        selected_agent=sel,
        all_agents=[],
        ticket_message="t",
        agent_bundle_dir=Path("/tmp/bundle"),
        agent_manifest_file=Path("/tmp/manifest.json"),
        invocation_block=_INVOC,
    )
    # Con el fixture fijo del plan, el prompt deduplicado debe quedar bajo un
    # umbral estricto de longitud (captura de reducción real de redundancia).
    assert len(prompt_after) < 2200
