"""
operations — Tipos de resultado y lógica core de operaciones ADO.

Todas las operaciones usan un HttpClient desacoplado (inyectable) para
facilitar tests con fake clients sin dependencia de credenciales reales.

Nota Fase 3: implementación mock-first. La integración HTTP real contra ADO API
es el paso siguiente (marcar como "núcleo viable, falta integración HTTP real").
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol, runtime_checkable


# ── Protocolo de HTTP client (desacoplado para tests) ─────────────────────────


@runtime_checkable
class HttpClient(Protocol):
    """Interfaz mínima para el cliente HTTP usado por AdoManager."""

    def get(self, url: str, **kwargs: Any) -> dict[str, Any]:
        ...

    def post(self, url: str, payload: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        ...

    def patch(self, url: str, payload: Any, **kwargs: Any) -> dict[str, Any]:
        ...


# ── Dataclasses de resultado ──────────────────────────────────────────────────


@dataclass
class CommentInfo:
    comment_id: int
    body: str
    author: Optional[str] = None


@dataclass
class TicketContext:
    id: int
    title: str
    state: str
    description: Optional[str] = None
    comments: list[CommentInfo] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class PublishResult:
    work_item_id: int
    dedupe: str  # "PUBLISHED" | "DEDUPED"
    comment_id: Optional[int] = None
    hash_key: Optional[str] = None


@dataclass
class UpdateStateResult:
    work_item_id: int
    previous_state: str
    new_state: str
    success: bool
    reason: Optional[str] = None


@dataclass
class CreateTicketResult:
    created: bool
    work_item_id: Optional[int]
    title: str
    reason: Optional[str] = None  # si ya existía, describe el match


@dataclass
class SearchResult:
    items: list[dict[str, Any]] = field(default_factory=list)
    total: int = 0


# ── Validación de inputs ──────────────────────────────────────────────────────


def _validate_work_item_id(wid: int) -> None:
    if not isinstance(wid, int) or wid <= 0:
        raise ValueError(f"work_item_id debe ser un entero positivo, recibido: {wid!r}")


def _validate_body(body: str) -> None:
    if not body or not body.strip():
        raise ValueError("body del comentario no puede estar vacío")


def _validate_state(state: str) -> None:
    if not state or not state.strip():
        raise ValueError("state no puede estar vacío")


def _validate_title(title: str) -> None:
    if not title or not title.strip():
        raise ValueError("title no puede estar vacío")


# ── Operaciones individuales ──────────────────────────────────────────────────


def get_ticket_context(
    client: HttpClient,
    org: str,
    project: str,
    work_item_id: int,
) -> TicketContext:
    """
    Obtiene datos del ticket + comentarios desde ADO.

    Parámetros
    ----------
    client:
        Instancia de HttpClient (real o fake).
    org, project:
        Organización y proyecto ADO.
    work_item_id:
        ID del work item.
    """
    _validate_work_item_id(work_item_id)

    base = f"https://dev.azure.com/{org}/{project}/_apis/wit/workItems"
    item_url = f"{base}/{work_item_id}?$expand=all&api-version=7.1"
    item_data = client.get(item_url)

    comments_url = f"{base}/{work_item_id}/comments?api-version=7.1-preview.3"
    comments_data = client.get(comments_url)

    fields = item_data.get("fields", {})
    title = fields.get("System.Title", "")
    state = fields.get("System.State", "")
    description = fields.get("System.Description", "")

    raw_comments = comments_data.get("comments", [])
    comments = [
        CommentInfo(
            comment_id=c.get("id", 0),
            body=c.get("text", ""),
            author=c.get("createdBy", {}).get("displayName"),
        )
        for c in raw_comments
    ]

    return TicketContext(
        id=work_item_id,
        title=title,
        state=state,
        description=description,
        comments=comments,
        extra=fields,
    )


def publish_comment(
    client: HttpClient,
    org: str,
    project: str,
    work_item_id: int,
    body: str,
    dedupe_cache: "DedupeCache",
    auto_html: bool = True,
) -> PublishResult:
    """
    Publica un comentario en el work item.
    - Convierte Markdown → HTML automáticamente si auto_html=True.
    - Chequea dedupe por SHA256(work_item_id, body) antes de publicar.
    """
    _validate_work_item_id(work_item_id)
    _validate_body(body)

    if auto_html:
        try:
            from ado_html_postprocessor import md_to_ado_html  # type: ignore
            body_to_publish = md_to_ado_html(body)
        except ImportError:
            body_to_publish = body
    else:
        body_to_publish = body

    hash_key = dedupe_cache.compute_key(work_item_id, body)
    if dedupe_cache.is_duplicate(hash_key):
        return PublishResult(
            work_item_id=work_item_id,
            dedupe="DEDUPED",
            comment_id=None,
            hash_key=hash_key,
        )

    url = (
        f"https://dev.azure.com/{org}/{project}/_apis/wit/workItems"
        f"/{work_item_id}/comments?api-version=7.1-preview.3"
    )
    response = client.post(url, {"text": body_to_publish})
    comment_id = response.get("id")

    dedupe_cache.register(hash_key)

    return PublishResult(
        work_item_id=work_item_id,
        dedupe="PUBLISHED",
        comment_id=comment_id,
        hash_key=hash_key,
    )


def update_state(
    client: HttpClient,
    org: str,
    project: str,
    work_item_id: int,
    new_state: str,
    expected_current_state: Optional[str] = None,
) -> UpdateStateResult:
    """
    Actualiza el estado de un work item con validación de estado actual.
    Si expected_current_state está definido y no coincide, rechaza la operación.
    """
    _validate_work_item_id(work_item_id)
    _validate_state(new_state)

    if expected_current_state is not None:
        ctx = get_ticket_context(client, org, project, work_item_id)
        if ctx.state != expected_current_state:
            return UpdateStateResult(
                work_item_id=work_item_id,
                previous_state=ctx.state,
                new_state=new_state,
                success=False,
                reason=(
                    f"Estado actual '{ctx.state}' no coincide con "
                    f"el esperado '{expected_current_state}'"
                ),
            )
        previous_state = ctx.state
    else:
        previous_state = ""

    url = (
        f"https://dev.azure.com/{org}/{project}/_apis/wit/workItems"
        f"/{work_item_id}?api-version=7.1"
    )
    patch_payload = [{"op": "add", "path": "/fields/System.State", "value": new_state}]
    client.patch(url, patch_payload)

    return UpdateStateResult(
        work_item_id=work_item_id,
        previous_state=previous_state,
        new_state=new_state,
        success=True,
    )


def create_ticket_idempotent(
    client: HttpClient,
    org: str,
    project: str,
    title: str,
    work_item_type: str = "Task",
    parent_id: Optional[int] = None,
    dedupe_key: Optional[str] = None,
) -> CreateTicketResult:
    """
    Crea un work item solo si no existe uno con el mismo titulo/dedupe_key.
    Busca por dedupe_key o por título exacto antes de crear.
    """
    _validate_title(title)

    # Buscar por título exacto via WIQL
    wiql_query = (
        f"SELECT [System.Id], [System.Title] FROM WorkItems "
        f"WHERE [System.TeamProject] = '{project}' "
        f"AND [System.Title] = '{title.replace(chr(39), chr(39)+chr(39))}' "
        f"AND [System.WorkItemType] = '{work_item_type}'"
    )
    search_results = search_work_items(client, org, project, wiql_query)
    if search_results.items:
        existing = search_results.items[0]
        return CreateTicketResult(
            created=False,
            work_item_id=existing.get("id"),
            title=title,
            reason=f"Ya existe work item #{existing.get('id')} con título idéntico",
        )

    # Crear ticket
    url = (
        f"https://dev.azure.com/{org}/{project}/_apis/wit/workItems"
        f"/${work_item_type}?api-version=7.1"
    )
    patch_payload: list[dict[str, Any]] = [
        {"op": "add", "path": "/fields/System.Title", "value": title}
    ]
    if parent_id is not None:
        patch_payload.append(
            {
                "op": "add",
                "path": "/relations/-",
                "value": {
                    "rel": "System.LinkTypes.Hierarchy-Reverse",
                    "url": (
                        f"https://dev.azure.com/{org}/{project}/_apis/wit/workItems/{parent_id}"
                    ),
                },
            }
        )
    response = client.patch(url, patch_payload)
    new_id = response.get("id")

    return CreateTicketResult(
        created=True,
        work_item_id=new_id,
        title=title,
    )


def search_work_items(
    client: HttpClient,
    org: str,
    project: str,
    wiql_query: str,
) -> SearchResult:
    """Ejecuta una WIQL query y devuelve los work items encontrados."""
    if not wiql_query or not wiql_query.strip():
        raise ValueError("wiql_query no puede estar vacío")

    url = (
        f"https://dev.azure.com/{org}/{project}/_apis/wit/wiql?api-version=7.1"
    )
    response = client.post(url, {"query": wiql_query})
    items = response.get("workItems", [])
    return SearchResult(items=items, total=len(items))


# ── Alias para importación desde manager ─────────────────────────────────────
from .dedupe import DedupeCache  # noqa: E402 — importado al final para evitar circularidad
