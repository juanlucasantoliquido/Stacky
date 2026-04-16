"""
meta_analyst.py — E-09: Análisis de Causa Raíz Sistémico (Meta-PM).

Periódicamente analiza el conjunto de tickets completados para detectar:
  - Patrones sistémicos de bugs (mismo módulo, misma causa raíz recurrente)
  - Módulos con alta tasa de rework
  - Tipos de tickets que tardan más
  - Recomendaciones de mejora de arquitectura

Genera META_ANALYSIS.md con insights accionables y puede auto-actualizar
configuraciones del pipeline.

Uso:
    from meta_analyst import MetaAnalyst
    ma = MetaAnalyst(tickets_base, project_name)
    report = ma.run_analysis()  # retorna path al reporte
"""

import json
import logging
import os
import re
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger("mantis.meta_analyst")

_ANALYSIS_WINDOW_DAYS = 30
_MIN_TICKETS_FOR_ANALYSIS = 5


class MetaAnalyst:
    """
    Analiza tendencias sistémicas en el historial de tickets procesados.
    """

    def __init__(self, tickets_base: str, project_name: str):
        self._tickets_base = tickets_base
        self._project      = project_name
        self._output_dir   = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "knowledge", project_name
        )
        os.makedirs(self._output_dir, exist_ok=True)

    # ── API pública ───────────────────────────────────────────────────────

    def run_analysis(self, days: int = _ANALYSIS_WINDOW_DAYS) -> str | None:
        """
        Ejecuta el análisis sistémico y genera META_ANALYSIS.md.
        Retorna la ruta al archivo generado, o None si no hay datos suficientes.
        """
        logger.info("[META] Iniciando análisis sistémico de los últimos %d días...", days)

        tickets = self._collect_completed_tickets(days)
        if len(tickets) < _MIN_TICKETS_FOR_ANALYSIS:
            logger.info("[META] Insuficientes tickets para análisis (%d < %d)",
                        len(tickets), _MIN_TICKETS_FOR_ANALYSIS)
            return None

        logger.info("[META] Analizando %d tickets completados...", len(tickets))

        insights = {
            "recurring_modules":   self._find_recurring_modules(tickets),
            "root_cause_patterns": self._find_root_cause_patterns(tickets),
            "rework_hotspots":     self._find_rework_hotspots(tickets),
            "complexity_trends":   self._find_complexity_trends(tickets),
            "qa_rejection_causes": self._find_qa_rejection_causes(tickets),
        }

        report_path = os.path.join(self._output_dir, "META_ANALYSIS.md")
        report      = self._format_report(insights, days, len(tickets))

        try:
            Path(report_path).write_text(report, encoding="utf-8")
            logger.info("[META] META_ANALYSIS.md generado: %s", report_path)
        except Exception as e:
            logger.error("[META] Error escribiendo reporte: %s", e)
            return None

        # Persistir insights en JSON para uso programático
        json_path = os.path.join(self._output_dir, "meta_insights.json")
        try:
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump({
                    "project":      self._project,
                    "analyzed_at":  datetime.now().isoformat(),
                    "ticket_count": len(tickets),
                    "insights":     insights,
                }, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

        return report_path

    def get_last_insights(self) -> dict | None:
        """Carga el último análisis generado."""
        json_path = os.path.join(self._output_dir, "meta_insights.json")
        try:
            with open(json_path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    # ── Recolección de datos ──────────────────────────────────────────────

    def _collect_completed_tickets(self, days: int) -> list[dict]:
        """Recolecta datos de tickets completados con QA aprobado."""
        cutoff  = (datetime.now() - timedelta(days=days)).isoformat()
        tickets = []

        for estado in ["archivado", "resuelta", "asignada", "aceptada"]:
            estado_dir = os.path.join(self._tickets_base, estado)
            if not os.path.isdir(estado_dir):
                continue
            try:
                for tid in os.listdir(estado_dir):
                    folder       = os.path.join(estado_dir, tid)
                    tester_path  = os.path.join(folder, "TESTER_COMPLETADO.md")
                    if not os.path.exists(tester_path):
                        continue
                    try:
                        mtime = os.path.getmtime(tester_path)
                        if datetime.fromtimestamp(mtime).isoformat() < cutoff:
                            continue
                    except Exception:
                        continue

                    ticket_data = self._extract_ticket_data(tid, folder)
                    if ticket_data:
                        tickets.append(ticket_data)
            except Exception as e:
                logger.debug("[META] Error en %s: %s", estado_dir, e)

        return tickets

    def _extract_ticket_data(self, ticket_id: str, folder: str) -> dict | None:
        """Extrae datos relevantes de un ticket para el análisis."""
        inc_path    = os.path.join(folder, f"INC-{ticket_id}.md")
        tester_path = os.path.join(folder, "TESTER_COMPLETADO.md")
        anal_path   = os.path.join(folder, "ANALISIS_TECNICO.md")
        arq_path    = os.path.join(folder, "ARQUITECTURA_SOLUCION.md")

        if not os.path.exists(inc_path):
            return None

        try:
            tester  = Path(tester_path).read_text(encoding="utf-8", errors="replace") \
                      if os.path.exists(tester_path) else ""
            inc     = Path(inc_path).read_text(encoding="utf-8", errors="replace")[:2000]
            anal    = Path(anal_path).read_text(encoding="utf-8", errors="replace")[:1500] \
                      if os.path.exists(anal_path) else ""
            arq     = Path(arq_path).read_text(encoding="utf-8", errors="replace")[:1500] \
                      if os.path.exists(arq_path) else ""
        except Exception:
            return None

        # Veredicto QA
        qa_verdict = "APROBADO" if "APROBADO" in tester.upper() else \
                     "RECHAZADO" if "RECHAZADO" in tester.upper() else \
                     "OBSERVACIONES"

        # ¿Tuvo rework?
        had_rework = os.path.exists(os.path.join(folder, "TESTER_COMPLETADO.md.prev"))

        # Módulos
        modules = re.findall(r'\b(Frm\w+|DAL_\w+|BLL_\w+)\b',
                             inc + anal + arq, re.IGNORECASE)

        # Causa raíz aproximada
        root_cause = ""
        m = re.search(r'causa[:\s]+([^.\n]{20,100})', anal, re.IGNORECASE)
        if m:
            root_cause = m.group(1).strip()

        # Tipo de error
        combined = (inc + anal).lower()
        error_type = "null_reference" if "nullreferenceexception" in combined else \
                     "validation" if "validaci" in combined else \
                     "performance" if "rendimiento" in combined or "lentitud" in combined else \
                     "ui" if "aspx" in combined or "postback" in combined else \
                     "data" if "oracle" in combined or "dal_" in combined else \
                     "general"

        return {
            "ticket_id":  ticket_id,
            "qa_verdict": qa_verdict,
            "had_rework": had_rework,
            "modules":    list(set(m.lower() for m in modules))[:5],
            "root_cause": root_cause,
            "error_type": error_type,
        }

    # ── Análisis ──────────────────────────────────────────────────────────

    def _find_recurring_modules(self, tickets: list[dict]) -> list[dict]:
        """Módulos que aparecen en múltiples tickets."""
        module_count: Counter = Counter()
        for t in tickets:
            for m in t.get("modules", []):
                module_count[m] += 1
        return [{"module": k, "count": v}
                for k, v in module_count.most_common(10) if v >= 2]

    def _find_root_cause_patterns(self, tickets: list[dict]) -> list[dict]:
        """Patrones de causa raíz recurrentes."""
        type_counts: Counter = Counter(t.get("error_type", "general") for t in tickets)
        return [{"type": k, "count": v, "pct": round(v/len(tickets)*100)}
                for k, v in type_counts.most_common()]

    def _find_rework_hotspots(self, tickets: list[dict]) -> list[dict]:
        """Módulos con alta tasa de rework."""
        module_rework: dict[str, dict] = {}
        for t in tickets:
            for m in t.get("modules", []):
                entry = module_rework.setdefault(m, {"total": 0, "rework": 0})
                entry["total"]  += 1
                if t.get("had_rework"):
                    entry["rework"] += 1
        hotspots = [
            {"module": k, "rework_rate": round(v["rework"]/v["total"], 2),
             "rework": v["rework"], "total": v["total"]}
            for k, v in module_rework.items() if v["total"] >= 2
        ]
        hotspots.sort(key=lambda x: -x["rework_rate"])
        return hotspots[:10]

    def _find_complexity_trends(self, tickets: list[dict]) -> dict:
        """Distribución de tipos de error."""
        type_dist: Counter = Counter(t.get("error_type") for t in tickets)
        total = len(tickets)
        return {k: {"count": v, "pct": round(v/total*100)}
                for k, v in type_dist.most_common()}

    def _find_qa_rejection_causes(self, tickets: list[dict]) -> dict:
        """Estadísticas de veredictos QA."""
        verdicts: Counter = Counter(t.get("qa_verdict") for t in tickets)
        total = len(tickets)
        rework_count = sum(1 for t in tickets if t.get("had_rework"))
        return {
            "verdicts":    {k: v for k, v in verdicts.items()},
            "rework_rate": round(rework_count / total, 3) if total else 0,
            "total":       total,
        }

    # ── Formato ───────────────────────────────────────────────────────────

    def _format_report(self, insights: dict, days: int, ticket_count: int) -> str:
        lines = [
            f"# Meta-Análisis Sistémico — {self._project}",
            "",
            f"> Período: últimos {days} días  ",
            f"> Tickets analizados: {ticket_count}  ",
            f"> Generado: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "",
            "---",
            "",
            "## Resumen Ejecutivo",
            "",
        ]

        # QA stats
        qa = insights.get("qa_rejection_causes", {})
        verdicts = qa.get("verdicts", {})
        rework_rate = qa.get("rework_rate", 0)
        lines += [
            f"- **Tickets analizados:** {ticket_count}",
            f"- **QA Aprobado:** {verdicts.get('APROBADO', 0)} ({verdicts.get('APROBADO', 0)/ticket_count*100:.0f}%)"
            if ticket_count else "",
            f"- **Tasa de rework:** {rework_rate:.0%}",
            "",
        ]

        # Módulos recurrentes
        recurring = insights.get("recurring_modules", [])
        if recurring:
            lines += [
                "## Módulos con Más Bugs",
                "",
                "| Módulo | Tickets |",
                "|--------|---------|",
            ]
            for m in recurring[:8]:
                lines.append(f"| `{m['module']}` | {m['count']} |")
            lines.append("")
            lines.append(
                f"_⚠️ `{recurring[0]['module']}` aparece en {recurring[0]['count']} tickets "
                f"— considerar refactor o tests adicionales._"
            )
            lines.append("")

        # Tipos de error
        patterns = insights.get("root_cause_patterns", [])
        if patterns:
            lines += [
                "## Distribución de Tipos de Error",
                "",
                "| Tipo | Cantidad | % |",
                "|------|----------|---|",
            ]
            for p in patterns:
                lines.append(f"| {p['type']} | {p['count']} | {p['pct']}% |")
            lines.append("")

        # Rework hotspots
        hotspots = insights.get("rework_hotspots", [])
        if hotspots:
            lines += [
                "## Módulos con Alta Tasa de Rework",
                "",
                "| Módulo | Rework | Total | Tasa |",
                "|--------|--------|-------|------|",
            ]
            for h in hotspots[:5]:
                icon = "🔴" if h["rework_rate"] > 0.5 else "🟡"
                lines.append(f"| {icon} `{h['module']}` | {h['rework']} | {h['total']} | {h['rework_rate']:.0%} |")
            lines.append("")

        lines += [
            "---",
            "",
            "## Recomendaciones",
            "",
        ]

        if recurring:
            lines.append(f"1. **{recurring[0]['module']}**: Agregar tests unitarios — módulo con mayor frecuencia de bugs")
        if rework_rate > 0.3:
            lines.append(f"2. **Alta tasa de rework ({rework_rate:.0%})**: Revisar calidad de los prompts PM o DEV")
        top_type = patterns[0]["type"] if patterns else ""
        if top_type and top_type != "general":
            lines.append(f"3. **{top_type}**: Tipo de error más frecuente — considerar guardrails específicos en prompts")

        lines += [
            "",
            "_Análisis generado automáticamente por Stacky Meta-Analyst._",
        ]
        return "\n".join(lines)
