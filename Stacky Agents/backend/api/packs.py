from datetime import datetime

from flask import Blueprint, abort, jsonify, request

import packs
from db import session_scope
from models import AgentExecution, PackRun

from ._helpers import current_user

bp = Blueprint("packs", __name__, url_prefix="/packs")


@bp.get("")
def list_packs_route():
    return jsonify(packs.list_packs())


@bp.post("/start")
def start():
    payload = request.get_json(force=True, silent=True) or {}
    pack_id = payload.get("pack_id")
    ticket_id = payload.get("ticket_id")
    options = payload.get("options") or {}

    pack = packs.get_pack(pack_id) if pack_id else None
    if pack is None:
        abort(400, "unknown pack_id")
    if not ticket_id:
        abort(400, "ticket_id is required")

    with session_scope() as session:
        run = PackRun(
            pack_definition_id=pack.id,
            ticket_id=int(ticket_id),
            status="running",
            current_step=1,
            started_by=current_user(),
            started_at=datetime.utcnow(),
        )
        run.options = options
        session.add(run)
        session.flush()
        return jsonify(run.to_dict())


@bp.get("/runs/<int:run_id>")
def get_run(run_id: int):
    with session_scope() as session:
        run = session.get(PackRun, run_id)
        if run is None:
            abort(404)
        d = run.to_dict()
        execs = (
            session.query(AgentExecution)
            .filter(AgentExecution.pack_run_id == run_id)
            .order_by(AgentExecution.pack_step.asc())
            .all()
        )
        d["executions"] = [e.to_dict(include_output=False) for e in execs]
        d["definition"] = packs.get_pack(run.pack_definition_id).to_dict() if packs.get_pack(run.pack_definition_id) else None
        return jsonify(d)


@bp.post("/runs/<int:run_id>/advance")
def advance(run_id: int):
    with session_scope() as session:
        run = session.get(PackRun, run_id)
        if run is None:
            abort(404)
        if run.status != "running":
            abort(409, f"pack run not running (status={run.status})")
        definition = packs.get_pack(run.pack_definition_id)
        if definition is None:
            abort(500, "pack definition missing")
        if run.current_step >= len(definition.steps):
            run.status = "completed"
            run.completed_at = datetime.utcnow()
        else:
            run.current_step += 1
        return jsonify(run.to_dict())


@bp.post("/runs/<int:run_id>/pause")
def pause(run_id: int):
    return _set_status(run_id, "paused", expect="running")


@bp.post("/runs/<int:run_id>/resume")
def resume(run_id: int):
    return _set_status(run_id, "running", expect="paused")


@bp.delete("/runs/<int:run_id>")
def abandon(run_id: int):
    return _set_status(run_id, "abandoned", expect=None)


def _set_status(run_id: int, new_status: str, expect: str | None):
    with session_scope() as session:
        run = session.get(PackRun, run_id)
        if run is None:
            abort(404)
        if expect and run.status != expect:
            abort(409, f"expected status={expect}, got {run.status}")
        run.status = new_status
        if new_status in ("completed", "abandoned"):
            run.completed_at = datetime.utcnow()
        return jsonify(run.to_dict())
