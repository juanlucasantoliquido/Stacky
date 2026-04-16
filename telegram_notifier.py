"""
telegram_notifier.py — Notificaciones Telegram para Stacky.

Envía mensajes al chat personal del usuario cuando:
  - Un ticket completa el pipeline (QA aprobado)
  - Un deploy es generado
  - Un error ocurre en cualquier etapa

Configuración en config.json:
  "telegram": {
    "bot_token": "123456:ABC-DEF...",
    "chat_id":   "987654321"
  }

Cómo obtener el bot_token y chat_id:
  1. Hablar con @BotFather en Telegram → /newbot → copiar el token
  2. Hablar con el bot recién creado → enviarle cualquier mensaje
  3. Abrir https://api.telegram.org/bot<TOKEN>/getUpdates
  4. El chat_id aparece en la respuesta bajo "message.chat.id"
"""

import json
import logging
import os
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path

logger = logging.getLogger("stacky.telegram")

BASE_DIR    = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.json"

_TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


def _load_config() -> dict:
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8")).get("telegram", {})
    except Exception:
        return {}


def _configured() -> tuple[str, str]:
    """Retorna (bot_token, chat_id) o ("", "") si no está configurado."""
    cfg   = _load_config()
    token = cfg.get("bot_token", "").strip()
    cid   = str(cfg.get("chat_id", "")).strip()
    return token, cid


def send(message: str, parse_mode: str = "HTML") -> dict:
    """
    Envía un mensaje Telegram al chat personal.
    Retorna { ok, error }.
    """
    token, chat_id = _configured()
    if not token or not chat_id:
        logger.debug("Telegram no configurado — notificación omitida")
        return {"ok": False, "error": "Telegram no configurado"}

    url     = _TELEGRAM_API.format(token=token)
    payload = json.dumps({
        "chat_id":    chat_id,
        "text":       message,
        "parse_mode": parse_mode,
    }).encode("utf-8")

    try:
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return {"ok": body.get("ok", False)}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        logger.warning("Telegram HTTP error %s: %s", e.code, body[:200])
        return {"ok": False, "error": f"HTTP {e.code}: {body[:100]}"}
    except Exception as e:
        logger.warning("Telegram error: %s", e)
        return {"ok": False, "error": str(e)}


def is_configured() -> bool:
    token, chat_id = _configured()
    return bool(token and chat_id)


def save_config(bot_token: str, chat_id: str) -> bool:
    """Guarda el token y chat_id en config.json."""
    try:
        data = {}
        if CONFIG_PATH.exists():
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        data["telegram"] = {"bot_token": bot_token.strip(), "chat_id": str(chat_id).strip()}
        CONFIG_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return True
    except Exception as e:
        logger.error("No se pudo guardar config Telegram: %s", e)
        return False


# ── Mensajes predefinidos ─────────────────────────────────────────────────────

def notify_pipeline_complete(ticket_id: str, titulo: str, verdict: str = "APROBADO",
                              dur_total_seg: int = None) -> dict:
    """Notifica que un ticket completó el pipeline."""
    icon   = "✅" if "APRO" in verdict.upper() else "⚠️"
    dur    = ""
    if dur_total_seg:
        m, s = divmod(int(dur_total_seg), 60)
        h, m = divmod(m, 60)
        dur  = f"  ⏱ {h}h {m}m" if h else f"  ⏱ {m}m {s}s"

    msg = (
        f"{icon} <b>Stacky — Ticket Completado</b>\n"
        f"\n"
        f"🎫 <b>#{ticket_id}</b>\n"
        f"📝 {_esc(titulo)}\n"
        f"🧪 QA: <b>{_esc(verdict)}</b>{dur}\n"
        f"\n"
        f"El ticket está listo para deployar."
    )
    return send(msg)


def notify_deploy_generated(ticket_id: str, titulo: str, zip_name: str,
                             file_count: int, has_sql: bool,
                             has_rollback: bool) -> dict:
    """Notifica que se generó un paquete de deploy."""
    sql_note = "  🗄 Incluye scripts SQL" if has_sql else ""
    rb_note  = "  ↩ Rollback disponible" if has_rollback else ""
    msg = (
        f"📦 <b>Stacky — Deploy Generado</b>\n"
        f"\n"
        f"🎫 <b>#{ticket_id}</b>\n"
        f"📝 {_esc(titulo)}\n"
        f"📁 {_esc(zip_name)} ({file_count} archivos){sql_note}{rb_note}\n"
        f"\n"
        f"Descargá el ZIP desde el dashboard de Stacky."
    )
    return send(msg)


def notify_error(ticket_id: str, stage: str, reason: str) -> dict:
    """Notifica un error en el pipeline."""
    stage_icon = {"pm": "📋", "dev": "⚙", "tester": "🧪"}.get(stage, "❌")
    msg = (
        f"❌ <b>Stacky — Error en pipeline</b>\n"
        f"\n"
        f"🎫 <b>#{ticket_id}</b>\n"
        f"{stage_icon} Etapa: <b>{stage.upper()}</b>\n"
        f"💬 {_esc(reason[:200])}"
    )
    return send(msg)


def notify_test(bot_token: str, chat_id: str) -> dict:
    """Envía un mensaje de prueba con una configuración dada."""
    url     = _TELEGRAM_API.format(token=bot_token.strip())
    payload = json.dumps({
        "chat_id":    str(chat_id).strip(),
        "text":       "✅ <b>Stacky</b> — Conexión Telegram configurada correctamente 🚀",
        "parse_mode": "HTML",
    }).encode("utf-8")
    try:
        req = urllib.request.Request(
            url, data=payload,
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return {"ok": body.get("ok", False)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _esc(text: str) -> str:
    """Escapa caracteres especiales HTML para Telegram."""
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
