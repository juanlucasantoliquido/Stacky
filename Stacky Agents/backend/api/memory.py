"""Endpoints de memoria colaborativa — Fase A (store local + búsqueda + preview).

Sin RBAC: `author_email` se toma de `current_user()` solo para atribución; no hay
enforcement (no existe sustrato de auth). Los endpoints de Git sync, validador y
triage son fases posteriores y no viven acá.
"""
from flask import Blueprint, abort, jsonify, request

from services import memory_store
from services import memory_git_sync
from services import memory_validator
from ._helpers import current_user

bp = Blueprint("memory", __name__, url_prefix="/memory")


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


@bp.get("/<memory_id>")
def get_route(memory_id: str):
    row = memory_store.get(memory_id)
    if row is None:
        abort(404)
    return jsonify(row)


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
