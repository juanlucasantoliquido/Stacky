"""Endpoints de memoria colaborativa — Fase A (store local + búsqueda + preview).

Sin RBAC: `author_email` se toma de `current_user()` solo para atribución; no hay
enforcement (no existe sustrato de auth). Los endpoints de Git sync, validador y
triage son fases posteriores y no viven acá.
"""
import json

from flask import Blueprint, abort, jsonify, request

from services import memory_store
from services import memory_git_sync
from services import memory_validator
from ._helpers import current_user

bp = Blueprint("memory", __name__, url_prefix="/memory")


def _validate_applies_to(applies_to) -> dict:
    """M2.1 — Valida el targeting de una directiva (contrato estricto).

    - debe ser dict; solo las 5 dimensiones de M1.1; valores listas de strings.
    Aborta 400 ante cualquier violación. Devuelve el dict (puede estar vacío;
    el caller decide si lo vacío es válido según el type).
    """
    if applies_to is None:
        return {}
    if not isinstance(applies_to, dict):
        abort(400, "applies_to must be an object")
    for key, val in applies_to.items():
        if key not in memory_store.APPLIES_TO_DIMENSIONS:
            abort(
                400,
                f"applies_to key '{key}' is not allowed; valid dimensions: "
                f"{list(memory_store.APPLIES_TO_DIMENSIONS)}",
            )
        if not isinstance(val, list) or not all(isinstance(x, str) for x in val):
            abort(400, f"applies_to['{key}'] must be a list of strings")
    return applies_to


def _is_nonempty_targeting(applies_to: dict) -> bool:
    return any(applies_to.get(k) for k in memory_store.APPLIES_TO_DIMENSIONS)


@bp.get("")
def list_route():
    project = request.args.get("project")
    return jsonify(
        memory_store.list_observations(
            project=project,
            status=request.args.get("status"),
            scope=request.args.get("scope"),
            type=request.args.get("type"),
            limit=int(request.args.get("limit", "200")),
        )
    )


@bp.post("")
def create_route():
    payload = request.get_json(force=True, silent=True) or {}
    project = payload.get("project")
    type_ = payload.get("type")
    title = payload.get("title")
    content = payload.get("content")
    if not project or not type_ or not title or not content:
        abort(400, "project, type, title and content are required")
    # V1.5 (B5): los tipos FA-* viven en el canal SYSTEM prompt; crearlos por
    # esta API (canal USER) duplicaría el conocimiento. Rechazo estructural,
    # mismo set que el filtro de inyección de get_context_for_run.
    if type_ in memory_store.RESERVED_TYPES:
        abort(
            400,
            f"type '{type_}' is reserved for the system-prompt (FA-*) channel; "
            f"use one of the injectable types instead",
        )

    # M2.1 — Campos de directiva (aditivos, default observacional).
    enforcement = payload.get("enforcement")
    if enforcement is not None and enforcement not in ("suggest", "always"):
        abort(400, "enforcement must be 'suggest' or 'always'")
    priority = int(payload.get("priority") or 0)
    applies_to = _validate_applies_to(payload.get("applies_to"))

    is_directive = type_ == "directive"
    if is_directive:
        # una directiva sin targeting aplicaría a TODO → peligrosa; se rechaza.
        if not _is_nonempty_targeting(applies_to):
            abort(400, "a directive needs at least one targeting dimension in applies_to")
        # default de enforcement para directivas: suggest (la máquina jamás nace always).
        if enforcement is None:
            enforcement = "suggest"
    else:
        # enforcement=always solo tiene sentido para directivas.
        if enforcement == "always":
            abort(400, "enforcement='always' is only allowed for type='directive'")

    applies_to_json = json.dumps(applies_to) if (is_directive and applies_to) else None

    memory_id = memory_store.save_observation(
        project=project,
        type=type_,
        title=title,
        content=content,
        scope=payload.get("scope", "project"),
        topic_key=payload.get("topic_key"),
        status=payload.get("status", "active"),
        confidence=payload.get("confidence"),
        source_kind=payload.get("source_kind", "operator"),
        source_execution_id=payload.get("source_execution_id"),
        source_ticket_id=payload.get("source_ticket_id"),
        source_ado_id=payload.get("source_ado_id"),
        source_agent_type=payload.get("source_agent_type"),
        author_email=current_user(),
        author_role=payload.get("author_role"),
        tags=payload.get("tags"),
        enforcement=enforcement,
        priority=priority,
        applies_to_json=applies_to_json,
    )
    return jsonify({"memory_id": memory_id}), 201


@bp.get("/search")
def search_route():
    project = request.args.get("project")
    if not project:
        abort(400, "project is required")
    return jsonify(
        memory_store.search(
            project=project,
            query_text=request.args.get("q"),
            scope=request.args.get("scope"),
            agent_type=request.args.get("agent_type"),
            k=int(request.args.get("k", "20")),
        )
    )


@bp.get("/context-preview")
def context_preview_route():
    """Preview de lo que `enrich_blocks` inyectaría como bloque `stacky-memory`."""
    project = request.args.get("project")
    if not project:
        abort(400, "project is required")
    return jsonify(
        memory_store.get_context_for_run(
            project=project,
            agent_type=request.args.get("agent_type"),
            query_text=request.args.get("q"),
        )
    )


@bp.get("/status")
def status_route():
    project = request.args.get("project")
    if not project:
        abort(400, "project is required")
    counts: dict[str, int] = {}
    for status in memory_store.ALL_STATUSES:
        counts[status] = len(
            memory_store.list_observations(project=project, status=status, limit=10000)
        )
    return jsonify({"project": project, "counts": counts})


@bp.post("/validation/runs")
def start_validation_run_route():
    payload = request.get_json(force=True, silent=True) or {}
    try:
        run_id = memory_validator.start_validation_run(
            project=(payload.get("project") or "").strip() or None,
            requested_by=current_user(),
            checks=payload.get("checks"),
        )
    except ValueError as exc:
        abort(400, str(exc))
    return jsonify({"run_id": run_id, "status": "queued"}), 202


@bp.get("/validation/runs")
def list_validation_runs_route():
    return jsonify(
        memory_validator.list_runs(
            project=request.args.get("project"),
            limit=int(request.args.get("limit", "50")),
        )
    )


@bp.get("/validation/runs/<int:run_id>")
def get_validation_run_route(run_id: int):
    row = memory_validator.get_run(run_id)
    if row is None:
        abort(404)
    return jsonify(row)


@bp.get("/validation/findings")
def list_validation_findings_route():
    run_id_raw = request.args.get("run_id")
    return jsonify(
        memory_validator.list_findings(
            project=request.args.get("project"),
            run_id=int(run_id_raw) if run_id_raw else None,
            status=request.args.get("status", "open"),
            check_name=request.args.get("check"),
            severity=request.args.get("severity"),
            limit=int(request.args.get("limit", "200")),
        )
    )


@bp.get("/validation/findings/<int:finding_id>")
def get_validation_finding_route(finding_id: int):
    row = memory_validator.get_finding(finding_id)
    if row is None:
        abort(404)
    return jsonify(row)


@bp.post("/validation/findings/<int:finding_id>/action")
def apply_validation_finding_action_route(finding_id: int):
    payload = request.get_json(force=True, silent=True) or {}
    action = payload.get("action")
    if action not in memory_validator.FINDING_ACTIONS:
        abort(400, f"action must be one of {memory_validator.FINDING_ACTIONS}")
    try:
        row = memory_validator.apply_finding_action(
            finding_id=finding_id,
            action=action,
            actor=current_user(),
            source_memory_id=payload.get("source_memory_id"),
            target_memory_id=payload.get("target_memory_id"),
            reason=payload.get("reason"),
        )
    except LookupError:
        abort(404)
    except ValueError as exc:
        abort(400, str(exc))
    return jsonify(row)


@bp.get("/validation/ticket-badges")
def validation_ticket_badges_route():
    return jsonify(
        memory_validator.ticket_badges(
            project=request.args.get("project"),
            status=request.args.get("status", "open"),
        )
    )


@bp.get("/relations")
def list_relations_route():
    return jsonify(
        memory_store.list_relations(
            project=request.args.get("project"),
            relation=request.args.get("relation"),
            status=request.args.get("status"),
            memory_id=request.args.get("memory_id"),
            limit=int(request.args.get("limit", "200")),
        )
    )


@bp.get("/conflict-graph")
def conflict_graph_route():
    project = request.args.get("project")
    if not project:
        abort(400, "project is required")
    return jsonify(memory_store.conflict_graph(project=project, status=request.args.get("status")))


@bp.get("/sync/status")
def sync_status_route():
    project = request.args.get("project")
    if not project:
        abort(400, "project is required")
    return jsonify(
        memory_git_sync.status(
            project,
            remote_url=request.args.get("remote_url"),
            timeout_seconds=int(request.args.get("timeout_seconds", "30")),
        )
    )


@bp.post("/sync/run")
def sync_run_route():
    payload = request.get_json(force=True, silent=True) or {}
    project = payload.get("project")
    if not project:
        abort(400, "project is required")
    # Gobernanza: un POST sin "enabled" NO activa la sync; cae al flag de
    # entorno STACKY_MEMORY_GIT_SYNC_ENABLED (OFF por default). Activar Fase E
    # exige opt-in explícito (enabled:true) o el flag de entorno (sign-off).
    enabled_req = payload.get("enabled")
    try:
        result = memory_git_sync.sync_once(
            project=project,
            enabled=None if enabled_req is None else bool(enabled_req),
            remote_url=payload.get("remote_url"),
            push=payload.get("push", True) is not False,
            timeout_seconds=int(payload.get("timeout_seconds", 30)),
            max_events=int(payload.get("max_events", 200)),
        )
    except ValueError as exc:
        abort(400, str(exc))
    return jsonify(result), 200 if result.get("ok") else 202


@bp.get("/directive-health")
def directive_health_route():
    """M3.2 — Salud del set de directivas (overlapping/budget/stale)."""
    project = request.args.get("project")
    if not project:
        abort(400, "project is required")
    return jsonify(memory_store.directive_health(project))


@bp.get("/types")
def types_route():
    """M3.1 — Tipos de memoria: injectables (canal USER) vs reservados (B5)."""
    return jsonify({
        "injectable": list(memory_store.INJECTABLE_TYPES),
        "reserved": sorted(memory_store.RESERVED_TYPES),
    })


@bp.get("/<memory_id>")
def get_route(memory_id: str):
    row = memory_store.get(memory_id)
    if row is None:
        abort(404)
    return jsonify(row)


@bp.patch("/<memory_id>")
def update_route(memory_id: str):
    """M2.2 — Edita contenido/targeting/enforcement/priority de una memoria."""
    payload = request.get_json(force=True, silent=True) or {}

    existing = memory_store.get(memory_id)
    if existing is None:
        abort(404)

    editable_keys = {
        "title", "content", "enforcement", "priority", "applies_to",
        "expires_at", "review_after",
    }
    provided = {k for k in editable_keys if k in payload}
    if not provided:
        abort(400, "no editable fields provided")

    enforcement = payload.get("enforcement")
    if "enforcement" in payload and enforcement not in ("suggest", "always"):
        abort(400, "enforcement must be 'suggest' or 'always'")

    # type efectivo tras la edición (no se puede cambiar el type por PATCH).
    eff_type = existing.get("type")
    applies_to_json = None
    if "applies_to" in payload:
        applies_to = _validate_applies_to(payload.get("applies_to"))
        if eff_type == "directive" and not _is_nonempty_targeting(applies_to):
            abort(400, "a directive needs at least one targeting dimension in applies_to")
        applies_to_json = json.dumps(applies_to)

    eff_enforcement = enforcement if "enforcement" in payload else existing.get("enforcement")
    if eff_enforcement == "always" and eff_type != "directive":
        abort(400, "enforcement='always' is only allowed for type='directive'")

    ok = memory_store.update_observation(
        memory_id,
        title=payload.get("title"),
        content=payload.get("content"),
        enforcement=enforcement if "enforcement" in payload else None,
        priority=payload.get("priority") if "priority" in payload else None,
        applies_to_json=applies_to_json,
    )
    if not ok:
        abort(404)
    return jsonify({"ok": True})


@bp.post("/directive-preview")
def directive_preview_route():
    """M2.2 — Dry-run de targeting: ¿matchea `applies_to` el ticket dado?"""
    from db import session_scope
    from models import Ticket

    payload = request.get_json(force=True, silent=True) or {}
    applies_to = _validate_applies_to(payload.get("applies_to"))
    ticket_id = payload.get("ticket_id")
    if ticket_id is None:
        abort(400, "ticket_id is required")

    with session_scope() as session:
        ticket = session.get(Ticket, int(ticket_id))
        if ticket is None:
            abort(404, "ticket not found")
        agent_type = payload.get("agent_type")
        matches = memory_store.directive_matches_run(
            applies_to,
            agent_type=agent_type,
            project=ticket.stacky_project_name or ticket.project,
            ticket_title=ticket.title,
            ticket_description=ticket.description,
            work_item_type=ticket.work_item_type,
        )
        reasons: list[str] = []
        if matches:
            reasons.append("el ticket cumple todas las dimensiones del targeting")
        else:
            reasons.append("el ticket no cumple alguna dimensión del targeting")
    return jsonify({"matches": matches, "reasons": reasons})


@bp.post("/<memory_id>/status")
def set_status_route(memory_id: str):
    payload = request.get_json(force=True, silent=True) or {}
    status = payload.get("status")
    if status not in memory_store.ALL_STATUSES:
        abort(400, f"status must be one of {memory_store.ALL_STATUSES}")
    if not memory_store.set_status(memory_id, status):
        abort(404)
    return jsonify({"ok": True})


@bp.post("/relations")
def mark_relation_route():
    payload = request.get_json(force=True, silent=True) or {}
    project = payload.get("project")
    source = payload.get("source_memory_id")
    target = payload.get("target_memory_id")
    relation = payload.get("relation")
    if not project or not source or not target or not relation:
        abort(400, "project, source_memory_id, target_memory_id and relation are required")
    if relation not in memory_store.RELATIONS:
        abort(400, f"relation must be one of {memory_store.RELATIONS}")
    if relation == "not_conflict":
        relation_id = memory_store.resolve_conflicts_between(
            project=project,
            source_memory_id=source,
            target_memory_id=target,
            marked_by_actor=current_user(),
            reason=payload.get("reason"),
        )
    else:
        relation_id = memory_store.mark_relation(
            project=project,
            source_memory_id=source,
            target_memory_id=target,
            relation=relation,
            reason=payload.get("reason"),
            evidence=payload.get("evidence"),
            confidence=payload.get("confidence"),
            marked_by_actor=current_user(),
            marked_by_kind="human",
        )
    return jsonify({"relation_id": relation_id}), 201
