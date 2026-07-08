"""api/devops_remote_console.py — Plan 105. url_prefix="/devops/console"
→ rutas /api/devops/console/... (NO poner /api/ en el prefix; gotcha C2 plan 73)."""
from __future__ import annotations

import json

import config as _config
from flask import Blueprint, jsonify, request
from sqlalchemy import select

from api._helpers import current_user
from models import Ticket
from runtime_paths import data_dir

bp = Blueprint("devops_remote_console", __name__, url_prefix="/devops/console")

_CONSOLE_ADO_ID = -4  # discriminador (plan 90 usa -2, plan 104 usa -3)


def _flag_off() -> bool:
    return not getattr(_config.config, "STACKY_DEVOPS_REMOTE_CONSOLE_ENABLED", False)


def _servers_off() -> bool:
    return not getattr(_config.config, "STACKY_DEVOPS_SERVERS_ENABLED", False)


def _guard():
    """Guard común: 404 si flag OFF, 400 si POST sin JSON (patrón plan 91)."""
    if _flag_off():
        from flask import abort
        abort(404)
    if request.method in ["POST", "PUT", "PATCH"] and not request.is_json:
        return jsonify({"error": "Content-Type debe ser application/json"}), 400
    return None


def _conv_meta(ticket) -> dict:
    """description es JSON {"kind":"remote_console","server_alias":str,
    "write_enabled":bool}. Tolerante: description no-JSON ⇒ {}."""
    if not ticket or not ticket.description:
        return {}
    try:
        return json.loads(ticket.description) if isinstance(ticket.description, str) else ticket.description
    except (json.JSONDecodeError, TypeError):
        return {}


# ---------------------------------------------------------------------------#
# RUTAS
# ---------------------------------------------------------------------------#

@bp.post("/exec")
def exec_route():
    """Ejecuta un comando remoto. Body: {alias, command, conversation_id?, timeout_s?}"""
    guard_result = _guard()
    if guard_result:
        return guard_result

    if _servers_off():
        return jsonify({"error": "remote_console_requires_servers"}), 409

    payload = request.get_json(force=True)
    alias = payload.get("alias")
    command = payload.get("command")
    conversation_id = payload.get("conversation_id")
    timeout_s = payload.get("timeout_s", 120)

    if not alias or not command:
        return jsonify({"error": "alias y command son obligatorios"}), 400

    # Determinar modo: read_only SALVO que la conversación tenga write_enabled
    mode = "read_only"
    if conversation_id:
        from db import db
        ticket = db.session.get(Ticket, conversation_id)
        if ticket and ticket.ado_id == _CONSOLE_ADO_ID:
            meta = _conv_meta(ticket)
            if meta.get("write_enabled") and meta.get("server_alias") == alias:
                mode = "write"

    # Ejecutar
    from services.remote_exec import run_remote
    result = run_remote(
        alias,
        command,
        mode=mode,
        conversation_id=conversation_id,
        user=current_user(),
        timeout_s=timeout_s,
    )

    # Mapeo HTTP
    if not result["ok"]:
        error_key = result.get("error")
        if error_key == "command_not_read_only":
            return jsonify(result), 403
        elif error_key == "server_not_found":
            return jsonify(result), 404
        elif error_key in ("keyring_unavailable", "no_password"):
            return jsonify(result), 503
        elif error_key == "remote_exec_windows_only":
            return jsonify(result), 501
        elif error_key == "timeout":
            return jsonify(result), 504
        else:
            return jsonify(result), 502
    return jsonify(result), 200


@bp.get("/audit/<alias>")
def audit_route(alias: str):
    """Devuelve auditoría del alias. Query: ?limit=&offset=."""
    guard_result = _guard()
    if guard_result:
        return guard_result

    from services.server_registry import validate_alias
    if not validate_alias(alias):
        return jsonify({"error": "alias inválido"}), 400

    limit = min(request.args.get("limit", 100, type=int), 500)
    offset = request.args.get("offset", 0, type=int)

    from services.remote_exec import read_audit
    rows = read_audit(alias, limit=limit, offset=offset)
    return jsonify(rows), 200


@bp.get("/winrm/<alias>")
def winrm_route(alias: str):
    """Test-WSMan contra el host del alias."""
    guard_result = _guard()
    if guard_result:
        return guard_result

    from services.remote_exec import check_winrm
    result = check_winrm(alias)
    return jsonify(result), 200


@bp.post("/conversations")
def create_conversation():
    """Crea una conversación de consola. Body: {server_alias, project, message, runtime?, model?, effort?}."""
    guard_result = _guard()
    if guard_result:
        return guard_result

    payload = request.get_json(force=True)
    server_alias = payload.get("server_alias")
    project = payload.get("project")
    message = payload.get("message")
    runtime = payload.get("runtime", "claude_code_cli")
    model = payload.get("model")
    effort = payload.get("effort")

    if not server_alias or not project or not message:
        return jsonify({"error": "server_alias, project y message son obligatorios"}), 400

    # Validar server existente
    from services.server_registry import get_server
    try:
        server = get_server(server_alias)
    except Exception:
        return jsonify({"error": "server_not_found"}), 404

    # Validar runtime
    from api.devops_agent import _CLI_RUNTIMES
    if runtime not in _CLI_RUNTIMES:
        return jsonify({"error": f"runtime inválido: {runtime}. Debe ser uno de {_CLI_RUNTIMES}"}), 400

    # Crear Ticket
    from database import db
    import datetime
    ticket = Ticket(
        ado_id=_CONSOLE_ADO_ID,
        project=project,
        stacky_project_name=project,
        title=f"[Stacky] Consola {server_alias} — {message[:50]}",
        work_item_type="Task",
        ado_state="Active",
        description=json.dumps({
            "kind": "remote_console",
            "server_alias": server_alias,
            "write_enabled": False,
        }),
        created_at=datetime.datetime.utcnow(),
        updated_at=datetime.datetime.utcnow(),
    )
    db.session.add(ticket)
    db.session.flush()

    # Obligatorio: external_id = -ticket.id (gotcha backfill db.py)
    ticket.external_id = -ticket.id
    db.session.commit()

    # Lanzar turno reusando _launch_turn del plan 90
    from api.devops_agent import _launch_turn
    base_url = request.host_url.rstrip("/")

    from services.remote_console_prompt import build_console_prompt
    wrapped_message = build_console_prompt(
        server_alias,
        base_url,
        message,
        ticket.id,
        write_enabled=False,
    )

    turn_result = _launch_turn(
        ticket_id=ticket.id,
        message=wrapped_message,
        runtime=runtime,
        model=model,
        effort=effort,
        user=current_user(),
    )

    return jsonify({
        "ok": True,
        "conversation_id": ticket.id,
        "execution_id": turn_result.get("execution_id"),
        "runtime": runtime,
        "server_alias": server_alias,
    }), 202


@bp.post("/conversations/<int:cid>/message")
def conversation_message(cid: int):
    """Envía un mensaje a una conversación existente. Mismo contrato dual del plan 90."""
    guard_result = _guard()
    if guard_result:
        return guard_result

    payload = request.get_json(force=True)
    message = payload.get("message")
    runtime = payload.get("runtime")
    model = payload.get("model")
    effort = payload.get("effort")

    if not message:
        return jsonify({"error": "message es obligatorio"}), 400

    from database import db
    ticket = db.session.get(Ticket, cid)
    if not ticket or ticket.ado_id != _CONSOLE_ADO_ID:
        return jsonify({"error": "conversation_not_found"}), 404

    # Si hay un run vivo → stdin; si no → nuevo turno
    from api.devops_agent import _send_input, _launch_turn

    last_run = ticket.runs[-1] if ticket.runs else None
    if last_run and last_run.state == "running":
        result = _send_input(last_run.id, message)
        return jsonify({"ok": True, "execution_id": last_run.id}), 200

    # Nuevo turno
    meta = _conv_meta(ticket)
    server_alias = meta.get("server_alias", "")
    write_enabled = meta.get("write_enabled", False)

    base_url = request.host_url.rstrip("/")
    from services.remote_console_prompt import build_console_prompt
    wrapped_message = build_console_prompt(
        server_alias,
        base_url,
        message,
        cid,
        write_enabled=write_enabled,
    )

    turn_result = _launch_turn(
        ticket_id=cid,
        message=wrapped_message,
        runtime=runtime,
        model=model,
        effort=effort,
        user=current_user(),
    )

    return jsonify({"ok": True, "execution_id": turn_result.get("execution_id")}), 200


@bp.post("/conversations/<int:cid>/write-mode")
def write_mode_toggle(cid: int):
    """Toggle de modo escritura por conversación. Body: {"enabled": true|false}."""
    guard_result = _guard()
    if guard_result:
        return guard_result

    payload = request.get_json(force=True)
    enabled = payload.get("enabled")

    if enabled is None:
        return jsonify({"error": "enabled es obligatorio"}), 400

    from database import db
    ticket = db.session.get(Ticket, cid)
    if not ticket or ticket.ado_id != _CONSOLE_ADO_ID:
        return jsonify({"error": "conversation_not_found"}), 404

    meta = _conv_meta(ticket)
    meta["write_enabled"] = bool(enabled)
    ticket.description = json.dumps(meta)
    db.session.commit()

    # Auditar
    from services.remote_exec import append_audit
    alias = meta.get("server_alias", "unknown")
    append_audit(alias, {
        "kind": "write_mode",
        "enabled": bool(enabled),
        "conversation_id": cid,
        "user": current_user(),
    })

    return jsonify({"ok": True, "write_enabled": bool(enabled)}), 200


@bp.get("/conversations")
def list_conversations():
    """Lista conversaciones del servidor. Query: ?server=<alias>."""
    guard_result = _guard()
    if guard_result:
        return guard_result

    server_alias = request.args.get("server")
    if not server_alias:
        return jsonify({"error": "server es obligatorio"}), 400

    from database import db
    stmt = select(Ticket).where(
        Ticket.ado_id == _CONSOLE_ADO_ID,
    ).order_by(Ticket.updated_at.desc())
    tickets = db.session.execute(stmt).scalars().all()

    # Filtrar por server_alias en description
    result = []
    for t in tickets:
        meta = _conv_meta(t)
        if meta.get("server_alias") == server_alias:
            item = {
                "id": t.id,
                "title": t.title,
                "ado_state": t.ado_state,
                "created_at": t.created_at.isoformat() if t.created_at else None,
                "updated_at": t.updated_at.isoformat() if t.updated_at else None,
                "server_alias": meta.get("server_alias"),
                "write_enabled": meta.get("write_enabled", False),
            }
            # Último run si existe
            if t.runs:
                last_run = t.runs[-1]
                item["last_run"] = {
                    "id": last_run.id,
                    "state": last_run.state,
                }
            result.append(item)

    return jsonify(result), 200
