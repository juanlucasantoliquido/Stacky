"""FA-05 — endpoints de git context."""
from flask import Blueprint, abort, jsonify, request

from services import git_context

bp = Blueprint("git", __name__, url_prefix="/git")


@bp.get("/file-context")
def file_context_route():
    """GET /api/git/file-context?path=trunk/OnLine/Cobranzas/X.cs"""
    path = request.args.get("path")
    if not path:
        abort(400, "path is required")
    n = request.args.get("n", default=5, type=int)
    return jsonify(git_context.file_context(path, n_commits=n).to_dict())


@bp.post("/context-block")
def context_block():
    """POST /api/git/context-block { paths: [...] } → ContextBlock listo para inyectar."""
    payload = request.get_json(force=True, silent=True) or {}
    paths = payload.get("paths") or []
    n = int(payload.get("n", 3))
    block = git_context.build_context_block(paths, n_commits=n)
    return jsonify(block)
