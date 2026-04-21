"""
issue_provider.azure_devops_provider — Integración nativa con Azure DevOps Work Items.

Diseño:
  - REST API 7.1 (json-patch+json para updates).
  - Auth con Personal Access Token — el PAT se resuelve en este orden:
      1. $STACKY_ADO_PAT
      2. campo `pat` dentro de `auth/ado_auth.json`
      3. campo `pat` del bloque `issue_tracker` en config del proyecto
    Soporta PAT en dos formatos:
      - "raw": el token tal cual ADO lo emite (46+ chars, alfanum).
      - "preencoded": ya base64-encoded con el prefijo ':' (como los scripts
        existentes del proyecto — .claude/create_ado_tickets.py).
  - WIQL opcional para filtrar tickets (se toma del config; hay defaults).
  - Sin dependencias externas — urllib stdlib para no sumar carga a requirements.txt.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

from .base import IssueProvider, ProviderError, TicketNotFound
from .types import (
    CommentKind,
    Ticket,
    TicketAttachment,
    TicketComment,
    TicketDetail,
)

logger = logging.getLogger("stacky.issue.ado")

_DEFAULT_API_VERSION = "7.1"

# Mapeo default ADO State → bucket Stacky. Override en config.
_DEFAULT_STATE_MAPPING = {
    "New":        "asignada",
    "To Do":      "asignada",
    "Proposed":   "asignada",
    "Approved":   "asignada",
    "Committed":  "aceptada",
    "Active":     "aceptada",
    "In Progress": "aceptada",
    "Doing":      "aceptada",
    "Resolved":   "resuelta",
    "Done":       "completada",
    "Closed":     "completada",
    "Completed":  "completada",
    "Removed":    "archivada",
}

# WIQL default: tickets abiertos asignados al usuario conectado.
_DEFAULT_WIQL = (
    "SELECT [System.Id] FROM WorkItems "
    "WHERE [System.TeamProject] = @project "
    "AND [System.AssignedTo] = @me "
    "AND [System.State] NOT IN ('Closed', 'Done', 'Removed', 'Completed') "
    "ORDER BY [System.ChangedDate] DESC"
)


class AzureDevOpsProvider(IssueProvider):
    """Azure DevOps Work Items como issue tracker."""

    name = "azure_devops"

    def __init__(self, config: dict):
        super().__init__(config)
        self._org   = (config.get("organization") or "").strip()
        self._proj  = (config.get("project") or "").strip()
        self._api   = config.get("api_version", _DEFAULT_API_VERSION)
        self._area  = (config.get("area_path") or "").strip() or None
        self._team  = (config.get("team") or "").strip() or None
        self._wiql  = config.get("wiql") or _DEFAULT_WIQL
        self._timeout = int(config.get("timeout_sec", 30))
        self._state_map = {**_DEFAULT_STATE_MAPPING, **(config.get("state_mapping") or {})}

        self._pat_header = self._resolve_pat(config)
        self._base_org = f"https://dev.azure.com/{self._org}" if self._org else ""
        self._base_proj = f"{self._base_org}/{urllib.parse.quote(self._proj)}" if self._org and self._proj else ""

    # ── Auth ─────────────────────────────────────────────────────────────

    @staticmethod
    def _resolve_pat(config: dict) -> str:
        """
        Devuelve el header Authorization listo para usar: 'Basic <base64>'.
        Busca el PAT en env, auth file y config, en ese orden.
        Acepta PAT "raw" o "preencoded" (ya base64 con ':' prefix).
        """
        candidates: list[tuple[str, str | None]] = []

        # 1. Env
        candidates.append(("env:STACKY_ADO_PAT", os.environ.get("STACKY_ADO_PAT")))

        # 2. Auth file (resuelto desde config, default auth/ado_auth.json)
        auth_file = config.get("auth_file")
        if not auth_file:
            # resolver relativo a Stacky/
            here = Path(__file__).resolve().parent.parent
            auth_file = str(here / "auth" / "ado_auth.json")
        try:
            if os.path.isfile(auth_file):
                with open(auth_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                candidates.append((f"file:{auth_file}", data.get("pat")))
        except Exception as e:
            logger.debug("No se pudo leer auth file %s: %s", auth_file, e)

        # 3. Config inline
        candidates.append(("config.pat", config.get("pat")))

        for source, raw in candidates:
            if not raw:
                continue
            raw = raw.strip()
            if not raw:
                continue
            # Heurística: si trae caracteres base64 puros y longitud típica de
            # PAT-preencoded (>64 chars y no contiene '-' ni '_' salvo permitidos),
            # lo pasamos tal cual. De lo contrario, encodeamos ":<pat>".
            is_pre = _looks_like_preencoded(raw)
            if is_pre:
                logger.debug("PAT preencoded tomado de %s", source)
                return f"Basic {raw}"
            encoded = base64.b64encode(f":{raw}".encode("utf-8")).decode("ascii")
            logger.debug("PAT raw encodeado on-the-fly desde %s", source)
            return f"Basic {encoded}"

        return ""  # → is_available reportará falta de credencial

    def _headers(self, content_type: str = "application/json") -> dict[str, str]:
        return {
            "Authorization": self._pat_header,
            "Content-Type":  content_type,
            "Accept":        "application/json",
        }

    # ── HTTP helpers ─────────────────────────────────────────────────────

    def _request(self, method: str, url: str, body: dict | list | None = None,
                 content_type: str = "application/json") -> dict:
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=self._headers(content_type),
                                     method=method)
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode("utf-8", errors="replace")[:500]
            except Exception:
                pass
            if e.code == 404:
                raise TicketNotFound(f"ADO {method} {url} → 404: {detail}") from e
            raise ProviderError(f"ADO {method} {url} → {e.code}: {detail}") from e
        except urllib.error.URLError as e:
            raise ProviderError(f"ADO network error {method} {url}: {e.reason}") from e

    # ── Discovery ────────────────────────────────────────────────────────

    def is_available(self) -> tuple[bool, str]:
        if not self._org:
            return False, "issue_tracker.organization no configurada"
        if not self._proj:
            return False, "issue_tracker.project no configurado"
        if not self._pat_header:
            return False, ("PAT no encontrado — defina $STACKY_ADO_PAT, "
                           "auth/ado_auth.json o config.issue_tracker.pat")
        # Ping liviano: metadatos del proyecto
        url = f"{self._base_org}/_apis/projects/{urllib.parse.quote(self._proj)}?api-version={self._api}"
        try:
            self._request("GET", url)
            return True, ""
        except ProviderError as e:
            return False, str(e)[:200]

    # ── Lectura ──────────────────────────────────────────────────────────

    def fetch_open_tickets(self) -> list[Ticket]:
        ids = self.fetch_ticket_ids_by_query(self._wiql)
        if not ids:
            return []
        return self._batch_get_tickets(ids)

    def fetch_ticket_ids_by_query(self, query: str) -> list[str]:
        url = f"{self._base_proj}/_apis/wit/wiql?api-version={self._api}"
        body = {"query": query}
        try:
            result = self._request("POST", url, body)
        except ProviderError as e:
            logger.warning("WIQL falló: %s", e)
            return []
        work_items = result.get("workItems") or []
        return [str(w["id"]) for w in work_items if w.get("id") is not None]

    def _batch_get_tickets(self, ids: list[str], page: int = 200) -> list[Ticket]:
        out: list[Ticket] = []
        for i in range(0, len(ids), page):
            chunk = ids[i:i + page]
            ids_qs = ",".join(chunk)
            url = (f"{self._base_proj}/_apis/wit/workitems"
                   f"?ids={ids_qs}&$expand=relations&api-version={self._api}")
            try:
                data = self._request("GET", url)
            except ProviderError as e:
                logger.warning("Batch GET work items falló: %s", e)
                continue
            for wi in data.get("value", []):
                out.append(self._to_ticket(wi))
        return out

    def _to_ticket(self, wi: dict) -> Ticket:
        fields = wi.get("fields") or {}
        wid = str(wi.get("id") or "")
        state_raw = str(fields.get("System.State") or "")
        return Ticket(
            id=wid,
            title=str(fields.get("System.Title") or ""),
            state_raw=state_raw,
            state_normalized=self.normalize_state(state_raw, self._state_map, "asignada"),
            severity=str(fields.get("Microsoft.VSTS.Common.Severity") or ""),
            priority=_coerce_int(fields.get("Microsoft.VSTS.Common.Priority")),
            category=str(fields.get("System.WorkItemType") or ""),
            assignee=_extract_user(fields.get("System.AssignedTo")),
            last_modified=str(fields.get("System.ChangedDate") or ""),
            url=self.ticket_url(wid),
            raw=wi,
        )

    def fetch_ticket_detail(self, ticket_id: str) -> TicketDetail:
        ticket = self._fetch_ticket(ticket_id)
        comments = self._fetch_comments(ticket_id)
        attachments = self._fetch_attachments(ticket.raw)
        fields = ticket.raw.get("fields") or {}

        return TicketDetail(
            ticket=ticket,
            description=str(fields.get("System.Description") or ""),
            description_is_html=True,
            reproduction_steps=str(fields.get("Microsoft.VSTS.TCM.ReproSteps") or ""),
            additional_info=str(fields.get("Microsoft.VSTS.Common.AcceptanceCriteria") or ""),
            comments=comments,
            attachments=attachments,
            extra={
                "area_path":      fields.get("System.AreaPath", ""),
                "iteration_path": fields.get("System.IterationPath", ""),
                "tags":           fields.get("System.Tags", ""),
                "work_item_type": fields.get("System.WorkItemType", ""),
                "created_by":     _extract_user(fields.get("System.CreatedBy")),
                "created_date":   fields.get("System.CreatedDate", ""),
            },
        )

    def _fetch_ticket(self, ticket_id: str) -> Ticket:
        url = (f"{self._base_proj}/_apis/wit/workitems/{ticket_id}"
               f"?$expand=all&api-version={self._api}")
        data = self._request("GET", url)
        return self._to_ticket(data)

    def _fetch_comments(self, ticket_id: str) -> list[TicketComment]:
        # comments API vive bajo preview; usamos 7.1-preview.4
        url = (f"{self._base_proj}/_apis/wit/workItems/{ticket_id}/comments"
               f"?api-version=7.1-preview.4&$top=200")
        try:
            data = self._request("GET", url)
        except ProviderError as e:
            logger.debug("No se pudieron leer comentarios: %s", e)
            return []
        out: list[TicketComment] = []
        for c in data.get("comments", []):
            out.append(TicketComment(
                id=str(c.get("id") or ""),
                author=_extract_user((c.get("createdBy") or {})),
                created_at=str(c.get("createdDate") or ""),
                body=str(c.get("text") or ""),
                is_html=True,
            ))
        return out

    def _fetch_attachments(self, wi: dict) -> list[TicketAttachment]:
        rels = wi.get("relations") or []
        out: list[TicketAttachment] = []
        for r in rels:
            if r.get("rel") != "AttachedFile":
                continue
            attrs = r.get("attributes") or {}
            out.append(TicketAttachment(
                id=str(attrs.get("id") or ""),
                filename=str(attrs.get("name") or ""),
                size_bytes=int(attrs.get("resourceSize") or 0),
                url=str(r.get("url") or ""),
                content_type="",
            ))
        return out

    # ── Escritura ────────────────────────────────────────────────────────

    def add_comment(
        self,
        ticket_id: str,
        body: str,
        kind: CommentKind = CommentKind.GENERIC,
        is_html: bool = False,
    ) -> bool:
        if not body.strip():
            logger.warning("add_comment: body vacío, skip")
            return False
        url = (f"{self._base_proj}/_apis/wit/workItems/{ticket_id}/comments"
               f"?api-version=7.1-preview.4")
        payload = {"text": body if is_html else _to_html(body)}
        try:
            self._request("POST", url, payload)
            logger.info("[ADO] Comentario (%s) publicado en #%s", kind.value, ticket_id)
            return True
        except ProviderError as e:
            logger.warning("[ADO] add_comment falló para #%s: %s", ticket_id, e)
            return False

    def transition_state(self, ticket_id: str, target_state: str) -> bool:
        if not target_state:
            return False
        url = (f"{self._base_proj}/_apis/wit/workitems/{ticket_id}"
               f"?api-version={self._api}")
        body = [{"op": "add", "path": "/fields/System.State", "value": target_state}]
        try:
            self._request("PATCH", url, body, content_type="application/json-patch+json")
            logger.info("[ADO] Ticket #%s → estado '%s'", ticket_id, target_state)
            return True
        except ProviderError as e:
            logger.warning("[ADO] transition_state falló para #%s → %s: %s",
                           ticket_id, target_state, e)
            return False

    def assign(self, ticket_id: str, user: str) -> bool:
        if not user:
            return False
        url = (f"{self._base_proj}/_apis/wit/workitems/{ticket_id}"
               f"?api-version={self._api}")
        body = [{"op": "add", "path": "/fields/System.AssignedTo", "value": user}]
        try:
            self._request("PATCH", url, body, content_type="application/json-patch+json")
            return True
        except ProviderError as e:
            logger.warning("[ADO] assign falló: %s", e)
            return False

    def close(self, ticket_id: str, reason: str = "") -> bool:
        # La mayoría de templates ADO requieren pasar por Resolved → Closed,
        # pero algunos permiten Closed directamente. Probamos los dos.
        for st in ("Closed", "Done", "Completed"):
            if self.transition_state(ticket_id, st):
                if reason:
                    self.add_comment(ticket_id, f"Cerrado automáticamente: {reason}",
                                     kind=CommentKind.GENERIC)
                return True
        return False

    # ── Metadata ─────────────────────────────────────────────────────────

    def ticket_url(self, ticket_id: str) -> str:
        if not (self._base_proj and ticket_id):
            return ""
        return f"{self._base_proj}/_workitems/edit/{ticket_id}"

    def state_mapping(self) -> dict[str, str]:
        return dict(self._state_map)


# ── helpers de módulo ────────────────────────────────────────────────────

_B64_RE = re.compile(r"^[A-Za-z0-9+/=]+$")


def _looks_like_preencoded(raw: str) -> bool:
    """
    PAT "raw" de ADO típicamente son 52 caracteres alfanum puros.
    PAT preencoded (tipo .claude/create_ado_tickets.py) son base64 sobre
    ':<pat>', resultando en una cadena >96 chars con padding '='.
    Heurística: más de 80 chars + match base64 → tratamos como preencoded.
    """
    if len(raw) < 80:
        return False
    return bool(_B64_RE.match(raw))


def _to_html(body: str) -> str:
    """Escape mínimo + conversión de saltos de línea a <br/> para comentarios ADO."""
    body = body.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return body.replace("\n", "<br/>\n")


def _extract_user(field: dict | str | None) -> str:
    """ADO expone usuarios como {displayName, uniqueName, id, ...} o string."""
    if not field:
        return ""
    if isinstance(field, str):
        return field
    return str(field.get("displayName") or field.get("uniqueName") or "")


def _coerce_int(v) -> int | None:
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None
