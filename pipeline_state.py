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


def save_state(state_path: str, state: dict) -> None:
    """Guarda el estado con timestamp actualizado. Invalida cache.
    Thread-safe: lock exclusivo durante escritura + actualización de cache."""
    with _state_lock:
        state["last_run"] = datetime.now().isoformat()
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
        # Invalidar cache para que el próximo load_state re-lea
        _load_cache["mtime"] = 0.0


def get_ticket_state(state: dict, ticket_id: str) -> str:
    """Retorna estado actual del ticket o 'pendiente_pm' si no existe."""
    return state.get("tickets", {}).get(ticket_id, {}).get("estado", "pendiente_pm")


def set_ticket_state(state: dict, ticket_id: str, new_state: str, **kwargs) -> None:
    """Actualiza el estado de un ticket."""
    if ticket_id not in state["tickets"]:
        state["tickets"][ticket_id] = {}

    entry = state["tickets"][ticket_id]
    entry["estado"] = new_state
    entry[f"{new_state}_at"] = datetime.now().isoformat()

    # Si es un estado de "en proceso", registrar metadata del proceso invocador
    if new_state.endswith("_en_proceso"):
        import os as _os
        entry["invoking_pid"]       = _os.getpid()
        entry["invoke_started_at"]  = datetime.now().isoformat()
        entry["invoke_ttl_minutes"] = kwargs.pop("invoke_ttl_minutes", 120)
        entry["invoke_host"]        = _socket.gethostname()

    for key, value in kwargs.items():
        entry[key] = value


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
    sino usa auto_priority calculado desde la gravedad de Mantis.
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
            _logging.getLogger("mantis.state").warning(
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
