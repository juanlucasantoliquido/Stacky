"""Heartbeat monitor: detecta runs colgados por ausencia de heartbeat.

Los runtimes que escriben `heartbeat.json` (ver manifest_watcher.write_heartbeat)
informan al reconciler que siguen vivos. Cuando el archivo:
  - no existe → el runtime nunca emitió heartbeat (proceso murió antes de
    arrancar, o usa un runtime sin heartbeat soportado), o
  - tiene timestamp más viejo que `STACKY_HEARTBEAT_TIMEOUT_MINUTES`,
el reconciler considera la ejecución "stale" y la marca como `error`.

Importante: este módulo NO toma decisiones — sólo evalúa. La transición de
estado la hace `services.ticket_status.recover_stale_running_tickets`.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from services.manifest_watcher import HEARTBEAT_FILENAME, default_runs_dir

logger = logging.getLogger("stacky.heartbeat_monitor")

HEARTBEAT_TIMEOUT_MINUTES: int = int(os.getenv("STACKY_HEARTBEAT_TIMEOUT_MINUTES", "10"))
# Período de gracia para ejecuciones recién creadas que aún no escribieron
# heartbeat: si la execution arrancó hace menos de este threshold, no la
# marcamos stale aunque no haya archivo.
STARTUP_GRACE_SECONDS: int = int(os.getenv("STACKY_HEARTBEAT_STARTUP_GRACE_SECONDS", "60"))


@dataclass
class HeartbeatStatus:
    """Resultado de evaluar el heartbeat de una ejecución."""

    exists: bool
    last_activity_ts: datetime | None
    pid: int | None
    phase: str | None
    age_seconds: float | None  # Segundos desde la última actividad. None si no hay heartbeat.

    def is_stale(self, *, timeout_minutes: int = HEARTBEAT_TIMEOUT_MINUTES) -> bool:
        """True si la actividad es más vieja que `timeout_minutes`."""
        if not self.exists or self.age_seconds is None:
            return False
        return self.age_seconds > timeout_minutes * 60

    def to_dict(self) -> dict[str, Any]:
        return {
            "exists": self.exists,
            "last_activity_ts": self.last_activity_ts.isoformat() + "Z"
            if self.last_activity_ts
            else None,
            "pid": self.pid,
            "phase": self.phase,
            "age_seconds": self.age_seconds,
        }


def read_heartbeat(execution_id: int, runs_dir: Path | None = None) -> HeartbeatStatus:
    """Lee heartbeat.json de una ejecución. Tolerante a archivo ausente o roto."""
    base = Path(runs_dir) if runs_dir is not None else default_runs_dir()
    path = base / str(execution_id) / HEARTBEAT_FILENAME
    if not path.is_file():
        return HeartbeatStatus(
            exists=False,
            last_activity_ts=None,
            pid=None,
            phase=None,
            age_seconds=None,
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.debug("heartbeat_monitor: heartbeat inválido en %s: %s", path, exc)
        return HeartbeatStatus(
            exists=False,
            last_activity_ts=None,
            pid=None,
            phase=None,
            age_seconds=None,
        )

    ts = _parse_ts(data.get("last_activity_ts"))
    age = (datetime.utcnow() - ts).total_seconds() if ts else None
    return HeartbeatStatus(
        exists=True,
        last_activity_ts=ts,
        pid=data.get("pid") if isinstance(data.get("pid"), int) else None,
        phase=data.get("phase") if isinstance(data.get("phase"), str) else None,
        age_seconds=age,
    )


def is_execution_heartbeat_stale(
    execution_id: int,
    *,
    started_at: datetime | None,
    timeout_minutes: int = HEARTBEAT_TIMEOUT_MINUTES,
    startup_grace_seconds: int = STARTUP_GRACE_SECONDS,
    runs_dir: Path | None = None,
) -> tuple[bool, HeartbeatStatus]:
    """Decide si una execution está stale en función del heartbeat.

    Reglas:
      - Si la execution arrancó hace < startup_grace_seconds y no hay
        heartbeat: NO stale (período de gracia).
      - Si arrancó hace > startup_grace_seconds y no hay heartbeat: STALE.
      - Si hay heartbeat con age > timeout: STALE.
      - Si hay heartbeat con age <= timeout: NO stale (vivo).

    Retorna (stale, status) con el status detallado para diagnóstico.
    """
    status = read_heartbeat(execution_id, runs_dir=runs_dir)
    if status.exists:
        return status.is_stale(timeout_minutes=timeout_minutes), status

    # No hay heartbeat. Aplicar período de gracia.
    if started_at is None:
        return True, status
    elapsed_since_start = (datetime.utcnow() - started_at).total_seconds()
    if elapsed_since_start <= startup_grace_seconds:
        return False, status
    return True, status


def _parse_ts(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.rstrip("Z"))
    except ValueError:
        return None
