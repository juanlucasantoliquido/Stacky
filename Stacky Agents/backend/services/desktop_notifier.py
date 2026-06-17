"""C10 — Desktop notifications.

Capa fina sobre `plyer` o `win10toast` (opcional). El backend la usa para
disparar notificaciones nativas cuando un ticket asignado al operador cambia
a un estado relevante (p.ej. "Ready for QA").

Si la dependencia opcional no está instalada o el SO no soporta toasts, las
llamadas se vuelven no-op silenciosos. La feature siempre es opt-in vía
`STACKY_DESKTOP_NOTIFY=true` para no spamear devs que no quieren.
"""
from __future__ import annotations

import logging
import os
import threading
from typing import Iterable

logger = logging.getLogger("stacky.desktop_notifier")

_NOTIFIER = None
_NOTIFIER_LOCK = threading.Lock()


def _get_notifier():
    """Resuelve un backend de notif disponible. Lazy + cached.

    Orden de preferencia:
      1) plyer.notification  (cross-platform, sin permisos extra)
      2) win10toast          (sólo Windows, soporta callback en click)
      3) None                (no-op)
    """
    global _NOTIFIER
    if _NOTIFIER is not None:
        return _NOTIFIER
    with _NOTIFIER_LOCK:
        if _NOTIFIER is not None:
            return _NOTIFIER
        try:
            from plyer import notification as plyer_notification  # type: ignore
            _NOTIFIER = ("plyer", plyer_notification)
            return _NOTIFIER
        except Exception:
            pass
        try:
            from win10toast import ToastNotifier  # type: ignore
            _NOTIFIER = ("win10toast", ToastNotifier())
            return _NOTIFIER
        except Exception:
            pass
        _NOTIFIER = ("noop", None)
        return _NOTIFIER


def is_enabled() -> bool:
    raw = os.getenv("STACKY_DESKTOP_NOTIFY_ENABLED")
    if raw is None:
        raw = os.getenv("STACKY_DESKTOP_NOTIFY", "false")
    return str(raw).lower() in {"1", "true", "yes"}


def notify(title: str, message: str, *, app_name: str = "Stacky Agents", timeout_sec: int = 6) -> bool:
    """Envía una notif. Retorna True si fue despachada; False si no-op."""
    if not is_enabled():
        return False
    kind, impl = _get_notifier()
    if impl is None:
        return False
    try:
        if kind == "plyer":
            impl.notify(
                title=title[:200],
                message=message[:400],
                app_name=app_name,
                timeout=timeout_sec,
            )
            return True
        if kind == "win10toast":
            impl.show_toast(title[:64], message[:200], duration=timeout_sec, threaded=True)
            return True
    except Exception as exc:
        logger.warning("desktop notify failed: %s", exc)
    return False


def notify_ticket_transition(*, ado_id: int | str, title: str, new_state: str) -> bool:
    """Helper específico para transiciones de ADO relevantes."""
    return notify(
        title=f"T-{ado_id} listo para {new_state}",
        message=title[:240],
        timeout_sec=8,
    )
