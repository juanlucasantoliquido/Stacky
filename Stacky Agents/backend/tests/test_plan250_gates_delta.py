"""Plan 250 F2 — gates por DELTA + sello de preservacion. 12 tests.

Los dos tests que importan son el 1 y el 2, y hacen falta LOS DOS: sin el 1 el gate es
inutil de estricto (bloquea por faltas ajenas y el operador aprende a ignorarlo); sin
el 2 el gate es una mentira (deja pasar lo que rompe).
"""
from __future__ import annotations

from pathlib import Path

from services import pipeline_diff as pd
from services import pipeline_patcher as pp
from services.cicd_task_catalog import PROFILE_DOTNET_FRAMEWORK as PERFIL
from services.pipeline_lint import SEV_ERROR

BACKEND = Path(__file__).resolve().parent.parent
GOLDEN = BACKEND / "tests" / "fixtures" / "cicd_nl" / "golden"
STEPS = "stages[0].jobs[0].steps"


def _leer(nombre: str) -> str:
    return (GOLDEN / nombre).read_text(encoding="utf-8")


def _revisar(texto: str, intent: pp.EditIntent, **kw):
    ops, errores = pp.plan_edit(texto, intent, profile=PERFIL)
    assert errores == (), errores
    res = pp.apply_ops(texto, ops)
    assert res.ok, res.errors
    return res, pd.review_patch(texto, res.text, res.hunks, profile=PERFIL,
                                verb=intent.verb, **kw)


def _codigos(review) -> set:
    return {f.code for g in review.gates for f in g.new_errors}


# ── 1 ────────────────────────────────────────────────────────────────────────
def test_error_preexistente_no_bloquea_la_edicion():
    """nightly-build-online.yml tiene un `- script: |` crudo y real en produccion.
    Un gate estricto sobre el documento entero lo marcaria RS008 y bloquearia un
    cambio que el operador no pidio sobre ese paso."""
    texto = _leer("nightly-build-online.yml")
    indice, _ = pp.build_anchor_index(texto)
    steps = sorted((a.start_line, p) for p, a in indice.items()
                   if a.kind == "seq" and p.endswith("steps"))[0][1]
    intent = pp.EditIntent(verb="set_task_input", target_path=steps,
                           anchor_ref="VSBuild@1", task_ref="VSBuild@1",
                           inputs={"configuration": "Debug"})
    _res, review = _revisar(texto, intent)
    assert review.ok is True, review.summary


# ── 2 ────────────────────────────────────────────────────────────────────────
def test_patch_que_introduce_error_nuevo_no_se_ofrece():
    """KPI-3 — ADO-369 detectado tambien en la ruta de EDICION."""
    texto = _leer("ci-cd-online.yml")
    indice, _ = pp.build_anchor_index(texto)
    anchor = indice[STEPS]
    bloque = pp.render_block(
        {"task": "IISWebAppDeploymentOnMachineGroup@0",
         "displayName": "Desplegar", "inputs": {"WebSiteName": "AgendaWeb"}},
        key_col=anchor.key_col, dash_col=anchor.dash_col)
    op = pp.EditOp("insert_after", anchor.item_paths[-1], bloque, "deploy")
    res = pp.apply_ops(texto, (op,))
    assert res.ok, res.errors
    review = pd.review_patch(texto, res.text, res.hunks, profile=PERFIL, verb="add_step")
    assert review.ok is False
    assert "RS002" in _codigos(review)


# ── 3 ────────────────────────────────────────────────────────────────────────
def test_paso_insertado_se_evalua_en_nl_strict():
    texto = _leer("ci-cd-online.yml")
    indice, _ = pp.build_anchor_index(texto)
    anchor = indice[STEPS]
    bloque = pp.render_block(
        {"task": "PowerShell@2", "displayName": "Inline",
         "inputs": {"targetType": "inline", "script": "Write-Host hola"}},
        key_col=anchor.key_col, dash_col=anchor.dash_col)
    op = pp.EditOp("insert_after", anchor.item_paths[-1], bloque, "ps inline")
    res = pp.apply_ops(texto, (op,))
    assert res.ok, res.errors
    review = pd.review_patch(texto, res.text, res.hunks, profile=PERFIL, verb="add_step")
    estricto = next(g for g in review.gates if g.gate == pd.GATE_SEM_NL_STRICT)
    assert estricto.passed is False
    assert "RS004" in {f.code for f in estricto.new_errors}
    # y en AUDIT sobre el documento completo, RS004 NO corre
    auditoria = next(g for g in review.gates if g.gate == pd.GATE_SEM_AUDIT)
    assert "RS004" not in {f.code for f in auditoria.new_errors}
    assert review.ok is False


# ── 4 ────────────────────────────────────────────────────────────────────────
def test_indices_desplazados_no_cuentan_como_nuevos():
    texto = _leer("ci-cd-online.yml")
    intent = pp.EditIntent(
        verb="add_step", target_path=STEPS, position="before",
        anchor_ref="NuGetToolInstaller@1", task_ref="UseDotNet@2",
        inputs={"packageType": "sdk", "version": "8.0.x"}, display_name="SDK")
    _res, review = _revisar(texto, intent)
    for g in review.gates:
        assert g.new_errors == (), (g.gate, g.new_errors)
        assert g.new_warnings == (), (g.gate, g.new_warnings)


# ── 5 ────────────────────────────────────────────────────────────────────────
def test_findings_resueltos_se_reportan():
    """Un gate que solo sabe decir 'no' enseña a ignorarlo: lo que el patch ARREGLA
    tambien se muestra."""
    texto = ("stages:\n"
             "- stage: A\n"
             "  jobs:\n"
             "  - job: b\n"
             "    steps:\n"
             "    - checkout: self\n"
             "- stage: A\n"
             "  jobs:\n"
             "  - job: c\n"
             "    steps:\n"
             "    - checkout: self\n")
    antes = pd.lint_yaml(texto, "ado")
    assert any(f.severity == SEV_ERROR for f in antes.findings), "el stage duplicado"
    op = pp.EditOp("delete", "stages[1]", (), "quitar el stage duplicado")
    res = pp.apply_ops(texto, (op,))
    assert res.ok, res.errors
    review = pd.review_patch(texto, res.text, res.hunks, profile=PERFIL, verb="remove_step")
    total = [f for g in review.gates for f in g.resolved]
    assert total, "quitar la causa de un hallazgo tiene que reportarlo como resuelto"
    assert review.ok is True


# ── 6 ────────────────────────────────────────────────────────────────────────
def test_lint_delta_solo_reporta_lo_nuevo():
    antes = "stages:\n- stage: A\n- stage: A\n"
    r = pd.lint_yaml(antes, "ado")
    assert any(f.severity == SEV_ERROR for f in r.findings), "el fixture debe traer un error"
    despues = antes + "\n"
    review = pd.review_patch(antes, despues, (), profile=PERFIL)
    lint = next(g for g in review.gates if g.gate == pd.GATE_LINT)
    assert lint.new_errors == ()
    assert lint.passed is True


# ── 7 ────────────────────────────────────────────────────────────────────────
def test_sin_repo_root_rs006_se_declara_skipped():
    texto = _leer("ci-cd-online.yml")
    intent = pp.EditIntent(verb="set_task_input", target_path=STEPS,
                           anchor_ref="VSBuild@1", task_ref="VSBuild@1",
                           inputs={"configuration": "Debug"})
    _res, review = _revisar(texto, intent, repo_root=None)
    sem = next(g for g in review.gates if g.gate == pd.GATE_SEM_AUDIT)
    assert sem.skipped_reason
    assert "RS006" in sem.skipped_reason
    assert "validado" in sem.skipped_reason


# ── 8 ────────────────────────────────────────────────────────────────────────
def test_after_no_parsea_bloquea():
    texto = _leer("ci-cd-online.yml")
    review = pd.review_patch(texto, "stages: [\n", (), profile=PERFIL)
    assert review.ok is False
    assert "PL001" in _codigos(review)


# ── 9 ────────────────────────────────────────────────────────────────────────
def test_unsupported_se_informa_y_no_bloquea():
    texto = _leer("ci-batch.yml")
    indice, _ = pp.build_anchor_index(texto)
    steps = sorted((a.start_line, p) for p, a in indice.items()
                   if a.kind == "seq" and p.endswith("steps"))[0][1]
    anchor = indice[steps]
    bloque = pp.render_block({"task": "PublishCodeCoverageResults@2",
                              "inputs": {"summaryFileLocation": "cov.xml"}},
                             key_col=anchor.key_col, dash_col=anchor.dash_col)
    op = pp.EditOp("insert_after", anchor.item_paths[-1], bloque, "cobertura")
    res = pp.apply_ops(texto, (op,))
    assert res.ok, res.errors
    review = pd.review_patch(texto, res.text, res.hunks, profile=PERFIL, verb="add_step")
    assert "matrix" in review.unsupported
    assert review.preservation.unsupported_lost == ()


# ── 10 ───────────────────────────────────────────────────────────────────────
def test_lint_delta_no_usa_line_como_identidad():
    """C4 — el v1 tenia UNA sola _finding_key(code, message, location) y LintFinding
    NO tiene `location`: era un AttributeError. Y usar `line` habria marcado como
    nuevos TODOS los findings posteriores a una insercion."""
    from services.pipeline_lint import LintFinding

    f_antes = LintFinding("PL007", SEV_ERROR, "mensaje", line=40, node="stage:Build")
    f_despues = LintFinding("PL007", SEV_ERROR, "mensaje", line=48, node="stage:Build")
    assert pd._lint_key(f_antes) == pd._lint_key(f_despues)
    assert 40 not in pd._lint_key(f_antes) and 48 not in pd._lint_key(f_despues)
    nuevos, _res = pd._delta([f_antes], [f_despues], pd._lint_key)
    assert nuevos == ()

    from services.cicd_semantic_rules import SemanticFinding
    s1 = SemanticFinding("RS001", SEV_ERROR, "m", "stages[1].jobs[0].steps[4]", "e")
    s2 = SemanticFinding("RS001", SEV_ERROR, "m", "stages[1].jobs[0].steps[5]", "e")
    assert pd._sem_key(s1) == pd._sem_key(s2)


# ── 11 ───────────────────────────────────────────────────────────────────────
def test_gate_preservacion_bloquea_si_desaparece_un_comentario():
    texto = _leer("ci-cd-online.yml")
    indice, _ = pp.build_anchor_index(texto)
    # una op fabricada a mano que PISA un rango con comentarios adentro
    op = pp.EditOp("replace", "stages[0].jobs[0]",
                   ("  - job: BuildJob", "    steps:", "    - checkout: self"),
                   "pisar el job entero")
    res = pp.apply_ops(texto, (op,))
    assert res.ok, res.errors
    review = pd.review_patch(texto, res.text, res.hunks, profile=PERFIL, verb="add_step")
    assert review.preservation.ok is False
    assert review.preservation.comments_after < review.preservation.comments_before
    assert review.ok is False
    gate = next(g for g in review.gates if g.gate == pd.GATE_PRESERVACION)
    assert gate.passed is False and gate.skipped_reason


# ── 12 ───────────────────────────────────────────────────────────────────────
def test_remove_step_no_dispara_falso_positivo_de_preservacion():
    texto = _leer("ci-cd-online.yml")
    intent = pp.EditIntent(verb="remove_step", target_path=STEPS,
                           anchor_ref="PublishTestResults@2")
    res, review = _revisar(texto, intent)
    assert review.preservation.ok is True
    assert review.preservation.comments_before == 47
    assert review.preservation.comments_after == 46
    assert pd.formato_preservacion(review.preservation).startswith("Se preservan 46/47")
