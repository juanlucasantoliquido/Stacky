"""Tests F3 — _validate_spec + ValidationError. Plan 73."""
import pytest
from services.pipeline_spec import PipelineSpec, Stage, Job, Step, ValidationError, _validate_spec


def _minimal_spec(**kwargs) -> PipelineSpec:
    defaults = dict(
        name="ok-pipeline",
        stages=(Stage(
            name="s1",
            jobs=(Job(
                name="j1",
                steps=(Step(name="st1", script="echo ok"),),
            ),),
        ),),
    )
    defaults.update(kwargs)
    return PipelineSpec(**defaults)


def test_f3_valid_spec_no_errors():
    spec = _minimal_spec()
    assert _validate_spec(spec) == []


def test_f3_empty_name_error():
    spec = _minimal_spec(name="")
    errs = _validate_spec(spec)
    assert any(e.field == "name" for e in errs)


def test_f3_no_stages_error():
    spec = _minimal_spec(stages=())
    errs = _validate_spec(spec)
    assert any(e.field == "stages" for e in errs)


def test_f3_stage_without_jobs():
    spec = _minimal_spec(
        stages=(Stage(name="empty", jobs=()),)
    )
    errs = _validate_spec(spec)
    assert any("jobs" in e.field for e in errs)


def test_f3_job_without_steps():
    spec = _minimal_spec(
        stages=(Stage(
            name="s1",
            jobs=(Job(name="empty-job", steps=()),),
        ),)
    )
    errs = _validate_spec(spec)
    assert any("steps" in e.field for e in errs)


def test_f3_step_empty_script():
    spec = _minimal_spec(
        stages=(Stage(
            name="s1",
            jobs=(Job(
                name="j1",
                steps=(Step(name="st1", script="   "),),
            ),),
        ),)
    )
    errs = _validate_spec(spec)
    assert any("script" in e.field for e in errs)


def test_f3_invalid_raw_yaml_target():
    spec = _minimal_spec(raw_yaml="stuff", raw_yaml_target="invalid")
    errs = _validate_spec(spec)
    assert any(e.field == "raw_yaml_target" for e in errs)


def test_f3_validation_error_is_exception():
    err = ValidationError("x", "y")
    assert isinstance(err, Exception)
    # Se puede raise
    with pytest.raises(ValidationError):
        raise err
