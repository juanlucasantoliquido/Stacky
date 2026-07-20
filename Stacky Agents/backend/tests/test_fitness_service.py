"""Plan 168 F4 — servicio de fitness: scorecards, contrato 167 (fitness_before/after
sin aplicar) y contrato 169 (evaluate_candidate). Requiere el 167 en el árbol.

REGLA DURA (§2.3): invoke_local_llm SIEMPRE monkeypatcheado.
"""
import json
import types

import pytest

import copilot_bridge
import runtime_paths
from evals import case_store, golden_runner
from services import evolution_store, fitness_service

_PROMPT = (
    "# Rol\nSos el agente Developer de Stacky que implementa tickets.\n"
    "# Contrato de salida\nRespondé con trazabilidad, tests unitarios y compilación.\n"
    "# Límites\nNo inventés datos; pedí lo que falte. Human-in-the-loop siempre.\n"
) * 3


def _resp(score):
    return types.SimpleNamespace(text=json.dumps({"score": score, "critique": "defecto concreto"}))


@pytest.fixture
def svc_env(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "developer.agent.md").write_text(_PROMPT, encoding="utf-8")
    monkeypatch.setattr(case_store, "prompts_dir", lambda: agents_dir)
    goldens = tmp_path / "goldens"
    goldens.mkdir()
    monkeypatch.setattr(golden_runner, "_AGENTS_DIR", goldens)
    monkeypatch.setattr(copilot_bridge, "invoke_local_llm", lambda **kw: _resp(0.5))
    return tmp_path


def _seed_golden(tmp_path):
    d = tmp_path / "goldens" / "developer"
    d.mkdir(parents=True, exist_ok=True)
    (d / "caso_a.json").write_text(
        json.dumps({"name": "caso_a", "agent_type": "developer", "output": "x", "expect": {"min_score": 0}}),
        encoding="utf-8",
    )


def _mk_proposal(artifact_type="prompt_file", target_ref="developer.agent.md",
                 proposed_content="# nuevo prompt\ncontenido propuesto mejorado"):
    return evolution_store.create_proposal(
        aspect_id="agent_prompts", title="mejora", rationale="porque sí",
        origin="manual", artifact_type=artifact_type, target_ref=target_ref,
        proposed_content=proposed_content, initial_status="pending_review",
    )


def test_run_scorecard_persiste_run(svc_env):
    run = fitness_service.run_scorecard(aspect_key="agent_prompts/developer", use_judge=False)
    tail = case_store.read_runs_tail("agent_prompts/developer")
    assert tail and tail[0]["id"] == run["id"]
    assert tail[0]["trigger"] == "manual"


def test_judge_flag_off_no_llama_llm(svc_env, monkeypatch):
    calls = {"n": 0}

    def _counter(**kw):
        calls["n"] += 1
        return _resp(0.9)
    monkeypatch.setattr(copilot_bridge, "invoke_local_llm", _counter)
    monkeypatch.setattr(fitness_service._cfg, "STACKY_EVAL_JUDGE_ENABLED", False)
    run = fitness_service.run_scorecard(aspect_key="agent_prompts/developer", use_judge=True)
    assert calls["n"] == 0
    judge_cases = [pc for pc in run["per_case"] if pc["level"] == "llm_judge"]
    assert judge_cases and all(pc["skip_reason"] == "juez_deshabilitado" for pc in judge_cases)


def test_compute_fitness_prompt_file_both(svc_env):
    p = _mk_proposal()
    result = fitness_service.compute_proposal_fitness(p["id"], which="both", use_judge=True)
    prop = result["proposal"]
    for side in ("fitness_before", "fitness_after"):
        assert set(prop[side].keys()) >= {"score", "metrics", "eval_ref", "evaluated_at"}
    assert prop["fitness_before"]["eval_ref"] != prop["fitness_after"]["eval_ref"]


def test_compute_fitness_no_aplica_nada(svc_env):
    p = _mk_proposal()
    target = svc_env / "agents" / "developer.agent.md"
    before_bytes = target.read_bytes()
    fitness_service.compute_proposal_fitness(p["id"], which="both", use_judge=False)
    assert target.read_bytes() == before_bytes
    assert evolution_store.get_proposal(p["id"])["status"] == "pending_review"


def test_compute_fitness_target_inexistente(svc_env):
    p = _mk_proposal(target_ref="fantasma.agent.md")
    result = fitness_service.compute_proposal_fitness(p["id"], which="before", use_judge=False)
    before = result["proposal"]["fitness_before"]
    assert before["score"] == 0.0
    assert before["metrics"]["reason"] == "artefacto_inexistente"


def test_compute_fitness_path_traversal(svc_env):
    p = _mk_proposal(target_ref="../../config.py")
    with pytest.raises(ValueError) as exc:
        fitness_service.compute_proposal_fitness(p["id"], which="before", use_judge=False)
    assert "target_fuera_de_allowlist" in str(exc.value)


def test_compute_fitness_free_text_rechaza(svc_env):
    p = evolution_store.create_proposal(
        aspect_id="agent_prompts", title="t", rationale="r", origin="manual",
        artifact_type="free_text", initial_status="pending_review",
    )
    with pytest.raises(ValueError) as exc:
        fitness_service.compute_proposal_fitness(p["id"], which="both")
    assert "fitness_not_applicable" in str(exc.value)


def test_behavior_score_solo_before(svc_env):
    _seed_golden(svc_env)
    p = _mk_proposal()
    result = fitness_service.compute_proposal_fitness(p["id"], which="both", use_judge=False)
    prop = result["proposal"]
    assert prop["fitness_before"]["metrics"]["behavior_score"] is not None
    assert prop["fitness_after"]["metrics"]["behavior_cases_skipped"] >= 1


def test_evaluate_candidate_contrato(svc_env):
    case_store.ensure_seed_cases()
    result = fitness_service.evaluate_candidate(
        "agent_prompts/developer", "un candidato de prompt", case_filter=None,
        generator_model="gpt", use_judge=False,
    )
    assert set(result.keys()) == {"score", "passed", "eval_ref", "per_case", "critiques", "cost", "deterministic_gate"}
    assert isinstance(result["critiques"], list)
    tail = case_store.read_runs_tail("agent_prompts/developer")
    assert any(r["trigger"] == "candidate" for r in tail)


def test_inject_proposal_fitness_valida(svc_env):
    p = _mk_proposal()
    with pytest.raises(ValueError) as exc:
        fitness_service.inject_proposal_fitness(p["id"], "after", {"score": 0.5})
    assert "invalid_payload:eval_ref" in str(exc.value)
    updated = fitness_service.inject_proposal_fitness(p["id"], "after", {"score": 0.5, "eval_ref": "eval-x"})
    assert updated["fitness_after"]["score"] == 0.5
    assert updated["fitness_after"]["eval_ref"] == "eval-x"


def test_scorecard_excluye_candidate_y_proposal_after(svc_env):
    case_store.ensure_seed_cases()
    ak = "agent_prompts/developer"
    for trigger, score in (("manual", 0.8), ("candidate", 0.1), ("proposal_after", 0.2)):
        case_store.append_run({
            "id": f"eval-{trigger}", "finished_at": "2026-01-01T00:00:00+00:00",
            "aspect_key": ak, "trigger": trigger, "score": score, "passed": True,
            "deterministic_gate": "passed",
        })
    cards = {c["aspect_key"]: c for c in fitness_service.build_scorecards()}
    card = cards[ak]
    assert card["latest"]["trigger"] == "manual"
    assert [h["score"] for h in card["history"]] == [0.8]
