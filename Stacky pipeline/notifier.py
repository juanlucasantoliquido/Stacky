"""
notifier.py — Sistema de notificaciones para el Stacky daemon.

Envía notificaciones Windows toast cuando los tickets avanzan en el pipeline
o cuando se requiere intervención manual.

Fallback: si win10toast/plyer no están disponibles, escribe en NOTIFICATIONS.json
(el endpoint /api/notifications del dashboard lo lee y muestra badges).
"""

import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime

BASE_DIR           = os.path.dirname(os.path.abspath(__file__))
NOTIFICATIONS_PATH = os.path.join(BASE_DIR, "NOTIFICATIONS.json")

# Intentar importar librería de notificaciones nativa
_TOAST_BACKEND = None

try:
    from win10toast import ToastNotifier as _Win10Toast
    _TOAST_BACKEND = "win10toast"
except ImportError:
    pass

if not _TOAST_BACKEND:
    try:
        from plyer import notification as _plyer_notification
        _TOAST_BACKEND = "plyer"
    except ImportError:
        pass


# ── Helpers de webhook (Slack / Teams) ───────────────────────────────────────

def _send_slack_webhook(webhook_url: str, title: str, message: str,
                        level: str, ticket_id: str = "") -> bool:
    """Envía notificación a Slack vía webhook. Retorna True si tuvo éxito."""
    color_map = {"info": "#36a64f", "warning": "#ff9900", "error": "#d00000"}
    color     = color_map.get(level, "#36a64f")

    payload = {
        "attachments": [{
            "color":  color,
            "title":  title,
            "text":   message,
            "footer": "Stacky Pipeline",
            "ts":     int(datetime.now().timestamp()),
            "fields": [{"title": "Ticket", "value": f"#{ticket_id}", "short": True}]
                       if ticket_id else [],
        }]
    }
    return _post_webhook(webhook_url, payload)


def _send_teams_webhook(webhook_url: str, title: str, message: str,
                        level: str, ticket_id: str = "") -> bool:
    """Envía Adaptive Card a Microsoft Teams vía webhook."""
    color_map = {"info": "Good", "warning": "Warning", "error": "Attention"}
    theme     = color_map.get(level, "Good")

    payload = {
        "@type":      "MessageCard",
        "@context":   "https://schema.org/extensions",
        "themeColor": {"Good": "0078D7", "Warning": "FF9900", "Attention": "D00000"}.get(theme, "0078D7"),
        "summary":    title,
        "sections":   [{
            "activityTitle":    f"**{title}**",
            "activitySubtitle": "Stacky Pipeline",
            "activityText":     message,
            "facts": [{"name": "Ticket", "value": f"#{ticket_id}"}] if ticket_id else [],
        }],
    }
    return _post_webhook(webhook_url, payload)


def _post_webhook(url: str, payload: dict) -> bool:
    """POST JSON a un webhook URL. Retorna True si status 2xx."""
    try:
        data = json.dumps(payload).encode("utf-8")
        req  = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return 200 <= resp.status < 300
    except urllib.error.URLError as e:
        print(f"[NOTIF] Webhook error: {e}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"[NOTIF] Error enviando webhook: {e}", file=sys.stderr)
        return False


def _load_webhook_config() -> dict:
    """
    Carga configuración de webhooks desde el config del proyecto activo.
    Retorna dict con keys: slack_webhook, teams_webhook, notify_on.
    """
    try:
        from project_manager import get_active_project, get_project_config
        proj = get_active_project()
        cfg  = get_project_config(proj) or {}
        return cfg.get("notifications", {})
    except Exception:
        pass
    # Fallback: leer config.json global
    try:
        cfg_path = os.path.join(BASE_DIR, "config.json")
        with open(cfg_path, encoding="utf-8") as f:
            gcfg = json.load(f)
        return gcfg.get("notifications", {})
    except Exception:
        return {}


class Notifier:
    """
    Envía notificaciones de escritorio (Windows toast) con fallback a archivo JSON.

    Uso:
        notifier = Notifier()
        notifier.send("Pipeline", "Ticket #0027698 completado", level="info")
        notifier.notify_ticket_ready("0027698", "pm")
        notifier.notify_action_needed("0027698", "Timeout en DEV — revisar VS Code")
    """

    def __init__(self, app_name: str = "Stacky"):
        self.app_name    = app_name
        self._toast      = None
        self._file_cache = None  # lazy-loaded desde NOTIFICATIONS.json
        if _TOAST_BACKEND == "win10toast":
            try:
                self._toast = _Win10Toast()
            except Exception:
                pass

    # ── API pública ────────────────────────────────────────────────────────

    def send(self, title: str, message: str, level: str = "info",
             ticket_id: str = "") -> bool:
        """
        Envía una notificación a todos los backends configurados:
        - Toast nativo de Windows
        - Slack webhook (si configurado)
        - Teams webhook (si configurado)
        - Archivo JSON (siempre)

        level: "info" | "warning" | "error"
        Retorna True si al menos un backend visual tuvo éxito.
        """
        self._write_to_file(title, message, level)
        toast_ok = self._send_toast(title, message, level)
        self._send_webhooks(title, message, level, ticket_id)
        return toast_ok

    def notify_ticket_ready(self, ticket_id: str, stage_completed: str) -> None:
        """El ticket completó una etapa y está listo para la siguiente."""
        stage_labels = {"pm": "PM Análisis", "dev": "Dev Impl.", "tester": "QA Tester"}
        label = stage_labels.get(stage_completed, stage_completed.upper())
        self.send(
            title=f"Ticket #{ticket_id} — {label} completado",
            message="Pipeline avanzó a la siguiente etapa automáticamente",
            level="info",
            ticket_id=ticket_id,
        )

    def notify_ticket_completed(self, ticket_id: str) -> None:
        """El ticket completó todo el pipeline PM→Dev→QA."""
        self.send(
            title=f"Ticket #{ticket_id} COMPLETADO",
            message="Pipeline PM → Dev → QA finalizado exitosamente",
            level="info",
            ticket_id=ticket_id,
        )

    def notify_action_needed(self, ticket_id: str, reason: str) -> None:
        """Requiere intervención manual del desarrollador."""
        self.send(
            title=f"Acción requerida — Ticket #{ticket_id}",
            message=reason,
            level="error",
            ticket_id=ticket_id,
        )

    def notify_new_tickets(self, count: int, project: str) -> None:
        """Se detectaron tickets nuevos al scrapear."""
        self.send(
            title=f"{count} ticket(s) nuevo(s) — {project}",
            message="El pipeline los procesará automáticamente",
            level="info",
        )

    def notify_session_expiring(self, project: str = "") -> None:
        """La sesión SSO está por expirar."""
        self.send(
            title="Sesión del tracker necesita renovación",
            message=f"Ejecutar capture_session.py{' para ' + project if project else ''}",
            level="warning",
        )

    # ── Implementación interna ─────────────────────────────────────────────

    def _send_toast(self, title: str, message: str, level: str) -> bool:
        """Intenta enviar un toast nativo. Retorna True si lo logró."""
        if _TOAST_BACKEND == "win10toast" and self._toast:
            try:
                duration = 5 if level == "info" else 10
                self._toast.show_toast(
                    title,
                    message,
                    duration=duration,
                    threaded=True,
                )
                return True
            except Exception as e:
                print(f"[NOTIF] win10toast error: {e}", file=sys.stderr)

        if _TOAST_BACKEND == "plyer":
            try:
                _plyer_notification.notify(
                    title=title,
                    message=message,
                    app_name=self.app_name,
                    timeout=5 if level == "info" else 10,
                )
                return True
            except Exception as e:
                print(f"[NOTIF] plyer error: {e}", file=sys.stderr)

        return False

    def _send_webhooks(self, title: str, message: str, level: str,
                       ticket_id: str = "") -> None:
        """Envía la notificación a Slack y/o Teams si están configurados."""
        try:
            wcfg = _load_webhook_config()
            notify_on = wcfg.get("notify_on", ["stage_complete", "error", "new_tickets"])

            # Determinar si este evento está en la lista de notify_on
            # Simplificado: errores siempre, el resto según config
            should_notify = (level == "error" or "stage_complete" in notify_on
                             or "pipeline_complete" in notify_on)
            if not should_notify:
                return

            slack_url = wcfg.get("slack_webhook", "")
            if slack_url:
                _send_slack_webhook(slack_url, title, message, level, ticket_id)

            teams_url = wcfg.get("teams_webhook", "")
            if teams_url:
                _send_teams_webhook(teams_url, title, message, level, ticket_id)
        except Exception as e:
            print(f"[NOTIF] Error en webhooks: {e}", file=sys.stderr)

    def _write_to_file(self, title: str, message: str, level: str) -> None:
        """Persiste la notificación en NOTIFICATIONS.json para el dashboard.
        Usa cache en memoria para evitar re-leer el archivo completo cada vez."""
        try:
            # Cargar solo si el archivo cambió (otro proceso escribió) o si no tenemos cache
            if self._file_cache is None:
                if os.path.exists(NOTIFICATIONS_PATH):
                    try:
                        with open(NOTIFICATIONS_PATH, encoding="utf-8") as f:
                            self._file_cache = json.load(f)
                    except Exception:
                        self._file_cache = []
                else:
                    self._file_cache = []

            self._file_cache.append({
                "at":      datetime.now().isoformat(),
                "title":   title,
                "message": message,
                "level":   level,
                "read":    False,
            })

            # Mantener solo las últimas 100 notificaciones
            if len(self._file_cache) > 100:
                self._file_cache = self._file_cache[-100:]

            with open(NOTIFICATIONS_PATH, "w", encoding="utf-8") as f:
                json.dump(self._file_cache, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[NOTIF] Error guardando en archivo: {e}", file=sys.stderr)


# Instancia global reutilizable
_default_notifier: Notifier | None = None


def get_notifier() -> Notifier:
    """Retorna la instancia global del notifier."""
    global _default_notifier
    if _default_notifier is None:
        _default_notifier = Notifier()
    return _default_notifier


def notify(title: str, message: str, level: str = "info",
           ticket_id: str = "") -> None:
    """Wrapper de conveniencia sobre la instancia global."""
    get_notifier().send(title, message, level=level, ticket_id=ticket_id)


# ── Y-06: Eventos especializados del hub de notificaciones ───────────────────

def notify_stagnation(ticket_id: str, cycle_num: int, last_issues: list) -> None:
    """Y-01: Notifica cuando un ticket entra en stagnation (sin progreso)."""
    title   = f"⚠️ Stacky — STAGNATION detectada en #{ticket_id}"
    issues_preview = "; ".join(str(i)[:60] for i in last_issues[:3])
    message = (
        f"El ticket #{ticket_id} lleva {cycle_num} ciclos QA→DEV sin progreso.\n"
        f"Últimos issues: {issues_preview or '(ver CORRECTION_MEMORY.json)'}\n"
        f"Requiere intervención manual."
    )
    notify(title, message, level="error", ticket_id=ticket_id)


def notify_dba_ready(ticket_id: str) -> None:
    """Y-04: Notifica cuando el agente DBA completó DB_SOLUTION.sql."""
    title   = f"✅ Stacky — DBA completó #{ticket_id}"
    message = f"DB_SOLUTION.sql generado y listo. DEV puede proceder con la implementación."
    notify(title, message, level="info", ticket_id=ticket_id)


def notify_tl_rejected(ticket_id: str, rejection_summary: str = "") -> None:
    """Y-05: Notifica cuando el Tech Lead rechazó la arquitectura de PM."""
    title   = f"🔄 Stacky — Tech Lead rechazó #{ticket_id}"
    message = (
        f"El Tech Lead encontró problemas en la arquitectura propuesta.\n"
        f"{rejection_summary or 'Ver TL_REJECTED.md para el detalle.'}\n"
        f"PM debe replantear el análisis."
    )
    notify(title, message, level="warning", ticket_id=ticket_id)


def notify_pipeline_complete(ticket_id: str, cycle_count: int = 1,
                              elapsed_minutes: float = 0) -> None:
    """Notifica cuando el pipeline completó exitosamente (QA aprobó)."""
    cycles_str = f" en {cycle_count} ciclos" if cycle_count > 1 else ""
    elapsed_str = f" ({elapsed_minutes:.0f} min)" if elapsed_minutes > 0 else ""
    title   = f"✅ Stacky — Pipeline completado #{ticket_id}"
    message = f"QA aprobó el ticket #{ticket_id}{cycles_str}{elapsed_str}."
    notify(title, message, level="info", ticket_id=ticket_id)


def _send_generic_webhook(webhook_url: str, payload: dict) -> bool:
    """Y-06: Webhook genérico — envía el payload JSON directamente."""
    return _post_webhook(webhook_url, payload)


def send_generic_webhook_event(event_type: str, ticket_id: str = "",
                                extra: dict = None) -> None:
    """
    Y-06: Envía un evento genérico a un webhook configurable.
    Permite integrar con cualquier herramienta sin código extra.

    Configurable en config.json:
    {
      "notifications": {
        "generic_webhook": "https://...",
        "notify_on": ["pipeline_complete", "error", "stagnation"]
      }
    }
    """
    cfg = _load_webhook_config()
    generic_url = cfg.get("generic_webhook", "")
    if not generic_url:
        return

    notify_on = cfg.get("notify_on", [])
    if notify_on and event_type not in notify_on:
        return  # Filtered by config

    payload = {
        "source":     "stacky",
        "event_type": event_type,
        "ticket_id":  ticket_id,
        "timestamp":  datetime.now().isoformat(),
        **(extra or {}),
    }
    _send_generic_webhook(generic_url, payload)


# ── Y-06: Reporte ejecutivo semanal ──────────────────────────────────────────

def generate_weekly_report() -> str:
    """
    Y-06: Genera el reporte ejecutivo semanal en texto Markdown.
    Usa MetricsCollector si disponible.
    Retorna el texto del reporte.
    """
    import importlib
    import datetime as _dt
    now = datetime.now()
    report_lines = [
        f"# Stacky — Reporte Ejecutivo Semanal",
        f"**Período:** semana del {(now - _dt.timedelta(days=7)).strftime('%d/%m/%Y')} al {now.strftime('%d/%m/%Y')}",
        f"**Generado:** {now.strftime('%d/%m/%Y %H:%M')}",
        "",
    ]

    try:
        from project_manager import get_active_project, get_project_config
        proj = get_active_project()
        mc_mod = importlib.import_module("metrics_collector")
        mc = mc_mod.MetricsCollector(proj)
        metrics = mc.get_dashboard_metrics(days=7)

        total = metrics.get("total_events", 0)
        report_lines.append(f"## Resumen operacional")
        report_lines.append(f"- **Eventos registrados (últimos 7 días):** {total}")

        for stage in ("pm", "dev", "tester"):
            sdata = metrics.get(stage, {})
            count = sdata.get("count", 0)
            if count == 0:
                continue
            success_rate = sdata.get("success_rate", 0)
            avg_dur = sdata.get("avg_duration_min", 0)
            rework_rate = sdata.get("rework_rate", 0)
            report_lines.append(
                f"- **{stage.upper()}:** {count} eventos | "
                f"{success_rate:.0%} éxito | "
                f"{avg_dur:.0f} min promedio | "
                f"{rework_rate:.0%} rework"
            )
    except Exception as e:
        report_lines.append(f"- Métricas no disponibles: {e}")

    report_lines += ["", "---", "_Reporte generado automáticamente por Stacky_"]
    return "\n".join(report_lines)


def send_weekly_report() -> None:
    """
    Y-06: Envía el reporte ejecutivo semanal a los webhooks configurados.
    Se llama desde el scheduler del daemon (lunes 08:00).
    """
    cfg = _load_webhook_config()
    report_text = generate_weekly_report()
    title   = f"📊 Stacky — Reporte Semanal {datetime.now().strftime('%d/%m/%Y')}"
    message = report_text[:2000]  # Truncar para webhooks

    slack_url = cfg.get("slack_webhook", "")
    if slack_url:
        _send_slack_webhook(slack_url, title, message, "info")

    teams_url = cfg.get("teams_webhook", "")
    if teams_url:
        _send_teams_webhook(teams_url, title, message, "info")

    generic_url = cfg.get("generic_webhook", "")
    if generic_url:
        _send_generic_webhook(generic_url, {
            "source":      "stacky",
            "event_type":  "weekly_report",
            "report":      report_text,
            "timestamp":   datetime.now().isoformat(),
        })

    # También guardar en disco
    try:
        reports_dir = os.path.join(BASE_DIR, "reports")
        os.makedirs(reports_dir, exist_ok=True)
        report_path = os.path.join(
            reports_dir,
            f"weekly_{datetime.now().strftime('%Y-%m-%d')}.md"
        )
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report_text)
    except Exception:
        pass
