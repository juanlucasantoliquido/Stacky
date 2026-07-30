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

# Tope de entradas del caché de `view.php` (ver `_get_view_html`). Con el HTML
# real rondando los 40 KB por ticket, 1500 entradas son ~60 MB: holgado para el
# proyecto 310 (1008 issues) y acotado para uno mucho más grande.
_VIEW_CACHE_MAX = 1500


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
    texto = _html.unescape(_TAG_RE.sub("", fragment or ""))
    # Mantis usa `&#160;` (espacio duro) como separador visual. Si queda
    # como \xa0 termina dentro de labels de GitLab y la API responde 500.
    texto = texto.replace("\xa0", " ")
    return re.sub(r"[ \t]{2,}", " ", texto).strip()


# En la celda de categoría Mantis antepone el proyecto entre corchetes
# (`<span class="small project">[Proyecto]</span>  Categoría`) cuando el
# listado abarca más de un proyecto. Ese prefijo NO es la categoría: si se
# cuela, el label queda `category::[602253 REC Banco…] General` y GitLab
# rechaza la creación del issue con 500.
_PROJECT_SPAN_RE = re.compile(
    r'<span[^>]*class=["\'][^"\']*\bproject\b[^"\']*["\'][^>]*>.*?</span>',
    re.IGNORECASE | re.DOTALL,
)


def _clean_category(cell_html: str) -> str:
    return _strip_tags(_PROJECT_SPAN_RE.sub("", cell_html or ""))


# Texto que Mantis muestra cuando el issue NO tiene etiquetas (varía con el
# idioma de la instancia): no es una etiqueta, es la ausencia de ellas.
_SIN_TAGS_RE = re.compile(r"^(sin etiquetas|no tags)\b", re.IGNORECASE)


def _split_tags(raw: "str | list | None") -> list[str]:
    """Normaliza la celda de etiquetas a una LISTA de strings."""
    if raw is None:
        return []
    if isinstance(raw, (list, tuple)):
        return [str(t).strip() for t in raw if str(t).strip()]
    texto = str(raw).strip()
    if not texto or _SIN_TAGS_RE.match(texto):
        return []
    return [t.strip() for t in re.split(r"[,;]", texto) if t.strip()]


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
            "category": _clean_category(cells.get("category", "")),
            # La fecha de última modificación SÍ viene en el listado
            # (`td.column-last-modified`) y antes se descartaba: el dict se
            # armaba sin ninguna clave de fecha, así que
            # `migrator_mg_core._build_authorship_block` —que lee
            # `last_modified`— nunca encontraba nada y las 52 issues de Ripley
            # se migraron SIN fecha, ni en campo nativo ni en metadata.
            # OJO con el formato: el listado trunca a `dd/mm/yy` (año de 2
            # dígitos), a diferencia del detalle que da `dd/mm/yyyy HH:MM`.
            # `mapping.date_map` maneja los dos.
            "last_modified": _strip_tags(cells.get("last-modified", "")),
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
# Fechas del detalle, por CLASE CSS (inmune al idioma, igual que el estado).
# Deliberadamente FUERA de `_LABEL_ALIASES`: ese dict gobierna el bucle que
# rellena `detail`, y meter fechas ahí las haría pasar por `pick()`, que también
# consulta etiquetas visibles traducidas — para fechas eso agrega riesgo de
# matchear la celda equivocada sin ganar nada.
_DATE_CLASS_ALIASES: dict[str, tuple[str, ...]] = {
    "date_submitted": ("date-submitted", "date_submitted", "reported"),
    "last_modified": ("last-modified", "last_modified", "updated"),
}

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

    historial = _parse_history_html(html_text)
    detail = {
        "id": issue_id,
        "notes": _parse_bugnotes_html(html_text),
        "attachments": _parse_attachments_html(html_text),
        "relationships": _parse_relationships_html(html_text),
        "history": historial,
        # `date_closed` es la fecha REAL de cierre (última transición de estado a
        # resolved/closed en el historial), no el proxy `last_modified` que
        # cambia con cualquier edición posterior. `None` si el ticket está
        # abierto o si el historial no es parseable.
        "date_closed": _extraer_fecha_cierre(historial),
        # `resolution` canónica vigente. Es lo que distingue un ticket CORREGIDO
        # de uno RECHAZADO (duplicado / no se corregirá / no se requieren
        # cambios) — matiz que antes se perdía por completo.
        "resolution": _extraer_resolucion(historial),
    }
    for canonical in _LABEL_ALIASES:
        detail[canonical] = pick(canonical)

    # `tags` debe ser una LISTA. Mantis renderiza esa celda como texto y,
    # cuando no hay etiquetas, un literal tipo "Sin etiquetas adjuntas." —
    # devolverlo como str hacía que el mapper lo iterara CARÁCTER a carácter
    # y generara labels basura (`tag::S`, `tag::i`, `tag::n`, …).
    detail["tags"] = _split_tags(detail.get("tags"))

    # El estado se normaliza al nombre canónico en inglés vía el ID numérico
    # de la clase CSS (`status-NN-fg`), igual que en el listado: el texto
    # visible viene traducido al idioma de la instancia y `field_mapping.status`
    # (§4 del config) se define con las claves en inglés.
    status_raw = raw_by_class.get("status", "")
    if _STATUS_CLASS_RE.search(status_raw):
        detail["status"] = _status_name_from_row(status_raw)

    # FECHAS. `_LABEL_ALIASES` no las incluye, así que el bucle de arriba no las
    # copiaba y el dato se descartaba pese a estar YA en memoria en `by_class`:
    # el HTML real del detalle trae `<td class="bug-date-submitted">10/01/2026
    # 09:15</td>`. Consecuencia del descarte: `_build_authorship_block` lee
    # `date_submitted`/`last_modified`, no encontraba nada, y las 52 issues de
    # Ripley se migraron SIN fecha ni en el campo nativo ni en la metadata.
    #
    # Se leen por CLASE CSS (no por etiqueta visible) porque la clase es inmune
    # al idioma de la instancia — mismo criterio que el estado. Se aceptan los
    # dos nombres que usa Mantis según versión/tema.
    for canonical, css_names in _DATE_CLASS_ALIASES.items():
        if detail.get(canonical):
            continue
        for css_name in css_names:
            valor = by_class.get(css_name)
            if valor:
                detail[canonical] = valor
                break
        detail.setdefault(canonical, "")

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


# ── Historial de cambios (fecha REAL de cierre + resolución) ────────────────
#
# Estructura VERIFICADA contra el HTML real de soporte.ais-int.net
# (`view.php?id=20636`, capturado el 2026-07-29). NO inventada — los regex
# anteriores de este archivo se escribieron dos veces contra estructuras
# supuestas y devolvían 0 filas contra el servidor real; ver los comentarios de
# `_parse_bugnotes_html` y `_parse_relationships_html`.
#
#   <div id="history" class="widget-box ...">
#     <table class="table table-bordered table-condensed table-hover table-striped">
#       <thead><tr><th>Fecha de modificación</th><th>Nombre de usuario</th>
#                  <th>Campo</th><th>Cambio</th></tr></thead>
#       <tbody>
#         <tr><td class="small-caption">25/03/2024 15:59</td>
#             <td class="small-caption"><del title="daniel">Daniel Ferre</del></td>
#             <td class="small-caption">Nueva Incidencia</td>
#             <td class="small-caption"></td></tr>
#         <tr>… <td>Estado</td> <td>confirmada =&gt; resuelta</td></tr>
#         <tr>… <td>Estado</td> <td>resuelta =&gt; cerrada</td></tr>
#         <tr>… <td>Resolución</td> <td>abierta =&gt; corregida</td></tr>
#
# Las filas vienen en orden CRONOLÓGICO ASCENDENTE (la más vieja primero), así
# que la última coincidencia es la vigente.
_HISTORY_DIV_RE = re.compile(
    r'<div\s+id="history"\s+class="widget-box.*?</table>', re.IGNORECASE | re.DOTALL
)
_HISTORY_ROW_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.IGNORECASE | re.DOTALL)
_HISTORY_CELL_RE = re.compile(
    r'<td[^>]*class="[^"]*small-caption[^"]*"[^>]*>(.*?)</td>', re.IGNORECASE | re.DOTALL
)

# Nombre visible del campo "Estado"/"Resolución" en el historial. A diferencia del
# estado del listado —que se lee del ID numérico de la clase CSS `status-NN-fg` y
# por eso es inmune al idioma— acá SÓLO hay texto traducido. Es una dependencia
# del idioma de la instancia, declarada: si Mantis se cambia de idioma, hay que
# sumar el alias, y `fetch_issue_history` devolverá listas vacías (nunca datos
# equivocados).
_HIST_CAMPO_ESTADO = ("estado", "status")
_HIST_CAMPO_RESOLUCION = ("resolucion", "resolution")

# Valor visible del estado -> nombre canónico en inglés (el de `field_mapping`).
_HIST_ESTADO_A_CANONICO = {
    "nueva": "new", "new": "new",
    "se necesitan mas datos": "feedback", "feedback": "feedback",
    "reconocida": "acknowledged", "aceptada": "acknowledged", "acknowledged": "acknowledged",
    "confirmada": "confirmed", "confirmed": "confirmed",
    "asignada": "assigned", "assigned": "assigned",
    "resuelta": "resolved", "resolved": "resolved",
    "cerrada": "closed", "closed": "closed",
}

# Estados que implican ticket cerrado (los que dan la FECHA DE CIERRE real).
_HIST_ESTADOS_CIERRE = frozenset({"resolved", "closed"})

# Valor visible de la resolución -> nombre canónico en inglés.
_HIST_RESOLUCION_A_CANONICO = {
    "abierta": "open", "open": "open",
    "corregida": "fixed", "fixed": "fixed",
    "reabierta": "reopened", "reopened": "reopened",
    "no se puede reproducir": "unable-to-duplicate",
    "unable to reproduce": "unable-to-duplicate",
    "unable to duplicate": "unable-to-duplicate",
    "no se puede corregir": "not-fixable", "not fixable": "not-fixable",
    "duplicada": "duplicate", "duplicate": "duplicate",
    "no se requieren cambios": "no-change-required",
    "no change required": "no-change-required",
    "suspendida": "suspended", "suspended": "suspended",
    "no se corregira": "wont-fix", "no se corregira nunca": "wont-fix",
    "won't fix": "wont-fix", "wont fix": "wont-fix",
}


def _hist_normalizar(texto: str) -> str:
    """Minúsculas, sin acentos y con espacios colapsados, para comparar etiquetas
    y valores del historial sin depender de tildes ni de espaciado."""
    return _normalize_label(texto)


def _parse_history_html(html_text: str) -> list[dict[str, Any]]:
    """Filas del historial: `{fecha, usuario, campo, desde, hasta}`.

    `campo` queda normalizado (sin acentos, minúsculas) para poder compararlo
    contra `_HIST_CAMPO_*`. `desde`/`hasta` salen de partir la celda "Cambio" por
    la flecha `=>` que Mantis usa (llega como `&gt;` y `_strip_tags` la
    desescapa). Una fila sin flecha (p. ej. "Nueva Incidencia") deja `desde`
    vacío y todo el texto en `hasta`.
    """
    bloque = _HISTORY_DIV_RE.search(html_text or "")
    if not bloque:
        return []

    filas: list[dict[str, Any]] = []
    for row in _HISTORY_ROW_RE.finditer(bloque.group(0)):
        celdas = _HISTORY_CELL_RE.findall(row.group(1))
        if len(celdas) < 3:
            continue  # cabecera (usa <th>) o fila incompleta
        fecha = _strip_tags(celdas[0])
        usuario = _strip_tags(celdas[1])
        campo = _strip_tags(celdas[2])
        cambio = _strip_tags(celdas[3]) if len(celdas) > 3 else ""

        desde, hasta = "", cambio
        partes = re.split(r"\s*=>\s*", cambio, maxsplit=1)
        if len(partes) == 2:
            desde, hasta = partes[0].strip(), partes[1].strip()

        filas.append({
            "fecha": fecha,
            "usuario": usuario,
            "campo": _hist_normalizar(campo),
            "campo_visible": campo,
            "desde": desde,
            "hasta": hasta,
        })
    return filas


def _extraer_fecha_cierre(filas: list[dict[str, Any]]) -> Optional[str]:
    """Fecha del ÚLTIMO cambio de estado hacia `resolved`/`closed`.

    Ésta es la fecha de cierre REAL del ticket — la que hasta ahora se aproximaba
    con `last_modified`, que cambia con cualquier edición posterior al cierre.

    "Último" y no "primero" a propósito: un ticket reabierto y vuelto a cerrar
    tiene varias transiciones de cierre, y la vigente es la más reciente. Si
    después del último cierre hay una transición a un estado ABIERTO, el ticket
    está reabierto y no tiene fecha de cierre vigente → `None`.
    """
    ultima_cierre: Optional[str] = None
    for fila in filas:
        if fila["campo"] not in _HIST_CAMPO_ESTADO:
            continue
        destino = _HIST_ESTADO_A_CANONICO.get(_hist_normalizar(fila["hasta"]))
        if destino is None:
            continue
        if destino in _HIST_ESTADOS_CIERRE:
            ultima_cierre = fila["fecha"]
        else:
            # Transición a un estado abierto POSTERIOR al cierre: reabierto.
            ultima_cierre = None
    return ultima_cierre


def _extraer_resolucion(filas: list[dict[str, Any]]) -> Optional[str]:
    """Nombre canónico de la resolución vigente (última transición), o `None`.

    Cierra el gap de `resolution`, que no se migraba en absoluto: es el campo que
    distingue un ticket **corregido** de uno **rechazado** (duplicado / no se
    corregirá / no se requieren cambios).
    """
    vigente: Optional[str] = None
    for fila in filas:
        if fila["campo"] not in _HIST_CAMPO_RESOLUCION:
            continue
        canonico = _HIST_RESOLUCION_A_CANONICO.get(_hist_normalizar(fila["hasta"]))
        if canonico:
            vigente = canonico
    return vigente


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


# El TOTAL que el propio Mantis declara para el filtro activo — el único número
# contra el cual se puede validar que la extracción no truncó nada.
#
# Texto REAL verificado contra soporte.ais-int.net (2026-07-29):
#     "Visualizando incidencias 1 - 500 / 1008"
# La primera versión de este regex exigía que el número siguiera INMEDIATAMENTE a
# la palabra clave y por eso no matcheaba: entre "Visualizando" y "1" va el
# sustantivo ("incidencias" / "issues"). Resultado: `None`, y el gate de conteo
# quedaba desactivado en silencio — justo el modo de falla que este gate existe
# para evitar. Ahora se admiten hasta 3 palabras intermedias.
_TOTAL_DECLARADO_RE = re.compile(
    r"(?:mostrando|viewing|visualizando|displaying)"
    r"(?:\s+[^\d\s]+){0,3}"
    r"\s*\d+\s*-\s*\d+\s*/\s*(\d+)",
    re.IGNORECASE,
)


def _parse_total_declarado(html_text: str) -> Optional[int]:
    """Total de issues que Mantis declara para el filtro activo, o `None`."""
    m = _TOTAL_DECLARADO_RE.search(_strip_tags(html_text or ""))
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def _verificar_cobertura_de_estados(
    issues: list[dict[str, Any]],
    *,
    project_id: int,
    include_resolved_closed: bool,
    total_declarado: Optional[int],
) -> None:
    """Gate anti-extracción-truncada. Aborta en vez de devolver un subconjunto.

    Existe por el bug #2 de la migración de Ripley: el filtro de estados se creyó
    aplicado, se extrajeron 52 de un universo desconocido, y la migración se dio
    por completa. El síntoma era perfectamente detectable —cero tickets en estado
    `closed` en un proyecto con años de actividad— pero nada lo miraba.

    Dos chequeos, los dos ruidosos:

    1. **Cobertura de estados**: con `include_resolved_closed=True`, un resultado
       sin NINGÚN ticket `resolved` ni `closed` es prueba de que el filtro sigue
       ocultándolos. Es teóricamente posible que un proyecto real no tenga
       ninguno, así que el error explica cómo confirmarlo y cómo saltearlo
       deliberadamente (`include_resolved_closed=False`).
    2. **Conteo contra el total declarado por Mantis**: si el listado dice
       "/ 583" y se recolectaron 52, se aborta. Este chequeo es el que el
       operador pidió como requisito antes de re-ejecutar, y acá es automático:
       no depende de que alguien se acuerde de mirarlo.
    """
    if total_declarado is not None and len(issues) != total_declarado:
        raise MantisScrapingPaginationError(
            f"Proyecto {project_id}: Mantis declara {total_declarado} issues para el "
            f"filtro activo pero se extrajeron {len(issues)}. Se aborta: migrar un "
            "subconjunto creyendo que es el total es exactamente el fallo que dejó "
            "8 tickets resueltos afuera en la migración anterior. Revisá la "
            "paginación (`page_size`, `_MAX_LIST_PAGES`) y el filtro antes de "
            "reintentar."
        )

    if not include_resolved_closed:
        return

    estados = {str(i.get("status") or "").strip().lower() for i in issues}
    if issues and not (estados & {"resolved", "closed"}):
        raise MantisScrapingPaginationError(
            f"Proyecto {project_id}: se pidió `include_resolved_closed=True` pero "
            f"de {len(issues)} issues extraídos NINGUNO está en estado `resolved` "
            f"(80) ni `closed` (90). Estados encontrados: {sorted(estados)}. "
            "Eso indica que el filtro guardado de la cuenta de Mantis sigue "
            "ocultando los cerrados (el `view_all_set.php?type=1` es un set "
            "PARCIAL). Verificá manualmente en la UI de Mantis cuántos tickets "
            "cerrados tiene el proyecto. Si de verdad no tiene ninguno, corré con "
            "`include_resolved_closed=False` para declarar esa decisión de forma "
            "explícita."
        )


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
        # Caché del HTML de `view.php?id=N` por issue. Ver `_get_view_html`:
        # CUATRO métodos del contrato piden exactamente el mismo recurso, así que
        # sin caché el barrido cuesta 4x lo necesario.
        self._view_cache: "dict[int, str]" = {}
        self._view_cache_hits = 0
        self._view_cache_misses = 0

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
        totales_declarados: dict[int, Optional[int]] = {}
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
            #
            # POR QUÉ EL RESET PRIMERO (esto era el bug #2 de la migración de
            # Ripley): `view_all_set.php?type=1` es un "set" PARCIAL — los campos
            # del filtro que NO se envían conservan el valor del filtro GUARDADO
            # de la cuenta. El filtro por defecto de Mantis oculta los cerrados,
            # así que mandar sólo `hide_status_id` dejaba `resolved` (80) visible
            # pero `closed` (90) oculto: de los 52 issues migrados, 1 resuelto y
            # CERO cerrados, y 8 tickets que se sabía resueltos quedaron afuera.
            # `type=3` es la acción RESET de Mantis: limpia el filtro guardado
            # para que el "set" siguiente parta de un estado conocido en vez de
            # heredar lo que hubiera.
            #
            # El reset va SOLO dentro de la rama `include_resolved_closed`: con
            # `False` el operador pidió explícitamente respetar el filtro guardado
            # de la cuenta, y resetearlo sería un efecto colateral que no pidió.
            filter_url = (
                f"{self._base_url}/view_all_set.php?type=1"
                f"&project_id[]={project_id}"
                f"&per_page={self._page_size}"
            )
            if self._include_resolved_closed:
                self._authenticated_get(f"{self._base_url}/view_all_set.php?type=3")
                # Defensa en profundidad: se envían TODOS los parámetros que
                # gobiernan el filtrado por estado, en las dos grafías que usa
                # MantisBT según versión (`hide_status_id` / `hide_status`, y
                # `status_id[]` como array además del escalar). Un parámetro que
                # la versión no conozca lo ignora; el que sí, manda.
                #   -2  = META_FILTER_NONE  -> "no ocultar ningún estado"
                #    0  = "cualquier estado"
                filter_url += (
                    "&hide_status_id=-2&hide_status=-2"
                    "&status_id=0&status_id[]=0"
                    "&sort=id&dir=ASC"
                )
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
                html_pagina = self._authenticated_get(page_url)
                if page_number == 1:
                    # Mantis imprime "Mostrando 1 - 50 / 583" en el listado. Es el
                    # ÚNICO número que el propio origen declara como total, así
                    # que es el gate contra el que se valida la extracción.
                    totales_declarados[project_id] = _parse_total_declarado(html_pagina)
                page_issues = _parse_issue_list_html(html_pagina, project_id)
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
            _verificar_cobertura_de_estados(
                project_issues,
                project_id=project_id,
                include_resolved_closed=self._include_resolved_closed,
                total_declarado=totales_declarados.get(project_id),
            )
            all_issues.extend(project_issues)
        return all_issues

    def _get_view_html(self, issue_id: int) -> str:
        """HTML de `view.php?id=N`, con caché por issue dentro de la corrida.

        POR QUÉ: `fetch_issue_detail`, `fetch_comments`, `fetch_attachments` y
        `fetch_relationships` piden **exactamente el mismo recurso**. Sin caché,
        un barrido de 1008 issues cuesta ~4000 GET a `view.php` en vez de 1008 —
        y `execute` hace ese barrido dos veces (una en `plan_migration` para
        comparar el hash, otra en la pasada de relaciones), así que el desperdicio
        se duplica. Medido en la instancia real: ~8000 requests evitables.

        Es seguro: es el mismo recurso dentro de la misma corrida, y tomar UNA
        foto consistente del ticket es más correcto que mezclar lecturas de
        momentos distintos (un ticket que cambia a mitad del barrido produciría un
        issue con descripción de un instante y notas de otro).

        Tope de memoria: `_VIEW_CACHE_MAX` entradas. Al llenarse se vacía por
        completo en vez de aplicar LRU — el patrón de acceso real es un barrido
        secuencial donde cada issue se consulta varias veces seguidas y después
        nunca más, así que un LRU no compraría nada y sí agregaría complejidad.
        """
        cached = self._view_cache.get(issue_id)
        if cached is not None:
            self._view_cache_hits += 1
            return cached

        self._view_cache_misses += 1
        html_text = self._authenticated_get(f"{self._base_url}/view.php?id={issue_id}")
        if len(self._view_cache) >= _VIEW_CACHE_MAX:
            self._view_cache.clear()
        self._view_cache[issue_id] = html_text
        return html_text

    def cache_stats(self) -> dict[str, int]:
        """Diagnóstico del caché de `view.php`, para poder afirmar con números
        que el barrido no está pidiendo el mismo recurso cuatro veces."""
        return {
            "hits": self._view_cache_hits,
            "misses": self._view_cache_misses,
            "entradas": len(self._view_cache),
        }

    def fetch_comments(self, issue_id: int) -> list[dict[str, Any]]:
        return _parse_bugnotes_html(self._get_view_html(issue_id))

    def fetch_attachments(self, issue_id: int) -> list[dict[str, Any]]:
        return _parse_attachments_html(self._get_view_html(issue_id))

    def fetch_relationships(self, issue_id: int) -> list[dict[str, Any]]:
        return _parse_relationships_html(self._get_view_html(issue_id))

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
        # `&type=bug` NO es opcional: sin él, Mantis responde 400 con CUERPO
        # VACÍO (verificado en vivo el 2026-07-30 contra soporte.ais-int.net:
        # `file_download.php?file_id=32057` -> 400 / 0 bytes;
        # `...&file_id=32057&type=bug` -> 200 / 70.015 bytes). Es exactamente
        # la URL que Mantis publica en el HTML del issue y que
        # `_parse_attachments_html` ya captura en `attachment_meta["url"]`.
        # Faltando el parámetro, TODA descarga devolvía 0 bytes, se subía un
        # archivo VACÍO a GitLab y se reportaba como migrado con éxito: así
        # se perdieron los 1.419 adjuntos de la migración de Ripley.
        url = f"{self._base_url}/file_download.php?file_id={file_id}&type=bug"

        resp = self._session.get(url, timeout=self._timeout)
        if self._response_is_login_page(resp):
            self._login()
            resp = self._session.get(url, timeout=self._timeout)
            if self._response_is_login_page(resp):
                raise MantisScrapingAuthError(
                    "La sesión Mantis expiró al descargar el adjunto "
                    f"(file_id={file_id}) y el re-login automático también falló."
                )

        # Gates duros: un adjunto vacío o un error HTTP NUNCA pueden pasar por
        # una descarga buena. Antes se devolvía `resp.content` sin mirar el
        # status, y un 400 con cuerpo vacío viajaba como "el archivo".
        if resp.status_code != 200:
            raise RuntimeError(
                f"file_download.php devolvió HTTP {resp.status_code} para "
                f"file_id={file_id} ({len(resp.content)} bytes). No se sube un "
                "adjunto que no se pudo descargar."
            )
        if not resp.content:
            raise RuntimeError(
                f"file_download.php devolvió 0 bytes para file_id={file_id} "
                f"(HTTP {resp.status_code}). Subir esto crearía un adjunto "
                "vacío en el destino y lo daría por migrado."
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
        return _parse_issue_detail_html(self._get_view_html(issue_id), issue_id)


__all__ = ["MantisScrapingAuthError", "MantisWebScrapingReadAdapter"]
