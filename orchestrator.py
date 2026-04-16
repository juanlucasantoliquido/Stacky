"""
orchestrator.py — X-02: Modo Multi-Tenant: Multiples Proyectos y Equipos en Paralelo.

Orquestador central que gestiona multiples proyectos simultaneamente
con recursos compartidos: pool de agentes, cola global con priorizacion
cross-proyecto y dashboard unificado.

Arquitectura:
  STACKY ORCHESTRATOR
    Proyecto RIPLEY    -> daemon_ripley (3 tickets activos)
    Proyecto RSMOBILE  -> daemon_rsmobile (1 ticket activo)
    Pool de agentes compartido: 3 slots PM, 2 slots DEV, 2 slots QA
    Cola global con priorizacion cross-proyecto

Uso:
    python orchestrator.py --projects RIPLEY,RSMOBILENET --interval 10
    python orchestrator.py --list-projects
"""

import argparse
import json
import logging
import signal
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger("mantis.orchestrator")

BASE_DIR = Path(__file__).parent

# Pool de slots por agente (compartido entre proyectos)
DEFAULT_AGENT_SLOTS = {
    "pm":     3,
    "dev":    2,
    "tester": 2,
    "doc":    1,   # Documentador — un slot único (escribe en KNOWLEDGE_BASE.md compartido)
}


class AgentPool:
    """
    Pool de slots de agentes compartido entre todos los proyectos.
    Un slot por agente garantiza que no se invoquen simultaneamente
    dos instancias del mismo agente en el mismo VS Code.
    """

    def __init__(self, slots_config: dict = None):
        self._slots   = slots_config or DEFAULT_AGENT_SLOTS
        self._in_use  = {agent: 0 for agent in self._slots}
        self._lock    = threading.Lock()
        self._waiters: dict[str, list] = {agent: [] for agent in self._slots}

    def acquire(self, agent: str, ticket_id: str = "", timeout: float = 300) -> bool:
        """
        Intenta adquirir un slot para el agente. Espera hasta timeout segundos.
        Retorna True si se adquirio, False si no habia slots disponibles en timeout.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._lock:
                if self._in_use.get(agent, 0) < self._slots.get(agent, 1):
                    self._in_use[agent] = self._in_use.get(agent, 0) + 1
                    logger.debug("[X-02] Slot adquirido: %s para %s (%d/%d)",
                                 agent, ticket_id, self._in_use[agent], self._slots[agent])
                    return True
            time.sleep(5)
        logger.warning("[X-02] Timeout esperando slot de %s para %s", agent, ticket_id)
        return False

    def release(self, agent: str, ticket_id: str = "") -> None:
        with self._lock:
            if self._in_use.get(agent, 0) > 0:
                self._in_use[agent] -= 1
                logger.debug("[X-02] Slot liberado: %s para %s (%d/%d)",
                             agent, ticket_id, self._in_use[agent], self._slots[agent])

    def available(self, agent: str) -> int:
        with self._lock:
            return self._slots.get(agent, 1) - self._in_use.get(agent, 0)

    def status(self) -> dict:
        with self._lock:
            return {
                agent: {
                    "total":     self._slots[agent],
                    "in_use":    self._in_use.get(agent, 0),
                    "available": self._slots[agent] - self._in_use.get(agent, 0),
                }
                for agent in self._slots
            }


class GlobalQueue:
    """
    Cola global de tickets ordenada por priority_score cross-proyecto.
    """

    def __init__(self):
        self._items = []
        self._lock  = threading.Lock()

    def enqueue(self, project: str, ticket_id: str, priority: float,
                stage: str = "pm") -> None:
        with self._lock:
            # Deduplicar
            self._items = [
                i for i in self._items
                if not (i["project"] == project and i["ticket_id"] == ticket_id)
            ]
            self._items.append({
                "project":    project,
                "ticket_id":  ticket_id,
                "priority":   priority,
                "stage":      stage,
                "enqueued_at": datetime.now().isoformat(),
            })
            self._items.sort(key=lambda x: x["priority"], reverse=True)

    def dequeue_for_agent(self, agent: str) -> Optional[dict]:
        """
        Retorna y remueve el ticket de mayor prioridad que necesita este agente.
        """
        with self._lock:
            for i, item in enumerate(self._items):
                if item["stage"] == agent or (
                    agent == "pm" and item["stage"] == "pm"
                ) or (
                    agent == "dev" and item["stage"] == "dev"
                ) or (
                    agent == "tester" and item["stage"] == "tester"
                ):
                    return self._items.pop(i)
        return None

    def size(self) -> int:
        with self._lock:
            return len(self._items)

    def peek_top(self, n: int = 5) -> list:
        with self._lock:
            return list(self._items[:n])

    def clear_project(self, project: str) -> int:
        with self._lock:
            before = len(self._items)
            self._items = [i for i in self._items if i["project"] != project]
            return before - len(self._items)


class ProjectWorker:
    """
    Wrapper que gestiona el daemon de un proyecto especifico
    dentro del orquestador multi-tenant.
    """

    def __init__(self, project_name: str, agent_pool: AgentPool,
                 global_queue: GlobalQueue):
        self.project_name = project_name
        self._pool        = agent_pool
        self._queue       = global_queue
        self._config      = self._load_config()
        self._active      = False
        self._thread: Optional[threading.Thread] = None
        self._tickets_processed = 0
        self._tickets_active    = 0

    def start(self) -> None:
        self._active = True
        self._thread = threading.Thread(
            target=self._worker_loop,
            daemon=True,
            name=f"worker-{self.project_name}",
        )
        self._thread.start()
        logger.info("[X-02] Worker iniciado: %s", self.project_name)

    def stop(self) -> None:
        self._active = False

    def get_status(self) -> dict:
        return {
            "project":            self.project_name,
            "active":             self._active,
            "tickets_processed":  self._tickets_processed,
            "tickets_active":     self._tickets_active,
            "thread_alive":       self._thread.is_alive() if self._thread else False,
        }

    def _worker_loop(self) -> None:
        """Loop del worker: detecta tickets nuevos y los encola en la cola global."""
        interval = self._config.get("scrape_interval_minutes", 15) * 60

        while self._active:
            try:
                self._sync_tickets_to_global_queue()
            except Exception as exc:
                logger.error("[X-02] Error en worker %s: %s", self.project_name, exc)

            time.sleep(interval)

    def _sync_tickets_to_global_queue(self) -> None:
        """Lee el estado del pipeline y sincroniza tickets a la cola global."""
        state_path = BASE_DIR / "pipeline" / "state.json"
        if not state_path.exists():
            return

        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except Exception:
            return

        self._tickets_active = 0
        for ticket_id, info in state.items():
            stage = info.get("stage", "")
            if "completado" in stage or "error" in stage:
                continue

            self._tickets_active += 1
            # Mapear etapa a agente necesario
            next_agent = None
            if stage in ("nueva", "asignada", "pendiente_pm"):
                next_agent = "pm"
            elif stage == "pm_completado":
                next_agent = "dev"
            elif stage == "dev_completado":
                next_agent = "tester"

            if next_agent:
                priority = float(info.get("priority_score", 3))
                self._queue.enqueue(self.project_name, ticket_id, priority, next_agent)

    def _load_config(self) -> dict:
        cfg = BASE_DIR / "projects" / self.project_name / "config.json"
        if cfg.exists():
            try:
                return json.loads(cfg.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}


class Orchestrator:
    """
    Orquestador central multi-tenant para Stacky.
    """

    def __init__(self, projects: list, agent_slots: dict = None):
        self.projects    = projects
        self._pool       = AgentPool(agent_slots or DEFAULT_AGENT_SLOTS)
        self._queue      = GlobalQueue()
        self._workers: dict[str, ProjectWorker] = {}
        self._stop_event = threading.Event()

        for project in projects:
            self._workers[project] = ProjectWorker(project, self._pool, self._queue)

    def start(self) -> None:
        logger.info("[X-02] Orquestador iniciando con proyectos: %s", self.projects)
        for worker in self._workers.values():
            worker.start()

        # Thread de despacho
        self._dispatch_thread = threading.Thread(
            target=self._dispatch_loop, daemon=True, name="orchestrator-dispatch"
        )
        self._dispatch_thread.start()

        # Thread de metricas
        self._metrics_thread = threading.Thread(
            target=self._metrics_loop, daemon=True, name="orchestrator-metrics"
        )
        self._metrics_thread.start()

        logger.info("[X-02] Orquestador activo. Cola global: %d items", self._queue.size())

    def stop(self) -> None:
        logger.info("[X-02] Deteniendo orquestador...")
        self._stop_event.set()
        for worker in self._workers.values():
            worker.stop()

    def get_status(self) -> dict:
        return {
            "projects":    [w.get_status() for w in self._workers.values()],
            "agent_pool":  self._pool.status(),
            "queue_size":  self._queue.size(),
            "queue_top":   self._queue.peek_top(3),
            "checked_at":  datetime.now().isoformat(),
        }

    def _dispatch_loop(self) -> None:
        """
        Loop de despacho: toma items de la cola y los procesa
        cuando hay slots disponibles.
        """
        while not self._stop_event.is_set():
            for agent in ("pm", "dev", "tester"):
                if self._pool.available(agent) > 0:
                    item = self._queue.dequeue_for_agent(agent)
                    if item:
                        threading.Thread(
                            target=self._process_item,
                            args=(item, agent),
                            daemon=True,
                            name=f"dispatch-{item['ticket_id']}",
                        ).start()
            self._stop_event.wait(10)

    def _process_item(self, item: dict, agent: str) -> None:
        """Procesa un item de la cola usando el pool de agentes."""
        ticket_id = item["ticket_id"]
        project   = item["project"]

        if not self._pool.acquire(agent, ticket_id, timeout=60):
            # Volver a encolar si no se pudo adquirir slot
            self._queue.enqueue(project, ticket_id, item["priority"], agent)
            return

        try:
            logger.info("[X-02] Procesando %s/%s con agente %s", project, ticket_id, agent)
            # Aqui invocar el pipeline_runner del proyecto correspondiente
            # worker = self._workers.get(project)
            # if worker: worker.run_stage(ticket_id, agent)
            time.sleep(1)  # placeholder
            self._workers[project]._tickets_processed += 1
        except Exception as exc:
            logger.error("[X-02] Error procesando %s/%s: %s", project, ticket_id, exc)
        finally:
            self._pool.release(agent, ticket_id)

    def _metrics_loop(self) -> None:
        """Persiste metricas del orquestador cada 60s."""
        metrics_path = BASE_DIR / "orchestrator_metrics.json"
        while not self._stop_event.is_set():
            try:
                status = self.get_status()
                metrics_path.write_text(
                    json.dumps(status, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
            except Exception:
                pass
            self._stop_event.wait(60)


# ── Entry point ───────────────────────────────────────────────────────────────

def _discover_projects() -> list:
    """Descubre proyectos configurados en tools/mantis_scraper/projects/."""
    projects_dir = BASE_DIR / "projects"
    if not projects_dir.exists():
        return []
    return [
        d.name for d in projects_dir.iterdir()
        if d.is_dir() and (d / "config.json").exists()
    ]


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)-5s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    parser = argparse.ArgumentParser(description="Stacky Orchestrator — Multi-Tenant")
    parser.add_argument(
        "--projects", default="",
        help="Proyectos separados por coma (ej: RIPLEY,RSMOBILENET). "
             "Si se omite, descubre todos los proyectos configurados."
    )
    parser.add_argument("--list-projects", action="store_true")
    args = parser.parse_args()

    if args.list_projects:
        projects = _discover_projects()
        print("Proyectos configurados:")
        for p in projects:
            print(f"  - {p}")
        sys.exit(0)

    projects = [p.strip() for p in args.projects.split(",") if p.strip()]
    if not projects:
        projects = _discover_projects()

    if not projects:
        print("No se encontraron proyectos. Usar --projects RIPLEY,RSMOBILENET")
        sys.exit(1)

    orch = Orchestrator(projects)

    def _handle_signal(sig, frame):
        logger.info("Senal recibida — deteniendo orquestador...")
        orch.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    orch.start()

    print(f"Orquestador activo — proyectos: {projects}")
    print("Presionar Ctrl+C para detener.")

    while True:
        time.sleep(30)
        status = orch.get_status()
        queue_size = status["queue_size"]
        total_active = sum(w["tickets_active"] for w in status["projects"])
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Cola: {queue_size} | Activos: {total_active}")
