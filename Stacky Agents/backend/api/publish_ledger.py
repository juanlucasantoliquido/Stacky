"""api/publish_ledger.py — Plan 153.

Panel de Diagnostico del ledger de publicaciones + acciones humanas 1-click.
El sweep (GET) SOLO lista/marca; re-publicar y descartar son SIEMPRE decisiones
del operador (human-in-the-loop). Registrado bajo api_bp (/api) => rutas efectivas
en /api/publish-ledger/... (el sub-blueprint NO lleva el /api, lo agrega el padre).
"""
from __future__ import annotations

from flask import Blueprint, jsonify

bp = Blueprint("publish_ledger", __name__, url_prefix="/publish-ledger")


def _row_dict(execution_id: int):
    from db import session_scope
    from services.publish_ledger import PublishLedgerEntry
    with session_scope() as session:
        row = (
            session.query(PublishLedgerEntry)
            .filter(PublishLedgerEntry.execution_id == int(execution_id))
            .one_or_none()
        )
        return row.to_dict() if row is not None else None


@bp.get("")
def list_ledger():
    from config import config as cfg
    from services.publish_ledger import snapshot_stuck
    enabled = bool(getattr(cfg, "STACKY_PUBLISH_IDEMPOTENT_GUARD_ENABLED", False))
    return jsonify({"enabled": enabled, **snapshot_stuck()}), 200


@bp.post("/<int:execution_id>/republish")
def republish(execution_id: int):
    """ACCION HUMANA — libera la fila y reintenta la publicacion. Nunca automatico."""
    row = _row_dict(execution_id)
    if row is None:
        return jsonify({"error": "no_ledger_row"}), 404
    if row["status"] == "posted":
        return jsonify({"error": "already_posted"}), 409
    from services.publish_ledger import release
    from services.agent_completion_internal import _attempt_publish
    release(execution_id)
    result = _attempt_publish(execution_id=execution_id, triggered_by="operator_republish")
    return jsonify({"result": result, "ledger": _row_dict(execution_id)}), 200


@bp.post("/<int:execution_id>/discard")
def discard(execution_id: int):
    """ACCION HUMANA — marca la fila como failed (recuperable: re-publicar sigue disponible)."""
    row = _row_dict(execution_id)
    if row is None:
        return jsonify({"error": "no_ledger_row"}), 404
    if row["status"] == "posted":
        return jsonify({"error": "already_posted"}), 409
    from services.publish_ledger import mark_failed
    mark_failed(execution_id, "descartado por el operador")
    return jsonify({"ledger": _row_dict(execution_id)}), 200
