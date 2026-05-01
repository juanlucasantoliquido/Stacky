"""
project_learner.py — E-11: Fase de Aprendizaje de Proyecto (Project Onboarding IA).

Cuando Stacky encuentra un proyecto nuevo o sin documentación base,
ejecuta una fase de aprendizaje estructurada en 4 etapas:

  Fase 1 — Exploración: scrapea la estructura de carpetas y archivos
  Fase 2 — Análisis: extrae convenciones del codebase (naming, patterns)
  Fase 3 — Documentación: genera PROYECTO_CONTEXT.md con el conocimiento base
  Fase 4 — Prompts: genera prompts PM/DEV/QA personalizados para el proyecto

El aprendizaje se activa desde el dashboard ("Botón Aprender Proyecto")
o automáticamente cuando se detecta un proyecto sin contexto.

Uso:
    from project_learner import ProjectLearner
    pl = ProjectLearner(project_name, workspace_root)
    pl.run_learning_phase()  # ejecuta las 4 fases
    pl.get_status()          # estado actual del aprendizaje
"""

import json
import logging
import os
import re
import threading
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("stacky.project_learner")

_SKIP_DIRS = {"bin", "obj", "packages", ".vs", ".git", ".svn",
              "node_modules", "TestResults", "temp", "tmp"}
_CODE_EXTS  = {".cs", ".aspx", ".aspx.cs", ".vb", ".sql", ".config"}
_MAX_FILES_TO_SAMPLE = 200
_MAX_FILE_CONTENT   = 3000


class ProjectLearner:
    """
    Aprende las convenciones y estructura de un proyecto .NET para
    personalizar los prompts de Stacky.
    """

    def __init__(self, project_name: str, workspace_root: str):
        self._project    = project_name
        self._workspace  = workspace_root
        self._output_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "projects", project_name
        )
        os.makedirs(self._output_dir, exist_ok=True)
        self._state_path = os.path.join(self._output_dir, "learning_state.json")
        self._state      = self._load_state()
        self._lock       = threading.RLock()

    # ── API pública ───────────────────────────────────────────────────────

    def run_learning_phase(self, phases: list[int] | None = None) -> dict:
        """
        Ejecuta la fase de aprendizaje completa o fases específicas.
        phases: [1,2,3,4] o None para todas.
        Retorna dict con resultados por fase.
        """
        phases = phases or [1, 2, 3, 4]
        results: dict = {}

        self._update_state("learning", "started")

        if 1 in phases:
            logger.info("[LEARNER] Fase 1 — Explorando estructura...")
            results["phase1"] = self._phase1_explore()
            self._update_state("phase1", "done")

        if 2 in phases:
            logger.info("[LEARNER] Fase 2 — Analizando convenciones...")
            results["phase2"] = self._phase2_analyze()
            self._update_state("phase2", "done")

        if 3 in phases:
            logger.info("[LEARNER] Fase 3 — Generando documentación base...")
            results["phase3"] = self._phase3_document(results)
            self._update_state("phase3", "done")

        if 4 in phases:
            logger.info("[LEARNER] Fase 4 — Personalizando prompts...")
            results["phase4"] = self._phase4_prompts(results)
            self._update_state("phase4", "done")

        self._update_state("learning", "completed")
        return results

    def is_learning_complete(self) -> bool:
        """Retorna True si el aprendizaje del proyecto ya fue completado."""
        return self._state.get("learning") == "completed"

    def get_status(self) -> dict:
        """Retorna el estado actual del aprendizaje."""
        return {
            "project":    self._project,
            "workspace":  self._workspace,
            "state":      dict(self._state),
            "context_exists": os.path.exists(
                os.path.join(self._output_dir, "PROYECTO_CONTEXT.md")
            ),
        }

    def get_project_context(self) -> str:
        """Retorna el contenido de PROYECTO_CONTEXT.md si existe."""
        ctx_path = os.path.join(self._output_dir, "PROYECTO_CONTEXT.md")
        try:
            return Path(ctx_path).read_text(encoding="utf-8", errors="replace")
        except Exception:
            return ""

    # ── Fases ─────────────────────────────────────────────────────────────

    def _phase1_explore(self) -> dict:
        """Fase 1: Escanea la estructura de archivos y carpetas."""
        structure: dict = {
            "directories": [],
            "file_counts": {},
            "sample_files": [],
            "total_files": 0,
        }

        for root, dirs, files in os.walk(self._workspace):
            dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
            rel_root = os.path.relpath(root, self._workspace).replace("\\", "/")

            for f in files:
                ext = os.path.splitext(f)[1].lower()
                if ext in _CODE_EXTS:
                    structure["total_files"] += 1
                    structure["file_counts"][ext] = \
                        structure["file_counts"].get(ext, 0) + 1

                    if len(structure["sample_files"]) < _MAX_FILES_TO_SAMPLE:
                        structure["sample_files"].append(
                            f"{rel_root}/{f}".lstrip("./")
                        )

            if rel_root and rel_root != ".":
                structure["directories"].append(rel_root)

        structure["directories"] = structure["directories"][:100]
        self._save_phase_data("phase1", structure)
        logger.info("[LEARNER] Fase 1: %d archivos en %d dirs",
                    structure["total_files"], len(structure["directories"]))
        return structure

    def _phase2_analyze(self) -> dict:
        """Fase 2: Analiza convenciones del codebase."""
        conventions: dict = {
            "naming": {},
            "dal_pattern": "",
            "bll_pattern": "",
            "ui_pattern":  "",
            "error_handling": "",
            "db_connection": "",
            "key_classes": [],
        }

        phase1 = self._load_phase_data("phase1") or {}
        sample_files = phase1.get("sample_files", [])[:50]

        all_content = ""
        for rel_path in sample_files:
            full_path = os.path.join(self._workspace, rel_path)
            try:
                content = Path(full_path).read_text(
                    encoding="utf-8", errors="replace")[:_MAX_FILE_CONTENT]
                all_content += content + "\n"
            except Exception:
                pass

        # Detectar patrones de naming
        frm_classes = re.findall(r'\bclass\s+(Frm\w+)\b', all_content)
        dal_classes = re.findall(r'\bclass\s+(DAL_?\w+)\b', all_content, re.IGNORECASE)
        bll_classes = re.findall(r'\bclass\s+(BLL_?\w+)\b', all_content, re.IGNORECASE)

        conventions["naming"] = {
            "ui_prefix":  "Frm" if frm_classes else "Form",
            "dal_prefix": "DAL_" if dal_classes else "Data",
            "bll_prefix": "BLL_" if bll_classes else "Business",
        }

        # DAL pattern
        if "OracleCommand" in all_content:
            conventions["dal_pattern"] = "OracleCommand (ADO.NET directo)"
        elif "SqlCommand" in all_content:
            conventions["dal_pattern"] = "SqlCommand (SQL Server ADO.NET)"
        elif "DbContext" in all_content:
            conventions["dal_pattern"] = "Entity Framework (DbContext)"

        # Error handling
        if "log.Error" in all_content.lower() or "logger.Error" in all_content.lower():
            conventions["error_handling"] = "log4net/NLog con Log.Error()"
        elif "Console.Write" in all_content:
            conventions["error_handling"] = "Console.WriteLine"

        # i18n pattern
        if "Idm.Texto" in all_content:
            conventions["i18n"] = "Idm.Texto(coMens.mXXXX)"
        elif "Resources." in all_content:
            conventions["i18n"] = "ASP.NET Resources"
        else:
            conventions["i18n"] = "strings directos"

        # Key classes
        key_classes = list(set(frm_classes[:5] + dal_classes[:3] + bll_classes[:3]))
        conventions["key_classes"] = key_classes[:10]

        self._save_phase_data("phase2", conventions)
        return conventions

    def _phase3_document(self, results: dict) -> dict:
        """Fase 3: Genera PROYECTO_CONTEXT.md."""
        phase1 = results.get("phase1", self._load_phase_data("phase1") or {})
        phase2 = results.get("phase2", self._load_phase_data("phase2") or {})

        naming = phase2.get("naming", {})
        lines  = [
            f"# Contexto del Proyecto — {self._project}",
            "",
            f"> Aprendizaje automático generado por Stacky el {datetime.now().strftime('%Y-%m-%d')}",
            "",
            "---",
            "",
            "## Estructura General",
            "",
            f"- **Total de archivos de código:** {phase1.get('total_files', '?')}",
            f"- **Tipos de archivo:** "
            + ", ".join(f"{ext}: {n}" for ext, n in
                        sorted(phase1.get('file_counts', {}).items())),
            "",
            "## Convenciones de Código",
            "",
            f"- **Capa UI:** Prefijo `{naming.get('ui_prefix', 'Frm')}` para formularios WebForms",
            f"- **Capa DAL:** Prefijo `{naming.get('dal_prefix', 'DAL_')}` — patrón: {phase2.get('dal_pattern', 'OracleCommand')}",
            f"- **Capa BLL:** Prefijo `{naming.get('bll_prefix', 'BLL_')}` para lógica de negocio",
            f"- **Manejo de errores:** {phase2.get('error_handling', 'log4net')}",
            f"- **i18n:** {phase2.get('i18n', 'Idm.Texto()')}",
            "",
            "## Clases Clave Detectadas",
            "",
        ]

        for cls in phase2.get("key_classes", []):
            lines.append(f"- `{cls}`")

        lines += [
            "",
            "## Notas para el PM/DEV",
            "",
            "- Al modificar la capa UI, buscar el formulario con prefijo correspondiente",
            "- Los cambios de DB van en la capa DAL con OracleCommand parametrizado",
            "- Los mensajes de error al usuario usan el patrón i18n del proyecto",
            "- Ver BLAST_RADIUS.md antes de modificar clases muy referenciadas",
            "",
            "_Contexto generado automáticamente. Editar manualmente si es incorrecto._",
        ]

        ctx_path = os.path.join(self._output_dir, "PROYECTO_CONTEXT.md")
        try:
            Path(ctx_path).write_text("\n".join(lines), encoding="utf-8")
            logger.info("[LEARNER] PROYECTO_CONTEXT.md generado")
        except Exception as e:
            logger.error("[LEARNER] Error escribiendo contexto: %s", e)

        return {"context_path": ctx_path, "lines": len(lines)}

    def _phase4_prompts(self, results: dict) -> dict:
        """Fase 4: Genera prompts personalizados para el proyecto."""
        phase2    = results.get("phase2", self._load_phase_data("phase2") or {})
        context   = self.get_project_context()[:1000]
        naming    = phase2.get("naming", {})
        dal_pat   = phase2.get("dal_pattern", "OracleCommand")
        i18n      = phase2.get("i18n", "Idm.Texto(coMens.mXXXX)")

        pm_addendum = f"""
## Contexto específico del proyecto {self._project}

- UI: formularios con prefijo `{naming.get('ui_prefix', 'Frm')}`
- DAL: `{naming.get('dal_prefix', 'DAL_')}` usando {dal_pat}
- Mensajes i18n: `{i18n}`
- Siempre parametrizar queries Oracle con OracleParameter
- Validaciones en BLL, no en code-behind
"""

        dev_addendum = f"""
## Stack técnico — {self._project}

- ASP.NET WebForms (.aspx + code-behind .cs)
- {dal_pat} para acceso a Oracle
- Patrón: UI ({naming.get('ui_prefix', 'Frm')}Xxx) → BLL ({naming.get('bll_prefix', 'BLL_')}Xxx) → DAL ({naming.get('dal_prefix', 'DAL_')}Xxx)
- Mensajes de error: `{i18n}`
- No usar LINQ to SQL ni Entity Framework
"""

        # Guardar addenda de prompts
        for fname, content in [("PM_ADDENDUM.md", pm_addendum),
                                ("DEV_ADDENDUM.md", dev_addendum)]:
            path = os.path.join(self._output_dir, fname)
            try:
                Path(path).write_text(content, encoding="utf-8")
            except Exception:
                pass

        return {"pm_addendum": len(pm_addendum), "dev_addendum": len(dev_addendum)}

    # ── Helpers ───────────────────────────────────────────────────────────

    def _update_state(self, key: str, value: str) -> None:
        with self._lock:
            self._state[key] = value
            self._state["updated_at"] = datetime.now().isoformat()
            try:
                with open(self._state_path, "w", encoding="utf-8") as f:
                    json.dump(self._state, f, indent=2, ensure_ascii=False)
            except Exception:
                pass

    def _save_phase_data(self, phase: str, data: dict) -> None:
        path = os.path.join(self._output_dir, f"{phase}_data.json")
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def _load_phase_data(self, phase: str) -> dict | None:
        path = os.path.join(self._output_dir, f"{phase}_data.json")
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def _load_state(self) -> dict:
        try:
            with open(self._state_path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
