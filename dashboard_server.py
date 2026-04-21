"""
dashboard_server.py — Servidor Flask para el dashboard visual del pipeline.

Uso:
    cd Tools/Stacky
    pip install flask
    python dashboard_server.py
    # Abrir http://localhost:5050
"""

import json
import os
import re
import subprocess
import threading
import sys
import uuid
from datetime import datetime
from pathlib import Path
from flask import Flask, Response, jsonify, request, send_from_directory

# SEQ-02: Lock por ticket — evita invocaciones concurrentes del mismo ticket
# dentro del mismo proceso (complementa el EN_CURSO flag en disco)
import collections as _collections
_ticket_invoke_locks: dict = _collections.defaultdict(lambda: __import__('threading').Lock())
_ticket_locks_rlock = __import__('threading').Lock()

# ── Gate global de ticket activo ─────────────────────────────────────────────
# Política: un único ticket puede estar procesándose a la vez. Cualquier otro
# intento de invocar PM/DEV/TESTER desde el reconciliador, el watcher, el Rally
# o un auto-advance es rechazado mientras haya un ticket "en vuelo".
# El gate se libera cuando el ticket activo llega a un estado terminal:
#   completado, bloqueo_humano, pm_revision, error_*, qa_rework
# (todos los que no auto-avanzan y requieren intervención/fin).
_active_ticket_id = None            # type: "str | None"
_active_ticket_since = None         # type: "float | None"  (monotonic)
_active_ticket_lock = __import__('threading').RLock()
# Safety net: libera por timeout si un ticket queda colgado sin cerrar.
_ACTIVE_TICKET_TIMEOUT_MIN = 180
_ACTIVE_TICKET_TERMINAL_STATES = frozenset((
    "completado", "bloqueo_humano", "pm_revision", "qa_rework",
))


def _is_terminal_gate_state(estado: str) -> bool:
    """Estados que liberan el gate global (pipeline pausado o finalizado)."""
    if not estado:
        return False
    if estado in _ACTIVE_TICKET_TERMINAL_STATES:
        return True
    return estado.startswith("error_")


def _try_claim_active_ticket(ticket_id: str) -> bool:
    """
    Toma el gate global para ticket_id. Devuelve:
      True  — si el gate estaba libre (claim nuevo) o ya era del mismo ticket (renovación).
      False — si otro ticket está activo.
    El mismo ticket puede re-claim entre stages (pm → dev → tester).
    """
    global _active_ticket_id, _active_ticket_since
    with _active_ticket_lock:
        now_mono = _time.monotonic()
        # Safety: liberación por timeout
        if (_active_ticket_id is not None
                and _active_ticket_since is not None
                and (now_mono - _active_ticket_since) > (_ACTIVE_TICKET_TIMEOUT_MIN * 60)):
            print(f"[GATE] Timeout — liberando ticket #{_active_ticket_id} "
                  f"tras {_ACTIVE_TICKET_TIMEOUT_MIN} min sin cerrar",
                  file=sys.stderr, flush=True)
            _active_ticket_id = None
            _active_ticket_since = None
        if _active_ticket_id is None:
            _active_ticket_id = ticket_id
            _active_ticket_since = now_mono
            print(f"[GATE] #{ticket_id} toma el gate (pipeline serial activo)",
                  flush=True)
            return True
        if _active_ticket_id == ticket_id:
            # Renovar: mismo ticket avanzando a la siguiente etapa.
            _active_ticket_since = now_mono
            return True
        return False


def _release_active_ticket(ticket_id: str, reason: str = "") -> bool:
    """Libera el gate si ticket_id es el dueño. Devuelve True si liberó."""
    global _active_ticket_id, _active_ticket_since
    with _active_ticket_lock:
        if _active_ticket_id == ticket_id:
            _active_ticket_id = None
            _active_ticket_since = None
            print(f"[GATE] #{ticket_id} liberado — {reason or 'sin detalle'}",
                  flush=True)
            return True
        return False


def _get_active_ticket():
    """Devuelve el ticket_id activo o None si el gate está libre."""
    with _active_ticket_lock:
        return _active_ticket_id


def _maybe_release_if_terminal(ticket_id: str, estado: str) -> None:
    """Si ticket_id está activo y estado es terminal → libera."""
    if _is_terminal_gate_state(estado) and _get_active_ticket() == ticket_id:
        _release_active_ticket(ticket_id, f"estado terminal: {estado}")

# ── Rutas base ────────────────────────────────────────────────────────────────
BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
TICKETS_BASE = os.path.join(BASE_DIR, "tickets")
STATE_PATH   = os.path.join(BASE_DIR, "pipeline", "state.json")
PLACEHOLDER  = "_A completar por PM_"
PM_FILES     = [
    "INCIDENTE.md", "ANALISIS_TECNICO.md", "ARQUITECTURA_SOLUCION.md",
    "TAREAS_DESARROLLO.md", "QUERIES_ANALISIS.sql", "NOTAS_IMPLEMENTACION.md",
]

# ── VS Code Bridge (extensión HTTP interna) ───────────────────────────────────
BRIDGE_PORT = 5051
BRIDGE_URL  = f"http://127.0.0.1:{BRIDGE_PORT}"

app = Flask(__name__, static_folder=BASE_DIR)

# ── Cache layer ──────────────────────────────────────────────────────────────
import time as _time

_runtime_cache      = {"data": None, "ts": 0.0}
_RUNTIME_TTL        = 10.0  # segundos — config de proyecto casi nunca cambia

_state_cache        = {"data": None, "mtime": 0.0, "path": ""}
_scan_cache         = {"data": None, "ts": 0.0, "state_mtime": 0.0}
_SCAN_TTL           = 3.0  # segundos — evita re-escanear el filesystem en ráfagas de polling
_title_cache: dict  = {}    # ticket_id → titulo (títulos nunca cambian post-scrape)

# SEQ-04: Timestamps de set_state manual para cooldown del watcher (30s)
_manual_set_timestamps: dict = {}
_MANUAL_SET_COOLDOWN_SECONDS: int = 30


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_runtime() -> dict:
    """Retorna configuración dinámica del proyecto activo (paths y agentes).
    Cacheada con TTL de 10s — evita re-leer config.json en cada request/ciclo."""
    now = _time.monotonic()
    if _runtime_cache["data"] and (now - _runtime_cache["ts"]) < _RUNTIME_TTL:
        return _runtime_cache["data"]
    try:
        from project_manager import get_active_project, get_project_config, get_project_paths
        name = get_active_project()
        cfg  = get_project_config(name)
        if cfg:
            paths = get_project_paths(name)
            result = {
                "name":           name,
                "display_name":   cfg.get("display_name", name),
                "workspace_root": cfg.get("workspace_root",
                                         os.path.abspath(os.path.join(BASE_DIR, "..", ".."))),
                "tickets_base":   paths["tickets"],
                "state_path":     paths["state"],
                "agents":         cfg.get("agents", {"pm": "PM-TL STack 3",
                                                     "dev": "DevStack3",
                                                     "tester": "QA"}),
            }
            _runtime_cache["data"] = result
            _runtime_cache["ts"]   = now
            return result
    except Exception:
        pass
    fallback = {
        "name":           "RIPLEY",
        "display_name":   "RIPLEY",
        "workspace_root": os.path.abspath(os.path.join(BASE_DIR, "..", "..")),
        "tickets_base":   TICKETS_BASE,
        "state_path":     STATE_PATH,
        "agents":         {"pm": "PM-TL STack 3", "dev": "DevStack3", "tester": "QA"},
    }
    _runtime_cache["data"] = fallback
    _runtime_cache["ts"]   = now
    return fallback


def _invalidate_runtime_cache():
    """Forzar recarga en el próximo _get_runtime() (e.g. al cambiar proyecto)."""
    _runtime_cache["ts"] = 0.0


def _load_pipeline_state() -> dict:
    """Carga state.json solo si cambió en disco (mtime-based cache)."""
    sp = _get_runtime()["state_path"]
    if not os.path.exists(sp):
        return {"tickets": {}, "last_run": None}
    try:
        mtime = os.path.getmtime(sp)
    except OSError:
        return {"tickets": {}, "last_run": None}
    if _state_cache["path"] == sp and _state_cache["mtime"] == mtime and _state_cache["data"]:
        return _state_cache["data"]
    with open(sp, "r", encoding="utf-8") as f:
        data = json.load(f)
    _state_cache["data"]  = data
    _state_cache["mtime"] = mtime
    _state_cache["path"]  = sp
    return data


def _save_pipeline_state(state: dict):
    sp = _get_runtime()["state_path"]
    os.makedirs(os.path.dirname(sp), exist_ok=True)
    state["last_run"] = datetime.now().isoformat()
    with open(sp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    # Invalidar caches para que el próximo read/scan vea el nuevo estado
    _state_cache["mtime"] = 0.0
    _scan_cache["ts"] = 0.0


# A4: helper para anexar el bloque heartbeat al prompt antes de invocar al agente.
# Mapea cada (sub-)agente a la etapa padre (PM/DEV/TESTER) — todos los sub-agentes
# de PM comparten el mismo archivo PM_HEARTBEAT.txt. Best-effort: si el helper no
# está disponible (instalación parcial), devuelve el prompt sin modificar.
_STAGE_TO_HEARTBEAT_LABEL = {
    "pm": "PM", "pm_inv": "PM", "pm_arq": "PM", "pm_plan": "PM",
    "dev": "DEV", "dev_loc": "DEV", "dev_impl": "DEV", "dev_doc": "DEV",
    "tester": "TESTER", "qa_rev": "TESTER", "qa_exec": "TESTER", "qa_arb": "TESTER",
}


def _with_heartbeat(prompt: str, stage_or_subagent: str) -> str:
    label = _STAGE_TO_HEARTBEAT_LABEL.get(stage_or_subagent)
    if not label:
        return prompt
    try:
        from prompt_builder import heartbeat_tail
        return prompt + heartbeat_tail(label)
    except Exception:
        return prompt


def _has_placeholders(folder: str) -> bool:
    for fname in PM_FILES:
        fpath = os.path.join(folder, fname)
        if not os.path.exists(fpath):
            continue
        try:
            content = open(fpath, encoding="utf-8").read()
            if PLACEHOLDER in content or "A completar por PM" in content:
                return True
        except Exception:
            pass
    return False


def _dev_completed(folder: str) -> bool:
    return os.path.exists(os.path.join(folder, "DEV_COMPLETADO.md"))


def _tester_completed(folder: str) -> bool:
    return os.path.exists(os.path.join(folder, "TESTER_COMPLETADO.md"))


def _read_tester_verdict(folder: str) -> str | None:
    """Lee TESTER_COMPLETADO.md y extrae el veredicto buscando el NEGATIVO primero.

    El orden importa: si el archivo contiene 'RECHAZADO' y también 'APROBADO'
    (por ejemplo en una sección de "Criterios aprobados"), debe ganar RECHAZADO.
    Devuelve 'APROBADO' | 'CON OBSERVACIONES' | 'RECHAZADO' | None si no aplica.
    """
    path = os.path.join(folder, "TESTER_COMPLETADO.md")
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            content = f.read().upper()
    except Exception:
        return None
    for v in ("RECHAZADO", "CON OBSERVACIONES", "APROBADO"):
        if v in content:
            return v
    return None


def _find_ticket_folder(ticket_id: str, tickets_base: str = None) -> str | None:
    """Busca la carpeta de un ticket en el tickets_base del proyecto activo."""
    base = tickets_base or _get_runtime()["tickets_base"]
    if not os.path.isdir(base):
        return None
    for estado_dir in os.listdir(base):
        candidate = os.path.join(base, estado_dir, ticket_id)
        if os.path.isdir(candidate):
            return candidate
    return None


def _pm_files_status(folder: str) -> dict:
    """Retorna estado de cada archivo PM: exists / has_placeholder."""
    result = {}
    for fname in PM_FILES:
        fpath = os.path.join(folder, fname)
        exists = os.path.exists(fpath)
        placeholder = False
        if exists:
            try:
                content = open(fpath, encoding="utf-8").read()
                placeholder = PLACEHOLDER in content or "A completar por PM" in content
            except Exception:
                pass
        result[fname] = {"exists": exists, "placeholder": placeholder}
    return result


_SQL_TRANSFORM_RE = None

def _has_sql_transforms(folder: str) -> bool:
    """Retorna True si QUERIES_ANALISIS.sql contiene DDL/DML de transformación de datos."""
    global _SQL_TRANSFORM_RE
    import re
    if _SQL_TRANSFORM_RE is None:
        _SQL_TRANSFORM_RE = re.compile(
            r'\b(INSERT|UPDATE|DELETE|ALTER|CREATE|DROP|TRUNCATE|MERGE|RENAME|UPSERT)\b',
            re.IGNORECASE,
        )
    fpath = os.path.join(folder, "QUERIES_ANALISIS.sql")
    if not os.path.exists(fpath):
        return False
    try:
        content = open(fpath, encoding="utf-8").read()
        return bool(_SQL_TRANSFORM_RE.search(content))
    except Exception:
        return False


def _calc_duration(pip_entry: dict, ini_key: str, fin_key: str):
    """Calcula duración entre dos timestamps ISO. Definida una sola vez, no por ticket."""
    try:
        ini = pip_entry.get(ini_key)
        fin = pip_entry.get(fin_key)
        if ini and fin:
            return round((datetime.fromisoformat(fin) - datetime.fromisoformat(ini)).total_seconds())
    except Exception:
        pass
    return None


def _get_ticket_title(ticket_folder: str, ticket_id: str) -> str:
    """Lee el título del ticket desde INC-{id}.md, con cache en memoria."""
    cached = _title_cache.get(ticket_id)
    if cached is not None:
        return cached

    titulo = "(sin título)"
    inc_file = os.path.join(ticket_folder, f"INC-{ticket_id}.md")
    if os.path.exists(inc_file):
        try:
            with open(inc_file, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("**Título:**"):
                        titulo = line.replace("**Título:**", "").strip()
                        break
                    if line.startswith("# "):
                        titulo = line.lstrip("# ").strip()
                        break
        except Exception:
            pass

    _title_cache[ticket_id] = titulo
    return titulo


def _scan_tickets() -> list:
    """Escanea tickets/ del proyecto activo y combina con state.json.
    Resultado cacheado por 3 segundos y/o hasta que state.json cambie en disco."""
    now = _time.monotonic()
    rt  = _get_runtime()

    # Check rápido: ¿state.json cambió desde el último scan?
    sp = rt["state_path"]
    try:
        state_mtime = os.path.getmtime(sp) if os.path.exists(sp) else 0.0
    except OSError:
        state_mtime = 0.0

    if (_scan_cache["data"] is not None
            and (now - _scan_cache["ts"]) < _SCAN_TTL
            and _scan_cache["state_mtime"] == state_mtime):
        return _scan_cache["data"]

    pipeline_state = _load_pipeline_state()
    tickets        = []

    if not os.path.isdir(rt["tickets_base"]):
        _scan_cache.update(data=tickets, ts=now, state_mtime=state_mtime)
        return tickets

    for estado_dir in sorted(os.listdir(rt["tickets_base"])):
        estado_path = os.path.join(rt["tickets_base"], estado_dir)
        if not os.path.isdir(estado_path):
            continue

        for ticket_id in sorted(os.listdir(estado_path)):
            ticket_folder = os.path.join(estado_path, ticket_id)
            if not os.path.isdir(ticket_folder):
                continue

            titulo = _get_ticket_title(ticket_folder, ticket_id)

            pip_entry = pipeline_state.get("tickets", {}).get(ticket_id, {})
            pip_estado = pip_entry.get("estado", "pendiente_pm")

            # Inferir estado real desde filesystem solo si el ticket nunca fue
            # registrado explícitamente (clave "estado" ausente).
            estado_es_inferido = "estado" not in pip_entry
            if pip_estado == "pendiente_pm" and estado_es_inferido:
                if _tester_completed(ticket_folder):
                    pip_estado = "completado"
                elif _dev_completed(ticket_folder):
                    pip_estado = "dev_completado"
                elif not _has_placeholders(ticket_folder):
                    pip_estado = "pm_completado"

            tickets.append({
                "ticket_id":        ticket_id,
                "titulo":           titulo,
                "estado_tracker":    estado_dir,
                "asignado":         pip_entry.get("asignado", ""),
                "estado_base":      pip_entry.get("estado_base", estado_dir),
                "pipeline_estado":  pip_estado,
                "folder":           ticket_folder,
                "pm_files":         _pm_files_status(ticket_folder),
                "dev_completado":   _dev_completed(ticket_folder),
                "has_placeholders": _has_placeholders(ticket_folder),
                "error":            pip_entry.get("error"),
                "intentos_pm":      pip_entry.get("intentos_pm", 0),
                "intentos_dev":     pip_entry.get("intentos_dev", 0),
                "intentos_tester":  pip_entry.get("intentos_tester", 0),
                "pm_completado_at":      pip_entry.get("pm_completado_at"),
                "dev_completado_at":     pip_entry.get("dev_completado_at"),
                "tester_completado_at":  pip_entry.get("tester_completado_at"),
                "completado_at":         pip_entry.get("completado_at"),
                "pm_inicio_at":          pip_entry.get("pm_inicio_at"),
                "pm_fin_at":             pip_entry.get("pm_fin_at"),
                "dev_inicio_at":         pip_entry.get("dev_inicio_at"),
                "dev_fin_at":            pip_entry.get("dev_fin_at"),
                "tester_inicio_at":      pip_entry.get("tester_inicio_at"),
                "tester_fin_at":         pip_entry.get("tester_fin_at"),
                "dur_pm_seg":            _calc_duration(pip_entry, "pm_inicio_at", "pm_fin_at"),
                "dur_dev_seg":           _calc_duration(pip_entry, "dev_inicio_at", "dev_fin_at"),
                "dur_tester_seg":        _calc_duration(pip_entry, "tester_inicio_at", "tester_fin_at"),
                "tester_completado":  _tester_completed(ticket_folder),
                "priority":           pip_entry.get("priority", 9999),
                "last_qa_verdict":    pip_entry.get("last_qa_verdict"),
                "rework_count":       pip_entry.get("rework_count", 0),
                "qa_findings":        pip_entry.get("qa_findings", []),
                "tester_verdict":     _read_tester_verdict(ticket_folder),
                "last_unstick":       pip_entry.get("last_unstick"),
                "has_sql_transforms": _has_sql_transforms(ticket_folder),
                "last_invoke":        pip_entry.get("last_invoke"),
                "paused":             os.path.exists(os.path.join(ticket_folder, "PAUSED.flag")),
                "paused_at":          pip_entry.get("paused_at"),
            })

    _scan_cache.update(data=tickets, ts=now, state_mtime=state_mtime)
    return tickets


# ── API endpoints ─────────────────────────────────────────────────────────────

@app.route("/api/dev_summary/<ticket_id>")
def api_dev_summary(ticket_id):
    """Retorna el contenido de DEV_COMPLETADO.md formateado para el dashboard."""
    folder = _find_ticket_folder(ticket_id)
    if not folder:
        return jsonify({"ok": False, "error": "Ticket no encontrado"}), 404
    fpath = os.path.join(folder, "DEV_COMPLETADO.md")
    if not os.path.exists(fpath):
        return jsonify({"ok": False, "error": "DEV_COMPLETADO.md no encontrado"}), 404
    try:
        content = open(fpath, encoding="utf-8").read()
        return jsonify({"ok": True, "content": content})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/tester_summary/<ticket_id>")
def api_tester_summary(ticket_id):
    """Retorna el contenido de TESTER_COMPLETADO.md formateado para el dashboard."""
    folder = _find_ticket_folder(ticket_id)
    if not folder:
        return jsonify({"ok": False, "error": "Ticket no encontrado"}), 404
    fpath = os.path.join(folder, "TESTER_COMPLETADO.md")
    if not os.path.exists(fpath):
        return jsonify({"ok": False, "error": "TESTER_COMPLETADO.md no encontrado"}), 404
    try:
        content = open(fpath, encoding="utf-8").read()
        return jsonify({"ok": True, "content": content})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/ticket_detail/<ticket_id>")
def api_ticket_detail(ticket_id):
    """Retorna el contenido de INC-{id}.md (detalle completo del ticket)."""
    folder = _find_ticket_folder(ticket_id)
    if not folder:
        return jsonify({"ok": False, "error": "Ticket no encontrado"}), 404
    fpath = os.path.join(folder, f"INC-{ticket_id}.md")
    if not os.path.exists(fpath):
        return jsonify({"ok": False, "error": f"INC-{ticket_id}.md no encontrado"}), 404
    try:
        content = open(fpath, encoding="utf-8").read()
        return jsonify({"ok": True, "content": content})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/tickets")
def api_tickets():
    return jsonify(_scan_tickets())


@app.route("/api/state")
def api_state():
    state = _load_pipeline_state()
    tickets = _scan_tickets()
    return jsonify({
        "last_run": state.get("last_run"),
        "total": len(tickets),
        "por_estado": _count_by_estado(tickets),
        "tickets": tickets,
    })


def _count_by_estado(tickets: list) -> dict:
    counts = {}
    for t in tickets:
        e = t["pipeline_estado"]
        counts[e] = counts.get(e, 0) + 1
    return counts


@app.route("/api/set_state", methods=["POST"])
def api_set_state():
    """Permite al dashboard marcar manualmente el estado de un ticket."""
    data = request.json or {}
    ticket_id = data.get("ticket_id")
    new_state  = data.get("estado")
    if not ticket_id or not new_state:
        return jsonify({"ok": False, "error": "ticket_id y estado requeridos"}), 400

    state = _load_pipeline_state()
    if ticket_id not in state["tickets"]:
        state["tickets"][ticket_id] = {}

    entry = state["tickets"][ticket_id]

    if new_state == "pendiente_pm":
        # Reset completo: limpiar todo excepto campos de identificación
        keep = {k: entry[k] for k in ("asignado", "estado_base", "titulo", "folder", "priority")
                if k in entry}
        state["tickets"][ticket_id] = keep
        state["tickets"][ticket_id]["estado"] = "pendiente_pm"
        state["tickets"][ticket_id]["reset_at"] = datetime.now().isoformat()

        # Eliminar flags del filesystem para que el watcher no reviva el estado
        folder = _find_ticket_folder(ticket_id)
        if folder:
            for flag in ("PM_COMPLETADO.flag", "PM_ERROR.flag",
                         "DEV_ERROR.flag", "TESTER_ERROR.flag"):
                fp = os.path.join(folder, flag)
                if os.path.exists(fp):
                    try:
                        os.remove(fp)
                    except Exception:
                        pass
    else:
        entry["estado"] = new_state
        entry[f"{new_state}_at"] = datetime.now().isoformat()
        # Limpiar error si se está reintentando
        if new_state in ("pm_completado", "dev_completado"):
            entry.pop("error", None)
        # SEQ-06: set_state manual NUNCA activa auto_advance
        # (auto_advance=True solo se activa vía transiciones automáticas del watcher)
        entry["auto_advance"] = False

    _save_pipeline_state(state)

    # SEQ-04: Limpiar todos los EN_CURSO flags al hacer set_state manual
    folder = _find_ticket_folder(ticket_id)
    if folder and os.path.isdir(folder):
        for en_curso_fname in (
            "PM_AGENTE_EN_CURSO.flag",
            "DEV_AGENTE_EN_CURSO.flag",
            "TESTER_AGENTE_EN_CURSO.flag",
            "DOC_AGENTE_EN_CURSO.flag",
        ):
            ec_path = os.path.join(folder, en_curso_fname)
            if os.path.exists(ec_path):
                try:
                    os.remove(ec_path)
                except Exception:
                    pass

    # SEQ-04: Registrar timestamp del set_state manual para cooldown del watcher
    _manual_set_timestamps[ticket_id] = _time.time()

    return jsonify({"ok": True, "ticket_id": ticket_id, "nuevo_estado": new_state})


@app.route("/api/set_priority", methods=["POST"])
def api_set_priority():
    """
    Asigna prioridad a un ticket para controlar el orden de procesamiento.
    Body: { "ticket_id": "0027559", "priority": 1 }
    O para reordenar lista completa:
    Body: { "order": ["0027559", "0027560", "0027561"] }  <- prioridad = índice+1
    """
    data = request.json or {}
    state = _load_pipeline_state()

    if "order" in data:
        # Reordenamiento masivo desde drag-and-drop del dashboard.
        # Resetea a 9999 los tickets que ANTES estaban en el Rally pero quedaron
        # afuera de la nueva orden, para que no se mantengan fantasmas entre sesiones.
        order_set = {str(t) for t in data["order"]}
        for tid, entry in state.get("tickets", {}).items():
            p = entry.get("priority")
            if isinstance(p, int) and p < 9999 and str(tid) not in order_set:
                entry["priority"] = 9999
        for i, tid in enumerate(data["order"], 1):
            if tid not in state["tickets"]:
                state["tickets"][tid] = {}
            state["tickets"][tid]["priority"] = i
        _save_pipeline_state(state)
        return jsonify({"ok": True, "reordenados": len(data["order"])})

    ticket_id = data.get("ticket_id")
    priority  = data.get("priority")
    if not ticket_id or priority is None:
        return jsonify({"ok": False, "error": "ticket_id y priority requeridos"}), 400

    if ticket_id not in state["tickets"]:
        state["tickets"][ticket_id] = {}
    state["tickets"][ticket_id]["priority"] = int(priority)
    _save_pipeline_state(state)
    return jsonify({"ok": True, "ticket_id": ticket_id, "priority": int(priority)})


# ── Rally play/pause ─────────────────────────────────────────────────────────
# El Rally nunca arranca solo. Requiere POST /api/rally/start para avanzar,
# y se apaga solo cuando se vacía la cola (ver _rally_launch_next).

@app.route("/api/rally/status", methods=["GET"])
def api_rally_status():
    state = _load_pipeline_state()
    pending = sum(
        1 for t in state.get("tickets", {}).values()
        if isinstance(t.get("priority"), int) and t["priority"] < 9999
        and not t.get("estado", "").endswith("_en_proceso")
    )
    return jsonify({
        "ok":       True,
        "running":  bool(state.get("rally_running", False)),
        "pending":  pending,
    })


@app.route("/api/rally/start", methods=["POST"])
def api_rally_start():
    """Activa el flag rally_running y lanza el próximo ticket elegible."""
    state = _load_pipeline_state()
    state["rally_running"] = True
    _save_pipeline_state(state)
    threading.Thread(
        target=_rally_launch_next, args=("api/rally/start",),
        daemon=True, name="rally-start",
    ).start()
    return jsonify({"ok": True, "running": True})


@app.route("/api/rally/stop", methods=["POST"])
def api_rally_stop():
    """Pausa el Rally: los tickets siguen en cola pero no avanzan solos."""
    state = _load_pipeline_state()
    state["rally_running"] = False
    _save_pipeline_state(state)
    return jsonify({"ok": True, "running": False})


@app.route("/api/run_pipeline", methods=["POST"])
def api_run_pipeline():
    """Dispara el pipeline en un thread background."""
    data = request.json or {}
    ticket_id  = data.get("ticket_id")
    stage_only = data.get("stage")  # "pm" | "dev" | "tester" | None (full pipeline)

    def _run():
        try:
            rt = _get_runtime()
            if stage_only:
                # Etapa puntual — marcar auto_advance para etapas no finales
                # (pm → dev, dev → tester) para que el watcher encadene automáticamente
                if stage_only != "tester":
                    from pipeline_state import load_state, save_state
                    st = load_state(rt["state_path"])
                    st.setdefault("tickets", {}).setdefault(ticket_id, {})
                    st["tickets"][ticket_id]["auto_advance"] = True
                    save_state(rt["state_path"], st)
                _invoke_stage(ticket_id, stage_only)
            else:
                # Full pipeline — determinar primera etapa pendiente y marcar auto_advance
                from pipeline_state import load_state, save_state
                st = load_state(rt["state_path"])
                st.setdefault("tickets", {}).setdefault(ticket_id, {})
                st["tickets"][ticket_id]["auto_advance"] = True
                save_state(rt["state_path"], st)

                # Determinar etapa de inicio según estado actual del ticket
                est = st["tickets"][ticket_id].get("estado", "pendiente_pm")

                # ── Leer flag de sub-agentes ──────────────────────────────
                _use_sub = False
                try:
                    import json as _jcfg2
                    _cfg2 = _jcfg2.load(open(os.path.join(BASE_DIR, "config.json"),
                                             encoding="utf-8"))
                    _use_sub = _cfg2.get("pipeline", {}).get("use_sub_agents", False)
                except Exception:
                    pass

                if est in ("pendiente_pm", "error_pm"):
                    first_stage = "pm_inv" if _use_sub else "pm"
                elif est == "pm_inv_completado":
                    first_stage = "pm_arq"
                elif est == "pm_arq_completado":
                    first_stage = "pm_plan"
                elif est in ("pm_completado", "error_dev"):
                    first_stage = "dev_loc" if _use_sub else "dev"
                elif est == "dev_loc_completado":
                    first_stage = "dev_impl"
                elif est == "dev_impl_completado":
                    first_stage = "dev_doc"
                elif est in ("dev_completado", "error_tester"):
                    first_stage = "qa_rev" if _use_sub else "tester"
                elif est == "qa_rev_completado":
                    first_stage = "qa_exec"
                elif est == "qa_exec_completado":
                    first_stage = "qa_arb"
                elif est.endswith("_en_proceso"):
                    # Ya hay un agente corriendo — no relanzar para evitar duplicados.
                    # El watcher detectará el flag de completado y avanzará solo.
                    print(f"[FULL-PIPELINE] Ticket {ticket_id} en '{est}' "
                          f"— agente ya en curso, ignorando invocación duplicada", file=sys.stderr)
                    return
                elif est in ("completado", "tester_completado"):
                    # Pipeline ya terminado — no hacer nada
                    print(f"[FULL-PIPELINE] Ticket {ticket_id} en '{est}' — pipeline ya completado",
                          file=sys.stderr)
                    return
                else:
                    # Estado no reconocido → empezar desde PM
                    first_stage = "pm"

                print(f"[FULL-PIPELINE] Ticket {ticket_id} — estado '{est}' → iniciando desde '{first_stage}'",
                      file=sys.stderr)
                _invoke_stage(ticket_id, first_stage)
        except Exception as e:
            print(f"[DASHBOARD] Error en full pipeline: {e}", file=sys.stderr)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return jsonify({"ok": True, "iniciado": True, "ticket_id": ticket_id, "stage": stage_only})


def _invoke_stage(ticket_id: str, stage: str, force: bool = False):
    """
    Invoca el agente para una etapa.
    Después de invocar, lanza un thread de fondo que espera el flag de
    completado y avanza automáticamente a la siguiente etapa (PM→DEV→TESTER).
    Registra el resultado en state["tickets"][id]["last_invoke"].

    Si force=True, salta los guardias de PAUSED.flag / EN_CURSO / lock de
    threading / gate global, limpiando todos los cerrojos antes de invocar.
    Útil para "Force Reinvoke" desde el dashboard cuando el pipeline está atascado.
    """
    from copilot_bridge import invoke_agent
    from pipeline_state import load_state, save_state, set_ticket_state, mark_error

    rt     = _get_runtime()
    state  = load_state(rt["state_path"])
    folder = _find_ticket_folder(ticket_id, rt["tickets_base"])

    def _record_invoke(ok: bool, detail: str = ""):
        s2 = load_state(rt["state_path"])
        s2.setdefault("tickets", {}).setdefault(ticket_id, {})["last_invoke"] = {
            "stage":  stage,
            "ok":     ok,
            "at":     datetime.now().isoformat(),
            "detail": detail,
        }
        save_state(rt["state_path"], s2)

    if not folder:
        print(f"[{stage.upper()}-INVOKE] Carpeta no encontrada para {ticket_id}", file=sys.stderr)
        _record_invoke(False, "Carpeta no encontrada")
        return

    # ── PAUSED flag: respeta pausa manual (salvo force=True) ──────────────
    paused_flag = os.path.join(folder, "PAUSED.flag")
    if os.path.exists(paused_flag) and not force:
        print(f"[{stage.upper()}-INVOKE] {ticket_id}: PAUSED.flag presente — invocación diferida",
              file=sys.stderr, flush=True)
        _record_invoke(False, "Pipeline pausado (PAUSED.flag)")
        return

    # ── force=True: limpieza proactiva de todos los cerrojos del ticket ───
    # Esto permite que un "Force Reinvoke" desde el dashboard destrabe el pipeline
    # aunque haya EN_CURSO, INVOKE_LOCK.pid, locks de stage o el gate tomado.
    if force:
        try:
            from pipeline_lock import clear_all_locks as _clear_all_locks
            _clear_all_locks(ticket_id, folder)
        except Exception as _e:
            print(f"[{stage.upper()}-INVOKE] {ticket_id}: clear_all_locks falló: {_e}",
                  file=sys.stderr, flush=True)
        try:
            with _ticket_locks_rlock:
                _ticket_invoke_locks.pop(ticket_id, None)
        except Exception:
            pass
        try:
            _release_active_ticket(ticket_id, "force reinvoke")
        except Exception:
            pass

    agents = rt.get("agents", {})

    # SEQ-02: Lock en memoria por ticket (primera línea de defensa intra-proceso)
    _ticket_lock = _ticket_invoke_locks[ticket_id]
    if not _ticket_lock.acquire(blocking=False):
        print(f"[{stage.upper()}-INVOKE] {ticket_id}: threading.Lock ya tomado por otro thread — abortando",
              file=sys.stderr, flush=True)
        return
    try:
        # ── EN_CURSO flag: evita invocaciones duplicadas del mismo agente ──────────
        # Chequear ANTES de reclamar el gate global. Si el flag existe y es fresco,
        # otro thread ya está corriendo y no debemos tocar el gate (si lo tomáramos
        # y retornáramos, dejaríamos el gate sujeto sin agente ejecutando — gate leak).
        # Si el flag es muy viejo (> stale_after_min), lo tratamos como huérfano:
        # limpiamos el flag y seguimos con la invocación normal.
        # Se elimina cuando:
        #   - invoke_agent falla (retorno False)
        #   - El watcher detecta el flag de COMPLETADO o ERROR
        en_curso_flag = os.path.join(folder, f"{stage.upper()}_AGENTE_EN_CURSO.flag")
        from pipeline_invoker import InvokeLogger as _InvokeLogger
        _ilog = _InvokeLogger(ticket_id, stage)
        _ilog.start()
        if os.path.exists(en_curso_flag):
            try:
                _flag_age_min = (_time.time() - os.path.getmtime(en_curso_flag)) / 60.0
            except Exception:
                _flag_age_min = 0.0
            _STALE_FLAG_MIN = 30.0  # igual criterio que stale_after_min del reconciliador
            if _flag_age_min < _STALE_FLAG_MIN:
                print(f"[{stage.upper()}-INVOKE] {ticket_id}: AGENTE_EN_CURSO.flag activo"
                      f" (hace {_flag_age_min:.1f} min) — invocación duplicada ignorada",
                      file=sys.stderr, flush=True)
                _ilog.en_curso_exists(en_curso_flag)
                return
            # Flag huérfano → limpiar y seguir
            print(f"[{stage.upper()}-INVOKE] {ticket_id}: AGENTE_EN_CURSO.flag huérfano "
                  f"(hace {_flag_age_min:.1f} min) — limpiando y reintentando",
                  file=sys.stderr, flush=True)
            try:
                os.remove(en_curso_flag)
            except Exception:
                pass

        # ── Gate global: pipeline serial ──────────────────────────────────────────
        # Rechaza la invocación si hay otro ticket activo. El reconciliador lo
        # reintentará en su próximo tick cuando el gate quede libre.
        if not _try_claim_active_ticket(ticket_id):
            _other = _get_active_ticket()
            print(f"[{stage.upper()}-INVOKE] {ticket_id}: gate global ocupado por "
                  f"#{_other} — rechazando (reintentará el reconciliador)",
                  file=sys.stderr, flush=True)
            return

        try:
            with open(en_curso_flag, "x") as _ecf:
                _ecf.write(datetime.now().isoformat())
        except FileExistsError:
            # Otro thread creó el flag entre nuestro check y aquí.
            print(f"[{stage.upper()}-INVOKE] {ticket_id}: AGENTE_EN_CURSO.flag (race condition)"
                  f" — liberando gate e ignorando", file=sys.stderr, flush=True)
            _release_active_ticket(ticket_id, "race EN_CURSO")
            return
        _ilog.en_curso_created(en_curso_flag)

        if stage == "pm":
            from prompt_builder import build_pm_prompt as _build
            agent  = agents.get("pm", "PM-TL STack 3")

            # ── FIX RACE: PM_COMPLETADO.flag puede existir si RECOVERY ya lo detectó
            # mientras la lock anterior estaba tomada.  En ese caso NO re-invocar PM —
            # limpiar el en_curso_flag, set pm_completado y Schedule DEV en nuevo thread
            # (el scheduling es post-return para garantizar que la lock ya fue liberada).
            _pm_done_flag = os.path.join(folder, "PM_COMPLETADO.flag")
            if os.path.exists(_pm_done_flag):
                print(f"[PM] {ticket_id}: PM_COMPLETADO.flag ya existe — "
                      f"saltando re-invocación, avanzando a DEV directamente",
                      file=sys.stderr, flush=True)
                try:
                    os.remove(en_curso_flag)
                except Exception:
                    pass
                _s2 = load_state(rt["state_path"])
                set_ticket_state(_s2, ticket_id, "pm_completado", folder=folder)
                _s2.setdefault("tickets", {}).setdefault(ticket_id, {})["auto_advance"] = True
                save_state(rt["state_path"], _s2)
                # Lanzar DEV después de liberar la lock (0.3s de margen)
                def _schedule_dev(_tid=ticket_id):
                    import time as _t; _t.sleep(0.3)
                    _invoke_stage(_tid, "dev")
                threading.Thread(target=_schedule_dev, daemon=True).start()
                return
            # ── Fin FIX RACE ─────────────────────────────────────────────────

            # Actualizar estado ANTES de construir el prompt para que el UI refleje el avance inmediatamente
            set_ticket_state(state, ticket_id, "pm_en_proceso", folder=folder)
            state.setdefault("tickets", {}).setdefault(ticket_id, {})["pm_inicio_at"] = datetime.now().isoformat()
            # Garantizar auto_advance independientemente del caller (api_run_pipeline, api_reinvoke, etc.)
            state["tickets"][ticket_id]["auto_advance"] = True
            save_state(rt["state_path"], state)
            print(f"[PM] Construyendo prompt para {ticket_id}...", file=sys.stderr, flush=True)
            prompt = _build(folder, ticket_id, rt["workspace_root"])
            prompt = _with_heartbeat(prompt, stage)
            print(f"[PM] Prompt listo ({len(prompt)} chars) — invocando agente '{agent}'...", file=sys.stderr, flush=True)
            _ilog.bridge_call(agent, len(prompt))
            ok = invoke_agent(prompt, agent_name=agent, project_name=rt["name"],
                      workspace_root=rt["workspace_root"],
                      new_conversation=True)
            _ilog.bridge_result(ok)
            _record_invoke(ok, f"Agente: {agent}")
            if not ok:
                print(f"[PM] FALLÓ invocar agente '{agent}' para {ticket_id}", file=sys.stderr, flush=True)
                try:
                    os.remove(en_curso_flag)
                except Exception:
                    pass
                mark_error(state, ticket_id, "pm", "No se pudo invocar al agente vía Bridge")
                save_state(rt["state_path"], state)
                return
            print(f"[PM] Agente invocado para {ticket_id} — watcher esperando PM_COMPLETADO.flag")

        elif stage == "dev":
            from prompt_builder import build_dev_prompt as _build
            agent  = agents.get("dev", "DevStack3")
            # Actualizar estado ANTES de construir el prompt para que el UI refleje el avance inmediatamente
            set_ticket_state(state, ticket_id, "dev_en_proceso")
            state.setdefault("tickets", {}).setdefault(ticket_id, {})["dev_inicio_at"] = datetime.now().isoformat()
            # Garantizar auto_advance independientemente del caller
            state["tickets"][ticket_id]["auto_advance"] = True
            save_state(rt["state_path"], state)
            print(f"[DEV] Construyendo prompt para {ticket_id}...", file=sys.stderr, flush=True)
            prompt = _build(folder, ticket_id, rt["workspace_root"])
            prompt = _with_heartbeat(prompt, stage)
            print(f"[DEV] Prompt listo ({len(prompt)} chars) — invocando agente '{agent}'...", file=sys.stderr, flush=True)
            _ilog.bridge_call(agent, len(prompt))
            ok = invoke_agent(prompt, agent_name=agent, project_name=rt["name"],
                              workspace_root=rt["workspace_root"])
            _ilog.bridge_result(ok)
            _record_invoke(ok, f"Agente: {agent}")
            if not ok:
                try:
                    os.remove(en_curso_flag)
                except Exception:
                    pass
                mark_error(state, ticket_id, "dev", "No se pudo invocar al agente vía Bridge")
                save_state(rt["state_path"], state)
                return
            print(f"[DEV] Agente invocado para {ticket_id} — watcher esperando DEV_COMPLETADO.md")

        elif stage == "tester":
            from prompt_builder import build_tester_prompt as _build
            agent  = agents.get("tester", "QA")
            # Actualizar estado ANTES de construir el prompt para que el UI refleje el avance inmediatamente
            set_ticket_state(state, ticket_id, "tester_en_proceso")
            state.setdefault("tickets", {}).setdefault(ticket_id, {})["tester_inicio_at"] = datetime.now().isoformat()
            save_state(rt["state_path"], state)
            print(f"[TESTER] Construyendo prompt para {ticket_id}...", file=sys.stderr, flush=True)
            prompt = _build(folder, ticket_id, rt["workspace_root"])
            prompt = _with_heartbeat(prompt, stage)
            print(f"[TESTER] Prompt listo ({len(prompt)} chars) — invocando agente '{agent}'...", file=sys.stderr, flush=True)
            _ilog.bridge_call(agent, len(prompt))
            ok = invoke_agent(prompt, agent_name=agent, project_name=rt["name"],
                              workspace_root=rt["workspace_root"])
            _ilog.bridge_result(ok)
            _record_invoke(ok, f"Agente: {agent}")
            if not ok:
                try:
                    os.remove(en_curso_flag)
                except Exception:
                    pass
                mark_error(state, ticket_id, "tester", "No se pudo invocar al agente vía Bridge")
                save_state(rt["state_path"], state)
                return
            print(f"[TESTER] Agente invocado para {ticket_id} — watcher esperando TESTER_COMPLETADO.md")

        elif stage == "pm_inv":
            from prompt_builder import build_pm_inv_prompt as _build
            agent = agents.get("pm", "PM-TL STack 3")
            set_ticket_state(state, ticket_id, "pm_inv_en_proceso", folder=folder)
            state.setdefault("tickets", {}).setdefault(ticket_id, {})["pm_inv_inicio_at"] = datetime.now().isoformat()
            state["tickets"][ticket_id]["auto_advance"] = True
            save_state(rt["state_path"], state)
            print(f"[PM-INV] Construyendo prompt para {ticket_id}...", file=sys.stderr, flush=True)
            prompt = _build(folder, ticket_id, rt["workspace_root"])
            prompt = _with_heartbeat(prompt, stage)
            print(f"[PM-INV] Prompt listo ({len(prompt)} chars) — invocando '{agent}'...", file=sys.stderr, flush=True)
            _ilog.bridge_call(agent, len(prompt))
            ok = invoke_agent(prompt, agent_name=agent, project_name=rt["name"],
                              workspace_root=rt["workspace_root"], new_conversation=True)
            _ilog.bridge_result(ok)
            _record_invoke(ok, f"Agente: {agent}")
            if not ok:
                try: os.remove(en_curso_flag)
                except Exception: pass
                mark_error(state, ticket_id, "pm", "No se pudo invocar PM-Investigador vía Bridge")
                save_state(rt["state_path"], state)
                return
            print(f"[PM-INV] Agente invocado para {ticket_id} — esperando INV_COMPLETADO.flag")

        elif stage == "pm_arq":
            from prompt_builder import build_pm_arq_prompt as _build
            agent = agents.get("pm", "PM-TL STack 3")
            set_ticket_state(state, ticket_id, "pm_arq_en_proceso", folder=folder)
            state.setdefault("tickets", {}).setdefault(ticket_id, {})["pm_arq_inicio_at"] = datetime.now().isoformat()
            state["tickets"][ticket_id]["auto_advance"] = True
            save_state(rt["state_path"], state)
            print(f"[PM-ARQ] Construyendo prompt para {ticket_id}...", file=sys.stderr, flush=True)
            prompt = _build(folder, ticket_id, rt["workspace_root"])
            prompt = _with_heartbeat(prompt, stage)
            print(f"[PM-ARQ] Prompt listo ({len(prompt)} chars) — invocando '{agent}'...", file=sys.stderr, flush=True)
            _ilog.bridge_call(agent, len(prompt))
            ok = invoke_agent(prompt, agent_name=agent, project_name=rt["name"],
                              workspace_root=rt["workspace_root"], new_conversation=False)
            _ilog.bridge_result(ok)
            _record_invoke(ok, f"Agente: {agent}")
            if not ok:
                try: os.remove(en_curso_flag)
                except Exception: pass
                mark_error(state, ticket_id, "pm", "No se pudo invocar PM-Arquitecto vía Bridge")
                save_state(rt["state_path"], state)
                return
            print(f"[PM-ARQ] Agente invocado para {ticket_id} — esperando ARQ_COMPLETADO.flag")

        elif stage == "pm_plan":
            from prompt_builder import build_pm_plan_prompt as _build
            agent = agents.get("pm", "PM-TL STack 3")
            set_ticket_state(state, ticket_id, "pm_plan_en_proceso", folder=folder)
            state.setdefault("tickets", {}).setdefault(ticket_id, {})["pm_plan_inicio_at"] = datetime.now().isoformat()
            state["tickets"][ticket_id]["auto_advance"] = True
            save_state(rt["state_path"], state)
            print(f"[PM-PLAN] Construyendo prompt para {ticket_id}...", file=sys.stderr, flush=True)
            prompt = _build(folder, ticket_id, rt["workspace_root"])
            prompt = _with_heartbeat(prompt, stage)
            print(f"[PM-PLAN] Prompt listo ({len(prompt)} chars) — invocando '{agent}'...", file=sys.stderr, flush=True)
            _ilog.bridge_call(agent, len(prompt))
            ok = invoke_agent(prompt, agent_name=agent, project_name=rt["name"],
                              workspace_root=rt["workspace_root"], new_conversation=False)
            _ilog.bridge_result(ok)
            _record_invoke(ok, f"Agente: {agent}")
            if not ok:
                try: os.remove(en_curso_flag)
                except Exception: pass
                mark_error(state, ticket_id, "pm", "No se pudo invocar PM-Planificador vía Bridge")
                save_state(rt["state_path"], state)
                return
            print(f"[PM-PLAN] Agente invocado para {ticket_id} — esperando PM_COMPLETADO.flag")

        elif stage == "dev_loc":
            from prompt_builder import build_dev_loc_prompt as _build
            agent = agents.get("dev", "DevStack3")
            set_ticket_state(state, ticket_id, "dev_loc_en_proceso", folder=folder)
            state.setdefault("tickets", {}).setdefault(ticket_id, {})["dev_loc_inicio_at"] = datetime.now().isoformat()
            state["tickets"][ticket_id]["auto_advance"] = True
            save_state(rt["state_path"], state)
            print(f"[DEV-LOC] Construyendo prompt para {ticket_id}...", file=sys.stderr, flush=True)
            prompt = _build(folder, ticket_id, rt["workspace_root"])
            prompt = _with_heartbeat(prompt, stage)
            print(f"[DEV-LOC] Prompt listo ({len(prompt)} chars) — invocando '{agent}'...", file=sys.stderr, flush=True)
            _ilog.bridge_call(agent, len(prompt))
            ok = invoke_agent(prompt, agent_name=agent, project_name=rt["name"],
                              workspace_root=rt["workspace_root"], new_conversation=True)
            _ilog.bridge_result(ok)
            _record_invoke(ok, f"Agente: {agent}")
            if not ok:
                try: os.remove(en_curso_flag)
                except Exception: pass
                mark_error(state, ticket_id, "dev", "No se pudo invocar DEV-Localizador vía Bridge")
                save_state(rt["state_path"], state)
                return
            print(f"[DEV-LOC] Agente invocado para {ticket_id} — esperando LOC_COMPLETADO.flag")

        elif stage == "dev_impl":
            from prompt_builder import build_dev_impl_prompt as _build
            agent = agents.get("dev", "DevStack3")
            set_ticket_state(state, ticket_id, "dev_impl_en_proceso", folder=folder)
            state.setdefault("tickets", {}).setdefault(ticket_id, {})["dev_impl_inicio_at"] = datetime.now().isoformat()
            state["tickets"][ticket_id]["auto_advance"] = True
            save_state(rt["state_path"], state)
            print(f"[DEV-IMPL] Construyendo prompt para {ticket_id}...", file=sys.stderr, flush=True)
            prompt = _build(folder, ticket_id, rt["workspace_root"])
            prompt = _with_heartbeat(prompt, stage)
            print(f"[DEV-IMPL] Prompt listo ({len(prompt)} chars) — invocando '{agent}'...", file=sys.stderr, flush=True)
            _ilog.bridge_call(agent, len(prompt))
            ok = invoke_agent(prompt, agent_name=agent, project_name=rt["name"],
                              workspace_root=rt["workspace_root"], new_conversation=False)
            _ilog.bridge_result(ok)
            _record_invoke(ok, f"Agente: {agent}")
            if not ok:
                try: os.remove(en_curso_flag)
                except Exception: pass
                mark_error(state, ticket_id, "dev", "No se pudo invocar DEV-Implementador vía Bridge")
                save_state(rt["state_path"], state)
                return
            print(f"[DEV-IMPL] Agente invocado para {ticket_id} — esperando IMPL_COMPLETADO.flag")

        elif stage == "dev_doc":
            from prompt_builder import build_dev_doc_prompt as _build
            agent = agents.get("dev", "DevStack3")
            set_ticket_state(state, ticket_id, "dev_doc_en_proceso", folder=folder)
            state.setdefault("tickets", {}).setdefault(ticket_id, {})["dev_doc_inicio_at"] = datetime.now().isoformat()
            state["tickets"][ticket_id]["auto_advance"] = True
            save_state(rt["state_path"], state)
            print(f"[DEV-DOC] Construyendo prompt para {ticket_id}...", file=sys.stderr, flush=True)
            prompt = _build(folder, ticket_id, rt["workspace_root"])
            prompt = _with_heartbeat(prompt, stage)
            print(f"[DEV-DOC] Prompt listo ({len(prompt)} chars) — invocando '{agent}'...", file=sys.stderr, flush=True)
            _ilog.bridge_call(agent, len(prompt))
            ok = invoke_agent(prompt, agent_name=agent, project_name=rt["name"],
                              workspace_root=rt["workspace_root"], new_conversation=False)
            _ilog.bridge_result(ok)
            _record_invoke(ok, f"Agente: {agent}")
            if not ok:
                try: os.remove(en_curso_flag)
                except Exception: pass
                mark_error(state, ticket_id, "dev", "No se pudo invocar DEV-Documentador vía Bridge")
                save_state(rt["state_path"], state)
                return
            print(f"[DEV-DOC] Agente invocado para {ticket_id} — esperando DEV_COMPLETADO.md")

        elif stage == "qa_rev":
            from prompt_builder import build_qa_rev_prompt as _build
            agent = agents.get("tester", "QA")
            set_ticket_state(state, ticket_id, "qa_rev_en_proceso", folder=folder)
            state.setdefault("tickets", {}).setdefault(ticket_id, {})["qa_rev_inicio_at"] = datetime.now().isoformat()
            state["tickets"][ticket_id]["auto_advance"] = True
            save_state(rt["state_path"], state)
            print(f"[QA-REV] Construyendo prompt para {ticket_id}...", file=sys.stderr, flush=True)
            prompt = _build(folder, ticket_id, rt["workspace_root"])
            prompt = _with_heartbeat(prompt, stage)
            print(f"[QA-REV] Prompt listo ({len(prompt)} chars) — invocando '{agent}'...", file=sys.stderr, flush=True)
            _ilog.bridge_call(agent, len(prompt))
            ok = invoke_agent(prompt, agent_name=agent, project_name=rt["name"],
                              workspace_root=rt["workspace_root"], new_conversation=True)
            _ilog.bridge_result(ok)
            _record_invoke(ok, f"Agente: {agent}")
            if not ok:
                try: os.remove(en_curso_flag)
                except Exception: pass
                mark_error(state, ticket_id, "tester", "No se pudo invocar QA-Revisor vía Bridge")
                save_state(rt["state_path"], state)
                return
            print(f"[QA-REV] Agente invocado para {ticket_id} — esperando REVIEW_COMPLETADO.flag")

        elif stage == "qa_exec":
            from prompt_builder import build_qa_exec_prompt as _build
            agent = agents.get("tester", "QA")
            set_ticket_state(state, ticket_id, "qa_exec_en_proceso", folder=folder)
            state.setdefault("tickets", {}).setdefault(ticket_id, {})["qa_exec_inicio_at"] = datetime.now().isoformat()
            state["tickets"][ticket_id]["auto_advance"] = True
            save_state(rt["state_path"], state)
            print(f"[QA-EXEC] Construyendo prompt para {ticket_id}...", file=sys.stderr, flush=True)
            prompt = _build(folder, ticket_id, rt["workspace_root"])
            prompt = _with_heartbeat(prompt, stage)
            print(f"[QA-EXEC] Prompt listo ({len(prompt)} chars) — invocando '{agent}'...", file=sys.stderr, flush=True)
            _ilog.bridge_call(agent, len(prompt))
            ok = invoke_agent(prompt, agent_name=agent, project_name=rt["name"],
                              workspace_root=rt["workspace_root"], new_conversation=False)
            _ilog.bridge_result(ok)
            _record_invoke(ok, f"Agente: {agent}")
            if not ok:
                try: os.remove(en_curso_flag)
                except Exception: pass
                mark_error(state, ticket_id, "tester", "No se pudo invocar QA-Ejecutor vía Bridge")
                save_state(rt["state_path"], state)
                return
            print(f"[QA-EXEC] Agente invocado para {ticket_id} — esperando TEST_COMPLETADO.flag")

        elif stage == "qa_arb":
            from prompt_builder import build_qa_arb_prompt as _build
            agent = agents.get("tester", "QA")
            set_ticket_state(state, ticket_id, "qa_arb_en_proceso", folder=folder)
            state.setdefault("tickets", {}).setdefault(ticket_id, {})["qa_arb_inicio_at"] = datetime.now().isoformat()
            state["tickets"][ticket_id]["auto_advance"] = True
            save_state(rt["state_path"], state)
            print(f"[QA-ARB] Construyendo prompt para {ticket_id}...", file=sys.stderr, flush=True)
            prompt = _build(folder, ticket_id, rt["workspace_root"])
            prompt = _with_heartbeat(prompt, stage)
            print(f"[QA-ARB] Prompt listo ({len(prompt)} chars) — invocando '{agent}'...", file=sys.stderr, flush=True)
            _ilog.bridge_call(agent, len(prompt))
            ok = invoke_agent(prompt, agent_name=agent, project_name=rt["name"],
                              workspace_root=rt["workspace_root"], new_conversation=False)
            _ilog.bridge_result(ok)
            _record_invoke(ok, f"Agente: {agent}")
            if not ok:
                try: os.remove(en_curso_flag)
                except Exception: pass
                mark_error(state, ticket_id, "tester", "No se pudo invocar QA-Árbitro vía Bridge")
                save_state(rt["state_path"], state)
                return
            print(f"[QA-ARB] Agente invocado para {ticket_id} — esperando TESTER_COMPLETADO.md")

        else:
            try:
                os.remove(en_curso_flag)
            except Exception:
                pass
            return  # etapa desconocida
    finally:
        _ticket_lock.release()


def _run_pm_only(ticket_id: str):
    _invoke_stage(ticket_id, "pm")


def _run_dev_only(ticket_id: str):
    _invoke_stage(ticket_id, "dev")


def _run_tester_only(ticket_id: str):
    _invoke_stage(ticket_id, "tester")


# ── RESET COMPLETO (B1) ───────────────────────────────────────────────────────
# Listas centralizadas de artefactos a limpiar — declaradas a nivel de módulo
# para que otros componentes (tests, daemon) puedan reusarlas sin duplicar.

RESET_FLAGS_TO_DELETE = [
    # Flags de completado / sentinelas
    "PM_COMPLETADO.flag", "DEV_COMPLETADO.md", "TESTER_COMPLETADO.md", "DOC_COMPLETADO.flag",
    # Flags de error
    "PM_ERROR.flag", "DEV_ERROR.flag", "TESTER_ERROR.flag", "DOC_ERROR.flag",
    # Flags de agente en curso
    "PM_AGENTE_EN_CURSO.flag", "DEV_AGENTE_EN_CURSO.flag",
    "TESTER_AGENTE_EN_CURSO.flag", "DOC_AGENTE_EN_CURSO.flag",
    # Heartbeats (A4)
    "PM_HEARTBEAT.txt", "DEV_HEARTBEAT.txt", "TESTER_HEARTBEAT.txt", "DOC_HEARTBEAT.txt",
]

RESET_ANALYSIS_FILES = [
    # PM
    "INCIDENTE.md", "ANALISIS_TECNICO.md", "ARQUITECTURA_SOLUCION.md",
    "TAREAS_DESARROLLO.md", "NOTAS_IMPLEMENTACION.md", "QUERIES_ANALISIS.sql",
    # DEV
    "BUG_LOCALIZATION.md", "DB_SOLUTION.sql", "GIT_CHANGES.md", "SVN_CHANGES.md",
    "COMMIT_MESSAGE.txt", "DEV_SHADOW_PLAN.md",
    # QA
    "CODE_REVIEW.md", "TEST_RESULTS.md", "MANTIS_UPDATE.json",
    "TESTER_COMPLETADO.md.prev",
]


def _parse_files_txt(files_txt_path: str) -> list[str]:
    """Parsea snapshots/{stage}_files.txt → lista de paths relativos al workspace.
    Cada línea de datos tiene formato `<status>  <path>` (estilo git status -s)."""
    paths = []
    try:
        with open(files_txt_path, encoding="utf-8") as f:
            for line in f:
                line = line.rstrip("\n")
                if not line or line.startswith("#") or line.strip() == "(sin cambios)":
                    continue
                parts = line.split(None, 1)
                paths.append(parts[1].strip() if len(parts) == 2 else parts[0].strip())
    except Exception:
        pass
    return paths


def _reset_ticket(ticket_id: str, mode: str = "soft", force: bool = False) -> dict:
    """Reset comprehensivo de un ticket.

    Modos:
      - "soft" (default): limpia todos los artefactos generados por Stacky
        (state.json, seen_tickets, flags, análisis, snapshots, locks, ZIPs,
        caches en memoria). NO toca el workspace.
      - "hard": además ejecuta `git checkout -- <archivo>` sobre cada archivo
        listado en snapshots/{stage}_files.txt para revertir los cambios del
        workspace. Destructivo: si dos tickets tocaron los mismos archivos
        se pierden todos los cambios.

    Devuelve dict con detalle exacto de lo limpiado/fallado (best-effort:
    cada paso en su propio try/except para no abortar los siguientes).
    """
    import glob as _glob
    import shutil as _shutil

    rt     = _get_runtime()
    folder = _find_ticket_folder(ticket_id, rt["tickets_base"])

    result: dict = {
        "ok":                  True,
        "ticket_id":           ticket_id,
        "mode":                mode,
        "force":               bool(force),
        "removed_pipeline":    False,
        "removed_seen":        False,
        "files_removed":       [],
        "snapshots_removed":   False,
        "locks_released":      [],
        "deploy_zips_removed": [],
        "files_reverted":      [],
        "revert_failed":       [],
        "caches_cleared":      [],
        "errors":              [],
    }

    # 1) Entry de pipeline/state.json
    try:
        from pipeline_state import load_state, save_state
        state = load_state(rt["state_path"])
        if ticket_id in state.get("tickets", {}):
            del state["tickets"][ticket_id]
            result["removed_pipeline"] = True
        save_state(rt["state_path"], state)
    except Exception as e:
        result["errors"].append(f"state.json: {e}")

    # 2) Entry de seen_tickets.json (para que el scraper lo re-importe)
    seen_path = os.path.join(BASE_DIR, "state", "seen_tickets.json")
    try:
        if os.path.exists(seen_path):
            with open(seen_path, encoding="utf-8") as f:
                seen = json.load(f)
            if ticket_id in seen.get("tickets", {}):
                del seen["tickets"][ticket_id]
                result["removed_seen"] = True
                with open(seen_path, "w", encoding="utf-8") as f:
                    json.dump(seen, f, indent=2, ensure_ascii=False)
    except Exception as e:
        result["errors"].append(f"seen_tickets.json: {e}")

    # 3) Hard mode: revertir workspace ANTES de borrar la carpeta del ticket.
    # Estrategia "Opción A": por cada archivo listado en snapshots/*_files.txt:
    #   a. Borrar el archivo local (si existe).
    #   b. `git checkout HEAD -- <relpath>` para traer la versión commiteada.
    # Esto recupera cambios aunque el git checkout simple falle por staging, CRLF
    # o locks de otras herramientas. Si el archivo no existe en HEAD, el paso (b)
    # falla y queda borrado — que es el comportamiento correcto para archivos que
    # el ticket creó nuevos.
    if mode == "hard" and folder:
        snap_dir = os.path.join(folder, "snapshots")
        files_to_revert: set = set()
        if os.path.isdir(snap_dir):
            for files_txt in _glob.glob(os.path.join(snap_dir, "*_files.txt")):
                files_to_revert.update(_parse_files_txt(files_txt))
        workspace_root = rt["workspace_root"]
        for relpath in sorted(files_to_revert):
            abs_path = os.path.join(workspace_root, relpath)
            # (a) borrar local
            try:
                if os.path.exists(abs_path):
                    os.remove(abs_path)
            except Exception as e:
                result["revert_failed"].append({"file": relpath, "error": f"rm: {e}"})
                continue
            # (b) restaurar desde HEAD
            try:
                r = subprocess.run(
                    ["git", "checkout", "HEAD", "--", relpath],
                    cwd=workspace_root,
                    capture_output=True, text=True, timeout=30,
                )
                if r.returncode == 0:
                    result["files_reverted"].append(relpath)
                else:
                    # Archivo probablemente nuevo en el ticket (no existe en HEAD).
                    # Queda borrado — comportamiento esperado.
                    stderr = (r.stderr or "").strip()
                    if "did not match any file" in stderr or "pathspec" in stderr:
                        result["files_reverted"].append(f"{relpath} (new → deleted)")
                    else:
                        result["revert_failed"].append({"file": relpath, "stderr": stderr})
            except Exception as e:
                result["revert_failed"].append({"file": relpath, "error": f"git: {e}"})

    # 4) Filesystem del ticket
    # - Soft: limpia flags, análisis, backups, ZIPs, snapshots/ (conserva INCIDENTE.md)
    # - Hard: wipe completo de la carpeta del ticket (se re-importará desde ADO)
    if folder and os.path.isdir(folder):
        if mode == "hard":
            try:
                _shutil.rmtree(folder)
                result["files_removed"].append(f"<folder>/{os.path.basename(folder)}")
                result["snapshots_removed"] = True
                result["folder_wiped"] = True
            except Exception as e:
                result["errors"].append(f"rmtree folder: {e}")
        else:
            for fname in RESET_FLAGS_TO_DELETE + RESET_ANALYSIS_FILES:
                fpath = os.path.join(folder, fname)
                if os.path.exists(fpath):
                    try:
                        os.remove(fpath)
                        result["files_removed"].append(fname)
                    except Exception as e:
                        result["errors"].append(f"{fname}: {e}")
            for pattern in ("*.bak", "*.flag*.bak", "*.md*.bak", "*.prev", "*.tmp"):
                for bak in _glob.glob(os.path.join(folder, pattern)):
                    try:
                        os.remove(bak)
                        result["files_removed"].append(os.path.basename(bak))
                    except Exception:
                        pass
            for zip_path in (_glob.glob(os.path.join(folder, "*_deploy.zip")) +
                             _glob.glob(os.path.join(folder, "deploy_*.zip"))):
                try:
                    os.remove(zip_path)
                    result["deploy_zips_removed"].append(os.path.basename(zip_path))
                except Exception as e:
                    result["errors"].append(f"zip {os.path.basename(zip_path)}: {e}")
            snap_dir = os.path.join(folder, "snapshots")
            if os.path.isdir(snap_dir):
                try:
                    _shutil.rmtree(snap_dir)
                    result["snapshots_removed"] = True
                except Exception as e:
                    result["errors"].append(f"snapshots/: {e}")

    # 5) Lock files file-based en Tools/Stacky/locks/
    try:
        from pipeline_lock import release_lock
        locks_dir = os.path.join(BASE_DIR, "locks")
        if os.path.isdir(locks_dir):
            prefix = f"{ticket_id}_"
            for lock_file in _glob.glob(os.path.join(locks_dir, f"{prefix}*.lock")):
                stage_name = os.path.basename(lock_file)[len(prefix):-len(".lock")]
                try:
                    release_lock(ticket_id, stage_name)
                except Exception:
                    pass
                if os.path.exists(lock_file):
                    try:
                        os.remove(lock_file)
                    except Exception as e:
                        result["errors"].append(f"lock {os.path.basename(lock_file)}: {e}")
                        continue
                result["locks_released"].append(os.path.basename(lock_file))
    except Exception as e:
        result["errors"].append(f"locks: {e}")

    # 5b) INVOKE_LOCK.pid (pipeline_invoker inter-process lockfile) — clear_all_locks
    # también re-limpia los lock files por si el paso 5 dejó alguno (best-effort).
    try:
        from pipeline_lock import clear_all_locks as _clear_all_locks
        clr = _clear_all_locks(ticket_id, folder)
        if clr.get("invoke_lock_pid"):
            result["locks_released"].append("INVOKE_LOCK.pid")
    except Exception as e:
        result["errors"].append(f"clear_all_locks: {e}")

    # 5c) Gate global de pipeline serial: si este ticket lo tenía tomado, liberarlo.
    try:
        if _release_active_ticket(ticket_id, f"reset {mode}"):
            result["caches_cleared"].append("active_ticket_gate")
    except Exception as e:
        result["errors"].append(f"gate_global: {e}")

    # 6) Caches en memoria del proceso dashboard
    try:
        with _ticket_locks_rlock:
            _ticket_invoke_locks.pop(ticket_id, None)
        result["caches_cleared"].append("_ticket_invoke_locks")
    except Exception as e:
        result["errors"].append(f"_ticket_invoke_locks: {e}")
    try:
        _invalidate_runtime_cache()
        _scan_cache["data"]  = None
        _scan_cache["ts"]    = 0.0
        _state_cache["mtime"] = 0.0
        _title_cache.pop(ticket_id, None)
        result["caches_cleared"].append("dashboard_caches")
    except Exception as e:
        result["errors"].append(f"dashboard_caches: {e}")

    # Queue en memoria de agent_queue (slots activos + cola pendiente)
    try:
        from agent_queue import get_agent_queue
        q = get_agent_queue()
        for stage_key in ("pm", "dev", "tester"):
            if ticket_id in q._active.get(stage_key, []):
                q._active[stage_key].remove(ticket_id)
            q._queue[stage_key] = [it for it in q._queue.get(stage_key, [])
                                   if getattr(it, "ticket_id", None) != ticket_id]
        result["caches_cleared"].append("agent_queue")
    except Exception as e:
        result["errors"].append(f"agent_queue: {e}")

    # 7b) Hard mode: disparar re-sync desde Azure para re-importar el ticket.
    # Corre en background — el usuario ya tiene la respuesta HTTP y el sync puede
    # tardar varios segundos.
    if mode == "hard":
        def _resync_after_hard(_proj=rt.get("name"), _tid=ticket_id):
            try:
                from issue_provider.sync import sync_tickets
                sync_tickets(_proj)
                print(f"[RESET-HARD] {_tid}: re-sync Azure finalizado",
                      file=sys.stderr, flush=True)
            except Exception as _e:
                print(f"[RESET-HARD] {_tid}: re-sync Azure falló: {_e}",
                      file=sys.stderr, flush=True)
        threading.Thread(target=_resync_after_hard, daemon=True,
                         name=f"reset-resync-{ticket_id}").start()
        result["resync_triggered"] = True

    # 7) Auditoría append-only
    try:
        audit_path = os.path.join(BASE_DIR, "state", "reset_audit.log")
        os.makedirs(os.path.dirname(audit_path), exist_ok=True)
        with open(audit_path, "a", encoding="utf-8") as f:
            entry = {
                "ts":                   datetime.now().isoformat(),
                "ticket_id":            ticket_id,
                "mode":                 mode,
                "force":                bool(force),
                "removed_pipeline":     result["removed_pipeline"],
                "removed_seen":         result["removed_seen"],
                "files_removed_count":  len(result["files_removed"]),
                "snapshots_removed":    result["snapshots_removed"],
                "locks_released_count": len(result["locks_released"]),
                "deploy_zips_count":    len(result["deploy_zips_removed"]),
                "files_reverted_count": len(result["files_reverted"]),
                "revert_failed_count":  len(result["revert_failed"]),
                "errors_count":         len(result["errors"]),
            }
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        result["errors"].append(f"audit: {e}")

    if result["errors"] or result["revert_failed"]:
        result["partial_success"] = True

    summary = (f"reset {mode}: {len(result['files_removed'])} archivos, "
               f"{len(result['locks_released'])} locks, "
               f"{len(result['files_reverted'])} reverts, "
               f"{len(result['errors'])} errores")
    result["msg"] = summary
    return result


@app.route("/api/reset/<ticket_id>", methods=["POST"])
def api_reset(ticket_id: str):
    """Endpoint canónico de reset. Acepta ?mode=soft|hard (default soft).

    Query params:
      - force=1: marca el reset como forzado en el audit log. El reset en sí
        ya libera el gate global y limpia locks aunque el ticket esté en
        *_en_proceso, pero con force=1 queda trazado como "reset durante
        ejecución" para diagnóstico.
    """
    mode  = request.args.get("mode", "soft").lower()
    force = request.args.get("force", "").lower() in ("1", "true", "yes")
    if mode not in ("soft", "hard"):
        return jsonify({"ok": False, "error": f"mode inválido: {mode} (usar soft|hard)"}), 400
    return jsonify(_reset_ticket(ticket_id, mode, force=force))


@app.route("/api/reimport/<ticket_id>", methods=["POST"])
def api_reimport(ticket_id: str):
    """Alias retrocompat de /api/reset/<id>?mode=soft.
    El botón "Reimportar" del dashboard sigue funcionando sin cambios."""
    return jsonify(_reset_ticket(ticket_id, "soft"))


@app.route("/api/reset_preview/<ticket_id>", methods=["GET"])
def api_reset_preview(ticket_id: str):
    """Preview de archivos que Reset Hard revertiría (unión de snapshots/*_files.txt).
    Permite mostrar al usuario qué se va a tocar antes de confirmar."""
    import glob as _glob
    folder = _find_ticket_folder(ticket_id)
    if not folder:
        return jsonify({"ok": False, "error": "ticket folder no encontrado", "files": []}), 404
    snap_dir = os.path.join(folder, "snapshots")
    files: set = set()
    stages_found: list = []
    if os.path.isdir(snap_dir):
        for files_txt in _glob.glob(os.path.join(snap_dir, "*_files.txt")):
            stages_found.append(os.path.basename(files_txt))
            try:
                files.update(_parse_files_txt(files_txt))
            except Exception:
                pass
    return jsonify({
        "ok": True,
        "ticket_id": ticket_id,
        "files": sorted(files),
        "snapshots": sorted(stages_found),
    })


@app.route("/api/gen_deploy/<ticket_id>", methods=["POST"])
def api_gen_deploy(ticket_id: str):
    """
    Genera un paquete ZIP de despliegue para el ticket:
      - Solo las DLLs modificadas (inferidas desde los .cs/.vb cambiados)
      - Archivos web modificados (.aspx, .ascx, .js, .css, etc.)
      - Scripts SQL encontrados en QUERIES_ANALISIS.sql
      - README_DEPLOY.md con instrucciones

    Retorna: { ok, zip_name, zip_path, files, sql_scripts, warnings }
    El ZIP queda en la carpeta del ticket; el cliente puede descargarlo vía
    GET /api/download_deploy/<ticket_id>/<zip_name>
    """
    rt     = _get_runtime()
    folder = _find_ticket_folder(ticket_id, rt["tickets_base"])
    if not folder:
        return jsonify({"ok": False, "error": f"Ticket {ticket_id} no encontrado"}), 404

    workspace = rt.get("workspace_root", os.path.abspath(os.path.join(BASE_DIR, "..", "..")))

    try:
        from deploy_packager import DeployPackager
        pkg    = DeployPackager(folder, ticket_id, workspace)
        result = pkg.build()

        # Notificar por Telegram si el deploy fue ok
        if result.get("ok"):
            def _notify_deploy(r=result):
                try:
                    from teams_notifier import notify_deploy_generated
                    titulo = _get_ticket_title(folder, ticket_id)
                    has_sql      = any(f.get("type") == "sql" for f in r.get("files", []))
                    has_rollback = bool(r.get("rollback_zip_name"))
                    notify_deploy_generated(
                        ticket_id, titulo, r["zip_name"],
                        len(r.get("files", [])), has_sql, has_rollback,
                    )
                except Exception:
                    pass
            threading.Thread(target=_notify_deploy, daemon=True).start()

        return jsonify(result)
    except Exception as e:
        import traceback
        return jsonify({"ok": False, "error": str(e), "trace": traceback.format_exc()}), 500


@app.route("/api/download_deploy/<ticket_id>/<path:zip_name>")
def api_download_deploy(ticket_id: str, zip_name: str):
    """Sirve el ZIP de deploy generado para un ticket."""
    # Sanitizar: no permitir traversal
    if ".." in zip_name or "/" in zip_name or "\\" in zip_name:
        return jsonify({"ok": False, "error": "Nombre inválido"}), 400

    rt     = _get_runtime()
    folder = _find_ticket_folder(ticket_id, rt["tickets_base"])
    if not folder:
        return jsonify({"ok": False, "error": "Ticket no encontrado"}), 404

    zip_path = os.path.join(folder, zip_name)
    if not os.path.exists(zip_path):
        return jsonify({"ok": False, "error": "ZIP no encontrado"}), 404

    from flask import send_file
    return send_file(zip_path, as_attachment=True, download_name=zip_name,
                     mimetype="application/zip")


@app.route("/api/tracker_confirm/<ticket_id>", methods=["POST"])
def api_tracker_confirm(ticket_id: str):
    """
    Publica una nota en el tracker con el estado actual del pipeline.
    Body (opcional): { "resolve": true }  → cambia el estado a 'resuelta'
    """
    from pipeline_state import load_state
    rt     = _get_runtime()
    folder = _find_ticket_folder(ticket_id, rt["tickets_base"])
    if not folder:
        return jsonify({"ok": False, "error": f"Ticket {ticket_id} no encontrado"}), 404

    data          = request.get_json(force=True, silent=True) or {}
    resolve_state = bool(data.get("resolve", False))

    # Resolución unificada: el IssueProvider activo decide cómo publicar.
    try:
        from issue_provider import get_provider, CommentKind, load_tracker_config
    except Exception as e:
        return jsonify({"ok": False, "error": f"issue_provider indisponible: {e}"}), 500

    tracker_cfg = load_tracker_config(rt.get("name"))
    if not tracker_cfg:
        return jsonify({"ok": False,
                        "error": "issue_tracker no configurado para el proyecto activo"}), 400

    state = load_state(rt["state_path"])
    est   = state.get("tickets", {}).get(ticket_id, {}).get("estado", "")

    def _run_update():
        try:
            provider = get_provider(rt.get("name"), override_config=tracker_cfg)
            kind = (CommentKind.PM_CONFIRM
                    if est in ("pm_completado", "pm_en_proceso")
                    else CommentKind.QA_RESOLUTION)
            from daemon import _build_resolution_note
            note = _build_resolution_note(folder, ticket_id)
            ok   = provider.add_comment(ticket_id, note, kind=kind, is_html=True)
            if ok and resolve_state and kind == CommentKind.QA_RESOLUTION:
                provider.transition_state(ticket_id, "Resolved")
            print(f"[TRACKER:{provider.name}] Nota publicada para #{ticket_id}: {ok}",
                  flush=True)
        except Exception as e:
            print(f"[TRACKER] Error publicando nota para #{ticket_id}: {e}",
                  file=sys.stderr, flush=True)

    threading.Thread(target=_run_update, daemon=True).start()
    return jsonify({"ok": True, "ticket_id": ticket_id, "estado": est,
                    "msg": "Publicando nota en el issue tracker en segundo plano..."})


@app.route("/api/ado/<ticket_id>/mark-doing", methods=["POST"])
def api_ado_mark_doing(ticket_id: str):
    """
    Marca el Work Item ADO como 'Active' (equivalente a 'Doing' en la
    terminología del usuario). Body opcional: {"target_state": "Active"} para
    forzar otro estado nativo.

    Nota sobre el estado: en el proyecto Strategist_Pacifico el estado nativo
    real para "trabajo en curso" es ``Active`` (ver ado_reporter._ADO_STATE_MAP
    y ado_query_provider). Los aliases ``Doing`` / ``In Progress`` existen en
    el ``state_mapping`` como defensa para otros templates de ADO. Esta ruta
    intenta ``Active`` primero y cae a los aliases si el workflow del proyecto
    no lo acepta — equivalente al patrón ya usado por AzureDevOpsProvider.close().

    La llamada a ADO corre en thread daemon: respondemos optimistamente al UI
    y el dashboard refresca a los ~2s. Emite ``ado_state_changed`` al bus de
    eventos y publica una notificación (NOTIFICATIONS.json) para trazabilidad.
    """
    try:
        from issue_provider import get_provider, load_tracker_config
    except Exception as e:
        return jsonify({"ok": False,
                        "error": f"issue_provider indisponible: {e}"}), 500

    rt = _get_runtime()
    tracker_cfg = load_tracker_config(rt.get("name"))
    if not tracker_cfg:
        return jsonify({"ok": False,
                        "error": "issue_tracker no configurado para el proyecto activo"}), 400

    body = request.get_json(silent=True) or {}
    requested = (body.get("target_state") or "").strip()
    # Orden: pedido explícito > Active (nativo del proyecto) > aliases de otros templates.
    candidates = [requested] if requested else []
    for st in ("Active", "Doing", "In Progress"):
        if st not in candidates:
            candidates.append(st)

    def _run_transition():
        try:
            provider = get_provider(rt.get("name"), override_config=tracker_cfg)
            applied = None
            last_err = None
            for target in candidates:
                try:
                    if provider.transition_state(ticket_id, target):
                        applied = target
                        break
                except Exception as e:
                    last_err = e
            if not applied:
                detail = f"falló la transición a los estados {candidates}"
                if last_err:
                    detail += f" — último error: {last_err}"
                print(f"[ADO] mark-doing #{ticket_id}: {detail}",
                      file=sys.stderr, flush=True)
                try:
                    from notifier import notify as _notify
                    _notify(f"ADO → Doing falló para #{ticket_id}",
                            detail, level="error", ticket_id=ticket_id)
                except Exception:
                    pass
                try:
                    from pipeline_events import emit as _emit
                    _emit(kind="ado_state_change_failed",
                          ticket_id=ticket_id,
                          project=rt.get("name"),
                          detail=detail[:400])
                except Exception:
                    pass
                return

            # Éxito — evento + notificación.
            try:
                from pipeline_events import emit as _emit
                _emit(kind="ado_state_changed",
                      ticket_id=ticket_id,
                      project=rt.get("name"),
                      detail=f"to={applied} source=dashboard_mark_doing")
            except Exception:
                pass
            try:
                from notifier import notify as _notify
                _notify(f"▶ #{ticket_id} marcado {applied} en ADO",
                        "Transición disparada desde el dashboard.",
                        level="info", ticket_id=ticket_id)
            except Exception:
                pass
            print(f"[ADO] mark-doing #{ticket_id} → {applied}", flush=True)
        except Exception as e:
            print(f"[ADO] mark-doing #{ticket_id} error inesperado: {e}",
                  file=sys.stderr, flush=True)

    threading.Thread(target=_run_transition, daemon=True).start()
    return jsonify({
        "ok": True,
        "ticket_id": ticket_id,
        "candidates": candidates,
        "msg": "Transición a Active/Doing en curso en ADO (respuesta en segundo plano)...",
    })


@app.route("/api/reinvoke/<ticket_id>", methods=["POST"])
def api_reinvoke(ticket_id: str):
    """
    Reintenta la invocación del agente para el estado actual del ticket,
    SIN cambiar el estado del pipeline (no hace reset a pendiente).
    Útil cuando VS Code se abrió pero el chat no recibió el prompt.

    Query params:
      - force=1: limpia todos los cerrojos antes de reinvocar (EN_CURSO,
        INVOKE_LOCK.pid, lock files de stage, threading.Lock, gate global,
        PAUSED.flag). Úselo cuando el botón normal da "invocación duplicada".
    """
    from pipeline_state import load_state
    rt    = _get_runtime()
    state = load_state(rt["state_path"])
    est   = state.get("tickets", {}).get(ticket_id, {}).get("estado", "")

    force = request.args.get("force", "").lower() in ("1", "true", "yes")

    stage_map = {
        "pm_en_proceso":     "pm",
        "dev_en_proceso":    "dev",
        "tester_en_proceso": "tester",
    }
    stage = stage_map.get(est)
    # En modo force, también aceptamos estados de error para reinvocar
    if not stage and force:
        stage_err_map = {
            "error_pm": "pm", "error_dev": "dev", "error_tester": "tester",
        }
        stage = stage_err_map.get(est)
    if not stage:
        return jsonify({"ok": False,
                        "error": f"El ticket está en '{est}' — solo se puede reinvocar en *_en_proceso "
                                 f"(o error_* con force=1)"}), 400

    # force=1: borrar PAUSED.flag si existe para no bloquear la invocación
    if force:
        folder = _find_ticket_folder(ticket_id, rt["tickets_base"])
        if folder:
            paused = os.path.join(folder, "PAUSED.flag")
            if os.path.exists(paused):
                try:
                    os.remove(paused)
                except Exception:
                    pass

    t = threading.Thread(target=_invoke_stage, args=(ticket_id, stage),
                         kwargs={"force": force}, daemon=True)
    t.start()
    return jsonify({"ok": True, "ticket_id": ticket_id, "stage": stage,
                    "force": force,
                    "msg": (f"Force-reinvocación de etapa {stage} "
                            f"(cerrojos limpiados)") if force else
                           f"Reintentando invocar agente para etapa {stage}"})


# ── CANCEL / PAUSE / RESUME (control de agentes en curso) ─────────────────────

@app.route("/api/cancel/<ticket_id>", methods=["POST"])
def api_cancel(ticket_id: str):
    """
    Cancela la invocación en curso de un ticket:
      1. Limpia todos los cerrojos (EN_CURSO, INVOKE_LOCK.pid, lock files, gate global)
      2. Marca el estado del ticket como error_{stage}
      3. NO reinvoca — el ticket queda disponible para intervención manual

    LIMITACIÓN FÍSICA: el agente ya invocado sigue corriendo dentro de VS Code
    porque no se guarda su PID. Sus outputs (flag COMPLETADO, etc.) serán ignorados
    porque el lock ya no le pertenece; pero el chat de VS Code no se cierra.
    """
    from pipeline_state import load_state, save_state, mark_error
    rt     = _get_runtime()
    state  = load_state(rt["state_path"])
    est    = state.get("tickets", {}).get(ticket_id, {}).get("estado", "")
    folder = _find_ticket_folder(ticket_id, rt["tickets_base"])

    stage_map = {
        "pm_en_proceso":     "pm",
        "dev_en_proceso":    "dev",
        "tester_en_proceso": "tester",
    }
    stage = stage_map.get(est)

    cleared = {}
    try:
        from pipeline_lock import clear_all_locks as _clear_all_locks
        cleared = _clear_all_locks(ticket_id, folder)
    except Exception as e:
        cleared = {"errors": [str(e)]}

    try:
        with _ticket_locks_rlock:
            _ticket_invoke_locks.pop(ticket_id, None)
    except Exception:
        pass

    gate_released = False
    try:
        gate_released = _release_active_ticket(ticket_id, "cancel via API")
    except Exception:
        pass

    # Marcar error_{stage} solo si estaba en un *_en_proceso conocido
    if stage:
        try:
            mark_error(state, ticket_id, stage, "Cancelado manualmente desde dashboard")
            save_state(rt["state_path"], state)
        except Exception as e:
            print(f"[CANCEL] {ticket_id}: no se pudo marcar error_{stage}: {e}",
                  file=sys.stderr, flush=True)

    return jsonify({
        "ok":              True,
        "ticket_id":       ticket_id,
        "previous_estado": est,
        "stage":           stage,
        "cleared":         cleared,
        "gate_released":   gate_released,
        "msg":             (f"Cancelado — estado: error_{stage}" if stage
                            else "Cerrojos limpiados (no había *_en_proceso)"),
        "note":            ("El agente en VS Code puede seguir corriendo — "
                            "sus outputs serán ignorados."),
    })


@app.route("/api/pause/<ticket_id>", methods=["POST"])
def api_pause(ticket_id: str):
    """
    Pausa el auto-avance del pipeline para este ticket.
    Crea PAUSED.flag en la carpeta del ticket; el reconciliador y _invoke_stage
    respetan este flag y no lanzan nuevas etapas hasta que se resuma.
    También setea auto_advance=False como defensa redundante.

    El agente ya invocado NO se detiene — solo se impiden nuevas invocaciones.
    """
    from pipeline_state import load_state, save_state
    rt     = _get_runtime()
    folder = _find_ticket_folder(ticket_id, rt["tickets_base"])
    if not folder:
        return jsonify({"ok": False, "error": f"Carpeta no encontrada para {ticket_id}"}), 404

    flag_path = os.path.join(folder, "PAUSED.flag")
    try:
        with open(flag_path, "w", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat()}\npid={os.getpid()}\n")
    except Exception as e:
        return jsonify({"ok": False, "error": f"No se pudo crear PAUSED.flag: {e}"}), 500

    try:
        state = load_state(rt["state_path"])
        state.setdefault("tickets", {}).setdefault(ticket_id, {})["auto_advance"] = False
        state["tickets"][ticket_id]["paused_at"] = datetime.now().isoformat()
        save_state(rt["state_path"], state)
    except Exception as e:
        print(f"[PAUSE] {ticket_id}: no se pudo actualizar auto_advance: {e}",
              file=sys.stderr, flush=True)

    return jsonify({"ok": True, "ticket_id": ticket_id, "paused": True,
                    "flag": os.path.basename(flag_path),
                    "msg": "Pipeline pausado. El agente actual sigue; no se invocarán nuevos."})


@app.route("/api/resume/<ticket_id>", methods=["POST"])
def api_resume(ticket_id: str):
    """
    Reanuda el pipeline: borra PAUSED.flag y re-activa auto_advance.
    El watcher/reconciliador retomará automáticamente el curso normal.
    """
    from pipeline_state import load_state, save_state
    rt     = _get_runtime()
    folder = _find_ticket_folder(ticket_id, rt["tickets_base"])
    if not folder:
        return jsonify({"ok": False, "error": f"Carpeta no encontrada para {ticket_id}"}), 404

    flag_path = os.path.join(folder, "PAUSED.flag")
    removed = False
    if os.path.exists(flag_path):
        try:
            os.remove(flag_path)
            removed = True
        except Exception as e:
            return jsonify({"ok": False, "error": f"No se pudo borrar PAUSED.flag: {e}"}), 500

    try:
        state = load_state(rt["state_path"])
        entry = state.setdefault("tickets", {}).setdefault(ticket_id, {})
        entry["auto_advance"] = True
        entry.pop("paused_at", None)
        save_state(rt["state_path"], state)
    except Exception as e:
        print(f"[RESUME] {ticket_id}: no se pudo actualizar auto_advance: {e}",
              file=sys.stderr, flush=True)

    return jsonify({"ok": True, "ticket_id": ticket_id, "paused": False,
                    "flag_removed": removed,
                    "msg": "Pipeline reanudado. El watcher retomará el avance automático."})


@app.route("/api/pipeline/health", methods=["GET"])
def api_pipeline_health():
    """
    Devuelve el diagnóstico de salud del pipeline ticket-por-ticket.

    Para cada ticket activo reporta:
      - estado almacenado en state.json
      - estado real derivado del folder
      - coherencia, sugerencias de reconciliación
      - stale (ticket atascado sin progreso)
      - timeline de las últimas N transiciones (si existen)

    El frontend usa esto para pintar badges de advertencia y ofrecer
    botones de "reanudar" en tickets divergentes.
    """
    from pipeline_reconciler import reconcile_ticket_entry
    from pipeline_state import load_state

    rt = _get_runtime()
    try:
        state = load_state(rt["state_path"])
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

    results = []
    for tid, entry in (state.get("tickets", {}) or {}).items():
        if not isinstance(entry, dict):
            continue
        # Saltar entradas sin folder (solo prioridad del Rally)
        est = entry.get("estado", "")
        if not est and not entry.get("folder"):
            continue
        folder = entry.get("folder") or _find_ticket_folder(tid, rt["tickets_base"])
        if not folder or not os.path.isdir(folder):
            continue

        try:
            res = reconcile_ticket_entry(tid, folder, entry, debounce_seconds=0)
        except Exception as e:
            results.append({
                "ticket_id": tid,
                "error":     f"reconcile_error: {e}",
            })
            continue

        transitions = entry.get("transitions") or []
        # Últimas 5 para la UI (compacto)
        recent_trans = transitions[-5:] if transitions else []

        results.append({
            "ticket_id":       tid,
            "stored_estado":   res.stored_estado,
            "derived_estado":  res.derived.estado if res.derived else None,
            "next_stage":      res.derived.next_stage if res.derived else None,
            "evidence":        res.derived.evidence if res.derived else [],
            "coherent":        res.coherent,
            "needs_sync":      res.needs_sync,
            "synthetic_state": res.synthetic_state,
            "launch_stage":    res.launch_stage,
            "is_stale":        res.is_stale,
            "stale_reason":    res.stale_reason,
            "warnings":        res.warnings,
            "qa_verdict":      res.derived.qa_verdict if res.derived else None,
            "transitions":     recent_trans,
        })

    return jsonify({
        "ok":      True,
        "tickets": results,
        "count":   len(results),
    })


@app.route("/api/pipeline/reconcile/<ticket_id>", methods=["POST"])
def api_pipeline_reconcile_now(ticket_id: str):
    """
    Fuerza reconciliación inmediata de un ticket (salta cooldown).

    Usa el mismo motor que el loop periódico, pero ejecuta ya. Útil cuando
    el usuario ve una divergencia en la UI y quiere corregirla al instante
    sin esperar el próximo tick del reconciliador.
    """
    from pipeline_reconciler import reconcile_ticket_entry
    from pipeline_state import load_state, save_state, _load_cache as _plc

    _plc["mtime"] = 0.0
    rt    = _get_runtime()
    state = load_state(rt["state_path"])
    entry = state.get("tickets", {}).get(ticket_id)
    if not entry:
        return jsonify({"ok": False, "error": f"Ticket {ticket_id} no encontrado"}), 404
    folder = entry.get("folder") or _find_ticket_folder(ticket_id, rt["tickets_base"])
    if not folder or not os.path.isdir(folder):
        return jsonify({"ok": False, "error": "Folder inexistente"}), 404

    res = reconcile_ticket_entry(ticket_id, folder, entry, debounce_seconds=0)

    actions = []
    if res.needs_sync and res.synthetic_state:
        prev_estado = entry.get("estado", "")
        entry["estado"] = res.synthetic_state
        entry[f"{res.synthetic_state}_at"] = datetime.now().isoformat()
        if prev_estado == "completado":
            entry.pop("completado_at", None)
        transitions = entry.setdefault("transitions", [])
        transitions.append({
            "at":   datetime.now().isoformat(),
            "from": prev_estado,
            "to":   res.synthetic_state,
            "by":   "manual_reconcile",
            "evidence": res.derived.evidence if res.derived else [],
        })
        if len(transitions) > 50:
            entry["transitions"] = transitions[-50:]
        save_state(rt["state_path"], state)
        actions.append(f"state synced: {prev_estado} → {res.synthetic_state}")
        _RECONCILER_PER_TICKET[ticket_id] = _time.monotonic()

    if res.launch_stage:
        entry["auto_advance"] = True
        save_state(rt["state_path"], state)
        threading.Thread(
            target=_invoke_stage, args=(ticket_id, res.launch_stage),
            daemon=True, name=f"manual-reconcile-{ticket_id}",
        ).start()
        actions.append(f"launched stage: {res.launch_stage}")

    return jsonify({
        "ok":       True,
        "actions":  actions,
        "coherent": res.coherent,
        "derived":  res.derived.estado if res.derived else None,
        "evidence": res.derived.evidence if res.derived else [],
        "is_stale": res.is_stale,
        "msg":      ("Reconciliación aplicada" if actions
                     else "Ya estaba coherente — nada que hacer"),
    })


# ── Agent customization (per-project, per-agent) ──────────────────────────────

@app.route("/api/agent_config/<agent>", methods=["GET", "POST"])
def api_agent_config(agent: str):
    """
    GET:  Retorna la config actual del agente para el proyecto activo.
    POST: Persiste una nueva config. Body JSON con campos de AgentConfig.
    """
    try:
        from agent_config import (
            load_agent_config, save_agent_config,
            from_dict, to_dict, KNOWN_AGENTS, VALID_STRICTNESS,
        )
        from project_manager import get_active_project, get_project_paths
    except ImportError as e:
        return jsonify({"ok": False, "error": f"Módulo no disponible: {e}"}), 500

    if agent not in KNOWN_AGENTS:
        return jsonify({
            "ok": False,
            "error": f"Agente desconocido: {agent}. Válidos: {list(KNOWN_AGENTS)}",
        }), 400

    project_name = get_active_project()
    project_root = get_project_paths(project_name)["base"]

    if request.method == "GET":
        cfg = load_agent_config(project_root, agent)
        return jsonify({
            "ok":            True,
            "agent":         agent,
            "project":       project_name,
            "config":        to_dict(cfg),
            "valid_strictness": list(VALID_STRICTNESS),
        })

    data = request.json or {}
    try:
        cfg = from_dict(data)
        if cfg.strictness not in VALID_STRICTNESS:
            return jsonify({
                "ok": False,
                "error": f"strictness debe ser uno de {list(VALID_STRICTNESS)}",
            }), 400
        path = save_agent_config(project_root, agent, cfg)
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except Exception as e:
        return jsonify({"ok": False, "error": f"Error guardando: {e}"}), 500

    return jsonify({
        "ok":      True,
        "agent":   agent,
        "project": project_name,
        "path":    path,
        "config":  to_dict(cfg),
        "msg":     "Configuración guardada. Aplicará en la próxima invocación del agente.",
    })


@app.route("/api/agent_config", methods=["GET"])
def api_agent_config_all():
    """Lista todas las configs de agentes para el proyecto activo."""
    try:
        from agent_config import load_agent_config, to_dict, KNOWN_AGENTS
        from project_manager import get_active_project, get_project_paths
    except ImportError as e:
        return jsonify({"ok": False, "error": f"Módulo no disponible: {e}"}), 500

    project_name = get_active_project()
    project_root = get_project_paths(project_name)["base"]

    configs = {}
    for ag in KNOWN_AGENTS:
        cfg = load_agent_config(project_root, ag)
        configs[ag] = to_dict(cfg)
    return jsonify({"ok": True, "project": project_name, "configs": configs})


@app.route("/api/unstick/<ticket_id>", methods=["POST"])
def api_unstick(ticket_id: str):
    """
    Invoca al agente DESATASCADOR para un ticket frenado.

    El agente recibe el estado actual + inventario de archivos + motivo y tiene
    autoridad para crear/borrar flags, completar archivos a medias y decidir la
    próxima etapa válida. Útil cuando el pipeline se queda colgado por:
      - Flag de completado no creado pese a que el trabajo está hecho
      - Archivos con placeholders o vacíos
      - Flags EN_CURSO / ERROR huérfanos
      - stagnation_detected tras rechazos repetidos
    """
    from copilot_bridge import invoke_agent
    from pipeline_state import load_state
    from prompt_builder import build_unstuck_prompt

    data   = request.json or {}
    reason = (data.get("reason") or "").strip()

    rt     = _get_runtime()
    state  = load_state(rt["state_path"])
    entry  = state.get("tickets", {}).get(ticket_id, {}) or {}
    est    = entry.get("estado", "")

    folder = _find_ticket_folder(ticket_id, rt["tickets_base"])
    if not folder:
        return jsonify({"ok": False, "error": f"Carpeta no encontrada para {ticket_id}"}), 404

    # Inferir motivo si no vino del frontend
    if not reason:
        last_err = entry.get("error") or ""
        last_inv = entry.get("last_invoke") or {}
        hints = []
        if est.endswith("_en_proceso"):
            hints.append(f"Sigue en '{est}' — probable flag de completado no creado")
        if est.startswith("error_"):
            hints.append(f"Estado de error: {est}")
        if est == "stagnation_detected":
            hints.append(f"Stagnation tras {entry.get('rework_count', 0)} reworks — "
                         f"último veredicto: {entry.get('last_qa_verdict', '?')}")
        if last_err:
            hints.append(f"error registrado: {last_err}")
        if last_inv.get("ok") is False:
            hints.append(f"última invocación falló: {last_inv.get('detail', '')}")
        reason = " · ".join(hints) or "Usuario solicitó desatasco manual sin detalle"

    prompt = build_unstuck_prompt(folder, ticket_id, rt["workspace_root"],
                                   current_state=est or "desconocido",
                                   reason=reason)

    # Usar el agente PM como ejecutor del desatasco (tiene el scope más amplio)
    pm_agent = rt.get("agents", {}).get("pm")

    def _do_unstick():
        try:
            ok = invoke_agent(prompt, agent_name=pm_agent,
                              project_name=rt.get("name", ""),
                              workspace_root=rt["workspace_root"],
                              new_conversation=True)
            s2 = load_state(rt["state_path"])
            s2.setdefault("tickets", {}).setdefault(ticket_id, {})["last_unstick"] = {
                "at":     datetime.now().isoformat(),
                "ok":     bool(ok),
                "reason": reason,
                "from_state": est,
            }
            from pipeline_state import save_state as _save
            _save(rt["state_path"], s2)
        except Exception as e:
            print(f"[UNSTICK] Error para {ticket_id}: {e}", file=sys.stderr, flush=True)
            return

        # Tras el desatasco, delegamos al reconciliador centralizado:
        # deriva el estado desde los archivos del folder, sincroniza state.json
        # y lanza la etapa que corresponda. Una sola fuente de verdad.
        def _relaunch_after_unstick():
            import time as _t
            _t.sleep(4.0)
            try:
                from pipeline_reconciler import reconcile_ticket_entry
                from pipeline_state import _load_cache as _plc
                _plc["mtime"] = 0.0
                s3 = load_state(rt["state_path"])
                entry3 = s3.get("tickets", {}).get(ticket_id, {}) or {}

                if not folder:
                    print(f"[UNSTICK] {ticket_id}: folder ausente — no relanzo",
                          flush=True)
                    return

                # Debounce=0 — recién invocamos el desatascador y ya esperamos 4s.
                # Queremos relanzar inmediatamente si hay divergencia.
                res = reconcile_ticket_entry(
                    ticket_id, folder, entry3, debounce_seconds=0,
                )

                if not res.derived:
                    print(f"[UNSTICK] {ticket_id}: sin derivación posible", flush=True)
                    return

                # Si hay bloqueo humano, no reintentar
                if res.derived.estado == "bloqueo_humano":
                    print(f"[UNSTICK] {ticket_id}: BLOQUEO_HUMANO.flag presente — "
                          f"no relanzo pipeline", flush=True)
                    _push_notification(
                        f"🛑 Ticket #{ticket_id} requiere intervención",
                        "El desatascador marcó BLOQUEO_HUMANO — revisar manualmente",
                        "warning",
                    )
                    return

                if res.coherent and not res.launch_stage:
                    print(f"[UNSTICK] {ticket_id}: estado ya coherente "
                          f"({res.stored_estado}) — nada que lanzar", flush=True)
                    return

                # Sincronizar state.json si diverge
                if res.needs_sync and res.synthetic_state:
                    prev_estado = entry3.get("estado", "")
                    s3.setdefault("tickets", {}).setdefault(ticket_id, {})
                    s3["tickets"][ticket_id]["estado"] = res.synthetic_state
                    s3["tickets"][ticket_id][f"{res.synthetic_state}_at"] = \
                        datetime.now().isoformat()
                    if prev_estado == "completado":
                        s3["tickets"][ticket_id].pop("completado_at", None)
                    # Timeline
                    transitions = s3["tickets"][ticket_id].setdefault("transitions", [])
                    transitions.append({
                        "at":   datetime.now().isoformat(),
                        "from": prev_estado,
                        "to":   res.synthetic_state,
                        "by":   "unstick",
                        "evidence": res.derived.evidence,
                    })
                    if len(transitions) > 50:
                        s3["tickets"][ticket_id]["transitions"] = transitions[-50:]
                    s3["tickets"][ticket_id]["auto_advance"] = True
                    _save(rt["state_path"], s3)

                if res.launch_stage:
                    print(f"[UNSTICK] {ticket_id}: post-desatasco → "
                          f"{res.launch_stage.upper()} "
                          f"(evidencia: {', '.join(res.derived.evidence)})",
                          flush=True)
                    _push_notification(
                        f"🚑 Post-desatasco #{ticket_id}",
                        f"Relanzando {res.launch_stage.upper()} — "
                        f"{', '.join(res.derived.evidence)}",
                        "info",
                    )
                    _invoke_stage(ticket_id, res.launch_stage)
                else:
                    print(f"[UNSTICK] {ticket_id}: sincronizado a "
                          f"{res.synthetic_state}, sin etapa que lanzar",
                          flush=True)
            except Exception as _re:
                print(f"[UNSTICK] Error relanzando post-desatasco: {_re}",
                      file=sys.stderr, flush=True)

        threading.Thread(target=_relaunch_after_unstick, daemon=True,
                         name=f"unstick-relaunch-{ticket_id}").start()

    threading.Thread(target=_do_unstick, daemon=True).start()
    return jsonify({"ok": True, "ticket_id": ticket_id,
                    "from_state": est, "reason": reason,
                    "msg": "Agente desatascador invocado — escribirá DESATASCO_COMPLETADO.md al terminar"})


@app.route("/api/send_correction", methods=["POST"])
def api_send_correction():
    """
    Envía una corrección manual al Developer para un ticket ya procesado por QA.

    Body: { "ticket_id": "0027698", "correction": "El campo X no valida correctamente..." }

    Proceso:
    1. Guarda la corrección en CORRECCION_DEV.md dentro del ticket folder
    2. Invoca al Developer con el contexto completo + el texto de corrección
    3. Resetea el estado a dev_en_proceso
    """
    from copilot_bridge import invoke_agent
    from pipeline_state import load_state, save_state, set_ticket_state, mark_error

    data       = request.json or {}
    ticket_id  = data.get("ticket_id", "").strip()
    correction = data.get("correction", "").strip()

    if not ticket_id or not correction:
        return jsonify({"ok": False, "error": "ticket_id y correction requeridos"}), 400

    folder = _find_ticket_folder(ticket_id)
    if not folder:
        return jsonify({"ok": False, "error": f"Ticket {ticket_id} no encontrado"}), 404

    rt             = _get_runtime()
    WORKSPACE_ROOT = rt["workspace_root"]
    DEV_AGENT      = rt["agents"]["dev"]

    # Guardar corrección en archivo
    correction_file = os.path.join(folder, "CORRECCION_DEV.md")
    try:
        with open(correction_file, "w", encoding="utf-8") as f:
            f.write(f"# Corrección solicitada por el usuario\n\n")
            f.write(f"**Fecha:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write(f"---\n\n")
            f.write(correction)
    except Exception as e:
        return jsonify({"ok": False, "error": f"Error guardando corrección: {e}"}), 500

    # Leer resumen de QA si existe para dárselo al dev
    qa_summary = ""
    qa_path = os.path.join(folder, "TESTER_COMPLETADO.md")
    if os.path.exists(qa_path):
        try:
            qa_summary = open(qa_path, encoding="utf-8").read()
        except Exception:
            pass

    # Construir prompt de corrección
    prompt = f"""Implementá las correcciones solicitadas para el ticket #{ticket_id}.

Carpeta de trabajo: {os.path.relpath(folder, WORKSPACE_ROOT).replace(chr(92), '/')}

## Contexto

El Developer ya implementó este ticket pero el QA Tester y/o el usuario identificaron problemas
que deben corregirse. Tu tarea es leer el contexto anterior y aplicar las correcciones indicadas.

## Archivos a leer (en orden)
1. INCIDENTE.md — contexto del ticket
2. ANALISIS_TECNICO.md — causa raíz
3. ARQUITECTURA_SOLUCION.md — solución propuesta
4. TAREAS_DESARROLLO.md — tareas originales
5. DEV_COMPLETADO.md — qué implementó el Developer
6. TESTER_COMPLETADO.md — qué encontró el QA (si existe)
7. CORRECCION_DEV.md — **las correcciones específicas que debés aplicar** ← PRIORITARIO

## Corrección solicitada

{correction}

{"## Reporte de QA" + chr(10) + chr(10) + qa_summary if qa_summary else ""}

## Instrucciones

1. Leé todos los archivos de contexto listados arriba
2. Aplicá SOLO las correcciones indicadas — no cambies lo que ya funciona
3. Al finalizar, actualizá (o recreá) el archivo DEV_COMPLETADO.md con los nuevos cambios
4. Si encontrás un bloqueante, creá DEV_ERROR.flag con la descripción
5. No preguntes — ejecutá basándote en los archivos de la carpeta
"""

    def _run():
        _rt   = _get_runtime()
        state = load_state(_rt["state_path"])
        set_ticket_state(state, ticket_id, "dev_en_proceso")
        save_state(_rt["state_path"], state)

        if not invoke_agent(prompt, agent_name=DEV_AGENT, project_name=_rt["name"]):
            mark_error(state, ticket_id, "dev", "No se pudo invocar al agente via UI (send_correction)")
            save_state(_rt["state_path"], state)
            return

        import time
        sentinel     = os.path.join(folder, "DEV_COMPLETADO.md")
        dev_err_flag = os.path.join(folder, "DEV_ERROR.flag")

        while True:
            time.sleep(5)
            if os.path.exists(dev_err_flag):
                try:
                    reason = open(dev_err_flag, encoding="utf-8").read().strip()
                except Exception:
                    reason = "DEV_ERROR.flag creado"
                mark_error(state, ticket_id, "dev", reason)
                save_state(_rt["state_path"], state)
                return
            if os.path.exists(sentinel):
                set_ticket_state(state, ticket_id, "dev_completado")
                save_state(_rt["state_path"], state)
                return

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"ok": True, "ticket_id": ticket_id, "correction_saved": correction_file})


# ── Endpoints de proyectos ────────────────────────────────────────────────────

@app.route("/api/projects")
def api_projects():
    """Lista todos los proyectos inicializados."""
    from project_manager import get_all_projects, get_active_project
    projects    = get_all_projects()
    active_name = get_active_project()

    result = []
    for p in projects:
        tracker = p.get("issue_tracker") or {}
        result.append({
            "name":              p["name"],
            "display_name":      p["display_name"],
            "workspace_root":    p.get("workspace_root", ""),
            "organization":      tracker.get("organization", ""),
            "ado_project":       tracker.get("project", ""),
            "active":            p["name"] == active_name,
            "initialized":       True,
        })
    return jsonify({"ok": True, "projects": result, "active": active_name})


@app.route("/api/active_project", methods=["GET", "POST"])
def api_active_project():
    from project_manager import get_active_project, set_active_project, get_project_config
    if request.method == "GET":
        name = get_active_project()
        cfg  = get_project_config(name) or {}
        return jsonify({"ok": True, "active": name, "display_name": cfg.get("display_name", name)})
    data = request.json or {}
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"ok": False, "error": "name requerido"}), 400
    cfg = get_project_config(name)
    if not cfg:
        return jsonify({"ok": False, "error": f"Proyecto '{name}' no inicializado"}), 404
    set_active_project(name)
    _invalidate_runtime_cache()
    _scan_cache["ts"] = 0.0  # forzar re-scan
    return jsonify({"ok": True, "active": name, "display_name": cfg.get("display_name", name)})


@app.route("/api/init_project", methods=["POST"])
def api_init_project():
    """
    Inicializa un nuevo proyecto.
    Body: { "name": "RSMOBILE", "display_name": "RS Mobile",
            "workspace_root": "N:/RSMOBILE/trunk",
            "organization": "UbimiaPacifico",
            "ado_project": "Strategist_Pacifico",
            "area_path": "Strategist_Pacifico\\AgendaWeb" }
    """
    from project_manager import initialize_ado_project
    data           = request.json or {}
    name           = data.get("name", "").strip()
    display_name   = data.get("display_name", "").strip()
    workspace_root = data.get("workspace_root", "").strip()
    organization   = data.get("organization", "").strip()
    ado_project    = data.get("ado_project", "").strip()
    area_path      = data.get("area_path", "").strip()
    if not name:
        return jsonify({"ok": False, "error": "name requerido"}), 400
    if not workspace_root:
        return jsonify({"ok": False, "error": "workspace_root requerido"}), 400
    if not organization:
        return jsonify({"ok": False, "error": "organization requerido (ej: UbimiaPacifico)"}), 400
    if not ado_project:
        return jsonify({"ok": False, "error": "ado_project requerido (ej: Strategist_Pacifico)"}), 400
    try:
        cfg = initialize_ado_project(
            name=name,
            display_name=display_name or name,
            workspace_root=workspace_root,
            organization=organization,
            ado_project=ado_project,
            area_path=area_path,
        )
        return jsonify({"ok": True, "project": cfg})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ── Stages ────────────────────────────────────────────────────────────────

@app.route("/api/stages", methods=["GET"])
def api_stages():
    """Retorna la definición de etapas del pipeline del proyecto activo.
    Si el proyecto tiene 'stages' en config.json se usan esas; sino las 3 por defecto."""
    rt = _get_runtime()
    default = [
        {"id": "pm",     "label": "PM Análisis", "icon": "📋", "color": "#3b82f6",
         "agent": rt["agents"].get("pm",     "PM-TL STack 3")},
        {"id": "dev",    "label": "Dev Impl.",    "icon": "⚙",  "color": "#a855f7",
         "agent": rt["agents"].get("dev",    "DevStack3")},
        {"id": "tester", "label": "QA Tester",    "icon": "🧪",  "color": "#f97316",
         "agent": rt["agents"].get("tester", "QA")},
    ]
    try:
        from project_manager import get_project_config
        cfg = get_project_config(rt["name"])
        if cfg and "stages" in cfg and isinstance(cfg["stages"], list) and cfg["stages"]:
            return jsonify({"stages": cfg["stages"], "project": rt["name"]})
    except Exception:
        pass
    return jsonify({"stages": default, "project": rt["name"]})


# ── Stats ─────────────────────────────────────────────────────────────────

@app.route("/api/metrics/operational")
def api_metrics_operational():
    """Y-07: Métricas operacionales — últimas 24h por defecto."""
    days = request.args.get("days", 1, type=int)
    try:
        from metrics_collector import MetricsCollector
        rt = _get_runtime()
        mc = MetricsCollector(rt.get("name", "default"))
        data = mc.get_operational_metrics(days=days)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e), "days": days}), 500


@app.route("/api/metrics/executive")
def api_metrics_executive():
    """Y-07: KPIs ejecutivos — últimas 4 semanas por defecto."""
    weeks = request.args.get("weeks", 4, type=int)
    try:
        from metrics_collector import MetricsCollector
        rt = _get_runtime()
        mc = MetricsCollector(rt.get("name", "default"))
        data = mc.get_executive_metrics(weeks=weeks)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e), "weeks": weeks}), 500


@app.route("/api/stats", methods=["GET"])
def api_stats():
    """Estadísticas de duración por etapa (pm, dev, tester)."""
    try:
        state = _load_pipeline_state()
        tickets_state = state.get("tickets", {})

        def _calc(ini_key, fin_key):
            durations = []
            for entry in tickets_state.values():
                try:
                    ini = entry.get(ini_key)
                    fin = entry.get(fin_key)
                    if ini and fin:
                        d = (datetime.fromisoformat(fin) - datetime.fromisoformat(ini)).total_seconds()
                        if d > 0:
                            durations.append(d)
                except Exception:
                    pass
            if not durations:
                return {"count": 0, "avg": None, "min": None, "max": None}
            return {
                "count": len(durations),
                "avg":   round(sum(durations) / len(durations), 1),
                "min":   round(min(durations), 1),
                "max":   round(max(durations), 1),
            }

        return jsonify({
            "pm":     _calc("pm_inicio_at",     "pm_fin_at"),
            "dev":    _calc("dev_inicio_at",    "dev_fin_at"),
            "tester": _calc("tester_inicio_at", "tester_fin_at"),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Prompts ───────────────────────────────────────────────────────────────

@app.route("/api/prompts/<role>", methods=["GET"])
def api_get_prompt(role):
    """Devuelve el contenido del prompt de un rol para el proyecto activo."""
    if role not in ("pm", "dev", "tester"):
        return jsonify({"ok": False, "error": "rol inválido"}), 400
    try:
        from project_manager import get_active_project, get_project_paths
        name  = get_active_project()
        paths = get_project_paths(name)
        fpath = os.path.join(paths["prompts"], f"{role}.md")
        if not os.path.exists(fpath):
            return jsonify({"ok": True, "content": ""})
        with open(fpath, "r", encoding="utf-8") as f:
            return jsonify({"ok": True, "content": f.read()})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/prompts/<role>", methods=["POST"])
def api_save_prompt(role):
    """Guarda el contenido del prompt de un rol para el proyecto activo."""
    if role not in ("pm", "dev", "tester"):
        return jsonify({"ok": False, "error": "rol inválido"}), 400
    try:
        from project_manager import get_active_project, get_project_paths
        data    = request.get_json(force=True) or {}
        content = data.get("content", "")
        name    = get_active_project()
        paths   = get_project_paths(name)
        prompts_dir = paths["prompts"]
        os.makedirs(prompts_dir, exist_ok=True)
        fpath = os.path.join(prompts_dir, f"{role}.md")
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(content)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ── Gen Prompts ────────────────────────────────────────────────────────────

@app.route("/api/gen_prompts/<ticket_id>", methods=["GET"])
def api_gen_prompts(ticket_id):
    """
    Lee el contexto de un ticket y genera prompts compactos para Dev y QA.
    Devuelve: { ok, titulo, dev_prompt, qa_prompt, folder, tareas }
    """
    folder = _find_ticket_folder(ticket_id)
    if not folder:
        return jsonify({"ok": False, "error": "Ticket no encontrado"}), 404

    rt = _get_runtime()
    workspace = rt.get("workspace_root", "")
    project   = rt.get("name", "RIPLEY")

    # ── Leer título ────────────────────────────────────────────────────────
    titulo = f"Ticket #{ticket_id}"
    inc_file = os.path.join(folder, f"INC-{ticket_id}.md")
    if os.path.exists(inc_file):
        try:
            for line in open(inc_file, encoding="utf-8"):
                line = line.strip()
                if line.startswith("**Título:**"):
                    titulo = line.replace("**Título:**", "").strip()
                    break
                if line.startswith("# "):
                    titulo = line.lstrip("# ").strip()
                    break
        except Exception:
            pass

    # ── Leer primeras líneas del ANALISIS_TECNICO para el problema ─────────
    problema = ""
    at_file = os.path.join(folder, "ANALISIS_TECNICO.md")
    if os.path.exists(at_file):
        try:
            content = open(at_file, encoding="utf-8").read()
            # Buscar sección "## Problema" o similar
            for m in [
                __import__("re").search(r"## Problema.*?\n(.+?)(?=\n##|\Z)", content, __import__("re").DOTALL),
                __import__("re").search(r"## Descripción.*?\n(.+?)(?=\n##|\Z)", content, __import__("re").DOTALL),
            ]:
                if m:
                    problema = m.group(1).strip()[:300]
                    # limpiar líneas vacías
                    problema = " ".join(l.strip() for l in problema.splitlines() if l.strip())
                    break
        except Exception:
            pass

    # ── Leer tareas de TAREAS_DESARROLLO.md ───────────────────────────────
    tareas = []
    td_file = os.path.join(folder, "TAREAS_DESARROLLO.md")
    if os.path.exists(td_file):
        try:
            content = open(td_file, encoding="utf-8").read()
            import re as _re2
            for m in _re2.finditer(r"^## (T\d+[^#\n]*)", content, _re2.MULTILINE):
                tareas.append(m.group(1).strip())
        except Exception:
            pass

    # Ruta relativa del folder para el prompt
    try:
        rel_folder = os.path.relpath(folder, workspace).replace("\\", "/")
    except ValueError:
        rel_folder = folder.replace("\\", "/")

    agente_dev    = rt.get("agents", {}).get("dev",    "DevStack2")
    agente_tester = rt.get("agents", {}).get("tester", "QA")

    # ── Prompt Dev ─────────────────────────────────────────────────────────
    tareas_txt = "\n".join(f"  - {t}" for t in tareas) if tareas else "  - Ver TAREAS_DESARROLLO.md"
    _ticket_header_dev = (
        f"═══════════════════════════════════════════════════\n"
        f"🎫 TICKET #{ticket_id} — {titulo}\n"
        f"   Etapa: ⚙ Dev — Implementación\n"
        f"═══════════════════════════════════════════════════\n\n"
        f"⚠️ **PRIMER PASO OBLIGATORIO:** Renombrá esta conversación a:\n"
        f"   `#{ticket_id} — DEV`\n"
        f"   (click en el título del chat → editá el nombre)\n\n"
    )
    dev_prompt = (
        _ticket_header_dev
        + f"Actuá como **{agente_dev}**.\n\n"
        f"**Ticket #{ticket_id} — {titulo}**\n\n"
        f"Carpeta de trabajo: `{rel_folder}/`\n\n"
        f"Lee en orden:\n"
        f"1. `INCIDENTE.md` — descripción del problema\n"
        f"2. `ANALISIS_TECNICO.md` — diagnóstico técnico\n"
        f"3. `ARQUITECTURA_SOLUCION.md` — diseño de la solución\n"
        f"4. `NOTAS_IMPLEMENTACION.md` — notas y precauciones\n"
        f"5. `TAREAS_DESARROLLO.md` — implementá las tareas\n\n"
        f"Tareas a ejecutar:\n{tareas_txt}\n\n"
    )
    if problema:
        dev_prompt += f"Contexto: {problema}\n\n"
    dev_prompt += (
        f"Al terminar, creá `DEV_COMPLETADO.md` con:\n"
        f"- Resumen de cambios por tarea\n"
        f"- Archivos modificados\n"
        f"- Cómo probar\n"
    )

    # ── Prompt QA ──────────────────────────────────────────────────────────
    _ticket_header_qa = (
        f"═══════════════════════════════════════════════════\n"
        f"🎫 TICKET #{ticket_id} — {titulo}\n"
        f"   Etapa: 🧪 QA — Pruebas\n"
        f"═══════════════════════════════════════════════════\n\n"
        f"⚠️ **PRIMER PASO OBLIGATORIO:** Renombrá esta conversación a:\n"
        f"   `#{ticket_id} — QA`\n"
        f"   (click en el título del chat → editá el nombre)\n\n"
    )
    qa_prompt = (
        _ticket_header_qa
        + f"Actuá como **{agente_tester}**.\n\n"
        f"**QA — Ticket #{ticket_id} — {titulo}**\n\n"
        f"El Dev implementó las tareas en: `{rel_folder}/`\n\n"
        f"Pasos:\n"
        f"1. Leé `DEV_COMPLETADO.md` para ver qué se implementó\n"
        f"2. Revisá `TAREAS_DESARROLLO.md` y verificá cada criterio de aceptación\n"
        f"3. Ejecutá las queries de `QUERIES_ANALISIS.sql` para validar en BD\n"
        f"4. Ejecutá pruebas unitarias para los cambios indicados\n"
        f"5. Documentá resultados en `TESTER_COMPLETADO.md`\n\n"
        f"Veredicto final en TESTER_COMPLETADO.md debe ser:\n"
        f"**APROBADO** · **CON OBSERVACIONES** · **RECHAZADO**\n"
    )
    if tareas:
        qa_prompt += f"\nTareas a verificar:\n" + "\n".join(f"- {t}" for t in tareas) + "\n"

    return jsonify({
        "ok":         True,
        "ticket_id":  ticket_id,
        "titulo":     titulo,
        "tareas":     tareas,
        "dev_prompt": dev_prompt,
        "qa_prompt":  qa_prompt,
        "folder":     rel_folder,
    })


@app.route("/api/generate_project_docs", methods=["POST"])
def api_generate_project_docs():
    """
    Construye el prompt de documentación del proyecto y lo envía al agente documentador
    configurado en config.json (agents.documenter, default: 'PM-TL STack 3').
    Devuelve: { ok, prompt, docs_path, agent }
    """
    rt            = _get_runtime()
    project_name  = rt.get("name", "RIPLEY")
    workspace     = rt.get("workspace_root", "")
    agents        = rt.get("agents", {})
    agent_name    = agents.get("documenter") or agents.get("pm", "PM-TL STack 3")

    from project_documenter import build_doc_prompt, get_project_docs_path
    docs_path = get_project_docs_path(project_name, BASE_DIR)
    prompt    = build_doc_prompt(project_name, workspace, docs_path)

    # Invocar agente en background
    def _run():
        try:
            from copilot_bridge import invoke_agent
            invoke_agent(prompt, agent_name=agent_name,
                         project_name=project_name, workspace_root=workspace)
        except Exception as e:
            print(f"[DOC-GEN] Error invocando agente: {e}", file=sys.stderr)

    threading.Thread(target=_run, daemon=True).start()

    return jsonify({
        "ok":        True,
        "prompt":    prompt,
        "docs_path": docs_path,
        "agent":     agent_name,
    })


@app.route("/api/project_docs_status", methods=["GET"])
def api_project_docs_status():
    """Informa si PROJECT_DOCS.md existe y cuándo fue generado."""
    rt           = _get_runtime()
    project_name = rt.get("name", "RIPLEY")
    from project_documenter import get_project_docs_path
    docs_path = get_project_docs_path(project_name, BASE_DIR)
    exists    = os.path.exists(docs_path)
    info      = {"ok": True, "exists": exists, "path": docs_path}
    if exists:
        import time as _t
        mtime = os.path.getmtime(docs_path)
        info["age_days"]     = round((_t.time() - mtime) / 86400, 1)
        info["generated_at"] = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
    return jsonify(info)


@app.route("/api/run_scraper", methods=["POST"])
def api_run_scraper():
    """Dispara la sincronización de tickets en background, pasando el proyecto activo."""
    rt = _get_runtime()
    project_name = rt.get("name")

    def _run():
        import subprocess, traceback
        try:
            from issue_provider.sync import sync_tickets
            sync_tickets(project_name)
        except Exception:
            print(f"[SYNC] ERROR EN THREAD:\n{traceback.format_exc()}", flush=True)

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"ok": True, "iniciado": True, "project": project_name})


@app.route("/api/project_config", methods=["PATCH"])
def api_patch_project_config():
    """Actualiza campos editables del config de un proyecto existente."""
    import json as _json
    from project_manager import PROJECTS_DIR
    data = request.json or {}
    name = (data.get("name") or "").strip().upper()
    if not name:
        return jsonify({"ok": False, "error": "name requerido"}), 400
    cfg_path = PROJECTS_DIR / name / "config.json"
    if not cfg_path.exists():
        return jsonify({"ok": False, "error": f"Proyecto '{name}' no encontrado"}), 404
    cfg = _json.loads(cfg_path.read_text(encoding="utf-8"))
    # Solo actualizamos campos permitidos
    if "display_name" in data:
        cfg["display_name"] = data["display_name"]
    cfg_path.write_text(_json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    return jsonify({"ok": True, "config": cfg})


@app.route("/")
def index():
    return send_from_directory(BASE_DIR, "dashboard.html")


# ── Git diff utilities ────────────────────────────────────────────────────────

def _git_changed_files(workspace_root: str) -> list:
    """
    Retorna lista de strings con los archivos modificados/agregados/eliminados
    respecto al repositorio Git (git status --porcelain).
    """
    try:
        r = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=workspace_root,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=15
        )
        lines = [l for l in r.stdout.splitlines() if l.strip()]
        return lines
    except FileNotFoundError:
        return ["[Git no disponible en PATH]"]
    except subprocess.TimeoutExpired:
        return ["[git status timeout]"]
    except Exception as e:
        return [f"[Error git status: {e}]"]


def _git_diff(workspace_root: str) -> str:
    """
    Retorna el diff completo de todos los cambios no commiteados (git diff + staged).
    Se limita a 500KB.
    """
    try:
        r = subprocess.run(
            ["git", "diff", "HEAD"],
            cwd=workspace_root,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=30
        )
        diff = r.stdout
        MAX = 500 * 1024  # 500 KB
        if len(diff) > MAX:
            diff = diff[:MAX] + "\n\n[... diff truncado a 500KB ...]"
        return diff
    except FileNotFoundError:
        return "[Git no disponible en PATH]"
    except subprocess.TimeoutExpired:
        return "[git diff timeout]"
    except Exception as e:
        return f"[Error git diff: {e}]"


def _save_git_snapshot(folder: str, stage: str, workspace_root: str) -> None:
    """
    Guarda snapshot Git al completar una etapa:
      {folder}/snapshots/{stage}_files.txt  → lista de archivos modificados
      {folder}/snapshots/{stage}_diff.patch → diff completo
    """
    try:
        snap_dir = os.path.join(folder, "snapshots")
        os.makedirs(snap_dir, exist_ok=True)

        files = _git_changed_files(workspace_root)
        diff  = _git_diff(workspace_root)

        with open(os.path.join(snap_dir, f"{stage}_files.txt"), "w", encoding="utf-8") as f:
            f.write(f"# Git status al completar etapa: {stage}\n")
            f.write(f"# Fecha: {datetime.now().isoformat()}\n")
            f.write(f"# Workspace: {workspace_root}\n\n")
            f.write("\n".join(files) if files else "(sin cambios)\n")

        with open(os.path.join(snap_dir, f"{stage}_diff.patch"), "w", encoding="utf-8") as f:
            f.write(f"# Git diff al completar etapa: {stage}\n")
            f.write(f"# Fecha: {datetime.now().isoformat()}\n\n")
            f.write(diff if diff.strip() else "(sin cambios)\n")

        print(f"[GIT] Snapshot guardado — {stage}: {len(files)} archivos modificados")
    except Exception as e:
        print(f"[GIT] Error guardando snapshot de {stage}: {e}", file=sys.stderr)


@app.route("/api/errors")
def api_errors():
    """Retorna las últimas 50 líneas de ERROR/WARNING de los últimos 3 archivos de log."""
    logs_dir = os.path.join(BASE_DIR, "logs")
    errors = []
    try:
        log_files = sorted(Path(logs_dir).glob("*.log"), reverse=True)[:3]
        for logfile in log_files:
            try:
                with open(logfile, encoding="utf-8", errors="replace") as f:
                    for line in f:
                        if "[ERROR]" in line or "[WARNING]" in line or "ERROR" in line.upper():
                            errors.append({"file": logfile.name, "line": line.strip()})
            except Exception:
                pass
    except Exception:
        pass
    return jsonify({"errors": errors[-50:]})


def _push_notification(title: str, message: str, level: str = "info") -> None:
    """Agrega una notificación delegando al notifier centralizado."""
    try:
        from notifier import get_notifier
        get_notifier().send(title, message, level)
    except Exception as e:
        print(f"[NOTIF] Error: {e}", file=sys.stderr)


@app.route("/api/notifications")
def api_notifications():
    """Retorna notificaciones pendientes."""
    try:
        from notifier import NOTIFICATIONS_PATH
        if not os.path.exists(NOTIFICATIONS_PATH):
            return jsonify({"notifications": [], "unread": 0})
        with open(NOTIFICATIONS_PATH, encoding="utf-8") as f:
            entries = json.load(f)
        unread = sum(1 for e in entries if not e.get("read"))
        return jsonify({"notifications": entries[-20:], "unread": unread})
    except Exception as e:
        return jsonify({"notifications": [], "unread": 0, "error": str(e)})


@app.route("/api/notifications/mark_read", methods=["POST"])
def api_notifications_mark_read():
    """Marca todas las notificaciones como leídas."""
    try:
        from notifier import NOTIFICATIONS_PATH
        if os.path.exists(NOTIFICATIONS_PATH):
            with open(NOTIFICATIONS_PATH, encoding="utf-8") as f:
                entries = json.load(f)
            for e in entries:
                e["read"] = True
            with open(NOTIFICATIONS_PATH, "w", encoding="utf-8") as f:
                json.dump(entries, f, indent=2, ensure_ascii=False)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/diff/<ticket_id>/<stage>")
def api_diff(ticket_id: str, stage: str):
    """
    Retorna el diff Git guardado al completar una etapa.
    Si no existe el snapshot guardado, intenta generar el diff on-the-fly desde Git.
    stage: pm | dev | tester  (también acepta sub-stages: pm_inv, dev_impl, qa_arb, etc.)
    """
    # Normalizar sub-stages al stage padre para buscar el snapshot correcto
    _STAGE_NORMALIZE = {
        "pm_inv": "pm", "pm_arq": "pm", "pm_plan": "pm",
        "dev_loc": "dev", "dev_impl": "dev", "dev_doc": "dev",
        "qa_rev": "tester", "qa_exec": "tester", "qa_arb": "tester",
    }
    stage = _STAGE_NORMALIZE.get(stage, stage)
    if stage not in ("pm", "dev", "tester"):
        return jsonify({"ok": False, "error": "stage inválido"}), 400

    rt     = _get_runtime()
    folder = _find_ticket_folder(ticket_id, rt["tickets_base"])
    if not folder:
        return jsonify({"ok": False, "error": "ticket no encontrado"}), 404

    snap_dir   = os.path.join(folder, "snapshots")
    diff_file  = os.path.join(snap_dir, f"{stage}_diff.patch")
    files_file = os.path.join(snap_dir, f"{stage}_files.txt")

    if os.path.exists(diff_file):
        try:
            diff  = open(diff_file,  encoding="utf-8").read()
            files = open(files_file, encoding="utf-8").read() if os.path.exists(files_file) else ""
            return jsonify({"ok": True, "stage": stage, "diff": diff, "files": files,
                            "source": "snapshot"})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    # Fallback 2: GIT_CHANGES.md escrito por el agente DEV (FASE 3)
    git_changes_file = os.path.join(folder, "GIT_CHANGES.md")
    if os.path.exists(git_changes_file):
        try:
            git_md = open(git_changes_file, encoding="utf-8").read()
            # Separar sección de git status y la parte del diff si existe
            diff_section  = ""
            files_section = ""
            in_diff = False
            files_lines = []
            for line in git_md.splitlines():
                if re.match(r'^[MADC?!]\s+', line):
                    files_lines.append(line)
                if line.startswith("Index: ") or line.startswith("---") or in_diff:
                    in_diff = True
                    diff_section += line + "\n"
            files_section = "\n".join(files_lines) if files_lines else git_md[:800]
            if files_section or diff_section:
                return jsonify({"ok": True, "stage": stage,
                                "diff":  diff_section or git_md,
                                "files": files_section,
                                "source": "git_changes_md",
                                "warning": "Leyendo GIT_CHANGES.md generado por el agente DEV"})
        except Exception:
            pass

    # Fallback 3: generar diff on-the-fly desde Git
    try:
        workspace = rt.get("workspace_root", "")
        diff  = _git_diff(workspace)
        files_lines = _git_changed_files(workspace)
        files = "\n".join(files_lines)
        if not diff.strip() and not files:
            return jsonify({"ok": False, "can_capture": True,
                            "error": "No hay snapshot guardado y Git no reporta cambios pendientes"}), 404
        return jsonify({"ok": True, "stage": stage, "diff": diff, "files": files,
                        "source": "live", "warning": "Snapshot no encontrado — mostrando diff Git actual (workspace completo)"})
    except Exception as e:
        return jsonify({"ok": False, "can_capture": True,
                        "error": f"No hay snapshot para {stage} y falló diff on-the-fly: {e}"}), 404


@app.route("/api/capture_snapshot/<ticket_id>/<stage>", methods=["POST"])
def api_capture_snapshot(ticket_id: str, stage: str):
    """
    Genera y guarda manualmente el snapshot Git para una etapa.
    Útil cuando el agente completó pero el watcher no guardó el snapshot automáticamente.
    """
    if stage not in ("pm", "dev", "tester"):
        return jsonify({"ok": False, "error": "stage inválido"}), 400

    rt     = _get_runtime()
    folder = _find_ticket_folder(ticket_id, rt["tickets_base"])
    if not folder:
        return jsonify({"ok": False, "error": "Ticket no encontrado"}), 404

    try:
        _save_git_snapshot(folder, stage, rt["workspace_root"])
        snap_dir  = os.path.join(folder, "snapshots")
        diff_file = os.path.join(snap_dir, f"{stage}_diff.patch")
        lines = 0
        if os.path.exists(diff_file):
            lines = len(open(diff_file, encoding="utf-8").readlines())
        return jsonify({"ok": True, "ticket_id": ticket_id, "stage": stage, "diff_lines": lines})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/pipeline_note/<ticket_id>", methods=["GET", "POST"])
def api_pipeline_note(ticket_id: str):
    """
    GET:  Retorna la nota de contexto pre-pipeline (NOTA_PM.md) si existe.
    POST: Guarda la nota de contexto pre-pipeline en NOTA_PM.md dentro del ticket folder.
          Body: { "note": "texto libre con contexto adicional para el PM" }
    """
    rt     = _get_runtime()
    folder = _find_ticket_folder(ticket_id, rt["tickets_base"])
    if not folder:
        return jsonify({"ok": False, "error": "Ticket no encontrado"}), 404

    note_path = os.path.join(folder, "NOTA_PM.md")

    if request.method == "GET":
        if not os.path.exists(note_path):
            return jsonify({"ok": True, "note": ""})
        try:
            return jsonify({"ok": True, "note": open(note_path, encoding="utf-8").read()})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    # POST
    data = request.json or {}
    note = data.get("note", "").strip()
    try:
        with open(note_path, "w", encoding="utf-8") as f:
            f.write(f"# Nota de contexto pre-pipeline\n\n")
            f.write(f"**Fecha:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write("---\n\n")
            f.write(note)
        return jsonify({"ok": True, "ticket_id": ticket_id, "saved": note_path})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/run_ui_tester/<ticket_id>", methods=["POST"])
def api_run_ui_tester(ticket_id: str):
    """
    Lanza el agente UI Tester (Playwright) para el ticket dado.
    El agente simula al usuario interactuando con la aplicación web usando Playwright.
    Body: { "app_url": "http://...", "notes": "instrucciones adicionales" } (opcionales)
    """
    data    = request.json or {}
    app_url = data.get("app_url", "").strip()
    notes   = data.get("notes", "").strip()

    rt     = _get_runtime()
    folder = _find_ticket_folder(ticket_id, rt["tickets_base"])
    if not folder:
        return jsonify({"ok": False, "error": "Ticket no encontrado"}), 404

    try:
        from prompt_builder import build_ui_tester_prompt
        prompt    = build_ui_tester_prompt(folder, ticket_id, rt["workspace_root"],
                                           app_url=app_url, extra_notes=notes)
        agent     = rt.get("agents", {}).get("ui_tester") or rt.get("agents", {}).get("tester", "QA")

        def _run():
            from pipeline_state import load_state, save_state, set_ticket_state
            from copilot_bridge import invoke_agent
            _rt   = _get_runtime()
            state = load_state(_rt["state_path"])
            # Marcar estado especial para que el dashboard lo muestre
            state.setdefault("tickets", {}).setdefault(ticket_id, {})["ui_tester_at"] = \
                datetime.now().isoformat()
            save_state(_rt["state_path"], state)
            invoke_agent(prompt, agent_name=agent, project_name=_rt["name"],
                         workspace_root=_rt["workspace_root"])

        threading.Thread(target=_run, daemon=True, name=f"ui-tester-{ticket_id}").start()
        return jsonify({"ok": True, "ticket_id": ticket_id, "agent": agent,
                        "msg": "UI Tester lanzado — abrirá VS Code Copilot y ejecutará Playwright"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ── Main ──────────────────────────────────────────────────────────────────────

# ── Timeout config con cache ─────────────────────────────────────────────────
_tconf_cache = {"data": None, "ts": 0.0}

def _get_timeout_config() -> dict:
    """Retorna timeouts por etapa. Cacheado con TTL de 30s."""
    now = _time.monotonic()
    if _tconf_cache["data"] and (now - _tconf_cache["ts"]) < 30.0:
        return _tconf_cache["data"]
    defaults = {"pm": 60, "dev": 120, "tester": 60, "max_retries": 2}
    try:
        from project_manager import get_active_project, get_project_config
        cfg = get_project_config(get_active_project()) or {}
        daemon_cfg = cfg.get("daemon", {})
        result = {
            "pm":          daemon_cfg.get("timeout_pm_minutes",     defaults["pm"]),
            "dev":         daemon_cfg.get("timeout_dev_minutes",    defaults["dev"]),
            "tester":      daemon_cfg.get("timeout_tester_minutes", defaults["tester"]),
            "max_retries": daemon_cfg.get("max_retries_per_stage",  defaults["max_retries"]),
        }
    except Exception:
        result = defaults
    _tconf_cache["data"] = result
    _tconf_cache["ts"]   = now
    return result


# ── Tabla de definición de etapas (elimina la triplicación del watcher) ──────
# Cada entrada: (estado_en_proceso, stage, ok_sentinel, error_flag,
#                completado_state, next_stage, is_final)
_WATCHER_STAGES = [
    {
        "estado":          "pm_en_proceso",
        "stage":           "pm",
        "ok_sentinel":     "PM_COMPLETADO.flag",
        "ok_fallback":     lambda folder: not _has_placeholders(folder),
        "err_flag":        "PM_ERROR.flag",
        "completado_state":"pm_completado",
        "fin_key":         "pm_fin_at",
        "inicio_key":      "pm_inicio_at",
        "next_stage":      "dev",
        "is_final":        False,
    },
    {
        "estado":          "dev_en_proceso",
        "stage":           "dev",
        "ok_sentinel":     "DEV_COMPLETADO.md",
        "ok_fallback":     None,
        "err_flag":        "DEV_ERROR.flag",
        "completado_state":"dev_completado",
        "fin_key":         "dev_fin_at",
        "inicio_key":      "dev_inicio_at",
        "next_stage":      "tester",
        "is_final":        False,
    },
    {
        "estado":          "tester_en_proceso",
        "stage":           "tester",
        "ok_sentinel":     "TESTER_COMPLETADO.md",
        "ok_fallback":     None,
        "err_flag":        "TESTER_ERROR.flag",
        "completado_state":"completado",
        "fin_key":         "tester_fin_at",
        "inicio_key":      "tester_inicio_at",
        "next_stage":      None,
        "is_final":        True,
    },
    # ── Sub-agentes PM ────────────────────────────────────────────────────────
    {
        "estado":          "pm_inv_en_proceso",
        "stage":           "pm_inv",
        "ok_sentinel":     "INV_COMPLETADO.flag",
        "ok_fallback":     None,
        "err_flag":        "PM_ERROR.flag",
        "completado_state":"pm_inv_completado",
        "fin_key":         "pm_inv_fin_at",
        "inicio_key":      "pm_inv_inicio_at",
        "next_stage":      "pm_arq",
        "is_final":        False,
    },
    {
        "estado":          "pm_arq_en_proceso",
        "stage":           "pm_arq",
        "ok_sentinel":     "ARQ_COMPLETADO.flag",
        "ok_fallback":     None,
        "err_flag":        "PM_ERROR.flag",
        "completado_state":"pm_arq_completado",
        "fin_key":         "pm_arq_fin_at",
        "inicio_key":      "pm_arq_inicio_at",
        "next_stage":      "pm_plan",
        "is_final":        False,
    },
    {
        "estado":          "pm_plan_en_proceso",
        "stage":           "pm_plan",
        "ok_sentinel":     "PM_COMPLETADO.flag",
        "ok_fallback":     None,
        "err_flag":        "PM_ERROR.flag",
        "completado_state":"pm_completado",
        "fin_key":         "pm_fin_at",
        "inicio_key":      "pm_plan_inicio_at",
        "next_stage":      "dev_loc",
        "is_final":        False,
    },
    # ── Sub-agentes DEV ───────────────────────────────────────────────────────
    {
        "estado":          "dev_loc_en_proceso",
        "stage":           "dev_loc",
        "ok_sentinel":     "LOC_COMPLETADO.flag",
        "ok_fallback":     None,
        "err_flag":        "DEV_ERROR.flag",
        "completado_state":"dev_loc_completado",
        "fin_key":         "dev_loc_fin_at",
        "inicio_key":      "dev_loc_inicio_at",
        "next_stage":      "dev_impl",
        "is_final":        False,
    },
    {
        "estado":          "dev_impl_en_proceso",
        "stage":           "dev_impl",
        "ok_sentinel":     "IMPL_COMPLETADO.flag",
        "ok_fallback":     None,
        "err_flag":        "DEV_ERROR.flag",
        "completado_state":"dev_impl_completado",
        "fin_key":         "dev_impl_fin_at",
        "inicio_key":      "dev_impl_inicio_at",
        "next_stage":      "dev_doc",
        "is_final":        False,
    },
    {
        "estado":          "dev_doc_en_proceso",
        "stage":           "dev_doc",
        "ok_sentinel":     "DEV_COMPLETADO.md",
        "ok_fallback":     None,
        "err_flag":        "DEV_ERROR.flag",
        "completado_state":"dev_completado",
        "fin_key":         "dev_fin_at",
        "inicio_key":      "dev_doc_inicio_at",
        "next_stage":      "qa_rev",
        "is_final":        False,
    },
    # ── Sub-agentes QA ────────────────────────────────────────────────────────
    {
        "estado":          "qa_rev_en_proceso",
        "stage":           "qa_rev",
        "ok_sentinel":     "REVIEW_COMPLETADO.flag",
        "ok_fallback":     None,
        "err_flag":        "TESTER_ERROR.flag",
        "completado_state":"qa_rev_completado",
        "fin_key":         "qa_rev_fin_at",
        "inicio_key":      "qa_rev_inicio_at",
        "next_stage":      "qa_exec",
        "is_final":        False,
    },
    {
        "estado":          "qa_exec_en_proceso",
        "stage":           "qa_exec",
        "ok_sentinel":     "TEST_COMPLETADO.flag",
        "ok_fallback":     None,
        "err_flag":        "TESTER_ERROR.flag",
        "completado_state":"qa_exec_completado",
        "fin_key":         "qa_exec_fin_at",
        "inicio_key":      "qa_exec_inicio_at",
        "next_stage":      "qa_arb",
        "is_final":        False,
    },
    {
        "estado":          "qa_arb_en_proceso",
        "stage":           "qa_arb",
        "ok_sentinel":     "TESTER_COMPLETADO.md",
        "ok_fallback":     None,
        "err_flag":        "TESTER_ERROR.flag",
        "completado_state":"tester_completado",
        "fin_key":         "tester_fin_at",
        "inicio_key":      "qa_arb_inicio_at",
        "next_stage":      None,
        "is_final":        True,
    },
]

# Set rápido para el pre-filtro del watcher
_EN_PROCESO_STATES = frozenset(s["estado"] for s in _WATCHER_STAGES)
# Lookup rápido estado → stage_def
_STAGE_BY_ESTADO   = {s["estado"]: s for s in _WATCHER_STAGES}

# Estados en los que un ticket del Rally es elegible para arrancar
_RALLY_START_STATES = frozenset((
    "pendiente_pm",
    "pm_completado", "dba_completado", "tl_aprobado", "tl_rechazado",
    "dev_completado",
    "tester_completado",
    "error_pm", "error_dev", "error_tester", "error_dba", "error_doc",
    "qa_rework", "dev_rework_completado",
    "pm_revision", "pm_revision_completado",
))


def _rally_launch_next(triggered_by: str = "") -> str | None:
    """
    Arranca el siguiente ticket del Rally cuando uno termina.

    Gateado por el flag `rally_running` en state.json: si está en False,
    el Rally NO avanza automáticamente aunque haya tickets encolados.
    El flag se activa con POST /api/rally/start y se desactiva al vaciar la cola.

    Busca tickets con `priority < 9999` en estados procesables (no en *_en_proceso),
    los ordena por prioridad (menor = primero) y lanza la etapa que corresponda.
    Respeta los slots del agent_queue si está disponible.

    Devuelve el ticket_id lanzado, o None si no había nadie esperando.
    """
    from pipeline_state import load_state, save_state
    try:
        rt    = _get_runtime()
        state = load_state(rt["state_path"])
    except Exception as e:
        print(f"[RALLY] No se pudo cargar state: {e}", file=sys.stderr, flush=True)
        return None

    if not state.get("rally_running", False):
        print(f"[RALLY] {triggered_by} — Rally pausado (rally_running=false), "
              f"no se lanza próximo ticket", flush=True)
        return None

    stage_map = {
        "pendiente_pm":            "pm",
        "error_pm":                "pm",
        "pm_completado":           "dev",
        "dba_completado":          "dev",
        "tl_aprobado":             "dev",
        "tl_rechazado":            "pm",
        "error_dev":               "dev",
        "dev_completado":          "tester",
        "dev_rework_completado":   "tester",
        "error_tester":            "tester",
        "tester_completado":       "doc",
        "qa_rework":               "dev",
        "pm_revision":             "pm",
        "pm_revision_completado":  "dev",
        "error_dba":               "dba",
        "error_doc":               "doc",
    }

    candidates = []
    for tid, entry in state.get("tickets", {}).items():
        est = entry.get("estado", "")
        if est not in _RALLY_START_STATES:
            continue
        # Saltar los que ya están corriendo alguna etapa
        if est.endswith("_en_proceso"):
            continue
        priority = entry.get("priority")
        if priority is None or priority >= 9999:
            continue
        next_stage = stage_map.get(est)
        if not next_stage:
            continue
        candidates.append((int(priority), tid, next_stage, est))

    if not candidates:
        print(f"[RALLY] {triggered_by} — no hay próximo ticket en el Rally", flush=True)
        # Cola vacía → apagar el flag para que el próximo ticket que se agregue
        # no arranque solo. El usuario debe volver a apretar play explícitamente.
        if state.get("rally_running"):
            state["rally_running"] = False
            try:
                save_state(rt["state_path"], state)
                print("[RALLY] Cola vacía → rally_running=false", flush=True)
                _push_notification("🏁 Rally finalizado",
                                   "Cola vacía — Rally pausado automáticamente", "info")
            except Exception as _e:
                print(f"[RALLY] No se pudo persistir rally_running=false: {_e}",
                      file=sys.stderr, flush=True)
        return None

    candidates.sort(key=lambda x: x[0])
    _, tid, next_stage, est = candidates[0]

    print(f"[RALLY] {triggered_by} → lanzando #{tid} "
          f"(estado={est}, etapa={next_stage})", flush=True)
    _push_notification(
        f"🏁 Rally — arrancando #{tid}",
        f"Ticket anterior finalizó. Lanzando etapa {next_stage.upper()}",
        "info",
    )
    threading.Thread(target=_invoke_stage, args=(tid, next_stage),
                     daemon=True, name=f"rally-next-{tid}").start()
    return tid


def _stage_transition_watcher():
    """
    Hilo background PRINCIPAL — transiciona tickets entre etapas del pipeline.
    Revisa cada 5 segundos los tickets en estado *_en_proceso.
    Tabla-driven: las 3 etapas comparten la misma lógica parametrizada.
    Cada 60 segundos ejecuta un "recovery scan" que ignora la mtime-cache de state.json
    y verifica el filesystem directamente para asegurarse de que ningún ticket quede
    atascado aunque el ciclo normal haya fallado.
    """
    from pipeline_state import (load_state, save_state, set_ticket_state,
                                 mark_error, is_stage_timed_out, get_retry_count)
    import time

    INTERVAL       = 10   # segundos entre ciclos normales
    RECOVERY_EVERY = 60   # segundos entre recovery scans completos
    _last_recovery = 0.0

    while True:
        time.sleep(INTERVAL)
        try:
            rt  = _get_runtime()
            sp  = rt["state_path"]
            now = time.monotonic()

            # ── Recovery scan cada 60s ────────────────────────────────────────
            # Ignora mtime-cache: re-lee state.json desde disco y cruza con filesystem.
            # Detecta tickets cuyo flag ya existe pero el state no fue actualizado.
            if (now - _last_recovery) >= RECOVERY_EVERY:
                _last_recovery = now
                try:
                    # Forzar re-lectura invalidando cache
                    from pipeline_state import _load_cache as _plc
                    _plc["mtime"] = 0.0
                    rec_state   = load_state(sp)
                    rec_changed = False

                    for tid, entry in list(rec_state.get("tickets", {}).items()):
                        est = entry.get("estado", "")
                        if est not in _EN_PROCESO_STATES:
                            continue
                        folder = entry.get("folder") or _find_ticket_folder(tid, rt["tickets_base"])
                        if not folder or not os.path.isdir(folder):
                            continue
                        sdef     = _STAGE_BY_ESTADO[est]
                        ok_path  = os.path.join(folder, sdef["ok_sentinel"])
                        err_path = os.path.join(folder, sdef["err_flag"])

                        if os.path.exists(err_path):
                            try:
                                reason = open(err_path, encoding="utf-8").read().strip()
                            except Exception:
                                reason = sdef["err_flag"]
                            # Eliminar flag de agente en curso — terminó con error (recovery)
                            try:
                                _en_curso = os.path.join(folder, f"{sdef['stage'].upper()}_AGENTE_EN_CURSO.flag")
                                if os.path.exists(_en_curso):
                                    os.remove(_en_curso)
                            except Exception:
                                pass
                            mark_error(rec_state, tid, sdef["stage"], reason)
                            print(f"[RECOVERY] {tid}: {sdef['stage'].upper()}_ERROR — corregido en recovery scan")
                            _release_active_ticket(tid, f"recovery error_{sdef['stage']}")
                            rec_changed = True
                            continue

                        ok = os.path.exists(ok_path)
                        if not ok and sdef["ok_fallback"]:
                            ok = sdef["ok_fallback"](folder)

                        if ok:
                            print(f"[RECOVERY] {tid}: {sdef['stage'].upper()} ya completó (flag existe) "
                                  f"pero estado era '{est}' — corrigiendo")
                            entry[sdef["fin_key"]] = datetime.now().isoformat()
                            # Eliminar flag de agente en curso — la etapa completó (recovery)
                            try:
                                _en_curso = os.path.join(folder, f"{sdef['stage'].upper()}_AGENTE_EN_CURSO.flag")
                                if os.path.exists(_en_curso):
                                    os.remove(_en_curso)
                            except Exception:
                                pass
                            if sdef["is_final"]:
                                set_ticket_state(rec_state, tid, "completado")
                                entry.pop("auto_advance", None)
                                entry["priority"] = 9999   # saca del Rally
                                _release_active_ticket(tid, "pipeline completado (recovery)")
                                _push_notification(f"Ticket #{tid} completado (recovery)",
                                                   "Pipeline finalizado — detectado en recovery scan", "info")
                                threading.Thread(
                                    target=_rally_launch_next,
                                    args=(f"recovery #{tid} completado",),
                                    daemon=True, name=f"rally-kick-{tid}",
                                ).start()
                            else:
                                set_ticket_state(rec_state, tid, sdef["completado_state"])
                            _save_git_snapshot(folder, sdef["stage"], rt["workspace_root"])
                            rec_changed = True

                            if not sdef["is_final"] and sdef["next_stage"]:
                                # PAUSED.flag: no sobrescribir auto_advance ni lanzar siguiente etapa
                                _paused = os.path.exists(os.path.join(folder, "PAUSED.flag"))
                                if _paused:
                                    print(f"[RECOVERY] {tid}: PAUSED.flag presente — no se lanza {sdef['next_stage'].upper()}")
                                else:
                                    # Asegurar auto_advance para que el ciclo normal lo lance
                                    rec_state["tickets"][tid]["auto_advance"] = True
                                    save_state(sp, rec_state)
                                    rec_changed = False
                                    print(f"[RECOVERY] {tid}: auto_advance → lanzando {sdef['next_stage'].upper()}")
                                    _push_notification(f"Ticket #{tid} — {sdef['stage'].upper()} completado (recovery)",
                                                       f"Avanzando a {sdef['next_stage'].upper()}", "info")
                                    threading.Thread(target=_invoke_stage,
                                                     args=(tid, sdef["next_stage"]), daemon=True).start()

                    if rec_changed:
                        save_state(sp, rec_state)

                    # SEQ-03: Stuck detection — solo notifica, NO lanza automáticamente
                    # (eliminado auto-launch para evitar invocaciones duplicadas RC2/RC5)
                    _STUCK_COMPLETADO = {
                        # Pipeline clásico
                        "pm_completado":      "dev",
                        "dev_completado":     "tester",
                        # Sub-agentes PM
                        "pm_inv_completado":  "pm_arq",
                        "pm_arq_completado":  "pm_plan",
                        # Sub-agentes DEV
                        "dev_loc_completado": "dev_impl",
                        "dev_impl_completado":"dev_doc",
                        # Sub-agentes QA
                        "qa_rev_completado":  "qa_exec",
                        "qa_exec_completado": "qa_arb",
                    }
                    # Leer config para ver si stuck_auto_launch está habilitado
                    _stuck_auto_launch = False
                    try:
                        import json as _jcfg
                        _cfg_path = os.path.join(BASE_DIR, "config.json")
                        _cfg_data = _jcfg.load(open(_cfg_path, encoding="utf-8"))
                        _stuck_auto_launch = _cfg_data.get("watcher", {}).get("stuck_auto_launch", False)
                    except Exception:
                        pass

                    try:
                        from pipeline_state import _load_cache as _plc2
                        _plc2["mtime"] = 0.0
                        stuck_state = load_state(sp)
                        for tid, entry in list(stuck_state.get("tickets", {}).items()):
                            est = entry.get("estado", "")
                            if est not in _STUCK_COMPLETADO:
                                continue
                            next_stage = _STUCK_COMPLETADO[est]
                            next_en_proceso = f"{next_stage}_en_proceso"
                            next_completado = f"{next_stage}_completado"
                            if entry.get(f"{next_en_proceso}_at") or entry.get(f"{next_completado}_at"):
                                continue
                            _stuck_folder = entry.get("folder") or _find_ticket_folder(tid, rt["tickets_base"])
                            if _stuck_folder:
                                _ec_path = os.path.join(_stuck_folder,
                                                        f"{next_stage.upper()}_AGENTE_EN_CURSO.flag")
                                if os.path.exists(_ec_path):
                                    continue

                            if _stuck_auto_launch:
                                # SEQ-06: Respetar auto_advance=False — usuario tiene control manual
                                if entry.get("auto_advance") is False:
                                    continue  # Usuario hizo set_state manual, no auto-avanzar
                                # Auto-launch habilitado en config (no recomendado en producción)
                                stuck_state["tickets"][tid]["auto_advance"] = True
                                save_state(sp, stuck_state)
                                print(f"[RECOVERY-STUCK] {tid}: atascado en '{est}' → lanzando {next_stage.upper()} (auto_launch=true)",
                                      file=sys.stderr)
                                _push_notification(
                                    f"Ticket #{tid} — recovery automático",
                                    f"Detectado atascado en '{est}' → lanzando {next_stage.upper()}", "warning")
                                threading.Thread(target=_invoke_stage,
                                                 args=(tid, next_stage), daemon=True).start()
                            else:
                                # Solo notificar (default — SEQ-03)
                                print(f"[RECOVERY-STUCK] {tid}: atascado en '{est}' hace tiempo "
                                      f"— notificando (auto_launch deshabilitado). "
                                      f"Usar dashboard o POST /api/run_pipeline para avanzar.",
                                      file=sys.stderr)
                                _push_notification(
                                    f"Ticket #{tid} — stuck en {est}",
                                    f"Requiere intervención manual. Clic en 'Ejecutar' para avanzar a {next_stage.upper()}.",
                                    "warning")
                    except Exception as stuck_exc:
                        print(f"[RECOVERY-STUCK] Error: {stuck_exc}", file=sys.stderr)

                except Exception as rec_exc:
                    print(f"[RECOVERY] Error en recovery scan: {rec_exc}", file=sys.stderr)

            # ── Ciclo normal (cada 5s) ────────────────────────────────────────
            state   = load_state(sp)  # usa mtime-cache interno
            changed = False
            tconf   = _get_timeout_config()

            # Release oportunista del gate global: si el ticket activo quedó
            # en estado terminal, libera para que otro ticket pueda arrancar.
            _active_tid = _get_active_ticket()
            if _active_tid:
                _active_est = state.get("tickets", {}).get(_active_tid, {}).get("estado", "")
                _maybe_release_if_terminal(_active_tid, _active_est)

            # Pre-filtrar: solo iterar tickets en *_en_proceso (usualmente 0-2)
            in_process = [
                (tid, entry) for tid, entry in state.get("tickets", {}).items()
                if entry.get("estado", "") in _EN_PROCESO_STATES
            ]
            if not in_process:
                continue

            for tid, entry in in_process:
                # SEQ-04: Cooldown post-set_state manual
                _last_manual = _manual_set_timestamps.get(tid, 0)
                if time.time() - _last_manual < _MANUAL_SET_COOLDOWN_SECONDS:
                    continue  # El usuario acaba de hacer un set_state manual, esperar

                est    = entry["estado"]
                folder = entry.get("folder") or _find_ticket_folder(tid, rt["tickets_base"])
                if not folder or not os.path.isdir(folder):
                    continue

                sdef  = _STAGE_BY_ESTADO[est]
                stage = sdef["stage"]

                err_path = os.path.join(folder, sdef["err_flag"])
                ok_path  = os.path.join(folder, sdef["ok_sentinel"])

                # 1. Error flag?
                if os.path.exists(err_path):
                    try:
                        reason = open(err_path, encoding="utf-8").read().strip()
                    except Exception:
                        reason = sdef["err_flag"]
                    # Eliminar flag de agente en curso — terminó con error
                    try:
                        _en_curso = os.path.join(folder, f"{stage.upper()}_AGENTE_EN_CURSO.flag")
                        if os.path.exists(_en_curso):
                            os.remove(_en_curso)
                    except Exception:
                        pass
                    mark_error(state, tid, stage, reason)
                    print(f"[WATCHER] {tid}: {stage.upper()}_ERROR detectado")
                    _release_active_ticket(tid, f"error_{stage}")
                    changed = True
                    continue

                # 2. Completado?
                ok = os.path.exists(ok_path)
                if not ok and sdef["ok_fallback"]:
                    ok = sdef["ok_fallback"](folder)

                if ok:
                    entry[sdef["fin_key"]] = datetime.now().isoformat()
                    # Eliminar flag de agente en curso — la etapa completó exitosamente
                    try:
                        _en_curso = os.path.join(folder, f"{stage.upper()}_AGENTE_EN_CURSO.flag")
                        if os.path.exists(_en_curso):
                            os.remove(_en_curso)
                    except Exception:
                        pass
                    # ── Bifurcación por veredicto QA ────────────────────────────────
                    # Política actual (pedido del usuario):
                    #   APROBADO          → completado (sigue con el próximo ticket)
                    #   CON OBSERVACIONES → se acepta como OK; las observaciones quedan
                    #                       registradas en TESTER_COMPLETADO.md pero no
                    #                       bloquean el pipeline. Va directo a completado.
                    #   RECHAZADO         → bifurca a pm_revision (requiere replanteo).
                    # Sin este check, RECHAZADO quedaba enmascarado como "completado"
                    # porque tester está marcado is_final=True.
                    if stage == "tester":
                        try:
                            from pipeline_runner import _parse_qa_verdict
                            _verdict, _findings = _parse_qa_verdict(folder)
                        except Exception:
                            _verdict, _findings = "DESCONOCIDO", []
                        entry["last_qa_verdict"] = _verdict
                        entry["qa_findings"]     = _findings
                        if _verdict == "RECHAZADO":
                            set_ticket_state(state, tid, "pm_revision")
                            entry.pop("auto_advance", None)
                            _push_notification(
                                f"⛔ Ticket #{tid} — QA RECHAZADO",
                                f"Bifurcación: pm_revision "
                                f"({len(_findings)} finding{'s' if len(_findings)!=1 else ''})",
                                "error",
                            )
                            print(f"[WATCHER] {tid}: QA RECHAZADO → pm_revision")
                            _release_active_ticket(tid, "pm_revision (QA rechazó)")
                            changed = True
                            continue
                        if _verdict == "CON OBSERVACIONES":
                            print(f"[WATCHER] {tid}: QA CON OBSERVACIONES → aceptado como OK "
                                  f"({len(_findings)} observacion{'es' if len(_findings)!=1 else ''})")
                    if sdef["is_final"]:
                        set_ticket_state(state, tid, "completado")
                        entry.pop("auto_advance", None)
                        entry["priority"] = 9999   # saca del Rally
                        _release_active_ticket(tid, "pipeline completado")
                        _push_notification(f"Ticket #{tid} completado",
                                           "Pipeline PM→Dev→QA finalizado exitosamente", "info")
                        threading.Thread(
                            target=_rally_launch_next,
                            args=(f"watcher #{tid} completado",),
                            daemon=True, name=f"rally-kick-{tid}",
                        ).start()
                    else:
                        set_ticket_state(state, tid, sdef["completado_state"])
                    _save_git_snapshot(folder, stage, rt["workspace_root"])
                    print(f"[WATCHER] {tid}: {stage.upper()} completado automaticamente")
                    changed = True

                    if not sdef["is_final"] and entry.get("auto_advance") and sdef["next_stage"]:
                        # PAUSED.flag: detener auto-avance
                        if os.path.exists(os.path.join(folder, "PAUSED.flag")):
                            print(f"[WATCHER] {tid}: PAUSED.flag presente — no se avanza a {sdef['next_stage'].upper()}")
                            save_state(rt["state_path"], state)
                            changed = False
                            continue
                        save_state(rt["state_path"], state)
                        changed = False
                        print(f"[WATCHER] {tid}: auto_advance → invocando {sdef['next_stage'].upper()}")
                        _push_notification(f"Ticket #{tid} — {stage.upper()} completado",
                                           f"Avanzando a {sdef['next_stage'].upper()} automáticamente", "info")
                        threading.Thread(target=_invoke_stage,
                                         args=(tid, sdef["next_stage"]), daemon=True).start()
                    continue

                # 3. Timeout?
                if is_stage_timed_out(state, tid, stage, tconf[stage]):
                    retries = get_retry_count(state, tid, stage)
                    if retries < tconf["max_retries"]:
                        # Respetar el gate global: si otro ticket tiene el gate,
                        # este ticket no puede correr aunque el timer haya expirado.
                        # No reseteamos inicio_key ni contamos reintento: volverá a
                        # intentarse en el próximo tick cuando el gate esté libre.
                        _gate_owner = _get_active_ticket()
                        if _gate_owner and _gate_owner != tid:
                            print(f"[WATCHER] {tid}: timeout {stage.upper()} pero gate "
                                  f"ocupado por #{_gate_owner} — posponiendo reintento")
                            continue
                        print(f"[WATCHER] {tid}: {stage.upper()} timeout ({tconf[stage]}min)"
                              f" — reintento {retries+1}/{tconf['max_retries']}")
                        entry[sdef["inicio_key"]] = datetime.now().isoformat()
                        save_state(rt["state_path"], state)
                        changed = False
                        threading.Thread(target=_invoke_stage,
                                         args=(tid, stage), daemon=True).start()
                        # Budget 1 por tick: si disparamos un reintento, no
                        # arrancamos otro en la misma iteración.
                        break
                    else:
                        reason = f"Timeout después de {tconf[stage]} min — {retries} reintentos agotados"
                        mark_error(state, tid, stage, reason)
                        _push_notification(f"Acción requerida — #{tid}", reason, "error")
                        print(f"[WATCHER] {tid}: {stage.upper()} timeout agotado → error")
                        _release_active_ticket(tid, f"timeout {stage}")
                        changed = True

            if changed:
                save_state(rt["state_path"], state)

        except Exception as exc:
            print(f"[WATCHER] Error: {exc}", file=sys.stderr)


# ── E-10: API v1 — Pipeline como API REST ────────────────────────────────────

@app.route("/api/v1/status", methods=["GET"])
def api_v1_status():
    """Estado global del pipeline."""
    rt    = _get_runtime()
    state = _load_pipeline_state()
    tickets = state.get("tickets", {})
    by_state: dict = {}
    for tid, t in tickets.items():
        s = t.get("estado", "desconocido")
        by_state.setdefault(s, []).append(tid)
    return jsonify({
        "project": rt["name"],
        "tickets_total": len(tickets),
        "by_state": by_state,
        "timestamp": datetime.now().isoformat(),
    })


@app.route("/api/v1/tickets", methods=["GET"])
def api_v1_tickets():
    """Lista todos los tickets con su estado."""
    state   = _load_pipeline_state()
    tickets = []
    for tid, t in state.get("tickets", {}).items():
        tickets.append({
            "ticket_id": tid,
            "estado":    t.get("estado"),
            "priority":  t.get("priority", 5),
            "error":     t.get("error"),
        })
    # Ordenar por prioridad
    tickets.sort(key=lambda x: x["priority"])
    return jsonify({"tickets": tickets, "count": len(tickets)})


@app.route("/api/v1/sessions", methods=["GET"])
def api_v1_sessions():
    """Estado de las sesiones de chat concurrentes."""
    try:
        from chat_session_manager import get_session_manager
        mgr = get_session_manager()
        return jsonify(mgr.status())
    except ImportError:
        return jsonify({"error": "chat_session_manager not available"}), 501
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Auto Enter Daemon ─────────────────────────────────────────────────────────

@app.route("/api/auto_enter/status", methods=["GET"])
def api_auto_enter_status():
    """Estado actual del daemon Ctrl+Enter."""
    try:
        from auto_enter_daemon import get_auto_enter_daemon
        return jsonify(get_auto_enter_daemon().status())
    except ImportError:
        return jsonify({"error": "auto_enter_daemon not available"}), 501


@app.route("/api/auto_enter/enable", methods=["POST"])
def api_auto_enter_enable():
    """Activa el daemon. Body opcional: {"interval_seconds": 15}"""
    try:
        from auto_enter_daemon import get_auto_enter_daemon
        data = {}
        if request.is_json and request.data:
            try:
                data = request.get_json(silent=True) or {}
            except Exception:
                data = {}
        interval = int(data.get("interval_seconds", 15))
        if interval <= 0:
            return jsonify({"ok": False, "error": "interval_seconds debe ser > 0"}), 400
        daemon = get_auto_enter_daemon()
        daemon.start(interval_seconds=interval)
        return jsonify({"ok": True, "enabled": True, "interval_seconds": daemon.interval})
    except ImportError:
        return jsonify({"ok": False, "error": "auto_enter_daemon not available"}), 501
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/auto_enter/disable", methods=["POST"])
def api_auto_enter_disable():
    """Desactiva el daemon."""
    try:
        from auto_enter_daemon import get_auto_enter_daemon
        get_auto_enter_daemon().stop()
        return jsonify({"ok": True, "enabled": False})
    except ImportError:
        return jsonify({"ok": False, "error": "auto_enter_daemon not available"}), 501
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/auto_enter/configure", methods=["POST"])
def api_auto_enter_configure():
    """Cambia el intervalo sin detener el daemon. Body: {"interval_seconds": N}"""
    try:
        from auto_enter_daemon import get_auto_enter_daemon
        data = request.get_json(silent=True) or {}
        interval = int(data.get("interval_seconds", 0))
        if interval <= 0:
            return jsonify({"ok": False, "error": "interval_seconds requerido y > 0"}), 400
        daemon = get_auto_enter_daemon()
        daemon.configure(interval_seconds=interval)
        return jsonify({"ok": True, "interval_seconds": daemon.interval, "enabled": daemon.enabled})
    except ImportError:
        return jsonify({"ok": False, "error": "auto_enter_daemon not available"}), 501
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/auto_enter/health", methods=["GET"])
def api_auto_enter_health():
    """Health extendido: thread_alive, bridge_up, dry_run, stalled, panic."""
    try:
        from auto_enter_daemon import get_auto_enter_daemon
        return jsonify(get_auto_enter_daemon().health())
    except ImportError:
        return jsonify({"error": "auto_enter_daemon not available"}), 501
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/auto_enter/panic", methods=["POST"])
def api_auto_enter_panic():
    """Kill-switch: desactiva el daemon y marca panic_active=True."""
    try:
        from auto_enter_daemon import get_auto_enter_daemon
        data = request.get_json(silent=True) or {}
        reason = (data.get("reason") or "manual").strip() or "manual"
        return jsonify(get_auto_enter_daemon().trigger_panic(reason=reason))
    except ImportError:
        return jsonify({"ok": False, "error": "auto_enter_daemon not available"}), 501
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/auto_enter/panic/reset", methods=["POST"])
def api_auto_enter_panic_reset():
    """Limpia el panic_active y restaura el estado previo del daemon."""
    try:
        from auto_enter_daemon import get_auto_enter_daemon
        return jsonify(get_auto_enter_daemon().reset_panic())
    except ImportError:
        return jsonify({"ok": False, "error": "auto_enter_daemon not available"}), 501
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/v1/tickets/<ticket_id>", methods=["GET"])
def api_v1_ticket_detail(ticket_id):
    """Detalle de un ticket específico."""
    state = _load_pipeline_state()
    t     = state.get("tickets", {}).get(ticket_id)
    if not t:
        return jsonify({"error": "Ticket no encontrado"}), 404

    rt     = _get_runtime()
    folder = _find_ticket_folder(ticket_id, rt["tickets_base"])
    files  = []
    if folder and os.path.isdir(folder):
        files = [f for f in os.listdir(folder) if not f.startswith(".")]

    return jsonify({
        "ticket_id": ticket_id,
        "state":     t,
        "folder":    folder or "",
        "files":     files,
    })


@app.route("/api/v1/tickets/<ticket_id>/advance", methods=["POST"])
def api_v1_advance_ticket(ticket_id):
    """Fuerza el avance de un ticket a la siguiente etapa."""
    try:
        from pipeline_state import load_state, save_state, set_ticket_state
        rt    = _get_runtime()
        state = load_state(rt["state_path"])
        t     = state.get("tickets", {}).get(ticket_id, {})
        est   = t.get("estado", "pendiente_pm")

        stage_map = {"pendiente_pm": "pm_en_proceso",
                     "pm_completado": "dev_en_proceso",
                     "dev_completado": "tester_en_proceso"}
        new_state = stage_map.get(est)
        if not new_state:
            return jsonify({"error": f"No se puede avanzar desde estado '{est}'"}), 400

        set_ticket_state(state, ticket_id, new_state)
        save_state(rt["state_path"], state)
        return jsonify({"ticket_id": ticket_id, "new_state": new_state})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/v1/metrics", methods=["GET"])
def api_v1_metrics():
    """Métricas de calidad del pipeline (N-08)."""
    rt   = _get_runtime()
    days = request.args.get("days", 7, type=int)
    try:
        from metrics_collector import get_metrics_collector
        mc = get_metrics_collector(rt["name"])
        return jsonify(mc.get_dashboard_metrics(days=days))
    except ImportError:
        return jsonify({"error": "metrics_collector no disponible"}), 503


@app.route("/api/v1/kb/search", methods=["GET"])
def api_v1_kb_search():
    """Busca en la Knowledge Base (E-01)."""
    query = request.args.get("q", "")
    k     = request.args.get("k", 3, type=int)
    if not query:
        return jsonify({"error": "Parámetro 'q' requerido"}), 400
    rt = _get_runtime()
    try:
        from knowledge_base import get_kb
        kb      = get_kb(rt["tickets_base"], rt["name"])
        results = kb.search(query, k=k)
        return jsonify({"results": results, "query": query})
    except ImportError:
        return jsonify({"error": "knowledge_base no disponible"}), 503


@app.route("/api/v1/kb/rebuild", methods=["POST"])
def api_v1_kb_rebuild():
    """Reconstruye el índice de la Knowledge Base."""
    rt = _get_runtime()
    try:
        from knowledge_base import get_kb
        kb    = get_kb(rt["tickets_base"], rt["name"])
        count = kb.rebuild_index()
        return jsonify({"indexed": count, "project": rt["name"]})
    except ImportError:
        return jsonify({"error": "knowledge_base no disponible"}), 503


@app.route("/api/v1/predict", methods=["POST"])
def api_v1_predict():
    """Predice atributos de un ticket (G-10)."""
    data        = request.get_json() or {}
    inc_content = data.get("inc_content", "")
    if not inc_content:
        return jsonify({"error": "Campo 'inc_content' requerido"}), 400
    rt = _get_runtime()
    try:
        from predictor import get_predictor
        pred   = get_predictor(rt["name"])
        result = pred.predict(inc_content)
        return jsonify(result)
    except ImportError:
        return jsonify({"error": "predictor no disponible"}), 503


@app.route("/api/v1/shadow", methods=["GET", "POST"])
def api_v1_shadow():
    """GET: estado shadow mode. POST: activar/desactivar."""
    rt = _get_runtime()
    try:
        from shadow_mode import get_shadow_mode
        sm = get_shadow_mode(rt["name"])
        if request.method == "GET":
            return jsonify({"enabled": sm.is_enabled(), "summary": sm.get_shadow_summary()})
        action = (request.get_json() or {}).get("action", "")
        if action == "enable":
            sm.enable()
        elif action == "disable":
            sm.disable()
        return jsonify({"enabled": sm.is_enabled()})
    except ImportError:
        return jsonify({"error": "shadow_mode no disponible"}), 503


@app.route("/api/v1/autonomy", methods=["GET", "POST"])
def api_v1_autonomy():
    """GET: nivel de autonomía. POST: cambiar nivel."""
    rt = _get_runtime()
    try:
        from autonomy_controller import AutonomyController, AutonomyLevel
        ac = AutonomyController(rt["name"])
        if request.method == "GET":
            return jsonify(ac.get_status())
        data  = request.get_json() or {}
        level = data.get("level", "guided")
        ac.set_level(AutonomyLevel(level))
        return jsonify(ac.get_status())
    except ImportError:
        return jsonify({"error": "autonomy_controller no disponible"}), 503
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/v1/autonomy/approve", methods=["POST"])
def api_v1_approve():
    """Aprueba una etapa pendiente de un ticket."""
    data      = request.get_json() or {}
    ticket_id = data.get("ticket_id", "")
    stage     = data.get("stage", "")
    if not ticket_id or not stage:
        return jsonify({"error": "ticket_id y stage requeridos"}), 400
    rt = _get_runtime()
    try:
        from autonomy_controller import AutonomyController
        ac = AutonomyController(rt["name"])
        ac.approve(ticket_id, stage)
        return jsonify({"approved": True, "ticket_id": ticket_id, "stage": stage})
    except ImportError:
        return jsonify({"error": "autonomy_controller no disponible"}), 503


@app.route("/api/v1/meta_analysis", methods=["GET", "POST"])
def api_v1_meta_analysis():
    """GET: último meta-análisis. POST: ejecutar nuevo análisis."""
    rt = _get_runtime()
    try:
        from meta_analyst import MetaAnalyst
        ma = MetaAnalyst(rt["tickets_base"], rt["name"])
        if request.method == "GET":
            insights = ma.get_last_insights()
            if not insights:
                return jsonify({"error": "Sin análisis previo — ejecutar POST primero"}), 404
            return jsonify(insights)
        # POST — ejecutar análisis en background
        days = (request.get_json() or {}).get("days", 30)
        def _run():
            ma.run_analysis(days=days)
        threading.Thread(target=_run, daemon=True, name="meta-analysis").start()
        return jsonify({"status": "started", "days": days})
    except ImportError:
        return jsonify({"error": "meta_analyst no disponible"}), 503


@app.route("/api/v1/learn", methods=["GET", "POST"])
def api_v1_learn():
    """E-11: GET: estado del aprendizaje. POST: lanzar fase de aprendizaje."""
    rt = _get_runtime()
    try:
        from project_learner import ProjectLearner
        pl = ProjectLearner(rt["name"], rt["workspace_root"])
        if request.method == "GET":
            return jsonify(pl.get_status())
        phases = (request.get_json() or {}).get("phases")
        def _run():
            pl.run_learning_phase(phases=phases)
        threading.Thread(target=_run, daemon=True, name="project-learner").start()
        return jsonify({"status": "started", "phases": phases or [1, 2, 3, 4]})
    except ImportError:
        return jsonify({"error": "project_learner no disponible"}), 503


@app.route("/api/v1/codebase/search", methods=["GET"])
def api_v1_codebase_search():
    """G-02: Búsqueda semántica en el codebase."""
    query = request.args.get("q", "")
    k     = request.args.get("k", 5, type=int)
    if not query:
        return jsonify({"error": "Parámetro 'q' requerido"}), 400
    rt = _get_runtime()
    try:
        from codebase_indexer import get_codebase_indexer
        idx     = get_codebase_indexer(rt["workspace_root"], rt["name"])
        results = idx.search(query, top_k=k)
        return jsonify({"results": results, "query": query,
                        "stats": idx.get_stats()})
    except ImportError:
        return jsonify({"error": "codebase_indexer no disponible"}), 503


@app.route("/api/v1/codebase/index", methods=["POST"])
def api_v1_codebase_index():
    """Reconstruye el índice del codebase en background."""
    rt = _get_runtime()
    try:
        from codebase_indexer import get_codebase_indexer
        idx = get_codebase_indexer(rt["workspace_root"], rt["name"])
        idx.build_index_async()
        return jsonify({"status": "indexing_started"})
    except ImportError:
        return jsonify({"error": "codebase_indexer no disponible"}), 503


@app.route("/api/v1/prompts/evolution", methods=["GET"])
def api_v1_prompt_evolution():
    """E-04: Reporte de evolución de prompts."""
    rt = _get_runtime()
    try:
        from prompt_tracker import get_prompt_tracker
        pt = get_prompt_tracker(rt["name"])
        return jsonify({"report": pt.get_evolution_report(),
                        "stats":  pt.get_stats()})
    except ImportError:
        return jsonify({"error": "prompt_tracker no disponible"}), 503


# ── G-07: Chat Conversacional con Stacky ─────────────────────────────────────

_chat_history: list[dict] = []
_CHAT_MAX_HISTORY = 50


@app.route("/api/v1/chat", methods=["POST"])
def api_v1_chat():
    """
    G-07: Interfaz conversacional con Stacky.
    Permite consultar el estado del pipeline, buscar tickets, obtener métricas,
    y ejecutar acciones mediante lenguaje natural.
    """
    data    = request.get_json() or {}
    message = data.get("message", "").strip()
    if not message:
        return jsonify({"error": "Campo 'message' requerido"}), 400

    rt      = _get_runtime()
    response = _process_chat_message(message, rt)

    # Guardar en historial
    _chat_history.append({
        "role":      "user",
        "content":   message,
        "ts":        datetime.now().isoformat(),
    })
    _chat_history.append({
        "role":      "assistant",
        "content":   response,
        "ts":        datetime.now().isoformat(),
    })
    # Mantener límite
    if len(_chat_history) > _CHAT_MAX_HISTORY * 2:
        del _chat_history[:_CHAT_MAX_HISTORY]

    return jsonify({"response": response, "history_length": len(_chat_history)})


@app.route("/api/v1/chat/history", methods=["GET"])
def api_v1_chat_history():
    """Retorna el historial del chat."""
    return jsonify({"history": _chat_history[-20:]})


@app.route("/api/v1/chat/clear", methods=["POST"])
def api_v1_chat_clear():
    """Limpia el historial del chat."""
    _chat_history.clear()
    return jsonify({"cleared": True})


def _process_chat_message(message: str, rt: dict) -> str:
    """
    Procesa un mensaje del chat y retorna la respuesta.
    Motor de reglas NL → acción del pipeline.
    """
    import re
    msg_lower = message.lower()

    # Estado general
    if any(kw in msg_lower for kw in ["estado", "status", "cómo va", "como va", "resumen"]):
        state   = _load_pipeline_state()
        tickets = state.get("tickets", {})
        by_s: dict = {}
        for t in tickets.values():
            s = t.get("estado", "?")
            by_s[s] = by_s.get(s, 0) + 1
        parts = [f"{s}: {n}" for s, n in sorted(by_s.items())]
        return (f"Pipeline {rt['name']} — {len(tickets)} tickets activos.\n"
                + "\n".join(parts) if parts else "Sin tickets en pipeline.")

    # Buscar ticket específico
    m = re.search(r'#?(\d{4,6})', message)
    if m and any(kw in msg_lower for kw in ["ticket", "inc", "bug", "estado de"]):
        tid   = m.group(1)
        state = _load_pipeline_state()
        t     = state.get("tickets", {}).get(tid)
        if t:
            return (f"Ticket #{tid}: estado={t.get('estado', '?')}, "
                    f"prioridad={t.get('priority', 5)}, "
                    f"error={t.get('error', 'ninguno')}")
        return f"Ticket #{tid} no encontrado en el pipeline."

    # Métricas
    if any(kw in msg_lower for kw in ["métricas", "metricas", "calidad", "rework", "éxito", "exito"]):
        try:
            from metrics_collector import get_metrics_collector
            mc = get_metrics_collector(rt["name"])
            return mc.format_metrics_summary(days=7)
        except ImportError:
            return "Módulo de métricas no disponible."

    # Shadow mode
    if "shadow" in msg_lower:
        try:
            from shadow_mode import get_shadow_mode
            sm = get_shadow_mode(rt["name"])
            if "activar" in msg_lower or "habilitar" in msg_lower or "enable" in msg_lower:
                sm.enable()
                return "Shadow mode ACTIVADO — DEV solo describirá cambios a partir de ahora."
            if "desactivar" in msg_lower or "deshabilitar" in msg_lower or "disable" in msg_lower:
                sm.disable()
                return "Shadow mode DESACTIVADO — pipeline operando normalmente."
            return sm.get_shadow_summary()
        except ImportError:
            return "Módulo shadow mode no disponible."

    # Meta-análisis
    if any(kw in msg_lower for kw in ["meta", "análisis sistémico", "tendencias", "patrones recurrentes"]):
        try:
            from meta_analyst import MetaAnalyst
            ma       = MetaAnalyst(rt["tickets_base"], rt["name"])
            insights = ma.get_last_insights()
            if not insights:
                return ("Sin meta-análisis previo. "
                        "Ejecutar POST /api/v1/meta_analysis para generarlo.")
            tc  = insights.get("ticket_count", 0)
            qa  = insights.get("insights", {}).get("qa_rejection_causes", {})
            rw  = qa.get("rework_rate", 0)
            return (f"Último análisis: {tc} tickets, "
                    f"tasa rework {rw:.0%}. "
                    f"Ver /api/v1/meta_analysis para detalles completos.")
        except ImportError:
            return "Meta-analyst no disponible."

    # Búsqueda KB
    if any(kw in msg_lower for kw in ["buscar", "similar", "parecido", "conoce"]):
        query = message
        try:
            from knowledge_base import get_kb
            kb      = get_kb(rt["tickets_base"], rt["name"])
            results = kb.search(query, k=3)
            if not results:
                return "No encontré tickets similares en la Knowledge Base."
            parts = [f"#{r['ticket_id']} ({r['score']:.0%}): {r.get('title', '')[:60]}"
                     for r in results]
            return "Tickets similares encontrados:\n" + "\n".join(parts)
        except ImportError:
            return "Knowledge Base no disponible."

    # Ayuda / comandos
    if any(kw in msg_lower for kw in ["ayuda", "help", "qué puedes", "que puedes", "comandos"]):
        return """Comandos disponibles:
- "estado" — resumen del pipeline
- "ticket #XXXX" — estado de un ticket específico
- "métricas" — tasa de éxito por agente
- "shadow activar/desactivar" — toggle shadow mode
- "buscar [texto]" — busca tickets similares en KB
- "análisis sistémico" — tendencias y patrones
- "meta-análisis" — insights del proyecto"""

    # Respuesta por defecto
    return (f"No entendí bien la consulta. "
            f"Escribe 'ayuda' para ver los comandos disponibles. "
            f"Mensaje recibido: '{message[:80]}'")


def _find_ticket_folder(ticket_id: str, tickets_base: str = None) -> str | None:
    """Busca la carpeta de un ticket por su ID."""
    if tickets_base is None:
        tickets_base = _get_runtime().get("tickets_base", TICKETS_BASE)
    for estado in os.listdir(tickets_base) if os.path.isdir(tickets_base) else []:
        candidate = os.path.join(tickets_base, estado, ticket_id)
        if os.path.isdir(candidate):
            return candidate
    return None


# ── E-08: Dashboard interactivo — endpoints adicionales ───────────────────────

@app.route("/api/v1/queue", methods=["GET"])
def api_v1_queue():
    """Estado de la cola de agentes (M-06)."""
    try:
        from agent_queue import get_agent_queue
        aq = get_agent_queue()
        return jsonify(aq.get_status())
    except ImportError:
        return jsonify({"error": "agent_queue no disponible"}), 503


@app.route("/api/v1/blast_radius/<ticket_id>", methods=["GET", "POST"])
def api_v1_blast_radius(ticket_id):
    """
    GET: retorna BLAST_RADIUS.md si existe.
    POST: ejecuta análisis de blast radius.
    """
    rt     = _get_runtime()
    folder = _find_ticket_folder(ticket_id, rt["tickets_base"])
    if not folder:
        return jsonify({"error": "Ticket no encontrado"}), 404

    if request.method == "GET":
        br_path = os.path.join(folder, "BLAST_RADIUS.md")
        if not os.path.exists(br_path):
            return jsonify({"error": "BLAST_RADIUS.md no existe aún"}), 404
        content = Path(br_path).read_text(encoding="utf-8", errors="replace")
        return jsonify({"ticket_id": ticket_id, "content": content})

    # POST — ejecutar análisis
    try:
        from blast_radius_analyzer import analyze_blast_radius
        def _run():
            analyze_blast_radius(folder, ticket_id, rt["workspace_root"])
        threading.Thread(target=_run, daemon=True).start()
        return jsonify({"status": "analysis_started", "ticket_id": ticket_id})
    except ImportError:
        return jsonify({"error": "blast_radius_analyzer no disponible"}), 503


@app.route("/api/v1/rollback/<ticket_id>", methods=["GET", "POST"])
def api_v1_rollback(ticket_id):
    """
    GET: retorna ROLLBACK_PLAN.md si existe.
    POST: genera plan de rollback.
    """
    rt     = _get_runtime()
    folder = _find_ticket_folder(ticket_id, rt["tickets_base"])
    if not folder:
        return jsonify({"error": "Ticket no encontrado"}), 404

    if request.method == "GET":
        plan_path = os.path.join(folder, "ROLLBACK_PLAN.md")
        if not os.path.exists(plan_path):
            return jsonify({"error": "ROLLBACK_PLAN.md no existe aún"}), 404
        content = Path(plan_path).read_text(encoding="utf-8", errors="replace")
        return jsonify({"ticket_id": ticket_id, "content": content})

    try:
        from rollback_assistant import generate_rollback_plan
        revision = (request.get_json() or {}).get("revision", "")
        ok = generate_rollback_plan(ticket_id, folder, rt["workspace_root"], revision)
        return jsonify({"generated": ok, "ticket_id": ticket_id})
    except ImportError:
        return jsonify({"error": "rollback_assistant no disponible"}), 503


# ── Git Commit ────────────────────────────────────────────────────────────────

@app.route("/api/git_commit_message/<ticket_id>", methods=["GET"])
def api_git_commit_message(ticket_id: str):
    """Genera un mensaje de commit propuesto para el ticket."""
    folder = _find_ticket_folder(ticket_id)
    if not folder:
        return jsonify({"ok": False, "error": "Ticket no encontrado"}), 404
    try:
        from commit_generator import generate_commit_message
        rt = _get_runtime()
        msg_path = generate_commit_message(folder, ticket_id, rt.get("name", ""))
        if not msg_path:
            return jsonify({
                "ok": False,
                "error": "No se pudo generar el mensaje (faltan INC-*.md o DEV_COMPLETADO.md)",
            }), 500
        from pathlib import Path as _Path
        msg = _Path(msg_path).read_text(encoding="utf-8")
        return jsonify({"ok": True, "message": msg, "ticket_id": ticket_id})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/git_status", methods=["GET"])
def api_git_status():
    """Devuelve la lista de archivos modificados/untracked en el workspace.

    Query params:
      ?ticket=<id>  → incluye `ticket_files` con los paths que el ticket
                      declara haber modificado (extraídos de DEV_COMPLETADO.md
                      y GIT_CHANGES.md), para pre-tildar solo esos en la UI.
    """
    rt = _get_runtime()
    ticket_id = request.args.get("ticket", "").strip()
    try:
        from scm_provider.factory import get_scm
        scm = get_scm(project_name=rt["name"], workspace=rt["workspace_root"])
        changes = scm.status(rt["workspace_root"])

        # Cross-match: para cada archivo de git status, chequear si aparece
        # mencionado en los docs del ticket (DEV_COMPLETADO.md, GIT_CHANGES.md,
        # TAREAS_DESARROLLO.md). Matching robusto: busca el basename y/o el
        # sufijo del path en el texto — no requiere regex frágiles.
        ticket_files: list[str] = []
        if ticket_id:
            folder = _find_ticket_folder(ticket_id)
            if folder:
                try:
                    from commit_generator import _read_safe
                    blob = " ".join([
                        _read_safe(folder, "DEV_COMPLETADO.md",    10000),
                        _read_safe(folder, "GIT_CHANGES.md",       10000),
                        _read_safe(folder, "TAREAS_DESARROLLO.md",  5000),
                    ]).lower().replace("\\", "/")
                    if blob.strip():
                        for c in changes:
                            p = c.path.replace("\\", "/").lower()
                            basename = p.rsplit("/", 1)[-1]
                            # Match por basename siempre que no sea trivial,
                            # o por path suficientemente específico.
                            if len(basename) < 4:
                                continue
                            # Excluir paths obviamente ajenos al ticket
                            if any(skip in p for skip in ("stacky/", "tools/")):
                                continue
                            if basename in blob or p in blob:
                                ticket_files.append(c.path)
                except Exception:
                    ticket_files = []

        return jsonify({
            "ok":           True,
            "files":        [{"path": c.path, "status": c.status} for c in changes],
            "ticket_files": ticket_files,
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/git_commit/<ticket_id>", methods=["POST"])
def api_git_commit(ticket_id: str):
    """
    Ejecuta git commit con el mensaje dado sobre los archivos seleccionados.
    Body: {
        "message": "#12345 Fix en la validación de compromiso de pago",
        "files":   ["path/a.cs", "path/b.sql"]   # opcional — si se omite, falla
    }
    """
    data    = request.json or {}
    message = data.get("message", "").strip()
    files   = data.get("files") or []
    if not message:
        return jsonify({"ok": False, "error": "message requerido"}), 400
    if not files:
        return jsonify({
            "ok": False,
            "error": "Seleccioná al menos un archivo para commitear",
        }), 400

    rt = _get_runtime()
    try:
        from scm_provider.factory import get_scm
        scm = get_scm(project_name=rt["name"], workspace=rt["workspace_root"])
        commit_result = scm.commit(
            rt["workspace_root"], message, files=files, work_item_id=ticket_id,
        )
        result = {
            "ok":       commit_result.ok,
            "revision": commit_result.revision,
            "message":  commit_result.message,
            "files":    commit_result.files,
            "error":    commit_result.error,
        }

        # Si el commit fue ok, notificar por Teams
        if commit_result.ok:
            def _notify():
                try:
                    folder = _find_ticket_folder(ticket_id)
                    titulo = _get_ticket_title(folder, ticket_id) if folder else f"Ticket #{ticket_id}"
                    from teams_notifier import notify_commit
                    notify_commit(ticket_id, titulo, commit_result.revision or "?", message)
                except Exception:
                    pass
            threading.Thread(target=_notify, daemon=True).start()

        return jsonify(result)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ── Diff Assistant ─────────────────────────────────────────────────────────────

@app.route("/api/diff_analysis/<ticket_id>", methods=["GET"])
def api_diff_analysis(ticket_id: str):
    """
    Analiza el diff Git del ticket y retorna:
      layers, risks, checklist, sql_order, summary
    """
    folder = _find_ticket_folder(ticket_id)
    if not folder:
        return jsonify({"ok": False, "error": "Ticket no encontrado"}), 404
    try:
        from diff_assistant import analyze_ticket
        rt     = _get_runtime()
        result = analyze_ticket(folder, rt["workspace_root"])
        return jsonify({"ok": True, **result})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ── Deploy History ─────────────────────────────────────────────────────────────

@app.route("/api/deploy_history/<ticket_id>", methods=["GET"])
def api_deploy_history(ticket_id: str):
    """Lista el historial de ZIPs de deploy generados para un ticket."""
    folder = _find_ticket_folder(ticket_id)
    if not folder:
        return jsonify({"ok": False, "error": "Ticket no encontrado"}), 404
    try:
        from deploy_history import DeployHistory
        hist = DeployHistory(folder)
        return jsonify({"ok": True, "ticket_id": ticket_id, "deploys": hist.list_zips()})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ── Pipeline Log ──────────────────────────────────────────────────────────────

@app.route("/api/log", methods=["GET"])
def api_log():
    """
    Retorna las últimas N líneas del log de pipeline Stacky.
    Query params:
      ?lines=100        (default: 100)
      ?ticket=27698     (filtra por ticket_id, opcional)
      ?level=ERROR      (filtra por nivel: DEBUG/INFO/WARN/ERROR, opcional)
    """
    try:
        from stacky_log import slog
        lines    = int(request.args.get("lines", 100))
        ticket   = request.args.get("ticket", "").strip()
        level    = request.args.get("level", "").strip().upper()
        log_lines = slog.tail(max(10, min(lines, 2000)))
        if ticket:
            log_lines = [l for l in log_lines if f"#{ticket}" in l]
        if level:
            log_lines = [l for l in log_lines if f"[{level}" in l or f"[{level[:4]}" in l]
        return jsonify({
            "ok":       True,
            "log_file": slog.log_file,
            "lines":    log_lines,
            "count":    len(log_lines),
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/log/files", methods=["GET"])
def api_log_files():
    """Lista todos los archivos de log disponibles con su tamaño."""
    try:
        from pathlib import Path as _Path
        logs_dir = _Path(__file__).parent / "logs"
        files = []
        for f in sorted(logs_dir.glob("stacky_pipeline_*.log"), reverse=True):
            files.append({
                "name":    f.name,
                "size_kb": round(f.stat().st_size / 1024, 1),
                "date":    f.stem.replace("stacky_pipeline_", ""),
            })
        return jsonify({"ok": True, "files": files})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ── Velocity Metrics ───────────────────────────────────────────────────────────

@app.route("/api/metrics", methods=["GET"])
def api_metrics():
    """Retorna métricas de velocity del equipo."""
    days = int(request.args.get("days", 30))
    try:
        from stacky_metrics import compute
        return jsonify({"ok": True, **compute(days=days)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ── Deploy Knowledge Base ──────────────────────────────────────────────────────

@app.route("/api/deploy_incident", methods=["POST"])
def api_deploy_incident():
    """
    Registra un incidente post-deploy.
    Body: { ticket_id, description, files_deployed, severity }
    """
    data = request.json or {}
    try:
        from deploy_knowledge import report_incident
        incident = report_incident(
            ticket_id      = data.get("ticket_id", ""),
            description    = data.get("description", ""),
            files_deployed = data.get("files_deployed", []),
            severity       = data.get("severity", "medium"),
        )
        # Notificar por Telegram
        def _notify():
            try:
                from teams_notifier import send
                send(
                    f"⚠️ <b>Stacky — Incidente post-deploy reportado</b>\n\n"
                    f"🎫 <b>#{data.get('ticket_id', '?')}</b>\n"
                    f"🔴 Severidad: <b>{data.get('severity','?').upper()}</b>\n"
                    f"💬 {data.get('description','')[:200]}"
                )
            except Exception:
                pass
        threading.Thread(target=_notify, daemon=True).start()
        return jsonify({"ok": True, "incident": incident})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/deploy_warnings/<ticket_id>", methods=["GET"])
def api_deploy_warnings(ticket_id: str):
    """
    Retorna advertencias de knowledge base para los archivos de un ticket
    (basadas en incidentes anteriores con archivos similares).
    """
    folder = _find_ticket_folder(ticket_id)
    if not folder:
        return jsonify({"ok": False, "error": "Ticket no encontrado"}), 404
    try:
        from deploy_history import DeployHistory
        from deploy_knowledge import get_warnings_for_files
        hist  = DeployHistory(folder)
        zips  = hist.list_zips()
        files = []
        if zips:
            log = hist.load()
            last = log["deploys"][-1] if log.get("deploys") else {}
            files = [f["arc"] for f in last.get("files_summary", [])]
        warnings = get_warnings_for_files(files)
        return jsonify({"ok": True, "warnings": warnings})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/incidents", methods=["GET"])
def api_incidents():
    """Lista todos los incidentes registrados."""
    resolved = request.args.get("resolved")
    resolved_bool = None if resolved is None else (resolved.lower() == "true")
    try:
        from deploy_knowledge import list_incidents
        return jsonify({"ok": True, "incidents": list_incidents(resolved=resolved_bool)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/incident_test_plan/<ticket_id>", methods=["GET"])
def api_incident_test_plan(ticket_id: str):
    """
    Genera un plan de testing combinado (negocio + técnico) para un ticket
    que tuvo una incidencia previa ya resuelta por otro dev.
    Combina el análisis del diff con el historial de incidentes del ticket.
    """
    folder = _find_ticket_folder(ticket_id)
    if not folder:
        return jsonify({"ok": False, "error": "Ticket no encontrado"}), 404

    rt = _get_runtime()

    # Análisis del diff
    diff_result = {}
    try:
        from diff_assistant import analyze_ticket
        diff_result = analyze_ticket(folder, rt["workspace_root"])
    except Exception:
        pass

    # Incidentes previos del ticket
    incidents = []
    try:
        from deploy_knowledge import list_incidents
        all_inc = list_incidents(limit=200)
        incidents = [i for i in all_inc if i.get("ticket_id") == ticket_id]
    except Exception:
        pass

    # Leer DEV_COMPLETADO.md para contexto
    dev_summary = ""
    dev_path = os.path.join(folder, "DEV_COMPLETADO.md")
    if os.path.exists(dev_path):
        try:
            dev_summary = open(dev_path, encoding="utf-8").read()[:2000]
        except Exception:
            pass

    # Leer TESTER_COMPLETADO.md
    qa_summary = ""
    qa_path = os.path.join(folder, "TESTER_COMPLETADO.md")
    if os.path.exists(qa_path):
        try:
            qa_summary = open(qa_path, encoding="utf-8").read()[:2000]
        except Exception:
            pass

    # Construir plan de tests
    business_tests = _build_business_tests(folder, ticket_id, incidents, qa_summary, dev_summary)
    technical_tests = _build_technical_tests(diff_result, incidents, dev_summary, folder)

    # Resumen de contexto para mostrar en el encabezado del modal
    context_parts = []
    if incidents:
        context_parts.append(f"{len(incidents)} incidente(s) previo(s) registrado(s) para este ticket.")
        resolved = [i for i in incidents if i.get("resolved")]
        if resolved:
            context_parts.append(f"{len(resolved)} ya resuelto(s).")
    layers = diff_result.get("layers", [])
    if layers:
        context_parts.append(f"Capas modificadas: {', '.join(layers)}.")

    # Detectar batch y enriquecer contexto
    batch_ctx = _detect_batch_context(folder, dev_summary)
    if batch_ctx["is_batch"]:
        context_parts.append(f"⚙️ Proceso batch detectado: {batch_ctx['batch_name']}.")
        if batch_ctx["suggested_date"]:
            context_parts.append(f"📅 Fecha sugerida para ejecutar el batch: {batch_ctx['suggested_date']}.")
        if batch_ctx["test_data"]:
            total_rows = sum(len(g["rows"]) for g in batch_ctx["test_data"])
            context_parts.append(
                f"🗂 Datos de prueba encontrados: {len(batch_ctx['test_data'])} grupo(s), "
                f"{total_rows} registro(s) en total."
            )
        else:
            context_parts.append("⚠️ No se encontraron datos de prueba en los archivos del ticket — "
                                  "ver test TEC-BATCH para la receta de preparación.")

    if not context_parts:
        context_parts.append("No hay incidentes previos registrados para este ticket.")
    context_parts.append("Completá los checkboxes a medida que validás cada test.")

    return jsonify({
        "ok":             True,
        "ticket_id":      ticket_id,
        "incidents":      incidents,
        "context":        "\n".join(context_parts),
        "business_tests": business_tests,
        "technical_tests": technical_tests,
        "layers":         layers,
        "risks":          diff_result.get("risks", []),
    })


def _detect_batch_context(folder: str, dev_summary: str = "") -> dict:
    """
    Detecta si el ticket involucra un proceso batch (Inchost, job, scheduler).
    Extrae datos de prueba suministrados por el PM/dev en los archivos del ticket.

    Retorna:
      {
        is_batch: bool,
        batch_name: str,          # ej. "Inchost", "CierreConvenios"
        test_data: list[dict],    # grupos de datos encontrados
        suggested_date: str,      # fecha sugerida para ejecutar el batch
        find_data_recipe: str,    # SQL WHERE para encontrar registros de prueba
      }
    """
    import re
    from datetime import date

    result = {
        "is_batch": False,
        "batch_name": "",
        "test_data": [],
        "suggested_date": "",
        "find_data_recipe": "",
    }

    # Leer todos los archivos de texto del folder
    all_text = dev_summary
    for fname in ["INCIDENTE.md", "DEV_COMPLETADO.md", "TESTER_COMPLETADO.md",
                  "PM_COMPLETADO.md", "GIT_CHANGES.md"]:
        fpath = os.path.join(folder, fname)
        if os.path.exists(fpath):
            try:
                all_text += "\n" + open(fpath, encoding="utf-8", errors="ignore").read()
            except Exception:
                pass

    # ── Detectar batch ────────────────────────────────────────────────────
    batch_keywords = re.compile(
        r"\b(inchost|batch|proceso\s+batch|job|scheduler|task\s*scheduler|"
        r"cierre|liquidaci[oó]n|proceso\s+masivo|proceso\s+nocturno|"
        r"proceso\s+autom[áa]tico|cron|quartz|hangfire|windows\s+service)\b",
        re.IGNORECASE
    )
    m = batch_keywords.search(all_text)
    if m:
        result["is_batch"] = True
        # Intentar extraer el nombre del ejecutable/clase
        exe_match = re.search(r"\b([A-Z][A-Za-z0-9]+(?:host|Host|batch|Batch|Job|Cierre|Proceso)[A-Za-z0-9]*)\b", all_text)
        if exe_match:
            result["batch_name"] = exe_match.group(1)
        else:
            result["batch_name"] = m.group(1).title()

    # ── Extraer datos de prueba ───────────────────────────────────────────
    # Buscar tablas tipo "| CAMPO: valor | CAMPO: valor |" o bloques "Lotes para prueba"
    # Patrón 1: líneas con "| KEY: value | KEY: value |"
    table_lines = re.findall(r"\|[^|\n]+:[^|\n]+(?:\|[^|\n]+:[^|\n]+)+\|?", all_text)
    if table_lines:
        group_label = ""
        groups = []
        # Buscar etiquetas de grupo como "[HP-1] ..." antes de las líneas
        labeled_blocks = re.findall(
            r"\[([A-Z]{2}-\d+)\]\s*([^\n]+)\n((?:\s*\|[^\n]+\n?)+)",
            all_text
        )
        for block_id, block_title, block_rows in labeled_blocks:
            rows = []
            for row_line in block_rows.strip().splitlines():
                row_line = row_line.strip().strip("|").strip()
                if not row_line:
                    continue
                fields = {}
                for kv in re.split(r"\s*\|\s*", row_line):
                    if ":" in kv:
                        k, _, v = kv.partition(":")
                        fields[k.strip()] = v.strip()
                if fields:
                    rows.append(fields)
            if rows:
                groups.append({
                    "group_id":    block_id,
                    "description": block_title.strip(),
                    "rows":        rows,
                })
        if groups:
            result["test_data"] = groups

    # ── Fecha sugerida ────────────────────────────────────────────────────
    # Buscar menciones de fecha en el texto
    date_match = re.search(
        r"\b(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4}|\d{1,2}-\d{1,2}-\d{4})\b",
        all_text
    )
    if date_match:
        result["suggested_date"] = date_match.group(1)
    elif result["is_batch"]:
        # Si no hay fecha explícita, sugerir hoy (el tester puede ajustar)
        result["suggested_date"] = date.today().isoformat()

    # ── Receta para encontrar datos si no hay ─────────────────────────────
    if result["is_batch"] and not result["test_data"]:
        # Receta genérica; se puede especializar con más heurísticas
        result["find_data_recipe"] = (
            "-- Buscar registros que entren en el proceso:\n"
            "-- 1. Identificar la tabla principal que procesa el batch\n"
            "-- 2. Aplicar los mismos filtros WHERE que usa el batch\n"
            "-- 3. Tomar 3-5 registros de muestra\n"
            "-- Ejemplo genérico (ajustar según el batch):\n"
            "SELECT TOP 5 * FROM <TABLA_PRINCIPAL>\n"
            "WHERE <CONDICION_QUE_USA_EL_BATCH>\n"
            "  AND ESTADO = <ESTADO_INICIAL_ESPERADO>\n"
            "ORDER BY NEWID()  -- aleatorio para variedad\n\n"
            "-- Luego de identificar los registros, actualizarlos al estado\n"
            "-- inicial que espera el batch (si es necesario):\n"
            "-- UPDATE <TABLA_PRINCIPAL> SET ESTADO = <ESTADO_INICIAL>\n"
            "-- WHERE ID IN (<ids de los registros de prueba>)"
        )

    return result


def _build_business_tests(folder: str, ticket_id: str,
                           incidents: list, qa_summary: str,
                           dev_summary: str = "") -> list:
    """Genera casos de testing de negocio, con soporte especial para procesos batch."""
    tests = []
    batch = _detect_batch_context(folder, dev_summary)

    # ── Test base ────────────────────────────────────────────────────────────
    tests.append({
        "id":       "BIZ-01",
        "title":    "Verificar el caso de uso principal del ticket",
        "steps":    ["Reproducir el escenario original del ticket end-to-end",
                     "Confirmar que el comportamiento incorrecto ya no ocurre",
                     "Confirmar que el comportamiento correcto está presente"],
        "expected": "El ticket funciona según lo especificado",
        "type":     "business",
    })

    # ── Tests de proceso batch ────────────────────────────────────────────────
    if batch["is_batch"]:
        batch_name = batch["batch_name"] or "el proceso batch"
        date_hint  = f" con fecha {batch['suggested_date']}" if batch["suggested_date"] else ""

        if batch["test_data"]:
            # Hay datos de prueba — generar tests específicos por grupo
            for grp in batch["test_data"]:
                g_id    = grp["group_id"]
                g_desc  = grp["description"]
                g_rows  = grp["rows"]

                # Determinar qué estado deben terminar teniendo
                # Heurística: si el grupo tiene ESTADO inicial, el batch debería cambiarlo
                expected_outcomes = []
                for row in g_rows[:4]:  # máx 4 filas para no saturar
                    parts = []
                    for k, v in row.items():
                        parts.append(f"{k}={v}")
                    expected_outcomes.append("  · " + " | ".join(parts))

                group_steps = [
                    f"Verificar en BD DEV que los registros del grupo '{g_id}' ({g_desc}) están disponibles:",
                ] + expected_outcomes + [
                    f"Ejecutar {batch_name}{date_hint}",
                    f"Verificar que los registros del grupo '{g_id}' procesaron correctamente",
                    "Consultar en BD el estado final de cada registro y confirmar que cambió al esperado",
                ]

                # Detectar grupos "negativos" (CE-x = Casos de Error, NO deben procesarse)
                is_negative = any(k in g_id.upper() for k in ["CE", "ERR", "NEG", "NO"])
                if is_negative:
                    group_steps[-1] = f"Confirmar que los registros del grupo '{g_id}' NO fueron procesados (permanecen en estado original)"

                tests.append({
                    "id":       f"BIZ-{g_id}",
                    "title":    f"Batch {batch_name} — Grupo {g_id}: {g_desc[:60]}",
                    "steps":    group_steps,
                    "expected": (f"Registros procesados correctamente" if not is_negative
                                 else f"Registros del grupo {g_id} no modificados (caso negativo)"),
                    "type":     "business",
                    "batch":    True,
                })
        else:
            # No hay datos — dar receta para encontrarlos
            recipe_steps = [
                f"Identificar registros de prueba en BD DEV que cumplan las condiciones del batch {batch_name}:",
                "  · Ejecutar la query de búsqueda de datos (ver sección técnica TEC-BATCH)",
                "  · Anotar los IDs/convenios/cuentas encontrados",
                "  · Si los registros no están en el estado correcto, actualizarlos (ver query de actualización)",
                f"Ejecutar {batch_name}{date_hint}",
                "Verificar en BD que los registros encontrados cambiaron al estado esperado",
                "Verificar que los registros que NO debían procesarse permanecen sin cambios",
            ]
            tests.append({
                "id":       "BIZ-BATCH",
                "title":    f"Prueba del proceso batch: {batch_name}",
                "steps":    recipe_steps,
                "expected": f"{batch_name} procesa solo los registros que cumplen la condición y los deja en el estado correcto",
                "type":     "business",
                "batch":    True,
            })

    # ── Tests basados en incidentes previos ──────────────────────────────────
    for i, inc in enumerate(incidents[:3], 2):
        tests.append({
            "id":       f"BIZ-0{i}",
            "title":    f"Regresión: {inc['description'][:80]}",
            "steps":    ["Reproducir el escenario que causó el incidente anterior",
                         "Verificar que el fix del incidente sigue funcionando",
                         "Verificar que el nuevo deploy no revierte el fix anterior"],
            "expected": "El incidente previo no reaparece",
            "type":     "business",
            "incident": inc["id"],
        })

    # ── Tests estándar de negocio ─────────────────────────────────────────────
    tests += [
        {
            "id":       "BIZ-10",
            "title":    "Verificar flujos alternativos",
            "steps":    ["Probar con datos límite (nulos, vacíos, valores máximos)",
                         "Probar con usuario sin permisos",
                         "Probar cancelación en medio del proceso"],
            "expected": "Los casos borde se manejan correctamente sin errores 500",
            "type":     "business",
        },
        {
            "id":       "BIZ-11",
            "title":    "Smoke test de funcionalidades adyacentes",
            "steps":    ["Verificar que los módulos relacionados siguen funcionando",
                         "Navegar por las pantallas principales del módulo",
                         "Confirmar que no hay regresiones visibles"],
            "expected": "Sin regresiones en funcionalidades no modificadas",
            "type":     "business",
        },
    ]
    return tests


def _build_technical_tests(diff_result: dict, incidents: list,
                            dev_summary: str, folder: str = "") -> list:
    """Genera casos de testing técnico."""
    tests = []
    layers = diff_result.get("layers", [])
    risks  = diff_result.get("risks",  [])

    tests.append({
        "id":       "TEC-01",
        "title":    "Verificar logs de error post-deploy",
        "steps":    ["Revisar Event Viewer / log4net los primeros 5 minutos",
                     "Buscar excepciones nuevas no existentes antes del deploy",
                     "Verificar que no hay warnings críticos en los logs"],
        "expected": "Sin errores ni excepciones nuevas en los logs",
        "type":     "technical",
    })

    # ── Test batch técnico ────────────────────────────────────────────────────
    if folder:
        batch = _detect_batch_context(folder, dev_summary)
        if batch["is_batch"]:
            batch_name = batch["batch_name"] or "el proceso batch"
            date_hint  = f" (fecha sugerida: {batch['suggested_date']})" if batch["suggested_date"] else ""

            batch_steps = [
                f"Confirmar que el ejecutable del batch está deployado correctamente ({batch_name}.exe o equivalente)",
                f"Ejecutar {batch_name} en entorno DEV{date_hint}",
                "Monitorear la salida del proceso (stdout / log) y confirmar que no hay stack traces",
                "Verificar el tiempo de ejecución — comparar con la ejecución anterior para detectar degradación",
            ]

            if batch["find_data_recipe"] and not batch["test_data"]:
                batch_steps.insert(1, "Preparar datos de prueba en BD DEV:")
                batch_steps.insert(2, batch["find_data_recipe"])
            elif batch["test_data"]:
                row_summary = []
                for grp in batch["test_data"][:2]:
                    row_summary.append(f"  Grupo {grp['group_id']}: {len(grp['rows'])} registro(s)")
                batch_steps.insert(1, "Datos de prueba detectados en el ticket:")
                batch_steps[2:2] = row_summary

            # Queries de verificación post-ejecución
            batch_steps += [
                "Ejecutar queries de verificación para confirmar el estado final en BD:",
                "  · Registros del grupo positivo → estado cambiado al esperado",
                "  · Registros del grupo negativo → sin cambios",
                "  · Sin registros procesados duplicados o huérfanos",
                "Confirmar que el proceso batch puede ejecutarse nuevamente sin errores (idempotencia)",
            ]

            tests.append({
                "id":       "TEC-BATCH",
                "title":    f"Verificación técnica del proceso batch: {batch_name}",
                "steps":    batch_steps,
                "expected": (f"{batch_name} ejecuta sin errores, procesa los registros correctos "
                             f"y los deja en el estado esperado"),
                "type":     "technical",
                "batch":    True,
            })

    if any("datos" in l.lower() or "dal" in l.lower() for l in layers):
        tests.append({
            "id":       "TEC-02",
            "title":    "Verificar integridad de datos en BD",
            "steps":    ["Ejecutar queries de verificación incluidas en QUERIES_ANALISIS.sql",
                         "Comparar conteos antes y después del deploy",
                         "Verificar que no hay registros huérfanos o duplicados"],
            "expected": "Datos consistentes en la base de datos",
            "type":     "technical",
        })

    if any("sesión" in r["message"].lower() or "session" in r["message"].lower() for r in risks):
        tests.append({
            "id":       "TEC-03",
            "title":    "Verificar gestión de sesión",
            "steps":    ["Login y logout completo",
                         "Sesión expirada — verificar redirección correcta",
                         "Dos usuarios simultáneos — sin interferencia de sesiones"],
            "expected": "Sesiones aisladas y comportamiento correcto",
            "type":     "technical",
        })

    if any("stored" in r["message"].lower() or "sp" in r["message"].lower() for r in risks):
        tests.append({
            "id":       "TEC-04",
            "title":    "Verificar stored procedures en BD destino",
            "steps":    ["Confirmar que todos los SPs requeridos existen",
                         "Ejecutar los SPs con parámetros de prueba",
                         "Verificar que los resultados son correctos"],
            "expected": "Todos los SPs funcionan correctamente en el entorno destino",
            "type":     "technical",
        })

    tests.append({
        "id":       "TEC-20",
        "title":    "Performance básica",
        "steps":    ["Medir tiempo de respuesta de las pantallas modificadas",
                     "Comparar con el tiempo esperado (< 3 segundos para operaciones normales)",
                     "Verificar que no hay consultas N+1 o timeouts"],
        "expected": "Tiempo de respuesta aceptable, sin degradación vs versión anterior",
        "type":     "technical",
    })

    tests.append({
        "id":       "TEC-21",
        "title":    "Verificar permisos y seguridad",
        "steps":    ["Acceder con usuario de bajo privilegio y verificar que no ve datos no permitidos",
                     "Intentar acceder directamente a URLs sensibles",
                     "Verificar que los roles no cambiaron"],
        "expected": "Acceso controlado según permisos definidos",
        "type":     "technical",
    })

    return tests


@app.route("/api/incidents/<incident_id>/resolve", methods=["POST"])
def api_resolve_incident(incident_id: str):
    """Marca un incidente como resuelto."""
    data = request.json or {}
    try:
        from deploy_knowledge import resolve_incident
        ok = resolve_incident(incident_id, data.get("resolution_note", ""))
        return jsonify({"ok": ok})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ── Teams Config ──────────────────────────────────────────────────────────────

@app.route("/api/teams/config", methods=["GET", "POST"])
def api_teams_config():
    """GET: estado de configuración. POST: guardar webhook_url + mode."""
    if request.method == "GET":
        try:
            from teams_notifier import is_configured
            return jsonify({"ok": True, "configured": is_configured()})
        except Exception as e:
            return jsonify({"ok": False, "configured": False, "error": str(e)})

    data        = request.json or {}
    webhook_url = data.get("webhook_url", "").strip()
    mode        = data.get("mode", "webhook").strip()
    if not webhook_url:
        return jsonify({"ok": False, "error": "webhook_url requerido"}), 400
    try:
        from teams_notifier import send_test
        result = send_test(webhook_url, mode)
        return jsonify({"ok": result.get("ok", False),
                        "test_sent": result.get("ok", False),
                        "test_error": result.get("error")})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ── Watcher: notificar Teams cuando un ticket completa ────────────────────────

def _teams_notify_watcher():
    """
    Hilo secundario — solo notifica por Teams cuando un ticket llega a 'completado'.
    NO transiciona estados — eso lo hace _stage_transition_watcher.
    """
    import time
    _notified: set = set()

    while True:
        try:
            tickets = _scan_tickets()
            for t in tickets:
                tid = t["ticket_id"]
                if t["pipeline_estado"] == "completado" and tid not in _notified:
                    _notified.add(tid)
                    def _do_notify(t=t):
                        try:
                            from teams_notifier import notify_pipeline_complete
                            rt     = _get_runtime()
                            folder = _find_ticket_folder(t["ticket_id"], rt["tickets_base"])
                            titulo = _get_ticket_title(folder, t["ticket_id"]) if folder else t.get("titulo", "")
                            dur = None
                            ini = t.get("pm_inicio_at") or t.get("pm_completado_at")
                            fin = t.get("completado_at") or t.get("tester_completado_at")
                            if ini and fin:
                                from datetime import datetime as _dt
                                try:
                                    dur = int((_dt.fromisoformat(fin) - _dt.fromisoformat(ini)).total_seconds())
                                except Exception:
                                    pass
                            notify_pipeline_complete(t["ticket_id"], titulo, dur_total_seg=dur)
                        except Exception:
                            pass
                    threading.Thread(target=_do_notify, daemon=True).start()
        except Exception:
            pass
        time.sleep(30)


# ── Reconciliador del pipeline (fuente de verdad canónica) ────────────────────
#
# Arregla la clase de bugs "state.json dice X, folder dice Y, nadie avanza":
# cada 45s inspecciona el folder de cada ticket no-terminal, deriva el estado
# real desde los archivos (flags, .md) y sincroniza state.json + lanza la
# etapa que falte si hay divergencia. También detecta tickets "stale" (en
# *_en_proceso sin progreso ni AGENTE_EN_CURSO) y emite warning al usuario.
#
# Ver pipeline_reconciler.py para la lógica pura y los tests unitarios.

# Cooldown: no reconciliar el mismo ticket más seguido que esto (evita ruido
# post-invocación cuando los flags están escribiéndose).
_RECONCILER_INTERVAL    = 45
_RECONCILER_PER_TICKET  = {}   # ticket_id → monotonic timestamp del último kick
_RECONCILER_COOLDOWN    = 120  # segundos


def _pipeline_reconciler_loop():
    """
    Hilo background — corre el reconciliador cada _RECONCILER_INTERVAL segundos.

    Para cada ticket en state.json:
      1. Deriva el estado real desde los archivos del folder.
      2. Si diverge con state.json → sincroniza + dispara la etapa que toque.
      3. Si está stale (en *_en_proceso sin progreso) → emite notificación.
    """
    from pipeline_reconciler import reconcile_ticket_entry
    from pipeline_state import load_state, save_state
    import time

    # Esperar un poco al arranque para que el watcher principal se asiente
    time.sleep(15)

    # Budget por tick: máximo de tickets que pueden lanzarse por ciclo.
    # Con el gate global=serial strict, mantenerlo en 1 previene cualquier
    # ráfaga aunque el gate se hubiera liberado entre tickets del mismo tick.
    _LAUNCH_BUDGET_PER_TICK = 1

    while True:
        time.sleep(_RECONCILER_INTERVAL)
        try:
            rt = _get_runtime()
            sp = rt["state_path"]
            # Forzar re-lectura
            try:
                from pipeline_state import _load_cache as _plc
                _plc["mtime"] = 0.0
            except Exception:
                pass
            state = load_state(sp)
            changed = False
            now_mono = time.monotonic()

            # Release oportunista: si el ticket activo quedó en estado terminal
            # (completado / error_* / bloqueo_humano / pm_revision / qa_rework),
            # libera el gate antes de iterar. Los watchers ya suelen liberarlo,
            # esto es el catch-all.
            _active = _get_active_ticket()
            if _active:
                _active_entry = state.get("tickets", {}).get(_active, {})
                _maybe_release_if_terminal(_active, _active_entry.get("estado", ""))

            launched_this_tick = 0

            for tid, entry in list(state.get("tickets", {}).items()):
                # Cooldown por ticket — evita que un ticket "flapeante" se
                # kickee cada tick
                last_kick = _RECONCILER_PER_TICKET.get(tid, 0)
                if now_mono - last_kick < _RECONCILER_COOLDOWN:
                    continue

                folder = entry.get("folder") or _find_ticket_folder(tid, rt["tickets_base"])
                if not folder or not os.path.isdir(folder):
                    continue

                # También saltar si el watcher normal recién hizo algo (cooldown
                # por set_state manual) — evita pisadas.
                if _manual_set_timestamps.get(tid, 0) and \
                   (_time.time() - _manual_set_timestamps[tid]) < 60:
                    continue

                res = reconcile_ticket_entry(tid, folder, entry)

                if res.is_stale and res.stale_reason:
                    # Notificar stale solo una vez cada cooldown window
                    _RECONCILER_PER_TICKET[tid] = now_mono
                    print(f"[RECONCILE] {tid} STALE: {res.stale_reason}",
                          file=sys.stderr, flush=True)
                    _push_notification(
                        f"⚠️ Ticket #{tid} atascado",
                        res.stale_reason + " — clic en 'Desatascar' o 'Ejecutar'",
                        "warning",
                    )
                    # No avanzamos automáticamente ante stale — es señal de
                    # que algo no está funcionando bien y el usuario debe ver.
                    continue

                if res.coherent:
                    continue

                # Divergencia real — sincronizar
                if res.needs_sync and res.synthetic_state:
                    # Pre-check gate y budget ANTES de mutar state: si no vamos
                    # a lanzar, igual sincronizamos el estado (coherencia), pero
                    # marcamos el lanzamiento como "pospuesto".
                    will_launch = bool(res.launch_stage)
                    postpone_reason = None
                    if will_launch:
                        _active_now = _get_active_ticket()
                        if _active_now and _active_now != tid:
                            will_launch = False
                            postpone_reason = f"gate global ocupado por #{_active_now}"
                        elif launched_this_tick >= _LAUNCH_BUDGET_PER_TICK:
                            will_launch = False
                            postpone_reason = (
                                f"budget del tick agotado ({_LAUNCH_BUDGET_PER_TICK})"
                            )

                    print(f"[RECONCILE] {tid}: {res.stored_estado} → "
                          f"{res.synthetic_state} (derivado desde folder: "
                          f"{', '.join(res.derived.evidence) if res.derived else '?'})",
                          flush=True)
                    prev_estado = entry.get("estado", "")
                    entry["estado"] = res.synthetic_state
                    entry[f"{res.synthetic_state}_at"] = datetime.now().isoformat()
                    if prev_estado == "completado":
                        entry.pop("completado_at", None)
                    # Auditoría: registrar transición
                    transitions = entry.setdefault("transitions", [])
                    transitions.append({
                        "at":   datetime.now().isoformat(),
                        "from": prev_estado,
                        "to":   res.synthetic_state,
                        "by":   "reconciler",
                        "evidence": res.derived.evidence if res.derived else [],
                    })
                    # Cap el historial de transiciones
                    if len(transitions) > 50:
                        entry["transitions"] = transitions[-50:]
                    changed = True

                    if res.launch_stage and not will_launch:
                        print(f"[RECONCILE] {tid}: postergando lanzamiento de "
                              f"{res.launch_stage.upper()} — {postpone_reason}",
                              flush=True)
                        continue

                    # Lanzar etapa si el plan lo indica
                    if will_launch:
                        entry["auto_advance"] = True
                        save_state(sp, state)
                        changed = False
                        _RECONCILER_PER_TICKET[tid] = now_mono
                        launched_this_tick += 1
                        _push_notification(
                            f"🔧 Reconciliador — #{tid}",
                            f"Divergencia detectada → lanzando "
                            f"{res.launch_stage.upper()}",
                            "info",
                        )
                        threading.Thread(
                            target=_invoke_stage, args=(tid, res.launch_stage),
                            daemon=True, name=f"reconcile-{tid}",
                        ).start()

            if changed:
                save_state(sp, state)
        except Exception as e:
            print(f"[RECONCILE] Error en loop: {e}", file=sys.stderr, flush=True)


# ════════════════════════════════════════════════════════════════════════════
# F1-F4 — scoring + observabilidad (endpoints aditivos)
# ════════════════════════════════════════════════════════════════════════════
#
# Expone 12 endpoints nuevos para el frontend de estimación y observabilidad:
#   - /api/scoring/<ticket_id>              (GET)
#   - /api/scoring/<ticket_id>/recompute    (POST)
#   - /api/scoring/<ticket_id>/actual       (POST)
#   - /api/scoring/history                  (GET)
#   - /api/scoring/calibration              (GET)
#   - /api/scoring/calibration/apply        (POST)
#   - /api/events/stream                    (GET, SSE)
#   - /api/events                           (GET)
#   - /api/errors/ticket/<ticket_id>        (GET)
#   - /api/pipeline/performance             (GET)
#   - /api/config/scoring                   (GET)
#   - /api/config/scoring                   (PATCH)
#
# Todos los imports viven dentro de los handlers para garantizar que si
# algún módulo (ticket_scoring, estimation_store, pipeline_events, sse_bus)
# no está disponible, el resto del servidor sigue funcionando y el endpoint
# responde con 503 + diagnóstico claro.

def _scoring_compute_for_ticket(ticket_id: str, project: str | None = None):
    """
    Helper canónico: calcula scoring de un ticket, persiste el estimate y
    emite evento ``estimation_recorded``. Retorna ``(scoring, None)`` o
    ``(None, error_message)``.
    """
    rt = _get_runtime()
    project = project or rt["name"]
    folder = _find_ticket_folder(ticket_id, rt["tickets_base"])
    if not folder:
        return None, "ticket_folder_not_found"
    try:
        from ticket_scoring import compute_scoring, read_incident_content
        from estimation_store import record_estimate, load_calibration
    except Exception as e:
        return None, f"scoring_module_missing: {e}"
    content = read_incident_content(folder, ticket_id=ticket_id)
    if not content:
        return None, "incidente_no_encontrado"
    try:
        calibration = load_calibration()
    except Exception:
        calibration = {}
    scoring = compute_scoring(content, project=project, global_calibration=calibration)
    try:
        record_estimate(ticket_id, scoring, project=project)
    except Exception as e:
        print(f"[SCORING] record_estimate falló para #{ticket_id}: {e}",
              file=sys.stderr, flush=True)
    # Emit best-effort — no debe romper el endpoint
    try:
        from pipeline_events import emit as _emit_event
        _emit_event(
            kind="estimation_recorded",
            ticket_id=ticket_id,
            project=project,
            detail=f"score={scoring.score} est={scoring.estimated_minutes}min",
        )
    except Exception:
        pass
    return scoring, None


@app.route("/api/scoring/<ticket_id>", methods=["GET"])
def api_scoring_get(ticket_id):
    """
    GET → retorna la entry de estimación del ticket.
    Si no existe, la calcula y persiste en el momento (lazy create).
    Además: si el ticket ya está en ``completado``, intenta cerrar la entry
    con los ``actual_minutes`` derivados de state.json.
    """
    try:
        from estimation_store import get_entry, maybe_close_from_state
    except Exception as e:
        return jsonify({"error": f"estimation_store indisponible: {e}"}), 503

    entry = get_entry(ticket_id)
    if entry is None:
        scoring, err = _scoring_compute_for_ticket(ticket_id)
        if err:
            return jsonify({"error": err}), 404
        entry = get_entry(ticket_id)

    # Auto-close lazy si el ticket está completado y la entry aún no tiene actuals
    try:
        state = _load_pipeline_state()
        state_entry = (state.get("tickets") or {}).get(ticket_id, {})
        if state_entry and entry and entry.get("actual_minutes") is None:
            if maybe_close_from_state(ticket_id, state_entry):
                entry = get_entry(ticket_id)
    except Exception as e:
        print(f"[SCORING] maybe_close_from_state #{ticket_id}: {e}",
              file=sys.stderr, flush=True)

    return jsonify(entry or {})


@app.route("/api/scoring/<ticket_id>/recompute", methods=["POST"])
def api_scoring_recompute(ticket_id):
    """POST → fuerza el recálculo y retorna la entry actualizada."""
    project = (request.get_json(silent=True) or {}).get("project") or None
    scoring, err = _scoring_compute_for_ticket(ticket_id, project=project)
    if err:
        return jsonify({"error": err}), 404
    try:
        from estimation_store import get_entry
        return jsonify(get_entry(ticket_id) or {})
    except Exception as e:
        return jsonify({"error": f"estimation_store indisponible: {e}"}), 503


@app.route("/api/scoring/<ticket_id>/actual", methods=["POST"])
def api_scoring_actual(ticket_id):
    """
    POST body: ``{actual_minutes, per_stage, corrections_sent, rework_cycles,
    first_attempt_approved}``. Registra los valores reales del ticket.
    """
    try:
        from estimation_store import record_actual
    except Exception as e:
        return jsonify({"error": f"estimation_store indisponible: {e}"}), 503
    body = request.get_json(silent=True) or {}
    updated = record_actual(
        ticket_id,
        actual_minutes=body.get("actual_minutes"),
        per_stage_actual=body.get("per_stage") or body.get("per_stage_actual"),
        rework_cycles=body.get("rework_cycles"),
        corrections_sent=body.get("corrections_sent"),
        first_attempt_approved=body.get("first_attempt_approved"),
    )
    if updated is None:
        return jsonify({"error": "entry no encontrada; llamá primero a /api/scoring/<id>"}), 404
    return jsonify(updated)


@app.route("/api/scoring/history", methods=["GET"])
def api_scoring_history():
    """GET ?project=&days= → lista de entries (estimación + realidad)."""
    try:
        from estimation_store import list_entries
    except Exception as e:
        return jsonify({"error": f"estimation_store indisponible: {e}"}), 503
    project = request.args.get("project") or None
    days_arg = request.args.get("days")
    days = int(days_arg) if days_arg and days_arg.isdigit() else None
    closed_only = request.args.get("closed_only", "").lower() in ("1", "true", "yes")
    entries = list_entries(project=project, days=days, closed_only=closed_only)
    return jsonify({
        "project": project,
        "days":    days,
        "count":   len(entries),
        "entries": entries,
    })


@app.route("/api/scoring/calibration", methods=["GET"])
def api_scoring_calibration():
    """GET → devuelve el bloque ``calibration`` del estimation store + sugerencia."""
    try:
        from estimation_store import load_calibration, suggest_delta_calibration, compute_accuracy
    except Exception as e:
        return jsonify({"error": f"estimation_store indisponible: {e}"}), 503
    project = request.args.get("project") or None
    days_arg = request.args.get("days")
    days = int(days_arg) if days_arg and days_arg.isdigit() else 90
    try:
        min_samples_arg = request.args.get("min_samples")
        min_samples = int(min_samples_arg) if min_samples_arg and min_samples_arg.isdigit() else 20
    except Exception:
        min_samples = 20
    try:
        suggestion = suggest_delta_calibration(
            min_samples=min_samples, project=project, days=days,
        )
    except Exception as e:
        suggestion = {"error": str(e)}
    try:
        accuracy = compute_accuracy(days=days, project=project)
    except Exception as e:
        accuracy = {"error": str(e)}
    return jsonify({
        "calibration": load_calibration(),
        "suggestion":  suggestion,
        "accuracy":    accuracy,
        "project":     project,
        "days":        days,
    })


@app.route("/api/scoring/calibration/apply", methods=["POST"])
def api_scoring_calibration_apply():
    """
    POST body: ``{scope: "global"|"project", project?}``. Aplica la delta
    sugerida (desde ``suggest_delta_calibration``) al store.
    """
    try:
        from estimation_store import apply_calibration, suggest_delta_calibration
    except Exception as e:
        return jsonify({"error": f"estimation_store indisponible: {e}"}), 503
    body = request.get_json(silent=True) or {}
    scope = (body.get("scope") or "global").lower()
    project = body.get("project") or None

    if scope == "global":
        sug = suggest_delta_calibration()
        delta = sug.get("suggested_delta_pct")
        if delta is None:
            return jsonify({"error": "sin suggestion disponible", "suggestion": sug}), 400
        result = apply_calibration(global_delta_pct=float(delta))
        return jsonify({"applied": "global", "delta_pct": float(delta),
                        "calibration": result})

    if scope == "project":
        if not project:
            return jsonify({"error": "project requerido para scope=project"}), 400
        sug = suggest_delta_calibration(project=project)
        delta = sug.get("suggested_delta_pct")
        if delta is None:
            return jsonify({"error": "sin suggestion disponible para project",
                            "suggestion": sug}), 400
        result = apply_calibration(project_deltas={project: float(delta)})
        return jsonify({"applied": "project", "project": project,
                        "delta_pct": float(delta), "calibration": result})

    return jsonify({"error": f"scope desconocido: {scope}"}), 400


@app.route("/api/events/stream", methods=["GET"])
def api_events_stream():
    """
    SSE stream de eventos del pipeline. Query opcional:
      ?ticket=<id>    — filtra por ticket_id
      ?kind=<kind>    — filtra por kind
    Header opcional: Last-Event-ID para replay tras reconexión.
    """
    try:
        from sse_bus import event_stream
    except Exception as e:
        return jsonify({"error": f"sse_bus indisponible: {e}"}), 503
    last_event_id = request.headers.get("Last-Event-ID")
    ticket = request.args.get("ticket") or None
    kind_filter = request.args.get("kind") or None
    return Response(
        event_stream(
            last_event_id=last_event_id,
            ticket_id=ticket,
            kind_filter=kind_filter,
        ),
        mimetype="text/event-stream",
        headers={
            "Cache-Control":         "no-cache",
            "X-Accel-Buffering":     "no",
            "Connection":            "keep-alive",
        },
    )


@app.route("/api/events", methods=["GET"])
def api_events_list():
    """GET ?ticket=&since=&limit=&kind= → lee del JSONL."""
    try:
        from pipeline_events import read_events
    except Exception as e:
        return jsonify({"error": f"pipeline_events indisponible: {e}"}), 503
    ticket = request.args.get("ticket") or None
    kind = request.args.get("kind") or None
    since_raw = request.args.get("since") or None
    since = None
    if since_raw:
        try:
            since = datetime.fromisoformat(since_raw.replace("Z", "+00:00"))
        except Exception:
            since = None
    try:
        limit = int(request.args.get("limit") or 500)
    except Exception:
        limit = 500
    events = read_events(ticket_id=ticket, kind=kind, since=since, limit=limit)
    return jsonify({"count": len(events), "events": events})


@app.route("/api/errors/ticket/<ticket_id>", methods=["GET"])
def api_errors_for_ticket(ticket_id):
    """Eventos ``action_error`` para un ticket (últimos N días)."""
    try:
        from pipeline_events import read_events
    except Exception as e:
        return jsonify({"error": f"pipeline_events indisponible: {e}"}), 503
    try:
        limit = int(request.args.get("limit") or 50)
    except Exception:
        limit = 50
    events = read_events(ticket_id=ticket_id, kind="action_error", limit=limit)
    return jsonify({"ticket_id": ticket_id, "count": len(events), "events": events})


@app.route("/api/pipeline/performance", methods=["GET"])
def api_pipeline_performance():
    """
    Métricas agregadas PM/DEV/QA: tiempo, reintentos, correcciones, 1er intento OK.
    Combina state.json + pipeline_events.jsonl.
    """
    try:
        from metrics_collector import get_metrics_collector
    except Exception as e:
        return jsonify({"error": f"metrics_collector indisponible: {e}"}), 503
    rt = _get_runtime()
    project = request.args.get("project") or rt["name"]
    try:
        days = int(request.args.get("days") or 7)
    except Exception:
        days = 7
    try:
        mc = get_metrics_collector(project)
        fn = getattr(mc, "get_pipeline_performance_metrics", None)
        if fn is None:
            return jsonify({"error": "metrics_collector.get_pipeline_performance_metrics no disponible"}), 503
        return jsonify(fn(days=days, project=project))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/config/scoring", methods=["GET"])
def api_config_scoring_get():
    """GET ?project=  → devuelve config de scoring resuelta (global + proyecto)."""
    try:
        from ticket_scoring import load_scoring_config
    except Exception as e:
        return jsonify({"error": f"ticket_scoring indisponible: {e}"}), 503
    project = request.args.get("project") or _get_runtime()["name"]
    cfg = load_scoring_config(project)
    return jsonify({"project": project, "config": cfg})


@app.route("/api/config/scoring", methods=["PATCH"])
def api_config_scoring_patch():
    """
    PATCH body: merge parcial sobre ``scoring_defaults`` (global, en config.json)
    o ``scoring`` (por proyecto, en projects/<NAME>/config.json si ?project=).
    """
    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        return jsonify({"error": "body debe ser objeto JSON"}), 400
    project = request.args.get("project") or None

    # Path del archivo a actualizar
    if project:
        cfg_path = os.path.join(BASE_DIR, "projects", project, "config.json")
        key = "scoring"
    else:
        cfg_path = os.path.join(BASE_DIR, "config.json")
        key = "scoring_defaults"

    if not os.path.exists(cfg_path):
        return jsonify({"error": f"config no encontrada: {cfg_path}"}), 404

    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return jsonify({"error": f"no se pudo leer config: {e}"}), 500

    # Deep merge sobre data[key]
    def _deep_merge(dst: dict, src: dict) -> None:
        for k, v in (src or {}).items():
            if isinstance(v, dict) and isinstance(dst.get(k), dict):
                _deep_merge(dst[k], v)
            else:
                dst[k] = v

    current = data.setdefault(key, {})
    _deep_merge(current, body)

    # Escritura atómica
    tmp = cfg_path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, cfg_path)
    except Exception as e:
        try:
            os.remove(tmp)
        except Exception:
            pass
        return jsonify({"error": f"no se pudo guardar config: {e}"}), 500

    return jsonify({"updated": key, "project": project, "config": data.get(key)})


# ── Endpoints de QA actions + valid transitions ──────────────────────────────

@app.route("/api/pipeline/valid_transitions", methods=["GET"])
def api_pipeline_valid_transitions():
    """
    Devuelve la tabla `_VALID_AUTO_ADVANCE_TRANSITIONS` (fuente de verdad de
    transiciones auto-avanzables). El dashboard la consume para decidir qué
    botones mostrar contextualmente.
    """
    try:
        from pipeline_state import _VALID_AUTO_ADVANCE_TRANSITIONS
    except Exception as e:
        return jsonify({"error": f"pipeline_state indisponible: {e}"}), 503
    return jsonify({"transitions": dict(_VALID_AUTO_ADVANCE_TRANSITIONS)})


# Acciones manuales de QA post-rechazo. Cada entry declara:
#   - valid_from: estados desde los cuales se puede ejecutar
#   - to_state:   estado destino
#   - releases_gate: si debe liberar el gate global del ticket activo
_QA_ACTION_MAP = {
    "reenviar_pm": {
        "valid_from":     frozenset((
            "tester_completado", "stagnation_detected",
            "pm_revision", "qa_rework",
        )),
        "to_state":       "pm_revision_en_proceso",
        "releases_gate":  False,
    },
    "volver_dev": {
        "valid_from":     frozenset((
            "tester_completado", "stagnation_detected",
            "pm_revision", "qa_rework",
        )),
        # qa_rework es el hop intermedio que _VALID_AUTO_ADVANCE_TRANSITIONS
        # usa para avanzar a dev_rework_en_proceso.
        "to_state":       "qa_rework",
        "releases_gate":  False,
    },
}


@app.route("/api/tickets/<ticket_id>/qa_action", methods=["POST"])
def api_tickets_qa_action(ticket_id: str):
    """
    Ejecuta una acción manual del usuario sobre un ticket QA-rechazado.
    Body: ``{"action": "reenviar_pm" | "volver_dev"}``.

    Valida contra ``_QA_ACTION_MAP`` (qué estados permiten qué acción) y ejecuta
    la transición usando ``set_ticket_state``. No dispara invocación de agente
    (eso lo maneja el watcher cuando vea el nuevo estado) — acá solo movemos
    el estado, para mantener la lógica de este endpoint simple y predecible.
    """
    from pipeline_state import load_state, save_state, set_ticket_state

    body = request.get_json(silent=True) or {}
    action = str(body.get("action") or "").strip()
    if not action:
        return jsonify({"ok": False, "error": "missing 'action'"}), 400
    action_cfg = _QA_ACTION_MAP.get(action)
    if not action_cfg:
        return jsonify({"ok": False, "error": f"acción desconocida: {action}",
                        "valid_actions": list(_QA_ACTION_MAP.keys())}), 400

    rt    = _get_runtime()
    state = load_state(rt["state_path"])
    entry = (state.get("tickets") or {}).get(ticket_id)
    if entry is None:
        return jsonify({"ok": False, "error": f"ticket no existe: {ticket_id}"}), 404

    current = entry.get("estado", "")
    if current not in action_cfg["valid_from"]:
        return jsonify({
            "ok":            False,
            "error":         f"transición inválida: desde '{current}' no se "
                             f"puede aplicar '{action}'",
            "current_state": current,
            "valid_from":    sorted(action_cfg["valid_from"]),
        }), 400

    to_state = action_cfg["to_state"]
    try:
        set_ticket_state(state, ticket_id, to_state,
                         qa_action=action, qa_action_by="dashboard-user",
                         qa_action_from=current)
        # Si la acción libera el gate (no es el caso actual, pero contemplado),
        # lo soltamos explícitamente.
        if action_cfg.get("releases_gate"):
            try:
                _release_active_ticket(ticket_id, reason=f"qa_action={action}")
            except Exception:
                pass
        save_state(rt["state_path"], state)
    except Exception as e:
        return jsonify({"ok": False, "error": f"no se pudo aplicar: {e}"}), 500

    # Log + evento best-effort
    try:
        from pipeline_events import emit as _emit
        _emit(
            kind="state_transition",
            ticket_id=ticket_id,
            project=rt.get("name"),
            action="qa_action",
            detail=f"{current} -> {to_state} ({action})",
        )
    except Exception:
        pass

    return jsonify({
        "ok":         True,
        "ticket_id":  ticket_id,
        "action":     action,
        "from_state": current,
        "to_state":   to_state,
    })


# ── Endpoint: re-entrenamiento manual del modelo de estimación ───────────────

@app.route("/api/estimation_model/retrain", methods=["POST"])
def api_estimation_model_retrain():
    """
    Dispara el entrenamiento manual de la regresión lineal que estima minutos
    reales a partir de los factores de scoring. Devuelve las stats del modelo.
    """
    try:
        from estimation_model import train_model
    except Exception as e:
        return jsonify({"error": f"estimation_model indisponible: {e}"}), 503
    try:
        stats = train_model()
    except Exception as e:
        return jsonify({"error": f"train_model falló: {e}"}), 500
    if stats is None:
        return jsonify({
            "ok":       False,
            "trained":  False,
            "reason":   "insuficientes samples o fallo silencioso — ver logs",
        })
    return jsonify({"ok": True, "trained": True, "stats": stats})


@app.route("/api/estimation_model", methods=["GET"])
def api_estimation_model_get():
    """Devuelve el estado del modelo entrenado (si existe)."""
    try:
        from estimation_model import load_model
    except Exception as e:
        return jsonify({"error": f"estimation_model indisponible: {e}"}), 503
    model = load_model()
    return jsonify(model or {"trained": False})


# ── Endpoints de metadata de tickets (color, user_tags, commits, notas) ──────

@app.route("/api/tickets/<ticket_id>/metadata", methods=["GET"])
def api_tickets_metadata(ticket_id: str):
    """GET /api/tickets/<id>/metadata — retorna metadata del ticket."""
    try:
        from ticket_metadata_store import get_store
        store = get_store()
        meta = store.get(ticket_id)
        if meta is None:
            return jsonify({"ok": False, "error": f"ticket {ticket_id} sin metadata"}), 404
        return jsonify({
            "ok": True,
            "ticket_id": ticket_id,
            "color": meta.color.hex if meta.color else None,
            "user_tags": meta.user_tags.tags if meta.user_tags else [],
            "commits_count": meta.commits_count or 0,
            "last_commit_hash": meta.last_commit_hash,
            "last_commit_at": meta.last_commit_at,
            "ado_comments_count": meta.ado_comments_count or 0,
            "notes_count": meta.notes_count or 0,
            "last_note_at": meta.last_note_at,
            "last_indexed_at": meta.last_indexed_at,
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/tickets/metadata/summary", methods=["GET"])
def api_tickets_metadata_summary():
    """GET /api/tickets/metadata/summary — agregados de metadata por estado/tag/asignado."""
    try:
        from ticket_metadata_store import get_store
        store = get_store()
        all_meta = store.get_all()

        # Parsing de query params para grouping
        group_by = request.args.get("group_by", "").split(",")
        group_by = [g.strip() for g in group_by if g.strip()]

        summary = {
            "total": len(all_meta),
            "con_color": sum(1 for m in all_meta.values() if m.color),
            "sin_color": sum(1 for m in all_meta.values() if not m.color),
            "con_commits": sum(1 for m in all_meta.values() if m.commits_count and m.commits_count > 0),
            "sin_commits": sum(1 for m in all_meta.values() if not m.commits_count or m.commits_count == 0),
            "con_notas": sum(1 for m in all_meta.values() if m.notes_count and m.notes_count > 0),
            "sin_notas": sum(1 for m in all_meta.values() if not m.notes_count or m.notes_count == 0),
        }

        # Agregados por grupo si se pidieron
        if "user_tags" in group_by:
            summary["per_user_tag"] = {}
            for meta in all_meta.values():
                tags_list = meta.user_tags.tags if meta.user_tags else []
                for tag in tags_list:
                    if tag not in summary["per_user_tag"]:
                        summary["per_user_tag"][tag] = {"count": 0, "tickets": []}
                    summary["per_user_tag"][tag]["count"] += 1
                    summary["per_user_tag"][tag]["tickets"].append(meta.ticket_id)

        if "color" in group_by:
            summary["per_color"] = {}
            for meta in all_meta.values():
                color = meta.color.hex if meta.color else "sin_color"
                if color not in summary["per_color"]:
                    summary["per_color"][color] = {"count": 0, "tickets": []}
                summary["per_color"][color]["count"] += 1
                summary["per_color"][color]["tickets"].append(meta.ticket_id)

        return jsonify({"ok": True, **summary})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/tickets/<ticket_id>/color", methods=["PATCH"])
def api_tickets_color_patch(ticket_id: str):
    """PATCH /api/tickets/<id>/color — set/clear color del ticket."""
    try:
        from ticket_metadata_store import get_store
        data = request.json or {}
        color = data.get("color")

        store = get_store()
        if color is None:
            store.clear_color(ticket_id)
            color_result = None
        else:
            if not isinstance(color, str) or not color.startswith("#") or len(color) != 7:
                return jsonify({"ok": False, "error": "color debe ser #rrggbb"}), 400
            store.set_color(ticket_id, color.lower())
            color_result = color.lower()

        meta = store.get(ticket_id)
        return jsonify({
            "ok": True,
            "ticket_id": ticket_id,
            "color": color_result if color_result else (meta.color.hex if meta.color else None),
            "updated_at": meta.updated_at if meta else None,
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/tickets/<ticket_id>/user_tags", methods=["POST"])
def api_tickets_user_tags_post(ticket_id: str):
    """POST /api/tickets/<id>/user_tags — agregar un tag."""
    try:
        from ticket_metadata_store import get_store
        from pydantic import ValidationError as PydanticError
        data = request.json or {}
        tag = data.get("tag", "").strip()

        if not tag:
            return jsonify({"ok": False, "error": "tag requerido"}), 400

        store = get_store()
        store.add_user_tag(ticket_id, tag)
        meta = store.get(ticket_id)
        return jsonify({
            "ok": True,
            "ticket_id": ticket_id,
            "user_tags": meta.user_tags.tags if meta and meta.user_tags else [],
            "updated_at": meta.updated_at if meta else None,
        })
    except (ValueError, PydanticError) as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/tickets/<ticket_id>/user_tags/<tag>", methods=["DELETE"])
def api_tickets_user_tags_delete(ticket_id: str, tag: str):
    """DELETE /api/tickets/<id>/user_tags/<tag> — remover un tag."""
    try:
        from ticket_metadata_store import get_store
        store = get_store()
        meta = store.get(ticket_id)
        if meta is None or (meta.user_tags and tag not in meta.user_tags.tags):
            return jsonify({"ok": False, "error": f"tag '{tag}' no existe"}), 404

        store.remove_user_tag(ticket_id, tag)
        meta = store.get(ticket_id)
        return jsonify({
            "ok": True,
            "ticket_id": ticket_id,
            "user_tags": meta.user_tags.tags if meta and meta.user_tags else [],
            "updated_at": meta.updated_at if meta else None,
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/tickets/<ticket_id>/user_tags", methods=["PUT"])
def api_tickets_user_tags_put(ticket_id: str):
    """PUT /api/tickets/<id>/user_tags — reemplazar lista completa de tags."""
    try:
        from ticket_metadata_store import get_store
        from pydantic import ValidationError as PydanticError
        data = request.json or {}
        tags = data.get("tags", [])

        if not isinstance(tags, list):
            return jsonify({"ok": False, "error": "tags debe ser lista"}), 400

        store = get_store()
        store.set_user_tags(ticket_id, tags)
        meta = store.get(ticket_id)
        return jsonify({
            "ok": True,
            "ticket_id": ticket_id,
            "user_tags": meta.user_tags.tags if meta and meta.user_tags else [],
            "updated_at": meta.updated_at if meta else None,
        })
    except (ValueError, PydanticError) as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


if __name__ == "__main__":
    print("=" * 60)
    print(" Stacky — Pipeline Dashboard — http://localhost:5050")
    print("=" * 60)

    # ── Watcher principal: transiciona etapas PM→DEV→QA automáticamente ──────
    _transition_thread = threading.Thread(
        target=_stage_transition_watcher, daemon=True, name="stage-transition-watcher"
    )
    _transition_thread.start()
    print("[STARTUP] stage-transition-watcher iniciado")

    # ── Reconciliador: garantiza que folder y state.json no diverjan ─────────
    _reconciler_thread = threading.Thread(
        target=_pipeline_reconciler_loop, daemon=True, name="pipeline-reconciler"
    )
    _reconciler_thread.start()
    print("[STARTUP] pipeline-reconciler iniciado")

    # ── Watcher secundario: notificaciones Teams ──────────────────────────────
    _teams_thread = threading.Thread(
        target=_teams_notify_watcher, daemon=True, name="teams-notify-watcher"
    )
    _teams_thread.start()
    print("[STARTUP] teams-notify-watcher iniciado")

    # ── Auto Enter Daemon: Ctrl+Enter periódico en VS Code ────────────────────
    try:
        from auto_enter_daemon import get_auto_enter_daemon
        _auto_enter = get_auto_enter_daemon()
        # load_state() ya fue llamado por get_auto_enter_daemon() — arranca
        # solo si fue guardado como habilitado en la sesión anterior.
        print(
            f"[STARTUP] auto-enter-daemon cargado | "
            f"enabled={_auto_enter.enabled} | intervalo={_auto_enter.interval}s"
        )
    except Exception as _ae_err:
        print(f"[STARTUP] auto-enter-daemon no disponible: {_ae_err}")

    # ── Metadata Indexer: indexación background de commits, notas, etc ────────
    try:
        from ticket_metadata_indexer import MetadataIndexer
        _metadata_indexer = MetadataIndexer(period_sec=300, force_git_only=False)
        _metadata_indexer.start()
        print(
            f"[STARTUP] metadata-indexer iniciado | "
            f"period={_metadata_indexer.period_sec}s | "
            f"running={_metadata_indexer.is_running}"
        )
    except Exception as _mi_err:
        print(f"[STARTUP] metadata-indexer no disponible: {_mi_err}")

    app.run(host="0.0.0.0", port=5050, debug=False, use_reloader=False)
