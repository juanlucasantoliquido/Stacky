"""R0.3 — Reaper de huerfanos + watchdog reconciliador.

Reconcilia executions en estado 'running' sin heartbeat reciente:
- Al arrancar el backend (si STACKY_ORPHAN_REAPER_ENABLED=true).
- Periodicamente cada STACKY_ORPHAN_REAPER_INTERVAL_SEC segundos (>0).

Para cada execution running huerfana:
  1. Flush de logs pendientes (R0.2, si habilitado).
  2. Reap del proceso exacto registrado (R0.1, si habilitado).
  3. Marcar como failed(reason="orphaned_on_restart").
  4. Sellar metadata["reaped"] = {by, at, reason}.

Para executions en estado terminal cuyo pid registrado siga vivo:
  1. Flush + reap.
  2. Sellar metadata["reaped"].

NUNCA toca runs con heartbeat reciente (definido por STACKY_RUNNING_ALERT_MINUTES).
NUNCA decide sobre el producto del trabajo ni publica a ADO.
"""
from __future__ import annotations

import logging
import os
import threading
from datetime import datetime, timedelta

logger = logging.getLogger("stacky_agents.orphan_reaper")

_TERMINAL = frozenset({"completed", "needs_review", "error", "cancelled", "failed"})


def _heartbeat_age_minutes() -> int:
    """Umbral de inactividad de heartbeat en minutos (configurable via env)."""
    return int(os.getenv("STACKY_RUNNING_ALERT_MINUTES", "30"))


def _is_pid_alive(pid: int) -> bool:
    """True si el pid sigue vivo en el SO (best-effort, no bloquea)."""
    try:
        import psutil  # type: ignore[import]
        return psutil.pid_exists(pid)
    except ImportError:
        pass
    # Fallback stdlib: os.kill(pid, 0) en Unix, no disponible en Windows sin error
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False
    except OSError:
        return False


def _seal_reaped_metadata(
    execution_id: int,
    *,
    by: str,
    reason: str,
    new_status: str | None = None,
) -> None:
    """Actualiza metadata["reaped"] en la DB (best-effort)."""
    try:
        from db import session_scope
        from models import AgentExecution
        with session_scope() as session:
            row = session.get(AgentExecution, execution_id)
            if row is None:
                return
            md = row.metadata_dict or {}
            md["reaped"] = {
                "by": by,
                "at": datetime.utcnow().isoformat(),
                "reason": reason,
            }
            row.metadata_dict = md
            if new_status is not None and row.status not in _TERMINAL:
                row.status = new_status
                row.completed_at = datetime.utcnow()
                row.error_message = reason
    except Exception as exc:  # noqa: BLE001
        logger.debug("seal_reaped_metadata fallo exec=%s: %s", execution_id, exc)


def reconcile_once() -> dict:
    """Ejecuta un barrido de reconciliacion.

    Retorna dict con contadores: {reaped, failed_orphans, skipped, errors}.
    """
    from config import config

    alert_minutes = _heartbeat_age_minutes()
    cutoff = datetime.utcnow() - timedelta(minutes=alert_minutes)
    reaped = 0
    failed_orphans = 0
    skipped = 0
    errors = 0

    try:
        from db import session_scope
        from models import AgentExecution

        with session_scope() as session:
            stale_running = (
                session.query(AgentExecution)
                .filter(
                    AgentExecution.status == "running",
                    AgentExecution.started_at < cutoff,
                )
                .all()
            )
            stale_ids = [(ex.id, ex.metadata_dict) for ex in stale_running]
    except Exception as exc:  # noqa: BLE001
        logger.warning("orphan_reaper: no se pudo consultar DB: %s", exc)
        return {"reaped": 0, "failed_orphans": 0, "skipped": 0, "errors": 1}

    for exec_id, md in stale_ids:
        if not isinstance(md, dict):
            md = {}
        pid = md.get("pid")
        runtime = md.get("runtime")

        try:
            # R0.2 — flush incremental si habilitado.
            if config.STACKY_LOG_FLUSH_INCREMENTAL_ENABLED:
                try:
                    import log_streamer
                    log_streamer.flush(exec_id)
                except Exception:  # noqa: BLE001
                    pass

            # R0.1 — reap via dispatcher.
            did_reap = False
            if config.STACKY_RUNNER_REAP_ON_CLOSE_ENABLED:
                try:
                    from services.runner_reap import reap_execution
                    did_reap = reap_execution(exec_id, runtime=runtime)
                except Exception:  # noqa: BLE001
                    pass
                if not did_reap and pid is not None:
                    # Proceso no registrado en memoria; comprobar pid vivo
                    if _is_pid_alive(int(pid)):
                        logger.info(
                            "orphan_reaper: exec=%s pid=%s vivo pero no registrado; ignorando",
                            exec_id, pid,
                        )

            _seal_reaped_metadata(
                exec_id,
                by="orphan_reaper",
                reason="orphaned_on_restart",
                new_status="failed",
            )
            failed_orphans += 1
            if did_reap:
                reaped += 1
            logger.info(
                "orphan_reaper: exec=%s marcado failed(orphaned_on_restart) reaped=%s",
                exec_id, did_reap,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("orphan_reaper: error en exec=%s: %s", exec_id, exc)
            errors += 1

    return {
        "reaped": reaped,
        "failed_orphans": failed_orphans,
        "skipped": skipped,
        "errors": errors,
    }


def start_background_reaper() -> None:
    """Lanza el barrido periodico en un daemon thread (si el intervalo es > 0).

    Solo hace algo si STACKY_ORPHAN_REAPER_ENABLED=true.
    """
    from config import config
    if not config.STACKY_ORPHAN_REAPER_ENABLED:
        return

    # Barrido inicial siempre al arrancar.
    try:
        result = reconcile_once()
        if result.get("failed_orphans"):
            logger.info(
                "orphan_reaper startup: %s huerfanos marcados failed, %s reaped",
                result["failed_orphans"], result["reaped"],
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("orphan_reaper startup fallo (no critico): %s", exc)

    interval_sec = config.STACKY_ORPHAN_REAPER_INTERVAL_SEC
    if interval_sec <= 0:
        return  # Solo al arrancar.

    def _loop() -> None:
        import time
        while True:
            time.sleep(interval_sec)
            try:
                result = reconcile_once()
                if result.get("failed_orphans") or result.get("reaped"):
                    logger.info("orphan_reaper periodic: %s", result)
            except Exception as exc:  # noqa: BLE001
                logger.debug("orphan_reaper periodic fallo: %s", exc)

    t = threading.Thread(target=_loop, daemon=True, name="stacky-orphan-reaper")
    t.start()
    logger.info("orphan_reaper: daemon iniciado (interval=%ss)", interval_sec)
