"""FA-05 — endpoints de git context."""
from flask import Blueprint, abort, jsonify, request

from services import console_repo, git_context

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


# ── Plan 265 F4 — Panel de Repositorio de la consola (SOLO LECTURA) ─────────
# Rutas NUEVAS: /status y /diff no existian antes de este plan. Parsean,
# delegan a services/console_repo.py y serializan — nada de logica acá.

@bp.get("/status")
def console_repo_status_route():
    """GET /api/git/status?workspace=<ruta> — solo lectura, gateado por flag."""
    from config import config as _cfg
    if not getattr(_cfg, "STACKY_CONSOLE_REPO_PANEL_ENABLED", True):
        return jsonify({"error": "feature_disabled", "feature": "STACKY_CONSOLE_REPO_PANEL_ENABLED"}), 404
    workspace_raw = request.args.get("workspace") or ""
    workspace = console_repo.resolve_known_workspace(workspace_raw)
    if workspace is None:
        abort(400, "workspace no registrado")
    return jsonify(console_repo.repo_status(workspace))


@bp.get("/diff")
def console_repo_diff_route():
    """GET /api/git/diff?workspace=<ruta>&path=<archivo> — solo lectura, gateado por flag."""
    from config import config as _cfg
    if not getattr(_cfg, "STACKY_CONSOLE_REPO_PANEL_ENABLED", True):
        return jsonify({"error": "feature_disabled", "feature": "STACKY_CONSOLE_REPO_PANEL_ENABLED"}), 404
    workspace_raw = request.args.get("workspace") or ""
    workspace = console_repo.resolve_known_workspace(workspace_raw)
    if workspace is None:
        abort(400, "workspace no registrado")
    path_raw = request.args.get("path") or ""
    safe_path = console_repo.resolve_safe_path(workspace, path_raw)
    if safe_path is None:
        abort(400, "path invalido")
    return jsonify(console_repo.repo_diff(workspace, safe_path))
