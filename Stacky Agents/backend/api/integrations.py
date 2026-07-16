"""api/integrations.py — Plan 148. Estado de salud de integraciones (read-only) +
reset manual. Registrado en backend/api/__init__.py (patrón del repo: los blueprints
se registran en __init__.py, NO en app.py)."""
from flask import Blueprint, jsonify, request

bp = Blueprint("integrations", __name__, url_prefix="/integrations")

_LABELS = {
    "ado_pat_expired": {"title": "PAT de Azure DevOps expirado",
        "action": "Renová el PAT en la Caja Fuerte", "vault": True},
    "ado_project_not_found": {"title": "Proyecto ADO inexistente",
        "action": "Revisá el nombre del proyecto en la config", "vault": False},
    "jira_not_configured": {"title": "Jira sin credenciales",
        "action": "Cargá las credenciales de Jira en la Caja Fuerte", "vault": True},
    "local_llm_unavailable": {"title": "Modelo local no disponible",
        "action": "Iniciá el servidor local (Ollama) o instalá el modelo", "vault": False},
    "ado_identity_unresolved": {"title": "Identidad ADO no resuelta",
        "action": "Renová el PAT en la Caja Fuerte", "vault": True},
}


@bp.get("/status")
def integrations_status():
    # NOTA: aquí `from config import config` importa la INSTANCIA (mismo patrón
    # ya establecido en app.py:34 y en decenas de imports locales del repo, p.ej.
    # api/tickets.py:6920, log_streamer.py:184, services/docs_rag.py:393) -> leer
    # `config.STACKY_...` bare es correcto; NO hace falta `.config` extra aquí
    # (eso es solo para archivos que importan `config` como MODULO, ver F3(b)/F5(b)).
    from config import config
    if not getattr(config, "STACKY_INTEGRATION_DEGRADATION_ENABLED", True):
        return jsonify({"enabled": False, "integrations": []})
    from services import integration_breaker as _brk
    out = []
    for key, st in _brk.all_states().items():
        if not st.open:  # solo reportar las caídas
            continue
        meta = _LABELS.get(st.reason, {"title": st.reason, "action": "", "vault": False})
        integ, _, project = key.partition("::")
        out.append({"key": key, "integration": integ, "project": project,
                    "reason": st.reason, "title": meta["title"], "action": meta["action"],
                    "vault": meta["vault"], "message": st.message,
                    "retry_after": st.retry_after, "seconds_until_retry": st.seconds_until_retry})
    return jsonify({"enabled": True, "integrations": out})


@bp.post("/<integration>/reset")
def integrations_reset(integration: str):
    """Acción HITL: el operador pide reintentar YA (tras renovar la credencial)."""
    from services import integration_breaker as _brk
    # [C4] project viene del querystring (el banner reenvía el 'project' que /status
    # ya devolvió, byte-idéntico, para que la key del reset matchee la de apertura).
    project = request.args.get("project")
    if project is None and request.is_json:
        project = (request.get_json(silent=True) or {}).get("project")
    _brk.reset(integration, project)
    return jsonify({"ok": True, "integration": integration, "project": project})
