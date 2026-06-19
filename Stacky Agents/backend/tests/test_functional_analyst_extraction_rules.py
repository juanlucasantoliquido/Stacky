"""Contrato del prompt FunctionalAnalyst.agent.md (fix sobre-división de Tasks).

Regresión del bug del Epic "3 EP 01": v2.0.0 proponía 3 Tasks cuando debía
proponer 1. El fix porta de AnalistaFuncionalPacifico las reglas de extracción
explícitas. Estos asserts garantizan que no se vuelvan a perder en una edición.
"""
from __future__ import annotations

from pathlib import Path

import pytest

AGENT_FILE = (
    Path(__file__).resolve().parent.parent
    / "Stacky" / "agents" / "FunctionalAnalyst.agent.md"
)


@pytest.fixture(scope="module")
def prompt() -> str:
    assert AGENT_FILE.is_file(), f"No existe {AGENT_FILE}"
    return AGENT_FILE.read_text(encoding="utf-8")


def test_single_requirement_fallback_present(prompt):
    # El guardrail clave: sin <hr><h2> → un único requisito.
    assert "<hr><h2>" in prompt
    assert "ÚNICO requisito" in prompt or "único requisito" in prompt


def test_no_oversplit_rule_present(prompt):
    assert "No sobre-dividas" in prompt or "sobre-dividas" in prompt


def test_preserve_rf_ids_rule_present(prompt):
    assert "No renumeres" in prompt


def test_confirm_total_before_loop(prompt):
    assert "Confirma el total" in prompt or "confirmar el total" in prompt.lower()


def test_version_bumped(prompt):
    assert 'version: "2.1.0"' in prompt
    assert "FunctionalAnalyst v2.1.0" in prompt


def test_process_catalog_rule_present(prompt):
    """v2.1.0 (R-PROCESOS): el agente debe leer el process_catalog y especificar
    los procesos por su propósito, no por su nombre. Cierra el bug 'infirió mal el
    punto de entrada de la carga'."""
    assert "process_catalog" in prompt
    assert "R-PROCESOS" in prompt
    assert "PROPÓSITO" in prompt or "propósito" in prompt


def test_uses_real_ado_epic_id_not_human_ep_label(prompt):
    assert "ADO_EPIC_ID" in prompt
    assert "epic_ado_id" in prompt
    assert '"parent_id": {ADO_EPIC_ID}' in prompt
    assert "No uses el numero de la etiqueta humana" in prompt


def test_json_validity_rule_present(prompt):
    """v2.0.2: el agente debe producir JSON VÁLIDO. El bug real (RSSICREA) fue un
    pending-task.json con comillas dobles sin escapar en description_html, que
    rompía el JSON y hacía que Stacky descartara el archivo en silencio. El prompt
    debe instruir explícitamente a evitar/escapar las comillas."""
    assert "JSON VÁLIDO" in prompt or "JSON válido" in prompt
    assert "&quot;" in prompt
    # Debe advertir sobre las comillas dobles sin escapar.
    assert "sin escapar" in prompt or "escapá" in prompt or "escapar" in prompt
