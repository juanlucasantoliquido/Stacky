"""
ado_task_creator.py — Creación de child tasks en ADO desde TAREAS_DESARROLLO.md.

Cuando PM completa el análisis de un ticket, las tareas se crean automáticamente
como Child Tasks del Work Item principal en ADO.

Uso:
    from ado_task_creator import ADOTaskCreator
    creator = ADOTaskCreator()
    ids = creator.create_child_tasks_from_tareas(27698, ticket_folder)
"""

import re
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.ado_task_creator")


class ADOTaskCreator:
    """Creates and manages child tasks in ADO from parsed TAREAS_DESARROLLO.md."""

    def __init__(self, ado_client=None):
        self._ado_client = ado_client

    @property
    def ado_client(self):
        if self._ado_client is None:
            try:
                from ado_enricher import _get_ado_client
                self._ado_client = _get_ado_client()
            except Exception as e:
                logger.error("Cannot initialize ADO client: %s", e)
                raise
        return self._ado_client

    def create_child_tasks_from_tareas(
        self,
        parent_work_item_id: int,
        ticket_folder: str,
        project: str = "Strategist_Pacifico",
    ) -> list[int]:
        """
        Parse TAREAS_DESARROLLO.md and create Child Tasks in ADO.

        Returns list of created Work Item IDs.
        """
        tasks = self._parse_tareas_md(ticket_folder)
        if not tasks:
            logger.warning("No tasks found in TAREAS_DESARROLLO.md for WI#%d",
                           parent_work_item_id)
            return []

        created_ids = []
        for task in tasks:
            try:
                child_id = self._create_child_task(
                    parent_work_item_id, task, project
                )
                if child_id:
                    created_ids.append(child_id)
            except Exception as e:
                logger.error("Failed to create child task '%s': %s",
                             task.get("title", "?"), e)

        logger.info("Created %d child tasks for WI#%d", len(created_ids),
                     parent_work_item_id)
        return created_ids

    def _create_child_task(
        self,
        parent_work_item_id: int,
        task: dict,
        project: str,
    ) -> Optional[int]:
        """Create a single child task in ADO linked to the parent."""
        title = f"[Stacky] {task['title']}"
        description = task.get("description", "")
        file_ref = task.get("file", "")

        if file_ref:
            description += f"\n\n**Archivo:** `{file_ref}`"

        body = [
            {
                "op": "add",
                "path": "/fields/System.Title",
                "value": title,
            },
            {
                "op": "add",
                "path": "/fields/System.Description",
                "value": description,
            },
            {
                "op": "add",
                "path": "/fields/System.Tags",
                "value": "stacky; auto-generated",
            },
            {
                "op": "add",
                "path": "/relations/-",
                "value": {
                    "rel": "System.LinkTypes.Hierarchy-Reverse",
                    "url": self._build_work_item_url(parent_work_item_id, project),
                },
            },
        ]

        try:
            result = self.ado_client.create_work_item_raw(
                project=project,
                work_item_type="Task",
                body=body,
            )
            child_id = result.get("id")
            logger.info("Created child task #%s: %s", child_id, title)
            return child_id
        except AttributeError:
            # Fallback: if ado_client doesn't have create_work_item_raw
            logger.warning("ADO client doesn't support create_work_item_raw, "
                           "trying alternative method")
            return self._create_child_task_fallback(
                parent_work_item_id, task, project
            )

    def _create_child_task_fallback(
        self,
        parent_work_item_id: int,
        task: dict,
        project: str,
    ) -> Optional[int]:
        """Fallback creation using simpler API."""
        try:
            result = self.ado_client.create_work_item(
                type="Task",
                title=f"[Stacky] {task['title']}",
                description=task.get("description", ""),
                tags="stacky; auto-generated",
            )
            return result if isinstance(result, int) else result.get("id")
        except Exception as e:
            logger.error("Fallback creation also failed: %s", e)
            return None

    def _build_work_item_url(self, work_item_id: int, project: str) -> str:
        """Build the ADO REST API URL for a work item."""
        org = self._get_org_url()
        return f"{org}/{project}/_apis/wit/workItems/{work_item_id}"

    def _get_org_url(self) -> str:
        """Get the ADO organization URL from auth config."""
        try:
            import json
            auth_file = Path(__file__).parent / "auth" / "ado_auth.json"
            if auth_file.exists():
                config = json.loads(auth_file.read_text(encoding="utf-8"))
                return config.get("organization_url", "https://dev.azure.com/UbimiaPacifico")
        except Exception:
            pass
        return "https://dev.azure.com/UbimiaPacifico"

    def mark_child_task_done(self, child_work_item_id: int, comment: str = ""):
        """Mark a child task as Done when DEV completes it."""
        try:
            self.ado_client.update_work_item(child_work_item_id, {
                "System.State": "Done",
            })
            if comment:
                self.ado_client.add_comment(child_work_item_id, comment)
            logger.info("Child task #%d marked as Done", child_work_item_id)
        except Exception as e:
            logger.error("Failed to mark task #%d as Done: %s",
                         child_work_item_id, e)

    def _parse_tareas_md(self, ticket_folder: str) -> list[dict]:
        """
        Parse TAREAS_DESARROLLO.md extracting task blocks.

        Expected format:
          ## [PENDIENTE] Tarea 1 — DAL
          Descripción de la tarea...
          **Archivo:** Batch/Negocio/EjemploDalc.cs

        Also handles:
          - [ ] Tarea simple (checkbox format)
        """
        tareas_path = Path(ticket_folder) / "TAREAS_DESARROLLO.md"
        if not tareas_path.exists():
            return []

        content = tareas_path.read_text(encoding="utf-8", errors="replace")
        tasks = []

        # Pattern 1: ## [ESTADO] Título — Componente
        section_pattern = re.compile(
            r"^##\s*\[(\w+)\]\s*(.+?)$",
            re.MULTILINE
        )
        sections = list(section_pattern.finditer(content))

        for i, match in enumerate(sections):
            state = match.group(1).strip()
            title = match.group(2).strip()
            # Get description (text between this heading and the next)
            start = match.end()
            end = sections[i + 1].start() if i + 1 < len(sections) else len(content)
            description = content[start:end].strip()

            # Extract file reference
            file_match = re.search(
                r"\*\*Archivo:\*\*\s*(.+?)$", description, re.MULTILINE
            )
            file_ref = file_match.group(1).strip() if file_match else ""

            tasks.append({
                "title": title,
                "state": state,
                "description": description[:500],  # cap description
                "file": file_ref,
            })

        # Pattern 2: - [ ] Tarea simple (if no sections found)
        if not tasks:
            checkbox_pattern = re.compile(
                r"^-\s*\[[ x]\]\s*(.+?)$", re.MULTILINE | re.IGNORECASE
            )
            for match in checkbox_pattern.finditer(content):
                title = match.group(1).strip()
                tasks.append({
                    "title": title,
                    "state": "PENDIENTE",
                    "description": "",
                    "file": "",
                })

        return tasks
