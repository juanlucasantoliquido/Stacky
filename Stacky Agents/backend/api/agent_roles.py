"""
api/agent_roles.py — Configuracion de roles por agente.

GET  /api/agent-roles          -> devuelve {filename: {stacky, utilitario, vscode}} para todos los agentes
PUT  /api/agent-roles          -> actualiza flags de uno o varios agentes
     body: { "AgentName.agent.md": { "stacky": bool, "utilitario": bool, "vscode": bool }, ... }

Cuando se detecta un agente nuevo (no guardado aun), devuelve las tres flags a True por defecto.
El estado se persiste en backend/data/agent_roles.json.

Portado de WS2 con adaptacion: config.agents_dir no existe en WS1 --
se usa config.VSCODE_PROMPTS_DIR directamente (equivalente funcional).
"""
import json
import logging
from pathlib import Path

from flask import Blueprint, jsonify, request

from config import config
from services import vscode_agents

logger = logging.getLogger(__name__)

bp = Blueprint("agent_roles", __name__, url_prefix="/agent-roles")

_ROLES_PATH = Path(__file__).resolve().parent.parent / "data" / "agent_roles.json"

_DEFAULT_ROLES = {"stacky": True, "utilitario": True, "vscode": True}


def _load() -> dict:
    if _ROLES_PATH.exists():
        try:
            return json.loads(_ROLES_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save(data: dict) -> None:
    _ROLES_PATH.parent.mkdir(parents=True, exist_ok=True)
    _ROLES_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


@bp.get("")
def get_roles():
    """Devuelve la configuracion de roles de todos los agentes conocidos."""
    # WS1 usa VSCODE_PROMPTS_DIR; WS2 usaria config.agents_dir (property no presente en WS1)
    agents_dir = getattr(config, "agents_dir", None) or config.VSCODE_PROMPTS_DIR
    agents = vscode_agents.list_agents(agents_dir)
    saved = _load()
    result = {}
    changed = False
    for agent in agents:
        fn = agent.filename
        if fn not in saved:
            saved[fn] = dict(_DEFAULT_ROLES)
            changed = True
        result[fn] = {
            "stacky":      bool(saved[fn].get("stacky", True)),
            "utilitario":  bool(saved[fn].get("utilitario", True)),
            "vscode":      bool(saved[fn].get("vscode", True)),
            "name":        agent.name,
            "description": agent.description,
        }
    if changed:
        _save(saved)
    return jsonify({"ok": True, "roles": result})


@bp.put("")
def put_roles():
    """Actualiza flags de uno o varios agentes.

    Body: { "AgentName.agent.md": { "stacky": bool, "utilitario": bool, "vscode": bool } }
    """
    body = request.get_json(silent=True) or {}
    saved = _load()
    for filename, flags in body.items():
        if not isinstance(flags, dict):
            continue
        entry = saved.setdefault(filename, dict(_DEFAULT_ROLES))
        for key in ("stacky", "utilitario", "vscode"):
            if key in flags:
                entry[key] = bool(flags[key])
    _save(saved)
    return jsonify({"ok": True})
