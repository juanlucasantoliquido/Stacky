"""Plan 208 F2 — Transición determinista de estado al completar un agente (R3).

Cuando un agente termina OK, Stacky transiciona el `System.State` del ticket al
estado que el operador configuró en la matriz (tipo de work item x tipo de agente).
Solo actúa si `resolve_task_state_plan(...).source == "matrix"`: sin cell
configurado el comportamiento es byte-idéntico al de hoy (backward-compat dura, P5).

Corre en el hilo del daemon del dispatcher: nunca bloquea ni demora la completación.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("stacky_agents.completion_state")

# C2 (set EXACTO, no "ajustar"): el final_status que llega al post-hook YA pasó por
# _coerce_terminal_status (ticket_status.py:268), que SOLO produce valores de
# status_vocabulary.VALID_TICKET_STATUSES = {idle, running, completed, error,
# cancelled, needs_review}. El ÚNICO terminal de éxito es "completed".
# PROHIBIDO incluir "needs_review" (exige revisión humana -> auto-transicionar
# violaría HITL) ni "error"/"cancelled" (fallo).
from services.status_vocabulary import TERMINAL_STATUSES  # noqa: E402  (ancla/invariante)

_OK_STATUSES = frozenset({"completed"})
assert _OK_STATUSES <= TERMINAL_STATUSES  # invariante: el éxito vive en el vocabulario canónico


def matrix_enabled() -> bool:
    # C1: leer la INSTANCIA config.config (NO el atributo de clase Config), igual que
    # todo el repo. Con la clase, monkeypatch.setattr(config.config, ..., False) del
    # test OFF-path no voltea el branch -> falso verde.
    try:
        from config import config as _cfg

        return bool(getattr(_cfg, "STACKY_ADO_STATE_MATRIX_ENABLED", False))
    except Exception:  # noqa: BLE001
        return False


def maybe_apply_state_transition(ev: dict) -> dict:
    """Aplica next_state_ok de la MATRIZ para (work_item_type x agent_type) si el
    operador lo configuró. Best-effort, idempotente, nunca lanza.

    Solo transiciona si: flag ON, final_status OK, y el plan resuelto viene de la
    matriz (`source == "matrix"`).
    """
    ctx: dict = {}
    try:
        if not matrix_enabled():
            return {"skipped": True, "reason": "flag_off"}
        final_status = (ev.get("final_status") or "").strip().lower()
        if final_status not in _OK_STATUSES:
            return {"skipped": True, "reason": "not_ok_status"}
        ticket_id = ev.get("ticket_id")

        from db import session_scope
        from models import Ticket

        with session_scope() as s:
            t = s.get(Ticket, ticket_id) if ticket_id else None
            if t is None:
                return {"skipped": True, "reason": "no_ticket"}
            ado_id = getattr(t, "ado_id", None)
            # C3: stacky_project_name (workspace Stacky) es la clave canónica para
            # profile/provider/breaker. NO caer a t.project (nombre del tracker):
            # divergiría de _startup_sync (app.py:196,203).
            stacky_project = getattr(t, "stacky_project_name", None)
            work_item_type = getattr(t, "work_item_type", None)

        agent_type = ev.get("agent_type")
        ctx = {
            "ado_id": ado_id,
            "project": stacky_project,
            "work_item_type": work_item_type,
            "agent_type": agent_type,
        }
        if not ado_id or not stacky_project:
            return _logged(ctx, ev, {"skipped": True, "reason": "no_ado_id_or_stacky_project"})

        from harness.task_states import (
            _safe_transition,
            applicable_states,
            resolve_task_state_plan,
        )
        from services.client_profile import load_effective_client_profile

        profile = load_effective_client_profile(stacky_project) or {}
        plan = resolve_task_state_plan(profile, agent_type, work_item_type)
        ctx["source"] = plan.source
        if plan.source != "matrix":
            # Backward-compat DURA: sin cell configurado, los paths de runner NO transicionan.
            return _logged(ctx, ev, {"skipped": True, "reason": "no_matrix_cell", "source": plan.source})
        target = plan.final_ok
        ctx["target"] = target
        if not target:
            return _logged(ctx, ev, {"skipped": True, "reason": "no_final_state"})
        # CENTINELA EN RUNTIME: jamás aplicar un estado fuera del conjunto cerrado.
        if target not in applicable_states(plan):
            return _logged(ctx, ev, {"skipped": True, "reason": "state_not_applicable"})

        from services.tracker_provider import get_tracker_provider

        try:
            provider = get_tracker_provider(stacky_project)
        except Exception:  # noqa: BLE001
            provider = None

        # P11 — guardia de origen (anti-pisada del humano).
        guard = _origin_guard(provider, ado_id, plan, profile, agent_type, target)
        if guard is not None:
            return _logged(ctx, ev, guard)

        result = _safe_transition(provider, ado_id, target, phase="final_matrix",
                                  legacy_client_fn=None)
        return _logged(ctx, ev, result)
    except Exception:  # noqa: BLE001
        logger.debug("maybe_apply_state_transition falló (no crítico)", exc_info=True)
        return {"skipped": True, "reason": "exception"}


def _origin_guard(provider, ado_id, plan, profile: dict, agent_type, target) -> "dict | None":
    """P11 — devuelve un dict-skip si el estado ACTUAL en el tracker cayó FUERA del
    flujo esperado del rol (el humano lo movió a propósito) ⇒ no pisar.

    Devuelve None para 'seguir' (deja que _safe_transition haga su idempotencia
    habitual). Best-effort: si no se puede leer el estado, NO bloquea.
    """
    try:
        if provider is None or not hasattr(provider, "get_item"):
            return None  # sin lectura -> no bloqueamos; _safe_transition decide
        from harness.task_states import _extract_current_state

        current = _extract_current_state(provider.get_item(str(ado_id)) or {})
        if not current:
            return None
        cl = current.strip().lower()
        if cl == (target or "").strip().lower():
            return None  # ya está en target: idempotencia la maneja _safe_transition
        # Estados de origen legítimos = los que el propio flujo produce/espera para el rol.
        machine = (profile.get("tracker_state_machine") or {}).get(agent_type) or {}
        expected = set()
        for k in ("in_progress", "blocked_state", "next_state_ok"):
            v = (machine.get(k) or "").strip()
            if v:
                expected.add(v.lower())
        for st in (machine.get("input_states") or []):
            if isinstance(st, str) and st.strip():
                expected.add(st.strip().lower())
        # El estado en-progreso RESUELTO (que puede venir del cell de la matriz, no
        # del nivel agente) también lo produce este mismo flujo: si no se incluyera,
        # un ticket que Stacky puso en el "in_progress" de la matriz se leería como
        # movido por el humano y jamás cerraría.
        if plan is not None and getattr(plan, "in_progress", None):
            expected.add(plan.in_progress.strip().lower())
        if expected and cl not in expected:
            return {"skipped": True, "reason": "human_moved_out_of_flow",
                    "current": current, "to": target}
        return None
    except Exception:  # noqa: BLE001
        logger.debug("_origin_guard falló (no crítico) -> no bloquea", exc_info=True)
        return None


def _logged(ctx: dict, ev: dict, result: dict) -> dict:
    """Plan 208 F6 — traza auditable de cada intento de transición. Nunca lanza.

    C6: `source` se toma del PLAN (="matrix"), nunca del dict de _safe_transition
    (que lo hardcodea a "config", task_states.py:136).
    """
    try:
        from services.completion_dispatcher import emit_completion_log

        ok = bool(result.get("ok"))
        error = result.get("ok") is False
        emit_completion_log(
            action="completion.matrix_transition",
            level="WARNING" if error else "INFO",
            ticket_id=ev.get("ticket_id"),
            execution_id=ev.get("execution_id"),
            context={
                **ctx,
                "result": "ok" if ok else ("error" if error else "skipped"),
                "reason": result.get("reason"),
                "to": result.get("to") or ctx.get("target"),
                "error": result.get("error"),
            },
            tags=["plan208", "matrix"],
        )
    except Exception:  # noqa: BLE001
        logger.debug("traza de matrix_transition falló (no crítico)", exc_info=True)
    return result
