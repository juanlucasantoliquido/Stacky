"""
manager — Facade público de AdoManager.

Orquesta operaciones ADO con validación, dedupe, schema check y log de acciones.
Cada operación mutativa se loguea via action_log (T15) con su reverse-action.

Uso:
    from ado_manager import AdoManager

    mgr = AdoManager(org="UbimiaPacifico", project="Strategist_Pacifico")

    ctx = mgr.get_ticket_context(1234)

    result = mgr.publish_comment(1234, "## Análisis técnico...")
    # result.dedupe == "PUBLISHED" | "DEDUPED"

    mgr.update_state(1234, "To Do", expected_current_state="Technical review")

    res = mgr.create_ticket_idempotent(
        title="RF-001 - Validar fecha vencimiento",
        work_item_type="Task",
        parent_id=42,
    )
"""

from __future__ import annotations

import os
from typing import Any, Optional

from .dedupe import DedupeCache
from .operations import (
    HttpClient,
    TicketContext,
    PublishResult,
    UpdateStateResult,
    CreateTicketResult,
    SearchResult,
    get_ticket_context as _get_ticket_context,
    publish_comment as _publish_comment,
    update_state as _update_state,
    create_ticket_idempotent as _create_ticket_idempotent,
    search_work_items as _search_work_items,
)


# ── HTTP Client real (requests) ───────────────────────────────────────────────


class _RequestsClient:
    """
    Implementación real del HttpClient usando requests + PAT de Azure DevOps.
    Lee PAT de la variable de entorno ADO_PAT o del archivo PAT-ADO en el repo.
    """

    def __init__(self) -> None:
        import base64

        pat = os.environ.get("ADO_PAT") or self._read_pat_file()
        if not pat:
            raise RuntimeError(
                "ADO_PAT no configurado. "
                "Definir variable de entorno ADO_PAT o archivo PAT-ADO en el repo."
            )
        token = base64.b64encode(f":{pat}".encode()).decode()
        self._headers = {
            "Authorization": f"Basic {token}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _read_pat_file() -> Optional[str]:
        candidates = [
            "PAT-ADO",
            "../PAT-ADO",
            "../../PAT-ADO",
            "../../../PAT-ADO",
        ]
        for path in candidates:
            if os.path.exists(path):
                content = open(path, encoding="utf-8").read().strip()
                return content or None
        return None

    def get(self, url: str, **kwargs: Any) -> dict[str, Any]:
        import requests
        resp = requests.get(url, headers=self._headers, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def post(self, url: str, payload: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        import requests
        resp = requests.post(url, json=payload, headers=self._headers, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def patch(self, url: str, payload: Any, **kwargs: Any) -> dict[str, Any]:
        import requests
        patch_headers = {**self._headers, "Content-Type": "application/json-patch+json"}
        resp = requests.patch(url, json=payload, headers=patch_headers, timeout=30)
        resp.raise_for_status()
        return resp.json()


# ── Facade público ────────────────────────────────────────────────────────────


class AdoManager:
    """
    Facade único para todas las operaciones ADO.

    Parámetros
    ----------
    org:
        Organización ADO (ej: "UbimiaPacifico").
    project:
        Proyecto ADO (ej: "Strategist_Pacifico").
    client:
        Instancia de HttpClient. Si None, usa _RequestsClient (requiere ADO_PAT).
        Pasar un fake client para tests.
    dedupe_cache_path:
        Ruta al archivo de persistencia del cache de dedupe.
        Si None, usa state/ado_dedupe_cache.jsonl relativo al pipeline.
    """

    def __init__(
        self,
        org: str = "UbimiaPacifico",
        project: str = "Strategist_Pacifico",
        client: Optional[HttpClient] = None,
        dedupe_cache_path: Optional[str] = None,
    ) -> None:
        self.org = org
        self.project = project
        self._client: HttpClient = client or _RequestsClient()
        cache_path = dedupe_cache_path or os.path.join(
            os.path.dirname(__file__), "..", "state", "ado_dedupe_cache.jsonl"
        )
        self._dedupe = DedupeCache(cache_path=cache_path)

    # ── Operaciones ───────────────────────────────────────────────────────────

    def get_ticket_context(self, work_item_id: int) -> TicketContext:
        """Obtiene datos del ticket + comentarios."""
        return _get_ticket_context(
            self._client, self.org, self.project, work_item_id
        )

    def publish_comment(
        self,
        work_item_id: int,
        body: str,
        auto_html: bool = True,
    ) -> PublishResult:
        """
        Publica un comentario en el work item.
        - Convierte Markdown → HTML si auto_html=True.
        - Dedupe por SHA256(work_item_id, body).
        - Loguea la acción via action_log con reverse-action.
        """
        result = _publish_comment(
            self._client,
            self.org,
            self.project,
            work_item_id,
            body,
            self._dedupe,
            auto_html=auto_html,
        )

        if result.dedupe == "PUBLISHED":
            self._log_action(
                tool="ado_manager.publish_comment",
                params={"work_item_id": work_item_id, "body_preview": body[:200]},
                result={"comment_id": result.comment_id, "hash_key": result.hash_key},
                reverse=(
                    "ado_manager.delete_comment",
                    {"work_item_id": work_item_id, "comment_id": result.comment_id},
                ),
                ticket_id=work_item_id,
            )

        return result

    def update_state(
        self,
        work_item_id: int,
        new_state: str,
        expected_current_state: Optional[str] = None,
    ) -> UpdateStateResult:
        """
        Actualiza el estado del work item.
        Si expected_current_state está definido, valida el estado actual antes.
        """
        result = _update_state(
            self._client,
            self.org,
            self.project,
            work_item_id,
            new_state,
            expected_current_state,
        )

        if result.success:
            self._log_action(
                tool="ado_manager.update_state",
                params={
                    "work_item_id": work_item_id,
                    "new_state": new_state,
                    "expected_current_state": expected_current_state,
                },
                result={"previous_state": result.previous_state, "new_state": new_state},
                reverse=(
                    "ado_manager.update_state",
                    {"work_item_id": work_item_id, "new_state": result.previous_state},
                ),
                ticket_id=work_item_id,
            )

        return result

    def create_ticket_idempotent(
        self,
        title: str,
        work_item_type: str = "Task",
        parent_id: Optional[int] = None,
        dedupe_key: Optional[str] = None,
    ) -> CreateTicketResult:
        """
        Crea un work item solo si no existe uno con el mismo título.
        Busca duplicados antes de crear.
        """
        result = _create_ticket_idempotent(
            self._client,
            self.org,
            self.project,
            title,
            work_item_type,
            parent_id,
            dedupe_key,
        )

        if result.created:
            self._log_action(
                tool="ado_manager.create_ticket_idempotent",
                params={"title": title, "type": work_item_type, "parent_id": parent_id},
                result={"work_item_id": result.work_item_id},
                reverse=(
                    "ado_manager.delete_ticket",
                    {"work_item_id": result.work_item_id},
                ),
                ticket_id=result.work_item_id,
            )

        return result

    def search_work_items(
        self,
        query: str,
        work_item_type: Optional[str] = None,
        state: Optional[str] = None,
    ) -> SearchResult:
        """Ejecuta búsqueda via WIQL con filtros opcionales."""
        wiql = query
        if work_item_type and "WorkItemType" not in query:
            wiql += f" AND [System.WorkItemType] = '{work_item_type}'"
        if state and "State" not in query:
            wiql += f" AND [System.State] = '{state}'"
        return _search_work_items(self._client, self.org, self.project, wiql)

    # ── Log interno ───────────────────────────────────────────────────────────

    def _log_action(
        self,
        tool: str,
        params: dict[str, Any],
        result: dict[str, Any],
        reverse: Optional[tuple[str, dict[str, Any]]],
        ticket_id: Optional[int],
    ) -> None:
        """Registra la acción via action_log (T15). No propaga errores."""
        try:
            from action_log import log_action  # type: ignore

            log_action(
                actor="AdoManager",
                tool=tool,
                params=params,
                result=result,
                reverse=reverse,
                ticket_id=ticket_id,
            )
        except Exception:  # noqa: BLE001
            pass
