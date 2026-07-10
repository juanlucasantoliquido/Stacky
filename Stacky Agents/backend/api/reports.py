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

    # Plan 117 — narrativa local opt-in. Sin ?narrate=1 el payload es byte-idéntico al actual.
    if request.args.get("narrate") == "1":
        import config as _config
        from services.local_insights import narrate_digest

        cfg = _config.config
        enabled = (
            getattr(cfg, "STACKY_LOCAL_INSIGHTS_ENABLED", False)
            and getattr(cfg, "STACKY_LOCAL_INSIGHTS_DIGEST_NARRATIVE_ENABLED", False)
            and getattr(cfg, "LOCAL_LLM_ENABLED", False)
            and bool(getattr(cfg, "LOCAL_LLM_ENDPOINT", ""))
        )
        if not enabled:
            digest["narrative"] = None
            digest["narrative_error"] = "narrative_disabled"
        else:
            try:
                digest["narrative"] = narrate_digest(digest)
                digest["narrative_error"] = None
            except Exception as e:  # noqa: BLE001 — el digest NUNCA falla por la narrativa
                digest["narrative"] = None
                digest["narrative_error"] = str(e)[:200]

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
