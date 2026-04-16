"""
autonomy_controller.py — G-09: Modo Autonomía Total con Approval Gates.

Permite a Stacky operar en distintos niveles de autonomía:
  - MANUAL:  Solo notifica — el humano decide cada etapa
  - GUIDED:  Lanza PM automáticamente, pide aprobación antes de DEV y QA
  - AUTO:    Pipeline completo sin intervención humana
  - SAFE:    AUTO pero requiere aprobación antes de commit SVN

Los approval gates se configuran por proyecto y se pueden sobrescribir
por ticket individual.

Uso:
    from autonomy_controller import AutonomyController, AutonomyLevel
    ac = AutonomyController(project_name, notifier)
    ac.set_level(AutonomyLevel.GUIDED)
    if ac.can_advance(ticket_id, "dev"):
        # lanzar DEV
"""

import json
import logging
import os
import threading
from datetime import datetime
from enum import Enum
from pathlib import Path

logger = logging.getLogger("mantis.autonomy")


class AutonomyLevel(str, Enum):
    MANUAL  = "manual"   # Solo notifica, sin lanzar nada
    GUIDED  = "guided"   # PM auto, DEV/QA requieren aprobación
    AUTO    = "auto"     # Pipeline completo sin intervención
    SAFE    = "safe"     # AUTO pero confirma antes de commit


# Gates por nivel: qué etapas requieren aprobación humana
_GATES: dict[AutonomyLevel, set[str]] = {
    AutonomyLevel.MANUAL:  {"pm", "dev", "tester"},
    AutonomyLevel.GUIDED:  {"dev", "tester"},
    AutonomyLevel.AUTO:    set(),
    AutonomyLevel.SAFE:    {"commit"},  # gate especial para commit
}


class AutonomyController:
    """
    Controla el nivel de autonomía del pipeline Stacky.
    Gestiona approval gates con timeout configurable.
    """

    def __init__(self, project_name: str, notifier=None,
                 approval_timeout_min: int = 30):
        self._project         = project_name
        self._notifier        = notifier
        self._approval_timeout = approval_timeout_min * 60  # en segundos
        self._lock            = threading.RLock()
        self._path            = self._get_path()
        self._data            = self._load()
        # Pendientes de aprobación: {ticket_id:stage → Event}
        self._pending_approvals: dict[str, threading.Event] = {}

    # ── API pública ───────────────────────────────────────────────────────

    def set_level(self, level: AutonomyLevel) -> None:
        """Establece el nivel de autonomía global."""
        with self._lock:
            self._data["level"] = level.value
            self._data["updated_at"] = datetime.now().isoformat()
            self._save()
        logger.info("[AUTONOMY] Nivel establecido: %s", level.value)

    def get_level(self) -> AutonomyLevel:
        """Retorna el nivel de autonomía actual."""
        with self._lock:
            return AutonomyLevel(self._data.get("level", AutonomyLevel.GUIDED.value))

    def can_advance(self, ticket_id: str, stage: str) -> bool:
        """
        Retorna True si se puede avanzar a esta etapa sin aprobación.
        Si requiere aprobación, notifica y espera (bloqueante con timeout).
        """
        level = self.get_level()
        gates = _GATES.get(level, set())

        if stage not in gates:
            return True  # No requiere aprobación

        # Verificar si ya fue aprobado previamente
        approval_key = f"{ticket_id}:{stage}"
        with self._lock:
            approvals = self._data.setdefault("approvals", {})
            if approvals.get(approval_key) == "approved":
                return True
            if approvals.get(approval_key) == "rejected":
                return False

        # Solicitar aprobación
        logger.info("[AUTONOMY] Esperando aprobación para %s/%s (timeout: %dmin)",
                    ticket_id, stage, self._approval_timeout // 60)

        if self._notifier:
            try:
                self._notifier.send(
                    title=f"⏸️ Aprobación requerida — Ticket #{ticket_id}",
                    message=(f"Stacky esperando aprobación para lanzar etapa '{stage}'. "
                             f"Responder en {self._approval_timeout//60} min."),
                    level="warning",
                    ticket_id=ticket_id,
                )
            except Exception:
                pass

        # Escribir flag de espera en la carpeta del ticket
        self._write_pending_flag(ticket_id, stage)

        # Esperar aprobación (polling cada 10s)
        import time
        deadline = time.time() + self._approval_timeout
        while time.time() < deadline:
            # Verificar si se aprobó/rechazó via flag o API
            result = self._check_approval_flag(ticket_id, stage)
            if result == "approved":
                with self._lock:
                    self._data.setdefault("approvals", {})[approval_key] = "approved"
                    self._save()
                logger.info("[AUTONOMY] %s/%s APROBADO", ticket_id, stage)
                return True
            if result == "rejected":
                with self._lock:
                    self._data.setdefault("approvals", {})[approval_key] = "rejected"
                    self._save()
                logger.info("[AUTONOMY] %s/%s RECHAZADO", ticket_id, stage)
                return False
            time.sleep(10)

        # Timeout — comportamiento por defecto según nivel
        logger.warning("[AUTONOMY] Timeout de aprobación para %s/%s — procediendo según política",
                       ticket_id, stage)
        # En GUIDED, el timeout es "auto-aprueba" (usuario no respondió → se procede)
        return level == AutonomyLevel.GUIDED

    def approve(self, ticket_id: str, stage: str) -> None:
        """Aprueba manualmente una etapa (desde dashboard o API)."""
        approval_key = f"{ticket_id}:{stage}"
        flag_path = self._get_approval_flag_path(ticket_id, stage)
        try:
            Path(flag_path).write_text("approved", encoding="utf-8")
        except Exception:
            pass
        with self._lock:
            self._data.setdefault("approvals", {})[approval_key] = "approved"
            self._save()
        logger.info("[AUTONOMY] Aprobado manualmente: %s/%s", ticket_id, stage)

    def reject(self, ticket_id: str, stage: str) -> None:
        """Rechaza manualmente una etapa."""
        approval_key = f"{ticket_id}:{stage}"
        flag_path = self._get_approval_flag_path(ticket_id, stage)
        try:
            Path(flag_path).write_text("rejected", encoding="utf-8")
        except Exception:
            pass
        with self._lock:
            self._data.setdefault("approvals", {})[approval_key] = "rejected"
            self._save()
        logger.info("[AUTONOMY] Rechazado manualmente: %s/%s", ticket_id, stage)

    def get_pending_approvals(self) -> list[dict]:
        """Retorna lista de aprobaciones pendientes."""
        pending = []
        with self._lock:
            for key, status in self._data.get("approvals", {}).items():
                if status == "pending":
                    tid, stage = key.split(":", 1)
                    pending.append({"ticket_id": tid, "stage": stage})
        return pending

    def get_status(self) -> dict:
        """Retorna el estado actual del controlador."""
        level = self.get_level()
        return {
            "level":    level.value,
            "gates":    list(_GATES.get(level, [])),
            "pending":  self.get_pending_approvals(),
            "timeout_min": self._approval_timeout // 60,
        }

    # ── Internals ─────────────────────────────────────────────────────────

    def _write_pending_flag(self, ticket_id: str, stage: str) -> None:
        """Escribe un flag de pendiente de aprobación en el disco."""
        flag_path = self._get_approval_flag_path(ticket_id, stage)
        try:
            Path(flag_path).write_text(
                json.dumps({
                    "ticket_id": ticket_id,
                    "stage":     stage,
                    "requested_at": datetime.now().isoformat(),
                }),
                encoding="utf-8"
            )
        except Exception:
            pass
        with self._lock:
            self._data.setdefault("approvals", {})[f"{ticket_id}:{stage}"] = "pending"
            self._save()

    def _check_approval_flag(self, ticket_id: str, stage: str) -> str:
        """Lee el flag de aprobación del disco. Retorna 'approved'/'rejected'/'pending'."""
        flag_path = self._get_approval_flag_path(ticket_id, stage)
        try:
            content = Path(flag_path).read_text(encoding="utf-8").strip()
            if content in ("approved", "rejected"):
                return content
        except Exception:
            pass
        return "pending"

    def _get_approval_flag_path(self, ticket_id: str, stage: str) -> str:
        base = os.path.dirname(os.path.abspath(__file__))
        approval_dir = os.path.join(base, "approvals")
        os.makedirs(approval_dir, exist_ok=True)
        return os.path.join(approval_dir, f"{self._project}_{ticket_id}_{stage}.approval")

    def _get_path(self) -> str:
        base = os.path.dirname(os.path.abspath(__file__))
        kb   = os.path.join(base, "knowledge", self._project)
        os.makedirs(kb, exist_ok=True)
        return os.path.join(kb, "autonomy_state.json")

    def _load(self) -> dict:
        try:
            with open(self._path, encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return {"level": AutonomyLevel.GUIDED.value, "approvals": {}}
        except Exception:
            return {"level": AutonomyLevel.GUIDED.value, "approvals": {}}

    def _save(self) -> None:
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error("[AUTONOMY] Error guardando estado: %s", e)
