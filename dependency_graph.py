"""
dependency_graph.py — E-03: Grafo de Dependencias entre Tickets.

Rastrea qué tickets dependen de otros tickets (mismo módulo, misma tabla,
mismo archivo) para detectar conflictos antes de que lleguen a producción.

Cuando dos tickets activos modifican el mismo archivo, genera una alerta
de conflicto potencial.

Uso:
    from dependency_graph import DependencyGraph
    dg = DependencyGraph(tickets_base, project_name)
    dg.update_ticket(ticket_id, ticket_folder)
    conflicts = dg.find_conflicts(ticket_id)
    report = dg.format_conflict_report(ticket_id)
"""

import json
import logging
import os
import re
import threading
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("mantis.dependency_graph")


class DependencyGraph:
    """
    Grafo de dependencias entre tickets activos basado en archivos compartidos.
    """

    def __init__(self, tickets_base: str, project_name: str):
        self._tickets_base = tickets_base
        self._project      = project_name
        self._lock         = threading.RLock()
        self._path         = self._get_path()
        self._data         = self._load()

    # ── API pública ───────────────────────────────────────────────────────

    def update_ticket(self, ticket_id: str, ticket_folder: str) -> None:
        """Actualiza el grafo con los archivos del ticket."""
        files = self._extract_files(ticket_folder)
        tables = self._extract_tables(ticket_folder)

        with self._lock:
            nodes = self._data.setdefault("nodes", {})
            nodes[ticket_id] = {
                "files":      files,
                "tables":     tables,
                "updated_at": datetime.now().isoformat(),
                "folder":     ticket_folder,
            }
            self._save()

    def find_conflicts(self, ticket_id: str) -> list[dict]:
        """
        Encuentra tickets activos que comparten archivos/tablas con ticket_id.
        Retorna lista de conflictos con detalle.
        """
        with self._lock:
            nodes = self._data.get("nodes", {})
            me = nodes.get(ticket_id)
            if not me:
                return []

            my_files  = set(me.get("files", []))
            my_tables = set(me.get("tables", []))
            conflicts = []

            for other_id, other in nodes.items():
                if other_id == ticket_id:
                    continue

                # Verificar que el otro ticket sigue activo
                if not self._is_active(other.get("folder", ""), other_id):
                    continue

                shared_files  = my_files  & set(other.get("files", []))
                shared_tables = my_tables & set(other.get("tables", []))

                if shared_files or shared_tables:
                    severity = "HIGH" if len(shared_files) > 2 else \
                               "MEDIUM" if shared_files else "LOW"
                    conflicts.append({
                        "other_ticket":  other_id,
                        "shared_files":  list(shared_files),
                        "shared_tables": list(shared_tables),
                        "severity":      severity,
                    })

            conflicts.sort(key=lambda x: {"HIGH": 0, "MEDIUM": 1, "LOW": 2}[x["severity"]])
            return conflicts

    def format_conflict_report(self, ticket_id: str) -> str:
        """Formatea los conflictos como sección Markdown para prompts."""
        conflicts = self.find_conflicts(ticket_id)
        if not conflicts:
            return ""

        lines = [
            "",
            "---",
            "",
            "## ⚠️ Conflictos Potenciales con Otros Tickets",
            "",
            "_Los siguientes tickets activos modifican archivos o tablas en común._",
            "",
        ]
        for c in conflicts:
            sev_icon = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}.get(c["severity"], "")
            lines.append(f"### {sev_icon} Ticket #{c['other_ticket']} — {c['severity']}")
            lines.append("")
            if c["shared_files"]:
                lines.append(f"**Archivos en conflicto:** {', '.join(c['shared_files'][:5])}")
            if c["shared_tables"]:
                lines.append(f"**Tablas en conflicto:** {', '.join(c['shared_tables'][:5])}")
            lines.append("")
            lines.append("_Coordinar con el desarrollador responsable antes de hacer commit._")
            lines.append("")

        return "\n".join(lines)

    def remove_ticket(self, ticket_id: str) -> None:
        """Elimina un ticket del grafo (cuando se completa o archiva)."""
        with self._lock:
            self._data.get("nodes", {}).pop(ticket_id, None)
            self._save()

    # ── Internals ─────────────────────────────────────────────────────────

    @staticmethod
    def _extract_files(ticket_folder: str) -> list[str]:
        files: set[str] = set()
        for fname in ["ARQUITECTURA_SOLUCION.md", "DEV_COMPLETADO.md", "SVN_CHANGES.md"]:
            fpath = os.path.join(ticket_folder, fname)
            if not os.path.exists(fpath):
                continue
            try:
                content = Path(fpath).read_text(encoding="utf-8", errors="replace")
                for m in re.finditer(r'([\w/\\.\-]+\.(?:cs|aspx\.cs|aspx|sql|vb))',
                                     content, re.IGNORECASE):
                    f = m.group(1).replace("\\", "/")
                    if "mantis" not in f.lower():
                        files.add(os.path.basename(f).lower())
            except Exception:
                pass
        return list(files)[:20]

    @staticmethod
    def _extract_tables(ticket_folder: str) -> list[str]:
        tables: set[str] = set()
        for fname in ["ANALISIS_TECNICO.md", "ARQUITECTURA_SOLUCION.md"]:
            fpath = os.path.join(ticket_folder, fname)
            if not os.path.exists(fpath):
                continue
            try:
                content = Path(fpath).read_text(encoding="utf-8", errors="replace")
                for m in re.finditer(
                    r'\b((?:RST|RPL|RIP|RMB|RMS|RPY|RCT)[_A-Z0-9]{3,25})\b',
                    content
                ):
                    tables.add(m.group(1).upper())
            except Exception:
                pass
        return list(tables)[:15]

    @staticmethod
    def _is_active(folder: str, ticket_id: str) -> bool:
        """Verifica si el ticket sigue activo (no completado/archivado)."""
        if not folder or not os.path.isdir(folder):
            return False
        tester_path = os.path.join(folder, "TESTER_COMPLETADO.md")
        return not os.path.exists(tester_path)

    def _get_path(self) -> str:
        base = os.path.dirname(os.path.abspath(__file__))
        kb   = os.path.join(base, "knowledge", self._project)
        os.makedirs(kb, exist_ok=True)
        return os.path.join(kb, "dependency_graph.json")

    def _load(self) -> dict:
        try:
            with open(self._path, encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return {"nodes": {}}
        except Exception as e:
            logger.warning("[DEP_GRAPH] Error cargando: %s", e)
            return {"nodes": {}}

    def _save(self) -> None:
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error("[DEP_GRAPH] Error guardando: %s", e)


# ── Singleton por proyecto ────────────────────────────────────────────────────

_dg_instances: dict[str, DependencyGraph] = {}
_dg_lock = threading.Lock()


def get_dependency_graph(tickets_base: str, project_name: str) -> DependencyGraph:
    with _dg_lock:
        if project_name not in _dg_instances:
            _dg_instances[project_name] = DependencyGraph(tickets_base, project_name)
        return _dg_instances[project_name]
