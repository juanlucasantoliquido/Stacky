"""
pipeline_state.py — Gestión del estado del pipeline por ticket.
"""

import json
import os
import socket as _socket
import threading
from datetime import datetime

# Lock global para lecturas/escrituras concurrentes del state.json
# (re-entrante: el mismo thread puede adquirirlo múltiples veces sin deadlock)
_state_lock = threading.RLock()

ESTADOS_VALIDOS = [
    "pendiente_pm", "pm_en_proceso", "pm_completado",
    "dev_en_proceso", "dev_completado",
    "tester_en_proceso", "tester_completado",
    # M-01: estados de rework QA→DEV
    "qa_rework", "dev_rework_en_proceso", "dev_rework_completado",
    "completado",
    "error_pm", "error_dev", "error_tester",
    # Y-01: estados de PM revision (loop infinito)
    "pm_revision", "pm_revision_en_proceso", "pm_revision_completado",
    "stagnation_detected",
    # Y-04: DBA Especialista
    "dba_en_proceso", "dba_completado", "error_dba",
    # Y-05: Tech Lead Reviewer
    "tl_review_en_proceso", "tl_aprobado", "tl_rechazado",
    # Sub-agentes PM (3 en cadena secuencial)
    "pm_inv_en_proceso", "pm_inv_completado",
    "pm_arq_en_proceso", "pm_arq_completado",
    "pm_plan_en_proceso",
    # Sub-agentes DEV (3 en cadena secuencial)
    "dev_loc_en_proceso", "dev_loc_completado",
    "dev_impl_en_proceso", "dev_impl_completado",
    "dev_doc_en_proceso",
    # Sub-agentes QA (3 en cadena secuencial)
    "qa_rev_en_proceso", "qa_rev_completado",
    "qa_exec_en_proceso", "qa_exec_completado",
    "qa_arb_en_proceso",
]

# ── mtime-cache para load_state ──────────────────────────────────────────────
_load_cache = {"path": "", "mtime": 0.0, "data": None}


def load_state(state_path: str) -> dict:
    """Carga pipeline/state.json con mtime-cache. Solo re-lee si cambió en disco.
    Thread-safe: adquiere el lock para evitar lecturas durante escrituras concurrentes."""
    with _state_lock:
        os.makedirs(os.path.dirname(state_path), exist_ok=True)
        if not os.path.exists(state_path):
            return {"tickets": {}, "last_run": None}
        try:
            mtime = os.path.getmtime(state_path)
        except OSError:
            return {"tickets": {}, "last_run": None}
        if (_load_cache["path"] == state_path
                and _load_cache["mtime"] == mtime
                and _load_cache["data"] is not None):
            return _load_cache["data"]
        with open(state_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        _load_cache["path"]  = state_path
        _load_cache["mtime"] = mtime
        _load_cache["data"]  = data
        return data


def _acquire_file_lock(lock_path: str, timeout_sec: float = 10.0):
    """A5: lock cross-process para serializar escrituras al state.json.
    En Windows usa msvcrt.locking (bloqueo cooperativo del SO sobre el archivo).
    Devuelve el file handle (a cerrar por el caller); None si no se pudo adquirir."""
    import time as _time
    deadline = _time.monotonic() + timeout_sec
    last_exc = None
    while _time.monotonic() < deadline:
        try:
            fh = open(lock_path, "a+b")
            try:
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                return fh
            except OSError as e:
                last_exc = e
                fh.close()
                _time.sleep(0.05)
        except Exception as e:
            last_exc = e
            _time.sleep(0.05)
    import logging as _logging
    _logging.getLogger("stacky.state").warning(
        "[A5] _acquire_file_lock timeout sobre %s: %s", lock_path, last_exc,
    )
    return None


def _release_file_lock(fh) -> None:
    if fh is None:
        return
    try:
        if os.name == "nt":
            import msvcrt
            try:
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
        else:
            import fcntl
            try:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
    finally:
        try:
            fh.close()
        except Exception:
            pass


def save_state(state_path: str, state: dict) -> None:
    """Guarda el estado con timestamp actualizado. Invalida cache.

    Thread-safe (lock intra-proceso) + cross-process safe (file lock + escritura
    atómica via temp+rename). Si el file lock no se adquiere a tiempo, se procede
    igualmente para no bloquear el daemon — la escritura sigue siendo atómica
    por temp+rename, así que el peor caso es un write perdido (no corrupción).
    """
    with _state_lock:
        state["last_run"] = datetime.now().isoformat()
        os.makedirs(os.path.dirname(state_path), exist_ok=True)

        lock_path = state_path + ".writelock"
        fh_lock   = _acquire_file_lock(lock_path, timeout_sec=10.0)
        try:
            tmp_path = state_path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2, ensure_ascii=False)
                f.flush()
                try:
                    os.fsync(f.fileno())
                except OSError:
                    pass
            os.replace(tmp_path, state_path)
        finally:
            _release_file_lock(fh_lock)
            try:
                if os.path.exists(lock_path):
                    os.remove(lock_path)
            except Exception:
                pass

        # Invalidar cache para que el próximo load_state re-lea
        _load_cache["mtime"] = 0.0


def get_ticket_state(state: dict, ticket_id: str) -> str:
    """Retorna estado actual del ticket o 'pendiente_pm' si no existe."""
    return state.get("tickets", {}).get(ticket_id, {}).get("estado", "pendiente_pm")


# A1: nombres canónicos de sub-agentes que componen cada stage padre
SUBAGENT_NAMES = {
    "pm_inv", "pm_arq", "pm_plan",
    "dev_loc", "dev_impl", "dev_doc",
    "qa_rev", "qa_exec", "qa_arb",
}


def set_ticket_state(state: dict, ticket_id: str, new_state: str, **kwargs) -> None:
    """Actualiza el estado de un ticket.

    Timing estructurado (consumido por stacky_metrics y ado_reporter):
      - `{stage}_started_at`  al entrar a `{stage}_en_proceso`
      - `{stage}_ended_at`    y `{stage}_duration_sec` al entrar a `{stage}_completado`
        o `error_{stage}`
    El timestamp legacy `{new_state}_at` se mantiene por retrocompatibilidad.

    A1 — tracking de sub-agentes: si la transición involucra a un sub-agente
    (pm_inv, pm_arq, pm_plan, dev_loc, ...), se actualizan automáticamente:
      - `current_subagent`        : nombre del sub-agente activo (o None al terminar)
      - `subagent_started_at`     : ISO timestamp de inicio
      - `subagent_history`        : lista de {name, started_at, ended_at, status, reason}
    """
    if ticket_id not in state["tickets"]:
        state["tickets"][ticket_id] = {}

    entry = state["tickets"][ticket_id]
    entry["estado"] = new_state
    now_iso = datetime.now().isoformat()
    entry[f"{new_state}_at"] = now_iso

    if new_state.endswith("_en_proceso"):
        stage = new_state[: -len("_en_proceso")]
        entry[f"{stage}_started_at"] = now_iso
        # Iteración DEV→QA: marca el inicio en el primer DEV / dev_rework
        if stage in ("dev", "dev_rework") and "iteration_started_at" not in entry:
            entry["iteration_started_at"] = now_iso

        # A1: si es sub-agente, abrir un slot en subagent_history
        if stage in SUBAGENT_NAMES:
            entry["current_subagent"]    = stage
            entry["subagent_started_at"] = now_iso
            entry.setdefault("subagent_history", []).append({
                "name":       stage,
                "started_at": now_iso,
                "ended_at":   None,
                "status":     "running",
                "reason":     None,
            })

        import os as _os
        entry["invoking_pid"]       = _os.getpid()
        entry["invoke_started_at"]  = now_iso
        entry["invoke_ttl_minutes"] = kwargs.pop("invoke_ttl_minutes", 120)
        entry["invoke_host"]        = _socket.gethostname()
    elif new_state.endswith("_completado") or new_state.startswith("error_"):
        if new_state.endswith("_completado"):
            stage = new_state[: -len("_completado")]
        else:
            stage = new_state[len("error_"):]
        entry[f"{stage}_ended_at"] = now_iso
        started = entry.get(f"{stage}_started_at")
        if started:
            try:
                dur = (datetime.fromisoformat(now_iso) - datetime.fromisoformat(started)).total_seconds()
                entry[f"{stage}_duration_sec"] = round(dur, 1)
            except Exception:
                pass

        # A1: cerrar el slot abierto del sub-agente
        if stage in SUBAGENT_NAMES:
            status = "ok" if new_state.endswith("_completado") else "error"
            history = entry.setdefault("subagent_history", [])
            for record in reversed(history):
                if record.get("name") == stage and record.get("status") == "running":
                    record["ended_at"] = now_iso
                    record["status"]   = status
                    record["reason"]   = kwargs.get("reason") or entry.get("error")
                    break
            entry["current_subagent"]    = None
            entry["subagent_started_at"] = None

    for key, value in kwargs.items():
        entry[key] = value


def record_iteration_end(state: dict, ticket_id: str, qa_verdict: str,
                         findings: list = None, duration_sec: float = None) -> int:
    """Cierra una iteración DEV→QA y la añade a `iteration_history`.

    Devuelve el número de iteración registrado.
    Mantiene también los contadores agregados `iterations` y `rework_count`.
    """
    entry = state.setdefault("tickets", {}).setdefault(ticket_id, {})
    iter_started = entry.pop("iteration_started_at", None)
    now_iso = datetime.now().isoformat()
    if duration_sec is None and iter_started:
        try:
            duration_sec = (datetime.fromisoformat(now_iso)
                            - datetime.fromisoformat(iter_started)).total_seconds()
        except Exception:
            duration_sec = None

    history = entry.setdefault("iteration_history", [])
    iter_num = len(history) + 1
    history.append({
        "iteration":      iter_num,
        "started_at":     iter_started,
        "ended_at":       now_iso,
        "duration_sec":   round(duration_sec, 1) if duration_sec is not None else None,
        "qa_verdict":     qa_verdict,
        "findings_count": len(findings or []),
    })
    entry["iterations"]   = iter_num
    entry["rework_count"] = max(0, iter_num - 1)
    return iter_num


def is_invoke_still_valid(entry: dict) -> bool:
    """
    SEQ-09: Verifica si la invocación registrada en un estado *_en_proceso
    sigue siendo válida (proceso vivo + TTL no expirado).

    Retorna True si:
    - El entry no tiene metadata de invocación (estado antiguo — compatible)
    - El proceso con invoking_pid sigue vivo
    - El TTL no expiró

    Retorna False si:
    - El proceso con invoking_pid ya no existe (zombie state)
    - El TTL expiró
    """
    pid     = entry.get("invoking_pid")
    started = entry.get("invoke_started_at")
    ttl_min = entry.get("invoke_ttl_minutes", 120)

    if not pid or not started:
        return True  # Sin metadata → asumir válido (compatibilidad hacia atrás)

    # Verificar TTL
    try:
        from datetime import datetime as _dt
        elapsed_min = (_dt.now() - _dt.fromisoformat(started)).total_seconds() / 60
        if elapsed_min > ttl_min:
            return False  # TTL expirado
    except Exception:
        pass  # Si no podemos parsear la fecha, no bloquear

    # Verificar si el proceso sigue vivo
    try:
        import os as _os
        _os.kill(pid, 0)  # signal 0 = solo verifica existencia
        return True  # proceso vivo
    except (ProcessLookupError, PermissionError):
        return False  # proceso muerto → zombie state
    except OSError:
        return True  # otro error OS → asumir válido


def mark_error(state: dict, ticket_id: str, stage: str, reason: str) -> None:
    """Marca un ticket como error en la etapa indicada."""
    error_state = f"error_{stage}"
    set_ticket_state(state, ticket_id, error_state)
    state["tickets"][ticket_id]["error"] = reason

    # Incrementar contador de intentos
    key = f"intentos_{stage}"
    state["tickets"][ticket_id][key] = state["tickets"][ticket_id].get(key, 0) + 1


def set_ticket_priority(state: dict, ticket_id: str, priority: int) -> None:
    """Asigna un número de prioridad al ticket (1 = primero). Se usa para ordenar la cola."""
    if ticket_id not in state["tickets"]:
        state["tickets"][ticket_id] = {}
    state["tickets"][ticket_id]["priority"] = priority


def get_ticket_priority(state: dict, ticket_id: str) -> int:
    """
    Retorna la prioridad del ticket.
    Respeta prioridad manual si fue asignada explícitamente,
    sino usa auto_priority calculado desde la gravedad del ticket.
    Sin ninguna = 9999 (al final de la cola).
    """
    entry = state.get("tickets", {}).get(ticket_id, {})
    manual = entry.get("priority")
    if manual is not None and manual != 9999:
        return int(manual)
    auto_p = entry.get("auto_priority")
    if auto_p is not None:
        return int(auto_p)
    return 9999


def get_pending_pm(state: dict) -> list:
    """Retorna ticket_ids pendientes de procesar por PM."""
    pending = []
    for tid, entry in state.get("tickets", {}).items():
        if entry.get("estado") in ("pendiente_pm", None):
            pending.append(tid)
    return pending


# ── Helpers de timeout y retry ────────────────────────────────────────────────

def get_stage_elapsed_minutes(state: dict, ticket_id: str, stage: str) -> float | None:
    """Retorna minutos transcurridos desde que inició la etapa, o None si no inició."""
    entry = state.get("tickets", {}).get(ticket_id, {})
    start = entry.get(f"{stage}_inicio_at")
    if not start:
        return None
    try:
        delta = datetime.now() - datetime.fromisoformat(start)
        return delta.total_seconds() / 60
    except Exception:
        return None


def is_stage_timed_out(state: dict, ticket_id: str, stage: str, timeout_minutes: int) -> bool:
    """True si la etapa lleva más de timeout_minutes en progreso."""
    elapsed = get_stage_elapsed_minutes(state, ticket_id, stage)
    if elapsed is None:
        return False
    return elapsed > timeout_minutes


def get_retry_count(state: dict, ticket_id: str, stage: str) -> int:
    """Retorna el número de intentos previos para la etapa."""
    return state.get("tickets", {}).get(ticket_id, {}).get(f"intentos_{stage}", 0)


def get_tickets_needing_action(state: dict) -> list:
    """
    Retorna lista de dicts {ticket_id, reason, estado} para tickets
    en estado error_* (requieren intervención manual).
    """
    result = []
    for tid, entry in state.get("tickets", {}).items():
        est = entry.get("estado", "")
        if est.startswith("error_"):
            result.append({
                "ticket_id": tid,
                "reason":    entry.get("error", "Error desconocido"),
                "estado":    est,
            })
    return result


# ── SEQ-10: auto_advance validado ────────────────────────────────────────────

# Estados que pueden legítimamente activar auto_advance hacia otro estado
_VALID_AUTO_ADVANCE_TRANSITIONS: dict = {
    "pm_completado":         "dev_en_proceso",
    "dev_completado":        "tester_en_proceso",
    "tester_completado":     "completado",
    "qa_rework":             "dev_rework_en_proceso",      # M-01
    "dev_rework_completado": "tester_en_proceso",          # M-01
    # Sub-agentes PM
    "pm_inv_completado":     "pm_arq_en_proceso",
    "pm_arq_completado":     "pm_plan_en_proceso",
    # Sub-agentes DEV
    "dev_loc_completado":    "dev_impl_en_proceso",
    "dev_impl_completado":   "dev_doc_en_proceso",
    # Sub-agentes QA
    "qa_rev_completado":     "qa_exec_en_proceso",
    "qa_exec_completado":    "qa_arb_en_proceso",
}


def set_auto_advance(state: dict, ticket_id: str, target_state: str,
                     state_path: str = None) -> bool:
    """
    SEQ-10: Activa auto_advance solo si el estado actual del ticket es coherente
    con la transición hacia target_state.

    Retorna True si se activó, False si se rechazó por estado incoherente.
    """
    with _state_lock:
        current = get_ticket_state(state, ticket_id)

        # Buscar qué estado "origen" debería tener el ticket para llegar a target_state
        reverse_map = {v: k for k, v in _VALID_AUTO_ADVANCE_TRANSITIONS.items()}
        expected_current = reverse_map.get(target_state)

        if expected_current and current != expected_current:
            import logging as _logging
            _logging.getLogger("stacky.state").warning(
                "[SEQ-10] set_auto_advance rechazado para %s: "
                "estado actual '%s' no es coherente con avanzar hacia '%s' "
                "(se esperaba '%s')",
                ticket_id, current, target_state, expected_current,
            )
            return False

        entry = state.setdefault("tickets", {}).setdefault(ticket_id, {})
        entry["auto_advance"]    = True
        entry["auto_advance_to"] = target_state

        if state_path:
            save_state(state_path, state)
        return True


def clear_auto_advance(state: dict, ticket_id: str, state_path: str = None) -> None:
    """
    SEQ-10: Limpia auto_advance de un ticket (cuando fue procesado o cuando
    el estado cambió y el auto_advance quedó obsoleto).
    """
    with _state_lock:
        entry = state.get("tickets", {}).get(ticket_id)
        if entry:
            entry["auto_advance"]    = False
            entry["auto_advance_to"] = None
        if state_path:
            save_state(state_path, state)
