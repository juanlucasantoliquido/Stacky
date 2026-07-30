import json
import logging
from datetime import datetime
from datetime import timedelta
from pathlib import Path

from flask import Blueprint, Response, abort, jsonify, request
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import joinedload

import log_streamer
from db import session_scope
from models import AgentExecution, Ticket
from ._helpers import current_user
from services import console_audit
from services import human_review as human_review_svc
from services.project_context import resolve_project_context
from project_manager import (
    PROJECTS_DIR,
    get_project_config,
    get_active_project,
    find_project_for_tracker,
)

bp = Blueprint("executions", __name__, url_prefix="/executions")
logger = logging.getLogger("stacky_agents.api.executions")


def _outcome_badge_enabled() -> bool:
    """Plan 254 F4 — kill-switch del badge de causa. Se lee la INSTANCIA."""
    import config as _config  # noqa: PLC0415

    return bool(getattr(_config.config, "STACKY_UI_OUTCOME_REASON_BADGE_ENABLED", True))


def _reason_visible_enabled() -> bool:
    """Plan 271 F5 — kill-switch de la razón del cambio de estado. INDEPENDIENTE
    de `_outcome_badge_enabled` (plan 254): C14, no puede quedar gateada por una
    flag que este plan no controla."""
    import config as _config  # noqa: PLC0415

    return bool(getattr(_config.config, "STACKY_FINAL_STATE_REASON_VISIBLE_ENABLED", True))


def _verdict_badge_enabled() -> bool:
    """Plan 269 F2 — kill-switch del veredicto en el payload. Se lee la INSTANCIA.

    Dependencia resuelta EN CÓDIGO, no con `requires=` en la FlagSpec: el
    veredicto solo se sirve si están ON la flag de UI Y la del núcleo.
    """
    import config as _config  # noqa: PLC0415

    return (
        bool(getattr(_config.config, "STACKY_UI_RUN_VERDICT_BADGE_ENABLED", True))
        and bool(getattr(_config.config, "STACKY_RUN_VERDICT_ENABLED", True))
    )


def _verdicts_for_batch(session, executions: list) -> dict[int, dict]:
    """Plan 269 F2 — veredicto de TODO el lote. Read-only, sin N+1.

    Nunca lanza: cualquier fallo devuelve {} y el listado sale como antes.
    """
    if not _verdict_badge_enabled():
        return {}
    try:
        from services.run_evidence import collect_for_executions  # noqa: PLC0415
        from services.run_verdict import evaluate_verdict  # noqa: PLC0415

        signals_by_id = collect_for_executions(session, executions)
        out: dict[int, dict] = {}
        for ex in executions:
            ticket = getattr(ex, "ticket", None)
            # DOS argumentos, NO uno colapsado. Está PROHIBIDO el patrón que
            # toma el estado del ticket con el del run como respaldo: dejaba que
            # un ticket `completed` blanqueara un run `error`, y el historial
            # pintaba "Terminó bien" al lado del chip "Error" en TODAS las
            # corridas fallidas de un ticket ya cerrado.
            # El run manda; el ticket solo puede EMPEORAR (nunca mejorar).
            meta = ex.metadata_dict if isinstance(ex.metadata_dict, dict) else {}
            v = evaluate_verdict(
                run_status=(ex.status or ""),
                ticket_status=getattr(ticket, "stacky_status", None),
                outcome_reason=meta.get("outcome_reason"),
                signals=signals_by_id.get(ex.id),
            )
            if v is None:          # run no terminado: NO tiene veredicto
                continue
            out[ex.id] = v.to_dict()
        return out
    except Exception:  # noqa: BLE001 — enriquecer JAMÁS rompe el listado
        logger.debug("run_verdict 269 falló", exc_info=True)
        return {}


def _with_verdict(d: dict, verdicts: dict[int, dict]) -> dict:
    """Agrega `run_verdict` si hay uno. Con la flag OFF no agrega NINGUNA clave:
    la UI simplemente no dibuja el chip (sin hueco ni error).

    La clave es `run_verdict`, NO `verdict`: `verdict` ya lo emite
    AgentExecution.to_dict() (models.py:327) con la revisión humana.
    """
    v = verdicts.get(d.get("id"))
    if v:
        d["run_verdict"] = v
    return d


def _dirty_close_execution_ids(session, execution_ids: list[int]) -> set[int]:
    """Plan 254 F1-bis — ejecuciones cuyo cierre preservó un terminal de éxito.

    La marca `blocked_downgrade.pending_review` la escribe el guard de F1 en el
    `TicketStatusEvent` (services/ticket_status.py), NO en el metadata de la
    ejecución: hay que leerla de ahí o el aviso nunca se vería.

    UNA sola query para todo el lote (nada de N+1). Read-only.
    """
    if not execution_ids:
        return set()
    from services.ticket_status import TicketStatusEvent  # noqa: PLC0415

    rows = (
        session.query(TicketStatusEvent.execution_id, TicketStatusEvent.metadata_json)
        .filter(TicketStatusEvent.execution_id.in_(execution_ids))
        .filter(TicketStatusEvent.metadata_json.like("%blocked_downgrade%"))
        .all()
    )
    dirty: set[int] = set()
    for exec_id, raw in rows:
        try:
            blocked = (json.loads(raw or "{}") or {}).get("blocked_downgrade")
        except (ValueError, TypeError):
            continue
        if isinstance(blocked, dict) and blocked.get("pending_review"):
            dirty.add(exec_id)
    return dirty


def _with_outcome(d: dict, dirty_ids: set[int] | None = None) -> dict:
    """Plan 254 F4 — expone la causa del desenlace donde el operador ya mira.

    `outcome_reason` lo dejó F2 en el `metadata_json` de la ejecución (no hace
    falta columna nueva); acá solo se promueve al nivel superior del payload para
    que la UI no tenga que conocer la forma del metadata.

    Con `STACKY_UI_OUTCOME_REASON_BADGE_ENABLED` apagada NO se agrega ninguna
    clave: la UI simplemente no dibuja el badge (sin hueco ni error).
    """
    # Plan 271 F5 (C14) — la razón del cambio de estado NO depende de la flag
    # del 254: se promueve ANTES del corte de `_outcome_badge_enabled`.
    meta_271 = d.get("metadata") or {}
    if _reason_visible_enabled() and isinstance(meta_271, dict):
        fso = meta_271.get("final_state_outcome")
        if isinstance(fso, dict):
            d["final_state_outcome"] = fso
    if not _outcome_badge_enabled():
        return d
    meta = d.get("metadata") or {}
    if isinstance(meta, dict):
        reason = meta.get("outcome_reason")
        if reason:
            d["outcome_reason"] = reason
            try:
                from services.run_outcome import is_operator_actionable  # noqa: PLC0415

                d["outcome_actionable"] = is_operator_actionable(str(reason))
            except Exception:  # noqa: BLE001 — enriquecer jamás rompe el listado
                logger.debug("outcome_actionable 254 falló", exc_info=True)
    if dirty_ids and d.get("id") in dirty_ids:
        # F1-bis — un `completed` preservado sobre un cierre sucio NO puede
        # presentarse como un éxito limpio.
        d["dirty_close_pending_review"] = True
    return d


@bp.get("")
def list_executions():
    ticket_id = request.args.get("ticket_id", type=int)
    agent_type = request.args.get("agent_type")
    status = request.args.get("status")
    status_values: list[str] = []
    # Soporta:
    # - ?status=running
    # - ?status=needs_review,error
    # - ?status=needs_review&status=error
    for raw in request.args.getlist("status"):
        for token in str(raw).split(","):
            val = token.strip()
            if val:
                status_values.append(val)
    if not status_values and status:
        status_values = [status.strip()]

    days = request.args.get("days", type=int)
    project_name = (request.args.get("project") or "").strip() or None
    all_projects = (request.args.get("all_projects") or "").strip().lower() in ("1", "true", "yes")
    limit = request.args.get("limit", default=50, type=int)

    # all_projects=true → NO filtrar por proyecto. Para vistas globales (p.ej. el
    # panel de runs activos) que deben poder ver/cancelar ejecuciones de cualquier
    # proyecto, incluidos runs huérfanos cuyo ticket quedó sin stacky_project_name.
    if all_projects:
        project_ctx = None
    else:
        project_ctx = resolve_project_context(project_name=project_name) if project_name else resolve_project_context()

    with session_scope() as session:
        q = session.query(AgentExecution)
        # Plan 134 F1: eager-load del ticket para servir project/ticket_title sin
        # N+1 (la relación es lazy="select" por default — models.py:234).
        q = q.options(joinedload(AgentExecution.ticket))
        if project_ctx is not None:
            q = q.join(Ticket, Ticket.id == AgentExecution.ticket_id).filter(
                or_(
                    Ticket.stacky_project_name == project_ctx.stacky_project_name,
                    and_(
                        Ticket.stacky_project_name.is_(None),
                        Ticket.project == project_ctx.tracker_project,
                    ),
                )
            )
        if ticket_id:
            q = q.filter(AgentExecution.ticket_id == ticket_id)
        if agent_type:
            q = q.filter(AgentExecution.agent_type == agent_type)
        if status_values:
            if len(status_values) == 1:
                q = q.filter(AgentExecution.status == status_values[0])
            else:
                q = q.filter(AgentExecution.status.in_(status_values))
        if days and days > 0:
            q = q.filter(AgentExecution.started_at >= (datetime.utcnow() - timedelta(days=days)))
        rows = q.order_by(AgentExecution.started_at.desc()).limit(limit).all()
        # Plan 254 F4 — causa del desenlace + aviso de cierre sucio.
        payload = [r.to_dict(include_output=False, include_ticket_context=True) for r in rows]
        dirty = (
            _dirty_close_execution_ids(session, [r.id for r in rows])
            if _outcome_badge_enabled() else set()
        )
        # Plan 269 F2 — `rows` ya viene con joinedload(AgentExecution.ticket),
        # así que getattr(ex, "ticket", None) NO dispara N+1 acá.
        verdicts = _verdicts_for_batch(session, rows)
        return jsonify([_with_verdict(_with_outcome(d, dirty), verdicts) for d in payload])


def _query_active_executions(session, *, project_ctx, status_values, limit):
    """Plan 156 F1 — misma logica de filtro/orden que list_executions, aislada
    para que /api/executions y /api/executions/summary NUNCA diverjan.

    Helper NUEVO consumido UNICAMENTE por executions_summary (blast-radius
    minimo, C1 v2): list_executions queda byte-identico. La garantia de que el
    summary y /api/executions nunca divergen la sostiene el TEST de paridad
    (test_summary_paridad_de_campos_running), no compartir codigo.
    """
    q = session.query(AgentExecution).options(joinedload(AgentExecution.ticket))
    if project_ctx is not None:
        q = q.join(Ticket, Ticket.id == AgentExecution.ticket_id).filter(
            or_(
                Ticket.stacky_project_name == project_ctx.stacky_project_name,
                and_(
                    Ticket.stacky_project_name.is_(None),
                    Ticket.project == project_ctx.tracker_project,
                ),
            )
        )
    if status_values:
        if len(status_values) == 1:
            q = q.filter(AgentExecution.status == status_values[0])
        else:
            q = q.filter(AgentExecution.status.in_(status_values))
    return q.order_by(AgentExecution.started_at.desc()).limit(limit).all()


@bp.get("/summary")
def executions_summary():
    """Plan 156 F1 — latido unico: running/preparing/queued en UNA respuesta.

    Shape: {"scope": "project"|"all_projects",
            "running":[...], "preparing":[...], "queued":[...]}

    Cada objeto es identico a /api/executions (to_dict include_output=False,
    include_ticket_context=True). scope=all_projects => sin filtro de proyecto.

    Campos que los callers consumen HOY (F0, verificado con grep del arbol):
      - activeRuns.ts/mergeActiveRuns: id
      - useRunningStatus.ts: ticket_id, y el objeto completo en runningByTicket
      - ActiveRunsPanel.tsx: id, project, ticket_id, ticket_title, agent_type, status
    Todos provienen de to_dict(include_ticket_context=True); la cobertura es
    total y el test de paridad de F1 la garantiza.
    """
    scope = (request.args.get("scope") or "project").strip().lower()
    all_projects = scope in ("all", "all_projects", "global")
    project_name = (request.args.get("project") or "").strip() or None
    limit = request.args.get("limit", default=50, type=int)

    if all_projects:
        project_ctx = None
    else:
        project_ctx = (
            resolve_project_context(project_name=project_name)
            if project_name else resolve_project_context()
        )

    out = {"scope": "all_projects" if all_projects else "project"}
    with session_scope() as session:
        for status in ("running", "preparing", "queued"):
            rows = _query_active_executions(
                session, project_ctx=project_ctx, status_values=[status], limit=limit,
            )
            out[status] = [
                r.to_dict(include_output=False, include_ticket_context=True) for r in rows
            ]
    return jsonify(out)


@bp.get("/<int:execution_id>")
def get_execution(execution_id: int):
    with session_scope() as session:
        row = session.get(AgentExecution, execution_id)
        if row is None:
            abort(404)
        # Plan 254 F4 — causa del desenlace + aviso de cierre sucio.
        dirty = (
            _dirty_close_execution_ids(session, [row.id])
            if _outcome_badge_enabled() else set()
        )
        return jsonify(_with_outcome(row.to_dict(include_ticket_context=True), dirty))


@bp.get("/<int:execution_id>/logs")
def get_logs(execution_id: int):
    return jsonify(log_streamer.snapshot(execution_id))


@bp.post("/<int:execution_id>/input")
def send_execution_input(execution_id: int):
    payload = request.get_json(silent=True) or {}
    text = str(payload.get("text") or "").strip()
    if not text:
        abort(400, "text is required")

    # Enrutar al runner correcto según el runtime de la ejecución.
    with session_scope() as session:
        row = session.get(AgentExecution, execution_id)
        if row is None:
            abort(404, "execution not found")
        runtime = (row.metadata_dict or {}).get("runtime")

    if runtime == "claude_code_cli":
        from services.claude_code_cli_runner import send_input
    else:
        from services.codex_cli_runner import send_input

    try:
        result = send_input(execution_id, text, user=current_user())
    except ValueError as exc:
        abort(400, str(exc))
    except RuntimeError as exc:
        abort(409, str(exc))

    return jsonify(result)


@bp.get("/<int:execution_id>/logs/stream")
def stream_logs(execution_id: int):
    def generator():
        for event in log_streamer.stream(execution_id):
            event_type = event.get("type") or "log"
            data = json.dumps(event, ensure_ascii=False)
            yield f"event: {event_type}\ndata: {data}\n\n"

    return Response(
        generator(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@bp.post("/<int:execution_id>/approve")
def approve(execution_id: int):
    return _set_verdict(execution_id, verdict="approved")


@bp.post("/<int:execution_id>/discard")
def discard(execution_id: int):
    return _set_verdict(execution_id, verdict="discarded")


def _set_verdict(execution_id: int, verdict: str):
    with session_scope() as session:
        row = session.get(AgentExecution, execution_id)
        if row is None:
            abort(404)
        if row.status != "completed":
            abort(409, "execution not in completed state")
        row.verdict = verdict
        result = row.to_dict(include_output=False)

    if verdict == "approved":
        try:
            from services import post_run_memory

            memory_id = post_run_memory.capture_on_approval(execution_id)
            if memory_id:
                result["stacky_memory_id"] = memory_id
        except Exception:  # noqa: BLE001
            logger.warning("post_run_memory approval hook falló exec=%s", execution_id, exc_info=True)
    return jsonify(result)


# ── Plan 47 — Veredicto humano de runs (anotación, no transición de estado) ───

# Estados sobre los que el operador PUEDE emitir veredicto humano: completed
# (legacy) + needs_review (gap del Plan 46). NO incluye running/error/failed.
_HUMAN_REVIEWABLE_STATUSES = ("completed", "needs_review")


@bp.post("/<int:execution_id>/human-review")
def human_review_route(execution_id: int):
    """Plan 47 F1 — Persiste el veredicto humano + nota en metadata_json.

    Anotación, NO transición: una run en needs_review con veredicto "rejected"
    SIGUE en needs_review (el status no cambia). Funciona sobre completed y
    needs_review. La promoción a memoria (F2) es opt-in vía flag y best-effort.
    """
    payload = request.get_json(force=True, silent=True) or {}
    try:
        block = human_review_svc.build_human_review(
            verdict=payload.get("verdict"),
            note=payload.get("note"),
            reviewed_by=current_user(),
        )
    except ValueError as exc:
        abort(400, str(exc))

    # Datos para captura de goldens (Plan 56 F2): extraídos dentro del scope.
    _review_snapshot: dict = {}

    with session_scope() as session:
        row = session.get(AgentExecution, execution_id)
        if row is None:
            abort(404)
        if row.status not in _HUMAN_REVIEWABLE_STATUSES:
            abort(409, f"execution not reviewable in status '{row.status}'")
        meta = row.metadata_dict
        meta[human_review_svc.METADATA_KEY] = block
        row.metadata_dict = meta  # setter → reserializa metadata_json
        # Reflejar en la columna verdict existente (sin romper legacy).
        row.verdict = (
            "approved" if block["verdict"] in ("approved", "approved_with_notes") else "rejected"
        )
        result = row.to_dict(include_output=False)
        # Snapshot para golden capture (fuera del scope no hay acceso lazy)
        _review_snapshot = {
            "id": row.id,
            "agent_type": row.agent_type,
            "output": row.output,
            "metadata_dict": dict(row.metadata_dict),
            "project": (row.ticket.stacky_project_name if row.ticket else None),
            "work_item_type": (row.ticket.work_item_type if row.ticket else "Epic"),
        }

    # C3 — persistencia del veredicto vs captura opt-in a memoria, separadas.
    result["human_review_persisted"] = True
    result["operator_note_captured"] = False

    # F2 — promoción opt-in a memoria (flag OFF por default). Best-effort.
    try:
        from services import post_run_memory
        memory_id = post_run_memory.capture_operator_note(execution_id)
        if memory_id:
            result["stacky_memory_id"] = memory_id
            result["operator_note_captured"] = True
    except Exception:  # noqa: BLE001 — el veredicto ya se persistió; nunca romper el request
        logger.warning("capture_operator_note falló exec=%s", execution_id, exc_info=True)

    # Plan 56 F2 — captura de golden positivo/negativo. Best-effort, siempre activo.
    try:
        from services.regression_capture import save_goldens_from_review

        class _ExecSnapshot:
            """Duck-type compatible con AgentExecution para regression_capture."""
            def __init__(self, snap: dict):
                self.id = snap["id"]
                self.agent_type = snap["agent_type"]
                self.output = snap["output"]
                self._metadata_dict = snap["metadata_dict"]

                class _T:
                    pass
                t = _T()
                t.stacky_project_name = snap["project"]
                t.work_item_type = snap["work_item_type"]
                self.ticket = t

            @property
            def metadata_dict(self):
                return self._metadata_dict

        save_goldens_from_review(
            execution=_ExecSnapshot(_review_snapshot),
            verdict=block["verdict"],
            note=payload.get("note") or "",
        )
    except Exception:  # noqa: BLE001
        logger.warning("save_goldens_from_review falló exec=%s", execution_id, exc_info=True)

    return jsonify(result)


# Plan 173 F5 — SOLO columnas reales de agent_executions. `duration_ms` se
# calcula por fila y `cost_usd`/`runtime` viven en metadata_json: ordenar por
# ellas en SQL es imposible, y ofrecerlo sería prometer un orden que no llega.
_HISTORY_SORT_COLUMNS = {
    "started_at": AgentExecution.started_at,
    "id": AgentExecution.id,
    "status": AgentExecution.status,
    "agent_type": AgentExecution.agent_type,
}


@bp.get("/history")
def executions_history():
    """Plan 39 A1 — Historial completo de ejecuciones con métricas del arnés.

    Gated por STACKY_EXECUTION_HISTORY_ENABLED. Si OFF → 404 feature_disabled.
    Soporta filtros: project, agent_type, runtime, status (csv), days, limit (max 500), offset.

    Plan 173 F5 — ADITIVO: `sort`/`dir` (allowlist de columnas REALES) e
    `include_total=1`, que envuelve la respuesta en {items, total}. Sin
    `include_total` devuelve la lista pelada de siempre.

    LIMITACIÓN del total: el filtro `runtime` NO vive en una columna sino en
    metadata_json, así que se aplica en Python DESPUÉS de paginar. El `total` es
    el COUNT SQL previo y NO lo descuenta: con filtro de runtime activo, la UI
    debe ignorarlo (ver `historyPaginationView` en el frontend).
    """
    from config import config as _cfg
    if not getattr(_cfg, "STACKY_EXECUTION_HISTORY_ENABLED", True):
        return jsonify({"error": "feature_disabled", "feature": "STACKY_EXECUTION_HISTORY_ENABLED"}), 404

    agent_type = request.args.get("agent_type")
    runtime_filter = request.args.get("runtime")
    project_name = (request.args.get("project") or "").strip() or None
    days = request.args.get("days", type=int)
    limit = min(request.args.get("limit", default=100, type=int), 500)
    offset = request.args.get("offset", default=0, type=int)
    # Plan 173 F5 — orden y total, los dos opt-in y aditivos.
    sort_key = request.args.get("sort", default="started_at")
    sort_dir = request.args.get("dir", default="desc")
    include_total = (request.args.get("include_total") or "").strip().lower() in ("1", "true", "yes")

    # status puede ser CSV o múltiples ?status=
    status_values: list[str] = []
    for raw in request.args.getlist("status"):
        for token in str(raw).split(","):
            val = token.strip()
            if val:
                status_values.append(val)

    with session_scope() as session:
        q = session.query(AgentExecution).join(Ticket, Ticket.id == AgentExecution.ticket_id)

        if project_name:
            q = q.filter(
                or_(
                    Ticket.stacky_project_name == project_name,
                    and_(
                        Ticket.stacky_project_name.is_(None),
                        Ticket.project == project_name,
                    ),
                )
            )

        if agent_type:
            q = q.filter(AgentExecution.agent_type == agent_type)

        if status_values:
            if len(status_values) == 1:
                q = q.filter(AgentExecution.status == status_values[0])
            else:
                q = q.filter(AgentExecution.status.in_(status_values))

        if days and days > 0:
            q = q.filter(
                AgentExecution.started_at >= (datetime.utcnow() - timedelta(days=days))
            )

        # El total se cuenta DESPUÉS de los filtros SQL y ANTES de paginar.
        total = q.count() if include_total else None

        # Allowlist: una columna fuera de la lista cae al orden de siempre en vez
        # de reventar. Un `sort` desconocido es un cliente viejo o un typo, no
        # motivo para devolverle un 400 al operador.
        columna = _HISTORY_SORT_COLUMNS.get(sort_key, AgentExecution.started_at)
        orden = columna.asc() if str(sort_dir).lower() == "asc" else columna.desc()

        rows = (
            q.order_by(orden)
            .offset(offset)
            .limit(limit)
            .all()
        )

        # Para cada ejecución construimos el item del contrato.
        items = []
        rows_servidas = []            # solo las que sobrevivieron el filtro de runtime
        for row in rows:
            meta = row.metadata_dict or {}
            row_runtime = meta.get("runtime") or ""

            # Filtro por runtime (runtime viene de metadata, no de columna)
            if runtime_filter and row_runtime != runtime_filter:
                continue

            ticket = row.ticket  # relación cargada por join
            ticket_title = ticket.title if ticket else None

            items.append({
                "id": row.id,
                "ticket_id": row.ticket_id,
                "ticket_title": ticket_title,
                "agent_type": row.agent_type,
                "agent_name": meta.get("agent_name") or None,
                "runtime": row_runtime or None,
                "model": meta.get("model") or None,
                "status": row.status,
                "started_at": row.started_at.isoformat() if row.started_at else None,
                "finished_at": row.completed_at.isoformat() if row.completed_at else None,
                "duration_ms": row.duration_ms(),
                "cost_usd": meta.get("cost_usd") or None,
                "tokens_in": meta.get("tokens_in") or None,
                "tokens_out": meta.get("tokens_out") or None,
                "prompt_sha": meta.get("prompt_sha") or None,
                "prompt_len": meta.get("prompt_len") or None,
                "has_prompt_text": bool(meta.get("prompt_text")),
                "produced_files_count": len(meta.get("produced_files") or []),
                "error_message": row.error_message or None,
                "local_insight": meta.get("local_insight") or None,  # Plan 117 (aditivo)
            })
            rows_servidas.append(row)

        # Plan 269 F2 — el historial es la superficie de F4, y este handler arma
        # los items A MANO (no pasa por _with_outcome): cablear solo el otro
        # endpoint dejaba toda F4 inerte. Misma función de lote, mismo
        # try/except: si falla, `items` sale exactamente como hoy. Se inyecta
        # ANTES del `if include_total` para que las DOS formas de respuesta lo
        # lleven.
        verdicts = _verdicts_for_batch(session, rows_servidas)
        for d in items:
            _with_verdict(d, verdicts)

    if include_total:
        return jsonify({"items": items, "total": total})
    # Contrato legacy INTACTO: sin include_total sigue siendo una lista pelada.
    return jsonify(items)


@bp.post("/<int:execution_id>/publish-to-ado")
def publish_to_ado(execution_id: int):
    """U2.2 — Publicación real en modo review-before-publish.

    Sólo opera cuando la ejecución quedó en hold por publish_mode=review.
    """
    with session_scope() as session:
        row = session.get(AgentExecution, execution_id)
        if row is None:
            abort(404)

    from services.agent_completion_internal import publish_execution_from_review

    result = publish_execution_from_review(
        execution_id=execution_id,
        triggered_by=current_user() or "operator_review",
    )
    status = int(result.pop("status", 200))
    return jsonify(result), status


@bp.get("/<int:execution_id>/diff/<int:other_id>")
def diff(execution_id: int, other_id: int):
    with session_scope() as session:
        a = session.get(AgentExecution, execution_id)
        b = session.get(AgentExecution, other_id)
        if a is None or b is None:
            abort(404)
        if a.ticket_id != b.ticket_id or a.agent_type != b.agent_type:
            abort(400, "executions must share ticket_id and agent_type")
        return jsonify({"left": a.to_dict(), "right": b.to_dict()})


# ── Endpoints portados desde WS2 (2026-05-23) ────────────────────────────────


@bp.post("/<int:execution_id>/cancel")
def cancel_execution(execution_id: int):
    """Cancela una ejecucion en curso (vscode_chat o running).

    Marca el status como 'cancelled' y registra la fecha de finalizacion.
    No publica nada al tracker.

    Portado desde WS2 (2026-05-23) — P1.3 item (1).
    """
    with session_scope() as session:
        row = session.get(AgentExecution, execution_id)
        if row is None:
            abort(404, "execution not found")
        if row.status not in ("vscode_chat", "preparing", "queued", "running"):
            abort(409, f"Cannot cancel execution in status '{row.status}'")
        row.status = "cancelled"
        row.completed_at = datetime.utcnow()
        meta = row.metadata_dict or {}
        runtime = meta.get("runtime")
        # B6: capturar ticket_id/agent_type dentro del session_scope para
        # sincronizar luego el stacky_status del ticket (hoy el endpoint lo omitía
        # y el ticket quedaba "running" hasta el próximo reconcile).
        ticket_id = row.ticket_id
        agent_type = row.agent_type

    if runtime == "codex_cli":
        from services import codex_cli_runner
        codex_cli_runner.cancel(execution_id)
    elif runtime == "claude_code_cli":
        from services import claude_code_cli_runner
        claude_code_cli_runner.cancel(execution_id)
    else:
        # B6: github_copilot (y cualquier runtime sin subproceso propio) no tiene
        # un proceso CLI que matar; la cancelación es cooperativa vía el flag
        # in-memory de copilot_bridge, expuesto por agent_runner.cancel().
        try:
            import agent_runner
            agent_runner.cancel(execution_id)
        except Exception:  # noqa: BLE001 — best-effort, no romper el cancel
            logger.warning("cancel cooperativo (agent_runner) falló exec=%s", execution_id, exc_info=True)

    # B6: sacar el ticket de "running" de inmediato (sin esperar al reaper). El
    # status ya quedó terminal en la execution row; reflejamos cancelled en el
    # ticket vía el hook de ciclo de vida (también dispara post-hooks coherentes).
    if ticket_id is not None:
        try:
            from services import ticket_status
            ticket_status.on_execution_end(
                ticket_id=ticket_id,
                execution_id=execution_id,
                final_status="cancelled",
                agent_type=agent_type,
                reason_override="cancelado manualmente desde el board",
            )
        except Exception:  # noqa: BLE001
            logger.warning("on_execution_end (cancel) falló exec=%s", execution_id, exc_info=True)

    logger.info("execution cancelled manually exec=%s", execution_id)
    # Plan 265 F7 — bitácora de acciones de consola: registro, nunca gate.
    # record_console_action nunca lanza; no puede tumbar un cancel exitoso.
    console_audit.record_console_action(execution_id=execution_id, action="cancel")
    return jsonify({"ok": True, "execution_id": execution_id})


@bp.delete("/<int:execution_id>")
def delete_execution(execution_id: int):
    """Elimina una ejecucion del historial.

    Solo se permite borrar ejecuciones terminadas (completed, error, cancelled,
    published, discarded). Las ejecuciones en curso se rechazan con 409.

    Portado desde WS2 (2026-05-23) — P1.3 item (2).
    """
    _TERMINAL_STATUSES = {"completed", "error", "cancelled", "published", "discarded", "failed"}
    with session_scope() as session:
        row = session.get(AgentExecution, execution_id)
        if row is None:
            abort(404, "execution not found")
        if row.status not in _TERMINAL_STATUSES:
            abort(409, f"cannot delete execution in status '{row.status}'")
        session.delete(row)
    return jsonify({"ok": True, "deleted_id": execution_id})


@bp.delete("/bulk-by-ticket")
def delete_executions_by_ticket():
    """Elimina todas las ejecuciones terminadas de un agente para un ticket dado.

    Query params:
      - ticket_id (int, required)
      - agent_filename (str, required)

    Las ejecuciones en curso se omiten (no se borran).

    Portado desde WS2 (2026-05-23) — P1.3 item (2).
    """
    ticket_id_raw = request.args.get("ticket_id")
    agent_filename = request.args.get("agent_filename", "").strip()
    if not ticket_id_raw or not agent_filename:
        abort(400, "ticket_id and agent_filename are required")
    try:
        ticket_id = int(ticket_id_raw)
    except ValueError:
        abort(400, "ticket_id must be an integer")

    _TERMINAL_STATUSES = {"completed", "error", "cancelled", "published", "discarded", "failed"}

    deleted_ids: list[int] = []
    skipped_ids: list[int] = []
    with session_scope() as session:
        rows = session.execute(
            select(AgentExecution).where(
                AgentExecution.ticket_id == ticket_id,
                AgentExecution.agent_filename == agent_filename,
            )
        ).scalars().all()
        for row in rows:
            if row.status not in _TERMINAL_STATUSES:
                skipped_ids.append(row.id)
                continue
            session.delete(row)
            deleted_ids.append(row.id)

    return jsonify({"ok": True, "deleted": deleted_ids, "skipped": skipped_ids})


@bp.post("/<int:execution_id>/answer")
def answer_question(execution_id: int):
    """Envia la respuesta del usuario a un agente en estado 'waiting_for_question'.

    Body: { "answer": "..." }
    Desbloquea el thread del agente para que continue la ejecucion.

    Portado desde WS2 (2026-05-23) — P1.3 item (3).
    """
    payload = request.get_json(force=True, silent=True) or {}
    answer = (payload.get("answer") or "").strip()

    with session_scope() as session:
        row = session.get(AgentExecution, execution_id)
        if row is None:
            abort(404, "execution not found")
        if row.status != "waiting_for_question":
            abort(409, f"execution no esta esperando respuesta (status='{row.status}')")

    import agent_runner as _runner
    if not hasattr(_runner, "answer_question"):
        # WS1 agent_runner no implementa answer_question todavia
        abort(501, "answer_question not implemented in this runtime")

    ok = _runner.answer_question(execution_id, answer)
    if not ok:
        abort(409, "no hay pregunta pendiente para esta ejecucion")

    return jsonify({"ok": True, "execution_id": execution_id})


def _resolve_ticket_output_dir_ws1(
    row: AgentExecution,
    ticket: Ticket,
) -> "Path | None":
    """Resuelve la carpeta donde el agente deposito sus ficheros generados.

    Adaptado para WS1: usa project_manager en vez de find_project_for_tracker de WS2.
    Prueba: metadata.ticket_output_dir -> Output/tickets/{ado_id}/.
    """
    meta = row.metadata_dict or {}
    output_dir_override = meta.get("ticket_output_dir")
    if output_dir_override:
        p = Path(output_dir_override)
        if p.is_dir():
            return p

    # Resolver workspace_root desde config del proyecto
    project_name = ticket.project or ""
    cfg = get_project_config(project_name) or {}
    workspace_root = (cfg.get("workspace_root") or "").strip()

    if not workspace_root:
        from project_manager import PROJECTS_DIR
        instance_file = PROJECTS_DIR / project_name / "vscode_instance.json"
        if instance_file.exists():
            try:
                inst = json.loads(instance_file.read_text(encoding="utf-8"))
                workspace_root = (inst.get("workspace_root") or "").strip()
            except Exception:
                pass

    if not workspace_root:
        return None

    ado_id = ticket.ado_id or 0
    output_base = Path(workspace_root) / "Output" / "tickets"

    # Convención primaria: {ado_id}
    candidate = output_base / str(ado_id)
    if candidate.is_dir():
        return candidate

    # Convención legada: azure_devops-{ado_id}
    candidate2 = output_base / f"azure_devops-{ado_id}"
    if candidate2.is_dir():
        return candidate2

    return None


@bp.get("/<int:execution_id>/output-files")
def list_output_files(execution_id: int):
    """Lista los ficheros generados por el agente en Output/tickets/{ado_id}/.

    Portado desde WS2 (2026-05-23) — P1.3 item (4).
    """
    with session_scope() as session:
        row = session.get(AgentExecution, execution_id)
        if row is None:
            abort(404, "execution not found")
        ticket = session.get(Ticket, row.ticket_id) if row.ticket_id else None
        if ticket is None:
            abort(404, "ticket not found for execution")
        ticket_dir = _resolve_ticket_output_dir_ws1(row, ticket)

    if ticket_dir is None:
        return jsonify({"files": [], "dir": None})

    files = []
    for f in sorted(ticket_dir.rglob("*")):
        if not f.is_file():
            continue
        stat = f.stat()
        files.append({
            "name": f.name,
            "rel_path": str(f.relative_to(ticket_dir)).replace("\\", "/"),
            "size": stat.st_size,
            "modified": int(stat.st_mtime * 1000),
        })

    return jsonify({"files": files, "dir": str(ticket_dir)})


@bp.delete("/<int:execution_id>/output-files")
def delete_output_files(execution_id: int):
    """Borra los ficheros seleccionados del directorio de salida del agente.

    Body: { "files": ["rel_path/to/file1.md", "file2.diff"] }
    Path traversal es rechazado explicitamente.

    Portado desde WS2 (2026-05-23) — P1.3 item (4).
    """
    payload = request.get_json(force=True, silent=True) or {}
    rel_paths: list[str] = payload.get("files") or []
    if not isinstance(rel_paths, list) or not rel_paths:
        abort(400, "files list required")

    with session_scope() as session:
        row = session.get(AgentExecution, execution_id)
        if row is None:
            abort(404, "execution not found")
        ticket = session.get(Ticket, row.ticket_id) if row.ticket_id else None
        if ticket is None:
            abort(404, "ticket not found for execution")
        ticket_dir = _resolve_ticket_output_dir_ws1(row, ticket)

    if ticket_dir is None:
        abort(404, "output directory not found")

    deleted = []
    errors = []
    for rel in rel_paths:
        try:
            target = (ticket_dir / rel).resolve()
            ticket_dir_resolved = ticket_dir.resolve()
            if not str(target).startswith(str(ticket_dir_resolved)):
                errors.append({"rel_path": rel, "error": "path traversal rejected"})
                continue
            if target.is_file():
                target.unlink()
                deleted.append(rel)
            else:
                errors.append({"rel_path": rel, "error": "not found"})
        except Exception as exc:  # noqa: BLE001
            errors.append({"rel_path": rel, "error": str(exc)})

    return jsonify({"deleted": deleted, "errors": errors})


@bp.patch("/<int:execution_id>/assumptions")
def patch_assumptions(execution_id: int):
    """Plan 213 F5 — El operador confirma o corrige los supuestos del análisis.

    NO toca el tracker, NO cambia el estado del ticket y NO relanza nada: es
    solo la decisión humana, guardada. Lo que hace con ella el sistema es
    devolvérsela al agente en la corrida siguiente (F6).
    """
    import json as _json

    from db import session_scope
    from models import AgentExecution

    _VALIDOS = ("pending", "confirmed", "corrected")
    body = request.get_json(silent=True) or {}
    updates = body.get("updates")
    if not isinstance(updates, list):
        return jsonify({"ok": False, "error": "updates_required"}), 400

    with session_scope() as session:
        fila = session.get(AgentExecution, execution_id)
        if fila is None:
            return jsonify({"ok": False, "error": "not_found"}), 404

        meta = dict(fila.metadata_dict or {})
        bloque = dict(meta.get("assumptions") or {})
        items = [dict(i) for i in (bloque.get("items") or [])]

        for upd in updates:
            if not isinstance(upd, dict):
                return jsonify({"ok": False, "error": "invalid_update"}), 400
            estado = (upd.get("status") or "").strip()
            if estado not in _VALIDOS:
                return jsonify({"ok": False, "error": "invalid_status",
                                "validos": list(_VALIDOS)}), 400
            try:
                indice = int(upd.get("index"))
            except (TypeError, ValueError):
                return jsonify({"ok": False, "error": "invalid_index"}), 400
            if indice < 0 or indice >= len(items):
                return jsonify({"ok": False, "error": "invalid_index"}), 400
            correccion = (upd.get("correction") or "").strip()
            if estado == "corrected" and not correccion:
                # Marcar algo como corregido sin decir cuál es la corrección
                # dejaría al agente sabiendo que se equivocó y nada más.
                return jsonify({"ok": False, "error": "correction_required"}), 400

            items[indice]["status"] = estado
            if estado == "corrected":
                items[indice]["correction"] = correccion
            else:
                items[indice].pop("correction", None)

        bloque["items"] = items
        meta["assumptions"] = bloque
        # metadata_json es una columna Text: asignar el dict crudo la dejaría
        # como feature muerta silenciosa.
        fila.metadata_json = _json.dumps(meta, ensure_ascii=False, default=str)
        resultado = dict(bloque)

    return jsonify({"ok": True, "assumptions": resultado})


# ── Plan 265 F7 — Bitácora de acciones de consola (SOLO LECTURA) ───────────
# La escritura se dispara desde los propios handlers de cancel / volver a
# lanzar; acá solo se expone la LECTURA. Es registro, no control de acceso
# (test 9 de F7 lo verifica): este endpoint reporta, nunca decide.

@bp.get("/console-audit")
def console_audit_route():
    """GET /api/executions/console-audit?limit=N — bitácora local, SOLO LECTURA."""
    limit = request.args.get("limit", default=200, type=int)
    return jsonify(console_audit.read_console_audit(limit=limit))
