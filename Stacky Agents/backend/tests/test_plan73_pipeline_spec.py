"""Tests F0 — PipelineSpec dataclass + dict_to_spec. Plan 73."""
import pytest
from services.pipeline_spec import PipelineSpec, Stage, Job, Step, dict_to_spec


def _minimal_spec() -> PipelineSpec:
    return PipelineSpec(
        name="test-pipeline",
        stages=(Stage(
            name="build",
            jobs=(Job(
                name="build-job",
                steps=(Step(name="compile", script="make build"),),
            ),),
        ),),
    )


def test_f0_minimal_spec():
    spec = _minimal_spec()
    assert spec.name == "test-pipeline"
    assert len(spec.stages) == 1
    assert spec.stages[0].jobs[0].steps[0].script == "make build"


def test_f0_raw_yaml_and_target():
    spec = PipelineSpec(
        name="raw-pipeline",
        stages=(),
        raw_yaml="custom yaml content",
        raw_yaml_target="gitlab",
    )
    assert spec.raw_yaml == "custom yaml content"
    assert spec.raw_yaml_target == "gitlab"


def test_f0_multiline_script():
    step = Step(name="multi", script="echo a\necho b\necho c")
    assert "\n" in step.script
    assert "echo b" in step.script


def test_f0_dataclasses_are_frozen():
    spec = _minimal_spec()
    with pytest.raises(Exception):  # FrozenInstanceError
        spec.name = "modified"  # type: ignore

    step = Step(name="s", script="echo")
    with pytest.raises(Exception):
        step.script = "other"  # type: ignore


def test_f0_validate_exists_and_returns_list():
    spec = _minimal_spec()
    result = spec.validate()
    assert isinstance(result, list)
    assert len(result) == 0  # spec mínimo válido → sin errores


def test_f0_dict_to_spec_full():
    d = {
        "name": "p",
        "stages": [
            {
                "name": "s",
                "jobs": [
                    {
                        "name": "j",
                        "steps": [{"name": "st", "script": "echo"}],
                    }
                ],
            }
        ],
    }
    spec = dict_to_spec(d)
    assert spec.name == "p"
    assert spec.stages[0].jobs[0].steps[0].script == "echo"
    # Todos los contenedores son tuple, no list
    assert isinstance(spec.stages, tuple)
    assert isinstance(spec.stages[0].jobs, tuple)
    assert isinstance(spec.stages[0].jobs[0].steps, tuple)


def test_f0_dict_to_spec_empty():
    spec = dict_to_spec({})
    assert spec.name == ""
    assert spec.stages == ()


def test_f0_dict_to_spec_preserves_raw_yaml():
    spec = dict_to_spec({"raw_yaml": "custom: true", "raw_yaml_target": "ado"})
    assert spec.raw_yaml == "custom: true"
    assert spec.raw_yaml_target == "ado"
