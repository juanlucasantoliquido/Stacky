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

        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
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
        with session_scope() as session:
            row = session.get(AgentExecution, execution_id)
            if row is None:
                return
            payload = {
                "event": "exec.completed",
                "execution": row.to_dict(include_output=True),
            }
            project = None
            if row.ticket and row.ticket.project:
                project = row.ticket.project
        fire("exec.completed", payload, project=project)
    except Exception as exc:  # noqa: BLE001
        log.warning("fire_completed_safe failed: %s", exc)


# ---------------------------------------------------------------------------
# CRUD (lo usa la API)
# ---------------------------------------------------------------------------

def create(*, event: str, url: str, project: str | None = None, secret: str | None = None) -> int:
    with session_scope() as session:
        wh = Webhook(
            event=event,
            url=url,
            project=project,
            secret=secret,
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
