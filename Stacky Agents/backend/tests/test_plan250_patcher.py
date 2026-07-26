"""Plan 250 F0 — motor de anclajes y splice quirurgico. 14 tests.

La tesis del plan: editar un pipeline NO es regenerarlo. Un round-trip
`parse_ado_yaml -> to_ado_yaml` sobre el corpus dorado borra 337/337 comentarios y
el 48% de las lineas. Estos tests prueban que el splice por lineas NO lo hace.
"""
from __future__ import annotations

import difflib
from pathlib import Path

import yaml

from services import pipeline_patcher as pp
from services.pipeline_renderers import scan_unsupported

BACKEND = Path(__file__).resolve().parent.parent
GOLDEN = BACKEND / "tests" / "fixtures" / "cicd_nl" / "golden"


def _leer(nombre: str) -> str:
    return (GOLDEN / nombre).read_text(encoding="utf-8")


def _comentarios(texto: str) -> int:
    return sum(1 for l in texto.splitlines() if l.lstrip().startswith("#"))


def _primer_steps(indice: dict) -> str:
    """Path del primer bloque `steps` (secuencia) del indice, en orden de aparicion."""
    candidatos = [
        (a.start_line, p) for p, a in indice.items()
        if a.kind == "seq" and p.endswith("steps")
    ]
    assert candidatos, "el fixture no tiene ningun bloque steps indexado"
    return sorted(candidatos)[0][1]


def _op_insertar_al_final(indice: dict, path_steps: str) -> pp.EditOp:
    anchor = indice[path_steps]
    ultimo = anchor.item_paths[-1]
    lineas = pp.render_block(
        {"task": "PublishCodeCoverageResults@2",
         "displayName": "Publicar cobertura",
         "inputs": {"codeCoverageTool": "Cobertura"}},
        key_col=anchor.key_col, dash_col=anchor.dash_col,
    )
    return pp.EditOp(kind="insert_after", anchor_path=ultimo, lines=lineas,
                     reason="agregar publicacion de cobertura al final")


# ── 1 ────────────────────────────────────────────────────────────────────────
def test_indice_de_anclajes_de_ci_cd_online():
    indice, errores = pp.build_anchor_index(_leer("ci-cd-online.yml"))
    assert errores == ()
    a = indice["stages[0].jobs[0].steps"]
    assert a.kind == "seq"
    assert a.key_col == 6
    assert a.dash_col == 4
    assert len(a.item_paths) == 6
    assert a.item_paths[0] == "stages[0].jobs[0].steps[0]"


# ── 2 ────────────────────────────────────────────────────────────────────────
def test_fin_efectivo_excluye_comentario_del_siguiente_item():
    """§2.3: end_mark.line de un item de secuencia es EXCLUSIVO y se traga la linea
    en blanco y el comentario que introduce al item SIGUIENTE."""
    texto = _leer("ci-cd-online.yml")
    lineas = texto.splitlines()
    indice, _ = pp.build_anchor_index(texto)
    a = indice["stages[0].jobs[0].steps[3]"]
    assert a.start_line == 100
    assert a.end_line == 109, "fin efectivo, no el end_mark 112"
    assert lineas[110] == ""
    assert lineas[111].strip() == "# 4. Publicar resultados de tests en ADO"


# ── 3 ────────────────────────────────────────────────────────────────────────
def test_insertar_paso_al_final_preserva_los_47_comentarios():
    texto = _leer("ci-cd-online.yml")
    assert _comentarios(texto) == 47
    indice, _ = pp.build_anchor_index(texto)
    op = _op_insertar_al_final(indice, "stages[0].jobs[0].steps")
    res = pp.apply_ops(texto, (op,))
    assert res.ok, res.errors
    assert _comentarios(res.text) == 47
    assert "PublishCodeCoverageResults@2" in res.text
    assert yaml.safe_load(res.text) is not None


# ── 4 ────────────────────────────────────────────────────────────────────────
def test_el_diff_real_no_sale_de_los_hunks_declarados():
    """KPI-2: los hunks son LA VERDAD del cambio, no una reconstruccion por LCS."""
    for archivo in sorted(GOLDEN.glob("*.yml")):
        texto = archivo.read_text(encoding="utf-8")
        indice, errores = pp.build_anchor_index(texto)
        assert errores == (), f"{archivo.name}: {errores}"
        op = _op_insertar_al_final(indice, _primer_steps(indice))
        res = pp.apply_ops(texto, (op,))
        assert res.ok, f"{archivo.name}: {res.errors}"

        antes, despues = texto.splitlines(), res.text.splitlines()
        rangos = [(h.start_line - 1, h.end_line) for h in res.hunks]
        puntos = {h.start_line - 1 for h in res.hunks if h.end_line < h.start_line}
        sm = difflib.SequenceMatcher(a=antes, b=despues, autojunk=False)
        for tag, i1, i2, _j1, _j2 in sm.get_opcodes():
            if tag == "equal":
                continue
            if i1 == i2:
                assert i1 in puntos, f"{archivo.name}: insercion en {i1} fuera de los hunks"
            else:
                assert any(lo <= i1 and i2 <= hi for lo, hi in rangos), \
                    f"{archivo.name}: cambio [{i1},{i2}) fuera de los hunks {rangos}"


# ── 5 ────────────────────────────────────────────────────────────────────────
def test_los_337_comentarios_del_corpus_sobreviven():
    """KPI-1, CAPSTONE. El round-trip los deja en 0; el splice los deja en 337."""
    total_antes = total_despues = 0
    for archivo in sorted(GOLDEN.glob("*.yml")):
        texto = archivo.read_text(encoding="utf-8")
        indice, errores = pp.build_anchor_index(texto)
        assert errores == (), f"{archivo.name}: {errores}"
        op = _op_insertar_al_final(indice, _primer_steps(indice))
        res = pp.apply_ops(texto, (op,))
        assert res.ok, f"{archivo.name}: {res.errors}"
        c_antes, c_despues = _comentarios(texto), _comentarios(res.text)
        assert c_despues == c_antes, f"{archivo.name}: {c_antes} -> {c_despues}"
        total_antes += c_antes
        total_despues += c_despues
    assert total_antes == 337
    assert total_despues == 337


# ── 6 ────────────────────────────────────────────────────────────────────────
def test_construcciones_no_modeladas_no_desaparecen():
    for archivo in sorted(GOLDEN.glob("*.yml")):
        texto = archivo.read_text(encoding="utf-8")
        indice, _ = pp.build_anchor_index(texto)
        op = _op_insertar_al_final(indice, _primer_steps(indice))
        res = pp.apply_ops(texto, (op,))
        assert res.ok, f"{archivo.name}: {res.errors}"
        assert scan_unsupported(res.text) == scan_unsupported(texto), archivo.name
    assert scan_unsupported(_leer("ci-batch.yml")) == ("matrix",)
    assert scan_unsupported(_leer("bootstrap-server-environment.yml")) == (
        "compile_time_expression",)
    assert scan_unsupported(_leer("ci-cd-online.yml")) == ()


# ── 7 ────────────────────────────────────────────────────────────────────────
def test_indentacion_se_deriva_del_archivo():
    """El MISMO paso sale con guion en col 4 en un pipeline y en col 16 en un deployment."""
    doc = {"task": "PowerShell@2", "displayName": "X"}

    t1 = _leer("ci-cd-online.yml")
    i1, _ = pp.build_anchor_index(t1)
    a1 = i1["stages[0].jobs[0].steps"]
    assert (a1.key_col, a1.dash_col) == (6, 4)
    l1 = pp.render_block(doc, key_col=a1.key_col, dash_col=a1.dash_col)
    assert l1[0] == "    - task: PowerShell@2"

    t2 = _leer("cd-deploy-test.yml")
    i2, _ = pp.build_anchor_index(t2)
    dep = [p for p in i2 if p.endswith("runOnce.deploy.steps") and i2[p].kind == "seq"]
    assert dep, "el deployment de cd-deploy-test.yml no quedo indexado"
    a2 = i2[sorted(dep)[0]]
    assert (a2.key_col, a2.dash_col) == (18, 16)
    l2 = pp.render_block(doc, key_col=a2.key_col, dash_col=a2.dash_col)
    assert l2[0] == " " * 16 + "- task: PowerShell@2"


# ── 8 ────────────────────────────────────────────────────────────────────────
def test_newline_final_se_preserva():
    base = _leer("ci-cd-online.yml")
    for texto in (base if base.endswith("\n") else base + "\n", base.rstrip("\n")):
        indice, _ = pp.build_anchor_index(texto)
        op = _op_insertar_al_final(indice, "stages[0].jobs[0].steps")
        res = pp.apply_ops(texto, (op,))
        assert res.ok, res.errors
        assert res.text.endswith("\n") == texto.endswith("\n")


# ── 9 ────────────────────────────────────────────────────────────────────────
def test_yaml_invalido_no_lanza():
    res = pp.apply_ops("stages: [\n", ())
    assert res.ok is False
    assert res.errors
    indice, errores = pp.build_anchor_index("stages: [\n")
    assert indice == {}
    assert errores


# ── 10 ───────────────────────────────────────────────────────────────────────
def test_yaml_gigante_rechazado():
    gigante = "# x\n" * (pp.MAX_YAML_BYTES // 4 + 10)
    assert len(gigante) > pp.MAX_YAML_BYTES
    res = pp.apply_ops(gigante, ())
    assert res.ok is False
    assert any("KB" in e or "grande" in e for e in res.errors)


# ── 11 ───────────────────────────────────────────────────────────────────────
def test_item_con_dash_en_linea_propia_no_soportado():
    texto = "steps:\n-\n  task: NuGetToolInstaller@1\n"
    indice, errores = pp.build_anchor_index(texto)
    assert errores, "un item con el guion en su propia linea debe dar error accionable"
    assert any("guion" in e or "-" in e for e in errores)
    res = pp.apply_ops(texto, ())
    assert res.ok is False
    assert res.text == texto


# ── 12 ───────────────────────────────────────────────────────────────────────
def test_ops_solapadas_rechazadas():
    texto = _leer("ci-cd-online.yml")
    indice, _ = pp.build_anchor_index(texto)
    op1 = pp.EditOp(kind="replace", anchor_path="stages[0].jobs[0].steps[3]",
                    lines=("    - task: PowerShell@2",), reason="a")
    op2 = pp.EditOp(kind="delete", anchor_path="stages[0].jobs[0].steps[3]",
                    lines=(), reason="b")
    res = pp.apply_ops(texto, (op1, op2))
    assert res.ok is False
    assert res.text == texto
    assert any("solap" in e for e in res.errors)


# ── 13 ───────────────────────────────────────────────────────────────────────
def _paths_esperados(texto: str) -> set:
    """Reimplementacion INDEPENDIENTE de la cobertura declarada (regla 1-bis),
    sobre yaml.safe_load (mecanismo distinto de yaml.compose)."""
    doc = yaml.safe_load(texto)
    esperado: set = set()
    if not isinstance(doc, dict):
        return esperado

    def steps_de(prefijo: str, lista) -> None:
        if not isinstance(lista, list):
            return
        esperado.add(prefijo)
        for k, paso in enumerate(lista):
            esperado.add(f"{prefijo}[{k}]")
            if isinstance(paso, dict) and isinstance(paso.get("inputs"), dict):
                esperado.add(f"{prefijo}[{k}].inputs")
                for clave in paso["inputs"]:
                    esperado.add(f"{prefijo}[{k}].inputs.{clave}")

    def job_de(prefijo: str, job) -> None:
        if not isinstance(job, dict):
            return
        if isinstance(job.get("steps"), list):
            steps_de(f"{prefijo}.steps", job["steps"])
        strategy = job.get("strategy")
        if isinstance(strategy, dict):
            esperado.add(f"{prefijo}.strategy")
            run_once = strategy.get("runOnce")
            if isinstance(run_once, dict):
                esperado.add(f"{prefijo}.strategy.runOnce")
                deploy = run_once.get("deploy")
                if isinstance(deploy, dict):
                    esperado.add(f"{prefijo}.strategy.runOnce.deploy")
                    if isinstance(deploy.get("steps"), list):
                        steps_de(f"{prefijo}.strategy.runOnce.deploy.steps", deploy["steps"])

    for clave in ("trigger", "pr", "schedules", "variables", "pool", "stages",
                  "jobs", "steps"):
        if clave in doc:
            esperado.add(clave)
    trigger = doc.get("trigger")
    if isinstance(trigger, dict) and isinstance(trigger.get("paths"), dict):
        esperado.add("trigger.paths")
        if "include" in trigger["paths"]:
            esperado.add("trigger.paths.include")
    if isinstance(doc.get("stages"), list):
        for i, stage in enumerate(doc["stages"]):
            esperado.add(f"stages[{i}]")
            if isinstance(stage, dict) and isinstance(stage.get("jobs"), list):
                esperado.add(f"stages[{i}].jobs")
                for j, job in enumerate(stage["jobs"]):
                    esperado.add(f"stages[{i}].jobs[{j}]")
                    job_de(f"stages[{i}].jobs[{j}]", job)
    if isinstance(doc.get("jobs"), list):
        for j, job in enumerate(doc["jobs"]):
            esperado.add(f"jobs[{j}]")
            job_de(f"jobs[{j}]", job)
    if isinstance(doc.get("steps"), list):
        steps_de("steps", doc["steps"])
    return esperado


def test_cobertura_del_indice_es_la_declarada():
    for archivo in sorted(GOLDEN.glob("*.yml")):
        texto = archivo.read_text(encoding="utf-8")
        indice, errores = pp.build_anchor_index(texto)
        assert errores == (), f"{archivo.name}: {errores}"
        assert set(indice) == _paths_esperados(texto), archivo.name

    i_dep, _ = pp.build_anchor_index(_leer("cd-deploy-test.yml"))
    assert any(p.endswith("strategy.runOnce.deploy.steps") for p in i_dep)
    # job-level (sin `stages`): el corpus lo tiene en nightly-build-online.yml
    i_job, _ = pp.build_anchor_index(_leer("nightly-build-online.yml"))
    assert "jobs[0].steps" in i_job
    assert not any(p.startswith("stages") for p in i_job)
    # step-level (sin `stages` ni `jobs`): pr-validation-online.yml
    i_step, _ = pp.build_anchor_index(_leer("pr-validation-online.yml"))
    assert "steps[0]" in i_step
    assert not any(p.startswith(("stages", "jobs")) for p in i_step)


# ── 14 ───────────────────────────────────────────────────────────────────────
def test_path_inexistente_enumera_los_disponibles():
    texto = _leer("ci-cd-online.yml")
    op = pp.EditOp(kind="insert_after", anchor_path="stages[9].jobs[0].steps",
                   lines=("    - task: X@1",), reason="x")
    res = pp.apply_ops(texto, (op,))
    assert res.ok is False
    mensaje = " ".join(res.errors)
    assert "stages[9].jobs[0].steps" in mensaje
    assert "stages[0].jobs[0].steps" in mensaje, "debe ENUMERAR los paths disponibles"
