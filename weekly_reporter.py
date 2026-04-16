# CANCELADO — X-06 removido por decision del equipo (2026-04-13).
# Este archivo esta deshabilitado. No importar ni ejecutar.
raise ImportError("weekly_reporter (X-06) fue cancelado — no usar.")

"""
weekly_reporter.py — X-06: Reporte Ejecutivo Automatico Semanal.

Genera un reporte HTML con el resumen de la semana anterior y lo envia
via Slack/Teams (N-09) y lo archiva en reports/weekly/.

Un agente Claude API redacta el analisis narrativo basado en las metricas
reales de N-08 (MetricsCollector).

Uso:
    from weekly_reporter import WeeklyReporter
    reporter = WeeklyReporter(project_name)
    reporter.generate_and_send()              # genera + envia + archiva

    # Para programar automaticamente: llamar desde daemon.py los lunes a las 08:00
    reporter.maybe_run_weekly()               # solo corre si no se genero esta semana
"""

import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger("mantis.weekly_reporter")

BASE_DIR = Path(__file__).parent


class WeeklyReporter:
    """
    Genera un reporte ejecutivo semanal con metricas del pipeline Stacky.

    Si anthropic esta disponible, redacta el analisis narrativo con Claude API.
    Si no, genera un reporte estadistico puro sin narrativa IA.
    """

    def __init__(self, project_name: str):
        self.project_name = project_name
        self.reports_dir  = BASE_DIR / "reports" / "weekly"
        self.reports_dir.mkdir(parents=True, exist_ok=True)

        # Cargar metricas del proyecto
        self._metrics_path = (
            BASE_DIR / "projects" / project_name / "metrics.json"
        )
        self._config_path = (
            BASE_DIR / "projects" / project_name / "config.json"
        )
        self._config = self._load_config()

    # ── API publica ──────────────────────────────────────────────────────────

    def maybe_run_weekly(self) -> bool:
        """
        Ejecuta generate_and_send() solo si no se genero reporte esta semana.
        Devuelve True si se genero, False si ya existia.
        """
        # El lunes de esta semana
        today = datetime.now()
        monday = today - timedelta(days=today.weekday())
        week_key = monday.strftime("%Y-W%V")
        marker_file = self.reports_dir / f".generated_{week_key}"

        if marker_file.exists():
            return False

        self.generate_and_send()
        marker_file.touch()
        return True

    def generate_and_send(self) -> str:
        """
        Genera el reporte HTML, lo archiva y lo envia por Slack/Teams.
        Devuelve la ruta del archivo generado.
        """
        week_end   = datetime.now()
        week_start = week_end - timedelta(days=7)

        logger.info(
            "[X-06] Generando reporte semanal %s → %s para proyecto %s",
            week_start.strftime("%Y-%m-%d"),
            week_end.strftime("%Y-%m-%d"),
            self.project_name,
        )

        metrics = self._load_metrics()
        stats   = self._compute_stats(metrics, week_start, week_end)
        narrative = self._generate_narrative(stats)
        html    = self._render_html(stats, narrative, week_start, week_end)

        # Archivar
        filename = (
            f"report_{self.project_name}_{week_start.strftime('%Y%m%d')}"
            f"_{week_end.strftime('%Y%m%d')}.html"
        )
        report_path = self.reports_dir / filename
        report_path.write_text(html, encoding="utf-8")
        logger.info("[X-06] Reporte archivado: %s", report_path)

        # Enviar notificacion
        self._send_notification(stats, str(report_path))

        return str(report_path)

    # ── Privados ─────────────────────────────────────────────────────────────

    def _load_config(self) -> dict:
        if self._config_path.exists():
            try:
                return json.loads(self._config_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    def _load_metrics(self) -> dict:
        if self._metrics_path.exists():
            try:
                return json.loads(self._metrics_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"runs": []}

    def _compute_stats(self, metrics: dict, start: datetime, end: datetime) -> dict:
        """Calcula estadisticas de la semana a partir de metrics.json."""
        runs = metrics.get("runs", [])

        # Filtrar a la ventana de la semana
        week_runs = []
        for run in runs:
            ts = run.get("end_time") or run.get("start_time", "")
            if not ts:
                continue
            try:
                dt = datetime.fromisoformat(ts[:19])
            except Exception:
                continue
            if start <= dt <= end:
                week_runs.append(run)

        total     = len(week_runs)
        completed = sum(1 for r in week_runs if r.get("success"))
        reworks   = sum(1 for r in week_runs if r.get("rework"))
        errors    = sum(1 for r in week_runs if not r.get("success") and not r.get("rework"))

        # Tiempos por etapa
        stage_times: dict[str, list[float]] = {}
        for run in week_runs:
            stage = run.get("stage", "unknown")
            dur   = run.get("duration_minutes")
            if dur is not None:
                stage_times.setdefault(stage, []).append(float(dur))

        stage_stats = {}
        for stage, times in stage_times.items():
            if times:
                avg  = sum(times) / len(times)
                p90  = sorted(times)[int(len(times) * 0.9)]
                stage_stats[stage] = {"avg": round(avg, 1), "p90": round(p90, 1), "count": len(times)}

        # Modulos mas frecuentes
        module_counts: dict[str, int] = {}
        for run in week_runs:
            for mod in run.get("files_touched", []):
                module_counts[mod] = module_counts.get(mod, 0) + 1

        top_modules = sorted(module_counts.items(), key=lambda x: x[1], reverse=True)[:5]

        # Ahorro estimado (asumir 2h dev manual por ticket)
        saved_hours = total * 2

        return {
            "project":       self.project_name,
            "week_start":    start.strftime("%d/%m/%Y"),
            "week_end":      end.strftime("%d/%m/%Y"),
            "total":         total,
            "completed":     completed,
            "reworks":       reworks,
            "errors":        errors,
            "qa_first_pass": round((completed - reworks) / max(total, 1) * 100, 1),
            "stage_stats":   stage_stats,
            "top_modules":   top_modules,
            "saved_hours":   saved_hours,
        }

    def _generate_narrative(self, stats: dict) -> str:
        """Genera analisis narrativo. Usa Claude API si esta disponible."""
        try:
            import anthropic
            client = anthropic.Anthropic()
            prompt = f"""Eres el analista de ingenieria de Stacky. Redacta un parrafo ejecutivo
conciso (maximo 5 oraciones) sobre la semana del {stats['week_start']} al {stats['week_end']}
para el proyecto {stats['project']}.

Datos:
- Tickets procesados: {stats['total']}
- Completados exitosamente: {stats['completed']}
- Con rework QA→DEV: {stats['reworks']}
- Errores sin resolver: {stats['errors']}
- Tasa QA primer intento: {stats['qa_first_pass']}%
- Ahorro estimado: {stats['saved_hours']}h de trabajo manual
- Modulos mas activos: {', '.join(m for m, _ in stats['top_modules'][:3]) if stats['top_modules'] else 'N/A'}

Tono: directo, ejecutivo, sin tecnicismos innecesarios. Si la tasa de QA primer
intento es baja (<70%), menciona que requiere atencion. Si hay modulos muy frecuentes,
menciona que son candidatos a refactorizacion.
"""
            resp = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=300,
                messages=[{"role": "user", "content": prompt}],
            )
            return resp.content[0].text.strip()
        except Exception as exc:
            logger.debug("[X-06] Claude API no disponible para narrativa: %s", exc)
            # Narrativa fallback generada localmente
            lines = []
            lines.append(
                f"Durante la semana del {stats['week_start']} al {stats['week_end']}, "
                f"Stacky proceso {stats['total']} tickets en el proyecto {stats['project']}."
            )
            if stats['total'] > 0:
                lines.append(
                    f"Se completaron {stats['completed']} tickets con una tasa de aprobacion "
                    f"QA en primer intento del {stats['qa_first_pass']}%."
                )
            if stats["reworks"] > 0:
                lines.append(
                    f"Se registraron {stats['reworks']} ciclos de rework QA→DEV."
                )
            if stats["top_modules"]:
                mod_str = ", ".join(m for m, _ in stats["top_modules"][:3])
                lines.append(f"Modulos mas activos: {mod_str}.")
            lines.append(
                f"Ahorro estimado de trabajo manual: {stats['saved_hours']} horas."
            )
            return " ".join(lines)

    def _render_html(
        self, stats: dict, narrative: str, start: datetime, end: datetime
    ) -> str:
        """Renderiza el reporte como HTML con estilo inline."""

        stage_rows = ""
        for stage, s in stats.get("stage_stats", {}).items():
            stage_rows += (
                f"<tr><td>{stage.upper()}</td><td>{s['count']}</td>"
                f"<td>{s['avg']} min</td><td>{s['p90']} min</td></tr>\n"
            )
        if not stage_rows:
            stage_rows = "<tr><td colspan='4'>Sin datos de etapas esta semana</td></tr>"

        module_rows = ""
        for mod, cnt in stats.get("top_modules", []):
            module_rows += f"<tr><td>{mod}</td><td>{cnt}</td></tr>\n"
        if not module_rows:
            module_rows = "<tr><td colspan='2'>Sin datos</td></tr>"

        qa_color = "#27ae60" if stats["qa_first_pass"] >= 70 else "#e74c3c"

        return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<title>Stacky — Reporte Semanal {stats['week_start']} — {stats['week_end']}</title>
<style>
  body {{ font-family: Arial, sans-serif; max-width: 800px; margin: 40px auto;
         color: #222; background: #f9f9f9; padding: 20px; }}
  h1   {{ color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 8px; }}
  h2   {{ color: #34495e; margin-top: 30px; }}
  .kpi-grid {{ display: flex; gap: 16px; flex-wrap: wrap; margin: 20px 0; }}
  .kpi {{ background: #fff; border-radius: 8px; padding: 16px 24px;
          box-shadow: 0 2px 6px rgba(0,0,0,.1); text-align: center; flex: 1; min-width: 120px; }}
  .kpi .value {{ font-size: 2em; font-weight: bold; }}
  .kpi .label {{ font-size: .85em; color: #666; margin-top: 4px; }}
  table  {{ width: 100%; border-collapse: collapse; background: #fff;
            box-shadow: 0 2px 6px rgba(0,0,0,.08); border-radius: 6px; overflow: hidden; }}
  th,td  {{ padding: 10px 14px; text-align: left; border-bottom: 1px solid #eee; }}
  th     {{ background: #2c3e50; color: #fff; }}
  tr:last-child td {{ border-bottom: none; }}
  .narrative {{ background: #eaf3fb; border-left: 4px solid #3498db;
                padding: 14px 18px; border-radius: 4px; margin: 20px 0; font-style: italic; }}
  .footer {{ color: #aaa; font-size: .8em; margin-top: 40px; text-align: center; }}
</style>
</head>
<body>
<h1>Stacky — Reporte Semanal</h1>
<p><strong>Proyecto:</strong> {stats['project']} &nbsp;|&nbsp;
   <strong>Periodo:</strong> {stats['week_start']} — {stats['week_end']}</p>

<div class="narrative">{narrative}</div>

<h2>Resumen Ejecutivo</h2>
<div class="kpi-grid">
  <div class="kpi">
    <div class="value">{stats['total']}</div>
    <div class="label">Tickets procesados</div>
  </div>
  <div class="kpi">
    <div class="value">{stats['completed']}</div>
    <div class="label">Completados</div>
  </div>
  <div class="kpi">
    <div class="value" style="color:{qa_color}">{stats['qa_first_pass']}%</div>
    <div class="label">QA 1er intento</div>
  </div>
  <div class="kpi">
    <div class="value">{stats['reworks']}</div>
    <div class="label">Reworks</div>
  </div>
  <div class="kpi">
    <div class="value">{stats['saved_hours']}h</div>
    <div class="label">Ahorro estimado</div>
  </div>
</div>

<h2>Tiempos por Etapa</h2>
<table>
  <thead><tr><th>Etapa</th><th>Tickets</th><th>Promedio</th><th>P90</th></tr></thead>
  <tbody>{stage_rows}</tbody>
</table>

<h2>Modulos mas Activos</h2>
<table>
  <thead><tr><th>Modulo / Archivo</th><th>Tickets</th></tr></thead>
  <tbody>{module_rows}</tbody>
</table>

<p class="footer">
  Generado automaticamente por Stacky el {datetime.now().strftime('%Y-%m-%d %H:%M')}
</p>
</body>
</html>"""

    def _send_notification(self, stats: dict, report_path: str) -> None:
        """Envia el reporte via Slack/Teams si esta configurado."""
        try:
            from notifier import notify
            notify(
                title=f"[Stacky] Reporte Semanal — {self.project_name}",
                message=(
                    f"Semana {stats['week_start']} → {stats['week_end']}: "
                    f"{stats['total']} tickets, QA 1er intento: {stats['qa_first_pass']}%. "
                    f"Reporte: {report_path}"
                ),
                level="info",
            )
        except Exception as exc:
            logger.debug("[X-06] No se pudo enviar notificacion: %s", exc)
