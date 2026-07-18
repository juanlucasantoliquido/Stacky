"""Plan 169 F3 — motor de la corrida (generate→evaluate→select→archive + emisión gateada).

REGLA DURA (G14): SIN threads — se llama `_run_optimization_sync` directo; generador y
fitness SIEMPRE mockeados (cero red/subprocess/DB). El 167/168 reales en el árbol para
create_proposal/inject_proposal_fitness/list_proposals (todo sobre data_dir → tmp_path).
"""
import random

import pytest

import runtime_paths
from config import config as _cfg
from evals import case_store
from services import evolution_optimizer as engine
from services import evolution_optimizer_store as store
from services import evolution_store
from services import fitness_service
from services import variant_generator


@pytest.fixture(autouse=True)
def _tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)
    pdir = tmp_path / "agents"
    pdir.mkdir()
    (pdir / "Developer.agent.md").write_text("# Developer\n" + ("linea util. " * 30), encoding="utf-8")
    (pdir / "EvolutionMutator.agent.md").write_text("# Mutator\n" + ("x " * 30), encoding="utf-8")
    monkeypatch.setattr(case_store, "prompts_dir", lambda: pdir)
    monkeypatch.setattr(_cfg, "LOCAL_LLM_MODEL", "qwen-test")
    return tmp_path


_ASPECT = "agent_prompts/developer"
_TARGET = "Developer.agent.md"


def _mk_run(variants=3, margin=0.02, mode="local"):
    return store.create_run(
        aspect_key=_ASPECT, target_ref=_TARGET,
        generator={"mode": mode, "runtime": None, "model": "qwen-test"},
        use_judge=True, variants_planned=variants, margin_used=margin,
        budget={"limit_tokens": 60000, "tokens_est_in": 0, "tokens_est_out": 0, "exhausted": False},
    )


def _eval_mock(score_by_text, *, gate_by_text=None, per_case=None, critiques=None, record=None):
    counter = {"n": 0}

    def _eval(aspect_key, artifact_text, case_filter=None, generator_model=None, use_judge=True):
        counter["n"] += 1
        if record is not None:
            record.append({"text": artifact_text, "generator_model": generator_model})
        score = score_by_text(artifact_text)
        gate = (gate_by_text or (lambda t: "passed"))(artifact_text)
        return {
            "score": score,
            "passed": bool(score is not None and score >= 0.5),
            "eval_ref": f"eval-{counter['n']}",
            "per_case": per_case if per_case is not None else [],
            "critiques": critiques if critiques is not None else [],
            "cost": {"tokens_in": 1, "tokens_out": 1},
            "deterministic_gate": gate,
        }

    return _eval


def _gen_mock(outputs, model="qwen-test"):
    it = iter(outputs)

    def _gen(*, user_prompt, mode, runtime, on_step=None):
        try:
            spec = dict(next(it))
        except StopIteration:
            spec = {"error": "sin_mas_variantes"}
        base = {"text": None, "lesson": None, "flag_suggestion": None, "model": model,
                "tokens_est_in": 10, "tokens_est_out": 10, "error": None}
        base.update(spec)
        base["_prompt"] = user_prompt
        return base

    return _gen


# 1
def test_list_targets_excluye_denylist():
    targets = engine.list_targets()
    refs = [t["target_ref"] for t in targets]
    assert refs == [_TARGET]  # EvolutionMutator.agent.md excluido (KPI-1 parcial)


# 2
def test_build_mutation_prompt_reflexivo(monkeypatch):
    # Sembrar lección previa + un padre en el archive/pareto.
    parent = store.append_archive_entry(run_id="opt-prev", aspect_key=_ASPECT, target_ref=_TARGET,
                                         kind="variant", verdict="pareto",
                                         artifact_text="PADRE_TEXTO_UTIL del frente", cost_proxy=40)
    store.update_pareto(_ASPECT, [{"variant_id": parent["id"], "run_id": "opt-prev",
                                   "score": 0.8, "cost_proxy": 40, "artifact_hash": "sha256:distinto"}])
    store.append_lesson(run_id="opt-prev", aspect_key=_ASPECT, variant_id=parent["id"],
                        text="agregue seccion de formato", outcome="mejoro", delta=0.05)

    per_case = [{"title": "Estructura minima", "checks": [
        {"kind": "min_len", "ok": False, "detail": "len=10 min=200"}]}]
    monkeypatch.setattr(fitness_service, "evaluate_candidate",
                        _eval_mock(lambda t: 0.5, per_case=per_case,
                                   critiques=["falta formato de salida", "poco detalle"]))
    captured = []
    monkeypatch.setattr(variant_generator, "generate",
                        _gen_mock([{"text": "V1", "lesson": "cambie X"}]))

    def _cap(*, user_prompt, mode, runtime, on_step=None):
        captured.append(user_prompt)
        return {"text": "V1", "lesson": "cambie X", "flag_suggestion": None, "model": "qwen-test",
                "tokens_est_in": 10, "tokens_est_out": 10, "error": None}

    monkeypatch.setattr(variant_generator, "generate", _cap)

    run = _mk_run(variants=1)
    engine._run_optimization_sync(run["id"])
    assert captured, "el generador no recibió prompt"
    prompt = captured[0]
    assert "linea util." in prompt  # texto base (KPI-2)
    assert "falta formato de salida" in prompt and "poco detalle" in prompt  # críticas
    assert "Estructura minima: min_len -> len=10 min=200" in prompt  # check fallado
    assert "agregue seccion de formato" in prompt  # lección previa
    assert "PADRE_TEXTO_UTIL" in prompt  # resumen del padre


# 3
def test_build_mutation_prompt_omite_secciones_vacias(monkeypatch):
    monkeypatch.setattr(fitness_service, "evaluate_candidate",
                        _eval_mock(lambda t: 0.5, per_case=[], critiques=[]))
    captured = []

    def _cap(*, user_prompt, mode, runtime, on_step=None):
        captured.append(user_prompt)
        return {"text": "V1", "lesson": None, "flag_suggestion": None, "model": "qwen-test",
                "tokens_est_in": 10, "tokens_est_out": 10, "error": None}

    monkeypatch.setattr(variant_generator, "generate", _cap)
    run = _mk_run(variants=1)
    engine._run_optimization_sync(run["id"])
    prompt = captured[0]
    assert "CRITICAS DE LA ULTIMA EVALUACION" not in prompt
    assert "LECCIONES DE MUTACIONES PREVIAS" not in prompt
    assert "PADRES DEL FRENTE PARETO" not in prompt
    assert "CHECKS DETERMINISTAS FALLADOS" not in prompt


# 4
def test_corrida_feliz_emite_propuesta(monkeypatch):
    record = []
    scores = {"V1": 0.55, "V2": 0.70, "V3": 0.65}
    base_text = engine.read_target_text(_TARGET)
    monkeypatch.setattr(fitness_service, "evaluate_candidate",
                        _eval_mock(lambda t: 0.60 if t == base_text else scores.get(t), record=record))
    monkeypatch.setattr(variant_generator, "generate",
                        _gen_mock([{"text": "V1", "lesson": "l1"}, {"text": "V2", "lesson": "l2"},
                                   {"text": "V3", "lesson": "l3"}]))
    run = _mk_run(variants=3, margin=0.02)
    engine._run_optimization_sync(run["id"])

    props = evolution_store.list_proposals(origin="optimizer")
    assert len(props) == 1
    p = props[0]
    assert p["status"] == "pending_review"
    assert p["origin"] == "optimizer"
    assert p["proposed_content"] == "V2"
    assert p["fitness_before"]["score"] == pytest.approx(0.60)
    assert p["fitness_after"]["score"] == pytest.approx(0.70)
    assert any(e.startswith("base_hash=") for e in p["evidence"])  # C5
    # C1 — el BASE se evaluó con el MISMO generator_model que las variantes, jamás None.
    gms = {r["generator_model"] for r in record}
    assert None not in gms
    assert len(gms) == 1
    final = store.get_run(run["id"])
    assert final["status"] == "completed"
    assert final["proposal_id"] == p["id"]


# 5
def test_margen_no_alcanzado_no_emite(monkeypatch):
    base_text = engine.read_target_text(_TARGET)
    monkeypatch.setattr(fitness_service, "evaluate_candidate",
                        _eval_mock(lambda t: 0.69 if t == base_text else 0.70))
    monkeypatch.setattr(variant_generator, "generate",
                        _gen_mock([{"text": "A"}, {"text": "B"}, {"text": "C"}]))
    run = _mk_run(variants=3, margin=0.02)
    engine._run_optimization_sync(run["id"])
    assert evolution_store.list_proposals(origin="optimizer") == []
    assert store.get_run(run["id"])["status"] == "no_improvement"


# 6
def test_gate_determinista_bloquea(monkeypatch):
    base_text = engine.read_target_text(_TARGET)
    monkeypatch.setattr(fitness_service, "evaluate_candidate",
                        _eval_mock(lambda t: 0.60 if t == base_text else 0.90,
                                   gate_by_text=lambda t: "passed" if t == base_text else "failed"))
    monkeypatch.setattr(variant_generator, "generate", _gen_mock([{"text": "A"}]))
    run = _mk_run(variants=1, margin=0.02)
    engine._run_optimization_sync(run["id"])
    assert evolution_store.list_proposals(origin="optimizer") == []


# 7
def test_seleccion_pareto_empate_score(monkeypatch):
    # dos variantes score 0.8: costos distintos (texto de longitudes distintas).
    short = "S"  # cost 1
    long_ = "L" * 800  # cost 200
    base_text = engine.read_target_text(_TARGET)
    monkeypatch.setattr(fitness_service, "evaluate_candidate",
                        _eval_mock(lambda t: 0.40 if t == base_text else 0.80))
    monkeypatch.setattr(variant_generator, "generate",
                        _gen_mock([{"text": long_}, {"text": short}]))
    run = _mk_run(variants=2, margin=0.02)
    engine._run_optimization_sync(run["id"])
    winner = store.get_run(run["id"])["winner"]
    assert winner["cost_proxy"] == 1  # la de menor costo (short)


# 8
def test_stop_presupuesto(monkeypatch):
    base_text = engine.read_target_text(_TARGET)
    monkeypatch.setattr(fitness_service, "evaluate_candidate",
                        _eval_mock(lambda t: 0.60 if t == base_text else 0.90))
    monkeypatch.setattr(variant_generator, "generate", _gen_mock([{"text": "A"}, {"text": "B"}]))
    run = store.create_run(
        aspect_key=_ASPECT, target_ref=_TARGET,
        generator={"mode": "local", "runtime": None, "model": "qwen-test"},
        use_judge=True, variants_planned=3, margin_used=0.02,
        budget={"limit_tokens": 5, "tokens_est_in": 0, "tokens_est_out": 0, "exhausted": False},
    )
    engine._run_optimization_sync(run["id"])
    final = store.get_run(run["id"])
    assert final["budget"]["exhausted"] is True
    assert final["status"] == "stopped_budget"


# 9
def test_stop_cancelacion(monkeypatch):
    base_text = engine.read_target_text(_TARGET)
    monkeypatch.setattr(fitness_service, "evaluate_candidate",
                        _eval_mock(lambda t: 0.60 if t == base_text else 0.90))
    run = _mk_run(variants=3, margin=0.02)
    rid = run["id"]
    calls = {"n": 0}

    def _gen(*, user_prompt, mode, runtime, on_step=None):
        calls["n"] += 1
        store.request_cancel(rid)  # el operador cancela tras la 1ª variante
        return {"text": f"V{calls['n']}", "lesson": None, "flag_suggestion": None,
                "model": "qwen-test", "tokens_est_in": 10, "tokens_est_out": 10, "error": None}

    monkeypatch.setattr(variant_generator, "generate", _gen)
    engine._run_optimization_sync(rid)
    final = store.get_run(rid)
    assert final["status"] == "cancelled"
    assert evolution_store.list_proposals(origin="optimizer") == []


# 10
def test_variante_invalida_no_rompe(monkeypatch):
    base_text = engine.read_target_text(_TARGET)
    monkeypatch.setattr(fitness_service, "evaluate_candidate",
                        _eval_mock(lambda t: 0.60 if t == base_text else 0.90))
    monkeypatch.setattr(variant_generator, "generate",
                        _gen_mock([{"text": "V1"}, {"error": "sin_marcador_variante"}, {"text": "V3"}]))
    run = _mk_run(variants=3, margin=0.02)
    engine._run_optimization_sync(run["id"])
    entries = store.read_archive(run_id=run["id"])
    invalids = [e for e in entries if e["verdict"] == "invalid"]
    assert len(invalids) == 1
    assert invalids[0]["invalid_reason"] == "sin_marcador_variante"
    assert store.get_run(run["id"])["status"] == "completed"  # la corrida completó igual


# 11
def test_archive_lineage_y_verdicts(monkeypatch):
    base_text = engine.read_target_text(_TARGET)
    scores = {"V1": 0.55, "V2": 0.70, "V3": 0.65}
    monkeypatch.setattr(fitness_service, "evaluate_candidate",
                        _eval_mock(lambda t: 0.60 if t == base_text else scores.get(t)))
    monkeypatch.setattr(variant_generator, "generate",
                        _gen_mock([{"text": "V1"}, {"text": "V2"}, {"text": "V3"}]))
    run = _mk_run(variants=3, margin=0.02)
    engine._run_optimization_sync(run["id"])
    entries = store.read_archive(run_id=run["id"])
    bases = [e for e in entries if e["kind"] == "base"]
    variants = [e for e in entries if e["kind"] == "variant"]
    assert len(bases) == 1 and len(variants) == 3
    assert all(v["parent_id"] == bases[0]["id"] for v in variants)
    verdicts = {e["verdict"] for e in variants}
    assert "winner" in verdicts
    assert all(v["generator_model"] for v in variants)


# 12
def test_congelador_denylist_y_hotl():
    from services import evolution_apply
    assert "EvolutionMutator.agent.md" in engine._TARGET_DENYLIST
    assert evolution_apply._HOTL_ALLOWED_ASPECTS == frozenset({"knowledge_rag"})  # KPI-1


# 13
def test_congelador_suggestable_flags():
    assert engine._SUGGESTABLE_FLAGS == frozenset({"LOCAL_LLM_MODEL"})
    for f in engine._SUGGESTABLE_FLAGS:
        assert not f.startswith("STACKY_EVOLUTION")
        assert not f.startswith("STACKY_EVAL")


# 14
def test_parent_proposal_id_lineage(monkeypatch):
    base_text = engine.read_target_text(_TARGET)
    monkeypatch.setattr(fitness_service, "evaluate_candidate",
                        _eval_mock(lambda t: 0.60 if t == base_text else 0.90))
    monkeypatch.setattr(variant_generator, "generate", _gen_mock([{"text": "V1"}]))
    run1 = _mk_run(variants=1, margin=0.02)
    engine._run_optimization_sync(run1["id"])
    props1 = evolution_store.list_proposals(origin="optimizer")
    assert len(props1) == 1
    first_id = props1[0]["id"]

    monkeypatch.setattr(variant_generator, "generate", _gen_mock([{"text": "V2"}]))
    run2 = _mk_run(variants=1, margin=0.02)
    engine._run_optimization_sync(run2["id"])
    final2 = store.get_run(run2["id"])
    assert final2["parent_proposal_id"] == first_id


# 15
def test_variante_gigante_o_vacia_no_evalua(monkeypatch):
    base_text = engine.read_target_text(_TARGET)
    record = []
    monkeypatch.setattr(fitness_service, "evaluate_candidate",
                        _eval_mock(lambda t: 0.60, record=record))
    monkeypatch.setattr(variant_generator, "generate",
                        _gen_mock([{"text": "z" * 50000}, {"text": "   "}]))
    run = _mk_run(variants=2, margin=0.02)
    engine._run_optimization_sync(run["id"])
    entries = store.read_archive(run_id=run["id"])
    invalids = {e["invalid_reason"] for e in entries if e["verdict"] == "invalid"}
    assert invalids == {"variante_demasiado_grande", "variante_vacia"}
    # evaluate_candidate SOLO se llamó para el base (C7 — el juez no se gasta en basura).
    assert len(record) == 1
    assert record[0]["text"] == base_text


# 16
def test_base_drift_descarta_propuesta(monkeypatch, tmp_path):
    base_text = engine.read_target_text(_TARGET)
    monkeypatch.setattr(fitness_service, "evaluate_candidate",
                        _eval_mock(lambda t: 0.60 if t == base_text else 0.95))

    def _gen(*, user_prompt, mode, runtime, on_step=None):
        # hook: el operador/otra sesión reescribe el target durante la corrida.
        (tmp_path / "agents" / _TARGET).write_text("# Developer EDITADO\ncambio ajeno", encoding="utf-8")
        return {"text": "GANADORA", "lesson": None, "flag_suggestion": None, "model": "qwen-test",
                "tokens_est_in": 10, "tokens_est_out": 10, "error": None}

    monkeypatch.setattr(variant_generator, "generate", _gen)
    run = _mk_run(variants=1, margin=0.02)
    engine._run_optimization_sync(run["id"])
    assert evolution_store.list_proposals(origin="optimizer") == []
    final = store.get_run(run["id"])
    assert final["status"] == "no_improvement"
    assert any(s["text"] == "base modificado durante la corrida: propuesta descartada"
               for s in final["steps"])


# 17
def test_rng_seed_reproducible(monkeypatch):
    # Sembrar 4 padres en el frente (cada uno con texto en el archive).
    hashes = []
    for i in range(4):
        e = store.append_archive_entry(run_id="opt-seed", aspect_key=_ASPECT, target_ref=_TARGET,
                                       kind="variant", verdict="pareto",
                                       artifact_text=f"PADRE_{i}_texto", cost_proxy=40 + i)
        hashes.append((e["id"], f"sha256:h{i}"))

    def _seed_pareto():
        store.update_pareto(_ASPECT, [{"variant_id": vid, "run_id": "opt-seed", "score": 0.7 + i * 0.01,
                                       "cost_proxy": 40 + i, "artifact_hash": h}
                                      for i, (vid, h) in enumerate(hashes)])

    base_text = engine.read_target_text(_TARGET)
    monkeypatch.setattr(fitness_service, "evaluate_candidate", _eval_mock(lambda t: 0.5))

    captured = []

    def _cap(*, user_prompt, mode, runtime, on_step=None):
        captured.append(user_prompt)
        return {"text": "V", "lesson": None, "flag_suggestion": None, "model": "qwen-test",
                "tokens_est_in": 10, "tokens_est_out": 10, "error": None}

    monkeypatch.setattr(variant_generator, "generate", _cap)

    _seed_pareto()
    run1 = _mk_run(variants=1)
    engine._run_optimization_sync(run1["id"], rng=random.Random(7))
    prompt1 = captured[-1]

    # Re-sembrar el frente al estado original (la corrida 1 lo mutó) y repetir con la MISMA semilla.
    _seed_pareto()
    run2 = _mk_run(variants=1)
    engine._run_optimization_sync(run2["id"], rng=random.Random(7))
    prompt2 = captured[-1]

    def _parents_block(p):
        idx = p.find("PADRES DEL FRENTE PARETO")
        return p[idx:] if idx >= 0 else ""

    assert _parents_block(prompt1) == _parents_block(prompt2)
    assert "PADRE_" in _parents_block(prompt1)  # sí hubo padres muestreados
