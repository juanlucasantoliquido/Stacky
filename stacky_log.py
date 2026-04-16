"""
stacky_log.py — Sistema de logging centralizado para Stacky Pipeline.

Crea/rota automáticamente el archivo de log en:
    tools/mantis_scraper/logs/stacky_pipeline_YYYY-MM-DD.log

Uso desde cualquier módulo:
    from stacky_log import slog
    slog.info("Mensaje")
    slog.pipeline("27698", "pm", "completado", "INCIDENTE.md: OK")
    slog.transition("27698", "pm_completado", "dev_en_proceso")
    slog.validation("27698", "pm", ok=False, issues=["TAREAS falta PENDIENTE"])
    slog.error("27698", "pm", "No se encontró PM_COMPLETADO.flag")

El log incluye timestamp, nivel, ticket_id y contexto en cada línea para
facilitar el grep/filtrado por ticket:

    2026-04-14 15:32:01 [INFO ] [#27698] [PM     ] Flag detectado: PM_COMPLETADO.flag
    2026-04-14 15:32:03 [WARN ] [#27698] [VALID  ] FAIL: TAREAS_DESARROLLO.md sin PENDIENTE
    2026-04-14 15:32:03 [ERROR] [#27698] [WATCHER] Validation failed → PM_ERROR.flag creado
    2026-04-14 15:32:05 [INFO ] [#27698] [STATE  ] pm_en_proceso → pm_completado
"""

import logging
import logging.handlers
import os
import sys
from datetime import datetime
from pathlib import Path


# ── Configuración ──────────────────────────────────────────────────────────────

_BASE_DIR  = Path(__file__).resolve().parent
_LOGS_DIR  = _BASE_DIR / "logs"
_LOG_FILE  = _LOGS_DIR / f"stacky_pipeline_{datetime.now().strftime('%Y-%m-%d')}.log"

# Formato de línea: timestamp [NIVEL] [#ticket] [COMPONENTE] mensaje
_FMT_FILE    = "%(asctime)s [%(levelname)-5s] %(message)s"
_FMT_CONSOLE = "%(asctime)s [%(levelname)-5s] %(message)s"
_DATE_FMT    = "%Y-%m-%d %H:%M:%S"

# Máximo de archivos de log que se conservan
_MAX_LOG_FILES = 14  # 2 semanas


# ── Bootstrap (se ejecuta al importar el módulo) ───────────────────────────────

def _setup() -> logging.Logger:
    _LOGS_DIR.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("stacky.pipeline")
    if logger.handlers:
        return logger  # ya inicializado en este proceso

    logger.setLevel(logging.DEBUG)

    # Handler de archivo rotativo por tamaño (5 MB × 5 backups del día)
    try:
        fh = logging.handlers.RotatingFileHandler(
            str(_LOG_FILE),
            maxBytes    = 5 * 1024 * 1024,
            backupCount = 5,
            encoding    = "utf-8",
        )
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter(_FMT_FILE, datefmt=_DATE_FMT))
        logger.addHandler(fh)
    except Exception as e:
        print(f"[stacky_log] No se pudo abrir log file: {e}", file=sys.stderr)

    # Purgar logs viejos (> _MAX_LOG_FILES días)
    try:
        log_files = sorted(_LOGS_DIR.glob("stacky_pipeline_*.log"))
        for old in log_files[:-_MAX_LOG_FILES]:
            old.unlink(missing_ok=True)
    except Exception:
        pass

    return logger


_log = _setup()


# ── API pública ────────────────────────────────────────────────────────────────

class _StackyLogger:
    """
    Logger de alto nivel con métodos semánticos para el pipeline de Stacky.
    Todos los mensajes incluyen ticket_id y componente para facilitar el filtrado.
    """

    # ── Nivel genérico ─────────────────────────────────────────────────────

    def debug(self, ticket_id: str, component: str, msg: str) -> None:
        _log.debug("[#%-7s] [%-7s] %s", ticket_id or "-", component.upper()[:7], msg)

    def info(self, ticket_id: str, component: str, msg: str) -> None:
        _log.info("[#%-7s] [%-7s] %s", ticket_id or "-", component.upper()[:7], msg)

    def warning(self, ticket_id: str, component: str, msg: str) -> None:
        _log.warning("[#%-7s] [%-7s] %s", ticket_id or "-", component.upper()[:7], msg)

    def error(self, ticket_id: str, component: str, msg: str) -> None:
        _log.error("[#%-7s] [%-7s] %s", ticket_id or "-", component.upper()[:7], msg)

    def critical(self, ticket_id: str, component: str, msg: str) -> None:
        _log.critical("[#%-7s] [%-7s] %s", ticket_id or "-", component.upper()[:7], msg)

    # ── Semánticos del pipeline ────────────────────────────────────────────

    def flag_detected(self, ticket_id: str, flag_name: str, folder: str = "") -> None:
        """Flag de completado/error detectado por el watcher."""
        loc = f" en {folder}" if folder else ""
        _log.info("[#%-7s] [WATCHER] Flag detectado: %s%s", ticket_id, flag_name, loc)

    def transition(self, ticket_id: str, from_state: str, to_state: str,
                   source: str = "") -> None:
        """Transición de estado del ticket."""
        src = f" [{source}]" if source else ""
        _log.info("[#%-7s] [STATE  ] %s → %s%s", ticket_id, from_state, to_state, src)

    def validation(self, ticket_id: str, stage: str, ok: bool,
                   issues: list[str] = None, warnings: list[str] = None) -> None:
        """Resultado de output_validator para una etapa."""
        if ok:
            warn_str = f" ({len(warnings)} warnings)" if warnings else ""
            _log.info("[#%-7s] [VALID  ] %s OK%s", ticket_id, stage.upper(), warn_str)
        else:
            _log.warning("[#%-7s] [VALID  ] %s FAIL:", ticket_id, stage.upper())
            for issue in (issues or []):
                _log.warning("[#%-7s] [VALID  ]   ERROR: %s", ticket_id, issue)
        for warn in (warnings or []):
            _log.warning("[#%-7s] [VALID  ]   WARN:  %s", ticket_id, warn)

    def stage_start(self, ticket_id: str, stage: str, retry: int = 0) -> None:
        """Inicio de invocación de un agente."""
        retry_str = f" (retry #{retry})" if retry else ""
        _log.info("[#%-7s] [AGENT  ] Lanzando agente %s%s", ticket_id, stage.upper(), retry_str)

    def stage_done(self, ticket_id: str, stage: str) -> None:
        """Etapa completada exitosamente."""
        _log.info("[#%-7s] [AGENT  ] Etapa %s completada OK", ticket_id, stage.upper())

    def stage_error(self, ticket_id: str, stage: str, reason: str,
                    retry_num: int = 0, max_retries: int = 0) -> None:
        """Error en una etapa (con detalle del motivo)."""
        retry_str = f" — reintento {retry_num}/{max_retries}" if max_retries else ""
        _log.error("[#%-7s] [AGENT  ] Error en %s%s: %s",
                   ticket_id, stage.upper(), retry_str, reason[:300])

    def invoke_result(self, ticket_id: str, stage: str, ok: bool,
                      method: str = "") -> None:
        """Resultado de la invocación del agente (bridge HTTP o UI fallback)."""
        status = "OK" if ok else "FALLÓ"
        via    = f" via {method}" if method else ""
        level  = logging.INFO if ok else logging.ERROR
        _log.log(level, "[#%-7s] [BRIDGE ] Invoke %s%s: %s",
                 ticket_id, stage.upper(), via, status)

    def svn_event(self, ticket_id: str, event: str, detail: str = "") -> None:
        """Evento SVN (commit, diff, error)."""
        _log.info("[#%-7s] [SVN    ] %s%s", ticket_id, event,
                  f": {detail}" if detail else "")

    def mantis_event(self, ticket_id: str, event: str, detail: str = "") -> None:
        """Evento en Mantis (nota publicada, estado cambiado, error)."""
        _log.info("[#%-7s] [MANTIS ] %s%s", ticket_id, event,
                  f": {detail}" if detail else "")

    def daemon_cycle(self, project: str, tickets_found: int,
                     tickets_processing: int) -> None:
        """Resumen de un ciclo del daemon."""
        _log.info("[#%-7s] [DAEMON ] Ciclo %s: %d procesables, %d en proceso",
                  "-", project, tickets_found, tickets_processing)

    def separator(self, label: str = "") -> None:
        """Línea separadora para marcar inicio/fin de una sesión en el log."""
        txt = f" {label} " if label else ""
        _log.info("─" * 30 + txt + "─" * 30)

    # ── Utilidades ─────────────────────────────────────────────────────────

    @property
    def log_file(self) -> str:
        """Ruta al archivo de log activo."""
        return str(_LOG_FILE)

    def tail(self, lines: int = 50) -> list[str]:
        """Retorna las últimas N líneas del log (útil para el dashboard)."""
        try:
            text = _LOG_FILE.read_text(encoding="utf-8", errors="replace")
            return text.splitlines()[-lines:]
        except Exception:
            return []


# Instancia global — importar con:  from stacky_log import slog
slog = _StackyLogger()
