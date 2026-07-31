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
import re
import time
import urllib.parse
from pathlib import Path
from typing import Optional

import requests

import config
from services.tracker_provider import TrackerConfigError, TrackerApiError


logger = logging.getLogger(__name__)

_DEFAULT_PAGE_CAP = 40
_RETRY_MAX = 3

# Plan 276 F9/P2-3 — techo del Retry-After. Un servidor que responde
# `Retry-After: 86400` colgaría el worker un día entero; se recorta y se avisa.
_RETRY_AFTER_MAX = 30.0


def _resolver_retry_after(crudo) -> float:
    """Segundos a esperar tras un 429, CLAMPEADOS a _RETRY_AFTER_MAX (P2-3).

    Un `Retry-After: 86400` (un día) dejaba el worker colgado sin ninguna señal.
    Se recorta y se avisa; un valor no numérico cae a 1 segundo.
    """
    try:
        pedido = float(crudo) if crudo not in (None, "") else 1.0
    except (TypeError, ValueError):
        logger.warning("GitLab devolvió un Retry-After no numérico (%r); se espera 1s.", crudo)
        return 1.0
    if pedido > _RETRY_AFTER_MAX:
        logger.warning(
            "GitLab pidió esperar %.0fs (Retry-After); se recorta a %.0fs para no "
            "colgar el worker.", pedido, _RETRY_AFTER_MAX,
        )
        return _RETRY_AFTER_MAX
    return max(pedido, 0.0)


class _AdaptadorOpenSSL(requests.adapters.HTTPAdapter):
    """Monta un ssl_context OpenSSL genuino en una sola sesión.

    init_poolmanager y proxy_manager_for son los DOS puntos por donde urllib3
    construye pools: sin el segundo, una red con proxy corporativo se saltea el
    contexto y vuelve el SSLError.
    """

    def __init__(self, contexto, **kw):
        self._contexto = contexto
        super().__init__(**kw)

    def init_poolmanager(self, *args, **kwargs):
        kwargs["ssl_context"] = self._contexto
        return super().init_poolmanager(*args, **kwargs)

    def proxy_manager_for(self, *args, **kwargs):
        kwargs["ssl_context"] = self._contexto
        return super().proxy_manager_for(*args, **kwargs)


def _validar_base_url(url: str) -> str:
    """La base_url es SOLO el origen. Con el namespace pegado, la URL que arma
    _request queda 'https://host/grupo/api/v4/...' => HTTP 404 mudo
    (kind='not_found', _kind_for_status). Plan 276 F3."""
    limpia = (url or "").strip().rstrip("/")
    if not limpia:
        return ""
    if not re.match(r"^https?://", limpia, re.I):
        raise TrackerConfigError(f"GITLAB_URL debe empezar con http:// o https://: '{url}'")
    resto = re.sub(r"^https?://[^/]+", "", limpia, flags=re.I)
    if re.search(r"/api/v[0-9]+$", resto, re.I):
        raise TrackerConfigError(
            f"Quitá el '/api/v4' del final de la URL de GitLab: Stacky lo agrega. Recibido: '{url}'"
        )
    if resto:
        raise TrackerConfigError(
            f"La URL de GitLab debe ser solo el servidor (ej: https://srvcgit01.imsolutions.local). "
            f"Sacá '{resto}' — eso va en el campo 'Proyecto' (ej: grupo/proyecto). Recibido: '{url}'"
        )
    return limpia


def _kind_for_status(status: int) -> str:
    """Traduce un status HTTP a un `kind` semántico.

    Plan 276 F2 — hay DOS kinds que NO nacen de un status HTTP y por eso no
    aparecen acá: `"tls"` y `"network"`. Se asignan en los `except` de `_request`
    cuando la llamada muere ANTES de tener respuesta (handshake TLS fallido o
    error de red). Se distinguen a propósito: `kind == "tls"` significa
    "el certificado/la cadena no cerró" y es lo que F4 usa para decidir que el
    sub-veredicto de TLS está en rojo; cualquier otro kind implica que el TLS
    anduvo porque hubo respuesta HTTP.
    """
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
        ca_bundle: Optional[str] = None,
    ):
        # 0. Verificación TLS. Los GitLab internos suelen presentar un
        #    certificado cuya CA emisora no está en ningún almacén de la
        #    máquina; sin bundle, TODA llamada muere con
        #    `CERTIFICATE_VERIFY_FAILED: unable to get local issuer certificate`.
        #    `preparar_verificacion` devuelve la ruta del bundle o la
        #    verificación estándar. Es POR CONEXIÓN a propósito:
        #    `REQUESTS_CA_BUNDLE` es global al proceso y rompería la
        #    verificación de ADO/Jira/Mantis/LLM en el mismo backend.
        #
        #    Plan 276 F2/F3: el pin de hoja ya NO se habilita parcheando urllib3
        #    (era global y debilitaba la verificación de todos los demás
        #    destinos): vive en el ssl_context del adapter de más abajo. Y una
        #    ruta de bundle DECLARADA que no existe ya no degrada en silencio:
        #    lanza CaBundleInvalido, que acá se traduce a TrackerConfigError.
        from services.tls_openssl_context import (  # noqa: PLC0415
            CaBundleInvalido,
            crear_contexto_openssl,
        )
        from services.tls_pinning import preparar_verificacion, resolver_ca_bundle  # noqa: PLC0415

        _adapter_habilitado = bool(
            getattr(config.config, "STACKY_GITLAB_TLS_ADAPTER_ENABLED", True)
        )
        try:
            # Con la flag OFF el resolvedor vuelve a ser tolerante (estricto=False)
            # para que la rama apagada sea byte-idéntica al comportamiento de hoy.
            self._ruta_bundle = resolver_ca_bundle(ca_bundle, estricto=_adapter_habilitado)
            self._verify = preparar_verificacion(ca_bundle, estricto=_adapter_habilitado)
        except CaBundleInvalido as exc:
            raise TrackerConfigError(str(exc)) from exc

        # 1. Resolver base_url
        self._base_url = _validar_base_url(base_url or os.getenv("GITLAB_URL") or "")

        # Plan 276 F2 — sesión propia. El contexto OpenSSL se monta SOLO para el
        # prefijo de este GitLab: cualquier otro destino del proceso (ADO, Jira,
        # LLM, gitlab.com) sigue por truststore, que es lo que resuelve Zscaler.
        self._session = requests.Session()
        self._contexto_tls = None
        if _adapter_habilitado:
            try:
                self._contexto_tls = crear_contexto_openssl(self._ruta_bundle)
            except CaBundleInvalido as exc:
                raise TrackerConfigError(str(exc)) from exc
            if self._contexto_tls is not None and self._base_url:
                self._session.mount(self._base_url, _AdaptadorOpenSSL(self._contexto_tls))

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

        try:
            resp = self._session.request(
                method,
                url,
                headers=self._headers(),
                params=params,
                json=json_body,
                files=files,
                timeout=20,
                verify=self._verify,
            )
        except requests.exceptions.SSLError as exc:
            # P1-7: sin esto la SSLError sube CRUDA y ningún `except
            # TrackerApiError` aguas arriba la ve — el operador recibe un 500 mudo.
            raise TrackerApiError(
                0,
                f"TLS contra {self._base_url}: {exc}. "
                f"Certificado en uso: {self._ruta_bundle or '(verificación estándar)'}",
                kind="tls",
            ) from exc
        except requests.exceptions.RequestException as exc:
            raise TrackerApiError(
                0, f"Red contra {self._base_url}: {exc}", kind="network"
            ) from exc

        if resp.status_code == 429 and _retry < _RETRY_MAX:
            retry_after = _resolver_retry_after(resp.headers.get("Retry-After"))
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
                # Plan 276 F9/P2-2 — un dict con HTTP 200 que NO es un ítem (un
                # `{"message": ...}`, una envoltura de error, un payload de
                # rate-limit) se appendeaba como issue FANTASMA y llegaba al
                # grafo. Solo se conserva si tiene identidad de ítem.
                if body.get("id") is not None or body.get("iid") is not None:
                    results.append(body)
                else:
                    logger.warning(
                        "GitLab devolvió un objeto sin 'id' ni 'iid' en %s (claves: %s); "
                        "se descarta en vez de contarlo como ítem.",
                        path, sorted(body.keys())[:8],
                    )

            pages_fetched += 1
            page = headers.get("X-Next-Page") or headers.get("x-next-page") or None
            if not page or not page.strip():
                break

        # Plan 276 F9/P2-1 — el techo de páginas truncaba en silencio
        # (per_page=100 x page_cap=40 = 4.000 ítems) y el operador veía una lista
        # incompleta sin ninguna señal. NO se sube el cap: se avisa.
        if page and pages_fetched >= page_cap:
            logger.warning(
                "GitLab: se alcanzó el techo de %s páginas en %s; se trajeron %s ítems y "
                "QUEDAN MÁS sin traer (próxima página: %s). El listado está TRUNCADO.",
                page_cap, path, len(results), page,
            )

        return results
