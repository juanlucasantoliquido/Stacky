"""Autonomía del Documentador — el run NUNCA debe quedar esperando al operador.

Dos causas cubiertas:
1. El runner de Claude CLI trataba los runs del Documentador (ticket pool
   ado_id=-7) como sesión conversacional multi-turno: tras el `result` terminal
   el proceso quedaba vivo con stdin abierto esperando input del operador, y
   doc_documenter._wait_and_read_output se colgaba hasta el timeout (1800s).
2. El prompt del agente no le prohibía preguntar: ante un dato faltante podía
   cerrar el turno con una pregunta en vez de inferir un default seguro.
"""
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# 1) Runner: los runs del Documentador son one-shot (cierran solos)
# ---------------------------------------------------------------------------

def test_one_shot_incluye_ticket_documentador():
    from services.claude_code_cli_runner import _is_one_shot

    assert _is_one_shot(-1) is True   # brief→épica (comportamiento histórico)
    assert _is_one_shot(-7) is True   # Documentador (plan 113, _CONVERSATION_ADO_ID)


def test_one_shot_no_afecta_consolas_conversacionales():
    from services.claude_code_cli_runner import _is_one_shot

    # Consolas multi-turno reales: DevOps (-4), consola remota (-5), doctor (-3),
    # revisor PRs (-6) y tickets normales (positivos) siguen conversacionales.
    for ado_id in (-3, -4, -5, -6, 0, 1, 12345, None):
        assert _is_one_shot(ado_id) is False, ado_id


def test_one_shot_ids_coinciden_con_el_ticket_del_documenter():
    from services.claude_code_cli_runner import _ONE_SHOT_ADO_IDS
    from services.doc_documenter import _CONVERSATION_ADO_ID

    assert _CONVERSATION_ADO_ID in _ONE_SHOT_ADO_IDS
    assert -1 in _ONE_SHOT_ADO_IDS


# ---------------------------------------------------------------------------
# 2) Prompt: autonomía explícita (inferir, nunca preguntar, supuestos [INF])
# ---------------------------------------------------------------------------

_AUTONOMY_MARKERS = ("NUNCA", "pregunt", "infer", "[INF]")


def test_prompt_fallback_exige_autonomia():
    from services.doc_documenter import _DEFAULT_DOCUMENTADOR_PROMPT as p

    low = p  # los marcadores se buscan case-sensitive donde importa
    assert "NUNCA" in low
    assert "pregunt" in low.lower(), "el prompt debe prohibir preguntar al operador"
    assert "infer" in low.lower(), "el prompt debe ordenar inferir defaults seguros"
    assert "[INF]" in low, "los supuestos inferidos se documentan con marca [INF]"
    # reglas anti-alucinación preexistentes intactas
    assert "[V]" in low and "[NV]" in low
    assert "<<<DOC" in low


def test_agente_documenter_usa_el_prompt_endurecido():
    from agents.documenter import DocumenterAgent
    from services.doc_documenter import _DEFAULT_DOCUMENTADOR_PROMPT

    assert DocumenterAgent().system_prompt() == _DEFAULT_DOCUMENTADOR_PROMPT


def test_agent_md_runtime_tiene_paridad_de_autonomia():
    """El runtime CLI lee backend/Stacky/agents/Documentador.agent.md (gitignored):
    debe tener la misma regla de autonomía. Se skipea si el archivo no existe
    (checkout fresco sin agentes materializados)."""
    agent_md = (Path(__file__).resolve().parents[1]
                / "Stacky" / "agents" / "Documentador.agent.md")
    if not agent_md.is_file():
        pytest.skip("Documentador.agent.md no materializado en este checkout")
    text = agent_md.read_text(encoding="utf-8")
    assert "pregunt" in text.lower()
    assert "infer" in text.lower()
    assert "[INF]" in text
