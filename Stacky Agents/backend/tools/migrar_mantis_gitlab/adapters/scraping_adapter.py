"""tools/migrar_mantis_gitlab/adapters/scraping_adapter.py — Plan 217 F2b
(PRIMERO por orden C6 — único camino viable HOY contra soporte.ais-int.net).

Porta a Python el login web de Mantis en 2 pasos (usuario -> contraseña) y
el parsing tolerante de `view_all_bug_page.php` (listado) y `view.php`
(detalle: descripción, reporter, handler, notas/bugnotes, adjuntos,
relaciones). Usa `requests.Session()` (dependencia ya presente en el repo,
`services/mantis_client.py` la usa para SOAP) + regex/`html.unescape`
(stdlib) para parsear — sin agregar BeautifulSoup/lxml (no son dependencias
del repo hoy).

Re-login automático (C7): cualquier request autenticado que reciba de vuelta
contenido de `login_page.php` (sesión expirada) dispara un re-login con las
credenciales ya resueltas (guardadas en el propio adapter, nunca logueadas)
y reintenta la request original UNA vez. Si tras el reintento la sesión
sigue sin autenticarse, se propaga `MantisScrapingAuthError` (no se oculta
el fallo).

La sesión autenticada se expone vía `get_session()` para que
`migrator_mg_attachments.py` (otro batch, F6) pueda descargar adjuntos
binarios con la misma cookie (los adjuntos de Mantis no tienen endpoint
anónimo).
"""
from __future__ import annotations

import html as _html
import re
from typing import Any, Optional

import requests

from .base import MantisReadAdapter


class MantisScrapingAuthError(RuntimeError):
    """Login Mantis (inicial o re-login tras expiración de sesión) fallido.

    Nunca se loguean usuario/contraseña en el mensaje de esta excepción."""


# ── Detección de página de login (sesión no autenticada o expirada) ───────

_LOGIN_PAGE_MARKERS = ('name="username"', 'login.php')


def _looks_like_login_page(text: str) -> bool:
    """Heurística tolerante: la respuesta es la página de login (o volvió a
    ella) si trae el campo de usuario Y hace referencia a login.php."""
    lowered = (text or "").lower()
    return all(marker in lowered for marker in _LOGIN_PAGE_MARKERS)


# ── Extracción de campos ocultos (CSRF token, si el HTML lo trae) ─────────

def _extract_hidden_input(html_text: str, name: str) -> Optional[str]:
    """Busca `<input ... name="{name}" ... value="...">` tolerando que
    `value` venga antes o después de `name` en los atributos. Devuelve
    `None` si el campo no está presente (instalaciones sin CSRF token en
    el login clásico de 2 pasos)."""
    name_first = re.compile(
        rf'<input[^>]*name=["\']{re.escape(name)}["\'][^>]*value=["\']([^"\']*)["\']',
        re.IGNORECASE,
    )
    match = name_first.search(html_text)
    if match:
        return match.group(1)

    value_first = re.compile(
        rf'<input[^>]*value=["\']([^"\']*)["\'][^>]*name=["\']{re.escape(name)}["\']',
        re.IGNORECASE,
    )
    match = value_first.search(html_text)
    if match:
        return match.group(1)
    return None


# ── Parsing HTML tolerante (regex + html.unescape, sin bs4/lxml) ──────────

_TAG_RE = re.compile(r"<[^>]+>")
_CELL_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.IGNORECASE | re.DOTALL)
_ROW_RE = re.compile(r'<tr[^>]*\sid=["\']row_(\d+)["\'][^>]*>(.*?)</tr>', re.IGNORECASE | re.DOTALL)
_ISSUE_LINK_RE = re.compile(r'href=["\']view\.php\?id=(\d+)["\']', re.IGNORECASE)
_BUGNOTE_ROW_RE = re.compile(r'<tr class="bugnote">(.*?)</tr>', re.IGNORECASE | re.DOTALL)
_ATTACHMENT_ROW_RE = re.compile(r'<tr class="attachment-row">(.*?)</tr>', re.IGNORECASE | re.DOTALL)
_RELATIONSHIP_ROW_RE = re.compile(r'<tr class="relationship-row">(.*?)</tr>', re.IGNORECASE | re.DOTALL)
_FILE_ID_RE = re.compile(r"file_id=(\d+)")
_HREF_RE = re.compile(r'href=["\']([^"\']+)["\']')
_LABELED_ROW_RE = re.compile(
    r'<tr>\s*<td class="bug-label">([^<]*)</td>\s*<td class="bug-value">(.*?)</td>\s*</tr>',
    re.IGNORECASE | re.DOTALL,
)


def _strip_tags(fragment: str) -> str:
    return _html.unescape(_TAG_RE.sub("", fragment or "")).strip()


def _parse_issue_list_html(html_text: str, project_id: int) -> list[dict[str, Any]]:
    """Parsea la tabla de `view_all_bug_page.php`: al menos id/summary/status/
    priority/link por fila. Tolerante: filas sin las 5 columnas esperadas
    simplemente devuelven cadenas vacías en los campos faltantes."""
    issues: list[dict[str, Any]] = []
    for row_match in _ROW_RE.finditer(html_text):
        row_id, row_html = row_match.group(1), row_match.group(2)
        link_match = _ISSUE_LINK_RE.search(row_html)
        issue_id = int(link_match.group(1)) if link_match else int(row_id)
        cells = [_strip_tags(c) for c in _CELL_RE.findall(row_html)]
        issues.append({
            "id": issue_id,
            "summary": cells[2] if len(cells) > 2 else "",
            "status": cells[3] if len(cells) > 3 else "",
            "priority": cells[4] if len(cells) > 4 else "",
            "project_id": project_id,
        })
    return issues


def _parse_issue_detail_html(html_text: str, issue_id: int) -> dict[str, Any]:
    """Parsea la tabla `bug-description-table` de `view.php` a un dict plano
    `{label: valor}` más los campos estructurados (notas/adjuntos/relaciones)."""
    fields: dict[str, str] = {}
    for label_match in _LABELED_ROW_RE.finditer(html_text):
        label = label_match.group(1).strip().lower()
        fields[label] = _strip_tags(label_match.group(2))

    return {
        "id": issue_id,
        "summary": fields.get("summary", ""),
        "reporter": fields.get("reporter", ""),
        "handler": fields.get("handler", ""),
        "status": fields.get("status", ""),
        "priority": fields.get("priority", ""),
        "description": fields.get("description", ""),
        "steps_to_reproduce": fields.get("steps_to_reproduce", ""),
        "additional_information": fields.get("additional_information", ""),
        "notes": _parse_bugnotes_html(html_text),
        "attachments": _parse_attachments_html(html_text),
        "relationships": _parse_relationships_html(html_text),
    }


def _parse_bugnotes_html(html_text: str) -> list[dict[str, Any]]:
    notes: list[dict[str, Any]] = []
    for row_match in _BUGNOTE_ROW_RE.finditer(html_text):
        cells = [_strip_tags(c) for c in _CELL_RE.findall(row_match.group(1))]
        if len(cells) < 3:
            continue
        notes.append({"reporter": cells[0], "date": cells[1], "text": cells[2]})
    return notes


def _parse_attachments_html(html_text: str) -> list[dict[str, Any]]:
    attachments: list[dict[str, Any]] = []
    for row_match in _ATTACHMENT_ROW_RE.finditer(html_text):
        cells = _CELL_RE.findall(row_match.group(1))
        if not cells:
            continue
        link_cell = cells[0]
        href_match = _HREF_RE.search(link_cell)
        file_id_match = _FILE_ID_RE.search(link_cell)
        size_text = _strip_tags(cells[1]) if len(cells) > 1 else ""
        attachments.append({
            "id": file_id_match.group(1) if file_id_match else "",
            "name": _strip_tags(link_cell),
            "size": int(size_text) if size_text.isdigit() else 0,
            "url": href_match.group(1) if href_match else "",
        })
    return attachments


def _parse_relationships_html(html_text: str) -> list[dict[str, Any]]:
    relationships: list[dict[str, Any]] = []
    for row_match in _RELATIONSHIP_ROW_RE.finditer(html_text):
        cells = _CELL_RE.findall(row_match.group(1))
        if len(cells) < 2:
            continue
        rel_type = _strip_tags(cells[0])
        target_match = _ISSUE_LINK_RE.search(cells[1])
        relationships.append({
            "type": rel_type,
            "target_issue_id": int(target_match.group(1)) if target_match else None,
        })
    return relationships


# ── Adapter ─────────────────────────────────────────────────────────────

class MantisWebScrapingReadAdapter(MantisReadAdapter):
    """Extractor de origen Mantis vía login web (2 pasos) + parsing HTML.

    Único camino viable HOY contra `soporte.ais-int.net` (SOAP deshabilitado,
    tokens REST no disponibles — evidencia §0/§20 del Plan 217)."""

    def __init__(
        self,
        base_url: str,
        project_ids: list[int],
        username: str,
        password: str,
        *,
        session: Optional[requests.Session] = None,
        timeout: int = 30,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._project_ids = list(project_ids)
        self._username = username
        self._password = password
        self._session = session if session is not None else requests.Session()
        self._timeout = timeout
        self._authenticated = False

    # ── Login (2 pasos) + re-login automático (C7) ────────────────────

    def _http_get(self, url: str) -> str:
        resp = self._session.get(url, timeout=self._timeout)
        return resp.text

    def _http_post(self, url: str, data: dict) -> str:
        resp = self._session.post(url, data=data, timeout=self._timeout)
        return resp.text

    def _login(self) -> None:
        self._authenticated = False

        login_page_html = self._http_get(f"{self._base_url}/login_page.php")
        csrf_step1 = _extract_hidden_input(login_page_html, "csrf_token")

        step1_data: dict[str, str] = {"username": self._username}
        if csrf_step1:
            step1_data["csrf_token"] = csrf_step1
        step2_html = self._http_post(f"{self._base_url}/login.php", step1_data)

        if _looks_like_login_page(step2_html):
            raise MantisScrapingAuthError(
                "Login Mantis fallido (paso 1 - usuario): la respuesta volvió "
                "a la página de login. Verificá el usuario configurado."
            )

        csrf_step2 = _extract_hidden_input(step2_html, "csrf_token")
        step2_data: dict[str, str] = {
            "username": self._username,
            "password": self._password,
        }
        if csrf_step2:
            step2_data["csrf_token"] = csrf_step2
        final_html = self._http_post(f"{self._base_url}/login_password_page.php", step2_data)

        if _looks_like_login_page(final_html):
            raise MantisScrapingAuthError(
                "Login Mantis fallido (paso 2 - contraseña): la respuesta "
                "volvió a la página de login. Verificá usuario/contraseña."
            )

        self._authenticated = True

    def _ensure_authenticated(self) -> None:
        if not self._authenticated:
            self._login()

    def _authenticated_get(self, url: str) -> str:
        """GET autenticado con re-login automático ante sesión expirada (C7):
        si la respuesta es la página de login, re-loguea UNA vez y reintenta
        la request original. Si sigue fallando, propaga `MantisScrapingAuthError`
        (nunca se oculta el fallo devolviendo datos vacíos en silencio)."""
        self._ensure_authenticated()
        text = self._http_get(url)
        if _looks_like_login_page(text):
            self._login()
            text = self._http_get(url)
            if _looks_like_login_page(text):
                raise MantisScrapingAuthError(
                    "La sesión Mantis expiró a mitad de la corrida y el "
                    "re-login automático también falló."
                )
        return text

    def get_session(self) -> requests.Session:
        """Expone la sesión/cookie autenticada (C7) para que
        `migrator_mg_attachments.py` (otro batch, F6) descargue adjuntos
        binarios reusando la misma cookie de sesión (no hay endpoint anónimo)."""
        self._ensure_authenticated()
        return self._session

    # ── MantisReadAdapter ───────────────────────────────────────────────

    def fetch_all_issues(self) -> list[dict[str, Any]]:
        all_issues: list[dict[str, Any]] = []
        for project_id in self._project_ids:
            url = f"{self._base_url}/view_all_bug_page.php?project_id={project_id}"
            html_text = self._authenticated_get(url)
            all_issues.extend(_parse_issue_list_html(html_text, project_id))
        return all_issues

    def fetch_comments(self, issue_id: int) -> list[dict[str, Any]]:
        html_text = self._authenticated_get(f"{self._base_url}/view.php?id={issue_id}")
        return _parse_bugnotes_html(html_text)

    def fetch_attachments(self, issue_id: int) -> list[dict[str, Any]]:
        html_text = self._authenticated_get(f"{self._base_url}/view.php?id={issue_id}")
        return _parse_attachments_html(html_text)

    def fetch_relationships(self, issue_id: int) -> list[dict[str, Any]]:
        html_text = self._authenticated_get(f"{self._base_url}/view.php?id={issue_id}")
        return _parse_relationships_html(html_text)

    def download_attachment_binary(self, file_id: "str | int") -> bytes:
        """Descarga el binario crudo de un adjunto vía `file_download.php`
        (endpoint estándar de Mantis para adjuntos, reusando la MISMA
        sesión/cookie autenticada que el resto del adapter — C7 del plan:
        "requieren cookie de sesión, no hay endpoint anónimo"). Re-login
        automático (mismo criterio que `_authenticated_get`, pero mirando
        `Content-Type` en vez de decodificar el binario como texto: un
        adjunto real puede tener bytes que no son UTF-8 válido, así que
        NUNCA se intenta `.text` sobre la respuesta salvo que el
        `Content-Type` indique HTML — eso evita un `UnicodeDecodeError`
        espurio sobre un PNG/ZIP real)."""
        self._ensure_authenticated()
        url = f"{self._base_url}/file_download.php?file_id={file_id}"

        resp = self._session.get(url, timeout=self._timeout)
        if self._response_is_login_page(resp):
            self._login()
            resp = self._session.get(url, timeout=self._timeout)
            if self._response_is_login_page(resp):
                raise MantisScrapingAuthError(
                    "La sesión Mantis expiró al descargar el adjunto "
                    f"(file_id={file_id}) y el re-login automático también falló."
                )
        return resp.content

    @staticmethod
    def _response_is_login_page(resp) -> bool:
        content_type = (resp.headers.get("Content-Type", "") or "").lower()
        if "text/html" not in content_type:
            return False
        return _looks_like_login_page(resp.text)

    # ── Extensión no-abstracta (detalle completo de un issue) ───────────

    def fetch_issue_detail(self, issue_id: int) -> dict[str, Any]:
        """No forma parte de `MantisReadAdapter` (que separa comments/
        attachments/relationships), pero se expone porque una sola carga de
        `view.php?id=X` ya trae todo — útil para el núcleo de migración
        (fases posteriores) evitando 3 requests redundantes si lo prefiere."""
        html_text = self._authenticated_get(f"{self._base_url}/view.php?id={issue_id}")
        return _parse_issue_detail_html(html_text, issue_id)


__all__ = ["MantisScrapingAuthError", "MantisWebScrapingReadAdapter"]
