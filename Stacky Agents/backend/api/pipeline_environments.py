"""api/pipeline_environments.py — Blueprint de la matriz de entornos. Plan 251 F4.

url_prefix="/pipeline-environments" -> ruta final /api/pipeline-environments/...
Guard PER-REQUEST (abort(404)), nunca gateado en el registro del blueprint.

SOLO LECTURA: no escribe en el repo, ni en el proveedor, ni en el disco del operador.
POST es por TRANSPORTE (el YAML viaja en el body, mismo patron que
POST /api/devops/parse-yaml del plan 87), no por semantica.
"""
from __future__ import annotations

import config as _config
from flask import Blueprint, abort, jsonify, request

from services.pipeline_env_resolver import resolve
from services.pipeline_environments import (
    PROVIDERS,
    build_matrix,
    derive_environments,
    extract_requirements,
    to_json_payload,
)
from services.secret_masking import strip_secret_keys

bp = Blueprint("pipeline_environments", __name__, url_prefix="/pipeline-environments")

MAX_YAML_CHARS = 500_000


def _guard():
    # GOTCHA dura: la INSTANCIA (_config.config), no el modulo: getattr del modulo
    # devuelve el default y mata el branch OFF (el test flag-off pasaria en falso).
    if not getattr(_config.config, "STACKY_PIPELINE_ENV_MATRIX_ENABLED", False):
        abort(404)
    if request.method == "POST" and not request.is_json:
        abort(400, description="Content-Type application/json requerido")


@bp.route("/analyze", methods=["POST"])
def analyze():
    """body: {yaml_text, provider, project?, resolve?} -> matriz entorno x valor."""
    _guard()
    body = request.get_json(silent=True) or {}

    provider = str(body.get("provider") or "")
    if provider not in PROVIDERS:
        return jsonify({"error": "provider_no_soportado",
                        "detail": "provider debe ser uno de: %s" % ", ".join(PROVIDERS)}), 400

    yaml_text = body.get("yaml_text")
    if not isinstance(yaml_text, str) or not yaml_text.strip():
        return jsonify({"error": "yaml_text_requerido"}), 400
    if len(yaml_text) > MAX_YAML_CHARS:
        return jsonify({"error": "yaml_demasiado_grande",
                        "detail": "YAML demasiado grande (máx 500 KB)"}), 400

    usar_proveedor = body.get("resolve")
    usar_proveedor = True if not isinstance(usar_proveedor, bool) else usar_proveedor
    project = body.get("project")

    requisitos = extract_requirements(yaml_text, provider)
    resoluciones: dict = {}
    degradaciones: tuple = ()
    entornos = derive_environments(yaml_text, provider)

    if usar_proveedor:
        # los scopes del proveedor tambien son evidencia de entornos (§F2 fuente 4)
        from services.pipeline_env_resolver import (  # noqa: PLC0415
            list_scoped_variables,
        )
        _vars, scopes, deg_scopes = list_scoped_variables(project)
        if scopes:
            entornos = derive_environments(yaml_text, provider, tuple(scopes))
        resoluciones, deg_resolve = resolve(
            requisitos, entornos, provider, project=project, use_provider=True,
            yaml_text=yaml_text)
        degradaciones = tuple(deg_scopes) + tuple(
            d for d in deg_resolve if d not in deg_scopes)
    else:
        resoluciones, degradaciones = resolve(
            requisitos, entornos, provider, project=project, use_provider=False,
            yaml_text=yaml_text)

    matriz = build_matrix(requisitos, entornos, resoluciones, provider,
                          degraded=degradaciones)
    # red C (estructural): claves de diccionario que suenen a secreto. NO sustituye a
    # las redes de VALOR del modulo puro; es la ultima linea, no la primera.
    payload = strip_secret_keys(to_json_payload(matriz, provider))
    return jsonify(payload), 200
