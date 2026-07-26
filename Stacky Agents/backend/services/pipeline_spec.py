"""
services/pipeline_spec.py — PipelineSpec dataclass puro + validador determinista.

Plan 73 F0 — dataclass + dict_to_spec + matriz de features v1.
Plan 73 F3 — ValidationError (Exception raisable, C1) + _validate_spec (pura).
Plan 243 F1 — TaskStep + DeploymentJob y campos de pipeline ADO real. ADITIVO:
              Step/Job/Stage/PipelineSpec no pierden ni cambian nada, todo campo
              nuevo trae default, y un spec del Plan 73 valida y renderiza igual.

C15 — este módulo NO importa services.cicd_task_catalog y NO valida pertenencia al
catálogo. Es el modelo GENÉRICO del Plan 73: sirve a ADO y a GitLab, y _validate_spec
recibe sólo el spec (no hay `profile` de dónde sacar el catálogo). Acá se valida
FORMA; la pertenencia al catálogo la decide F3 (RS008), donde `profile` es explícito.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

# Formato de referencia de tarea ADO: "VSBuild@1", "PublishCodeCoverageResults@2".
_TASK_REF_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*@\d+$")

# Única estrategia de deployment modelada (evidencia: cd-deploy-test.yml:125-127).
_VALID_STRATEGIES = ("runOnce",)


# ── Validación (F3) ────────────────────────────────────────────────────────────

class ValidationError(Exception):
    """Excepción Y dato: (field, message). Hereda de Exception para poder raise en renderers (C1)."""

    def __init__(self, field: str, message: str):
        self.field = field
        self.message = message
        super().__init__(f"{field}: {message}")


# ── Dataclasses PUROS (F0) ─────────────────────────────────────────────────────

@dataclass(frozen=True)
class Step:
    name: str
    script: str                         # bash/script multi-línea
    working_directory: Optional[str] = None
    condition: Optional[str] = None     # expresión cruda ADO o simplificada
    env: dict = field(default_factory=dict)


@dataclass(frozen=True)
class TaskStep:
    """Plan 243 F1 — paso `- task: X@N` con `inputs:`.

    El 100% de los pasos de los 9 pipelines ADO reales del ecosistema está escrito
    así (ver tests/fixtures/cicd_nl/golden/). Sin esto el panel emite YAML válido
    que no compila nada: compilar WebForms .NET Framework 4.8.1 requiere MSBuild vía
    `- task: VSBuild@1`, no `dotnet build` en un `- script:`.
    """
    name: str                           # displayName
    task: str                           # "VSBuild@1"
    inputs: dict = field(default_factory=dict)
    condition: Optional[str] = None
    env: dict = field(default_factory=dict)


@dataclass(frozen=True)
class DeploymentJob:
    """Plan 243 F1 — job `- deployment:` con `environment:` y `strategy.runOnce`.

    Evidencia: cd-deploy-test.yml:122-149.
    """
    name: str
    environment: str
    strategy: str = "runOnce"
    steps: tuple = ()                   # tuple[TaskStep, ...]
    checkout: bool = True               # `- checkout: self`
    download_artifacts: tuple = ()      # `- download: current` + `artifact: <nombre>`
    display_name: Optional[str] = None


@dataclass(frozen=True)
class Job:
    name: str
    steps: tuple                        # tuple[Step, ...]
    image: Optional[str] = None         # GitLab image
    pool_vm_image: Optional[str] = None # ADO-specific (ej. "ubuntu-latest")
    runner_tags: tuple = ()             # GitLab tags / ADO demands
    variables: dict = field(default_factory=dict)
    artifacts: tuple = ()               # paths a artifacts (sin cache)
    services: tuple = ()               # GitLab services / ADO container jobs — v1 sólo lista de nombres
    # ── Plan 243 F1 (aditivo) ──
    task_steps: tuple = ()              # tuple[TaskStep, ...]
    pool_name: Optional[str] = None     # pool self-hosted por nombre
    depends_on: tuple = ()
    display_name: Optional[str] = None


@dataclass(frozen=True)
class Stage:
    name: str
    jobs: tuple                        # tuple[Job, ...]
    condition: Optional[str] = None
    # ── Plan 243 F1 (aditivo) ──
    deployments: tuple = ()            # tuple[DeploymentJob, ...] — van dentro de `jobs:`
    pool_name: Optional[str] = None    # `pool: name:` a nivel stage (cd-deploy-test.yml:119-120)
    pool_vm_image: Optional[str] = None
    depends_on: tuple = ()
    display_name: Optional[str] = None


@dataclass(frozen=True)
class PipelineSpec:
    name: str
    stages: tuple                           # tuple[Stage, ...]
    variables: dict = field(default_factory=dict)
    trigger_branches: tuple = ()           # branches que disparan el pipeline
    raw_yaml: Optional[str] = None         # ESCAPE HATCH: para features no cubiertas
    raw_yaml_target: Optional[str] = None  # "ado" | "gitlab" | None
    # ── Plan 243 F1 (aditivo) ──
    trigger_disabled: bool = False         # `trigger: none` (agendaweb-ci.yml:13)
    trigger_paths: tuple = ()              # `trigger.paths.include` (ci-cd-online.yml:36-39)
    pr_disabled: bool = False              # `pr: none` (ci-cd-online.yml:44)
    schedules: tuple = ()                  # bloques `schedules:` crudos (nightly-build-online.yml:7)
    parameters: tuple = ()                 # bloques `parameters:` crudos (bootstrap:37)
    pool_vm_image: Optional[str] = None    # `pool: vmImage:` a nivel raíz (ci-cd-online.yml:55-56)
    pool_name: Optional[str] = None        # `pool: name:` a nivel raíz
    # ADO admite tres formas de raíz: `stages:`, `jobs:` o `steps:`. El corpus usa las
    # tres (5 archivos con `steps:`, 1 con `jobs:`, 3 con `stages:`), así que el modelo
    # las representa explícitamente en vez de perderlas en silencio al parsear.
    root_task_steps: tuple = ()            # `steps:` a nivel raíz — tareas (agendaweb-ci.yml:34)
    root_steps: tuple = ()                 # `steps:` a nivel raíz — scripts (tuple[Step, ...])
    root_jobs: tuple = ()                  # `jobs:` a nivel raíz (nightly-build-online.yml)

    def validate(self) -> list[ValidationError]:
        return _validate_spec(self)


# ── Deserializador PURO (F0, FIX C5) ──────────────────────────────────────────

def dict_to_spec(d: dict) -> PipelineSpec:
    """JSON/dict -> PipelineSpec. PURA. Listas JSON -> tuplas; campos ausentes -> defaults.
    No hace I/O ni valida (la validación es _validate_spec en F3)."""
    def _step(s: dict) -> Step:
        return Step(
            name=s.get("name", ""),
            script=s.get("script", ""),
            working_directory=s.get("working_directory"),
            condition=s.get("condition"),
            env=dict(s.get("env") or {}),
        )

    def _task_step(s: dict) -> TaskStep:
        """Plan 243 F1 — mismo patrón puro que _step."""
        return TaskStep(
            name=s.get("name", ""),
            task=s.get("task", ""),
            inputs=s.get("inputs") if isinstance(s.get("inputs"), dict) else dict(s.get("inputs") or {}),
            condition=s.get("condition"),
            env=dict(s.get("env") or {}),
        )

    def _deployment(dp: dict) -> DeploymentJob:
        """Plan 243 F1 — mismo patrón puro que _job."""
        return DeploymentJob(
            name=dp.get("name", ""),
            environment=dp.get("environment", ""),
            strategy=dp.get("strategy", "runOnce"),
            steps=tuple(_task_step(s) for s in (dp.get("steps") or [])),
            checkout=bool(dp.get("checkout", True)),
            download_artifacts=tuple(dp.get("download_artifacts") or ()),
            display_name=dp.get("display_name"),
        )

    def _job(j: dict) -> Job:
        return Job(
            name=j.get("name", ""),
            steps=tuple(_step(s) for s in (j.get("steps") or [])),
            image=j.get("image"),
            pool_vm_image=j.get("pool_vm_image"),
            runner_tags=tuple(j.get("runner_tags") or ()),
            variables=dict(j.get("variables") or {}),
            artifacts=tuple(j.get("artifacts") or ()),
            services=tuple(j.get("services") or ()),
            task_steps=tuple(_task_step(s) for s in (j.get("task_steps") or [])),
            pool_name=j.get("pool_name"),
            depends_on=tuple(j.get("depends_on") or ()),
            display_name=j.get("display_name"),
        )

    def _stage(st: dict) -> Stage:
        return Stage(
            name=st.get("name", ""),
            jobs=tuple(_job(j) for j in (st.get("jobs") or [])),
            condition=st.get("condition"),
            deployments=tuple(_deployment(dp) for dp in (st.get("deployments") or [])),
            pool_name=st.get("pool_name"),
            pool_vm_image=st.get("pool_vm_image"),
            depends_on=tuple(st.get("depends_on") or ()),
            display_name=st.get("display_name"),
        )

    return PipelineSpec(
        name=d.get("name", ""),
        stages=tuple(_stage(st) for st in (d.get("stages") or [])),
        variables=dict(d.get("variables") or {}),
        trigger_branches=tuple(d.get("trigger_branches") or ()),
        raw_yaml=d.get("raw_yaml"),
        raw_yaml_target=d.get("raw_yaml_target"),
        trigger_disabled=bool(d.get("trigger_disabled", False)),
        trigger_paths=tuple(d.get("trigger_paths") or ()),
        pr_disabled=bool(d.get("pr_disabled", False)),
        schedules=tuple(d.get("schedules") or ()),
        parameters=tuple(d.get("parameters") or ()),
        pool_vm_image=d.get("pool_vm_image"),
        pool_name=d.get("pool_name"),
        root_task_steps=tuple(_task_step(s) for s in (d.get("root_task_steps") or [])),
        root_steps=tuple(_step(s) for s in (d.get("root_steps") or [])),
        root_jobs=tuple(_job(j) for j in (d.get("root_jobs") or [])),
    )


# ── Validador PURO (F3) ────────────────────────────────────────────────────────

def _validate_task_step(step: "TaskStep", where: str) -> list[ValidationError]:
    """Plan 243 F1 — validación de FORMA de un TaskStep. NO consulta el catálogo (C15)."""
    errors: list[ValidationError] = []
    ref = str(step.task or "").strip()
    if not ref:
        errors.append(ValidationError(f"{where}.task", "task vacía"))
    elif not _TASK_REF_RE.match(ref):
        errors.append(ValidationError(
            f"{where}.task", f"formato de tarea inválido: {step.task!r} (se espera Nombre@N)"
        ))
    if not isinstance(step.inputs, dict):
        errors.append(ValidationError(f"{where}.inputs", "inputs debe ser un dict"))
    return errors


def _validate_spec(spec: PipelineSpec) -> list[ValidationError]:
    """Validación determinista sin LLM. Retorna lista de errores (vacía si OK)."""
    errors: list[ValidationError] = []
    if not spec.name.strip():
        errors.append(ValidationError("name", "name vacío"))
    # Plan 243 F1: un pipeline con `steps:` o `jobs:` a nivel raíz (agendaweb-ci.yml:34,
    # nightly-build-online.yml) no tiene stages y es perfectamente válido en ADO.
    if not spec.stages and not spec.root_task_steps and not spec.root_steps and not spec.root_jobs:
        errors.append(ValidationError("stages", "sin stages"))
    for k, step in enumerate(spec.root_task_steps):
        errors.extend(_validate_task_step(step, f"root_task_steps[{k}]"))
    for j, jb in enumerate(spec.root_jobs):
        for k, tstep in enumerate(jb.task_steps):
            errors.extend(_validate_task_step(tstep, f"root_jobs[{j}].task_steps[{k}]"))
    for i, st in enumerate(spec.stages):
        if not st.jobs and not st.deployments:
            errors.append(ValidationError(f"stages[{i}].jobs", "stage sin jobs"))
        for j, jb in enumerate(st.jobs):
            # Plan 243 F1: un job puede ser task-only. Sólo es inválido si no tiene
            # NINGUNA de las dos formas de paso.
            if not jb.steps and not jb.task_steps:
                errors.append(ValidationError(f"stages[{i}].jobs[{j}].steps", "job sin steps"))
            for k, step in enumerate(jb.steps):
                if not step.script.strip():
                    errors.append(ValidationError(
                        f"stages[{i}].jobs[{j}].steps[{k}].script", "step sin script"
                    ))
            for k, tstep in enumerate(jb.task_steps):
                errors.extend(_validate_task_step(
                    tstep, f"stages[{i}].jobs[{j}].task_steps[{k}]"
                ))
        for d, dp in enumerate(st.deployments):
            where = f"stages[{i}].deployments[{d}]"
            if not str(dp.environment or "").strip():
                errors.append(ValidationError(f"{where}.environment", "environment vacío"))
            if dp.strategy not in _VALID_STRATEGIES:
                errors.append(ValidationError(
                    f"{where}.strategy",
                    f"strategy inválida: {dp.strategy!r} (soportadas: {', '.join(_VALID_STRATEGIES)})"
                ))
            if not dp.steps:
                errors.append(ValidationError(f"{where}.steps", "deployment sin steps"))
            for k, tstep in enumerate(dp.steps):
                errors.extend(_validate_task_step(tstep, f"{where}.steps[{k}]"))
    if spec.raw_yaml and spec.raw_yaml_target not in ("ado", "gitlab", None):
        errors.append(ValidationError("raw_yaml_target", f"target inválido: {spec.raw_yaml_target}"))
    return errors
