"""Plan 169 F3 — Motor de la corrida del optimizador evolutivo.

El loop generate→evaluate→select→archive de UNA corrida sobre UN artefacto objetivo
(un `*.agent.md`), con mutación reflexiva (GEPA), STOP conditions duras, emisión gateada
de la propuesta (contrato 167 §8.2, `pending_review` — el operador decide SIEMPRE) y
registro completo en el archive append-only con lineage (estilo Darwin Gödel Machine).

Riel duro (§3.1): este módulo NO importa el aplicador de propuestas del 167 — NUNCA
aplica nada. La única salida con efecto es una `ImprovementProposal` en `pending_review`.
El mutador NO se optimiza a sí mismo (`_TARGET_DENYLIST`). `_SUGGESTABLE_FLAGS` es allowlist-only.
"""
from __future__ import annotations

import hashlib
import logging
import random
from uuid import uuid4

from config import config as _cfg  # G1

_SUGGESTABLE_FLAGS = frozenset({"LOCAL_LLM_MODEL"})  # §4.7 — allowlist-only
_TARGET_DENYLIST = frozenset({"EvolutionMutator.agent.md"})  # §4.6
_MAX_CRITIQUES = 6
_MAX_FAILED_CHECKS = 6
_MAX_LESSONS = 10
_PARENT_HEAD_LINES = 40
_VARIANT_MAX_CHARS = 40000  # C7: tope duro del tamaño de una variante
_LOG = logging.getLogger("evolution_optimizer")  # ADICIÓN v2: observabilidad


def _now_iso() -> str:
    from services import evolution_optimizer_store as store
    return store._now_iso()


def _estimate_tokens(text: str) -> int:
    return max(1, len(text or "") // 4)


def _sha256(text: str) -> str:
    return "sha256:" + hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _margin() -> float:
    try:
        pct = int(getattr(_cfg, "STACKY_EVOLUTION_OPTIMIZER_MIN_MARGIN_PCT", 2))
    except (TypeError, ValueError):
        pct = 2
    return max(0, pct) / 100.0


def _variants_planned() -> int:
    try:
        v = int(getattr(_cfg, "STACKY_EVOLUTION_OPTIMIZER_VARIANTS", 3))
    except (TypeError, ValueError):
        v = 3
    return max(1, min(6, v))


def _budget() -> int:
    try:
        return int(getattr(_cfg, "STACKY_EVOLUTION_OPTIMIZER_TOKEN_BUDGET", 60000))
    except (TypeError, ValueError):
        return 60000


# ── Targets ──────────────────────────────────────────────────────────────────
def _last_score(case_store, aspect_key: str):
    for r in case_store.read_runs_tail(aspect_key, 20):
        if r.get("trigger") != "candidate":
            return r.get("score")
    return None


def list_targets() -> list[dict]:
    """Glob tolerante (G15) de prompts_dir()/*.agent.md menos _TARGET_DENYLIST, orden
    alfabético. Shape §4.8 GET /targets."""
    from evals import case_store
    pdir = case_store.prompts_dir()
    try:
        files = sorted(pdir.glob("*.agent.md")) if pdir.exists() else []
    except Exception:  # noqa: BLE001 — G15
        files = []
    out: list[dict] = []
    for pf in files:
        if pf.name in _TARGET_DENYLIST:
            continue
        slug = case_store.slug_for_prompt_file(pf.name)
        aspect_key = "agent_prompts/" + slug
        cases_enabled = len([
            c for c in case_store.list_cases(aspect_key=aspect_key, enabled=True)
            if c.get("subject") == "artifact"
        ])
        out.append({
            "target_ref": pf.name, "aspect_key": aspect_key,
            "cases_enabled": cases_enabled, "last_score": _last_score(case_store, aspect_key),
        })
    return out


def read_target_text(target_ref: str) -> str:
    """Allowlist ANTI path-traversal (espejo del guard 167 F2 / 168 F4)."""
    from evals import case_store
    base = case_store.prompts_dir().resolve()
    candidate = (base / (target_ref or "")).resolve()
    try:
        candidate.relative_to(base)
    except ValueError:
        raise ValueError("target_fuera_de_allowlist")
    if not str(candidate).endswith(".agent.md"):
        raise ValueError("target_fuera_de_allowlist")
    if not candidate.exists():
        raise KeyError("target_not_found")
    return candidate.read_text(encoding="utf-8")


# ── Prompt de mutación reflexiva (§4.5) ──────────────────────────────────────
def build_mutation_prompt(*, base_text, base_score, base_cost, critiques,
                          failed_checks, lessons, parents, k, total) -> str:
    parts: list[str] = []
    parts.append(
        f"ARTEFACTO ACTUAL (score {base_score}, costo {base_cost} tokens est.):\n{base_text}"
    )
    crit = [c for c in (critiques or []) if c][:_MAX_CRITIQUES]
    if crit:
        parts.append("CRITICAS DE LA ULTIMA EVALUACION:\n" + "\n".join(f"- {c}" for c in crit))
    fc = [f for f in (failed_checks or []) if f][:_MAX_FAILED_CHECKS]
    if fc:
        parts.append("CHECKS DETERMINISTAS FALLADOS:\n" + "\n".join(f"- {f}" for f in fc))
    les = (lessons or [])[:_MAX_LESSONS]
    if les:
        lines = [f"- ({l.get('outcome')}, delta {l.get('delta')}) {l.get('text')}" for l in les]
        parts.append("LECCIONES DE MUTACIONES PREVIAS (outcome entre parentesis):\n" + "\n".join(lines))
    if parents:
        blocks = []
        for p in parents:
            head = "\n".join((p.get("text") or "").splitlines()[:_PARENT_HEAD_LINES])
            blocks.append(f"- score {p.get('score')} / costo {p.get('cost_proxy')} tokens est.:\n{head}")
        parts.append("PADRES DEL FRENTE PARETO (variantes previas prometedoras, resumen):\n" + "\n".join(blocks))
    parts.append(f"VARIANTE {k} de {total}. Ataca las criticas senaladas.")
    return "\n\n".join(parts)


def collect_failed_checks(per_case: list[dict]) -> list[str]:
    out: list[str] = []
    for pc in per_case or []:
        title = pc.get("title") or ""
        for chk in pc.get("checks") or []:
            if not chk.get("ok"):
                out.append(f"{title}: {chk.get('kind')} -> {chk.get('detail')}")
    return out


# ── Helpers de emisión ───────────────────────────────────────────────────────
def _join_critiques(critiques) -> str | None:
    if not critiques:
        return None
    joined = " | ".join(str(c) for c in critiques if c)
    return joined[:500] if joined else None


def _lesson_outcome(vscore, base_score):
    if vscore is None:
        return ("invalida", None)
    a, b = round(vscore, 4), round(base_score, 4)
    delta = round(vscore - base_score, 4)
    if a > b:
        return ("mejoro", delta)
    if a < b:
        return ("empeoro", delta)
    return ("igual", delta)


def _build_rationale(margen, critiques, lesson) -> str:
    parts = [f"Margen usado: {margen}."]
    top = [c for c in (critiques or []) if c][:3]
    if top:
        parts.append("Criticas atacadas: " + " | ".join(str(c) for c in top))
    if lesson:
        parts.append(f"Leccion de la ganadora: {lesson}")
    return " ".join(parts)


def _parent_proposal_id(evolution_store, target_ref):
    """C13 — la propuesta MÁS RECIENTE por created_at (list_proposals da updated_at DESC)."""
    props = [p for p in evolution_store.list_proposals(origin="optimizer")
             if p.get("target_ref") == target_ref]
    if not props:
        return None
    props.sort(key=lambda p: p.get("created_at") or "", reverse=True)
    return props[0].get("id")


def _parent_text(store, point):
    vid = point.get("variant_id")
    if not vid:
        return None
    for e in store.read_archive(limit=500):
        if e.get("id") == vid:
            return e.get("artifact_text")
    return None


# ── Arranque de la corrida ───────────────────────────────────────────────────
def start_optimization_run(*, target_ref: str, runtime: str | None, use_judge: bool,
                           rng_seed: int | None = None) -> dict:
    """Validaciones SÍNCRONAS + create_run + lanzar thread. Nombre ÚNICO en el backend
    (C3: 'start_run' colisiona con qa_browser_runner:31)."""
    from services import evolution_optimizer_store as store
    from services import variant_generator

    targets = list_targets()
    target = next((t for t in targets if t["target_ref"] == target_ref), None)
    if target is None:
        raise KeyError("target_not_found")
    if store.any_run_running():
        raise RuntimeError("optimizer_already_running")
    mode, ready = variant_generator.resolve_generator_mode()
    if not ready:
        raise RuntimeError("generator_unavailable")
    norm_runtime = None
    if mode == "runtime":
        norm_runtime = runtime or "github_copilot"
        if norm_runtime not in variant_generator.VALID_RUNTIMES:
            raise ValueError("invalid_payload:runtime")

    model = variant_generator.generator_model_for(mode, norm_runtime)
    run = store.create_run(
        aspect_key=target["aspect_key"], target_ref=target_ref,
        generator={"mode": mode, "runtime": norm_runtime, "model": model},
        use_judge=bool(use_judge), variants_planned=_variants_planned(),
        margin_used=_margin(), rng_seed=rng_seed,
        budget={"limit_tokens": _budget(), "tokens_est_in": 0, "tokens_est_out": 0, "exhausted": False},
    )
    rng = random.Random(rng_seed) if rng_seed is not None else random.Random()
    _start_run_async(run["id"], rng=rng)
    return run


def _start_run_async(run_id: str, *, rng=None) -> None:
    import threading
    threading.Thread(
        target=_run_optimization_sync, args=(run_id,), kwargs={"rng": rng}, daemon=True,
    ).start()


def _fitness_dict(res: dict) -> dict:
    return {
        "score": res.get("score"), "passed": res.get("passed"),
        "deterministic_gate": res.get("deterministic_gate"), "eval_ref": res.get("eval_ref"),
    }


def _run_optimization_sync(run_id: str, *, rng=None) -> dict:
    """EL LOOP. Todo bajo try/except global → status 'error'. G14: los tests llaman esta
    función síncrona directo (nunca el thread real)."""
    from services import evolution_optimizer_store as store
    from services import variant_generator
    from services import fitness_service
    from services import evolution_store

    try:
        run = store.get_run(run_id)
        aspect_key = run["aspect_key"]
        target_ref = run["target_ref"]
        gen_cfg = run["generator"]
        mode = gen_cfg.get("mode")
        runtime = gen_cfg.get("runtime")
        use_judge = run["use_judge"]
        margen = run["margin_used"]
        rng = rng or random.Random()

        _LOG.info("optimizer run %s start target=%s generator=%s", run_id, target_ref, mode)

        # 1) base + base_hash (C5)
        target_text = read_target_text(target_ref)
        base_cost = _estimate_tokens(target_text)
        base_hash = _sha256(target_text)
        store.update_run(run_id, base_hash=base_hash)

        # 2) BASE eval — MISMA vara que las variantes (C1: gen_model JAMÁS None)
        gen_model = variant_generator.generator_model_for(mode, runtime)
        base_res = fitness_service.evaluate_candidate(
            aspect_key, target_text, case_filter=None,
            generator_model=gen_model, use_judge=use_judge,
        )
        base_score = base_res.get("score")
        base_eval_ref = base_res.get("eval_ref")
        base_entry = store.append_archive_entry(
            run_id=run_id, aspect_key=aspect_key, target_ref=target_ref,
            kind="base", verdict="base", parent_id=None,
            fitness=_fitness_dict(base_res), cost_proxy=base_cost,
            critique_summary=_join_critiques(base_res.get("critiques")),
            artifact_text=target_text, generator_model=None,
        )
        store.update_run(run_id, base={
            "variant_id": base_entry["id"], "score": base_score,
            "cost_proxy": base_cost, "eval_ref": base_eval_ref,
        })
        store.append_step(run_id, f"base evaluado: score {base_score}")
        if base_score is None:
            store.append_step(run_id, "base sin score evaluable")
            store.update_run(run_id, status="no_improvement", finished_at=_now_iso())
            _LOG.info("optimizer run %s end status=%s base=%s winner=%s tokens=%s",
                      run_id, "no_improvement", None, None, 0)
            return store.get_run(run_id)

        # 3) señal reflexiva
        critiques = base_res.get("critiques") or []
        failed = collect_failed_checks(base_res.get("per_case") or [])
        lessons = store.read_lessons_tail(aspect_key, _MAX_LESSONS)
        parents = store.sample_parents(aspect_key, base_hash, rng)
        parent_ctx = []
        for p in parents:
            ptext = _parent_text(store, p)
            if ptext:
                parent_ctx.append({"score": p.get("score"), "cost_proxy": p.get("cost_proxy"), "text": ptext})

        # 4) LOOP
        K = run["variants_planned"]
        budget = dict(run["budget"])
        limit_tokens = budget["limit_tokens"]
        tokens_spent = budget["tokens_est_in"] + budget["tokens_est_out"]
        pending_invalid: list[dict] = []
        candidates: list[dict] = []
        flag_suggested = False
        cancelled = False

        for k in range(1, K + 1):
            cur = store.get_run(run_id)
            if cur.get("cancel_requested"):
                cancelled = True
                store.append_step(run_id, "cancelación solicitada por el operador")
                break

            prompt = build_mutation_prompt(
                base_text=target_text, base_score=base_score, base_cost=base_cost,
                critiques=critiques, failed_checks=failed, lessons=lessons,
                parents=parent_ctx, k=k, total=K,
            )
            if tokens_spent + _estimate_tokens(prompt) > limit_tokens:
                budget["exhausted"] = True
                store.update_run(run_id, budget=budget)
                store.append_step(run_id, "presupuesto agotado")
                break

            gen = variant_generator.generate(user_prompt=prompt, mode=mode, runtime=runtime)
            tokens_spent += gen.get("tokens_est_in", 0) + gen.get("tokens_est_out", 0)
            budget["tokens_est_in"] += gen.get("tokens_est_in", 0)
            budget["tokens_est_out"] += gen.get("tokens_est_out", 0)
            store.update_run(run_id, budget=budget)

            def _invalid(reason, lesson=None, model=None):
                pending_invalid.append({
                    "run_id": run_id, "aspect_key": aspect_key, "target_ref": target_ref,
                    "kind": "variant", "parent_id": base_entry["id"], "verdict": "invalid",
                    "invalid_reason": reason, "fitness": None, "cost_proxy": 0,
                    "mutation_lesson": lesson, "generator_model": model,
                })

            if gen.get("error"):
                _invalid(gen["error"], lesson=gen.get("lesson"), model=gen.get("model"))
                store.append_step(run_id, f"variante {k} inválida: {gen['error']}")
                store.update_run(run_id, variants_done=k)
                continue

            vtext = gen["text"]
            # d2 (C7) — límites duros ANTES de evaluar (no gastar juez en basura)
            if not vtext.strip():
                _invalid("variante_vacia", lesson=gen.get("lesson"), model=gen.get("model"))
                store.append_step(run_id, f"variante {k} inválida: variante_vacia")
                store.update_run(run_id, variants_done=k)
                continue
            if len(vtext) > _VARIANT_MAX_CHARS:
                _invalid("variante_demasiado_grande", lesson=gen.get("lesson"), model=gen.get("model"))
                store.append_step(run_id, f"variante {k} inválida: variante_demasiado_grande")
                store.update_run(run_id, variants_done=k)
                continue
            if _sha256(vtext) == base_hash:
                _invalid("variante_identica", lesson=gen.get("lesson"), model=gen.get("model"))
                store.append_step(run_id, f"variante {k} inválida: variante_identica")
                store.update_run(run_id, variants_done=k)
                continue

            fit = fitness_service.evaluate_candidate(
                aspect_key, vtext, case_filter=None,
                generator_model=variant_generator.generator_model_for(mode, runtime),
                use_judge=use_judge,
            )
            vid = "var-" + uuid4().hex
            candidates.append({
                "variant_id": vid, "score": fit.get("score"),
                "cost_proxy": _estimate_tokens(vtext), "eval_ref": fit.get("eval_ref"),
                "passed": fit.get("passed"), "deterministic_gate": fit.get("deterministic_gate"),
                "text": vtext, "critiques": fit.get("critiques") or [],
                "lesson": gen.get("lesson"), "generator_model": gen.get("model"),
            })
            if gen.get("lesson"):
                outcome, delta = _lesson_outcome(fit.get("score"), base_score)
                store.append_lesson(run_id=run_id, aspect_key=aspect_key, variant_id=vid,
                                    text=gen["lesson"], outcome=outcome, delta=delta)
            if not flag_suggested and gen.get("flag_suggestion"):
                fs = gen["flag_suggestion"]
                flag = fs.get("flag")
                if flag in _SUGGESTABLE_FLAGS:
                    evolution_store.create_proposal(
                        aspect_id="config_flags_models",
                        title=f"[Optimizador] Sugerencia de flag {flag}",
                        rationale=str(fs.get("razon") or ""), origin="optimizer",
                        artifact_type="flag_change", target_ref=flag,
                        proposed_content=str(fs.get("value") or ""),
                        evidence=[f"optimizer:{run_id}", f"razon={fs.get('razon')}"],
                        initial_status="pending_review", actor="optimizer",
                    )
                    store.append_step(run_id, f"sugerencia de flag emitida: {flag}")
                    flag_suggested = True
                else:
                    store.append_step(run_id, f"sugerencia de flag descartada: {flag} fuera de allowlist")

            store.append_step(run_id, f"variante {k} evaluada: score {fit.get('score')}")
            store.update_run(run_id, variants_done=k)

        # 5) SELECT (paso diferido: TODAS las entries de variantes se appendean acá, ya
        #    con su verdict definitivo → archive estrictamente append-only)
        front = store.pareto_front([
            {"variant_id": c["variant_id"], "score": c["score"], "cost_proxy": c["cost_proxy"]}
            for c in candidates
        ])
        front_ids = {p["variant_id"] for p in front}
        winner = front[0] if front else None
        winner_cand = next((c for c in candidates if c["variant_id"] == winner["variant_id"]), None) if winner else None

        # 6) EMITIR (§4.6): margen + gate determinista + re-chequeo de drift (C5)
        emitted = False
        proposal_id = None
        parent_proposal_id = None
        winner_for_run = None
        if winner_cand is not None:
            winner_for_run = {
                "variant_id": winner_cand["variant_id"], "score": winner_cand["score"],
                "cost_proxy": winner_cand["cost_proxy"], "eval_ref": winner_cand["eval_ref"],
            }
        if not cancelled and winner_cand is not None and winner_cand["score"] is not None:
            gate_ok = winner_cand["deterministic_gate"] != "failed"
            margin_ok = round(winner_cand["score"], 4) >= round(base_score + margen, 4)
            if gate_ok and margin_ok:
                drift_ok = True
                try:
                    if _sha256(read_target_text(target_ref)) != base_hash:
                        drift_ok = False
                except (KeyError, ValueError):
                    drift_ok = False
                if not drift_ok:
                    store.append_step(run_id, "base modificado durante la corrida: propuesta descartada")
                else:
                    parent_proposal_id = _parent_proposal_id(evolution_store, target_ref)
                    proposal = evolution_store.create_proposal(
                        aspect_id="agent_prompts",
                        title=f"[Optimizador] Mejora de {target_ref}: score {base_score:.2f} -> {winner_cand['score']:.2f}",
                        rationale=_build_rationale(margen, critiques, winner_cand.get("lesson")),
                        origin="optimizer", artifact_type="prompt_file", target_ref=target_ref,
                        proposed_content=winner_cand["text"],
                        evidence=[
                            f"optimizer:{run_id}", f"base_score={base_score}",
                            f"winner_score={winner_cand['score']}", f"margen={margen}",
                            f"eval_base={base_eval_ref}", f"eval_winner={winner_cand['eval_ref']}",
                            f"base_hash={base_hash}",
                        ],
                        initial_status="pending_review",
                        parent_proposal_id=parent_proposal_id, actor="optimizer",
                    )
                    proposal_id = proposal["id"]
                    fitness_service.inject_proposal_fitness(proposal_id, "before", {
                        "score": base_score,
                        "metrics": {"passed": base_res.get("passed"),
                                    "deterministic_gate": base_res.get("deterministic_gate"),
                                    "generator_model": None, "cost_proxy": base_cost},
                        "eval_ref": base_eval_ref, "evaluated_at": _now_iso(),
                    })
                    fitness_service.inject_proposal_fitness(proposal_id, "after", {
                        "score": winner_cand["score"],
                        "metrics": {"passed": winner_cand["passed"],
                                    "deterministic_gate": winner_cand["deterministic_gate"],
                                    "generator_model": winner_cand["generator_model"],
                                    "cost_proxy": winner_cand["cost_proxy"]},
                        "eval_ref": winner_cand["eval_ref"], "evaluated_at": _now_iso(),
                    })
                    emitted = True

        # Appendear TODAS las entries de variantes (verdict final) — append-only.
        for pe in pending_invalid:
            store.append_archive_entry(**pe)
        for c in candidates:
            if emitted and winner_cand is not None and c["variant_id"] == winner_cand["variant_id"]:
                verdict = "winner"
            elif c["variant_id"] in front_ids:
                verdict = "pareto"
            else:
                verdict = "dominated"
            store.append_archive_entry(
                run_id=run_id, aspect_key=aspect_key, target_ref=target_ref, kind="variant",
                parent_id=base_entry["id"], verdict=verdict, id=c["variant_id"],
                fitness={"score": c["score"], "passed": c["passed"],
                         "deterministic_gate": c["deterministic_gate"], "eval_ref": c["eval_ref"]},
                cost_proxy=c["cost_proxy"], critique_summary=_join_critiques(c["critiques"]),
                mutation_lesson=c["lesson"], generator_model=c["generator_model"],
                artifact_text=c["text"],
            )

        # status final
        if cancelled:
            status = "cancelled"
        elif emitted:
            status = "completed"
        elif budget.get("exhausted"):
            status = "stopped_budget"
        else:
            status = "no_improvement"

        # 7) frente Pareto (salvo error)
        pareto_points = [{
            "variant_id": base_entry["id"], "run_id": run_id, "score": base_score,
            "cost_proxy": base_cost, "artifact_hash": base_hash,
        }]
        for c in candidates:
            if c["score"] is not None:
                pareto_points.append({
                    "variant_id": c["variant_id"], "run_id": run_id, "score": c["score"],
                    "cost_proxy": c["cost_proxy"], "artifact_hash": _sha256(c["text"]),
                })
        store.update_pareto(aspect_key, pareto_points)

        # 8) cierre
        store.update_run(run_id, proposal_id=proposal_id, parent_proposal_id=parent_proposal_id,
                         winner=winner_for_run, status=status, finished_at=_now_iso())
        _LOG.info("optimizer run %s end status=%s base=%s winner=%s tokens=%s",
                  run_id, status, base_score,
                  winner_cand["score"] if winner_cand else None,
                  budget["tokens_est_in"] + budget["tokens_est_out"])
        return store.get_run(run_id)
    except Exception as exc:  # noqa: BLE001 — cualquier fallo no recuperable → error
        _LOG.exception("optimizer run %s error", run_id)
        try:
            store.update_run(run_id, status="error", error=str(exc), finished_at=_now_iso())
            store.append_step(run_id, f"error: {exc}")
        except Exception:  # noqa: BLE001
            pass
        return store.get_run(run_id)
