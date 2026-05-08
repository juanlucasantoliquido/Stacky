"""
FA-45 + FA-14 — Endpoints de búsqueda por similitud.
"""
from flask import Blueprint, abort, jsonify, request

from services import similarity

bp = Blueprint("similarity", __name__, url_prefix="/similarity")


@bp.get("/similar")
def similar_for_ticket():
    """FA-45 — top-K execs aprobadas similares a un ticket dado."""
    ticket_id = request.args.get("ticket_id", type=int)
    if not ticket_id:
        abort(400, "ticket_id is required")
    agent_type = request.args.get("agent_type")
    limit = request.args.get("limit", default=5, type=int)
    hits = similarity.find_similar(
        ticket_id=ticket_id, agent_type=agent_type, limit=limit
    )
    return jsonify([h.to_dict() for h in hits])


@bp.get("/graveyard")
def graveyard_search():
    """FA-14 — search outputs descartados / fallidos por texto query."""
    query = request.args.get("q", "").strip()
    if not query:
        abort(400, "q is required")
    agent_type = request.args.get("agent_type")
    limit = request.args.get("limit", default=10, type=int)
    hits = similarity.search_graveyard(
        query=query, agent_type=agent_type, limit=limit
    )
    return jsonify([h.to_dict() for h in hits])
