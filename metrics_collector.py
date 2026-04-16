"""
metrics_collector.py — N-08: Dashboard de Métricas de Calidad por Agente.

Registra métricas de cada ejecución de agente (duración, resultado, reintentos,
rework, complejidad del ticket). Persiste en metrics.json por proyecto.

Expone:
  - record_stage_start / record_stage_end  → llamados desde daemon/watcher
  - get_dashboard_metrics()                → para endpoint Flask del dashboard
  - format_metrics_summary()               → para consola / notificaciones

Uso:
    from metrics_collector import MetricsCollector
    mc = MetricsCollector(project_name)
    mc.record_stage_start(ticket_id, "pm")
    mc.record_stage_end(ticket_id, "pm", success=True, rework=False)
    data = mc.get_dashboard_metrics()
"""

import json
import logging
import os
import threading
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger("mantis.metrics")

_STAGES = ("pm", "dev", "tester")


class MetricsCollector:
    """
    Registra y expone métricas de calidad del pipeline Stacky.
    Thread-safe: usa RLock para escrituras concurrentes.
    """

    def __init__(self, project_name: str):
        self._project   = project_name
        self._lock      = threading.RLock()
        self._path      = self._get_metrics_path()
        self._data      = self._load()
        # Cache de tiempos de inicio por ticket+etapa en memoria (no persiste)
        self._starts: dict[str, datetime] = {}

    # ── API pública ───────────────────────────────────────────────────────

    def record_stage_start(self, ticket_id: str, stage: str) -> None:
        """Registra el inicio de una etapa."""
        key = f"{ticket_id}:{stage}"
        self._starts[key] = datetime.now()

    def record_stage_end(self, ticket_id: str, stage: str, *,
                         success: bool, rework: bool = False,
                         retry_num: int = 0, complexity: str = "medio") -> None:
        """
        Registra el fin de una etapa y persiste las métricas.
        success=False si el agente generó error flag o fue rechazado.
        """
        key     = f"{ticket_id}:{stage}"
        started = self._starts.pop(key, None)
        duration_sec = (datetime.now() - started).total_seconds() if started else None

        with self._lock:
            now = datetime.now().isoformat()
            ev  = {
                "ticket_id":    ticket_id,
                "stage":        stage,
                "success":      success,
                "rework":       rework,
                "retry_num":    retry_num,
                "complexity":   complexity,
                "duration_sec": round(duration_sec, 1) if duration_sec else None,
                "ts":           now,
            }

            events = self._data.setdefault("events", [])
            events.append(ev)
            # Mantener máximo 5000 eventos
            if len(events) > 5000:
                self._data["events"] = events[-5000:]

            # Actualizar resumen rápido
            self._update_summary(ev)
            self._save()

        logger.debug("[METRICS] %s/%s success=%s dur=%ss",
                     ticket_id, stage, success,
                     f"{duration_sec:.0f}" if duration_sec else "?")

    def get_dashboard_metrics(self, days: int = 7) -> dict:
        """
        Retorna métricas consolidadas para el dashboard Flask.
        days: ventana de tiempo en días (default: últimos 7 días).
        """
        with self._lock:
            cutoff = (datetime.now() - timedelta(days=days)).isoformat()
            events = [e for e in self._data.get("events", [])
                      if e.get("ts", "") >= cutoff]

        result: dict = {
            "project":    self._project,
            "window_days": days,
            "generated_at": datetime.now().isoformat(),
            "total_events": len(events),
        }

        for stage in _STAGES:
            stage_evs = [e for e in events if e["stage"] == stage]
            if not stage_evs:
                result[stage] = {"count": 0}
                continue

            success_evs  = [e for e in stage_evs if e.get("success")]
            fail_evs     = [e for e in stage_evs if not e.get("success")]
            rework_evs   = [e for e in stage_evs if e.get("rework")]
            durations    = [e["duration_sec"] for e in stage_evs
                            if e.get("duration_sec") is not None]

            result[stage] = {
                "count":         len(stage_evs),
                "success_rate":  round(len(success_evs) / len(stage_evs), 3),
                "fail_count":    len(fail_evs),
                "rework_count":  len(rework_evs),
                "avg_duration_min": round(sum(durations) / len(durations) / 60, 1)
                                    if durations else None,
                "max_duration_min": round(max(durations) / 60, 1) if durations else None,
            }

        # Complejidad breakdown
        by_complexity: dict[str, dict] = {}
        for e in events:
            comp = e.get("complexity", "medio")
            entry = by_complexity.setdefault(comp, {"total": 0, "success": 0})
            entry["total"]  += 1
            if e.get("success"):
                entry["success"] += 1
        result["by_complexity"] = by_complexity

        # Últimos tickets procesados
        seen: list[str] = []
        last_tickets: list[dict] = []
        for ev in reversed(self._data.get("events", [])):
            tid = ev["ticket_id"]
            if tid not in seen:
                seen.append(tid)
                last_tickets.append({"ticket_id": tid, "ts": ev["ts"],
                                      "stage": ev["stage"], "success": ev["success"]})
            if len(last_tickets) >= 10:
                break
        result["last_tickets"] = last_tickets

        return result

    def format_metrics_summary(self, days: int = 7) -> str:
        """Texto compacto con métricas clave — para consola o notificaciones."""
        m = self.get_dashboard_metrics(days)
        lines = [f"=== Métricas Stacky — últimos {days} días ({self._project}) ==="]
        for stage in _STAGES:
            s = m.get(stage, {})
            if not s.get("count"):
                continue
            rate = s.get("success_rate", 0)
            lines.append(
                f"  {stage.upper():7s}: {s['count']} ejecuciones | "
                f"éxito {rate:.0%} | rework {s.get('rework_count', 0)}x | "
                f"avg {s.get('avg_duration_min', '?')} min"
            )
        return "\n".join(lines)

    def get_operational_metrics(self, days: int = 1) -> dict:
        """
        Y-07: Métricas operacionales para el equipo técnico.
        Vista de últimas 24h por defecto.
        """
        with self._lock:
            cutoff = (datetime.now() - timedelta(days=days)).isoformat()
            events = [e for e in self._data.get("events", [])
                      if e.get("ts", "") >= cutoff]

        bottleneck_stage = None
        bottleneck_count = 0
        in_process_counts = {}
        for stage in _STAGES:
            stage_active = len([e for e in events
                                if e["stage"] == stage and not e.get("success")])
            in_process_counts[stage] = stage_active
            if stage_active > bottleneck_count:
                bottleneck_count = stage_active
                bottleneck_stage = stage

        rework_by_module: dict = {}
        for ev in events:
            if ev.get("rework"):
                mod = ev.get("module", "unknown")
                rework_by_module[mod] = rework_by_module.get(mod, 0) + 1

        return {
            "window_days":      days,
            "total_events":     len(events),
            "bottleneck_stage": bottleneck_stage,
            "in_process":       in_process_counts,
            "rework_by_module": dict(sorted(rework_by_module.items(),
                                            key=lambda x: x[1], reverse=True)[:10]),
            "generated_at":     datetime.now().isoformat(),
        }

    def get_executive_metrics(self, weeks: int = 4) -> dict:
        """
        Y-07: KPIs ejecutivos — vista semanal para las últimas N semanas.
        """
        with self._lock:
            cutoff = (datetime.now() - timedelta(weeks=weeks)).isoformat()
            events = [e for e in self._data.get("events", [])
                      if e.get("ts", "") >= cutoff]

        total_tickets  = len(set(e["ticket_id"] for e in events))
        success_first  = len([e for e in events
                               if e["stage"] == "tester" and e.get("success")
                               and not e.get("rework")])
        rework_events  = len([e for e in events if e.get("rework")])
        durations      = [e["duration_sec"] for e in events
                          if e.get("duration_sec") is not None]
        avg_duration_h = (sum(durations) / len(durations) / 3600) if durations else 0

        # ROI estimado: horas-developer ahorradas
        # Asumiendo 3h de work manual por ticket en el pipeline
        roi_hours_saved = total_tickets * 3 * 0.7  # 70% ahorro estimado

        return {
            "window_weeks":      weeks,
            "total_tickets":     total_tickets,
            "success_first_try": success_first,
            "rework_total":      rework_events,
            "avg_resolution_h":  round(avg_duration_h, 1),
            "roi_hours_saved":   round(roi_hours_saved, 1),
            "generated_at":      datetime.now().isoformat(),
        }

    # ── Internals ─────────────────────────────────────────────────────────

    def _update_summary(self, ev: dict) -> None:
        """Actualiza contadores rápidos en self._data['summary']."""
        summary = self._data.setdefault("summary", {})
        stage   = ev["stage"]
        s       = summary.setdefault(stage, {"total": 0, "success": 0,
                                             "fail": 0, "rework": 0})
        s["total"]  += 1
        if ev.get("success"):
            s["success"] += 1
        else:
            s["fail"] += 1
        if ev.get("rework"):
            s["rework"] += 1

    def _get_metrics_path(self) -> str:
        base = os.path.dirname(os.path.abspath(__file__))
        kb   = os.path.join(base, "knowledge", self._project)
        os.makedirs(kb, exist_ok=True)
        return os.path.join(kb, "metrics.json")

    def _load(self) -> dict:
        try:
            with open(self._path, encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return {"events": [], "summary": {}}
        except Exception as e:
            logger.warning("[METRICS] Error cargando metrics.json: %s", e)
            return {"events": [], "summary": {}}

    def _save(self) -> None:
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, separators=(",", ":"), ensure_ascii=False)
        except Exception as e:
            logger.error("[METRICS] Error guardando metrics.json: %s", e)


# ── Singleton por proyecto ────────────────────────────────────────────────────

_mc_instances: dict[str, MetricsCollector] = {}
_mc_lock = threading.Lock()


def get_metrics_collector(project_name: str) -> MetricsCollector:
    """Retorna (y cachea) una instancia de MetricsCollector por proyecto."""
    with _mc_lock:
        if project_name not in _mc_instances:
            _mc_instances[project_name] = MetricsCollector(project_name)
        return _mc_instances[project_name]
