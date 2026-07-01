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
# blocked_state queda FUERA a propósito: es acción humana (Plan B7), nunca la
# aplica este flujo.


class TaskStatePlan(NamedTuple):
    in_progress: Optional[str]   # estado a aplicar AL INICIAR; None = no aplicar
    final_ok: Optional[str]      # estado a aplicar al COMPLETAR OK; None = no aplicar
    source: str                  # "config" | "absent" | "no_agent_type"


def _machine_for(profile: dict, agent_type: Optional[str]) -> dict:
    """Devuelve tracker_state_machine[agent_type] o {} defensivo."""
    if not isinstance(profile, dict) or not agent_type:
        return {}
    machine = (profile.get("tracker_state_machine") or {}).get(agent_type)
    return machine if isinstance(machine, dict) else {}


def resolve_task_state_plan(profile: dict, agent_type: Optional[str]) -> TaskStatePlan:
    """Fuente ÚNICA de los estados deterministas. Pura, nunca lanza.
    - in_progress = machine['in_progress'] (str no vacío) o None
    - final_ok    = machine['next_state_ok'] (str no vacío) o None
    - source: 'no_agent_type' si falta agent_type; 'absent' si la máquina no
      define ninguno; 'config' si define ≥1.
    """
    try:
        if not agent_type:
            return TaskStatePlan(None, None, "no_agent_type")
        m = _machine_for(profile, agent_type)
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
        return {"ok": False, "to": target, "error": str(exc), "type": type(exc).__name__, "phase": phase}


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
    no expone estados."""
    out: list = []
    try:
        if not valid_states:
            return out
        valid = {s.strip().lower() for s in valid_states if isinstance(s, str)}
        machines = (profile.get("tracker_state_machine") or {}) if isinstance(profile, dict) else {}
        for agent_type, m in machines.items():
            if not isinstance(m, dict):
                continue
            for field in ("in_progress", "next_state_ok"):
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
        return out
    except Exception:
        logger.debug("validate_states_against_tracker falló (no crítico)", exc_info=True)
        return []
