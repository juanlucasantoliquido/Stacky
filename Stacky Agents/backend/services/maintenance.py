"""Plan 253 F5 — registro de tareas periodicas de mantenimiento.

Punto de extension COMPARTIDO. El loop vive en app.py (_maintenance_loop,
thread "stacky-maintenance"); aca solo se declara QUE correr y CADA CUANTO.
Los planes hermanos (257 F2 y siguientes) registran aca en vez de crear
daemons nuevos.

Modulo PURO: no toca Flask, ni disco, ni la base.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class MaintenanceTask:
    name: str                      # slug estable, aparece en el log y en el health
    interval_s: Callable[[], int]  # LAZY: se relee cada vuelta (la UI puede cambiarlo en caliente)
    enabled: Callable[[], bool]    # LAZY: idem para la flag
    run: Callable[[], int]         # devuelve "unidades procesadas" (filas, archivos, lo que sea)


_LOCK = threading.Lock()
_TASKS: list[MaintenanceTask] = []
_STATE: dict[str, dict] = {}


def register_maintenance_task(task: MaintenanceTask) -> None:
    """Alta idempotente por `name`: registrar dos veces no duplica la tarea."""
    with _LOCK:
        for existing in _TASKS:
            if existing.name == task.name:
                return
        _TASKS.append(task)
        _STATE.setdefault(task.name, {"last_run_at": None, "last_count": 0, "last_error": None})


def iter_maintenance_tasks() -> tuple[MaintenanceTask, ...]:
    with _LOCK:
        return tuple(_TASKS)


def maintenance_state() -> dict:
    """{name: {"last_run_at": float|None, "last_count": int, "last_error": str|None}}"""
    with _LOCK:
        return {name: dict(info) for name, info in _STATE.items()}


def note_run(name: str, count: int, error: str | None = None) -> None:
    import time

    with _LOCK:
        _STATE[name] = {
            "last_run_at": time.time(),
            "last_count": int(count or 0),
            "last_error": error,
        }


def reset_for_tests() -> None:
    """Hook de test: vacia el registro. NO se llama en produccion."""
    with _LOCK:
        _TASKS.clear()
        _STATE.clear()
