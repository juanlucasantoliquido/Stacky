"""api/db_compare_demo.py — Plan 183 F3: sandbox de demostración del comparador.

Blueprint aparte con el MISMO url_prefix="/db-compare" (nombre distinto,
rutas /demo/* libres — verificado contra api/db_compare.py). Doble gate de
flags: master 122 + la flag propia del sandbox. Seed/delete son SIEMPRE por
click del operador (HITL); el DELETE es idempotente e inocuo fuera del sandbox
(guard doble en el servicio, §3.1).
"""
from __future__ import annotations

import config as _config
from flask import Blueprint, jsonify

from services import dbcompare_demo

bp = Blueprint("db_compare_demo", __name__, url_prefix="/db-compare")


def _require_demo_enabled():
    # Idioma api/db_compare.py:27-29 — la instancia de flags es config.config.
    if not getattr(_config.config, "STACKY_DB_COMPARE_ENABLED", False):
        return jsonify({
            "ok": False,
            "error": "Comparador de BD deshabilitado (STACKY_DB_COMPARE_ENABLED).",
        }), 403
    if not getattr(_config.config, "STACKY_DB_COMPARE_DEMO_ENABLED", False):
        return jsonify({
            "ok": False,
            "error": "Sandbox de demostración deshabilitado (STACKY_DB_COMPARE_DEMO_ENABLED).",
        }), 403
    return None


@bp.post("/demo/seed")
def seed_demo_route():
    gate = _require_demo_enabled()
    if gate:
        return gate
    try:
        result = dbcompare_demo.seed_demo_environments()
    except ValueError as exc:  # fix C4 — alias ajeno ocupa el prefijo reservado
        return jsonify({"ok": False, "error": str(exc)}), 409
    except RuntimeError as exc:  # fix C1 — keyring no disponible
        return jsonify({"ok": False, "error": str(exc)}), 503
    except OSError as exc:  # sqlite/FS inesperado — controlado, sin 500 crudo
        return jsonify({"ok": False, "error": str(exc)}), 500
    return jsonify({"ok": True, **result})


@bp.get("/demo/status")
def demo_status_route():
    gate = _require_demo_enabled()
    if gate:
        return gate
    return jsonify({"ok": True, "status": dbcompare_demo.demo_status()})


@bp.delete("/demo")
def delete_demo_route():
    gate = _require_demo_enabled()
    if gate:
        return gate
    result = dbcompare_demo.delete_demo()
    if result.get("error"):  # fix C3 — archivos lockeados por una corrida activa
        return jsonify({"ok": False, **result}), 409
    return jsonify({"ok": True, **result})
