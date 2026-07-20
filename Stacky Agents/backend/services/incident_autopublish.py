"""Plan 166 F3 — auto-publica la Issue de una incidencia al terminar el análisis,
sin confirmación humana. Agnóstico de runtime (corre en el post-hook de
ticket_status). EXCEPCIÓN DURA #1, aceptada por directiva del operador
2026-07-17 (mismo precedente que épica-desde-brief)."""
from __future__ import annotations

import logging

logger = logging.getLogger("stacky.services.incident_autopublish")


def maybe_autopublish_incident(*, ticket_id, execution_id, final_status, agent_type, error=None, **_):
    from config import config as _cfg
    if not getattr(_cfg, "STACKY_INCIDENT_AUTO_PUBLISH_ENABLED", False):
        return
    if agent_type != "incident" or final_status != "completed":
        return
    from services import incident_store
    # localizar el incidente por execution_id (el store lo guardó al lanzar el
    # análisis — VERIFICADO: api/agents.py:1053 hace
    # update_incident(incident_id, status="analizando", execution_id=execution_id))
    incident = incident_store.find_by_execution(execution_id)
    if incident is None or not incident.get("auto_publish"):
        return
    if incident.get("tracker_id"):
        return  # ya publicada (idempotente)
    try:
        from api.tickets import _do_publish_incident
        payload, status = _do_publish_incident(
            incident_id=incident["id"], execution_id=execution_id,
        )
        if status >= 400:
            # Los errores terminales de tracker YA marcan status="error" en el
            # store (vía _incident_publish_terminal_error). Otros payloads de
            # error (p.ej. incident_not_in_output 422) NO — marcarlo acá para
            # que la cola del modal lo muestre (C3, plan 135: cero errores mudos).
            if (incident_store.get_incident(incident["id"]) or {}).get("status") != "error":
                incident_store.update_incident(
                    incident["id"], status="error",
                    error=str(payload.get("error") or f"http_{status}"),
                )
            logger.warning("autopublish incidencia execution=%s status=%s payload=%s",
                           execution_id, status, payload.get("error"))
    except Exception as exc:  # noqa: BLE001 — C3: el fallo NUNCA queda mudo
        logger.warning("autopublish incidencia execution=%s falló: %s", execution_id, exc)
        try:
            incident_store.update_incident(incident["id"], status="error", error=str(exc))
        except Exception:  # noqa: BLE001 — best-effort final
            pass


def register(register_post_hook):
    register_post_hook(maybe_autopublish_incident)
