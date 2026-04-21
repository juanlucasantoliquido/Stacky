"""
pipeline_invoker.py — SEQ-11: Logging estructurado con correlation ID por invocación.

Este módulo provee utilidades para loguear invocaciones de agentes con un ID único
por invocación, de modo que todos los eventos de una misma invocación sean fácilmente
correlacionables en el log aunque vengan de distintos threads.

Uso:
    from pipeline_invoker import InvokeLogger

    logger = InvokeLogger(ticket_id="0027698", stage="pm")
    logger.start()                           # log INVOKE_START con correlation_id
    logger.en_curso_created(path)            # log EN_CURSO_CREATED
    logger.bridge_call(agent, prompt_len)    # log BRIDGE_CALL
    logger.end(success=True, elapsed=45.2)   # log INVOKE_END
    
    # O acceder al prefijo directamente:
    log.info(f"{logger.prefix} mensaje personalizado")
"""

import logging
import os
import threading
import time
import uuid

logger = logging.getLogger("stacky.invoker")


class InvokeLogger:
    """
    Genera un correlation_id único por invocación y centraliza los logs
    de una invocación de agente con el formato:
    
        [{ticket_id}/{stage}/{correlation_id}] EVENTO ...detalle...
    
    El correlation_id es un string de 8 caracteres hex (legible, único por invocación).
    """

    def __init__(self, ticket_id: str, stage: str):
        self.ticket_id      = ticket_id
        self.stage          = stage.upper()
        self.correlation_id = str(uuid.uuid4())[:8]
        self.prefix         = f"[{ticket_id}/{self.stage}/{self.correlation_id}]"
        self._start_time    = None

    def start(self) -> None:
        """Log INVOKE_START con thread name y PID."""
        self._start_time = time.monotonic()
        logger.info(
            "%s INVOKE_START thread=%s pid=%d",
            self.prefix,
            threading.current_thread().name,
            os.getpid(),
        )

    def lock_acquired(self) -> None:
        """Log LOCK_ACQUIRED (threading.Lock obtenido)."""
        logger.debug("%s LOCK_ACQUIRED", self.prefix)

    def lock_blocked(self) -> None:
        """Log LOCK_BLOCKED (lock ya tomado por otro thread — abortando)."""
        logger.warning("%s LOCK_BLOCKED — otro thread ya tiene el lock, abortando", self.prefix)

    def en_curso_created(self, path: str = "") -> None:
        """Log EN_CURSO flag creado en disco."""
        logger.info("%s EN_CURSO_CREATED path=%s", self.prefix, path or "—")

    def en_curso_exists(self, path: str = "") -> None:
        """Log EN_CURSO flag ya existía — invocación duplicada abortada."""
        logger.warning(
            "%s EN_CURSO_EXISTS (invocación duplicada ignorada) path=%s",
            self.prefix, path or "—"
        )

    def bridge_call(self, agent: str, prompt_len: int) -> None:
        """Log justo antes de llamar a invoke_agent (Copilot Bridge)."""
        logger.info(
            "%s BRIDGE_CALL agent=%s prompt_len=%d",
            self.prefix, agent, prompt_len,
        )

    def bridge_result(self, ok: bool) -> None:
        """Log resultado del invoke_agent."""
        status = "OK" if ok else "FAILED"
        logger.info("%s BRIDGE_RESULT status=%s", self.prefix, status)

    def en_curso_cleaned(self, path: str = "") -> None:
        """Log EN_CURSO flag limpiado (fin de invocación)."""
        logger.debug("%s EN_CURSO_CLEANED path=%s", self.prefix, path or "—")

    def end(self, success: bool, elapsed: float = None) -> None:
        """Log INVOKE_END con resultado y tiempo transcurrido."""
        if elapsed is None and self._start_time is not None:
            elapsed = time.monotonic() - self._start_time
        elapsed_str = f"{elapsed:.1f}s" if elapsed is not None else "—"
        status = "SUCCESS" if success else "FAILED"
        logger.info(
            "%s INVOKE_END result=%s elapsed=%s",
            self.prefix, status, elapsed_str,
        )

    def error(self, reason: str) -> None:
        """Log ERROR durante la invocación."""
        logger.error("%s INVOKE_ERROR reason=%s", self.prefix, reason)

    def warning(self, msg: str) -> None:
        """Log WARNING."""
        logger.warning("%s %s", self.prefix, msg)

    def info(self, msg: str) -> None:
        """Log INFO genérico con el prefix de correlación."""
        logger.info("%s %s", self.prefix, msg)


def make_invoke_logger(ticket_id: str, stage: str) -> InvokeLogger:
    """Factory function — alias conveniente."""
    return InvokeLogger(ticket_id, stage)


# ── SEQ-08: Mutex inter-proceso via lockfile ──────────────────────────────────

_open_lock_fds: dict = {}   # path → fd abierto (mantener abierto = lock)


def _acquire_process_lock(lock_path: str):
    """
    SEQ-08: Adquiere un lockfile inter-proceso.

    Usa O_CREAT | O_EXCL (atómico en NTFS local) para crear el lockfile.
    Escribe el PID del proceso actual en el archivo.

    Retorna el file descriptor si se adquirió el lock, None si ya está tomado
    por un proceso vivo.

    Nota Windows: O_EXCL es atómico en NTFS local pero NO garantizado en
    drives de red. Para drives mapeados (ej. N:\\) se usa como best-effort.
    """
    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        _open_lock_fds[lock_path] = fd
        return fd
    except FileExistsError:
        # Lock existe — verificar si el proceso que lo tiene sigue vivo
        try:
            with open(lock_path, "r") as f:
                content = f.read().strip()
                holding_pid = int(content) if content.isdigit() else 0
            if holding_pid:
                os.kill(holding_pid, 0)  # signal 0 = solo verifica existencia
                return None  # proceso vivo, lock válido
            else:
                raise ProcessLookupError("PID no parseable")
        except (ProcessLookupError, PermissionError):
            # Proceso muerto → lock stale, eliminar y reintentar una vez
            _safe_remove_lock(lock_path)
            try:
                fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, str(os.getpid()).encode())
                _open_lock_fds[lock_path] = fd
                return fd
            except FileExistsError:
                return None  # Race condition con otro proceso — no adquirido
        except (ValueError, OSError):
            return None  # No podemos determinar → conservador, no adquirir


def _release_process_lock(lock_path: str, fd=None) -> None:
    """Libera el lockfile inter-proceso."""
    fd_to_close = fd or _open_lock_fds.pop(lock_path, None)
    if fd_to_close is not None:
        try:
            os.close(fd_to_close)
        except OSError:
            pass
    _open_lock_fds.pop(lock_path, None)
    _safe_remove_lock(lock_path)


def _safe_remove_lock(path: str) -> None:
    try:
        os.remove(path)
    except FileNotFoundError:
        pass
    except Exception:
        pass


# ── SEQ-07: Función canónica de invocación ────────────────────────────────────

import collections as _col

_canonical_ticket_locks: dict = _col.defaultdict(lambda: __import__('threading').Lock())


def invoke_stage_canonical(
    ticket_id: str,
    stage: str,
    ticket_folder: str,
    bridge_invoke_fn,          # callable: (prompt, agent_name, **kwargs) -> bool
    prompt: str,
    agent_name: str,
    en_curso_flag_path: str,
    *,
    on_success=None,           # callable() llamado si invoke ok
    on_failure=None,           # callable(reason: str) llamado si invoke falla
    extra_bridge_kwargs: dict = None,
) -> bool:
    """
    SEQ-07: Punto de entrada canónico para invocar un stage de agente.

    Garantías (en orden):
    1. threading.Lock por ticket (intra-proceso) — SEQ-02
    2. Process lockfile por ticket (inter-proceso) — SEQ-08
    3. EN_CURSO flag atómico en disco
    4. Logging estructurado con correlation ID — SEQ-11
    5. Cleanup de EN_CURSO + lockfile en todos los paths de error

    Retorna True si invoke_agent retornó True, False en cualquier otro caso.
    """
    import datetime

    ilog = InvokeLogger(ticket_id, stage)
    ilog.start()

    # ── 1: Lock intra-proceso (threading.Lock) ─────────────────────────────
    tlock = _canonical_ticket_locks[ticket_id]
    if not tlock.acquire(blocking=False):
        ilog.lock_blocked()
        return False

    # ── 2: Lockfile inter-proceso (SEQ-08) ─────────────────────────────────
    lock_file_path = os.path.join(ticket_folder, "INVOKE_LOCK.pid")
    lock_fd = _acquire_process_lock(lock_file_path)
    if lock_fd is None:
        ilog.warning(f"process lockfile ya tomado por otro proceso — abortando")
        tlock.release()
        return False

    ilog.lock_acquired()

    try:
        # ── 3: EN_CURSO flag atómico en disco ──────────────────────────────
        try:
            with open(en_curso_flag_path, "x") as _ecf:
                _ecf.write(f"{os.getpid()}\n{datetime.datetime.now().isoformat()}")
        except FileExistsError:
            ilog.en_curso_exists(en_curso_flag_path)
            return False

        ilog.en_curso_created(en_curso_flag_path)

        try:
            # ── 4: Invocar agente ───────────────────────────────────────────
            ilog.bridge_call(agent_name, len(prompt))
            kwargs = extra_bridge_kwargs or {}
            ok = bridge_invoke_fn(prompt, agent_name=agent_name, **kwargs)
            ilog.bridge_result(ok)

            if ok:
                ilog.end(success=True)
                if on_success:
                    on_success()
            else:
                reason = f"bridge_invoke_fn retornó False para {agent_name}"
                ilog.error(reason)
                ilog.end(success=False)
                if on_failure:
                    on_failure(reason)
                _safe_remove(en_curso_flag_path)
                ilog.en_curso_cleaned(en_curso_flag_path)

            return ok

        except Exception as e:
            ilog.error(f"Excepción al invocar agente: {e}")
            ilog.end(success=False)
            if on_failure:
                on_failure(str(e))
            _safe_remove(en_curso_flag_path)
            return False

    finally:
        _release_process_lock(lock_file_path, lock_fd)
        tlock.release()


def _safe_remove(path: str) -> None:
    """Elimina un archivo sin lanzar excepción si no existe."""
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception:
        pass
