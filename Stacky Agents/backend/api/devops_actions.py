"""api/devops_actions.py - Catalogo de acciones DevOps (Plan 267).

url_prefix="/devops/actions" -> rutas /api/devops/actions/... (NO poner /api/ en el
prefix; mismo gotcha C2 del plan 73, ver api/devops_agent.py:3-4).

SOLO LECTURA. Este blueprint NO ejecuta ninguna accion: sirve el catalogo,
matchea una frase contra el y arma la propuesta. La ejecucion la hace el
frontend reusando los endpoints que YA existen (plan 267 §7.4: "ningun endpoint
de ejecucion nuevo").

La linea del Blueprint es copia LITERAL del plan 267 (doc :871): el nombre
"devops_actions" y el prefix "/devops/actions" son contrato. El import y el
register_blueprint viven en api/__init__.py y los dejo la costura P0; este
archivo NO necesita tocar ese archivo compartido.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

import config as _config

bp = Blueprint("devops_actions", __name__, url_prefix="/devops/actions")


def _catalog_off() -> bool:
    return not getattr(_config.config, "STACKY_DEVOPS_ACTION_CATALOG_ENABLED", False)


def _nl_off() -> bool:
    return not getattr(_config.config, "STACKY_DEVOPS_ACTION_NL_ENABLED", False)


def _agent_write_enabled() -> bool:
    """Flag 3, default OFF (excepcion dura (B) del plan): es la unica ruta por la
    que una frase en castellano puede terminar ESCRIBIENDO en un sistema real."""
    return bool(
        getattr(_config.config, "STACKY_DEVOPS_AGENT_ACTION_RUN_ENABLED", False)
    )


def _health_payload_for_catalog() -> dict:
    """Seam parcheable (F1 test 3). Envuelve api.devops._health_payload para que
    un test pueda inyectar un health sintetico sin monkeypatchear ~45 atributos
    de config.config [C13]. NUNCA lanza: si el health no se puede calcular
    devuelve {}, y visible_actions() deja solo las acciones de afuera del panel.
    """
    try:
        from api.devops import _health_payload

        return _health_payload()
    except Exception:  # pragma: no cover - defensa, no camino esperado
        return {}


@bp.get("/catalog")
def get_catalog():
    if _catalog_off():
        return jsonify({"error": "devops_action_catalog_disabled"}), 404
    from services.devops_action_catalog import catalog_payload

    return jsonify(catalog_payload(_health_payload_for_catalog()))


@bp.post("/propose")
def propose_action():
    """Frase en castellano -> ActionProposal tipada. DETERMINISTA: no llama a
    ningun modelo. Funciona identico en Codex CLI, Claude Code CLI y GitHub
    Copilot Pro: el runtime del body se ACEPTA y se ignora para el matching (a
    diferencia de api/devops_agent.py, que devuelve 400 para copilot)."""
    if _catalog_off():
        return jsonify({"error": "devops_action_catalog_disabled"}), 404
    if _nl_off():
        return jsonify({"error": "devops_action_nl_disabled"}), 404
    body = request.get_json(silent=True) or {}
    text = (body.get("text") or "").strip()
    if not text:
        return jsonify({"ok": False, "error": "text es obligatorio"}), 400
    supplied = body.get("params") if isinstance(body.get("params"), dict) else {}

    # v2 [C7] — el v1 usaba replace() sin importarlo: NameError seguro en el
    # camino ambiguo, y ningun test lo cubria.
    from dataclasses import replace

    from services import devops_action_proposal as dap
    from services.devops_action_catalog import assistant_actions, get_action
    from services.devops_action_matcher import is_ambiguous, match_intent

    health = _health_payload_for_catalog()
    # v2 [C5]: el universo del matcher son las acciones con "assistant" en su
    # reach, no todas las visibles.
    actions = assistant_actions(health)
    matches = match_intent(text, actions)
    if not matches:
        return jsonify({
            "ok": True,
            "proposal": None,
            "blocked_reason": dap.BLOCKED_NO_MATCH,
            "suggestions": [a.label for a in actions[:5]],
        })

    agent_write = _agent_write_enabled()
    top = get_action(matches[0].action_id)
    alts = [m.action_id for m in matches[1:]] if is_ambiguous(matches) else []
    prop = dap.build_proposal(top, supplied, matches[0].score, alts, agent_write)
    if alts:
        prop = replace(prop, blocked_reason=dap.BLOCKED_AMBIGUOUS)
    return jsonify({"ok": True, "proposal": dap.proposal_to_dict(prop)})


@bp.post("/preview")
def preview_action():
    """action_id + params EXPLICITOS -> la misma ActionProposal, sin matching.
    Es lo que llama la tarjeta cuando el operador corrige un parametro.
    SOLO LECTURA: no ejecuta nada, jamas."""
    if _catalog_off():
        return jsonify({"error": "devops_action_catalog_disabled"}), 404
    if _nl_off():
        return jsonify({"error": "devops_action_nl_disabled"}), 404
    body = request.get_json(silent=True) or {}
    action_id = (body.get("action_id") or "").strip()
    supplied = body.get("params") if isinstance(body.get("params"), dict) else {}

    from services import devops_action_proposal as dap
    from services.devops_action_catalog import get_action, visible_actions

    action = get_action(action_id)
    if action is None:
        return jsonify({"error": "devops_action_unknown"}), 404
    # Una accion gateada NO se previsualiza: si su health_key esta apagado no
    # esta alcanzable, y prometerle una vista previa al operador seria mentirle.
    visibles = {a.id for a in visible_actions(_health_payload_for_catalog())}
    if action.id not in visibles:
        return jsonify({"error": "devops_action_gated"}), 404

    prop = dap.build_proposal(action, supplied, 1.0, [], _agent_write_enabled())
    return jsonify({"ok": True, "proposal": dap.proposal_to_dict(prop)})
