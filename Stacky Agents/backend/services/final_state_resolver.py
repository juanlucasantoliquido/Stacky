# backend/services/final_state_resolver.py
"""Plan 271 F1 — Resolutor ÚNICO del estado final al terminar un agente.

Puro: sin DB, sin red, sin config global mutable salvo la lectura de la flag.
Nunca lanza. Siempre devuelve una FinalStateDecision con `reason` no vacío.
"""
from __future__ import annotations
from typing import NamedTuple, Optional

# Precedencia CONGELADA, de mayor a menor. El primero que produce un estado gana.
PRECEDENCE: tuple[str, ...] = ("caller", "matrix", "role", "employee_config")

# `final_status` que habilita una transición. Igual que completion_state._OK_STATUSES.
_OK_FINAL_STATUSES: frozenset[str] = frozenset({"completed"})

# Razones que ESTE módulo puede devolver.
REASONS: frozenset[str] = frozenset({
    "ok", "not_ok_status", "no_agent_type", "no_config", "flag_off",
})

# Catálogo COMPLETO de razones que cualquier escritor de estado puede emitir
# (§2.4 del plan 271). Fuente única para el mapa de la UI (F6), para el test
# puente (F6) y para el centinela de contrato (F9).
# Agregar una razón nueva sin agregarla acá deja DOS tests rojos.
# D3 — "unknown" NO está y NO puede estar: es la confesión de que falta una razón.
ALL_FINAL_STATE_REASONS: frozenset[str] = frozenset({
    "ok", "flag_off", "not_ok_status", "no_ticket",
    "no_ado_id_or_stacky_project", "no_matrix_cell", "no_final_state",
    "state_not_applicable", "human_moved_out_of_flow", "exception",
    "no_config", "no_agent_type", "no_target_or_id", "already_in_state",
    "no_provider", "not_requested", "publish_not_ok", "review_mode_hold",
    "no_ticket_id", "ticket_lookup_failed", "no_ado_id",
    "ado_client_unavailable", "provider_unavailable",
    # ── agregadas en el v3 (D3, D6) ──────────────────────────────────────
    "dev_build_gate_no_state",          # api/tickets.py:574 (YA existe) + F2-bis
    "already_written_by_other_engine",  # árbitro simétrico (F2-bis, F3-bis-2)
    "transition_failed",                # rama de error de _safe_transition (F3-bis-3)
    "no_project_context",               # ticket sin stacky_project_name (F3, D6)
})

assert REASONS <= ALL_FINAL_STATE_REASONS
assert "unknown" not in ALL_FINAL_STATE_REASONS


class FinalStateDecision(NamedTuple):
    state: Optional[str]   # estado a aplicar; None = no aplicar
    source: str            # uno de PRECEDENCE, o "none"
    reason: str            # uno de REASONS. NUNCA vacío.


def role_fallback_enabled() -> bool:
    """Lee la INSTANCIA config.config (NO el atributo de clase Config): con la
    clase, monkeypatch.setattr(config.config, ...) del test no voltea el branch.
    Mismo patrón que completion_state.matrix_enabled (completion_state.py:32-35)."""
    try:
        from config import config as _cfg
        return bool(getattr(_cfg, "STACKY_FINAL_STATE_ROLE_FALLBACK_ENABLED", False))
    except Exception:  # noqa: BLE001
        return False


# D2 — el árbitro SIMÉTRICO vive acá, no en un motor, para que los DOS motores
# lean exactamente el mismo criterio de "ya se escribió". El cuerpo completo está
# en §F2-bis; se crea en ESTA fase porque F2-bis y F3-bis-2 lo importan los dos.
def final_state_already_written(execution_id) -> bool:
    """Plan 271 F2-bis / F3-bis-2 — árbitro SIMÉTRICO por execution_id.

    True si algún motor ya aplicó el estado final de esta ejecución (la key
    `final_state_outcome` que F5 persiste, con applied=True).
    Best-effort: cualquier problema ⇒ False (fail-open, nunca bloquea un cierre).
    """
    if not execution_id:
        return False
    try:
        from db import session_scope
        from models import AgentExecution
        with session_scope() as s:
            row = s.get(AgentExecution, int(execution_id))
            fso = (row.metadata_dict or {}).get("final_state_outcome") if row else None
            return bool(isinstance(fso, dict) and fso.get("applied") is True)
    except Exception:  # noqa: BLE001
        return False


def resolve_final_state(
    *,
    caller_state: Optional[str] = None,
    matrix_state: Optional[str] = None,
    role_state: Optional[str] = None,
    employee_state: Optional[str] = None,
    agent_type: Optional[str] = None,
    final_status: str = "completed",
) -> FinalStateDecision:
    """Aplica PRECEDENCE. Pura. Nunca lanza.

    Casos borde: strings "" y "   " se tratan como None (`.strip()` antes de
    evaluar). Sólo la rama `role` consulta la flag; `caller`, `matrix` y
    `employee_config` la ignoran (E7): con las 4 flags apagadas, el
    comportamiento tiene que ser byte-idéntico al de hoy, y hoy esas tres
    ramas no dependen de ninguna flag de este plan.
    """
    try:
        fs = (final_status or "").strip().lower()
        caller_state = (caller_state or "").strip() or None
        matrix_state = (matrix_state or "").strip() or None
        role_state = (role_state or "").strip() or None
        employee_state = (employee_state or "").strip() or None

        if fs not in _OK_FINAL_STATUSES:
            return FinalStateDecision(None, "none", "not_ok_status")
        if not agent_type:
            return FinalStateDecision(None, "none", "no_agent_type")

        if caller_state:
            return FinalStateDecision(caller_state, "caller", "ok")
        if matrix_state:
            return FinalStateDecision(matrix_state, "matrix", "ok")
        if role_state:
            if not role_fallback_enabled():
                return FinalStateDecision(None, "none", "flag_off")
            return FinalStateDecision(role_state, "role", "ok")
        if employee_state:
            return FinalStateDecision(employee_state, "employee_config", "ok")
        return FinalStateDecision(None, "none", "no_config")
    except Exception:  # noqa: BLE001
        return FinalStateDecision(None, "none", "no_config")
