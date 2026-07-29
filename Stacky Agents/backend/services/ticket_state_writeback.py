"""Plan 270 F4 — Refresco del snapshot local de estado tras escribir en el tracker.

Por qué un módulo propio y no reusar lo existente:
  - services/run_ticket_refresh.py:44-45 corta con "non_ado_tracker": no sirve
    para GitLab.
  - services/completion_sync.py:111 despacha a services.<tracker>_sync, y
    services/gitlab_sync.py NO EXISTE (0 hits en todo el backend): para GitLab
    levanta ModuleNotFoundError, que además abre el breaker.
  - Además completion_sync se dispara en la completación de una EJECUCIÓN
    (completion_dispatcher.py:120), no en el cierre manual del tablero.

Este módulo lee del tracker y escribe SÓLO en la base local de Stacky. NUNCA
toca `stacky_status`: si lo pisara, se comería el "completed" que acaba de
escribir el paso 5 del cierre y el KPI del plan mediría cualquier cosa.

C5 — una capa de services/ nunca importa de la capa web.
"""
from __future__ import annotations


def writeback_enabled() -> bool:
    """STACKY_TICKET_STATE_WRITEBACK_ENABLED (default True)."""
    from config import config as _cfg
    return bool(getattr(_cfg, "STACKY_TICKET_STATE_WRITEBACK_ENABLED", True))


def _result(refreshed: bool, reason: str, ado_state=None) -> dict:
    return {"refreshed": refreshed, "reason": reason, "ado_state": ado_state}


def refresh_local_state(ticket_id: int) -> dict:
    """Relee el ítem del tracker y persiste su estado en Ticket.ado_state.

    Devuelve {"refreshed": bool, "reason": str, "ado_state": str|None}.
    NUNCA levanta: un fallo de refresco no puede tumbar un cierre que YA se
    escribió en el tracker (fail-open, mismo criterio que
    run_ticket_refresh.py:64-69).

    Razones posibles: "ok" | "flag_off" | "ticket_not_found" | "no_ado_id" |
    "writer_unavailable" | "tracker_error: <detalle>" | "state_absent".
    """
    if not writeback_enabled():
        return _result(False, "flag_off")

    try:
        from datetime import datetime

        from db import session_scope           # db.py:485, NO models.py
        from models import Ticket

        with session_scope() as session:
            ticket = session.get(Ticket, ticket_id)
            if ticket is None:
                return _result(False, "ticket_not_found")
            ado_id = getattr(ticket, "ado_id", None)
            # Los sentinelas negativos (-1..-9) son un patrón vivo del repo:
            # run_ticket_refresh.py:41-42 ya los descarta con ado_id <= 0.
            if ado_id is None or int(ado_id) <= 0:
                return _result(False, "no_ado_id")

            from services import tracker_write_router as _twr
            try:
                writer = _twr.resolve_state_writer(ticket)
            except Exception as exc:  # noqa: BLE001
                return _result(False, f"writer_unavailable: {type(exc).__name__}")

            if writer.kind == "ado_client":
                # Se delega en el helper que YA usa el repo para refrescar un
                # work item puntual. Escribe las 9 columnas de ado_sync.py:326-335
                # (title, ado_state, work_item_type, ...) y CERO veces
                # stacky_status: todos los valores vienen del tracker, así que
                # "pisar" es converger a la verdad.
                from services import ado_sync
                try:
                    ado_sync.upsert_single_work_item(writer.handle, int(ado_id))
                except Exception as exc:  # noqa: BLE001
                    return _result(False, f"tracker_error: {exc}")
                refrescado = session.get(Ticket, ticket_id)
                return _result(True, "ok", getattr(refrescado, "ado_state", None))

            # Rama provider (GitLab y cualquier otro puerto): sólo ado_state.
            try:
                item = writer.handle.get_item(str(ado_id))
            except Exception as exc:  # noqa: BLE001
                return _result(False, f"tracker_error: {exc}")

            # C10 — la key es literalmente "state" (gitlab_provider.py:86), y
            # GitLab devuelve "opened"/"closed". "Closed" está en
            # DEFAULT_CLOSED_STATES y la comparación es case-insensitive.
            nuevo = str((item or {}).get("state") or "")
            if not nuevo:
                # No se pisa la columna con "": la verdad ausente no es una verdad.
                return _result(False, "state_absent", getattr(ticket, "ado_state", None))

            ticket.ado_state = nuevo
            ticket.last_synced_at = datetime.utcnow()
            return _result(True, "ok", nuevo)
    except Exception as exc:  # noqa: BLE001
        # Fail-open duro: este módulo no puede tumbar un cierre ya escrito.
        return _result(False, f"tracker_error: {exc}")
