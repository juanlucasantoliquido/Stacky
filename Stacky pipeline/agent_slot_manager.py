"""
agent_slot_manager.py — Pipeline multi-proyecto paralelo con slots por agente.

Gestiona slots de ejecución por agente. Copilot solo soporta 1 invocación a la vez
por agente, pero permite paralelismo entre agentes distintos:
  Ticket A: [PM ejecutando]
  Ticket B: [DEV ejecutando en paralelo con PM de Ticket A]

Uso:
    from agent_slot_manager import AgentSlotManager
    mgr = AgentSlotManager()
    if mgr.acquire_slot("pm", "12345", "RIPLEY"):
        # run PM
        mgr.release_slot("pm", "12345")
"""

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.agent_slots")

STATE_FILE = Path(__file__).parent / "state" / "agent_slots.json"


@dataclass
class SlotInfo:
    """Information about an occupied slot."""
    agent: str
    ticket_id: str
    project: str
    acquired_at: float
    thread_id: int = 0


class AgentSlotManager:
    """
    Manages execution slots per agent type.
    Each agent type has a maximum of 1 concurrent execution.
    """

    MAX_CONCURRENT_PM = 1
    MAX_CONCURRENT_DEV = 1
    MAX_CONCURRENT_QA = 1

    # Maximum time a slot can be held (seconds) before auto-release
    SLOT_TIMEOUT = 3600  # 1 hour

    def __init__(self):
        self._lock = threading.Lock()
        self._slots: dict[str, list[SlotInfo]] = {
            "pm": [],
            "dev": [],
            "tester": [],
        }
        self._max_slots = {
            "pm": self.MAX_CONCURRENT_PM,
            "dev": self.MAX_CONCURRENT_DEV,
            "tester": self.MAX_CONCURRENT_QA,
        }
        self._queues: dict[str, list[dict]] = {
            "pm": [],
            "dev": [],
            "tester": [],
        }
        self._load_state()

    def acquire_slot(self, agent: str, ticket_id: str, project: str = "") -> bool:
        """
        Try to acquire a slot for an agent.
        Returns True if slot acquired, False if agent is busy.
        """
        with self._lock:
            self._cleanup_expired_slots()
            agent = agent.lower()
            max_slots = self._max_slots.get(agent, 1)
            current = self._slots.get(agent, [])

            if len(current) >= max_slots:
                # Add to queue
                self._queues.setdefault(agent, []).append({
                    "ticket_id": ticket_id,
                    "project": project,
                    "queued_at": time.time(),
                })
                logger.info("[Slots] %s busy — ticket %s queued (position %d)",
                             agent, ticket_id, len(self._queues[agent]))
                return False

            slot = SlotInfo(
                agent=agent,
                ticket_id=ticket_id,
                project=project,
                acquired_at=time.time(),
                thread_id=threading.current_thread().ident or 0,
            )
            current.append(slot)
            self._slots[agent] = current
            self._save_state()
            logger.info("[Slots] %s slot acquired for ticket %s (project: %s)",
                         agent, ticket_id, project)
            return True

    def release_slot(self, agent: str, ticket_id: str):
        """Release a slot when processing completes."""
        with self._lock:
            agent = agent.lower()
            current = self._slots.get(agent, [])
            self._slots[agent] = [
                s for s in current if s.ticket_id != ticket_id
            ]
            self._save_state()
            logger.info("[Slots] %s slot released for ticket %s", agent, ticket_id)

    def is_available(self, agent: str) -> bool:
        """Check if an agent has available slots."""
        with self._lock:
            self._cleanup_expired_slots()
            agent = agent.lower()
            max_slots = self._max_slots.get(agent, 1)
            current = len(self._slots.get(agent, []))
            return current < max_slots

    def get_queue_position(self, agent: str, ticket_id: str) -> int:
        """
        Get position in the queue for an agent. Returns 0 if not queued.
        Useful for ETAs in ADO comments.
        """
        with self._lock:
            queue = self._queues.get(agent.lower(), [])
            for i, item in enumerate(queue):
                if item["ticket_id"] == ticket_id:
                    return i + 1
            return 0

    def get_status(self) -> dict:
        """Get current status of all slots and queues."""
        with self._lock:
            status = {}
            for agent in self._max_slots:
                current = self._slots.get(agent, [])
                queue = self._queues.get(agent, [])
                status[agent] = {
                    "active": [
                        {
                            "ticket_id": s.ticket_id,
                            "project": s.project,
                            "duration_min": round((time.time() - s.acquired_at) / 60, 1),
                        }
                        for s in current
                    ],
                    "queue_size": len(queue),
                    "available": len(current) < self._max_slots.get(agent, 1),
                }
            return status

    def _cleanup_expired_slots(self):
        """Release slots that exceeded the timeout."""
        now = time.time()
        for agent in list(self._slots.keys()):
            expired = [
                s for s in self._slots[agent]
                if now - s.acquired_at > self.SLOT_TIMEOUT
            ]
            if expired:
                for s in expired:
                    logger.warning("[Slots] Auto-releasing expired slot: %s/%s (held %.0f min)",
                                    agent, s.ticket_id,
                                    (now - s.acquired_at) / 60)
                self._slots[agent] = [
                    s for s in self._slots[agent]
                    if now - s.acquired_at <= self.SLOT_TIMEOUT
                ]

    def _save_state(self):
        """Persist slot state to file."""
        try:
            STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            data = {}
            for agent, slots in self._slots.items():
                data[agent] = [
                    {
                        "ticket_id": s.ticket_id,
                        "project": s.project,
                        "acquired_at": s.acquired_at,
                    }
                    for s in slots
                ]
            STATE_FILE.write_text(
                json.dumps(data, indent=2), encoding="utf-8"
            )
        except Exception as e:
            logger.warning("Failed to save slot state: %s", e)

    def _load_state(self):
        """Load persisted slot state."""
        if not STATE_FILE.exists():
            return
        try:
            data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            for agent, slots in data.items():
                self._slots[agent] = [
                    SlotInfo(
                        agent=agent,
                        ticket_id=s["ticket_id"],
                        project=s.get("project", ""),
                        acquired_at=s.get("acquired_at", 0),
                    )
                    for s in slots
                ]
        except Exception as e:
            logger.warning("Failed to load slot state: %s", e)
