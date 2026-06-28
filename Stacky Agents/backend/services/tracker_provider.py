"""
services/tracker_provider.py -- Puerto TrackerProvider (Plan 65).

Define el protocolo formal (Port) que todos los adaptadores de tracker deben
implementar, más la fábrica get_tracker_provider() que selecciona el adapter
correcto según issue_tracker.type del proyecto.

Tipos soportados:
  azure_devops → AdoTrackerProvider  (always available)
  gitlab       → GitLabTrackerProvider (requires STACKY_GITLAB_ENABLED=true)

Tipos con path de sync existente (jira, mantis) se rechazan — usen su integración
directa; no redirigir por este puerto todavía.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable, Optional


@dataclass(frozen=True)
class TrackerQuery:
    state: str = "open"
    labels: tuple[str, ...] = ()
    milestone: Optional[str] = None
    assignee: Optional[str] = None
    search: Optional[str] = None
    parent_id: Optional[str] = None


@dataclass(frozen=True)
class TrackerItem:
    item_type: str
    title: str
    description_html: str
    labels: tuple[str, ...] = ()
    assignee: Optional[str] = None
    parent_id: Optional[str] = None
    fields: dict = field(default_factory=dict)


class TrackerError(RuntimeError): ...


class TrackerConfigError(TrackerError): ...


class TrackerApiError(TrackerError):
    def __init__(self, status: int, message: str, *, kind: str = "unknown"):
        super().__init__(message)
        self.status = status
        self.kind = kind


@runtime_checkable
class TrackerProvider(Protocol):
    name: str

    def credentials_present(self) -> bool: ...
    def get_authenticated_user(self) -> dict: ...
    def fetch_open_items(self, query: TrackerQuery) -> list[dict]: ...
    def get_item(self, item_id: str) -> dict: ...
    def item_url(self, item_id: str) -> str: ...
    def fetch_states(self) -> list[str]: ...
    def update_item_state(self, item_id: str, logical_state: str) -> dict: ...
    def fetch_comments(self, item_id: str) -> list[dict]: ...
    def fetch_all_comments(self, item_id: str) -> list[dict]: ...
    def post_comment(self, item_id: str, body_html: str) -> dict: ...
    def comment_exists(self, item_id: str, marker: str) -> bool: ...
    def create_item(self, item: TrackerItem) -> dict: ...
    def find_child_by_marker(self, parent_id: str, marker: str) -> Optional[dict]: ...
    def update_item_assignee(self, item_id: str, assignee: str) -> dict: ...
    def fetch_attachments(self, item_id: str) -> list[dict]: ...
    def upload_attachment(self, file_path: str, file_name: str) -> dict: ...
    def link_attachment(self, item_id: str, attachment: dict) -> dict: ...
    def fetch_item_updates(self, item_id: str, since: Optional[str] = None) -> list[dict]: ...


PORT_METHODS: tuple[str, ...] = (
    "credentials_present",
    "get_authenticated_user",
    "fetch_open_items",
    "get_item",
    "item_url",
    "fetch_states",
    "update_item_state",
    "fetch_comments",
    "fetch_all_comments",
    "post_comment",
    "comment_exists",
    "create_item",
    "find_child_by_marker",
    "update_item_assignee",
    "fetch_attachments",
    "upload_attachment",
    "link_attachment",
    "fetch_item_updates",
)

# Importados a nivel módulo para poder parchear en tests
from services.project_context import resolve_project_context  # noqa: E402
import config  # noqa: E402


def get_tracker_provider(project: Optional[str] = None):
    """Fábrica: selecciona adapter por issue_tracker.type del proyecto."""
    ctx = resolve_project_context(project_name=project)
    ttype = (getattr(ctx, "tracker_type", None) or "azure_devops").strip().lower()

    if ttype == "gitlab":
        if not getattr(config, "STACKY_GITLAB_ENABLED", False):
            raise TrackerConfigError(
                "issue_tracker.type=gitlab pero STACKY_GITLAB_ENABLED=false"
            )
        from services.gitlab_provider import GitLabTrackerProvider
        return GitLabTrackerProvider(project=project)

    if ttype == "azure_devops":
        from services.ado_provider import AdoTrackerProvider
        return AdoTrackerProvider(project=project)

    raise TrackerConfigError(
        f"tracker '{ttype}' sin puerto formal (usa su path de sync existente)"
    )
