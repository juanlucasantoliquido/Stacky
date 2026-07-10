"""Plan 113 — Documentador agéntico 1-click.

Agente que reconstruye/normaliza/completa/enriquece la documentación de un
proyecto a formato Obsidian, con anti-alucinación operacionalizado (marcas
[V]/[INF]/[NV] + trazabilidad archivo:línea). El agente SOLO propone el
artefacto estructurado; un aplicador determinista (services/doc_documenter.py)
valida y escribe a una rama git dedicada y revertible.
"""
from __future__ import annotations

from .base import BaseAgent


class DocumenterAgent(BaseAgent):
    type = "Documentador"
    name = "Documentador"
    icon = "📝"
    description = "Genera/corrige documentación técnica en formato Obsidian, anti-alucinación"
    inputs_hint = ["árbol y símbolos del módulo", "notas existentes", "subgrafo documental"]
    outputs_hint = ["bloques DOC con frontmatter, wikilinks y marcas [V]/[INF]/[NV]"]
    default_blocks = ["module-tree", "existing-notes", "doc-subgraph"]

    def system_prompt(self) -> str:
        from services.doc_documenter import _DEFAULT_DOCUMENTADOR_PROMPT
        return _DEFAULT_DOCUMENTADOR_PROMPT
