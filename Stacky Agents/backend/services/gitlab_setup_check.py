"""Plan 259 F4 — 5 chequeos de SOLO LECTURA de una configuración GitLab.

NUNCA escribe: ni en GitLab, ni en disco, ni en os.environ.
NUNCA loguea el token ni lo devuelve.
allow_redirects=False: un 30x podría reenviar el header PRIVATE-TOKEN a otro host.

Camino HTTP propio y mínimo, deliberadamente separado de GitLabClient por tres
razones concretas: (1) GitLabClient lee GITLAB_TOKEN del entorno y TAPARÍA el
token que el operador acaba de tipear (E5) -> falso verde; (2) lanza
TrackerConfigError en __init__ si no hay token, y acá "no hay token" es un
RESULTADO, no una excepción; (3) acá hace falta allow_redirects=False, que el
cliente general no impone.
"""
from __future__ import annotations

import urllib.parse

import requests

_TIMEOUT_S = 8
_OK, _FAIL, _UNKNOWN = "ok", "fail", "unknown"
_ID_TLS = "chk-tls"


def _res(check_id, status, message, detail=""):
    return {"id": check_id, "status": status, "message": message, "detail": detail}


def _sesion_para(base: str, ca_bundle: str | None) -> tuple[requests.Session, str]:
    """Plan 295 F5 — sesión con el contexto OpenSSL GENUINO montado SOLO para el
    prefijo de este host.

    POR QUÉ: `app.py:26` llama `truststore.inject_into_ssl()`, que reemplaza
    `ssl.SSLContext` para TODO el proceso (ver `services/tls_openssl_context.py:3-13`:
    es NECESARIO por la inspección TLS de la red, y LETAL para el GitLab interno
    porque verifica por Windows CryptoAPI e ignora VERIFY_X509_PARTIAL_CHAIN).
    Por eso un `verify=<bundle>` a secas NO alcanza y el `requests.get()` pelado de
    esta sonda NACÍA ROTO con un síntoma que culpaba a la red.

    Se REUSA el adaptador del plan 276 (`gitlab_client._AdaptadorOpenSSL`), no se
    copia, y se copia el idioma exacto del cliente (`gitlab_client.py:155-181`):
    primero `resolver_ca_bundle`, después `crear_contexto_openssl`. Saltear el
    resolvedor haría que la sonda hable un TLS DISTINTO del que usa el sync cuando
    el bundle viene por entorno (STACKY_GITLAB_CA_BUNDLE / REQUESTS_CA_BUNDLE).

    Devuelve (sesion, motivo_tls). `motivo_tls != ""` significa que el bundle
    DECLARADO no se pudo usar: eso ya es un veredicto de chk-tls, sin tocar la red.
    """
    import config  # noqa: PLC0415  -- el MÓDULO; el valor vive en config.config

    from services.gitlab_client import _AdaptadorOpenSSL  # noqa: PLC0415
    from services.tls_openssl_context import (  # noqa: PLC0415
        CaBundleInvalido,
        crear_contexto_openssl,
    )
    from services.tls_pinning import resolver_ca_bundle  # noqa: PLC0415

    sesion = requests.Session()
    habilitado = bool(getattr(config.config, "STACKY_GITLAB_TLS_ADAPTER_ENABLED", True))
    if not habilitado:
        return sesion, ""  # flag OFF: sesión pelada, byte-idéntico a antes de F5
    try:
        ruta = resolver_ca_bundle(ca_bundle, estricto=True)
        contexto = crear_contexto_openssl(ruta)
    except CaBundleInvalido as exc:
        # NO se lanza: acá "el bundle no sirve" es un RESULTADO, igual que
        # "no hay token" (razón 2 del docstring :7-12 de este módulo).
        return sesion, str(exc)
    if contexto is not None and base:
        sesion.mount(base, _AdaptadorOpenSSL(contexto))
    return sesion, ""


def _get(sesion: requests.Session, base: str, path: str, token: str | None):
    headers = {"Accept": "application/json"}
    if token:
        headers["PRIVATE-TOKEN"] = token
    # allow_redirects=False SE CONSERVA: un 30x reenviaría PRIVATE-TOKEN a otro host.
    return sesion.get(f"{base}/api/v4{path}", headers=headers,
                      timeout=_TIMEOUT_S, allow_redirects=False)


def run_gitlab_checks(base_url: str, project_path: str, token: str,
                      engine_enabled: bool, engine_will_enable: bool = False,
                      *, ca_bundle: str | None = None) -> list[dict]:
    """Plan 259 v2 (hallazgo C5): `engine_enabled` es el estado REAL del servidor
    (`config.config.STACKY_GITLAB_ENABLED`) y el cliente no puede mentirlo.
    `engine_will_enable` es la INTENCIÓN declarada en el formulario (la casilla
    'Activar el motor GitLab'): no pinta un verde sobre el estado real, pinta el
    tercer estado honesto "apagado, se activa al crear". Sin esto, 'Verificar
    ahora' antes de crear daba SIEMPRE rojo en el camino feliz.

    Devuelve SIEMPRE 6 resultados, uno por chequeo de la guía, en todos los
    caminos de salida: la UI lo necesita para pintar la lista.

    Plan 295 F5 — eran 5; `chk-tls` es el sexto. `ca_bundle` es keyword-only y con
    default: los llamadores viejos (los tests del 259) siguen funcionando y nadie
    puede pisarlo por posición.
    """
    out: list[dict] = []

    # chk-flag — local, sin red. Tres estados, ninguno mentiroso.
    if engine_enabled:
        out.append(_res("chk-flag", _OK, "El motor GitLab está encendido."))
    elif engine_will_enable:
        out.append(_res("chk-flag", _OK,
                        "El motor GitLab está apagado ahora y se va a activar al crear el "
                        "proyecto, porque dejaste tildada la casilla."))
    else:
        out.append(_res("chk-flag", _FAIL,
                        "El motor GitLab está apagado y la casilla 'Activar el motor GitLab' "
                        "está destildada: la sincronización va a fallar."))

    base = (base_url or "").rstrip("/")
    if not base.startswith(("http://", "https://")):
        # Plan 295 F5 — chk-tls también acá: la UI necesita los 6 SIEMPRE.
        out.append(_res(_ID_TLS, _UNKNOWN,
                        "No se pudo evaluar el certificado: falta una URL válida."))
        out.append(_res("chk-instancia", _FAIL,
                        "La URL tiene que empezar con http:// o https://."))
        for cid in ("chk-token", "chk-scope", "chk-proyecto"):
            out.append(_res(cid, _UNKNOWN, "No se pudo probar: falta una URL válida."))
        return out

    # ── chk-tls (Plan 295 F5) ────────────────────────────────────────────────
    # Va ANTES de chk-instancia porque el handshake ocurre antes de que exista un
    # status HTTP. Sin este chequeo, un cert que no cierra salía como
    # chk-instancia=fail "No se pudo llegar a esa dirección" -> culpaba a la RED.
    sesion, motivo_bundle = _sesion_para(base, ca_bundle)
    if motivo_bundle:
        out.append(_res(_ID_TLS, _FAIL,
                        "El certificado de la empresa que declaraste no se pudo usar. "
                        "Revisá el campo 'Certificado de la empresa' del proyecto.",
                        motivo_bundle))
        for cid in ("chk-instancia", "chk-token", "chk-scope", "chk-proyecto"):
            out.append(_res(cid, _UNKNOWN,
                            "No se pudo probar: el certificado declarado no se pudo leer."))
        return out
    try:
        _get(sesion, base, "/version", None)
        out.append(_res(_ID_TLS, _OK, "El TLS cerró: el certificado del servidor es válido."))
    except requests.exceptions.SSLError as exc:
        # LA DISTINCIÓN QUE ESTE PLAN AGREGA. NO dice "no se pudo llegar".
        out.append(_res(_ID_TLS, _FAIL,
                        "El certificado del servidor no cerró la cadena de confianza. "
                        "Si tu GitLab usa un certificado de la empresa, pegalo en el "
                        "campo 'Certificado de la empresa' del proyecto.",
                        type(exc).__name__))
        for cid in ("chk-instancia", "chk-token", "chk-scope", "chk-proyecto"):
            out.append(_res(cid, _UNKNOWN, "No se pudo probar: el certificado no cerró."))
        return out
    except requests.RequestException:
        # Cualquier otro fallo de transporte NO es del certificado: chk-tls queda
        # en unknown y el veredicto lo da chk-instancia, que ya sabe decirlo.
        out.append(_res(_ID_TLS, _UNKNOWN,
                        "No se pudo evaluar el certificado: la dirección no respondió."))

    # chk-instancia — sin token
    try:
        r = _get(sesion, base, "/version", None)
        if r.status_code == 200:
            out.append(_res("chk-instancia", _OK, "La URL responde y es un GitLab."))
        elif r.status_code == 401:
            # v2 (C15): un 401 dice "pide autenticación", no "es GitLab". Un portal
            # SSO corporativo responde igual. No mentimos: es OK provisorio y el
            # veredicto real lo da chk-token, que sí habla con /user.
            out.append(_res("chk-instancia", _OK,
                            "La dirección responde y pide autenticación, como corresponde. "
                            "Si no fuera un GitLab, el control del token lo va a decir."))
        elif r.status_code in (301, 302, 307, 308):
            out.append(_res("chk-instancia", _FAIL,
                            "La URL redirige a otro lado. Usá la dirección final.",
                            f"HTTP {r.status_code}"))
            for cid in ("chk-token", "chk-scope", "chk-proyecto"):
                out.append(_res(cid, _UNKNOWN, "No se pudo probar: la URL redirige."))
            return out
        else:
            out.append(_res("chk-instancia", _FAIL,
                            "La dirección responde pero no parece un GitLab.",
                            f"HTTP {r.status_code}"))
    except requests.RequestException as exc:
        out.append(_res("chk-instancia", _FAIL,
                        "No se pudo llegar a esa dirección.", type(exc).__name__))
        for cid in ("chk-token", "chk-scope", "chk-proyecto"):
            out.append(_res(cid, _UNKNOWN, "No se pudo probar: la dirección no responde."))
        return out

    if not token:
        for cid, msg in (("chk-token",    "Falta pegar el token."),
                         ("chk-scope",    "No se pudo probar: falta el token."),
                         ("chk-proyecto", "No se pudo probar: falta el token.")):
            out.append(_res(cid, _FAIL if cid == "chk-token" else _UNKNOWN, msg))
        return out

    # chk-token
    # PII: /user devuelve el perfil del operador. Solo se toma `username` para que
    # reconozca la cuenta; el cuerpo crudo NO se loguea ni se devuelve (F4.b).
    try:
        r = _get(sesion, base, "/user", token)
        if r.status_code == 200:
            out.append(_res("chk-token", _OK,
                            f"Token válido (usuario: {r.json().get('username', '?')})."))
        elif r.status_code in (401, 403):
            out.append(_res("chk-token", _FAIL,
                            "El token no sirve: está mal copiado, venció o fue revocado."))
        else:
            out.append(_res("chk-token", _UNKNOWN,
                            "Respuesta inesperada al validar el token.", f"HTTP {r.status_code}"))
    except requests.RequestException as exc:
        out.append(_res("chk-token", _UNKNOWN, "No se pudo validar el token.", type(exc).__name__))

    # chk-scope — GitLab 15.x+; 404 en tokens de proyecto o versiones viejas => unknown, no rojo
    try:
        r = _get(sesion, base, "/personal_access_tokens/self", token)
        if r.status_code == 200:
            scopes = r.json().get("scopes") or []
            if "api" in scopes:
                out.append(_res("chk-scope", _OK, "El token tiene el permiso 'api'."))
            elif "read_api" in scopes:
                out.append(_res("chk-scope", _FAIL,
                                "El token solo puede LEER ('read_api'). Stacky no va a poder "
                                "comentar ni cerrar tickets.", f"permisos: {', '.join(scopes)}"))
            else:
                out.append(_res("chk-scope", _FAIL,
                                "Al token le falta el permiso 'api'.",
                                f"permisos: {', '.join(scopes) or 'ninguno'}"))
        else:
            out.append(_res("chk-scope", _UNKNOWN,
                            "Tu GitLab no informa los permisos del token. "
                            "Revisá a mano que tenga 'api'.", f"HTTP {r.status_code}"))
    except requests.RequestException as exc:
        out.append(_res("chk-scope", _UNKNOWN,
                        "No se pudieron consultar los permisos.", type(exc).__name__))

    # chk-proyecto
    pp = (project_path or "").strip()
    if not pp:
        out.append(_res("chk-proyecto", _FAIL, "Falta el path del proyecto."))
        return out
    enc = urllib.parse.quote(pp, safe="") if not pp.isdigit() else pp
    try:
        r = _get(sesion, base, f"/projects/{enc}", token)
        if r.status_code == 200:
            body = r.json()
            if body.get("issues_enabled") is False:
                out.append(_res("chk-proyecto", _FAIL,
                                "El proyecto existe pero tiene los Issues deshabilitados.",
                                body.get("name_with_namespace", "")))
            else:
                out.append(_res("chk-proyecto", _OK,
                                f"Proyecto encontrado: {body.get('name_with_namespace', pp)}."))
        elif r.status_code == 404:
            out.append(_res("chk-proyecto", _FAIL,
                            "No existe un proyecto con ese path, o tu usuario no tiene acceso."))
        else:
            out.append(_res("chk-proyecto", _UNKNOWN,
                            "Respuesta inesperada al buscar el proyecto.", f"HTTP {r.status_code}"))
    except requests.RequestException as exc:
        out.append(_res("chk-proyecto", _UNKNOWN,
                        "No se pudo buscar el proyecto.", type(exc).__name__))
    return out


__all__ = ["run_gitlab_checks"]
