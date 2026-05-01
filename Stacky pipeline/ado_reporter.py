"""
ado_reporter.py — Actualización automática de estados y comentarios en ADO.

Cuando Stacky completa PM, DEV o QA, el Work Item en ADO recibe un comentario
detallado y su estado se actualiza para reflejar el progreso real del pipeline.

Uso:
    from ado_reporter import ADOReporter
    reporter = ADOReporter()
    reporter.report_stage_complete(27698, "pm_completado", context)
    reporter.update_ado_state(27698, "dev_en_proceso")
"""

import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger("stacky.ado_reporter")


# ── Templates de comentarios por etapa ────────────────────────────────────────

ADO_COMMENTS = {
    "pm_completado": """
## ✅ Análisis PM completado — Stacky

El agente PM-TL finalizó el análisis técnico del ticket.

**Artefactos generados:**
- `INCIDENTE.md` — descripción técnica del problema
- `ANALISIS_TECNICO.md` — causa raíz identificada
- `ARQUITECTURA_SOLUCION.md` — archivos a modificar: {files_list}
- `TAREAS_DESARROLLO.md` — {task_count} tarea(s) de implementación

**Próxima etapa:** DEV
**Timestamp:** {timestamp}
""",
    "dev_completado": """
## ✅ Implementación DEV completada — Stacky

El agente DEV finalizó la implementación.

**Archivos modificados ({files_count}):**
{files_list}

**Próxima etapa:** QA / Tester
**Timestamp:** {timestamp}
""",
    "qa_aprobado": """
## ✅ QA APROBADO — Stacky

El agente Tester aprobó los cambios.

**Casos de prueba ejecutados:** {cases_count}
**Total de iteraciones:** {iterations}
**Duración total del pipeline:** {duration}

### Desglose de tiempos por etapa
{stage_breakdown}

### Historial de iteraciones
{iteration_table}

Los cambios están listos para deploy.
**Timestamp:** {timestamp}
""",
    "qa_con_observaciones": """
## ⚠️ QA con observaciones — Stacky (ciclo rework #{cycle})

El agente Tester encontró issues que requieren corrección.

**Issues detectados:**
{findings_list}

Stacky iniciará automáticamente un ciclo de rework DEV → QA.
**Timestamp:** {timestamp}
""",
    "qa_rechazado": """
## ❌ QA RECHAZADO — Stacky

El agente Tester rechazó los cambios.

**Razón:**
{findings_list}

Se requiere intervención manual o re-análisis completo.
**Timestamp:** {timestamp}
""",
    "error": """
## ❌ Error en pipeline — Stacky

**Etapa:** {stage}
**Error:** {error_detail}
**Reintentos realizados:** {retries}
**Acción requerida:** Revisar dashboard Stacky o ejecutar retry manual.
**Timestamp:** {timestamp}
""",
    "pipeline_iniciado": """
## 🔄 Pipeline Stacky iniciado

Stacky comenzó a procesar este ticket.
**Etapa inicial:** {first_stage}
**Timestamp:** {timestamp}
""",
}


# Orden de stages en el breakdown — alinea con pipeline_state.ESTADOS_VALIDOS
_STAGE_ORDER: list[tuple[str, str]] = [
    ("PM",           "pm"),
    ("DBA",          "dba"),
    ("TL Review",    "tl_review"),
    ("DEV",          "dev"),
    ("DEV Rework",   "dev_rework"),
    ("QA / Tester",  "tester"),
    ("PM Revision",  "pm_revision"),
    ("DOC",          "doc"),
]


def _format_duration(seconds: Optional[float]) -> str:
    """Formato humano: `3m 45s` / `1h 02m 15s`."""
    if seconds is None:
        return "N/A"
    try:
        total = int(round(float(seconds)))
    except (TypeError, ValueError):
        return "N/A"
    hrs, rem  = divmod(max(0, total), 3600)
    mins, sec = divmod(rem, 60)
    if hrs:
        return f"{hrs}h {mins:02d}m {sec:02d}s"
    if mins:
        return f"{mins}m {sec:02d}s"
    return f"{sec}s"


def _fmt_iso(iso_str: Optional[str]) -> str:
    if not iso_str:
        return "—"
    return iso_str[:19].replace("T", " ")


def build_stage_breakdown(ticket_state: dict) -> tuple[str, float]:
    """
    Construye la tabla Markdown con tiempos por etapa.
    Retorna (markdown, total_duration_sec).
    """
    rows: list[str] = []
    total_sec = 0.0
    for label, key in _STAGE_ORDER:
        dur = ticket_state.get(f"{key}_duration_sec")
        if dur is None:
            continue
        rows.append(
            f"| {label} | {_fmt_iso(ticket_state.get(f'{key}_started_at'))} | "
            f"{_fmt_iso(ticket_state.get(f'{key}_ended_at'))} | "
            f"{_format_duration(dur)} |"
        )
        total_sec += float(dur)
    if not rows:
        return "_(sin datos de timing registrados)_", 0.0
    table = (
        "| Etapa | Inicio | Fin | Duración |\n"
        "|-------|--------|-----|----------|\n"
        + "\n".join(rows)
    )
    return table, total_sec


def build_iteration_table(ticket_state: dict) -> str:
    """Tabla Markdown con el resumen de cada iteración DEV→QA."""
    history = ticket_state.get("iteration_history") or []
    if not history:
        return "_(resuelto en la primera iteración, sin rework)_"
    lines = [
        "| # | Inicio | Fin | Duración | Veredicto QA | Findings |",
        "|---|--------|-----|----------|--------------|----------|",
    ]
    for it in history:
        lines.append(
            f"| {it.get('iteration', '?')} | "
            f"{_fmt_iso(it.get('started_at'))} | "
            f"{_fmt_iso(it.get('ended_at'))} | "
            f"{_format_duration(it.get('duration_sec'))} | "
            f"{it.get('qa_verdict', '—')} | "
            f"{it.get('findings_count', 0)} |"
        )
    return "\n".join(lines)


# Maps pipeline stage to ADO Work Item state
_ADO_STATE_MAP = {
    "pipeline_iniciado": "Active",
    "pm_en_proceso":     "Active",
    "pm_completado":     "Active",
    "dev_en_proceso":    "Active",
    "dev_completado":    "Active",
    "qa_en_proceso":     "Active",
    "qa_aprobado":       "Resolved",
    "qa_con_observaciones": "Active",
    "qa_rechazado":      "Active",
    "completado":        "Resolved",
    "error":             "Active",
}


class ADOReporter:
    """Reports pipeline progress to Azure DevOps via comments and state updates."""

    def __init__(self, ado_client=None, state_provider=None):
        self._ado_client = ado_client
        self._state_provider = state_provider

    @property
    def ado_client(self):
        if self._ado_client is None:
            try:
                from ado_enricher import _get_ado_client
                self._ado_client = _get_ado_client()
            except Exception as e:
                logger.error("Cannot initialize ADO client: %s", e)
                raise
        return self._ado_client

    @property
    def state_provider(self):
        if self._state_provider is None:
            try:
                from ado_state_provider import ADOStateProvider
                self._state_provider = ADOStateProvider(self.ado_client)
            except Exception as e:
                logger.error("Cannot initialize state provider: %s", e)
        return self._state_provider

    def report_stage_complete(
        self,
        work_item_id: int,
        stage: str,
        context: Optional[dict] = None,
    ):
        """
        Post a formatted comment to ADO when a pipeline stage completes.

        Args:
            work_item_id: ADO Work Item ID
            stage: One of the keys in ADO_COMMENTS
            context: Dict with template variables for the comment
        """
        if context is None:
            context = {}

        context.setdefault("timestamp", datetime.now().strftime("%Y-%m-%d %H:%M"))
        context.setdefault("files_list", "(no files reported)")
        context.setdefault("files_count", 0)
        context.setdefault("task_count", 0)
        context.setdefault("cases_count", 0)
        context.setdefault("rework_cycles", 0)
        context.setdefault("duration", "N/A")
        context.setdefault("cycle", 1)
        context.setdefault("findings_list", "(none)")
        context.setdefault("error_detail", "unknown")
        context.setdefault("retries", 0)
        context.setdefault("stage", stage)
        context.setdefault("first_stage", "PM")

        template = ADO_COMMENTS.get(stage)
        if not template:
            logger.warning("No comment template for stage '%s'", stage)
            return

        try:
            comment = template.format(**context)
        except KeyError as e:
            logger.warning("Missing key in context for stage '%s': %s", stage, e)
            comment = f"Pipeline stage '{stage}' completed. Context: {context}"

        try:
            self.ado_client.add_comment(work_item_id, comment)
            logger.info("ADO comment posted for WI#%d stage=%s", work_item_id, stage)
        except Exception as e:
            logger.error("Failed to post comment to WI#%d: %s", work_item_id, e)

    def update_ado_state(self, work_item_id: int, stage: str):
        """
        Update ADO Work Item state based on pipeline stage.

        Args:
            work_item_id: ADO Work Item ID
            stage: Pipeline stage (e.g., 'pm_completado', 'completado', 'error')
        """
        new_state = _ADO_STATE_MAP.get(stage)
        if not new_state:
            logger.warning("No ADO state mapping for stage '%s'", stage)
            return

        try:
            self.ado_client.update_work_item(work_item_id, {
                "System.State": new_state,
            })
            logger.info("ADO WI#%d state → %s (stage=%s)", work_item_id, new_state, stage)
        except Exception as e:
            logger.error("Failed to update state for WI#%d: %s", work_item_id, e)

    def report_and_update(
        self,
        work_item_id: int,
        stage: str,
        stacky_state: str,
        stacky_stage: str,
        context: Optional[dict] = None,
        rework_cycles: int = 0,
    ):
        """
        Combined operation: post comment + update ADO state + update Stacky state provider.

        This is the primary method to call from pipeline_watcher.py stage transitions.
        """
        self.report_stage_complete(work_item_id, stage, context)
        self.update_ado_state(work_item_id, stage)

        if self.state_provider:
            try:
                self.state_provider.set_ticket_state(
                    work_item_id, stacky_state, stacky_stage, rework_cycles
                )
            except Exception as e:
                logger.error("Failed to update state provider for WI#%d: %s",
                             work_item_id, e)

    def report_pipeline_complete(
        self,
        work_item_id: int,
        ticket_state: dict,
        cases_count: Optional[int] = None,
    ):
        """
        Comentario único de cierre con el breakdown completo (timings por etapa
        + historial de iteraciones). Se invoca una sola vez cuando QA aprueba.

        Lee los campos que escribe `pipeline_state.set_ticket_state` y
        `pipeline_state.record_iteration_end`.
        """
        stage_breakdown, total_sec = build_stage_breakdown(ticket_state)
        iteration_table            = build_iteration_table(ticket_state)
        iterations                 = int(ticket_state.get("iterations") or 1)
        resolved_cases             = (cases_count
                                      if cases_count is not None
                                      else ticket_state.get("cases_count", 0))

        context = {
            "cases_count":     resolved_cases,
            "iterations":      iterations,
            "rework_cycles":   max(0, iterations - 1),
            "duration":        _format_duration(total_sec) if total_sec else "N/A",
            "stage_breakdown": stage_breakdown,
            "iteration_table": iteration_table,
        }
        self.report_stage_complete(work_item_id, "qa_aprobado", context)
        self.update_ado_state(work_item_id, "qa_aprobado")

    def report_error(
        self,
        work_item_id: int,
        stage: str,
        error_detail: str,
        retries: int = 0,
    ):
        """Report an error in the pipeline to ADO."""
        self.report_and_update(
            work_item_id=work_item_id,
            stage="error",
            stacky_state="error",
            stacky_stage=stage,
            context={
                "stage": stage,
                "error_detail": error_detail,
                "retries": retries,
            },
        )

    def create_self_improvement_insight(
        self,
        improvement_description: str,
        metric_improvement: float,
        area: str,
    ):
        """
        Create an ADO Work Item of type 'Task' to track self-improvement insights.
        Used by X-05 Autonomous Pipeline Self-Rewriting.
        """
        try:
            self.ado_client.create_work_item(
                type="Task",
                title=f"[Stacky Insight] {area}: {improvement_description[:80]}",
                description=(
                    f"<b>Auto-detected improvement opportunity</b><br>"
                    f"<b>Area:</b> {area}<br>"
                    f"<b>Improvement:</b> {improvement_description}<br>"
                    f"<b>Expected metric gain:</b> {metric_improvement:.1%}<br>"
                    f"<b>Generated by:</b> Stacky MetaAgent<br>"
                    f"<b>Date:</b> {datetime.now().strftime('%Y-%m-%d %H:%M')}"
                ),
                tags="stacky:insight; auto-generated",
            )
        except Exception as e:
            logger.error("Failed to create insight WI: %s", e)
