"""
pipeline_runner.py — Orquestador del pipeline de agentes PM + DEV.

Uso:
    python pipeline_runner.py                       # todos los tickets en estado 'asignada'
    python pipeline_runner.py --ticket 0026772      # un ticket específico
    python pipeline_runner.py --reprocess 0026772   # reprocesar aunque ya esté completado/error
    python pipeline_runner.py --verbose             # muestra DEBUG + progreso de espera
"""

import argparse
import hashlib
import json as _json_cfg
import logging
import os
import socket as _socket
import sys
import time
from datetime import datetime

from pipeline_state import (load_state, save_state, set_ticket_state, mark_error,
                             set_ticket_priority, get_ticket_priority)
from ticket_detector import get_processable_tickets
from prompt_builder import (build_pm_prompt, build_dev_prompt, build_tester_prompt,
                            build_doc_agent_prompt, build_rework_prompt,
                            build_pm_revision_prompt)
from dba_agent import is_dba_required, get_dba_agent_name
from tech_lead_reviewer import is_tl_review_required, get_tl_agent_name
from copilot_bridge import invoke_agent

# Import defensivo: import de stacky_log por side-effect (configura logging)
try:
    import stacky_log  # noqa: F401
except Exception:
    pass

# F1-F4: wrappers de tracking de acciones. Defensive imports para permitir que
# pipeline_runner funcione aún si los módulos de observabilidad no están
# disponibles (degradación grácil).
try:
    from action_tracker import ActionContext as _ActionContext
    from pipeline_events import emit as _emit_event
    _HAS_ACTION_TRACKER = True
except Exception:
    _ActionContext = None
    _emit_event = None
    _HAS_ACTION_TRACKER = False

# Mapping de stage del pipeline a phase canónica de PipelineEvent.
# phase ∈ {"pm","dev","tester","dba","tl","deploy","sync","other"}
_STAGE_TO_PHASE = {
    "pm":           "pm",
    "pm_revision":  "pm",
    "dev":          "dev",
    "dev_rework":   "dev",
    "tester":       "tester",
    "doc":          "other",
    "dba":          "dba",
    "tl":           "tl",
}


def _invoke_with_tracking(prompt, *, agent_name, project_name,
                          new_conversation=False, ticket_id, ticket_folder, stage):
    """
    Envuelve ``invoke_agent(...)`` en una ``ActionContext`` para emitir eventos
    de progreso/éxito/error. Si el tracker no está disponible o la construcción
    del contexto falla, cae al invoke directo sin romper el flujo.
    """
    if not _HAS_ACTION_TRACKER or _ActionContext is None:
        return invoke_agent(
            prompt, agent_name=agent_name, project_name=project_name,
            new_conversation=new_conversation,
        )
    phase = _STAGE_TO_PHASE.get(stage, "other")
    try:
        ctx = _ActionContext(
            action=f"invoke_{stage}",
            ticket_id=ticket_id,
            project=project_name or None,
            phase=phase,
            ticket_folder=ticket_folder,
            correlation={"agent": agent_name or "", "stage": stage},
        )
    except Exception:
        return invoke_agent(
            prompt, agent_name=agent_name, project_name=project_name,
            new_conversation=new_conversation,
        )
    with ctx:
        try:
            ctx.progress(25, subaction="prompt_built")
        except Exception:
            pass
        ok = invoke_agent(
            prompt, agent_name=agent_name, project_name=project_name,
            new_conversation=new_conversation,
        )
        try:
            if ok:
                ctx.progress(90, subaction="invoke_sent")
            else:
                ctx.error(RuntimeError("invoke_agent returned False"))
        except Exception:
            pass
        return ok

# ── Configuración ─────────────────────────────────────────────────────────────

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
TICKETS_BASE   = os.path.join(os.path.dirname(__file__), "tickets")
STATE_PATH     = os.path.join(os.path.dirname(__file__), "pipeline", "state.json")
LOGS_DIR       = os.path.join(os.path.dirname(__file__), "pipeline", "logs")

PM_TIMEOUT     = 300   # 5 minutos — SOLO para el docstring del CLI (no se usa como límite)
DEV_TIMEOUT    = 600   # ídem
POLL_INTERVAL  = 5     # segundos entre checks
PLACEHOLDER    = "_A completar por PM_"

# Nombres de agentes/modos en VS Code Copilot Chat
PM_AGENT     = "PM-TLStack 1 PACIFICO"
DEV_AGENT    = "DevStack3"
TESTER_AGENT = "QA"
DOC_AGENT    = "DocStack"
DBA_AGENT    = "DevStack3"      # Y-04: fallback si no está configurado
TL_AGENT     = "PM-TL STack 3"  # Y-05: fallback TL agent

# ── Logging ───────────────────────────────────────────────────────────────────

def setup_logging(verbose: bool = False):
    os.makedirs(LOGS_DIR, exist_ok=True)
    log_file = os.path.join(LOGS_DIR, f"{datetime.now().strftime('%Y-%m-%d')}.log")

    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ]
    )

log = logging.getLogger(__name__)

# ── Detección de completitud PM ───────────────────────────────────────────────

def _folder_hashes(folder: str) -> dict:
    """Retorna dict {filename: sha256} para todos los .md y .sql del folder."""
    hashes = {}
    for fname in os.listdir(folder):
        if fname.endswith((".md", ".sql")):
            fpath = os.path.join(folder, fname)
            try:
                data = open(fpath, "rb").read()
                hashes[fname] = hashlib.sha256(data).hexdigest()
            except Exception:
                pass
    return hashes


def _has_placeholders(folder: str) -> bool:
    for fname in os.listdir(folder):
        if not fname.endswith((".md", ".sql")):
            continue
        fpath = os.path.join(folder, fname)
        try:
            content = open(fpath, encoding="utf-8").read()
            if PLACEHOLDER in content or "A completar por PM" in content:
                return True
        except Exception:
            pass
    return False


# ── M-01: Helpers de rework QA→DEV ──────────────────────────────────────────

def _parse_qa_verdict(folder: str) -> tuple[str, list]:
    """
    Parsea TESTER_COMPLETADO.md y devuelve el veredicto estructurado.
    Retorna (verdict, findings). verdict ∈ {"APROBADO", "CON OBSERVACIONES", "RECHAZADO", "DESCONOCIDO"}.
    """
    try:
        from output_validator import validate_stage_output
        val = validate_stage_output("tester", folder, "")
        verdict = getattr(val, "verdict", "DESCONOCIDO") or "DESCONOCIDO"
        findings = getattr(val, "qa_findings", []) or []
        return verdict, findings
    except Exception:
        pass
    tester_file = os.path.join(folder, "TESTER_COMPLETADO.md")
    if not os.path.exists(tester_file):
        return "DESCONOCIDO", []
    try:
        content = open(tester_file, encoding="utf-8").read().upper()
        for v in ("CON OBSERVACIONES", "RECHAZADO", "APROBADO"):
            if v in content:
                return v, []
        return "DESCONOCIDO", []
    except Exception:
        return "DESCONOCIDO", []


def _parse_qa_issues(folder: str) -> tuple:
    """Backwards-compatible wrapper. Devuelve (has_issues, findings)."""
    verdict, findings = _parse_qa_verdict(folder)
    return verdict in ("CON OBSERVACIONES", "RECHAZADO"), findings


def _wait_for_pm_completion(folder: str) -> bool:
    """
    Espera SIN TIMEOUT hasta que el PM complete los archivos.
    Condiciones de salida:
      OK:    PM_COMPLETADO.flag existe  <- señal explícita del agente (ÚNICA fuente de verdad)
      ERROR: PM_ERROR.flag existe       <- el agente reportó un error
    Nunca termina por timeout ni por fallback — solo el usuario puede interrumpir (Ctrl+C).
    """
    pm_ok_flag  = os.path.join(folder, "PM_COMPLETADO.flag")
    pm_err_flag = os.path.join(folder, "PM_ERROR.flag")
    elapsed = 0

    while True:
        time.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL

        # ── Error explícito del agente ────────────────────────────────
        if os.path.exists(pm_err_flag):
            sys.stdout.write("\n")
            try:
                reason = open(pm_err_flag, encoding="utf-8").read().strip()
            except Exception:
                reason = "PM_ERROR.flag creado (sin detalle)"
            log.error("PM reportó error: %s", reason)
            return False

        # ── Señal explícita OK del agente ───────────────────────────
        if os.path.exists(pm_ok_flag):
            sys.stdout.write("\n")
            log.info("PM completó — PM_COMPLETADO.flag detectado")
            return True

        mins, secs = divmod(elapsed, 60)
        sys.stdout.write(
            f"\r  [PM]  [{mins:02d}:{secs:02d} esperando] "
            f"| flag={'SI' if os.path.exists(pm_ok_flag) else 'NO'}"
        )
        sys.stdout.flush()


def _wait_for_dev_completion(folder: str) -> bool:
    """
    Espera SIN TIMEOUT hasta que el DEV cree DEV_COMPLETADO.md.
    Condiciones de salida:
      OK:    DEV_COMPLETADO.md existe
      ERROR: DEV_ERROR.flag existe
    Nunca termina por timeout.
    """
    sentinel     = os.path.join(folder, "DEV_COMPLETADO.md")
    dev_err_flag = os.path.join(folder, "DEV_ERROR.flag")
    elapsed = 0

    while True:
        time.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL

        if os.path.exists(dev_err_flag):
            sys.stdout.write("\n")
            try:
                reason = open(dev_err_flag, encoding="utf-8").read().strip()
            except Exception:
                reason = "DEV_ERROR.flag creado (sin detalle)"
            log.error("DEV reportó error: %s", reason)
            return False

        mins, secs = divmod(elapsed, 60)
        centinela_ok = os.path.exists(sentinel)
        sys.stdout.write(
            f"\r  [DEV] [{mins:02d}:{secs:02d} esperando] "
            f"| DEV_COMPLETADO.md={'ENCONTRADO' if centinela_ok else 'esperando...'}"
        )
        sys.stdout.flush()

        if centinela_ok:
            sys.stdout.write("\n")
            log.info("DEV completó — DEV_COMPLETADO.md encontrado")
            return True


def _wait_for_tester_completion(folder: str) -> bool:
    """
    Espera SIN TIMEOUT hasta que el TESTER cree TESTER_COMPLETADO.md.
    Condiciones de salida:
      OK:    TESTER_COMPLETADO.md existe
      ERROR: TESTER_ERROR.flag existe
    """
    sentinel       = os.path.join(folder, "TESTER_COMPLETADO.md")
    tester_err_flag = os.path.join(folder, "TESTER_ERROR.flag")
    elapsed = 0

    while True:
        time.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL

        if os.path.exists(tester_err_flag):
            sys.stdout.write("\n")
            try:
                reason = open(tester_err_flag, encoding="utf-8").read().strip()
            except Exception:
                reason = "TESTER_ERROR.flag creado (sin detalle)"
            log.error("TESTER reportó error: %s", reason)
            return False

        mins, secs = divmod(elapsed, 60)
        centinela_ok = os.path.exists(sentinel)
        sys.stdout.write(
            f"\r  [QA]  [{mins:02d}:{secs:02d} esperando] "
            f"| TESTER_COMPLETADO.md={'ENCONTRADO' if centinela_ok else 'esperando...'}"
        )
        sys.stdout.flush()

        if centinela_ok:
            sys.stdout.write("\n")
            log.info("TESTER completó — TESTER_COMPLETADO.md encontrado")
            return True


def _wait_for_doc_completion(folder: str) -> bool:
    """
    Espera SIN TIMEOUT hasta que el DOC cree DOC_COMPLETADO.flag.
    Condiciones de salida:
      OK:    DOC_COMPLETADO.flag existe
      ERROR: DOC_ERROR.flag existe
    """
    sentinel      = os.path.join(folder, "DOC_COMPLETADO.flag")
    doc_err_flag  = os.path.join(folder, "DOC_ERROR.flag")
    elapsed = 0

    while True:
        time.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL

        if os.path.exists(doc_err_flag):
            sys.stdout.write("\n")
            try:
                reason = open(doc_err_flag, encoding="utf-8").read().strip()
            except Exception:
                reason = "DOC_ERROR.flag creado (sin detalle)"
            log.error("DOC reportó error: %s", reason)
            return False

        mins, secs = divmod(elapsed, 60)
        centinela_ok = os.path.exists(sentinel)
        sys.stdout.write(
            f"\r  [DOC] [{mins:02d}:{secs:02d} esperando] "
            f"| DOC_COMPLETADO.flag={'ENCONTRADO' if centinela_ok else 'esperando...'}"
        )
        sys.stdout.flush()

        if centinela_ok:
            sys.stdout.write("\n")
            log.info("DOC completó — DOC_COMPLETADO.flag encontrado")
            return True


# ── Y-04: Wait DBA / Y-05: Wait TL ───────────────────────────────────────────

def _wait_for_dba_completion(folder: str) -> bool:
    """Espera hasta que el DBA Agent cree DB_READY.flag o DBA_ERROR.flag."""
    sentinel     = os.path.join(folder, "DB_READY.flag")
    dba_err_flag = os.path.join(folder, "DBA_ERROR.flag")
    elapsed = 0
    while True:
        time.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL
        if os.path.exists(dba_err_flag):
            sys.stdout.write("\n")
            try:
                reason = open(dba_err_flag, encoding="utf-8").read().strip()
            except Exception:
                reason = "DBA_ERROR.flag creado (sin detalle)"
            log.error("DBA reportó error: %s", reason)
            return False
        mins, secs = divmod(elapsed, 60)
        centinela_ok = os.path.exists(sentinel)
        sys.stdout.write(
            f"\r  [DBA] [{mins:02d}:{secs:02d} esperando] "
            f"| DB_READY.flag={'ENCONTRADO' if centinela_ok else 'esperando...'}"
        )
        sys.stdout.flush()
        if centinela_ok:
            sys.stdout.write("\n")
            log.info("DBA completó — DB_READY.flag encontrado")
            return True


def _wait_for_tl_completion(folder: str) -> bool:
    """Espera TL_APPROVED.flag o TL_REJECTED.md del Tech Lead."""
    approved = os.path.join(folder, "TL_APPROVED.flag")
    rejected = os.path.join(folder, "TL_REJECTED.md")
    elapsed = 0
    while True:
        time.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL
        if os.path.exists(approved):
            sys.stdout.write("\n")
            log.info("Tech Lead APROBÓ — TL_APPROVED.flag detectado")
            return True
        if os.path.exists(rejected):
            sys.stdout.write("\n")
            log.info("Tech Lead RECHAZÓ — TL_REJECTED.md detectado (redirigiendo a PM)")
            return True  # True = completó (el state determinará el siguiente paso)
        mins, secs = divmod(elapsed, 60)
        sys.stdout.write(
            f"\r  [TL]  [{mins:02d}:{secs:02d} esperando] "
            f"| TL_APPROVED={'SÍ' if os.path.exists(approved) else 'NO'}"
            f" | TL_REJECTED={'SÍ' if os.path.exists(rejected) else 'NO'}"
        )
        sys.stdout.flush()


# ── Orquestador ───────────────────────────────────────────────────────────────

def _resolve_kb_path(ticket_folder: str) -> str:
    """
    Resuelve la ruta de KNOWLEDGE_BASE.md para el proyecto del ticket.
    Sube desde ticket_folder buscando la carpeta 'projects/{PROJECT}' —
    es decir, el primer ancestro que tenga 'projects' como padre.
    Si no encuentra la estructura esperada, lo deja junto al ticket.
    """
    p = os.path.abspath(ticket_folder)
    # Subir hasta encontrar un directorio cuyo padre se llame 'projects'
    for _ in range(10):
        parent = os.path.dirname(p)
        if os.path.basename(parent).lower() == "projects":
            # p es la carpeta del proyecto (ej: .../projects/RSMOBILENET)
            return os.path.join(p, "KNOWLEDGE_BASE.md")
        if parent == p:
            break
        p = parent
    # Fallback: junto al ticket
    return os.path.join(ticket_folder, "KNOWLEDGE_BASE.md")


def _read_ticket_title(folder: str, ticket_id: str) -> str:
    """Lee el título desde INC-{id}.md."""
    inc_file = os.path.join(folder, f"INC-{ticket_id}.md")
    if not os.path.exists(inc_file):
        return "(sin título)"
    try:
        for line in open(inc_file, encoding="utf-8"):
            line = line.strip()
            if line.startswith("**Título:**"):
                return line.replace("**Título:**", "").strip()
            if line.startswith("# "):
                return line.lstrip("# ").strip()
    except Exception:
        pass
    return "(sin título)"


def _select_tickets_interactive(tickets: list, state: dict) -> list:
    """
    Muestra la lista de tickets pendientes y pregunta al usuario en qué orden procesarlos.
    Retorna la lista reordenada según la elección.

    Opciones:
      - Enter sola             → procesar en el orden mostrado (prioridad guardada)
      - Números: "2 1 3"      → procesar en ese orden (sólo los seleccionados)
      - "q"                   → salir sin procesar
    """
    print()
    print("═" * 62)
    print("  TICKETS PENDIENTES — Elegir orden de procesamiento")
    print("═" * 62)

    # Ordenar por prioridad guardada (si existe)
    tickets_sorted = sorted(tickets,
                            key=lambda t: get_ticket_priority(state, t["ticket_id"]))

    for i, t in enumerate(tickets_sorted, 1):
        titulo = _read_ticket_title(t["folder"], t["ticket_id"])
        estado = t["pipeline_estado"]
        prio   = get_ticket_priority(state, t["ticket_id"])
        prio_str = f" [prio={prio}]" if prio != 9999 else ""
        print(f"  {i:2d})  #{t['ticket_id']}  {estado:<18}  {titulo[:44]}{prio_str}")

    print("═" * 62)
    print("  Ingresu00e1 el orden (ej: 2 1 3), Enter para usar el orden actual, 'q' para salir:")
    print("  (tip: podés ingresar solo algunos, ej: '2' para procesar solo el segundo)")
    print()

    try:
        raw = input("  → ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\n  Cancelado.")
        return []

    if raw.lower() == "q":
        print("  Saliendo sin procesar.")
        return []

    if not raw:
        # Orden actual, guardar prioridades
        for i, t in enumerate(tickets_sorted, 1):
            set_ticket_priority(state, t["ticket_id"], i)
        save_state(STATE_PATH, state)
        return tickets_sorted

    # Parsear los números ingresados
    try:
        indices = [int(x) for x in raw.split()]
    except ValueError:
        print("  Formato inválido — usando orden actual.")
        return tickets_sorted

    # Validar que sean índices válidos
    invalid = [n for n in indices if n < 1 or n > len(tickets_sorted)]
    if invalid:
        print(f"  Números inválidos: {invalid} — usando orden actual.")
        return tickets_sorted

    # Reconstruir lista en el orden elegido
    ordered = [tickets_sorted[i - 1] for i in indices]

    # Guardar prioridades en state para el dashboard
    for i, t in enumerate(ordered, 1):
        set_ticket_priority(state, t["ticket_id"], i)
    save_state(STATE_PATH, state)

    print()
    print("  Orden seleccionado:")
    for i, t in enumerate(ordered, 1):
        titulo = _read_ticket_title(t["folder"], t["ticket_id"])
        print(f"    {i}) #{t['ticket_id']} — {titulo[:50]}")
    print()

    return ordered


# ── Registro de watchers activos (un thread por ticket) ───────────────────────
import threading as _threading
_active_watchers: dict[str, _threading.Thread] = {}
_watchers_lock = _threading.Lock()


def _auto_advance(tid: str, folder: str, current_stage: str,
                  state_path: str, workspace_root: str,
                  agents: dict, project_name: str) -> None:
    """
    Hilo de fondo: espera el flag de completado de current_stage y luego
    llama a process_ticket() para que avance solo a la siguiente etapa.
    Se registra en _active_watchers para evitar duplicados.
    """
    wait_fn = {
        "pm":          _wait_for_pm_completion,
        "dev":         _wait_for_dev_completion,
        "dev_rework":  _wait_for_dev_completion,   # M-01: rework usa el mismo sentinel
        "tester":      _wait_for_tester_completion,
        "doc":         _wait_for_doc_completion,
        "pm_revision": _wait_for_pm_completion,   # Y-01: usa el mismo waitfn
        "dba":         _wait_for_dba_completion,  # Y-04
        "tl":          _wait_for_tl_completion,   # Y-05
    }.get(current_stage)

    if wait_fn is None:
        return

    log.info("[AUTO-ADVANCE] Watcher iniciado para #%s etapa %s", tid, current_stage.upper())

    try:
        ok = wait_fn(folder)
    except Exception as e:
        log.error("[AUTO-ADVANCE] Error esperando %s de #%s: %s", current_stage, tid, e)
        ok = False

    # Limpiar registro de watcher activo
    with _watchers_lock:
        _active_watchers.pop(tid, None)

    if not ok:
        log.warning("[AUTO-ADVANCE] #%s: %s reportó error — no se avanza automáticamente",
                    tid, current_stage.upper())
        return

    # Re-cargar state fresco del disco antes de avanzar
    fresh_state = load_state(state_path)
    pip_est = fresh_state.get("tickets", {}).get(tid, {}).get("estado", "")

    # ── Y-01/M-01: Veredicto QA bifurca el flujo ─────────────────────────────
    # APROBADO          → continúa al auto-advance normal (doc)
    # CON OBSERVACIONES → se acepta como OK (observaciones quedan anotadas en el
    #                     reporte pero no bloquean el pipeline). Continúa al doc
    #                     como si fuera APROBADO y arranca el siguiente ticket.
    # RECHAZADO         → pm_revision inmediato (replanteo de fondo)
    if current_stage == "tester" and ok:
        verdict, qa_findings = _parse_qa_verdict(folder)
        # Guardar el veredicto en el state aun cuando sea OBSERVACIONES/APROBADO,
        # para que el dashboard pueda mostrarlo (banner amarillo para OBS, etc.)
        if verdict in ("APROBADO", "CON OBSERVACIONES"):
            try:
                fresh_state.setdefault("tickets", {}).setdefault(tid, {})["last_qa_verdict"] = verdict
                fresh_state["tickets"][tid]["qa_findings"] = qa_findings
                save_state(state_path, fresh_state)
            except Exception:
                pass
            if verdict == "CON OBSERVACIONES":
                log.info("[Y-01] #%s: QA CON OBSERVACIONES → aceptado como OK (no rework)", tid)
        if verdict == "RECHAZADO":
            # Duración real del ciclo DEV→QA para métricas de iteración
            iter_started_iso = fresh_state.get("tickets", {}).get(tid, {}).get("iteration_started_at")
            duration_sec = None
            if iter_started_iso:
                try:
                    duration_sec = (datetime.now() - datetime.fromisoformat(iter_started_iso)).total_seconds()
                except Exception:
                    duration_sec = None

            try:
                from correction_memory import CorrectionMemory
                cm = CorrectionMemory(folder)
                cycle_num = cm.get_cycle_count() + 1
                cm.add_cycle(cycle_num, qa_findings, qa_verdict=verdict, duration_sec=duration_sec)

                if cm.check_stagnation():
                    log.warning("[Y-01] #%s: STAGNATION tras %d ciclos — intervención manual", tid, cycle_num)
                    state_to_update = load_state(state_path)
                    set_ticket_state(state_to_update, tid, "stagnation_detected", folder=folder)
                    save_state(state_path, state_to_update)
                    try:
                        from notifier import notify
                        notify(f"⚠️ Ticket #{tid} — STAGNATION",
                               f"Sin progreso en {cycle_num} ciclos (último: {verdict}). Requiere intervención manual.",
                               level="error", ticket_id=tid)
                    except Exception:
                        pass
                    return

                accumulated_issues = cm.get_all_issues()
                efficiency = cm.get_efficiency_score()
                log.info("[Y-01] #%s: QA verdict=%s ciclo %d — issues acum: %d, efficiency: %.0f%%",
                         tid, verdict, cycle_num, len(accumulated_issues), efficiency * 100)
            except Exception as cm_err:
                log.warning("[Y-01] Error CorrectionMemory para #%s: %s", tid, cm_err)
                accumulated_issues = qa_findings

            # Registrar iteración cerrada (timing + contador) en state
            try:
                from pipeline_state import record_iteration_end
                record_iteration_end(fresh_state, tid, qa_verdict=verdict,
                                     findings=qa_findings, duration_sec=duration_sec)
            except Exception as ier:
                log.warning("[Y-01] record_iteration_end falló para #%s: %s", tid, ier)

            # Límite de reintentos (salvaguarda adicional a check_stagnation)
            try:
                _cfg = _json_cfg.load(open(os.path.join(os.path.dirname(__file__), "config.json"),
                                           encoding="utf-8"))
                max_rework = int(_cfg.get("pipeline", {}).get("max_rework_cycles", 999))
            except Exception:
                max_rework = 999

            rework_count = fresh_state.get("tickets", {}).get(tid, {}).get("rework_count", 0)
            if rework_count >= max_rework:
                log.error("[Y-01] #%s: max_rework_cycles (%d) alcanzado tras veredicto %s — "
                          "marcando stagnation_detected y notificando",
                          tid, max_rework, verdict)
                fresh_state.setdefault("tickets", {}).setdefault(tid, {})["qa_findings"] = qa_findings
                fresh_state["tickets"][tid]["last_qa_verdict"] = verdict
                set_ticket_state(fresh_state, tid, "stagnation_detected", folder=folder)
                save_state(state_path, fresh_state)
                try:
                    from notifier import notify
                    notify(f"⛔ Ticket #{tid} — max_rework_cycles ({max_rework}) alcanzado",
                           f"Último veredicto QA: {verdict}. Requiere intervención manual.",
                           level="error", ticket_id=tid)
                except Exception:
                    pass
                return

            fresh_state.setdefault("tickets", {}).setdefault(tid, {})["qa_findings"] = qa_findings
            fresh_state["tickets"][tid]["accumulated_issues"] = accumulated_issues
            fresh_state["tickets"][tid]["last_qa_verdict"] = verdict

            log.info("[Y-01] #%s: QA RECHAZADO → escalando a PM revision (replanteo de fondo)", tid)
            set_ticket_state(fresh_state, tid, "pm_revision", folder=folder)
            save_state(state_path, fresh_state)
            next_state = "pm_revision"

            next_t = {"ticket_id": tid, "folder": folder, "pipeline_estado": next_state}
            try:
                process_ticket(next_t, load_state(state_path),
                               state_path=state_path, workspace_root=workspace_root,
                               agents=agents, project_name=project_name)
            except Exception as e:
                log.error("[Y-01] Error lanzando '%s' para #%s: %s", next_state, tid, e)
            return
    # ── Fin check rework ───────────────────────────────────────────────────────

    # ── Y-05: Para TL, determinar el next_state según flag generado ───────────
    if current_stage == "tl" and ok:
        tl_folder = folder
        approved_flag = os.path.join(tl_folder, "TL_APPROVED.flag")
        rejected_file = os.path.join(tl_folder, "TL_REJECTED.md")
        if os.path.exists(rejected_file):
            set_ticket_state(fresh_state, tid, "tl_rechazado", folder=folder)
        else:
            set_ticket_state(fresh_state, tid, "tl_aprobado", folder=folder)
        save_state(state_path, fresh_state)
        next_t = {"ticket_id": tid, "folder": folder,
                  "pipeline_estado": fresh_state["tickets"][tid]["estado"]}
        try:
            process_ticket(next_t, load_state(state_path),
                           state_path=state_path, workspace_root=workspace_root,
                           agents=agents, project_name=project_name)
        except Exception as e:
            log.error("[TL] Error avanzando tras TL review para #%s: %s", tid, e)
        return
    # ── Fin Y-05 ─────────────────────────────────────────────────────────────

    # Marcar etapa completada en el state si todavía figura como "en_proceso"
    if pip_est in (f"{current_stage}_en_proceso",):
        set_ticket_state(fresh_state, tid, f"{current_stage}_completado", folder=folder)
        save_state(state_path, fresh_state)
        log.info("[AUTO-ADVANCE] #%s: state actualizado → %s_completado", tid, current_stage)

    # Construir ticket dict para la siguiente llamada
    next_ticket = {"ticket_id": tid, "folder": folder,
                   "pipeline_estado": f"{current_stage}_completado"}
    try:
        process_ticket(next_ticket, load_state(state_path),
                       state_path=state_path,
                       workspace_root=workspace_root,
                       agents=agents,
                       project_name=project_name)
    except Exception as e:
        log.error("[AUTO-ADVANCE] Error lanzando siguiente etapa para #%s: %s", tid, e)


def process_ticket(ticket: dict, state: dict,
                   state_path: str = None, workspace_root: str = None,
                   agents: dict = None, project_name: str = None,
                   stage: str = None):
    """
    Lanza la próxima etapa pendiente del ticket.
    Después de invocar el agente, arranca un thread de fondo (_auto_advance)
    que espera el flag de completado y avanza solo a la siguiente etapa.
    """
    tid    = ticket["ticket_id"]
    folder = ticket["folder"]

    _state_path     = state_path     or STATE_PATH
    _workspace_root = workspace_root or WORKSPACE_ROOT
    _pm_agent       = (agents or {}).get("pm",     PM_AGENT)
    _dev_agent      = (agents or {}).get("dev",    DEV_AGENT)
    _tester_agent   = (agents or {}).get("tester", TESTER_AGENT)
    _doc_agent      = (agents or {}).get("doc",    DOC_AGENT)
    _dba_agent      = (agents or {}).get("dba",    DBA_AGENT)   # Y-04
    _tl_agent       = (agents or {}).get("tl",     TL_AGENT)    # Y-05
    _project_name   = project_name   or ""

    pip_est = state.get("tickets", {}).get(tid, {}).get("estado", "pendiente_pm")

    # Determinar etapa a ejecutar
    if stage:
        next_stage = stage
    elif pip_est in ("pendiente_pm", "error_pm"):
        next_stage = "pm"
    elif pip_est == "pm_completado":
        # Y-05: TL primero → Y-04: DBA segundo → DEV
        if is_tl_review_required(folder, tid):
            next_stage = "tl"
        elif is_dba_required(folder, tid):
            next_stage = "dba"
        else:
            next_stage = "dev"
    # ── Y-04: DBA Especialista ────────────────────────────────────────────────
    elif pip_est == "dba_completado":
        next_stage = "dev"
    elif pip_est == "error_dba":
        next_stage = "dba"  # reintentar DBA en caso de error
    # ── Y-05: Tech Lead Reviewer ──────────────────────────────────────────────
    elif pip_est == "tl_aprobado":
        next_stage = "dev"  # TL aprobó → avanzar a DEV
    elif pip_est == "tl_rechazado":
        next_stage = "pm"   # TL rechazó → volver a PM para replantear
    # ── Fin Y-04/Y-05 ─────────────────────────────────────────────────────────
    elif pip_est in ("dev_completado", "error_dev"):
        next_stage = "tester"
    elif pip_est in ("tester_completado", "error_doc"):
        next_stage = "doc"
    # ── M-01: Estados de rework QA→DEV ────────────────────────────────────────
    elif pip_est == "qa_rework":
        next_stage = "dev_rework"
    elif pip_est == "dev_rework_completado":
        next_stage = "tester"  # re-lanzar QA tras rework
    # ── Fin estados rework ────────────────────────────────────────────────────
    # ── Y-01: PM revision (replanteo completo tras múltiples reworks) ─────────
    elif pip_est == "pm_revision":
        next_stage = "pm_revision"
    elif pip_est == "pm_revision_completado":
        next_stage = "dev"  # relanzar DEV con el nuevo análisis de PM
    # ── Fin Y-01 ──────────────────────────────────────────────────────────────
    elif pip_est.endswith("_en_proceso"):
        # Agente ya corriendo — verificar si ya hay un watcher activo
        with _watchers_lock:
            if tid in _active_watchers and _active_watchers[tid].is_alive():
                log.info("[PIPELINE] #%s ya tiene watcher activo para '%s' — ignorando llamada duplicada",
                         tid, pip_est)
                return
        # No hay watcher → relanzar el watcher para el agente en curso
        running_stage = pip_est.replace("_en_proceso", "")
        log.warning("[PIPELINE] #%s en '%s' sin watcher activo — re-registrando watcher",
                    tid, pip_est)
        _start_watcher(tid, folder, running_stage, _state_path, _workspace_root,
                       agents or {}, _project_name)
        return
    else:
        log.info("[PIPELINE] Ticket %s está en estado '%s', no hay etapa siguiente automática.",
                 tid, pip_est)
        return

    def _save():
        save_state(_state_path, state)

    def _stamp(etapa, evento):
        entry = state.setdefault("tickets", {}).setdefault(tid, {})
        entry[f"{etapa}_{evento}_at"] = datetime.now().isoformat()

    log.info("=" * 50)
    log.info("Ticket %s — lanzando etapa: %s", tid, next_stage.upper())

    if next_stage == "pm":
        _stamp("pm", "inicio")
        set_ticket_state(state, tid, "pm_en_proceso", folder=folder)
        _save()
        prompt = build_pm_prompt(folder, tid, _workspace_root)
        if not _invoke_with_tracking(prompt, agent_name=_pm_agent,
                                     project_name=_project_name,
                                     new_conversation=True,
                                     ticket_id=tid, ticket_folder=folder,
                                     stage="pm"):
            mark_error(state, tid, "pm", "No se pudo invocar al agente vía UI")
            _save()
            log.error("[PM] Error invocando agente para %s", tid)
            return
        log.info("[PM] Agente invocado para %s — watcher esperando PM_COMPLETADO.flag", tid)

    elif next_stage == "dev":
        _stamp("dev", "inicio")
        set_ticket_state(state, tid, "dev_en_proceso")
        _save()
        prompt = build_dev_prompt(folder, tid, _workspace_root)
        if not _invoke_with_tracking(prompt, agent_name=_dev_agent,
                                     project_name=_project_name,
                                     ticket_id=tid, ticket_folder=folder,
                                     stage="dev"):
            mark_error(state, tid, "dev", "No se pudo invocar al agente vía UI")
            _save()
            log.error("[DEV] Error invocando agente para %s", tid)
            return
        log.info("[DEV] Agente invocado para %s — watcher esperando DEV_COMPLETADO.md", tid)

    elif next_stage == "tester":
        _stamp("tester", "inicio")
        set_ticket_state(state, tid, "tester_en_proceso")
        _save()
        prompt = build_tester_prompt(folder, tid, _workspace_root)
        if not _invoke_with_tracking(prompt, agent_name=_tester_agent,
                                     project_name=_project_name,
                                     ticket_id=tid, ticket_folder=folder,
                                     stage="tester"):
            mark_error(state, tid, "tester", "No se pudo invocar al agente vía UI")
            _save()
            log.error("[TESTER] Error invocando agente para %s", tid)
            return
        log.info("[TESTER] Agente invocado para %s — watcher esperando TESTER_COMPLETADO.md", tid)

    elif next_stage == "doc":
        _stamp("doc", "inicio")
        set_ticket_state(state, tid, "doc_en_proceso")
        _save()
        kb_path = _resolve_kb_path(folder)
        prompt = build_doc_agent_prompt(folder, tid, _workspace_root, kb_path)
        if not _invoke_with_tracking(prompt, agent_name=_doc_agent,
                                     project_name=_project_name,
                                     ticket_id=tid, ticket_folder=folder,
                                     stage="doc"):
            mark_error(state, tid, "doc", "No se pudo invocar al agente vía UI")
            _save()
            log.error("[DOC] Error invocando agente para %s", tid)
            return
        log.info("[DOC] Agente invocado para %s — watcher esperando DOC_COMPLETADO.flag", tid)

    # ── Y-01: PM Revision — replanteo completo tras múltiples reworks ────────
    elif next_stage == "pm_revision":
        ticket_entry    = state.get("tickets", {}).get(tid, {})
        accumulated     = ticket_entry.get("accumulated_issues", [])
        rework_count    = ticket_entry.get("rework_count", 0)
        cycle_num       = rework_count + 1
        _stamp("pm_revision", "inicio")
        set_ticket_state(state, tid, "pm_revision_en_proceso", folder=folder)
        _save()
        # Renombrar PM_COMPLETADO.flag para que PM regenere
        pm_flag = os.path.join(folder, "PM_COMPLETADO.flag")
        if os.path.exists(pm_flag):
            os.rename(pm_flag, pm_flag + ".prev")
        prompt = build_pm_revision_prompt(folder, tid, _workspace_root,
                                          accumulated, cycle_num)
        if not _invoke_with_tracking(prompt, agent_name=_pm_agent,
                                     project_name=_project_name,
                                     new_conversation=True,
                                     ticket_id=tid, ticket_folder=folder,
                                     stage="pm_revision"):
            mark_error(state, tid, "pm", "No se pudo invocar PM revision vía UI")
            _save()
            log.error("[PM_REVISION] Error invocando PM revision para %s", tid)
            return
        log.info("[PM_REVISION] PM revision ciclo %d lanzada para %s", cycle_num, tid)
    # ── Fin Y-01 ─────────────────────────────────────────────────────────────

    # ── M-01: Rework DEV tras issues reportados por QA ────────────────────────
    elif next_stage == "dev_rework":
        ticket_entry = state.get("tickets", {}).get(tid, {})
        rework_count = ticket_entry.get("rework_count", 0) + 1
        qa_findings  = ticket_entry.get("qa_findings", [])
        _stamp("dev_rework", "inicio")
        set_ticket_state(state, tid, "dev_rework_en_proceso", folder=folder)
        state.setdefault("tickets", {}).setdefault(tid, {})["rework_count"] = rework_count
        _save()
        # Renombrar TESTER_COMPLETADO.md para que QA re-valide desde cero
        tester_flag = os.path.join(folder, "TESTER_COMPLETADO.md")
        if os.path.exists(tester_flag):
            os.rename(tester_flag, tester_flag + ".prev")
        prompt = build_rework_prompt(folder, tid, _workspace_root, qa_findings, rework_count)
        if not _invoke_with_tracking(prompt, agent_name=_dev_agent,
                                     project_name=_project_name,
                                     ticket_id=tid, ticket_folder=folder,
                                     stage="dev_rework"):
            mark_error(state, tid, "dev", "No se pudo invocar al agente DEV para rework vía UI")
            _save()
            log.error("[DEV_REWORK] Error invocando agente de rework para %s", tid)
            return
        log.info("[DEV_REWORK] Agente invocado para rework #%d de %s — watcher esperando DEV_COMPLETADO.md",
                 rework_count, tid)
    # ── Fin bloque rework ─────────────────────────────────────────────────────

    # ── Y-04: Agente DBA Especialista ─────────────────────────────────────────
    elif next_stage == "dba":
        from prompt_builder import build_dba_prompt as _build_dba
        _stamp("dba", "inicio")
        set_ticket_state(state, tid, "dba_en_proceso", folder=folder)
        _save()
        prompt = _build_dba(folder, tid, _workspace_root)
        if not _invoke_with_tracking(prompt, agent_name=_dba_agent,
                                     project_name=_project_name,
                                     ticket_id=tid, ticket_folder=folder,
                                     stage="dba"):
            mark_error(state, tid, "dba", "No se pudo invocar al agente DBA vía UI")
            _save()
            log.error("[DBA] Error invocando agente DBA para %s", tid)
            return
        log.info("[DBA] Agente DBA invocado para %s — esperando DB_READY.flag", tid)
    # ── Fin Y-04 ──────────────────────────────────────────────────────────────

    # ── Y-05: Tech Lead Reviewer ───────────────────────────────────────────────
    elif next_stage == "tl":
        from prompt_builder import build_tl_prompt as _build_tl
        _stamp("tl", "inicio")
        set_ticket_state(state, tid, "tl_review_en_proceso", folder=folder)
        _save()
        prompt = _build_tl(folder, tid, _workspace_root)
        if not _invoke_with_tracking(prompt, agent_name=_tl_agent,
                                     project_name=_project_name,
                                     new_conversation=False,
                                     ticket_id=tid, ticket_folder=folder,
                                     stage="tl"):
            mark_error(state, tid, "tl", "No se pudo invocar al agente TL vía UI")
            _save()
            log.error("[TL] Error invocando agente TL para %s", tid)
            return
        log.info("[TL] Tech Lead Review invocado para %s — esperando TL_APPROVED.flag o TL_REJECTED.md", tid)
    # ── Fin Y-05 ──────────────────────────────────────────────────────────────

    # Arrancar watcher de auto-avance en background
    _start_watcher(tid, folder, next_stage, _state_path, _workspace_root,
                   agents or {}, _project_name)


def _start_watcher(tid: str, folder: str, stage: str,
                   state_path: str, workspace_root: str,
                   agents: dict, project_name: str) -> None:
    """Registra y arranca el thread _auto_advance para el ticket/etapa dados."""
    with _watchers_lock:
        existing = _active_watchers.get(tid)
        if existing and existing.is_alive():
            log.debug("[WATCHER] #%s ya tiene watcher vivo — no se duplica", tid)
            return
        t = _threading.Thread(
            target=_auto_advance,
            args=(tid, folder, stage, state_path, workspace_root, agents, project_name),
            daemon=True,
            name=f"auto-advance-{tid}-{stage}",
        )
        _active_watchers[tid] = t
    t.start()
    log.info("[WATCHER] #%s: thread de auto-avance iniciado para etapa %s", tid, stage.upper())


def run_pipeline(target_ticket: str = None, force_reprocess: list = None,
                 verbose: bool = False, interactive: bool = False,
                 tickets_base: str = None, state_path: str = None,
                 workspace_root: str = None, agents: dict = None,
                 project_name: str = None, stage: str = None):
    """Punto de entrada principal — fire-and-forget por etapa."""
    setup_logging(verbose=verbose)
    force_reprocess = force_reprocess or []

    _tickets_base   = tickets_base   or TICKETS_BASE
    _state_path     = state_path     or STATE_PATH
    _workspace_root = workspace_root or WORKSPACE_ROOT
    _agents         = agents         or {}
    _project_name   = project_name   or ""

    from ticket_detector import ESTADO_PROCESABLE
    log.info("Pipeline iniciado — procesando solo estado del tracker: '%s'", ESTADO_PROCESABLE)
    log.info("tickets_base = %s", _tickets_base)
    log.info("state_path   = %s", _state_path)

    state = load_state(_state_path)

    tickets = get_processable_tickets(_tickets_base, state, force_reprocess)

    if target_ticket:
        tickets = [t for t in tickets if t["ticket_id"] == target_ticket]
        if not tickets:
            log.warning("Ticket %s no encontrado o no elegible (estado del tracker != '%s' o ya procesado)",
                        target_ticket, ESTADO_PROCESABLE)
            return

    if not tickets:
        log.info("No hay tickets en estado '%s' pendientes de procesamiento", ESTADO_PROCESABLE)
        return

    if (interactive or len(tickets) > 1) and not target_ticket:
        tickets = _select_tickets_interactive(tickets, state)
        if not tickets:
            log.info("Sin tickets seleccionados. Finalizando.")
            return
    else:
        tickets = sorted(tickets,
                         key=lambda t: get_ticket_priority(state, t["ticket_id"]))

    log.info("Tickets a procesar (%d): %s",
             len(tickets), [t["ticket_id"] for t in tickets])

    for ticket in tickets:
        try:
            process_ticket(ticket, state,
                           state_path=_state_path,
                           workspace_root=_workspace_root,
                           agents=_agents,
                           project_name=_project_name,
                           stage=stage)
        except Exception as e:
            log.error("Error inesperado procesando %s: %s", ticket["ticket_id"], e, exc_info=True)
            mark_error(state, ticket["ticket_id"], "pm", f"Error inesperado: {e}")
            save_state(_state_path, state)

    log.info("Pipeline finalizado")


# ── Helpers SEQ-01: Production Mode Guard ────────────────────────────────────

def _check_production_mode() -> bool:
    """Retorna True si estamos en modo producción (CLI deshabilitado)."""
    try:
        cfg_path = os.path.join(os.path.dirname(__file__), "config.json")
        cfg = _json_cfg.load(open(cfg_path, encoding="utf-8"))
        return cfg.get("runtime", {}).get("production_mode", False) or \
               cfg.get("runtime", {}).get("disable_cli_runner", False)
    except Exception:
        return False


def _is_dashboard_active(port: int = 5050) -> bool:
    """Retorna True si el dashboard Flask ya está corriendo en el puerto indicado."""
    try:
        with _socket.create_connection(("localhost", port), timeout=0.5):
            return True
    except (ConnectionRefusedError, OSError):
        return False


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if _check_production_mode():
        print("ERROR: pipeline_runner.py CLI está deshabilitado en modo producción.")
        print("Usar el dashboard (localhost:5050) o POST /api/run_pipeline para lanzar tickets.")
        print("Para desarrollo/debug: setear STACKY_ENV=debug o runtime.production_mode=false en config.json")
        sys.exit(1)

    if _is_dashboard_active():
        print("ADVERTENCIA: El dashboard de Stacky está activo en localhost:5050.")
        print("Ejecutar el CLI simultáneamente puede causar invocaciones duplicadas.")
        print("Si estás seguro, ignorá esta advertencia. Continuando en 3 segundos...")
        time.sleep(3)

    parser = argparse.ArgumentParser(
        description="Pipeline de agentes PM+DEV — procesa tickets en estado 'asignada'"
    )
    parser.add_argument("--ticket",      help="Procesar un ticket específico por ID")
    parser.add_argument("--reprocess",   help="Reprocesar un ticket aunque ya esté completado/error")
    parser.add_argument("--interactive", action="store_true",
                        help="Mostrar selector de tickets aunque solo haya uno")
    parser.add_argument("--verbose",     action="store_true",
                        help="Mostrar logs DEBUG + progreso detallado en consola")
    args = parser.parse_args()

    reprocess = [args.reprocess] if args.reprocess else []
    run_pipeline(target_ticket=args.ticket, force_reprocess=reprocess,
                 verbose=args.verbose, interactive=args.interactive)
