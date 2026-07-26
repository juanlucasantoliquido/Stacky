"""Plan 171 F3 — Traza estructurada de una corrida.

Reconstruir qué pasó en una ejecución deja de ser leer JSON crudo: fases, duración,
costo clasificado, fuente de telemetría, incidente enlazado y — sobre todo — los
campos que quedaron SIN DATO, declarados explícitamente en vez de inventados.

Read-only. `prompt_text` NUNCA se expone (solo su SHA).
"""
from __future__ import annotations

import logging
from datetime import timedelta

from services import run_signals as rs

logger = logging.getLogger("stacky_agents.run_trace")


def _telemetry_source(md) -> str:
    """De dónde salió la telemetría de esta corrida. Determinista, nunca lanza."""
    if not isinstance(md, dict):
        return "ninguna"
    harness = md.get("harness_telemetry")
    if isinstance(harness, dict) and harness:
        return "harness_telemetry"
    claude = md.get("claude_telemetry")
    if isinstance(claude, dict) and claude:
        return "claude_telemetry"
    if md.get("tokens_in") is not None or md.get("tokens_out") is not None \
            or md.get("model") is not None:
        return "bridge_metadata"
    return "ninguna"


def _first_present(*values):
    for value in values:
        if value is not None:
            return value
    return None


def build_run_trace(execution_id: int) -> dict | None:
    """Dict de la traza, o None si la ejecución no existe."""
    from db import session_scope
    from models import AgentExecution, Ticket
    from services.cost_analytics import extract_cost_row

    # Todo lo necesario se lee DENTRO del scope (no depender de expire_on_commit).
    with session_scope() as session:
        ex = session.get(AgentExecution, execution_id)
        if ex is None:
            return None
        md = ex.metadata_dict or {}
        status = ex.status or ""
        agent_type = ex.agent_type
        started_at = ex.started_at
        completed_at = ex.completed_at
        ticket_id = ex.ticket_id
        ticket_payload = None
        if ticket_id is not None:
            tk = session.get(Ticket, ticket_id)
            if tk is not None:
                ticket_payload = {"ticket_id": tk.id, "ado_id": tk.ado_id, "title": tk.title}

    row = extract_cost_row(md)
    source = _telemetry_source(md)
    telemetry_dict = md.get(source) if source in ("harness_telemetry", "claude_telemetry") else {}
    if not isinstance(telemetry_dict, dict):
        telemetry_dict = {}

    duration_seconds = None
    if started_at is not None and completed_at is not None:
        duration_seconds = round((completed_at - started_at).total_seconds(), 3)

    phases = []
    if started_at is not None:
        phases.append({"name": "started", "ts": started_at.isoformat() + "Z"})
    if completed_at is not None:
        # El nombre es literal "completed" sea cual sea el status final (va aparte).
        phases.append({"name": "completed", "ts": completed_at.isoformat() + "Z"})

    session_id = _first_present(md.get("session_id"), telemetry_dict.get("session_id"))
    num_turns = _first_present(md.get("num_turns"), telemetry_dict.get("num_turns"))

    stall_minutes = 120
    try:
        from services import ops_telemetry

        stall_minutes = int(ops_telemetry.load_thresholds().get("stall_minutes") or 120)
    except Exception:  # noqa: BLE001
        logger.debug("no se pudieron leer los umbrales (no crítico)", exc_info=True)

    stalled = False
    if status in rs.ACTIVE_STATUSES and started_at is not None:
        stalled = started_at < rs._utcnow() - timedelta(minutes=stall_minutes)

    incident = None
    try:
        from services import incident_store

        found = incident_store.find_by_execution(execution_id)
        if isinstance(found, dict):
            incident = {"id": found.get("id"), "title": found.get("title"),
                        "status": found.get("status")}
    except Exception:  # noqa: BLE001
        logger.debug("incident_store no disponible (no crítico)", exc_info=True)
        incident = None

    # Orden de chequeo congelado. agent_name/prompt_sha NO entran acá.
    sin_dato: list = []
    if row.model is None:
        sin_dato.append("model")
    if row.tokens_in is None and row.tokens_out is None:
        sin_dato.append("tokens")
    if row.cost_usd is None:
        sin_dato.append("cost")
    if session_id is None:
        sin_dato.append("session_id")
    if num_turns is None:
        sin_dato.append("num_turns")

    return {
        "execution_id": execution_id,
        "agent_type": agent_type,
        "status": status,
        "runtime": row.runtime,
        "model": row.model,
        "ticket": ticket_payload,
        "phases": phases,
        "duration_seconds": duration_seconds,
        "cost": {
            "cost_usd": row.cost_usd,
            "cost_kind": row.cost_kind,
            "tokens_in": row.tokens_in,
            "tokens_out": row.tokens_out,
            "cache_read_tokens": row.cache_read_tokens,
            "cache_savings_usd": row.cache_savings_usd,
        },
        "telemetry_source": source,
        "session_id": session_id,
        "num_turns": num_turns,
        # PROHIBIDO exponer prompt_text (privacidad): solo el SHA.
        "agent_name": md.get("agent_name"),
        "prompt_sha": md.get("prompt_sha"),
        "stalled": stalled,
        "incident": incident,
        "sin_dato": sin_dato,
    }
