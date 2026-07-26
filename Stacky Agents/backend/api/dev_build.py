"""Plan 210 F3 — Endpoint disparador de la verificación de build del Developer.

El agente lo llama durante su PASO 4: es la forma de producir el HECHO de máquina
dentro del run que el operador ya autorizó. Siempre responde 200 con el veredicto
(aunque sea bloqueante), para que el cliente pueda renderizarlo; solo 404 si la
flag está apagada.
"""
from __future__ import annotations

import logging
from dataclasses import asdict

from flask import Blueprint, jsonify

import config as _config
from services import dev_build_verify

logger = logging.getLogger(__name__)

bp = Blueprint("dev_build", __name__)


@bp.post("/tickets/by-ado/<int:ado_id>/dev/build-verify")
def build_verify_route(ado_id: int):
    if not bool(getattr(_config.config, "STACKY_DEV_BUILD_VERIFY_ENABLED", False)):
        return jsonify({"error": "dev_build_verify deshabilitado"}), 404

    project_name = dev_build_verify.project_name_for_ado(ado_id)
    workspace_root = dev_build_verify.workspace_root_for_ado(ado_id)
    execution_id = dev_build_verify.latest_execution_id_for_ado(ado_id)

    verdict = dev_build_verify.verify_build(
        ado_id=ado_id, project_name=project_name,
        workspace_root=workspace_root, execution_id=execution_id,
    )
    logger.info("dev_build_verify: ADO-%s gate_ok=%s reason=%s",
                ado_id, verdict.gate_ok, verdict.reason)
    return jsonify({"verdict": asdict(verdict)}), 200
