"""
bug_localizer.py — S-04: Bug Localizer: Orquestador que genera BUG_LOCALIZATION.md.

Orquesta S-01, S-02 y S-03 para producir un archivo BUG_LOCALIZATION.md
en la carpeta del ticket antes de que PM empiece.

BUG_LOCALIZATION.md contiene:
  - Stack trace parseado con archivo/metodo exacto (S-01)
  - Constantes RIDIOMA y sus callers (S-02)
  - Entry points del Form/Batch afectado (S-03)
  - Hipotesis preliminar del punto de falla (sintetizada sin LLM)

Este archivo se inyecta en los prompts PM y DEV (S-05) para dar contexto
quirurgico desde el primer prompt.

Uso:
    from bug_localizer import BugLocalizer
    bl = BugLocalizer(project_name, workspace_root)
    result = bl.localize(ticket_folder, ticket_id)
    # result["localization_file"] → ruta de BUG_LOCALIZATION.md generado
    # result["has_stack_trace"]   → si se encontro stack trace
    # result["primary_location"]  → archivo:linea del punto de falla
"""

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger("mantis.bug_localizer")

BASE_DIR = Path(__file__).parent


class BugLocalizer:
    """
    Orquesta el analisis de localizacion de bug usando S-01, S-02 y S-03.
    Genera BUG_LOCALIZATION.md en la carpeta del ticket.
    """

    def __init__(self, project_name: str, workspace_root: str = None):
        self.project_name = project_name
        self._config      = self._load_config()
        self._workspace   = workspace_root or self._config.get(
            "workspace_root", str(BASE_DIR.parent.parent)
        )

    def localize(self, ticket_folder: str, ticket_id: str) -> dict:
        """
        Ejecuta el analisis completo de localizacion para un ticket.
        Retorna dict con: localization_file, has_stack_trace, primary_location, summary.
        """
        folder = Path(ticket_folder)
        logger.info("[S-04] Bug Localizer iniciando para ticket %s", ticket_id)

        # Leer contenido del ticket
        inc_content = self._read_inc(folder)
        if not inc_content:
            return {"success": False, "error": "INC file no encontrado"}

        sections = []
        primary_location = None

        # S-01: Stack Trace Parser
        try:
            from stack_trace_parser import StackTraceParser
            parser    = StackTraceParser(self._workspace)
            st_result = parser.parse(inc_content)
            if st_result.has_stack_trace:
                sections.append(("Stack Trace Analizado", st_result.markdown))
                if st_result.primary:
                    p = st_result.primary
                    primary_location = f"{p.file_path}:{p.line_number}" if p.file_path else None
        except Exception as exc:
            logger.debug("[S-04] StackTraceParser: %s", exc)
            sections.append(("Stack Trace", "_No se pudo parsear el stack trace._"))

        # S-02: RIDIOMA Lookup — buscar mensajes de error mencionados
        try:
            from ridioma_lookup import RIDIOMALookup
            lookup = RIDIOMALookup(self.project_name, self._workspace)

            # Extraer mensajes de error del ticket (entre comillas o despues de ":")
            messages = self._extract_error_messages(inc_content)
            ridioma_sections = []
            for msg in messages[:2]:
                r = lookup.find_message(msg)
                if r.found:
                    ridioma_sections.append(r.markdown)

            if ridioma_sections:
                sections.append(("RIDIOMA Lookup", "\n\n".join(ridioma_sections)))
        except Exception as exc:
            logger.debug("[S-04] RIDIOMALookup: %s", exc)

        # S-03: Entry Point Resolver
        try:
            from entry_point_resolver import EntryPointResolver
            resolver = EntryPointResolver(self._workspace)
            ep_result = resolver.resolve_from_ticket(inc_content)
            if ep_result and ep_result.found:
                sections.append(("Entry Point del Componente Afectado", ep_result.markdown))
                if not primary_location and ep_result.entry_points:
                    ep = ep_result.entry_points[0]
                    primary_location = f"{ep.file_path}:{ep.line_number}"
        except Exception as exc:
            logger.debug("[S-04] EntryPointResolver: %s", exc)

        # Hipotesis preliminar
        hypothesis = self._build_hypothesis(inc_content, primary_location, sections)

        # Generar BUG_LOCALIZATION.md
        content = self._render_localization_file(
            ticket_id, sections, hypothesis, primary_location
        )
        output_path = folder / "BUG_LOCALIZATION.md"
        output_path.write_text(content, encoding="utf-8")

        logger.info("[S-04] BUG_LOCALIZATION.md generado para %s", ticket_id)

        return {
            "success":            True,
            "localization_file":  str(output_path),
            "has_stack_trace":    any("Stack Trace" in s[0] for s in sections),
            "primary_location":   primary_location,
            "summary":            hypothesis[:200],
        }

    # ── Privados ─────────────────────────────────────────────────────────────

    def _read_inc(self, folder: Path) -> str:
        for f in folder.glob("INC-*.md"):
            try:
                return f.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                pass
        inc = folder / "INCIDENTE.md"
        if inc.exists():
            return inc.read_text(encoding="utf-8", errors="ignore")
        return ""

    def _extract_error_messages(self, text: str) -> list:
        """Extrae mensajes de error probables del texto del ticket."""
        messages = []
        # Mensajes entre comillas
        for match in re.finditer(r'"([^"]{10,80})"', text):
            msg = match.group(1).strip()
            if any(kw in msg.lower() for kw in ("error", "no se", "no pudo", "invalido", "encontrado")):
                messages.append(msg)
        # Mensajes despues de "Error:" o "Mensaje:"
        for match in re.finditer(r"(?:Error|Mensaje|Message)[:\s]+(.{10,100})", text, re.IGNORECASE):
            messages.append(match.group(1).strip()[:80])

        return list(dict.fromkeys(messages))[:3]

    def _build_hypothesis(self, inc_content: str, primary_location: Optional[str],
                          sections: list) -> str:
        """Construye una hipotesis sin LLM basada en los datos encontrados."""
        parts = []

        if primary_location:
            parts.append(f"El error probablemente se origina en `{primary_location}`.")

        # Detectar tipo de bug por keywords
        text_lower = inc_content.lower()
        if "null" in text_lower or "nulo" in text_lower:
            parts.append("El patron sugiere un NullReferenceException — verificar acceso a objeto antes de usarlo.")
        elif "timeout" in text_lower or "tiempo" in text_lower:
            parts.append("El patron sugiere un problema de performance o timeout — revisar queries sin indice.")
        elif "acceso" in text_lower or "permisos" in text_lower or "autoriza" in text_lower:
            parts.append("El patron sugiere un problema de permisos o autorizacion.")
        elif "conversion" in text_lower or "cast" in text_lower or "formato" in text_lower:
            parts.append("El patron sugiere un error de conversion de tipos o formato de datos.")

        if not parts:
            parts.append("Analisis preliminar insuficiente — revisar stack trace y logs manualmente.")

        return " ".join(parts)

    def _render_localization_file(self, ticket_id: str, sections: list,
                                  hypothesis: str, primary_location: Optional[str]) -> str:
        lines = [
            f"# Bug Localization — {ticket_id}",
            f"*Generado automaticamente por Stacky el {datetime.now().strftime('%Y-%m-%d %H:%M')}*",
            "",
            "## Hipotesis Preliminar",
            "",
            hypothesis,
            "",
        ]

        if primary_location:
            lines += [
                f"**Punto de falla probable:** `{primary_location}`",
                "",
            ]

        lines += ["---", ""]

        for title, content in sections:
            lines.append(f"## {title}")
            lines.append("")
            lines.append(content)
            lines.append("")
            lines.append("---")
            lines.append("")

        lines += [
            "## Instruccion para PM",
            "",
            "Este documento fue generado automaticamente antes de tu analisis.",
            "Usa la informacion de localizacion como punto de partida — NO la tomes como",
            "verdad absoluta. Puede haber falsos positivos. Valida contra el codigo real.",
            "",
        ]

        return "\n".join(lines)

    def _load_config(self) -> dict:
        cfg = BASE_DIR / "projects" / self.project_name / "config.json"
        if cfg.exists():
            try:
                return json.loads(cfg.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}
