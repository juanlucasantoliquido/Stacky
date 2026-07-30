"""Plan 79 — Estados de tarea deterministas y configurables.

Módulo puro (F1/F8) + lector de flag (F0) + helper runner-side (F2). Espeja el
estilo de harness/task_gate.py: nunca lanza, es la fuente única de verdad de
qué estados puede aplicar el wiring determinista.
"""
from __future__ import annotations

import logging
from typing import NamedTuple, Optional

logger = logging.getLogger("stacky_agents.task_states")


# ---------------------------------------------------------------------------
# F0 — lector del flag maestro (vía Config, NO os.getenv directo)
# ---------------------------------------------------------------------------

def deterministic_task_states_enabled() -> bool:
    """Lee del atributo de Config (env_only=False ⇒ editable por UI sin reiniciar
    el proceso). NO usar os.getenv: rompería la edición por UI que actualiza
    Config en caliente."""
    try:
        from config import Config

        return bool(getattr(Config, "STACKY_DETERMINISTIC_TASK_STATES_ENABLED", False))
    except Exception:
        return False


# ---------------------------------------------------------------------------
# F1 — resolver puro + vocabulario congelado
# ---------------------------------------------------------------------------

# Claves del dict tracker_state_machine.<agent> que este módulo lee/aplica.
# CONGELADO: el wiring NO puede aplicar un estado que no provenga de estas claves.
_APPLICABLE_KEYS: frozenset[str] = frozenset({"in_progress", "next_state_ok"})
# Mismo conjunto, con orden estable para recorrer/reportar (validación, UI).
_APPLICABLE_KEYS_ORDER: tuple[str, ...] = ("in_progress", "next_state_ok")
# blocked_state queda FUERA a propósito: es acción humana (Plan B7), nunca la
# aplica este flujo.


class TaskStatePlan(NamedTuple):
    in_progress: Optional[str]   # estado a aplicar AL INICIAR; None = no aplicar
    final_ok: Optional[str]      # estado a aplicar al COMPLETAR OK; None = no aplicar
    source: str                  # "matrix" | "config" | "absent" | "no_agent_type"


def _machine_for(profile: dict, agent_type: Optional[str]) -> dict:
    """Devuelve tracker_state_machine[agent_type] o {} defensivo."""
    if not isinstance(profile, dict) or not agent_type:
        return {}
    machine = (profile.get("tracker_state_machine") or {}).get(agent_type)
    return machine if isinstance(machine, dict) else {}


# ── Plan 208 F1 — dimensión work_item_type de la matriz ──────────────────────

def _normalize_wit(raw: Optional[str]) -> Optional[str]:
    """Normaliza un WorkItemType para lookup: strip; None/'' -> None. El case se
    compara aparte (match exacto primero, luego case-insensitive)."""
    s = (raw or "").strip()
    return s or None


def _matrix_cell(machine: dict, work_item_type: Optional[str]) -> dict:
    """Devuelve by_work_item_type[<tipo>] con match case-insensitive; {} si no hay
    override. Pura, defensiva."""
    wit = _normalize_wit(work_item_type)
    if not wit or not isinstance(machine, dict):
        return {}
    by = machine.get("by_work_item_type")
    if not isinstance(by, dict):
        return {}
    # match exacto primero; luego case-insensitive.
    if wit in by and isinstance(by[wit], dict):
        return by[wit]
    low = wit.casefold()
    for k, v in by.items():
        if isinstance(k, str) and k.strip().casefold() == low and isinstance(v, dict):
            return v
    return {}


def resolve_task_state_plan(
    profile: dict,
    agent_type: Optional[str],
    work_item_type: Optional[str] = None,
) -> TaskStatePlan:
    """Fuente ÚNICA de los estados deterministas. Pura, nunca lanza.

    Retrocompatible: `work_item_type=None` ⇒ comportamiento previo exacto.
    - Si hay override en by_work_item_type[<tipo>] con ≥1 valor no vacío
      ⇒ source="matrix" (el cell MANDA: lo no definido en el cell queda None).
    - Si no ⇒ cae a machine.in_progress/next_state_ok ⇒ source="config"/"absent".
    - source: 'no_agent_type' si falta agent_type; 'absent' si la máquina no
      define ninguno; 'config' si define ≥1.
    """
    try:
        if not agent_type:
            return TaskStatePlan(None, None, "no_agent_type")
        m = _machine_for(profile, agent_type)
        cell = _matrix_cell(m, work_item_type)
        ip_m = (cell.get("in_progress") or "").strip() or None
        fk_m = (cell.get("next_state_ok") or "").strip() or None
        if ip_m is not None or fk_m is not None:
            return TaskStatePlan(ip_m, fk_m, "matrix")
        ip = (m.get("in_progress") or "").strip() or None
        fk = (m.get("next_state_ok") or "").strip() or None
        if ip is None and fk is None:
            return TaskStatePlan(None, None, "absent")
        return TaskStatePlan(ip, fk, "config")
    except Exception:
        logger.debug("resolve_task_state_plan falló (no crítico)", exc_info=True)
        return TaskStatePlan(None, None, "absent")


def applicable_states(plan: TaskStatePlan) -> frozenset[str]:
    """Conjunto CERRADO de estados que el wiring puede aplicar para este plan."""
    return frozenset(s for s in (plan.in_progress, plan.final_ok) if s)


# ---------------------------------------------------------------------------
# F8 — _safe_transition: idempotencia + única escritura de estado
# ---------------------------------------------------------------------------

def _extract_current_state(item: dict) -> "str | None":
    """Estado actual tolerante a ambos shapes de provider.get_item():
    - GitLab normaliza → item['state'] (gitlab_provider.py:74).
    - ADO devuelve crudo → item['fields']['System.State'] (ado_client.get_work_item:842).
    Pura, nunca lanza."""
    if not isinstance(item, dict):
        return None
    top = item.get("state")
    if isinstance(top, str) and top.strip():
        return top.strip()
    fields = item.get("fields")
    if isinstance(fields, dict):
        sysst = fields.get("System.State")
        if isinstance(sysst, str) and sysst.strip():
            return sysst.strip()
    return None


def _safe_transition(
    provider,
    ado_id,
    target,
    *,
    phase,
    legacy_client_fn=None,
    correlation_id=None,
) -> dict:
    """ÚNICA función que escribe estado. Idempotente y defensiva; nunca lanza.
    - Si provider expone get_item, lee el estado actual (via _extract_current_state,
      tolerante ADO/GitLab); si ya == target (case-insensitive) → skip 'already_in_state'.
    - Aplica via provider.update_item_state(str(ado_id), target); si provider es
      None y hay legacy_client_fn, usa legacy_client_fn().update_work_item_state(int(ado_id), target).
    - Devuelve {ok|skipped|error, to, phase, ...}."""
    if not target or ado_id is None:
        return {"skipped": True, "reason": "no_target_or_id", "phase": phase}
    # Idempotencia (best-effort: si get_item falla, seguimos a la transición).
    try:
        if provider is not None and hasattr(provider, "get_item"):
            current = _extract_current_state(provider.get_item(str(ado_id)) or {})
            if current and current.lower() == target.strip().lower():
                return {"skipped": True, "reason": "already_in_state", "to": target, "phase": phase}
    except Exception:
        logger.debug("get_item falló en _safe_transition (no crítico)", exc_info=True)
    try:
        if provider is not None:
            provider.update_item_state(str(ado_id), target)
        elif legacy_client_fn is not None:
            legacy_client_fn().update_work_item_state(int(ado_id), target)
        else:
            return {"skipped": True, "reason": "no_provider", "phase": phase}
        return {"ok": True, "to": target, "phase": phase, "source": "config"}
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "_safe_transition(%s) falló ADO-%s corr=%s", phase, ado_id, correlation_id
        )
        # Plan 271 D3/F3-bis-3 — la ÚNICA rama de todo el sistema que decidía no
        # cambiar el estado y no decía por qué. Sin `reason`, F5 la traducía a
        # "unknown", string fuera de ALL_FINAL_STATE_REASONS (services/
        # final_state_resolver.py). "transition_failed" SÍ está en ese catálogo.
        return {"ok": False, "to": target, "reason": "transition_failed",
                "error": str(exc), "type": type(exc).__name__, "phase": phase}


# ---------------------------------------------------------------------------
# F2 — helper runner-side (aplicar estado-en-progreso al iniciar)
# ---------------------------------------------------------------------------

def apply_task_start_state(*, project_name, agent_type, ado_id, provider) -> dict:
    """Aplica el estado-en-progreso de la config. Pura respecto de HTTP (sin
    request/correlation_id). `provider` = TrackerProvider ya resuelto para el
    proyecto (o None). Nunca lanza."""
    if not deterministic_task_states_enabled():
        return {"skipped": True, "reason": "flag_off"}
    try:
        from services.client_profile import load_effective_client_profile

        profile = load_effective_client_profile(project_name) or {}
    except Exception:
        profile = {}
    plan = resolve_task_state_plan(profile, agent_type)
    target = plan.in_progress
    if not target or target not in applicable_states(plan) or not ado_id or provider is None:
        return {"skipped": True, "reason": "no_in_progress_or_no_target"}
    return _safe_transition(provider, ado_id, target, phase="start")


# ---------------------------------------------------------------------------
# F5 — validación de la config contra los estados reales del tracker
# ---------------------------------------------------------------------------

def validate_states_against_tracker(profile: dict, valid_states: list) -> list:
    """Devuelve warnings [{agent_type, field, value, reason:'state_not_in_tracker'}].
    valid_states vacío → no valida (devuelve []), para no romper si el tracker
    no expone estados.

    Plan 208 F4/F5: además del nivel agente, recorre
    `by_work_item_type[<tipo>].{in_progress,next_state_ok}`; esos warnings traen
    `work_item_type` para que la UI ubique el cell exacto."""
    out: list = []
    try:
        if not valid_states:
            return out
        valid = {s.strip().lower() for s in valid_states if isinstance(s, str)}
        machines = (profile.get("tracker_state_machine") or {}) if isinstance(profile, dict) else {}
        for agent_type, m in machines.items():
            if not isinstance(m, dict):
                continue
            for field in _APPLICABLE_KEYS_ORDER:
                val = (m.get(field) or "").strip()
                if val and val.lower() not in valid:
                    out.append(
                        {
                            "agent_type": agent_type,
                            "field": field,
                            "value": val,
                            "reason": "state_not_in_tracker",
                        }
                    )
            by = m.get("by_work_item_type")
            if not isinstance(by, dict):
                continue
            for wit, cell in by.items():
                if not isinstance(cell, dict):
                    continue
                for field in _APPLICABLE_KEYS_ORDER:
                    val = (cell.get(field) or "").strip()
                    if val and val.lower() not in valid:
                        out.append(
                            {
                                "agent_type": agent_type,
                                "work_item_type": str(wit),
                                "field": field,
                                "value": val,
                                "reason": "state_not_in_tracker",
                            }
                        )
        return out
    except Exception:
        logger.debug("validate_states_against_tracker falló (no crítico)", exc_info=True)
        return []
