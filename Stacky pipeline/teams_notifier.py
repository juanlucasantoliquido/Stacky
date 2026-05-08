"""
teams_notifier.py — Notificaciones Microsoft Teams para Stacky.

Soporta dos modos:
  1. Incoming Webhook (canal de Teams) — más fácil de configurar
  2. Power Automate HTTP trigger  — permite enviar al chat personal / 1:1

El modo recomendado para el chat personal es Power Automate:
  - Crear un flujo en https://make.powerautomate.com
  - Trigger: "Cuando se recibe una solicitud HTTP"
  - Acción: "Publicar mensaje en un chat o canal" → seleccionar "Chat" → tu usuario
  - Copiar la URL del trigger y pegarla en Stacky

Configuración en config.json:
  "teams": {
    "webhook_url": "https://...",          ← Incoming Webhook o Power Automate URL
    "mode": "webhook"                       ← "webhook" | "powerautomate"
  }
"""

import json
import logging
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

logger   = logging.getLogger("stacky.teams")
BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.json"

_SEVERITY_COLOR = {
    "critical": "FF0000",
    "high":     "FF6600",
    "medium":   "FFAA00",
    "low":      "00AA44",
}


# ── Config helpers ────────────────────────────────────────────────────────────

def _load_cfg() -> dict:
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8")).get("teams", {})
    except Exception:
        return {}


def is_configured() -> bool:
    return bool(_load_cfg().get("webhook_url", "").strip())


def save_config(webhook_url: str, mode: str = "webhook") -> bool:
    try:
        data = {}
        if CONFIG_PATH.exists():
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        data["teams"] = {"webhook_url": webhook_url.strip(), "mode": mode}
        CONFIG_PATH.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return True
    except Exception as e:
        logger.error("No se pudo guardar config Teams: %s", e)
        return False


# ── Send ─────────────────────────────────────────────────────────────────────

def send(title: str, body: str, color: str = "6366F1",
         facts: list[dict] = None) -> dict:
    """
    Envía una notificación a Teams.
    Soporta tanto Incoming Webhook (MessageCard) como Power Automate (payload JSON simple).

    facts: lista de { "name": "...", "value": "..." }
    """
    cfg  = _load_cfg()
    url  = cfg.get("webhook_url", "").strip()
    mode = cfg.get("mode", "webhook")

    if not url:
        logger.debug("Teams no configurado — notificación omitida")
        return {"ok": False, "error": "Teams no configurado"}

    if mode == "powerautomate":
        payload = _build_powerautomate_payload(title, body, facts)
    else:
        payload = _build_messagecard_payload(title, body, color, facts)

    try:
        data = json.dumps(payload).encode("utf-8")
        req  = urllib.request.Request(
            url, data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp_body = resp.read().decode("utf-8", errors="ignore")
            # Incoming Webhook retorna "1" o empty; Power Automate retorna JSON
            return {"ok": True, "response": resp_body[:100]}
    except urllib.error.HTTPError as e:
        body_err = e.read().decode("utf-8", errors="ignore")
        logger.warning("Teams HTTP error %s: %s", e.code, body_err[:200])
        return {"ok": False, "error": f"HTTP {e.code}: {body_err[:100]}"}
    except Exception as e:
        logger.warning("Teams send error: %s", e)
        return {"ok": False, "error": str(e)}


def send_test(webhook_url: str, mode: str = "webhook") -> dict:
    """Envía mensaje de prueba con la config dada (sin guardar)."""
    cfg_bak  = _load_cfg()
    url_bak  = cfg_bak.get("webhook_url", "")
    mode_bak = cfg_bak.get("mode", "webhook")
    save_config(webhook_url, mode)
    result = send(
        title="✅ Stacky conectado a Teams",
        body="Las notificaciones de pipeline, deploys y errores llegarán a este chat.",
        color="22C55E",
    )
    # Restaurar config anterior
    save_config(url_bak, mode_bak)
    # Guardar la nueva si el test fue ok
    if result.get("ok"):
        save_config(webhook_url, mode)
    return result


# ── Payload builders ──────────────────────────────────────────────────────────

def _build_messagecard_payload(title: str, body: str,
                                color: str = "6366F1",
                                facts: list = None) -> dict:
    """Formato MessageCard para Incoming Webhook clásico."""
    card = {
        "@type":       "MessageCard",
        "@context":    "http://schema.org/extensions",
        "themeColor":  color,
        "summary":     title,
        "sections": [{
            "activityTitle":    f"**{title}**",
            "activitySubtitle": body,
            "markdown":         True,
        }],
    }
    if facts:
        card["sections"][0]["facts"] = facts
    return card


def _build_powerautomate_payload(title: str, body: str,
                                  facts: list = None) -> dict:
    """
    Payload simple para Power Automate HTTP trigger.
    El flujo recibirá estos campos y los podrá mapear a la acción de Teams.
    """
    facts_text = ""
    if facts:
        facts_text = "\n".join(f"• **{f['name']}:** {f['value']}" for f in facts)

    return {
        "title":      title,
        "body":       body + ("\n\n" + facts_text if facts_text else ""),
        "timestamp":  datetime.now().isoformat(),
        "source":     "Stacky",
    }


# ── Mensajes predefinidos ─────────────────────────────────────────────────────

def notify_pipeline_complete(ticket_id: str, titulo: str,
                              verdict: str = "APROBADO",
                              dur_total_seg: int = None) -> dict:
    dur_str = ""
    if dur_total_seg:
        m, s = divmod(int(dur_total_seg), 60)
        h, m = divmod(m, 60)
        dur_str = f"{h}h {m}m" if h else f"{m}m {s}s"

    facts = [
        {"name": "Ticket",   "value": f"#{ticket_id}"},
        {"name": "Título",   "value": titulo[:120]},
        {"name": "QA",       "value": verdict},
    ]
    if dur_str:
        facts.append({"name": "Duración total", "value": dur_str})

    icon = "✅" if "APRO" in verdict.upper() else "⚠️"
    return send(
        title=f"{icon} Stacky — Ticket #{ticket_id} completado",
        body=f"{titulo[:120]}\nEl ticket está listo para deployar.",
        color="22C55E" if "APRO" in verdict.upper() else "FFAA00",
        facts=facts,
    )


def notify_deploy_generated(ticket_id: str, titulo: str, zip_name: str,
                             file_count: int, has_sql: bool,
                             has_rollback: bool) -> dict:
    extras = []
    if has_sql:
        extras.append("incluye scripts SQL")
    if has_rollback:
        extras.append("rollback disponible")
    extras_str = "  · ".join(extras)

    facts = [
        {"name": "Ticket",   "value": f"#{ticket_id}"},
        {"name": "Archivos", "value": str(file_count)},
        {"name": "ZIP",      "value": zip_name},
    ]
    if extras_str:
        facts.append({"name": "Extras", "value": extras_str})

    return send(
        title=f"📦 Stacky — Deploy generado #{ticket_id}",
        body=f"{titulo[:120]}\nDescargá el ZIP desde el dashboard de Stacky.",
        color="6366F1",
        facts=facts,
    )


def notify_commit(ticket_id: str, titulo: str,
                  revision: str, message: str) -> dict:
    return send(
        title=f"🔖 Stacky — Git Commit #{ticket_id}",
        body=f"{titulo[:120]}",
        color="3B82F6",
        facts=[
            {"name": "Ticket",   "value": f"#{ticket_id}"},
            {"name": "Revisión", "value": revision or "?"},
            {"name": "Mensaje",  "value": message[:200]},
        ],
    )


def notify_error(ticket_id: str, stage: str, reason: str) -> dict:
    stage_icon = {"pm": "📋", "dev": "⚙", "tester": "🧪"}.get(stage, "❌")
    return send(
        title=f"❌ Stacky — Error en pipeline #{ticket_id}",
        body=f"Etapa {stage_icon} {stage.upper()} falló.",
        color="EF4444",
        facts=[
            {"name": "Ticket", "value": f"#{ticket_id}"},
            {"name": "Etapa",  "value": stage.upper()},
            {"name": "Motivo", "value": reason[:200]},
        ],
    )


def notify_incident(ticket_id: str, severity: str, description: str) -> dict:
    color = _SEVERITY_COLOR.get(severity.lower(), "FFAA00")
    return send(
        title=f"⚠️ Stacky — Incidente post-deploy #{ticket_id}",
        body=description[:300],
        color=color,
        facts=[
            {"name": "Ticket",     "value": f"#{ticket_id}"},
            {"name": "Severidad",  "value": severity.upper()},
        ],
    )
