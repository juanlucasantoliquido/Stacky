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
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable

logger = logging.getLogger("stacky.agent_queue")


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

    def __init__(self, slots_pm: int = 1, slots_dev: int = 1, slots_tester: int = 1,
                 state_path: str = None, zombie_sweep_interval: float = 60.0,
                 max_zombie_retries: int = 3):
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
        self._stats     = {
            "submitted": 0, "completed": 0, "failed": 0,
            "zombies_reaped": 0, "zombie_dead_letters": 0,
        }

        self._state_path         = state_path
        self._max_zombie_retries = max_zombie_retries
        self._sweep_interval     = zombie_sweep_interval
        self._zombie_retries: dict[str, int] = {}

        for stage in ("pm", "dev", "tester"):
            t = threading.Thread(
                target=self._worker, args=(stage,),
                daemon=True, name=f"aq-worker-{stage}"
            )
            t.start()

        self._sweeper_thread = threading.Thread(
            target=self._zombie_sweeper_loop, daemon=True, name="aq-zombie-sweeper"
        )
        self._sweeper_thread.start()

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
                    # Reset zombie retry counter on clean completion
                    self._zombie_retries.pop(item.ticket_id, None)
                    self._cond.notify_all()

    # ── Zombie sweeper ────────────────────────────────────────────────────
    # Libera slots ocupados por tickets cuyo proceso invocador murió o cuyo
    # TTL expiró. Evita que la cola se atasque indefinidamente. Deja el ticket
    # en `error_<stage>` para que el daemon lo re-procese.

    def _zombie_sweeper_loop(self) -> None:
        while self._running:
            try:
                # Dormir en pedazos para responder rápido a shutdown
                slept = 0.0
                while slept < self._sweep_interval and self._running:
                    time.sleep(1.0)
                    slept += 1.0
                if not self._running:
                    break
                self.sweep_zombies()
            except Exception as e:
                logger.error("[QUEUE] Error en zombie sweeper: %s", e)

    def sweep_zombies(self) -> list[tuple[str, str]]:
        """
        Escanea `_active` y libera slots ocupados por procesos muertos o con TTL vencido.
        Devuelve la lista de `(stage, ticket_id)` reaped — expuesto para tests.
        """
        if not self._state_path:
            return []

        try:
            from pipeline_state import load_state, save_state, is_invoke_still_valid, mark_error
        except ImportError:
            logger.warning("[QUEUE] pipeline_state no importable — sweeper deshabilitado")
            return []

        try:
            state = load_state(self._state_path)
        except Exception as e:
            logger.warning("[QUEUE] sweeper no pudo cargar state: %s", e)
            return []

        # A4: heartbeat stale threshold — si {STAGE}_HEARTBEAT.txt no se actualiza
        # en este tiempo, consideramos el ticket zombie aun con PID vivo.
        HEARTBEAT_STALE_SEC = 5 * 60
        now_ts              = time.time()

        candidates: list[tuple[str, str, str]] = []  # (stage, ticket_id, reason)
        with self._lock:
            for stage, active_list in self._active.items():
                for ticket_id in list(active_list):
                    entry = state.get("tickets", {}).get(ticket_id, {})
                    if not is_invoke_still_valid(entry):
                        candidates.append((stage, ticket_id,
                                           "proceso invocador muerto o TTL expirado"))
                        continue
                    # A4: chequeo de heartbeat
                    folder = entry.get("folder")
                    if folder and os.path.isdir(folder):
                        hb = os.path.join(folder, f"{stage.upper()}_HEARTBEAT.txt")
                        if os.path.exists(hb):
                            try:
                                age = now_ts - os.path.getmtime(hb)
                                if age > HEARTBEAT_STALE_SEC:
                                    candidates.append((
                                        stage, ticket_id,
                                        f"heartbeat stale ({int(age)}s sin actualizar)"
                                    ))
                            except OSError:
                                pass

        if not candidates:
            return []

        for stage, ticket_id, reason_detail in candidates:
            try:
                mark_error(state, ticket_id, stage, f"Zombie reaped: {reason_detail}")
            except Exception as e:
                logger.warning("[QUEUE] mark_error falló para %s/%s: %s",
                               ticket_id, stage, e)
        try:
            save_state(self._state_path, state)
        except Exception as e:
            logger.warning("[QUEUE] save_state falló en sweeper: %s", e)

        reaped: list[tuple[str, str]] = []
        with self._cond:
            for stage, ticket_id, _reason in candidates:
                try:
                    self._active[stage].remove(ticket_id)
                except ValueError:
                    continue
                self._stats["zombies_reaped"] += 1
                retries = self._zombie_retries.get(ticket_id, 0) + 1
                self._zombie_retries[ticket_id] = retries
                reaped.append((stage, ticket_id))

                if retries > self._max_zombie_retries:
                    self._stats["zombie_dead_letters"] += 1
                    logger.error(
                        "[QUEUE] DEAD LETTER: %s superó %d reintentos de zombie — "
                        "requiere intervención manual",
                        ticket_id, self._max_zombie_retries,
                    )
                    self._notify_zombie(ticket_id, stage, retries, dead_letter=True)
                else:
                    logger.warning(
                        "[QUEUE] ZOMBIE reaped: %s/%s (retry %d/%d) — slot liberado, "
                        "estado=error_%s (daemon re-procesará)",
                        ticket_id, stage, retries, self._max_zombie_retries, stage,
                    )
                    self._notify_zombie(ticket_id, stage, retries, dead_letter=False)
            self._cond.notify_all()
        return reaped

    def _notify_zombie(self, ticket_id: str, stage: str, retries: int,
                       dead_letter: bool) -> None:
        try:
            from notifier import notify
        except Exception:
            return
        if dead_letter:
            notify(
                f"🪦 Ticket #{ticket_id} DEAD LETTER",
                f"Stage {stage} superó {self._max_zombie_retries} reintentos "
                f"por zombie. Requiere intervención manual.",
                level="error", ticket_id=ticket_id,
            )
        else:
            notify(
                f"⚠️ Zombie reaped #{ticket_id}",
                f"Stage {stage} liberado (retry {retries}/"
                f"{self._max_zombie_retries}). Estado=error_{stage}, "
                f"daemon re-procesará.",
                level="warning", ticket_id=ticket_id,
            )


# ── Singleton global ──────────────────────────────────────────────────────────

_queue_instance: AgentQueue | None = None
_queue_lock = threading.Lock()


def get_agent_queue(slots_pm: int = 1, slots_dev: int = 1,
                    slots_tester: int = 1, state_path: str = None,
                    zombie_sweep_interval: float = 60.0,
                    max_zombie_retries: int = 3) -> AgentQueue:
    """Retorna (y cachea) la instancia singleton de AgentQueue."""
    global _queue_instance
    with _queue_lock:
        if _queue_instance is None:
            _queue_instance = AgentQueue(
                slots_pm=slots_pm, slots_dev=slots_dev, slots_tester=slots_tester,
                state_path=state_path, zombie_sweep_interval=zombie_sweep_interval,
                max_zombie_retries=max_zombie_retries,
            )
        elif state_path and not _queue_instance._state_path:
            _queue_instance._state_path = state_path
        return _queue_instance
