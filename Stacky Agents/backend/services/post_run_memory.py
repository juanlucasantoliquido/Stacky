"""Captura post-run de memoria colaborativa — Fase B.

Dos hooks (el gate del v1 "score>=umbral Y verdict approved" es imposible en un
solo momento: el score existe al terminar el run, pero el approve lo hace un
humano DESPUÉS):

  - `capture_on_completion(execution_id)`: al completar un run, crea/actualiza un
    DRAFT (no exportable). Best-effort. Hoy lo llama el runtime github_copilot
    (agent_runner); los runtimes CLI caen en el hook de approve.
  - `capture_on_approval(execution_id)`: cuando un humano aprueba (verdict=
    'approved'), promueve el draft a ACTIVE — o lo crea ACTIVE si no había draft
    (caso CLI). Runtime-agnóstico: el approve opera sobre cualquier ejecución.

Consolidación (NO duplicar — decisión Fase B): este extractor crea SOLO tipos
que los servicios FA-* NO inyectan ya por el SYSTEM prompt
(`few_shot`/`anti_patterns`/`decisions`/`constraints`/`style_memory`). Hoy
captura `session_summary` (genuinamente nuevo). Así el bloque `stacky-memory`
(user prompt) nunca re-emite el conocimiento que el system prompt ya inyecta. Un
subsume total con backfill (y retirar la inyección de system prompt de los FA-*)
queda diferido por riesgo de regresión.

Privacidad: el contenido se REDACTA con `pii_masker` y se descarta el mapa (la
memoria es persistida/reinyectable; el mapa reversible es per-run y no
sobrevive). El escaneo de secretos / quarantine es del validador (Fase D).
"""
from __future__ import annotations

import logging
import os

from db import session_scope
from models import AgentExecution, Ticket

logger = logging.getLogger("stacky.post_run_memory")

# `umbral` configurable. Único número preexistente en el sistema: el 70 que
# `contract_validator` usa hoy para gatear el output_cache.
CONTRACT_SCORE_THRESHOLD = int(os.getenv("STACKY_MEMORY_CAPTURE_MIN_SCORE", "70"))

# Tope de caracteres del cuerpo capturado (el output completo puede ser enorme).
_MAX_SUMMARY_CHARS = 4000

# Tipo capturado. DISJUNTO de los tipos que inyectan los FA-* por system prompt.
_CAPTURE_TYPE = "session_summary"


def _enabled() -> bool:
    return os.getenv("STACKY_MEMORY_CAPTURE_ENABLED", "false").lower() in {
        "1",
        "true",
        "on",
        "yes",
    }


def _gather(execution_id: int) -> dict | None:
    """Lee los escalares necesarios de la ejecución + ticket (sesión propia)."""
    with session_scope() as session:
        ex = session.get(AgentExecution, execution_id)
        if ex is None:
            # Modo A del output_watcher crea Tasks sin AgentExecution: no hay de
            # dónde capturar. Se loggea para que NO sea una pérdida silenciosa.
            logger.info(
                "post_run_memory: execution %s sin AgentExecution (p.ej. output_watcher Modo A); captura omitida",
                execution_id,
            )
            return None
        if not (ex.output or "").strip():
            return None
        tk = session.get(Ticket, ex.ticket_id) if ex.ticket_id else None
        contract = ex.contract_result or {}
        meta = ex.metadata_dict or {}
        confidence = ((meta.get("confidence") or {}).get("overall")) if isinstance(meta, dict) else None
        return {
            "execution_id": ex.id,
            "agent_type": ex.agent_type,
            "ticket_id": ex.ticket_id,
            "output": ex.output or "",
            "score": contract.get("score"),
            "confidence": confidence,
            "started_by": ex.started_by,
            "project": (tk.stacky_project_name or tk.project) if tk else None,
            "ticket_title": tk.title if tk else None,
            "ado_id": tk.ado_id if tk else None,
        }


def _build_memory(data: dict) -> dict:
    """Arma (title, content, topic_key, tags) determinísticamente, con PII redactada."""
    from services import pii_masker

    agent_type = data["agent_type"] or "agent"
    ado_id = data.get("ado_id")
    ticket_title = (data.get("ticket_title") or "").strip()

    body = (data["output"] or "").strip()
    if len(body) > _MAX_SUMMARY_CHARS:
        body = body[:_MAX_SUMMARY_CHARS].rstrip() + "\n…(truncado)"
    # Redacción IRREVERSIBLE: placeholders fijos [PII_*]; el map reversible no
    # debe persistirse en memoria almacenada/exportada (plan §1.6/§10).
    body = pii_masker.redact_irreversible(body)

    footer_bits = []
    if data.get("score") is not None:
        footer_bits.append(f"contract_score={data['score']}")
    if data.get("confidence") is not None:
        footer_bits.append(f"confidence={data['confidence']}")
    if ado_id is not None:
        footer_bits.append(f"ado={ado_id}")
    footer = ("\n\n_" + " · ".join(footer_bits) + "_") if footer_bits else ""

    title = f"Resumen {agent_type}" + (f" — {ticket_title}" if ticket_title else "")
    content = body + footer
    if ado_id is not None:
        topic_key = f"session/ado-{ado_id}-{agent_type}"
    else:
        topic_key = f"session/ticket-{data['ticket_id']}-{agent_type}"
    tags = [agent_type, "session"]
    return {"title": title, "content": content, "topic_key": topic_key, "tags": tags}


def _save(data: dict, *, status: str) -> str | None:
    if not data.get("project"):
        logger.info("post_run_memory: sin project para exec=%s, no se captura", data.get("execution_id"))
        return None
    from services import memory_store

    mem = _build_memory(data)
    return memory_store.save_observation(
        project=data["project"],
        type=_CAPTURE_TYPE,
        title=mem["title"],
        content=mem["content"],
        topic_key=mem["topic_key"],
        status=status,
        scope="project",
        confidence=(float(data["confidence"]) / 100.0) if data.get("confidence") is not None else None,
        source_kind="agent_execution",
        source_execution_id=data["execution_id"],
        source_ticket_id=data["ticket_id"],
        source_ado_id=data.get("ado_id"),
        source_agent_type=data["agent_type"],
        author_email=data.get("started_by"),
        tags=mem["tags"],
    )


def capture_on_completion(execution_id: int) -> str | None:
    """Hook A: al completar, crea/actualiza un DRAFT si el score supera el umbral."""
    if not _enabled():
        return None
    try:
        data = _gather(execution_id)
        if data is None:
            return None
        score = data.get("score")
        if score is not None and score < CONTRACT_SCORE_THRESHOLD:
            logger.info(
                "post_run_memory: exec=%s score=%s < umbral=%s, no se crea draft",
                execution_id, score, CONTRACT_SCORE_THRESHOLD,
            )
            return None
        return _save(data, status="draft")
    except Exception:  # noqa: BLE001
        logger.warning("post_run_memory.capture_on_completion falló exec=%s", execution_id, exc_info=True)
        return None


def capture_on_approval(execution_id: int) -> str | None:
    """Hook B: al aprobar, promueve el draft a ACTIVE (o lo crea ACTIVE).

    El upsert por `topic_key` actualiza el draft existente a `active` (y sube
    `revision_count`); si no había draft (caso CLI), crea la fila ACTIVE.
    """
    if not _enabled():
        return None
    try:
        data = _gather(execution_id)
        if data is None:
            return None
        return _save(data, status="active")
    except Exception:  # noqa: BLE001
        logger.warning("post_run_memory.capture_on_approval falló exec=%s", execution_id, exc_info=True)
        return None


# ── Plan 47 F2 — Promoción de la NOTA del operador a memoria colaborativa ─────

_OPERATOR_NOTE_TYPE = "operator_note"  # canal USER, NO reservado (no FA-*)
_OPERATOR_NOTE_MAX = 2000


def _operator_note_enabled() -> bool:
    return os.getenv("STACKY_OPERATOR_NOTE_TO_MEMORY_ENABLED", "true").lower() in {
        "1", "true", "on", "yes",
    }


def capture_operator_note(execution_id: int) -> str | None:
    """Hook (plan 47): promueve la NOTA HUMANA de una run a memoria operator_note.

    OFF por default. Distinto de capture_on_approval: NO usa el output del
    agente; usa metadata_json["human_review"]["note"]. Si no hay nota, no captura
    (un veredicto sin nota no aporta conocimiento reutilizable).
    """
    if not _operator_note_enabled():
        return None
    try:
        from services import human_review as hr
        from services import memory_store, pii_masker
        with session_scope() as session:
            ex = session.get(AgentExecution, execution_id)
            if ex is None:
                return None
            block = (ex.metadata_dict or {}).get(hr.METADATA_KEY) or {}
            note = (block.get("note") or "").strip()
            if not note:
                return None  # veredicto sin nota → nada reutilizable
            verdict = block.get("verdict")
            agent_type = ex.agent_type or "agent"
            tk = session.get(Ticket, ex.ticket_id) if ex.ticket_id else None
            project = (tk.stacky_project_name or tk.project) if tk else None
            ado_id = tk.ado_id if tk else None
            reviewed_by = block.get("reviewed_by")
        if not project:
            return None
        body = pii_masker.redact_irreversible(note[:_OPERATOR_NOTE_MAX])
        title = f"Nota del operador — {agent_type}" + (f" (ado {ado_id})" if ado_id else "")
        content = f"Veredicto: {verdict}\n\n{body}"
        # topic_key estable por run → re-revisar la misma run upsertea (no duplica).
        topic_key = (
            f"opnote/ado-{ado_id}-{agent_type}" if ado_id
            else f"opnote/exec-{execution_id}-{agent_type}"
        )
        # Auto-categorización por veredicto (multiplica reuso en épicas futuras):
        # rejected → "rejected_reason"; approved_with_notes → "approval_condition".
        tags = [agent_type, "operator_note", verdict or "review"]
        if verdict == "rejected":
            tags.append("rejected_reason")
        elif verdict == "approved_with_notes":
            tags.append("approval_condition")

        return memory_store.save_observation(
            project=project,
            type=_OPERATOR_NOTE_TYPE,
            title=title,
            content=content,
            topic_key=topic_key,
            status="active",
            scope="project",
            source_kind="operator",
            source_execution_id=execution_id,
            source_agent_type=agent_type,
            author_email=reviewed_by,
            tags=tags,
        )
    except Exception:  # noqa: BLE001
        logger.warning("capture_operator_note falló exec=%s", execution_id, exc_info=True)
        return None
