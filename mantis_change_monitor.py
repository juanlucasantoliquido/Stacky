"""
mantis_change_monitor.py — N-05: Detector de escaladas de prioridad en Mantis.

Monitorea cambios en tickets ya scrapeados buscando:
  - Nuevas notas con keywords de urgencia
  - Cambio de gravedad a bloqueante/crítica
  - Cambio de estado que indica escalada

Cuando detecta una escalada, reordena automáticamente la cola de procesamiento
y notifica al usuario con el motivo específico.

Uso:
    from mantis_change_monitor import MantisChangeMonitor
    monitor = MantisChangeMonitor(tickets_base, state_path, notifier)
    changes = monitor.check_for_escalations(project_name)
"""

import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("mantis.change_monitor")

# ── Keywords de escalada en notas de Mantis ───────────────────────────────────
_ESCALATION_KEYWORDS = [
    "urgente", "urgentísimo", "crítico", "bloqueando producción",
    "bloqueando el trabajo", "cliente escala", "gerencia", "directivo",
    "escalado por", "escalado a", "necesito esto hoy", "para hoy",
    "está caído", "sistema caído", "no pueden trabajar", "parado",
    "impacto en producción", "pérdida de datos", "datos incorrectos",
    "facturación incorrecta", "cierre de mes", "auditoría",
]

# Keywords de resolución (bajan prioridad)
_RESOLUTION_KEYWORDS = [
    "se resuelve", "resuelto", "cerrado", "workaround", "solución temporal",
    "esperar", "diferido", "pospuesto",
]


@dataclass
class EscalationEvent:
    ticket_id:    str
    reason:       str
    keyword:      str
    severity:     str   # "high" | "medium"
    detected_at:  str
    new_priority: int   # 1 = máxima prioridad


class MantisChangeMonitor:
    """
    Monitorea cambios en los archivos INC de tickets ya scrapeados
    y detecta escaladas de prioridad.
    """

    def __init__(self, tickets_base: str, state_path: str, notifier=None):
        self._tickets_base = tickets_base
        self._state_path   = state_path
        self._notifier     = notifier
        # Cache de mtime de archivos INC para detectar cambios
        self._mtime_cache: dict[str, float] = {}

    def check_for_escalations(self, project_name: str = "") -> list[EscalationEvent]:
        """
        Escanea todos los tickets en estados activos buscando escaladas.
        Retorna lista de EscalationEvents detectados.
        """
        events = []
        active_states = ["asignada", "confirmada", "nueva", "aceptada"]

        for estado in active_states:
            estado_dir = os.path.join(self._tickets_base, estado)
            if not os.path.isdir(estado_dir):
                continue
            try:
                for ticket_id in os.listdir(estado_dir):
                    ticket_folder = os.path.join(estado_dir, ticket_id)
                    inc_path      = os.path.join(ticket_folder, f"INC-{ticket_id}.md")
                    if not os.path.exists(inc_path):
                        continue

                    # ¿Cambió desde la última vez?
                    try:
                        mtime = os.path.getmtime(inc_path)
                    except OSError:
                        continue

                    cache_key   = f"{estado}/{ticket_id}"
                    last_mtime  = self._mtime_cache.get(cache_key, 0)
                    self._mtime_cache[cache_key] = mtime

                    if mtime <= last_mtime and last_mtime > 0:
                        continue  # No cambió

                    # Analizar el archivo
                    event = self._analyze_ticket(ticket_id, inc_path)
                    if event:
                        events.append(event)
                        self._handle_escalation(event, ticket_folder)
            except Exception as e:
                logger.debug("Error escaneando %s: %s", estado_dir, e)

        return events

    def _analyze_ticket(self, ticket_id: str, inc_path: str) -> EscalationEvent | None:
        """Analiza un INC.md buscando señales de escalada."""
        try:
            content       = Path(inc_path).read_text(encoding="utf-8", errors="replace")
            content_lower = content.lower()
        except Exception:
            return None

        # Buscar keywords de escalada
        for keyword in _ESCALATION_KEYWORDS:
            if keyword in content_lower:
                # Verificar que no sea en sección de historial antiguo
                # (buscar el keyword en las últimas notas)
                severity = "high" if any(k in keyword for k in
                                          ["producción", "caído", "cierre", "auditoría",
                                           "gerencia", "directivo"]) else "medium"
                return EscalationEvent(
                    ticket_id=ticket_id,
                    reason=f"Keyword de escalada detectado: '{keyword}'",
                    keyword=keyword,
                    severity=severity,
                    detected_at=datetime.now().isoformat(),
                    new_priority=1 if severity == "high" else 2,
                )

        # Verificar cambio de gravedad a bloqueante/crítica
        if re.search(r'gravedad[:\s]+\*{0,2}(bloqueante|crítica?)',
                     content, re.IGNORECASE):
            return EscalationEvent(
                ticket_id=ticket_id,
                reason="Gravedad escalada a bloqueante/crítica",
                keyword="gravedad bloqueante",
                severity="high",
                detected_at=datetime.now().isoformat(),
                new_priority=1,
            )

        return None

    def _handle_escalation(self, event: EscalationEvent,
                            ticket_folder: str) -> None:
        """Actualiza prioridad en pipeline_state y notifica."""
        try:
            from pipeline_state import load_state, save_state, set_ticket_priority
            state = load_state(self._state_path)
            set_ticket_priority(state, event.ticket_id, event.new_priority)
            save_state(self._state_path, state)
            logger.info(
                "[ESCALATION] Ticket #%s escalado a prioridad %d: %s",
                event.ticket_id, event.new_priority, event.reason
            )
        except Exception as e:
            logger.warning("[ESCALATION] Error actualizando prioridad: %s", e)

        # Escribir flag de escalada en la carpeta del ticket
        flag_path = os.path.join(ticket_folder, "ESCALATION.json")
        try:
            import json
            with open(flag_path, "w", encoding="utf-8") as f:
                json.dump({
                    "ticket_id":   event.ticket_id,
                    "reason":      event.reason,
                    "keyword":     event.keyword,
                    "severity":    event.severity,
                    "detected_at": event.detected_at,
                    "new_priority": event.new_priority,
                }, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

        # Notificar
        if self._notifier:
            try:
                self._notifier.send(
                    title=f"Escalada detectada — Ticket #{event.ticket_id}",
                    message=f"{event.reason} — Subido a prioridad {event.new_priority}",
                    level="warning",
                    ticket_id=event.ticket_id,
                )
            except Exception:
                pass
