"""
ticket_detector.py — Detecta tickets pendientes de procesamiento por el pipeline.
"""

import os

PLACEHOLDER = "_A completar por PM_"
PM_FILES = [
    "INCIDENTE.md",
    "ANALISIS_TECNICO.md",
    "ARQUITECTURA_SOLUCION.md",
    "TAREAS_DESARROLLO.md",
    "QUERIES_ANALISIS.sql",
    "NOTAS_IMPLEMENTACION.md",
]

# Estados que el pipeline ya está manejando — no re-encolar
_SKIP_STATES = frozenset({
    "completado",
    "archivado",
    "error_pm",
    "error_dev",
    "error_tester",
    "pm_en_proceso",
    "dev_en_proceso",
    "tester_en_proceso",   # ← faltaba: evita lanzar un segundo agente si ya está corriendo
})


def _has_placeholders(ticket_folder: str) -> bool:
    """Retorna True si algún archivo PM del ticket todavía tiene placeholders."""
    for fname in PM_FILES:
        fpath = os.path.join(ticket_folder, fname)
        if not os.path.exists(fpath):
            continue
        try:
            with open(fpath, encoding="utf-8") as fh:   # ← with para cerrar siempre
                content = fh.read()
            if PLACEHOLDER in content or "A completar por PM" in content:
                return True
        except Exception:
            continue
    return False


def _has_inc_file(ticket_folder: str, ticket_id: str) -> bool:
    """Verifica que el ticket principal INC-{id}.md existe."""
    return os.path.exists(os.path.join(ticket_folder, f"INC-{ticket_id}.md"))


def _dev_completed(ticket_folder: str) -> bool:
    """Verifica si DEV_COMPLETADO.md ya existe (pipeline completo)."""
    return os.path.exists(os.path.join(ticket_folder, "DEV_COMPLETADO.md"))


def get_error_flag(ticket_folder: str) -> tuple[str, str] | tuple[None, None]:
    """
    Detecta flags de error dejados por agentes (PM_ERROR.flag, DEV_ERROR.flag,
    TESTER_ERROR.flag). Retorna (stage, reason) o (None, None).
    """
    for stage in ("pm", "dev", "tester"):
        flag_path = os.path.join(ticket_folder, f"{stage.upper()}_ERROR.flag")
        if os.path.exists(flag_path):
            try:
                with open(flag_path, encoding="utf-8") as fh:
                    reason = fh.read().strip()
            except Exception:
                reason = "Error desconocido (no se pudo leer el flag)"
            return stage, reason
    return None, None


# Estado por defecto — se puede sobreescribir via parámetro o config del proyecto
ESTADO_PROCESABLE = "asignada"


def get_processable_tickets(tickets_base: str, pipeline_state: dict,
                            force_reprocess: list = None,
                            estados_procesables: list = None) -> list:
    """
    Escanea tickets_base/{estado}/{id}/ y retorna los tickets procesables.
    Por defecto solo considera el estado "asignada", pero puede configurarse
    via el parámetro estados_procesables (e.g. ["asignada", "en_progreso"]).

    Usa os.scandir (más rápido que os.listdir — reutiliza los metadatos del OS
    en lugar de descartarlos y re-pedirlos con is_dir()).

    Retorna lista de dicts:
    {
        "ticket_id":     "0026772",
        "folder":        "tickets/asignada/0026772",
        "estado_mantis": "asignada",
        "pipeline_estado": "pendiente_pm",
        "error_stage":   None | "pm" | "dev" | "tester",
        "error_reason":  None | "descripción del error",
    }
    """
    force_reprocess    = force_reprocess or []
    estados_permitidos = set(estados_procesables) if estados_procesables else {ESTADO_PROCESABLE}
    processable        = []

    if not os.path.isdir(tickets_base):
        return processable

    with os.scandir(tickets_base) as state_dirs:
        for state_entry in state_dirs:
            if not state_entry.is_dir():
                continue
            if state_entry.name not in estados_permitidos:
                continue

            with os.scandir(state_entry.path) as ticket_dirs:
                for ticket_entry in ticket_dirs:
                    if not ticket_entry.is_dir():
                        continue

                    ticket_id     = ticket_entry.name
                    ticket_folder = ticket_entry.path

                    # Verificar que tiene el archivo principal
                    if not _has_inc_file(ticket_folder, ticket_id):
                        continue

                    # Estado actual en el pipeline
                    pip_state     = pipeline_state.get("tickets", {}).get(ticket_id, {})
                    current_state = pip_state.get("estado", "pendiente_pm")

                    # Forzar reproceso si se solicitó
                    if ticket_id in force_reprocess:
                        error_stage, error_reason = get_error_flag(ticket_folder)
                        processable.append({
                            "ticket_id":     ticket_id,
                            "folder":        ticket_folder,
                            "estado_mantis": state_entry.name,
                            "pipeline_estado": current_state,
                            "error_stage":   error_stage,
                            "error_reason":  error_reason,
                        })
                        continue

                    # Ignorar estados que ya están siendo manejados
                    if current_state in _SKIP_STATES:
                        continue

                    # Solo incluir si tiene placeholders sin completar
                    if _has_placeholders(ticket_folder):
                        error_stage, error_reason = get_error_flag(ticket_folder)
                        processable.append({
                            "ticket_id":     ticket_id,
                            "folder":        ticket_folder,
                            "estado_mantis": state_entry.name,
                            "pipeline_estado": current_state,
                            "error_stage":   error_stage,
                            "error_reason":  error_reason,
                        })

    return processable
