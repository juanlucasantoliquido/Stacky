"""
FA-27 — Slack/Teams slash commands.

Webhook receiver compatible con Slack `/slash` y Teams `outgoing webhook`.

Comandos soportados:
  /stacky run <agent> <ado_id>     → dispara una exec
  /stacky status <exec_id>          → status + link al output
  /stacky approve <exec_id>         → aprueba
  /stacky discard <exec_id>         → descarta
  /stacky list <ado_id>             → lista execs de un ticket

Auth: shared secret HMAC en header (`X-Stacky-Slash-Token`).
Para Slack real se sumaría signing-secret + Bolt SDK; este endpoint es
provider-agnostic y devuelve respuestas en formato genérico.
"""
from __future__ import annotations

import hashlib
import hmac
import os
from dataclasses import dataclass


SLASH_TOKEN = os.getenv("SLASH_TOKEN", "stacky-slash-default-secret")


@dataclass
class SlashResponse:
    text: str
    blocks: list[dict] | None = None
    ephemeral: bool = True

    def to_dict(self) -> dict:
        d = {"text": self.text, "response_type": "ephemeral" if self.ephemeral else "in_channel"}
        if self.blocks:
            d["blocks"] = self.blocks
        return d


def verify_token(provided: str | None) -> bool:
    if not provided:
        return False
    return hmac.compare_digest(provided, SLASH_TOKEN)


def parse_command(text: str) -> tuple[str, list[str]]:
    parts = (text or "").strip().split()
    if not parts:
        return "help", []
    cmd = parts[0].lower()
    return cmd, parts[1:]


def handle(text: str, user: str = "slack-user") -> SlashResponse:
    cmd, args = parse_command(text)

    if cmd in {"help", ""}:
        return SlashResponse(text=(
            "*Stacky Agents — slash commands*\n"
            "• `/stacky run <agent> <ado_id>` — dispara una exec\n"
            "• `/stacky status <exec_id>` — status\n"
            "• `/stacky approve <exec_id>` — aprueba\n"
            "• `/stacky discard <exec_id>` — descarta\n"
            "• `/stacky list <ado_id>` — execs de un ticket"
        ))

    if cmd == "run" and len(args) >= 2:
        return _cmd_run(agent_type=args[0], ado_id=args[1], user=user)
    if cmd == "status" and args:
        return _cmd_status(exec_id=args[0])
    if cmd == "approve" and args:
        return _cmd_verdict(exec_id=args[0], verdict="approved")
    if cmd == "discard" and args:
        return _cmd_verdict(exec_id=args[0], verdict="discarded")
    if cmd == "list" and args:
        return _cmd_list(ado_id=args[0])

    return SlashResponse(text=f"Comando no reconocido: `{cmd}`. Probá `/stacky help`.")


def _cmd_run(agent_type: str, ado_id: str, user: str) -> SlashResponse:
    import agent_runner
    from db import session_scope
    from models import Ticket

    try:
        ado_int = int(ado_id.lstrip("ADO-").lstrip("#"))
    except ValueError:
        return SlashResponse(text=f"`{ado_id}` no parece un ID válido.")

    with session_scope() as session:
        t = session.query(Ticket).filter_by(ado_id=ado_int).first()
        if t is None:
            return SlashResponse(text=f"Ticket ADO-{ado_int} no existe en la BD.")
        ticket_id = t.id
        title = t.title
        description = t.description or ""

    try:
        eid = agent_runner.run_agent(
            agent_type=agent_type,
            ticket_id=ticket_id,
            context_blocks=[
                {"id": "ticket", "kind": "auto", "title": "Ticket",
                 "content": f"{title}\n\n{description}"}
            ],
            user=user,
        )
    except agent_runner.UnknownAgentError:
        return SlashResponse(text=f"Agente `{agent_type}` desconocido.")

    return SlashResponse(
        text=f":rocket: Run iniciado: agente *{agent_type}* sobre ADO-{ado_int}\n"
             f"_Exec ID: {eid}_\n"
             f"Mirá el progreso en: http://localhost:5173/?exec={eid}"
    )


def _cmd_status(exec_id: str) -> SlashResponse:
    from db import session_scope
    from models import AgentExecution

    try:
        eid = int(exec_id.lstrip("#"))
    except ValueError:
        return SlashResponse(text=f"`{exec_id}` no es un ID válido.")

    with session_scope() as session:
        ex = session.get(AgentExecution, eid)
        if ex is None:
            return SlashResponse(text=f"Exec #{eid} no existe.")
        verdict_str = f" ({ex.verdict})" if ex.verdict else ""
        return SlashResponse(text=(
            f"*exec #{ex.id}* — {ex.agent_type}\n"
            f"Status: `{ex.status}`{verdict_str}\n"
            f"Iniciado por: {ex.started_by}\n"
            f"Link: http://localhost:5173/?exec={ex.id}"
        ))


def _cmd_verdict(exec_id: str, verdict: str) -> SlashResponse:
    from db import session_scope
    from models import AgentExecution

    try:
        eid = int(exec_id.lstrip("#"))
    except ValueError:
        return SlashResponse(text=f"`{exec_id}` no es un ID válido.")

    with session_scope() as session:
        ex = session.get(AgentExecution, eid)
        if ex is None:
            return SlashResponse(text=f"Exec #{eid} no existe.")
        if ex.status != "completed":
            return SlashResponse(text=f"Exec #{eid} no está completed (está {ex.status}).")
        ex.verdict = verdict
    icon = ":white_check_mark:" if verdict == "approved" else ":x:"
    return SlashResponse(text=f"{icon} exec #{eid} marcada como *{verdict}*")


def _cmd_list(ado_id: str) -> SlashResponse:
    from db import session_scope
    from models import AgentExecution, Ticket

    try:
        ado_int = int(ado_id.lstrip("ADO-").lstrip("#"))
    except ValueError:
        return SlashResponse(text=f"`{ado_id}` no es un ID válido.")

    with session_scope() as session:
        t = session.query(Ticket).filter_by(ado_id=ado_int).first()
        if t is None:
            return SlashResponse(text=f"Ticket ADO-{ado_int} no existe.")
        execs = (
            session.query(AgentExecution)
            .filter_by(ticket_id=t.id)
            .order_by(AgentExecution.started_at.desc())
            .limit(10)
            .all()
        )
        if not execs:
            return SlashResponse(text=f"Sin ejecuciones en ADO-{ado_int}.")
        lines = [
            f"• *#{e.id}* — {e.agent_type} — `{e.status}`"
            f"{f' ({e.verdict})' if e.verdict else ''}"
            for e in execs
        ]
        return SlashResponse(
            text=f"*Ejecuciones de ADO-{ado_int}:*\n" + "\n".join(lines)
        )
