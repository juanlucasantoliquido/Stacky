"""
tech_debt_analyzer.py — X-07: Indice de Deuda Tecnica con Priorizacion Automatica.

Analiza el historial de tickets procesados y construye un indice cuantificado
de deuda tecnica basado en evidencia real:
  - Frecuencia de tickets por modulo
  - Cantidad de reworks por modulo
  - Tiempo promedio de fix por modulo
  - Bugs recurrentes (mismo tipo en mismo modulo)
  - Patron de deuda sistemica (ej: null checks faltantes en toda la capa DAL)

Expone:
  get_heatmap_data()        → datos para el mapa de calor del dashboard (JSON)
  get_debt_report()         → reporte completo en Markdown
  suggest_refactoring()     → modulos candidatos a refactorizacion
  get_systemic_patterns()   → patrones que cruzan multiples modulos

Uso:
    from tech_debt_analyzer import TechDebtAnalyzer
    tda = TechDebtAnalyzer(project_name)
    heatmap = tda.get_heatmap_data()
    report  = tda.get_debt_report()
"""

import json
import logging
import re
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.tech_debt")

BASE_DIR = Path(__file__).parent

# Umbral para sugerir refactorizacion
DEFAULT_TICKET_THRESHOLD = 5
DEFAULT_REWORK_THRESHOLD = 2


class TechDebtAnalyzer:
    """
    Construye y expone un indice de deuda tecnica basado en historial de tickets Stacky.
    """

    def __init__(self, project_name: str):
        self.project_name  = project_name
        self._tickets_base = BASE_DIR / "projects" / project_name / "tickets"
        self._metrics_path = BASE_DIR / "projects" / project_name / "metrics.json"
        self._config       = self._load_config()
        self._threshold_tickets = self._config.get("debt_ticket_threshold", DEFAULT_TICKET_THRESHOLD)
        self._threshold_reworks = self._config.get("debt_rework_threshold", DEFAULT_REWORK_THRESHOLD)

    # ── API publica ──────────────────────────────────────────────────────────

    def get_heatmap_data(self) -> dict:
        """
        Retorna datos para el mapa de calor del dashboard.
        Formato optimizado para consumo desde JavaScript.
        """
        index = self._build_index()
        modules = []
        for module, data in sorted(
            index.items(), key=lambda x: x[1]["debt_score"], reverse=True
        ):
            modules.append({
                "module":        module,
                "ticket_count":  data["ticket_count"],
                "rework_count":  data["rework_count"],
                "avg_minutes":   round(data["avg_minutes"], 1) if data["avg_minutes"] else None,
                "debt_score":    round(data["debt_score"], 2),
                "level":         self._debt_level(data["debt_score"]),
                "last_touched":  data["last_touched"],
                "ticket_ids":    data["ticket_ids"][:5],
            })
        return {
            "project":       self.project_name,
            "generated_at":  datetime.now().isoformat(),
            "total_modules": len(modules),
            "modules":       modules,
            "systemic":      self.get_systemic_patterns(),
        }

    def get_debt_report(self) -> str:
        """Genera un reporte Markdown con el indice de deuda tecnica."""
        index = self._build_index()
        lines = [
            f"# Indice de Deuda Tecnica — {self.project_name}",
            f"*Generado: {datetime.now().strftime('%Y-%m-%d %H:%M')}*",
            "",
            "## Modulos por Nivel de Deuda",
            "",
            "| Modulo | Tickets | Reworks | Tiempo prom. | Deuda |",
            "|--------|---------|---------|--------------|-------|",
        ]
        for module, data in sorted(
            index.items(), key=lambda x: x[1]["debt_score"], reverse=True
        )[:20]:
            level = self._debt_level(data["debt_score"])
            avg   = f"{data['avg_minutes']:.0f}m" if data["avg_minutes"] else "N/A"
            lines.append(
                f"| `{module}` | {data['ticket_count']} | "
                f"{data['rework_count']} | {avg} | {level} |"
            )

        lines += ["", "## Candidatos a Refactorizacion", ""]
        suggestions = self.suggest_refactoring()
        if suggestions:
            for s in suggestions:
                lines.append(f"- **{s['module']}** — {s['reason']}")
        else:
            lines.append("_No se identificaron candidatos urgentes esta semana._")

        lines += ["", "## Patrones Sistemicos Detectados", ""]
        for pattern in self.get_systemic_patterns():
            lines.append(f"### {pattern['name']}")
            lines.append(f"{pattern['description']}")
            lines.append(f"- **Modulos afectados:** {', '.join(pattern['modules'][:5])}")
            lines.append(f"- **Tickets relacionados:** {pattern['ticket_count']}")
            lines.append(f"- **Recomendacion:** {pattern['recommendation']}")
            lines.append("")

        return "\n".join(lines)

    def suggest_refactoring(self) -> list:
        """Retorna lista de modulos candidatos a refactorizacion con justificacion."""
        index       = self._build_index()
        suggestions = []
        for module, data in index.items():
            reasons = []
            if data["ticket_count"] >= self._threshold_tickets:
                reasons.append(
                    f"{data['ticket_count']} tickets en los ultimos 90 dias"
                )
            if data["rework_count"] >= self._threshold_reworks:
                reasons.append(
                    f"{data['rework_count']} reworks QA→DEV"
                )
            if data["avg_minutes"] and data["avg_minutes"] > 90:
                reasons.append(
                    f"tiempo promedio de fix: {data['avg_minutes']:.0f}m (alto)"
                )
            if reasons:
                suggestions.append({
                    "module":      module,
                    "reason":      " + ".join(reasons),
                    "debt_score":  data["debt_score"],
                    "ticket_ids":  data["ticket_ids"][:3],
                })
        return sorted(suggestions, key=lambda x: x["debt_score"], reverse=True)[:10]

    def get_systemic_patterns(self) -> list:
        """Detecta patrones de deuda que cruzan multiples modulos."""
        tickets = self._load_all_tickets()
        patterns_raw: dict[str, list] = defaultdict(list)

        # Patron: null check faltante
        null_pattern = re.compile(
            r"null|nulo|NullReference|valor.*nulo|campo.*null", re.IGNORECASE
        )
        # Patron: performance / timeout
        perf_pattern = re.compile(
            r"lent[oa]|timeout|performance|demora|rendimiento|cuelga", re.IGNORECASE
        )
        # Patron: validacion de entrada
        valid_pattern = re.compile(
            r"validaci[oó]n|sin validar|falta.*validar|no valida", re.IGNORECASE
        )

        for ticket in tickets:
            desc = ticket.get("description", "")
            if null_pattern.search(desc):
                patterns_raw["null_checks"].append(ticket)
            if perf_pattern.search(desc):
                patterns_raw["performance"].append(ticket)
            if valid_pattern.search(desc):
                patterns_raw["validation"].append(ticket)

        results = []
        pattern_meta = {
            "null_checks": {
                "name":           "Null Checks Faltantes",
                "description":    "Multiples tickets causados por falta de validacion de nulos.",
                "recommendation": "Agregar analisis estatico de null-safety. Considerar extension Nullable en C#.",
            },
            "performance": {
                "name":           "Problemas de Performance Recurrentes",
                "description":    "Varios tickets con sintomas de lentitud o timeout.",
                "recommendation": "Revisar consultas Oracle sin indices. Agregar query profiler al pipeline CI.",
            },
            "validation": {
                "name":           "Validaciones de Entrada Faltantes",
                "description":    "Pattern recurrente de falta de validacion en capas BLL/UI.",
                "recommendation": "Crear clase de validacion centralizada. Agregar regla de code review.",
            },
        }

        for key, ticket_list in patterns_raw.items():
            if len(ticket_list) >= 3:
                modules = list({
                    m for t in ticket_list for m in t.get("files_touched", [])
                })[:6]
                meta = pattern_meta.get(key, {"name": key, "description": "", "recommendation": ""})
                results.append({
                    "pattern_id":    key,
                    "name":          meta["name"],
                    "description":   meta["description"],
                    "recommendation": meta["recommendation"],
                    "ticket_count":  len(ticket_list),
                    "modules":       modules,
                    "ticket_ids":    [t["ticket_id"] for t in ticket_list[:5]],
                })

        return sorted(results, key=lambda x: x["ticket_count"], reverse=True)

    # ── Privados ─────────────────────────────────────────────────────────────

    def _build_index(self) -> dict:
        """Construye el indice de deuda por modulo desde el historial."""
        tickets = self._load_all_tickets()
        cutoff  = datetime.now() - timedelta(days=90)

        index: dict[str, dict] = {}

        for ticket in tickets:
            ts_str = ticket.get("completed_at", "")
            try:
                ts = datetime.fromisoformat(ts_str[:19]) if ts_str else None
            except Exception:
                ts = None

            if ts and ts < cutoff:
                continue

            for mod in ticket.get("files_touched", []):
                if mod not in index:
                    index[mod] = {
                        "ticket_count": 0,
                        "rework_count": 0,
                        "total_minutes": 0.0,
                        "count_with_time": 0,
                        "avg_minutes": None,
                        "last_touched": "",
                        "ticket_ids": [],
                        "debt_score": 0.0,
                    }
                entry = index[mod]
                entry["ticket_count"] += 1
                entry["ticket_ids"].append(ticket.get("ticket_id", ""))
                if ticket.get("rework"):
                    entry["rework_count"] += 1
                dur = ticket.get("total_minutes")
                if dur:
                    entry["total_minutes"]    += dur
                    entry["count_with_time"]  += 1
                if ts_str > entry["last_touched"]:
                    entry["last_touched"] = ts_str[:10]

            # Calcular avg y debt_score
        for mod, data in index.items():
            if data["count_with_time"]:
                data["avg_minutes"] = data["total_minutes"] / data["count_with_time"]
            # Debt score: tickets * 1 + reworks * 2 + tiempo_excess * 0.5
            time_factor = max(0, (data["avg_minutes"] or 0) - 60) * 0.5 / 60
            data["debt_score"] = (
                data["ticket_count"] * 1.0
                + data["rework_count"] * 2.0
                + time_factor
            )

        return index

    def _load_all_tickets(self) -> list:
        """
        Carga historial de tickets completados desde metrics.json y carpetas.
        """
        tickets = []

        # Desde metrics.json
        if self._metrics_path.exists():
            try:
                metrics = json.loads(self._metrics_path.read_text(encoding="utf-8"))
                for run in metrics.get("runs", []):
                    if run.get("stage") == "tester" and run.get("success"):
                        tickets.append({
                            "ticket_id":    run.get("ticket_id", ""),
                            "files_touched": run.get("files_touched", []),
                            "rework":       run.get("rework", False),
                            "total_minutes": run.get("duration_minutes"),
                            "completed_at": run.get("end_time", ""),
                            "description":  run.get("ticket_summary", ""),
                        })
            except Exception as exc:
                logger.debug("[X-07] Error leyendo metrics: %s", exc)

        # Complementar con carpetas de tickets completados
        completed_dir = self._tickets_base / "completado" if self._tickets_base.exists() else None
        if completed_dir and completed_dir.exists():
            for ticket_folder in completed_dir.iterdir():
                if not ticket_folder.is_dir():
                    continue
                ticket_id = ticket_folder.name
                # Evitar duplicados
                if any(t["ticket_id"] == ticket_id for t in tickets):
                    continue

                files = self._extract_files_from_folder(ticket_folder)
                description = self._read_inc_snippet(ticket_folder)
                tickets.append({
                    "ticket_id":    ticket_id,
                    "files_touched": files,
                    "rework":       False,
                    "total_minutes": None,
                    "completed_at": "",
                    "description":  description,
                })

        return tickets

    def _extract_files_from_folder(self, folder: Path) -> list:
        files = set()
        for fname in ("GIT_CHANGES.md", "ARQUITECTURA_SOLUCION.md"):
            fpath = folder / fname
            if fpath.exists():
                content = fpath.read_text(encoding="utf-8", errors="ignore")
                for match in re.finditer(
                    r"[\w.\-]+\.(?:cs|aspx|vb|sql|config|aspx\.cs)", content
                ):
                    files.add(match.group(0))
        return list(files)

    def _read_inc_snippet(self, folder: Path) -> str:
        for f in folder.glob("INC-*.md"):
            try:
                return f.read_text(encoding="utf-8", errors="ignore")[:500]
            except Exception:
                pass
        return ""

    def _debt_level(self, score: float) -> str:
        if score >= 8:
            return "🔴 CRITICO"
        if score >= 5:
            return "🟠 ALTO"
        if score >= 3:
            return "🟡 MEDIO"
        return "🟢 BAJO"

    def _load_config(self) -> dict:
        cfg = BASE_DIR / "projects" / self.project_name / "config.json"
        if cfg.exists():
            try:
                return json.loads(cfg.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}
