"""
services/gitlab_provider.py -- Adapter GitLabTrackerProvider (Plan 65 F3..F9).

Implementa el puerto TrackerProvider usando la API v4 de GitLab vía GitLabClient.

Fases implementadas:
  F3 — CRUD básico de issues (fetch, get, create, states, update_state)
  F4 — Comentarios (post, fetch, fetch_all, comment_exists)
  F5 — Attachments (upload, link, fetch)
  F6 — Identity/assignees (_resolve_assignee_id, update_item_assignee)
  F7 — Jerarquía épica + fallback (native epics vs issue-links)
  F8 — Updates/edit-learning (fetch_item_updates)
  F9 — Pipeline CI (fetch_pipelines)
  Plan 73 F4 — RepoWriter: commit_file + _detect_commit_action (sub-puerto separado de CIProvider).
"""
from __future__ import annotations

import base64
import re
import urllib.parse
from typing import Optional

from services.tracker_provider import TrackerItem, TrackerQuery, TrackerApiError, TrackerConfigError
from services.gitlab_client import GitLabClient  # importado a nivel módulo para poder parchear en tests
import config  # importado a nivel módulo para poder parchear en tests


class GitLabTrackerProvider:
    """Adapter de la API GitLab v4 al puerto TrackerProvider."""

    name = "gitlab"

    def __init__(self, project: Optional[str] = None):
        base_url = getattr(config, "GITLAB_URL", "") or ""
        proj = project or getattr(config, "GITLAB_PROJECT", "") or ""
        self._client = GitLabClient(base_url=base_url, project=proj)
        self._project = proj
        self._group = getattr(config, "STACKY_GITLAB_GROUP", "") or ""
        self._epics_native = getattr(config, "STACKY_GITLAB_EPICS_NATIVE", False)

    # ── Helpers internos ──────────────────────────────────────────────────────

    def _type_label(self, item_type: str) -> str:
        return f"type::{item_type}"

    def _query_to_gitlab_params(self, q: TrackerQuery) -> dict:
        params: dict = {}
        if q.state == "open":
            params["state"] = "opened"
        elif q.state == "closed":
            params["state"] = "closed"
        if q.labels:
            params["labels"] = ",".join(q.labels)
        if q.milestone:
            params["milestone"] = q.milestone
        if q.assignee:
            params["assignee_username"] = q.assignee
        if q.search:
            params["search"] = q.search
        return params

    def _normalize_issue(self, body: dict) -> dict:
        assignees = body.get("assignees") or []
        assignee_names = [a.get("username") for a in assignees if a.get("username")]
        labels = body.get("labels") or []
        # parent: si tiene epic_iid (GitLab Premium) o _link_parent_id inyectado
        parent = body.get("epic", {}) or {}
        parent_id = str(parent.get("iid") or parent.get("id") or "") or None
        return {
            "id": str(body.get("id") or ""),
            "iid": str(body.get("iid") or ""),
            "title": body.get("title") or "",
            "description": body.get("description") or "",
            "state": body.get("state") or "",
            "labels": labels,
            "assignees": assignee_names,
            "web_url": body.get("web_url") or "",
            "updated_at": body.get("updated_at") or "",
            "parent": parent_id,
        }

    def _state_map_for_gitlab(self) -> dict:
        """Mapa lógico → acción GitLab. Cada valor: {label, close}."""
        # Default razonable sin proyecto específico; puede sobreescribirse por profile.
        return {
            "functional": {"label": "stacky::functional", "closed": False},
            "accepted": {"label": "stacky::accepted", "closed": True},
            "rejected": {"label": "stacky::rejected", "closed": True},
            "in_progress": {"label": "stacky::in_progress", "closed": False},
        }

    def _resolve_assignee_id(self, username: str) -> Optional[int]:
        """Resuelve un username GitLab a su user_id numérico (F6)."""
        try:
            body, _ = self._client._request("GET", "/users", params={"username": username})
            if isinstance(body, list) and body:
                return body[0].get("id")
        except Exception:
            pass
        return None

    def _link_parent(self, child_iid: str, parent_id: str) -> None:
        """Establece la relación padre-hijo (F7): epics nativos o issue-links."""
        proj_path = self._client._project_path()
        if self._epics_native and self._group:
            # Modo: Group Epics nativos (requiere licencia Premium/Ultimate)
            try:
                self._client._request(
                    "POST",
                    f"/groups/{self._group}/epics/{parent_id}/issues",
                    json_body={"issue_id": child_iid},
                )
                return
            except TrackerApiError as e:
                if e.status == 403:
                    # Degradar a issue-links (sin licencia)
                    pass
                else:
                    raise
        # Fallback: issue-links (siempre disponible)
        try:
            self._client._request(
                "POST",
                f"/projects/{proj_path}/issues/{child_iid}/links",
                json_body={"target_project_id": self._project, "target_issue_iid": parent_id},
            )
        except Exception:
            pass  # silencioso — no bloquear la creación del issue

    def _render_note(self, body_html: str) -> str:
        """Convierte HTML a texto de nota GitLab (preserva el marker)."""
        # GitLab acepta markdown en notas; devolvemos el HTML como está
        # (la API lo almacena y muestra como texto/markdown)
        return body_html

    # ── F3: CRUD básico ───────────────────────────────────────────────────────

    def credentials_present(self) -> bool:
        try:
            return bool(self._client._token)
        except Exception:
            return False

    def get_authenticated_user(self) -> dict:
        body, _ = self._client._request("GET", "/user")
        return {
            "id": str(body.get("id") or ""),
            "username": body.get("username") or "",
            "name": body.get("name") or "",
            "email": body.get("email") or "",
        }

    def fetch_open_items(self, query: TrackerQuery) -> list[dict]:
        proj_path = self._client._project_path()
        params = self._query_to_gitlab_params(query)
        items = self._client._request_paginated(
            f"/projects/{proj_path}/issues",
            params=params,
        )
        return [self._normalize_issue(i) for i in items]

    def get_item(self, item_id: str) -> dict:
        proj_path = self._client._project_path()
        body, _ = self._client._request("GET", f"/projects/{proj_path}/issues/{item_id}")
        return self._normalize_issue(body)

    def item_url(self, item_id: str) -> "str | None":
        """URL de issue GitLab. Devuelve None si STACKY_GITLAB_DEEP_LINKS_ENABLED=False.

        Plan 75 F2: reescrito para usar compose_issue_url (corrige gap de encoding para
        sub-groups) y gateado por el flag. _project_path() devuelve el path ya URL-encoded;
        compose_issue_url lo usa directamente sin re-encodear (C3).
        """
        if not getattr(config.config, "STACKY_GITLAB_DEEP_LINKS_ENABLED", False):
            return None
        from services.gitlab_deep_links import compose_issue_url
        return compose_issue_url(self._client._base_url, self._client._project_path(), item_id)

    def mr_url(self, mr_iid: str) -> "str | None":
        """URL de merge request GitLab. Devuelve None si STACKY_GITLAB_DEEP_LINKS_ENABLED=False.

        Plan 75 F2 — método NUEVO del provider GitLab (no del puerto TrackerProvider).
        """
        if not getattr(config.config, "STACKY_GITLAB_DEEP_LINKS_ENABLED", False):
            return None
        from services.gitlab_deep_links import compose_mr_url
        return compose_mr_url(self._client._base_url, self._client._project_path(), mr_iid)

    def commit_url(self, sha: str) -> "str | None":
        """URL de commit GitLab. Devuelve None si STACKY_GITLAB_DEEP_LINKS_ENABLED=False.

        Plan 75 F2 — método NUEVO del provider GitLab (no del puerto TrackerProvider).
        """
        if not getattr(config.config, "STACKY_GITLAB_DEEP_LINKS_ENABLED", False):
            return None
        from services.gitlab_deep_links import compose_commit_url
        return compose_commit_url(self._client._base_url, self._client._project_path(), sha)

    def epic_url(self, epic_iid: str) -> "str | None":
        """URL de épica GitLab (Premium). Devuelve None si STACKY_GITLAB_DEEP_LINKS_ENABLED=False.

        Plan 75 F2 — método NUEVO del provider GitLab (no del puerto TrackerProvider).
        Requiere _group configurado; levanta TrackerConfigError si Free sin _group.
        """
        if not getattr(config.config, "STACKY_GITLAB_DEEP_LINKS_ENABLED", False):
            return None
        from services.gitlab_deep_links import compose_epic_url
        if not self._group:
            raise TrackerConfigError("GitLab Free: epicas no nativas; usar fallback Free (F3)")
        return compose_epic_url(self._client._base_url, self._group, epic_iid)

    def fetch_states(self) -> list[str]:
        """Devuelve los estados lógicos disponibles (del state map)."""
        return list(self._state_map_for_gitlab().keys())

    def update_item_state(self, item_id: str, logical_state: str) -> dict:
        """Mapea logical_state → label GitLab + close si corresponde."""
        state_map = self._state_map_for_gitlab()
        proj_path = self._client._project_path()
        mapping = state_map.get(logical_state, {})

        update_body: dict = {}
        if mapping.get("label"):
            # Agregar label de estado; obtener labels actuales primero
            try:
                current, _ = self._client._request("GET", f"/projects/{proj_path}/issues/{item_id}")
                current_labels = list(current.get("labels") or [])
            except Exception:
                current_labels = []
            # Remover labels de estado previos (type:: y stacky::)
            filtered = [
                lbl for lbl in current_labels
                if not lbl.startswith("stacky::")
            ]
            filtered.append(mapping["label"])
            update_body["labels"] = ",".join(filtered)

        if mapping.get("closed"):
            update_body["state_event"] = "close"
        else:
            update_body["state_event"] = "reopen"

        body, _ = self._client._request(
            "PUT",
            f"/projects/{proj_path}/issues/{item_id}",
            json_body=update_body,
        )
        return self._normalize_issue(body)

    def create_item(self, item: TrackerItem) -> dict:
        proj_path = self._client._project_path()
        labels = list(item.labels) + [self._type_label(item.item_type)]
        create_body: dict = {
            "title": item.title,
            "description": item.description_html,
            "labels": ",".join(labels),
        }
        if item.assignee:
            assignee_id = self._resolve_assignee_id(item.assignee)
            if assignee_id:
                create_body["assignee_ids"] = [assignee_id]

        body, _ = self._client._request(
            "POST",
            f"/projects/{proj_path}/issues",
            json_body=create_body,
        )
        result = self._normalize_issue(body)

        # Enlazar con padre si se especificó (F7)
        if item.parent_id:
            self._link_parent(str(body.get("iid") or body.get("id") or ""), item.parent_id)

        return result

    # ── F4: Comentarios ───────────────────────────────────────────────────────

    def _fetch_notes_raw(self, item_id: str, exclude_system: bool = True) -> list[dict]:
        proj_path = self._client._project_path()
        notes = self._client._request_paginated(
            f"/projects/{proj_path}/issues/{item_id}/notes",
        )
        if exclude_system:
            notes = [n for n in notes if not n.get("system", False)]
        return notes

    def fetch_comments(self, item_id: str) -> list[dict]:
        """Devuelve comentarios no-system del issue (hasta page_cap páginas)."""
        return self._fetch_notes_raw(item_id, exclude_system=True)

    def fetch_all_comments(self, item_id: str) -> list[dict]:
        """Devuelve TODOS los comentarios no-system (hasta page_cap=40 páginas)."""
        return self._fetch_notes_raw(item_id, exclude_system=True)

    def post_comment(self, item_id: str, body_html: str) -> dict:
        proj_path = self._client._project_path()
        note_body = self._render_note(body_html)
        result, _ = self._client._request(
            "POST",
            f"/projects/{proj_path}/issues/{item_id}/notes",
            json_body={"body": note_body},
        )
        return result if isinstance(result, dict) else {}

    def comment_exists(self, item_id: str, marker: str) -> bool:
        comments = self.fetch_all_comments(item_id)
        return any(marker in (c.get("body") or "") for c in comments)

    # ── F5: Attachments ───────────────────────────────────────────────────────

    def upload_attachment(self, file_path: str, file_name: str) -> dict:
        """Sube un archivo a GitLab project uploads. Devuelve {markdown, url}."""
        proj_path = self._client._project_path()
        with open(file_path, "rb") as f:
            files = {"file": (file_name, f)}
            body, _ = self._client._request(
                "POST",
                f"/projects/{proj_path}/uploads",
                files=files,
            )
        return body if isinstance(body, dict) else {}

    def link_attachment(self, item_id: str, attachment: dict) -> dict:
        """Agrega el link markdown del attachment a la descripción del issue."""
        proj_path = self._client._project_path()
        # Obtener descripción actual
        try:
            current, _ = self._client._request("GET", f"/projects/{proj_path}/issues/{item_id}")
            description = current.get("description") or ""
        except Exception:
            description = ""
        markdown = attachment.get("markdown") or attachment.get("url") or ""
        new_description = description + f"\n\n{markdown}" if description else markdown
        body, _ = self._client._request(
            "PUT",
            f"/projects/{proj_path}/issues/{item_id}",
            json_body={"description": new_description},
        )
        return self._normalize_issue(body)

    def fetch_attachments(self, item_id: str) -> list[dict]:
        """Extrae links de upload desde la descripción del issue."""
        proj_path = self._client._project_path()
        try:
            body, _ = self._client._request("GET", f"/projects/{proj_path}/issues/{item_id}")
            description = body.get("description") or ""
        except Exception:
            return []
        # Regex: ![filename](/uploads/hash/filename)
        pattern = re.compile(r"!\[([^\]]*)\]\((/uploads/[^\)]+)\)")
        base = self._client._base_url
        proj = self._project
        results = []
        for m in pattern.finditer(description):
            name, path = m.group(1), m.group(2)
            results.append({"name": name, "url": f"{base}/{proj}{path}", "path": path})
        return results

    # ── F6: Identity/assignees ────────────────────────────────────────────────

    def update_item_assignee(self, item_id: str, assignee: str) -> dict:
        """Asigna el issue al username. Si no se encuentra, limpia assignees."""
        proj_path = self._client._project_path()
        assignee_id = self._resolve_assignee_id(assignee) if assignee else None
        update_body: dict = {}
        if assignee_id:
            update_body["assignee_ids"] = [assignee_id]
        else:
            update_body["assignee_ids"] = []
        body, _ = self._client._request(
            "PUT",
            f"/projects/{proj_path}/issues/{item_id}",
            json_body=update_body,
        )
        return self._normalize_issue(body)

    # ── F7: Jerarquía épica ───────────────────────────────────────────────────

    def find_child_by_marker(self, parent_id: str, marker: str) -> Optional[dict]:
        """Busca un issue hijo que contenga el marker en la descripción o un comentario."""
        proj_path = self._client._project_path()

        # Buscar en issues vinculados
        try:
            linked, _ = self._client._request(
                "GET", f"/projects/{proj_path}/issues/{parent_id}/links"
            )
            if isinstance(linked, list):
                for issue in linked:
                    desc = issue.get("description") or ""
                    if marker in desc:
                        return self._normalize_issue(issue)
        except Exception:
            pass

        # Buscar en comentarios del padre
        try:
            notes = self.fetch_all_comments(parent_id)
            for note in notes:
                body_text = note.get("body") or ""
                if marker in body_text:
                    # Retornar el issue del padre como proxy (marker encontrado en comentario)
                    return self.get_item(parent_id)
        except Exception:
            pass

        return None

    # ── F8: Updates/edit-learning ─────────────────────────────────────────────

    def fetch_item_updates(self, item_id: str, since: Optional[str] = None) -> list[dict]:
        """Combina resource_label_events + resource_state_events + notes y ordena por created_at."""
        proj_path = self._client._project_path()
        all_updates: list[dict] = []

        # Label events
        try:
            label_events = self._client._request_paginated(
                f"/projects/{proj_path}/issues/{item_id}/resource_label_events"
            )
            for ev in label_events:
                all_updates.append({
                    "kind": "label_event",
                    "created_at": ev.get("created_at") or "",
                    "label": ev.get("label") or {},
                    "action": ev.get("action") or "",
                    "user": (ev.get("user") or {}).get("username") or "",
                    "raw": ev,
                })
        except Exception:
            pass

        # State events
        try:
            state_events = self._client._request_paginated(
                f"/projects/{proj_path}/issues/{item_id}/resource_state_events"
            )
            for ev in state_events:
                all_updates.append({
                    "kind": "state_event",
                    "created_at": ev.get("created_at") or "",
                    "state": ev.get("state") or "",
                    "user": (ev.get("user") or {}).get("username") or "",
                    "raw": ev,
                })
        except Exception:
            pass

        # Notes (comments editados o relevantes)
        try:
            notes = self._fetch_notes_raw(item_id, exclude_system=False)
            for note in notes:
                if note.get("system"):
                    all_updates.append({
                        "kind": "system_note",
                        "created_at": note.get("created_at") or "",
                        "body": note.get("body") or "",
                        "user": (note.get("author") or {}).get("username") or "",
                        "raw": note,
                    })
        except Exception:
            pass

        # Ordenar por created_at
        all_updates.sort(key=lambda u: u.get("created_at") or "")

        # Filtrar por since
        if since:
            all_updates = [u for u in all_updates if u.get("created_at", "") >= since]

        return all_updates

    # ── F9: Pipeline CI ───────────────────────────────────────────────────────

    def fetch_pipelines(self, ref: Optional[str] = None) -> list[dict]:
        """Lista pipelines del proyecto GitLab (CI)."""
        proj_path = self._client._project_path()
        params: dict = {}
        if ref:
            params["ref"] = ref
        try:
            pipelines = self._client._request_paginated(
                f"/projects/{proj_path}/pipelines",
                params=params,
            )
            return [
                {
                    "id": str(p.get("id") or ""),
                    "status": p.get("status") or "",
                    "ref": p.get("ref") or "",
                    "sha": p.get("sha") or "",
                    "web_url": p.get("web_url") or "",
                    "created_at": p.get("created_at") or "",
                    "updated_at": p.get("updated_at") or "",
                }
                for p in pipelines
            ]
        except Exception:
            return []

    def infer_pipeline(self, ref: Optional[str] = None) -> list[dict]:
        """Infiere pipeline para GitLab: usa CI real cuando hay pipelines,
        cae a fallback LLM genérico cuando CI está vacío o deshabilitado.

        Cada ítem devuelto tiene al menos:
          - "source": "ci" | "llm"
          - "status": str
          - "ref": str
        """
        ci_pipelines = self.fetch_pipelines(ref=ref)
        if ci_pipelines:
            return [{**p, "source": "ci"} for p in ci_pipelines]

        # Fallback: pipeline genérico derivado de LLM (sin llamada real al LLM
        # para no acoplar al provider con el motor de inferencia; el consumer
        # puede escalar a infer_pipeline de ado_pipeline_inference si necesita
        # más detalle).
        return [{"source": "llm", "status": "unknown", "ref": ref or ""}]

    # ── Plan 72 F1: trigger y poll ────────────────────────────────────────────

    def trigger_pipeline(self, ref: str) -> dict:
        """POST /projects/:id/pipeline — dispara pipeline sobre el ref. Requiere scope api.

        Contrato de _request (gitlab_client.py:107):
          - Devuelve (body, response_headers).
          - YA lanza TrackerApiError(status, msg, kind=...) ante no-2xx (L153-159).
          - NUNCA comparar el 2º valor a un status (C1').
        Si GitLab responde 403, TrackerApiError se propaga al caller (endpoint la mapea a 403).
        """
        proj_path = self._client._project_path()
        body, _ = self._client._request(
            "POST",
            f"/projects/{proj_path}/pipeline",
            json_body={"ref": ref},
        )
        return {
            "id": str(body.get("id") or ""),
            "status": body.get("status") or "",
            "ref": body.get("ref") or ref,
            "sha": body.get("sha") or "",
            "web_url": body.get("web_url") or "",
        }

    def poll_pipeline(self, pipeline_id: str) -> dict:
        """GET /projects/:id/pipelines/:pipeline_id — estado actual del pipeline."""
        proj_path = self._client._project_path()
        body, _ = self._client._request(
            "GET",
            f"/projects/{proj_path}/pipelines/{pipeline_id}",
        )
        return {
            "id": str(body.get("id") or ""),
            "status": body.get("status") or "",
            "ref": body.get("ref") or "",
            "sha": body.get("sha") or "",
            "web_url": body.get("web_url") or "",
        }

    # ── Plan 73 F4 — RepoWriter (sub-puerto separado de CIProvider) ─────────────

    def _decode_file_content(self, body: dict) -> str:
        """Decodifica el contenido base64 que devuelve la API de archivos de GitLab."""
        raw = body.get("content") or ""
        try:
            return base64.b64decode(raw).decode("utf-8", errors="replace")
        except Exception:
            return raw

    def _detect_commit_action(self, path: str, branch: str) -> tuple[str, str | None]:
        """Devuelve ("create", None) si el archivo no existe; ("update", contenido_actual) si existe.
        GET /projects/:id/repository/files/:path?ref=branch.
        Captura TrackerApiError(404) → create. Propaga cualquier otro error (C1).
        """
        from services.tracker_provider import TrackerApiError  # lazy import — patrón del repo
        proj_path = self._client._project_path()
        encoded_path = urllib.parse.quote(path, safe="")
        try:
            body, _ = self._client._request(
                "GET",
                f"/projects/{proj_path}/repository/files/{encoded_path}",
                params={"ref": branch},
            )
            return "update", self._decode_file_content(body)
        except TrackerApiError as e:
            if e.status == 404:
                return "create", None
            raise

    def commit_file(self, path: str, content: str, branch: str, message: str) -> dict:
        """POST /projects/:id/repository/commits — crea/actualiza archivo en 1 commit.
        FIX C1: body, _ = _request(...); NO compara status; TrackerApiError ya se lanza y propaga.
        FIX C7: si el contenido es idéntico al actual, NO commitea (retorna status 'unchanged').
        """
        proj_path = self._client._project_path()
        action, current = self._detect_commit_action(path, branch)
        if action == "update" and current == content:
            return {
                "sha": "",
                "branch": branch,
                "path": path,
                "web_url": "",
                "status": "unchanged",
            }
        body, _ = self._client._request(
            "POST",
            f"/projects/{proj_path}/repository/commits",
            json_body={
                "branch": branch,
                "commit_message": message,
                "actions": [{"action": action, "file_path": path, "content": content}],
            },
        )
        return {
            "sha": str(body.get("id") or ""),
            "branch": branch,
            "path": path,
            "web_url": body.get("web_url", ""),
            "status": action,
        }
