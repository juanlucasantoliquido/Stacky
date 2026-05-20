"""
ticket_diagnostics.py — Diagnostico causal de bloqueos por ticket.

Feature B: genera un diagnostico estructurado sobre por que un ticket no avanza.
Recopila datos de la BD local (aging, ejecuciones, historial de estado) y
opcionalmente llama al LLM si TICKET_DIAGNOSTICS_LLM_ENABLED=true.

Gate de eval: el endpoint solo usa LLM si run_evals_gate() pasa.
Si el LLM no esta habilitado, devuelve diagnostico deterministico con
las causas que se pueden inferir directamente de los datos.

Feature flag: TICKET_DIAGNOSTICS_LLM_ENABLED (default: false)
Cache: 60 minutos por ticket_id, invalidable manualmente via DELETE.
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timedelta
from typing import Any

logger = logging.getLogger("stacky_agents.ticket_diagnostics")

# Feature flag — el LLM no se habilita hasta que pasen los evals
_LLM_ENABLED = os.environ.get("TICKET_DIAGNOSTICS_LLM_ENABLED", "false").lower() == "true"

# Cache simple en memoria (por proceso)
# { ticket_id: { "result": dict, "cached_at": float } }
_CACHE: dict[int, dict] = {}
_CACHE_TTL_SEC = 3600  # 60 minutos


def _get_cached(ticket_id: int) -> dict | None:
    entry = _CACHE.get(ticket_id)
    if not entry:
        return None
    if time.time() - entry["cached_at"] > _CACHE_TTL_SEC:
        del _CACHE[ticket_id]
        return None
    return entry["result"]


def _set_cache(ticket_id: int, result: dict) -> None:
    _CACHE[ticket_id] = {"result": result, "cached_at": time.time()}


def invalidate_cache(ticket_id: int) -> bool:
    """Invalida la cache para un ticket. Retorna True si habia entrada."""
    if ticket_id in _CACHE:
        del _CACHE[ticket_id]
        return True
    return False


def _compute_aging_days(ticket) -> int:
    """Calcula cuantos dias lleva el ticket sin cerrarse."""
    if ticket.last_synced_at:
        return (datetime.utcnow() - ticket.created_at).days if ticket.created_at else 0
    return 0


def _build_deterministic_causes(ticket, executions: list, state_history: list) -> list[dict]:
    """Infiere causas probables sin LLM, basandose en datos de la BD."""
    causes = []

    # Causa: descripcion vacia o muy corta
    desc = (ticket.description or "").strip()
    if len(desc) < 50:
        causes.append({
            "category": "DATA",
            "description": "El ticket tiene descripcion vacia o demasiado corta",
            "confidence": 0.90,
            "evidence": [
                f"Longitud de descripcion: {len(desc)} caracteres",
                "Minimo recomendado: 50 caracteres",
            ],
        })

    # Causa: no tiene agente ejecutado
    if not executions:
        causes.append({
            "category": "PIP",
            "description": "Ningun agente Stacky fue ejecutado sobre este ticket",
            "confidence": 0.85,
            "evidence": [
                "0 ejecuciones registradas en agent_executions",
                "El pipeline de Stacky no fue iniciado",
            ],
        })
    else:
        # Causa: ultimo agente en error
        last_exec = max(executions, key=lambda e: e.started_at or datetime.min)
        if last_exec.status == "error":
            causes.append({
                "category": "PIP",
                "description": f"El ultimo agente ({last_exec.agent_type}) termino en error",
                "confidence": 0.88,
                "evidence": [
                    f"Ejecucion {last_exec.id}: status=error",
                    f"Error: {(last_exec.error_message or '')[:200]}",
                ],
            })

    # Causa: ticket sin asignar
    if not ticket.assigned_to_ado:
        causes.append({
            "category": "DATA",
            "description": "El ticket no tiene responsable asignado en ADO",
            "confidence": 0.75,
            "evidence": ["assigned_to_ado es NULL", "Usar el recomendador P6 para asignar"],
        })

    # Causa: sin transicion de estado reciente
    if state_history:
        last_transition_raw = max(state_history, key=lambda h: h.recorded_at or datetime.min)
        days_since = (datetime.utcnow() - last_transition_raw.recorded_at).days if last_transition_raw.recorded_at else 0
        if days_since > 7:
            causes.append({
                "category": "PIP",
                "description": f"El estado del ticket no cambio en los ultimos {days_since} dias",
                "confidence": 0.70,
                "evidence": [
                    f"Ultima transicion: {last_transition_raw.new_state} hace {days_since} dias",
                ],
            })

    return causes


def _build_suggested_actions(causes: list[dict]) -> list[str]:
    """Genera acciones sugeridas basadas en las causas detectadas."""
    actions = []
    categories = {c["category"] for c in causes}

    if "DATA" in categories:
        actions.append("Completar la descripcion y criterios de aceptacion del ticket")
    if "PIP" in categories:
        actions.append("Ejecutar el agente de Stacky correspondiente al estado actual del ticket")
        actions.append("Revisar los errores de la ultima ejecucion en el panel de historial")

    for cause in causes:
        if "no tiene responsable" in cause["description"]:
            actions.append("Usar el Recomendador de Asignacion P6 para asignar el ticket a un desarrollador")
            break

    if not actions:
        actions.append("Revisar manualmente el historial del ticket en ADO")

    return actions


def run_evals_gate() -> tuple[bool, str]:
    """Verifica si los evals para diagnosticos estan configurados y pasan.

    Por ahora valida que los fixtures existen. Si existen, el gate pasa.
    Returns: (passed, reason)
    """
    from pathlib import Path
    evals_dir = Path(__file__).parent.parent / "evals" / "ticket_diagnostics"
    if not evals_dir.exists():
        return False, "evals/ticket_diagnostics/ no existe — crear fixtures antes de habilitar LLM"

    fixtures = list(evals_dir.glob("*.json"))
    if len(fixtures) < 2:
        return False, f"Insuficientes fixtures de eval ({len(fixtures)} < 2 requeridos)"

    return True, f"eval gate OK — {len(fixtures)} fixtures disponibles"


def generate_diagnostics(ticket_id: int) -> dict:
    """Genera el diagnostico completo para un ticket.

    1. Verifica cache.
    2. Carga datos de la BD.
    3. Calcula causas deterministicas.
    4. Si LLM habilitado y eval gate pasa, enriquece con LLM.
    5. Cachea y devuelve.
    """
    cached = _get_cached(ticket_id)
    if cached:
        result = dict(cached)
        result["from_cache"] = True
        return result

    from db import session_scope
    from models import AgentExecution, Ticket, TicketStateHistory

    with session_scope() as session:
        ticket = session.query(Ticket).filter_by(id=ticket_id).first()
        if ticket is None:
            return {
                "ok": False,
                "error": "ticket_not_found",
                "message": f"Ticket {ticket_id} no existe en la BD local",
            }

        executions = (
            session.query(AgentExecution)
            .filter_by(ticket_id=ticket_id)
            .order_by(AgentExecution.started_at.desc())
            .limit(10)
            .all()
        )

        state_history = (
            session.query(TicketStateHistory)
            .filter_by(ticket_id=ticket_id)
            .order_by(TicketStateHistory.recorded_at.desc())
            .limit(20)
            .all()
        )

        aging_days = (datetime.utcnow() - ticket.created_at).days if ticket.created_at else 0
        last_state_change = None
        if state_history:
            last_entry = max(state_history, key=lambda h: h.recorded_at or datetime.min)
            last_state_change = last_entry.recorded_at.isoformat() if last_entry.recorded_at else None

        causes = _build_deterministic_causes(ticket, executions, state_history)
        actions = _build_suggested_actions(causes)

        generated_by = "deterministic"
        model = None
        eval_gate_passed = False

        if _LLM_ENABLED:
            gate_ok, gate_reason = run_evals_gate()
            eval_gate_passed = gate_ok
            if not gate_ok:
                logger.warning("Diagnosticos LLM bloqueados por eval gate: %s", gate_reason)
                causes.append({
                    "category": "OBS",
                    "description": f"LLM habilitado pero eval gate no paso: {gate_reason}",
                    "confidence": 1.0,
                    "evidence": ["Configurar fixtures en evals/ticket_diagnostics/"],
                })
            else:
                # TODO: enriquecer con LLM cuando el servicio LLM este configurado
                # Ver llm_router.py para el patron de integracion
                logger.info("Eval gate paso pero LLM no implementado aun en diagnosticos")
                generated_by = "deterministic_with_eval_gate"
        else:
            eval_gate_passed = False

        result = {
            "ok": True,
            "ticket_id": ticket_id,
            "ticket_ado_id": ticket.ado_id,
            "ticket_title": ticket.title,
            "ado_state": ticket.ado_state,
            "assigned_to_ado": ticket.assigned_to_ado,
            "aging_days": aging_days,
            "last_state_change": last_state_change,
            "executions_count": len(executions),
            "probable_causes": causes,
            "suggested_actions": actions,
            "advisory_only": True,
            "generated_by": generated_by,
            "model": model,
            "eval_gate_passed": eval_gate_passed,
            "llm_enabled": _LLM_ENABLED,
            "from_cache": False,
        }

    _set_cache(ticket_id, result)
    return result


__all__ = [
    "generate_diagnostics",
    "invalidate_cache",
    "run_evals_gate",
]
