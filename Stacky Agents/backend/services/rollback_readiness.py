"""services/rollback_readiness.py — Plan 189. Reversibilidad como indicador (read-only).

PURO: lecturas locales vía services.deploy_store + builder puro de deploy_planner.
PROHIBIDO importar deploy_executor, remote_exec o requests (ver
test_sin_imports_de_ejecucion): este módulo JAMÁS ejecuta nada, solo compone la
información de "¿puedo volver atrás?" y CONSTRUYE (sin correr) los pasos del
rollback para un simulacro inocuo.
"""
from __future__ import annotations

from services import deploy_store as store
from services import deploy_planner as planner

SCHEMA_VERSION = "189.1"

# códigos EXACTOS de razones de no-readiness (la UI los traduce)
REASON_NO_TARGET_CFG = "sin_target_cfg"
REASON_NO_RETAINED = "sin_versiones_retenidas"
REASON_ONLY_CURRENT = "solo_version_actual"
REASON_RUN_IN_PROGRESS = "run_en_curso"


def compute_rollback_readiness(app_id: str, target: str) -> dict | None:
    """Semáforo de reversibilidad para (app_id, target). Lecturas locales puras.

    None si la app no existe. Si existe, devuelve el shape completo con `ready`,
    `to_version`, `candidates`, `reasons` tipadas. F1 implementa el cálculo real.
    """
    app = store.get_app(app_id)              # deploy_store.py:63
    if app is None:
        return None
    cfg = (app.get("targets") or {}).get(target)
    reasons: list[str] = []
    if cfg is None:
        reasons.append(REASON_NO_TARGET_CFG)
    current = store.last_success_version(app_id, target)      # :186
    # retained_versions (:195): más recientes primero, sin duplicados. NO re-ordenar:
    # ese orden ya refleja la retención del plan 120.
    retained = store.retained_versions(app_id, target, n=10)
    candidates = [v for v in retained if v != current]
    if not retained:
        reasons.append(REASON_NO_RETAINED)
    elif not candidates:
        reasons.append(REASON_ONLY_CURRENT)
    locked = store.is_locked(app_id, target)                  # :175 — C4: UNA sola llamada
    if locked:
        reasons.append(REASON_RUN_IN_PROGRESS)
    return {
        "schema_version": SCHEMA_VERSION,
        "ready": not reasons,
        "to_version": candidates[0] if candidates else None,  # la más reciente ≠ actual
        "candidates": candidates,
        "current_version": current,
        "protected": bool(cfg.get("protected")) if cfg else False,
        "locked": locked,
        "reasons": reasons,
    }


def simulate_rollback_plan(app_id: str, target: str, to_version: str,
                           smoke_timeout_s: int) -> dict | None:
    """Simulacro read-only: construye (sin ejecutar) los pasos EXACTOS del rollback.

    None si app/target/version inválidos. NUNCA ejecuta: solo construye el plan
    con el MISMO builder puro que usa el executor real (deploy_planner.build_rollback_plan,
    espejando el call-site deploy_executor.py:312). F2 implementa el cálculo real.
    """
    app = store.get_app(app_id)
    if app is None:
        return None
    cfg = (app.get("targets") or {}).get(target)
    if cfg is None:
        return None
    retained = store.retained_versions(app_id, target, n=10)
    if to_version not in retained:
        return None                      # el endpoint lo traduce a 404 version_not_retained
    # Mismo orden de argumentos que deploy_executor.py:312 (fuente de verdad de KPI-3):
    #   build_rollback_plan(app, target_key, target_cfg, to_version, smoke_timeout_s)
    steps = planner.build_rollback_plan(app, target, cfg, to_version, smoke_timeout_s)
    return {
        "schema_version": SCHEMA_VERSION,
        "to_version": to_version,
        "smoke_timeout_s": smoke_timeout_s,
        "steps": steps,                  # dicts _step: {name, command, read_only, housekeeping}
        "simulated": True,               # SIEMPRE True — marca inequívoca de que NADA se ejecutó
    }
