"""
Endpoints agrupados de Fase 4:
- FA-07 /api/release/context
- FA-16 /api/drift/alerts, /api/drift/run, /api/drift/alerts/:id/ack
- FA-25 /api/context/inbox (bookmarklet target)
- FA-15 /api/glossary/* (glosario auto-build)
"""
from flask import Blueprint, abort, jsonify, request

from services import drift_detector, glossary_builder, release_context
from ._helpers import current_user

bp = Blueprint("phase4", __name__, url_prefix="")


# ── FA-07 — release context ──────────────────────────────────

@bp.get("/release/context")
def release_ctx():
    project = request.args.get("project")
    info = release_context.get_release_info(project=project)
    return jsonify(info.to_dict())


@bp.get("/release/block")
def release_block():
    project = request.args.get("project")
    block = release_context.build_context_block(project=project)
    return jsonify(block)


# ── FA-16 — drift detection ──────────────────────────────────

@bp.get("/drift/alerts")
def list_drift_alerts():
    only_unack = request.args.get("unacknowledged", "false").lower() == "true"
    return jsonify(drift_detector.list_alerts(only_unacknowledged=only_unack))


@bp.post("/drift/run")
def run_drift():
    p = request.get_json(force=True, silent=True) or {}
    alerts = drift_detector.run_detection(
        window_days=int(p.get("window_days", 7)),
        min_sample=int(p.get("min_sample", 5)),
    )
    return jsonify({"alerts_generated": len(alerts), "alerts": alerts})


@bp.post("/drift/alerts/<int:alert_id>/ack")
def ack_drift(alert_id: int):
    if not drift_detector.acknowledge(alert_id, user=current_user()):
        abort(404)
    return jsonify({"ok": True})


# ── FA-25 — bookmarklet inbox ────────────────────────────────

@bp.post("/context/inbox")
def context_inbox():
    """
    Recibe texto enviado desde el bookmarklet y lo convierte en un ContextBlock
    que el frontend puede agregar al editor del ticket activo.
    """
    p = request.get_json(force=True, silent=True) or {}
    url = p.get("url") or ""
    selection = p.get("selection") or ""
    title_hint = p.get("title") or url.split("/")[-1][:60] or "Fuente externa"

    if not selection:
        abort(400, "selection is required")

    block = {
        "id": f"bookmarklet-{abs(hash(url + selection)) % 9999:04d}",
        "kind": "auto",
        "title": f"Desde: {title_hint}",
        "content": f"URL: {url}\n\n{selection}",
        "source": {"type": "bookmarklet", "url": url},
    }
    return jsonify({"block": block, "hint": "Abrí el editor y pegá este bloque."})


@bp.get("/context/bookmarklet.js")
def bookmarklet_js():
    """
    Devuelve el código del bookmarklet. El frontend lo muestra como link
    drag-and-drop a la barra de bookmarks.
    """
    from flask import current_app
    base = request.host_url.rstrip("/")
    # El bookmarklet obtiene la selección + URL y las manda al backend.
    code = (
        f"javascript:(function(){{"
        f"var s=window.getSelection().toString();"
        f"if(!s){{alert('Seleccioná texto primero');return;}}"
        f"fetch('{base}/api/context/inbox',{{"
        f"method:'POST',"
        f"headers:{{'Content-Type':'application/json'}},"
        f"body:JSON.stringify({{url:location.href,title:document.title,selection:s}})"
        f"}}).then(r=>r.json()).then(d=>alert('✓ Bloque listo para pegar en Stacky Agents'));"
        f"}})();"
    )
    return code, 200, {"Content-Type": "application/javascript"}


# ── FA-15 — glossary (también registrado en api/glossary.py, acá sólo scan rápido) ──

@bp.post("/glossary/scan")
def glossary_scan():
    p = request.get_json(force=True, silent=True) or {}
    count = glossary_builder.scan_approved(
        project=p.get("project"), days=int(p.get("days", 30))
    )
    return jsonify({"new_candidates": count})
