"""tools/migrar_mantis_gitlab/retry.py — Plan 217 F8 (§9, C2).

Capa ADICIONAL de reintentos/pausas/circuit-breaker que **envuelve** las
llamadas del `DestinationWriter`/adapters del tool — **NO** importa ni
modifica `services/gitlab_client.py`. Ese cliente compartido YA lee
`Retry-After` y reintenta automáticamente en 429 dentro de `_request`
(`gitlab_client.py:146` aprox., C2 del plan, corregido en la crítica v2).
Este módulo es la pausa/reintento ADICIONAL y más conservadora que pide
§9 para corridas largas, y vive standalone: el futuro CLI (F9, otro batch)
la usa para envolver llamadas al `DestinationWriter`.

Prohibición dura de este batch: cero imports de `services.gitlab_client`
o `services.gitlab_provider` acá.
"""
from __future__ import annotations

import re
import time
from typing import Any, Callable

# Heurística best-effort (documentada, no exhaustiva): `TrackerApiError`/
# `MantisApiError` no siempre exponen el status code HTTP de forma
# estructurada al llegar hasta acá, así que se detecta "reintentable" por:
#   - tipo de excepción típico de timeout/conexión de red, o
#   - un código 5xx mencionado en el mensaje de la excepción (regex \b5\d{2}\b).
# 429 NO se contempla acá a propósito: eso ya lo maneja `gitlab_client`
# internamente (Retry-After), duplicarlo acá sería reintentar dos veces.
_RETRYABLE_5XX_RE = re.compile(r"\b5\d{2}\b")


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return True
    return bool(_RETRYABLE_5XX_RE.search(str(exc)))


def with_backoff(
    fn: Callable[..., Any],
    *args: Any,
    max_retries: int,
    backoff_seconds: "list[float]",
    sleep_fn: Callable[[float], None] = time.sleep,
    **kwargs: Any,
) -> Any:
    """Ejecuta `fn(*args, **kwargs)`. Si lanza una excepción "reintentable"
    (`_is_retryable`), espera `backoff_seconds[intento]` (o el último valor
    de la lista si se agotan) y reintenta, hasta `max_retries` veces; luego
    re-lanza la excepción ORIGINAL (nunca la enmascara). Excepciones no
    reintentables (ej. 401/403/404, §9 "errores no recuperables") se
    re-lanzan de inmediato, sin reintentar.

    `sleep_fn` es inyectable (default `time.sleep`) para que los tests no
    dependan de mockear el módulo `time` global — pasan una función que no
    duerme de verdad.
    """
    attempt = 0
    while True:
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            if not _is_retryable(exc) or attempt >= max_retries:
                raise
            wait = backoff_seconds[attempt] if attempt < len(backoff_seconds) else (
                backoff_seconds[-1] if backoff_seconds else 0.0
            )
            sleep_fn(wait)
            attempt += 1


def rate_limit_pause(seconds: float, sleep_fn: Callable[[float], None] = time.sleep) -> None:
    """Pausa configurable adicional (§9: "más conservadora que el
    Retry-After del server, para corridas largas"). `sleep_fn` inyectable
    por el mismo motivo que en `with_backoff`."""
    sleep_fn(seconds)


class CircuitBreaker:
    """§9 del plan: "si más de N ops consecutivas fallan, la corrida se
    pausa y pide confirmación al operador". Esta clase SOLO expone el
    estado (`is_open`) — el "pedir confirmación" es interacción de CLI
    (F9, otro batch); el caller decide qué hacer cuando `is_open` es
    `True` (ej. abortar, o preguntarle al operador si continúa)."""

    def __init__(self, threshold: int = 10) -> None:
        self.threshold = threshold
        self._consecutive_failures = 0

    def record_failure(self) -> None:
        self._consecutive_failures += 1

    def record_success(self) -> None:
        self._consecutive_failures = 0

    @property
    def is_open(self) -> bool:
        return self._consecutive_failures >= self.threshold


__all__ = ["CircuitBreaker", "rate_limit_pause", "with_backoff"]
