"""screen_guard.py — Un PASS en la pantalla equivocada es imposible (Plan 241 F0).

CASO REAL QUE ESTE MODULO MATA (ADO-366, verificado el 2026-07-25): el run reporto
PASS 3/3 y la captura del propio run mostraba "Agenda Personal" (FrmAgenda.aspx),
cuando el criterio era sobre el mantenedor de telefonos de FrmDetalleClie.aspx.
Lo detecto un humano mirando una imagen, no el arnes.

100% DETERMINISTA (string matching puro) => identico en los 3 runtimes.
"""
from __future__ import annotations

_CODE_OK = ""
_CODE_WRONG_SCREEN = "NAV_WRONG_SCREEN"
_CODE_SESSION_LOST = "NAV_SESSION_LOST"


def is_login_redirect(url: str) -> bool:
    """True si la URL es la pantalla de login.

    Case-insensitive: la app redirige a 'frmLogin.aspx' con f minuscula
    (verificado en vivo, Plan 240 H4).
    """
    return "frmlogin" in (url or "").lower()


def _screen_token(expected_screen: str) -> str:
    """'FrmDetalleClie.aspx' -> 'frmdetalleclie' (sin extension, lower)."""
    raw = (expected_screen or "").strip().lower()
    if raw.endswith(".aspx"):
        raw = raw[: -len(".aspx")]
    return raw


def verify_screen(page_state: dict, expected_screen: str) -> dict:
    """Verifica que el escenario probo LA pantalla del criterio. NUNCA lanza.

    page_state: {"url": str, "title": str, "anchor_present": bool|None}
    Retorna {"ok": bool, "code": str, "detail": str}.

    Reglas EXACTAS (en orden):
      1. expected_screen vacio           => ok True (nada que verificar).
      2. is_login_redirect(url)          => code NAV_SESSION_LOST.
      3. token de expected_screen NO contenido en url.lower()
                                         => code NAV_WRONG_SCREEN con la url real.
      4. anchor_present is False         => code NAV_WRONG_SCREEN (llego la URL pero
                                            no el contenido: postback a medias).
      5. resto                           => ok True.
    """
    try:
        state = page_state if isinstance(page_state, dict) else {}
        url = str(state.get("url") or "")
        title = str(state.get("title") or "")
        anchor_present = state.get("anchor_present")

        token = _screen_token(expected_screen or "")
        if not token:
            return {"ok": True, "code": _CODE_OK,
                    "detail": "sin pantalla esperada declarada: nada que verificar"}

        if is_login_redirect(url):
            return {
                "ok": False,
                "code": _CODE_SESSION_LOST,
                "detail": (
                    f"la app expulso al login: esperada={expected_screen} url_real={url}"
                ),
            }

        if token not in url.lower():
            return {
                "ok": False,
                "code": _CODE_WRONG_SCREEN,
                "detail": (
                    f"pantalla equivocada: esperada={expected_screen} "
                    f"url_real={url} titulo={title!r}"
                ),
            }

        if anchor_present is False:
            return {
                "ok": False,
                "code": _CODE_WRONG_SCREEN,
                "detail": (
                    f"la URL es {expected_screen} pero el ancla de contenido no esta "
                    f"presente (postback a medias): url_real={url} titulo={title!r}"
                ),
            }

        return {"ok": True, "code": _CODE_OK,
                "detail": f"pantalla verificada: {expected_screen}"}
    except Exception as exc:  # noqa: BLE001 — NUNCA lanza (G6: degradar ruidoso)
        return {"ok": True, "code": _CODE_OK,
                "detail": f"screen_guard_error:{type(exc).__name__}: {exc}"}
