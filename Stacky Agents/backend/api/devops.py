"""api/devops.py — Blueprint del panel DevOps (Plan 87).

url_prefix="/devops" → rutas finales /api/devops/... (NO poner /api/ en el prefix,
ver FIX C2 del plan 73 en api/pipeline_generator.py:7-8).
"""
import sys
from dataclasses import asdict
from flask import Blueprint, jsonify, request, abort
import config as _config
from api._helpers import current_user
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
    validate_sandbox_override,  # Plan 107
)

bp = Blueprint("devops", __name__, url_prefix="/devops")


def _health_payload() -> dict:
    """Payload compartido por /health y /bootstrap (Plan 98). SIEMPRE calculable.

    [DESVÍO del plan 98 F3, verificado contra código real]: el doc mostraba un
    subset de keys (snapshot de cuando se escribió, 2026-07-06); el /health real
    ya incluía además doctor_enabled/production_enabled/ado_commit_supported/
    section_doctor_enabled (planes 95/96/104, mergeados después). Se extraen
    TODAS las keys actuales para no regresionar /health ni romper
    test_bootstrap_health_matches_health_endpoint (paridad exacta)."""
    cfg = _config.config
    return {
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
        "section_doctor_enabled": bool(getattr(cfg, "STACKY_DEVOPS_SECTION_DOCTOR_ENABLED", False)),  # Plan 104
        "bootstrap_enabled": bool(getattr(cfg, "STACKY_DEVOPS_BOOTSTRAP_ENABLED", False)),  # Plan 98
        "remote_console_enabled": bool(getattr(cfg, "STACKY_DEVOPS_REMOTE_CONSOLE_ENABLED", False)),  # Plan 105
        "remote_target_enabled": bool(getattr(cfg, "STACKY_DEVOPS_REMOTE_TARGET_ENABLED", False)),  # Plan 108
        "env_tree_preview_enabled": bool(getattr(cfg, "STACKY_DEVOPS_ENV_TREE_PREVIEW_ENABLED", False)),  # Plan 107
        "env_sandbox_enabled": bool(getattr(cfg, "STACKY_DEVOPS_ENV_SANDBOX_ENABLED", False)),  # Plan 107
        "pr_reviewer_enabled": bool(getattr(cfg, "STACKY_PR_REVIEWER_ENABLED", False)),  # Plan 110
        "connection_doctor_enabled": bool(getattr(cfg, "STACKY_DEVOPS_CONNECTION_DOCTOR_ENABLED", False)),  # Plan 116
        "ui_v2_enabled": bool(getattr(cfg, "STACKY_DEVOPS_UI_V2_ENABLED", False)),  # Plan 119
        "deployments_enabled": bool(getattr(cfg, "STACKY_DEPLOYMENTS_ENABLED", False)),  # Plan 120
        "deployments_execute_enabled": bool(getattr(cfg, "STACKY_DEPLOYMENTS_EXECUTE_ENABLED", False)),  # Plan 120
        "deployments_ai_enabled": bool(getattr(cfg, "STACKY_DEPLOYMENTS_AI_DIAGNOSIS_ENABLED", False)),  # Plan 120
        "local_doctor_enabled": bool(
            getattr(cfg, "STACKY_DEVOPS_LOCAL_DOCTOR_ENABLED", False)
            and getattr(cfg, "LOCAL_LLM_ENABLED", False)
        ),  # Plan 127 — CONJUNCIÓN: la UI solo ofrece el botón si el camino completo sirve
    }


@bp.get("/health")
def devops_health_route():
    """SIEMPRE 200 (la UI lo usa para decidir si muestra la tab, patrón /api/migrator/health)."""
    return jsonify(_health_payload())


@bp.get("/bootstrap")
def devops_bootstrap_route():
    """Hidratacion del panel DevOps en UN round-trip. SOLO-LECTURA. Plan 98."""
    if not getattr(_config.config, "STACKY_DEVOPS_BOOTSTRAP_ENABLED", False):
        abort(404)
    project = request.args.get("project")
    if not project:
        return jsonify({"error": "project es obligatorio"}), 400
    health = _health_payload()
    profile = load_client_profile(project) or {}

    def _lst(k):
        v = profile.get(k)
        return v if isinstance(v, list) else []

    def _dct(k):
        v = profile.get(k)
        return v if isinstance(v, dict) else None

    payload = {
        "health": health,
        "has_profile": bool(profile),
        "profile_keys": {
            "devops_pipeline_drafts": _lst("devops_pipeline_drafts"),
            "devops_publication_presets": _lst("devops_publication_presets"),
            "devops_publication_settings": _dct("devops_publication_settings") or {},
            # None (no {}) si ausente: EnvironmentsSection distingue "sin configurar"
            # (hasSavedSettings=false) de "configurado vacio" — EnvironmentsSection.tsx:88-95.
            "devops_environment_settings": _dct("devops_environment_settings"),
            "process_catalog": _lst("process_catalog"),
        },
        "servers": None,
    }
    if health["servers_enabled"]:
        payload["servers"] = {
            "servers": server_registry.list_servers(),
            "keyring_available": server_registry.keyring_available(),
        }
    return jsonify(payload)


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


@bp.post("/pipeline-lint/validate")
def pipeline_lint_validate_route():
    """YAML → LintReport. PURO (el servicio no toca red); known_variables viene de la UI. Plan 186."""
    if not getattr(_config.config, "STACKY_DEVOPS_PIPELINE_LINT_ENABLED", False):
        abort(404)  # guard per-request, patrón devops.py:147
    body = request.get_json(silent=True) or {}
    source = body.get("source")
    yaml_str = body.get("yaml") or ""
    if source not in ("ado", "gitlab") or not yaml_str.strip():
        return jsonify({"error": "source ('ado'|'gitlab') y yaml son obligatorios"}), 400
    kv = body.get("known_variables")
    kv = [str(x) for x in kv] if isinstance(kv, list) else None
    from services.pipeline_lint import lint_yaml
    return jsonify(lint_yaml(yaml_str, source, known_variables=kv).to_dict())


@bp.post("/pipeline-lint/explain")
def pipeline_lint_explain_route():
    """YAML → ExecutionPlan (explain-plan estilo terraform-plan). PURO, sin red. Plan 186."""
    if not getattr(_config.config, "STACKY_DEVOPS_PIPELINE_LINT_ENABLED", False):
        abort(404)  # guard per-request, patrón devops.py:147
    body = request.get_json(silent=True) or {}
    source = body.get("source")
    yaml_str = body.get("yaml") or ""
    if source not in ("ado", "gitlab") or not yaml_str.strip():
        return jsonify({"error": "source ('ado'|'gitlab') y yaml son obligatorios"}), 400
    from services.pipeline_lint import explain_plan
    return jsonify({"plan": explain_plan(yaml_str, source).to_dict()})


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


def _map_remote_error_status(error_key: str | None) -> int:
    """Plan 108 F5 — mapa de errores del riel remoto (copiado de
    api/devops_remote_console.py:95-108, mismos códigos que /console/exec)."""
    if error_key == "command_not_read_only":
        return 403
    if error_key == "server_not_found":
        return 404
    if error_key in ("keyring_unavailable", "no_password"):
        return 503
    if error_key == "remote_exec_windows_only":
        return 501
    if error_key == "timeout":
        return 504
    return 502


def _load_env_context(body):
    """Helper compartido plan/apply. Retorna ((root, rel_paths, sandbox_active,
    server_alias), None) o (None, respuesta_error). Plan 107: root_override
    opcional, validado server-side contra el guard de solapamiento
    (validate_sandbox_override) cuando la flag STACKY_DEVOPS_ENV_SANDBOX_ENABLED
    está ON; sin override el comportamiento es idéntico a Plan 89 (root =
    production_root, sandbox_active=False). Plan 108 F5: server_alias leído SIN
    validar acá (el caller valida vía _validate_remote_target); ausente ⇒ None
    ⇒ camino local byte-idéntico."""
    project = body.get("project")
    if not project:
        return None, (jsonify({"error": "project es obligatorio"}), 400)
    profile = load_client_profile(project) or {}
    settings = profile.get("devops_environment_settings")
    settings = settings if isinstance(settings, dict) else {}   # defensivo (clase C5 del 88)
    production_root = settings.get("environment_root") or ""

    # Plan 107 — resolución de raíz efectiva (sandbox opt-in, server-side).
    root = production_root
    sandbox_active = False
    override = body.get("root_override")
    if override is not None and str(override).strip():
        if not getattr(_config.config, "STACKY_DEVOPS_ENV_SANDBOX_ENABLED", False):
            return None, (jsonify({"error": "el modo sandbox está deshabilitado",
                                   "kind": "sandbox_disabled"}), 400)
        serr = validate_sandbox_override(str(override), production_root)
        if serr:
            return None, (jsonify({"error": f"raíz sandbox inválida: {serr}",
                                   "kind": "sandbox_invalid", "reason": serr}), 400)
        root = str(override)
        sandbox_active = True

    err = validate_root(root or "")
    if err:
        return None, (jsonify({"error": f"environment_root invalido o no configurado: {err}",
                               "kind": "environment_root_invalid"}), 400)
    catalog = profile.get("process_catalog")
    rel_paths = build_environment_layout(catalog if isinstance(catalog, list) else [], settings)
    # Plan 108 F5 — server_alias opcional (ausente ⇒ camino local, byte-compat).
    server_alias = (body.get("server_alias") or "").strip() or None
    return (root, rel_paths, sandbox_active, server_alias), None


@bp.post("/environments/plan")
def environment_plan_route():
    """Dry-run SOLO-LECTURA del árbol de carpetas. Plan 108 F5: con server_alias
    evalúa el árbol EN el servidor remoto (mismo shape, + remote/server_alias)."""
    if not getattr(_config.config, "STACKY_DEVOPS_ENVIRONMENTS_ENABLED", False):
        abort(404)
    ctx, err = _load_env_context(request.get_json(silent=True) or {})
    if err: return err
    root, rel_paths, sandbox_active, server_alias = ctx
    if server_alias:
        from api.devops_agent import _validate_remote_target
        target_err = _validate_remote_target(server_alias)
        if target_err:
            return target_err
        from services.environment_remote import plan_environment_remote
        result = plan_environment_remote(server_alias, root, rel_paths, user=current_user())
        if result.get("ok") is False:
            return jsonify(result), _map_remote_error_status(result.get("error"))
    else:
        result = plan_environment(root, rel_paths)
    result["sandbox_active"] = sandbox_active  # Plan 107 — la UI muestra el badge
    return jsonify(result)


@bp.post("/environments/apply")
def environment_apply_route():
    """Crea SOLO to_create. HITL: confirm=True + fingerprint del plan visto (ADICIÓN).
    Plan 108 F5: con server_alias crea EN el servidor remoto (mismo HITL)."""
    if not getattr(_config.config, "STACKY_DEVOPS_ENVIRONMENTS_ENABLED", False):
        abort(404)
    body = request.get_json(silent=True) or {}
    if body.get("confirm") is not True:
        return jsonify({"error": "confirm=True requerido (HITL)"}), 400
    # Plan 107 — ack extra cuando se opera en sandbox.
    if body.get("root_override") is not None and str(body.get("root_override")).strip():
        if body.get("sandbox_ack") is not True:
            return jsonify({"error": "sandbox_ack=True requerido para crear en la raíz sandbox",
                            "kind": "sandbox_ack_required"}), 400
    fingerprint = body.get("fingerprint")
    if not isinstance(fingerprint, str) or not fingerprint:
        return jsonify({"error": "fingerprint del plan es obligatorio (respuesta de /plan)"}), 400
    ctx, err = _load_env_context(body)
    if err: return err
    root, rel_paths, sandbox_active, server_alias = ctx
    if fingerprint != layout_fingerprint(root, rel_paths):
        return jsonify({"error": "el layout cambio desde el ultimo plan; recalcular el plan",
                        "kind": "plan_stale"}), 409
    requested = body.get("paths")
    if not isinstance(requested, list) or not requested:
        return jsonify({"error": "paths (lista no vacia) es obligatorio"}), 400
    # server-side: solo la intersección con el layout derivado del catálogo REAL
    approved = [p for p in rel_paths if p in set(requested)]
    if server_alias:
        from api.devops_agent import _validate_remote_target
        target_err = _validate_remote_target(server_alias)
        if target_err:
            return target_err
        from services.environment_remote import resolve_remote_layout, apply_environment_remote
        safe_pairs, _unsafe_pairs = resolve_remote_layout(root, approved)
        result = apply_environment_remote(server_alias, root, safe_pairs, user=current_user())
        if result.get("ok") is False:
            return jsonify(result), _map_remote_error_status(result.get("error"))
    else:
        result = apply_environment(root, approved)
    result["ignored_not_in_layout"] = sorted(set(requested) - set(rel_paths))  # C8: visible
    result["sandbox_active"] = sandbox_active  # Plan 107
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


@bp.post("/doctor/explain-failure")
def doctor_explain_failure_route():
    """Plan 127 C2 — explica UN job fallido con el modelo LOCAL. El log NO se persiste."""
    if not getattr(_config.config, "STACKY_DEVOPS_DOCTOR_ENABLED", False):
        abort(404)
    if not getattr(_config.config, "STACKY_DEVOPS_LOCAL_DOCTOR_ENABLED", False):
        abort(404)

    from api.local_llm_analysis import _guard

    guard = _guard()
    if guard:
        return guard

    body = request.get_json(silent=True) or {}
    project = body.get("project")
    pipeline_id = body.get("pipeline_id")
    job_id = body.get("job_id")
    if not project or not pipeline_id or not job_id:
        return jsonify({"error": "project, pipeline_id y job_id son obligatorios"}), 400

    from services.ci_logs_provider import get_ci_logs_provider
    from services.tracker_provider import TrackerApiError, TrackerConfigError

    try:
        provider = get_ci_logs_provider(project)
        log = provider.get_job_log(str(job_id))
    except TrackerConfigError as e:            # fábrica: tracker/flag sin soporte
        return jsonify({"error": str(e), "kind": "tracker_config"}), 400
    except TrackerApiError as e:
        return jsonify({"error": str(e), "kind": getattr(e, "kind", "")}), e.status
    except Exception as e:
        return jsonify({"error": str(e), "kind": "logs_unavailable"}), 502

    from services.failure_doctor import classify_failure

    diagnosis = classify_failure(log)

    from services.local_insights import HITL_RULES, truncate_middle
    from services.pr_review_sanitize import redact_secrets
    import json as _json

    system = "Sos un ingeniero DevOps senior experto en debugging de CI." + HITL_RULES
    user = redact_secrets(
        "== CLASIFICACIÓN DETERMINISTA ==\n" + _json.dumps(diagnosis, ensure_ascii=False)
        + "\n\n== LOG (recortado) ==\n" + truncate_middle(log, 4000, 4000)
        + "\n\nExplicá en markdown: ## Qué falló / ## Causa raíz más probable / ## Fix sugerido"
    )

    from api.local_llm_analysis import _create_execution, _ensure_internal_ticket, _finish_execution
    from db import session_scope

    with session_scope() as session:
        ticket = _ensure_internal_ticket(session, project)
        analyzer_id = _create_execution(
            session, ticket.id, "local_llm_ci_explainer",
            {"project": project, "pipeline_id": pipeline_id, "job_id": job_id, "log_chars": len(log)},
        )

    from copilot_bridge import invoke_local_llm  # import lazy (patrón del repo)

    try:
        response = invoke_local_llm(
            agent_type="local_llm_ci_explainer",
            system=system,
            user=user,
            on_log=lambda level, msg: None,
            execution_id=analyzer_id,
            model=body.get("model"),
        )
    except Exception as e:
        _finish_execution(analyzer_id, status="error", error=str(e))
        return jsonify({"ok": False, "error": str(e), "execution_id": analyzer_id}), 502

    resolved_model = (
        (response.metadata or {}).get("model") or body.get("model")
        or _config.config.LOCAL_LLM_MODEL
    )
    _finish_execution(analyzer_id, status="completed", output=response.text[:10000])
    return jsonify({
        "ok": True,
        "analysis": response.text,
        "model": resolved_model,
        "job_id": job_id,
        "execution_id": analyzer_id,
    })
