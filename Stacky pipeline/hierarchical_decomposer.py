"""
hierarchical_decomposer.py — Tickets complejos → N sub-pipelines en paralelo.

Cuando PM detecta que un ticket tiene 3+ componentes independientes, genera
sub-tickets con contextos independientes y los lanza en paralelo.

Uso:
    from hierarchical_decomposer import HierarchicalDecomposer
    decomposer = HierarchicalDecomposer()
    if decomposer.should_decompose(tareas_content):
        sub_tickets = decomposer.decompose(ticket_folder, parent_wi_id)
"""

import logging
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.hierarchical_decomposer")


@dataclass
class SubTicket:
    folder: str
    ado_id: Optional[int]
    component: str
    tasks: list[str]


class HierarchicalDecomposer:
    MIN_COMPONENTS_FOR_SPLIT = 3

    def __init__(self, ado_task_creator=None):
        self._ado_task_creator = ado_task_creator

    @property
    def ado_task_creator(self):
        if self._ado_task_creator is None:
            try:
                from ado_task_creator import ADOTaskCreator
                self._ado_task_creator = ADOTaskCreator()
            except ImportError:
                pass
        return self._ado_task_creator

    def should_decompose(self, tareas_md_content: str) -> bool:
        components = self._extract_components(tareas_md_content)
        return len(components) >= self.MIN_COMPONENTS_FOR_SPLIT

    def decompose(
        self, ticket_folder: str, parent_work_item_id: int = 0
    ) -> list[SubTicket]:
        folder = Path(ticket_folder)
        tareas_path = folder / "TAREAS_DESARROLLO.md"
        if not tareas_path.exists():
            return []

        components = self._extract_components(
            tareas_path.read_text(encoding="utf-8", errors="replace")
        )
        if len(components) < self.MIN_COMPONENTS_FOR_SPLIT:
            return []

        sub_tickets = []
        for i, component in enumerate(components):
            sub_folder = folder / f"sub_{i+1}_{self._safe_name(component['name'])}"
            sub_folder.mkdir(exist_ok=True)
            self._write_sub_context(sub_folder, component, ticket_folder)

            child_id = None
            if parent_work_item_id and self.ado_task_creator:
                try:
                    child_id = self.ado_task_creator._create_child_task(
                        parent_work_item_id,
                        {"title": f"Sub-pipeline: {component['name']}",
                         "description": "\n".join(component.get("tasks", [])),
                         "file": ""},
                        "Strategist_Pacifico"
                    )
                except Exception as e:
                    logger.warning("Failed to create child task for %s: %s",
                                   component["name"], e)

            sub_tickets.append(SubTicket(
                folder=str(sub_folder),
                ado_id=child_id,
                component=component["name"],
                tasks=component.get("tasks", []),
            ))

        logger.info("Decomposed ticket into %d sub-tickets: %s",
                     len(sub_tickets),
                     [st.component for st in sub_tickets])
        return sub_tickets

    def _extract_components(self, tareas_content: str) -> list[dict]:
        components = {}
        section_pattern = re.compile(
            r"^##\s*\[\w+\]\s*(.+?)(?:\s*—\s*(.+))?$", re.MULTILINE
        )
        sections = list(section_pattern.finditer(tareas_content))

        for i, match in enumerate(sections):
            title = match.group(1).strip()
            component_hint = match.group(2).strip() if match.group(2) else self._infer_component(title)
            start = match.end()
            end = sections[i + 1].start() if i + 1 < len(sections) else len(tareas_content)
            body = tareas_content[start:end].strip()

            if component_hint not in components:
                components[component_hint] = {"name": component_hint, "tasks": []}
            components[component_hint]["tasks"].append(f"## {title}\n{body}")

        if not components:
            checkbox_pattern = re.compile(r"^-\s*\[[ x]\]\s*(.+)$", re.MULTILINE | re.IGNORECASE)
            matches = checkbox_pattern.findall(tareas_content)
            for task_text in matches:
                comp = self._infer_component(task_text)
                if comp not in components:
                    components[comp] = {"name": comp, "tasks": []}
                components[comp]["tasks"].append(task_text)

        return list(components.values())

    def _infer_component(self, text: str) -> str:
        text_lower = text.lower()
        if any(k in text_lower for k in ["dalc", "dal", "negocio", "batch"]):
            return "Batch"
        elif any(k in text_lower for k in ["aspx", "frm", "online", "frontend"]):
            return "OnLine"
        elif any(k in text_lower for k in ["sql", "ddl", "tabla", "alter", "bd"]):
            return "BD"
        elif any(k in text_lower for k in ["vb", "visual basic"]):
            return "VB"
        return "General"

    def _write_sub_context(self, sub_folder: Path, component: dict, parent_folder: str):
        parent = Path(parent_folder)
        for fname in ["INCIDENTE.md", "ANALISIS_TECNICO.md"]:
            src = parent / fname
            if src.exists():
                shutil.copy2(src, sub_folder / fname)

        tareas = "\n\n".join(component.get("tasks", []))
        (sub_folder / "TAREAS_DESARROLLO.md").write_text(
            f"# Tareas — Sub-pipeline: {component['name']}\n\n{tareas}",
            encoding="utf-8"
        )
        (sub_folder / "ARQUITECTURA_SOLUCION.md").write_text(
            f"# Arquitectura — Componente: {component['name']}\n\n"
            f"Sub-pipeline enfocado en el componente {component['name']}.\n",
            encoding="utf-8"
        )

    def _safe_name(self, name: str) -> str:
        return re.sub(r"[^a-zA-Z0-9_]", "_", name)[:30]
