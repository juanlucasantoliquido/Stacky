"""
auto_enter_watchdog.py — Monitor externo del AutoEnterDaemon.

Cada 30s valida:
    - Que el thread del daemon siga vivo cuando enabled=True (auto-relaunch).
    - Que la última pulsación OK no esté estancada (stalled).
    - Que el bridge HTTP (:5051/health) responda (bridge_down/up).
    - Expira dry_run_expires_at y emite ``auto_enter_dry_run_expired``.

No toca el daemon directamente salvo para relanzar el thread; siempre usa la
API pública del daemon. Emite eventos al bus y, en casos warning/error,
también dispara ``notifier.notify`` para que aparezca en NOTIFICATIONS.json.
"""

from __future__ import annotations

import logging
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from auto_enter_daemon import AutoEnterDaemon

logger = logging.getLogger("stacky.auto_enter.watchdog")

# ── Defensive imports de observabilidad ──────────────────────────────────────
try:
    from pipeline_events import emit as _emit_event
    _HAS_EVENTS = True
except Exception:  # pragma: no cover - defensive
    _emit_event = None  # type: ignore[assignment]
    _HAS_EVENTS = False

try:
    from notifier import notify as _notifier_notify
except Exception:  # pragma: no cover - defensive
    _notifier_notify = None  # type: ignore[assignment]

try:
    import auto_enter_guard as _guard
except Exception:  # pragma: no cover - defensive
    _guard = None  # type: ignore[assignment]


# ── Config del watchdog ──────────────────────────────────────────────────────
WATCHDOG_INTERVAL     = 30.0   # s
STALLED_FACTOR        = 3.0    # stalled si seconds_since_last_ok > factor * interval
RELAUNCH_BACKOFFS     = (1.0, 2.0, 5.0, 10.0, 30.0)  # tope 3 intentos de relaunch
MAX_RELAUNCH_ATTEMPTS = 3


# ── Helpers ──────────────────────────────────────────────────────────────────

def _safe_emit(kind: str, **kwargs) -> None:
    if not _HAS_EVENTS or _emit_event is None:
        return
    try:
        _emit_event(kind=kind, **kwargs)  # type: ignore[arg-type]
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("[AutoEnterWatchdog] emit %s falló: %s", kind, e)


def _safe_notify(title: str, message: str, level: str = "warning") -> None:
    if _notifier_notify is None:
        return
    try:
        _notifier_notify(title, message, level=level)
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("[AutoEnterWatchdog] notify falló: %s", e)


def _bridge_health(port: int) -> bool:
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/health", method="GET",
        )
        with urllib.request.urlopen(req, timeout=2) as resp:
            import json
            body = json.loads(resp.read().decode("utf-8"))
            return bool(body.get("ok"))
    except (urllib.error.URLError, TimeoutError, OSError):
        return False
    except Exception:
        return False


# ── Watchdog core ────────────────────────────────────────────────────────────

class AutoEnterWatchdog:
    """Thread daemon que monitorea el estado del AutoEnterDaemon."""

    def __init__(self, daemon: "AutoEnterDaemon") -> None:
        self._daemon = daemon
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._bridge_was_up: Optional[bool] = None     # None = aún no medido
        self._stalled_flagged: bool = False
        self._relaunch_attempts: int = 0
        self._last_dry_run_expired_emit: Optional[datetime] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="auto-enter-watchdog",
        )
        self._thread.start()
        logger.info("[AutoEnterWatchdog] iniciado (interval=%.0fs)", WATCHDOG_INTERVAL)

    def stop(self) -> None:
        self._stop_event.set()

    # ── Internals ────────────────────────────────────────────────────────

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._tick()
            except Exception as exc:  # pragma: no cover - defensive
                logger.debug("[AutoEnterWatchdog] tick falló: %s", exc)
            if self._stop_event.wait(timeout=WATCHDOG_INTERVAL):
                return

    def _tick(self) -> None:
        d = self._daemon

        # 1) Bridge health transitions
        bridge_now = _bridge_health(d.bridge_port)
        if self._bridge_was_up is None:
            # primera medición: solo guardar estado
            self._bridge_was_up = bridge_now
        elif self._bridge_was_up and not bridge_now:
            logger.warning("[AutoEnterWatchdog] bridge DOWN")
            _safe_emit("notification",
                       action="auto_enter_bridge_down",
                       message="Bridge HTTP no responde")
            _safe_notify("Stacky AutoEnter — Bridge DOWN",
                         "El bridge HTTP (:5051/health) dejó de responder",
                         level="warning")
            self._bridge_was_up = False
        elif not self._bridge_was_up and bridge_now:
            logger.info("[AutoEnterWatchdog] bridge UP")
            _safe_emit("notification",
                       action="auto_enter_bridge_up",
                       message="Bridge HTTP recuperado")
            self._bridge_was_up = True

        # 2) Thread vivo pero enabled=True → relaunch con backoff
        if d.enabled and not d.thread_alive and not d.panic_active:
            self._attempt_relaunch()
        elif d.thread_alive:
            # Reset de reintentos cuando volvió a estar vivo
            self._relaunch_attempts = 0

        # 3) Stalled detection (solo si enabled)
        if d.enabled and d.thread_alive:
            last_ok = d.last_press_ok_ts
            now = datetime.now(timezone.utc)
            if last_ok is not None:
                seconds_since = (now - last_ok.astimezone(timezone.utc)).total_seconds()
                threshold = d.interval * STALLED_FACTOR
                if seconds_since > threshold and not self._stalled_flagged:
                    self._stalled_flagged = True
                    logger.warning(
                        "[AutoEnterWatchdog] STALLED — %.0fs sin pulsación OK (umbral %.0fs)",
                        seconds_since, threshold,
                    )
                    _safe_emit(
                        "notification",
                        action="auto_enter_stalled",
                        message=f"Sin pulsación OK en {seconds_since:.0f}s",
                        detail=f"fg={d.last_foreground_title or 'unknown'} "
                               f"consecutive_failures={d.consecutive_failures}",
                    )
                    _safe_notify(
                        "Stacky AutoEnter — STALLED",
                        f"Sin pulsación OK hace {seconds_since:.0f}s. "
                        f"Ventana activa: {d.last_foreground_title or 'desconocida'}",
                        level="warning",
                    )
                elif seconds_since <= threshold and self._stalled_flagged:
                    # Recuperado: desmarcar para permitir una nueva alerta
                    self._stalled_flagged = False

        # 4) Dry-run expirado
        if _guard is not None:
            try:
                if _guard.dry_run_expired():
                    # Emitir una vez cada 30 min para no inundar
                    now = datetime.now(timezone.utc)
                    last = self._last_dry_run_expired_emit
                    if last is None or (now - last).total_seconds() >= 1800:
                        self._last_dry_run_expired_emit = now
                        logger.warning(
                            "[AutoEnterWatchdog] dry_run_expires_at ya pasó — revisar config.auto_approve"
                        )
                        _safe_emit(
                            "notification",
                            action="auto_enter_dry_run_expired",
                            message="dry_run_expires_at alcanzado — definir transición a modo real",
                        )
                        _safe_notify(
                            "Stacky AutoEnter — dry_run expirado",
                            "Decidir si pasar dry_run=false en config.json.auto_approve",
                            level="warning",
                        )
            except Exception as e:  # pragma: no cover - defensive
                logger.debug("[AutoEnterWatchdog] dry_run check falló: %s", e)

    def _attempt_relaunch(self) -> None:
        if self._relaunch_attempts >= MAX_RELAUNCH_ATTEMPTS:
            logger.error(
                "[AutoEnterWatchdog] tope de %d relaunches alcanzado — dando up",
                MAX_RELAUNCH_ATTEMPTS,
            )
            _safe_emit("notification",
                       action="auto_enter_thread_crashed",
                       message="Watchdog agotó reintentos de relaunch",
                       error_kind="technical")
            _safe_notify(
                "Stacky AutoEnter — CRASH (relaunch agotado)",
                f"El watchdog intentó {self._relaunch_attempts} relaunches sin éxito.",
                level="error",
            )
            return

        backoff = RELAUNCH_BACKOFFS[min(self._relaunch_attempts, len(RELAUNCH_BACKOFFS) - 1)]
        self._relaunch_attempts += 1
        logger.warning(
            "[AutoEnterWatchdog] thread muerto con enabled=True — relaunch #%d tras %.1fs",
            self._relaunch_attempts, backoff,
        )
        time.sleep(backoff)
        try:
            self._daemon.start(interval_seconds=self._daemon.interval)
            _safe_emit(
                "notification",
                action="auto_enter_thread_restarted",
                message=f"Daemon relanzado (intento {self._relaunch_attempts})",
                detail=f"backoff={backoff}s",
            )
            _safe_notify(
                "Stacky AutoEnter — Daemon relanzado",
                f"Watchdog relanzó el daemon (intento {self._relaunch_attempts})",
                level="warning",
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("[AutoEnterWatchdog] relaunch falló: %s", exc)


# ── API pública ──────────────────────────────────────────────────────────────

_watchdog_instance: Optional[AutoEnterWatchdog] = None
_watchdog_lock = threading.Lock()


def start_watchdog(daemon: "AutoEnterDaemon") -> AutoEnterWatchdog:
    """Inicia el watchdog singleton ligado al daemon dado."""
    global _watchdog_instance
    with _watchdog_lock:
        if _watchdog_instance is None:
            _watchdog_instance = AutoEnterWatchdog(daemon)
            _watchdog_instance.start()
    return _watchdog_instance


def get_watchdog() -> Optional[AutoEnterWatchdog]:
    return _watchdog_instance
