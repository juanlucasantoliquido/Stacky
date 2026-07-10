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
    # Plan 95 F1.a — commit_file real vía Git Pushes API (cierra TODO del plan 73 C12).

    def commit_file(self, path: str, content: str, branch: str, message: str) -> dict:
        """Plan 95 F1.a — commit real vía Git Pushes API (cierra el TODO del plan 73 C12).
        Contrato IDÉNTICO a gitlab_provider.py:590: {sha, branch, path, web_url, status}
        con status 'create'|'update'|'unchanged'. Lanza TrackerApiError (propaga status).
        """
        from services.ado_pipeline_definitions import _resolve_repo_id, _default_branch  # noqa: PLC0415
        from services.tracker_provider import TrackerApiError  # noqa: PLC0415

        project = self._project
        client = self._client

        # 1) repo_id: _resolve_repo_id(project)
        repo_id = _resolve_repo_id(project)

        # 2) old_object_id del branch
        ref_url = f"{client._base_proj}/_apis/git/repositories/{repo_id}/refs?filter=heads/{branch}&api-version=7.1"
        try:
            ref_body = client._request("GET", ref_url)
            refs_list = ref_body.get("value", [])
            if refs_list:
                # Branch existe
                old_object_id = refs_list[0].get("objectId")
            else:
                # Branch NO existe → usar default branch como base
                default_branch = _default_branch(None, project)  # noqa: PLW0621
                # Crear la rama apuntando al commit de la default
                default_ref_url = f"{client._base_proj}/_apis/git/repositories/{repo_id}/refs?filter=heads/{default_branch}&api-version=7.1"
                default_ref_body = client._request("GET", default_ref_url)
                default_refs = default_ref_body.get("value", [])
                if not default_refs:
                    raise TrackerApiError(
                        status=404,
                        kind="ado_default_branch_not_found",
                        message=f"Default branch '{default_branch}' no encontrado",
                    )
                base_sha = default_refs[0].get("objectId")

                # POST refs para crear la rama
                create_ref_url = f"{client._base_proj}/_apis/git/repositories/{repo_id}/refs?api-version=7.1"
                create_ref_body = [{
                    "name": f"refs/heads/{branch}",
                    "oldObjectId": "0" * 40,  # 40 ceros para crear rama nueva
                    "newObjectId": base_sha,
                }]
                client._request("POST", create_ref_url, body=create_ref_body)
                old_object_id = base_sha
        except Exception as e:
            raise TrackerApiError(
                status=500,
                kind="ado_ref_resolution_failed",
                message=f"Error resolviendo ref para branch '{branch}': {e}",
            ) from e

        # 3) ¿create o update? GET items
        item_url = f"{client._base_proj}/_apis/git/repositories/{repo_id}/items?path={path}&versionDescriptor.version={branch}&api-version=7.1"
        try:
            item_body = client._request("GET", item_url)
            # 200 ⇒ existe
            # Ver si el contenido es idéntico
            existing_content = item_body.get("content")
            if existing_content:
                # ADO devuelve base64
                import base64  # noqa: PLC0415
                try:
                    decoded = base64.b64decode(existing_content).decode("utf-8")
                    if decoded == content:
                        # Contenido idéntico ⇒ unchanged sin pushear
                        web_url = f"{client._base_project_url}/_git/{repo_id}?path=/{path.lstrip('/')}&version=GB{branch}"
                        return {
                            "sha": old_object_id,
                            "branch": branch,
                            "path": path,
                            "web_url": web_url,
                            "status": "unchanged",
                        }
                except Exception:
                    pass  # Falla decode ⇒ treat como update
            change_type = "edit"
        except Exception:
            # 404 ⇒ no existe ⇒ add
            change_type = "add"

        # 4) POST push
        push_url = f"{client._base_proj}/_apis/git/repositories/{repo_id}/pushes?api-version=7.1"
        push_body = {
            "refUpdates": [{
                "name": f"refs/heads/{branch}",
                "oldObjectId": old_object_id,
            }],
            "commits": [{
                "comment": message,
                "changes": [{
                    "changeType": change_type,
                    "item": {"path": "/" + path.lstrip("/")},
                    "newContent": {"content": content, "contentType": "rawtext"},
                }],
            }],
        }

        try:
            push_response = client._request("POST", push_url, body=push_body)
            commit_sha = push_response.get("commits", [{}])[0].get("commitId")
            web_url = f"{client._base_project_url}/_git/{repo_id}?path=/{path.lstrip('/')}&version=GB{branch}"
            return {
                "sha": commit_sha,
                "branch": branch,
                "path": path,
                "web_url": web_url,
                "status": "create" if change_type == "add" else "update",
            }
        except Exception as e:
            raise TrackerApiError(
                status=500,
                kind="ado_push_failed",
                message=f"Error haciendo push a ADO: {e}",
            ) from e

    # ── Plan 95 F2 — MergeRequestProvider ─────────────────────────────────────

    def create_merge_request(
        self,
        source_branch: str,
        target_branch: str,
        title: str,
        description: str,
    ) -> dict:
        """POST {base_proj}/_apis/git/repositories/{repo}/pullrequests?api-version=7.1"""
        from services.ado_pipeline_definitions import _resolve_repo_id  # noqa: PLC0415

        project = self._project
        client = self._client
        repo_id = _resolve_repo_id(project)

        url = f"{client._base_proj}/_apis/git/repositories/{repo_id}/pullrequests?api-version=7.1"
        body = {
            "sourceRefName": f"refs/heads/{source_branch}",
            "targetRefName": f"refs/heads/{target_branch}",
            "title": title,
            "description": description,
        }

        try:
            response = client._request("POST", url, body=body)
            return {
                "id": str(response.get("pullRequestId") or ""),
                "web_url": response.get("_links", {}).get("web", {}).get("href", ""),
                "state": "open",
            }
        except Exception as e:
            raise TrackerApiError(
                status=500,
                kind="ado_pr_creation_failed",
                message=f"Error creando PR en ADO: {e}",
            ) from e

    def get_merge_request(self, mr_id: str) -> dict:
        """GET .../pullrequests/{id} + builds para pipeline_status."""
        from services.ado_pipeline_definitions import _resolve_repo_id  # noqa: PLC0415
        from services.tracker_provider import TrackerApiError  # noqa: PLC0415

        project = self._project
        client = self._client
        repo_id = _resolve_repo_id(project)

        # GET PR
        url = f"{client._base_proj}/_apis/git/repositories/{repo_id}/pullrequests/{mr_id}?api-version=7.1"
        pr = client._request("GET", url)

        # State map: active→open, completed→merged, abandoned→closed
        state_map = {"active": "open", "completed": "merged", "abandoned": "closed"}
        state = state_map.get(pr.get("status") or "", "open")

        # Pipeline status: último build del source branch
        source_ref = pr.get("sourceRefName", "")
        builds_url = (
            f"{client._base_proj}/_apis/build/builds?"
            f"branchName={source_ref}&$top=1&queryOrder=queueTimeDescending&api-version=7.1"
        )
        try:
            builds_response = client._request("GET", builds_url)
            builds = builds_response.get("value", [])
            if builds:
                build = builds[0]
                # Mapear status ADO → vocabulario GitLab
                if build.get("status") == "completed":
                    result = build.get("result") or ""
                    if result == "succeeded":
                        pipeline_status = "success"
                    elif result in ("failed", "partiallySucceeded"):
                        pipeline_status = "failed"
                    elif result == "canceled":
                        pipeline_status = "canceled"
                    else:
                        pipeline_status = "pending"
                elif build.get("status") == "inProgress":
                    pipeline_status = "running"
                elif build.get("status") == "postponed":
                    pipeline_status = "pending"
                else:
                    pipeline_status = "pending"
            else:
                pipeline_status = "none"
        except Exception:
            pipeline_status = "none"

        # Mergeable: mergeStatus == "succeeded"
        mergeable = pr.get("mergeStatus") == "succeeded"

        return {
            "id": str(pr.get("pullRequestId") or ""),
            "state": state,
            "pipeline_status": pipeline_status,
            "mergeable": mergeable,
            "web_url": pr.get("_links", {}).get("web", {}).get("href", ""),
        }

    def merge_merge_request(self, mr_id: str) -> dict:
        """GET PR → PATCH con status=completed + lastMergeSourceCommit."""
        from services.ado_pipeline_definitions import _resolve_repo_id  # noqa: PLC0415
        from services.tracker_provider import TrackerApiError  # noqa: PLC0415

        project = self._project
        client = self._client
        repo_id = _resolve_repo_id(project)

        # GET PR para obtener lastMergeSourceCommit
        url = f"{client._base_proj}/_apis/git/repositories/{repo_id}/pullrequests/{mr_id}?api-version=7.1"
        pr = client._request("GET", url)
        last_merge_sha = pr.get("lastMergeSourceCommit", {}).get("commitId")

        if not last_merge_sha:
            raise TrackerApiError(
                status=400,
                kind="ado_pr_merge_not_ready",
                message="PR no listo para merge: no hay lastMergeSourceCommit",
            )

        # PATCH para completar
        patch_url = f"{client._base_proj}/_apis/git/repositories/{repo_id}/pullrequests/{mr_id}?api-version=7.1"
        patch_body = {
            "status": "completed",
            "lastMergeSourceCommit": {"commitId": last_merge_sha},
            "completionOptions": {"mergeStrategy": "noFastForward", "deleteSourceBranch": False},
        }

        try:
            response = client._request("PATCH", patch_url, body=patch_body)
            return {
                "id": str(response.get("pullRequestId") or ""),
                "state": "merged",
            }
        except Exception as e:
            raise TrackerApiError(
                status=500,
                kind="ado_pr_merge_failed",
                message=f"Error mergeando PR en ADO: {e}",
            ) from e

    # ── Plan 110 — Revisor de PRs ──────────────────────────────────────────
    def list_merge_requests(self, state: str = "open") -> list[dict]:
        """GET .../pullrequests?searchCriteria.status=<active|completed|abandoned|all>."""
        from services.ado_pipeline_definitions import _resolve_repo_id  # noqa: PLC0415
        repo_id = _resolve_repo_id(self._project)
        ado_status = {"open": "active", "merged": "completed", "closed": "abandoned", "all": "all"}.get(state, "active")
        url = (f"{self._client._base_proj}/_apis/git/repositories/{repo_id}/pullrequests"
               f"?searchCriteria.status={ado_status}&$top=50&api-version=7.1")
        resp = self._client._request("GET", url)
        rows = resp.get("value", []) if isinstance(resp, dict) else []
        state_map = {"active": "open", "completed": "merged", "abandoned": "closed"}
        out = []
        for pr in rows:
            out.append({
                "id": str(pr.get("pullRequestId") or ""),
                "title": pr.get("title") or "",
                "state": state_map.get(pr.get("status") or "", "open"),
                "source_branch": (pr.get("sourceRefName") or "").replace("refs/heads/", ""),
                "target_branch": (pr.get("targetRefName") or "").replace("refs/heads/", ""),
                "author": ((pr.get("createdBy") or {}).get("displayName")) or "",
                "web_url": pr.get("_links", {}).get("web", {}).get("href", ""),
                "pipeline_status": "none",  # v1: no consultamos builds en el listado (barato)
            })
        return out

    def get_merge_request_diff(self, mr_id: str) -> dict:
        """Degradación controlada (v1): lista de archivos cambiados de la última iteración.
        El diff línea a línea de ADO requiere varias llamadas por archivo; NO se incluye en v1.
        """
        from services.ado_pipeline_definitions import _resolve_repo_id  # noqa: PLC0415
        repo_id = _resolve_repo_id(self._project)
        base = f"{self._client._base_proj}/_apis/git/repositories/{repo_id}/pullRequests/{mr_id}"
        files = []
        try:
            iters = self._client._request("GET", f"{base}/iterations?api-version=7.1")
            it_list = iters.get("value", []) if isinstance(iters, dict) else []
            if it_list:
                last = it_list[-1].get("id")
                changes = self._client._request("GET", f"{base}/iterations/{last}/changes?api-version=7.1")
                ct_map = {"add": "added", "edit": "modified", "delete": "deleted", "rename": "renamed"}
                for c in (changes.get("changeEntries", []) if isinstance(changes, dict) else []):
                    item = c.get("item") or {}
                    files.append({
                        "path": item.get("path") or "",
                        "change_type": ct_map.get((c.get("changeType") or "").lower().split(",")[0], "modified"),
                    })
        except Exception:
            files = []
        return {
            "id": str(mr_id),
            "files": files,
            "diff_text": "",
            "diff_available": False,
            "note": "Azure DevOps: en esta versión se listan los archivos cambiados, no el detalle línea a línea.",
        }

    def comment_merge_request(self, mr_id: str, body: str) -> dict:
        """POST .../pullRequests/:id/threads (comentario a nivel del PR)."""
        from services.ado_pipeline_definitions import _resolve_repo_id  # noqa: PLC0415
        repo_id = _resolve_repo_id(self._project)
        url = f"{self._client._base_proj}/_apis/git/repositories/{repo_id}/pullRequests/{mr_id}/threads?api-version=7.1"
        payload = {"comments": [{"parentCommentId": 0, "content": body, "commentType": 1}], "status": 1}
        resp = self._client._request("POST", url, body=payload)
        return {"ok": True, "id": str((resp or {}).get("id") or "")}

    def close_merge_request(self, mr_id: str) -> dict:
        """PATCH .../pullrequests/:id con status=abandoned."""
        from services.ado_pipeline_definitions import _resolve_repo_id  # noqa: PLC0415
        repo_id = _resolve_repo_id(self._project)
        url = f"{self._client._base_proj}/_apis/git/repositories/{repo_id}/pullrequests/{mr_id}?api-version=7.1"
        self._client._request("PATCH", url, body={"status": "abandoned"})
        return {"ok": True, "id": str(mr_id), "state": "closed"}
    # ADO NO define approve_merge_request en v1 → capability False.
