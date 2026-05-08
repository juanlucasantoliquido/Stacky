"""
blocker_registry.py — Registry persistente de blockers por run.

Un "blocker" es un evento en el que el pipeline no puede continuar
sin intervención humana. Cada blocker tiene:
  - blocker_id: UUID canónico
  - stage: stage del pipeline donde ocurrió
  - reason: por qué se bloqueó
  - question: pregunta al operador (qué necesita para desbloquearse)
  - options: lista de opciones válidas (puede estar vacía = texto libre)
  - status: pending | resolved | skipped | expired
  - answer: respuesta del operador (solo cuando resolved)
  - answered_at: timestamp de la respuesta
  - answered_by: quién respondió (operador, sistema, etc.)

Persistencia: <run_dir>/blockers.json (JSON array, rewrite-on-change).

Diseño: sin SQLite propio — el archivo JSON es pequeño y legible
directamente por el operador. EventStore/ForensicEventLogger recibe
los eventos de lifecycle del blocker si se pasan como parámetros.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _new_blocker_id() -> str:
    return f"blk-{uuid.uuid4().hex[:12]}"


class BlockerRegistry:
    """
    Registry de blockers para un run de QA UAT.

    Thread-safety: básica (un solo operador por run).
    Persiste en <run_dir>/blockers.json.
    """

    STATUSES = frozenset({"pending", "resolved", "skipped", "expired"})

    def __init__(self, run_id: str, run_dir: Path) -> None:
        self.run_id = run_id
        self.run_dir = run_dir
        self._path = run_dir / "blockers.json"
        self._blockers: list[dict] = []
        self._load()

    # ── Persistencia ──────────────────────────────────────────────────────────

    def _load(self) -> None:
        if self._path.exists():
            try:
                self._blockers = json.loads(self._path.read_text(encoding="utf-8"))
            except Exception:
                self._blockers = []

    def _save(self) -> None:
        try:
            self._path.write_text(
                json.dumps(self._blockers, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass  # never raise from registry

    # ── API ───────────────────────────────────────────────────────────────────

    def register(
        self,
        stage: str,
        reason: str,
        question: str,
        *,
        options: Optional[list[str]] = None,
        blocker_id: Optional[str] = None,
        source_event_id: Optional[str] = None,
        extra: Optional[dict] = None,
    ) -> str:
        """
        Registrar un nuevo blocker.

        Devuelve el blocker_id.
        """
        bid = blocker_id or _new_blocker_id()
        entry: dict = {
            "blocker_id": bid,
            "run_id": self.run_id,
            "stage": stage,
            "reason": reason,
            "question": question,
            "options": options or [],
            "status": "pending",
            "answer": None,
            "answered_at": None,
            "answered_by": None,
            "source_event_id": source_event_id,
            "created_at": _utcnow(),
            "extra": extra or {},
        }
        # Replace if same blocker_id (idempotent)
        self._blockers = [b for b in self._blockers if b["blocker_id"] != bid]
        self._blockers.append(entry)
        self._save()
        return bid

    def resolve(
        self,
        blocker_id: str,
        answer: str,
        *,
        answered_by: str = "operator",
    ) -> bool:
        """
        Marcar un blocker como resuelto con la respuesta del operador.

        Devuelve True si se encontró y actualizó, False si no existía.
        """
        for b in self._blockers:
            if b["blocker_id"] == blocker_id:
                if b["status"] != "pending":
                    return False  # ya resuelto / expirado
                b["status"] = "resolved"
                b["answer"] = answer
                b["answered_at"] = _utcnow()
                b["answered_by"] = answered_by
                self._save()
                return True
        return False

    def skip(self, blocker_id: str, *, skipped_by: str = "operator") -> bool:
        """Marcar un blocker como skipped (operador elige ignorarlo)."""
        for b in self._blockers:
            if b["blocker_id"] == blocker_id and b["status"] == "pending":
                b["status"] = "skipped"
                b["answered_at"] = _utcnow()
                b["answered_by"] = skipped_by
                self._save()
                return True
        return False

    def get(self, blocker_id: str) -> Optional[dict]:
        for b in self._blockers:
            if b["blocker_id"] == blocker_id:
                return dict(b)
        return None

    def get_pending(self) -> list[dict]:
        return [dict(b) for b in self._blockers if b["status"] == "pending"]

    def get_all(self) -> list[dict]:
        return [dict(b) for b in self._blockers]

    def all_resolved(self) -> bool:
        """True si no hay ningún blocker en estado pending."""
        return all(b["status"] != "pending" for b in self._blockers)

    def summary(self) -> dict:
        total = len(self._blockers)
        by_status: dict[str, int] = {}
        for b in self._blockers:
            s = b["status"]
            by_status[s] = by_status.get(s, 0) + 1
        return {
            "total": total,
            "pending": by_status.get("pending", 0),
            "resolved": by_status.get("resolved", 0),
            "skipped": by_status.get("skipped", 0),
            "expired": by_status.get("expired", 0),
            "all_resolved": self.all_resolved(),
        }
