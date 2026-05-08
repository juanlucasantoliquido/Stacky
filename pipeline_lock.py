"""
pipeline_lock.py — File-based distributed lock con TTL para etapas del pipeline.

Evita que dos instancias concurrentes (daemon + watcher, dos daemons, dashboard +
daemon) ejecuten la misma etapa para el mismo ticket al mismo tiempo.

Características:
  - Cross-process: el lock es un archivo en disco → protege incluso entre procesos distintos
  - Cross-thread:  threading.Lock() protege las operaciones en el mismo proceso
  - TTL / anti-zombie: si el proceso muere, el lock expira a los LOCK_TIMEOUT_SECONDS
  - Escritura atómica: write-to-temp + os.replace → no deja archivos corruptos
  - run_id: cada invocación recibe un ID único (ticket_stage_timestamp) para trazabilidad

Estructura del lock file:
    locks/{ticket_id}_{stage}.lock
    Contenido JSON:
        { "run_id": "INC-0027795_pm_1713000000",
          "ticket_id": "INC-0027795",
          "stage": "pm",
          "timestamp": 1713000000.0,
          "pid": 12345 }

Uso típico en _launch_stage:
    from pipeline_lock import acquire_lock, release_lock

    run_id = acquire_lock(ticket_id, stage)
    if run_id is None:
        logger.warning("Lock activo — invocación duplicada ignorada")
        return
    try:
        # ... invocar agente ...
    finally:
        release_lock(ticket_id, stage, run_id)
"""

import json
import logging
import os
import threading
import time
from pathlib import Path

logger = logging.getLogger("mantis.pipeline_lock")

# TTL del lock: si transcurren más de N segundos sin que se libere,
# se considera zombie y se limpia automáticamente.
LOCK_TIMEOUT_SECONDS: int = 600  # 10 minutos

# Directorio donde se crean los lock files
_BASE_DIR   = Path(__file__).parent
_LOCKS_DIR  = _BASE_DIR / "locks"

# Lock en memoria para serializar accesos al filesystem dentro del mismo proceso.
# Re-entrante para que el mismo thread pueda llamar acquire + is_locked sin deadlock.
_proc_lock = threading.RLock()


# ── Helpers internos ──────────────────────────────────────────────────────────

def _lock_path(ticket_id: str, stage: str) -> Path:
    return _LOCKS_DIR / f"{ticket_id}_{stage}.lock"


def _read_lock_data(lock_file: Path) -> dict:
    """Lee y parsea el archivo de lock. Retorna {} si falla."""
    try:
        return json.loads(lock_file.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _is_lock_expired(data: dict) -> bool:
    """True si el lock supera el TTL o no tiene timestamp válido."""
    ts = data.get("timestamp")
    if not isinstance(ts, (int, float)):
        return True  # Sin timestamp → tratar como expirado
    return (time.time() - ts) >= LOCK_TIMEOUT_SECONDS


def _remove_lock(lock_file: Path) -> None:
    """Elimina el archivo de lock ignorando errores (ya lo borró otro thread/proceso)."""
    try:
        lock_file.unlink()
    except FileNotFoundError:
        pass
    except Exception as exc:
        logger.debug("No se pudo eliminar lock %s: %s", lock_file.name, exc)


# ── API pública ───────────────────────────────────────────────────────────────

def generate_run_id(ticket_id: str, stage: str) -> str:
    """Genera un ID único para esta invocación (útil para logs y artefactos)."""
    return f"{ticket_id}_{stage}_{int(time.time())}"


def acquire_lock(ticket_id: str, stage: str) -> "str | None":
    """
    Intenta adquirir el lock file-based para el par (ticket_id, stage).

    Retorna:
        str  — run_id único si se adquirió el lock (otro no estaba corriendo)
        None — si ya hay un lock activo y no-expirado (skip esta invocación)

    En caso de lock zombie (proceso muerto o TTL superado), lo sobrescribe
    automáticamente y adquiere el lock.
    """
    _LOCKS_DIR.mkdir(parents=True, exist_ok=True)
    lock_file = _lock_path(ticket_id, stage)

    with _proc_lock:
        if lock_file.exists():
            data    = _read_lock_data(lock_file)
            expired = _is_lock_expired(data)

            if not expired:
                logger.warning(
                    "[LOCK] %s/%s — lock activo (run_id=%s, pid=%s, edad=%.0fs) — invocación duplicada ignorada",
                    ticket_id, stage,
                    data.get("run_id", "?"),
                    data.get("pid", "?"),
                    time.time() - data.get("timestamp", time.time()),
                )
                return None  # Lock válido — otra instancia está corriendo

            # Lock zombie — loggear y reutilizar slot
            logger.warning(
                "[LOCK] %s/%s — lock zombie detectado (edad=%.0fs) — limpiando y re-adquiriendo",
                ticket_id, stage,
                time.time() - data.get("timestamp", 0),
            )
            _remove_lock(lock_file)

        # Crear el lock con escritura atómica (write-to-tmp + rename)
        run_id  = generate_run_id(ticket_id, stage)
        payload = {
            "run_id":    run_id,
            "ticket_id": ticket_id,
            "stage":     stage,
            "timestamp": time.time(),
            "pid":       os.getpid(),
        }
        tmp_file = lock_file.with_suffix(".tmp")
        tmp_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        os.replace(str(tmp_file), str(lock_file))

        logger.debug(
            "[LOCK] %s/%s — lock adquirido (run_id=%s)",
            ticket_id, stage, run_id,
        )
        return run_id


def release_lock(ticket_id: str, stage: str, run_id: str = None) -> None:
    """
    Libera el lock para (ticket_id, stage).

    Si se proporciona run_id, solo libera si el lock le pertenece a esa
    invocación (evita que una instancia libere el lock de otra).
    Si run_id es None, libera incondicionalmente.
    """
    lock_file = _lock_path(ticket_id, stage)

    with _proc_lock:
        if not lock_file.exists():
            return

        if run_id is not None:
            data = _read_lock_data(lock_file)
            if data.get("run_id") != run_id:
                logger.debug(
                    "[LOCK] release_lock(%s/%s) ignorado — run_id no coincide "
                    "(esperado=%s, en_disco=%s)",
                    ticket_id, stage, run_id, data.get("run_id"),
                )
                return

        _remove_lock(lock_file)
        logger.debug("[LOCK] %s/%s — lock liberado (run_id=%s)", ticket_id, stage, run_id or "?")


def is_locked(ticket_id: str, stage: str) -> bool:
    """
    Retorna True si existe un lock activo (no expirado) para (ticket_id, stage).
    No adquiere ni modifica el lock.
    """
    lock_file = _lock_path(ticket_id, stage)
    if not lock_file.exists():
        return False

    with _proc_lock:
        data = _read_lock_data(lock_file)
        return not _is_lock_expired(data)


def cleanup_zombie_locks() -> int:
    """
    Recorre todos los lock files y elimina los que superaron el TTL.
    Llamar periódicamente desde el ciclo del daemon.

    Retorna: cantidad de locks zombie eliminados.
    """
    if not _LOCKS_DIR.exists():
        return 0

    cleaned = 0
    with _proc_lock:
        for lock_file in _LOCKS_DIR.glob("*.lock"):
            try:
                data    = _read_lock_data(lock_file)
                expired = _is_lock_expired(data)
                if expired:
                    age = time.time() - data.get("timestamp", 0)
                    logger.warning(
                        "[LOCK] Zombie cleanup: %s (run_id=%s, edad=%.0fs)",
                        lock_file.name, data.get("run_id", "?"), age,
                    )
                    _remove_lock(lock_file)
                    cleaned += 1
            except Exception as exc:
                logger.debug("Error revisando lock %s: %s", lock_file.name, exc)
                _remove_lock(lock_file)
                cleaned += 1

    if cleaned:
        logger.info("[LOCK] cleanup_zombie_locks: %d lock(s) zombie eliminados", cleaned)
    return cleaned


def get_active_locks() -> list:
    """
    Retorna lista de dicts con información de todos los locks activos.
    Útil para dashboard y diagnóstico.
    """
    if not _LOCKS_DIR.exists():
        return []

    result = []
    with _proc_lock:
        for lock_file in _LOCKS_DIR.glob("*.lock"):
            try:
                data = _read_lock_data(lock_file)
                if not _is_lock_expired(data):
                    result.append({
                        "run_id":    data.get("run_id", "?"),
                        "ticket_id": data.get("ticket_id", "?"),
                        "stage":     data.get("stage", "?"),
                        "age_s":     round(time.time() - data.get("timestamp", time.time()), 1),
                        "pid":       data.get("pid"),
                    })
            except Exception:
                pass
    return result
