"""api/devops.py — Blueprint del panel DevOps (Plan 87).

url_prefix="/devops" → rutas finales /api/devops/... (NO poner /api/ en el prefix,
ver FIX C2 del plan 73 en api/pipeline_generator.py:7-8).
"""
import sys
from dataclasses import asdict
from flask import Blueprint, jsonify, request, abort
import config as _config
from services import server_registry  # Plan 91 — rdp_available en health
from services.pipeline_renderers import parse_ado_yaml, parse_gitlab_yaml
from services.publication_spec import build_publication_spec
from services.client_profile import load_client_profile  # services/client_profile.py:266
from services.environment_init import (
    build_environment_layout,
    plan_environment,
    apply_environment,
    validate_root,
    layout_fingerprint,
)

bp = Blueprint("devops", __name__, url_prefix="/devops")


@bp.get("/health")
def devops_health_route():
    """SIEMPRE 200 (la UI lo usa para decidir si muestra la tab, patrón /api/migrator/health)."""
    cfg = _config.config
    return jsonify({
        "flag_enabled": bool(getattr(cfg, "STACKY_DEVOPS_PANEL_ENABLED", False)),
        "generator_enabled": bool(getattr(cfg, "STACKY_PIPELINE_GENERATOR_ENABLED", False)),
        "trigger_enabled": bool(getattr(cfg, "STACKY_PIPELINE_TRIGGER_ENABLED", False)),
        "publications_enabled": bool(getattr(cfg, "STACKY_DEVOPS_PUBLICATIONS_ENABLED", False)),
        "environments_enabled": bool(getattr(cfg, "STACKY_DEVOPS_ENVIRONMENTS_ENABLED", False)),
        "agent_enabled": bool(getattr(cfg, "STACKY_DEVOPS_AGENT_ENABLED", False)),  # Plan 90
        "servers_enabled": bool(getattr(cfg, "STACKY_DEVOPS_SERVERS_ENABLED", False)),  # Plan 91
        "rdp_available": (sys.platform == "win32") and server_registry.keyring_available(),  # Plan 91
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


@bp.post("/publications/materialize")
def materialize_publication_route():
    """Preset -> dict PipelineSpec. SOLO-LECTURA (no commitea, no dispara). Plan 88."""
    if not getattr(_config.config, "STACKY_DEVOPS_PUBLICATIONS_ENABLED", False):
        abort(404)  # guard per-request (patrón pipeline_generator.py:37)
    body = request.get_json(silent=True) or {}
    project = body.get("project")
    preset_name = body.get("preset_name")
    if not project or not preset_name:
        return jsonify({"error": "project y preset_name son obligatorios"}), 400
    profile = load_client_profile(project) or {}
    # C5 — defensivo: el profile puede haberse editado por JSON directo.
    presets_raw = profile.get("devops_publication_presets")
    presets = [p for p in presets_raw if isinstance(p, dict)] if isinstance(presets_raw, list) else []
    preset = next((p for p in presets if p.get("name") == preset_name), None)
    if preset is None:
        return jsonify({"error": f"preset '{preset_name}' no existe", "kind": "preset_not_found"}), 404
    catalog = profile.get("process_catalog")
    settings = profile.get("devops_publication_settings")
    result = build_publication_spec(
        preset,
        catalog if isinstance(catalog, list) else [],
        settings if isinstance(settings, dict) else None,
    )
    return jsonify(result)   # {'spec':..., 'resolved':[...], 'unknown_processes':[...]}


def _load_env_context(body):
    """Helper compartido plan/apply. Retorna ((root, rel_paths), None) o (None, respuesta_error)."""
    project = body.get("project")
    if not project:
        return None, (jsonify({"error": "project es obligatorio"}), 400)
    profile = load_client_profile(project) or {}
    settings = profile.get("devops_environment_settings")
    settings = settings if isinstance(settings, dict) else {}   # defensivo (clase C5 del 88)
    root = settings.get("environment_root")
    err = validate_root(root or "")
    if err:
        return None, (jsonify({"error": f"environment_root invalido o no configurado: {err}",
                               "kind": "environment_root_invalid"}), 400)
    catalog = profile.get("process_catalog")
    rel_paths = build_environment_layout(catalog if isinstance(catalog, list) else [], settings)
    return (root, rel_paths), None


@bp.post("/environments/plan")
def environment_plan_route():
    """Dry-run SOLO-LECTURA del árbol de carpetas."""
    if not getattr(_config.config, "STACKY_DEVOPS_ENVIRONMENTS_ENABLED", False):
        abort(404)
    ctx, err = _load_env_context(request.get_json(silent=True) or {})
    if err: return err
    root, rel_paths = ctx
    return jsonify(plan_environment(root, rel_paths))


@bp.post("/environments/apply")
def environment_apply_route():
    """Crea SOLO to_create. HITL: confirm=True + fingerprint del plan visto (ADICIÓN)."""
    if not getattr(_config.config, "STACKY_DEVOPS_ENVIRONMENTS_ENABLED", False):
        abort(404)
    body = request.get_json(silent=True) or {}
    if body.get("confirm") is not True:
        return jsonify({"error": "confirm=True requerido (HITL)"}), 400
    fingerprint = body.get("fingerprint")
    if not isinstance(fingerprint, str) or not fingerprint:
        return jsonify({"error": "fingerprint del plan es obligatorio (respuesta de /plan)"}), 400
    ctx, err = _load_env_context(body)
    if err: return err
    root, rel_paths = ctx
    if fingerprint != layout_fingerprint(root, rel_paths):
        return jsonify({"error": "el layout cambio desde el ultimo plan; recalcular el plan",
                        "kind": "plan_stale"}), 409
    requested = body.get("paths")
    if not isinstance(requested, list) or not requested:
        return jsonify({"error": "paths (lista no vacia) es obligatorio"}), 400
    # server-side: solo la intersección con el layout derivado del catálogo REAL
    approved = [p for p in rel_paths if p in set(requested)]
    result = apply_environment(root, approved)
    result["ignored_not_in_layout"] = sorted(set(requested) - set(rel_paths))  # C8: visible
    return jsonify(result)
