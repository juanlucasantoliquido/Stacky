"""
ridioma_knowledge_registry.py — Catálogo vivo de campos RIDIOMA inyectado en prompts DEV.

RIDIOMA es el lenguaje de campos del sistema Pacifico. Cuando DEV no conoce el campo
exacto, genera código con nombres incorrectos. Este módulo extrae los campos mencionados
en los artefactos PM y los enriquece con sus definiciones del catálogo.

Uso:
    from ridioma_knowledge_registry import RIDIOMAKnowledgeRegistry
    registry = RIDIOMAKnowledgeRegistry()
    block = registry.build_context_block(ticket_folder)
"""

import re
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.ridioma_registry")

# Pattern to detect RIDIOMA field names in text
# RIDIOMA fields follow patterns like: RCOD_CLIE, RDESC_PROD, RFEC_PAGO, etc.
RIDIOMA_FIELD_PATTERN = re.compile(
    r"\b(R[A-Z]{2,5}_[A-Z]{2,10}(?:_[A-Z]{2,10})?)\b"
)

# Additional known prefixes
KNOWN_PREFIXES = re.compile(
    r"\b(RCOD|RDESC|RFEC|RNRO|RIMP|RCANT|REST|RTIP|ROBS|RNOM|RDIR|RTEL|RMAIL)\w+\b"
)


class RIDIOMAKnowledgeRegistry:
    """
    Extracts RIDIOMA field references from PM artifacts and enriches
    DEV prompts with their catalog definitions.
    """

    def __init__(self, ridioma_lookup=None):
        self._ridioma_lookup = ridioma_lookup

    @property
    def ridioma_lookup(self):
        if self._ridioma_lookup is None:
            try:
                from ridioma_lookup import RIDIOMALookup
                self._ridioma_lookup = RIDIOMALookup()
            except ImportError:
                logger.warning("ridioma_lookup module not available")
                self._ridioma_lookup = _FallbackLookup()
        return self._ridioma_lookup

    def build_context_block(self, ticket_folder: str) -> str:
        """
        Extract RIDIOMA fields from PM artifacts and return a markdown block
        with their definitions for injection into the DEV prompt.

        Returns empty string if no fields found.
        """
        fields = self._extract_fields_from_artifacts(ticket_folder)
        if not fields:
            return ""

        lines = [
            "### Contexto RIDIOMA — campos del sistema referenciados",
            "",
        ]

        resolved = 0
        unresolved = 0
        for field_name in sorted(fields):
            definition = self._lookup_field(field_name)
            if definition:
                lines.append(
                    f"- `{field_name}`: {definition.get('description', 'N/A')} "
                    f"(tabla: {definition.get('table', '?')}, "
                    f"tipo: {definition.get('type', '?')})"
                )
                resolved += 1
            else:
                lines.append(
                    f"- `{field_name}`: ⚠️ campo no encontrado en catálogo — "
                    f"verificar nombre exacto antes de usar"
                )
                unresolved += 1

        lines.append("")
        if unresolved > 0:
            lines.append(
                f"⚠️ {unresolved} campo(s) no encontrado(s) en el catálogo RIDIOMA. "
                f"Verificá los nombres exactos en la BD antes de codificar."
            )

        logger.info("RIDIOMA context: %d fields (%d resolved, %d unresolved)",
                     len(fields), resolved, unresolved)
        return "\n".join(lines)

    def _extract_fields_from_artifacts(self, ticket_folder: str) -> set[str]:
        """Extract all RIDIOMA field names from PM artifacts."""
        folder = Path(ticket_folder)
        fields = set()

        # Files to scan for RIDIOMA references
        scan_files = [
            "ARQUITECTURA_SOLUCION.md",
            "ANALISIS_TECNICO.md",
            "TAREAS_DESARROLLO.md",
            "NOTAS_IMPLEMENTACION.md",
            "QUERIES_ANALISIS.sql",
        ]

        for fname in scan_files:
            fpath = folder / fname
            if not fpath.exists():
                continue
            try:
                content = fpath.read_text(encoding="utf-8", errors="replace")
                # Find RIDIOMA field patterns
                for match in RIDIOMA_FIELD_PATTERN.finditer(content):
                    fields.add(match.group(1))
                for match in KNOWN_PREFIXES.finditer(content):
                    fields.add(match.group(0))
            except Exception as e:
                logger.warning("Error reading %s: %s", fpath, e)

        return fields

    def _lookup_field(self, field_name: str) -> Optional[dict]:
        """Look up a RIDIOMA field definition from the catalog."""
        try:
            if hasattr(self.ridioma_lookup, "get"):
                return self.ridioma_lookup.get(field_name)
            elif hasattr(self.ridioma_lookup, "lookup"):
                return self.ridioma_lookup.lookup(field_name)
            elif hasattr(self.ridioma_lookup, "search"):
                results = self.ridioma_lookup.search(field_name)
                return results[0] if results else None
        except Exception as e:
            logger.debug("Lookup failed for '%s': %s", field_name, e)
        return None


class _FallbackLookup:
    """Fallback when ridioma_lookup module is not available."""

    def get(self, field_name: str) -> Optional[dict]:
        return None

    def lookup(self, field_name: str) -> Optional[dict]:
        return None
