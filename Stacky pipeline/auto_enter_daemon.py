"""
auto_enter_daemon.py — Daemon silencioso que presiona Ctrl+Enter en VS Code.

FUNCIÓN:
    Presiona Ctrl+Enter periódicamente en la ventana de VS Code activa.
    Útil para confirmar/continuar prompts en Copilot Chat cuando el agente
    está generando y necesita un "keep-alive" o trigger manual.

CONTROL DESDE DASHBOARD:
    - GET  /api/auto_enter/status        → estado actual (compat)
    - GET  /api/auto_enter/health        → health extendido (watchdog)
    - POST /api/auto_enter/enable        → activar (body: {"interval_seconds": 15})
    - POST /api/auto_enter/disable       → desactivar
    - POST /api/auto_enter/configure     → cambiar intervalo sin reiniciar
    - POST /api/auto_enter/panic         → kill-switch (pánico)
    - POST /api/auto_enter/panic/reset   → limpia pánico

LOGGING:
    Cada pulsación queda registrada en consola con timestamp y contador acumulado.
    Audit persistente en ``data/auto_enter_audit_YYYY-MM-DD.jsonl``.

USO DIRECTO:
    from auto_enter_daemon import get_auto_enter_daemon
    d = get_auto_enter_daemon()
    d.start(interval_seconds=15)
    d.stop()
"""

from __future__ import annotations

import logging
import threading
import time
import traceback
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("stacky.auto_enter")

# ─── Registro de pulsaciones (en memoria — para el endpoint de status) ────────
_press_log: list[dict] = []          # últimas N pulsaciones
_press_log_max = 200                 # cuántas guardar en el log circular
_press_log_lock = threading.Lock()
_total_presses_ok: int = 0           # contador real — nunca se trunca con el log
_total_presses_failed: int = 0

# Rate-limit del log de "no foreground" (inundación cuando VS Code no está al frente)
_last_no_foreground_log_ts: float = 0.0
_NO_FOREGROUND_LOG_INTERVAL = 60.0   # máximo un log cada 60s


# ─── Defensive imports (observabilidad aditiva) ──────────────────────────────
try:
    from pipeline_events import emit as _emit_event
    _HAS_EVENTS = True
except Exception:  # pragma: no cover - defensive
    _emit_event = None  # type: ignore[assignment]
    _HAS_EVENTS = False

try:
    from action_tracker import current_execution_id as _current_execution_id
except Exception:  # pragma: no cover - defensive
    _current_execution_id = lambda: None  # type: ignore[assignment]

try:
    import auto_enter_audit as _audit
except Exception:  # pragma: no cover - defensive
    _audit = None  # type: ignore[assignment]

try:
    import auto_enter_guard as _guard
except Exception:  # pragma: no cover - defensive
    _guard = None  # type: ignore[assignment]

try:
    from notifier import notify as _notifier_notify
except Exception:  # pragma: no cover - defensive
    _notifier_notify = None  # type: ignore[assignment]


def _safe_emit(kind: str, **kwargs) -> None:
    """Emite un PipelineEvent sin romper nunca al caller."""
    if not _HAS_EVENTS or _emit_event is None:
        return
    try:
        exec_id = _current_execution_id()
        _emit_event(
            kind=kind,  # type: ignore[arg-type]
            execution_id=exec_id,
            **kwargs,
        )
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("[AutoEnter] emit %s falló: %s", kind, e)


def _safe_notify(title: str, message: str, level: str = "warning") -> None:
    """Fire-and-forget hacia NOTIFICATIONS.json + toast/webhooks."""
    if _notifier_notify is None:
        return
    try:
        _notifier_notify(title, message, level=level)
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("[AutoEnter] notify falló: %s", e)


def _get_foreground_title() -> str:
    """Devuelve el título de la ventana en foreground (o '' si falla)."""
    try:
        import ctypes
        user32 = ctypes.windll.user32
        user32.GetForegroundWindow.restype = ctypes.c_void_p
        fg = user32.GetForegroundWindow()
        if not fg:
            return ""
        buf = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(ctypes.c_void_p(fg), buf, 512)
        return buf.value or ""
    except Exception:
        return ""


def _record_press(success: bool, method: str = "ui") -> None:
    """Registra una pulsación en el log en memoria y en consola."""
    global _press_log, _total_presses_ok, _total_presses_failed
    now = datetime.now()
    ts  = now.strftime("%Y-%m-%d %H:%M:%S")

    with _press_log_lock:
        if success:
            _total_presses_ok += 1
        else:
            _total_presses_failed += 1
        entry = {
            "timestamp": ts,
            "success":   success,
            "method":    method,
            "total_ok":  _total_presses_ok,
        }
        _press_log.append(entry)
        if len(_press_log) > _press_log_max:
            _press_log = _press_log[-_press_log_max:]

    # Console log — SIEMPRE visible
    status = "OK" if success else "FALLO"
    print(
        f"[AutoEnter] {ts} | Ctrl+Enter → {status} | "
        f"método={method} | total={entry['total_ok']}",
        flush=True,
    )
    if success:
        logger.info("[AutoEnter] %s | Ctrl+Enter presionado (%s) | total=%d",
                    ts, method, entry["total_ok"])
    else:
        logger.warning("[AutoEnter] %s | Ctrl+Enter FALLÓ (%s)", ts, method)


# ─────────────────────────────────────────────────────────────────────────────
# Implementaciones de la pulsación
# ─────────────────────────────────────────────────────────────────────────────

def _press_via_bridge(bridge_port: int) -> tuple[bool, str]:
    """
    Pide al bridge HTTP de VS Code que dispare workbench.action.chat.submit.
    Retorna (ok, reason) — reason ∈ {bridge_ok, bridge_404, bridge_timeout,
    bridge_error}.
    """
    try:
        import json
        import urllib.error
        import urllib.request
        req = urllib.request.Request(
            f"http://127.0.0.1:{bridge_port}/submit",
            data=b"",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return bool(body.get("ok")), "bridge_ok" if body.get("ok") else "bridge_error"
    except urllib.error.HTTPError as e:
        if e.code == 404:
            logger.debug("[AutoEnter] bridge /submit 404 — ¿extensión desactualizada?")
            return False, "bridge_404"
        logger.debug("[AutoEnter] bridge /submit HTTP %d", e.code)
        return False, "bridge_error"
    except urllib.error.URLError:
        return False, "bridge_timeout"
    except Exception as e:
        logger.debug("[AutoEnter] bridge /submit error: %s", e)
        return False, "bridge_error"


def _vscode_is_foreground() -> bool:
    """
    Retorna True si la ventana en foreground pertenece a VS Code.
    Compara por título — evita toda aritmética de HWND que falla en 64-bit.
    """
    try:
        title = _get_foreground_title()
        return "Visual Studio Code" in title
    except Exception:
        return False


def _sendinput_ctrl_enter() -> None:
    """Envía Ctrl+Enter al foco actual sin mover ventanas (SendInput)."""
    import ctypes

    INPUT_KEYBOARD  = 1
    VK_CONTROL      = 0x11
    VK_RETURN       = 0x0D
    KEYEVENTF_KEYUP = 0x0002

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk",         ctypes.c_ushort),
            ("wScan",       ctypes.c_ushort),
            ("dwFlags",     ctypes.c_ulong),
            ("time",        ctypes.c_ulong),
            ("dwExtraInfo", ctypes.c_ulong),
        ]

    class _INPUT_UNION(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT)]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", ctypes.c_ulong), ("_u", _INPUT_UNION)]

    def _make(vk: int, up: bool = False) -> INPUT:
        return INPUT(type=INPUT_KEYBOARD,
                     _u=_INPUT_UNION(ki=KEYBDINPUT(wVk=vk,
                                                   dwFlags=KEYEVENTF_KEYUP if up else 0)))

    seq = [
        _make(VK_CONTROL),
        _make(VK_RETURN),
        _make(VK_RETURN,  up=True),
        _make(VK_CONTROL, up=True),
    ]
    arr = (INPUT * len(seq))(*seq)
    ctypes.windll.user32.SendInput(len(seq), arr, ctypes.sizeof(INPUT))


def _press_via_sendinput() -> tuple[bool, str]:
    """
    Fallback SendInput. Retorna (ok, reason) — reason ∈
    {keypress_ok, not_foreground, sendinput_error}.
    """
    global _last_no_foreground_log_ts
    try:
        if not _vscode_is_foreground():
            now = time.monotonic()
            if (now - _last_no_foreground_log_ts) >= _NO_FOREGROUND_LOG_INTERVAL:
                _last_no_foreground_log_ts = now
                fg = _get_foreground_title()
                logger.warning(
                    "[AutoEnter] VS Code no es foreground — ventana activa: %r",
                    fg or "(desconocida)",
                )
            return False, "not_foreground"

        _sendinput_ctrl_enter()
        logger.debug("[AutoEnter] SendInput Ctrl+Enter OK")
        return True, "keypress_ok"

    except Exception as e:
        logger.debug("[AutoEnter] Error en SendInput: %s", e)
        return False, "sendinput_error"


# ─────────────────────────────────────────────────────────────────────────────
# AutoEnterDaemon
# ─────────────────────────────────────────────────────────────────────────────

class AutoEnterDaemon:
    """
    Hilo de fondo que presiona Ctrl+Enter cada N segundos en VS Code.

    Estado persistido en state/auto_enter.json para sobrevivir reinicios.
    """

    DEFAULT_INTERVAL = 15       # segundos
    MAX_CONSECUTIVE_EXC = 5     # después: backoff de 30s
    CRASH_THRESHOLD     = 20    # después: apagado duro

    def __init__(self, bridge_port: int = 5051):
        self._bridge_port  = bridge_port
        self._enabled      = False
        self._interval     = self.DEFAULT_INTERVAL
        self._thread: Optional[threading.Thread] = None
        self._stop_event   = threading.Event()
        self._lock         = threading.Lock()

        # Estado para observabilidad / watchdog
        self._last_press_ok_ts: Optional[datetime]  = None
        self._last_press_attempt_ts: Optional[datetime] = None
        self._consecutive_failures: int = 0
        self._consecutive_exceptions: int = 0
        self._last_foreground_title: str = ""

        # Kill-switch
        self._panic_active: bool = False
        self._panic_prev_enabled: bool = False

        # Inicializar guard config en disco (idempotente)
        if _guard is not None:
            try:
                _guard.ensure_defaults_persisted()
            except Exception as e:  # pragma: no cover - defensive
                logger.debug("[AutoEnter] ensure_defaults_persisted falló: %s", e)

    # ── API pública ───────────────────────────────────────────────────────

    def start(self, interval_seconds: int = None) -> None:
        """Activa el daemon con el intervalo dado (default 15s)."""
        with self._lock:
            if self._panic_active:
                logger.warning("[AutoEnter] No se puede activar: panic_active=True")
                return
            if interval_seconds is not None and interval_seconds > 0:
                self._interval = int(interval_seconds)
            self._enabled = True
            self._stop_event.clear()
            self._save_state()

            if self._thread and self._thread.is_alive():
                print(
                    f"[AutoEnter] Activado | intervalo={self._interval}s",
                    flush=True,
                )
                logger.info("[AutoEnter] Reconfigurado — intervalo=%ds", self._interval)
                return

            self._thread = threading.Thread(
                target=self._loop,
                daemon=True,
                name="auto-enter-daemon",
            )
            self._thread.start()
            print(
                f"[AutoEnter] Daemon iniciado | intervalo={self._interval}s | "
                f"bridge=:{self._bridge_port}",
                flush=True,
            )
            logger.info("[AutoEnter] Daemon iniciado — intervalo=%ds, bridge=:%d",
                        self._interval, self._bridge_port)

    def stop(self) -> None:
        """Desactiva el daemon. La próxima iteración del hilo verá el flag y saldrá."""
        with self._lock:
            self._enabled = False
            self._stop_event.set()
            self._save_state()
        print("[AutoEnter] Desactivado", flush=True)
        logger.info("[AutoEnter] Daemon desactivado")

    def configure(self, interval_seconds: int) -> None:
        """Cambia el intervalo sin detener el daemon."""
        if interval_seconds <= 0:
            raise ValueError("interval_seconds debe ser > 0")
        with self._lock:
            self._interval = int(interval_seconds)
            self._save_state()
        print(f"[AutoEnter] Intervalo actualizado → {self._interval}s", flush=True)
        logger.info("[AutoEnter] Intervalo cambiado a %ds", self._interval)

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def interval(self) -> int:
        return self._interval

    @property
    def bridge_port(self) -> int:
        return self._bridge_port

    @property
    def panic_active(self) -> bool:
        return self._panic_active

    @property
    def last_press_ok_ts(self) -> Optional[datetime]:
        return self._last_press_ok_ts

    @property
    def consecutive_failures(self) -> int:
        return self._consecutive_failures

    @property
    def last_foreground_title(self) -> str:
        return self._last_foreground_title

    @property
    def thread_alive(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def status(self) -> dict:
        """Estado completo para el dashboard (compat)."""
        with _press_log_lock:
            recent = list(_press_log[-10:])
            total  = _total_presses_ok
        return {
            "enabled":          self._enabled,
            "interval_seconds": self._interval,
            "bridge_port":      self._bridge_port,
            "thread_alive":     self.thread_alive,
            "total_presses":    total,
            "recent_presses":   recent,
            "panic_active":     self._panic_active,
        }

    def health(self) -> dict:
        """Health extendido para /api/auto_enter/health."""
        cfg = None
        dry_run = False
        if _guard is not None:
            try:
                cfg = _guard.load_config()
                dry_run = bool(cfg.dry_run)
            except Exception:
                pass

        with _press_log_lock:
            total_ok     = _total_presses_ok
            total_failed = _total_presses_failed

        now = datetime.now(timezone.utc)
        seconds_since_last_ok: Optional[float] = None
        last_ok_iso: Optional[str] = None
        if self._last_press_ok_ts is not None:
            last_ok_iso = self._last_press_ok_ts.astimezone(timezone.utc).isoformat()
            seconds_since_last_ok = (now - self._last_press_ok_ts.astimezone(timezone.utc)).total_seconds()

        # Bridge health (no-throw)
        bridge_up = False
        try:
            import urllib.request
            import json as _json
            req = urllib.request.Request(
                f"http://127.0.0.1:{self._bridge_port}/health",
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=2) as resp:
                body = _json.loads(resp.read().decode("utf-8"))
                bridge_up = bool(body.get("ok"))
        except Exception:
            bridge_up = False

        return {
            "enabled":                  self._enabled,
            "thread_alive":             self.thread_alive,
            "last_ok_ts":               last_ok_iso,
            "seconds_since_last_ok":    seconds_since_last_ok,
            "consecutive_failures":     self._consecutive_failures,
            "consecutive_exceptions":   self._consecutive_exceptions,
            "current_foreground_title": _get_foreground_title(),
            "bridge_up":                bridge_up,
            "bridge_port":              self._bridge_port,
            "total_presses_ok":         total_ok,
            "total_presses_failed":     total_failed,
            "panic_active":             self._panic_active,
            "dry_run":                  dry_run,
            "interval_seconds":         self._interval,
        }

    # ── Kill-switch ──────────────────────────────────────────────────────

    def trigger_panic(self, reason: str = "manual") -> dict:
        """Activa el kill-switch: desactiva el daemon y marca panic_active=True."""
        with self._lock:
            self._panic_prev_enabled = self._enabled
            self._panic_active = True
            self._enabled = False
            self._stop_event.set()
            self._save_state()
        stopped_at = datetime.now(timezone.utc).isoformat()
        print(f"[AutoEnter] PANIC activado | reason={reason}", flush=True)
        logger.error("[AutoEnter] PANIC activado — reason=%s", reason)
        _safe_emit("notification",
                   action="auto_enter_panic_triggered",
                   message=f"Panic activado: {reason}",
                   detail=reason)
        _safe_notify("Stacky AutoEnter — PANIC",
                     f"El daemon fue detenido manualmente. Razón: {reason}",
                     level="error")
        return {"ok": True, "stopped_at": stopped_at, "reason": reason}

    def reset_panic(self) -> dict:
        """Limpia el panic_active y restaura el estado previo de enabled."""
        with self._lock:
            self._panic_active = False
            prev_enabled = self._panic_prev_enabled
            self._panic_prev_enabled = False
        if prev_enabled:
            self.start()
        else:
            # Persistir panic_active=False aunque no re-habilitemos
            with self._lock:
                self._save_state()
        logger.info("[AutoEnter] panic reset — prev_enabled=%s", prev_enabled)
        return {"ok": True, "enabled": self._enabled, "panic_active": False}

    # ── Loop interno ──────────────────────────────────────────────────────

    def _loop(self) -> None:
        """Loop principal del daemon."""
        logger.debug("[AutoEnter] Loop iniciado")
        while not self._stop_event.is_set():
            interrupted = self._stop_event.wait(timeout=self._interval)
            if interrupted or self._stop_event.is_set():
                break

            try:
                self._press()
                # Reset contador de excepciones tras éxito parcial (no crash)
                self._consecutive_exceptions = 0
            except Exception as exc:
                self._handle_press_exception(exc)

        logger.debug("[AutoEnter] Loop terminado")

    def _handle_press_exception(self, exc: Exception) -> None:
        """Maneja excepciones no esperadas dentro de _press()."""
        self._consecutive_exceptions += 1
        stack = traceback.format_exc()
        logger.error("[AutoEnter] Excepción en _press (%d/%d): %s",
                     self._consecutive_exceptions,
                     self.CRASH_THRESHOLD, exc)
        _safe_emit(
            "notification",
            action="auto_enter_thread_exception",
            message=str(exc)[:300],
            detail=f"consecutive={self._consecutive_exceptions}",
            stack=stack[:2000],
        )

        if _audit is not None:
            try:
                _audit.record(
                    method="exception", ok=False, reason="exception",
                    elapsed_ms=0, foreground_title=_get_foreground_title(),
                    total_ok_running=_total_presses_ok,
                    dry_run=self._is_dry_run(),
                    error=str(exc)[:200],
                )
            except Exception:
                pass

        if self._consecutive_exceptions >= self.CRASH_THRESHOLD:
            logger.critical("[AutoEnter] %d excepciones consecutivas — apagando daemon",
                            self._consecutive_exceptions)
            _safe_emit(
                "notification",
                action="auto_enter_thread_crashed",
                message=f"{self._consecutive_exceptions} excepciones consecutivas",
                error_kind="technical",
            )
            _safe_notify("Stacky AutoEnter — CRASH",
                         f"Daemon apagado tras {self._consecutive_exceptions} excepciones consecutivas",
                         level="error")
            with self._lock:
                self._enabled = False
                self._stop_event.set()
                self._save_state()
            return

        if self._consecutive_exceptions >= self.MAX_CONSECUTIVE_EXC:
            logger.warning("[AutoEnter] Backoff de 30s tras %d excepciones",
                           self._consecutive_exceptions)
            self._stop_event.wait(timeout=30.0)

    def _is_dry_run(self) -> bool:
        if _guard is None:
            return False
        try:
            return bool(_guard.load_config().dry_run)
        except Exception:
            return False

    def _press(self) -> None:
        """Ejecuta la pulsación usando el mejor método disponible."""
        self._last_press_attempt_ts = datetime.now(timezone.utc)

        cfg = _guard.load_config() if _guard is not None else None
        dry_run = bool(cfg.dry_run) if cfg else False
        mode = cfg.mode if cfg else "advisory"

        # Guard: revisar prompt pendiente (si lo hay en el portapapeles como
        # proxy barato — el caller de copilot_bridge ya copió el texto ahí).
        pending_text = self._read_pending_prompt_snippet()
        matched = False
        pattern_label: Optional[str] = None
        if _guard is not None and mode != "off":
            matched, pattern_label = _guard.check(pending_text)
            if matched:
                _safe_emit(
                    "notification",
                    action="auto_enter_destructive_detected",
                    message=f"Patrón detectado: {pattern_label}",
                    detail=_guard.snippet(pending_text),
                )
                _safe_notify(
                    "Stacky AutoEnter — comando destructivo detectado",
                    f"Patrón: {pattern_label} | modo={mode} | dry_run={dry_run}",
                    level="warning",
                )
                if mode == "blocking":
                    # Bloquear el press
                    self._register_outcome(
                        ok=False, method="blocked",
                        reason="blocked_by_guard",
                        elapsed_ms=0,
                        pattern=pattern_label,
                        dry_run=dry_run,
                    )
                    return

        # Dry-run: nunca mandar keypress real
        if dry_run:
            self._register_outcome(
                ok=True, method="dry_run",
                reason="dry_run",
                elapsed_ms=0,
                pattern=pattern_label,
                dry_run=True,
            )
            return

        # ── Intento real: bridge → sendinput ──────────────────────────────
        t0 = time.monotonic()
        bridge_ok, bridge_reason = _press_via_bridge(self._bridge_port)
        elapsed_bridge = int((time.monotonic() - t0) * 1000)

        if bridge_ok:
            self._register_outcome(
                ok=True, method="bridge", reason=bridge_reason,
                elapsed_ms=elapsed_bridge, pattern=pattern_label, dry_run=False,
            )
            return

        # Fallback SendInput
        t1 = time.monotonic()
        ui_ok, ui_reason = _press_via_sendinput()
        elapsed_ui = int((time.monotonic() - t1) * 1000)

        self._register_outcome(
            ok=ui_ok,
            method="sendinput",
            reason=ui_reason,
            elapsed_ms=elapsed_ui,
            pattern=pattern_label,
            dry_run=False,
            bridge_reason=bridge_reason,
        )

    def _register_outcome(
        self,
        *,
        ok: bool,
        method: str,
        reason: str,
        elapsed_ms: int,
        pattern: Optional[str],
        dry_run: bool,
        bridge_reason: Optional[str] = None,
    ) -> None:
        """Centraliza el post-procesamiento: log en memoria, audit, eventos, notifier."""
        fg_title = _get_foreground_title()
        self._last_foreground_title = fg_title

        _record_press(success=ok, method=method)

        if ok:
            self._last_press_ok_ts = datetime.now(timezone.utc)
            self._consecutive_failures = 0
        else:
            self._consecutive_failures += 1

        # Audit persistente
        if _audit is not None:
            try:
                exec_id = None
                try:
                    exec_id = _current_execution_id()
                except Exception:
                    pass
                _audit.record(
                    method           = method,
                    ok               = ok,
                    reason           = reason,
                    foreground_title = fg_title or None,
                    elapsed_ms       = elapsed_ms,
                    total_ok_running = _total_presses_ok,
                    dry_run          = dry_run,
                    guard_matched    = pattern,
                    execution_id     = exec_id,
                    bridge_reason    = bridge_reason,
                )
            except Exception:
                pass

        # Eventos al bus
        if ok:
            # Cada 10 OK emitimos un success para no inundar
            if _total_presses_ok % 10 == 0:
                _safe_emit(
                    "notification",
                    action="auto_enter_success",
                    message=f"{_total_presses_ok} pulsaciones OK acumuladas",
                    detail=f"method={method} dry_run={dry_run}",
                )
        else:
            _safe_emit(
                "notification",
                action="auto_enter_failed",
                message=f"Pulsación falló — {reason}",
                detail=f"method={method} fg={fg_title or 'unknown'}",
            )

    def _read_pending_prompt_snippet(self) -> Optional[str]:
        """
        Heurística barata para auditar prompts destructivos: leer el clipboard.
        copilot_bridge.send_prompt() acaba de copiar el texto ahí antes de
        Ctrl+V + Enter. Si pyperclip no está disponible, retorna None (el
        guard deja pasar sin alertar).
        """
        try:
            import pyperclip  # type: ignore
            text = pyperclip.paste()
            if isinstance(text, str) and text.strip():
                return text[:4000]  # límite defensivo
        except Exception:
            return None
        return None

    # ── Persistencia ──────────────────────────────────────────────────────

    def _save_state(self) -> None:
        state_file = _state_file_path()
        try:
            state_file.parent.mkdir(parents=True, exist_ok=True)
            import json
            state_file.write_text(
                json.dumps({
                    "enabled":          self._enabled,
                    "interval_seconds": self._interval,
                    "panic_active":     self._panic_active,
                    "panic_prev_enabled": self._panic_prev_enabled,
                }, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.debug("[AutoEnter] No se pudo guardar estado: %s", e)

    def load_state(self) -> None:
        """Carga estado persistido desde disco."""
        state_file = _state_file_path()
        if not state_file.exists():
            return
        try:
            import json
            s = json.loads(state_file.read_text(encoding="utf-8"))
            self._interval = int(s.get("interval_seconds", self.DEFAULT_INTERVAL))
            self._panic_active = bool(s.get("panic_active", False))
            self._panic_prev_enabled = bool(s.get("panic_prev_enabled", False))
            if self._panic_active:
                logger.warning("[AutoEnter] panic_active=True persistido — no se auto-arranca")
                return
            if s.get("enabled"):
                self.start()
        except Exception as e:
            logger.debug("[AutoEnter] No se pudo cargar estado: %s", e)


def _state_file_path() -> "Path":
    from pathlib import Path
    return Path(__file__).parent / "state" / "auto_enter.json"


# ─────────────────────────────────────────────────────────────────────────────
# Singleton
# ─────────────────────────────────────────────────────────────────────────────

_instance: Optional[AutoEnterDaemon] = None
_instance_lock = threading.Lock()


def get_auto_enter_daemon(bridge_port: int = 5051) -> AutoEnterDaemon:
    """Retorna el singleton del AutoEnterDaemon."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = AutoEnterDaemon(bridge_port=bridge_port)
                _instance.load_state()
                # Levantar watchdog si está disponible
                try:
                    from auto_enter_watchdog import start_watchdog
                    start_watchdog(_instance)
                except Exception as _wd_err:  # pragma: no cover - defensive
                    logger.debug("[AutoEnter] Watchdog no disponible: %s", _wd_err)
                # Registrar hotkey global de pánico (Ctrl+Alt+Shift+F12)
                try:
                    from auto_enter_hotkey import start_panic_hotkey
                    start_panic_hotkey(_instance)
                except Exception as _hk_err:  # pragma: no cover - defensive
                    logger.debug("[AutoEnter] Panic hotkey no disponible: %s", _hk_err)
    return _instance
