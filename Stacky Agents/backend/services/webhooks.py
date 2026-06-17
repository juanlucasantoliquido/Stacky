"""
FA-52 — Webhooks out on exec.completed.

Otros sistemas (CI, Slack, dashboards) reaccionan a una exec aprobada
sin polling. Stacky Agents pasa a ser hub de eventos.

Modelo:
- Tabla `webhooks` (project, event, url, secret, active)
- Eventos disponibles: exec.completed, exec.approved, exec.discarded
- Delivery con retry simple + signature HMAC-SHA256 en header

API expuesta en `/api/webhooks`.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import threading
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Index, Integer, String, Text

from config import config
from db import Base, session_scope
from models import AgentExecution

log = logging.getLogger(__name__)


class Webhook(Base):
    __tablename__ = "webhooks"

    id = Column(Integer, primary_key=True)
    project = Column(String(80))
    event = Column(String(40), nullable=False)  # exec.completed | exec.approved | exec.discarded
    url = Column(String(600), nullable=False)
    secret = Column(String(120))
    format = Column(String(20), default="raw")  # raw | teams
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_fired_at = Column(DateTime)
    last_status = Column(String(20))
    last_error = Column(Text)
    fires = Column(Integer, default=0)

    __table_args__ = (Index("ix_webhooks_event_active", "event", "active"),)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "project": self.project,
            "event": self.event,
            "url": self.url,
            "format": self.format or "raw",
            "active": self.active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_fired_at": self.last_fired_at.isoformat() if self.last_fired_at else None,
            "last_status": self.last_status,
            "last_error": self.last_error,
            "fires": self.fires or 0,
        }


# ---------------------------------------------------------------------------
# Delivery
# ---------------------------------------------------------------------------

def _sign(secret: str | None, body: bytes) -> str | None:
    if not secret:
        return None
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def _deliver(webhook_id: int, payload: dict) -> None:
    """Posta un webhook. No relanza excepciones — sólo loguea."""
    try:
        import requests  # local import — keep startup fast

        with session_scope() as session:
            wh = session.get(Webhook, webhook_id)
            if wh is None or not wh.active:
                return
            url = wh.url
            secret = wh.secret
            fmt = (wh.format or "raw").strip().lower()

        if fmt == "teams":
            body_payload = _to_teams_card(payload)
        else:
            body_payload = payload

        body = json.dumps(body_payload, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        signature = _sign(secret, body)
        if signature:
            headers["X-StackyAgents-Signature"] = signature

        resp = requests.post(url, data=body, headers=headers, timeout=8)
        status = "ok" if resp.ok else f"http_{resp.status_code}"
        with session_scope() as session:
            wh = session.get(Webhook, webhook_id)
            if wh:
                wh.last_fired_at = datetime.utcnow()
                wh.last_status = status
                wh.last_error = None if resp.ok else resp.text[:500]
                wh.fires = (wh.fires or 0) + 1
    except Exception as exc:  # noqa: BLE001
        log.warning("webhook delivery failed (id=%s): %s", webhook_id, exc)
        try:
            with session_scope() as session:
                wh = session.get(Webhook, webhook_id)
                if wh:
                    wh.last_fired_at = datetime.utcnow()
                    wh.last_status = "error"
                    wh.last_error = str(exc)[:500]
                    wh.fires = (wh.fires or 0) + 1
        except Exception:
            pass


def fire(event: str, payload: dict, project: str | None = None) -> int:
    """Lanza todos los webhooks subscritos a `event` para `project`.
    Devuelve cantidad disparada (en background)."""
    with session_scope() as session:
        q = session.query(Webhook).filter(Webhook.event == event, Webhook.active.is_(True))
        if project:
            from sqlalchemy import or_

            q = q.filter(or_(Webhook.project == project, Webhook.project.is_(None)))
        else:
            q = q.filter(Webhook.project.is_(None))
        targets = [w.id for w in q.all()]

    for wid in targets:
        threading.Thread(target=_deliver, args=(wid, payload), daemon=True).start()
    return len(targets)


def fire_completed_safe(execution_id: int) -> None:
    """Wrapper seguro para llamar desde agent_runner sin riesgo de tirar el thread."""
    try:
        fire_for_execution(execution_id)
    except Exception as exc:  # noqa: BLE001
        log.warning("fire_completed_safe failed: %s", exc)


def fire_for_execution(execution_id: int) -> None:
    """Emite webhook según estado final de la ejecución.

    V2 (flag ON):
      completed -> exec.completed
      error     -> exec.failed
      needs_review -> exec.needs_review

    Legacy (flag OFF): solo github_copilot + completed (paridad exacta).
    """
    with session_scope() as session:
        row = session.get(AgentExecution, execution_id)
        if row is None:
            return
        md = row.metadata_dict or {}
        runtime = str(md.get("runtime") or "")
        status = str(row.status or "")

        if config.STACKY_WEBHOOKS_V2_ENABLED:
            event = _event_for_status(status)
            if event is None:
                return
            payload = {
                "event": event,
                "execution": _compact_execution_payload(row),
            }
        else:
            if runtime != "github_copilot" or status != "completed":
                return
            event = "exec.completed"
            payload = {
                "event": event,
                "execution": row.to_dict(include_output=True),
            }

        project = None
        if row.ticket and row.ticket.project:
            project = row.ticket.project

    fire(event, payload, project=project)


def _event_for_status(status: str) -> str | None:
    if status == "completed":
        return "exec.completed"
    if status == "error":
        return "exec.failed"
    if status == "needs_review":
        return "exec.needs_review"
    return None


def _compact_execution_payload(row: AgentExecution) -> dict:
    md = row.metadata_dict or {}
    telem = md.get("claude_telemetry") or {}
    usage = telem.get("usage") if isinstance(telem, dict) else {}
    input_tokens = usage.get("input_tokens") if isinstance(usage, dict) else None
    output_tokens = usage.get("output_tokens") if isinstance(usage, dict) else None
    cost_usd = None
    if isinstance(telem, dict):
        cost_usd = telem.get("total_cost_usd")
    failure_kind = md.get("failure_kind")

    return {
        "id": row.id,
        "ticket_id": row.ticket_id,
        "agent_type": row.agent_type,
        "runtime": md.get("runtime"),
        "status": row.status,
        "error_message": row.error_message,
        "duration_s": round((row.duration_ms or 0) / 1000, 3) if row.duration_ms else None,
        "cost_usd": cost_usd,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "failure_kind": failure_kind,
    }


def _to_teams_card(payload: dict) -> dict:
    event = str(payload.get("event") or "stacky.event")
    execution = payload.get("execution") or {}
    status = str(execution.get("status") or "")
    agent = str(execution.get("agent_type") or "agente")
    runtime = str(execution.get("runtime") or "runtime")
    ticket_id = execution.get("ticket_id")
    duration = execution.get("duration_s")
    cost = execution.get("cost_usd")
    error_message = execution.get("error_message")

    if event == "exec.completed":
        color = "2EB886"
        verb = "completó"
    elif event == "exec.failed":
        color = "D64545"
        verb = "falló"
    else:
        color = "D4A017"
        verb = "requiere revisión"

    parts = [f"Ticket {ticket_id}" if ticket_id is not None else "Ticket N/A", runtime]
    if duration is not None:
        parts.append(f"{duration}s")
    if cost is not None:
        try:
            parts.append(f"${float(cost):.4f}")
        except Exception:
            parts.append(f"${cost}")
    if error_message:
        parts.append(str(error_message)[:240])

    text = " · ".join(parts)
    title = f"Stacky · {agent} {verb}"

    return {
        "@type": "MessageCard",
        "@context": "https://schema.org/extensions",
        "summary": title,
        "themeColor": color,
        "title": title,
        "text": text,
        "potentialAction": [],
    }


# ---------------------------------------------------------------------------
# CRUD (lo usa la API)
# ---------------------------------------------------------------------------

def create(
    *, event: str, url: str, project: str | None = None, secret: str | None = None, format: str | None = None
) -> int:
    fmt = (format or "raw").strip().lower()
    if fmt not in {"raw", "teams"}:
        fmt = "raw"
    with session_scope() as session:
        wh = Webhook(
            event=event,
            url=url,
            project=project,
            secret=secret,
            format=fmt,
            active=True,
        )
        session.add(wh)
        session.flush()
        return wh.id


def list_all() -> list[dict]:
    with session_scope() as session:
        rows = session.query(Webhook).order_by(Webhook.created_at.desc()).all()
        return [r.to_dict() for r in rows]


def deactivate(wh_id: int) -> bool:
    with session_scope() as session:
        wh = session.get(Webhook, wh_id)
        if wh is None:
            return False
        wh.active = False
        return True
