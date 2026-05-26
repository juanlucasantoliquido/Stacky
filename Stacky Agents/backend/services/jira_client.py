"""
services/jira_client.py — Cliente Jira REST API para Stacky Agents.

Soporta Jira Cloud (v3) y Jira Server / Data Center (v2).
Las credenciales se resuelven en este orden:
  1. env JIRA_URL / JIRA_USER / JIRA_TOKEN
  2. backend/auth/jira_auth.json (ruta indicada en issue_tracker.auth_file)

Formato auth/jira_auth.json:
  { "url": "https://empresa.atlassian.net", "user": "me@emp.com", "token": "ATATT..." }
  (Para Server/DC: "token" es la contraseña o un PAT de Jira Server)
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from services.secrets_store import (
    load_json_file,
    resolve_secret_in_payload,
    write_json_file,
)

logger = logging.getLogger("stacky_agents.jira")

_TIMEOUT_SEC = 30
_BACKEND_ROOT = Path(__file__).resolve().parent.parent

_TEXT_EXTENSIONS = {
    ".txt", ".log", ".md", ".csv", ".json", ".xml", ".yaml", ".yml",
    ".py", ".js", ".ts", ".cs", ".java", ".sql", ".html", ".htm",
    ".sh", ".bat", ".ps1", ".rb", ".go", ".rs", ".php", ".tf",
}


def _is_text_attachment(filename: str) -> bool:
    return Path(filename).suffix.lower() in _TEXT_EXTENSIONS


class JiraConfigError(RuntimeError):
    pass


class JiraApiError(RuntimeError):
    pass


def _resolve_credentials(auth_file: str, base_url: str) -> tuple[str, str, str]:
    """
    Retorna (url, user, token).

    Primero intenta variables de entorno, luego el archivo auth_file.
    """
    env_url   = (os.environ.get("JIRA_URL")   or "").strip()
    env_user  = (os.environ.get("JIRA_USER")  or "").strip()
    env_token = (os.environ.get("JIRA_TOKEN") or "").strip()

    if env_url and env_user and env_token:
        return env_url.rstrip("/"), env_user, env_token

    # Intentar el archivo de credenciales
    p = Path(auth_file)
    candidates = (
        [p] if p.is_absolute()
        else [
            _BACKEND_ROOT / auth_file,
            _BACKEND_ROOT.parent.parent / "Stacky" / auth_file,
        ]
    )
    for path in candidates:
        if path.is_file():
            try:
                data = load_json_file(path)
                token_secret = resolve_secret_in_payload(
                    data,
                    "token",
                    format_field="token_format",
                )
                password_secret = resolve_secret_in_payload(
                    data,
                    "password",
                    format_field="password_format",
                )
                if token_secret.migrated or password_secret.migrated:
                    write_json_file(path, data)
                file_url   = (data.get("url")   or base_url or "").strip().rstrip("/")
                file_user  = (data.get("user")  or data.get("email") or "").strip()
                file_token = (token_secret.value or password_secret.value or "").strip()
                if file_user and file_token:
                    return file_url or base_url.rstrip("/"), file_user, file_token
            except Exception as e:
                logger.debug("No se pudo leer %s: %s", path, e)

    raise JiraConfigError(
        "Credenciales Jira no encontradas. "
        "Setea JIRA_URL/JIRA_USER/JIRA_TOKEN en el .env o crea auth/jira_auth.json."
    )


class JiraClient:
    def __init__(
        self,
        url: str = "",
        project_key: str = "",
        api_version: str = "3",
        jql: str = "",
        auth_file: str = "auth/jira_auth.json",
        verify_ssl: bool = True,
    ):
        resolved_url, self.user, self.token = _resolve_credentials(auth_file, url)
        self.base_url    = (resolved_url or url or "").rstrip("/")
        self.project_key = project_key.strip()
        self.api_version = api_version.strip() or "3"
        self.verify_ssl  = verify_ssl

        if not self.base_url:
            raise JiraConfigError("Jira URL no configurada.")
        if not self.project_key:
            raise JiraConfigError("Jira project_key no configurado.")

        # Auth header: Basic base64(user:token)
        creds = f"{self.user}:{self.token}"
        self._auth = "Basic " + base64.b64encode(creds.encode("utf-8")).decode("ascii")

        # JQL por defecto o el que viene en config
        self.jql = jql or (
            f"project = {self.project_key} "
            "AND statusCategory != Done "
            "ORDER BY updated DESC"
        )
        self._api_base = f"{self.base_url}/rest/api/{self.api_version}"

    # ── HTTP ─────────────────────────────────────────────────────────────────

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": self._auth,
            "Content-Type":  "application/json",
            "Accept":        "application/json",
        }

    def _ssl_context(self):
        if not self.verify_ssl:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode    = ssl.CERT_NONE
            return ctx
        return None

    def _request(self, method: str, url: str, body: dict | None = None) -> dict:
        data = None if body is None else json.dumps(body).encode("utf-8")
        req  = urllib.request.Request(url, data=data, headers=self._headers(), method=method)
        ctx  = self._ssl_context()
        try:
            kw: dict = {"timeout": _TIMEOUT_SEC}
            if ctx:
                kw["context"] = ctx
            with urllib.request.urlopen(req, **kw) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode("utf-8", errors="replace")[:500]
            except Exception:
                pass
            raise JiraApiError(f"Jira {method} {url} → {e.code}: {detail}") from e
        except urllib.error.URLError as e:
            raise JiraApiError(f"Jira network error {method} {url}: {e.reason}") from e

    # ── Búsqueda de issues ────────────────────────────────────────────────────

    def fetch_open_issues(self) -> list[dict]:
        """
        Retorna los issues abiertos del proyecto usando JQL.
        Usa POST /search/jql (nueva API Atlassian Cloud 2025) con paginación
        por cursor (nextPageToken). Capa de compatibilidad: si el servidor
        devuelve 410/404 cae a GET /search clásico.
        Pagina automáticamente hasta 500 resultados.
        """
        fields_list = ["summary", "status", "description", "priority",
                       "assignee", "updated", "issuetype", "comment"]
        results: list[dict] = []
        max_results = 50
        next_page_token: str | None = None
        url_new = f"{self._api_base}/search/jql"

        while True:
            body: dict = {
                "jql":        self.jql,
                "fields":     fields_list,
                "maxResults": max_results,
            }
            if next_page_token:
                body["nextPageToken"] = next_page_token

            try:
                data = self._request("POST", url_new, body=body)
            except JiraApiError as e:
                logger.warning("fetch_open_issues falló: %s", e)
                raise

            issues = data.get("issues") or data.get("values") or []
            results.extend(issues)

            next_page_token = data.get("nextPageToken") or None
            if not next_page_token or not issues or len(results) >= 500:
                break

        return results

    def issue_url(self, issue_key: str) -> str:
        return f"{self.base_url}/browse/{issue_key}"

    def fetch_issue_ids_for_jql(self, jql: str) -> set[int]:
        """Retorna el conjunto de IDs internos de Jira que coinciden con el JQL dado.
        Solo solicita el campo ``id`` para minimizar la carga de red.

        Portado de WS2 (Sprint 3 — P1.4).
        """
        import urllib.parse as _up
        url_base = f"{self._api_base}/search"
        ids: set[int] = set()
        start_at = 0
        page_size = 200

        while True:
            params = _up.urlencode({
                "jql":        jql,
                "fields":     "id",
                "maxResults": page_size,
                "startAt":    start_at,
            })
            try:
                resp = self._request("GET", f"{url_base}?{params}")
            except Exception as exc:
                logger.warning("fetch_issue_ids_for_jql fallo en startAt=%s: %s", start_at, exc)
                break
            issues = resp.get("issues") or []
            for issue in issues:
                try:
                    ids.add(int(issue["id"]))
                except (KeyError, ValueError, TypeError):
                    pass
            total     = resp.get("total", 0)
            start_at += len(issues)
            if not issues or start_at >= total:
                break

        return ids

    def fetch_comments(self, issue_key: str, top: int = 20) -> list[dict]:
        """Retorna los últimos `top` comentarios de un issue."""
        url = f"{self._api_base}/issue/{issue_key}/comment?maxResults={top}&orderBy=-created"
        try:
            data = self._request("GET", url)
        except JiraApiError as e:
            logger.warning("fetch_comments(%s) falló: %s", issue_key, e)
            return []

        out: list[dict] = []
        for c in (data.get("comments") or []):
            body = c.get("body") or ""
            if isinstance(body, dict):
                body = _adf_to_text(body)
            author_obj = c.get("author") or {}
            author = (
                author_obj.get("displayName")
                or author_obj.get("emailAddress")
                or "?"
            )
            date = (c.get("updated") or c.get("created") or "")[:10]
            if body:
                out.append({"author": author, "date": date, "text": body})
        return out

    def transition_issue(self, issue_key: str, status_name: str) -> bool:
        """Transiciona un issue de Jira al estado con el nombre dado.

        1. Obtiene las transiciones disponibles.
        2. Busca por nombre (case-insensitive).
        3. POST /issue/{key}/transitions con el id encontrado.
        Retorna True si tuvo éxito, False en caso de error.
        """
        try:
            url = f"{self._api_base}/issue/{issue_key}/transitions"
            data = self._request("GET", url)
            transitions = data.get("transitions") or []
            match = next(
                (t for t in transitions if (t.get("name") or "").lower() == status_name.lower()),
                None,
            )
            if not match:
                match = next(
                    (t for t in transitions
                     if (t.get("to") or {}).get("name", "").lower() == status_name.lower()),
                    None,
                )
            if not match:
                logger.warning("transition_issue(%s): no se encontró transición '%s'", issue_key, status_name)
                return False
            self._request("POST", url, {"transition": {"id": match["id"]}})
            return True
        except JiraApiError as e:
            logger.warning("transition_issue(%s, %r) falló: %s", issue_key, status_name, e)
            return False

    # ── Métodos portados desde WS2 (2026-05-23) ───────────────────────────────

    def fetch_attachments(self, issue_key: str) -> list[dict]:
        """Retorna los adjuntos de un issue de Jira.

        Llama a GET /issue/{key}?fields=attachment para obtener la lista.
        Para archivos de texto pequeños (<= 100 KB) descarga el contenido.

        Retorna lista de dicts: { "id", "name", "size", "url", "created", "text_content" }
        """
        url = f"{self._api_base}/issue/{issue_key}?fields=attachment"
        try:
            data = self._request("GET", url)
        except JiraApiError as e:
            logger.warning("fetch_attachments(%s) falló: %s", issue_key, e)
            return []

        out: list[dict] = []
        for att in ((data.get("fields") or {}).get("attachment") or []):
            name = (att.get("filename") or "(sin nombre)").strip()
            att_id = str(att.get("id") or "").strip()
            size = int(att.get("size") or 0)
            content_url = (att.get("content") or "").strip()
            mime = (att.get("mimeType") or "").lower()
            created = (att.get("created") or "")[:19]

            text_content: str | None = None
            is_text = _is_text_attachment(name) or mime.startswith("text/")
            if content_url and is_text and 0 < size <= 102_400:
                try:
                    text_content = self._download_text(content_url)
                except Exception as _e:
                    logger.debug("fetch_attachments: no se pudo leer '%s': %s", name, _e)

            out.append({
                "id": att_id, "name": name, "size": size, "url": content_url,
                "created": created, "text_content": text_content,
            })
        return out

    def delete_attachment(self, attachment_id: str) -> bool:
        """Elimina un adjunto de Jira por su ID.

        Usa DELETE /rest/api/{v}/attachment/{id}.
        Retorna True si tuvo éxito, False en caso de error.
        """
        url = f"{self._api_base}/attachment/{attachment_id}"
        try:
            self._request("DELETE", url)
            logger.debug("delete_attachment OK: id=%s", attachment_id)
            return True
        except JiraApiError as e:
            logger.warning("delete_attachment(%s) falló: %s", attachment_id, e)
            return False

    def _download_text(self, url: str) -> str:
        """Descarga el contenido de una URL usando credenciales Jira y lo retorna como texto."""
        req = urllib.request.Request(url, headers=self._headers(), method="GET")
        ctx = self._ssl_context()
        kw: dict = {"timeout": _TIMEOUT_SEC}
        if ctx:
            kw["context"] = ctx
        with urllib.request.urlopen(req, **kw) as resp:
            raw = resp.read()
        return raw.decode("utf-8", errors="replace")

    def upload_attachment(self, issue_key: str, file_name: str, content_bytes: bytes) -> bool:
        """Adjunta un fichero a un issue de Jira via multipart/form-data.

        Jira requiere el header X-Atlassian-Token: no-check para desactivar la
        protección XSRF en el endpoint de adjuntos.
        Retorna True si tuvo éxito, False en caso de error.
        """
        url = f"{self._api_base}/issue/{issue_key}/attachments"
        boundary = "StackyJiraBoundary12345"
        body = (
            (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="file"; filename="{file_name}"\r\n'
                f"Content-Type: application/octet-stream\r\n\r\n"
            ).encode("utf-8")
            + content_bytes
            + f"\r\n--{boundary}--\r\n".encode("utf-8")
        )
        headers = {
            "Authorization": self._auth,
            "X-Atlassian-Token": "no-check",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Accept": "application/json",
        }
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        ctx = self._ssl_context()
        try:
            kw: dict = {"timeout": _TIMEOUT_SEC}
            if ctx:
                kw["context"] = ctx
            with urllib.request.urlopen(req, **kw) as resp:
                resp.read()
            logger.debug("upload_attachment OK: %s → %s", file_name, issue_key)
            return True
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode("utf-8", errors="replace")[:300]
            except Exception:
                pass
            logger.warning(
                "upload_attachment(%s, %r) HTTP %s: %s", issue_key, file_name, e.code, detail
            )
            return False
        except urllib.error.URLError as e:
            logger.warning(
                "upload_attachment(%s, %r) network error: %s", issue_key, file_name, e.reason
            )
            return False

    def get_project_statuses(self) -> list[str]:
        """Retorna los nombres únicos de todos los estados del proyecto Jira.

        Usa GET /rest/api/{v}/project/{projectKey}/statuses.
        Retorna lista de nombres únicos en orden de primera aparición.
        Si falla, retorna lista vacía.
        """
        url = f"{self._api_base}/project/{self.project_key}/statuses"
        try:
            data = self._request("GET", url)
        except JiraApiError as e:
            logger.warning("get_project_statuses(%s) falló: %s", self.project_key, e)
            return []

        seen: set[str] = set()
        result: list[str] = []
        for issue_type in (data if isinstance(data, list) else []):
            for status in (issue_type.get("statuses") or []):
                name = (status.get("name") or "").strip()
                if name and name not in seen:
                    seen.add(name)
                    result.append(name)
        return result

    def create_issue(
        self,
        issue_type: str,
        summary: str,
        description: str = "",
        initial_status: str = "",
        parent_key: str | None = None,
        assignee_id: str | None = None,
        extra_fields: dict | None = None,
    ) -> dict:
        """Crea un issue en Jira y retorna el dict completo de la respuesta.

        Args:
            issue_type:     Tipo de issue (ej. "Tarea", "Trabajo").
            summary:        Título / resumen del issue.
            description:    Texto descriptivo. Se convierte a ADF para v3 o texto plano para v2.
            initial_status: Estado inicial. Si se indica, se aplica una transición tras la creación.
            parent_key:     Clave del issue padre para subtareas (opcional).
            assignee_id:    accountId del usuario al que asignar el issue (opcional).
            extra_fields:   Campos adicionales a incluir en el payload de creación (opcional).

        Returns:
            Dict con al menos {"key": "PROJ-123", "id": "...", "self": "..."}.

        Raises:
            JiraApiError: si la API devuelve un error HTTP.
        """
        url = f"{self._api_base}/issue"

        fields: dict = {
            "project": {"key": self.project_key},
            "issuetype": {"name": issue_type},
            "summary": summary,
        }

        if description:
            if self.api_version == "3":
                fields["description"] = {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [{"type": "text", "text": description}],
                        }
                    ],
                }
            else:
                fields["description"] = description

        if parent_key:
            fields["parent"] = {"key": parent_key}

        if assignee_id:
            fields["assignee"] = {"accountId": assignee_id}

        if extra_fields:
            fields.update(extra_fields)

        result = self._request("POST", url, {"fields": fields})

        # Si se indica estado inicial, transicionar después de crear
        if initial_status and result.get("key"):
            self.transition_issue(result["key"], initial_status)

        return result

    def get_issue_types(self) -> list[str]:
        """Retorna los nombres de los tipos de issue disponibles para el proyecto Jira."""
        try:
            url = (
                f"{self._api_base}/issue/createmeta"
                f"?projectKeys={self.project_key}&expand=projects.issuetypes"
            )
            data = self._request("GET", url)
            types: list[str] = []
            for proj in (data.get("projects") or []):
                for it in (proj.get("issuetypes") or []):
                    name = (it.get("name") or "").strip()
                    if name:
                        types.append(name)
            return types
        except JiraApiError as e:
            logger.warning("get_issue_types: %s", e)
            return []

    def update_issue_fields(self, issue_key: str, fields: dict) -> bool:
        """Actualiza campos de un issue existente via PUT.

        Args:
            issue_key: Clave del issue a actualizar (ej. "B2IM-132").
            fields:    Dict de campos en formato Jira API.

        Returns:
            True si tuvo éxito, False si hubo error.
        """
        url = f"{self._api_base}/issue/{issue_key}"
        try:
            self._request("PUT", url, {"fields": fields})
            return True
        except JiraApiError as e:
            logger.warning("update_issue_fields(%s) falló: %s", issue_key, e)
            return False

    @staticmethod
    def normalize_field_for_update(value: object) -> object:
        """Normaliza un valor de campo de la respuesta GET para uso en PUT/POST.

        - Lista de dicts con 'value' (multi-select) → [{"value": ...}]
        - Dict con 'value' (single-select) → {"value": ...}
        - Lista de strings (labels) → sin cambios
        - Otros → sin cambios
        """
        if isinstance(value, list):
            if value and isinstance(value[0], dict) and "value" in value[0]:
                return [{"value": v["value"]} for v in value if "value" in v]
            return value
        if isinstance(value, dict) and "value" in value:
            return {"value": value["value"]}
        return value


# ── Helpers ───────────────────────────────────────────────────────────────────

def _adf_to_text(node: dict | list | None, depth: int = 0) -> str:
    """Convierte Atlassian Document Format (ADF) a texto plano."""
    if node is None:
        return ""
    if isinstance(node, list):
        return "".join(_adf_to_text(n, depth) for n in node)
    if isinstance(node, str):
        return node

    node_type = node.get("type", "")
    content   = node.get("content") or []
    text_val  = node.get("text", "")

    if node_type == "text":
        return text_val

    inner = "".join(_adf_to_text(c, depth + 1) for c in content)

    if node_type in {"paragraph", "heading"}:
        return inner.strip() + "\n"
    if node_type in {"bulletList", "orderedList"}:
        return inner
    if node_type == "listItem":
        return "• " + inner.strip() + "\n"
    if node_type == "hardBreak":
        return "\n"
    if node_type == "codeBlock":
        return f"\n```\n{inner}\n```\n"

    return inner


_STRIP_RE = re.compile(r"\{[^}]+\}|h[1-6]\.")


def strip_jira_wiki_markup(text: str) -> str:
    """Limpieza básica de Jira wiki markup para Server/DC (v2)."""
    if not text:
        return ""
    text = _STRIP_RE.sub("", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)   # bold
    text = re.sub(r"_([^_]+)_",   r"\1", text)   # italic
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


__all__ = [
    "JiraClient",
    "JiraConfigError",
    "JiraApiError",
    "strip_jira_wiki_markup",
    "_is_text_attachment",
]
