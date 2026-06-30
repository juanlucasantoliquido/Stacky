"""
Cliente Azure DevOps para Stacky Agents.

Trae work items reales del proyecto configurado (default: UbimiaPacifico/Strategist_Pacifico).
Sin dependencias extra — usa urllib stdlib.

PAT se resuelve en este orden:
  1. env ADO_PAT
  2. Tools/PAT-ADO (formato {"pat": "...", "pat_format": "preencoded|raw"})
  3. Tools/Stacky/auth/ado_auth.json (mismo formato, compatibilidad)
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import time
import uuid
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from config import config
from services.secrets_store import read_secret_from_file

logger = logging.getLogger("stacky_agents.ado")

_API_VERSION = "7.1"
_TIMEOUT_SEC = 30

# Plan 52 F1 — tope duro de páginas para la búsqueda idempotente de comentarios.
# Evita loops si ADO devolviera continuationToken indefinidamente.
_COMMENT_PAGE_CAP = 40          # 40 páginas * 200 = 8000 comentarios máximos inspeccionados
_COMMENT_PAGE_SIZE = 200        # $top por página

# Retry configuration (CA-09)
_MAX_RETRIES = 3
_RETRY_STATUS_CODES = {429, 500, 502, 503, 504}
_RETRY_BACKOFF_BASE = 1.0   # seconds; doubles each attempt
_RETRY_AFTER_MAX = 30.0     # clamp Retry-After header to 30 seconds
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
_TOOLS_ROOT = _BACKEND_ROOT.parent.parent

_DEFAULT_WIQL = (
    "SELECT [System.Id] FROM WorkItems "
    "WHERE [System.TeamProject] = @project "
    "ORDER BY [System.ChangedDate] DESC"
)

_B64_RE = re.compile(r"^[A-Za-z0-9+/=]+$")
_JSON_CONTENT_TYPES = ("application/json", "application/json;", "text/json")


class AdoConfigError(RuntimeError):
    pass


class AdoApiError(RuntimeError):
    """Error de API de ADO. Opcionalmente incluye correlation_id para trazabilidad."""

    def __init__(
        self,
        message: str,
        correlation_id: str | None = None,
        *,
        status_code: int | None = None,
        method: str | None = None,
        url: str | None = None,
        detail: str | None = None,
    ):
        super().__init__(message)
        self.correlation_id: str = correlation_id or str(uuid.uuid4())
        self.status_code: int | None = status_code
        self.method: str | None = method
        self.url: str | None = url
        self.detail: str | None = detail


def _is_signin_html(content_type: str | None, final_url: str | None, raw: str) -> bool:
    ct = (content_type or "").lower()
    url = (final_url or "").lower()
    snippet = (raw or "")[:400].lower()
    return (
        "text/html" in ct
        and ("/_signin" in url or "azure devops services | sign in" in snippet)
    )


def _looks_preencoded(raw: str) -> bool:
    return len(raw) >= 80 and bool(_B64_RE.match(raw))


def _read_pat_file(path: Path) -> str | None:
    try:
        if not path.is_file():
            return None
        resolved = read_secret_from_file(
            path,
            "pat",
            format_field="pat_format",
            allow_preencoded=True,
            detect_preencoded=True,
        )
    except Exception as e:
        logger.debug("No se pudo leer %s: %s", path, e)
        return None
    raw = resolved.value.strip()
    if not raw:
        return None
    if resolved.is_preencoded:
        return raw
    if _looks_preencoded(raw):
        return raw
    return base64.b64encode(f":{raw}".encode("utf-8")).decode("ascii")


def _resolve_active_project_defaults(
    org: str | None,
    project: str | None,
    auth_path: str | None,
) -> tuple[str | None, str | None, str | None]:
    try:
        from project_manager import find_project_for_tracker, get_active_project, get_project_config
    except Exception:
        return org, project, auth_path

    cfg: dict | None = None
    stacky_name: str | None = None

    if project:
        stacky_name, cfg = find_project_for_tracker(project)

    if cfg is None:
        active = get_active_project()
        if active:
            cfg = get_project_config(active)
            stacky_name = active

    if not cfg:
        return org, project, auth_path

    tracker = cfg.get("issue_tracker") or {}
    if (tracker.get("type") or "azure_devops").strip().lower() != "azure_devops":
        return org, project, auth_path

    resolved_org = (tracker.get("organization") or "").strip() or org
    resolved_project = (tracker.get("project") or "").strip() or project
    resolved_auth = auth_path
    if not resolved_auth and stacky_name:
        auth_rel = (tracker.get("auth_file") or "auth/ado_auth.json").strip()
        try:
            from project_manager import PROJECTS_DIR

            resolved_auth = str((PROJECTS_DIR / stacky_name.upper() / auth_rel).resolve(strict=False))
        except Exception:
            resolved_auth = str((_BACKEND_ROOT / "projects" / stacky_name.upper() / auth_rel).resolve(strict=False))
    return resolved_org, resolved_project, resolved_auth


def _resolve_auth_header(auth_path: str | Path | None = None) -> str:
    explicit_auth = Path(auth_path).expanduser() if auth_path else None
    if explicit_auth:
        token = _read_pat_file(explicit_auth)
        if token:
            return f"Basic {token}"

    raw_env = (os.environ.get("ADO_PAT") or config.ADO_PAT or "").strip()
    if raw_env:
        if _looks_preencoded(raw_env):
            return f"Basic {raw_env}"
        return f"Basic {base64.b64encode(f':{raw_env}'.encode()).decode('ascii')}"

    candidates = [
        _TOOLS_ROOT / "PAT-ADO",
        _TOOLS_ROOT / "Stacky" / "auth" / "ado_auth.json",
    ]
    for p in candidates:
        token = _read_pat_file(p)
        if token:
            return f"Basic {token}"

    raise AdoConfigError(
        "ADO PAT no encontrado. Setea ADO_PAT en backend/.env o llena Tools/PAT-ADO."
    )


def ado_pat_present(auth_path: str | Path | None = None) -> bool:
    """¿Hay un PAT de ADO resoluble? No lanza — devuelve bool.

    Útil para preflight de arranque y diag/health: el auto-create de Tasks del
    output_watcher requiere PAT; sin él la Task no se crea (causa raíz C2 del
    PLAN_FIX_REGISTRO_COMPLETION_OPENCHAT).

    Resuelve en dos niveles para no dar falsos negativos:
      1. Cadena global de `_resolve_auth_header` (env ADO_PAT, Tools/PAT-ADO, …).
      2. Auth del **proyecto activo** (`projects/<activo>/auth/ado_auth.json`), que
         es la que realmente usa el auto-create vía build_ado_client. Sin este
         segundo nivel, el health reportaba "sin PAT" aunque el proyecto sí lo
         tuviera.
    """
    try:
        _resolve_auth_header(auth_path)
        return True
    except AdoConfigError:
        pass
    except Exception:  # noqa: BLE001 — defensivo: cualquier fallo = "no presente"
        return False

    # Nivel 2: auth del proyecto activo (sólo si no se pidió un auth_path explícito).
    if auth_path is None:
        try:
            from services.project_context import resolve_project_context

            ctx = resolve_project_context()
            if ctx and ctx.auth_path:
                _resolve_auth_header(ctx.auth_path)
                return True
        except Exception:  # noqa: BLE001
            return False
    return False


class AdoClient:
    def __init__(
        self,
        org: str | None = None,
        project: str | None = None,
        auth_path: str | None = None,
    ):
        resolved_org, resolved_project, resolved_auth_path = _resolve_active_project_defaults(
            org,
            project,
            auth_path,
        )
        self.org = (resolved_org or config.ADO_ORG or "UbimiaPacifico").strip()
        self.project = (resolved_project or config.ADO_PROJECT or "Strategist_Pacifico").strip()
        self.auth_path = (resolved_auth_path or "").strip() or None
        if not self.org or not self.project:
            raise AdoConfigError("ADO_ORG y ADO_PROJECT son obligatorios.")
        self._auth = _resolve_auth_header(self.auth_path)
        self._base_proj = (
            f"https://dev.azure.com/{urllib.parse.quote(self.org)}/"
            f"{urllib.parse.quote(self.project)}"
        )

    def _headers(self, content_type: str = "application/json") -> dict[str, str]:
        return {
            "Authorization": self._auth,
            "Content-Type": content_type,
            "Accept": "application/json",
        }

    def _request(self, method: str, url: str, body: dict | list | None = None) -> dict:
        data = None if body is None else json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=self._headers(), method=method)
        try:
            with urllib.request.urlopen(req, timeout=_TIMEOUT_SEC) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                final_url = resp.geturl()
                content_type = resp.headers.get("Content-Type")
                if _is_signin_html(content_type, final_url, raw):
                    raise AdoApiError(
                        f"ADO auth redirected to sign-in for {url}. "
                        "El PAT configurado para este proyecto es inválido, expiró o no tiene acceso.",
                        status_code=401,
                        method=method,
                        url=url,
                        detail=f"content_type={content_type}; final_url={final_url}",
                    )
                if raw and not any(token in (content_type or "").lower() for token in _JSON_CONTENT_TYPES):
                    raise AdoApiError(
                        f"ADO devolvió una respuesta no JSON para {url} "
                        f"(content_type={content_type or 'unknown'}).",
                        status_code=getattr(resp, "status", None),
                        method=method,
                        url=url,
                        detail=raw[:300],
                    )
                return json.loads(raw) if raw else {}
        except AdoApiError:
            raise
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode("utf-8", errors="replace")[:500]
            except Exception:
                pass
            raise AdoApiError(
                f"ADO {method} {url} → {e.code}: {detail}",
                status_code=e.code,
                method=method,
                url=url,
                detail=detail or None,
            ) from e
        except urllib.error.URLError as e:
            raise AdoApiError(
                f"ADO network error {method} {url}: {e.reason}",
                method=method,
                url=url,
                detail=str(e.reason),
            ) from e

    def fetch_open_work_items(self, wiql: str | None = None) -> list[dict]:
        ids = self._wiql_ids(wiql or _DEFAULT_WIQL)
        if not ids:
            return []
        return self._batch_get(ids)

    def _wiql_ids(self, wiql: str) -> list[int]:
        url = f"{self._base_proj}/_apis/wit/wiql?api-version={_API_VERSION}"
        result = self._request("POST", url, {"query": wiql})
        return [int(w["id"]) for w in (result.get("workItems") or []) if w.get("id") is not None]

    def _batch_get(self, ids: list[int], page: int = 200) -> list[dict]:
        out: list[dict] = []
        fields = [
            "System.Id",
            "System.Title",
            "System.State",
            "System.Description",
            "System.WorkItemType",
            "System.AssignedTo",
            "System.ChangedDate",
            "System.Parent",
            "Microsoft.VSTS.Common.Priority",
        ]
        fields_qs = ",".join(fields)
        for i in range(0, len(ids), page):
            chunk = ids[i : i + page]
            ids_qs = ",".join(str(x) for x in chunk)
            url = (
                f"{self._base_proj}/_apis/wit/workitems"
                f"?ids={ids_qs}&fields={urllib.parse.quote(fields_qs)}"
                f"&api-version={_API_VERSION}"
            )
            data = self._request("GET", url)
            out.extend(data.get("value") or [])
        return out

    def work_item_url(self, ado_id: int) -> str:
        return f"{self._base_proj}/_workitems/edit/{ado_id}"

    def get_authenticated_user(self) -> dict:
        """Resuelve la identidad ADO del PAT configurado (usuario sincronizado).

        Usa el endpoint org-scoped `_apis/connectionData`, que devuelve el
        `authenticatedUser` asociado al token. El `unique_name` (normalmente el
        email) es el valor que se compara contra `Ticket.assigned_to_ado`
        (uniqueName de System.AssignedTo) para el filtro "Mis tareas".

        Retorna: { display_name, unique_name, id, descriptor }.
        Lanza AdoApiError si el PAT es inválido o ADO no responde JSON.
        """
        base_org = f"https://dev.azure.com/{urllib.parse.quote(self.org)}"
        url = f"{base_org}/_apis/connectionData?api-version={_API_VERSION}"
        data = self._request("GET", url)
        user = data.get("authenticatedUser") or {}
        props = user.get("properties") or {}
        account = props.get("Account")
        if isinstance(account, dict):
            email = account.get("$value") or ""
        else:
            email = account or ""
        unique_name = (
            email
            or user.get("uniqueName")
            or user.get("providerDisplayName")
            or ""
        )
        return {
            "display_name": user.get("providerDisplayName") or unique_name or "",
            "unique_name": (unique_name or "").strip(),
            "id": user.get("id") or "",
            "descriptor": user.get("subjectDescriptor") or user.get("descriptor") or "",
        }

    def fetch_states(self) -> list[str]:
        """Devuelve todos los estados definidos en el proceso del proyecto ADO.

        Recorre los work item types del proyecto y junta sus estados en el orden
        que ADO los reporta. Incluye estados que todavía no tiene asignado ningún
        work item (ej. "Technical Review"), porque consulta la definición del
        proceso y no los tickets existentes.
        """
        url = (
            f"{self._base_proj}/_apis/wit/workitemtypes"
            f"?api-version={_API_VERSION}"
        )
        data = self._request("GET", url)
        states: list[str] = []
        seen: set[str] = set()
        for wit in (data.get("value") or []):
            for st in (wit.get("states") or []):
                name = (st.get("name") or "").strip()
                if name and name not in seen:
                    seen.add(name)
                    states.append(name)
        return states

    def fetch_comments(self, ado_id: int, top: int = 20) -> list[dict]:
        """Devuelve los últimos `top` comentarios de un work item.

        Retorna lista de dicts con keys: author, date, text (HTML ya limpiado).
        Si el ADO project no soporta la API preview, devuelve lista vacía.
        """
        url = (
            f"{self._base_proj}/_apis/wit/workitems/{ado_id}/comments"
            f"?api-version=7.1-preview.3&$top={top}&order=desc"
        )
        try:
            data = self._request("GET", url)
        except AdoApiError as e:
            logger.warning("fetch_comments(%s) falló: %s", ado_id, e)
            return []
        comments = data.get("comments") or []
        out: list[dict] = []
        for c in comments:
            text_html = (c.get("text") or "").strip()
            if not text_html:
                continue
            revised_by = c.get("revisedBy") or c.get("createdBy") or {}
            author = revised_by.get("displayName") or revised_by.get("uniqueName") or "?"
            date = (c.get("revisedDate") or c.get("createdDate") or "")[:10]
            out.append({"author": author, "date": date, "text": text_html})
        return out

    def fetch_attachments(self, ado_id: int, max_text_bytes: int = 65_536) -> list[dict]:
        """Devuelve los adjuntos del work item con metadatos y contenido de texto (si aplica).

        Usa $expand=relations para obtener las relaciones AttachedFile.
        Para archivos de texto reconocidos (<=max_text_bytes), descarga el contenido.

        Retorna lista de dicts: {name, url, size, text_content (str|None)}.
        Si el ticket no tiene adjuntos o hay error, devuelve lista vacía.
        """
        _TEXT_EXTS = {".txt", ".md", ".html", ".htm", ".xml", ".json", ".csv", ".log", ".cs", ".vb", ".sql", ".py"}
        url = (
            f"{self._base_proj}/_apis/wit/workitems/{ado_id}"
            f"?$expand=relations&api-version={_API_VERSION}"
        )
        try:
            data = self._request("GET", url)
        except AdoApiError as e:
            logger.warning("fetch_attachments(%s) — GET relations falló: %s", ado_id, e)
            return []

        relations = data.get("relations") or []
        out: list[dict] = []
        for rel in relations:
            if rel.get("rel") != "AttachedFile":
                continue
            attrs = rel.get("attributes") or {}
            name = attrs.get("name") or ""
            resource_size = attrs.get("resourceSize") or 0
            attach_url = rel.get("url") or ""
            if not attach_url:
                continue

            text_content: str | None = None
            ext = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""
            if ext in _TEXT_EXTS and resource_size <= max_text_bytes:
                try:
                    req = urllib.request.Request(
                        attach_url,
                        headers={"Authorization": self._headers()["Authorization"]},
                        method="GET",
                    )
                    with urllib.request.urlopen(req, timeout=_TIMEOUT_SEC) as resp:
                        raw_bytes = resp.read(max_text_bytes + 1)
                    if len(raw_bytes) <= max_text_bytes:
                        text_content = raw_bytes.decode("utf-8", errors="replace")
                except Exception as e:
                    logger.debug("fetch_attachments(%s) — no se pudo descargar %s: %s", ado_id, name, e)

            out.append({
                "name": name,
                "url": attach_url,
                "size": resource_size,
                "text_content": text_content,
            })
        return out

    # ── Fase 2: extensiones para create_child_task ────────────────────────────

    def _request_with_retry(
        self,
        method: str,
        url: str,
        body: dict | list | None = None,
        content_type: str = "application/json",
    ) -> dict:
        """Como `_request`, pero con retry exponencial para 429/5xx (CA-09).

        Reintentos: hasta _MAX_RETRIES intentos.
        Backoff: 1s → 2s → 4s (base=1, exponencial).
        Retry-After header: respetado, clampeado a _RETRY_AFTER_MAX.
        Tras agotar reintentos: eleva AdoApiError con correlation_id.
        """
        correlation_id = str(uuid.uuid4())
        data = None if body is None else json.dumps(body).encode("utf-8")
        headers = self._headers(content_type)

        last_error: urllib.error.HTTPError | None = None

        for attempt in range(1, _MAX_RETRIES + 1):
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            try:
                with urllib.request.urlopen(req, timeout=_TIMEOUT_SEC) as resp:
                    raw = resp.read().decode("utf-8", errors="replace")
                    return json.loads(raw) if raw else {}
            except urllib.error.HTTPError as e:
                if e.code not in _RETRY_STATUS_CODES or attempt == _MAX_RETRIES:
                    detail = ""
                    try:
                        detail = e.read().decode("utf-8", errors="replace")[:500]
                    except Exception:
                        pass
                    if attempt == _MAX_RETRIES and e.code in _RETRY_STATUS_CODES:
                        logger.warning(
                            "ado_client: retry_exhausted method=%s url=%s code=%s corr=%s",
                            method, url, e.code, correlation_id,
                        )
                        raise AdoApiError(
                            f"ADO {method} {url} → {e.code}: {detail} (retries exhausted)",
                            correlation_id=correlation_id,
                        ) from e
                    raise AdoApiError(
                        f"ADO {method} {url} → {e.code}: {detail}",
                        correlation_id=correlation_id,
                    ) from e

                last_error = e
                # Calcular tiempo de espera
                retry_after_raw = getattr(e.headers, "get", lambda k, d=None: None)("Retry-After")
                if retry_after_raw:
                    try:
                        wait = min(float(retry_after_raw), _RETRY_AFTER_MAX)
                    except (ValueError, TypeError):
                        wait = _RETRY_BACKOFF_BASE * (2 ** (attempt - 1))
                else:
                    wait = _RETRY_BACKOFF_BASE * (2 ** (attempt - 1))

                logger.warning(
                    "ado_client: retry attempt=%d/%d code=%s wait=%.1fs corr=%s url=%s",
                    attempt, _MAX_RETRIES, e.code, wait, correlation_id, url,
                )
                time.sleep(wait)

            except urllib.error.URLError as e:
                raise AdoApiError(
                    f"ADO network error {method} {url}: {e.reason}",
                    correlation_id=correlation_id,
                ) from e

        # Guardrail — no debería llegar aquí
        raise AdoApiError(
            f"ADO {method} {url}: retry loop exhausted unexpectedly",
            correlation_id=correlation_id,
        )

    def create_work_item(  # Unificado WS1+WS2 (2026-05-23)
        self,
        work_item_type: str,
        title: str = "",
        description: str = "",
        initial_state: str = "",
        parent_id: int | None = None,
        # Alias de compatibilidad con la firma original de WS1
        fields: dict | None = None,
        parent_ado_id: int | None = None,
    ) -> dict:
        """Crea un work item en Azure DevOps y retorna el dict completo de la respuesta.

        Portado desde WS2 (2026-05-23) — acepta tanto la firma de WS2 (title/description/
        initial_state/parent_id) como la firma original de WS1 (fields/parent_ado_id).

        Args:
            work_item_type: Tipo de work item (ej. "Task", "Bug", "User Story").
            title:          Título del work item (nueva firma WS2).
            description:    Descripción en HTML.
            initial_state:  Estado inicial.
            parent_id:      ID del padre para relación jerárquica (nueva firma WS2).
            fields:         Dict de campos ya construidos (firma original WS1 — deprecated).
            parent_ado_id:  ID del padre — alias de parent_id (firma original WS1).

        Raises:
            AdoApiError: si la API devuelve un error HTTP.
        """
        # Compatibilidad backward con la firma original (fields + parent_ado_id)
        if fields is not None:
            patch_ops: list[dict] = [
                {"op": "add", "path": f"/fields/{field_name}", "value": value}
                for field_name, value in fields.items()
            ]
            effective_parent = parent_ado_id if parent_ado_id is not None else parent_id
            if effective_parent is not None:
                parent_url = (
                    f"https://dev.azure.com/{urllib.parse.quote(self.org)}/"
                    f"{urllib.parse.quote(self.project)}/_apis/wit/workitems/{effective_parent}"
                )
                patch_ops.append({
                    "op": "add",
                    "path": "/relations/-",
                    "value": {
                        "rel": "System.LinkTypes.Hierarchy-Reverse",
                        "url": parent_url,
                        "attributes": {"comment": "Task hija del Epic creada por Stacky Agents"},
                    },
                })
            url = (
                f"{self._base_proj}/_apis/wit/workitems/"
                f"${urllib.parse.quote(work_item_type)}"
                f"?api-version={_API_VERSION}"
            )
            return self._request_with_retry(
                "POST", url, body=patch_ops, content_type="application/json-patch+json"
            )

        # Nueva firma WS2: parámetros individuales
        url = (
            f"{self._base_proj}/_apis/wit/workitems/"
            f"${urllib.parse.quote(work_item_type)}?api-version={_API_VERSION}"
        )
        html_desc = (
            description if description.strip().startswith("<")
            else f"<p>{description}</p>"
        ) if description else ""

        patch: list[dict] = [
            {"op": "add", "path": "/fields/System.Title", "value": title},
        ]
        if html_desc:
            patch.append({"op": "add", "path": "/fields/System.Description", "value": html_desc})
        if initial_state:
            patch.append({"op": "add", "path": "/fields/System.State", "value": initial_state})

        effective_parent = parent_id if parent_id is not None else parent_ado_id
        if effective_parent is not None:
            patch.append({
                "op": "add",
                "path": "/relations/-",
                "value": {
                    "rel": "System.LinkTypes.Hierarchy-Reverse",
                    "url": (
                        f"https://dev.azure.com/{urllib.parse.quote(self.org)}/"
                        f"{urllib.parse.quote(self.project)}/_apis/wit/workitems/{effective_parent}"
                    ),
                    "attributes": {"comment": "Padre del work item"},
                },
            })

        return self._request_with_retry(
            "POST", url, body=patch, content_type="application/json-patch+json"
        )

    def upload_attachment(self, file_path: Path, file_name: str) -> dict:
        """Sube un archivo como adjunto a ADO (CA-02).

        POST _apis/wit/attachments?fileName=...&api-version={ver}
        Content-Type: application/octet-stream
        Body: contenido binario del archivo

        Returns: dict con 'id' (str UUID) y 'url' del adjunto en ADO.
        """
        file_path = Path(file_path)
        content = file_path.read_bytes()

        encoded_name = urllib.parse.quote(file_name, safe="")
        url = (
            f"{self._base_proj}/_apis/wit/attachments"
            f"?fileName={encoded_name}&api-version={_API_VERSION}"
        )
        # Construir request manualmente para body binario
        req = urllib.request.Request(
            url,
            data=content,
            headers={
                "Authorization": self._auth,
                "Content-Type": "application/octet-stream",
                "Accept": "application/json",
            },
            method="POST",
        )
        correlation_id = str(uuid.uuid4())
        try:
            with urllib.request.urlopen(req, timeout=_TIMEOUT_SEC) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode("utf-8", errors="replace")[:500]
            except Exception:
                pass
            raise AdoApiError(
                f"ADO POST attachments → {e.code}: {detail}",
                correlation_id=correlation_id,
            ) from e
        except urllib.error.URLError as e:
            raise AdoApiError(
                f"ADO network error uploading attachment: {e.reason}",
                correlation_id=correlation_id,
            ) from e

    def link_attachment_to_work_item(
        self,
        work_item_id: int,
        attachment_url: str,
        comment: str = "",
    ) -> dict:
        """Vincula un adjunto ya subido a un work item via JSON Patch (CA-02).

        PATCH _apis/wit/workitems/{id}?api-version={ver}
        Content-Type: application/json-patch+json

        Returns: dict del work item actualizado.
        """
        url = (
            f"{self._base_proj}/_apis/wit/workitems/{work_item_id}"
            f"?api-version={_API_VERSION}"
        )
        patch_ops = [
            {
                "op": "add",
                "path": "/relations/-",
                "value": {
                    "rel": "AttachedFile",
                    "url": attachment_url,
                    "attributes": {"comment": comment or "Adjunto desde Stacky Agents"},
                },
            }
        ]
        return self._request_with_retry(
            "PATCH", url, body=patch_ops, content_type="application/json-patch+json"
        )

    def post_comment(self, ado_id: int, text: str, fmt: str = "html") -> dict:
        """Publica un comentario en un work item (CA-07).

        POST _apis/wit/workitems/{id}/comments?api-version=7.1-preview.3

        Fase 1 plan creacion-tareas-comentarios-100-efectiva (2026-05-29):
        ya NO degrada silenciosamente devolviendo {}. Si ADO falla, propaga
        AdoApiError. Si responde sin id, levanta AdoApiError tambien para
        que los callers no traten "sin id" como exito. Los callers son
        responsables de decidir si esa falla es bloqueante o degradada,
        pero deben verla explicitamente.
        """
        url = (
            f"{self._base_proj}/_apis/wit/workitems/{ado_id}/comments"
            f"?api-version=7.1-preview.3"
        )
        body = {"text": text}
        response = self._request_with_retry("POST", url, body=body)
        if not isinstance(response, dict) or not response.get("id"):
            raise AdoApiError(
                f"ADO post_comment({ado_id}) no devolvio comment_id. "
                f"respuesta={str(response)[:200]}",
                method="POST",
                url=url,
                detail=str(response)[:300],
            )
        return response

    def fetch_all_comments(self, ado_id: int, marker: str | None = None) -> list[dict]:
        """Recorre TODAS las páginas de comentarios del work item (Plan 52 F1).

        Sigue `continuationToken` de la API de comments de ADO hasta agotar páginas
        o alcanzar `_COMMENT_PAGE_CAP`. Si se pasa `marker`, hace short-circuit:
        devuelve apenas encuentra una página que contenga el marker (no sigue
        paginando). Tolerante a fallos: ante cualquier AdoApiError devuelve lo
        acumulado hasta ahí. Si ADO no expone `continuationToken` corta tras 1
        página (degradación al comportamiento legacy). Devuelve dicts con la misma
        forma que fetch_comments: {author, date, text}.
        """
        out: list[dict] = []
        token: str | None = None
        for _page in range(_COMMENT_PAGE_CAP):
            url = (
                f"{self._base_proj}/_apis/wit/workitems/{ado_id}/comments"
                f"?api-version=7.1-preview.3&$top={_COMMENT_PAGE_SIZE}&order=asc"
            )
            if token:
                url += f"&continuationToken={urllib.parse.quote(str(token))}"
            try:
                data = self._request("GET", url)
            except AdoApiError as e:
                logger.warning("fetch_all_comments(%s) fallo en pagina %s: %s", ado_id, _page, e)
                return out
            for c in (data.get("comments") or []):
                text_html = (c.get("text") or "").strip()
                if not text_html:
                    continue
                revised_by = c.get("revisedBy") or c.get("createdBy") or {}
                author = revised_by.get("displayName") or revised_by.get("uniqueName") or "?"
                date = (c.get("revisedDate") or c.get("createdDate") or "")[:10]
                out.append({"author": author, "date": date, "text": text_html})
                if marker and marker in text_html:
                    return out  # short-circuit: ya basta para idempotencia
            token = data.get("continuationToken")
            if not token:
                break
        return out

    def comment_exists(self, ado_id: int, marker: str, top: int = 50) -> dict | None:
        """Busca un comentario que contenga el marcador Stacky dado.

        Plan 52 F1: recorre TODAS las páginas (no solo las `top` más recientes)
        vía fetch_all_comments con short-circuit en el marker, para que el marker
        idempotente viejo se encuentre aunque el work item tenga >50 comentarios.
        `top` se conserva en la firma por compatibilidad pero ya no limita.
        Retorna el dict del comentario o None. No lanza.
        """
        if not marker:
            return None
        # Plan 52 F1 — rollback barato sin redeploy: STACKY_COMMENT_FULL_SCAN_ENABLED
        # (default ON) escanea todas las páginas; OFF restaura el legacy de 1 página.
        _full_scan = os.getenv("STACKY_COMMENT_FULL_SCAN_ENABLED", "true").strip().lower() != "false"
        try:
            if _full_scan:
                comments = self.fetch_all_comments(ado_id, marker=marker)
            else:
                comments = self.fetch_comments(ado_id, top=top)
        except Exception:  # noqa: BLE001 — defensivo
            return None
        for c in comments:
            text_html = (c.get("text") or "")
            if marker in text_html:
                return c
        return None

    def get_work_item(self, ado_id: int, fields: list[str] | None = None) -> dict:
        """Lee un work item por ID. Util para verificacion post-creacion (Fase 1).

        Lanza AdoApiError si ADO falla o el item no existe.
        """
        fields_qs = ",".join(fields or [
            "System.Id", "System.Title", "System.State", "System.WorkItemType",
            "System.Parent", "System.AssignedTo", "System.ChangedDate",
        ])
        url = (
            f"{self._base_proj}/_apis/wit/workitems/{ado_id}"
            f"?fields={urllib.parse.quote(fields_qs)}&api-version={_API_VERSION}"
        )
        return self._request("GET", url)

    def find_child_by_marker(self, parent_ado_id: int, marker: str) -> dict | None:
        """Busca una Task hija de `parent_ado_id` cuya descripcion contenga el marcador Stacky.

        Idempotencia de creacion (Fase 2 plan creacion-tareas-comentarios-100-efectiva):
        antes de crear una Task hija, Stacky inserta un marcador invisible
        `<!-- stacky-task:{idempotency_key} -->` en System.Description. Si una
        ejecucion anterior ya creo la Task pero el receipt local se perdio, este
        metodo la reencuentra leyendo los hijos del Epic en ADO, evitando duplicar.

        Estrategia:
          1. WIQL: hijos directos del padre (System.Parent = parent_ado_id).
          2. batch GET de sus System.Description.
          3. match exacto del marcador.

        Devuelve el dict del work item hijo (campos basicos + System.Description) o
        None. No lanza: ante cualquier fallo de ADO devuelve None (el caller cae al
        flujo de creacion normal, que es seguro porque ADO igual rechaza duplicados
        logicos solo si hay otra barrera; el marcador es la barrera principal).
        """
        if not marker:
            return None
        try:
            wiql = (
                "SELECT [System.Id] FROM WorkItems "
                f"WHERE [System.Parent] = {int(parent_ado_id)}"
            )
            child_ids = self._wiql_ids(wiql)
            if not child_ids:
                return None
            for i in range(0, len(child_ids), 200):
                chunk = child_ids[i : i + 200]
                ids_qs = ",".join(str(x) for x in chunk)
                fields_qs = "System.Id,System.Title,System.State,System.Description,System.Parent"
                url = (
                    f"{self._base_proj}/_apis/wit/workitems"
                    f"?ids={ids_qs}&fields={urllib.parse.quote(fields_qs)}"
                    f"&api-version={_API_VERSION}"
                )
                data = self._request("GET", url)
                for wi in (data.get("value") or []):
                    desc = str((wi.get("fields") or {}).get("System.Description") or "")
                    if marker in desc:
                        return wi
        except Exception as exc:  # noqa: BLE001 — defensivo: cualquier fallo = "no encontrado"
            logger.warning("find_child_by_marker(parent=%s) falló: %s", parent_ado_id, exc)
            return None
        return None

    def update_work_item_state(self, ado_id: int, new_state: str) -> dict:
        """Cambia el System.State de un work item en ADO."""
        url = (
            f"{self._base_proj}/_apis/wit/workitems/{ado_id}"
            f"?api-version={_API_VERSION}"
        )
        patch_ops = [
            {"op": "add", "path": "/fields/System.State", "value": new_state}
        ]
        return self._request_with_retry(
            "PATCH", url, body=patch_ops, content_type="application/json-patch+json"
        )

    def update_work_item_assigned_to(self, ado_id: int, ado_unique_name: str) -> dict:
        """Cambia System.AssignedTo de un work item en ADO.

        P6: Se usa para asignar un ticket a una persona real desde el recomendador.
        ado_unique_name: uniqueName del usuario en ADO (ej. "jluca@ubimia.com").
        Requiere que el PAT tenga scope vso.work_write.
        """
        url = (
            f"{self._base_proj}/_apis/wit/workitems/{ado_id}"
            f"?api-version={_API_VERSION}"
        )
        patch_ops = [
            {"op": "add", "path": "/fields/System.AssignedTo", "value": ado_unique_name}
        ]
        return self._request_with_retry(
            "PATCH", url, body=patch_ops, content_type="application/json-patch+json"
        )

    def fetch_work_item_updates(self, ado_id: int, top: int = 50) -> list[dict]:
        """Devuelve el historial de revisiones de un work item (System.State, System.AssignedTo, etc.).

        Usado opcionalmente para diagnosticos. No se usa en el sync normal (Opcion B es la elegida).
        Si ADO no soporta el endpoint, devuelve lista vacia silenciosamente.
        """
        url = (
            f"{self._base_proj}/_apis/wit/workitems/{ado_id}/updates"
            f"?api-version={_API_VERSION}&$top={top}"
        )
        try:
            data = self._request("GET", url)
        except AdoApiError as e:
            logger.warning("fetch_work_item_updates(%s) falló: %s", ado_id, e)
            return []
        return data.get("value") or []
