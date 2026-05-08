"""FA-15 — Endpoints de glossary auto-build."""
from flask import Blueprint, abort, jsonify, request

from services import glossary_builder
from ._helpers import current_user

bp = Blueprint("glossary", __name__, url_prefix="/glossary")


@bp.get("/entries")
def list_entries():
    project = request.args.get("project")
    return jsonify(glossary_builder.list_entries(project=project))


@bp.post("/entries")
def create_entry():
    p = request.get_json(force=True, silent=True) or {}
    term = p.get("term")
    definition = p.get("definition")
    if not term or not definition:
        abort(400, "term and definition required")
    with __import__("db").session_scope() as session:
        from services.glossary_builder import GlossaryEntry
        entry = GlossaryEntry(
            project=p.get("project"),
            term=term,
            definition=definition,
            auto_generated=False,
            created_by=current_user(),
        )
        session.add(entry)
        session.flush()
        eid = entry.id
    return jsonify({"id": eid}), 201


@bp.get("/candidates")
def list_candidates():
    project = request.args.get("project")
    status = request.args.get("status", "pending")
    return jsonify(glossary_builder.list_candidates(project=project, status=status))


@bp.post("/candidates/scan")
def scan():
    """Dispara el scan de outputs aprobados para extraer nuevos candidatos."""
    p = request.get_json(force=True, silent=True) or {}
    count = glossary_builder.scan_approved(
        project=p.get("project"),
        days=int(p.get("days", 30)),
        min_occurrences=int(p.get("min_occurrences", 2)),
    )
    return jsonify({"new_candidates": count})


@bp.post("/candidates/<int:cid>/promote")
def promote(cid: int):
    p = request.get_json(force=True, silent=True) or {}
    definition = p.get("definition", "")
    if not definition:
        abort(400, "definition required")
    try:
        eid = glossary_builder.promote(cid, definition, created_by=current_user())
    except ValueError as e:
        abort(404, str(e))
    return jsonify({"entry_id": eid})


@bp.post("/candidates/<int:cid>/reject")
def reject(cid: int):
    glossary_builder.reject(cid)
    return jsonify({"ok": True})
