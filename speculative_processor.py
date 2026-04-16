"""
speculative_processor.py — X-09: Modo Turbo: Pre-Procesamiento Especulativo.

En lugar de esperar a que un developer tome un ticket para lanzar PM,
inicia el analisis PM de forma especulativa en los tickets con mayor
probabilidad de ser los proximos en trabajarse.

Cuando el developer toma el siguiente ticket, ANALISIS_TECNICO.md
ya esta listo. El developer empieza directo en DEV.

Caracteristicas:
  - Selecciona candidatos por priority score + posicion en cola
  - Cache con TTL configurable (default: 2h)
  - Invalidacion automatica si el ticket recibe notas nuevas en Mantis
  - Compatible con el daemon existente (se activa via config)

Uso:
    from speculative_processor import SpeculativeProcessor
    sp = SpeculativeProcessor(project_name, pipeline_runner)
    sp.maybe_speculate(active_tickets, queue)  # llamar desde daemon loop
"""

import json
import logging
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger("mantis.speculative")

BASE_DIR = Path(__file__).parent

# TTL por defecto del cache especulativo (2 horas)
DEFAULT_TTL_HOURS = 2
# Maximo de tickets especulativos en paralelo
MAX_SPECULATIVE = 2


class PMCache:
    """
    Cache de analisis PM especulativos.
    Persiste en pm_cache.json para sobrevivir reinicios del daemon.
    """

    def __init__(self, project_name: str):
        self._project = project_name
        self._path    = BASE_DIR / "projects" / project_name / "pm_cache.json"
        self._data    = self._load()
        self._lock    = threading.Lock()

    def get(self, ticket_id: str) -> Optional[dict]:
        """Retorna el entry del cache si existe y no expiro."""
        with self._lock:
            entry = self._data.get(ticket_id)
            if not entry:
                return None
            expires_at = datetime.fromisoformat(entry["expires_at"])
            if datetime.now() > expires_at:
                del self._data[ticket_id]
                self._save()
                return None
            return entry

    def put(self, ticket_id: str, status: str, ticket_folder: str,
            ttl_hours: float = DEFAULT_TTL_HOURS) -> None:
        """Almacena un entry en cache."""
        expires_at = datetime.now() + timedelta(hours=ttl_hours)
        with self._lock:
            self._data[ticket_id] = {
                "ticket_id":     ticket_id,
                "status":        status,  # "speculating", "ready", "invalidated"
                "ticket_folder": ticket_folder,
                "created_at":    datetime.now().isoformat(),
                "expires_at":    expires_at.isoformat(),
            }
            self._save()

    def invalidate(self, ticket_id: str, reason: str = "") -> None:
        """Invalida el cache para un ticket (ej: recibio notas nuevas)."""
        with self._lock:
            if ticket_id in self._data:
                self._data[ticket_id]["status"] = "invalidated"
                self._data[ticket_id]["invalidated_reason"] = reason
                self._save()
                logger.info("[X-09] Cache invalidado para %s: %s", ticket_id, reason)

    def is_ready(self, ticket_id: str) -> bool:
        entry = self.get(ticket_id)
        return entry is not None and entry.get("status") == "ready"

    def is_speculating(self, ticket_id: str) -> bool:
        entry = self.get(ticket_id)
        return entry is not None and entry.get("status") == "speculating"

    def list_ready(self) -> list:
        """Lista todos los tickets con PM especulativo listo."""
        with self._lock:
            now = datetime.now()
            return [
                e for e in self._data.values()
                if e.get("status") == "ready"
                and datetime.fromisoformat(e["expires_at"]) > now
            ]

    def cleanup_expired(self) -> int:
        """Elimina entries expirados. Retorna cuantos se borraron."""
        with self._lock:
            now = datetime.now()
            expired = [
                k for k, v in self._data.items()
                if datetime.fromisoformat(v["expires_at"]) <= now
            ]
            for k in expired:
                del self._data[k]
            if expired:
                self._save()
            return len(expired)

    def _load(self) -> dict:
        if self._path.exists():
            try:
                return json.loads(self._path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    def _save(self) -> None:
        self._path.write_text(
            json.dumps(self._data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


class SpeculativeProcessor:
    """
    Lanza PM de forma especulativa para los tickets con mayor probabilidad
    de ser los proximos en trabajarse.
    """

    def __init__(self, project_name: str, pipeline_runner=None):
        self.project_name    = project_name
        self._pipeline_runner = pipeline_runner
        self._config         = self._load_config()
        self._cache          = PMCache(project_name)
        self._enabled        = self._config.get("turbo_mode", {}).get("enabled", False)
        self._max_speculative = self._config.get("turbo_mode", {}).get("max_speculative", MAX_SPECULATIVE)
        self._ttl_hours      = self._config.get("turbo_mode", {}).get("ttl_hours", DEFAULT_TTL_HOURS)
        self._tickets_base   = BASE_DIR / "projects" / project_name / "tickets"

    # ── API publica ──────────────────────────────────────────────────────────

    def maybe_speculate(self, pending_tickets: list, active_tickets: list) -> list:
        """
        Analiza la cola y lanza PM especulativo para los candidatos optimos.

        Args:
            pending_tickets: Lista de tickets aun no procesados (con priority_score).
            active_tickets:  Lista de tickets actualmente en pipeline.

        Retorna lista de ticket_ids que se enviaron a especulacion.
        """
        if not self._enabled:
            return []

        # Limpiar cache expirado
        cleaned = self._cache.cleanup_expired()
        if cleaned:
            logger.debug("[X-09] %d entries de cache expirados eliminados", cleaned)

        # Cuantos slots especulativos quedan
        currently_speculating = len([
            t for t in pending_tickets
            if self._cache.is_speculating(t.get("ticket_id", ""))
        ])
        slots_available = self._max_speculative - currently_speculating
        if slots_available <= 0:
            return []

        # Ordenar pendientes por priority_score descendente
        candidates = sorted(
            pending_tickets,
            key=lambda t: t.get("priority_score", 0),
            reverse=True,
        )

        launched = []
        for ticket in candidates:
            if slots_available <= 0:
                break
            ticket_id = ticket.get("ticket_id", "")
            if not ticket_id:
                continue
            # No especular si ya esta en cache (ready o especulando) o activo
            if self._cache.get(ticket_id):
                continue
            if any(a.get("ticket_id") == ticket_id for a in active_tickets):
                continue

            # Lanzar especulacion en thread separado
            logger.info("[X-09] Lanzando PM especulativo para ticket %s", ticket_id)
            self._cache.put(ticket_id, "speculating",
                            str(self._get_ticket_folder(ticket_id)),
                            self._ttl_hours)
            t = threading.Thread(
                target=self._run_speculative_pm,
                args=(ticket,),
                daemon=True,
                name=f"speculative-pm-{ticket_id}",
            )
            t.start()
            launched.append(ticket_id)
            slots_available -= 1

        return launched

    def check_cache_hit(self, ticket_id: str) -> Optional[dict]:
        """
        Verifica si hay un PM especulativo listo para un ticket que se acaba de asignar.
        Si existe, retorna el entry del cache para que el daemon lo use directamente.
        """
        entry = self._cache.get(ticket_id)
        if entry and entry.get("status") == "ready":
            logger.info(
                "[X-09] Cache HIT para ticket %s — PM ya completo, iniciando DEV directamente",
                ticket_id,
            )
            return entry
        return None

    def invalidate_if_changed(self, ticket_id: str, new_notes_count: int,
                              cached_notes_count: int) -> bool:
        """
        Invalida el cache si el ticket recibio nuevas notas desde que se especulo.
        Retorna True si se invalido.
        """
        if new_notes_count > cached_notes_count:
            self._cache.invalidate(
                ticket_id,
                f"Ticket recibio {new_notes_count - cached_notes_count} notas nuevas"
            )
            return True
        return False

    def get_status(self) -> dict:
        """Retorna estado del modo turbo para el dashboard."""
        ready        = self._cache.list_ready()
        return {
            "enabled":          self._enabled,
            "max_speculative":  self._max_speculative,
            "ttl_hours":        self._ttl_hours,
            "ready_tickets":    [e["ticket_id"] for e in ready],
            "ready_count":      len(ready),
        }

    # ── Privados ─────────────────────────────────────────────────────────────

    def _run_speculative_pm(self, ticket: dict) -> None:
        """
        Ejecuta el pipeline PM en modo especulativo para un ticket.
        Corre en thread separado — no bloquea el daemon.
        """
        ticket_id = ticket.get("ticket_id", "")
        try:
            if self._pipeline_runner:
                # Invocar solo la etapa PM del pipeline runner
                success = self._pipeline_runner.run_stage(ticket_id, "pm", speculative=True)
                status  = "ready" if success else "error"
            else:
                # Modo simulado (para testing sin pipeline_runner real)
                logger.debug("[X-09] pipeline_runner no disponible — modo simulado para %s", ticket_id)
                time.sleep(1)
                status = "ready"

            self._cache.put(
                ticket_id, status,
                str(self._get_ticket_folder(ticket_id)),
                self._ttl_hours,
            )
            logger.info("[X-09] PM especulativo completado para %s: %s", ticket_id, status)

        except Exception as exc:
            logger.warning("[X-09] Error en PM especulativo para %s: %s", ticket_id, exc)
            self._cache.put(ticket_id, "error",
                            str(self._get_ticket_folder(ticket_id)),
                            ttl_hours=0.1)  # expirar rapido en error

    def _get_ticket_folder(self, ticket_id: str) -> Path:
        padded = ticket_id.zfill(7)
        if self._tickets_base.exists():
            for estado_dir in self._tickets_base.iterdir():
                candidate = estado_dir / padded
                if candidate.exists():
                    return candidate
        return self._tickets_base / "nueva" / padded

    def _load_config(self) -> dict:
        cfg = BASE_DIR / "projects" / self.project_name / "config.json"
        if cfg.exists():
            try:
                return json.loads(cfg.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}
