"""Plan 238 F2 -- Bandeja de incidencias abiertas (solo lectura).

Blueprint independiente: NO se toca backend/api/tickets.py (351 KB, disputado
por los planes 212/213 y por una sesion paralela viva).
"""
from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request

# Plan 269 F5 paso 1 — ESTE MODULO NO TENIA LOGGER (0 ocurrencias, ni importaba
# logging). Un `logger.debug(...)` dentro de un `except` sin esto lanza NameError
# DESDE el handler de excepcion y convierte una degradacion silenciosa en un 500
# en la bandeja: exactamente lo contrario de lo que se promete.
logger = logging.getLogger("stacky_agents.api.incident_inbox")

bp = Blueprint("incident_inbox", __name__, url_prefix="/incident-inbox")


def _enabled() -> bool:
    # GOTCHA REAL: `config` importado como MODULO devuelve el default y mata el
    # branch OFF. La instancia es `config.config`.
    from config import config as _cfg
    return bool(getattr(_cfg, "STACKY_INCIDENT_INBOX_ENABLED", True))


def _actions_enabled() -> bool:
    """Acciones de escritura desde la bandeja (cerrar / resolver+PR / lote).

    Depende de la flag padre: con la bandeja apagada no hay acciones posibles,
    asi que se devuelve False sin mirar la hija (misma semantica que `requires`).
    """
    if not _enabled():
        return False
    from config import config as _cfg
    return bool(getattr(_cfg, "STACKY_INCIDENT_INBOX_ACTIONS_ENABLED", True))


def _inbox_verdict_enabled() -> bool:
    """Plan 269 F5 — veredicto de la ultima corrida en la fila de la bandeja.

    Se usa EL PATRON QUE YA VIVE EN ESTE ARCHIVO (`from config import config as
    _cfg` + getattr), igual que _enabled() y _actions_enabled(). El comentario de
    :14-15 advierte de este gotcha exacto: mezclar dos patrones en el archivo que
    lo documenta es pedir el error. Un solo patron por archivo.
    """
    from config import config as _cfg  # noqa: PLC0415

    return (
        bool(getattr(_cfg, "STACKY_INCIDENT_INBOX_VERDICT_ENABLED", True))
        and bool(getattr(_cfg, "STACKY_RUN_VERDICT_ENABLED", True))
    )


def _last_execution_by_ticket(session, ticket_ids: list[int]) -> dict:
    """UNA query ACOTADA para todo el lote: como mucho 1 fila por ticket.

    Un `.filter(ticket_id.in_(ids)).all()` que se queda con la primera de cada
    ticket EN MEMORIA no es N+1, pero trae TODAS las ejecuciones historicas de
    todos los tickets del lote: un fetch sin cota que crece con la antiguedad del
    proyecto, no con el tamano de la pagina.

    La subconsulta `max(started_at) GROUP BY ticket_id` deja el trabajo en el
    motor y devuelve <= len(ticket_ids) filas. El indice ix_exec_ticket_started
    (models.py:278, sobre (ticket_id, started_at)) cubre exactamente este acceso.
    """
    if not ticket_ids:
        return {}
    from sqlalchemy import func  # noqa: PLC0415

    from models import AgentExecution  # noqa: PLC0415

    sub = (
        session.query(
            AgentExecution.ticket_id.label("tid"),
            func.max(AgentExecution.started_at).label("ult"),
        )
        .filter(AgentExecution.ticket_id.in_(ticket_ids))
        .group_by(AgentExecution.ticket_id)
        .subquery()
    )
    filas = (
        session.query(AgentExecution)
        .join(
            sub,
            (AgentExecution.ticket_id == sub.c.tid)
            & (AgentExecution.started_at == sub.c.ult),
        )
        .all()
    )
    out: dict = {}
    for ex in filas:
        # Empate exacto de started_at (posible en SQLite): gana el id mayor.
        prev = out.get(ex.ticket_id)
        if prev is None or ex.id > prev.id:
            out[ex.ticket_id] = ex
    return out


def _divergence_badge_enabled() -> bool:
    """Plan 270 F5 — marca "Sin sincronizar" en la bandeja (solo lectura).

    Depende de la flag padre igual que las acciones: con la bandeja apagada no
    hay nada que marcar.
    """
    if not _enabled():
        return False
    from config import config as _cfg
    return bool(getattr(_cfg, "STACKY_INCIDENT_DIVERGENCE_BADGE_ENABLED", True))


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
        # Gate de las acciones de escritura de la bandeja (cerrar / resolver+PR
        # / lote). ADITIVO: un frontend viejo que no lo lea sigue funcionando en
        # modo solo lectura. False si la bandeja entera esta apagada.
        "actions_enabled": _actions_enabled(),
        # Plan 270 F5 — gate del badge "Sin sincronizar". ADITIVO y estricto a
        # true del lado del frontend: un backend viejo que no lo manda deja el
        # badge oculto y la pagina sigue funcionando.
        "divergence_badge_enabled": _divergence_badge_enabled(),
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

        # Plan 270 F5 — divergencia EXACTA por agregación (no depende del LIMIT).
        # Misma regla de dos condiciones que isDiverged() en el .ts: Stacky la da
        # por cerrada pero el tablero la sigue pintando abierta.
        diverged_count = incident_q.filter(
            Ticket.stacky_status == "completed"
        ).filter(~state_expr.in_(closed_norm)).count()

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

        # Plan 269 F5 — veredicto de la ULTIMA ejecucion de cada incidencia.
        # La restriccion heredada del comentario de arriba ("Sin N+1") se
        # CONSERVA: se agrega UNA sola query acotada para todo el lote.
        verdicts: dict = {}
        if _inbox_verdict_enabled():
            try:
                ultimas = _last_execution_by_ticket(session, [t.id for t in rows])
                from services.run_evidence import collect_for_executions
                from services.run_verdict import evaluate_verdict
                señales = collect_for_executions(session, list(ultimas.values()))
                # Se usa `by_tid` armado desde `rows`, que YA estan en memoria, en
                # vez de getattr(ex, "ticket", None): esa relacion es lazy="select"
                # (models.py:275), asi que tocarla por fila seria un N+1 encubierto
                # — exactamente lo que el comentario del endpoint prohibe.
                by_tid = {t.id: t for t in rows}
                for tid, ex in ultimas.items():
                    meta = ex.metadata_dict if isinstance(ex.metadata_dict, dict) else {}
                    # El run manda, el ticket solo EMPEORA (ver F2).
                    v = evaluate_verdict(
                        run_status=(ex.status or ""),
                        ticket_status=getattr(by_tid.get(tid), "stacky_status", None),
                        outcome_reason=meta.get("outcome_reason"),
                        signals=señales.get(ex.id),
                    )
                    if v is not None:      # un run no terminado NO tiene veredicto
                        verdicts[tid] = v.to_dict()
            except Exception:  # noqa: BLE001 — la bandeja JAMAS se rompe por esto
                logger.debug("run_verdict 269 en la bandeja fallo", exc_info=True)
                verdicts = {}

        items = []
        for t in rows:
            payload = t.to_dict()  # 218 F5: canonico + alias legacy, nunca quita keys
            payload["is_open"] = is_open_state(t.ado_state, closed)
            if t.id in verdicts:
                payload["run_verdict"] = verdicts[t.id]  # OPCIONAL: nunca vacia
            items.append(payload)

    # Abiertas primero; dentro de cada grupo se conserva el orden de la query.
    items.sort(key=lambda i: 0 if i["is_open"] else 1)

    return jsonify({
        "ok": True,
        "scope": scope,
        "counts": counts,
        "truncated": truncated,
        "untyped_count": untyped_count,
        # Plan 270 F5 — incidencias completed en Stacky pero abiertas en el
        # tracker. ADITIVA: un frontend viejo que no la lea sigue funcionando.
        "diverged_count": diverged_count,
        "provider": provider,
        "incident_types": list(types),
        "closed_states": list(closed),
        "items": items,
    })
