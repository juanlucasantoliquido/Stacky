"""
auto_enter_hotkey.py — Hotkey global para disparar el panic button.

Registra Ctrl+Alt+Shift+F12 (configurable) usando ``RegisterHotKey`` de user32.
Corre un message loop en un thread dedicado. Cuando detecta la combinación,
invoca ``AutoEnterDaemon.trigger_panic("hotkey")``.

Implementación en pywin32 puro (ctypes) para no agregar dependencias nuevas.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import logging
import threading
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from auto_enter_daemon import AutoEnterDaemon

logger = logging.getLogger("stacky.auto_enter.hotkey")

# Win32 constants
MOD_ALT          = 0x0001
MOD_CONTROL      = 0x0002
MOD_SHIFT        = 0x0004
MOD_NOREPEAT     = 0x4000
WM_HOTKEY        = 0x0312
VK_F12           = 0x7B
HOTKEY_ID        = 0xB0A4  # arbitrario, único dentro de este thread

DEFAULT_MODIFIERS = MOD_CONTROL | MOD_ALT | MOD_SHIFT | MOD_NOREPEAT
DEFAULT_VK        = VK_F12


class PanicHotkey:
    """Registra un hotkey global y llama al callback cuando se activa."""

    def __init__(
        self,
        daemon: "AutoEnterDaemon",
        modifiers: int = DEFAULT_MODIFIERS,
        vk: int = DEFAULT_VK,
    ) -> None:
        self._daemon = daemon
        self._modifiers = modifiers
        self._vk = vk
        self._thread: Optional[threading.Thread] = None
        self._started = False

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="auto-enter-panic-hotkey",
        )
        self._thread.start()

    # ── Win32 message loop ───────────────────────────────────────────────

    def _run(self) -> None:
        user32 = ctypes.windll.user32

        # RegisterHotKey debe llamarse desde el mismo thread que bombea mensajes.
        ok = user32.RegisterHotKey(None, HOTKEY_ID, self._modifiers, self._vk)
        if not ok:
            err = ctypes.get_last_error()
            logger.warning(
                "[PanicHotkey] RegisterHotKey falló (err=%d) — probablemente ya registrado",
                err,
            )
            return

        logger.info("[PanicHotkey] Ctrl+Alt+Shift+F12 registrado (panic button)")

        msg = ctypes.wintypes.MSG()
        try:
            while True:
                # GetMessage retorna 0 cuando WM_QUIT. Bloquea hasta recibir un mensaje.
                ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if ret == 0 or ret == -1:
                    break
                if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                    try:
                        logger.warning("[PanicHotkey] HOTKEY disparado — activando panic")
                        self._daemon.trigger_panic(reason="hotkey")
                    except Exception as exc:  # pragma: no cover - defensive
                        logger.error("[PanicHotkey] trigger_panic falló: %s", exc)
        finally:
            try:
                user32.UnregisterHotKey(None, HOTKEY_ID)
            except Exception:
                pass


# ── API pública ──────────────────────────────────────────────────────────────

_hotkey_instance: Optional[PanicHotkey] = None
_hotkey_lock = threading.Lock()


def start_panic_hotkey(daemon: "AutoEnterDaemon") -> Optional[PanicHotkey]:
    """
    Inicia el hotkey global. No-op fuera de Windows.
    Retorna la instancia o None si no se pudo iniciar.
    """
    global _hotkey_instance
    try:
        import sys
        if sys.platform != "win32":
            return None
        with _hotkey_lock:
            if _hotkey_instance is None:
                _hotkey_instance = PanicHotkey(daemon)
                _hotkey_instance.start()
        return _hotkey_instance
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("[PanicHotkey] no se pudo iniciar: %s", exc)
        return None
