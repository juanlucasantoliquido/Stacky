"""
session_manager.py — Gestión y validación de la sesión SSO de Mantis.

Permite detectar sesiones expiradas antes de que el scraper falle,
y ofrece mecanismos de renovación headless (reutilizando cookies) o
interactiva (abriendo el navegador para que el usuario complete el login).
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime


class SessionExpiredError(Exception):
    """Se lanza cuando la sesión de Mantis está expirada y no se pudo renovar."""


# ── Cache de validación ──────────────────────────────────────────────────────
# Evita lanzar Playwright repetidamente si ya validamos hace poco.
_validation_cache = {"valid": None, "ts": 0.0, "auth_mtime": 0.0}
_VALIDATION_TTL   = 300.0  # 5 minutos — si validamos hace menos de 5min, reusar


class SessionManager:
    """
    Verifica y renueva la sesión SSO de MantisBT.

    Uso típico (en run_scraper o daemon):

        sm = SessionManager(auth_path, mantis_url)
        if sm.needs_renewal():
            if not sm.renew_session_headless():
                sm.prompt_renewal()   # bloquea hasta que el usuario renueve
    """

    def __init__(self, auth_path: str, mantis_url: str, timeout_ms: int = 30000):
        self.auth_path   = auth_path
        self.mantis_url  = mantis_url
        self.timeout_ms  = timeout_ms
        self._base_dir   = os.path.dirname(os.path.abspath(__file__))

    # ── Verificación de estado ─────────────────────────────────────────────

    def get_session_age_hours(self) -> float:
        """Retorna horas desde que se escribió auth.json. -1 si no existe."""
        if not os.path.exists(self.auth_path):
            return -1.0
        mtime = os.path.getmtime(self.auth_path)
        return (time.time() - mtime) / 3600

    def _is_session_valid_http(self) -> bool:
        """
        Verificación ligera via HTTP GET con cookies de auth.json.
        Mucho más rápido que lanzar Playwright: ~200ms vs ~5s.
        Retorna True si Mantis responde con HTML que contiene #buglist,
        False si redirige al login.
        """
        try:
            import urllib.request
            import http.cookiejar

            # Extraer cookies de auth.json (formato Playwright storage_state)
            with open(self.auth_path, encoding="utf-8") as f:
                storage = json.load(f)

            cookies = storage.get("cookies", [])
            if not cookies:
                return False

            # Construir cookie header manualmente (más rápido que CookieJar)
            cookie_str = "; ".join(f"{c['name']}={c['value']}" for c in cookies)

            req = urllib.request.Request(
                self.mantis_url,
                headers={
                    "Cookie": cookie_str,
                    "User-Agent": "MantisScraperSessionCheck/1.0",
                },
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                # Leer solo los primeros 8KB — suficiente para detectar #buglist o login
                body = resp.read(8192).decode("utf-8", errors="replace")
                return "buglist" in body

        except Exception as e:
            print(f"[SESSION] HTTP check falló: {e} — usando Playwright como fallback")
            return self._is_session_valid_playwright()

    def _is_session_valid_playwright(self) -> bool:
        """
        Verificación pesada via Playwright (fallback).
        Solo se usa si el HTTP check falla por razones de red/CORS.
        """
        try:
            from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
        except ImportError:
            print("[SESSION] playwright no disponible — asumiendo sesión válida")
            return True

        if not os.path.exists(self.auth_path):
            return False

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                ctx     = browser.new_context(storage_state=self.auth_path)
                page    = ctx.new_page()
                page.goto(self.mantis_url, timeout=self.timeout_ms)
                try:
                    page.wait_for_selector("#buglist", timeout=8000)
                    valid = True
                except PlaywrightTimeout:
                    valid = False
                browser.close()
            return valid
        except Exception as e:
            print(f"[SESSION] Error verificando sesión: {e}")
            return False

    def is_session_valid(self) -> bool:
        """
        Verifica si la sesión está activa. Usa cache de 5 minutos para
        evitar verificaciones repetidas. Primero intenta HTTP ligero (~200ms),
        solo cae en Playwright si HTTP falla.
        """
        now = time.monotonic()
        try:
            auth_mtime = os.path.getmtime(self.auth_path) if os.path.exists(self.auth_path) else 0
        except OSError:
            auth_mtime = 0

        # Si auth.json no cambió y validamos hace poco, reusar resultado
        if (_validation_cache["valid"] is not None
                and auth_mtime == _validation_cache["auth_mtime"]
                and (now - _validation_cache["ts"]) < _VALIDATION_TTL):
            return _validation_cache["valid"]

        valid = self._is_session_valid_http()

        _validation_cache["valid"]      = valid
        _validation_cache["ts"]         = now
        _validation_cache["auth_mtime"] = auth_mtime
        return valid

    def needs_renewal(self, max_age_hours: float = 8.0) -> bool:
        """
        True si la sesión necesita renovación.
        Lógica optimizada:
        - auth.json no existe → True (sin verificación)
        - age < 1h → False (sesión reciente, no verificar)
        - age 1h-4h → False (probablemente OK, no verificar)
        - age 4h-max → verificar via HTTP ligero
        - age > max → True directamente (ya expiró, no gastar en verificar)
        """
        age = self.get_session_age_hours()
        if age < 0:
            return True   # auth.json no existe
        if age > max_age_hours:
            # Ya pasó el límite — no gastar recursos verificando, renovar directamente
            print(f"[SESSION] Sesión tiene {age:.1f}h (límite {max_age_hours}h) — renovar")
            return True
        if age > 4.0:
            # Zona gris: verificar con HTTP ligero
            return not self.is_session_valid()
        return False

    # ── Renovación ────────────────────────────────────────────────────────

    def renew_session_headless(self) -> bool:
        """
        Intenta renovar la sesión reutilizando las cookies existentes
        (útil cuando la VPN estaba caída pero las cookies aún son válidas).
        Si la sesión es válida, actualiza el mtime de auth.json para resetear el timer.
        Retorna True si la sesión quedó válida, False si se necesita login interactivo.
        """
        if self.is_session_valid():
            # Tocar auth.json para resetear la antigüedad (sin re-leer/re-escribir todo)
            try:
                os.utime(self.auth_path, None)  # touch — actualiza mtime sin I/O
                print("[SESSION] Sesión validada y timestamp renovado")
            except Exception:
                pass
            # Invalidar cache de validación (mtime cambió)
            _validation_cache["auth_mtime"] = 0.0
            return True
        return False

    def prompt_renewal(self, timeout_seconds: int = 300) -> bool:
        """
        Muestra un aviso en consola y abre capture_session.py en una nueva ventana.
        Bloquea hasta que auth.json sea actualizado (el usuario completó el login)
        o hasta que se agote timeout_seconds.
        Retorna True si la renovación fue exitosa.
        """
        capture_script = os.path.join(self._base_dir, "capture_session.py")
        if not os.path.exists(capture_script):
            print(f"[SESSION] No se encontró capture_session.py en {self._base_dir}")
            return False

        mtime_before = os.path.getmtime(self.auth_path) if os.path.exists(self.auth_path) else 0

        print("=" * 60)
        print("[SESSION] La sesión de Mantis necesita renovación.")
        print("[SESSION] Abriendo navegador para completar el login SSO...")
        print("[SESSION] Esperando hasta que el login sea completado...")
        print("=" * 60)

        try:
            subprocess.Popen(
                [sys.executable, capture_script],
                cwd=self._base_dir,
                creationflags=subprocess.CREATE_NEW_CONSOLE
                              if sys.platform == "win32" else 0,
            )
        except Exception as e:
            print(f"[SESSION] Error abriendo capture_session.py: {e}")
            return False

        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            time.sleep(3)
            if not os.path.exists(self.auth_path):
                continue
            mtime_now = os.path.getmtime(self.auth_path)
            if mtime_now > mtime_before:
                print("[SESSION] auth.json actualizado — sesión renovada exitosamente")
                _validation_cache["auth_mtime"] = 0.0  # invalidar cache
                return True

        print(f"[SESSION] Timeout ({timeout_seconds}s) esperando renovación de sesión")
        return False

    def prompt_renewal_async(self, on_complete=None) -> None:
        """
        Versión no bloqueante de prompt_renewal para uso en el daemon.
        Llama on_complete(True/False) cuando termina la renovación.
        """
        import threading

        def _run():
            result = self.prompt_renewal()
            if on_complete:
                on_complete(result)

        t = threading.Thread(target=_run, daemon=True, name="session-renewal")
        t.start()
