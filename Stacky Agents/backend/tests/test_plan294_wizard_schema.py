"""tests/test_plan294_wizard_schema.py — Plan 294 F4.

Las preguntas del paso 3 salen de DATOS, no de `if`s: agregar un tipo de
pipeline es agregar una entrada, no reescribir el asistente.

El caso que mas valor tiene es el 2 (anti-formulario-generico) con su contraste
en el 3: sin el par, "adaptado al objetivo" es una intencion.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

_BACKEND = pathlib.Path(__file__).resolve().parents[1]

_TABLA_KIND = {
    "compilar_validar": "ci",
    "ejecutar_tests": "ci",
    "generar_artefacto": "ci",
    "desplegar": "cd",
    "ci_completo": "ci",
    "entrega_completa": "ci_cd",
    "calidad_seguridad": "quality",
    "modificar_existente": "ci",
    "describir_libre": "ci",
}


def test_los_nueve_objetivos_estan_completos():
    from services.pipeline_wizard_schema import WIZARD_GOALS

    assert len(WIZARD_GOALS) == 9
    ids = [g.id for g in WIZARD_GOALS]
    assert len(set(ids)) == 9, f"ids repetidos: {ids}"
    for g in WIZARD_GOALS:
        assert g.help.strip(), f"{g.id} sin ayuda"
        assert g.example.strip(), f"{g.id} sin ejemplo"
        assert g.label.strip(), f"{g.id} sin etiqueta"


def test_anti_formulario_generico_en_ejecutar_tests():
    """El objetivo mas simple no puede pedir datos de despliegue ni de artefactos."""
    from services.pipeline_wizard_schema import questions_for

    qs = questions_for("ejecutar_tests", stack="node")
    assert len(qs) <= 4, [q.id for q in qs]
    prohibidas = [q.id for q in qs if q.id.startswith(("deploy_", "artifact_"))]
    assert prohibidas == [], prohibidas


def test_contraste_desplegar_si_pregunta_por_el_despliegue():
    """MITAD DE CONTRASTE del caso anterior: si el esquema devolviera siempre las
    mismas preguntas, o siempre ninguna, uno de los dos casos caeria."""
    from services.pipeline_wizard_schema import questions_for

    qs = questions_for("desplegar", stack="node")
    assert any(q.id.startswith("deploy_") for q in qs), [q.id for q in qs]


def test_objetivos_distintos_piden_cosas_distintas():
    from services.pipeline_wizard_schema import questions_for

    a = {q.id for q in questions_for("compilar_validar", stack="dotnet")}
    b = {q.id for q in questions_for("desplegar", stack="dotnet")}
    assert a != b


def test_r9_no_se_pregunta_lo_que_el_sondeo_ya_trajo():
    from services.pipeline_wizard_schema import questions_for

    sin_saber = questions_for("compilar_validar", stack="dotnet")
    assert any(q.autofilled_from == "build_command" for q in sin_saber)

    sabiendo = questions_for(
        "compilar_validar", stack="dotnet", known={"build_command": "dotnet build"}
    )
    assert not any(q.autofilled_from == "build_command" for q in sabiendo)


def test_depends_on_oculta_lo_que_no_corresponde():
    from services.pipeline_wizard_schema import questions_for, visible_questions

    qs = questions_for("desplegar", stack="node", has_docker=True)
    visibles = {q.id for q in visible_questions(qs, {"needs_docker": "no"})}
    assert "docker_registry" not in visibles
    assert "docker_tag" not in visibles

    con_docker = {q.id for q in visible_questions(qs, {"needs_docker": "si"})}
    assert "docker_registry" in con_docker


def test_defaults_seguros_por_stack():
    from services.pipeline_wizard_schema import default_answers

    assert default_answers("ejecutar_tests", "dotnet", "ado")["test_command"] == "dotnet test"
    assert default_answers("ejecutar_tests", "node", "ado")["test_command"] == "npm test"
    assert default_answers("ejecutar_tests", "python", "ado")["test_command"] == "pytest"


def test_las_veintisiete_combinaciones_no_lanzan_ni_repiten_ids():
    from services.pipeline_wizard_schema import WIZARD_GOALS, questions_for

    for stack in ("python", "node", "dotnet"):
        for goal in WIZARD_GOALS:
            qs = questions_for(goal.id, stack=stack, provider="ado")
            ids = [q.id for q in qs]
            assert len(ids) == len(set(ids)), f"{goal.id}/{stack}: ids repetidos {ids}"


def test_needs_inventory_solo_para_modificar_existente():
    from services.pipeline_wizard_schema import WIZARD_GOALS

    con_inventario = {g.id for g in WIZARD_GOALS if g.needs_inventory}
    assert con_inventario == {"modificar_existente"}


def test_el_modulo_es_puro():
    fuente = (_BACKEND / "services" / "pipeline_wizard_schema.py").read_text(
        encoding="utf-8"
    )
    for prohibida in ("requests", "urllib", "os.walk", "open("):
        assert prohibida not in fuente, f"pipeline_wizard_schema.py usa {prohibida}"


def test_el_tipo_de_cada_objetivo_esta_fijado():
    """Sin esto, 4 de los 9 quedaban con tipo indefinido y cada implementador
    elegia uno distinto. Se compara el dict COMPLETO, no una pertenencia."""
    from services.pipeline_intent import PIPELINE_KINDS
    from services.pipeline_wizard_schema import WIZARD_GOALS

    real = {g.id: g.pipeline_kind for g in WIZARD_GOALS}
    assert real == _TABLA_KIND
    assert set(real.values()) <= set(PIPELINE_KINDS)
