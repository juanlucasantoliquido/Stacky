"""services/parity_rollout.py -- Plan 218 F8.

Único punto de evaluación del despliegue gradual por capacidad. Sin I/O de red.

Tres niveles, en este orden (§8 del plan):
  1) la flag maestra STACKY_PROVIDER_PARITY_ENABLED (OFF ⇒ True para TODO,
     comportamiento pre-plan byte-idéntico);
  2) el status de la capacidad en CAPABILITY_MATRIX;
  3) un override opcional por proyecto en issue_tracker.parity_overrides.<capability>.

R4: ningún subplan agrega una flag por capacidad — usan `parity_overrides`.

Este módulo nombra a los dos proveedores por definición (resuelve el tracker activo):
está en NEUTRAL_REGISTRY_ALLOWLIST del censo de F1.
"""
from __future__ import annotations

from services.provider_capabilities import (
    CAPABILITY_KEYS,
    capability_loss,
    capability_status,
    supports,
)

_DEFAULT_PROVIDER = "azure_devops"


def _parity_enabled() -> bool:
    import config as _config  # noqa: PLC0415

    return bool(getattr(_config.config, "STACKY_PROVIDER_PARITY_ENABLED", True))


def _project_tracker(project: str | None) -> tuple[str, str, dict]:
    """(tracker_type, nombre del proyecto, overrides declarados). Nunca levanta."""
    try:
        from services.project_context import (  # noqa: PLC0415
            _config_for_project_name,
            resolve_project_context,
        )

        ctx = resolve_project_context(project_name=project)
        tracker_type = (getattr(ctx, "tracker_type", None) or _DEFAULT_PROVIDER).strip().lower()
        nombre = getattr(ctx, "stacky_project_name", None) or (project or "")
        cfg = _config_for_project_name(nombre) or {}
        overrides = ((cfg.get("issue_tracker") or {}).get("parity_overrides")) or {}
        if not isinstance(overrides, dict):
            overrides = {}
        return tracker_type, nombre, overrides
    except Exception:  # noqa: BLE001 — consultivo: nunca romper el flujo del llamador
        return _DEFAULT_PROVIDER, (project or ""), {}


def capability_enabled(capability: str, project: str | None = None) -> bool:
    """AND de los tres niveles. Con la flag maestra OFF devuelve True para todo."""
    if not _parity_enabled():
        return True

    tracker_type, _, overrides = _project_tracker(project)
    if capability in overrides:
        return bool(overrides[capability])
    return supports(tracker_type, capability)


def parity_report(project: str | None = None) -> dict:
    """{'provider','project','parity_enabled','capabilities':[{key,status,enabled,loss,owner_plan}]}"""
    tracker_type, nombre, overrides = _project_tracker(project)
    duenos = _owner_plans()
    maestra = _parity_enabled()

    capacidades = []
    for key in CAPABILITY_KEYS:
        estado = capability_status(tracker_type, key)
        if not maestra:
            habilitada = True
        elif key in overrides:
            habilitada = bool(overrides[key])
        else:
            habilitada = estado in ("full", "partial")
        capacidades.append({
            "key": key,
            "status": estado,
            "enabled": habilitada,
            "loss": capability_loss(tracker_type, key),
            "owner_plan": duenos.get(key),
        })

    return {
        "provider": tracker_type,
        "project": nombre,
        "parity_enabled": maestra,
        "capabilities": capacidades,
    }


def _owner_plans() -> dict[str, int]:
    """capacidad -> subplan dueño, leído del catálogo de F7. {} si no está disponible."""
    try:
        from services.parity_series import load_series  # noqa: PLC0415

        duenos: dict[str, int] = {}
        for sub in load_series().get("subplans", []):
            for cap in sub.get("capabilities", []):
                duenos.setdefault(cap, int(sub["number"]))
        return duenos
    except Exception:  # noqa: BLE001 — el catálogo es informativo, no crítico
        return {}
