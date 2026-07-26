"""Plan 250 F1 — verbos de edicion cerrados: EditIntent -> EditPlan. 10 tests.

Lista CERRADA de 7 verbos, catalogo cerrado de tareas, y determinismo byte a byte:
el no determinismo del modelo se concentra en el intent (F5), nunca en el YAML.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from services import pipeline_patcher as pp
from services.cicd_task_catalog import PROFILE_DOTNET_FRAMEWORK as PERFIL

BACKEND = Path(__file__).resolve().parent.parent
GOLDEN = BACKEND / "tests" / "fixtures" / "cicd_nl" / "golden"
STEPS = "stages[0].jobs[0].steps"


def _leer(nombre: str) -> str:
    return (GOLDEN / nombre).read_text(encoding="utf-8")


def _comentarios(texto: str) -> int:
    return sum(1 for l in texto.splitlines() if l.lstrip().startswith("#"))


def _refs(texto: str) -> list:
    doc = yaml.safe_load(texto)
    pasos = doc["stages"][0]["jobs"][0]["steps"]
    return [p.get("task") for p in pasos if isinstance(p, dict)]


# ── 1 ────────────────────────────────────────────────────────────────────────
def test_add_step_al_final_de_ci_cd_online():
    texto = _leer("ci-cd-online.yml")
    intent = pp.EditIntent(
        verb="add_step", target_path=STEPS, position="end",
        task_ref="PublishCodeCoverageResults@2",
        inputs={"summaryFileLocation": "$(Agent.TempDirectory)/**/coverage.cobertura.xml"},
        display_name="Publicar cobertura")
    ops, errores = pp.plan_edit(texto, intent, profile=PERFIL)
    assert errores == (), errores
    assert len(ops) == 1
    assert ops[0].kind == "insert_after"
    assert ops[0].anchor_path == "%s[5]" % STEPS
    res = pp.apply_ops(texto, ops)
    assert res.ok, res.errors
    assert yaml.safe_load(res.text) is not None
    assert _refs(res.text)[-1] == "PublishCodeCoverageResults@2"
    assert _comentarios(res.text) == 47


# ── 2 ────────────────────────────────────────────────────────────────────────
def test_add_step_antes_de_una_ref():
    texto = _leer("ci-cd-online.yml")
    intent = pp.EditIntent(
        verb="add_step", target_path=STEPS, position="before",
        anchor_ref="PublishBuildArtifacts@1",
        task_ref="CopyFiles@2",
        inputs={"SourceFolder": "$(Build.SourcesDirectory)", "Contents": "**/*.dll",
                "TargetFolder": "$(Build.ArtifactStagingDirectory)", "flattenFolders": "true"},
        display_name="Copiar binarios")
    ops, errores = pp.plan_edit(texto, intent, profile=PERFIL)
    assert errores == (), errores
    res = pp.apply_ops(texto, ops)
    assert res.ok, res.errors
    refs = _refs(res.text)
    assert refs.index("CopyFiles@2") == refs.index("PublishTestResults@2") + 1
    assert refs.index("CopyFiles@2") == refs.index("PublishBuildArtifacts@1") - 1
    # el comentario que presenta a PublishBuildArtifacts@1 sigue pegado a EL, no al nuevo
    lineas = res.text.splitlines()
    i = next(n for n, l in enumerate(lineas) if "PublishBuildArtifacts@1" in l)
    assert "# 5. Publicar artefacto de build" in lineas[i - 1]


# ── 3 ────────────────────────────────────────────────────────────────────────
def test_remove_step_por_ref():
    """El paso se va CON el comentario que lo presenta.

    El plan decia "menos los 2 propios de ese paso": medido, el bloque de
    PublishTestResults@2 no contiene NINGUN comentario adentro; el unico comentario
    suyo es el que lo introduce (`# 4. Publicar resultados de tests en ADO`, linea
    112 1-based), que §2.3 le saca al paso anterior. Sin llevarselo, queda huerfano
    sobre el paso equivocado.
    """
    texto = _leer("ci-cd-online.yml")
    assert _comentarios(texto) == 47
    intent = pp.EditIntent(verb="remove_step", target_path=STEPS,
                           anchor_ref="PublishTestResults@2")
    ops, errores = pp.plan_edit(texto, intent, profile=PERFIL)
    assert errores == (), errores
    assert len(ops) == 1 and ops[0].kind == "delete"
    res = pp.apply_ops(texto, ops)
    assert res.ok, res.errors
    assert "PublishTestResults@2" not in res.text
    assert "# 4. Publicar resultados de tests en ADO" not in res.text
    assert _comentarios(res.text) == 46
    assert _refs(res.text) == ["NuGetToolInstaller@1", "NuGetCommand@2", "VSBuild@1",
                               "DotNetCoreCLI@2", "PublishBuildArtifacts@1"]


# ── 4 ────────────────────────────────────────────────────────────────────────
def test_move_step_reordena_sin_reescribir():
    texto = _leer("ci-cd-online.yml")
    intent = pp.EditIntent(verb="move_step", target_path=STEPS,
                           anchor_ref="PublishTestResults@2", position="after",
                           values=("PublishBuildArtifacts@1",))
    ops, errores = pp.plan_edit(texto, intent, profile=PERFIL)
    assert errores == (), errores
    assert len(ops) == 2
    res = pp.apply_ops(texto, ops)
    assert res.ok, res.errors
    assert len(res.hunks) == 2
    refs = _refs(res.text)
    assert refs.index("PublishTestResults@2") == refs.index("PublishBuildArtifacts@1") + 1
    assert _comentarios(res.text) == 47, "ningun comentario se pierde al reordenar"


# ── 5 ────────────────────────────────────────────────────────────────────────
def test_set_task_input_cambia_una_sola_linea():
    texto = _leer("ci-cd-online.yml")
    intent = pp.EditIntent(verb="set_task_input", target_path=STEPS,
                           anchor_ref="VSBuild@1", task_ref="VSBuild@1",
                           inputs={"configuration": "Debug"})
    ops, errores = pp.plan_edit(texto, intent, profile=PERFIL)
    assert errores == (), errores
    assert len(ops) == 1 and ops[0].kind == "replace"
    res = pp.apply_ops(texto, ops)
    assert res.ok, res.errors
    assert len(res.hunks) == 1
    h = res.hunks[0]
    assert len(h.before) == 1 and len(h.after) == 1
    assert "configuration: Debug" in h.after[0]
    assert _comentarios(res.text) == 47


# ── 6 ────────────────────────────────────────────────────────────────────────
def test_add_stage_respeta_el_estilo_del_archivo():
    texto = _leer("cd-deploy-test.yml")
    indice, _ = pp.build_anchor_index(texto)
    assert indice["stages"].dash_col == 2, "en este archivo los stages van indentados"
    intent = pp.EditIntent(verb="add_stage", position="end",
                           display_name="SmokeTests", values=("Pruebas de humo",))
    ops, errores = pp.plan_edit(texto, intent, profile=PERFIL)
    assert errores == (), errores
    assert ops[0].lines[0] == "  - stage: SmokeTests"
    res = pp.apply_ops(texto, ops)
    assert res.ok, res.errors
    assert _comentarios(res.text) == _comentarios(texto)


# ── 7 ────────────────────────────────────────────────────────────────────────
def test_tarea_fuera_del_catalogo_rechazada():
    texto = _leer("ci-cd-online.yml")
    intent = pp.EditIntent(verb="add_step", target_path=STEPS, position="end",
                           task_ref="MSBuild@1", inputs={})
    ops, errores = pp.plan_edit(texto, intent, profile=PERFIL)
    assert ops == ()
    assert any("MSBuild@1" in e and "catalogo" in e for e in errores)


# ── 8 ────────────────────────────────────────────────────────────────────────
def test_input_invalido_rechazado():
    texto = _leer("ci-cd-online.yml")
    intent = pp.EditIntent(verb="set_task_input", target_path=STEPS,
                           anchor_ref="VSBuild@1", task_ref="VSBuild@1",
                           inputs={"msbuildArguments": "x"})
    ops, errores = pp.plan_edit(texto, intent, profile=PERFIL)
    assert ops == ()
    assert any("msbuildArguments" in e for e in errores)
    assert any("msbuildArgs" in e for e in errores), "el error nombra el input REAL"


# ── 9 ────────────────────────────────────────────────────────────────────────
def test_display_name_multilinea_rechazado():
    texto = _leer("ci-cd-online.yml")
    intent = pp.EditIntent(verb="add_step", target_path=STEPS, position="end",
                           task_ref="PublishCodeCoverageResults@2",
                           inputs={"summaryFileLocation": "x"},
                           display_name="a\nb")
    ops, errores = pp.plan_edit(texto, intent, profile=PERFIL)
    assert ops == ()
    assert any("una sola linea" in e for e in errores)


# ── 10 ───────────────────────────────────────────────────────────────────────
def test_determinismo():
    texto = _leer("ci-cd-online.yml")
    intent = pp.EditIntent(
        verb="add_step", target_path=STEPS, position="end",
        task_ref="PublishCodeCoverageResults@2",
        inputs={"summaryFileLocation": "cov.xml"}, display_name="Cobertura")
    a, ea = pp.plan_edit(texto, intent, profile=PERFIL)
    b, eb = pp.plan_edit(texto, intent, profile=PERFIL)
    assert (a, ea) == (b, eb)
    assert pp.apply_ops(texto, a).text == pp.apply_ops(texto, b).text


def test_verbo_fuera_de_la_lista_cerrada():
    ops, errores = pp.plan_edit(_leer("ci-cd-online.yml"),
                                pp.EditIntent(verb="delete_pipeline"), profile=PERFIL)
    assert ops == ()
    assert errores and "delete_pipeline" in errores[0]
    assert len(pp.EDIT_VERBS) == 7
