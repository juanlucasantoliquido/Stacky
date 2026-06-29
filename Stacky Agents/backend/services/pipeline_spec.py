"""
services/pipeline_spec.py — PipelineSpec dataclass puro + validador determinista.

Plan 73 F0 — dataclass + dict_to_spec + matriz de features v1.
Plan 73 F3 — ValidationError (Exception raisable, C1) + _validate_spec (pura).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


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
class Job:
    name: str
    steps: tuple                        # tuple[Step, ...]
    image: Optional[str] = None         # GitLab image
    pool_vm_image: Optional[str] = None # ADO-specific (ej. "ubuntu-latest")
    runner_tags: tuple = ()             # GitLab tags / ADO demands
    variables: dict = field(default_factory=dict)
    artifacts: tuple = ()               # paths a artifacts (sin cache)
    services: tuple = ()               # GitLab services / ADO container jobs — v1 sólo lista de nombres


@dataclass(frozen=True)
class Stage:
    name: str
    jobs: tuple                        # tuple[Job, ...]
    condition: Optional[str] = None


@dataclass(frozen=True)
class PipelineSpec:
    name: str
    stages: tuple                           # tuple[Stage, ...]
    variables: dict = field(default_factory=dict)
    trigger_branches: tuple = ()           # branches que disparan el pipeline
    raw_yaml: Optional[str] = None         # ESCAPE HATCH: para features no cubiertas
    raw_yaml_target: Optional[str] = None  # "ado" | "gitlab" | None

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
        )

    def _stage(st: dict) -> Stage:
        return Stage(
            name=st.get("name", ""),
            jobs=tuple(_job(j) for j in (st.get("jobs") or [])),
            condition=st.get("condition"),
        )

    return PipelineSpec(
        name=d.get("name", ""),
        stages=tuple(_stage(st) for st in (d.get("stages") or [])),
        variables=dict(d.get("variables") or {}),
        trigger_branches=tuple(d.get("trigger_branches") or ()),
        raw_yaml=d.get("raw_yaml"),
        raw_yaml_target=d.get("raw_yaml_target"),
    )


# ── Validador PURO (F3) ────────────────────────────────────────────────────────

def _validate_spec(spec: PipelineSpec) -> list[ValidationError]:
    """Validación determinista sin LLM. Retorna lista de errores (vacía si OK)."""
    errors: list[ValidationError] = []
    if not spec.name.strip():
        errors.append(ValidationError("name", "name vacío"))
    if not spec.stages:
        errors.append(ValidationError("stages", "sin stages"))
    for i, st in enumerate(spec.stages):
        if not st.jobs:
            errors.append(ValidationError(f"stages[{i}].jobs", "stage sin jobs"))
        for j, jb in enumerate(st.jobs):
            if not jb.steps:
                errors.append(ValidationError(f"stages[{i}].jobs[{j}].steps", "job sin steps"))
            for k, step in enumerate(jb.steps):
                if not step.script.strip():
                    errors.append(ValidationError(
                        f"stages[{i}].jobs[{j}].steps[{k}].script", "step sin script"
                    ))
    if spec.raw_yaml and spec.raw_yaml_target not in ("ado", "gitlab", None):
        errors.append(ValidationError("raw_yaml_target", f"target inválido: {spec.raw_yaml_target}"))
    return errors
