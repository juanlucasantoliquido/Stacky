"""
fast_track_processor.py — Pipeline acelerado para tickets DDL/triviales.

Un ticket que solo necesita ALTER TABLE ADD COLUMN pasa por 1 agente en vez de 3.
3x más rápido que el pipeline estándar.

Criterios de elegibilidad:
- Tag ADO "fast-track"
- Contenido es DDL puro (ALTER TABLE, CREATE INDEX, sp_rename)
- NO menciona archivos .cs o .aspx (solo SQL)

Uso:
    from fast_track_processor import FastTrackProcessor
    ftp = FastTrackProcessor(config, copilot_bridge)
    if ftp.is_fast_track_eligible(inc_content, ado_tags):
        ftp.run(ticket_folder, work_item_id)
"""

import re
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.fast_track")

DDL_PATTERNS = [
    r"alter\s+table\s+\w+\s+add\s+",
    r"create\s+index",
    r"alter\s+table\s+\w+\s+modify\s+",
    r"sp_rename",
    r"alter\s+table\s+\w+\s+drop\s+column",
    r"create\s+table\s+",
    r"alter\s+table\s+\w+\s+alter\s+column",
]

# Patterns that disqualify fast-track (require full pipeline)
DISQUALIFYING_PATTERNS = [
    r"\.(cs|aspx|aspx\.cs|vb)\b",
    r"stored\s+procedure",
    r"trigger\b",
    r"cursor\b",
]


class FastTrackProcessor:
    """
    Pipeline de 1 agente para tickets DDL-puro o triviales.
    Salta PM (genera análisis directamente) y usa DEV con contexto reducido.
    """

    def __init__(self, config: dict, copilot_bridge=None):
        self.config = config
        self.copilot_bridge = copilot_bridge

    def is_fast_track_eligible(self, inc_content: str, ado_tags: str = "") -> bool:
        """
        Determina si un ticket es elegible para fast-track.

        Returns True if:
        - ADO tag contains 'fast-track', OR
        - Content matches DDL patterns AND does NOT mention .cs/.aspx files
        """
        if "fast-track" in ado_tags.lower():
            logger.info("[FastTrack] Eligible via ADO tag 'fast-track'")
            return True

        content_lower = inc_content.lower()

        # Check DDL patterns
        has_ddl = any(re.search(p, content_lower) for p in DDL_PATTERNS)
        if not has_ddl:
            return False

        # Disqualify if complex code references found
        has_code = any(re.search(p, content_lower) for p in DISQUALIFYING_PATTERNS)
        if has_code:
            logger.debug("[FastTrack] DDL detected but disqualified by code references")
            return False

        logger.info("[FastTrack] Eligible via DDL pattern detection")
        return True

    def run(self, ticket_folder: str, work_item_id: int):
        """
        Execute fast-track pipeline: single agent invocation with reduced context.
        Generates minimal PM artifacts and invokes DEV directly.
        """
        logger.info("[FastTrack] Running for ticket folder=%s, WI#%d",
                    ticket_folder, work_item_id)

        # Generate minimal PM artifacts from the INC content
        self._generate_minimal_pm_artifacts(ticket_folder)

        # Build fast-track prompt
        prompt = self._build_fast_track_prompt(ticket_folder, work_item_id)

        # Invoke DEV agent with reduced context
        if self.copilot_bridge:
            self.copilot_bridge.invoke_agent(
                prompt,
                agent_name=self.config.get("agents", {}).get("dev", "DevStack2"),
                project_name=self.config.get("project_name", ""),
            )

    def _generate_minimal_pm_artifacts(self, ticket_folder: str):
        """Generate minimal PM output files for fast-track tickets."""
        folder = Path(ticket_folder)

        # Read INC content
        inc_files = list(folder.glob("INC-*.md")) + list(folder.glob("INC_*.md"))
        inc_content = ""
        if inc_files:
            inc_content = inc_files[0].read_text(encoding="utf-8", errors="replace")

        # Extract SQL-related info
        sql_objects = self._extract_sql_objects(inc_content)

        # Generate INCIDENTE.md
        if not (folder / "INCIDENTE.md").exists():
            (folder / "INCIDENTE.md").write_text(
                f"# Incidente (Fast-Track DDL)\n\n{inc_content}\n",
                encoding="utf-8"
            )

        # Generate ANALISIS_TECNICO.md
        if not (folder / "ANALISIS_TECNICO.md").exists():
            (folder / "ANALISIS_TECNICO.md").write_text(
                f"# Análisis Técnico (Fast-Track)\n\n"
                f"Tipo: DDL / Cambio de esquema\n"
                f"Objetos SQL detectados: {', '.join(sql_objects) if sql_objects else 'N/A'}\n"
                f"Complejidad: Baja\n"
                f"Riesgo: Bajo (solo estructura, no lógica de negocio)\n",
                encoding="utf-8"
            )

        # Generate ARQUITECTURA_SOLUCION.md
        if not (folder / "ARQUITECTURA_SOLUCION.md").exists():
            (folder / "ARQUITECTURA_SOLUCION.md").write_text(
                f"# Arquitectura de Solución (Fast-Track)\n\n"
                f"## Archivos a modificar\n"
                f"- BD/Scripts/*.sql\n\n"
                f"## Tipo de cambio\n"
                f"DDL puro — sin impacto en código fuente .cs/.aspx\n",
                encoding="utf-8"
            )

        # Generate TAREAS_DESARROLLO.md
        if not (folder / "TAREAS_DESARROLLO.md").exists():
            (folder / "TAREAS_DESARROLLO.md").write_text(
                f"# Tareas de Desarrollo (Fast-Track)\n\n"
                f"## PENDIENTE\n"
                f"- [ ] Ejecutar script DDL en BD de desarrollo\n"
                f"- [ ] Verificar que la estructura resultante es correcta\n"
                f"- [ ] Generar ROLLBACK_SCRIPT.sql\n",
                encoding="utf-8"
            )

        # Mark PM as completed
        (folder / "PM_COMPLETADO.flag").write_text(
            "Fast-Track: PM generado automáticamente sin agente",
            encoding="utf-8"
        )

    def _build_fast_track_prompt(self, ticket_folder: str, work_item_id: int) -> str:
        """Build a reduced prompt for fast-track DEV execution."""
        folder = Path(ticket_folder)

        inc_content = ""
        inc_files = list(folder.glob("INC-*.md")) + list(folder.glob("INC_*.md"))
        if inc_files:
            inc_content = inc_files[0].read_text(encoding="utf-8", errors="replace")

        return (
            f"# FAST-TRACK DDL — Work Item #{work_item_id}\n\n"
            f"Este es un ticket DDL simple. NO requiere análisis de código .cs/.aspx.\n"
            f"Solo necesitás generar/verificar el script SQL.\n\n"
            f"## Incidente\n{inc_content}\n\n"
            f"## Instrucciones\n"
            f"1. Generá el script DDL (.sql) necesario\n"
            f"2. Generá el ROLLBACK_SCRIPT.sql correspondiente\n"
            f"3. Documentá en DEV_COMPLETADO.md los cambios realizados\n"
        )

    def _extract_sql_objects(self, content: str) -> list[str]:
        """Extract SQL object names (tables, indexes) from content."""
        objects = []
        patterns = [
            (r"(?:alter|create)\s+table\s+(\w+)", "table"),
            (r"create\s+index\s+(\w+)", "index"),
            (r"sp_rename\s+'(\w+)'", "object"),
        ]
        for pattern, obj_type in patterns:
            for match in re.finditer(pattern, content, re.IGNORECASE):
                objects.append(f"{obj_type}:{match.group(1)}")
        return objects
