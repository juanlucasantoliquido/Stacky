"""
federated_knowledge_bus.py — Knowledge pool compartido entre todos los proyectos.

Un bus que agrega pitfalls y soluciones de TODOS los proyectos Stacky.
Un bug resuelto en RSPACIFICO hoy evita el mismo bug en RSTANDARD mañana.

Uso:
    from federated_knowledge_bus import FederatedKnowledgeBus, KnowledgeEvent
    bus = FederatedKnowledgeBus()
    bus.publish("RSPACIFICO", KnowledgeEvent(type="pitfall", content="...", file_type="dalc"))
    results = bus.query(file_type="dalc", query_text="NULL check")
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.knowledge_bus")

BUS_FILE = Path(__file__).parent / "data" / "knowledge_bus.json"
MAX_BUS_ENTRIES = 5000


@dataclass
class KnowledgeEvent:
    type: str  # "pitfall", "solution", "pattern"
    content: str
    file_type: str  # "dalc", "aspx", "sql", "config"
    tags: list[str] = field(default_factory=list)
    ticket_id: str = ""


class FederatedKnowledgeBus:
    def __init__(self, bus_file: Optional[Path] = None):
        self._bus_file = bus_file or BUS_FILE

    def publish(self, project: str, event: KnowledgeEvent):
        entry = {
            "project": project,
            "event_type": event.type,
            "content": event.content,
            "file_type": event.file_type,
            "tags": event.tags,
            "ticket_id": event.ticket_id,
            "timestamp": datetime.now().isoformat(),
        }
        bus = self._load()
        bus.append(entry)
        if len(bus) > MAX_BUS_ENTRIES:
            bus = bus[-MAX_BUS_ENTRIES:]
        self._save(bus)
        logger.info("[KnowledgeBus] Published %s from %s: %s",
                     event.type, project, event.content[:80])

    def query(
        self,
        file_type: str,
        query_text: str = "",
        exclude_project: Optional[str] = None,
        max_results: int = 10,
    ) -> list[dict]:
        bus = self._load()
        results = []
        for e in reversed(bus):
            if e.get("file_type") != file_type:
                continue
            if exclude_project and e.get("project") == exclude_project:
                continue
            if query_text and not self._is_relevant(query_text, e.get("content", "")):
                continue
            results.append(e)
            if len(results) >= max_results:
                break
        return results

    def get_all_for_project(self, project: str) -> list[dict]:
        bus = self._load()
        return [e for e in bus if e.get("project") == project]

    def get_cross_project_pitfalls(self, file_type: str, current_project: str) -> list[str]:
        entries = self.query(file_type=file_type, exclude_project=current_project)
        return [
            f"[{e['project']}] {e['content']}"
            for e in entries if e.get("event_type") == "pitfall"
        ]

    def _is_relevant(self, query: str, content: str) -> bool:
        query_words = set(query.lower().split())
        content_lower = content.lower()
        return any(w in content_lower for w in query_words if len(w) > 3)

    def _load(self) -> list[dict]:
        if self._bus_file.exists():
            try:
                return json.loads(self._bus_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        return []

    def _save(self, bus: list[dict]):
        self._bus_file.parent.mkdir(parents=True, exist_ok=True)
        self._bus_file.write_text(
            json.dumps(bus, indent=2, ensure_ascii=False), encoding="utf-8"
        )
