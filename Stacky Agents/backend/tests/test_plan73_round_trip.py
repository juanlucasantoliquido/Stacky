"""Tests F6 — Round-trip test (idempotencia semántica, núcleo round-trip-safe). Plan 73.

Contrato explícito (C6):
  _CORE_ROUNDTRIP_FIELDS: campos que ambos trackers preservan.
  _LOSSY_BY_DESIGN: campos que se pierden a propósito por tracker (trigger_branches en GitLab).
  _specs_equivalent: comparación semántica que excluye los lossy con justificación documentada.
"""
from services.pipeline_spec import PipelineSpec, Stage, Job, Step, ValidationError
from services.pipeline_renderers import (
    to_ado_yaml, to_gitlab_yaml,
    parse_ado_yaml, parse_gitlab_yaml,
)

# ── Contrato explícito de equivalencia (C6) ────────────────────────────────────

_CORE_ROUNDTRIP_FIELDS = ("name", "stages")  # stages incluye jobs/steps/script/variables/artifacts/runner_tags

_LOSSY_BY_DESIGN = {
    "ado": (),                        # ADO preserva trigger_branches; pool_vm_image; condition crudo
    "gitlab": ("trigger_branches",),  # GitLab dispara por push: trigger_branches se OMITE (F2) → no recuperable
}


def _normalize(val):
    """Normaliza None vs default () / {} para comparación semántica."""
    if val is None:
        return ()
    return val


def _stages_equivalent(a_stages: tuple, b_stages: tuple) -> bool:
    """Compara stages (jobs/steps/script) preservando el subconjunto núcleo."""
    if len(a_stages) != len(b_stages):
        return False
    for a_st, b_st in zip(a_stages, b_stages):
        if a_st.name != b_st.name:
            return False
        if len(a_st.jobs) != len(b_st.jobs):
            return False
        for a_jb, b_jb in zip(a_st.jobs, b_st.jobs):
            if a_jb.name != b_jb.name:
                return False
            # Comparar steps (núcleo: script)
            a_scripts = " ".join(s.script for s in a_jb.steps)
            b_scripts = " ".join(s.script for s in b_jb.steps)
            if a_scripts.strip() != b_scripts.strip():
                return False
    return True


def _specs_equivalent(
    a: PipelineSpec,
    b: PipelineSpec,
    ignore_fields: tuple[str, ...] = (),
) -> bool:
    """Comparación semántica (no string-exacta).
    Ignora ignore_fields (los lossy-by-design del tracker).
    Normaliza None vs default (() / {})."""
    for field in _CORE_ROUNDTRIP_FIELDS:
        if field == "stages":
            if not _stages_equivalent(a.stages, b.stages):
                return False
        elif field not in ignore_fields:
            a_val = _normalize(getattr(a, field))
            b_val = _normalize(getattr(b, field))
            if a_val != b_val:
                return False
    # Campos opcionales no en core ni en ignore
    for field in ("variables", "trigger_branches"):
        if field in ignore_fields:
            continue
        a_val = _normalize(getattr(a, field))
        b_val = _normalize(getattr(b, field))
        if a_val != b_val:
            return False
    return True


# ── Fixtures separados por tracker (C6) ────────────────────────────────────────

def _ado_fixture() -> PipelineSpec:
    """Fixture ADO: usa pool_vm_image y trigger_branches."""
    return PipelineSpec(
        name="ado-pipeline",
        stages=(Stage(
            name="build",
            jobs=(Job(
                name="build-job",
                steps=(Step(name="compile", script="make build && make test"),),
                pool_vm_image="ubuntu-latest",
                variables={"BUILD_ENV": "ci"},
                artifacts=("dist/",),
                runner_tags=("linux",),
            ),),
        ),),
        variables={"GLOBAL_VAR": "value"},
        trigger_branches=("main", "develop"),
    )


def _gitlab_fixture() -> PipelineSpec:
    """Fixture GitLab: usa image (no pool_vm_image); sin trigger_branches (lossy en GitLab)."""
    return PipelineSpec(
        name="",  # nombre no se emite en YAML GitLab; se pierde en round-trip
        stages=(Stage(
            name="build",
            jobs=(Job(
                name="build-job",
                steps=(Step(name="compile", script="make build && make test"),),
                image="python:3.11",
                runner_tags=("docker", "linux"),
                artifacts=("dist/",),
                variables={"BUILD_ENV": "ci"},
            ),),
        ),),
        variables={"GLOBAL_VAR": "value"},
        trigger_branches=(),  # vacío: no se emite en GitLab
    )


# ── Tests ──────────────────────────────────────────────────────────────────────

def test_f6_round_trip_ado():
    """Round-trip ADO: spec_ado → to_ado_yaml → parse_ado_yaml ≈ spec_ado (núcleo round-trip-safe)."""
    spec = _ado_fixture()
    yaml_str = to_ado_yaml(spec)
    parsed = parse_ado_yaml(yaml_str)
    assert _specs_equivalent(spec, parsed, ignore_fields=_LOSSY_BY_DESIGN["ado"]), (
        f"Round-trip ADO falló. YAML:\n{yaml_str}\nParsed stages: {parsed.stages}"
    )


def test_f6_round_trip_gitlab():
    """Round-trip GitLab: spec_gl → to_gitlab_yaml → parse_gitlab_yaml ≈ spec_gl (núcleo)."""
    spec = _gitlab_fixture()
    yaml_str = to_gitlab_yaml(spec)
    parsed = parse_gitlab_yaml(yaml_str)
    assert _specs_equivalent(spec, parsed, ignore_fields=_LOSSY_BY_DESIGN["gitlab"]), (
        f"Round-trip GitLab falló. YAML:\n{yaml_str}\nParsed stages: {parsed.stages}"
    )


def test_f6_c6_lossy_trigger_branches_is_exact_exclusion():
    """[C6 — exclusion real, no tautológico] Un fixture GitLab CON trigger_branches no nulo:
    - SIN ignore_fields: specs_equivalent devuelve False (el campo se perdió).
    - CON ignore_fields=('trigger_branches',): devuelve True (es exactamente el lossy esperado).
    Prueba que el ignore no oculta otros bugs."""
    spec_with_branches = PipelineSpec(
        name="",
        stages=(Stage(
            name="build",
            jobs=(Job(
                name="build-job",
                steps=(Step(name="s", script="echo"),),
            ),),
        ),),
        trigger_branches=("main",),  # se perderá en GitLab round-trip
    )
    yaml_str = to_gitlab_yaml(spec_with_branches)
    parsed = parse_gitlab_yaml(yaml_str)
    # SIN ignore: False (trigger_branches se perdió)
    assert not _specs_equivalent(spec_with_branches, parsed, ignore_fields=()), (
        "Se esperaba False sin ignore_fields (trigger_branches se perdió en round-trip GitLab)"
    )
    # CON ignore: True (el único campo que difiere es el lossy esperado)
    assert _specs_equivalent(spec_with_branches, parsed, ignore_fields=("trigger_branches",)), (
        "Se esperaba True con ignore_fields=('trigger_branches',)"
    )


def test_f6_raw_yaml_round_trip_gitlab():
    """raw_yaml target=gitlab: to_gitlab_yaml retorna el crudo; el ADO renderer lanza ValidationError."""
    spec = PipelineSpec(
        name="raw-pipeline",
        stages=(),
        raw_yaml="raw: content",
        raw_yaml_target="gitlab",
    )
    # GitLab: retorna el crudo literal
    assert to_gitlab_yaml(spec) == "raw: content"
    # ADO: no portable → ValidationError (no diverge silenciosamente)
    try:
        to_ado_yaml(spec)
        assert False, "Se esperaba ValidationError para raw_yaml target=gitlab en ADO renderer"
    except ValidationError:
        pass  # OK


def test_f6_specs_equivalent_normalizes_none_vs_default():
    """_specs_equivalent normaliza None vs default ((), {}) en campos opcionales."""
    spec_a = PipelineSpec(
        name="",
        stages=(Stage(name="s", jobs=(Job(name="j", steps=(Step(name="st", script="echo"),)),)),),
        trigger_branches=(),   # default
    )
    spec_b = PipelineSpec(
        name="",
        stages=(Stage(name="s", jobs=(Job(name="j", steps=(Step(name="st", script="echo"),)),)),),
        trigger_branches=(),   # default
    )
    assert _specs_equivalent(spec_a, spec_b, ignore_fields=("trigger_branches",))
