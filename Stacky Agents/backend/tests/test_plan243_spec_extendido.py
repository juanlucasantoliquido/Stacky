"""Plan 243 F1 — TaskStep y DeploymentJob en el modelo (backend).

Comando (§7.1 del plan):
    .venv\\Scripts\\python.exe -m pytest tests/test_plan243_spec_extendido.py -q

Aditivo y retrocompatible: Step/Job/Stage/PipelineSpec del Plan 73 no pierden nada.
C15: _validate_spec valida FORMA, no pertenencia al catálogo. pipeline_spec.py NO
importa cicd_task_catalog — es el modelo genérico del Plan 73 y sirve también a GitLab.
"""
from __future__ import annotations

import io
import os

from services.pipeline_spec import (
    DeploymentJob,
    Job,
    PipelineSpec,
    Stage,
    Step,
    TaskStep,
    ValidationError,
    dict_to_spec,
)


def _msgs(errors):
    return [e.message for e in errors]


def _spec_con(job=None, stage=None, **kw):
    job = job or Job(name="j", steps=(Step(name="s", script="echo hola"),))
    stage = stage or Stage(name="Build", jobs=(job,))
    base = dict(name="p", stages=(stage,))
    base.update(kw)
    return PipelineSpec(**base)


# ── 1. Construcción válida ────────────────────────────────────────────────────

def test_construccion_valida_de_task_step_y_deployment():
    task = TaskStep(name="Build", task="VSBuild@1", inputs={"solution": "x.sln"})
    assert task.task == "VSBuild@1"
    assert task.inputs["solution"] == "x.sln"
    assert task.condition is None and task.env == {}

    dep = DeploymentJob(name="DeployWeb", environment="Test", steps=(task,))
    assert dep.strategy == "runOnce"
    assert dep.checkout is True
    assert dep.download_artifacts == ()

    spec = _spec_con(stage=Stage(name="Deploy", jobs=(), deployments=(dep,),
                                 pool_name="TEST-Server"))
    assert spec.validate() == []


# ── 2. dict_to_spec con task_steps ────────────────────────────────────────────

def test_dict_to_spec_con_task_steps():
    spec = dict_to_spec({
        "name": "p",
        "stages": [{
            "name": "Build",
            "display_name": "Build & Test",
            "jobs": [{
                "name": "BuildJob",
                "steps": [],
                "task_steps": [
                    {"name": "NuGet", "task": "NuGetToolInstaller@1",
                     "inputs": {"versionSpec": "6.x"}},
                    {"name": "MSBuild", "task": "VSBuild@1",
                     "inputs": {"solution": "$(solution)"}, "condition": "succeeded()"},
                ],
            }],
        }],
    })
    job = spec.stages[0].jobs[0]
    assert isinstance(job.task_steps, tuple) and len(job.task_steps) == 2
    assert isinstance(job.task_steps[0], TaskStep)
    assert job.task_steps[1].condition == "succeeded()"
    assert spec.stages[0].display_name == "Build & Test"
    assert spec.validate() == []


# ── 3. dict_to_spec con deployments ───────────────────────────────────────────

def test_dict_to_spec_con_deployments():
    spec = dict_to_spec({
        "name": "p",
        "stages": [{
            "name": "DeployWeb",
            "pool_name": "TEST-Server",
            "depends_on": ["Build"],
            "jobs": [],
            "deployments": [{
                "name": "DeployWeb",
                "environment": "Test",
                "strategy": "runOnce",
                "download_artifacts": ["AgendaWeb"],
                "steps": [{"name": "Deploy", "task": "PowerShell@2",
                           "inputs": {"filePath": "scripts/Deploy-Local.ps1"}}],
            }],
        }],
    })
    stage = spec.stages[0]
    assert stage.depends_on == ("Build",)
    assert stage.pool_name == "TEST-Server"
    dep = stage.deployments[0]
    assert isinstance(dep, DeploymentJob)
    assert dep.environment == "Test"
    assert dep.download_artifacts == ("AgendaWeb",)
    assert isinstance(dep.steps[0], TaskStep)
    assert spec.validate() == []


# ── 4. Job task-only aceptado (sin script steps) ──────────────────────────────

def test_job_task_only_es_valido_y_job_vacio_sigue_fallando():
    task_only = Job(name="j", steps=(),
                    task_steps=(TaskStep(name="b", task="VSBuild@1"),))
    assert _spec_con(job=task_only).validate() == []

    # No regresión del Plan 73: un job SIN steps y SIN task_steps sigue siendo error.
    vacio = Job(name="j", steps=())
    errores = _spec_con(job=vacio).validate()
    assert any("job sin steps" in m for m in _msgs(errores))


# ── 5. Formato de `task` inválido rechazado ───────────────────────────────────

def test_task_con_formato_invalido_rechazada():
    for malo in ("", "VSBuild", "VSBuild@", "@1", "1VSBuild@1", "VS Build@1", "VSBuild@x"):
        job = Job(name="j", steps=(), task_steps=(TaskStep(name="b", task=malo),))
        errores = _spec_con(job=job).validate()
        assert errores, "task=%r deberia ser rechazada" % malo
        assert any("task" in e.field for e in errores)

    # Y las bien formadas pasan (aunque no existan: el catalogo es cosa de F3)
    for bueno in ("VSBuild@1", "PublishCodeCoverageResults@2", "Use_DotNet@10"):
        job = Job(name="j", steps=(), task_steps=(TaskStep(name="b", task=bueno),))
        assert _spec_con(job=job).validate() == []


def test_inputs_que_no_son_dict_rechazados():
    job = Job(name="j", steps=(),
              task_steps=(TaskStep(name="b", task="VSBuild@1", inputs=["no", "soy", "dict"]),))
    errores = _spec_con(job=job).validate()
    assert any("inputs" in e.field for e in errores)


# ── 6. environment vacío rechazado ────────────────────────────────────────────

def test_environment_vacio_rechazado():
    dep = DeploymentJob(name="d", environment="   ",
                        steps=(TaskStep(name="b", task="VSBuild@1"),))
    errores = _spec_con(stage=Stage(name="Deploy", jobs=(), deployments=(dep,))).validate()
    assert any("environment" in e.field for e in errores)


# ── 7. strategy inválida rechazada ────────────────────────────────────────────

def test_strategy_invalida_rechazada():
    dep = DeploymentJob(name="d", environment="Test", strategy="canary",
                        steps=(TaskStep(name="b", task="VSBuild@1"),))
    errores = _spec_con(stage=Stage(name="Deploy", jobs=(), deployments=(dep,))).validate()
    assert any("strategy" in e.field for e in errores)


# ── 8. C15 — el modelo NO conoce el catálogo ──────────────────────────────────

def test_no_importa_el_catalogo():
    ruta = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "services", "pipeline_spec.py")
    with io.open(ruta, "r", encoding="utf-8") as fh:
        fuente = fh.read()
    # Lectura del módulo, no adivinanza: ninguna forma de import del catálogo.
    for linea in fuente.splitlines():
        limpia = linea.strip()
        if limpia.startswith("import ") or limpia.startswith("from "):
            assert "cicd_task_catalog" not in limpia, "acople prohibido (C15): %s" % limpia

    # Y un spec con una tarea inexistente PASA la validación de forma:
    # la pertenencia al catálogo la decide F3 (RS008), no el modelo genérico.
    job = Job(name="j", steps=(), task_steps=(TaskStep(name="b", task="Loquesea@9"),))
    assert _spec_con(job=job).validate() == []


# ── Retrocompatibilidad de los campos nuevos del spec ─────────────────────────

def test_campos_nuevos_del_spec_tienen_default_y_no_rompen_plan73():
    viejo = dict_to_spec({"name": "p", "stages": [
        {"name": "b", "jobs": [{"name": "j", "steps": [{"name": "s", "script": "echo"}]}]}]})
    assert viejo.pr_disabled is False
    assert viejo.trigger_disabled is False
    assert viejo.trigger_paths == () and viejo.schedules == () and viejo.parameters == ()
    assert viejo.pool_vm_image is None and viejo.root_task_steps == ()
    assert viejo.validate() == []


def test_root_task_steps_hace_valido_un_spec_sin_stages():
    """agendaweb-ci.yml es un pipeline con `steps:` a nivel raíz y sin `stages:`."""
    spec = dict_to_spec({
        "name": "",
        "stages": [],
        "root_task_steps": [{"name": "NuGet", "task": "NuGetToolInstaller@1",
                             "inputs": {"versionSpec": "6.x"}}],
    })
    assert isinstance(spec.root_task_steps[0], TaskStep)
    errores = _msgs(spec.validate())
    assert not any("sin stages" in m for m in errores)
    # name vacío sigue siendo error del Plan 73 — no se toca esa regla
    assert any("name" in e.field for e in spec.validate())


def test_validation_error_sigue_siendo_raisable():
    try:
        raise ValidationError("campo", "mensaje")
    except ValidationError as exc:
        assert exc.field == "campo" and exc.message == "mensaje"
