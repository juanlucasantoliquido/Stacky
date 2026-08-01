"""Plan 208 F3 — Auto-sync de tickets al completar un agente (R2).

Al terminar cualquier agente se refrescan los tickets del proyecto desde el
tracker: **pull read-only**, coalescido por proyecto, respetando el circuit
breaker (Plan 148), sin bloquear ni demorar la completación (todo corre en el
hilo del daemon del dispatcher; el post-hook solo hizo `put_nowait`).

Multi-tracker: despacha al `sync_tickets` correcto (ADO / Jira / Mantis) con la
firma que cada uno expone — ADO toma `project_name`, Jira y Mantis toman
`tracker_config` (verificado en jira_sync.py:45 y mantis_sync.py:33).
"""
from __future__ import annotations

import logging
import threading
import time

logger = logging.getLogger("stacky_agents.completion_sync")

_COALESCE_WINDOW_SEC = 30            # constante interna (espejo integration_breaker._BACKOFF_BASE_SEC)
_last_sync_ts: dict[str, float] = {}  # project -> epoch del último sync masivo
_pending: dict[str, dict] = {}        # project -> último evento visto en la ventana (para flush)
_mutex = threading.Lock()


def sync_on_completion_enabled() -> bool:
    # C1: INSTANCIA config.config, no el atributo de clase (ver completion_state.matrix_enabled).
    try:
        from config import config as _cfg

        return bool(getattr(_cfg, "STACKY_ADO_SYNC_ON_COMPLETION_ENABLED", False))
    except Exception:  # noqa: BLE001
        return False


def coalesce_window_sec() -> float:
    return float(_COALESCE_WINDOW_SEC)


def _resolve_sync_and_project(ticket) -> tuple:
    """Devuelve (sync_callable, project_name, tracker_type).

    `project_name` es SIEMPRE el `stacky_project_name` (workspace Stacky): clave
    canónica de breaker/cliente, coherente con `_startup_sync` (app.py:196,203).
    C3: NO caer a `ticket.project` (nombre del tracker) ⇒ divergiría la key del breaker.
    """
    tracker_type = (getattr(ticket, "tracker_type", None) or "azure_devops").strip().lower()
    project = getattr(ticket, "stacky_project_name", None)
    if tracker_type == "jira":
        from services.jira_sync import sync_tickets as fn
    elif tracker_type == "mantis":
        from services.mantis_sync import sync_tickets as fn
    else:
        from services.ado_sync import sync_tickets as fn
    return fn, project, tracker_type


def _tracker_config_for(project: str) -> dict:
    """`issue_tracker` del proyecto (fuente que usa `_startup_sync` para Jira/Mantis)."""
    try:
        from project_manager import get_project_config

        return (get_project_config(project) or {}).get("issue_tracker") or {}
    except Exception:  # noqa: BLE001
        logger.debug("no se pudo leer issue_tracker de %s", project, exc_info=True)
        return {}


def _breaker_target(project: str, tracker_type: str) -> tuple[str, str | None]:
    """(integration, key) con la MISMA derivación que los demás consumidores del
    breaker, para que las ventanas de backoff coincidan."""
    from services import integration_breaker as brk

    if tracker_type == "azure_devops":
        return "ado_sync", brk.ado_breaker_project(project)
    if tracker_type == "jira":
        # app.py:123 usa el `project` del issue_tracker como key de jira_sync.
        return "jira_sync", (_tracker_config_for(project).get("project") or "").strip() or None
    return f"{tracker_type}_sync", project


def _do_project_sync(project: str, tracker_type: str, ado_id=None) -> None:
    """Sync masivo + upsert puntual. Respeta el breaker. Best-effort, nunca lanza."""
    from services import integration_breaker as brk

    integ, bkey = _breaker_target(project, tracker_type)
    if brk.should_skip(integ, bkey):
        logger.debug("completion_sync: breaker abierto para %s/%s, skip", integ, bkey)
        return
    result: dict = {}
    try:
        if tracker_type == "azure_devops":
            from services import ado_sync
            # C4: construir el cliente desde services (NO importar api.tickets: acopla
            # service->api y arriesga import circular al arrancar el daemon).
            # build_ado_client(project_name=<stacky>) es la firma canónica
            # (project_context.py:289), ya usada así en _startup_sync (app.py:203).
            from services import project_context

            client = project_context.build_ado_client(project_name=project)
            if ado_id:
                try:
                    ado_sync.upsert_single_work_item(client, int(ado_id))  # refleja el ticket puntual YA
                except Exception:  # noqa: BLE001
                    logger.debug("upsert_single best-effort falló", exc_info=True)
            result = ado_sync.sync_tickets(client=client, project_name=project) or {}
        else:
            # Plan 281 F5 — el dispatch dinámico asume la firma
            # `sync_tickets(tracker_config=...)`, que GitLab NO tiene: su entrada es
            # `sync_gitlab_tickets(project_name, provider=...)` (services/gitlab_sync.py,
            # única entrada de su `__all__`). Antes esto era un AttributeError que se
            # tragaba el `except Exception` de más abajo: el sync post-completación
            # NUNCA corría en GitLab, en silencio.
            # Se elige la rama EXPLÍCITA sobre un alias silencioso en gitlab_sync:
            # un alias haría que el próximo tracker repita el mismo problema.
            if tracker_type == "gitlab":
                from services.gitlab_sync import sync_gitlab_tickets

                result = sync_gitlab_tickets(project) or {}
            else:
                # Jira y Mantis NO aceptan project_name: su entrada es tracker_config.
                from importlib import import_module

                mod = import_module(f"services.{tracker_type}_sync")
                if not hasattr(mod, "sync_tickets"):
                    # Ruidoso a propósito: un tracker nuevo sin la firma esperada tiene
                    # que APARECER en el log, no desaparecer.
                    raise AttributeError(
                        f"services.{tracker_type}_sync no expone sync_tickets(); "
                        f"agregá su rama explícita en _do_project_sync"
                    )
                result = mod.sync_tickets(tracker_config=_tracker_config_for(project)) or {}
        brk.record_success(integ, bkey)
        _last_sync_ts[project] = time.time()
        _log_sync(project, tracker_type, result, breaker_open=False)
    except Exception as exc:  # noqa: BLE001
        try:
            from services.integration_breaker import classify_ado_error

            reason, message = (
                classify_ado_error(exc) if tracker_type == "azure_devops"
                else ("unknown", str(exc)[:200])
            )
            brk.record_failure(integ, bkey, reason, message)
        except Exception:  # noqa: BLE001
            logger.debug("record_failure falló", exc_info=True)
        logger.warning("completion_sync: sync de %s falló (best-effort): %s", project, exc)
        _log_sync(project, tracker_type, {}, breaker_open=False, error=str(exc)[:300])


def maybe_coalesced_sync(ev: dict) -> None:
    """Coalesce por proyecto: sync inmediato si pasó la ventana desde el último;
    si no, marca pending (lo drena `flush_pending_syncs` al vencer la ventana)."""
    if not sync_on_completion_enabled():
        return
    try:
        from db import session_scope
        from models import Ticket

        ticket_id = ev.get("ticket_id")
        with session_scope() as s:
            t = s.get(Ticket, ticket_id) if ticket_id else None
            if t is None:
                return
            _, project, tracker_type = _resolve_sync_and_project(t)
            ado_id = getattr(t, "ado_id", None)
        if not project:
            return
        now = time.time()
        with _mutex:
            last = _last_sync_ts.get(project, 0.0)
            if now - last >= _COALESCE_WINDOW_SEC:
                _pending.pop(project, None)
                do_now = True
            else:
                _pending[project] = {"tracker_type": tracker_type, "ado_id": ado_id}
                do_now = False
        if do_now:
            _do_project_sync(project, tracker_type, ado_id)
    except Exception:  # noqa: BLE001
        logger.debug("maybe_coalesced_sync falló (no crítico)", exc_info=True)


def flush_pending_syncs() -> None:
    """Se llama cuando la cola queda vacía por >= ventana: drena los proyectos
    pendientes (1 sync cada uno)."""
    if not sync_on_completion_enabled():
        with _mutex:
            _pending.clear()
        return
    with _mutex:
        items = list(_pending.items())
        _pending.clear()
    for project, meta in items:
        _do_project_sync(project, meta.get("tracker_type", "azure_devops"), meta.get("ado_id"))


def _log_sync(project: str, tracker_type: str, result: dict, *, breaker_open: bool,
              error: str | None = None) -> None:
    """Plan 208 F6 — traza auditable de cada auto-sync. Nunca lanza."""
    try:
        from services.completion_dispatcher import emit_completion_log

        emit_completion_log(
            action="completion.auto_sync",
            level="WARNING" if error else "INFO",
            context={
                "project": project,
                "tracker_type": tracker_type,
                "coalesced": project in _pending,
                "breaker_open": breaker_open,
                "fetched": result.get("fetched"),
                "created": result.get("created"),
                "updated": result.get("updated"),
                "removed": result.get("removed"),
                "error": error,
            },
            tags=["plan208", "auto_sync"],
        )
    except Exception:  # noqa: BLE001
        logger.debug("traza de auto_sync falló (no crítico)", exc_info=True)
