"""route_allowlist.py — Plan 262 F4. Rutas permitidas, ruta segura y validacion.

Es el paso 2 del orden que exigio el operador y la unica forma determinista de
distinguir "URL mal construida" de "la prueba fallo".

POLITICA EXPLICITA: la allowlist DERIVADA es PERMISIVA por diseno. Una lista
deducida e incompleta que rechace pantallas legitimas convertiria fallos reales de
la prueba en errores de ruta reintentables — o sea, fabricaria resultados verdes
que no lo son, que es justo lo que INV-1 prohibe. La lista solo se vuelve estricta
cuando el operador la declara. Es una decision de seguridad del veredicto, no una
comodidad.

NUNCA lanza. Sin red, sin disco, sin modelos.
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

_ROOT_ROUTES: frozenset[str] = frozenset({"", "/"})


@dataclass(frozen=True)
class RouteVerdict:
    allowed: bool
    normalized: str        # ruta relativa normalizada, ej "FrmBusqueda.aspx"
    absolute: str          # URL absoluta resuelta contra la base
    reason: str            # "in_allowlist" | "not_in_allowlist" | "foreign_host" |
                           # "unparseable" | "outside_base_path"
    source: str            # "configured" | "derived" — de donde salio la allowlist


def _base_url(base_url: str | None = None) -> str:
    if base_url:
        return base_url.rstrip("/") + "/"
    try:
        from recovery_config import base_url as _b
        return _b()
    except Exception:                              # noqa: BLE001
        try:
            from agenda_health import DEFAULT_BASE_URL
            return DEFAULT_BASE_URL
        except Exception:                          # noqa: BLE001
            return "http://localhost:35017/AgendaWeb/"


def _child_screens() -> frozenset[str]:
    """Import DIFERIDO: si el driver no esta disponible se degrada sin romper."""
    try:
        from navigation_driver import CHILD_SCREENS
        return frozenset(CHILD_SCREENS)
    except Exception:                              # noqa: BLE001
        return frozenset()


def _login_path() -> str:
    try:
        from environment_preflight import _LOGIN_PATH
        return _LOGIN_PATH
    except Exception:                              # noqa: BLE001
        return "FrmLogin.aspx"


def _safe_route_raw() -> str:
    try:
        from recovery_config import safe_route_raw
        return safe_route_raw()
    except Exception:                              # noqa: BLE001
        return ""


def _configured_raw() -> list[str]:
    try:
        from recovery_config import route_allowlist_raw
        return route_allowlist_raw()
    except Exception:                              # noqa: BLE001
        return []


def effective_allowlist() -> tuple[frozenset[str], str]:
    """(rutas, source). Vacia la config => lista DERIVADA del codigo, permisiva."""
    declarada = _configured_raw()
    segura = _safe_route_raw()
    if declarada:
        rutas = set(declarada)
        if segura:
            rutas.add(segura)                      # auto-inclusion: anti-bucle
        return frozenset(rutas), "configured"

    rutas = set(_child_screens())
    rutas.add(_login_path())
    rutas |= set(_ROOT_ROUTES)
    if segura:
        rutas.add(segura)
    return frozenset(rutas), "derived"


def normalize_route(url_or_path: str, *, base_url: str | None = None) -> str:
    """Devuelve la ruta relativa a la base, sin query ni fragmento. NUNCA lanza."""
    if not url_or_path or not str(url_or_path).strip():
        return ""
    base = _base_url(base_url)
    raw = str(url_or_path).strip()
    try:
        absoluto = urljoin(base, raw)
        partes = urlsplit(absoluto)
        base_path = urlsplit(base).path            # ej "/AgendaWeb/"
        path = partes.path
        if path.lower().startswith(base_path.lower()):
            path = path[len(base_path):]
        return path.lstrip("/")
    except Exception:                              # noqa: BLE001
        return raw


def safe_route_url() -> str:
    """URL absoluta de la ruta segura. Vacia => la URL base, que siempre es valida."""
    base = _base_url()
    segura = _safe_route_raw()
    if not segura:
        return base
    try:
        return urljoin(base, segura)
    except Exception:                              # noqa: BLE001
        return base


def is_child_screen(route: str) -> bool:
    """Delega en navigation_driver.CHILD_SCREENS. Sin driver => False (degrada)."""
    if not route:
        return False
    nombre = normalize_route(route).rsplit("/", 1)[-1].lower()
    return nombre in {s.lower() for s in _child_screens()}


def _es_ilegible(raw, normalizada: str) -> bool:
    if raw is None or not str(raw).strip():
        return True
    nombre = normalizada.rsplit("/", 1)[-1]
    # Un segmento sin un solo caracter alfanumerico no es una ruta evaluable.
    return not any(c.isalnum() for c in nombre)


def is_allowed(url_or_path, *, base_url: str | None = None) -> RouteVerdict:
    """Veredicto determinista sobre la URL usada. NUNCA lanza."""
    rutas, source = effective_allowlist()
    base = _base_url(base_url)

    if url_or_path is None or not str(url_or_path).strip():
        return RouteVerdict(False, "", "", "unparseable", source)

    raw = str(url_or_path).strip()
    try:
        absoluto = urljoin(base, raw)
        partes = urlsplit(absoluto)
        base_partes = urlsplit(base)

        # Host ajeno: cubre la "redireccion inesperada" del pedido.
        if partes.netloc and partes.netloc.lower() != base_partes.netloc.lower():
            return RouteVerdict(False, normalize_route(raw, base_url=base), absoluto,
                                "foreign_host", source)

        # Mismo host pero fuera del path base.
        if not partes.path.lower().startswith(base_partes.path.lower()):
            return RouteVerdict(False, partes.path.lstrip("/"), absoluto,
                                "outside_base_path", source)
    except Exception:                              # noqa: BLE001
        return RouteVerdict(False, "", "", "unparseable", source)

    normalizada = normalize_route(raw, base_url=base)
    if _es_ilegible(raw, normalizada):
        return RouteVerdict(False, normalizada, absoluto, "unparseable", source)

    # La raiz de la base siempre es legal.
    if normalizada in _ROOT_ROUTES:
        return RouteVerdict(True, normalizada, absoluto, "in_allowlist", source)

    nombre = normalizada.rsplit("/", 1)[-1].lower()
    conocidas = {r.rsplit("/", 1)[-1].lower() for r in rutas}
    if nombre in conocidas:
        return RouteVerdict(True, normalizada, absoluto, "in_allowlist", source)

    # DERIVADA => permisiva: una pantalla desconocida que vive bajo el path base y
    # termina en .aspx se acepta. Ver la politica del docstring de modulo.
    if source == "derived" and nombre.endswith(".aspx"):
        return RouteVerdict(True, normalizada, absoluto, "in_allowlist", source)

    return RouteVerdict(False, normalizada, absoluto, "not_in_allowlist", source)
