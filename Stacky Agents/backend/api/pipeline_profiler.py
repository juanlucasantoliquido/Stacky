"""api/pipeline_profiler.py — Blueprint del perfilador de pipelines. Plan 247 F4.

Blueprint registrado SIEMPRE en api/__init__.py sobre api_bp (url_prefix="/api").
url_prefix="/pipeline-profiler" -> ruta final /api/pipeline-profiler/...
NO poner url_prefix="/api/pipeline-profiler" (daria /api/api/...) y NO registrar en app.py.
Guard de la flag es PER-REQUEST (abort(404)) — nunca gateado en el registro del blueprint.
"""
from __future__ import annotations

import config as _config
from flask import Blueprint, abort, jsonify, request

from services.pipeline_profiler import narrate_purpose, profile_pipeline, profile_to_dict

bp = Blueprint("pipeline_profiler", __name__, url_prefix="/pipeline-profiler")


@bp.post("/profile")
def profile_route():
    # GOTCHA DURA: se lee la INSTANCIA `_config.config`, no el modulo. getattr del modulo
    # devuelve el default y mata el branch OFF (el test flag-off pasaria en falso).
    if not getattr(_config.config, "STACKY_PIPELINE_PROFILER_ENABLED", False):
        abort(404)
    body = request.get_json(silent=True) or {}
    yaml_text = body.get("yaml_text")
    source_path = str(body.get("source_path") or "")

    if yaml_text is None and body.get("pipeline_id"):
        # Import PEREZOSO: el plan 246 puede no exponer el resolutor. Importarlo a nivel
        # de modulo tumbaria el arranque de api/__init__.py con ImportError.
        try:
            from services.pipeline_inventory import get_pipeline_yaml  # plan 246
        except ImportError:
            return jsonify({
                "error": "inventory_unavailable",
                "detail": ("el registro de pipelines (plan 246) no esta instalado; "
                           "envia yaml_text"),
            }), 501
        yaml_text, source_path = get_pipeline_yaml(str(body["pipeline_id"]))

    if not isinstance(yaml_text, str) or not yaml_text.strip():
        return jsonify({"error": "yaml_text_requerido",
                        "detail": "envia yaml_text (string no vacio) o pipeline_id"}), 400

    try:
        profile = profile_pipeline(yaml_text,
                                   provider=str(body.get("provider") or "ado"),
                                   source_path=source_path)
    except ValueError as exc:
        return jsonify({"error": "provider_no_soportado", "detail": str(exc)}), 400

    if body.get("narrate") is True:
        from services.pm.pm_llm_client import call_llm  # import perezoso: 0 costo si no se narra
        texto, fuente = narrate_purpose(profile, llm_caller=call_llm)
    else:
        texto, fuente = narrate_purpose(profile, llm_caller=None)

    out = profile_to_dict(profile)
    out["purpose"], out["purpose_source"] = texto, fuente
    return jsonify(out), 200
