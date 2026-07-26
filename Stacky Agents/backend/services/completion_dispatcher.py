"""Plan 208 F0 — Dispatcher de completación (punto de integración runtime-agnóstico).

Único punto por el que pasan R2 (auto-sync) y R3 (matriz de estados). El post-hook
que se registra en `ticket_status.register_post_hook` SOLO encola (O(1)) y retorna:
todo el trabajo real (red, DB) corre en un daemon de fondo, para que una falla o
lentitud jamás demore la completación ni la respuesta HTTP.

Paridad de los 3 runtimes por construcción: Codex CLI, Claude Code CLI y el runtime
in-proc/Copilot llaman todos `ticket_status.on_execution_end`, que dispara los
post-hooks.
"""
from __future__ import annotations

import json
import logging
import queue
import threading

logger = logging.getLogger("stacky_agents.completion_dispatcher")

# Evento mínimo (el post-hook lo arma O(1), sin tocar DB):
#   {"ticket_id": int, "execution_id": int|None, "final_status": str, "agent_type": str|None}
_Q: "queue.Queue[dict]" = queue.Queue(maxsize=10000)
_started = False
_lock = threading.Lock()

_LOG_SOURCE = "completion_dispatcher"


def enqueue_completion(*, ticket_id, execution_id, final_status, agent_type=None) -> None:
    """O(1), nunca lanza, nunca bloquea. Se llama desde el post-hook."""
    try:
        # Gate hot: si ambas mitades están off, ni encolar.
        from services.completion_state import matrix_enabled
        from services.completion_sync import sync_on_completion_enabled

        if not (matrix_enabled() or sync_on_completion_enabled()):
            return
        _Q.put_nowait(
            {
                "ticket_id": ticket_id,
                "execution_id": execution_id,
                "final_status": final_status,
                "agent_type": agent_type,
            }
        )
    except queue.Full:
        logger.warning("completion_dispatcher: cola llena, evento descartado (best-effort)")
    except Exception:  # noqa: BLE001
        logger.debug("enqueue_completion falló (no crítico)", exc_info=True)


def _post_hook(*, ticket_id, execution_id, final_status, agent_type=None, error=None, **kwargs) -> None:
    enqueue_completion(
        ticket_id=ticket_id,
        execution_id=execution_id,
        final_status=final_status,
        agent_type=agent_type,
    )


def register(register_fn) -> None:
    """Espeja incident_autopublish.register: register_fn == ticket_status.register_post_hook."""
    register_fn(_post_hook)


def emit_completion_log(
    *,
    action: str,
    level: str = "INFO",
    ticket_id=None,
    execution_id=None,
    context: dict | None = None,
    tags: list | None = None,
) -> None:
    """Plan 208 F6 — traza auditable en SystemLog. Best-effort: nunca lanza.

    Espeja `agent_completion._emit_system_log` (mismo modelo/serialización) sin
    importar ese módulo, para no acoplar el daemon al gateway HTTP.
    """
    try:
        from db import session_scope
        from models import SystemLog

        row = SystemLog(
            level=level,
            source=_LOG_SOURCE,
            action=action,
            ticket_id=ticket_id,
            execution_id=execution_id,
            context_json=json.dumps(context or {}, ensure_ascii=False, default=str),
            tags_json=json.dumps(tags or ["plan208"], ensure_ascii=False),
        )
        with session_scope() as s:
            s.add(row)
    except Exception:  # noqa: BLE001
        logger.debug("emit_completion_log falló (no crítico)", exc_info=True)


def _drain_loop() -> None:
    from services.completion_state import maybe_apply_state_transition
    from services.completion_sync import (
        coalesce_window_sec,
        flush_pending_syncs,
        maybe_coalesced_sync,
    )

    while True:
        try:
            try:
                ev = _Q.get(timeout=coalesce_window_sec())
            except queue.Empty:
                flush_pending_syncs()  # vencer ventana de coalescing sin segundo hilo
                continue
            # Orden: R3 (transiciona ADO) ANTES que R2 (pull ADO->local). C7: esto solo
            # optimiza el caso de sync INMEDIATO; bajo coalescing el sync puede diferirse
            # a flush_pending_syncs, y la convergencia es EVENTUAL igual (el próximo pull
            # captura el System.State que R3 escribió).
            maybe_apply_state_transition(ev)
            maybe_coalesced_sync(ev)
        except Exception:  # noqa: BLE001
            logger.debug("completion_dispatcher drain: iteración falló (no crítico)", exc_info=True)


def start(logger_=None) -> None:
    """Arranca el daemon una sola vez. Idempotente. Se llama en create_app.

    Arranca SIEMPRE (barato: bloquea en Queue.get), así ambas flags son hot
    (sin restart_required). Con ambas off, `enqueue_completion` ni siquiera encola.
    """
    global _started
    with _lock:
        if _started:
            return
        t = threading.Thread(target=_drain_loop, name="completion-dispatcher", daemon=True)
        t.start()
        _started = True
        (logger_ or logger).debug("completion_dispatcher: daemon arrancado")
