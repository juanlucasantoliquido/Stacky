"""
services/gitlab_client.py -- Cliente HTTP de bajo nivel para la API GitLab v4 (Plan 65 F2).

Maneja:
  - Auth por token (env GITLAB_TOKEN > archivo auth/gitlab_auth.json > campo token)
  - Encoding de project path con "/" → "%2F"
  - Retry automático en 429 (Retry-After)
  - Paginación vía X-Next-Page (page_cap default 40)
  - Mapping de status HTTP → kind semántico (auth, not_found, rate_limited, server)

NUNCA escribe tokens a disco. Solo lee de las fuentes declaradas.
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.parse
from pathlib import Path
from typing import Optional

import requests

from services.tracker_provider import TrackerConfigError, TrackerApiError


logger = logging.getLogger(__name__)

_DEFAULT_PAGE_CAP = 40
_RETRY_MAX = 3


def _kind_for_status(status: int) -> str:
    if status in (401, 403):
        return "auth"
    if status == 404:
        return "not_found"
    if status == 429:
        return "rate_limited"
    if status >= 500:
        return "server"
    return "unknown"


class GitLabClient:
    """Cliente HTTP para la API v4 de GitLab.

    Instancia liviana: no hace red en __init__. Todas las llamadas son lazily iniciadas.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        project: Optional[str] = None,
        auth_path: Optional[str] = None,
    ):
        # 1. Resolver base_url
        self._base_url = (base_url or os.getenv("GITLAB_URL") or "").rstrip("/")

        # 2. Resolver project
        self._project_id = project or os.getenv("GITLAB_PROJECT") or ""

        # 3. Resolver token: env > archivo > campo en archivo
        token = os.getenv("GITLAB_TOKEN") or ""
        if not token:
            token = self._load_token_from_file(auth_path)

        if not token:
            raise TrackerConfigError(
                "GitLab: no se encontró GITLAB_TOKEN ni archivo auth/gitlab_auth.json"
            )

        self._token = token

    # ── Configuración ─────────────────────────────────────────────────────────

    def _load_token_from_file(self, auth_path: Optional[str]) -> str:
        """Busca el token en el archivo de credencial GitLab bajo auth_path.

        Plan 259 F3: usa read_secret_from_file, que descifra DPAPI cuando el
        archivo declara token_format y devuelve el valor tal cual cuando está en
        texto plano.

        ATENCIÓN (Plan 259 v2, hallazgo C7): read_secret_from_file NO es solo
        lectura. Cuando encuentra el secreto en claro lo cifra y REESCRIBE el
        archivo (services/secrets_store.py:277-279), lo que además ata el archivo
        al usuario de Windows que corrió la migración (DPAPI es por-usuario y
        solo-Windows). Eso es lo que queremos —el archivo queda al nivel de los
        otros 3 trackers— pero significa que un archivo no escribible haría
        fallar la lectura. Por eso, si el camino cifrado lanza, se cae al lector
        plano EXACTO de hoy: una configuración que funciona no puede dejar de
        funcionar por este plan.
        """
        from services.secrets_store import read_secret_from_file  # import local: evita ciclo

        candidates: list[Path] = []
        if auth_path:
            candidates.append(Path(auth_path) / "auth" / "gitlab_auth.json")
            candidates.append(Path(auth_path))
        # Fallback: buscar relativo al cwd (util en tests con rutas configuradas)
        candidates.append(Path("auth") / "gitlab_auth.json")

        for path in candidates:
            if not path.exists():
                continue
            for field, fmt in (("token", "token_format"), ("private_token", "private_token_format")):
                try:
                    tok = (read_secret_from_file(path, field, format_field=fmt).value or "").strip()
                except Exception:
                    tok = ""
                if tok:
                    return tok
            # Fallback literal al comportamiento previo a este plan (archivo de
            # solo lectura, disco lleno, JSON con el token plano que no se pudo
            # migrar). NO se pierde ninguna instalación que hoy anda.
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                tok = str(data.get("token") or data.get("private_token") or "").strip()
                if tok:
                    logger.warning(
                        "GitLab: token leído en texto plano de %s (no se pudo migrar a DPAPI)", path
                    )
                    return tok
            except Exception:
                pass
        return ""

    def _headers(self) -> dict:
        return {"PRIVATE-TOKEN": self._token, "Accept": "application/json"}

    def _project_path(self) -> str:
        """URL-encode el project path: 'grp/sub/proj' → 'grp%2Fsub%2Fproj', '123' → '123'."""
        pid = self._project_id
        if "/" in str(pid):
            return urllib.parse.quote(str(pid), safe="")
        return str(pid)

    # ── HTTP primitivo ─────────────────────────────────────────────────────────

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[dict] = None,
        json_body: Optional[dict] = None,
        files: Optional[dict] = None,
        _retry: int = 0,
    ) -> tuple[object, dict]:
        """Hace una llamada HTTP a la API de GitLab.

        Returns:
            (body, response_headers) donde body es el JSON parseado (dict/list)
            o la respuesta cruda (bytes) si no es JSON.

        Raises:
            TrackerApiError con status y kind semántico.
        """
        if not self._base_url:
            raise TrackerConfigError("GitLab: GITLAB_URL no configurada")

        # path puede ser absoluto (/user) o relativo (projects/...)
        if path.startswith("/"):
            url = f"{self._base_url}/api/v4{path}"
        else:
            url = f"{self._base_url}/api/v4/{path}"

        resp = requests.request(
            method,
            url,
            headers=self._headers(),
            params=params,
            json=json_body,
            files=files,
            timeout=20,
        )

        if resp.status_code == 429 and _retry < _RETRY_MAX:
            retry_after = float(resp.headers.get("Retry-After") or 1)
            time.sleep(retry_after)
            return self._request(
                method, path, params=params, json_body=json_body,
                files=files, _retry=_retry + 1,
            )

        if not resp.ok:
            kind = _kind_for_status(resp.status_code)
            try:
                msg = resp.json().get("message") or resp.text or f"HTTP {resp.status_code}"
            except Exception:
                msg = resp.text or f"HTTP {resp.status_code}"
            raise TrackerApiError(resp.status_code, str(msg), kind=kind)

        # Extraer headers sin forzar conversión a dict (algunos mocks no lo soportan)
        response_headers = resp.headers if hasattr(resp.headers, "get") else {}

        content_type = resp.headers.get("Content-Type", "")
        if "application/json" in content_type or "text/json" in content_type:
            return resp.json(), response_headers

        # Para uploads que devuelven texto o body vacío
        if not resp.content:
            return {}, response_headers

        try:
            return resp.json(), response_headers
        except Exception:
            return resp.text, response_headers

    def _request_paginated(
        self,
        path: str,
        *,
        params: Optional[dict] = None,
        page_cap: int = _DEFAULT_PAGE_CAP,
    ) -> list:
        """Pagina hasta page_cap páginas siguiendo X-Next-Page.

        Returns:
            Lista concatenada de todos los items.
        """
        base_params = dict(params or {})
        base_params.setdefault("per_page", 100)

        results: list = []
        page: Optional[str] = "1"
        pages_fetched = 0

        while page and pages_fetched < page_cap:
            current_params = {**base_params, "page": page}
            body, headers = self._request("GET", path, params=current_params)

            if isinstance(body, list):
                results.extend(body)
            elif isinstance(body, dict) and body:
                results.append(body)

            pages_fetched += 1
            page = headers.get("X-Next-Page") or headers.get("x-next-page") or None
            if not page or not page.strip():
                break

        return results
