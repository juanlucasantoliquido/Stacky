"""Plan 213 F3 — Los prompts de los analistas ya no los mandan a frenar.

La política de F2 se inyecta por run_contract, pero si el .agent.md sigue
diciendo "publicá una consulta pre-bloqueo y esperá", el agente recibe dos
instrucciones opuestas. Esta fase saca la contradicción de raíz.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

_AGENTS = ROOT / "Stacky" / "agents"
_DEPLOY = ROOT.parent / "DeployStackyAgents" / "Stacky" / "agents"
_TEC = "TechnicalAnalyst.v2.agent.md"
_FUN = "FunctionalAnalyst.agent.md"


def _leer(nombre: str, base: Path = _AGENTS) -> str:
    return (base / nombre).read_text(encoding="utf-8")


def test_technical_no_longer_instructs_pre_block_query():
    """La frase que hoy frena el ticket no puede seguir en el prompt."""
    texto = _leer(_TEC)

    assert "pre-bloqueo" not in texto
    assert "CONSULTA TÉCNICA" not in texto


def test_technical_declares_the_canonical_format():
    texto = _leer(_TEC)

    assert "[SUPUESTO:" in texto
    assert "[PENDIENTE:" in texto
    assert "Supuestos asumidos" in texto


def test_technical_advances_when_only_assumptions():
    """El punto del plan: supuestos declarados NO frenan el ticket."""
    texto = _leer(_TEC)

    assert "Tener supuestos declarados **no** te saca de este caso" in texto


def test_technical_still_never_applies_blocked_state():
    """Human-in-the-loop innegociable: el bloqueo sigue siendo humano."""
    texto = _leer(_TEC)

    assert "NUNCA aplica `blocked_state` por su cuenta" in texto


def test_functional_ambiguity_rule_points_to_a_real_section():
    """La regla vieja apuntaba a 'Preguntas abiertas', una sección FANTASMA."""
    texto = _leer(_FUN)

    assert "Preguntas abiertas" not in texto
    assert "Cero ambigüedad NO significa frenar" in texto
    assert "## 8. Supuestos asumidos" in texto, \
        "la sección que la regla nombra tiene que existir en la plantilla"


def test_functional_declares_the_canonical_format():
    texto = _leer(_FUN)

    assert "[SUPUESTO: <interpretación> | base: <doc/módulo> | impacto: alto|medio|bajo]" in texto
    assert "[PENDIENTE:" in texto


def test_versions_were_bumped():
    assert 'version: "2.1.0"' in _leer(_TEC)
    assert 'version: "2.2.0"' in _leer(_FUN)


def test_deploy_mirror_matches_dev():
    """El deploy es foto fiel del dev: si diverge, corre con el prompt viejo."""
    for nombre in (_TEC, _FUN):
        assert _leer(nombre, _DEPLOY) == _leer(nombre), \
            f"{nombre}: el espejo del deploy quedó desactualizado"


def test_python_system_prompts_agree_with_the_agent_md():
    """Paridad copilot: el prompt Python no puede decir lo contrario."""
    from agents.functional import FunctionalAgent
    from agents.technical import TechnicalAgent

    tecnico = TechnicalAgent().system_prompt()
    funcional = FunctionalAgent().system_prompt()

    assert "consulta al humano" not in tecnico
    assert "supuesto" in tecnico.lower()
    assert "supuesto" in funcional.lower()
