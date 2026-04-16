"""
agent_queue.py — M-06: Procesamiento Paralelo por Etapas (Pipeline Lanes).

Implementa un sistema de colas con slots limitados por tipo de agente:
  - Un slot por tipo de agente (PM, DEV, QA) por defecto
  - Múltiples tickets pueden estar en distintas etapas simultáneamente
  - Prioridad dinámica: tickets escalados pasan al frente
  - Backpressure: si todos los slots están ocupados, encola y espera

Ejemplo con 2 lanes por agente:
  Slot PM-1: Ticket #100 (en análisis)
  Slot PM-2: Ticket #101 (en análisis)
  Slot DEV-1: Ticket #98 (en desarrollo)
  Slot QA-1: Ticket #97 (en testing)

Uso:
    from agent_queue import AgentQueue
    aq = AgentQueue(slots_pm=1, slots_dev=2, slots_tester=1)
    aq.submit(ticket_id, stage, callback)
    aq.get_status()
"""

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable

logger = logging.getLogger("mantis.agent_queue")


@dataclass(order=True)
class QueueItem:
    priority:   int                    # menor = más urgente
    ticket_id:  str = field(compare=False)
    stage:      str = field(compare=False)
    callback:   Callable = field(compare=False)
    submitted_at: str = field(compare=False, default_factory=lambda: datetime.now().isoformat())
    retry_num:  int = field(compare=False, default=0)


class AgentQueue:
    """
    Cola de trabajo con slots limitados por tipo de agente.
    Permite múltiples tickets en distintas etapas simultáneamente.
    """

    def __init__(self, slots_pm: int = 1, slots_dev: int = 1, slots_tester: int = 1):
        self._slots = {
            "pm":     slots_pm,
            "dev":    slots_dev,
            "tester": slots_tester,
        }
        self._active:   dict[str, list[str]] = {"pm": [], "dev": [], "tester": []}
        self._queue:    dict[str, list[QueueItem]] = {"pm": [], "dev": [], "tester": []}
        self._lock      = threading.RLock()
        self._cond      = threading.Condition(self._lock)
        self._running   = True
        self._stats     = {"submitted": 0, "completed": 0, "failed": 0}

        # Worker threads por etapa
        for stage in ("pm", "dev", "tester"):
            t = threading.Thread(
                target=self._worker, args=(stage,),
                daemon=True, name=f"aq-worker-{stage}"
            )
            t.start()

    # ── API pública ───────────────────────────────────────────────────────

    def submit(self, ticket_id: str, stage: str, callback: Callable,
               priority: int = 5, retry_num: int = 0) -> bool:
        """
        Encola un ticket para ejecutarse en la etapa dada.
        callback: función sin argumentos que invoca al agente.
        priority: 1=máxima, 10=mínima.
        Retorna False si el stage no es válido.
        """
        if stage not in self._slots:
            return False

        item = QueueItem(priority=priority, ticket_id=ticket_id,
                         stage=stage, callback=callback, retry_num=retry_num)
        with self._cond:
            # Insertar en orden de prioridad
            queue = self._queue[stage]
            import bisect
            bisect.insort(queue, item)
            self._stats["submitted"] += 1
            self._cond.notify_all()

        logger.debug("[QUEUE] Encolado %s/%s (prioridad=%d, pos=%d)",
                     ticket_id, stage, priority, len(queue))
        return True

    def boost_priority(self, ticket_id: str, new_priority: int = 1) -> bool:
        """Sube la prioridad de un ticket en la cola."""
        with self._cond:
            for stage, queue in self._queue.items():
                for i, item in enumerate(queue):
                    if item.ticket_id == ticket_id:
                        queue.pop(i)
                        item.priority = new_priority
                        import bisect
                        bisect.insort(queue, item)
                        self._cond.notify_all()
                        logger.info("[QUEUE] %s boosted a prioridad %d en %s",
                                    ticket_id, new_priority, stage)
                        return True
        return False

    def get_status(self) -> dict:
        """Retorna el estado actual de la cola."""
        with self._lock:
            return {
                "active":  {s: list(ids) for s, ids in self._active.items()},
                "queued":  {s: [i.ticket_id for i in q]
                            for s, q in self._queue.items()},
                "slots":   dict(self._slots),
                "stats":   dict(self._stats),
            }

    def is_busy(self, stage: str) -> bool:
        """Retorna True si todos los slots de la etapa están ocupados."""
        with self._lock:
            return len(self._active.get(stage, [])) >= self._slots.get(stage, 1)

    def set_slots(self, stage: str, n: int) -> None:
        """Actualiza el número de slots disponibles para una etapa."""
        with self._cond:
            self._slots[stage] = max(1, n)
            self._cond.notify_all()

    def shutdown(self) -> None:
        """Detiene los workers de la cola."""
        with self._cond:
            self._running = False
            self._cond.notify_all()

    # ── Worker ────────────────────────────────────────────────────────────

    def _worker(self, stage: str) -> None:
        """Worker loop para una etapa específica."""
        while True:
            with self._cond:
                while self._running and (
                    not self._queue[stage] or
                    len(self._active[stage]) >= self._slots[stage]
                ):
                    self._cond.wait(timeout=5.0)

                if not self._running:
                    break

                if not self._queue[stage]:
                    continue
                if len(self._active[stage]) >= self._slots[stage]:
                    continue

                item = self._queue[stage].pop(0)
                self._active[stage].append(item.ticket_id)

            # Ejecutar fuera del lock
            wait_sec = (datetime.now() - datetime.fromisoformat(
                item.submitted_at)).total_seconds()
            logger.info("[QUEUE] Ejecutando %s/%s (esperó %.0fs)",
                        item.ticket_id, stage, wait_sec)

            try:
                item.callback()
                with self._lock:
                    self._stats["completed"] += 1
            except Exception as e:
                logger.error("[QUEUE] Error ejecutando %s/%s: %s",
                             item.ticket_id, stage, e)
                with self._lock:
                    self._stats["failed"] += 1
            finally:
                with self._cond:
                    try:
                        self._active[stage].remove(item.ticket_id)
                    except ValueError:
                        pass
                    self._cond.notify_all()


# ── Singleton global ──────────────────────────────────────────────────────────

_queue_instance: AgentQueue | None = None
_queue_lock = threading.Lock()


def get_agent_queue(slots_pm: int = 1, slots_dev: int = 1,
                    slots_tester: int = 1) -> AgentQueue:
    """Retorna (y cachea) la instancia singleton de AgentQueue."""
    global _queue_instance
    with _queue_lock:
        if _queue_instance is None:
            _queue_instance = AgentQueue(
                slots_pm=slots_pm, slots_dev=slots_dev, slots_tester=slots_tester
            )
        return _queue_instance
