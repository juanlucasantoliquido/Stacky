"""Plan 209 F0 — Schema del objeto canónico ValidationPlaybook + scope user-facing."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

from services.validation_playbook import (  # noqa: E402
    DEGRADED_MESSAGE,
    SECTION_MARKER,
    SECTION_TITLE,
    USER_FACING_AGENT_TYPES,
    ValidationPlaybook,
    ValidationStep,
    assert_no_invented_steps,
    is_user_facing,
)


def test_playbook_roundtrip():
    pb = ValidationPlaybook(
        status="enriched",
        steps=[
            ValidationStep(n=1, action="Entrar al detalle del cliente",
                           expected_result="Se abre la ficha", source="func-docs:alta-cliente"),
            ValidationStep(n=2, action="Asignar una obligación",
                           expected_result="Aparece en el inicio", source="catalog:IncHost"),
        ],
        sources=["func-docs:alta-cliente", "catalog:IncHost"],
        confidence=0.7,
        degraded_reason=None,
    )
    back = ValidationPlaybook.from_dict(pb.to_dict())

    assert back == pb
    assert back.steps[1].source == "catalog:IncHost"
    assert back.to_dict()["steps"][0]["expected_result"] == "Se abre la ficha"


def test_from_dict_defensivo():
    pb = ValidationPlaybook.from_dict({})
    assert pb.status == "disabled"
    assert pb.steps == []
    assert ValidationPlaybook.from_dict(None).status == "disabled"


@pytest.mark.parametrize("status", ["agent_provided", "enriched", "degraded", "disabled"])
def test_status_values_validos(status):
    assert ValidationPlaybook(status=status, steps=[], sources=[], confidence=0.0,
                              degraded_reason=None).status == status


@pytest.mark.parametrize("bad", ["ok", "", "AGENT_PROVIDED", None, "provided"])
def test_status_invalido_lanza(bad):
    with pytest.raises(ValueError):
        ValidationPlaybook(status=bad, steps=[], sources=[], confidence=0.0,
                           degraded_reason=None)


def test_degraded_message_constante():
    assert "referente" in DEGRADED_MESSAGE
    assert not any(ch.isdigit() for ch in DEGRADED_MESSAGE), (
        "el mensaje de degradación no debe traer números de pasos"
    )
    assert SECTION_TITLE == "Cómo validar esto (como usuario del sistema RS)"
    assert SECTION_MARKER == 'data-stacky="validation-playbook"'


def test_step_source_required():
    """Un paso sin fuente es una violación detectable (el validador de F5)."""
    pb = ValidationPlaybook(
        status="enriched",
        steps=[
            ValidationStep(n=1, action="paso ok", expected_result="r", source="func-docs:x"),
            ValidationStep(n=2, action="paso huérfano", expected_result="r", source=""),
            ValidationStep(n=3, action="fuente en blanco", expected_result="r", source="   "),
        ],
        sources=[], confidence=0.5, degraded_reason=None,
    )
    violaciones = assert_no_invented_steps(pb)

    assert len(violaciones) == 2, violaciones
    assert "2" in violaciones[0] and "3" in violaciones[1]
    assert assert_no_invented_steps(
        ValidationPlaybook(status="enriched",
                           steps=[ValidationStep(1, "a", "b", "func-docs:x")],
                           sources=[], confidence=0.5, degraded_reason=None)
    ) == []


def test_user_facing_allowlist():
    assert is_user_facing("functional") is True
    assert is_user_facing("developer") is True
    assert is_user_facing("incident_dev") is True
    assert is_user_facing("qa") is True
    assert is_user_facing("technical") is True
    assert is_user_facing("business") is True

    assert is_user_facing("devops") is False
    assert is_user_facing("__critic__") is False
    assert is_user_facing("incident") is False
    assert is_user_facing("pr_review") is False
    assert is_user_facing("Documentador") is False
    assert is_user_facing("evolution_mutator") is False
    assert is_user_facing("debug") is False
    assert is_user_facing("custom") is False
    assert is_user_facing(None) is False
    assert is_user_facing("") is False

    assert isinstance(USER_FACING_AGENT_TYPES, frozenset)


def test_allowlist_solo_tipos_de_agente_reales():
    """Cada tipo de la allowlist debe existir como `type` de un agente real."""
    import re

    agents_dir = ROOT / "agents"
    declarados = set()
    for path in agents_dir.glob("*.py"):
        declarados.update(
            re.findall(r'^\s{4}type\s*=\s*"([^"]+)"', path.read_text(encoding="utf-8"),
                       re.MULTILINE)
        )

    faltantes = USER_FACING_AGENT_TYPES - declarados
    assert faltantes == set(), f"tipos inexistentes en agents/: {sorted(faltantes)}"
