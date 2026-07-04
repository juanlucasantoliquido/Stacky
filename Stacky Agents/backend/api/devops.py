"""api/devops.py — Blueprint del panel DevOps (Plan 87).

url_prefix="/devops" → rutas finales /api/devops/... (NO poner /api/ en el prefix,
ver FIX C2 del plan 73 en api/pipeline_generator.py:7-8).
"""
from dataclasses import asdict
from flask import Blueprint, jsonify, request, abort
import config as _config
from services.pipeline_renderers import parse_ado_yaml, parse_gitlab_yaml

bp = Blueprint("devops", __name__, url_prefix="/devops")


@bp.get("/health")
def devops_health_route():
    """SIEMPRE 200 (la UI lo usa para decidir si muestra la tab, patrón /api/migrator/health)."""
    cfg = _config.config
    return jsonify({
        "flag_enabled": bool(getattr(cfg, "STACKY_DEVOPS_PANEL_ENABLED", False)),
        "generator_enabled": bool(getattr(cfg, "STACKY_PIPELINE_GENERATOR_ENABLED", False)),
        "trigger_enabled": bool(getattr(cfg, "STACKY_PIPELINE_TRIGGER_ENABLED", False)),
    })


@bp.post("/parse-yaml")
def parse_yaml_route():
    """YAML (ado|gitlab) → dict PipelineSpec para hidratar el editor. PURO, sin I/O."""
    if not getattr(_config.config, "STACKY_DEVOPS_PANEL_ENABLED", False):
        abort(404)  # guard per-request, mismo patrón que pipeline_generator.py:37
    body = request.get_json(silent=True) or {}
    source = body.get("source")           # "ado" | "gitlab"
    yaml_str = body.get("yaml") or ""
    if source not in ("ado", "gitlab") or not yaml_str.strip():
        return jsonify({"error": "source ('ado'|'gitlab') y yaml son obligatorios"}), 400
    try:
        spec = parse_ado_yaml(yaml_str) if source == "ado" else parse_gitlab_yaml(yaml_str)
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"spec": asdict(spec)})
