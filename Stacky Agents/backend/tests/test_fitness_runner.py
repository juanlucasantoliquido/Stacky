"""Plan 168 F2 — checks deterministas + runner de niveles (jerarquía, cap, presupuesto)."""
import types

import pytest

import contract_validator
from evals import checks, fitness_runner, golden_runner


def _case(**kw):
    base = {
        "id": kw.get("id", "c1"),
        "aspect_key": kw.get("aspect_key", "agent_prompts/developer"),
        "agent_type": kw.get("agent_type"),
        "subject": kw.get("subject", "artifact"),
        "level": kw.get("level", "deterministic"),
        "title": kw.get("title", "t"),
        "input": kw.get("input", {"kind": "artifact_text", "text": None, "golden_name": None}),
        "checks": kw.get("checks", []),
        "rubric_id": kw.get("rubric_id"),
        "weight": kw.get("weight", 1.0),
        "origin": kw.get("origin", "manual"),
        "enabled": kw.get("enabled", True),
    }
    return base


def _judge_stub(score=0.5, error=None, tin=10, tout=10, rid="prompt_de_agente", rver=1):
    def _fn(case, text):
        return {"score": score, "error": error, "critique": "defecto X",
                "tokens_est_in": tin, "tokens_est_out": tout,
                "rubric_id": rid, "rubric_version": rver, "model": "m"}
    return _fn


def test_checks_contains_y_regex():
    assert checks.run_check({"kind": "contains", "value": "HOLA"}, "hola mundo")["ok"] is True
    assert checks.run_check({"kind": "contains", "value": "chau"}, "hola")["ok"] is False
    assert checks.run_check({"kind": "regex", "pattern": r"(?m)^#\s"}, "# titulo")["ok"] is True
    bad = checks.run_check({"kind": "regex", "pattern": "("}, "x")
    assert bad["ok"] is False and "regex_invalida" in bad["detail"]


def test_checks_len_y_json():
    assert checks.run_check({"kind": "min_len", "value": 3}, "abcd")["ok"] is True
    assert checks.run_check({"kind": "min_len", "value": 10}, "abcd")["ok"] is False
    assert checks.run_check({"kind": "max_len", "value": 3}, "ab")["ok"] is True
    assert checks.run_check({"kind": "json_valid"}, '{"a": 1}')["ok"] is True
    assert checks.run_check({"kind": "json_valid"}, "no json")["ok"] is False


def test_check_artifact_contract(monkeypatch):
    monkeypatch.setattr(
        contract_validator, "validate",
        lambda at, text: types.SimpleNamespace(score=90, passed=True),
    )
    ok = checks.run_check(
        {"kind": "artifact_contract", "agent_type": "developer", "min_score": 80, "must_pass": True},
        "texto",
    )
    assert ok["ok"] is True
    monkeypatch.setattr(
        contract_validator, "validate",
        lambda at, text: types.SimpleNamespace(score=50, passed=False),
    )
    bad = checks.run_check(
        {"kind": "artifact_contract", "agent_type": "developer", "min_score": 80, "must_pass": True},
        "texto",
    )
    assert bad["ok"] is False


def test_validate_check_spec_desconocido():
    with pytest.raises(ValueError) as exc:
        checks.validate_check_spec({"kind": "magia"})
    assert "unknown_check_kind:magia" in str(exc.value)


def test_run_case_deterministic_score_fraccional():
    case = _case(checks=[{"kind": "contains", "value": "a"}, {"kind": "contains", "value": "zzz"}])
    pc = fitness_runner.run_case(case, "abc")
    assert pc["score"] == 0.5
    assert pc["passed"] is False


def test_run_case_golden_ref(tmp_path, monkeypatch):
    import json
    goldens = tmp_path / "goldens"
    (goldens / "developer").mkdir(parents=True)
    (goldens / "developer" / "caso_a.json").write_text(
        json.dumps({"name": "caso_a", "agent_type": "developer", "output": "x", "expect": {"min_score": 0}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(golden_runner, "_AGENTS_DIR", goldens)
    case = _case(level="execution", subject="output", agent_type="developer",
                 input={"kind": "golden_ref", "text": None, "golden_name": "caso_a"})
    pc = fitness_runner.run_case(case, None)
    assert pc["score"] == 1.0 and pc["skipped"] is False
    case_missing = _case(level="execution", subject="output", agent_type="developer",
                         input={"kind": "golden_ref", "text": None, "golden_name": "nope"})
    pc2 = fitness_runner.run_case(case_missing, None)
    assert pc2["skipped"] is True and pc2["skip_reason"] == "golden_no_disponible"


def test_run_case_judge_skips():
    judge_case = _case(level="llm_judge", rubric_id="prompt_de_agente")
    pc_none = fitness_runner.run_case(judge_case, "texto", judge_fn=None)
    assert pc_none["skipped"] is True and pc_none["skip_reason"] == "juez_deshabilitado"
    pc_err = fitness_runner.run_case(judge_case, "texto", judge_fn=_judge_stub(error="x"))
    assert pc_err["skipped"] is True and pc_err["skip_reason"] == "juez_error:x"
    agg = fitness_runner.aggregate([pc_err], self_judge_risk=False)
    assert agg["score"] is None  # no cuenta en el agregado


def test_guard_deterministic_cap():
    det = _case(id="d", level="deterministic", checks=[{"kind": "contains", "value": "XYZ"}])
    judge = _case(id="j", level="llm_judge", rubric_id="prompt_de_agente")
    run = fitness_runner.run_eval(
        aspect_key="agent_prompts/developer", cases=[det, judge], artifact_text="hello",
        trigger="manual", judge_fn=_judge_stub(score=1.0), judge_model="m",
    )
    assert run["score"] <= 0.49
    assert run["deterministic_gate"] == "failed"
    assert run["passed"] is False


def test_aggregate_ponderacion():
    per_case = [
        {"level": "deterministic", "score": 1.0, "passed": True, "skipped": False, "_weight": 1.0},
        {"level": "llm_judge", "score": 0.0, "passed": True, "skipped": False, "_weight": 1.0},
    ]
    agg = fitness_runner.aggregate(per_case, self_judge_risk=False)
    assert agg["score"] == 0.75


def test_self_judge_risk_pondera_mitad():
    per_case = [
        {"level": "deterministic", "score": 1.0, "passed": True, "skipped": False, "_weight": 1.0},
        {"level": "llm_judge", "score": 0.0, "passed": True, "skipped": False, "_weight": 1.0},
    ]
    agg = fitness_runner.aggregate(per_case, self_judge_risk=True)
    assert agg["score"] == 0.8571


def test_budget_agota():
    j1 = _case(id="j1", level="llm_judge", rubric_id="prompt_de_agente")
    j2 = _case(id="j2", level="llm_judge", rubric_id="prompt_de_agente")
    run = fitness_runner.run_eval(
        aspect_key="a", cases=[j1, j2], artifact_text="x" * 20, trigger="manual",
        judge_fn=_judge_stub(score=0.5, tin=200, tout=200), judge_model="m",
        budget_tokens=1000,
    )
    reasons = {pc["case_id"]: pc.get("skip_reason") for pc in run["per_case"]}
    assert reasons["j2"] == "budget_exhausted"
    assert run["budget"]["exhausted"] is True


def test_reproducibilidad():
    det = _case(id="d", level="deterministic", checks=[{"kind": "contains", "value": "a"}])
    kwargs = dict(aspect_key="a", cases=[det], artifact_text="abc", trigger="manual", judge_fn=None)
    r1 = fitness_runner.run_eval(**kwargs)
    r2 = fitness_runner.run_eval(**kwargs)
    assert r1["score"] == r2["score"]
    assert [(p["case_id"], p["score"], p["passed"]) for p in r1["per_case"]] == \
           [(p["case_id"], p["score"], p["passed"]) for p in r2["per_case"]]


def test_max_judge_calls():
    cases = [_case(id=f"j{i}", level="llm_judge", rubric_id="prompt_de_agente") for i in range(7)]
    run = fitness_runner.run_eval(
        aspect_key="a", cases=cases, artifact_text="texto", trigger="manual",
        judge_fn=_judge_stub(score=0.5, tin=10, tout=10), judge_model="m",
        budget_tokens=1_000_000,
    )
    skipped = [pc for pc in run["per_case"] if pc.get("skip_reason") == "max_judge_calls"]
    assert len(skipped) == 1
    assert run["budget"]["judge_cases_skipped"] == 1
