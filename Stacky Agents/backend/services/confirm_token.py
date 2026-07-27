"""Plan 253 F6 — interlock de confirmacion para acciones destructivas.

NO ES SEGURIDAD. Stacky es mono-operador sin login: `current_user` es un
encabezado sin validar y no existe un 403 real. Esto es un interlock
ANTI-CLIC-ACCIDENTAL que transporta el conteo exacto que se le mostro al
operador, para que no pueda confirmar una cifra distinta de la que vio.
Quien lo lea buscando un control de acceso, no lo encontro.

Modulo COMPARTIDO y generico: los planes hermanos (256 y 258) lo importan tal
cual para sus propios interlocks; no lo reimplementan.

Sin persistencia a proposito: si el proceso se reinicia, el operador vuelve a
pedir el diagnostico. Es lo correcto — el conteo cambio.
"""
from __future__ import annotations

import secrets
import threading
import time

DEFAULT_TTL_S = 120.0

_LOCK = threading.Lock()
# token -> {"action": str, "payload": dict, "expires_at": float}
_TOKENS: dict[str, dict] = {}


class ConfirmTokenError(Exception):
    """El identificador no existe, ya se uso, vencio o es de otra accion."""


def _purge_expired(now: float) -> None:
    """Se llama SIEMPRE con _LOCK tomado."""
    vencidos = [t for t, info in _TOKENS.items() if info["expires_at"] <= now]
    for t in vencidos:
        _TOKENS.pop(t, None)


def issue_token(action: str, payload: dict, ttl_s: float = DEFAULT_TTL_S) -> str:
    """Emite un identificador efimero atado a (action, payload). En memoria del proceso."""
    if not action:
        raise ValueError("action es obligatoria")
    token = secrets.token_urlsafe(24)
    now = time.time()
    with _LOCK:
        _purge_expired(now)
        _TOKENS[token] = {
            "action": str(action),
            "payload": dict(payload or {}),
            "expires_at": now + float(ttl_s),
        }
    return token


def consume_token(action: str, token: str) -> dict:
    """Devuelve el payload y lo invalida (un solo uso).

    Levanta ConfirmTokenError si no existe, ya se uso, vencio o la accion no coincide.
    """
    now = time.time()
    with _LOCK:
        _purge_expired(now)
        info = _TOKENS.pop(token or "", None)
    if info is None:
        raise ConfirmTokenError("confirmacion inexistente, ya usada o vencida")
    if info["action"] != str(action):
        raise ConfirmTokenError(
            f"la confirmacion es de otra accion ({info['action']!r}, se esperaba {action!r})"
        )
    if info["expires_at"] <= now:
        raise ConfirmTokenError("la confirmacion vencio")
    return dict(info["payload"])


def expire_token_for_tests(token: str) -> None:
    """Hook de test: fuerza el vencimiento sin esperar el TTL real."""
    with _LOCK:
        if token in _TOKENS:
            _TOKENS[token]["expires_at"] = time.time() - 1.0


def reset_for_tests() -> None:
    """Hook de test: vacia el registro. NO se llama en produccion."""
    with _LOCK:
        _TOKENS.clear()
