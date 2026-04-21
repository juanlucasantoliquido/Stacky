"""
auto_enter_audit.py — Audit log persistente JSONL para el AutoEnterDaemon.

Un registro por cada intento de pulsación (OK o fail). Rotación diaria con
14 días de retención vía ``logging.handlers.TimedRotatingFileHandler``.

API pública:
    record(method, ok, reason, **kwargs)

Archivo destino: ``data/auto_enter_audit_YYYY-MM-DD.jsonl``.
Thread-safe: el handler serializa writes con su propio lock interno más
un ``threading.Lock`` aditivo para envolver la serialización del payload.
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

__all__ = ["record"]

_BASE_DIR   = Path(__file__).resolve().parent
_DATA_DIR   = _BASE_DIR / "data"
_FILE_STEM  = "auto_enter_audit"
_RETENTION  = 14

_logger: logging.Logger | None = None
_init_lock  = threading.Lock()
_write_lock = threading.Lock()


def _iso_utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + \
           f"{datetime.now(timezone.utc).microsecond // 1000:03d}Z"


def _get_logger() -> logging.Logger:
    """Inicialización lazy del logger con TimedRotatingFileHandler."""
    global _logger
    if _logger is not None:
        return _logger
    with _init_lock:
        if _logger is not None:
            return _logger

        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        base_path = _DATA_DIR / f"{_FILE_STEM}.jsonl"

        lg = logging.getLogger("stacky.auto_enter.audit")
        lg.setLevel(logging.INFO)
        lg.propagate = False  # no mezclar con el logger root

        # Si alguien ya lo inicializó (hot-reload), reusar
        if not lg.handlers:
            handler = logging.handlers.TimedRotatingFileHandler(
                filename    = str(base_path),
                when        = "midnight",
                interval    = 1,
                backupCount = _RETENTION,
                encoding    = "utf-8",
                delay       = True,
                utc         = True,
            )
            # Sufijo del backup: .jsonl.YYYY-MM-DD
            handler.suffix = "%Y-%m-%d"
            handler.setFormatter(logging.Formatter("%(message)s"))
            lg.addHandler(handler)

        _logger = lg
        return _logger


def record(method: str, ok: bool, reason: str, **kwargs: Any) -> None:
    """
    Registra un intento de pulsación en el audit log JSONL.

    Campos:
        method           — "bridge" | "sendinput" | "dry_run"
        ok               — bool
        reason           — etiqueta corta ("bridge_ok", "not_foreground", ...)
        foreground_title — título de la ventana en foreground al momento
        elapsed_ms       — int
        total_ok_running — contador acumulado global
        dry_run          — bool
        guard_matched    — label del regex que matcheó (si aplica)
        execution_id     — UUID del ActionContext activo (si aplica)
    """
    try:
        payload: dict[str, Any] = {
            "ts":     _iso_utc_now(),
            "method": method,
            "ok":     bool(ok),
            "reason": reason,
        }
        # Merge de kwargs, omitiendo None
        for k, v in kwargs.items():
            if v is not None:
                payload[k] = v

        line = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        with _write_lock:
            _get_logger().info(line)
    except Exception as exc:  # pragma: no cover - defensive
        # Nunca romper al caller — solo dejar rastro en el logger principal
        logging.getLogger("stacky.auto_enter").debug(
            "[AutoEnterAudit] record falló: %s", exc,
        )
