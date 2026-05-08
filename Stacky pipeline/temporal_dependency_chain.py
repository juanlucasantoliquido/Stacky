"""
temporal_dependency_chain.py — Serializa tickets que tocan el mismo archivo.

Si ticket A modifica PagosDalc.cs y ticket B también lo necesita, B espera a A
y recibe los cambios de A en su contexto. Elimina conflictos de merge.

Uso:
    from temporal_dependency_chain import TemporalDependencyChain
    chain = TemporalDependencyChain()
    chain.register_file_lock("Batch/Negocio/PagosDalc.cs", "12345")
    blockers = chain.get_blocking_tickets(["Batch/Negocio/PagosDalc.cs"])
"""

import json
import logging
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.temporal_chain")

LOCKS_FILE = Path(__file__).parent / "state" / "file_locks.json"


class TemporalDependencyChain:
    LOCK_TIMEOUT = 7200  # 2 hours max lock

    def __init__(self):
        self._locks = self._load_locks()

    def register_file_lock(self, file_path: str, ticket_id: str):
        normalized = file_path.replace("\\", "/").lower()
        self._locks[normalized] = {
            "ticket": ticket_id,
            "since": time.time(),
        }
        self._save_locks()
        logger.info("[Chain] File locked: %s by ticket #%s", file_path, ticket_id)

    def release_file_lock(self, file_path: str, ticket_id: str):
        normalized = file_path.replace("\\", "/").lower()
        lock = self._locks.get(normalized)
        if lock and lock["ticket"] == ticket_id:
            del self._locks[normalized]
            self._save_locks()
            logger.info("[Chain] File unlocked: %s", file_path)

    def release_all_for_ticket(self, ticket_id: str):
        to_remove = [
            f for f, lock in self._locks.items()
            if lock["ticket"] == ticket_id
        ]
        for f in to_remove:
            del self._locks[f]
        if to_remove:
            self._save_locks()
            logger.info("[Chain] Released %d locks for ticket #%s",
                         len(to_remove), ticket_id)

    def get_blocking_tickets(self, estimated_files: list[str]) -> list[str]:
        self._cleanup_expired()
        blockers = []
        for f in estimated_files:
            normalized = f.replace("\\", "/").lower()
            lock = self._locks.get(normalized)
            if lock:
                blockers.append(
                    f"Archivo '{f}' está siendo modificado por ticket "
                    f"#{lock['ticket']} (desde hace "
                    f"{int((time.time() - lock['since']) / 60)} min)"
                )
        return blockers

    def is_blocked(self, estimated_files: list[str], current_ticket: str) -> bool:
        self._cleanup_expired()
        for f in estimated_files:
            normalized = f.replace("\\", "/").lower()
            lock = self._locks.get(normalized)
            if lock and lock["ticket"] != current_ticket:
                return True
        return False

    def inject_pending_changes(self, ticket_folder: str, blocked_by: list[str]) -> str:
        snippets = []
        for blocker_id in blocked_by:
            blocker_folder = self._find_ticket_folder(blocker_id)
            if not blocker_folder:
                continue
            dev_done = Path(blocker_folder) / "DEV_COMPLETADO.md"
            if dev_done.exists():
                content = dev_done.read_text(encoding="utf-8", errors="replace")
                snippets.append(
                    f"## CAMBIOS RECIENTES (ticket #{blocker_id}):\n"
                    + content[:1500]
                )
        return "\n\n".join(snippets)

    def _cleanup_expired(self):
        now = time.time()
        expired = [
            f for f, lock in self._locks.items()
            if now - lock["since"] > self.LOCK_TIMEOUT
        ]
        for f in expired:
            logger.warning("[Chain] Expired lock: %s (ticket #%s)",
                           f, self._locks[f]["ticket"])
            del self._locks[f]
        if expired:
            self._save_locks()

    def _find_ticket_folder(self, ticket_id: str) -> Optional[str]:
        projects_dir = Path(__file__).parent / "projects"
        if not projects_dir.exists():
            return None
        for state_dir in ["asignada", "en_proceso", "completado"]:
            for project_dir in projects_dir.iterdir():
                folder = project_dir / "tickets" / state_dir / ticket_id
                if folder.exists():
                    return str(folder)
        return None

    def _load_locks(self) -> dict:
        if LOCKS_FILE.exists():
            try:
                return json.loads(LOCKS_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    def _save_locks(self):
        LOCKS_FILE.parent.mkdir(parents=True, exist_ok=True)
        LOCKS_FILE.write_text(
            json.dumps(self._locks, indent=2), encoding="utf-8"
        )
