"""CONTRATO CONGELADO (Plan 145 F0). Helper stdlib-only de logging con dedup por
cambio de estado / rate-limit por intervalo. Consumido en 145 (agents_dir) y
disponible para MIGRACIÓN OPCIONAL de 147 (outputs_dir) y 148 (breaker).
No importar nada del repo (evita ciclos)."""
from __future__ import annotations

import logging
import threading
import time
from typing import Any

__all__ = ["log_state_change", "log_throttled", "warn_once", "reset"]

_lock = threading.Lock()
_last_state: dict[str, Any] = {}
_last_time: dict[str, float] = {}
_NEVER = object()  # sentinel "nunca logueado"


def log_state_change(key: str, state, logger: logging.Logger, level: int, msg: str, *args) -> bool:
    """Loguea msg%args a level solo si state difiere del último estado logueado bajo key."""
    with _lock:
        if _last_state.get(key, _NEVER) == state:
            return False
        _last_state[key] = state
    logger.log(level, msg, *args)  # fuera del lock: no bloquear en I/O
    return True


def log_throttled(key: str, logger: logging.Logger, level: int, msg: str, *args, min_interval_s: float = 60.0) -> bool:
    """Loguea a lo sumo una vez cada min_interval_s segundos por key."""
    now = time.monotonic()
    with _lock:
        last = _last_time.get(key)
        if last is not None and (now - last) < min_interval_s:
            return False
        _last_time[key] = now
    logger.log(level, msg, *args)
    return True


def warn_once(key: str, logger: logging.Logger, msg: str, *args) -> bool:
    """Conveniencia: WARNING exactamente una vez por proceso por key."""
    return log_state_change(key, True, logger, logging.WARNING, msg, *args)


def reset(key: str | None = None) -> None:
    """Hook de test: limpia estado (todo o una key). No se llama en producción."""
    with _lock:
        if key is None:
            _last_state.clear()
            _last_time.clear()
        else:
            _last_state.pop(key, None)
            _last_time.pop(key, None)
