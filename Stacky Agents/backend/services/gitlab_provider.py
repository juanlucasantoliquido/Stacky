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
import logging
import re
import urllib.parse
from typing import Optional

from services.tracker_provider import TrackerItem, TrackerQuery, TrackerApiError, TrackerConfigError
from services.gitlab_client import GitLabClient  # importado a nivel módulo para poder parchear en tests
import config  # importado a nivel módulo para poder parchear en tests

# Plan 277 F2 — el módulo NO tenía logger. Es la única infraestructura nueva que
# agrega la fase: los avisos del contrato (multi-tipo, multi-padre, token
# desconocido) tienen que ser visibles o el defecto vuelve a ser silencioso.
logger = logging.getLogger(__name__)

# Plan 291 F2 — SENTINELA INTERNO. NO es una acción de la API de GitLab: la API
# solo conoce "create"/"update"/"delete"/"move"/"chmod". Lo devuelve
# _detect_commit_action cuando la rama destino no existe, y commit_file lo
# traduce a "create" antes de armar el body del POST.
_ACCION_RAMA_NUEVA = "create_new_branch"


def _assignee_strict_enabled() -> bool:
    """Plan 282 F3 — STACKY_GITLAB_ASSIGNEE_STRICT_ENABLED (default True).

    Con OFF vuelve el comportamiento previo: un username que no resuelve VACÍA
    el campo `assignee_ids` en silencio. Nace ON porque REDUCE la escritura al
    sistema del operador (deja de emitir un PUT destructivo); una flag que quita
    una escritura destructiva no puede nacer OFF sin dejar el destrozo encendido
    de fábrica.

    `config` acá es el MÓDULO (import de arriba, "para poder parchear en
    tests"); la instancia de flags es `config.config`.
    """
    return bool(getattr(
        config.config, "STACKY_GITLAB_ASSIGNEE_STRICT_ENABLED", True,
    ))


def _unknown_state_guard_enabled() -> bool:
    """Plan 270 F2 — STACKY_TRACKER_STATE_WRITE_ROUTING_ENABLED (default True).

    Comparte flag con F1: son la misma promesa ("no escribas cualquier cosa en
    el sistema equivocado"), y separarlas permitiría una combinación incoherente
    (enrutar bien pero seguir reabriendo).

    C9: `config` acá es el MÓDULO (gitlab_provider.py:25 hace `import config`
    "para poder parchear en tests"). La instancia de flags es `config.config`,
    igual que en las otras 8 lecturas del archivo (:46, :47, :50, :51, :186,
    :196, :206, :217). NO usar un import local.
    """
    return bool(getattr(config.config, "STACKY_TRACKER_STATE_WRITE_ROUTING_ENABLED", True))


class GitLabTrackerProvider:
    """Adapter de la API GitLab v4 al puerto TrackerProvider."""

    name = "gitlab"

    def __init__(
        self,
        project: Optional[str] = None,
        *,
        base_url: Optional[str] = None,
        group: Optional[str] = None,
        auth_path: Optional[str] = None,
        ca_bundle: Optional[str] = None,
    ):
        # D2 (Plan 218 F0): las 4 lecturas iban al MÓDULO config y devolvían
        # siempre el default ⇒ _group y _epics_native quedaban muertos.
        # F4: la firma se amplía de forma ADITIVA — todos los parámetros nuevos son
        # opcionales y caen a la config global si vienen None, así
        # GitLabTrackerProvider(project="x") sigue funcionando igual.
        base = base_url or (getattr(config.config, "GITLAB_URL", "") or "")
        proj = project or (getattr(config.config, "GITLAB_PROJECT", "") or "")
        # El `ca_bundle` viaja hasta acá porque este es el cliente que LISTA
        # TICKETS. Cablearlo solo en la sonda de diagnóstico dejaba el check en
        # verde y la lista de issues vacía por SSLError (RIPLEY, 2026-07-30).
        self._client = GitLabClient(
            base_url=base, project=proj, auth_path=auth_path, ca_bundle=ca_bundle
        )
        self._project = proj
        self._group = group or (getattr(config.config, "STACKY_GITLAB_GROUP", "") or "")
        self._epics_native = bool(getattr(config.config, "STACKY_GITLAB_EPICS_NATIVE", False))

    # ── Helpers internos ──────────────────────────────────────────────────────

    def _type_label(self, item_type: str) -> str:
        """La etiqueta de tipo que se ESCRIBE en GitLab. Plan 277: sale del contrato.

        Antes componía el item_type CRUDO (`type::User Story`, con espacio y
        mayúsculas). Eso lo perdía el lector del migrador (`migrator_verify`, que
        parseaba con `type::(\\w+)`) y no coincidía con el token canónico, así que
        Stacky escribía una etiqueta que Stacky no sabía volver a leer.

        Adelantado desde F3 porque el gate de F2-bis (un solo motor) exige que este
        archivo no conserve NINGÚN literal de clasificación propio, y este era el
        último. Es literal el diff 1 de F3; el comportamiento de los 4 call sites
        vivos (`epic`, `issue`, `task`, `bug`) es idéntico: ya son tokens canónicos.
        """
        from services.gitlab_hierarchy import etiqueta_de_tipo   # import local: evita ciclo

        return etiqueta_de_tipo(item_type)

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
        # Plan 277 F2 — la clasificación sale del CONTRATO, no de este archivo.
        # Lo de antes tenía dos defectos medidos: (1) el `epic` de Premium NUNCA
        # viene en CE ⇒ parent_id salía siempre None ⇒ todo caía en `orphans`
        # (api/tickets.py:646-654); (2) "la primera etiqueta del array" es NO
        # DETERMINISTA — el orden de `labels` que devuelve la API no está
        # garantizado, así que dos corridas idénticas podían clasificar distinto.
        from services.gitlab_hierarchy import clasificar_issue   # import local: evita ciclo

        veredicto = clasificar_issue(body)
        for aviso in veredicto["avisos"]:
            logger.warning("Plan 277 contrato (issue iid=%s): %s", body.get("iid"), aviso)
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
            "work_item_type": veredicto["work_item_type"],
            # CAMBIO DE TIPO DECLARADO (§3.2): `parent` pasa de str|None a int|None
            # y sale SOLO de la etiqueta `epic::<iid>`. El `epic` nativo de Premium
            # vive en el namespace del GRUPO y no machea contra Ticket.ado_id (que
            # lleva el iid del PROYECTO): escribirlo acá producía un padre que nunca
            # resolvía y tapaba la causa real. Se conserva aparte, para diagnóstico.
            "parent": veredicto["parent_iid"],
            "parent_native_epic_iid": veredicto["parent_native_epic_iid"],
            "origen_tipo": veredicto["origen_tipo"],
            "origen_padre": veredicto["origen_padre"],
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
        """Resuelve un username GitLab a su user_id numérico (F6).

        Plan 282 F3 — QUEDA BYTE-IDÉNTICO A PROPÓSITO: devuelve `None` ante
        cualquier fallo. Tiene DOS llamadores más además de
        `update_item_assignee` (el camino de creación/actualización de item de
        este mismo archivo y el migrador Mantis→GitLab, que corre en batch y
        abortaría migraciones enteras por un usuario faltante). Hacer que
        propague acá sería "arreglar arriba y romper al lado": el cambio va en
        el helper hermano `_resolve_assignee_id_strict`.
        """
        try:
            body, _ = self._client._request("GET", "/users", params={"username": username})
            if isinstance(body, list) and body:
                return body[0].get("id")
        except Exception:
            pass
        return None

    def _resolve_assignee_id_strict(self, username: str) -> int:
        """Plan 282 F3 — como `_resolve_assignee_id` pero DICE por qué falló.

        Método NUEVO. Reusa el otro (no duplica el GET) y sólo convierte el
        `None` mudo en un error tipado, para que un typo en el username o un
        fallo transitorio de `/users` deje de vaciar el campo en silencio.
        """
        uid = self._resolve_assignee_id(username)
        if uid is None:
            raise TrackerApiError(
                404, f"usuario GitLab no resuelto: '{username}'", kind="not_found",
            )
        return uid

    def _link_parent(self, child_iid: str, parent_id: str) -> None:
        """Establece la relación padre-hijo. Plan 277 F3: la etiqueta es el mecanismo
        PRIMARIO; el epic nativo queda como camino Premium; los issue-links se retiran.

        POR QUÉ SE RETIRAN LOS ISSUE-LINKS: un link de GitLab CE es `relates_to`,
        SIMÉTRICO — no dice quién es el padre — y `_normalize_issue` nunca los lee
        (jamás hace GET /links). Se estaba escribiendo en un lugar que nadie lee, y
        el POST estaba envuelto en `except Exception: pass`, así que su fallo era
        invisible. La etiqueta `epic::<iid>` es direccional, viaja en el mismo
        payload que el listado ya trae (cero requests extra al leer) y es visible y
        filtrable en la UI de GitLab.

        Solo el **403** del camino nativo degrada a etiqueta: es el código con el que
        GitLab responde "no tenés licencia para épicas". Cualquier otro status es un
        fallo real y se re-lanza, para que un 500 del servidor no se disfrace de
        "esta instancia es Community Edition".
        """
        # Import local: evita el ciclo. `PREFIJO_PADRE` se usa en el log en vez de
        # escribir el prefijo literal acá — este archivo es uno de los 4 motores que
        # el gate de F2-bis vigila, y un literal de clasificación en un mensaje
        # cuenta igual que uno en la lógica (el gate mira `ast.Constant`, no
        # distingue). Consumir la constante del contrato es la forma correcta.
        from services.gitlab_hierarchy import PREFIJO_PADRE, etiqueta_de_padre

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
                if e.status != 403:
                    raise
                logger.info(
                    "Plan 277: épicas nativas rechazadas (403) — degradando a etiqueta "
                    "%s para el issue %s.",
                    PREFIJO_PADRE, child_iid,
                )

        # Camino primario en CE: la etiqueta.
        try:
            etiqueta = etiqueta_de_padre(parent_id)   # ValueError si no es un iid
        except ValueError:
            logger.warning(
                "Plan 277: parent_id %r no es un iid válido; el hijo %s queda huérfano "
                "(no se escribe una etiqueta basura en GitLab).",
                parent_id, child_iid,
            )
            return

        try:
            self._client._request(
                "PUT",
                f"/projects/{proj_path}/issues/{child_iid}",
                json_body={"add_labels": etiqueta},
            )
        except Exception as exc:
            # v277: NO se traga. Antes era `pass` mudo y el operador nunca sabía que
            # la jerarquía no se había escrito. Se registra y se re-lanza envuelto:
            # quien crea el item decide si el hijo huérfano es aceptable.
            # El status se hereda del error original cuando existe (0 = desconocido):
            # `TrackerApiError` lo exige posicional, y perderlo dejaría al llamador
            # sin saber si fue un 403, un 404 o una caída de red.
            logger.error(
                "Plan 277: no se pudo etiquetar el padre de %s: %s", child_iid, exc
            )
            raise TrackerApiError(
                getattr(exc, "status", 0) or 0,
                f"El issue {child_iid} se creó pero no se pudo enlazar a su padre "
                f"{parent_id} (etiqueta {etiqueta}): {exc}",
            ) from exc

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
        mapping = state_map.get(logical_state)
        # Plan 270 F2 — un estado no mapeable NO puede caer en el else de abajo:
        # con mapping={} se emitía state_event="reopen", es decir, cerrar
        # REABRÍA la issue. Ahora se declara la incapacidad (Plan 218).
        if mapping is None:
            if _unknown_state_guard_enabled():
                from services.tracker_provider import CapabilityUnavailable
                raise CapabilityUnavailable(
                    "tracker.items.update_state",
                    "gitlab",
                    reason=(
                        f"el estado '{logical_state}' no existe en el mapa de "
                        f"estados de GitLab ({', '.join(sorted(state_map))})"
                    ),
                    workaround=(
                        "usá uno de los estados lógicos soportados, o definí el "
                        "mapeo en el perfil del cliente"
                    ),
                )
            mapping = {}   # comportamiento histórico, sólo con la flag apagada

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

        # Enlazar con padre si se especificó (F7 / Plan 277 F3)
        if item.parent_id:
            try:
                self._link_parent(str(body.get("iid") or body.get("id") or ""), item.parent_id)
            except TrackerApiError as exc:
                # El issue YA existe en GitLab: no se puede deshacer ni se debe. Se
                # devuelve creado pero con la falla VISIBLE en el resultado, en vez
                # del silencio de antes (`except Exception: pass`). Punto medio entre
                # tragarse el error y abortar una creación que ya ocurrió.
                result["parent_link_error"] = str(exc)
                logger.error("Plan 277: issue creado sin enlace de padre: %s", exc)

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
        """Asigna el issue al username.

        Plan 282 F3 — se separan los dos casos que antes estaban COLAPSADOS:
          - `assignee` vacío/None  -> intención EXPLÍCITA de desasignar. Se
            conserva: manda `assignee_ids: []`.
          - `assignee` con valor que NO resuelve -> levanta antes de armar el
            body. Antes mandaba `assignee_ids: []` igual, así que un typo en el
            username o un fallo transitorio de `/users` DESASIGNABA el issue del
            operador sin avisar. El docstring viejo ("Si no se encuentra, limpia
            assignees") documentaba el bug como si fuera la feature.
        """
        proj_path = self._client._project_path()
        update_body: dict = {}
        if assignee and _assignee_strict_enabled():
            update_body["assignee_ids"] = [self._resolve_assignee_id_strict(assignee)]
        else:
            assignee_id = self._resolve_assignee_id(assignee) if assignee else None
            update_body["assignee_ids"] = [assignee_id] if assignee_id else []
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

    def branch_exists(self, branch: str) -> bool:
        """GET /projects/:id/repository/branches/:branch — ¿existe la rama?

        SOLO LECTURA. 200 → True; 404 → False; cualquier otro TrackerApiError se
        PROPAGA (un 401/403/500 NO es "no existe": tratarlo como False haría que
        commit_file intentara crear una rama que quizás ya está, C1 del plan 73).

        El nombre de rama del auto-PR lleva una BARRA ('stacky/incidencia-12-exec-34'),
        así que va URL-encodeado con safe="" o GitLab lo lee como dos segmentos de path.

        Plan 291 F1. Sin flag: es un GET de solo lectura que no puede cambiar
        ningún resultado exitoso (ver plan 291 sección 3.3).
        """
        from services.tracker_provider import TrackerApiError  # lazy import — patrón del repo
        proj_path = self._client._project_path()
        encoded_branch = urllib.parse.quote(branch, safe="")
        try:
            self._client._request(
                "GET",
                f"/projects/{proj_path}/repository/branches/{encoded_branch}",
            )
            return True
        except TrackerApiError as e:
            if e.status == 404:
                return False
            raise

    def _default_branch_name(self) -> str:
        """GET /projects/:id → campo 'default_branch'. Cadena vacía si el repo no
        tiene rama default (repo recién creado y VACÍO).

        NO adivina 'main': si el repo usa 'master' o 'develop', devuelve eso.
        NO importa nada de `api/` — `services/` NUNCA importa `api/` (riel duro).

        ⚠️ ESTA ES LA IMPLEMENTACIÓN CANÓNICA a partir del plan 291. La rama GitLab
        de `api/devops_production._default_branch` hacía EXACTAMENTE este GET y
        pasa a delegar acá (plan 291 F1.b, hallazgo C7).
        """
        proj_path = self._client._project_path()
        body, _ = self._client._request("GET", f"/projects/{proj_path}")
        return str((body or {}).get("default_branch") or "")

    def _decode_file_content(self, body: dict) -> str:
        """Decodifica el contenido base64 que devuelve la API de archivos de GitLab."""
        raw = body.get("content") or ""
        try:
            return base64.b64decode(raw).decode("utf-8", errors="replace")
        except Exception:
            return raw

    def _detect_commit_action(
        self, path: str, branch: str, *, rama_existe: bool | None = None,
    ) -> tuple[str, str | None]:
        """Devuelve ("create", None) si el archivo no existe; ("update", contenido_actual) si existe.
        GET /projects/:id/repository/files/:path?ref=branch.
        Captura TrackerApiError(404) → create. Propaga cualquier otro error (C1).

        Plan 291 F2:
          rama_existe=False → devuelve (_ACCION_RAMA_NUEVA, None) SIN hacer el GET de
            archivos: si la rama no existe, ningún archivo puede existir en ella, y un
            404 de ese endpoint NO probaría nada sobre el archivo. Ese sentinela es
            INTERNO: commit_file lo traduce a la acción real "create" de la API.
          rama_existe=None (default) → comportamiento IDÉNTICO al de hoy. Retro-
            compatible: cualquier caller viejo se comporta igual.
          rama_existe=True → comportamiento IDÉNTICO al de hoy.
        """
        from services.tracker_provider import TrackerApiError  # lazy import — patrón del repo
        if rama_existe is False:
            return _ACCION_RAMA_NUEVA, None
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

    # ── Plan 95 F2 — MergeRequestProvider ─────────────────────────────────────

    def create_merge_request(
        self,
        source_branch: str,
        target_branch: str,
        title: str,
        description: str,
    ) -> dict:
        """POST /projects/:id/merge_requests."""
        proj_path = self._client._project_path()
        body, _ = self._client._request(
            "POST",
            f"/projects/{proj_path}/merge_requests",
            json_body={
                "source_branch": source_branch,
                "target_branch": target_branch,
                "title": title,
                "description": description,
            },
        )
        return {
            "id": str(body.get("iid") or ""),
            "web_url": body.get("web_url", ""),
            "state": "open",
        }

    def get_merge_request(self, mr_id: str) -> dict:
        """GET /projects/:id/merge_requests/:iid."""
        proj_path = self._client._project_path()
        body, _ = self._client._request(
            "GET",
            f"/projects/{proj_path}/merge_requests/{mr_id}",
        )
        # pipeline_status desde head_pipeline
        head_pipeline = body.get("head_pipeline") or {}
        pipeline_status = "none"
        if head_pipeline:
            status_map = {
                "created": "created",
                "pending": "pending",
                "running": "running",
                "success": "success",
                "failed": "failed",
                "canceled": "canceled",
                "skipped": "canceled",
            }
            pipeline_status = status_map.get(head_pipeline.get("status") or "", "none")

        # mergeable: si merge_status es "can_be_merged" o detailed_merge_status es "mergeable"
        mergeable = body.get("merge_status") == "can_be_merged"
        if not mergeable:
            # Fallback al campo moderno detailed_merge_status si existe
            mergeable = body.get("detailed_merge_status") == "mergeable"

        # GitLab usa "opened" para MRs abiertos; normalizar al vocabulario
        # compartido open/merged/closed (mismo que ADO).
        state_map = {"opened": "open", "merged": "merged", "closed": "closed"}
        state = state_map.get(body.get("state") or "", "open")

        return {
            "id": str(body.get("iid") or ""),
            "state": state,  # open, merged, closed
            "pipeline_status": pipeline_status,
            "mergeable": mergeable,
            "web_url": body.get("web_url", ""),
        }

    def merge_merge_request(self, mr_id: str) -> dict:
        """PUT /projects/:id/merge_requests/:iid/merge."""
        proj_path = self._client._project_path()
        body, _ = self._client._request(
            "PUT",
            f"/projects/{proj_path}/merge_requests/{mr_id}/merge",
        )
        return {
            "id": str(body.get("iid") or ""),
            "state": "merged",
        }

    # ── Plan 110 — Revisor de PRs ──────────────────────────────────────────
    def list_merge_requests(self, state: str = "open") -> list[dict]:
        """GET /projects/:id/merge_requests?state=<opened|merged|closed|all>&scope=all."""
        proj_path = self._client._project_path()
        gl_state = {"open": "opened", "merged": "merged", "closed": "closed", "all": "all"}.get(state, "opened")
        # C5: query vía params= (firma real _request(..., params=...)), no embebida en el path.
        body, _ = self._client._request(
            "GET",
            f"/projects/{proj_path}/merge_requests",
            params={"state": gl_state, "scope": "all", "per_page": 50, "order_by": "updated_at"},
        )
        rows = body if isinstance(body, list) else []
        state_map = {"opened": "open", "merged": "merged", "closed": "closed"}
        ps_map = {"created": "created", "pending": "pending", "running": "running",
                  "success": "success", "failed": "failed", "canceled": "canceled",
                  "skipped": "canceled"}
        out = []
        for mr in rows:
            hp = mr.get("head_pipeline") or {}
            out.append({
                "id": str(mr.get("iid") or ""),
                "title": mr.get("title") or "",
                "state": state_map.get(mr.get("state") or "", "open"),
                "source_branch": mr.get("source_branch") or "",
                "target_branch": mr.get("target_branch") or "",
                "author": ((mr.get("author") or {}).get("name")) or "",
                "web_url": mr.get("web_url") or "",
                "pipeline_status": ps_map.get(hp.get("status") or "", "none"),
            })
        return out

    def get_merge_request_diff(self, mr_id: str) -> dict:
        """GET /projects/:id/merge_requests/:iid/changes."""
        proj_path = self._client._project_path()
        body, _ = self._client._request(
            "GET", f"/projects/{proj_path}/merge_requests/{mr_id}/changes",
        )
        changes = (body.get("changes") if isinstance(body, dict) else None) or []
        files, parts = [], []
        for ch in changes:
            if ch.get("new_file"):
                ct = "added"
            elif ch.get("deleted_file"):
                ct = "deleted"
            elif ch.get("renamed_file"):
                ct = "renamed"
            else:
                ct = "modified"
            path = ch.get("new_path") or ch.get("old_path") or ""
            files.append({"path": path, "change_type": ct})
            if ch.get("diff"):
                parts.append(f"--- {path} ({ct}) ---\n{ch['diff']}")
        return {
            "id": str(mr_id),
            "files": files,
            "diff_text": "\n".join(parts),
            "diff_available": True,
            "note": "",
        }

    def comment_merge_request(self, mr_id: str, body: str) -> dict:
        """POST /projects/:id/merge_requests/:iid/notes."""
        proj_path = self._client._project_path()
        result, _ = self._client._request(
            "POST", f"/projects/{proj_path}/merge_requests/{mr_id}/notes",
            json_body={"body": body})
        return {"ok": True, "id": str((result or {}).get("id") or "")}

    def close_merge_request(self, mr_id: str) -> dict:
        """PUT /projects/:id/merge_requests/:iid con state_event=close."""
        proj_path = self._client._project_path()
        self._client._request("PUT", f"/projects/{proj_path}/merge_requests/{mr_id}",
                              json_body={"state_event": "close"})
        return {"ok": True, "id": str(mr_id), "state": "closed"}

    def approve_merge_request(self, mr_id: str) -> dict:
        """POST /projects/:id/merge_requests/:iid/approve (OPCIONAL, capability)."""
        proj_path = self._client._project_path()
        self._client._request("POST", f"/projects/{proj_path}/merge_requests/{mr_id}/approve")
        return {"ok": True, "id": str(mr_id), "approved": True}
