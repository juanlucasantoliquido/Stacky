"""api/parity.py -- Plan 218 F8. Endpoint de SOLO LECTURA de la matriz de paridad.

R6: el blueprint declara `url_prefix="/parity"` y se registra dentro de `api_bp`
(que ya aporta `/api`) ⇒ la ruta final es `/api/parity/matrix`. Declarar `/api`
acá produciría `/api/api/parity/...`, el defecto que hizo rechazar a los planes
72, 73 y 74.
"""
from __future__ import annotations

from flask import Blueprint, abort, jsonify, request

parity_bp = Blueprint("parity", __name__, url_prefix="/parity")


@parity_bp.get("/matrix")
def get_parity_matrix():
    """Qué puede y qué no puede hacer el tracker del proyecto activo.

    Solo lectura y sin I/O de red: es el registro en proceso. Cierra el lazo
    human-in-the-loop — la degradación deja de ser un error a mitad de un flujo y
    pasa a ser información disponible ANTES de empezar.

    Con STACKY_PROVIDER_PARITY_ENABLED=false devuelve 404: la superficie del 218
    desaparece por completo (rollback en un click, sin reiniciar el backend).
    """
    import config as _config

    from services.parity_rollout import parity_report

    if not bool(getattr(_config.config, "STACKY_PROVIDER_PARITY_ENABLED", True)):
        abort(404)

    project = (request.args.get("project") or "").strip() or None
    return jsonify(parity_report(project))
