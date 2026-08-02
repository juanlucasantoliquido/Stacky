"""Plan 283 F7 - La API del modulo de reuniones.

R6: el blueprint declara `url_prefix="/meetings"` y se registra DENTRO de
`api_bp` (que ya aporta `/api`), asi que la ruta final es `/api/meetings/...`.
Declarar `/api` aca produciria `/api/api/meetings/...`, el defecto que hizo
rechazar a los planes 72, 73 y 74.

El apagado por flag vive DENTRO de cada ruta (404), NO en el registro: el
registro se evalua una sola vez al importar el modulo, asi que gatearlo ahi
obligaria a REINICIAR el backend para que el operador viera el efecto de tocar
la flag desde el panel.

Cuerpo por JSON, no multipart: el repo tiene UN SOLO `request.files`
(`api/incidents.py`) y el patron dominante es JSON. La pantalla lee el archivo
de subtitulos con `FileReader` y manda texto. Cero dependencias, prueba
hermetica.

D6: este modulo NO importa `api.tickets` (8.000+ lineas, con cambios sin
commitear del operador) ni llama a `create_item`. La publicacion vive en
`api/meetings_publish.py`, con su propio blueprint. Hay un gate por AST.
"""
from __future__ import annotations

import threading
from datetime import datetime

from flask import Blueprint, jsonify, request

bp = Blueprint("meetings", __name__, url_prefix="/meetings")

# El codigo de dispositivo NUNCA vuelve al navegador: es material de
# autenticacion en transito. Vive en memoria del proceso, con su candado, y la
# pantalla solo ve el codigo CORTO que el operador tiene que tipear.
_DEVICE_CODES: dict[str, str] = {}
_DEVICE_LOCK = threading.Lock()


def _cfg():
    import config as _config

    return _config.config


def _habilitado() -> bool:
    return bool(getattr(_cfg(), "STACKY_MEETINGS_ENABLED", True))


def _graph_habilitado() -> bool:
    return bool(getattr(_cfg(), "STACKY_MEETINGS_GRAPH_ENABLED", True))


def _apagada():
    return jsonify({"ok": False, "error": "feature_disabled"}), 404


def _cuerpo() -> dict:
    return request.get_json(silent=True) or {}


def _proyecto() -> str:
    """Proyecto del pedido; si no viene, el activo del operador.

    Mono-operador sin login: esto NO es control de acceso, es alcance de datos.
    """
    explicito = (request.args.get("project") or "").strip()
    if not explicito:
        explicito = str(_cuerpo().get("project") or "").strip()
    if explicito:
        return explicito
    try:
        from project_manager import get_active_project

        return str(get_active_project() or "")
    except Exception:  # noqa: BLE001
        return ""


@bp.get("/health")
def health():
    """SIEMPRE 200, incluso con la flag apagada. Es lo que consume el gate de
    navegacion de la pantalla: si respondiera 404 el tab quedaria en `unknown`
    para siempre y el enlace directo moriria."""
    return jsonify({
        "ok": True,
        "flag_enabled": _habilitado(),
        "graph_enabled": _graph_habilitado(),
        "publish_enabled": bool(getattr(_cfg(), "STACKY_MEETINGS_PUBLISH_ENABLED", False)),
    })


@bp.get("")
def list_meetings():
    if not _habilitado():
        return _apagada()
    from services import meetings_store

    proyecto = _proyecto()
    return jsonify({"ok": True, "project": proyecto,
                    "meetings": meetings_store.list_meetings(proyecto)})


@bp.post("")
def create_meeting():
    if not _habilitado():
        return _apagada()
    from services import meetings_source, meetings_store

    cuerpo = _cuerpo()
    subject = str(cuerpo.get("subject") or "").strip()
    if not subject:
        return jsonify({"ok": False, "error": "subject_required",
                        "message": "Poné un titulo para la reunion."}), 400

    registro = meetings_source.from_manual(
        subject=subject,
        organizer=(str(cuerpo.get("organizer") or "").strip() or None),
        started_at=_fecha(cuerpo.get("started_at")),
        ended_at=_fecha(cuerpo.get("ended_at")),
    )
    mid = meetings_store.create_meeting(
        project=_proyecto(), subject=registro.subject, source=registro.source,
        external_id=str(cuerpo.get("external_id") or "").strip() or None,
        organizer=registro.organizer, started_at=registro.started_at,
        ended_at=registro.ended_at, join_url=str(cuerpo.get("join_url") or "") or None,
    )
    return jsonify({"ok": True, "id": mid}), 201


def _fecha(valor):
    from services.graph_client import parse_iso_utc

    return parse_iso_utc(valor)


@bp.get("/calendar")
def calendar():
    """NUNCA 500: devuelve el `estado` de la degradacion para que la pantalla lo
    pinte en castellano."""
    if not _habilitado():
        return _apagada()
    from services import meetings_source

    dias = request.args.get("dias", type=int) or 14
    return jsonify(meetings_source.list_upcoming(project=_proyecto(), dias=dias))


@bp.post("/<int:mid>/transcript")
def put_transcript(mid: int):
    """Guarda la transcripcion Y destila la minuta en el MISMO pedido (D8).

    Si el modelo falla, la reunion queda con la transcripcion intacta y estado
    `failed`, y la pantalla ofrece Reintentar. La transcripcion NUNCA se pierde.
    """
    if not _habilitado():
        return _apagada()
    from services import meeting_minutes, meetings_store, transcript_parser

    cuerpo = _cuerpo()
    contenido = str(cuerpo.get("content") or "")
    if not contenido.strip():
        return jsonify({"ok": False, "error": "content_required",
                        "message": "Pegá o subí el texto de la reunion."}), 400

    proyecto = _proyecto()
    if meetings_store.get_meeting_dict(mid, project=proyecto) is None:
        return jsonify({"ok": False, "error": "not_found"}), 404

    formato = str(cuerpo.get("format") or "").strip().lower()
    if formato not in ("vtt", "txt"):
        formato = transcript_parser.detect_format(contenido)
    meetings_store.save_transcript(mid, content=contenido, fmt=formato)

    resultado = meeting_minutes.build_minutes_payload(meeting_id=mid, project=proyecto)
    detalle = meetings_store.get_meeting_dict(mid, project=proyecto)
    return jsonify({"ok": bool(resultado.get("ok")), "estado": resultado.get("estado"),
                    "detalle": resultado.get("detalle", ""), "meeting": detalle}), 200


@bp.post("/<int:mid>/minutes/retry")
def retry_minutes(mid: int):
    if not _habilitado():
        return _apagada()
    from services import meeting_minutes, meetings_store

    proyecto = _proyecto()
    if meetings_store.get_meeting_dict(mid, project=proyecto) is None:
        return jsonify({"ok": False, "error": "not_found"}), 404
    if meetings_store.get_transcript(mid) is None:
        return jsonify({"ok": False, "error": "no_transcript",
                        "message": "Esta reunion todavia no tiene texto que analizar."}), 409

    resultado = meeting_minutes.build_minutes_payload(meeting_id=mid, project=proyecto)
    detalle = meetings_store.get_meeting_dict(mid, project=proyecto)
    return jsonify({"ok": bool(resultado.get("ok")), "estado": resultado.get("estado"),
                    "detalle": resultado.get("detalle", ""), "meeting": detalle}), 200


@bp.get("/<int:mid>")
def get_meeting(mid: int):
    if not _habilitado():
        return _apagada()
    from services import meetings_store

    detalle = meetings_store.get_meeting_dict(mid, project=_proyecto())
    if detalle is None:
        return jsonify({"ok": False, "error": "not_found"}), 404
    return jsonify({"ok": True, "meeting": detalle})


@bp.post("/graph/device-login")
def device_login():
    if not _habilitado():
        return _apagada()
    if not _graph_habilitado():
        return jsonify({"ok": False, "error": "graph_disabled",
                        "message": "La conexion con el calendario esta desactivada."}), 404
    from services import meetings_source
    from services.graph_client import GraphApiError, GraphConfigError

    proyecto = _proyecto()
    try:
        datos = meetings_source.crear_cliente(proyecto).start_device_login()
    except GraphConfigError as exc:
        return jsonify({"ok": False, "error": "sin_credenciales", "message": str(exc)}), 409
    except GraphApiError as exc:
        return jsonify({"ok": False, "error": exc.kind, "message": str(exc)}), 502

    with _DEVICE_LOCK:
        _DEVICE_CODES[proyecto] = datos["device_code"]
    # El `device_code` se OMITE a proposito: no vuelve nunca al navegador.
    return jsonify({"ok": True, "user_code": datos["user_code"],
                    "verification_uri": datos["verification_uri"],
                    "expires_in": datos["expires_in"], "interval": datos["interval"]})


@bp.post("/graph/device-poll")
def device_poll():
    if not _habilitado():
        return _apagada()
    if not _graph_habilitado():
        return jsonify({"ok": False, "error": "graph_disabled"}), 404
    from services import meetings_source
    from services.graph_client import GraphApiError, GraphConfigError

    proyecto = _proyecto()
    with _DEVICE_LOCK:
        device_code = _DEVICE_CODES.get(proyecto, "")
    if not device_code:
        return jsonify({"ok": False, "error": "sin_ingreso_en_curso",
                        "message": "Empezá el ingreso antes de consultar."}), 409

    try:
        salida = meetings_source.crear_cliente(proyecto).poll_device_login(device_code)
    except GraphConfigError as exc:
        return jsonify({"ok": False, "error": "sin_credenciales", "message": str(exc)}), 409
    except GraphApiError as exc:
        return jsonify({"ok": False, "error": exc.kind, "message": str(exc)}), 502

    if salida.get("estado") == "ok":
        with _DEVICE_LOCK:
            _DEVICE_CODES.pop(proyecto, None)
    return jsonify({"ok": salida.get("estado") == "ok", **salida})


@bp.get("/graph/probe")
def graph_probe():
    if not _habilitado():
        return _apagada()
    from services import meetings_source

    return jsonify(meetings_source.probe_graph(project=_proyecto()))


@bp.get("/graph/transcript/<path:external_id>")
def graph_transcript(external_id: str):
    """Baja la transcripcion de una reunion del calendario. Solo lectura."""
    if not _habilitado():
        return _apagada()
    if not _graph_habilitado():
        return jsonify({"ok": False, "error": "graph_disabled"}), 404
    from services import meetings_source
    from services.graph_client import GraphApiError, GraphConfigError

    try:
        texto = meetings_source.crear_cliente(_proyecto()).get_transcript(meeting_id=external_id)
    except GraphConfigError as exc:
        return jsonify({"ok": False, "error": "sin_credenciales", "message": str(exc)}), 409
    except GraphApiError as exc:
        return jsonify({"ok": False, "error": exc.kind, "message": str(exc)}), 502

    if texto is None:
        return jsonify({"ok": False, "error": "sin_transcripcion",
                        "message": "Esa reunion no tiene texto disponible."}), 404
    return jsonify({"ok": True, "content": texto, "format": "vtt",
                    "leido_a": datetime.utcnow().isoformat() + "Z"})
