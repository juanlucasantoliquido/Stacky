"""Plan 296 F3/F4/F5 - API del copiloto conversacional del perfil de cliente.

⚠️ C7 - `api/__init__.py` declara `Blueprint("api", __name__, url_prefix="/api")`
y lo advierte textual: NUNCA "/api/...": api_bp ya lo pone. Este blueprint se
declara con url_prefix="" (igual que api/client_profile.py) y las rutas del
DECORADOR no llevan "/api". Copiar la URL final al decorador produce
/api/api/... y todos los tests de endpoint fallan sin explicacion.

    Decorador                                                    URL final
    /runtimes/profile                                            /api/runtimes/profile
    /projects/<n>/client-profile/copilot/state                   /api/projects/<n>/.../state
    /projects/<n>/client-profile/copilot/turn                    /api/projects/<n>/.../turn
    /projects/<n>/client-profile/copilot/propose                 /api/projects/<n>/.../propose
    /projects/<n>/client-profile/copilot/apply                   /api/projects/<n>/.../apply

Mono-operador sin login/roles: 404 = flag maestra apagada, 403 = flag de apply
apagada. NINGUNO significa "permiso".
"""
from __future__ import annotations

import json
import logging

from flask import Blueprint, jsonify, request

from project_manager import get_project_config
from services.client_profile import (
    ClientProfileError,
    complete_client_profile,
    load_client_profile,
    save_client_profile,
    validate_client_profile,
)
from services.config_transfer import record_event
from services.profile_completeness import (
    completitud,
    estado_perfil,
    preguntas_pendientes,
    proxima_pregunta,
)
from services.profile_copilot_session import (
    MAX_PREGUNTAS,
    MAX_SESSION_BYTES,
    TERMINAL_STATES,
    ProfileCopilotSession,
    advance,
    elegir_runtime,
    session_from_dict,
    session_to_dict,
)
from services.profile_patch import (
    aplicar_sobre,
    build_profile_patch,
    patch_from_dict,
    patch_to_dict,
)
from services.runtime_capabilities import RUNTIMES, save_run_preference
from services.runtime_profile import all_runtime_profiles, recomendar_runtime, runtime_profile

logger = logging.getLogger("stacky_agents.api.profile_copilot")

bp = Blueprint("profile_copilot", __name__, url_prefix="")

_MSG_PREF_NO_PERSISTE = (
    "La elección vale para esta sesión, pero no quedará guardada para la próxima."
)


def _actor() -> str:
    return (request.headers.get("X-User-Email") or "operator").strip() or "operator"


def _flag_off() -> bool:
    """Molde exacto de api/client_profile.py:326-328."""
    import config as _config
    return not getattr(_config.config, "STACKY_PROFILE_COPILOT_ENABLED", False)


def _apply_flag_off() -> bool:
    import config as _config
    return not getattr(_config.config, "STACKY_PROFILE_COPILOT_APPLY_ENABLED", False)


def _guard():
    """404 si la flag maestra esta apagada. Devuelve None si se puede seguir."""
    if _flag_off():
        from flask import abort
        abort(404)  # 404 = flag apagada, NO permiso (mono-operador sin roles)
    return None


def _no_encontrado(project_name: str):
    # Mismo texto que api/client_profile.py:170.
    return jsonify({"ok": False, "error": f"Proyecto '{project_name}' no encontrado"}), 404


# ── Contexto determinista para el banco de preguntas ─────────────────────────

def _estados_validos(project_name: str) -> tuple[str, ...]:
    try:
        from api.client_profile import _valid_states_for
        return tuple(_valid_states_for(project_name) or ())
    except Exception:  # noqa: BLE001 - best-effort; degrada a texto libre
        logger.debug("estados validos no disponibles para %s", project_name, exc_info=True)
        return ()


def _tipos_work_item(project_name: str) -> tuple[str, ...]:
    try:
        from api.client_profile import _work_item_types_for
        return tuple(_work_item_types_for(project_name) or ())
    except Exception:  # noqa: BLE001
        logger.debug("tipos de work item no disponibles para %s", project_name, exc_info=True)
        return ()


def _procesos_detectados(project_name: str) -> tuple[str, ...]:
    """C1 - `autodetect_process_catalog` es una RUTA FLASK, no un servicio, y
    services/ no puede importar api/. Este proveedor vive en la capa API (que si
    puede) y usa las MISMAS DOS FUENTES DETERMINISTAS de services/ que usa esa
    ruta: `services.project_autoprofile` (headings reales de los docs) y
    `services.grounding_observatory` (procesos citados en epicas publicadas).
    NUNCA inventa nombres. Una fuente caida no anula la otra; si las dos fallan
    la tupla queda vacia y la pregunta degrada a texto libre.
    """
    from pathlib import Path

    cfg = get_project_config(project_name) or {}
    existentes = (load_client_profile(project_name) or {}).get("process_catalog") or []
    vistos: set[str] = {
        (e.get("name") or "").strip().lower()
        for e in existentes
        if isinstance(e, dict) and (e.get("name") or "").strip()
    }
    nombres: list[str] = []

    # Fuente 1 - headings de docs.
    try:
        docs_root_str = (cfg.get("docs_root") or "").strip()
        if docs_root_str:
            docs_root = Path(docs_root_str)
            if docs_root.is_dir():
                from services.project_autoprofile import draft_profile_from_docs
                for item in (draft_profile_from_docs(docs_root).get("process_catalog") or []):
                    nombre = (item.get("name") or "").strip()
                    if nombre and nombre.lower() not in vistos:
                        vistos.add(nombre.lower())
                        nombres.append(nombre)
    except Exception:  # noqa: BLE001 - best-effort
        logger.debug("procesos: fuente docs fallo para %s", project_name, exc_info=True)

    # Fuente 2 - procesos citados en epicas publicadas.
    try:
        from api.agents import _collect_epic_summaries
        from services.grounding_observatory import suggest_process_catalog_entries
        resumenes, _ = _collect_epic_summaries(project_name)
        for item in suggest_process_catalog_entries(resumenes, existentes):
            nombre = (item.get("name") or "").strip()
            if nombre and nombre.lower() not in vistos:
                vistos.add(nombre.lower())
                nombres.append(nombre)
    except Exception:  # noqa: BLE001 - best-effort
        logger.debug("procesos: fuente ejecuciones fallo para %s", project_name, exc_info=True)

    return tuple(nombres)


def _contexto(project_name: str) -> dict:
    """Los tres parametros de contexto, cada uno best-effort e independiente."""
    def _seguro(fn):
        try:
            return fn(project_name)
        except Exception:  # noqa: BLE001 - una fuente caida degrada, no rompe
            logger.debug("fuente de contexto caida para %s", project_name, exc_info=True)
            return ()

    return {
        "estados_validos": _seguro(_estados_validos),
        "tipos_work_item": _seguro(_tipos_work_item),
        "procesos_detectados": _seguro(_procesos_detectados),
    }


# ── GET /api/runtimes/profile ────────────────────────────────────────────────

@bp.get("/runtimes/profile")
def get_runtimes_profile():
    """La ficha de 7 campos de los 3 runtimes + la recomendacion (que NO decide)."""
    _guard()
    project_name = (request.args.get("project") or "").strip() or None
    fichas = all_runtime_profiles(project_name=project_name)
    return jsonify({
        "ok": True,
        "runtimes": fichas,
        "recomendacion": recomendar_runtime(fichas),
    })


# ── GET /api/projects/<name>/client-profile/copilot/state ────────────────────

@bp.get("/projects/<string:project_name>/client-profile/copilot/state")
def get_copilot_state(project_name: str):
    _guard()
    if not get_project_config(project_name):
        return _no_encontrado(project_name)

    estado = estado_perfil(project_name)
    ctx = _contexto(project_name)
    preguntas = preguntas_pendientes(estado, **ctx)
    return jsonify({
        "ok": True,
        "estado": _estado_serializable(estado),
        "completitud": completitud(estado),
        "preguntas": [p.to_dict() for p in preguntas],
        "contexto": {k: list(v) for k, v in ctx.items()},
    })


def _estado_serializable(estado: dict) -> dict:
    """El estado tal cual, menos el perfil efectivo completo (que puede ser
    grande y no aporta al panel: lo que se muestra es lo que falta)."""
    return {k: v for k, v in estado.items() if k not in ("perfil", "perfil_guardado")}


# ── POST /api/projects/<name>/client-profile/copilot/turn ────────────────────

@bp.post("/projects/<string:project_name>/client-profile/copilot/turn")
def post_copilot_turn(project_name: str):
    _guard()
    if not get_project_config(project_name):
        return _no_encontrado(project_name)

    data = request.get_json(force=True, silent=True) or {}
    if not isinstance(data, dict):
        data = {}

    sesion_cruda = data.get("session")
    if sesion_cruda is not None:
        try:
            tamano = len(json.dumps(sesion_cruda, ensure_ascii=False))
        except Exception:  # noqa: BLE001
            tamano = MAX_SESSION_BYTES + 1
        if tamano > MAX_SESSION_BYTES:
            return jsonify({"ok": False, "error": "sesion_demasiado_grande",
                            "tope": MAX_SESSION_BYTES, "recibido": tamano}), 400

    sesion = session_from_dict(sesion_cruda)
    if not sesion.proyecto:
        from dataclasses import replace as _replace
        sesion = _replace(sesion, proyecto=project_name)

    # Sesion terminada: se responde 200 y la sesion NO se modifica.
    if sesion.state in TERMINAL_STATES:
        return jsonify({
            "ok": True,
            "session": session_to_dict(sesion),
            "mensaje": ("Esta conversación ya terminó. Abrí una nueva si querés "
                        "seguir configurando el perfil."),
            "pregunta": None,
            "completitud": completitud(estado_perfil(project_name)),
            "runtime_elegido": sesion.runtime_elegido,
            "cambio_sugerido": None,
            "preferencia_persistida": False,
            "advertencia": "",
        })

    # ── Runtime ──────────────────────────────────────────────────────────────
    runtime = (data.get("runtime") or "").strip()
    cambiar = bool(data.get("cambiar_runtime"))
    preferencia_persistida = False

    if runtime:
        if runtime not in RUNTIMES:
            return jsonify({"ok": False, "error": "runtime_desconocido",
                            "validos": list(RUNTIMES)}), 400
        anterior = sesion.runtime_elegido
        sesion, motivo = elegir_runtime(sesion, runtime, explicito=cambiar)
        if motivo == "cambio_de_runtime_requiere_confirmacion":
            return jsonify({"ok": False, "error": motivo,
                            "runtime_elegido": anterior}), 409
        if motivo:
            return jsonify({"ok": False, "error": motivo,
                            "runtime_elegido": anterior}), 400
        if sesion.state == "diagnostico" and anterior != sesion.runtime_elegido:
            # Riel existente. Con STACKY_RUN_SELECTION_PREFS_ENABLED OFF esto
            # devuelve False SIN lanzar y la respuesta lo dice.
            preferencia_persistida = bool(save_run_preference(
                project_name, {"runtime": sesion.runtime_elegido, "model": None, "effort": None}
            ))

    if not sesion.runtime_elegido:
        return jsonify({
            "ok": True,
            "session": session_to_dict(sesion),
            "mensaje": ("Antes de empezar, elegí con qué motor de ejecución querés "
                        "trabajar. Stacky no elige por vos."),
            "pregunta": None,
            "completitud": completitud(estado_perfil(project_name)),
            "runtime_elegido": "",
            "cambio_sugerido": None,
            "preferencia_persistida": preferencia_persistida,
            "advertencia": "",
        })

    # ── Tope de turnos ───────────────────────────────────────────────────────
    if sesion.turnos >= MAX_PREGUNTAS:
        sesion, _ = advance(sesion, "detenido", motivo_detencion="tope_de_turnos")
        return jsonify({
            "ok": True,
            "session": session_to_dict(sesion),
            "mensaje": ("Llegamos al tope de preguntas de una sesión. Revisá lo "
                        "propuesto y volvé a empezar si falta algo."),
            "pregunta": None,
            "completitud": completitud(estado_perfil(project_name)),
            "runtime_elegido": sesion.runtime_elegido,
            "cambio_sugerido": None,
            "preferencia_persistida": preferencia_persistida,
            "advertencia": "",
        })

    # ── Respuesta del operador ───────────────────────────────────────────────
    from dataclasses import replace as _replace

    respuesta = data.get("respuesta")
    if isinstance(respuesta, str) and respuesta.strip() and sesion.pregunta_actual:
        sesion = _replace(
            sesion,
            respondidas=tuple(dict.fromkeys(sesion.respondidas + (sesion.pregunta_actual,))),
            respuestas=sesion.respuestas + ((sesion.pregunta_actual, respuesta.strip()),),
        )

    sesion = _replace(sesion, turnos=sesion.turnos + 1)

    # ── Proxima pregunta ─────────────────────────────────────────────────────
    estado = estado_perfil(project_name)
    ctx = _contexto(project_name)
    sesion = _replace(sesion, tracker_type=estado.get("tracker_type") or "")
    pregunta = proxima_pregunta(estado, sesion.respondidas, **ctx)

    if pregunta is not None:
        sesion, _ = advance(sesion, "preguntando", pregunta_actual=pregunta.id)
        mensaje = pregunta.texto
    else:
        sesion = _replace(sesion, pregunta_actual="")
        mensaje = ("No queda nada obligatorio por preguntar. Revisá la propuesta "
                   "antes de aplicarla.")

    # ── Degradacion VISIBLE del runtime elegido ──────────────────────────────
    ficha = runtime_profile(sesion.runtime_elegido, project_name=project_name)
    advertencia = ""
    cambio_sugerido = None
    if not ficha["disponible"]:
        advertencia = ficha["disponibilidad_motivo"]
        # P4: se SUGIERE, no se aplica. `runtime_elegido` queda intacto.
        sugerencia = recomendar_runtime(all_runtime_profiles(project_name=project_name))
        if sugerencia.get("runtime") and sugerencia["runtime"] != sesion.runtime_elegido:
            cambio_sugerido = {"runtime": sugerencia["runtime"], "motivo": sugerencia["motivo"]}

    if runtime and not preferencia_persistida and sesion.state != "eleccion_runtime":
        advertencia = (advertencia + " " if advertencia else "") + _MSG_PREF_NO_PERSISTE

    return jsonify({
        "ok": True,
        "session": session_to_dict(sesion),
        "mensaje": mensaje,
        "pregunta": pregunta.to_dict() if pregunta is not None else None,
        "completitud": completitud(estado),
        "runtime_elegido": sesion.runtime_elegido,
        "cambio_sugerido": cambio_sugerido,
        "preferencia_persistida": preferencia_persistida,
        "advertencia": advertencia,
    })


# ── POST /api/projects/<name>/client-profile/copilot/propose ─────────────────

@bp.post("/projects/<string:project_name>/client-profile/copilot/propose")
def post_copilot_propose(project_name: str):
    """READ-ONLY: arma el diff y devuelve ademas el VEREDICTO DE VALIDACION del
    resultado. Si `validacion_previa["ok"]` es False, el boton de aplicar de la
    UI queda DESHABILITADO CON EL MOTIVO A LA VISTA (deshabilitar y explicar,
    nunca esconder). No escribe nada."""
    _guard()
    if not get_project_config(project_name):
        return _no_encontrado(project_name)

    data = request.get_json(force=True, silent=True) or {}
    if not isinstance(data, dict):
        data = {}

    base = load_client_profile(project_name) or {}
    propuesta = data.get("propuesta")
    if not isinstance(propuesta, dict):
        # Anexo B - "completar automaticamente campos": la propuesta por defecto
        # es el prellenado DETERMINISTA que ya existe. Cero modelo, cero red.
        estado = estado_perfil(project_name)
        try:
            propuesta = complete_client_profile(base, estado.get("tracker_type"))
        except Exception:  # noqa: BLE001 - el prellenado nunca puede tumbar la consulta
            logger.exception("prellenado determinista fallo para %s", project_name)
            propuesta = {}

    patch = build_profile_patch(proyecto=project_name, base=base, propuesta=propuesta)
    resultado = aplicar_sobre(base, patch)
    validacion = validate_client_profile(resultado).to_dict()
    # `normalized` puede ser el perfil entero: no aporta al panel y engorda la
    # respuesta. Lo que el operador necesita ver son errors y warnings.
    validacion.pop("normalized", None)

    return jsonify({
        "ok": True,
        "patch": patch_to_dict(patch),
        "validacion_previa": validacion,
    })


# ── POST /api/projects/<name>/client-profile/copilot/apply ───────────────────

#: Camino LEGAL hacia el estado terminal `aplicado`, en orden. El apply avanza la
#: sesion SOLO hacia adelante desde donde este: nunca inventa una transicion que
#: TRANSITIONS no declare, y nunca retrocede.
_CAMINO_A_APLICADO = (
    "eleccion_runtime", "diagnostico", "preguntando", "propuesta", "confirmando", "aplicado",
)


def _llevar_a_aplicado(sesion):
    """Avanza por transiciones LEGALES hasta `aplicado`. Si no puede (sesion ya
    terminal), devuelve la sesion tal cual. NUNCA lanza."""
    try:
        indice = _CAMINO_A_APLICADO.index(sesion.state)
    except ValueError:
        indice = -1
    for destino in _CAMINO_A_APLICADO[indice + 1:]:
        nueva, motivo = advance(sesion, destino)
        if motivo:
            break
        sesion = nueva
    return sesion


@bp.post("/projects/<string:project_name>/client-profile/copilot/apply")
def post_copilot_apply(project_name: str):
    """El copiloto EJECUTA. El primer fallo corta y NO escribe nada."""
    # 1 - flag maestra.
    _guard()

    # 2 - flag de escritura. 403 = FLAG APAGADA, no permiso (mono-operador).
    if _apply_flag_off():
        return jsonify({
            "ok": False,
            "error": "apply_deshabilitado",
            "flag": "STACKY_PROFILE_COPILOT_APPLY_ENABLED",
            "mensaje": ("Aplicar cambios al perfil está apagado. Se puede activar "
                        "desde Configuración > Arnés."),
        }), 403

    # 3 - proyecto.
    if not get_project_config(project_name):
        return _no_encontrado(project_name)

    data = request.get_json(force=True, silent=True) or {}
    if not isinstance(data, dict):
        data = {}

    # 4 - patch.
    patch = patch_from_dict(data.get("patch"))
    if not patch.cambios:
        return jsonify({"ok": False, "error": "patch_vacio"}), 400

    # 5 - el token se RECALCULA desde el patch recibido. Si el diff cambio desde
    #     que el operador lo vio, el token no valida y no se escribe nada.
    enviado = str(data.get("confirm_token") or "")
    if enviado != patch.confirm_token:
        return jsonify({
            "ok": False,
            "error": "patch_desactualizado",
            "mensaje": "La propuesta cambió desde que la viste. Volvé a revisarla.",
        }), 409

    # 6 - confirmacion POR SECCION sensible.
    confirmadas = {str(x) for x in (data.get("confirmaciones_sensibles") or [])}
    faltantes = sorted({c.path[0] for c in patch.cambios if c.sensible} - confirmadas)
    if faltantes:
        return jsonify({
            "ok": False, "error": "confirmacion_faltante", "secciones": faltantes,
        }), 409

    # 7 - resultado (PURO, todavia no escribe).
    base = load_client_profile(project_name) or {}
    resultado = aplicar_sobre(base, patch)

    # 8 - segundo candado de P6 y gate duro: si no valida, NO se escribe.
    v = validate_client_profile(resultado)
    if not v.ok:
        return jsonify({"ok": False, "error": "perfil_invalido", "errors": list(v.errors)}), 400

    # 9 - escritura, bajo el MISMO lock que el resto del perfil (uno solo para
    #     todo el perfil: dos escrituras por caminos distintos se pisarian).
    from api.client_profile import _PROFILE_WRITE_LOCK  # api -> api es legal
    with _PROFILE_WRITE_LOCK:
        try:
            normalized = save_client_profile(project_name, resultado)
        except ClientProfileError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        except Exception as exc:  # noqa: BLE001
            logger.exception("apply del copiloto fallo para %s", project_name)
            return jsonify({"ok": False, "error": str(exc)}), 500

    sesion = session_from_dict(data.get("session"))

    # 10 - auditoria. Molde exacto de api/client_profile.py:362-369.
    record_event(
        action="profile_copilot_apply",
        project=project_name,
        result="applied",
        actor=_actor(),
        schema_version=int(normalized.get("schema_version") or 1),
        detail={
            "paths": [".".join(c.path) for c in patch.cambios],
            "runtime_elegido": sesion.runtime_elegido,
            "sensibles": sorted({c.path[0] for c in patch.cambios if c.sensible}),
        },
    )

    # 11 - la sesion llega a su estado terminal. El runtime elegido NO se toca.
    sesion = _llevar_a_aplicado(sesion)
    return jsonify({
        "ok": True,
        "session": session_to_dict(sesion),
        "completitud": completitud(estado_perfil(project_name)),
        "aplicados": len(patch.cambios),
        "profile": normalized,
    })
