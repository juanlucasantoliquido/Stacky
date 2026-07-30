"""agenda_web_launcher.py — Arranque local ACOTADO de AgendaWeb (Plan 240 F2).

Guardarrailes NO negociables (todos verificados ANTES de ejecutar nada):
  1. SOLO localhost: si el host de base_url no es localhost/127.0.0.1 => rechaza.
  2. SOLO si el ejecutable de IIS Express y el applicationhost.config EXISTEN.
  3. Idempotente: si AgendaWeb ya responde => no arranca nada y NUNCA lo apaga
     (started_by_us=False). Solo se apaga lo que este modulo arranco.
  4. Un intento, con timeout. Cero reintentos infinitos, cero polling eterno.
  5. Jamas en deploy/frozen: si STACKY_DEPLOY_MODE esta seteada o el ejecutable
     corre congelado (sys.frozen), rechaza.

FLAG: STACKY_QA_UAT_AUTOSTART_AGENDA_ENABLED, default ON desde el barrido 2026-07-27
(config.py). Con OFF el comportamiento es byte-identico al previo al plan 240
(BLOCKED/APP_NOT_RUNNING sin intentar arrancar nada).
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

logger = logging.getLogger("stacky.qa_uat.agenda_launcher")

_TOOL_ROOT = Path(__file__).resolve().parent
_DEFAULT_SITE = "AgendaWeb-Site"
_APPPOOL = "Clr4IntegratedAppPool"
_IIS_CANDIDATES = (r"C:\Program Files\IIS Express\iisexpress.exe",
                   r"C:\Program Files (x86)\IIS Express\iisexpress.exe")
_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "[::1]"})
_FLAG = "STACKY_QA_UAT_AUTOSTART_AGENDA_ENABLED"


def _flag_on() -> bool:
    return str(os.environ.get(_FLAG, "")).strip().lower() in ("1", "true", "yes", "on")


def _resolve_iisexpress():
    """QA_UAT_IISEXPRESS_EXE si esta y existe; si no, el primer candidato estandar."""
    env = os.environ.get("QA_UAT_IISEXPRESS_EXE", "").strip()
    if env and Path(env).is_file():
        return env
    for cand in _IIS_CANDIDATES:
        if Path(cand).is_file():
            return cand
    return None


def _resolve_apphost_config():
    """QA_UAT_AGENDA_APPHOST_CONFIG si esta y existe; si no, None.

    NO adivina rutas de clientes: el operador la configura una vez por env/UI.
    """
    env = os.environ.get("QA_UAT_AGENDA_APPHOST_CONFIG", "").strip()
    if env and Path(env).is_file():
        return env
    return None


def _out(ok, code, *, already_running=False, started_by_us=False, pid=None,
         base_url="", detail="", remediation="") -> dict:
    return {"ok": ok, "already_running": already_running,
            "started_by_us": started_by_us, "pid": pid, "code": code,
            "base_url": base_url, "detail": detail, "remediation": remediation}


def _responds(base_url: str, timeout_s: float = 3.0) -> bool:
    """True si AgendaWeb responde con un status 'vivo'. NUNCA lanza.

    Plan 262 F9 — delega en agenda_health. Antes tenia una COPIA hardcodeada de los
    alive codes como fallback por si el import fallaba: tres modulos opinando sobre
    lo mismo con codigo distinto es exactamente como se deriva.
    """
    try:
        from agenda_health import probe_url
        return probe_url(base_url, timeout_s=timeout_s).alive
    except Exception:  # noqa: BLE001
        return False


def ensure_agenda_web(*, base_url=None, timeout_s: int = 60) -> dict:
    """Arranca AgendaWeb local si hace falta. NUNCA lanza. Keys FIJAS del contrato."""
    try:
        url = base_url
        if not url:
            try:
                from environment_preflight import get_agenda_base_url
                url = get_agenda_base_url()
            except Exception:  # noqa: BLE001
                url = os.environ.get("AGENDA_WEB_BASE_URL", "")
        url = str(url or "")

        # (1) flag
        if not _flag_on():
            return _out(False, "AUTOSTART_DISABLED", base_url=url,
                        detail="el autostart esta apagado (default): no es un error",
                        remediation="Activalo en Configuracion -> Arnes si tenes IIS "
                                    "Express y el applicationhost.config del cliente")

        # (5) jamas en deploy/frozen
        if os.environ.get("STACKY_DEPLOY_MODE") or getattr(sys, "frozen", False):
            return _out(False, "DEPLOY_MODE", base_url=url,
                        detail="arrancar servicios locales esta prohibido en deploy",
                        remediation="Levanta AgendaWeb manualmente en ese entorno")

        # (2) solo localhost
        host = (urlsplit(url).hostname or "").lower()
        if host not in _LOCAL_HOSTS:
            return _out(False, "NOT_LOCALHOST", base_url=url,
                        detail=f"host={host!r}: solo se arranca en localhost",
                        remediation="Usa una AGENDA_WEB_BASE_URL local o levanta la app "
                                    "vos mismo en el server remoto")

        # (3) idempotente: si ya responde, no arrancamos NADA
        if _responds(url):
            return _out(True, "", already_running=True, started_by_us=False,
                        base_url=url, detail="AgendaWeb ya responde")

        exe = _resolve_iisexpress()
        if not exe:
            return _out(False, "IISEXPRESS_NOT_FOUND", base_url=url,
                        detail="no se encontro iisexpress.exe",
                        remediation="Instala IIS Express o define QA_UAT_IISEXPRESS_EXE "
                                    "con la ruta al ejecutable")
        cfg = _resolve_apphost_config()
        if not cfg:
            return _out(False, "APPHOST_CONFIG_NOT_FOUND", base_url=url,
                        detail="no se encontro el applicationhost.config",
                        remediation="Define QA_UAT_AGENDA_APPHOST_CONFIG con la ruta al "
                                    "applicationhost.config del cliente")

        site = os.environ.get("QA_UAT_AGENDA_SITE", _DEFAULT_SITE)
        log_dir = _TOOL_ROOT / "evidence" / "_runtime"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "iisexpress.log"

        # (4) UN intento, sin shell (rutas con espacios no se reinterpretan)
        proc = None
        try:
            with log_path.open("ab") as fh:
                proc = subprocess.Popen(
                    [exe, f"/config:{cfg}", f"/site:{site}", f"/apppool:{_APPPOOL}"],
                    stdout=fh, stderr=fh,
                )
        except Exception as exc:  # noqa: BLE001
            return _out(False, "START_FAILED", base_url=url,
                        detail=f"{type(exc).__name__}: {exc}"[:200],
                        remediation="Revisa el applicationhost.config y los permisos")

        deadline = time.time() + max(1, int(timeout_s))
        while time.time() < deadline:
            if _responds(url, timeout_s=2.0):
                return _out(True, "", already_running=False, started_by_us=True,
                            pid=proc.pid, base_url=url,
                            detail=f"AgendaWeb arrancado por nosotros (pid={proc.pid})")
            time.sleep(1)

        # timeout => matamos SOLO lo que arrancamos
        try:
            proc.terminate()
        except Exception:  # noqa: BLE001
            pass
        return _out(False, "START_TIMEOUT", base_url=url, pid=proc.pid,
                    detail=f"AgendaWeb no respondio en {timeout_s}s; el proceso se termino",
                    remediation=f"Revisa {log_path} y que la solucion este compilada")
    except Exception as exc:  # noqa: BLE001 — NUNCA lanza
        return _out(False, "START_FAILED", base_url=str(base_url or ""),
                    detail=f"{type(exc).__name__}: {exc}"[:200],
                    remediation="Revisa la configuracion del autostart")


def stop_agenda_web(handle: dict) -> dict:
    """Apaga SOLO si handle['started_by_us'] is True y hay pid. NUNCA lanza.

    Con started_by_us False => {"ok": True, "stopped": False, ...}: jamas se apaga
    algo que ya estaba corriendo antes del run.
    """
    try:
        h = handle if isinstance(handle, dict) else {}
        if not h.get("started_by_us") or not h.get("pid"):
            return {"ok": True, "stopped": False,
                    "detail": "no lo arrancamos nosotros"}
        proc = h.get("_proc")
        if proc is not None:
            try:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except Exception:  # noqa: BLE001
                    proc.kill()
                return {"ok": True, "stopped": True, "detail": "proceso terminado"}
            except Exception as exc:  # noqa: BLE001
                return {"ok": False, "stopped": False,
                        "detail": f"{type(exc).__name__}: {exc}"[:200]}
        # Sin handle de proceso: matamos por pid, de forma acotada.
        import signal
        try:
            os.kill(int(h["pid"]), getattr(signal, "SIGTERM", signal.SIGINT))
            return {"ok": True, "stopped": True, "detail": f"pid {h['pid']} terminado"}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "stopped": False,
                    "detail": f"{type(exc).__name__}: {exc}"[:200]}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "stopped": False,
                "detail": f"{type(exc).__name__}: {exc}"[:200]}
