"""menu_resolver.py — Resolucion de navegacion por el menu VIVO (Plan 240 F3 / 241 F5).

REGLA DURA (H4): AgendaWeb usa URLs con un payload de query ENCRIPTADO POR SESION
(p.ej. FrmReportes.aspx?<clave>=TdbfUQQM9SQ5...). Deep-linkear una de esas SIN ese
payload redirige a frmLogin.aspx Y ESE REDIRECT DESTRUYE LA SESION, cascando falsos
NAV_AUTH_EXPIRED en todos los pasos siguientes. Por lo tanto:
  - NUNCA se sintetiza una URL con ese payload.
  - NUNCA se persiste un href con ese payload en un playbook/ui_map.
  - El destino se resuelve clickeando el ANCLA REAL del menu, por etiqueta visible.

100% DETERMINISTA (normalizacion + matching de strings) => identico en los 3 runtimes.
El unico contacto con el navegador es `harvest_menu_sync`, y su JS no filtra nada:
el filtrado es Python puro y testeable sin navegador.
"""
from __future__ import annotations

import re
import unicodedata
from urllib.parse import urlsplit, parse_qs

# Ligature de Material Icons pegada al texto visible. Los nombres de icono son
# SIEMPRE [a-z_]+ y el texto visible arranca en MAYUSCULA, asi que el token de icono
# se reconoce sin ambiguedad en las dos formas observadas en vivo:
#   - pegado:   "switch_accountReasignacion Manual" -> "Reasignacion Manual"
#   - separado: "event\nAgenda Personal" (el \n ya se colapso a espacio)
_ICON_LIGATURE_RE = re.compile(r"^[a-z_]+ ?(?=[A-ZÁÉÍÓÚÑ])")
_SESSION_QUERY_KEY = "q"


def normalize_label(raw: str) -> str:
    """Normaliza una etiqueta de menu para comparar. NUNCA lanza.

    Pasos EXACTOS, en este orden:
      1. Reemplazar \\n y \\t por espacio; colapsar espacios; strip.
      2. Quitar el token de icono Material: si el texto arranca con un run de
         [a-z_]+ pegado a una mayuscula, eliminarlo.
         Casos reales verificados: "event\\nAgenda Personal" -> "agenda personal";
         "switch_accountReasignacion Manual" -> "reasignacion manual";
         "searchFiltrar" -> "filtrar";
         "grid_on\\nAGENDADOS POR USUARIO" -> "agendados por usuario".
      3. Quitar acentos (NFKD + drop de combinantes).
      4. lower() y colapsar espacios de nuevo.
    """
    try:
        txt = str(raw or "").replace("\n", " ").replace("\t", " ")
        txt = re.sub(r"\s+", " ", txt).strip()
        txt = _ICON_LIGATURE_RE.sub("", txt)
        txt = unicodedata.normalize("NFKD", txt)
        txt = "".join(c for c in txt if not unicodedata.combining(c))
        return re.sub(r"\s+", " ", txt.lower()).strip()
    except Exception:  # noqa: BLE001
        return ""


def harvest_menu_js() -> str:
    """JS que se pasa a page.evaluate() para cosechar el menu.

    Extrae de TODOS los <a>: text (innerText o title), href CRUDO (getAttribute, NO
    .href resuelto) e id. No filtra nada: el filtrado es Python puro y testeable.
    """
    return """
    () => Array.from(document.querySelectorAll('a')).map(a => ({
      text: (a.innerText || a.getAttribute('title') || '').trim(),
      href: a.getAttribute('href') || '',
      id: a.id || ''
    }))
    """


def _classify(href: str) -> str:
    low = (href or "").lower()
    if "__dopostback" in low:
        return "postback"
    if ".aspx" in low:
        return "aspx"
    return "other"


def _screen_of(href: str):
    """Nombre del archivo .aspx del path (sin query), preservando el case del href."""
    try:
        path = urlsplit(href or "").path
        name = path.rsplit("/", 1)[-1]
        return name if name.lower().endswith(".aspx") else None
    except Exception:  # noqa: BLE001
        return None


def _has_session_query(href: str) -> bool:
    try:
        return _SESSION_QUERY_KEY in parse_qs(urlsplit(href or "").query)
    except Exception:  # noqa: BLE001
        return False


def harvest_menu_sync(page) -> list:
    """Cosecha el menu de la pagina ACTUAL. NUNCA lanza (ante error devuelve []).

    Cada item: {"label", "label_norm", "href", "id", "kind", "screen", "has_q_param"}
    """
    try:
        raw = page.evaluate(harvest_menu_js()) or []
    except Exception:  # noqa: BLE001
        return []
    out: list = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        label = str(item.get("text") or "")
        href = str(item.get("href") or "")
        out.append({
            "label": label,
            "label_norm": normalize_label(label),
            "href": href,
            "id": str(item.get("id") or ""),
            "kind": _classify(href),
            "screen": _screen_of(href),
            "has_q_param": _has_session_query(href),
        })
    return out


def resolve_target(menu: list, wanted: str):
    """Resuelve por precedencia EXACTA (la primera que matchea gana):
      1. screen == wanted (case-insensitive) — p.ej. wanted="FrmBusqueda.aspx".
      2. label_norm == normalize_label(wanted) — igualdad exacta de etiqueta.
      3. label_norm empieza con normalize_label(wanted).
      4. normalize_label(wanted) contenido en label_norm.
    Empate en el mismo nivel: gana el de menor indice (orden del DOM), determinista.
    Sin match => None (el caller emite MENU_LABEL_NOT_FOUND). NUNCA lanza.
    """
    try:
        items = [m for m in (menu or []) if isinstance(m, dict)]
        want_raw = str(wanted or "").strip()
        if not want_raw or not items:
            return None
        want_screen = want_raw.lower()
        want_norm = normalize_label(want_raw)

        for m in items:
            if str(m.get("screen") or "").lower() == want_screen:
                return m
        if not want_norm:
            return None
        for m in items:
            if m.get("label_norm") == want_norm:
                return m
        for m in items:
            if str(m.get("label_norm") or "").startswith(want_norm):
                return m
        for m in items:
            if want_norm in str(m.get("label_norm") or ""):
                return m
        return None
    except Exception:  # noqa: BLE001
        return None


def sanitize_for_playbook(entry: dict) -> dict:
    """Copia SEGURA de persistir. NUNCA lanza.

    Si el href trae el payload de sesion, se elimina la query ENTERA (queda solo el
    path) y se agrega requires_live_menu=True + resolve_by = entry['label_norm'],
    para que el playbook diga COMO volver a resolverlo. Sin payload,
    requires_live_menu=False y el href se conserva tal cual.
    """
    try:
        out = dict(entry or {})
        if out.get("has_q_param"):
            parts = urlsplit(str(out.get("href") or ""))
            out["href"] = parts.path
            out["requires_live_menu"] = True
            out["resolve_by"] = out.get("label_norm") or normalize_label(out.get("label"))
        else:
            out["requires_live_menu"] = False
        return out
    except Exception:  # noqa: BLE001
        return dict(entry or {})


def is_login_redirect(url: str) -> bool:
    """True si la URL es la pantalla de login.

    Case-insensitive: la app redirige a 'frmLogin.aspx' con f minuscula
    (verificado en vivo). Un redirect a login DENTRO de un paso es
    NAV_SESSION_LOST (expulsion por navegar mal, recuperable con re-auth),
    NO NAV_AUTH_EXPIRED (la sesion vencio por tiempo).
    """
    return "frmlogin" in (url or "").lower()
