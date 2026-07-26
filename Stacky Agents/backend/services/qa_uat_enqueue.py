"""Plan 214 F3 — Candidato de validación QAUAT al completar el Developer.

Hoy nadie conecta "el desarrollo terminó" con "validalo de punta a punta". Este
post-hook lo cierra: cuando el Developer completa un ticket, deja preparada (y
visible) la validación E2E de ese ticket.

Runtime-agnóstico por construcción: se registra en `ticket_status.on_execution_end`,
por el que cierran los 3 runners. Solo ESCRIBE METADATA: no publica, no toca ADO y
no ejecuta nada — salvo que el operador active el autorun, que corre siempre en
dry-run literal (constante en código, no configurable).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

logger = logging.getLogger("stacky_agents.qa_uat_enqueue")

# Extensible a futuro; NUNCA "qa-uat" (anti-recursión).
_TRIGGER_AGENT_TYPES = frozenset({"developer"})
# Único terminal de éxito del vocabulario canónico: el final_status ya pasó por
# _coerce_terminal_status, así que "done"/"success" no existen y needs_review
# (que exige revisión humana) no es éxito.
_OK_FINAL = "completed"


def _enabled() -> bool:
    # INSTANCIA config.config: el módulo devolvería siempre el default y mataría el OFF.
    try:
        from config import config as _cfg

        return bool(getattr(_cfg, "STACKY_QA_UAT_ON_DEV_COMPLETE_ENABLED", True))
    except Exception:  # noqa: BLE001
        return False


def _autorun_enabled() -> bool:
    try:
        from config import config as _cfg

        return bool(getattr(_cfg, "STACKY_QA_UAT_AUTORUN_ENABLED", False))
    except Exception:  # noqa: BLE001
        return False


def _post_hook(*, ticket_id, execution_id, final_status, agent_type=None, error=None,
               **kwargs) -> None:
    """Firma exacta de `register_post_hook`. Nunca lanza."""
    try:
        if not _enabled():
            return
        if final_status != _OK_FINAL:
            return
        if (agent_type or "") not in _TRIGGER_AGENT_TYPES:
            return

        from db import session_scope
        from models import AgentExecution, Ticket

        ado_id = None
        status = None
        with session_scope() as session:
            row = session.query(AgentExecution).filter(
                AgentExecution.id == execution_id).first()
            if row is None:
                return
            t = session.query(Ticket).filter(Ticket.id == ticket_id).first()
            ado_id = getattr(t, "ado_id", None)
            if not ado_id:
                return  # sin id de ADO no hay run QAUAT posible
            md = dict(row.metadata_dict or {})
            if "qa_uat_candidate" in md:
                return  # idempotente ante reintentos/zombies
            build = md.get("build_verdict") or {}
            # Gate best-effort del veredicto de build: si no compiló verificado, se
            # dice honestamente en vez de sugerir validar algo que no compila.
            status = "blocked_by_build" if build.get("gate_ok") is False else "pending"
            md["qa_uat_candidate"] = {
                "status": status,
                "ado_id": int(ado_id),
                "mode": "dry-run",
                "suggested_at": datetime.now(timezone.utc).isoformat(),
                "source": "on_execution_end",
            }
            row.metadata_dict = md

        if status == "pending" and _autorun_enabled():
            # Import LAZY: evita el ciclo service→api al arrancar.
            from api.qa_uat import start_qa_uat_run

            start_qa_uat_run(int(ado_id), mode="dry-run", started_by="qa-uat-auto")
    except Exception:  # noqa: BLE001
        logger.debug("qa_uat_enqueue post_hook falló (best-effort)", exc_info=True)


def register(register_fn) -> None:
    """Espeja incident_autopublish.register: register_fn == ticket_status.register_post_hook."""
    register_fn(_post_hook)
