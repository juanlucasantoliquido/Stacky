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

_ALLOWED_KEYS = {
    "pinnedAgents",
    "agentAvatars",
    "agentNicknames",
    "agentRoles",
    "agentTypes",
}


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


# ── Plan 173 — Store clave-valor de preferencias de UI (vistas guardadas) ──
#
# Persistir las vistas en el backend y no en localStorage es lo que hace que
# sobrevivan a limpiar el navegador o a cambiar de máquina. Sin tabla nueva ni
# blueprint nuevo: un sub-objeto dentro del archivo que ya existe.

import re as _re

import config as _config

_UI_KEY_RE = _re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_UI_STATE_KEY = "ui"
_UI_VALUE_MAX_BYTES = 65536  # 64 KB por clave: un preset es chico


def _saved_views_enabled() -> bool:
    return bool(getattr(_config.config, "STACKY_UI_SAVED_VIEWS_ENABLED", False))


@bp.get("/ui/<key>")
def get_ui_preference(key: str):
    if not _saved_views_enabled():
        return jsonify({"error": "feature_disabled"}), 404
    # La clave viaja en la URL: sin validar, `../x` escribiría fuera del
    # sub-objeto `ui` y podría pisar preferencias que esto no debe tocar.
    if not _UI_KEY_RE.match(key):
        return jsonify({"error": "invalid_key"}), 400
    # Ausente ⇒ null, NO 404: el frontend distingue "no hay preferencia" sin
    # tener que manejar un error para el caso más normal que existe.
    value = (_read().get(_UI_STATE_KEY) or {}).get(key)
    return jsonify({"key": key, "value": value})


@bp.put("/ui/<key>")
def put_ui_preference(key: str):
    if not _saved_views_enabled():
        return jsonify({"error": "feature_disabled"}), 404
    if not _UI_KEY_RE.match(key):
        return jsonify({"error": "invalid_key"}), 400

    payload = request.get_json(force=True, silent=True) or {}
    if "value" not in payload:
        return jsonify({"error": "value_required"}), 400

    value = payload["value"]
    # Se mide el tamaño ANTES de tocar el archivo: rechazar y guardar igual
    # sería peor que no validar.
    tamano = len(json.dumps(value, ensure_ascii=False).encode("utf-8"))
    if tamano > _UI_VALUE_MAX_BYTES:
        return jsonify({"error": "value_too_large", "max_bytes": _UI_VALUE_MAX_BYTES}), 413

    existing = _read()
    ui = dict(existing.get(_UI_STATE_KEY) or {})
    ui[key] = value
    existing[_UI_STATE_KEY] = ui
    _write(existing)
    return jsonify({"ok": True, "key": key})
