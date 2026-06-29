"""Tests F2 — to_gitlab_yaml renderer. Plan 73."""
import yaml
import pytest
from services.pipeline_spec import PipelineSpec, Stage, Job, Step, ValidationError
from services.pipeline_renderers import to_gitlab_yaml


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


def test_f2_minimal_contains_stages():
    result = to_gitlab_yaml(_minimal_spec())
    assert "stages:" in result
    assert "build-job" in result or "build_job" in result
    assert "script:" in result


def test_f2_image():
    spec = _minimal_spec(
        stages=(Stage(
            name="build",
            jobs=(Job(
                name="j",
                steps=(Step(name="s", script="echo"),),
                image="python:3.11",
            ),),
        ),)
    )
    result = to_gitlab_yaml(spec)
    assert "image: python:3.11" in result


def test_f2_runner_tags():
    spec = _minimal_spec(
        stages=(Stage(
            name="build",
            jobs=(Job(
                name="j",
                steps=(Step(name="s", script="echo"),),
                runner_tags=("docker", "linux"),
            ),),
        ),)
    )
    result = to_gitlab_yaml(spec)
    assert "tags:" in result
    assert "docker" in result
    assert "linux" in result


def test_f2_artifacts():
    spec = _minimal_spec(
        stages=(Stage(
            name="build",
            jobs=(Job(
                name="j",
                steps=(Step(name="s", script="echo"),),
                artifacts=("dist/", "*.whl"),
            ),),
        ),)
    )
    result = to_gitlab_yaml(spec)
    assert "artifacts:" in result
    assert "paths:" in result


def test_f2_condition_translated_to_rules():
    step = Step(
        name="s",
        script="echo",
        condition="eq(variables['Build.SourceBranchName'], 'main')",
    )
    spec = _minimal_spec(
        stages=(Stage(
            name="s1",
            jobs=(Job(name="j1", steps=(step,)),),
        ),)
    )
    result = to_gitlab_yaml(spec)
    assert "rules:" in result
    assert "CI_COMMIT_BRANCH" in result or "main" in result


def test_f2_condition_untranslatable_raises():
    step = Step(
        name="s",
        script="echo",
        condition="eq(variables['System.PullRequest.PullRequestId'], 'something-complex')",
    )
    spec = _minimal_spec(
        stages=(Stage(
            name="s1",
            jobs=(Job(name="j1", steps=(step,)),),
        ),)
    )
    with pytest.raises(ValidationError):
        to_gitlab_yaml(spec)


def test_f2_raw_yaml_gitlab_returned_literal():
    spec = _minimal_spec(stages=(), raw_yaml="raw: true", raw_yaml_target="gitlab")
    assert to_gitlab_yaml(spec) == "raw: true"


def test_f2_raw_yaml_wrong_target_raises():
    spec = _minimal_spec(stages=(), raw_yaml="raw: true", raw_yaml_target="ado")
    with pytest.raises(ValidationError):
        to_gitlab_yaml(spec)


def test_f2_yaml_parses_back():
    spec = _minimal_spec()
    result = to_gitlab_yaml(spec)
    parsed = yaml.safe_load(result)
    assert isinstance(parsed, dict)
