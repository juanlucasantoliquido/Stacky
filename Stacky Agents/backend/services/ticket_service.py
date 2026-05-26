"""
services/ticket_service.py — Servicio unificado de creación de tickets.

Abstrae la creación de work items / issues sobre los tres sistemas de tickets
soportados (Azure DevOps, Jira, Mantis), resolviendo el tracker y el estado
inicial a partir de la configuración del proyecto activo y del agente.

Uso:
    from services.ticket_service import create_task, TaskResult

    result = create_task(
        project_name="PACIFICO",
        agent_id="AnalistaFuncionalPacifico.agent.md",
        title="RF-001 — Filtro por fecha",
        description="<p>Análisis funcional...</p>",
        parent_id=42,          # ID del Epic padre (ADO) o clave Jira (str) — opcional
    )
    print(result.ticket_id, result.ticket_url)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from project_manager import get_project_config, PROJECTS_DIR

logger = logging.getLogger("stacky_agents.ticket_service")


@dataclass
class TaskResult:
    ticket_id: str          # ID del ticket creado (string para compatibilidad entre trackers)
    ticket_url: str         # URL directa al ticket
    tracker_type: str       # "azure_devops" | "jira" | "mantis"
    raw_response: dict      # Respuesta completa de la API


class TicketServiceError(RuntimeError):
    pass


def _resolve_task_creation_config(project_name: str, agent_id: str) -> dict:
    """Retorna el bloque task_creation del agente en el proyecto indicado.

    Estructura esperada en config.json:
        agent_workflow_configs:
          {agent_id}:
            task_creation:
              work_item_type: "Task"
              initial_state:  "Technical review"
    """
    cfg = get_project_config(project_name)
    if not cfg:
        raise TicketServiceError(f"Proyecto '{project_name}' no encontrado.")
    agent_configs = cfg.get("agent_workflow_configs") or {}
    agent_cfg = agent_configs.get(agent_id) or {}
    task_creation = agent_cfg.get("task_creation") or {}
    return task_creation


def _abs_auth_file(project_name: str, rel_auth: str) -> str:
    """Convierte auth_file relativo en ruta absoluta dentro del proyecto."""
    p = Path(rel_auth)
    if p.is_absolute():
        return str(p)
    return str(PROJECTS_DIR / project_name / rel_auth)


def create_task(
    project_name: str,
    agent_id: str,
    title: str,
    description: str = "",
    parent_id: int | str | None = None,
) -> TaskResult:
    """Crea una tarea en el sistema de tickets del proyecto indicado.

    El tipo de work item y el estado inicial se leen de:
        projects/{project_name}/config.json
          → agent_workflow_configs → {agent_id} → task_creation

    Args:
        project_name: Nombre del proyecto (ej. "PACIFICO", "B2IMPACT", "RSSTANDAR").
        agent_id:     ID del agente que crea la tarea (ej. "AnalistaFuncionalPacifico.agent.md").
        title:        Título de la tarea.
        description:  Descripción (HTML para ADO, texto para Jira/Mantis).
        parent_id:    ID del elemento padre (int para ADO, str/int para Jira/Mantis — opcional).

    Returns:
        TaskResult con ticket_id, ticket_url, tracker_type y raw_response.

    Raises:
        TicketServiceError: si hay un error de configuración o de la API.
    """
    cfg = get_project_config(project_name)
    if not cfg:
        raise TicketServiceError(f"Proyecto '{project_name}' no encontrado.")

    tracker: dict = cfg.get("issue_tracker") or {}
    tracker_type: str = tracker.get("type", "azure_devops")

    task_cfg = _resolve_task_creation_config(project_name, agent_id)
    initial_state: str = task_cfg.get("initial_state", "")
    work_item_type: str = task_cfg.get("work_item_type", "Task")

    auth_rel = tracker.get("auth_file", "")
    auth_abs = _abs_auth_file(project_name, auth_rel) if auth_rel else ""

    # ── Azure DevOps ──────────────────────────────────────────────────────────
    if tracker_type == "azure_devops":
        from services.ado_client import AdoClient, AdoApiError, AdoConfigError

        try:
            client = AdoClient(
                org=tracker.get("organization", ""),
                project=tracker.get("project", ""),
                auth_file=auth_abs or None,
            )
            parent_int = int(parent_id) if parent_id is not None else None
            raw = client.create_work_item(
                work_item_type=work_item_type,
                title=title,
                description=description,
                initial_state=initial_state,
                parent_id=parent_int,
            )
        except (AdoApiError, AdoConfigError) as e:
            raise TicketServiceError(f"Error ADO al crear work item: {e}") from e

        ado_id = raw.get("id")
        url = client.work_item_url(ado_id) if ado_id else ""
        return TaskResult(
            ticket_id=str(ado_id or ""),
            ticket_url=url,
            tracker_type="azure_devops",
            raw_response=raw,
        )

    # ── Jira ──────────────────────────────────────────────────────────────────
    if tracker_type == "jira":
        from services.jira_client import JiraClient, JiraApiError, JiraConfigError

        try:
            client = JiraClient(
                url=tracker.get("url", ""),
                project_key=tracker.get("project_key", ""),
                api_version=tracker.get("api_version", "3"),
                auth_file=auth_abs or "auth/jira_auth.json",
                verify_ssl=tracker.get("verify_ssl", True),
            )
            parent_key = str(parent_id) if parent_id is not None else None

            # Campos a copiar del padre y asignado configurado en el proyecto
            assignee_id: str = task_cfg.get("assignee_id", "")
            copy_fields: list = task_cfg.get("copy_fields_from_parent", [])

            # Campos que se pueden pasar en la creación (disponibles en createmeta de Tarea)
            create_extra: dict = {}
            # Campos que requieren un PUT posterior (no disponibles en createmeta)
            post_update_fields: dict = {}

            if copy_fields and parent_key:
                fields_param = ",".join(copy_fields)
                try:
                    parent_data = client._request(
                        "GET",
                        f"{client._api_base}/issue/{parent_key}?fields={fields_param}",
                    )
                    parent_flds = parent_data.get("fields") or {}
                    # Campos en createmeta de Tarea que admiten copia directa en creación
                    CREATE_SUPPORTED = {"labels", "priority", "components"}
                    for field in copy_fields:
                        raw = parent_flds.get(field)
                        if raw is None or raw == [] or raw == "":
                            continue
                        norm = JiraClient.normalize_field_for_update(raw)
                        if field in CREATE_SUPPORTED:
                            create_extra[field] = norm
                        else:
                            post_update_fields[field] = norm
                except JiraApiError as e:
                    logger.warning(
                        "ticket_service: no se pudieron leer campos del padre %s: %s",
                        parent_key, e,
                    )

            raw = client.create_issue(
                issue_type=work_item_type,
                summary=title,
                description=description,
                initial_status=initial_state,
                parent_key=parent_key,
                assignee_id=assignee_id or None,
                extra_fields=create_extra or None,
            )
        except (JiraApiError, JiraConfigError) as e:
            raise TicketServiceError(f"Error Jira al crear issue: {e}") from e

        issue_key = raw.get("key", "")

        # Actualizar campos no disponibles en creación (producto, área, clasificación…)
        if issue_key and post_update_fields:
            client.update_issue_fields(issue_key, post_update_fields)

        url = client.issue_url(issue_key) if issue_key else ""
        return TaskResult(
            ticket_id=issue_key,
            ticket_url=url,
            tracker_type="jira",
            raw_response=raw,
        )

    # ── Mantis ────────────────────────────────────────────────────────────────
    if tracker_type == "mantis":
        from services.mantis_client import MantisClient, MantisApiError, MantisConfigError

        try:
            client = MantisClient(
                url=tracker.get("url", ""),
                project_id=tracker.get("project_id", ""),
                auth_file=auth_abs or "auth/mantis_auth.json",
                verify_ssl=tracker.get("verify_ssl", True),
            )
            raw = client.create_issue(
                summary=title,
                description=description,
                initial_status=initial_state,
                category=work_item_type if work_item_type else "General",
            )
        except (MantisApiError, MantisConfigError) as e:
            raise TicketServiceError(f"Error Mantis al crear issue: {e}") from e

        issue_id = str(raw.get("issue", {}).get("id") or raw.get("id") or "")
        issue_url = (
            f"{tracker.get('url', '').rstrip('/')}/view.php?id={issue_id}"
            if issue_id else ""
        )
        return TaskResult(
            ticket_id=issue_id,
            ticket_url=issue_url,
            tracker_type="mantis",
            raw_response=raw,
        )

    raise TicketServiceError(f"Tracker '{tracker_type}' no soportado.")


__all__ = ["create_task", "TaskResult", "TicketServiceError"]
