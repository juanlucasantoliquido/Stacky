"""
Feature #4 — FlowConfig Blueprint
====================================
Endpoints para CRUD de reglas ``ado_state → agent_type`` y resolución determinística.

Decisión DO-4.1: la clave del mapping es ``agent_type`` (no ``agent_filename``).

Rutas:
    GET    /api/flow-config                       — lista todas las reglas
    POST   /api/flow-config                       — crea regla
    PUT    /api/flow-config/<rule_id>             — actualiza regla
    DELETE /api/flow-config/<rule_id>             — borra regla
    GET    /api/flow-config/resolve?ado_state=X   — resolución determinística

Observabilidad:
    Eventos stacky_logger: flow_config_rule_created, flow_config_rule_updated,
    flow_config_rule_deleted, flow_config_resolve.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from services.flow_config_store import (
    DuplicateStateError,
    RuleNotFoundError,
    ValidationError,
    create_rule,
    delete_rule,
    list_rules,
    resolve,
    update_rule,
)
from services.stacky_logger import logger as stacky_logger

bp = Blueprint("flow_config", __name__, url_prefix="/flow-config")


def _request_project_name() -> str | None:
    project = (request.args.get("project") or "").strip()
    if project:
        return project
    payload = request.get_json(silent=True) or {}
    body_project = (payload.get("project") or "").strip()
    return body_project or None


# ── GET /flow-config ────────────────────────────────────────────────────────


@bp.get("")
def get_all():
    """Lista todas las reglas de mapping."""
    project_name = _request_project_name()
    rules = list_rules(project_name=project_name)
    return jsonify({"ok": True, "rules": rules, "project": project_name})


# ── POST /flow-config ───────────────────────────────────────────────────────


@bp.post("")
def post_rule():
    """Crea una nueva regla. Body: { ado_state, agent_type }."""
    payload = request.get_json(force=True, silent=True) or {}
    ado_state = payload.get("ado_state", "")
    agent_type = payload.get("agent_type", "")
    project_name = (payload.get("project") or "").strip() or None

    # Validación de presencia de campos requeridos antes de delegar al store
    if not ado_state or not agent_type:
        return (
            jsonify(
                {
                    "ok": False,
                    "error": "validation_error",
                    "message": "ado_state y agent_type son requeridos.",
                }
            ),
            400,
        )

    try:
        rule = create_rule(ado_state=ado_state, agent_type=agent_type, project_name=project_name)
    except ValidationError as exc:
        return (
            jsonify({"ok": False, "error": "validation_error", "message": str(exc)}),
            400,
        )
    except DuplicateStateError as exc:
        return (
            jsonify(
                {
                    "ok": False,
                    "error": "duplicate_state",
                    "message": str(exc),
                }
            ),
            409,
        )

    stacky_logger.info(
        "flow_config",
        "flow_config_rule_created",
        rule_id=rule["id"],
        ado_state=rule["ado_state"],
        agent_type=rule["agent_type"],
        operator="system",
    )
    return jsonify({"ok": True, "rule": rule}), 201


# ── PUT /flow-config/<rule_id> ──────────────────────────────────────────────


@bp.put("/<rule_id>")
def put_rule(rule_id: str):
    """Actualiza una regla existente. Body: { ado_state, agent_type }."""
    payload = request.get_json(force=True, silent=True) or {}
    ado_state = payload.get("ado_state", "")
    agent_type = payload.get("agent_type", "")
    project_name = (payload.get("project") or "").strip() or None

    if not ado_state or not agent_type:
        return (
            jsonify(
                {
                    "ok": False,
                    "error": "validation_error",
                    "message": "ado_state y agent_type son requeridos.",
                }
            ),
            400,
        )

    try:
        rule = update_rule(
            rule_id=rule_id,
            ado_state=ado_state,
            agent_type=agent_type,
            project_name=project_name,
        )
    except ValidationError as exc:
        return (
            jsonify({"ok": False, "error": "validation_error", "message": str(exc)}),
            400,
        )
    except DuplicateStateError as exc:
        return (
            jsonify(
                {
                    "ok": False,
                    "error": "duplicate_state",
                    "message": str(exc),
                }
            ),
            409,
        )
    except RuleNotFoundError:
        return jsonify({"ok": False, "error": "not_found"}), 404

    stacky_logger.info(
        "flow_config",
        "flow_config_rule_updated",
        rule_id=rule["id"],
        ado_state=rule["ado_state"],
        agent_type=rule["agent_type"],
        operator="system",
    )
    return jsonify({"ok": True, "rule": rule})


# ── DELETE /flow-config/<rule_id> ───────────────────────────────────────────


@bp.delete("/<rule_id>")
def delete_rule_endpoint(rule_id: str):
    """Elimina una regla por ID."""
    project_name = _request_project_name()
    try:
        delete_rule(rule_id, project_name=project_name)
    except RuleNotFoundError:
        return jsonify({"ok": False, "error": "not_found"}), 404

    stacky_logger.info(
        "flow_config",
        "flow_config_rule_deleted",
        rule_id=rule_id,
        operator="system",
    )
    return jsonify({"ok": True})


# ── GET /flow-config/resolve ────────────────────────────────────────────────


@bp.get("/resolve")
def resolve_endpoint():
    """
    Dado un estado ADO, retorna el agente mapeado.

    Query params: ado_state=<string>

    Response (200 siempre):
        { ok, found, ado_state, agent_type }
    """
    ado_state = request.args.get("ado_state", "").strip()
    project_name = _request_project_name()
    if not ado_state:
        return (
            jsonify(
                {
                    "ok": False,
                    "error": "validation_error",
                    "message": "El parámetro ado_state es requerido.",
                }
            ),
            400,
        )

    result = resolve(ado_state, project_name=project_name)

    stacky_logger.info(
        "flow_config",
        "flow_config_resolve",
        ado_state=ado_state,
        found=result["found"],
        agent_type=result.get("agent_type"),
    )

    return jsonify({"ok": True, **result})
