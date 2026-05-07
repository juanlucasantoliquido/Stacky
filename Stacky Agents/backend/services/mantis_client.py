"""
services/mantis_client.py â€” Cliente Mantis BT para Stacky Agents.

Soporta dos protocolos:
  â€¢ REST  â€” Mantis BT 2.0+, autenticaciÃ³n por API Token.
  â€¢ SOAP  â€” MantisConnect (todas las versiones), autenticaciÃ³n usuario/contraseÃ±a.

ResoluciÃ³n de credenciales (en orden):
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

logger = logging.getLogger("stacky_agents.mantis")

_TIMEOUT_SEC  = 30
_BACKEND_ROOT = Path(__file__).resolve().parent.parent

# Mantis status IDs: >= 80 son resueltos/cerrados
_RESOLVED_STATUS_IDS = {80, 90}

# Mantis priority id â†’ escala interna 1-5 (1=crÃ­tico, 5=trivial)
_PRIORITY_MAP: dict[int, int | None] = {
    10: None,  # none
    20: 5,     # low
    30: 3,     # normal
    40: 2,     # high
    50: 1,     # urgent
    60: 1,     # immediate
}


class MantisConfigError(RuntimeError):
    pass


class MantisApiError(RuntimeError):
    pass


# â”€â”€ ResoluciÃ³n de credenciales â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _resolve_auth_dict(auth_file: str) -> dict:
    """
    Lee el archivo de autenticaciÃ³n y retorna su contenido como dict.
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
                data = json.loads(path.read_text(encoding="utf-8"))
                if data.get("url"):
                    return data
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


# â”€â”€ REST Client â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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
        else:
            resolved_url, self.token, resolved_pid = _resolve_credentials(auth_file)
            self.base_url   = (resolved_url or url or "").rstrip("/")
            self.project_id = str(project_id or resolved_pid or "").strip()

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


# â”€â”€ SOAP Client â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class MantisSOAPClient:
    """
    Cliente Mantis BT vÃ­a SOAP (MantisConnect).
    Interfaz idÃ©ntica a MantisClient para ser intercambiable.

    WSDL: {url}/api/soap/mantisconnect.php?wsdl
    Auth: usuario + contraseÃ±a (parÃ¡metros en cada llamada SOAP).

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
                "ConfigurÃ¡ username/password en mantis_auth.json."
            )

        self._soap = self._build_soap_client()

    def _build_soap_client(self):
        try:
            import zeep
            import requests as req_lib
            from zeep.transports import Transport
        except ImportError as exc:
            raise MantisConfigError(
                "La librerÃ­a 'zeep' es requerida para SOAP. "
                "InstalÃ¡ con: pip install zeep"
            ) from exc

        wsdl    = f"{self.base_url}/api/soap/mantisconnect.php?wsdl"
        session = req_lib.Session()
        session.verify = self.verify_ssl
        transport = Transport(session=session, timeout=_TIMEOUT_SEC)
        try:
            return zeep.Client(wsdl, transport=transport)
        except Exception as e:
            raise MantisApiError(f"No se pudo conectar al WSDL de Mantis ({wsdl}): {e}") from e

    # â”€â”€ Proyectos â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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

    # â”€â”€ Issues â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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


# â”€â”€ Factory â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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
    Factory que retorna el cliente adecuado segÃºn el protocolo.

    Si no se pasan credenciales directas las resuelve desde auth_file.
    Si auth_file contiene el campo 'protocol', ese valor tiene precedencia
    sobre el parÃ¡metro protocol cuando este es el valor por defecto 'rest'.
    """
    # Intentar leer protocolo del auth_file si no se especificÃ³ explÃ­citamente
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

