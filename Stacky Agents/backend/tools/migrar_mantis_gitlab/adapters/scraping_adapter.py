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

from services.mantis_client import _STANDARD_STATUS_IDS

from .base import MantisReadAdapter


class MantisScrapingAuthError(RuntimeError):
    """Login Mantis (inicial o re-login tras expiración de sesión) fallido.

    Nunca se loguean usuario/contraseña en el mensaje de esta excepción."""


class MantisScrapingPaginationError(RuntimeError):
    """Se alcanzó el tope de páginas del listado y Mantis seguía devolviendo
    issues nuevos. Se aborta en vez de truncar en silencio: migrar "una
    parte" del proyecto creyendo que es el total es peor que fallar."""


# Tope de seguridad del paginado del listado (anti-loop infinito). Con el
# `page_size` default (500) cubre 100k issues por proyecto.
_MAX_LIST_PAGES = 200


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


# ── Parsing del listado real de Mantis (`view_all_bug_page.php`) ─────────
#
# Estructura REAL verificada en vivo contra la instancia de referencia: la
# tabla NO usa `<tr id="row_N">` (eso era una invención del fixture original,
# por lo que el parser devolvía 0 issues contra el servidor real). Cada fila
# es un `<tr>` cuyas celdas se identifican por `class="column-XXX"`:
#   column-id        -> <a href="...view.php?id=22511">0022511</a>
#   column-summary   -> <a href="view.php?id=22511">Título…</a>
#   column-status    -> <i class="... status-20-fg"></i><span>texto</span>
#   column-priority  -> <i class="fa …" title="normal"></i>   (¡en el title!)
#   column-severity  -> texto
#   column-category  -> [proyecto] Categoría
_ANY_ROW_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.IGNORECASE | re.DOTALL)
_COLUMN_CELL_RE = re.compile(
    r'<td[^>]*class=["\'][^"\']*column-([a-z-]+)[^"\']*["\'][^>]*>(.*?)</td>',
    re.IGNORECASE | re.DOTALL,
)
_ANY_ISSUE_LINK_RE = re.compile(r'href=["\'][^"\']*view\.php\?id=(\d+)', re.IGNORECASE)
_TITLE_ATTR_RE = re.compile(r'title=["\']([^"\']*)["\']', re.IGNORECASE)
# El ID numérico de estado va en la clase `status-NN-fg`: es INMUNE al idioma
# de la instancia (a diferencia del texto visible, que está traducido).
_STATUS_CLASS_RE = re.compile(r"status-(\d+)-", re.IGNORECASE)


def _status_name_from_row(cell_html: str) -> str:
    """Nombre canónico en inglés del estado (`new`, `feedback`, …), derivado
    del ID numérico de la clase CSS. Cae al texto visible si no está."""
    match = _STATUS_CLASS_RE.search(cell_html or "")
    if match:
        status_id = int(match.group(1))
        for name, sid in _STANDARD_STATUS_IDS.items():
            if sid == status_id:
                return name
    return _strip_tags(cell_html)


def _parse_issue_list_html(html_text: str, project_id: int) -> list[dict[str, Any]]:
    """Parsea la tabla de `view_all_bug_page.php` por CLASE de columna.

    Tolerante: una fila sin `column-id` (encabezados, separadores, filtros)
    simplemente se ignora; las columnas ausentes quedan como cadena vacía.
    """
    issues: list[dict[str, Any]] = []
    for row_match in _ANY_ROW_RE.finditer(html_text):
        row_html = row_match.group(1)
        cells = {
            name.lower(): fragment
            for name, fragment in _COLUMN_CELL_RE.findall(row_html)
        }
        if "id" not in cells:
            continue  # no es una fila de issue
        link_match = _ANY_ISSUE_LINK_RE.search(cells["id"]) or _ANY_ISSUE_LINK_RE.search(row_html)
        if not link_match:
            continue
        priority_cell = cells.get("priority", "")
        priority_title = _TITLE_ATTR_RE.search(priority_cell)
        issues.append({
            "id": int(link_match.group(1)),
            "summary": _strip_tags(cells.get("summary", "")),
            "status": _status_name_from_row(cells.get("status", "")),
            # La prioridad se renderiza como un icono: el valor está en `title`.
            "priority": (
                priority_title.group(1).strip() if priority_title
                else _strip_tags(priority_cell)
            ),
            "severity": _strip_tags(cells.get("severity", "")),
            "category": _strip_tags(cells.get("category", "")),
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

# Clases CSS reales de las celdas de `view.php` (verificadas en vivo). Este
# es el camino PRINCIPAL de extracción del detalle: no depende del idioma
# porque las clases son fijas, a diferencia del texto de las etiquetas.
_BUG_FIELD_CELL_RE = re.compile(
    r'<td[^>]*class=["\'][^"\']*\bbug-([a-z0-9-]+)\b[^"\']*["\'][^>]*>(.*?)</td>',
    re.IGNORECASE | re.DOTALL,
)
_BUG_CLASS_ALIASES: dict[str, tuple[str, ...]] = {
    "summary": ("summary",),
    "reporter": ("reporter",),
    "handler": ("assigned-to",),
    "status": ("status",),
    "priority": ("priority",),
    "severity": ("severity",),
    "category": ("category",),
    "description": ("description",),
    "steps_to_reproduce": ("steps-to-reproduce",),
    "additional_information": ("additional-information",),
    "target_version": ("target-version",),
    "fixed_in_version": ("fixed-in-version",),
    "version": ("version", "product-version"),
    "tags": ("tags",),
}
# `bug-summary` viene como "0022511: Título real" — se quita el prefijo.
_SUMMARY_ID_PREFIX_RE = re.compile(r"^\d+\s*:\s*(.+)$", re.DOTALL)


def _parse_issue_detail_html(html_text: str, issue_id: int) -> dict[str, Any]:
    """Parsea la tabla `bug-description-table` de `view.php` a un dict plano
    `{label: valor}` más los campos estructurados (notas/adjuntos/relaciones).

    Tolerante al idioma de la instancia (ver `_LABEL_ALIASES`)."""
    # 1) Camino PRINCIPAL: Mantis real marca cada celda del detalle con
    #    `class="bug-XXX"` (verificado en vivo). El camino por etiquetas
    #    visibles queda como respaldo para temas/versiones que no las usen.
    raw_by_class: dict[str, str] = {}
    by_class: dict[str, str] = {}
    for name, fragment in _BUG_FIELD_CELL_RE.findall(html_text):
        key = name.lower()
        # Mantis repite algunas clases (th de etiqueta + td de valor): se
        # conserva la primera con contenido real.
        if by_class.get(key):
            continue
        raw_by_class[key] = fragment
        by_class[key] = _strip_tags(fragment)

    # 2) Respaldo: filas `label -> valor` (tolerante al idioma).
    by_label: dict[str, str] = {}
    for label_match in _LABELED_ROW_RE.finditer(html_text):
        by_label[_normalize_label(label_match.group(1))] = _strip_tags(label_match.group(2))

    def pick(canonical: str) -> str:
        for css_name in _BUG_CLASS_ALIASES.get(canonical, ()):
            value = by_class.get(css_name)
            if value:
                return value
        for alias in _LABEL_ALIASES.get(canonical, (canonical,)):
            value = by_label.get(_normalize_label(alias))
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

    # El estado se normaliza al nombre canónico en inglés vía el ID numérico
    # de la clase CSS (`status-NN-fg`), igual que en el listado: el texto
    # visible viene traducido al idioma de la instancia y `field_mapping.status`
    # (§4 del config) se define con las claves en inglés.
    status_raw = raw_by_class.get("status", "")
    if _STATUS_CLASS_RE.search(status_raw):
        detail["status"] = _status_name_from_row(status_raw)

    # Mantis antepone el ID al título en `bug-summary` ("0022511: Título").
    summary = detail.get("summary", "")
    match = _SUMMARY_ID_PREFIX_RE.match(summary)
    if match:
        detail["summary"] = match.group(1).strip()
    return detail


# Estructura REAL de una nota (verificada en vivo):
#   <tr class="bugnote visible-on-hover-toggle" id="c52682">
#     <td class="category">… <a href="view_user_page.php?id=200">Nombre</a>
#         … 16/12/2024 17:44 … </td>
#     <td class="bugnote-note bugnote-public">texto de la nota</td>
#   </tr>
_REAL_BUGNOTE_ROW_RE = re.compile(
    r'<tr[^>]*class=["\'][^"\']*\bbugnote\b[^"\']*["\'][^>]*id=["\']c(\d+)["\'][^>]*>(.*?)</tr>',
    re.IGNORECASE | re.DOTALL,
)
_BUGNOTE_TEXT_RE = re.compile(
    r'<td[^>]*class=["\'][^"\']*\bbugnote-note\b[^"\']*["\'][^>]*>(.*?)</td>',
    re.IGNORECASE | re.DOTALL,
)
_BUGNOTE_USER_RE = re.compile(
    r'<a[^>]*view_user_page\.php\?id=\d+["\'][^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL
)
_BUGNOTE_DATE_RE = re.compile(r"(\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2})")
_BUGNOTE_PRIVATE_RE = re.compile(r"bugnote-private", re.IGNORECASE)


def _parse_bugnotes_html(html_text: str) -> list[dict[str, Any]]:
    """Extrae las notas/bugnotes de `view.php`.

    El patrón anterior (`<tr class="bugnote">` exacto + 3 celdas
    posicionales) NO existe en Mantis real: la clase trae sufijos
    (`bugnote visible-on-hover-toggle`) y el texto vive en una celda
    `bugnote-note`. Contra el servidor real devolvía 0 notas siempre.
    """
    notes: list[dict[str, Any]] = []
    for row_match in _REAL_BUGNOTE_ROW_RE.finditer(html_text):
        note_id, row_html = row_match.group(1), row_match.group(2)
        text_match = _BUGNOTE_TEXT_RE.search(row_html)
        user_match = _BUGNOTE_USER_RE.search(row_html)
        date_match = _BUGNOTE_DATE_RE.search(_strip_tags(row_html))
        notes.append({
            "id": note_id,
            "reporter": _strip_tags(user_match.group(1)) if user_match else "",
            "date": date_match.group(1) if date_match else "",
            "text": _strip_tags(text_match.group(1)) if text_match else "",
            # Las notas privadas de Mantis no deben publicarse sin querer.
            "private": bool(_BUGNOTE_PRIVATE_RE.search(row_html)),
        })
    return notes


# Estructura REAL de los adjuntos (verificada en vivo): viven en la celda
# `bug-attach-tags`, como pares de links a `file_download.php?file_id=N`
# (uno para el icono, otro para el nombre) seguidos del tamaño entre
# paréntesis: `…>GAP Mensajeria.docx</a>&#32;(1,882,466&#32;bytes)`.
_ATTACH_LINK_RE = re.compile(
    r'<a[^>]+href=["\']([^"\']*file_download\.php\?file_id=(\d+)[^"\']*)["\'][^>]*>(.*?)</a>'
    r"(?:[^<]*\(([\d.,\s&#;]+?)\s*bytes\))?",
    re.IGNORECASE | re.DOTALL,
)


def _parse_attachments_html(html_text: str) -> list[dict[str, Any]]:
    """Extrae los adjuntos de `view.php`.

    El patrón anterior (`<tr class="attachment-row">`) era inventado: Mantis
    no genera esa clase, así que contra el servidor real devolvía siempre 0
    adjuntos. Se deduplica por `file_id` porque cada adjunto aparece dos
    veces (link del icono + link del nombre).
    """
    attachments: list[dict[str, Any]] = []
    seen: set[str] = set()
    for match in _ATTACH_LINK_RE.finditer(html_text):
        url, file_id, label, size_text = match.groups()
        name = _strip_tags(label)
        if not name or file_id in seen:
            continue  # el 1er link del par es solo el icono (sin texto)
        seen.add(file_id)
        digits = re.sub(r"\D", "", _html.unescape(size_text or ""))
        attachments.append({
            "id": file_id,
            "name": name,
            "size": int(digits) if digits else 0,
            "url": _html.unescape(url),
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
        include_resolved_closed: bool = True,
        page_size: int = 500,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._project_ids = list(project_ids)
        self._username = username
        self._password = password
        self._session = session if session is not None else requests.Session()
        self._timeout = timeout
        # `origin.include_resolved_closed` (§4 del config): con True se fuerza
        # el filtro "mostrar todos los estados" — imprescindible, porque el
        # filtro por defecto de Mantis oculta resueltos/cerrados.
        self._include_resolved_closed = include_resolved_closed
        self._page_size = page_size
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
        """Lista TODOS los issues del/los proyecto(s) configurados.

        CRÍTICO — `view_all_bug_page.php` a secas aplica el FILTRO GUARDADO
        del usuario, que por defecto OCULTA los resueltos/cerrados: contra la
        instancia real devolvía 11 de 52 issues, o sea el 79% de los tickets
        se habría perdido en silencio. Se fuerza el filtro vía
        `view_all_set.php?type=1` con `hide_status_id=-2` (no ocultar ningún
        estado) y `status_id=0` (cualquier estado), que es el mecanismo
        estándar de Mantis para "mostrar todo".

        Efecto colateral declarado: esto reescribe el filtro guardado de la
        cuenta usada para la migración (no afecta datos de tickets, solo la
        vista por defecto de ese usuario en la UI de Mantis).
        """
        all_issues: list[dict[str, Any]] = []
        for project_id in self._project_ids:
            # 1) Fijar el PROYECTO ACTUAL de la sesión. Imprescindible: el
            #    alcance del listado lo define el proyecto activo de la
            #    sesión, NO un `project_id` suelto en la URL del filtro.
            #    Sin esto el listado devolvía issues de TODOS los proyectos
            #    (7 clientes distintos mezclados: 583 filas en vez de las 52
            #    del proyecto pedido) — habría migrado tickets de otros
            #    clientes al repo destino.
            self._authenticated_get(
                f"{self._base_url}/set_project.php?project_id={project_id}"
            )

            # 2) Fijar el filtro de estados ("todos" si se piden los
            #    resueltos/cerrados) + tamaño de página.
            filter_url = (
                f"{self._base_url}/view_all_set.php?type=1"
                f"&project_id[]={project_id}"
                f"&per_page={self._page_size}"
            )
            if self._include_resolved_closed:
                filter_url += "&hide_status_id=-2&status_id=0"
            self._authenticated_get(filter_url)

            # 2) Paginar hasta agotar. Mantis pagina con `page_number` y el
            #    listado NO trae el total de forma fiable, así que se avanza
            #    hasta que una página no aporte IDs nuevos. Sin esto solo se
            #    migraba la 1ª página (pérdida silenciosa en proyectos grandes).
            seen_ids: set[int] = set()
            project_issues: list[dict[str, Any]] = []
            page_number = 1
            while page_number <= _MAX_LIST_PAGES:
                page_url = (
                    f"{self._base_url}/view_all_bug_page.php"
                    f"?page_number={page_number}"
                )
                page_issues = _parse_issue_list_html(
                    self._authenticated_get(page_url), project_id
                )
                nuevos = [i for i in page_issues if i["id"] not in seen_ids]
                if not nuevos:
                    break
                seen_ids.update(i["id"] for i in nuevos)
                project_issues.extend(nuevos)
                page_number += 1
            else:
                # Se agotó el tope de páginas: NUNCA truncar en silencio.
                raise MantisScrapingPaginationError(
                    f"Proyecto {project_id}: se alcanzó el tope de "
                    f"{_MAX_LIST_PAGES} páginas ({len(project_issues)} issues "
                    "leídos) y Mantis seguía devolviendo issues nuevos. "
                    "Subí `_MAX_LIST_PAGES` o el `page_size`: abortar es "
                    "preferible a migrar una parte del proyecto creyendo que "
                    "es el total."
                )
            all_issues.extend(project_issues)
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
