"""V0.3 — Límite de concurrencia de runs CLI.

Contador global thread-safe (chequeo NO bloqueante). El launch llama
try_acquire() antes de spawnear; el runner llama release() en su finally.

Config: STACKY_MAX_CONCURRENT_RUNS (int, 0 = ilimitado, retro-compat).
El límite se lee en cada try_acquire() (call time) para respetar hot-apply
de flags sin reiniciar.
"""
from __future__ import annotations

import threading

_lock = threading.Lock()
_active = 0


def _limit() -> int:
    """Lee el límite vigente desde config (0 = ilimitado)."""
    try:
        from config import config

        return int(getattr(config, "STACKY_MAX_CONCURRENT_RUNS", 0) or 0)
    except Exception:
        return 0


def try_acquire() -> bool:
    """Intenta tomar un slot. False si activos >= límite. Límite 0 = siempre True."""
    global _active
    limit = _limit()
    with _lock:
        if limit > 0 and _active >= limit:
            return False
        _active += 1
        return True


def release() -> None:
    """Libera un slot. Idempotente en el piso (nunca negativo)."""
    global _active
    with _lock:
        if _active > 0:
            _active -= 1


def active_count() -> int:
    """Cantidad de slots activos actualmente."""
    with _lock:
        return _active


def _reset_for_tests() -> None:
    """Resetea el contador (solo para tests)."""
    global _active
    with _lock:
        _active = 0
