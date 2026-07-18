"""Plan 163 F3 — evento de shutdown estructurado en system_logs.

Escribe UNA fila al apagarse el proceso grácilmente (atexit / SIGTERM / SIGINT).
Escritura SINCRONA en el main thread (mismo patron seguro que
stacky_logger._flush_on_exit). Un kill -9 / corte de energia NO dispara nada:
eso es fisica, no un bug (ver plan, principio 7)."""
from __future__ import annotations

import atexit
import json
import logging
import os

logger = logging.getLogger("stacky.services.lifecycle_log")

_LOGGED = False       # idempotencia: una sola fila por proceso
_INSTALLED = False    # registrar hooks una sola vez


def log_shutdown(reason: str) -> None:
    """Escribe (una sola vez) la fila de shutdown. Nunca lanza (no bloquea el apagado)."""
    global _LOGGED
    if _LOGGED:
        return
    _LOGGED = True
    try:
        from db import session_scope
        from models import SystemLog
        from services.app_version import get_app_version, get_source_commit
        ctx = json.dumps({
            "reason": reason,
            "pid": os.getpid(),
            "version": get_app_version(),
            "source_commit": get_source_commit(),
        })
        with session_scope() as session:
            session.add(SystemLog(
                level="INFO", source="app_lifecycle", action="shutdown", context_json=ctx,
            ))
    except Exception as exc:  # noqa: BLE001 — jamas bloquear el apagado
        logger.debug("lifecycle_log: no se pudo registrar shutdown: %s", exc)


def _in_test_mode() -> bool:
    """C2: misma llave unica de pytest que app.py:530 y el plan del arnes veraz."""
    return os.environ.get("STACKY_TEST_MODE", "").strip().lower() in ("1", "true", "yes")


def install_shutdown_hook() -> None:
    """Registra atexit (siempre) + SIGTERM/SIGINT (best-effort). Idempotente.

    C2: NO-OP bajo STACKY_TEST_MODE — pytest no debe quedar con atexit ni con
    los handlers de senal reemplazados, ni escribir filas shutdown espurias.
    Los tests ejercitan log_shutdown() directo."""
    global _INSTALLED
    if _in_test_mode():
        return
    if _INSTALLED:
        return
    _INSTALLED = True
    atexit.register(lambda: log_shutdown("atexit"))
    try:
        import signal
        for sig in (signal.SIGTERM, signal.SIGINT):
            prev = signal.getsignal(sig)

            def _handler(signum, frame, _prev=prev):
                log_shutdown(f"signal:{signum}")
                if callable(_prev) and _prev not in (signal.SIG_DFL, signal.SIG_IGN):
                    _prev(signum, frame)
                else:
                    raise SystemExit(0)

            signal.signal(sig, _handler)
    except (ValueError, OSError) as exc:  # no es main thread / SIGTERM limitado en Windows
        logger.debug("lifecycle_log: signals no instalables: %s", exc)
