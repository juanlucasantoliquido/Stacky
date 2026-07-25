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
import unicodedata
from typing import Any, Optional

import requests

from .base import MantisReadAdapter


class MantisScrapingAuthError(RuntimeError):
    """Login Mantis (inicial o re-login tras expiración de sesión) fallido.

    Nunca se loguean usuario/contraseña en el mensaje de esta excepción."""


# ── Detección de página de login (sesión no autenticada o expirada) ───────

# Marcador POSITIVO de sesión autenticada: Mantis renderiza el link de
# logout en la barra de navegación de toda página autenticada, y NUNCA en
# las páginas de login. Es el discriminante fiable.
_AUTHENTICATED_MARKER = "logout_page.php"

# Marcadores de "esto es un formulario de login" (paso 1 usuario o paso 2
# contraseña). Verificados contra la instancia real: `login_page.php` postea
# a `login_password_page.php`, y esa página postea a `login.php`.
_LOGIN_FORM_MARKERS = (
    "login_password_page.php",
    'action="login.php"',
    "action='login.php'",
)

_PASSWORD_FIELD_RE = re.compile(r'name=["\']password["\']', re.IGNORECASE)


def _looks_like_login_page(text: str) -> bool:
    """La respuesta es una página de login (sesión no autenticada o expirada).

    OJO — la heurística original ('name="username"' Y 'login.php' presentes)
    estaba ROTA contra Mantis real: el `login_page.php` real NO contiene el
    literal `login.php` (su form postea a `login_password_page.php`), así que
    jamás detectaba ni un login fallido ni una sesión expirada. Se reemplaza
    por: autenticada si trae el link de logout; si no, es login cuando trae
    cualquier marcador de formulario de login.
    """
    lowered = (text or "").lower()
    if _AUTHENTICATED_MARKER in lowered:
        return False
    return any(marker in lowered for marker in _LOGIN_FORM_MARKERS)


def _has_password_field(text: str) -> bool:
    """El paso 1 del login fue aceptado si Mantis devuelve el formulario de
    contraseña (la página de usuario no lo tiene)."""
    return bool(_PASSWORD_FIELD_RE.search(text or ""))


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


def _normalize_label(raw: str) -> str:
    """Normaliza una etiqueta de `view.php` para comparar sin depender de
    acentos, mayúsculas ni espaciado (`"Información adicional"` ->
    `"informacion adicional"`)."""
    text = _html.unescape(raw or "").strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[\s_]+", " ", text).strip(" :")


# Mantis renderiza las etiquetas de `view.php` EN EL IDIOMA DE LA INSTANCIA.
# La instancia de referencia (soporte.ais-int.net) está en ESPAÑOL, así que
# buscar solo claves en inglés devolvía el detalle 100% vacío. Se aceptan
# ambos idiomas (y las variantes habituales de la traducción es_ES).
_LABEL_ALIASES: dict[str, tuple[str, ...]] = {
    "summary": ("summary", "resumen"),
    "reporter": ("reporter", "reportador", "informador", "reportado por"),
    "handler": ("handler", "assigned to", "asignado a", "responsable"),
    "status": ("status", "estado"),
    "priority": ("priority", "prioridad"),
    "severity": ("severity", "gravedad", "severidad"),
    "category": ("category", "categoria"),
    "description": ("description", "descripcion"),
    "steps_to_reproduce": (
        "steps to reproduce", "pasos para reproducir", "pasos a reproducir",
    ),
    "additional_information": (
        "additional information", "informacion adicional", "info adicional",
    ),
    "target_version": ("target version", "version objetivo", "version destino"),
    "fixed_in_version": ("fixed in version", "corregido en version"),
    "version": ("version", "producto version"),
    "tags": ("tags", "etiquetas"),
}


def _parse_issue_detail_html(html_text: str, issue_id: int) -> dict[str, Any]:
    """Parsea la tabla `bug-description-table` de `view.php` a un dict plano
    `{label: valor}` más los campos estructurados (notas/adjuntos/relaciones).

    Tolerante al idioma de la instancia (ver `_LABEL_ALIASES`)."""
    fields: dict[str, str] = {}
    for label_match in _LABELED_ROW_RE.finditer(html_text):
        label = _normalize_label(label_match.group(1))
        fields[label] = _strip_tags(label_match.group(2))

    def pick(canonical: str) -> str:
        for alias in _LABEL_ALIASES.get(canonical, (canonical,)):
            value = fields.get(_normalize_label(alias))
            if value:
                return value
        return ""

    detail = {
        "id": issue_id,
        "notes": _parse_bugnotes_html(html_text),
        "attachments": _parse_attachments_html(html_text),
        "relationships": _parse_relationships_html(html_text),
    }
    for canonical in _LABEL_ALIASES:
        detail[canonical] = pick(canonical)
    return detail


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
        """Login web de Mantis en 2 pasos, verificado contra la instancia real.

        Flujo REAL (comprobado en vivo contra soporte.ais-int.net):
          1. GET  /login_page.php            -> form action="login_password_page.php"
                                                campos: username + hidden `return`
          2. POST /login_password_page.php   -> form action="login.php"
                                                campos: password + hidden username/`return`
          3. POST /login.php                 -> autentica y redirige a `return`

        (La versión anterior posteaba a `login.php` PRIMERO y a
        `login_password_page.php` después — invertido — por lo que jamás
        habría podido autenticarse contra un Mantis real.)
        """
        self._authenticated = False

        login_page_html = self._http_get(f"{self._base_url}/login_page.php")
        return_to = _extract_hidden_input(login_page_html, "return") or "index.php"

        # Paso 1 — usuario. El form de login_page.php postea a login_password_page.php.
        step1_data: dict[str, str] = {"username": self._username, "return": return_to}
        csrf_step1 = _extract_hidden_input(login_page_html, "csrf_token")
        if csrf_step1:
            step1_data["csrf_token"] = csrf_step1
        password_page_html = self._http_post(
            f"{self._base_url}/login_password_page.php", step1_data
        )

        # Éxito del paso 1 = Mantis devolvió el formulario de contraseña.
        if not _has_password_field(password_page_html):
            raise MantisScrapingAuthError(
                "Login Mantis fallido (paso 1 - usuario): la respuesta no trae "
                "el formulario de contraseña. Verificá el usuario configurado."
            )

        # Paso 2 — contraseña. Ese form postea a login.php.
        return_to = _extract_hidden_input(password_page_html, "return") or return_to
        step2_data: dict[str, str] = {
            "username": self._username,
            "password": self._password,
            "return": return_to,
        }
        csrf_step2 = _extract_hidden_input(password_page_html, "csrf_token")
        if csrf_step2:
            step2_data["csrf_token"] = csrf_step2
        final_html = self._http_post(f"{self._base_url}/login.php", step2_data)

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
