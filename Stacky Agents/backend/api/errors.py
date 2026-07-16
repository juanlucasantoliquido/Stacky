"""Plan 149 — Taxonomía de errores tipados de la API + envelope canónico."""
from __future__ import annotations

from flask import g


class StackyApiError(Exception):
    http_status: int = 500
    error_type: str = "internal"

    def __init__(
        self,
        message: str,
        *,
        http_status: int | None = None,
        error_type: str | None = None,
        details: dict | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if http_status is not None:
            self.http_status = http_status
        if error_type is not None:
            self.error_type = error_type
        self.details = details or {}


class ValidationError(StackyApiError):
    http_status = 422
    error_type = "validation"


class ResourceNotFoundError(StackyApiError):
    http_status = 404
    error_type = "not_found"


class ConflictError(StackyApiError):
    http_status = 409
    error_type = "conflict"


class UpstreamError(StackyApiError):
    http_status = 502
    error_type = "upstream"


class IntegrationUnavailableError(StackyApiError):
    http_status = 503
    error_type = "integration_unavailable"


class InternalError(StackyApiError):
    http_status = 500
    error_type = "internal"


def set_exec_id(exec_id) -> None:
    """Correlación: el endpoint la llama cuando conoce su execution_id.

    Defensivo: fuera de un request context (g inaccesible) es un no-op silencioso
    (C6): asignar g.exec_id fuera de contexto lanza RuntimeError, que atrapamos.
    """
    try:
        g.exec_id = int(exec_id) if exec_id is not None else None
    except Exception:
        try:
            g.exec_id = None
        except Exception:
            pass  # sin request context → no-op


def build_error_envelope(
    *,
    error_type: str,
    message: str,
    request_id: str,
    exec_id,
    endpoint: str,
    method: str,
    details: dict | None = None,
) -> dict:
    # C2 BACKWARD-COMPAT: la clave `.error` CONSERVA la semántica legacy = mensaje
    # humano (hoy los consumidores que la muestran esperan un string legible como
    # "Internal server error"). El TOKEN de máquina va SOLO en `.error_type` (nuevo).
    # Así flag ON es superset puro: nunca cambia el significado de un campo existente.
    env = {
        "ok": False,
        "error": message,           # legacy: mensaje humano (idéntico a la forma OFF)
        "error_type": error_type,   # nuevo, explícito (token estable de máquina)
        "message": message,         # alias explícito de .error para consumidores nuevos
        "request_id": request_id or "",
        "exec_id": exec_id,
        "endpoint": endpoint,
        "method": method,
    }
    if details:
        env["details"] = details
    return env
