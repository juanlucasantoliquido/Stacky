"""I3.2 — Caché en memoria de lecturas caras de ADO con invalidación.

Singleton por proceso: `_singleton` (instancia de `ADoReadCache`).

Contrato:
  - `get_or_fetch(key, fetch_fn, ttl_sec)` — hit/miss por TTL.
    TTL 0 → siempre llama a fetch_fn (byte-idéntico al comportamiento sin caché).
  - `invalidate(ado_id)` — invalida todas las entradas cuyo campo key[1] == str(ado_id).
  - `is_warm(key)` — True si la entrada existe y no expiró.
  - `clear()` — limpia todo (para tests / reinicio).

Thread-safe con `threading.Lock`. El lock NO se sostiene durante la I/O de fetch_fn
(lock-free fetch, luego lock para escribir el resultado).

Flags: `STACKY_ADO_READ_CACHE_TTL_SEC` (int, default 0 = sin caché).
"""
from __future__ import annotations

import threading
import time
from typing import Any, Callable


class ADoReadCache:
    """Caché en memoria con TTL por entrada."""

    def __init__(self) -> None:
        self._cache: dict[tuple, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def get_or_fetch(
        self,
        key: tuple,
        fetch_fn: Callable[[], Any],
        ttl_sec: int,
    ) -> Any:
        """Retorna valor cacheado o llama a fetch_fn y lo almacena.

        Si ttl_sec <= 0 → siempre llama a fetch_fn (no-op del caché).
        El lock se libera antes de llamar a fetch_fn para no bloquear I/O.
        Si fetch_fn lanza, la excepción se propaga y NO se guarda en caché.
        """
        if ttl_sec <= 0:
            return fetch_fn()

        now = time.monotonic()
        with self._lock:
            entry = self._cache.get(key)
            if entry is not None and entry["expires_at"] > now:
                return entry["value"]

        # Fetch sin lock (puede ser I/O)
        value = fetch_fn()

        with self._lock:
            # Escribir aunque otra thread haya llenado mientras tanto (idempotente)
            self._cache[key] = {"value": value, "expires_at": now + ttl_sec}
        return value

    def invalidate(self, ado_id: str | int) -> None:
        """Invalida todas las entradas de un ado_id (key[1] == str(ado_id))."""
        target = str(ado_id)
        with self._lock:
            keys_to_del = [
                k for k in self._cache
                if len(k) >= 2 and str(k[1]) == target
            ]
            for k in keys_to_del:
                del self._cache[k]

    def is_warm(self, key: tuple) -> bool:
        """True si la entrada existe y no ha expirado."""
        now = time.monotonic()
        with self._lock:
            entry = self._cache.get(key)
            return entry is not None and entry["expires_at"] > now

    def clear(self) -> None:
        """Vacía el caché (para tests y reinicios)."""
        with self._lock:
            self._cache.clear()

    def size(self) -> int:
        """Número de entradas actualmente en caché (incluyendo expiradas)."""
        with self._lock:
            return len(self._cache)


# Singleton por proceso
_singleton = ADoReadCache()


# Funciones de conveniencia sobre el singleton

def get_or_fetch(key: tuple, fetch_fn: Callable[[], Any], ttl_sec: int = 0) -> Any:
    return _singleton.get_or_fetch(key, fetch_fn, ttl_sec)


def invalidate(ado_id: str | int) -> None:
    _singleton.invalidate(ado_id)


def is_warm(key: tuple) -> bool:
    return _singleton.is_warm(key)


def clear() -> None:
    _singleton.clear()
