"""
Persistencia de preferencias de usuario (avatares, nicknames, roles, agentes fijados).

GET  /api/preferences   → devuelve el objeto completo desde data/preferences.json
PUT  /api/preferences   → hace merge del payload en data/preferences.json
"""
import json
from pathlib import Path

from flask import Blueprint, jsonify, request

bp = Blueprint("preferences", __name__, url_prefix="/preferences")

_PREFS_FILE = Path("data/preferences.json")

_ALLOWED_KEYS = {"pinnedAgents", "agentAvatars", "agentNicknames", "agentRoles"}


def _read() -> dict:
    try:
        return json.loads(_PREFS_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _write(data: dict) -> None:
    _PREFS_FILE.parent.mkdir(exist_ok=True)
    _PREFS_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


@bp.get("")
def get_preferences():
    return jsonify(_read())


@bp.put("")
def put_preferences():
    payload = request.get_json(force=True, silent=True) or {}
    # Solo permitir claves conocidas para evitar polución del archivo
    filtered = {k: v for k, v in payload.items() if k in _ALLOWED_KEYS}
    existing = _read()
    existing.update(filtered)
    _write(existing)
    return jsonify({"ok": True})
