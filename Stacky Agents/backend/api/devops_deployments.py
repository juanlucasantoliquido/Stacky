"""api/devops_deployments.py — Plan 120 F5. API del Centro de Despliegues.

url_prefix="/devops/deployments" → rutas finales /api/devops/deployments/...
(convención de la casa, ver api/devops.py:3-4). Guard por flag con
abort(404) (patrón api/devops.py:76-77). HITL innegociable: /execute y
/rollback exigen confirm:true SIEMPRE; destinos `protected` exigen además
confirm_text == app_id.
"""
from __future__ import annotations

from datetime import datetime, timezone

from flask import Blueprint, jsonify, request, abort

import config as _config
from api._helpers import current_user
from services import deploy_planner as planner
from services import deploy_store as store
from services import deploy_executor as executor
from services import server_registry

bp = Blueprint("devops_deployments", __name__, url_prefix="/devops/deployments")


def _master_on() -> bool:
    return bool(getattr(_config.config, "STACKY_DEPLOYMENTS_ENABLED", False))


def _execute_on() -> bool:
    return bool(getattr(_config.config, "STACKY_DEPLOYMENTS_EXECUTE_ENABLED", False))


def _ai_on() -> bool:
    return bool(getattr(_config.config, "STACKY_DEPLOYMENTS_AI_DIAGNOSIS_ENABLED", False))


def _guard_master():
    if not _master_on():
        abort(404)


def _all_destinations() -> list[dict]:
    """Local SIEMPRE primero, luego los servidores registrados (plan 91)."""
    dests = [{"key": "__local__", "label": "Local", "kind": "local", "host": None}]
    for s in server_registry.list_servers():
        dests.append({"key": s["alias"], "label": s["alias"], "kind": "remote", "host": s.get("host")})
    return dests


def _target_cfg(app: dict, target_key: str) -> dict | None:
    return (app.get("targets") or {}).get(target_key)


def _now():
    return datetime.now(timezone.utc)


def _decorate_entry(entry: dict | None) -> dict | None:
    if entry is None:
        return None
    out = dict(entry)
    out["effective_status"] = planner.derive_effective_status(entry, _now())
    return out


# ── /overview ────────────────────────────────────────────────────────────────

@bp.get("/overview")
def overview_route():
    _guard_master()
    apps = store.list_apps()
    dests = _all_destinations()
    out_apps = []
    for app in apps:
        targets_out = []
        for d in dests:
            cfg = _target_cfg(app, d["key"])
            last_rows = store.read_ledger(app_id=app["id"], target=d["key"], limit=1)
            last = _decorate_entry(last_rows[0]) if last_rows else None
            targets_out.append({
                "key": d["key"], "label": d["label"], "kind": d["kind"], "host": d.get("host"),
                "configured": cfg is not None,
                "protected": bool((cfg or {}).get("protected")),
                "last": last,
                "locked": store.is_locked(app["id"], d["key"]),
            })
        entries_all = store.read_ledger(app_id=app["id"], limit=1000)
        out_apps.append({
            "id": app["id"], "name": app.get("name") or app["id"],
            "artifact": app.get("artifact"),
            "targets": targets_out,
            "metrics": planner.dora_metrics(entries_all, _now()),
        })
    return jsonify({"apps": out_apps})


# ── apps CRUD ─────────────────────────────────────────────────────────────────

@bp.post("/apps")
def create_app_route():
    _guard_master()
    body = request.get_json(silent=True) or {}
    try:
        app = store.upsert_app(body)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"app": app})


@bp.put("/apps/<app_id>")
def update_app_route(app_id):
    _guard_master()
    body = request.get_json(silent=True) or {}
    body = {**body, "id": app_id}
    try:
        app = store.upsert_app(body)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"app": app})


@bp.delete("/apps/<app_id>")
def delete_app_route(app_id):
    _guard_master()
    if store.is_locked(app_id):
        return jsonify({"error": "deploy_in_progress"}), 409
    ok = store.delete_app(app_id)
    if not ok:
        return jsonify({"error": "app_not_found"}), 404
    return jsonify({"ok": True})


# ── /plan (dry-run, SIN efectos) ────────────────────────────────────────────

def _preflight_target(app: dict, target_key: str, target_cfg: dict, artifact_size_mb: float) -> list[dict]:
    warnings = []
    if target_key == "__local__":
        import shutil
        try:
            free = shutil.disk_usage(target_cfg["install_path"][:3]).free  # "D:\\"
        except Exception:
            free = None
        w = planner.check_disk_headroom(free, int(artifact_size_mb * 1024 * 1024))
        if w:
            warnings.append({"kind": "disk_headroom", "detail": w})
        return warnings

    from services import remote_exec
    server = server_registry.get_server(target_key)
    host = (server or {}).get("host")
    if host:
        ok, detail = server_registry.test_connectivity(host, 5985)
        if not ok:
            warnings.append({"kind": "connectivity", "detail": detail})
    winrm = remote_exec.check_winrm(target_key)
    if not winrm.get("ok"):
        warnings.append({
            "kind": "winrm", "detail": winrm.get("detail"),
            "winrm_kind": winrm.get("kind"), "remediation": winrm.get("remediation", []),
        })
    return warnings


@bp.post("/plan")
def plan_route():
    _guard_master()
    body = request.get_json(silent=True) or {}
    app_id = body.get("app_id")
    target_keys = body.get("targets") or []
    app = store.get_app(app_id)
    if app is None:
        return jsonify({"error": "app_not_found"}), 404
    if not target_keys:
        return jsonify({"error": "targets (lista no vacia) es obligatorio"}), 400

    retain = int(getattr(_config.config, "STACKY_DEPLOYMENTS_RETAIN_RELEASES", 3))
    smoke_timeout = int(getattr(_config.config, "STACKY_DEPLOYMENTS_SMOKE_TIMEOUT_SEC", 30))
    version_id = planner.make_version_id(_now(), "0" * 64)  # tentativa (sha real recién en /execute)

    by_target = []
    for tk in target_keys:
        cfg = _target_cfg(app, tk)
        if cfg is None:
            by_target.append({"target": tk, "error": "target_not_configured"})
            continue
        plan_steps = planner.build_deploy_plan(app, tk, cfg, version_id, retain, smoke_timeout)
        warnings = _preflight_target(app, tk, cfg, 0)
        by_target.append({"target": tk, "steps": plan_steps, "warnings": warnings})

    return jsonify({"version_id": version_id, "targets": by_target})


# ── /execute (HITL, EXECUTE gate) ───────────────────────────────────────────

@bp.post("/execute")
def execute_route():
    _guard_master()
    if not _execute_on():
        return jsonify({"error": "deployments_execute_disabled"}), 403
    body = request.get_json(silent=True) or {}
    if body.get("confirm") is not True:
        return jsonify({"error": "confirm=True requerido (HITL)"}), 400
    app_id = body.get("app_id")
    target_keys = body.get("targets") or []
    app = store.get_app(app_id)
    if app is None:
        return jsonify({"error": "app_not_found"}), 404
    if not target_keys:
        return jsonify({"error": "targets (lista no vacia) es obligatorio"}), 400

    for tk in target_keys:
        cfg = _target_cfg(app, tk)
        if cfg is None:
            return jsonify({"error": f"target no configurado: {tk}"}), 400
        if cfg.get("protected") and body.get("confirm_text") != app_id:
            return jsonify({"error": "confirm_text_required"}), 400

    retain = int(getattr(_config.config, "STACKY_DEPLOYMENTS_RETAIN_RELEASES", 3))
    smoke_timeout = int(getattr(_config.config, "STACKY_DEPLOYMENTS_SMOKE_TIMEOUT_SEC", 30))
    try:
        artifact = executor.build_artifact_zip(app)
    except ValueError as e:
        return jsonify({"error": str(e), "kind": "artifact_invalid"}), 400
    version_id = planner.make_version_id(_now(), artifact["sha256"])

    plans = {}
    for tk in target_keys:
        cfg = _target_cfg(app, tk)
        plan_steps = planner.build_deploy_plan(app, tk, cfg, version_id, retain, smoke_timeout)
        plans[tk] = {
            "plan": plan_steps, "version_id": version_id, "zip_local": artifact["zip_path"],
            "retain": retain, "prev_version_id": store.last_success_version(app_id, tk),
            "source": {"kind": app["artifact"]["kind"], "path": app["artifact"]["path"],
                       "sha256": artifact["sha256"], "size_mb": artifact["size_mb"]},
        }

    results = executor.start_deploy_async(app, target_keys, plans, operator=current_user())
    all_locked = all(r.get("error") == "deploy_in_progress" for r in results)
    status_code = 409 if all_locked else 200
    return jsonify({"version_id": version_id, "results": results}), status_code


# ── /rollback (HITL, EXECUTE gate) ──────────────────────────────────────────

@bp.post("/rollback")
def rollback_route():
    _guard_master()
    if not _execute_on():
        return jsonify({"error": "deployments_execute_disabled"}), 403
    body = request.get_json(silent=True) or {}
    if body.get("confirm") is not True:
        return jsonify({"error": "confirm=True requerido (HITL)"}), 400
    app_id = body.get("app_id")
    target_key = body.get("target")
    to_version = body.get("to_version")
    app = store.get_app(app_id)
    if app is None:
        return jsonify({"error": "app_not_found"}), 404
    cfg = _target_cfg(app, target_key or "")
    if cfg is None:
        return jsonify({"error": "target no configurado"}), 400
    if not to_version:
        return jsonify({"error": "to_version es obligatorio"}), 400
    if cfg.get("protected") and body.get("confirm_text") != app_id:
        return jsonify({"error": "confirm_text_required"}), 400

    result = executor.start_rollback_async(app, target_key, to_version, operator=current_user())
    status_code = 409 if result.get("error") == "deploy_in_progress" else 200
    return jsonify(result), status_code


# ── /rollback/preview (Plan 189 — read-only, SIN gate de ejecución) ──────────

@bp.post("/rollback/preview")
def rollback_preview_route():
    """Semáforo de reversibilidad + simulacro read-only. NO exige _execute_on():
    acá NO se ejecuta nada (solo lecturas locales del ledger + builder puro).

    Modos: single {app_id, target[, to_version]} | batch {pairs: [{app_id, target}, ...]}
    (C3 — la UI resuelve todas las cards en 1 request). Plan 189."""
    _guard_master()  # master del Centro (patrón :37-39)
    if not bool(getattr(_config.config, "STACKY_DEVOPS_ROLLBACK_READINESS_ENABLED", False)):
        abort(404)
    body = request.get_json(silent=True) or {}
    from services.rollback_readiness import compute_rollback_readiness, simulate_rollback_plan
    from services.stacky_logger import logger as stacky_logger

    # C1 — timeout INLINE (la helper _smoke_timeout_s vive en deploy_executor.py:262-264 y
    # este blueprint NO la tiene; NO importar deploy_executor):
    smoke_timeout_s = int(getattr(_config.config, "STACKY_DEPLOYMENTS_SMOKE_TIMEOUT_SEC", 30))

    pairs = body.get("pairs")
    if isinstance(pairs, list):                      # ── modo BATCH (C3)
        if len(pairs) > 100:
            return jsonify({"error": "max 100 pares"}), 400
        out: dict = {}
        for p in pairs:
            a, t = (p or {}).get("app_id"), (p or {}).get("target")
            if not a or not t:
                continue                             # pares malformados se omiten, no rompen el batch
            r = compute_rollback_readiness(a, t)
            if r is not None:
                out[f"{a}|{t}"] = r
        stacky_logger.info("rollback_readiness", "preview_built", batch=True, count=len(out))
        return jsonify({"readiness_map": out})

    app_id, target = body.get("app_id"), body.get("target")  # ── modo SINGLE
    if not app_id or not target:
        return jsonify({"error": "app_id y target son obligatorios"}), 400
    readiness = compute_rollback_readiness(app_id, target)
    if readiness is None:
        return jsonify({"error": "app_not_found"}), 404
    plan = None
    to_version = body.get("to_version")
    if to_version:
        plan = simulate_rollback_plan(app_id, target, str(to_version), smoke_timeout_s)
        if plan is None:
            return jsonify({"error": "version_not_retained"}), 404
    stacky_logger.info("rollback_readiness", "preview_built",
                       app_id=app_id, target=target, batch=False)  # [ADICIÓN ARQUITECTO 2]
    return jsonify({"readiness": readiness, "plan": plan})


# ── runs / history ───────────────────────────────────────────────────────────

@bp.get("/runs/<run_id>")
def run_detail_route(run_id):
    _guard_master()
    rows = store.read_ledger(limit=5000)
    entry = next((r for r in rows if r.get("run_id") == run_id), None)
    if entry is None:
        return jsonify({"error": "run_not_found"}), 404
    return jsonify({"run": _decorate_entry(entry)})


@bp.get("/history")
def history_route():
    _guard_master()
    app_id = request.args.get("app_id")
    target = request.args.get("target")
    limit = int(request.args.get("limit") or 100)
    rows = store.read_ledger(app_id=app_id, target=target, limit=limit)
    return jsonify({"runs": [_decorate_entry(r) for r in rows]})


# ── evidence (Plan 188 — run fallido → paquete de evidencia, solo-lectura) ────

@bp.post("/evidence")
def evidence_route():
    """Run fallido → paquete de evidencia determinista (resumen + markdown +
    JSON sin secretos). Solo-lectura local; crear la incidencia sigue siendo
    decisión del operador en el modal HITL. Plan 188."""
    _guard_master()  # master del Centro (patrón :37-39)
    if not bool(getattr(_config.config, "STACKY_DEVOPS_FAILURE_EVIDENCE_ENABLED", False)):
        abort(404)
    body = request.get_json(silent=True) or {}
    app_id, target, run_id = body.get("app_id"), body.get("target"), body.get("run_id")
    if not app_id or not target or not run_id:
        return jsonify({"error": "app_id, target y run_id son obligatorios"}), 400
    from services.devops_evidence import build_deploy_failure_evidence
    bundle = build_deploy_failure_evidence(app_id, target, run_id)
    if bundle is None:
        return jsonify({"error": "run_not_found"}), 404
    from services.stacky_logger import logger as stacky_logger
    stacky_logger.info("devops_evidence", "evidence_built",
                       app_id=app_id, target=target, run_id=run_id)
    return jsonify({"evidence": bundle.to_dict()})


# ── drift ────────────────────────────────────────────────────────────────────

@bp.post("/drift")
def drift_route():
    _guard_master()
    body = request.get_json(silent=True) or {}
    app_id = body.get("app_id")
    target_key = body.get("target")
    app = store.get_app(app_id)
    if app is None:
        return jsonify({"error": "app_not_found"}), 404
    cfg = _target_cfg(app, target_key or "")
    if cfg is None:
        return jsonify({"error": "target no configurado"}), 400

    command = f"Get-Content -LiteralPath '{cfg['install_path']}\\release.json' -Raw"
    if target_key == "__local__":
        result = executor.LocalTransport().run(command, read_only=True)
    else:
        from services import remote_exec
        result = remote_exec.run_deploy_step(target_key, command, timeout_s=30, read_only=True, run_id="drift")
    marker = planner.parse_release_marker(result.get("stdout") or "") if result.get("ok") else None
    desired = store.last_success_version(app_id, target_key)
    drift = planner.compute_drift(desired, marker)
    return jsonify({"drift": drift, "desired_version": desired, "marker": marker})


# ── metrics ──────────────────────────────────────────────────────────────────

@bp.get("/metrics")
def metrics_route():
    _guard_master()
    app_id = request.args.get("app_id")
    if not app_id:
        return jsonify({"error": "app_id es obligatorio"}), 400
    entries = store.read_ledger(app_id=app_id, limit=1000)
    return jsonify(planner.dora_metrics(entries, _now()))


# ── diagnose (IA local, opt-in) ──────────────────────────────────────────────

@bp.post("/diagnose")
def diagnose_route():
    _guard_master()
    if not _ai_on():
        abort(404)
    body = request.get_json(silent=True) or {}
    run_id = body.get("run_id")
    if not run_id:
        return jsonify({"error": "run_id es obligatorio"}), 400
    from services.deploy_diagnosis import diagnose_run
    result = diagnose_run(run_id)
    status = 200 if result.get("ok") else 502
    return jsonify(result), status
