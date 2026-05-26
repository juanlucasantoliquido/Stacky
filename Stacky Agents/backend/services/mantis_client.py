"""
services/mantis_client.py — Cliente Mantis BT para Stacky Agents.

Soporta dos protocolos:
  • REST  — Mantis BT 2.0+, autenticación por API Token.
  • SOAP  — MantisConnect (todas las versiones), autenticación usuario/contraseña.

Resolución de credenciales (en orden):
  1. Variables de entorno  MANTIS_URL / MANTIS_TOKEN / MANTIS_PROJECT_ID  (REST)
                           MANTIS_URL / MANTIS_USERNAME / MANTIS_PASSWORD  (SOAP)
  2. Archivo  backend/projects/{NAME}/auth/mantis_auth.json

Formato auth/mantis_auth.json para REST:
  { "url": "https://mantis.empresa.com", "token": "TU_API_TOKEN",
    "project_id": "1", "protocol": "rest" }

Formato auth/mantis_auth.json para SOAP:
  { "url": "https://mantis.empresa.com", "username": "admin",
    "password": "secret", "project_id": "1", "protocol": "soap" }
"""

from __future__ import annotations

import json
import logging
import os
import ssl
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Union

from services.secrets_store import (
    load_json_file,
    resolve_secret_in_payload,
    write_json_file,
)

logger = logging.getLogger("stacky_agents.mantis")

_TIMEOUT_SEC  = 30
_BACKEND_ROOT = Path(__file__).resolve().parent.parent

# Mantis status IDs: >= 80 son resueltos/cerrados
_RESOLVED_STATUS_IDS = {80, 90}

# Mantis default status IDs (can be overridden per installation, but these are the defaults).
# mc_issue_update (SOAP) and PATCH /issues (REST) need the numeric id on the status ObjectRef;
# sending only 'name' causes Mantis to default to id=0, shown as "@0@".
_STANDARD_STATUS_IDS: dict[str, int] = {
    "new": 10, "feedback": 20, "acknowledged": 30, "confirmed": 40,
    "assigned": 50, "resolved": 80, "closed": 90,
}

# Mantis priority id → escala interna 1-5 (1=crítico, 5=trivial)
_PRIORITY_MAP: dict[int, int | None] = {
    10: None,  # none
    20: 5,     # low
    30: 3,     # normal
    40: 2,     # high
    50: 1,     # urgent
    60: 1,     # immediate
}

_TEXT_EXTENSIONS: frozenset[str] = frozenset({
    ".txt", ".md", ".csv", ".log", ".json", ".xml", ".html", ".htm",
    ".yml", ".yaml", ".ini", ".cfg", ".conf", ".py", ".js", ".ts",
    ".cs", ".java", ".sql", ".diff", ".patch",
})


def _is_text_attachment(filename: str) -> bool:
    return Path(filename).suffix.lower() in _TEXT_EXTENSIONS


def _resolve_mantis_status_id(status_name: str) -> int | None:
    """Returns the numeric Mantis status ID for the given name, or None if unknown."""
    return _STANDARD_STATUS_IDS.get(status_name.strip().lower())


def _parse_mantis_enum(raw: str) -> list[str]:
    """Parsea una cadena de enumeracion Mantis del tipo '10:new,20:feedback,30:acknowledged'.

    Retorna la lista de labels en orden de ID ascendente.
    """
    result: list[tuple[int, str]] = []
    for part in raw.split(","):
        part = part.strip()
        if ":" not in part:
            continue
        id_str, _, label = part.partition(":")
        try:
            result.append((int(id_str.strip()), label.strip()))
        except ValueError:
            continue
    return [label for _, label in sorted(result)]


class MantisConfigError(RuntimeError):
    pass


class MantisApiError(RuntimeError):
    pass


# ─"─"─ Resoluci─n de credenciales ─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─

def _resolve_auth_dict(auth_file: str) -> dict:
    """
    Lee el archivo de autenticación y retorna su contenido como dict.
    Primero prueba variables de entorno, luego el archivo.
    """
    env_url      = (os.environ.get("MANTIS_URL")        or "").strip()
    env_token    = (os.environ.get("MANTIS_TOKEN")      or "").strip()
    env_user     = (os.environ.get("MANTIS_USERNAME")   or "").strip()
    env_password = (os.environ.get("MANTIS_PASSWORD")   or "").strip()
    env_pid      = (os.environ.get("MANTIS_PROJECT_ID") or "").strip()

    if env_url and env_token:
        return {"url": env_url, "token": env_token, "project_id": env_pid, "protocol": "rest"}
    if env_url and env_user and env_password:
        return {"url": env_url, "username": env_user, "password": env_password,
                "project_id": env_pid, "protocol": "soap"}

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
                if data.get("url"):
                    resolved = dict(data)
                    if token_secret.value:
                        resolved["token"] = token_secret.value
                    if password_secret.value:
                        resolved["password"] = password_secret.value
                    return resolved
            except Exception as e:
                logger.debug("No se pudo leer %s: %s", path, e)

    raise MantisConfigError(
        "Credenciales Mantis no encontradas. "
        "Setea MANTIS_URL/MANTIS_TOKEN (o MANTIS_USERNAME/MANTIS_PASSWORD) "
        "en el .env o crea auth/mantis_auth.json."
    )


def _resolve_credentials(auth_file: str) -> tuple[str, str, str]:
    """Retorna (url, token, project_id) para el cliente REST (backward compat)."""
    d = _resolve_auth_dict(auth_file)
    url   = (d.get("url")   or "").strip().rstrip("/")
    token = (d.get("token") or "").strip()
    pid   = str(d.get("project_id") or "").strip()
    if not url:
        raise MantisConfigError("Mantis URL no configurada.")
    if not token:
        raise MantisConfigError(
            "Mantis token no configurado. Para SOAP usa get_mantis_client(protocol='soap')."
        )
    return url, token, pid


# ─"─"─ REST Client ─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─

class MantisClient:
    """
    Cliente Mantis BT REST API (Mantis 2.0+, token de API).
    """
    def __init__(
        self,
        url: str = "",
        project_id: str | int = "",
        token: str = "",
        auth_file: str = "auth/mantis_auth.json",
        verify_ssl: bool = True,
    ):
        self.verify_ssl = verify_ssl

        if token:
            self.base_url   = (url or "").rstrip("/")
            self.token      = token
            self.project_id = str(project_id or "").strip()
            self._current_user_id: int | None = None
            self._auth_username: str | None = None
        else:
            resolved_url, self.token, resolved_pid = _resolve_credentials(auth_file)
            self.base_url   = (resolved_url or url or "").rstrip("/")
            self.project_id = str(project_id or resolved_pid or "").strip()
            # user_id opcional en el auth JSON — evita depender de /users/me
            try:
                import json as _json
                _p = Path(auth_file) if Path(auth_file).is_absolute() else _BACKEND_ROOT / auth_file
                _auth_dict = _json.loads(_p.read_text(encoding="utf-8")) if _p.is_file() else {}
            except Exception:
                _auth_dict = {}
            raw_uid = _auth_dict.get("user_id")
            self._current_user_id = int(raw_uid) if raw_uid is not None else None
            # Guardar username SOAP por si hace falta buscarlo via /users
            self._auth_username: str | None = (_auth_dict.get("username") or "").strip() or None

        if not self.base_url:
            raise MantisConfigError("Mantis URL no configurada.")
        if not self.token:
            raise MantisConfigError("Mantis token no configurado.")

        self._api_base = f"{self.base_url}/api/rest"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": self.token,
            "Content-Type":  "application/json",
            "Accept":        "application/json",
        }

    def _get(self, path: str, params: dict | None = None) -> dict | list:
        url = f"{self._api_base}/{path.lstrip('/')}"
        if params:
            url += "?" + urllib.parse.urlencode(params)

        ctx = None
        if not self.verify_ssl:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

        req = urllib.request.Request(url, headers=self._headers(), method="GET")
        try:
            with urllib.request.urlopen(req, timeout=_TIMEOUT_SEC, context=ctx) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")[:500]
            raise MantisApiError(f"Mantis API {e.code} en {url}: {body}") from e
        except urllib.error.URLError as e:
            raise MantisApiError(f"Mantis API no accesible ({url}): {e.reason}") from e

    def list_projects(self) -> list[dict]:
        data = self._get("projects")
        projects = data if isinstance(data, list) else data.get("projects", [])
        return [
            {
                "id":          str(p.get("id", "")),
                "name":        p.get("name", ""),
                "description": p.get("description", ""),
                "status":      (p.get("status") or {}).get("label", ""),
            }
            for p in projects
        ]

    def fetch_open_issues(self) -> list[dict]:
        if not self.project_id:
            raise MantisConfigError("Mantis project_id no configurado.")

        all_issues: list[dict] = []
        page = 1
        page_size = 50

        while True:
            data = self._get("issues", {
                "project_id": self.project_id,
                "page_size":  page_size,
                "page":       page,
            })
            issues = data.get("issues", []) if isinstance(data, dict) else []
            if not issues:
                break

            for issue in issues:
                status    = issue.get("status") or {}
                status_id = status.get("id", 0) if isinstance(status, dict) else 0
                if int(status_id) not in _RESOLVED_STATUS_IDS:
                    all_issues.append(issue)

            if len(issues) < page_size:
                break
            page += 1

        return all_issues

    def issue_url(self, issue_id: int | str) -> str:
        return f"{self.base_url}/view.php?id={issue_id}"

    def fetch_notes(self, issue_id: int | str) -> list[dict]:
        try:
            data  = self._get(f"issues/{issue_id}")
            issue = data if isinstance(data, dict) else {}
            notes = issue.get("notes") or []
            return [
                {
                    "id":         n.get("id"),
                    "text":       n.get("text", ""),
                    "reporter":   (n.get("reporter") or {}).get("name", ""),
                    "created_at": n.get("created_at", ""),
                }
                for n in notes
            ]
        except MantisApiError:
            return []

    def get_current_user_id(self) -> int | None:
        """Retorna el ID del usuario autenticado (propietario del token).

        Orden de prioridad:
        1. Valor ya cacheado (incluyendo el leido del auth JSON).
        2. GET /users/me  (Mantis 2.x).
        3. GET /users?username=X  usando el username del config SOAP.
        Retorna None si todos los intentos fallan; el filtro se omite.

        Portado de WS2 (Sprint 3 — P1.4).
        """
        if self._current_user_id is not None:
            return self._current_user_id

        # Intento 1: /users/me
        try:
            data = self._get("users/me")
            uid = data.get("id") if isinstance(data, dict) else None
            if uid is not None:
                self._current_user_id = int(uid)
                logger.debug("get_current_user_id: obtenido de /users/me -> %d", self._current_user_id)
                return self._current_user_id
        except Exception as _e:
            logger.debug("get_current_user_id: /users/me no disponible (%s)", _e)

        # Intento 2: /users?username=X si tenemos username del config
        username = getattr(self, "_auth_username", None)
        if username:
            try:
                data = self._get("users", {"username": username})
                users = data.get("users") if isinstance(data, dict) else None
                if not users and isinstance(data, list):
                    users = data
                if users:
                    first = users[0] if isinstance(users, list) else None
                    uid = (first or {}).get("id") if isinstance(first, dict) else None
                    if uid is not None:
                        self._current_user_id = int(uid)
                        logger.debug(
                            "get_current_user_id: obtenido de /users?username=%s -> %d",
                            username, self._current_user_id,
                        )
                        return self._current_user_id
            except Exception as _e:
                logger.debug("get_current_user_id: /users lookup fallo (%s)", _e)

        logger.warning(
            "get_current_user_id: no se pudo determinar el usuario actual. "
            "Agrega 'user_id' al mantis_auth.json para forzarlo."
        )
        return None

    def fetch_attachments(self, issue_id: int | str) -> list[dict]:
        """Retorna los adjuntos de un issue de Mantis BT.

        Obtiene el issue completo y extrae el array `attachments`.
        Para archivos de texto pequenos (<= 100 KB) descarga el contenido.

        Retorna lista de dicts: { "id", "name", "size", "url", "text_content" }

        Portado de WS2 (Sprint 3 — P1.4).
        """
        try:
            data = self._get(f"issues/{issue_id}")
            # Mantis REST returns {"issues": [{...}]}, not the issue at root level.
            if isinstance(data, dict) and "issues" in data:
                issues_list = data.get("issues") or []
                issue = issues_list[0] if issues_list else {}
            else:
                issue = data if isinstance(data, dict) else {}
            attachments = issue.get("attachments") or []
        except MantisApiError as e:
            logger.warning("fetch_attachments(%s) fallo: %s", issue_id, e)
            return []

        out: list[dict] = []
        for att in attachments:
            name   = (att.get("file_name") or att.get("filename") or "(sin nombre)").strip()
            size   = int(att.get("size") or 0)
            att_id = str(att.get("id") or "").strip()

            # Preferir el endpoint REST /files/{id} cuando tenemos att_id.
            if att_id:
                dl_url = f"{self._api_base}/files/{att_id}"
            else:
                dl_url = (att.get("download_url") or att.get("content_url") or "").strip()

            text_content: str | None = None
            if dl_url and _is_text_attachment(name) and size <= 102_400:
                try:
                    text_content = self._download_text(dl_url)
                except Exception as _e:
                    logger.warning("fetch_attachments: no se pudo descargar '%s' (%s): %s", name, dl_url, _e)

            out.append({"id": att_id, "name": name, "size": size, "url": dl_url, "text_content": text_content})
        return out

    def delete_attachment(self, issue_id: int | str, attachment_id: str) -> bool:
        """Elimina un adjunto de un issue de Mantis BT.

        Usa DELETE /issues/{issue_id}/files/{file_id} (Mantis REST API).
        Retorna True si tuvo exito, False en caso de error.

        Portado de WS2 (Sprint 3 — P1.4).
        """
        url = f"{self._api_base}/issues/{issue_id}/files/{attachment_id}"
        ctx = None
        if not self.verify_ssl:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(url, headers=self._headers(), method="DELETE")
        kw: dict = {"timeout": _TIMEOUT_SEC}
        if ctx:
            kw["context"] = ctx
        try:
            with urllib.request.urlopen(req, **kw):
                pass
            logger.debug("delete_attachment Mantis OK: issue=%s att=%s", issue_id, attachment_id)
            return True
        except urllib.error.HTTPError as e:
            err_body = ""
            try:
                err_body = e.read().decode("utf-8", errors="replace")[:300]
            except Exception:
                pass
            logger.warning(
                "delete_attachment HTTP %s issue=%s att=%s url=%s -- %s",
                e.code, issue_id, attachment_id, url, err_body or str(e),
            )
            return False
        except Exception as exc:
            logger.warning("delete_attachment(%s, %s) fallo: %s", issue_id, attachment_id, exc)
            return False

    def _download_text(self, url: str) -> str:
        """Descarga el contenido de una URL usando credenciales Mantis y lo retorna como texto.

        Maneja dos formatos de respuesta:
        - Texto/binario directo: se decodifica como UTF-8.
        - JSON con campo ``content`` en base64 (Mantis REST /files/{id} en algunos setups):
          se extrae y decodifica el contenido real.

        Portado de WS2 (Sprint 3 — P1.4).
        """
        import base64 as _base64
        ctx = None
        if not self.verify_ssl:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        download_headers = {"Authorization": self.token, "Accept": "*/*"}
        req = urllib.request.Request(url, headers=download_headers, method="GET")
        kw: dict = {"timeout": _TIMEOUT_SEC}
        if ctx:
            kw["context"] = ctx
        with urllib.request.urlopen(req, **kw) as resp:
            content_type = (resp.headers.get("Content-Type") or "").lower()
            raw = resp.read()
        # Mantis REST /files/{id} puede devolver JSON con el contenido en base64.
        if "application/json" in content_type or (raw[:1] == b"{"):
            try:
                parsed = json.loads(raw)
                b64 = (
                    parsed.get("content")
                    or (parsed.get("file") or {}).get("content")
                    or ((parsed.get("files") or [{}])[0]).get("content")
                )
                if b64:
                    return _base64.b64decode(b64).decode("utf-8", errors="replace")
            except Exception:
                pass  # No es JSON con base64 — continuar con decodificacion directa
        return raw.decode("utf-8", errors="replace")

    def upload_attachment(self, issue_id: int | str, file_name: str, content_bytes: bytes) -> bool:
        """Adjunta un fichero a un issue de Mantis (REST API).

        Usa POST /api/rest/issues/{id}/files con JSON+base64.
        Retorna True si tuvo exito, False en caso de error.

        Portado de WS2 (Sprint 3 — P1.4).
        """
        import base64

        encoded = base64.b64encode(content_bytes).decode("ascii")
        payload = {"files": [{"name": file_name, "content": encoded}]}
        body = json.dumps(payload).encode("utf-8")

        url = f"{self._api_base}/issues/{issue_id}/files"
        headers = {
            "Authorization": self.token,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        ctx = None
        if not self.verify_ssl:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        try:
            kw: dict = {"timeout": _TIMEOUT_SEC}
            if ctx:
                kw["context"] = ctx
            with urllib.request.urlopen(req, **kw) as resp:
                resp.read()
            logger.debug("upload_attachment OK: %s -> issue#%s", file_name, issue_id)
            return True
        except urllib.error.HTTPError as e:
            err_body = ""
            try:
                err_body = e.read().decode("utf-8", errors="replace")[:600]
            except Exception:
                pass
            logger.warning(
                "upload_attachment HTTP %s issue#%s file=%r URL=%s -- %s",
                e.code, issue_id, file_name, url, err_body or str(e),
            )
            return False
        except Exception as e:
            logger.warning("upload_attachment(%s, %r) fallo: %s", issue_id, file_name, e)
            return False

    def get_project_statuses(self) -> list[str]:
        """Retorna los nombres unicos de todos los estados configurados en Mantis.

        1. Intenta obtener la enumeracion completa de estados via
           GET /config?option[]=status_enum_string
        2. Si falla, cae en obtener estados de los issues del proyecto (primera pagina).
        Retorna [] si ambos metodos fallan; el caller usa BD como fallback.

        Portado de WS2 (Sprint 3 — P1.4).
        """
        # Intento 1: config API (todos los estados de la instalacion)
        try:
            data = self._get("config", {"option[]": "status_enum_string"})
            configs = data.get("configs") if isinstance(data, dict) else None

            if isinstance(configs, list):
                for entry in configs:
                    if not isinstance(entry, dict):
                        continue
                    if entry.get("option") != "status_enum_string":
                        continue
                    value = entry.get("value")
                    # Formato a) lista de objetos con label
                    if isinstance(value, list):
                        result = []
                        for item in sorted(value, key=lambda x: x.get("id", 0)):
                            label = (item.get("label") or item.get("name") or "").strip()
                            if label:
                                result.append(label)
                        if result:
                            return result
                    # Formato b) string enum
                    if isinstance(value, str) and value:
                        return _parse_mantis_enum(value)

            elif isinstance(configs, dict):
                raw_enum = (
                    configs.get("status_enum_string")
                    or configs.get("status_enum")
                    or ""
                )
                if raw_enum:
                    return _parse_mantis_enum(str(raw_enum))

        except Exception as _e:
            logger.debug("get_project_statuses: config API fallo (%s), usando fallback", _e)

        # Intento 2: extraer estados de los issues del proyecto
        if not self.project_id:
            return []
        try:
            data = self._get("issues", {
                "project_id": self.project_id,
                "page_size":  100,
                "page":       1,
            })
            issues = data.get("issues", []) if isinstance(data, dict) else []
        except MantisApiError as e:
            logger.warning("get_project_statuses(%s): %s", self.project_id, e)
            return []

        seen: set[str] = set()
        result: list[str] = []
        for issue in issues:
            status = issue.get("status") or {}
            name = (status.get("label") or status.get("name") or "").strip()
            if name and name not in seen:
                seen.add(name)
                result.append(name)
        return result

    def get_project_categories(self) -> list[str]:
        """Retorna las categorias disponibles para el proyecto en Mantis BT.

        1. Intenta GET /projects/{id}/categories (Mantis REST API >= 2.3).
        2. Si falla, extrae categorias unicas de los issues del proyecto.
        Retorna [] si ambos metodos fallan.

        Portado de WS2 (Sprint 3 — P1.4).
        """
        if not self.project_id:
            return []

        # Intento 1: endpoint dedicado de categorias
        try:
            data = self._get(f"projects/{self.project_id}/categories")
            categories = data if isinstance(data, list) else (data.get("categories") if isinstance(data, dict) else [])
            if isinstance(categories, list):
                result = []
                seen: set[str] = set()
                for cat in categories:
                    name = (cat.get("name") if isinstance(cat, dict) else str(cat) if isinstance(cat, str) else "").strip()
                    if name and name not in seen:
                        seen.add(name)
                        result.append(name)
                if result:
                    return result
        except Exception as _e:
            logger.debug("get_project_categories: endpoint /projects/.../categories fallo (%s), usando fallback", _e)

        # Intento 2: extraer categorias de issues existentes
        try:
            data = self._get("issues", {"project_id": self.project_id, "page_size": 100, "page": 1})
            issues = data.get("issues", []) if isinstance(data, dict) else []
        except MantisApiError as e:
            logger.warning("get_project_categories(%s): %s", self.project_id, e)
            return []

        seen2: set[str] = set()
        result2: list[str] = []
        for issue in issues:
            cat = issue.get("category") or {}
            name = (cat.get("name") or "").strip()
            if name and name not in seen2:
                seen2.add(name)
                result2.append(name)
        return result2

    def transition_issue(self, issue_id: int | str, status_name: str) -> bool:
        """Cambia el estado de un issue vía REST PATCH.

        status_name: nombre de estado Mantis (ej. 'acknowledged', 'resolved').
        Retorna True si tuvo éxito.
        """
        try:
            import urllib.request as _ur
            import ssl as _ssl
            url = f"{self._api_base}/issues/{issue_id}"
            body = json.dumps({"status": {"name": status_name}}).encode("utf-8")
            req = _ur.Request(url, data=body, headers=self._headers(), method="PATCH")
            ctx = None
            if not self.verify_ssl:
                ctx = _ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = _ssl.CERT_NONE
            kw = {"timeout": 30}
            if ctx:
                kw["context"] = ctx
            with _ur.urlopen(req, **kw) as resp:
                resp.read()
            return True
        except Exception as e:
            import logging as _log
            _log.getLogger("stacky_agents.mantis").warning(
                "transition_issue(%s, %r) falló: %s", issue_id, status_name, e
            )
            return False

    def create_issue(
        self,
        summary: str,
        description: str = "",
        initial_status: str = "",
        category: str = "General",
    ) -> dict:
        """Crea un issue en Mantis BT (REST API) y retorna el dict completo de la respuesta.

        Portado desde WS2 (2026-05-23).

        Args:
            summary:        Titulo del issue.
            description:    Descripcion en texto plano.
            initial_status: Estado inicial (nombre o label). Si esta vacio, Mantis usa 'new'.
            category:       Categoria del issue (por defecto 'General').

        Returns:
            Dict con al menos {"id": "123", "summary": "..."}.

        Raises:
            MantisApiError: si la API devuelve un error HTTP.
        """
        url = f"{self._api_base}/issues"
        body: dict = {
            "summary": summary,
            "project": {"id": int(self.project_id)} if self.project_id else {},
            "category": {"name": category},
        }
        if description:
            body["description"] = description
        if initial_status:
            status_id = _STANDARD_STATUS_IDS.get(initial_status.strip().lower())
            body["status"] = {"name": initial_status}
            if status_id:
                body["status"]["id"] = status_id

        encoded = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=encoded, headers=self._headers(), method="POST")
        ctx = None
        if not self.verify_ssl:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
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
            raise MantisApiError(f"Mantis create_issue -> {e.code}: {detail}") from e
        except urllib.error.URLError as e:
            raise MantisApiError(f"Mantis network error create_issue: {e.reason}") from e

class MantisSOAPClient:
    """
    Cliente Mantis BT vía SOAP (MantisConnect).
    Interfaz idéntica a MantisClient para ser intercambiable.

    WSDL: {url}/api/soap/mantisconnect.php?wsdl
    Auth: usuario + contraseña (parámetros en cada llamada SOAP).

    Requiere: pip install zeep
    """

    def __init__(
        self,
        url: str = "",
        project_id: str | int = "",
        username: str = "",
        password: str = "",
        auth_file: str = "auth/mantis_auth.json",
        verify_ssl: bool = True,
    ):
        self.verify_ssl = verify_ssl

        if username:
            self.base_url   = (url or "").rstrip("/")
            self.username   = username
            self.password   = password
            self.project_id = str(project_id or "").strip()
        else:
            d = _resolve_auth_dict(auth_file)
            self.base_url   = (url or d.get("url", "")).rstrip("/")
            self.username   = d.get("username", "")
            self.password   = d.get("password", "")
            self.project_id = str(project_id or d.get("project_id", "")).strip()

        if not self.base_url:
            raise MantisConfigError("Mantis URL no configurada.")
        if not self.username:
            raise MantisConfigError(
                "Mantis username no configurado para SOAP. "
                "Configurá username/password en mantis_auth.json."
            )

        self._soap = self._build_soap_client()

    def _build_soap_client(self):
        try:
            import zeep
            import requests as req_lib
            from zeep.transports import Transport
        except ImportError as exc:
            raise MantisConfigError(
                "La librería 'zeep' es requerida para SOAP. "
                "Instalá con: pip install zeep"
            ) from exc

        wsdl    = f"{self.base_url}/api/soap/mantisconnect.php?wsdl"
        session = req_lib.Session()
        session.verify = self.verify_ssl
        transport = Transport(session=session, timeout=_TIMEOUT_SEC)
        try:
            return zeep.Client(wsdl, transport=transport)
        except Exception as e:
            raise MantisApiError(f"No se pudo conectar al WSDL de Mantis ({wsdl}): {e}") from e

    # ─"─"─ Proyectos ─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─

    def list_projects(self) -> list[dict]:
        try:
            raw = self._soap.service.mc_projects_get_user_accessible(
                self.username, self.password
            )
        except Exception as e:
            raise MantisApiError(f"Error SOAP listando proyectos: {e}") from e

        result = []
        for p in (raw or []):
            result.append({
                "id":          str(getattr(p, "id", "") or ""),
                "name":        getattr(p, "name", "") or "",
                "description": getattr(p, "description", "") or "",
                "status":      str(getattr(p, "status", "") or ""),
            })
        return result

    # ─"─"─ Issues ─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─

    def fetch_open_issues(self) -> list[dict]:
        if not self.project_id:
            raise MantisConfigError("Mantis project_id no configurado.")

        all_issues: list[dict] = []
        page      = 1
        page_size = 50

        while True:
            try:
                raw = self._soap.service.mc_project_get_issues(
                    self.username, self.password,
                    int(self.project_id), page, page_size,
                )
            except Exception as e:
                raise MantisApiError(f"Error SOAP obteniendo issues: {e}") from e

            issues = list(raw) if raw else []
            if not issues:
                break

            for issue in issues:
                status_id = int(getattr(getattr(issue, "status", None), "id", 0) or 0)
                if status_id not in _RESOLVED_STATUS_IDS:
                    all_issues.append(self._soap_issue_to_dict(issue))

            if len(issues) < page_size:
                break
            page += 1

        return all_issues

    def _soap_issue_to_dict(self, issue) -> dict:
        status   = getattr(issue, "status",   None)
        priority = getattr(issue, "priority", None)
        return {
            "id":          getattr(issue, "id", None),
            "summary":     getattr(issue, "summary",     "") or "",
            "description": getattr(issue, "description", "") or "",
            "status": {
                "id":    int(getattr(status, "id", 0) or 0),
                "label": getattr(status, "name", "") or "",
            },
            "priority": {
                "id": int(getattr(priority, "id", 30) or 30),
            },
        }

    def issue_url(self, issue_id: int | str) -> str:
        return f"{self.base_url}/view.php?id={issue_id}"

    def fetch_notes(self, issue_id: int | str) -> list[dict]:
        try:
            issue = self._soap.service.mc_issue_get(
                self.username, self.password, int(issue_id)
            )
            notes = list(getattr(issue, "notes", None) or [])
            return [
                {
                    "id":         getattr(n, "id",             None),
                    "text":       getattr(n, "text",           "") or "",
                    "reporter":   getattr(getattr(n, "reporter", None), "name", "") or "",
                    "created_at": str(getattr(n, "date_submitted", "") or ""),
                }
                for n in notes
            ]
        except Exception:
            return []

    def transition_issue(self, issue_id: int | str, status_name: str) -> bool:
        """Cambia el estado de un issue vía SOAP mc_issue_update.

        status_name: nombre de estado Mantis (ej. 'acknowledged', 'resolved').
        Retorna True si tuvo éxito.
        """
        try:
            issue = self._soap.service.mc_issue_get(
                self.username, self.password, int(issue_id)
            )
            # Crear objeto de actualización con solo el campo status
            issue_data = self._soap.get_type("ns0:IssueData")()
            issue_data.status = self._soap.get_type("ns0:ObjectRef")()
            issue_data.status.name = status_name
            # Copiar campos obligatorios del issue original
            for field in ("summary", "project", "category", "priority", "reproducibility", "severity"):
                val = getattr(issue, field, None)
                if val is not None:
                    setattr(issue_data, field, val)
            self._soap.service.mc_issue_update(
                self.username, self.password, int(issue_id), issue_data
            )
            return True
        except Exception as e:
            import logging as _log
            _log.getLogger("stacky_agents.mantis").warning(
                "SOAP transition_issue(%s, %r) falló: %s", issue_id, status_name, e
            )
            return False


# ─"─"─ Factory ─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─"─

AnyMantisClient = Union[MantisClient, MantisSOAPClient]


def get_mantis_client(
    url: str = "",
    project_id: str | int = "",
    protocol: str = "rest",
    token: str = "",
    username: str = "",
    password: str = "",
    auth_file: str = "auth/mantis_auth.json",
    verify_ssl: bool = True,
) -> AnyMantisClient:
    """
    Factory que retorna el cliente adecuado según el protocolo.

    Si no se pasan credenciales directas las resuelve desde auth_file.
    Si auth_file contiene el campo 'protocol', ese valor tiene precedencia
    sobre el parámetro protocol cuando este es el valor por defecto 'rest'.
    """
    # Intentar leer protocolo del auth_file si no se especificó explícitamente
    if protocol == "rest" and not token and not username:
        try:
            d = _resolve_auth_dict(auth_file)
            protocol = d.get("protocol", "rest")
        except MantisConfigError:
            pass

    if protocol == "soap":
        return MantisSOAPClient(
            url=url,
            project_id=project_id,
            username=username,
            password=password,
            auth_file=auth_file,
            verify_ssl=verify_ssl,
        )
    else:
        return MantisClient(
            url=url,
            project_id=project_id,
            token=token,
            auth_file=auth_file,
            verify_ssl=verify_ssl,
        )


__all__ = [
    "MantisClient",
    "MantisSOAPClient",
    "AnyMantisClient",
    "get_mantis_client",
    "MantisConfigError",
    "MantisApiError",
    "_PRIORITY_MAP",
    "_RESOLVED_STATUS_IDS",
]

