"""Plan 168 F2 — Runner de niveles del arnés de fitness (§4.4/§4.5).

Corre casos por la jerarquía de señal (deterministas > ejecución > juez LLM) y
agrega un `score` ponderado con gate determinista duro (anti reward-hacking).
SIN Flask y SIN LLM directo: el juez entra como `judge_fn` inyectable
(colaborador de F3). NUNCA persiste (eso es fitness_service, F4).
"""
from __future__ import annotations

import hashlib
import threading
import time
from datetime import datetime, timezone
from uuid import uuid4

LEVEL_MULTIPLIERS = {"deterministic": 3.0, "execution": 2.0, "llm_judge": 1.0}
SELF_JUDGE_MULTIPLIER = 0.5      # multiplica el peso llm_judge si generador == juez
DETERMINISTIC_FAIL_CAP = 0.49   # techo del score agregado si falla un determinista
PASS_THRESHOLD = 0.7            # passed = gate determinista OK y score >= umbral
_JUDGE_CALL_OVERHEAD_TOKENS = 800  # v2 C4 — estimación fija de system+rúbrica por juicio
MAX_JUDGE_CALLS_PER_RUN = 6      # v2 C4 — tope duro de llamadas al juez por corrida

_RUN_LOCK = threading.Lock()    # single-flight de corridas

_LEVEL_ORDER = {"deterministic": 0, "execution": 1, "llm_judge": 2}


def _estimate_tokens(text: str | None) -> int:
    return max(1, len(text or "") // 4)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def resolve_case_text(case: dict, artifact_text: str | None) -> str | None:
    kind = (case.get("input") or {}).get("kind")
    if kind == "artifact_text":
        return artifact_text
    if kind == "frozen_output":
        return (case.get("input") or {}).get("text")
    return None  # golden_ref -> lo resuelve run_case vía golden_runner


def _base_per_case(case: dict) -> dict:
    return {
        "case_id": case.get("id"),
        "title": case.get("title", ""),
        "level": case.get("level"),
        "subject": case.get("subject"),
        "score": None,
        "passed": False,
        "skipped": False,
        "skip_reason": None,
        "checks": [],
        "critique": None,
        "_weight": float(case.get("weight", 1.0) or 0.0),
    }


def run_case(case: dict, artifact_text: str | None, *, judge_fn=None) -> dict:
    """Devuelve el elemento per_case de §4.5 (con clave interna `_weight` y, si
    hubo juez, `_judge` con el retorno crudo — run_eval las consume y las quita)."""
    pc = _base_per_case(case)
    level = case.get("level")
    input_kind = (case.get("input") or {}).get("kind")

    if level in ("deterministic", "execution"):
        if input_kind == "golden_ref":
            from evals import golden_runner  # lazy

            agent_type = case.get("agent_type")
            golden_name = (case.get("input") or {}).get("golden_name")
            gcases = golden_runner.load_golden_set(agent_type) if agent_type else []
            gc = next((g for g in gcases if g.name == golden_name), None)
            if gc is None:
                pc["skipped"] = True
                pc["skip_reason"] = "golden_no_disponible"
                return pc
            result = golden_runner._evaluate(gc)
            pc["score"] = 1.0 if result.ok else 0.0
            pc["passed"] = bool(result.ok)
            return pc

        text = resolve_case_text(case, artifact_text)
        if text is None:
            pc["skipped"] = True
            pc["skip_reason"] = "sin_artefacto"
            return pc
        from evals import checks as _checks  # lazy

        results = _checks.run_checks(case.get("checks") or [], text)
        pc["checks"] = results
        total = len(results)
        ok = sum(1 for r in results if r.get("ok"))
        pc["score"] = (ok / total) if total else 1.0
        pc["passed"] = ok == total
        return pc

    # level == "llm_judge"
    if judge_fn is None:
        pc["skipped"] = True
        pc["skip_reason"] = "juez_deshabilitado"
        return pc
    text = resolve_case_text(case, artifact_text)
    if text is None:
        pc["skipped"] = True
        pc["skip_reason"] = "sin_artefacto"
        return pc
    jr = judge_fn(case, text) or {}
    pc["_judge"] = jr
    if jr.get("error"):
        pc["skipped"] = True
        pc["skip_reason"] = f"juez_error:{jr.get('error')}"
        return pc
    pc["score"] = _clamp01(float(jr.get("score") or 0.0))
    pc["critique"] = jr.get("critique")
    chk_specs = case.get("checks") or []
    if chk_specs:
        from evals import checks as _checks  # lazy

        results = _checks.run_checks(chk_specs, text)
        pc["checks"] = results
        pc["passed"] = all(r.get("ok") for r in results)
    else:
        pc["passed"] = True
    return pc


def aggregate(per_case: list[dict], *, self_judge_risk: bool) -> dict:
    """Implementa §4.4. Devuelve {score, passed, deterministic_gate, levels}."""
    levels = {
        "deterministic": {"total": 0, "passed": 0},
        "execution": {"total": 0, "passed": 0},
        "llm_judge": {"total": 0, "passed": 0, "skipped": 0},
    }
    for pc in per_case:
        lv = pc.get("level")
        if lv not in levels:
            continue
        levels[lv]["total"] += 1
        if pc.get("skipped"):
            if lv == "llm_judge":
                levels[lv]["skipped"] += 1
        elif pc.get("passed"):
            levels[lv]["passed"] += 1

    det_run = [pc for pc in per_case if pc.get("level") == "deterministic" and not pc.get("skipped")]
    if not det_run:
        gate = "none"
    elif all(pc.get("passed") for pc in det_run):
        gate = "passed"
    else:
        gate = "failed"

    considered = [
        pc for pc in per_case
        if not pc.get("skipped") and pc.get("score") is not None
    ]
    if not considered:
        return {"score": None, "passed": False, "deterministic_gate": gate, "levels": levels}

    num = 0.0
    den = 0.0
    for pc in considered:
        mult = LEVEL_MULTIPLIERS.get(pc.get("level"), 0.0)
        if pc.get("level") == "llm_judge" and self_judge_risk:
            mult *= SELF_JUDGE_MULTIPLIER
        weight = float(pc.get("_weight", 1.0))
        num += weight * mult * float(pc.get("score") or 0.0)
        den += weight * mult
    score = round(num / den, 4) if den else None

    if score is not None and gate == "failed":
        score = min(score, DETERMINISTIC_FAIL_CAP)

    passed = gate != "failed" and score is not None and score >= PASS_THRESHOLD
    return {"score": score, "passed": passed, "deterministic_gate": gate, "levels": levels}


def run_eval(*, aspect_key: str, cases: list[dict], artifact_text: str | None,
             trigger: str, proposal_id: str | None = None,
             judge_fn=None, judge_model: str | None = None,
             generator_model: str | None = None,
             budget_tokens: int = 30000) -> dict:
    """Corre los casos habilitados y devuelve el EvalRun §4.5 (NO persiste)."""
    if not _RUN_LOCK.acquire(blocking=False):
        raise RuntimeError("eval_already_running")
    try:
        started_at = _now_iso()
        t0 = time.time()

        enabled = [c for c in cases if c.get("enabled", True)]
        enabled.sort(key=lambda c: _LEVEL_ORDER.get(c.get("level"), 3))

        self_judge_risk = bool(
            generator_model and judge_model
            and str(generator_model).casefold() == str(judge_model).casefold()
        )

        artifact_hash = None
        if artifact_text is not None:
            artifact_hash = "sha256:" + hashlib.sha256(artifact_text.encode("utf-8")).hexdigest()

        budget = {"limit_tokens": budget_tokens, "exhausted": False, "judge_cases_skipped": 0}
        judge_calls_made = 0
        tokens_acc_in = 0
        tokens_acc_out = 0
        any_judge_success = False
        any_judge_attempt = False
        first_error: str | None = None
        parse_errors = 0
        rubric_versions: dict = {}

        per_case: list[dict] = []
        for case in enabled:
            level = case.get("level")
            if level == "llm_judge" and judge_fn is not None:
                if judge_calls_made >= MAX_JUDGE_CALLS_PER_RUN:
                    pc = _base_per_case(case)
                    pc["skipped"] = True
                    pc["skip_reason"] = "max_judge_calls"
                    budget["judge_cases_skipped"] += 1
                    per_case.append(pc)
                    continue
                resolved = resolve_case_text(case, artifact_text)
                est = _estimate_tokens(resolved) + _JUDGE_CALL_OVERHEAD_TOKENS
                if (tokens_acc_in + tokens_acc_out) + est > budget_tokens:
                    pc = _base_per_case(case)
                    pc["skipped"] = True
                    pc["skip_reason"] = "budget_exhausted"
                    budget["exhausted"] = True
                    budget["judge_cases_skipped"] += 1
                    per_case.append(pc)
                    continue
                pc = run_case(case, artifact_text, judge_fn=judge_fn)
                jr = pc.pop("_judge", None)
                judge_calls_made += 1
                if jr is not None:
                    any_judge_attempt = True
                    tokens_acc_in += int(jr.get("tokens_est_in") or 0)
                    tokens_acc_out += int(jr.get("tokens_est_out") or 0)
                    rid = jr.get("rubric_id")
                    rver = jr.get("rubric_version")
                    if rid is not None and rver is not None:
                        rubric_versions[rid] = rver
                    if jr.get("error") is None:
                        any_judge_success = True
                    else:
                        if jr.get("error") == "judge_parse_error":
                            parse_errors += 1
                        if first_error is None:
                            first_error = jr.get("error")
                per_case.append(pc)
            else:
                pc = run_case(case, artifact_text, judge_fn=(judge_fn if level == "llm_judge" else None))
                per_case.append(pc)

        agg = aggregate(per_case, self_judge_risk=self_judge_risk)

        # Quitar claves internas del per_case final (§4.5 no las incluye).
        clean_per_case = []
        for pc in per_case:
            pc.pop("_weight", None)
            pc.pop("_judge", None)
            clean_per_case.append(pc)

        judge_error = first_error if (not any_judge_success and any_judge_attempt) else None
        judge_shape = {
            "used": any_judge_success,
            "model": judge_model if judge_fn is not None else None,
            "error": judge_error,
            "rubric_versions": rubric_versions,
            "parse_errors": parse_errors,
            "self_judge_risk": self_judge_risk,
        }

        duration_ms = int((time.time() - t0) * 1000)
        return {
            "id": "eval-" + uuid4().hex,
            "started_at": started_at,
            "finished_at": _now_iso(),
            "aspect_key": aspect_key,
            "trigger": trigger,
            "proposal_id": proposal_id,
            "artifact_hash": artifact_hash,
            "score": agg["score"],
            "passed": agg["passed"],
            "deterministic_gate": agg["deterministic_gate"],
            "per_case": clean_per_case,
            "levels": agg["levels"],
            "judge": judge_shape,
            "cost": {
                "tokens_est_in": tokens_acc_in,
                "tokens_est_out": tokens_acc_out,
                "duration_ms": duration_ms,
                "cost_usd": 0.0,
            },
            "budget": budget,
        }
    finally:
        _RUN_LOCK.release()
