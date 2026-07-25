"""Plan 238 F2 -- Bandeja de incidencias abiertas (solo lectura).

Blueprint independiente: NO se toca backend/api/tickets.py (351 KB, disputado
por los planes 212/213 y por una sesion paralela viva).
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

bp = Blueprint("incident_inbox", __name__, url_prefix="/incident-inbox")


def _enabled() -> bool:
    # GOTCHA REAL: `config` importado como MODULO devuelve el default y mata el
    # branch OFF. La instancia es `config.config`.
    from config import config as _cfg
    return bool(getattr(_cfg, "STACKY_INCIDENT_INBOX_ENABLED", True))


def _feature_disabled_response():
    return jsonify({"ok": False, "error": "feature_disabled"}), 404


def _profile_for(project_name: str | None) -> dict | None:
    """client_profile del proyecto activo. Nunca lanza: si no se puede leer,
    devuelve None y el resolvedor cae al default.

    Simbolos verificados 2026-07-25:
      services/client_profile.py    def load_client_profile(project_name)
      services/project_context.py   def resolve_project_context(...)
    """
    try:
        from services.client_profile import load_client_profile
        if not project_name:
            from services.project_context import resolve_project_context
            ctx = resolve_project_context()
            project_name = getattr(ctx, "stacky_project_name", None) if ctx else None
        if not project_name:
            return None
        return load_client_profile(project_name)
    except Exception:
        return None


@bp.get("/status")
def incident_inbox_status():
    from services.incident_inbox import resolve_closed_states, resolve_incident_types

    project_name = (request.args.get("project") or "").strip() or None
    profile = _profile_for(project_name)
    types, types_source = resolve_incident_types(profile)
    closed, closed_source = resolve_closed_states(profile)
    return jsonify({
        "ok": True,
        "enabled": _enabled(),
        # Alias ADITIVO (no reemplaza a "enabled"): App.tsx gatea los tabs con
        # utils/flagHealth.probeFlagHealth, que SOLO entiende `flag_enabled` y
        # es sticky ante respuestas desconocidas. Sin esta key el tab quedaria
        # siempre oculto.
        "flag_enabled": _enabled(),
        "incident_types": list(types),
        "incident_types_source": types_source,
        "closed_states": list(closed),
        "closed_states_source": closed_source,
    })


@bp.get("/items")
def incident_inbox_items():
    if not _enabled():
        return _feature_disabled_response()

    from sqlalchemy import func, or_

    from db import session_scope
    from models import Ticket
    from services.incident_inbox import (
        MAX_ITEMS, build_counts, is_open_state, normalize, normalize_scope,
        resolve_closed_states, resolve_incident_types,
    )

    # SEAM DELIBERADO: se reusan los helpers privados de api/tickets.py para NO
    # duplicar la semantica multi-proyecto del filtro (que es sutil: compara
    # stacky_project_name y cae a project cuando el primero es NULL,
    # api/tickets.py:347-354). Import LAZY dentro de la vista: evita ciclos.
    try:
        from api.tickets import _request_project_name, _ticket_project_filter
    except ImportError:
        return jsonify({
            "ok": False,
            "error": "project_filter_seam_missing",
            "message": (
                "Los helpers _request_project_name/_ticket_project_filter de "
                "api/tickets.py cambiaron de nombre. Ver Plan 238 F2."
            ),
        }), 200

    scope = normalize_scope(request.args.get("scope"))
    project_name = _request_project_name()
    profile = _profile_for(project_name)
    types, _ = resolve_incident_types(profile)
    closed, _ = resolve_closed_states(profile)

    types_norm = [normalize(t) for t in types]
    closed_norm = [normalize(s) for s in closed]
    state_expr = func.lower(func.coalesce(Ticket.ado_state, ""))

    with session_scope() as session:
        project_filter = _ticket_project_filter(project_name)

        def _scoped(q):
            return q.filter(project_filter) if project_filter is not None else q

        # (1) COUNTS EXACTOS por agregacion: NO dependen del LIMIT (Plan 238 4.2).
        incident_q = _scoped(session.query(Ticket)).filter(
            func.lower(Ticket.work_item_type).in_(types_norm)
        )
        total = incident_q.count()
        closed_count = incident_q.filter(state_expr.in_(closed_norm)).count()
        counts = build_counts(total, closed_count)

        # (2) DEGRADACION POR PROVEEDOR (Plan 238 4.1.4): tickets del proyecto
        # SIN tipo sincronizado. En GitLab el tipo viaja como label, no como
        # columna, asi que work_item_type queda NULL y el filtro de (1) los
        # descarta en silencio. Contarlos es lo que evita la pantalla vacia
        # mentirosa.
        untyped_count = _scoped(session.query(Ticket)).filter(
            or_(Ticket.work_item_type.is_(None), func.trim(Ticket.work_item_type) == "")
        ).count()
        first_row = _scoped(session.query(Ticket)).first()
        provider = getattr(first_row, "tracker_type", None) if first_row else None

        # (3) FILAS. Sin N+1: NO se consulta AgentExecution ni pipeline_summary.
        rows_q = incident_q
        if scope == "open":
            rows_q = rows_q.filter(~state_expr.in_(closed_norm))
        rows = rows_q.order_by(
            Ticket.last_synced_at.desc().nulls_last(), Ticket.ado_id.desc()
        ).limit(MAX_ITEMS + 1).all()

        truncated = len(rows) > MAX_ITEMS
        rows = rows[:MAX_ITEMS]

        items = []
        for t in rows:
            payload = t.to_dict()  # 218 F5: canonico + alias legacy, nunca quita keys
            payload["is_open"] = is_open_state(t.ado_state, closed)
            items.append(payload)

    # Abiertas primero; dentro de cada grupo se conserva el orden de la query.
    items.sort(key=lambda i: 0 if i["is_open"] else 1)

    return jsonify({
        "ok": True,
        "scope": scope,
        "counts": counts,
        "truncated": truncated,
        "untyped_count": untyped_count,
        "provider": provider,
        "incident_types": list(types),
        "closed_states": list(closed),
        "items": items,
    })
