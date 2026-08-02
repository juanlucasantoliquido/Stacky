"""Plan 283 F8 - El unico camino de este plan que ESCRIBE afuera.

D6: blueprint PROPIO. Este modulo NO importa `api.tickets` — ese archivo tiene
8.000+ lineas y cambios sin commitear del operador en este arbol, y un plan que
lo edite crea conflicto con trabajo real. La escritura va por el puerto
`get_tracker_provider(project).create_item(...)`, que es la fachada unica para
hablar con Azure DevOps o GitLab. Hay un gate por AST que lo verifica.

LAS DOS LLAVES (K6), las dos obligatorias:
  1. `STACKY_MEETINGS_PUBLISH_ENABLED` en ON — nace OFF por excepcion (B). Si
     no, 404. Gatea TAMBIEN el borrador: el borrador ya nombra el proyecto
     destino, asi que mostrarlo con la capacidad apagada seria ofrecer un
     callejon sin salida.
  2. Una confirmacion de un solo uso y con vencimiento. Si no, 409.

Y una tercera regla que no es una llave pero pesa igual (K8): el responsable
propuesto va SOLO si su atribucion quedo `confirmada` contra los que hablaron en
la reunion. En cualquier otro caso va vacio. El sistema no le asigna trabajo
real a una persona real por una atribucion que no pudo probar.
"""
from __future__ import annotations

import html

from flask import Blueprint, jsonify, request

bp = Blueprint("meetings_publish", __name__, url_prefix="/meetings-publish")

ACCION = "meetings_publish"
CONFIRM_TTL_S = 120.0
TITULO_TRACKER_MAX = 255


def _cfg():
    import config as _config

    return _config.config


def _publicacion_habilitada() -> bool:
    return bool(getattr(_cfg(), "STACKY_MEETINGS_ENABLED", True)) and bool(
        getattr(_cfg(), "STACKY_MEETINGS_PUBLISH_ENABLED", False)
    )


def _apagada():
    return jsonify({"ok": False, "error": "feature_disabled"}), 404


def _cuerpo() -> dict:
    return request.get_json(silent=True) or {}


def _proyecto() -> str:
    explicito = (request.args.get("project") or "").strip() or str(
        _cuerpo().get("project") or ""
    ).strip()
    if explicito:
        return explicito
    try:
        from project_manager import get_active_project

        return str(get_active_project() or "")
    except Exception:  # noqa: BLE001
        return ""


def _descripcion_html(item: dict, *, meeting: dict | None) -> str:
    """HTML, no texto plano: `TrackerItem.description_html` lo espera asi y el
    texto plano rompe el marcado del work item.

    Cero datos de mas: viaja LA CITA, nunca la transcripcion completa.
    """
    responsable = item.get("responsable") or ""
    atribucion = item.get("atribucion") or "sin_responsable"
    fecha = item.get("fecha_compromiso") or ""
    asunto = (meeting or {}).get("subject") or "una reunion"

    partes = [
        f"<p>Compromiso registrado en <b>{html.escape(str(asunto))}</b>.</p>",
    ]
    if responsable:
        if atribucion == "confirmada":
            partes.append(f"<p><b>Responsable:</b> {html.escape(str(responsable))}</p>")
        else:
            partes.append(
                "<p><b>Responsable propuesto:</b> "
                f"{html.escape(str(responsable))} — <i>no se pudo verificar contra "
                "las personas que hablaron en la reunion, asi que no se asigno a "
                "nadie. Revisalo antes de darlo por bueno.</i></p>"
            )
    else:
        partes.append("<p><b>Responsable:</b> sin definir.</p>")
    if fecha:
        partes.append(f"<p><b>Fecha comprometida:</b> {html.escape(str(fecha))}</p>")
    partes.append(
        "<blockquote>" + html.escape(str(item.get("cita") or "")) + "</blockquote>"
    )
    partes.append(
        f"<p>Generado por Stacky a partir de la reunion #{item.get('meeting_id')}.</p>"
    )
    return "".join(partes)


def _assignee(item: dict) -> str | None:
    """K8 - el sistema NO adivina de quien es el trabajo."""
    if (item.get("atribucion") or "") == "confirmada":
        return item.get("responsable") or None
    return None


def _borrador(item: dict, meeting: dict | None, proyecto: str) -> dict:
    return {
        "item_id": item.get("id"),
        "meeting_id": item.get("meeting_id"),
        "project": proyecto,
        "item_type": "Task",
        "title": str(item.get("titulo") or "")[:TITULO_TRACKER_MAX],
        "description_html": _descripcion_html(item, meeting=meeting),
        "labels": ["reunion"],
        "assignee": _assignee(item),
        "atribucion": item.get("atribucion"),
        "cita": item.get("cita"),
    }


@bp.post("/<int:item_id>/draft")
def draft(item_id: int):
    """No escribe NADA. Devuelve el borrador y una confirmacion de un solo uso."""
    if not _publicacion_habilitada():
        return _apagada()
    from services import confirm_token, meetings_store

    item = meetings_store.get_action_item_dict(item_id)
    if item is None:
        return jsonify({"ok": False, "error": "not_found"}), 404
    if item.get("estado") == "publicado":
        return jsonify({"ok": False, "error": "ya_publicado",
                        "message": "Este compromiso ya se publico.",
                        "external_id": item.get("external_id")}), 409

    proyecto = _proyecto()
    meeting = meetings_store.get_meeting_dict(int(item["meeting_id"]), project=proyecto)
    borrador = _borrador(item, meeting, proyecto)
    token = confirm_token.issue_token(
        ACCION, {"item_id": item_id, "project": proyecto, "title": borrador["title"]},
        CONFIRM_TTL_S,
    )
    return jsonify({"ok": True, "draft": borrador, "confirm_token": token,
                    "expires_in": int(CONFIRM_TTL_S)})


@bp.post("/<int:item_id>/confirm")
def confirm(item_id: int):
    if not _publicacion_habilitada():
        return _apagada()
    from services import confirm_token, meetings_store
    from services.tracker_provider import (
        TrackerApiError, TrackerConfigError, TrackerItem, get_tracker_provider,
    )

    token = str(_cuerpo().get("confirm_token") or "").strip()
    if not token:
        return jsonify({"ok": False, "error": "confirmacion_requerida",
                        "message": "Falta confirmar la publicacion."}), 409
    try:
        payload = confirm_token.consume_token(ACCION, token)
    except confirm_token.ConfirmTokenError as exc:
        return jsonify({"ok": False, "error": "confirmacion_invalida",
                        "message": str(exc)}), 409
    if int(payload.get("item_id") or 0) != item_id:
        return jsonify({"ok": False, "error": "confirmacion_de_otro_item"}), 409

    item = meetings_store.get_action_item_dict(item_id)
    if item is None:
        return jsonify({"ok": False, "error": "not_found"}), 404
    if item.get("estado") == "publicado":
        return jsonify({"ok": False, "error": "ya_publicado",
                        "external_id": item.get("external_id")}), 409

    proyecto = str(payload.get("project") or "") or _proyecto()
    meeting = meetings_store.get_meeting_dict(int(item["meeting_id"]), project=proyecto)
    borrador = _borrador(item, meeting, proyecto)

    try:
        provider = get_tracker_provider(proyecto)
        creado = provider.create_item(TrackerItem(
            item_type=borrador["item_type"],
            title=borrador["title"],
            description_html=borrador["description_html"],
            labels=("reunion",),
            assignee=borrador["assignee"],
            parent_id=None,
            fields={},
        ))
    except TrackerConfigError as exc:
        return jsonify({"ok": False, "error": "tracker_sin_configurar",
                        "message": str(exc)}), 409
    except TrackerApiError as exc:
        # El pendiente NO se marca publicado: quedaria mintiendo sobre un work
        # item que nunca existio.
        return jsonify({"ok": False, "error": exc.kind or "tracker_error",
                        "message": str(exc)}), 502

    externo = str((creado or {}).get("id") or (creado or {}).get("iid") or "")
    meetings_store.mark_item_published(
        item_id, tracker_type=str(getattr(provider, "name", "") or "desconocido"),
        external_id=externo,
    )
    return jsonify({"ok": True, "item_id": item_id, "external_id": externo,
                    "url": (creado or {}).get("web_url") or (creado or {}).get("url") or ""})
