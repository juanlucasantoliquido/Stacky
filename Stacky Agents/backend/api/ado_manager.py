"""
api/ado_manager.py — Endpoint de creación de tareas en el sistema de tickets configurado.

POST /api/projects/<project_name>/tasks
    Body JSON:
      {
        "agent_id":    "AnalistaFuncionalPacifico.agent.md",  (requerido)
        "title":       "RF-001 — Filtro por fecha",           (requerido)
        "description": "<p>Análisis funcional...</p>",        (opcional)
        "parent_id":   42                                      (opcional — int ADO / str Jira)
      }

    Response 201:
      {
        "ticket_id":    "1234",
        "ticket_url":   "https://...",
        "tracker_type": "azure_devops",
        "initial_state": "Technical review",
        "work_item_type": "Task"
      }

    Response 400 / 500:
      { "error": "mensaje de error" }
"""

from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request

from project_manager import get_project_config
from services.ticket_service import create_task, TicketServiceError

logger = logging.getLogger("stacky_agents.ado_manager")

bp = Blueprint("ado_manager", __name__)


@bp.post("/api/projects/<project_name>/tasks")
def create_project_task(project_name: str):
    """Crea una tarea en el tracker configurado para el proyecto indicado.

    El tipo de work item y el estado inicial se resuelven desde:
        projects/{project_name}/config.json
            → agent_workflow_configs → {agent_id} → task_creation
    """
    body = request.get_json(silent=True) or {}

    agent_id: str = (body.get("agent_id") or "").strip()
    title: str = (body.get("title") or "").strip()
    description: str = (body.get("description") or "").strip()
    parent_id = body.get("parent_id")  # int | str | None

    if not agent_id:
        return jsonify({"error": "El campo 'agent_id' es obligatorio."}), 400
    if not title:
        return jsonify({"error": "El campo 'title' es obligatorio."}), 400

    # Verificar que el proyecto existe
    cfg = get_project_config(project_name)
    if not cfg:
        return jsonify({"error": f"Proyecto '{project_name}' no encontrado."}), 404

    # Verificar que el agente tiene task_creation configurado
    agent_cfgs = cfg.get("agent_workflow_configs") or {}
    agent_cfg = agent_cfgs.get(agent_id) or {}
    task_cfg = agent_cfg.get("task_creation") or {}
    if not task_cfg:
        return jsonify({
            "error": (
                f"El agente '{agent_id}' no tiene 'task_creation' configurado "
                f"en el proyecto '{project_name}'."
            )
        }), 400

    try:
        result = create_task(
            project_name=project_name,
            agent_id=agent_id,
            title=title,
            description=description,
            parent_id=parent_id,
        )
    except TicketServiceError as e:
        logger.warning("create_project_task(%s, %s): %s", project_name, agent_id, e)
        return jsonify({"error": str(e)}), 500

    logger.info(
        "Tarea creada: project=%s agent=%s tracker=%s ticket_id=%s",
        project_name, agent_id, result.tracker_type, result.ticket_id,
    )
    return jsonify({
        "ticket_id":      result.ticket_id,
        "ticket_url":     result.ticket_url,
        "tracker_type":   result.tracker_type,
        "initial_state":  task_cfg.get("initial_state", ""),
        "work_item_type": task_cfg.get("work_item_type", "Task"),
    }), 201
