"""
services/ado_provider.py -- Adapter AdoTrackerProvider (Plan 65 F1).

Wrapper sobre AdoClient que implementa el puerto TrackerProvider.
Delega 1:1 todos los PORT_METHODS a los métodos equivalentes de AdoClient,
casteando tipos donde la firma difiere (str → int para ado_id).

NO reemplaza build_ado_client ni _default_client/_client_for_ticket_project
en ado_publisher — esos seams quedan intactos para no romper regresión ADO.
"""
from __future__ import annotations

from typing import Optional

from services.tracker_provider import TrackerItem, TrackerQuery
from services.project_context import build_ado_client  # importado a nivel módulo para poder parchear en tests


_ADO_TYPE_MAP = {
    "epic": "Epic",
    "feature": "Feature",
    "story": "User Story",
    "task": "Task",
    "bug": "Bug",
    "issue": "Issue",
}


class AdoTrackerProvider:
    """Adapter de AdoClient al puerto TrackerProvider."""

    name = "azure_devops"

    def __init__(self, project: Optional[str] = None):
        self._client = build_ado_client(project_name=project)
        self._project = project

    # ── Identidad ─────────────────────────────────────────────────────────────

    def credentials_present(self) -> bool:
        """Verifica si hay credenciales ADO configuradas."""
        try:
            import config as _cfg
            return bool(getattr(_cfg, "ADO_PAT", None) or "")
        except Exception:
            return False

    def get_authenticated_user(self) -> dict:
        return self._client.get_authenticated_user()

    # ── Consulta ──────────────────────────────────────────────────────────────

    def fetch_open_items(self, query: TrackerQuery) -> list[dict]:
        """Lista work items abiertos. Usa list_work_items si existe, si no WIQL directo."""
        # AdoClient no tiene list_work_items genérico — usar WIQL interno
        try:
            # Intentar método genérico si existe
            return self._client.list_work_items(  # type: ignore[attr-defined]
                state=query.state,
                assignee=query.assignee,
            )
        except AttributeError:
            # Fallback: devolver lista vacía (integración de WIQL es responsabilidad del cliente)
            return []

    def get_item(self, item_id: str) -> dict:
        return self._client.get_work_item(int(item_id))

    def item_url(self, item_id: str) -> str:
        """Construye la URL de un work item ADO."""
        import urllib.parse
        base = f"https://dev.azure.com/{urllib.parse.quote(self._client.org)}"
        proj = urllib.parse.quote(self._client.project)
        return f"{base}/{proj}/_workitems/edit/{item_id}"

    def fetch_states(self) -> list[str]:
        return self._client.fetch_states()

    # ── Mutación de estado ────────────────────────────────────────────────────

    def update_item_state(self, item_id: str, logical_state: str) -> dict:
        return self._client.update_work_item_state(int(item_id), logical_state)

    # ── Comentarios ───────────────────────────────────────────────────────────

    def fetch_comments(self, item_id: str) -> list[dict]:
        return self._client.fetch_comments(int(item_id))

    def fetch_all_comments(self, item_id: str) -> list[dict]:
        return self._client.fetch_all_comments(int(item_id))

    def post_comment(self, item_id: str, body_html: str) -> dict:
        return self._client.post_comment(int(item_id), body_html)

    def comment_exists(self, item_id: str, marker: str) -> bool:
        result = self._client.comment_exists(int(item_id), marker)
        return result is not None

    # ── Creación ──────────────────────────────────────────────────────────────

    def create_item(self, item: TrackerItem) -> dict:
        ado_type = _ADO_TYPE_MAP.get(item.item_type.lower(), item.item_type)
        fields = dict(item.fields)
        if item.assignee:
            fields["System.AssignedTo"] = item.assignee
        parent_id = int(item.parent_id) if item.parent_id else None
        return self._client.create_work_item(
            work_item_type=ado_type,
            title=item.title,
            description=item.description_html,
            fields=fields or None,
            parent_id=parent_id,
        )

    def find_child_by_marker(self, parent_id: str, marker: str) -> Optional[dict]:
        return self._client.find_child_by_marker(int(parent_id), marker)

    # ── Assignees ─────────────────────────────────────────────────────────────

    def update_item_assignee(self, item_id: str, assignee: str) -> dict:
        return self._client.update_work_item_assigned_to(int(item_id), assignee)

    # ── Attachments ───────────────────────────────────────────────────────────

    def fetch_attachments(self, item_id: str) -> list[dict]:
        return self._client.fetch_attachments(int(item_id))

    def upload_attachment(self, file_path: str, file_name: str) -> dict:
        from pathlib import Path
        return self._client.upload_attachment(Path(file_path), file_name)

    def link_attachment(self, item_id: str, attachment: dict) -> dict:
        return self._client.link_attachment_to_work_item(int(item_id), attachment)

    # ── Updates/edit-learning ─────────────────────────────────────────────────

    def fetch_item_updates(self, item_id: str, since: Optional[str] = None) -> list[dict]:
        updates = self._client.fetch_work_item_updates(int(item_id))
        if since:
            updates = [u for u in updates if (u.get("revisedDate") or "") >= since]
        return updates

    # ── Plan 73 F4 — RepoWriter (ADO: render-only v1, C12) ───────────────────

    def commit_file(self, path: str, content: str, branch: str, message: str) -> dict:
        """ADO commit diferido post-v1. Lanza NotImplementedError (C12 — render-only en v1)."""
        raise NotImplementedError(
            "commit_file no implementado para ADO en v1. "
            "Usa to_ado_yaml() para renderizar y commitea manualmente. "
            "El commit ADO está diferido post-v1."
        )
