"""
error_classifier.py — Clasifica excepciones en categorías semánticas y genera
mensajes user-friendly para mostrar en el dashboard.

Las categorías se usan en:
  - PipelineEvent.error_kind (JSONL)
  - slog.error_classified(...)
  - franja roja del dashboard (por ticket)
  - state.json → tickets[<id>].last_error.error_kind

Convención de clasificación (en orden de precedencia):

    auth       — HTTP 401/403, credenciales, token vencido
    network    — socket timeouts, DNS, conexión rechazada
    technical  — subprocess, ImportError, errores de Python
    functional — archivo esperado no está en workspace del ticket
    data       — ValidationError de pydantic en prompts/outputs
    user       — PermissionError (permisos FS del usuario)
    technical  — default para cualquier otro Exception
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Literal

logger = logging.getLogger("stacky.errors")

ErrorKind = Literal["technical", "functional", "auth", "network", "data", "user"]

# ── Mensajes user-friendly por categoría ─────────────────────────────────────
_USER_FRIENDLY_TEMPLATES: dict[ErrorKind, str] = {
    "auth":       "Problema de autenticación con {service}. Revisá credenciales / token.",
    "network":    "No se pudo contactar a {service}. Verificá conectividad / VPN.",
    "technical":  "Error técnico en {action}. Revisá el log para detalle.",
    "functional": "Falta un archivo esperado del ticket ({detail}). Verificá la carpeta.",
    "data":       "Los datos generados por el agente no cumplen el formato esperado.",
    "user":       "Sin permisos para operar sobre {detail}. Revisá ACLs / antivirus.",
}


def classify_exception(
    exc: BaseException,
    *,
    ticket_folder: str | None = None,
    action: str | None = None,
) -> ErrorKind:
    """
    Clasifica una excepción en una de las categorías de ``ErrorKind``.

    La precedencia está pensada para que errores "amigables para el usuario"
    (auth/network/functional) ganen sobre ``technical`` (default).
    """
    # Auth → HTTP 401/403 por urllib o requests
    if _is_http_auth_error(exc):
        return "auth"

    # Network
    if _is_network_error(exc):
        return "network"

    # Pydantic ValidationError → data
    if _is_validation_error(exc):
        return "data"

    # subprocess.CalledProcessError → technical (explícito antes del default)
    import subprocess as _sp
    if isinstance(exc, _sp.CalledProcessError):
        return "technical"

    # FileNotFoundError dentro del workspace del ticket → functional
    if isinstance(exc, FileNotFoundError) and ticket_folder:
        return "functional" if _path_inside(ticket_folder, getattr(exc, "filename", None)) else "technical"

    # PermissionError → user (problema de permisos del usuario / antivirus)
    if isinstance(exc, PermissionError):
        return "user"

    # ImportError / ModuleNotFoundError → technical
    if isinstance(exc, (ImportError, ModuleNotFoundError)):
        return "technical"

    return "technical"


def friendly_message(
    exc: BaseException,
    *,
    kind: ErrorKind | None = None,
    action: str | None = None,
    service: str | None = None,
    ticket_folder: str | None = None,
) -> str:
    """Genera un mensaje user-friendly a partir de una excepción."""
    kind = kind or classify_exception(exc, ticket_folder=ticket_folder, action=action)

    # Service inference
    if service is None:
        service = _infer_service(exc)

    detail = ""
    if isinstance(exc, FileNotFoundError):
        detail = getattr(exc, "filename", None) or str(exc)
    elif isinstance(exc, PermissionError):
        detail = getattr(exc, "filename", None) or str(exc)
    elif action:
        detail = action

    template = _USER_FRIENDLY_TEMPLATES.get(kind, _USER_FRIENDLY_TEMPLATES["technical"])
    try:
        return template.format(
            service=service or "servicio externo",
            action=action or "la acción",
            detail=detail or "archivo",
        )
    except Exception:
        return template


# ── Helpers privados ─────────────────────────────────────────────────────────

def _is_http_auth_error(exc: BaseException) -> bool:
    """Detecta HTTP 401/403 en requests, urllib, httpx."""
    # requests.HTTPError → .response.status_code
    resp = getattr(exc, "response", None)
    status = getattr(resp, "status_code", None) or getattr(resp, "status", None)
    if status in (401, 403):
        return True

    # urllib.error.HTTPError → .code
    code = getattr(exc, "code", None)
    if code in (401, 403):
        return True

    # Heurística por mensaje (último recurso)
    msg = str(exc)
    if re.search(r"\b(401|403)\b", msg) and re.search(r"(unauthorized|forbidden)", msg, re.I):
        return True
    return False


def _is_network_error(exc: BaseException) -> bool:
    """Detecta errores de red (connection refused, DNS, timeout de socket)."""
    # requests.ConnectionError / Timeout — por nombre de clase (evita import duro)
    cls_name = type(exc).__name__
    if cls_name in {"ConnectionError", "ConnectionResetError", "ConnectionRefusedError",
                    "ConnectionAbortedError", "Timeout", "ConnectTimeout",
                    "ReadTimeout", "NewConnectionError"}:
        return True

    # urllib.error.URLError (envuelve casi siempre problemas de red)
    if cls_name == "URLError":
        return True

    # socket.timeout, socket.gaierror
    import socket
    if isinstance(exc, (socket.timeout, socket.gaierror, ConnectionError)):
        return True

    # TimeoutError builtin
    if isinstance(exc, TimeoutError):
        return True

    return False


def _is_validation_error(exc: BaseException) -> bool:
    """Detecta pydantic.ValidationError sin import duro (soporta v1 y v2)."""
    if type(exc).__name__ == "ValidationError":
        mod = type(exc).__module__ or ""
        if mod.startswith("pydantic"):
            return True
    # pydantic_core en v2 también puede levantar
    if type(exc).__name__ == "ValidationError" and "pydantic" in (type(exc).__module__ or ""):
        return True
    return False


def _path_inside(base: str | os.PathLike[str], target: str | None) -> bool:
    if not target:
        return False
    try:
        bp = Path(base).resolve()
        tp = Path(target).resolve()
        return bp in tp.parents or bp == tp.parent or bp == tp
    except Exception:
        return False


def _infer_service(exc: BaseException) -> str | None:
    """Infiere el servicio afectado desde URL / atributo request.url."""
    # requests → .request.url
    req = getattr(exc, "request", None)
    url = getattr(req, "url", None) or getattr(exc, "url", None)
    if not url:
        msg = str(exc)
        m = re.search(r"https?://([^/\s]+)", msg)
        if m:
            url = m.group(0)
    if url:
        m = re.search(r"https?://([^/\s]+)", str(url))
        if m:
            return m.group(1)
    return None
