from __future__ import annotations

from datetime import datetime

from flask import Blueprint, Response, jsonify, request

from services.run_digest import compose_digest, to_html, to_markdown

bp = Blueprint("reports", __name__, url_prefix="/reports")


@bp.get("/digest")
def get_digest():
    days = request.args.get("days", default=7, type=int)
    project = (request.args.get("project") or "").strip() or None
    fmt = (request.args.get("fmt") or "json").strip().lower()

    digest = compose_digest(days=days, project=project)
    if fmt == "json":
        return jsonify(digest)

    date_stamp = datetime.utcnow().strftime("%Y%m%d")
    if fmt == "md":
        content = to_markdown(digest)
        return Response(
            content,
            mimetype="text/markdown",
            headers={"Content-Disposition": f"attachment; filename=stacky-digest-{date_stamp}.md"},
        )

    if fmt == "html":
        content = to_html(digest)
        return Response(
            content,
            mimetype="text/html",
            headers={"Content-Disposition": f"attachment; filename=stacky-digest-{date_stamp}.html"},
        )

    return jsonify({"ok": False, "error": "invalid_fmt", "message": "fmt must be json|md|html"}), 400
