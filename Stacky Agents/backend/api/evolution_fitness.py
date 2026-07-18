"""api/evolution_fitness.py — Plan 168: arnés de fitness (contratos §4.8).

Blueprint separado del 167 (mismo url_prefix `/evolution`, nombre distinto —
válido en Flask, rutas no colisionan). `/fitness/health` responde SIEMPRE 200;
el resto está gateado por `_fitness_enabled()` (CENTER && EVAL_HARNESS) → 404
`fitness_disabled` con OFF. Imports de services/evals LAZY dentro de cada handler.
"""
from flask import Blueprint, jsonify, request

from config import config as _cfg  # G1

bp = Blueprint("evolution_fitness", __name__, url_prefix="/evolution")


def _fitness_enabled() -> bool:
    return bool(getattr(_cfg, "STACKY_EVOLUTION_CENTER_ENABLED", False)) and \
        bool(getattr(_cfg, "STACKY_EVAL_HARNESS_ENABLED", False))


def _disabled_resp():
    return jsonify({
        "ok": False, "error": "fitness_disabled",
        "message": "El arnés de fitness está deshabilitado (STACKY_EVAL_HARNESS_ENABLED).",
    }), 404


def _clamp(raw, default: int, lo: int = 1, hi: int = 100) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, value))


def _enabled_arg(raw):
    if raw is None:
        return None
    if str(raw).lower() == "true":
        return True
    if str(raw).lower() == "false":
        return False
    return None


# ── Health (siempre 200) ─────────────────────────────────────────────────────
@bp.get("/fitness/health")
def health():
    return jsonify({
        "ok": True,
        "flag_enabled": _fitness_enabled(),
        "judge_configured": bool(getattr(_cfg, "LOCAL_LLM_ENDPOINT", "")),
    })


# ── Casos ────────────────────────────────────────────────────────────────────
@bp.get("/fitness/cases")
def list_cases():
    if not _fitness_enabled():
        return _disabled_resp()
    from evals import case_store

    case_store.ensure_seed_cases()
    cases = case_store.list_cases(
        aspect_key=request.args.get("aspect_key") or None,
        enabled=_enabled_arg(request.args.get("enabled")),
    )
    return jsonify({"ok": True, "cases": cases})


@bp.post("/fitness/cases")
def create_case():
    if not _fitness_enabled():
        return _disabled_resp()
    from evals import case_store

    body = request.get_json(silent=True) or {}
    try:
        case = case_store.create_case(**body)
    except ValueError as exc:
        return jsonify({"ok": False, "error": "invalid_case", "message": str(exc)}), 400
    return jsonify({"ok": True, "case": case}), 201


@bp.patch("/fitness/cases/<cid>")
def patch_case(cid):
    if not _fitness_enabled():
        return _disabled_resp()
    from evals import case_store

    body = request.get_json(silent=True) or {}
    try:
        case = case_store.patch_case(cid, **body)
    except KeyError:
        return jsonify({"ok": False, "error": "case_not_found"}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": "invalid_case", "message": str(exc)}), 400
    return jsonify({"ok": True, "case": case})


@bp.post("/fitness/cases/from-incident")
def from_incident():
    if not _fitness_enabled():
        return _disabled_resp()
    from evals import case_store
    from services import incident_store
    from services.pii_masker import redact_irreversible

    body = request.get_json(silent=True) or {}
    incident_id = body.get("incident_id")
    inc = incident_store.get_incident(incident_id) if incident_id else None
    if inc is None:
        return jsonify({"ok": False, "error": "incident_not_found"}), 404
    title = inc.get("title") or incident_id
    composed = redact_irreversible(f"{title}\n\n{inc.get('text') or ''}")
    case = case_store.create_case(
        origin="incident", enabled=False, subject="output", level="deterministic",
        aspect_key="knowledge_rag", agent_type=None,
        input={"kind": "frozen_output", "text": composed, "golden_name": None},
        checks=[{"kind": "min_len", "value": 1}],
        source_ref=f"incident:{incident_id}",
        title=f"Caso desde incidencia: {title}",
    )
    return jsonify({"ok": True, "case": case}), 201


@bp.post("/fitness/cases/from-execution")
def from_execution():
    if not _fitness_enabled():
        return _disabled_resp()
    from db import session_scope
    from models import AgentExecution
    from evals import case_store
    from services.pii_masker import redact_irreversible

    body = request.get_json(silent=True) or {}
    try:
        execution_id = int(body.get("execution_id"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "execution_not_found"}), 404
    with session_scope() as session:
        row = session.get(AgentExecution, execution_id)
        if row is None:
            return jsonify({"ok": False, "error": "execution_not_found"}), 404
        if row.status != "completed" or not row.output:
            return jsonify({"ok": False, "error": "execution_not_usable"}), 409
        agent_type = row.agent_type
        output = row.output
    case = case_store.create_case(
        origin="execution", enabled=False, subject="output", level="execution",
        aspect_key=f"agent_prompts/{agent_type}", agent_type=agent_type,
        input={"kind": "frozen_output", "text": redact_irreversible(output), "golden_name": None},
        checks=[{"kind": "artifact_contract", "agent_type": agent_type, "min_score": 0, "must_pass": True}],
        source_ref=f"execution:{execution_id}",
        title=f"Caso desde ejecución #{execution_id} ({agent_type})",
    )
    return jsonify({"ok": True, "case": case}), 201


# ── Corridas ─────────────────────────────────────────────────────────────────
@bp.post("/fitness/run")
def run():
    if not _fitness_enabled():
        return _disabled_resp()
    from services import fitness_service

    body = request.get_json(silent=True) or {}
    aspect_key = body.get("aspect_key")
    if not aspect_key:
        return jsonify({"ok": False, "error": "aspect_key_requerido"}), 400
    use_judge = bool(body.get("use_judge", True))
    try:
        run_obj = fitness_service.run_scorecard(aspect_key=aspect_key, use_judge=use_judge)
    except RuntimeError as exc:
        if "eval_already_running" in str(exc):
            return jsonify({"ok": False, "error": "eval_already_running"}), 409
        raise
    return jsonify({"ok": True, "run": run_obj})


@bp.get("/fitness/runs")
def runs():
    if not _fitness_enabled():
        return _disabled_resp()
    from evals import case_store

    return jsonify({
        "ok": True,
        "runs": case_store.read_runs_tail(
            request.args.get("aspect_key") or None,
            _clamp(request.args.get("limit"), 20),
        ),
    })


@bp.get("/fitness/scorecard")
def scorecard():
    if not _fitness_enabled():
        return _disabled_resp()
    from services import fitness_service

    return jsonify({"ok": True, "scorecards": fitness_service.build_scorecards()})


@bp.get("/fitness/rubrics")
def rubrics():
    if not _fitness_enabled():
        return _disabled_resp()
    from evals import judge

    loaded = judge.load_rubrics()
    return jsonify({
        "ok": True,
        "rubrics": [
            {"id": r["id"], "version": r["version"], "text": r["text"]}
            for r in loaded.values()
        ],
    })


# ── Selfcheck del juez ([ADICIÓN v2]) ────────────────────────────────────────
@bp.post("/fitness/judge/selfcheck")
def judge_selfcheck_post():
    if not _fitness_enabled():
        return _disabled_resp()
    if not bool(getattr(_cfg, "STACKY_EVAL_JUDGE_ENABLED", False)):
        return jsonify({"ok": False, "error": "judge_disabled"}), 409
    from evals import judge

    return jsonify({"ok": True, "selfcheck": judge.judge_selfcheck()})


@bp.get("/fitness/judge/selfcheck")
def judge_selfcheck_get():
    if not _fitness_enabled():
        return _disabled_resp()
    from evals import case_store

    return jsonify({"ok": True, "selfcheck": case_store.read_judge_selfcheck()})


# ── Contratos hacia el 167 (inyección) y el 169 (candidato) ──────────────────
@bp.post("/proposals/<pid>/fitness")
def inject_fitness(pid):
    if not _fitness_enabled():
        return _disabled_resp()
    from services import fitness_service

    body = request.get_json(silent=True) or {}
    try:
        proposal = fitness_service.inject_proposal_fitness(
            pid, body.get("which"), body.get("fitness") or {},
        )
    except KeyError:
        return jsonify({"ok": False, "error": "proposal_not_found"}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": "invalid_payload", "message": str(exc)}), 400
    return jsonify({"ok": True, "proposal": proposal})


@bp.post("/proposals/<pid>/fitness/run")
def proposal_fitness_run(pid):
    if not _fitness_enabled():
        return _disabled_resp()
    from services import fitness_service

    body = request.get_json(silent=True) or {}
    which = body.get("which") or "both"
    use_judge = bool(body.get("use_judge", True))
    try:
        result = fitness_service.compute_proposal_fitness(pid, which=which, use_judge=use_judge)
    except KeyError:
        return jsonify({"ok": False, "error": "proposal_not_found"}), 404
    except ValueError as exc:
        msg = str(exc)
        if "fitness_not_applicable" in msg:
            return jsonify({"ok": False, "error": "fitness_not_applicable", "message": msg}), 409
        if "target_fuera_de_allowlist" in msg:
            return jsonify({"ok": False, "error": "invalid_payload", "message": msg}), 400
        return jsonify({"ok": False, "error": "invalid_payload", "message": msg}), 400
    return jsonify({"ok": True, "proposal": result["proposal"], "runs": result["runs"]})


@bp.post("/fitness/evaluate-candidate")
def evaluate_candidate():
    if not _fitness_enabled():
        return _disabled_resp()
    from services import fitness_service

    body = request.get_json(silent=True) or {}
    aspect_key = body.get("aspect_key")
    artifact_text = body.get("artifact_text")
    if not aspect_key or not isinstance(artifact_text, str):
        return jsonify({"ok": False, "error": "invalid_payload"}), 400
    result = fitness_service.evaluate_candidate(
        aspect_key, artifact_text,
        case_filter=body.get("case_filter"),
        generator_model=body.get("generator_model"),
        use_judge=bool(body.get("use_judge", True)),
    )
    return jsonify({"ok": True, "result": result})
