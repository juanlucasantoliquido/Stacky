"""
services/pipeline_renderers.py — Renderers PUROS PipelineSpec → YAML ADO/GitLab.
                                  Parsers PUROS YAML → PipelineSpec (para F6 round-trip).

Plan 73 F1 — to_ado_yaml (pura).
Plan 73 F2 — to_gitlab_yaml (pura).
Plan 73 F6 — parse_ado_yaml / parse_gitlab_yaml (puras, inversas para el subset v1).

PyYAML ya disponible (requirements.txt:10 PyYAML==6.0.3 — verificado C10).
"""
from __future__ import annotations

import yaml

from services.pipeline_spec import (
    PipelineSpec, Stage, Job, Step, TaskStep, DeploymentJob,
    ValidationError, dict_to_spec,
)


# ── Construcciones ADO NO modeladas (Plan 243 F2, C14) ────────────────────────
#
# Allowlist CERRADA y versionada. Cerrar el round-trip de los 9 pipelines reales
# exigiría un AST completo de ADO YAML; en vez de prometerlo, se declara qué queda
# afuera y se prueba que la lista no crece en silencio
# (test_allowlist_no_crece_en_silencio). Agregar una entrada obliga a tocar el test
# y a justificarlo en el documento del plan.
UNSUPPORTED_CONSTRUCTS: tuple = (
    "matrix",                     # ci-batch.yml:58-59 (strategy: matrix:)
    "compile_time_expression",    # bootstrap-server-environment.yml (17 x ${{ }})
    "template",                   # 0 usos en el corpus — no se agrega
    "extends",                    # 0 usos en el corpus — no se agrega
    "resources",                  # 0 usos en el corpus — no se agrega
)

_COMPILE_TIME_MARKER = "${{"


def _walk(node):
    """Todos los nodos dict/list de un documento, en orden de aparición. PURA."""
    yield node
    if isinstance(node, dict):
        for key, value in node.items():
            yield key
            yield from _walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk(value)


def scan_unsupported(yaml_text: str) -> tuple:
    """Declara qué construcciones NO modeladas trae este YAML. PURA (sin I/O).

    Se evalúa sobre el documento PARSEADO, no sobre el texto: un `${{` dentro de un
    comentario no es una expresión de tiempo de compilación, y un pipeline no debería
    quedar marcado por lo que dice su propia documentación.
    """
    try:
        doc = yaml.safe_load(yaml_text)
    except yaml.YAMLError:
        return ()

    encontrados = set()
    for node in _walk(doc):
        if isinstance(node, str):
            if _COMPILE_TIME_MARKER in node:
                encontrados.add("compile_time_expression")
            continue
        if isinstance(node, dict):
            for clave in node:
                if clave in ("matrix", "template", "extends", "resources"):
                    encontrados.add(clave)
    # Orden determinista: el de la allowlist, nunca el de un set.
    return tuple(c for c in UNSUPPORTED_CONSTRUCTS if c in encontrados)


# ── ADO ────────────────────────────────────────────────────────────────────────

def to_ado_yaml(spec: PipelineSpec) -> str:
    """Convierte PipelineSpec a azure-pipelines.yml. PURA (sin I/O)."""
    if spec.raw_yaml and spec.raw_yaml_target == "ado":
        return spec.raw_yaml
    if spec.raw_yaml and spec.raw_yaml_target != "ado":
        raise ValidationError(
            "raw_yaml", f"raw_yaml target={spec.raw_yaml_target} no portable a ado"
        )
    doc = _spec_to_ado_doc(spec)
    return yaml.safe_dump(doc, sort_keys=False, allow_unicode=True)


def _depends_on_value(depends_on: tuple):
    """`dependsOn` acepta escalar o lista en ADO. Una sola dependencia se emite como
    escalar, que es como está escrito el corpus (cd-deploy-test.yml:117)."""
    valores = list(depends_on)
    return valores[0] if len(valores) == 1 else valores


def _script_step_doc(step: Step) -> dict:
    """Paso `- script:` (Plan 73). Orden de claves INTACTO: no tocar (no regresión)."""
    step_doc: dict = {"script": step.script, "displayName": step.name}
    if step.working_directory:
        step_doc["workingDirectory"] = step.working_directory
    if step.condition:
        step_doc["condition"] = step.condition
    if step.env:
        step_doc["env"] = dict(step.env)
    return step_doc


def _task_step_doc(step: TaskStep) -> dict:
    """Paso `- task: X@N` (Plan 243 F2). Claves en orden task → displayName → inputs;
    `yaml.safe_dump(sort_keys=False)` lo preserva en la salida."""
    step_doc: dict = {"task": step.task}
    if step.name:
        step_doc["displayName"] = step.name
    if step.condition:
        step_doc["condition"] = step.condition
    if step.inputs:
        step_doc["inputs"] = dict(step.inputs)
    if step.env:
        step_doc["env"] = dict(step.env)
    return step_doc


def _job_steps_docs(steps: tuple, task_steps: tuple) -> list:
    return [_script_step_doc(s) for s in steps] + [_task_step_doc(t) for t in task_steps]


def _job_doc(jb: Job) -> dict:
    """Job clásico. El orden de claves preexistente (job → pool → variables → steps →
    artifacts → demands) NO se altera: las claves nuevas sólo se insertan si el campo
    está presente, así un spec del Plan 73 emite byte por byte lo mismo que antes."""
    job_doc: dict = {"job": jb.name}
    if jb.display_name:
        job_doc["displayName"] = jb.display_name
    if jb.depends_on:
        job_doc["dependsOn"] = _depends_on_value(jb.depends_on)
    if jb.pool_name:
        job_doc["pool"] = {"name": jb.pool_name}
    elif jb.pool_vm_image:
        job_doc["pool"] = {"vmImage": jb.pool_vm_image}
    if jb.variables:
        job_doc["variables"] = dict(jb.variables)
    job_doc["steps"] = _job_steps_docs(jb.steps, jb.task_steps)
    # Artifacts como sección separada en el job (no como publish step)
    if jb.artifacts:
        job_doc["artifacts"] = {"publish": list(jb.artifacts)}
    if jb.runner_tags:
        job_doc["demands"] = list(jb.runner_tags)
    return job_doc


def _deployment_doc(dp: DeploymentJob) -> dict:
    """Job `- deployment:` con `strategy.runOnce.deploy.steps`.
    Patrón exacto de cd-deploy-test.yml:122-149: `- checkout: self` y
    `- download: current` van al frente de los steps."""
    steps: list = []
    if dp.checkout:
        steps.append({"checkout": "self"})
    for artifact in dp.download_artifacts:
        steps.append({"download": "current", "artifact": artifact})
    steps.extend(_task_step_doc(t) for t in dp.steps)

    doc: dict = {"deployment": dp.name}
    if dp.display_name:
        doc["displayName"] = dp.display_name
    doc["environment"] = dp.environment
    doc["strategy"] = {dp.strategy: {"deploy": {"steps": steps}}}
    return doc


def _stage_doc(st: Stage) -> dict:
    """Stage. Orden preexistente (stage → condition → jobs) preservado para los specs
    del Plan 73; las claves nuevas se insertan sólo si el campo está presente."""
    stage_doc: dict = {"stage": st.name}
    if st.display_name:
        stage_doc["displayName"] = st.display_name
    if st.depends_on:
        stage_doc["dependsOn"] = _depends_on_value(st.depends_on)
    if st.condition:
        stage_doc["condition"] = st.condition
    if st.pool_name:
        stage_doc["pool"] = {"name": st.pool_name}
    elif st.pool_vm_image:
        stage_doc["pool"] = {"vmImage": st.pool_vm_image}
    # En ADO los `- deployment:` son items de la MISMA lista `jobs:`.
    stage_doc["jobs"] = [_job_doc(jb) for jb in st.jobs] + \
                        [_deployment_doc(dp) for dp in st.deployments]
    return stage_doc


def _spec_to_ado_doc(spec: PipelineSpec) -> dict:
    """PipelineSpec → dict YAML-ready para ADO. PURA."""
    doc: dict = {}

    # name del pipeline (ADO soporta root-level name para el display)
    if spec.name:
        doc["name"] = spec.name

    # trigger: none / trigger.branches.include / trigger.paths.include
    if spec.trigger_disabled:
        doc["trigger"] = "none"
    elif spec.trigger_branches or spec.trigger_paths:
        trigger_doc: dict = {}
        if spec.trigger_branches:
            trigger_doc["branches"] = {"include": list(spec.trigger_branches)}
        if spec.trigger_paths:
            trigger_doc["paths"] = {"include": list(spec.trigger_paths)}
        doc["trigger"] = trigger_doc

    if spec.pr_disabled:
        doc["pr"] = "none"
    if spec.parameters:
        doc["parameters"] = [dict(p) for p in spec.parameters]
    if spec.schedules:
        doc["schedules"] = [dict(s) for s in spec.schedules]

    # variables globales
    if spec.variables:
        doc["variables"] = dict(spec.variables)

    if spec.pool_name:
        doc["pool"] = {"name": spec.pool_name}
    elif spec.pool_vm_image:
        doc["pool"] = {"vmImage": spec.pool_vm_image}

    # ADO admite tres raíces alternativas. `stages:` es la del Plan 73 y sigue siendo
    # la salida por defecto — incluso vacía — para no cambiar nada de lo existente.
    if spec.root_task_steps or spec.root_steps:
        doc["steps"] = _job_steps_docs(spec.root_steps, spec.root_task_steps)
    elif spec.root_jobs:
        doc["jobs"] = [_job_doc(jb) for jb in spec.root_jobs]
    else:
        doc["stages"] = [_stage_doc(st) for st in spec.stages]
    return doc


# ── GitLab ─────────────────────────────────────────────────────────────────────

# Tabla de traducción de condiciones ADO → GitLab (parcial, F2)
_ADO_TO_GITLAB_CONDITION_MAP = {
    "eq(variables['Build.SourceBranchName'], 'main')": '$CI_COMMIT_BRANCH == "main"',
    "eq(variables['Build.SourceBranchName'], 'develop')": '$CI_COMMIT_BRANCH == "develop"',
    "eq(variables['Build.SourceBranchName'], 'master')": '$CI_COMMIT_BRANCH == "master"',
    "ne(variables['Agent.JobStatus'], 'Succeeded')": '$CI_JOB_STATUS != "success"',
    "always()": "always()",  # GitLab usa "always" en reglas de when:
}


def _translate_condition_to_gitlab(condition: str) -> str:
    """Traduce condición ADO a expresión GitLab. Lanza ValidationError si intraducible."""
    if condition in _ADO_TO_GITLAB_CONDITION_MAP:
        return _ADO_TO_GITLAB_CONDITION_MAP[condition]
    # Si la condición ya parece ser GitLab (empieza con $CI_)
    if condition.strip().startswith("$CI_") or "==" in condition or "!=" in condition:
        return condition
    raise ValidationError(
        "condition",
        f"Condición ADO no traducible a GitLab: '{condition}'. "
        f"Usa raw_yaml para condiciones complejas.",
    )


def _image_map(pool_vm_image: str | None, image: str | None) -> str | None:
    """Resuelve la imagen GitLab. ADO ubuntu-latest → ubuntu:latest si no hay image explícita."""
    if image:
        return image
    if pool_vm_image == "ubuntu-latest":
        return "ubuntu:latest"
    if pool_vm_image == "windows-latest":
        return None  # Windows runners en GitLab se configuran por tag, no por imagen
    if pool_vm_image:
        return pool_vm_image  # best-effort
    return None


def to_gitlab_yaml(spec: PipelineSpec) -> str:
    """Convierte PipelineSpec a .gitlab-ci.yml. PURA (sin I/O)."""
    if spec.raw_yaml and spec.raw_yaml_target == "gitlab":
        return spec.raw_yaml
    if spec.raw_yaml and spec.raw_yaml_target != "gitlab":
        raise ValidationError(
            "raw_yaml", f"raw_yaml target={spec.raw_yaml_target} no portable a gitlab"
        )
    doc = _spec_to_gitlab_doc(spec)
    return yaml.safe_dump(doc, sort_keys=False, allow_unicode=True)


def _spec_to_gitlab_doc(spec: PipelineSpec) -> dict:
    """PipelineSpec → dict YAML-ready para GitLab. PURA.
    trigger_branches se OMITE (GitLab dispara por push) — lossy-by-design (F6, C6)."""
    doc: dict = {}

    # Stages list
    stage_names = [st.name for st in spec.stages]
    doc["stages"] = stage_names

    # Variables globales
    if spec.variables:
        doc["variables"] = dict(spec.variables)

    # Jobs al root del documento
    for st in spec.stages:
        if st.condition:
            # condition de stage → se aplica a todos sus jobs como regla
            pass
        for jb in st.jobs:
            job_doc: dict = {"stage": st.name}
            img = _image_map(jb.pool_vm_image, jb.image)
            if img:
                job_doc["image"] = img
            if jb.runner_tags:
                job_doc["tags"] = list(jb.runner_tags)
            if jb.variables:
                job_doc["variables"] = dict(jb.variables)
            if jb.services:
                job_doc["services"] = list(jb.services)

            scripts = []
            rules = []
            for step in jb.steps:
                # Agregar líneas del script
                for line in step.script.split("\n"):
                    if line.strip():
                        scripts.append(line)
                # Traducir condición
                if step.condition:
                    gitlab_cond = _translate_condition_to_gitlab(step.condition)
                    rules.append({"if": gitlab_cond})

            job_doc["script"] = scripts if scripts else ["echo 'no-op'"]
            if rules:
                job_doc["rules"] = rules

            if jb.artifacts:
                job_doc["artifacts"] = {"paths": list(jb.artifacts)}

            doc[jb.name] = job_doc

    return doc


# ── Parsers PUROS (F6 — inversos para el subset v1) ───────────────────────────

def _as_tuple(value) -> tuple:
    """`dependsOn`/`include` aceptan escalar o lista en ADO."""
    if value is None:
        return ()
    if isinstance(value, (list, tuple)):
        return tuple(value)
    return (value,)


def _parse_steps(step_docs) -> tuple:
    """Lista de steps ADO → (script_steps, task_steps, checkout, download_artifacts).

    Tolerante por diseño: lo que no es `script:` ni `task:` (`checkout`, `download`,
    `- template:`…) no rompe el parseo — se reconoce lo modelado y se ignora el resto.
    """
    scripts: list = []
    tasks: list = []
    checkout = False
    downloads: list = []

    for step_doc in (step_docs or []):
        if not isinstance(step_doc, dict):
            continue
        if isinstance(step_doc.get("task"), str):
            inputs = step_doc.get("inputs")
            tasks.append(TaskStep(
                name=step_doc.get("displayName", ""),
                task=step_doc["task"],
                inputs=dict(inputs) if isinstance(inputs, dict) else {},
                condition=step_doc.get("condition"),
                env=dict(step_doc.get("env") or {}),
            ))
        elif "script" in step_doc:
            script_val = step_doc.get("script", "")
            if not isinstance(script_val, str):
                script_val = str(script_val)
            scripts.append(Step(
                name=step_doc.get("displayName", ""),
                script=script_val,
                working_directory=step_doc.get("workingDirectory"),
                condition=step_doc.get("condition"),
                env=dict(step_doc.get("env") or {}),
            ))
        elif "checkout" in step_doc:
            checkout = True
        elif "download" in step_doc:
            artifact = step_doc.get("artifact")
            if artifact is not None:
                downloads.append(artifact)

    return tuple(scripts), tuple(tasks), checkout, tuple(downloads)


def _parse_job(jb_doc: dict) -> Job:
    pool = jb_doc.get("pool") if isinstance(jb_doc.get("pool"), dict) else {}
    scripts, tasks, _checkout, _downloads = _parse_steps(jb_doc.get("steps"))
    # Artifacts como sección separada en el job (patrón to_ado_yaml)
    arts_block = jb_doc.get("artifacts") or {}
    arts = tuple(arts_block.get("publish") or []) if isinstance(arts_block, dict) else ()
    return Job(
        name=jb_doc.get("job", ""),
        steps=scripts,
        pool_vm_image=pool.get("vmImage"),
        pool_name=pool.get("name"),
        variables=dict(jb_doc.get("variables") or {}),
        artifacts=arts,
        runner_tags=tuple(jb_doc.get("demands") or jb_doc.get("tags") or ()),
        task_steps=tasks,
        depends_on=_as_tuple(jb_doc.get("dependsOn")),
        display_name=jb_doc.get("displayName"),
    )


def _parse_deployment(jb_doc: dict) -> DeploymentJob:
    strategy_doc = jb_doc.get("strategy") if isinstance(jb_doc.get("strategy"), dict) else {}
    strategy_name = "runOnce"
    step_docs = []
    for key, value in strategy_doc.items():
        if isinstance(value, dict) and isinstance(value.get("deploy"), dict):
            strategy_name = key
            step_docs = value["deploy"].get("steps") or []
            break
    _scripts, tasks, checkout, downloads = _parse_steps(step_docs)
    return DeploymentJob(
        name=jb_doc.get("deployment", ""),
        environment=jb_doc.get("environment", ""),
        strategy=strategy_name,
        steps=tasks,
        checkout=checkout,
        download_artifacts=downloads,
        display_name=jb_doc.get("displayName"),
    )


def _split_jobs(job_docs) -> tuple:
    """Una lista `jobs:` de ADO mezcla `- job:` y `- deployment:`."""
    jobs: list = []
    deployments: list = []
    for jb_doc in (job_docs or []):
        if not isinstance(jb_doc, dict):
            continue
        if "deployment" in jb_doc:
            deployments.append(_parse_deployment(jb_doc))
        else:
            jobs.append(_parse_job(jb_doc))
    return tuple(jobs), tuple(deployments)


def parse_ado_yaml(yaml_str: str) -> PipelineSpec:
    """YAML ADO → PipelineSpec. PURA (parsea texto, no lee disco).

    Plan 243 F2 — reescrito: la versión del Plan 73 sólo entendía `script`/`displayName`,
    así que perdía el 100% de los pasos de un pipeline ADO real.

    TOLERANTE POR DISEÑO (Gate B): sobre cualquiera de los 9 pipelines reales no lanza
    y recupera la espina de `task:` completa. Lo que el modelo no cubre —`matrix`,
    expresiones `${{ }}`, `template`/`extends`/`resources`— NO se inventa: se declara
    con `scan_unsupported()`. Un `- script:` a nivel raíz mezclado con tareas se
    recupera, pero al re-emitir sale agrupado antes de las tareas: el round-trip exacto
    está garantizado sólo para los pipelines que el generador debe producir (Gate A).
    """
    doc = yaml.safe_load(yaml_str) or {}
    if not isinstance(doc, dict):
        return PipelineSpec(name="", stages=())

    # trigger: none | {branches: {include}, paths: {include}}
    trigger = doc.get("trigger")
    trigger_disabled = trigger == "none"
    trigger_block = trigger if isinstance(trigger, dict) else {}
    branches_block = trigger_block.get("branches") or {}
    paths_block = trigger_block.get("paths") or {}

    pool = doc.get("pool") if isinstance(doc.get("pool"), dict) else {}

    root_scripts, root_tasks, _checkout, _downloads = _parse_steps(doc.get("steps"))
    root_jobs, root_deployments = _split_jobs(doc.get("jobs"))
    # Un `- deployment:` a nivel raíz (sin stage) no aparece en el corpus; si apareciera,
    # se conserva como job para no perder su espina de tareas.
    root_jobs = root_jobs + tuple(
        Job(name=d.name, steps=(), task_steps=d.steps, display_name=d.display_name)
        for d in root_deployments
    )

    stages = []
    for st_doc in (doc.get("stages") or []):
        if not isinstance(st_doc, dict):
            continue
        st_pool = st_doc.get("pool") if isinstance(st_doc.get("pool"), dict) else {}
        jobs, deployments = _split_jobs(st_doc.get("jobs"))
        stages.append(Stage(
            name=st_doc.get("stage", ""),
            jobs=jobs,
            condition=st_doc.get("condition"),
            deployments=deployments,
            pool_name=st_pool.get("name"),
            pool_vm_image=st_pool.get("vmImage"),
            depends_on=_as_tuple(st_doc.get("dependsOn")),
            display_name=st_doc.get("displayName"),
        ))

    return PipelineSpec(
        name=doc.get("name", "") if isinstance(doc.get("name"), str) else "",
        stages=tuple(stages),
        variables=dict(doc.get("variables") or {}),
        trigger_branches=_as_tuple(branches_block.get("include")),
        trigger_disabled=trigger_disabled,
        trigger_paths=_as_tuple(paths_block.get("include")),
        pr_disabled=doc.get("pr") == "none",
        schedules=tuple(doc.get("schedules") or ()),
        parameters=tuple(doc.get("parameters") or ()),
        pool_vm_image=pool.get("vmImage"),
        pool_name=pool.get("name"),
        root_task_steps=root_tasks,
        root_steps=root_scripts,
        root_jobs=root_jobs,
    )


# Inverso de _ADO_TO_GITLAB_CONDITION_MAP para el parser GitLab
_GITLAB_TO_ADO_CONDITION_MAP = {v: k for k, v in _ADO_TO_GITLAB_CONDITION_MAP.items()}


def parse_gitlab_yaml(yaml_str: str) -> PipelineSpec:
    """YAML GitLab → PipelineSpec (subset v1). PURA. Solo cubre el subset que to_gitlab_yaml emite.
    trigger_branches es siempre () tras el round-trip (lossy-by-design, C6)."""
    doc = yaml.safe_load(yaml_str) or {}
    stage_names: list[str] = doc.get("stages") or []
    variables = dict(doc.get("variables") or {})
    # Agrupar jobs por stage
    stages_dict: dict[str, list[Job]] = {s: [] for s in stage_names}
    raw_yaml_content: str | None = None
    raw_yaml_target: str | None = None

    for key, val in doc.items():
        if key in ("stages", "variables"):
            continue
        if not isinstance(val, dict):
            continue
        stage_name = val.get("stage", "")
        img = val.get("image")
        tags = tuple(val.get("tags") or ())
        job_vars = dict(val.get("variables") or {})
        services = tuple(val.get("services") or [])
        arts_block = val.get("artifacts") or {}
        arts = tuple(arts_block.get("paths") or []) if isinstance(arts_block, dict) else ()
        scripts = val.get("script") or []
        if isinstance(scripts, str):
            scripts = [scripts]
        step = Step(name=key, script="\n".join(scripts))
        job = Job(
            name=key,
            steps=(step,),
            image=img,
            runner_tags=tags,
            variables=job_vars,
            services=services,
            artifacts=arts,
        )
        if stage_name in stages_dict:
            stages_dict[stage_name].append(job)
        else:
            # stage desconocido — agregar al final
            stages_dict[stage_name] = [job]
            stage_names.append(stage_name)

    stages = [
        Stage(name=s, jobs=tuple(stages_dict.get(s) or []))
        for s in stage_names
    ]
    return PipelineSpec(
        name="",  # el nombre no se emite en el YAML GitLab estándar
        stages=tuple(stages),
        variables=variables,
        trigger_branches=(),  # siempre vacío tras round-trip GitLab (lossy-by-design, C6)
        raw_yaml=raw_yaml_content,
        raw_yaml_target=raw_yaml_target,
    )
