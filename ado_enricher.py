"""ado_enricher — G-03 Deep Enrichment de Work Items ADO para prompts PM."""

from __future__ import annotations

import html as _html_mod
import logging
import re
import urllib.parse

logger = logging.getLogger("stacky.ado_enricher")

_MAX_ATTACHMENT_BYTES = 256 * 1024  # 256 KB safety cap per attachment


_TEXT_ATTACHMENT_EXTS = (".txt", ".log", ".md", ".csv")


class ADOEnricher:

    def __init__(self, provider=None, project_name: str | None = None):
        self._provider = provider
        self._project_name = project_name
        if self._provider is None:
            try:
                from issue_provider import get_provider
                self._provider = get_provider(project_name=project_name)
            except Exception as e:
                logger.debug("ADOEnricher: no provider disponible: %s", e)
                self._provider = None

    # ── API pública ──────────────────────────────────────────────────────

    def enrich(self, work_item_id) -> str:
        wid = self._coerce_id(work_item_id)
        if not wid:
            return ""
        if self._provider is None:
            logger.warning("ADOEnricher.enrich: provider no disponible para #%s", wid)
            return ""

        try:
            wi = self._get_work_item(wid)
        except Exception as e:
            logger.warning("ADOEnricher.enrich: fallo al traer WI #%s: %s", wid, e)
            return ""

        if not wi:
            return ""

        fields = (wi.get("fields") or {})
        title  = fields.get("System.Title") or ""
        state  = fields.get("System.State") or ""
        prio   = fields.get("Microsoft.VSTS.Common.Priority", "N/A")
        tags   = fields.get("System.Tags", "") or ""
        desc_html = fields.get("System.Description") or "(sin descripción)"

        lines = [
            f"## Work Item #{wid}: {title}",
            f"**Estado:** {state}",
            f"**Prioridad:** {prio}",
            f"**Tags:** {tags}",
            "",
            "### Descripción",
            self._html_to_md(desc_html),
            "",
        ]

        # Comentarios
        try:
            comments = self._get_comments(wid)
        except Exception as e:
            logger.warning("ADOEnricher: fallo al traer comentarios de #%s: %s", wid, e)
            comments = []

        if comments:
            lines.append("### Comentarios en ADO")
            for c in comments[-10:]:
                author = (c.get("createdBy") or {}).get("displayName", "?")
                date   = (c.get("createdDate") or "")[:10]
                body   = self._html_to_md(c.get("text", "") or "")
                lines.append(f"**{author} ({date}):** {body}")
            lines.append("")

        # Work items relacionados
        try:
            related = self._get_related_work_items(wid, wi)
        except Exception as e:
            logger.warning("ADOEnricher: fallo en related de #%s: %s", wid, e)
            related = []

        if related:
            lines.append("### Work Items relacionados")
            for r in related[:5]:
                lines.append(f"- #{r.get('id','')}: {r.get('title','')} ({r.get('state','')})")
            lines.append("")

        # Adjuntos de texto (solo nombres — el contenido puede venir vacío)
        try:
            attachments = [
                a for a in self._get_attachments(wid, wi)
                if (a.get("name") or "").lower().endswith(_TEXT_ATTACHMENT_EXTS)
            ]
        except Exception as e:
            logger.warning("ADOEnricher: fallo en attachments de #%s: %s", wid, e)
            attachments = []

        if attachments:
            lines.append("### Adjuntos de texto")
            for a in attachments[:5]:
                lines.append(f"- {a.get('name','')}")
            lines.append("")

        return "\n".join(lines)

    def deep_enrich(self, work_item_id, *, include_attachment_content: bool = True) -> str:
        """G-03: Deep enrichment — like enrich() but also downloads text attachment contents.

        Returns a markdown block ready to inject into the PM prompt.
        """
        wid = self._coerce_id(work_item_id)
        if not wid:
            return ""
        if self._provider is None:
            logger.warning("ADOEnricher.deep_enrich: provider no disponible para #%s", wid)
            return ""

        try:
            wi = self._get_work_item(wid)
        except Exception as e:
            logger.warning("ADOEnricher.deep_enrich: fallo al traer WI #%s: %s", wid, e)
            return ""

        if not wi:
            return ""

        fields = (wi.get("fields") or {})
        title  = fields.get("System.Title") or ""
        state  = fields.get("System.State") or ""
        wi_type = fields.get("System.WorkItemType") or ""
        prio   = fields.get("Microsoft.VSTS.Common.Priority", "N/A")
        severity = fields.get("Microsoft.VSTS.Common.Severity", "")
        tags   = fields.get("System.Tags", "") or ""
        assigned = (fields.get("System.AssignedTo") or {})
        if isinstance(assigned, dict):
            assigned = assigned.get("displayName", "")
        area_path = fields.get("System.AreaPath", "")
        iteration = fields.get("System.IterationPath", "")
        desc_html = fields.get("System.Description") or "(sin descripción)"
        repro_html = fields.get("Microsoft.VSTS.TCM.ReproSteps") or ""
        acceptance = fields.get("Microsoft.VSTS.Common.AcceptanceCriteria") or ""

        lines = [
            f"## Work Item #{wid}: {title}",
            f"**Tipo:** {wi_type}  ",
            f"**Estado:** {state}  ",
            f"**Prioridad:** {prio}  ",
        ]
        if severity:
            lines.append(f"**Severidad:** {severity}  ")
        lines.append(f"**Asignado a:** {assigned}  ")
        lines.append(f"**Tags:** {tags}  ")
        if area_path:
            lines.append(f"**Area Path:** {area_path}  ")
        if iteration:
            lines.append(f"**Iteration:** {iteration}  ")
        lines.append("")

        # Descripción
        lines.append("### Descripción")
        lines.append(self._html_to_md(desc_html))
        lines.append("")

        # Repro Steps (for bugs)
        if repro_html:
            lines.append("### Pasos de Reproducción")
            lines.append(self._html_to_md(repro_html))
            lines.append("")

        # Acceptance Criteria
        if acceptance:
            lines.append("### Criterios de Aceptación")
            lines.append(self._html_to_md(acceptance))
            lines.append("")

        # Comentarios (últimos 10)
        try:
            comments = self._get_comments(wid)
        except Exception as e:
            logger.warning("deep_enrich: fallo al traer comentarios de #%s: %s", wid, e)
            comments = []

        if comments:
            lines.append("### Comentarios en ADO (últimos 10)")
            for c in comments[-10:]:
                author = (c.get("createdBy") or {}).get("displayName", "?")
                date   = (c.get("createdDate") or "")[:10]
                body   = self._html_to_md(c.get("text", "") or "")
                lines.append(f"**{author} ({date}):** {body}")
            lines.append("")

        # Work items relacionados (hasta 5)
        try:
            related = self._get_related_work_items(wid, wi)
        except Exception as e:
            logger.warning("deep_enrich: fallo en related de #%s: %s", wid, e)
            related = []

        if related:
            lines.append("### Work Items relacionados")
            for r in related[:5]:
                lines.append(f"- #{r.get('id','')}: {r.get('title','')} ({r.get('state','')})")
            lines.append("")

        # Adjuntos de texto — con contenido descargado
        try:
            attachments = [
                a for a in self._get_attachments(wid, wi)
                if (a.get("name") or "").lower().endswith(_TEXT_ATTACHMENT_EXTS)
            ]
        except Exception as e:
            logger.warning("deep_enrich: fallo en attachments de #%s: %s", wid, e)
            attachments = []

        if attachments:
            lines.append("### Adjuntos de texto")
            for a in attachments[:5]:
                name = a.get("name", "")
                lines.append(f"#### 📎 {name}")
                if include_attachment_content and a.get("url"):
                    content = self._download_attachment_content(a)
                    if content:
                        lines.append("```")
                        lines.append(content)
                        lines.append("```")
                    else:
                        lines.append("_(contenido no disponible)_")
                else:
                    lines.append("_(solo referencia, contenido no descargado)_")
                lines.append("")

        return "\n".join(lines)

    # ── Providers de datos: delegación al provider o fallback REST ──────

    def _get_work_item(self, wid: str) -> dict:
        # Primero: método "estándar" (si provider lo tiene)
        if hasattr(self._provider, "get_work_item"):
            try:
                return self._provider.get_work_item(wid) or {}
            except Exception as e:
                logger.debug("provider.get_work_item falló: %s", e)
        # Fallback: usar el helper interno existente
        if hasattr(self._provider, "_request") and hasattr(self._provider, "_base_proj"):
            api = getattr(self._provider, "_api", "7.1")
            url = f"{self._provider._base_proj}/_apis/wit/workitems/{wid}?$expand=all&api-version={api}"
            return self._provider._request("GET", url) or {}
        # Último recurso: fetch_ticket_detail (si existe) para al menos tener title/state/desc
        if hasattr(self._provider, "fetch_ticket_detail"):
            try:
                detail = self._provider.fetch_ticket_detail(str(wid))
                raw = getattr(detail.ticket, "raw", {}) or {}
                return raw
            except Exception as e:
                logger.debug("fetch_ticket_detail falló: %s", e)
        return {}

    def _get_comments(self, wid: str) -> list:
        if hasattr(self._provider, "get_comments"):
            try:
                return self._provider.get_comments(wid) or []
            except Exception as e:
                logger.debug("provider.get_comments falló: %s", e)
        if hasattr(self._provider, "_request") and hasattr(self._provider, "_base_proj"):
            url = (f"{self._provider._base_proj}/_apis/wit/workItems/{wid}/comments"
                   f"?api-version=7.1-preview.4&$top=200")
            try:
                data = self._provider._request("GET", url) or {}
                return data.get("comments", []) or []
            except Exception as e:
                logger.debug("REST comments falló: %s", e)
        return []

    def _get_related_work_items(self, wid: str, wi: dict | None = None) -> list:
        if hasattr(self._provider, "get_related_work_items"):
            try:
                return self._provider.get_related_work_items(wid) or []
            except Exception as e:
                logger.debug("provider.get_related_work_items falló: %s", e)

        if not wi:
            wi = self._get_work_item(wid)
        rels = (wi.get("relations") or []) if wi else []
        related_ids: list[str] = []
        for r in rels:
            rel_type = (r.get("rel") or "")
            if not rel_type or rel_type == "AttachedFile":
                continue
            url = r.get("url") or ""
            # Extraer id del final de la URL si apunta a un work item
            m = re.search(r"/workItems/(\d+)", url) or re.search(r"/workitems/(\d+)", url)
            if m:
                related_ids.append(m.group(1))

        if not related_ids:
            return []

        # Resolver en batch por REST si es posible
        if hasattr(self._provider, "_request") and hasattr(self._provider, "_base_proj"):
            api = getattr(self._provider, "_api", "7.1")
            ids_qs = ",".join(related_ids[:20])
            url = (f"{self._provider._base_proj}/_apis/wit/workitems"
                   f"?ids={ids_qs}&fields=System.Id,System.Title,System.State"
                   f"&api-version={api}")
            try:
                data = self._provider._request("GET", url) or {}
            except Exception as e:
                logger.debug("REST batch related falló: %s", e)
                return []
            out = []
            for rwi in data.get("value", []):
                f = rwi.get("fields") or {}
                out.append({
                    "id":    rwi.get("id"),
                    "title": f.get("System.Title", ""),
                    "state": f.get("System.State", ""),
                })
            return out

        return [{"id": rid, "title": "", "state": ""} for rid in related_ids]

    def _download_attachment_content(self, attachment: dict) -> str:
        """Download a text attachment and return its content (truncated to safety cap)."""
        url = attachment.get("url") or ""
        if not url:
            return ""
        size = int(attachment.get("size") or 0)
        if size > _MAX_ATTACHMENT_BYTES:
            logger.debug("Attachment %s too large (%d bytes), skipping", attachment.get("name"), size)
            return f"(archivo demasiado grande: {size} bytes, límite: {_MAX_ATTACHMENT_BYTES})"

        # Try provider._request first (reuses auth)
        if hasattr(self._provider, "_request"):
            try:
                import requests as _requests
                session = getattr(self._provider, "_session", None)
                auth = getattr(self._provider, "_auth", None)
                if session:
                    resp = session.get(url, timeout=15)
                elif auth:
                    resp = _requests.get(url, auth=auth, timeout=15)
                else:
                    resp = self._provider._request("GET", url)
                    if isinstance(resp, (str, bytes)):
                        text = resp if isinstance(resp, str) else resp.decode("utf-8", errors="replace")
                        return text[:_MAX_ATTACHMENT_BYTES]
                    return ""
                resp.raise_for_status()
                text = resp.text[:_MAX_ATTACHMENT_BYTES]
                return text
            except Exception as e:
                logger.debug("_download_attachment_content falló: %s", e)
                return ""

        return ""

    def _get_attachments(self, wid: str, wi: dict | None = None) -> list:
        if hasattr(self._provider, "get_attachments"):
            try:
                return self._provider.get_attachments(wid) or []
            except Exception as e:
                logger.debug("provider.get_attachments falló: %s", e)
        if not wi:
            wi = self._get_work_item(wid)
        rels = (wi.get("relations") or []) if wi else []
        out = []
        for r in rels:
            if r.get("rel") != "AttachedFile":
                continue
            attrs = r.get("attributes") or {}
            out.append({
                "id":   str(attrs.get("id") or ""),
                "name": str(attrs.get("name") or ""),
                "url":  str(r.get("url") or ""),
                "size": int(attrs.get("resourceSize") or 0),
            })
        return out

    # ── Helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _coerce_id(value) -> str:
        if value is None:
            return ""
        if isinstance(value, bool):
            return ""
        try:
            s = str(value).strip()
        except Exception:
            return ""
        if not s:
            return ""
        # Aceptar "INC-123", "#123", "123"
        m = re.search(r"\d+", s)
        if not m:
            return ""
        return m.group(0)

    @staticmethod
    def _html_to_md(html_text: str) -> str:
        if not html_text:
            return ""
        s = str(html_text)
        # Listas y saltos de línea típicos antes de strippar
        s = re.sub(r"(?i)<\s*br\s*/?>", "\n", s)
        s = re.sub(r"(?i)</\s*(p|div|li|tr|h[1-6])\s*>", "\n", s)
        s = re.sub(r"(?i)<\s*li[^>]*>", "- ", s)
        # Strip tags
        s = re.sub(r"<[^>]+>", "", s)
        # Decode entidades
        s = _html_mod.unescape(s)
        # Entidades residuales por si acaso
        for raw, repl in (("&nbsp;", " "), ("&lt;", "<"), ("&gt;", ">"),
                         ("&amp;", "&"), ("&quot;", '"')):
            s = s.replace(raw, repl)
        # Colapsar espacios por línea, conservando saltos
        lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in s.splitlines()]
        # Colapsar múltiples líneas vacías consecutivas
        out_lines: list[str] = []
        empty = False
        for ln in lines:
            if not ln:
                if empty:
                    continue
                empty = True
            else:
                empty = False
            out_lines.append(ln)
        return "\n".join(out_lines).strip()
