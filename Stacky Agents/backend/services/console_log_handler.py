"""console_log_handler.py — captura logs Python del root logger y los persiste en SystemLog.

Usa una queue + hilo worker para que el handler no bloquee el hilo principal.
Se instala una sola vez en create_app() después de init_db().
"""
from __future__ import annotations

import logging
import queue
import threading
from datetime import datetime

_install_lock = threading.Lock()
_installed = False

# Loggers cuyo output debe ser ignorado para evitar recursión
_IGNORED_LOGGERS = {
    "stacky_agents.console_log_handler",
    "sqlalchemy.engine",
    "sqlalchemy.pool",
    "sqlalchemy.orm",
}


class _SystemLogHandler(logging.Handler):
    """Handler que encola records y los persiste en SystemLog vía worker thread."""

    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self._queue: queue.Queue[logging.LogRecord | None] = queue.Queue(maxsize=2000)
        self._thread = threading.Thread(target=self._worker, daemon=True, name="console-log-handler")
        self._thread.start()

    def emit(self, record: logging.LogRecord) -> None:
        # Evitar recursión — si el logger viene de SQLAlchemy o de nosotros mismos
        if record.name in _IGNORED_LOGGERS or record.name.startswith("sqlalchemy"):
            return
        try:
            self._queue.put_nowait(record)
        except queue.Full:
            pass  # Silenciar si la queue está llena

    def _worker(self) -> None:
        # Importamos aquí para evitar imports circulares en el arranque
        from db import SessionLocal
        from models import SystemLog

        while True:
            record = self._queue.get()
            if record is None:
                break
            try:
                level_map = {
                    logging.DEBUG: "DEBUG",
                    logging.INFO: "INFO",
                    logging.WARNING: "WARNING",
                    logging.ERROR: "ERROR",
                    logging.CRITICAL: "CRITICAL",
                }
                level_str = level_map.get(record.levelno, "INFO")
                message = self.format(record)
                with SessionLocal() as session:
                    log = SystemLog(
                        timestamp=datetime.utcfromtimestamp(record.created),
                        level=level_str,
                        source="console",
                        action=record.name[:120],
                        context_json=message[:16000],
                    )
                    session.add(log)
                    session.commit()
            except Exception:
                pass  # No propagar errores del handler


def install_console_log_handler() -> None:
    """Instala el handler en el root logger exactamente una vez."""
    global _installed
    with _install_lock:
        if _installed:
            return
        handler = _SystemLogHandler()
        from services.local_file_logging import _AnsiStrippingFormatter, _strip_ansi_enabled  # lazy

        fmt_cls = _AnsiStrippingFormatter if _strip_ansi_enabled() else logging.Formatter
        formatter = fmt_cls("%(asctime)s [%(name)s] %(message)s")
        handler.setFormatter(formatter)
        logging.getLogger().addHandler(handler)
        _installed = True
