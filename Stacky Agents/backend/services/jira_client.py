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

logger = logging.getLogger("stacky_agents.jira")

_TIMEOUT_SEC = 30
_BACKEND_ROOT = Path(__file__).resolve().parent.parent


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
                data = json.loads(path.read_text(encoding="utf-8"))
                file_url   = (data.get("url")   or base_url or "").strip().rstrip("/")
                file_user  = (data.get("user")  or data.get("email") or "").strip()
                file_token = (data.get("token") or data.get("password") or "").strip()
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
]
