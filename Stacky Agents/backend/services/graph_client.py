"""Plan 283 F4 - Cliente de Microsoft Graph: ingreso por codigo de dispositivo +
lectura. Sin dependencias nuevas y sin tocar la red en los tests.

SUPUESTOS DE PLATAFORMA, NO DEL REPO (D2). Los `scope` exactos, que el tenant
habilite el ingreso por codigo de dispositivo, y la ruta de transcripcion para
quien NO es el organizador, son hechos de Microsoft que ningun `grep` sobre este
repo puede verificar. Por eso existe D1: si alguno falla se pierde este archivo
y la mitad de `meetings_source`, y NADA MAS — el camino manual entrega minutas
igual. Tratá `DEFAULT_SCOPES` como valor por defecto EDITABLE, no como verdad.

TLS. Graph es un servicio publico con certificado de CA publica, asi que aca NO
se monta el adaptador OpenSSL de `gitlab_client` (ese existe porque los GitLab
internos presentan CA privada). Pero ojo: `backend/app.py` llama
`truststore.inject_into_ssl()`, que es GLOBAL AL PROCESO, asi que la
verificacion va por el almacen de certificados del sistema operativo y no por
`certifi`. Para Graph eso es bueno y necesario: es justamente lo que hace que
funcione detras de una inspeccion TLS corporativa. TRES PROHIBICIONES, las tres
ya escritas en el repo:
  - PROHIBIDO tocar `REQUESTS_CA_BUNDLE` (global al proceso; rompe ADO/Jira/LLM).
  - PROHIBIDO llamar `truststore.extract_from_ssl()` (desarma el TLS de todo el
    backend; la prohibicion es literal en `services/tls_openssl_context.py`).
  - PROHIBIDO pasar `verify=<ruta>` en las llamadas a Graph: con truststore
    inyectado el efecto es el CONTRARIO al esperado y se manifiesta como
    `RecursionError`, no como error de TLS. Es la causa raiz que el plan 276
    tardo en encontrar.
"""
from __future__ import annotations

import pathlib
from datetime import datetime

import requests

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
AUTH_BASE = "https://login.microsoftonline.com"
# Valor por defecto EDITABLE (D2): son hechos de la plataforma Microsoft.
DEFAULT_SCOPES = ("offline_access", "Calendars.Read", "OnlineMeetingTranscript.Read.All")
# El default del tenant vive ACA, no en config.py ni en la FlagSpec: una flag
# `str` no puede declarar `default=` sin romper la biyeccion del arnes, asi que
# si config.py resolviera "common" el panel mostraria "" y estaria mintiendo.
DEFAULT_TENANT = "common"
# Molde: services/gitlab_client.py usa timeout=20 en cada llamada. Importa mas
# aca que alla: `POST /transcript` importa y destila en el MISMO request
# sincrono, asi que un Graph colgado sin timeout cuelga la pantalla.
GRAPH_TIMEOUT_S = 20

DEVICE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"


class GraphConfigError(RuntimeError):
    """Falta configuracion (identificador de aplicacion, credencial guardada)."""


class GraphApiError(RuntimeError):
    """Molde LITERAL de `TrackerApiError`: `status` es POSICIONAL y obligatorio.

    Construirlo con `GraphApiError(status=401, ...)` revienta a proposito: asi
    se parece exactamente al error del tracker y nadie tiene que recordar dos
    convenciones distintas.
    """

    def __init__(self, status: int, message: str, *, kind: str = "unknown"):
        super().__init__(message)
        self.status = status
        self.kind = kind


def _kind_for_status(status: int) -> str:
    """Molde: `gitlab_client._kind_for_status`.

    Hay dos `kind` que NO nacen de un status HTTP y por eso no aparecen aca:
    `"timeout"` y `"network"`. Se asignan en los `except` de `_request`, cuando
    la llamada muere ANTES de tener respuesta.
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


def parse_iso_utc(value) -> datetime | None:
    """ISO con `Z` u offset -> `datetime` NAIVE UTC. Mismo criterio que
    `services/ado_sync._parse_iso`, que es la convencion del repo."""
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:  # noqa: BLE001
        return None


def resolve_graph_auth_path(project: str) -> pathlib.Path:
    """`backend/projects/<PROYECTO>/auth/graph_auth.json`.

    Molde: `project_manager.resolve_gitlab_auth_path`. Se importa perezoso para
    no arrastrar el gestor de proyectos al importar este modulo.
    """
    from runtime_paths import projects_dir

    return pathlib.Path(projects_dir()) / str(project or "").upper() / "auth" / "graph_auth.json"


class GraphClient:
    """Cliente HTTP de Graph. Instancia liviana: NO hace red en `__init__`.

    `transport=None` monta una `requests.Session()` PROPIA (molde
    `gitlab_client`). `transport != None` se usa tal cual: ES EL SEAM DE TEST, y
    es lo que permite que los 11 casos de esta fase corran con CERO red.
    """

    def __init__(
        self,
        *,
        tenant: str | None = None,
        client_id: str | None = None,
        auth_path: str | pathlib.Path | None = None,
        transport=None,
    ):
        self._tenant = (tenant or "").strip() or DEFAULT_TENANT
        self._client_id = (client_id or "").strip()
        self._auth_path = pathlib.Path(auth_path) if auth_path else None
        # Sesion propia SOLO si no inyectaron transporte. Sin red todavia.
        self._transport = transport if transport is not None else requests.Session()
        # Credencial de acceso cacheada POR INSTANCIA. `get_transcript` hace dos
        # llamadas seguidas: sin esto renovaria la sesion dos veces por una sola
        # operacion del operador. La instancia vive lo que dura el pedido.
        self._acceso: str | None = None

    # ── HTTP ──────────────────────────────────────────────────────────────
    def _request(self, method: str, url: str, *, headers=None, params=None, data=None):
        """UNICO punto de salida del modulo. Todo pasa `timeout=`.

        No se pasa `verify=`: ver la prohibicion del encabezado.
        """
        try:
            resp = self._transport.request(
                method,
                url,
                headers=headers,
                params=params,
                data=data,
                timeout=GRAPH_TIMEOUT_S,
            )
        except requests.exceptions.Timeout as exc:
            raise GraphApiError(
                0, f"Microsoft no respondio en {GRAPH_TIMEOUT_S} segundos: {exc}", kind="timeout"
            ) from exc
        except requests.exceptions.RequestException as exc:
            raise GraphApiError(0, f"Error de red contra Microsoft: {exc}", kind="network") from exc
        return resp

    @staticmethod
    def _json(resp) -> dict:
        try:
            cuerpo = resp.json()
        except Exception:  # noqa: BLE001 - una respuesta no-JSON no puede tumbar el request
            return {}
        return cuerpo if isinstance(cuerpo, dict) else {"value": cuerpo}

    @staticmethod
    def _status(resp) -> int:
        return int(getattr(resp, "status_code", 0) or 0)

    def _elevar(self, resp, contexto: str) -> None:
        status = self._status(resp)
        if status >= 400:
            raise GraphApiError(
                status,
                f"{contexto}: Microsoft respondio {status}",
                kind=_kind_for_status(status),
            )

    # ── Ingreso por codigo de dispositivo (D2) ────────────────────────────
    def start_device_login(self) -> dict:
        if not self._client_id:
            raise GraphConfigError(
                "Falta el identificador de la aplicacion registrada en Microsoft. "
                "Cargalo en el panel de configuracion y volvé a intentar."
            )
        url = f"{AUTH_BASE}/{self._tenant}/oauth2/v2.0/devicecode"
        resp = self._request(
            "POST", url,
            data={"client_id": self._client_id, "scope": " ".join(DEFAULT_SCOPES)},
        )
        self._elevar(resp, "Inicio del ingreso")
        cuerpo = self._json(resp)
        return {
            "user_code": str(cuerpo.get("user_code") or ""),
            "verification_uri": str(
                cuerpo.get("verification_uri") or cuerpo.get("verification_url") or ""
            ),
            "device_code": str(cuerpo.get("device_code") or ""),
            "expires_in": int(cuerpo.get("expires_in") or 900),
            "interval": int(cuerpo.get("interval") or 5),
        }

    def poll_device_login(self, device_code: str) -> dict:
        if not self._client_id:
            raise GraphConfigError("Falta el identificador de la aplicacion registrada.")
        url = f"{AUTH_BASE}/{self._tenant}/oauth2/v2.0/token"
        resp = self._request("POST", url, data={
            "client_id": self._client_id,
            "grant_type": DEVICE_GRANT,
            "device_code": device_code,
        })
        cuerpo = self._json(resp)
        error = str(cuerpo.get("error") or "")
        if error == "authorization_pending":
            # NO es un error: el operador todavia no termino de escribir el codigo.
            return {"estado": "pending", "detalle": "Esperando que confirmes en el navegador."}
        if error == "authorization_declined":
            return {"estado": "rechazado", "detalle": "Rechazaste el pedido de permiso."}
        if error in ("expired_token", "code_expired"):
            return {"estado": "vencido", "detalle": "El codigo vencio. Empezá de nuevo."}

        refresh = str(cuerpo.get("refresh_token") or "")
        if not refresh:
            self._elevar(resp, "Confirmacion del ingreso")
            raise GraphApiError(
                self._status(resp) or 400,
                f"Microsoft no devolvio credencial de sesion ({error or 'sin detalle'}).",
                kind="auth",
            )
        self._guardar_refresh(refresh)
        return {"estado": "ok", "detalle": "Ingreso confirmado."}

    def _guardar_refresh(self, refresh_token: str) -> None:
        from services import secrets_store

        if self._auth_path is None:
            raise GraphConfigError("No se resolvio donde guardar la credencial de sesion.")
        payload = secrets_store.load_json_file(self._auth_path) or {}
        payload["tenant"] = self._tenant
        payload["client_id"] = self._client_id
        secrets_store.set_encrypted_secret(
            payload, "refresh_token", refresh_token, format_field="refresh_token_format"
        )
        secrets_store.write_json_file(self._auth_path, payload)

    def _leer_refresh(self) -> str:
        from services import secrets_store

        if self._auth_path is None or not pathlib.Path(self._auth_path).is_file():
            raise GraphConfigError(
                "Todavia no hiciste el ingreso con tu cuenta de Microsoft en este proyecto."
            )
        # OJO, trampa documentada del repo: `read_secret_from_file` NO es solo
        # lectura — si encuentra el secreto en claro lo cifra y REESCRIBE el
        # archivo. Es el comportamiento deseado; el test no debe sorprenderse.
        resuelto = secrets_store.read_secret_from_file(
            self._auth_path, "refresh_token", format_field="refresh_token_format"
        )
        valor = (resuelto.value or "").strip()
        if not valor:
            raise GraphConfigError("La credencial de sesion guardada esta vacia. Volvé a ingresar.")
        return valor

    def _access_token(self) -> str:
        if self._acceso:
            return self._acceso
        if not self._client_id:
            raise GraphConfigError("Falta el identificador de la aplicacion registrada.")
        refresh = self._leer_refresh()
        url = f"{AUTH_BASE}/{self._tenant}/oauth2/v2.0/token"
        resp = self._request("POST", url, data={
            "client_id": self._client_id,
            "grant_type": "refresh_token",
            "refresh_token": refresh,
            "scope": " ".join(DEFAULT_SCOPES),
        })
        self._elevar(resp, "Renovacion de la sesion")
        cuerpo = self._json(resp)
        nuevo_refresh = str(cuerpo.get("refresh_token") or "")
        if nuevo_refresh and nuevo_refresh != refresh:
            self._guardar_refresh(nuevo_refresh)
        acceso = str(cuerpo.get("access_token") or "")
        if not acceso:
            raise GraphApiError(
                self._status(resp) or 401, "Microsoft no renovo la sesion.", kind="auth"
            )
        self._acceso = acceso
        return acceso

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._access_token()}",
            "Accept": "application/json",
            "Prefer": 'outlook.timezone="UTC"',
        }

    # ── Lectura ───────────────────────────────────────────────────────────
    def list_events(self, *, desde: datetime, hasta: datetime) -> list[dict]:
        resp = self._request(
            "GET",
            f"{GRAPH_BASE}/me/calendarView",
            headers=self._headers(),
            params={
                "startDateTime": desde.isoformat(),
                "endDateTime": hasta.isoformat(),
                "$top": 50,
            },
        )
        self._elevar(resp, "Lectura del calendario")
        crudos = self._json(resp).get("value") or []
        eventos: list[dict] = []
        for evento in crudos:
            if not isinstance(evento, dict):
                continue
            copia = dict(evento)
            # Naive UTC SIEMPRE: es la convencion del repo y lo que espera SQLite.
            copia["start_at"] = parse_iso_utc((evento.get("start") or {}).get("dateTime"))
            copia["end_at"] = parse_iso_utc((evento.get("end") or {}).get("dateTime"))
            eventos.append(copia)
        return eventos

    def get_transcript(self, *, meeting_id: str) -> str | None:
        """El texto de la transcripcion, o `None` si la reunion no tiene.

        Un 404 NO es error: hay reuniones sin transcripcion, y tratarlo como
        fallo obligaria a la pantalla a pintar un error donde no pasa nada.
        """
        listado = self._request(
            "GET",
            f"{GRAPH_BASE}/me/onlineMeetings/{meeting_id}/transcripts",
            headers=self._headers(),
        )
        if self._status(listado) == 404:
            return None
        self._elevar(listado, "Listado de transcripciones")
        entradas = self._json(listado).get("value") or []
        if not entradas:
            return None
        transcript_id = str((entradas[0] or {}).get("id") or "")
        if not transcript_id:
            return None

        contenido = self._request(
            "GET",
            f"{GRAPH_BASE}/me/onlineMeetings/{meeting_id}/transcripts/{transcript_id}/content",
            headers=self._headers(),
            params={"$format": "text/vtt"},
        )
        if self._status(contenido) == 404:
            return None
        self._elevar(contenido, "Descarga de la transcripcion")
        return getattr(contenido, "text", "") or ""
