"""Plan 168 F4 — Servicio de fitness: orquesta corridas, persiste EvalRuns,
computa scorecards con tendencia, llena fitness_before/after de las propuestas
del 167 SIN aplicarlas (sandbox de solo-lectura) y expone `evaluate_candidate`
(contrato hacia el 169). Depende de `services/evolution_store.py` (Plan 167).
"""
from __future__ import annotations

from datetime import datetime, timezone

from config import config as _cfg  # G1


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _budget() -> int:
    return int(getattr(_cfg, "STACKY_EVAL_RUN_TOKEN_BUDGET", 30000))


def _judge_enabled() -> bool:
    return bool(getattr(_cfg, "STACKY_EVAL_JUDGE_ENABLED", False))


def _make_judge_fn(use_judge: bool):
    """None si (not use_judge or not _judge_enabled()); si no, un closure que
    resuelve la rúbrica del caso y llama judge.judge_text (v2 C1)."""
    if not use_judge or not _judge_enabled():
        return None
    from evals import judge as _judge

    rubrics = _judge.load_rubrics()

    def _fn(case: dict, text: str) -> dict:
        rid = case.get("rubric_id")
        rubric = rubrics.get(rid)
        if rubric is None:
            return {"error": f"rubrica_no_encontrada:{rid}", "rubric_id": rid,
                    "rubric_version": None, "score": None, "critique": None,
                    "model": _judge.judge_model(), "tokens_est_in": 0, "tokens_est_out": 0}
        return _judge.judge_text(rubric=rubric, text=text, case_title=case.get("title", ""))

    return _fn


def _judge_model_for(judge_fn) -> str | None:
    if judge_fn is None:
        return None
    from evals import judge as _judge

    return _judge.judge_model()


def _artifact_text_for_aspect(aspect_key: str) -> str | None:
    from evals import case_store

    if not aspect_key.startswith("agent_prompts/"):
        return None
    pdir = case_store.prompts_dir()
    if not pdir.exists():
        return None
    for pf in sorted(pdir.glob("*.agent.md")):
        if f"agent_prompts/{case_store.slug_for_prompt_file(pf.name)}" == aspect_key:
            try:
                return pf.read_text(encoding="utf-8")
            except Exception:  # noqa: BLE001
                return None
    return None


def _read_target_prompt(target_ref: str | None) -> str | None:
    """Lee el prompt vigente con allowlist anti path-traversal (espejo 167 F2):
    dentro de prompts_dir() y con sufijo .agent.md. Fuera → ValueError; ausente → None."""
    from evals import case_store

    base = case_store.prompts_dir().resolve()
    if not target_ref:
        raise ValueError("target_fuera_de_allowlist")
    candidate = (base / target_ref).resolve()
    try:
        candidate.relative_to(base)
    except ValueError:
        raise ValueError("target_fuera_de_allowlist")
    if not str(candidate).endswith(".agent.md"):
        raise ValueError("target_fuera_de_allowlist")
    if not candidate.exists():
        return None
    try:
        return candidate.read_text(encoding="utf-8")
    except Exception:  # noqa: BLE001
        return None


def _apply_case_filter(cases: list[dict], case_filter: dict | None) -> list[dict]:
    if not case_filter:
        return cases
    out = cases
    ids = case_filter.get("ids")
    if ids is not None:
        idset = set(ids)
        out = [c for c in out if c.get("id") in idset]
    levels = case_filter.get("levels")
    if levels is not None:
        lvset = set(levels)
        out = [c for c in out if c.get("level") in lvset]
    return out


def _metrics_base(run: dict) -> dict:
    return {
        "passed": run.get("passed"),
        "deterministic_gate": run.get("deterministic_gate"),
        "levels": run.get("levels"),
        "judge_used": (run.get("judge") or {}).get("used"),
    }


def run_scorecard(*, aspect_key: str, use_judge: bool = True) -> dict:
    from evals import case_store, fitness_runner

    case_store.ensure_seed_cases()
    cases = case_store.list_cases(aspect_key=aspect_key, enabled=True)
    artifact_text = _artifact_text_for_aspect(aspect_key)
    judge_fn = _make_judge_fn(use_judge)
    run = fitness_runner.run_eval(
        aspect_key=aspect_key, cases=cases, artifact_text=artifact_text,
        trigger="manual", judge_fn=judge_fn, judge_model=_judge_model_for(judge_fn),
        budget_tokens=_budget(),
    )
    case_store.append_run(run)
    return run


def evaluate_candidate(aspect_key: str, artifact_text: str,
                       case_filter: dict | None = None,
                       generator_model: str | None = None,
                       use_judge: bool = True) -> dict:
    """CONTRATO HACIA EL 169 (§8.2 — NO cambiar firma ni shape de retorno)."""
    from evals import case_store, fitness_runner

    cases = [c for c in case_store.list_cases(aspect_key=aspect_key, enabled=True)
             if c.get("subject") == "artifact"]
    cases = _apply_case_filter(cases, case_filter)
    judge_fn = _make_judge_fn(use_judge)
    run = fitness_runner.run_eval(
        aspect_key=aspect_key, cases=cases, artifact_text=artifact_text,
        trigger="candidate", judge_fn=judge_fn, judge_model=_judge_model_for(judge_fn),
        generator_model=generator_model, budget_tokens=_budget(),
    )
    case_store.append_run(run)
    return {
        "score": run["score"],
        "passed": run["passed"],
        "eval_ref": run["id"],
        "per_case": run["per_case"],
        "critiques": [c["critique"] for c in run["per_case"] if c.get("critique")],
        "cost": run["cost"],
        "deterministic_gate": run["deterministic_gate"],
    }


def compute_proposal_fitness(proposal_id: str, which: str = "both",
                             use_judge: bool = True) -> dict:
    from services import evolution_store
    from evals import case_store, fitness_runner

    p = evolution_store.get_proposal(proposal_id)
    if p is None:
        raise KeyError("proposal_not_found")
    artifact_type = p.get("artifact_type")
    if artifact_type in ("free_text", "flag_change"):
        raise ValueError("fitness_not_applicable")

    if artifact_type == "prompt_file":
        aspect_key = "agent_prompts/" + case_store.slug_for_prompt_file(p.get("target_ref") or "")
        before_text = _read_target_prompt(p.get("target_ref"))  # guard allowlist
        after_text = p.get("proposed_content")
    elif artifact_type == "knowledge_note":
        aspect_key = "knowledge_rag"
        before_text = None
        after_text = p.get("proposed_content")
    else:
        raise ValueError("fitness_not_applicable")

    case_store.ensure_seed_cases()
    all_enabled = case_store.list_cases(aspect_key=aspect_key, enabled=True)
    artifact_cases = [c for c in all_enabled if c.get("subject") == "artifact"]
    output_cases = [c for c in all_enabled if c.get("subject") == "output"]
    judge_fn = _make_judge_fn(use_judge)
    jmodel = _judge_model_for(judge_fn)

    sides = ["before", "after"] if which == "both" else [which]
    runs: dict = {"before": None, "after": None}

    for side in sides:
        if side == "before":
            if artifact_type == "knowledge_note":
                continue  # no hay artefacto previo
            if before_text is None:
                fitness = {"score": 0.0, "metrics": {"reason": "artefacto_inexistente"},
                           "eval_ref": None, "evaluated_at": _now_iso()}
                evolution_store.update_proposal_fields(proposal_id, fitness_before=fitness)
                continue
            run = fitness_runner.run_eval(
                aspect_key=aspect_key, cases=artifact_cases, artifact_text=before_text,
                trigger="proposal_before", proposal_id=proposal_id,
                judge_fn=judge_fn, judge_model=jmodel, budget_tokens=_budget(),
            )
            case_store.append_run(run)
            runs["before"] = run
            behavior_score = None
            if output_cases:
                beh = fitness_runner.run_eval(
                    aspect_key=aspect_key, cases=output_cases, artifact_text=None,
                    trigger="proposal_before", proposal_id=proposal_id,
                    judge_fn=None, judge_model=None, budget_tokens=_budget(),
                )  # aux SOLO para behavior_score — NO se persiste (no contamina el scorecard)
                behavior_score = beh["score"]
            metrics = _metrics_base(run)
            metrics["behavior_score"] = behavior_score
            fitness = {"score": run["score"] if run["score"] is not None else 0.0,
                       "metrics": metrics, "eval_ref": run["id"], "evaluated_at": _now_iso()}
            evolution_store.update_proposal_fields(proposal_id, fitness_before=fitness)
        else:  # after
            run = fitness_runner.run_eval(
                aspect_key=aspect_key, cases=artifact_cases, artifact_text=after_text,
                trigger="proposal_after", proposal_id=proposal_id,
                judge_fn=judge_fn, judge_model=jmodel, budget_tokens=_budget(),
            )
            case_store.append_run(run)
            runs["after"] = run
            metrics = _metrics_base(run)
            metrics["behavior_cases_skipped"] = len(output_cases)
            fitness = {"score": run["score"] if run["score"] is not None else 0.0,
                       "metrics": metrics, "eval_ref": run["id"], "evaluated_at": _now_iso()}
            evolution_store.update_proposal_fields(proposal_id, fitness_after=fitness)

    updated = evolution_store.get_proposal(proposal_id)
    return {"proposal": updated, "runs": runs}


def inject_proposal_fitness(proposal_id: str, which: str, fitness: dict) -> dict:
    """Contrato LITERAL 167 §8.1 (inyección para el 169)."""
    from services import evolution_store

    if which not in ("before", "after"):
        raise ValueError("invalid_payload:which")
    if not isinstance(fitness, dict):
        raise ValueError("invalid_payload:fitness")
    score = fitness.get("score")
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        raise ValueError("invalid_payload:score")
    eval_ref = fitness.get("eval_ref")
    if not isinstance(eval_ref, str) or not eval_ref:
        raise ValueError("invalid_payload:eval_ref")

    payload = dict(fitness)
    payload.setdefault("evaluated_at", _now_iso())
    payload.setdefault("metrics", {})
    field = "fitness_before" if which == "before" else "fitness_after"
    return evolution_store.update_proposal_fields(proposal_id, **{field: payload})


def _summarize_run(run: dict) -> dict:
    # EXACTAMENTE las 7 claves de EvalRunSummaryDto (v2 C9).
    return {k: run.get(k) for k in (
        "id", "finished_at", "aspect_key", "trigger", "score", "passed", "deterministic_gate",
    )}


def build_scorecards() -> list[dict]:
    from evals import case_store

    out: list[dict] = []
    for aspect_key in case_store.list_aspect_keys():
        all_cases = case_store.list_cases(aspect_key=aspect_key)
        enabled = [c for c in all_cases if c.get("enabled")]
        # v2 C3 — SOLO runs manual/proposal_before (candidate y proposal_after
        # evalúan texto NO vigente y contaminarían la tendencia).
        runs = [r for r in case_store.read_runs_tail(aspect_key, 21)
                if r.get("trigger") in ("manual", "proposal_before")]
        latest = _summarize_run(runs[0]) if runs else None
        latest_score = runs[0].get("score") if runs else None
        previous_score = runs[1].get("score") if len(runs) > 1 else None
        delta = (round(latest_score - previous_score, 4)
                 if (latest_score is not None and previous_score is not None) else None)
        history = [{"ts": r.get("finished_at"), "score": r.get("score")} for r in runs[:20]]
        history.reverse()  # viejo -> nuevo
        out.append({
            "aspect_key": aspect_key,
            "latest": latest,
            "previous_score": previous_score,
            "delta": delta,
            "history": history,
            "cases_enabled": len(enabled),
            "cases_total": len(all_cases),
        })
    return out
