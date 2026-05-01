"""
batch_processor.py — N-04: Modo Batch por Componente.

Agrupa tickets activos que comparten el mismo módulo/componente y genera
un prompt PM unificado que analiza todos juntos, aprovechando el contexto
compartido para mayor coherencia.

Beneficio principal: cuando 3 tickets afectan FrmPagos, el PM analiza los
3 en un solo pase con visibilidad completa de interacciones.

Uso:
    from batch_processor import BatchProcessor
    bp = BatchProcessor(tickets_base, project_name)
    groups = bp.find_component_groups(pending_tickets)
    for group in groups:
        prompt = bp.build_batch_pm_prompt(group)
        # invocar PM una sola vez con el prompt batch
"""

import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("stacky.batch_processor")

_MIN_GROUP_SIZE = 2  # mínimo tickets para agrupar
_MAX_GROUP_SIZE = 5  # máximo tickets por batch


@dataclass
class TicketGroup:
    component:    str                  # nombre del componente compartido
    ticket_ids:   list[str]
    folders:      list[str]
    similarity:   float = 0.0          # 0-1


class BatchProcessor:
    """
    Agrupa tickets por componente compartido para análisis PM unificado.
    """

    def __init__(self, tickets_base: str, project_name: str):
        self._tickets_base = tickets_base
        self._project      = project_name

    # ── API pública ───────────────────────────────────────────────────────

    def find_component_groups(self, pending_tickets: list[dict]) -> list[TicketGroup]:
        """
        Agrupa una lista de tickets pendientes por componente principal.
        pending_tickets: lista de dicts con 'ticket_id' y 'folder'.
        Retorna grupos de ≥2 tickets con componente compartido.
        """
        # Extraer componente principal de cada ticket
        ticket_components: dict[str, tuple[str, str]] = {}  # id → (component, folder)
        for t in pending_tickets:
            tid    = t["ticket_id"]
            folder = t["folder"]
            comp   = self._extract_primary_component(folder, tid)
            if comp:
                ticket_components[tid] = (comp, folder)

        if len(ticket_components) < _MIN_GROUP_SIZE:
            return []

        # Agrupar por componente
        groups_by_comp: dict[str, list[str]] = {}
        for tid, (comp, _) in ticket_components.items():
            groups_by_comp.setdefault(comp, []).append(tid)

        result = []
        for comp, tids in groups_by_comp.items():
            if len(tids) < _MIN_GROUP_SIZE:
                continue
            # Cap en MAX_GROUP_SIZE
            tids = tids[:_MAX_GROUP_SIZE]
            folders = [ticket_components[tid][1] for tid in tids]
            result.append(TicketGroup(
                component=comp,
                ticket_ids=tids,
                folders=folders,
            ))

        result.sort(key=lambda g: -len(g.ticket_ids))
        logger.info("[BATCH] %d grupo(s) de componente encontrado(s)", len(result))
        return result

    def build_batch_pm_prompt(self, group: TicketGroup,
                               workspace_root: str = "") -> str:
        """
        Construye un prompt PM unificado para un grupo de tickets.
        El PM analiza todos los tickets juntos con contexto de sus interacciones.
        """
        lines = [
            f"# Análisis PM Batch — Componente: {group.component}",
            f"# Tickets en este batch: {', '.join('#' + t for t in group.ticket_ids)}",
            "",
            "## Contexto del Batch",
            "",
            f"Estos {len(group.ticket_ids)} tickets afectan el mismo componente "
            f"**{group.component}**. Analiza todos juntos para detectar:",
            "- Soluciones que se contradicen entre sí",
            "- Oportunidad de resolver múltiples bugs en un solo fix",
            "- Riesgos de regresión entre los tickets",
            "- Orden óptimo de implementación",
            "",
            "---",
            "",
        ]

        # Agregar INC de cada ticket
        for i, (tid, folder) in enumerate(zip(group.ticket_ids, group.folders), 1):
            inc_path = os.path.join(folder, f"INC-{tid}.md")
            try:
                inc_content = Path(inc_path).read_text(
                    encoding="utf-8", errors="replace")[:2500]
            except Exception:
                inc_content = "(INC no disponible)"

            lines += [
                f"## Ticket #{tid} ({i}/{len(group.ticket_ids)})",
                "",
                inc_content,
                "",
                "---",
                "",
            ]

        lines += [
            "## Instrucciones para el PM",
            "",
            "Para cada ticket produce los archivos estándar en su carpeta:",
            "- `ANALISIS_TECNICO.md`",
            "- `ARQUITECTURA_SOLUCION.md`",
            "- `TAREAS_DESARROLLO.md`",
            "",
            "Adicionalmente, crea `BATCH_ANALYSIS.md` en la carpeta del primer ticket con:",
            "- Interacciones detectadas entre tickets",
            "- Orden recomendado de implementación",
            "- Riesgos de conflicto",
            "",
            "Al finalizar, crea `PM_COMPLETADO.flag` en CADA carpeta de ticket.",
        ]

        return "\n".join(lines)

    def build_batch_status_report(self, groups: list[TicketGroup]) -> str:
        """Genera un reporte de los grupos detectados para el dashboard."""
        if not groups:
            return "Sin grupos batch activos."

        lines = ["## Grupos Batch Activos", ""]
        for g in groups:
            lines.append(
                f"- **{g.component}**: "
                + ", ".join(f"#{t}" for t in g.ticket_ids)
                + f" ({len(g.ticket_ids)} tickets)"
            )
        return "\n".join(lines)

    # ── Internals ─────────────────────────────────────────────────────────

    def _extract_primary_component(self, ticket_folder: str,
                                    ticket_id: str) -> str:
        """Extrae el componente principal del ticket."""
        inc_path = os.path.join(ticket_folder, f"INC-{ticket_id}.md")
        if not os.path.exists(inc_path):
            return ""

        try:
            content = Path(inc_path).read_text(
                encoding="utf-8", errors="replace")[:2000]
        except Exception:
            return ""

        # Prioridad 1: FrmXxx (formulario más mencionado)
        frm_matches = re.findall(r'\b(Frm[A-Z]\w{3,})\b', content)
        if frm_matches:
            most_common = max(set(frm_matches), key=frm_matches.count)
            return most_common

        # Prioridad 2: DAL_Xxx
        dal_matches = re.findall(r'\b(DAL_\w{3,})\b', content, re.IGNORECASE)
        if dal_matches:
            return max(set(dal_matches), key=dal_matches.count).upper()

        # Prioridad 3: Módulo por nombre de tabla
        table_matches = re.findall(r'\b(RST_[A-Z0-9_]{3,15})\b', content)
        if table_matches:
            return max(set(table_matches), key=table_matches.count)

        # Prioridad 4: Categoría por keyword
        content_lower = content.lower()
        if "batch" in content_lower or "proceso masivo" in content_lower:
            return "BATCH"
        if "reporte" in content_lower or "report" in content_lower:
            return "REPORTES"
        if "integración" in content_lower or "webservice" in content_lower:
            return "INTEGRACION"

        return ""
