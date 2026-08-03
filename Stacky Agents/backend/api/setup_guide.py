"""api/setup_guide.py - Guia de configuracion verificable (Plan 259).

url_prefix="/setup-guide" -> rutas /api/setup-guide/... (NO poner /api/ en el
prefix: `api_bp` de api/__init__.py:84 ya aporta el /api).

=============================================================================
STUB CREADO POR LA COSTURA P0 (2026-07-28). CERO RUTAS A PROPOSITO.
-----------------------------------------------------------------------------
Existe unicamente para que `api/__init__.py` pueda registrar este blueprint
AHORA, sin que el arranque explote con ImportError, y asi el paquete P2 (plan
259) no tenga que editar `api/__init__.py` -- que es un archivo compartido con
el paquete P3 (plan 267).

DUENO EXCLUSIVO: el paquete P2 / plan 259. Llena este archivo con sus 2 rutas
(F4.b del plan):
    GET  /api/setup-guide/<provider>
    POST /api/setup-guide/gitlab/verify
NO hace falta tocar `api/__init__.py`: el import y el register_blueprint YA ESTAN.

OJO -- ESTO NO SALIO DEL PLAN, SE DERIVO (el plan 259 no declara ni el nombre
del Blueprint, ni la variable, ni el url_prefix; `url_prefix` aparece 0 veces en
sus 2299 lineas). Se derivo de las URLs finales que el plan SI especifica mas la
convencion de la casa (`bp`, y el prefix sin /api). Si el plan 259 acaba
declarando otro prefix, este es el lugar para cambiarlo -- pero entonces hay que
cambiarlo tambien en el frontend.

TRAMPA que el criterio binario del propio plan NO detecta: F4 verifica que
`app.url_map` contenga "setup-guide" filtrando por esa cadena. Con el prefix mal
puesto las rutas quedan en /api/api/setup-guide/... y ese filtro PASA IGUAL,
porque la cadena "setup-guide" sigue presente. Verificar la ruta COMPLETA.
=============================================================================
"""
from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

bp = Blueprint("setup_guide", __name__, url_prefix="/setup-guide")


def _flag(name: str, default: bool = True) -> bool:
    """Lee la flag de la INSTANCIA (config.config), no del modulo.

    En ESTE archivo el import es local y se llama `config`, asi que la instancia
    es `config.config`. Regla operativa de la casa: mira como importa el archivo
    que estas editando, NO copies el prefijo de otra fase (en api/diag.py es
    `_config.config` — v4, hallazgo N3).
    """
    try:
        import config
        return bool(getattr(config.config, name, default))
    except Exception:
        return default


@bp.get("/<string:provider>")
def get_setup_guide(provider: str):
    """Devuelve la guia de configuracion de un proveedor. 404 si no tiene guia.

    Texto de SOLO LECTURA servido desde un modulo puro: sin red, sin escritura,
    sin modelo.
    """
    if not _flag("STACKY_SETUP_GUIDE_ENABLED"):
        return jsonify({"ok": False, "error": "guía deshabilitada"}), 403

    from services.setup_guides import guide_as_dict

    guide = guide_as_dict(provider)
    if guide is None:
        return jsonify({
            "ok": False,
            "error": f"No hay guía de configuración para '{provider}'.",
        }), 404
    return jsonify({"ok": True, "guide": guide})


@bp.post("/gitlab/verify")
def verify_gitlab_setup():
    """Corre los 5 chequeos de SOLO LECTURA contra la instancia que el operador
    escribio en el formulario.

    `engine_enabled` NO viene del cliente: lo lee el servidor de
    `config.config.STACKY_GITLAB_ENABLED`. Lo unico que aporta el cliente es
    `gitlab_enable_engine`, que viaja como `engine_will_enable` — la INTENCION
    declarada, que nunca pinta verde sobre un motor apagado sin decirlo (v2, C5).

    DATOS PERSONALES: el chequeo del token habla con /user de GitLab y esa
    respuesta trae el nombre de usuario del operador. NUNCA se loguea ni se
    devuelve el cuerpo crudo: solo el veredicto de cada chequeo. La linea de log
    es exclusivamente el mapa id -> status.
    """
    if not _flag("STACKY_SETUP_GUIDE_VERIFY_ENABLED"):
        return jsonify({"ok": False, "error": "verificación deshabilitada"}), 403

    from services.gitlab_setup_check import run_gitlab_checks

    body = request.get_json(force=True, silent=True) or {}
    try:
        checks = run_gitlab_checks(
            base_url=str(body.get("gitlab_url") or "").strip(),
            project_path=str(body.get("gitlab_project") or "").strip(),
            token=str(body.get("gitlab_token") or "").strip(),
            # El estado REAL lo pone el servidor; la clave `engine_enabled` del
            # body se IGNORA a proposito (el cliente no puede forzar un verde).
            engine_enabled=_flag("STACKY_GITLAB_ENABLED", default=False),
            engine_will_enable=bool(body.get("gitlab_enable_engine", False)),
            # Plan 295 F5 — el certificado que el operador ACABA de tipear (no el
            # guardado): mismo criterio que el token. Sin esto la sonda hablaba un
            # TLS distinto del que usa el sync y daba rojo con el producto andando.
            ca_bundle=str(body.get("gitlab_ca_bundle") or "").strip() or None,
        )
    except Exception as exc:
        logger.warning("setup-guide verify gitlab: fallo inesperado: %s", type(exc).__name__)
        return jsonify({"ok": False, "error": "No se pudo completar la verificación."}), 500

    logger.info("setup-guide verify gitlab: %s", {c["id"]: c["status"] for c in checks})
    return jsonify({"ok": True, "checks": checks})
