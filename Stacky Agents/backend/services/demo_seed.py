"""C2 — Sandbox demo project.

Crea un proyecto sintético `__demo__` con tickets de ejemplo para que un dev
nuevo pueda experimentar sin tocar data real. Idempotente: si el proyecto ya
existe, no hace nada.

Los outputs de agentes en modo demo deberían usar `services.output_cache` para
no consumir tokens reales — esa parte la maneja el caller (agent_runner).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from db import session_scope
from models import Ticket

logger = logging.getLogger("stacky.demo_seed")

DEMO_PROJECT_NAME = "__demo__"

_DEMO_TICKETS = [
    {
        "ado_id": 90001,
        "title": "[DEMO] Implementar login con Google",
        "description": (
            "Como usuario, quiero loguearme con mi cuenta de Google para no tener "
            "que recordar otra contraseña. AC: usar OAuth 2.0, almacenar refresh "
            "token cifrado, expirar sesiones a las 24h."
        ),
        "ado_state": "Doing",
        "work_item_type": "User Story",
        "priority": 2,
    },
    {
        "ado_id": 90002,
        "title": "[DEMO] Bug — el carrito pierde items al cambiar de pestaña",
        "description": (
            "Repro: agregar 2 productos al carrito → cambiar de pestaña → volver. "
            "El segundo producto desaparece. Causa probable: race en localStorage."
        ),
        "ado_state": "New",
        "work_item_type": "Bug",
        "priority": 1,
    },
    {
        "ado_id": 90003,
        "title": "[DEMO] Refactor — extraer InvoiceService a su propio módulo",
        "description": (
            "El controlador de facturación tiene 800 líneas. Separar la lógica de "
            "cálculo en InvoiceService.cs y agregar tests unitarios."
        ),
        "ado_state": "Doing",
        "work_item_type": "Task",
        "priority": 3,
    },
]


def is_demo_project(name: str | None) -> bool:
    return (name or "").strip().lower() == DEMO_PROJECT_NAME


def seed_demo_project() -> dict:
    """Idempotente: crea tickets demo si no existen.

    Retorna {created: int, existed: int, project: str}.
    """
    created = 0
    existed = 0
    now = datetime.utcnow()

    with session_scope() as session:
        for spec in _DEMO_TICKETS:
            row = (
                session.query(Ticket)
                .filter(Ticket.project == DEMO_PROJECT_NAME)
                .filter(Ticket.ado_id == spec["ado_id"])
                .first()
            )
            if row:
                existed += 1
                continue
            ticket = Ticket(
                ado_id=spec["ado_id"],
                external_id=spec["ado_id"],
                project=DEMO_PROJECT_NAME,
                stacky_project_name=DEMO_PROJECT_NAME,
                tracker_type="demo",
                title=spec["title"],
                description=spec["description"],
                ado_state=spec["ado_state"],
                ado_url=f"https://demo.local/T-{spec['ado_id']}",
                priority=spec["priority"],
                work_item_type=spec["work_item_type"],
                last_synced_at=now - timedelta(minutes=2),
                created_at=now,
                stacky_status="idle",
            )
            session.add(ticket)
            created += 1

    logger.info("demo seed: created=%d existed=%d", created, existed)
    return {"created": created, "existed": existed, "project": DEMO_PROJECT_NAME}
