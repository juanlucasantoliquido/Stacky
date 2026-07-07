"""Plan 93 F1 — checks PUROS de services/pipeline_preflight.py (tests primero).

Sin I/O, sin config, sin flags, sin red. Todo determinista.
"""
from __future__ import annotations

import copy
from pathlib import Path

from services.pipeline_preflight import (
    check_placeholders,
    referenced_variables,
    check_undefined_variables,
    normalize_check,
    runners_check,
)


def _spec(script: str, target_extra: dict | None = None) -> dict:
    """Spec mínimo con un solo step, para tests de placeholders/variables."""
    job = {
        "name": "job1",
        "steps": [{"name": "step1", "script": script}],
    }
    if target_extra:
        job.update(target_extra)
    return {
        "name": "pipeline-test",
        "stages": [{"name": "stage1", "jobs": [job]}],
        "variables": {},
    }


# ── check_placeholders ──────────────────────────────────────────────────────

def test_f1_placeholder_starter_87_detected():
    spec = _spec('echo "reemplazar por el comando real"')
    result = check_placeholders(spec)
    assert result["status"] == "warn"
    assert "1 paso" in result["title"]


def test_f1_placeholder_plan88_prefix_detected():
    spec = _spec('echo "[stacky] publicar Mul2Bane (entry)"')
    result = check_placeholders(spec)
    assert result["status"] == "warn"


def test_f1_placeholder_real_script_ok():
    spec = _spec(r"robocopy .\out \\srv\in_ /MIR")
    result = check_placeholders(spec)
    assert result["status"] == "ok"


def test_f1_placeholder_literals_frozen():
    """Centinela anti-drift: los literales de PLACEHOLDER_LITERALS coinciden
    byte a byte con starterSpec (frontend) y con _DEFAULT_TEMPLATE (publication_spec.py)."""
    from services.pipeline_preflight import PLACEHOLDER_LITERALS

    frontend_path = (
        Path(__file__).resolve().parents[2] / "frontend" / "src" / "devops" / "specBuilder.ts"
    )
    assert frontend_path.exists()
    frontend_content = frontend_path.read_text(encoding="utf-8")
    assert PLACEHOLDER_LITERALS[0] in frontend_content

    from services.publication_spec import _DEFAULT_TEMPLATE

    # El literal del plan 88 es el prefijo compartido antes de "{process_name}"
    assert _DEFAULT_TEMPLATE.startswith(PLACEHOLDER_LITERALS[1])


# ── referenced_variables / check_undefined_variables ────────────────────────

def test_f1_vars_gitlab_undefined_warn():
    spec = _spec("echo $DEPLOY_PATH")
    result = check_undefined_variables(spec, "gitlab")
    assert result["status"] == "warn"
    assert "DEPLOY_PATH" in str(result)

    spec_defined = _spec("echo $DEPLOY_PATH")
    spec_defined["variables"] = {"DEPLOY_PATH": "x"}
    result_ok = check_undefined_variables(spec_defined, "gitlab")
    assert result_ok["status"] == "ok"


def test_f1_vars_ado_syntax():
    spec_ado = _spec("copy $(DEPLOY_PATH) destino")
    result_ado = check_undefined_variables(spec_ado, "ado")
    assert result_ado["status"] == "warn"

    spec_gitlab = _spec("copy $(DEPLOY_PATH) destino")
    result_gitlab = check_undefined_variables(spec_gitlab, "gitlab")
    assert result_gitlab["status"] == "ok"


def test_f1_vars_predefined_ignored():
    spec_gitlab = _spec("echo $CI_COMMIT_BRANCH")
    assert check_undefined_variables(spec_gitlab, "gitlab")["status"] == "ok"

    spec_ado = _spec("echo $(Build.SourceBranch)")
    assert check_undefined_variables(spec_ado, "ado")["status"] == "ok"


def test_f1_vars_defined_keys_from_plan94():
    spec = _spec("echo $DEPLOY_PATH")
    result = check_undefined_variables(spec, "gitlab", defined_keys=["DEPLOY_PATH"])
    assert result["status"] == "ok"


def test_f1_vars_gitlab_escaped_dollar_ignored():
    spec = _spec("echo $$HOME_LIT")
    result = check_undefined_variables(spec, "gitlab")
    assert result["status"] == "ok"


def test_f1_pure_no_mutation():
    spec = _spec("echo $DEPLOY_PATH")
    spec_copy = copy.deepcopy(spec)
    check_placeholders(spec)
    check_undefined_variables(spec, "gitlab")
    assert spec == spec_copy


# ── referenced_variables (helper directo) ───────────────────────────────────

def test_f1_referenced_variables_gitlab_and_ado():
    spec = _spec("echo ${FOO} && echo $BAR")
    assert referenced_variables(spec, "gitlab") >= {"FOO", "BAR"}

    spec_ado = _spec("copy $(FOO) $(Agent.WorkFolder)")
    result = referenced_variables(spec_ado, "ado")
    assert "FOO" in result
    assert "Agent.WorkFolder" not in result  # predefinida


# ── normalize_check ──────────────────────────────────────────────────────────

def test_f1_normalize_check_fills_contract():
    raw = {"status": "fail", "errors": ["e1", "e2"], "detail": "x"}
    result = normalize_check(raw, "lint_tracker", "YAML válido")
    assert result["id"] == "lint_tracker"
    assert result["title"] == "YAML válido"
    assert "e1" in result["detail"] and "e2" in result["detail"]
    assert set(result.keys()) >= {"id", "status", "title", "detail", "fix_hint"}

    raw_min = {"status": "ok"}
    result_min = normalize_check(raw_min, "lint_tracker", "YAML válido")
    assert result_min["detail"] == ""
    assert result_min["fix_hint"] == ""


# ── runners_check ────────────────────────────────────────────────────────────

def test_f1_runners_no_tags_online_ok():
    spec = _spec("echo hola", target_extra={"runner_tags": []})
    runners_ok = {"status": "ok", "runners": [{"id": 1, "online": True, "tags": []}]}
    assert runners_check(runners_ok, spec)["status"] == "ok"

    runners_none_online = {"status": "ok", "runners": [{"id": 1, "online": False, "tags": []}]}
    assert runners_check(runners_none_online, spec)["status"] == "warn"


def test_f1_runners_tags_no_match_fail():
    spec = _spec("echo hola", target_extra={"runner_tags": ["deploy"]})
    runners_result = {"status": "ok", "runners": [{"id": 1, "online": True, "tags": ["build"]}]}
    result = runners_check(runners_result, spec)
    assert result["status"] == "fail"
    assert "deploy" in str(result)


def test_f1_runners_tags_unknown_unavailable():
    spec = _spec("echo hola", target_extra={"runner_tags": ["deploy"]})
    runners_result = {"status": "ok", "runners": [{"id": 1, "online": True, "tags": None}]}
    result = runners_check(runners_result, spec)
    assert result["status"] == "unavailable"


def test_f1_runners_unavailable_propagates():
    spec = _spec("echo hola", target_extra={"runner_tags": ["deploy"]})
    runners_result = {"status": "unavailable", "detail": "PAT sin scope"}
    result = runners_check(runners_result, spec)
    assert result["status"] == "unavailable"
    assert result["detail"] == "PAT sin scope"
