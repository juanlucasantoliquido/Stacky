"""api/pipeline_copilot.py — Sesion del copiloto de pipelines (Plan 279 F5).

url_prefix="/pipeline-copilot" -> rutas /api/pipeline-copilot/... (NO poner /api/
en el prefix; mismo gotcha C2 del plan 73, ver api/devops_agent.py:3-4).

SOLO ESTADO. Este blueprint NO ejecuta ninguna accion: crea, lee y avanza la
sesion. Toda escritura sigue pasando por la tarjeta de confirmacion del frontend
(D1), que reusa los endpoints que YA existen. El caso 8 de
tests/test_pipeline_copilot_api.py lo gatea por `ast`.
"""
from __future__ import annotations

import json

from flask import Blueprint, jsonify, request

import config as _config
from services.pipeline_session import (
    PipelineSession,
    advance,
    next_question,
    session_from_dict,
    session_to_dict,
    undo_hint,
)

bp = Blueprint("pipeline_copilot", __name__, url_prefix="/pipeline-copilot")

_CONVERSATION_ADO_ID = -2

#: Clave bajo la que la sesion vive dentro del JSON de Ticket.description (D4).
_SESSION_KEY = "pipeline_session"

#: [C6] Las 2 acciones que envuelven /api/pipeline-generator/{preview,commit},
#: que hacen abort(404) si STACKY_PIPELINE_GENERATOR_ENABLED esta OFF. NO se crea
#: una flag equivalente: se DEGRADA HONESTO nombrando la flag que falta.
_GENERATOR_ACTIONS = ("devops.pipeline_new.draft", "devops.pipeline_new.commit")
_GENERATOR_FLAG = "STACKY_PIPELINE_GENERATOR_ENABLED"


def _flag_off() -> bool:
    """Lee config.config, NUNCA os.getenv con default local (lo gatea
    tests/test_flags_env_read_meta.py)."""
    return not getattr(_config.config, "STACKY_PIPELINE_COPILOT_ENABLED", False)


def _generator_off() -> bool:
    return not getattr(_config.config, _GENERATOR_FLAG, False)


def _meta(ticket) -> dict:
    """JSON de Ticket.description, tolerante. Duplicado adrede de
    api/devops_agent.py:_chat_meta para no crear un import circular."""
    if not ticket or not ticket.description:
        return {}
    try:
        cargado = json.loads(ticket.description) if isinstance(ticket.description, str) else {}
    except (json.JSONDecodeError, TypeError):
        return {}
    return cargado if isinstance(cargado, dict) else {}


def _payload(session: PipelineSession) -> dict:
    """Cuerpo comun de las respuestas que devuelven la sesion."""
    faltantes = list(_GENERATOR_ACTIONS) if _generator_off() else []
    return {
        "ok": True,
        "session": session_to_dict(session),
        "unavailable_actions": faltantes,
        "unavailable_reason": _GENERATOR_FLAG if faltantes else "",
    }


def _leer(conversation_id: int):
    """(session, meta) si la conversacion existe; (None, None) si no."""
    from db import session_scope
    from models import Ticket

    with session_scope() as db:
        ticket = db.query(Ticket).filter_by(
            id=conversation_id, ado_id=_CONVERSATION_ADO_ID
        ).first()
        if ticket is None:
            return None, None
        meta = _meta(ticket)
    return session_from_dict(meta.get(_SESSION_KEY)), meta


def _log_transicion(conversation_id: int, origen: str, destino: str,
                    action_id: str) -> None:
    """Plan 279 F9 — UNA linea por transicion, calcando
    api/devops_actions.py:_log_si_quedo_bloqueada.

    CERO PII: solo conversation_id, estados y action_id (constantes del
    catalogo). NO se registra el texto del operador, ni el proyecto, ni la rama,
    ni ningun nombre de variable, NI el undo_hint (que contiene la rama).
    NUNCA lanza: el log no puede romper la request.
    """
    try:
        from services.stacky_logger import logger as stacky_logger

        stacky_logger.info(
            "pipeline_copilot",
            "session_advance",
            conversation_id=conversation_id,
            origen=origen,
            destino=destino,
            action_id=action_id,
        )
    except Exception:  # pragma: no cover - el log nunca puede romper la request
        pass


@bp.get("/session/<int:conversation_id>")
def get_session(conversation_id: int):
    if _flag_off():
        return jsonify({"error": "pipeline_copilot_disabled"}), 404
    session, meta = _leer(conversation_id)
    if session is None:
        return jsonify({"ok": False, "error": "conversation_not_found"}), 404
    return jsonify(_payload(session))


@bp.post("/session/<int:conversation_id>/advance")
def advance_session(conversation_id: int):
    """Mueve el estado. NO ejecuta acciones."""
    if _flag_off():
        return jsonify({"error": "pipeline_copilot_disabled"}), 404

    body = request.get_json(silent=True) or {}
    destino = (body.get("to") or "").strip()
    campos = body.get("fields") if isinstance(body.get("fields"), dict) else {}

    from db import session_scope
    from models import Ticket

    with session_scope() as db:
        ticket = db.query(Ticket).filter_by(
            id=conversation_id, ado_id=_CONVERSATION_ADO_ID
        ).first()
        if ticket is None:
            return jsonify({"ok": False, "error": "conversation_not_found"}), 404

        meta = _meta(ticket)
        actual = session_from_dict(meta.get(_SESSION_KEY))
        origen = actual.state

        # session_from_dict normaliza los tipos (tuplas de str), asi que los
        # campos del body pasan por el mismo saneador que la persistencia.
        crudos = {**session_to_dict(actual), **campos, "state": origen}
        saneada = session_from_dict(crudos)

        nueva, motivo = advance(saneada, destino)
        if motivo:
            return jsonify({
                "ok": False, "error": "transicion_ilegal", "detail": motivo,
            }), 409

        # D4: se CONSERVA cualquier otra clave del JSON (ej. server_alias del
        # plan 108). Se lee, se muta SOLO pipeline_session, se reescribe.
        meta[_SESSION_KEY] = session_to_dict(nueva)
        meta.setdefault("kind", "devops_chat")
        ticket.description = json.dumps(meta)

    _log_transicion(conversation_id, origen, nueva.state, nueva.last_action_id)
    return jsonify(_payload(nueva))


@bp.get("/session/<int:conversation_id>/question")
def next_question_route(conversation_id: int):
    if _flag_off():
        return jsonify({"error": "pipeline_copilot_disabled"}), 404
    session, _ = _leer(conversation_id)
    if session is None:
        return jsonify({"ok": False, "error": "conversation_not_found"}), 404
    return jsonify({"ok": True, "question": next_question(session)})


@bp.get("/session/<int:conversation_id>/undo-hint")
def undo_hint_route(conversation_id: int):
    """[ADICION ARQUITECTO] Como deshacer la escritura que se esta por confirmar.
    "" mientras todavia no aplique."""
    if _flag_off():
        return jsonify({"error": "pipeline_copilot_disabled"}), 404
    session, _ = _leer(conversation_id)
    if session is None:
        return jsonify({"ok": False, "error": "conversation_not_found"}), 404
    return jsonify({"ok": True, "undo_hint": undo_hint(session)})
