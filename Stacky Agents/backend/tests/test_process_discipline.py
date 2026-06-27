"""Tests de disciplina de procesos (Plan 67)."""
import os
from unittest import mock

import pytest
from services.process_discipline import (
    decide_process_action,
    DisciplineDecision,
    _contains_create_instruction,
    _contains_no_create_prefix,
)


# PD-01: instrucción explícita "crear nuevo proceso" → CREATE
def test_pd01_explicit_create_instruction():
    """Instrucción explícita de crear nuevo proceso → action=CREATE."""
    catalog = [
        {"name": "Mul2Bane", "purpose": "Punto de entrada de la carga", "kind": "carga"},
    ]
    decision = decide_process_action(
        title="Nuevo requerimiento",
        description="Se debe crear un nuevo proceso de carga que procesar archivo X",
        process_catalog=catalog,
    )
    assert decision.action == "CREATE"
    assert decision.instruction_present is True
    assert decision.confidence >= 0.9
    assert "explícita" in decision.reason.lower()


# PD-02: prefijo "modificar" + "proceso" → REUSE (no es creación)
def test_pd02_modify_prefix_is_not_create():
    """Prefijo 'modificar proceso' NO debe interpretarse como creación."""
    catalog = [
        {"name": "Mul2Bane", "purpose": "Punto de entrada de la carga", "kind": "carga"},
    ]
    decision = decide_process_action(
        title="Ajuste Mul2Bane",
        description="Modificar proceso Mul2Bane para agregar campo CLESPECIAL",
        process_catalog=catalog,
    )
    assert decision.instruction_present is False
    assert decision.action == "REUSE"
    assert decision.process_name == "Mul2Bane"


# PD-03: similitud con proceso existente → REUSE
def test_pd03_similarity_triggers_reuse():
    """Coincidencia por similitud de vocabulario → REUSE."""
    catalog = [
        {"name": "Mul2Bane", "purpose": "Lee interfaces de entrada y las carga en tablas IN_", "kind": "carga"},
        {"name": "RsExtrae", "purpose": "Genera interfaces de salida", "kind": "reporte"},
    ]
    decision = decide_process_action(
        title="Carga de clientes",
        description="Procesar archivo de clientes y cargarlo en base de datos",
        process_catalog=catalog,
    )
    assert decision.action == "REUSE"
    assert decision.process_name == "Mul2Bane"
    assert decision.confidence >= 0.4


# PD-04: sin coincidencia clara y sin instrucción → CREATE con baja confianza
def test_pd04_no_match_no_instruction():
    """Sin coincidencia y sin instrucción explícita → CREATE pero con baja confianza."""
    catalog = [
        {"name": "RsExtrae", "purpose": "Genera interfaces de salida", "kind": "reporte"},
    ]
    decision = decide_process_action(
        title="Algoritmo de scoring",
        description="Implementar lógica de scoring de riesgo",
        process_catalog=catalog,
    )
    assert decision.action == "CREATE"
    assert decision.confidence < 0.5
    assert "similitud" in decision.reason.lower() or "no se encontró" in decision.reason.lower()


# PD-05: sin catálogo → CREATE con confianza 0
def test_pd05_no_catalog():
    """Sin catálogo de procesos → CREATE con confianza 0 (fallback)."""
    decision = decide_process_action(
        title="Cualquier tarea",
        description="Descripción cualquiera",
        process_catalog=None,
    )
    assert decision.action == "CREATE"
    assert decision.confidence == 0.0
    assert "no hay catálogo" in decision.reason.lower()


# PD-06: build_discipline_block genera texto no vacío
def test_pd06_build_discipline_block_non_empty():
    """El bloque de disciplina siempre genera texto."""
    from services.process_discipline import build_discipline_block

    decision_reuse = DisciplineDecision(
        action="REUSE",
        process_name="Mul2Bane",
        reason="Coincide con catálogo",
        confidence=0.8,
        instruction_present=False,
    )
    block_reuse = build_discipline_block(decision_reuse)
    assert block_reuse.strip()
    assert "REUTILIZAR" in block_reuse
    assert "Mul2Bane" in block_reuse

    decision_create = DisciplineDecision(
        action="CREATE",
        process_name=None,
        reason="Instrucción explícita",
        confidence=0.95,
        instruction_present=True,
    )
    block_create = build_discipline_block(decision_create)
    assert block_create.strip()
    assert "CREAR" in block_create or "crear" in block_create.lower()


# PD-07: [ADICIÓN ARQUITECTO] integración del wiring — flag ON/OFF gobierna el bloque
def test_pd07_wiring_flag_governs_block(monkeypatch):
    """Con flag ON + catálogo → bloque 'process-discipline' presente y meta.action seteado.
    Con flag OFF → ausente (byte-idéntico). Sin catálogo → ausente."""
    from services.context_enrichment import _inject_process_discipline_block

    fake_profile = {"process_catalog": [
        {"name": "Mul2Bane", "purpose": "carga de interfaces de entrada", "kind": "carga"},
    ]}

    def _noop(level, msg=""):
        return None

    base_blocks: list[dict] = []

    # ON + catálogo → bloque presente
    with mock.patch("services.client_profile.load_client_profile", return_value=fake_profile):
        with mock.patch("services.harness_flags.get_flag", return_value=True):
            result_on = _inject_process_discipline_block(
                blocks=list(base_blocks),
                project_name="PACIFICO",
                title="Carga de clientes",
                description="Procesar archivo de clientes",
                log=_noop,
            )
    ids_on = {b.get("id") for b in result_on}
    assert "process-discipline" in ids_on
    disc = next(b for b in result_on if b.get("id") == "process-discipline")
    assert disc["meta"]["action"] in {"REUSE", "CREATE"}
    assert "content" in disc and disc["content"].strip()

    # OFF → ausente (byte-idéntico)
    with mock.patch("services.harness_flags.get_flag", return_value=False):
        result_off = _inject_process_discipline_block(
            blocks=list(base_blocks),
            project_name="PACIFICO",
            title="Carga de clientes",
            description="Procesar archivo de clientes",
            log=_noop,
        )
    ids_off = {b.get("id") for b in result_off}
    assert "process-discipline" not in ids_off

    # Sin catálogo → ausente
    with mock.patch("services.client_profile.load_client_profile", return_value={"process_catalog": []}):
        with mock.patch("services.harness_flags.get_flag", return_value=True):
            result_nocat = _inject_process_discipline_block(
                blocks=list(base_blocks),
                project_name="PACIFICO",
                title="x",
                description="y",
                log=_noop,
            )
    ids_nocat = {b.get("id") for b in result_nocat}
    assert "process-discipline" not in ids_nocat


# PD-08 (C5): negación ampliada — "nunca crees" no debe contar como instrucción de crear
def test_pd08_negation_never_create():
    """'nunca crees un proceso' NO debe disparar CREATE por instrucción explícita."""
    catalog = [{"name": "Mul2Bane", "purpose": "carga", "kind": "carga"}]
    decision = decide_process_action(
        title="Recordatorio",
        description="Nunca crees un nuevo proceso sin autorización",
        process_catalog=catalog,
    )
    assert decision.instruction_present is False
