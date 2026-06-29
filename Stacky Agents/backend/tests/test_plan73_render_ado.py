"""Tests F1 — to_ado_yaml renderer. Plan 73."""
import yaml
import pytest
from services.pipeline_spec import PipelineSpec, Stage, Job, Step, ValidationError
from services.pipeline_renderers import to_ado_yaml


def _minimal_spec(**kwargs) -> PipelineSpec:
    defaults = dict(
        name="my-pipeline",
        stages=(Stage(
            name="build",
            jobs=(Job(
                name="build-job",
                steps=(Step(name="compile", script="make build"),),
            ),),
        ),),
    )
    defaults.update(kwargs)
    return PipelineSpec(**defaults)


def test_f1_minimal_contains_stages():
    result = to_ado_yaml(_minimal_spec())
    assert "stages:" in result
    assert "- stage:" in result or "stage: build" in result
    assert "- job:" in result or "job: build-job" in result
    assert "script:" in result


def test_f1_trigger_branches():
    spec = _minimal_spec(trigger_branches=("main", "develop"))
    result = to_ado_yaml(spec)
    assert "trigger:" in result
    assert "main" in result
    assert "develop" in result


def test_f1_pool_vm_image():
    spec = _minimal_spec(
        stages=(Stage(
            name="build",
            jobs=(Job(
                name="j",
                steps=(Step(name="s", script="echo"),),
                pool_vm_image="ubuntu-latest",
            ),),
        ),)
    )
    result = to_ado_yaml(spec)
    assert "pool:" in result
    assert "vmImage" in result
    assert "ubuntu-latest" in result


def test_f1_raw_yaml_ado_returned_literal():
    spec = _minimal_spec(stages=(), raw_yaml="custom content", raw_yaml_target="ado")
    result = to_ado_yaml(spec)
    assert result == "custom content"


def test_f1_raw_yaml_wrong_target_raises():
    spec = _minimal_spec(stages=(), raw_yaml="custom", raw_yaml_target="gitlab")
    with pytest.raises(ValidationError):
        to_ado_yaml(spec)


def test_f1_yaml_parses_back():
    spec = _minimal_spec(trigger_branches=("main",))
    result = to_ado_yaml(spec)
    parsed = yaml.safe_load(result)
    assert isinstance(parsed, dict)
    assert "stages" in parsed
