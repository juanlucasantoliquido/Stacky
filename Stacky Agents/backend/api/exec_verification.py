"""E2.1 — Reporte de verificación ejecutable adjunto al verdict.

Bloque read-only en la vista de revisión de la ejecución.
Serializa metadata["exec_verification"] con degradación con gracia.

API pública:
    serialize_exec_verification_block(metadata) -> dict | None
    bp: Blueprint con GET /executions/<id>/exec-verification
"""
from __future__ import annotations

import logging
from typing import Any

from flask import Blueprint, jsonify, abort

from db import session_scope
from models import AgentExecution

bp = Blueprint("exec_verification", __name__, url_prefix="/executions")
logger = logging.getLogger("stacky.api.exec_verification")


def serialize_exec_verification_block(metadata: dict | None) -> dict | None:
    """Extrae y serializa el bloque exec_verification del metadata.

    Returns:
        Dict con el bloque exec_verification, o None si no existe/no habilitado.
        Degrada con gracia: si el bloque parcialmente formado, retorna lo que hay.
    """
    if not metadata:
        return None

    try:
        from config import config as _cfg
        enabled = getattr(_cfg, "STACKY_EXEC_VERIFICATION_VERDICT_CARD_ENABLED", False)
    except Exception:
        enabled = False

    if not enabled:
        return None

    ev = metadata.get("exec_verification")
    if not ev or not isinstance(ev, dict):
        return None

    # Construir resumen legible
    hard_failed = ev.get("hard_failed", [])
    soft = ev.get("soft", [])
    ran = ev.get("ran", [])
    passed = ev.get("passed")
    fake_green = ev.get("fake_green", [])
    duration_ms = ev.get("duration_ms", 0)
    repair = ev.get("repair")

    # Resumen textual
    if passed is True:
        summary_parts = [f"✓ {v}" for v in ran if v not in [r.get("name") for r in soft]]
        if soft:
            summary_parts += [f"~ {r.get('name', '?')} (soft-warn)" for r in soft]
        summary = " · ".join(summary_parts) if summary_parts else "✓ verificado"
    elif passed is False:
        failed_names = [r.get("name", "?") for r in hard_failed]
        summary = f"✗ {', '.join(failed_names)} en rojo"
    else:
        summary = "— no verificado"

    # Excerpts de fallos (acotados)
    failure_excerpts = [
        {"verifier": r.get("name", "?"), "detail": (r.get("detail") or "")[:300]}
        for r in hard_failed[:5]
    ]

    block: dict[str, Any] = {
        "summary": summary,
        "passed": passed,
        "mode": ev.get("mode", "annotate"),
        "ran": ran,
        "hard_failed_count": len(hard_failed),
        "soft_count": len(soft),
        "failure_excerpts": failure_excerpts,
        "duration_ms": duration_ms,
        "skipped_reason": ev.get("skipped_reason"),
        "fake_green": fake_green,
    }

    if repair:
        block["repair"] = {
            "attempted": repair.get("attempted", False),
            "recovered": repair.get("recovered", False),
            "failed_before": repair.get("failed_before", []),
        }

    return block


@bp.get("/<int:execution_id>/exec-verification")
def get_exec_verification(execution_id: int):
    """GET /executions/<id>/exec-verification — bloque read-only de verificación ejecutable."""
    try:
        from config import config as _cfg
        enabled = getattr(_cfg, "STACKY_EXEC_VERIFICATION_VERDICT_CARD_ENABLED", False)
    except Exception:
        enabled = False

    if not enabled:
        return jsonify({"enabled": False, "block": None}), 200

    with session_scope() as session:
        execution = session.get(AgentExecution, execution_id)
        if execution is None:
            abort(404)

        metadata = execution.exec_metadata or {}
        block = serialize_exec_verification_block(metadata)

        return jsonify({
            "enabled": True,
            "execution_id": execution_id,
            "block": block,
        })
