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
from services.pipeline_stack_detector import detect_stack  # Plan 97 F2
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
        "preflight_enabled": bool(getattr(cfg, "STACKY_DEVOPS_PREFLIGHT_ENABLED", False)),  # Plan 93
        "variables_enabled": bool(getattr(cfg, "STACKY_DEVOPS_VARIABLES_ENABLED", False)),  # Plan 94
        "stack_detect_enabled": bool(getattr(cfg, "STACKY_DEVOPS_STACK_DETECT_ENABLED", False)),  # Plan 97
        "doctor_enabled": bool(getattr(cfg, "STACKY_DEVOPS_DOCTOR_ENABLED", False)),  # Plan 96
        "production_enabled": bool(getattr(cfg, "STACKY_DEVOPS_PRODUCTION_ENABLED", False)),  # Plan 95
        # Plan 95 [C2]: capability, NO flag -- literal True porque este build
        # incluye F1 (commit ADO real). Deploys viejos no tienen la key ⇒ el
        # modal de commit (F4) la lee ausente ⇒ opción ADO sigue disabled.
        "ado_commit_supported": True,
    })


@bp.get("/detect-stack")
def detect_stack_route():
    """Detecta el stack técnico del proyecto activo por archivos de manifiesto.
    SOLO-LECTURA. Flag propia STACKY_DEVOPS_STACK_DETECT_ENABLED."""
    if not getattr(_config.config, "STACKY_DEVOPS_STACK_DETECT_ENABLED", False):
        abort(404)
    project = request.args.get("project")
    if not project:
        return jsonify({"error": "project es obligatorio"}), 400
    # Reusar la resolución de ruta YA existente del proyecto (mismo helper que
    # usa el resto de api/devops.py y api/projects.py para ir de nombre -> ruta
    # en disco; NO inventar una ruta nueva de resolución).
    from project_manager import get_project_config
    cfg = get_project_config(project)
    # La key REAL de la ruta del repo en el dict que devuelve get_project_config
    # es `workspace_root` (project_manager.py) — NO `local_path`/`path`: no
    # existen en ese dict y dejarían el detector siempre en None.
    root = (cfg or {}).get("workspace_root")
    detected = detect_stack(root) if root else None
    return jsonify({"detected": detected})


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


@bp.post("/preflight/check")
def preflight_check_route():
    """Semáforo pre-vuelo. SOLO-LECTURA (no commitea, no dispara, no escribe)."""
    if not getattr(_config.config, "STACKY_DEVOPS_PREFLIGHT_ENABLED", False):
        abort(404)
    body = request.get_json(silent=True) or {}
    project = body.get("project")
    spec_dict = body.get("spec")
    target = body.get("target") or "auto"      # [C11] "auto" | "ado" | "gitlab" | "both"
    if not project or not isinstance(spec_dict, dict) or target not in ("auto", "ado", "gitlab", "both"):
        return jsonify({"error": "project, spec (objeto) y target ('auto'|'ado'|'gitlab'|'both') son obligatorios"}), 400
    # [C11] "auto" = el tracker REAL del proyecto (menos ruido); fallback "both":
    if target == "auto":
        try:
            from services.project_context import resolve_project_context
            tt = resolve_project_context(project_name=project).tracker_type
            target = "gitlab" if tt == "gitlab" else "ado"
        except Exception:
            target = "both"
    checks = []
    # 1) estructural (reusa el validador del 87 — fuente de verdad)
    from services.pipeline_spec import dict_to_spec
    try:
        spec = dict_to_spec(spec_dict)
    except Exception as exc:  # [C5] spec malformado (p.ej. stages string) => 400, nunca 500
        return jsonify({"error": f"spec malformado: {exc}"}), 400
    errors = spec.validate()
    checks.append({"id": "estructura", "status": "fail" if errors else "ok",
                   "title": "Estructura del pipeline",
                   "detail": "; ".join(f"{e.field}: {e.message}" for e in errors) or "OK",
                   "fix_hint": "Resolvé los avisos del builder" if errors else ""})
    # 2) placeholders + 3) variables (F1, por target resuelto)
    from services.pipeline_preflight import (
        check_placeholders, check_undefined_variables, normalize_check, runners_check,
    )
    checks.append(check_placeholders(spec_dict))
    defined_keys = None
    # Integración ADITIVA plan 94 (si no está implementado/ON, queda None):
    if getattr(_config.config, "STACKY_DEVOPS_VARIABLES_ENABLED", False):
        try:
            from services.ci_variables import get_variables_provider
            defined_keys = [v["key"] for v in get_variables_provider(project).list_variables()]
        except Exception:
            defined_keys = None
    for t in (("ado", "gitlab") if target == "both" else (target,)):
        checks.append({**check_undefined_variables(spec_dict, t, defined_keys),
                       "id": f"variables_{t}"})
    # 4) lint remoto + 5) runners (F2, del tracker REAL del proyecto)
    if not errors:
        from services.pipeline_renderers import to_ado_yaml, to_gitlab_yaml
        from services.ci_preflight import get_preflight_provider
        try:
            provider = get_preflight_provider(project)
            yaml_str = to_ado_yaml(spec) if provider.name == "azure_devops" else to_gitlab_yaml(spec)
            lint = provider.lint_yaml(yaml_str)
            # [C6] normalize_check completa title/detail/fix_hint y aplana errors:
            checks.append(normalize_check(lint, "lint_tracker",
                                          f"YAML válido en {provider.name}"))
            runners = provider.list_runners()
            checks.append(runners_check(runners, spec_dict))  # [C4] puro, F1
        except Exception as exc:   # nunca 500 (§3.9)
            checks.append({"id": "tracker", "status": "unavailable",
                           "title": "Chequeos remotos", "detail": str(exc)[:500], "fix_hint": ""})
    summary = {s: sum(1 for c in checks if c["status"] == s)
               for s in ("ok", "warn", "fail", "unavailable")}
    return jsonify({"checks": checks, "summary": summary})


@bp.post("/doctor/diagnose")
def doctor_diagnose_route():
    """Jobs fallidos + clasificación en llano. SOLO-LECTURA; el log NO se persiste. Plan 96."""
    if not getattr(_config.config, "STACKY_DEVOPS_DOCTOR_ENABLED", False):
        abort(404)
    body = request.get_json(silent=True) or {}
    project, pipeline_id = body.get("project"), body.get("pipeline_id")
    if not project or not pipeline_id:
        return jsonify({"error": "project y pipeline_id son obligatorios"}), 400
    from services.ci_logs_provider import get_ci_logs_provider
    from services.failure_doctor import classify_failure
    from services.tracker_provider import TrackerApiError, TrackerConfigError
    try:
        provider = get_ci_logs_provider(project)
        failed = provider.list_failed_jobs(str(pipeline_id))
    except TrackerConfigError as e:            # fábrica: tracker/flag sin soporte
        return jsonify({"error": str(e), "kind": "tracker_config"}), 400
    except TrackerApiError as e:
        return jsonify({"error": str(e), "kind": getattr(e, "kind", "")}), e.status
    except Exception as e:
        return jsonify({"error": str(e), "kind": "logs_unavailable"}), 502
    jobs = []
    for j in failed[:10]:                      # cap defensivo de jobs por request
        try:
            log = provider.get_job_log(j["job_id"])
            diagnosis = classify_failure(log)
        except Exception as e:                 # log inaccesible ⇒ honesto, sigue
            diagnosis = {"matches": [], "snippet": f"(no pude bajar el log: {e})"}
        jobs.append({**j, "diagnosis": diagnosis})
    return jsonify({"provider": provider.name, "jobs": jobs,
                    "no_failures_found": len(failed) == 0,
                    "failed_jobs_total": len(failed)})   # honestidad del cap
