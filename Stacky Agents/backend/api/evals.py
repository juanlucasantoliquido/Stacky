"""V2.3 (plan 22) — API del golden loop: promote-to-golden + historia de evals.

- POST /api/evals/promote {execution_id}  → convierte un run `completed` en golden
  (reusa evals.harvest, que aplica redact_irreversible/PII).
- GET  /api/evals/eval-history?agent_type=X → tendencia de scores por agent_type.

(Plan §V2.3 menciona /api/metrics/eval-history; se consolida acá junto a promote
por cohesión — ambas son preocupaciones de evals. La ruta vive bajo /api/evals.)
"""
import logging

from flask import Blueprint, abort, jsonify, request

logger = logging.getLogger("stacky_agents.api.evals")

bp = Blueprint("evals", __name__, url_prefix="/evals")


@bp.post("/promote")
def promote_to_golden():
    payload = request.get_json(force=True, silent=True) or {}
    execution_id = payload.get("execution_id")
    if not execution_id:
        abort(400, "execution_id is required")
    try:
        execution_id = int(execution_id)
    except (TypeError, ValueError):
        abort(400, "execution_id must be an integer")

    from evals.harvest import harvest, HarvestError

    try:
        out_path = harvest(execution_id=execution_id, name=payload.get("name"))
    except HarvestError as exc:
        # run inexistente / no completado / sin output → 409 con el detalle.
        return jsonify({"ok": False, "error": "harvest_failed", "detail": str(exc)}), 409

    return jsonify({"ok": True, "golden_path": str(out_path)}), 201


@bp.get("/eval-history")
def eval_history():
    from services import eval_history as _hist

    agent_type = (request.args.get("agent_type") or "").strip() or None
    limit = request.args.get("limit", default=50, type=int)
    return jsonify({"runs": _hist.list_runs(agent_type, limit=limit)})
