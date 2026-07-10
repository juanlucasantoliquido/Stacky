"""api/devops_connections.py — Plan 116: doctor de conexiones con remediación guiada.

url_prefix="/devops/connections" → /api/devops/connections/... (§3.12 plan 87).
Guard 404 si STACKY_DEVOPS_CONNECTION_DOCTOR_ENABLED=OFF. HITL: el chequeo corre
SOLO por POST explícito del operador; GET devuelve el último snapshot (o never_run).
El POST no exige body ⇒ NO aplica guard is_json (no hay payload mutante que forjar).
"""
from __future__ import annotations

import threading
from datetime import datetime

from flask import Blueprint, jsonify, abort

import config as _config
from services import connection_doctor

bp = Blueprint("devops_connections", __name__, url_prefix="/devops/connections")

_SNAPSHOT: dict | None = None
_SNAPSHOT_LOCK = threading.Lock()
_STALE_AFTER_SECONDS = 300


def _guard():
    if not getattr(_config.config, "STACKY_DEVOPS_CONNECTION_DOCTOR_ENABLED", False):
        abort(404)


def _is_stale(snap: dict) -> bool:
    ts = str(snap.get("generated_at") or "")
    try:
        parsed = datetime.fromisoformat(ts.replace("Z", ""))
    except Exception:
        return False
    return (datetime.utcnow() - parsed).total_seconds() > _STALE_AFTER_SECONDS


@bp.get("/health")
def health_route():
    _guard()
    with _SNAPSHOT_LOCK:
        snap = _SNAPSHOT
    if snap is None:
        return jsonify({"status": "never_run", "stale": False, "snapshot": None}), 200
    return jsonify({"status": "ready", "stale": _is_stale(snap), "snapshot": snap}), 200


@bp.post("/check")
def check_route():
    _guard()
    global _SNAPSHOT
    snap = connection_doctor.run_connection_check()
    with _SNAPSHOT_LOCK:
        _SNAPSHOT = snap
    return jsonify({"status": "ready", "stale": False, "snapshot": snap}), 200
