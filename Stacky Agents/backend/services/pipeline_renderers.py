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
    PipelineSpec, Stage, Job, Step,
    ValidationError, dict_to_spec,
)


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


def _spec_to_ado_doc(spec: PipelineSpec) -> dict:
    """PipelineSpec → dict YAML-ready para ADO. PURA."""
    doc: dict = {}

    # name del pipeline (ADO soporta root-level name para el display)
    if spec.name:
        doc["name"] = spec.name

    # trigger_branches → trigger: branches: include: [...]
    if spec.trigger_branches:
        doc["trigger"] = {"branches": {"include": list(spec.trigger_branches)}}

    # variables globales
    if spec.variables:
        doc["variables"] = dict(spec.variables)

    stages = []
    for st in spec.stages:
        stage_doc: dict = {"stage": st.name}
        if st.condition:
            stage_doc["condition"] = st.condition
        jobs = []
        for jb in st.jobs:
            job_doc: dict = {"job": jb.name}
            if jb.pool_vm_image:
                job_doc["pool"] = {"vmImage": jb.pool_vm_image}
            if jb.variables:
                job_doc["variables"] = dict(jb.variables)
            steps = []
            for step in jb.steps:
                step_doc: dict = {"script": step.script, "displayName": step.name}
                if step.working_directory:
                    step_doc["workingDirectory"] = step.working_directory
                if step.condition:
                    step_doc["condition"] = step.condition
                if step.env:
                    step_doc["env"] = dict(step.env)
                steps.append(step_doc)
            job_doc["steps"] = steps
            # Artifacts como sección separada en el job (no como publish step)
            if jb.artifacts:
                job_doc["artifacts"] = {"publish": list(jb.artifacts)}
            if jb.runner_tags:
                job_doc["demands"] = list(jb.runner_tags)
            jobs.append(job_doc)
        stage_doc["jobs"] = jobs
        stages.append(stage_doc)

    doc["stages"] = stages
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

def parse_ado_yaml(yaml_str: str) -> PipelineSpec:
    """YAML ADO → PipelineSpec (subset v1). PURA. Solo cubre el subset que to_ado_yaml emite."""
    doc = yaml.safe_load(yaml_str) or {}
    # name (emitido por to_ado_yaml como root-level name:)
    name_from_doc = doc.get("name", "")
    # trigger_branches
    trigger = doc.get("trigger") or {}
    branches_block = trigger.get("branches") or {}
    trigger_branches = tuple(branches_block.get("include") or [])
    variables = dict(doc.get("variables") or {})
    stages = []
    for st_doc in (doc.get("stages") or []):
        cond = st_doc.get("condition")
        jobs = []
        for jb_doc in (st_doc.get("jobs") or []):
            pool = jb_doc.get("pool") or {}
            steps = []
            for step_doc in (jb_doc.get("steps") or []):
                script_val = step_doc.get("script", "")
                if not isinstance(script_val, str):
                    script_val = str(script_val)
                steps.append(Step(
                    name=step_doc.get("displayName", ""),
                    script=script_val,
                    working_directory=step_doc.get("workingDirectory"),
                    condition=step_doc.get("condition"),
                    env=dict(step_doc.get("env") or {}),
                ))
            # Artifacts como sección separada en el job (patrón to_ado_yaml)
            arts_block = jb_doc.get("artifacts") or {}
            arts = tuple(arts_block.get("publish") or []) if isinstance(arts_block, dict) else ()
            runner_tags = tuple(jb_doc.get("demands") or jb_doc.get("tags") or ())
            jobs.append(Job(
                name=jb_doc.get("job", ""),
                steps=tuple(steps),
                pool_vm_image=pool.get("vmImage"),
                variables=dict(jb_doc.get("variables") or {}),
                artifacts=arts,
                runner_tags=runner_tags,
            ))
        stages.append(Stage(
            name=st_doc.get("stage", ""),
            jobs=tuple(jobs),
            condition=cond,
        ))
    return PipelineSpec(
        name=name_from_doc,
        stages=tuple(stages),
        variables=variables,
        trigger_branches=trigger_branches,
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
