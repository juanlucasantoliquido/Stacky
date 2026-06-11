"""stacky_mcp_tools.py — Lógica de las tools del Stacky MCP server (F2.1).

Este módulo NO habla MCP (eso lo hace stacky_mcp_server.py): expone funciones
puras de negocio que el server envuelve como tools. Separarlo permite testearlas
sin levantar el protocolo stdio.

Contrato de seguridad / gobernanza (plan §4):
  - "Solo Stacky escribe en ADO": las tools submit_* NO publican en ADO. Escriben
    el artifact canónico (comment.html / pending-task.json) — el MISMO que la
    convención de archivos — tras validarlo server-side, y encolan una operación
    en el outbox durable (ado_write_outbox). La publicación real sigue por el
    pipeline existente (output_watcher / UI / agent_completion). El MCP server ES
    Stacky: el agente nunca recibe credenciales ADO.
  - El valor agregado vs file-drop: validación ANTES de escribir → imposible
    dejar un JSON inválido o un epic_id ordinal/mismatcheado en disco. Reusa
    artifact_validator (mismo contrato que el hook F1.4 y el loop F1.3).

Las tools de lectura (get_ticket / search_memory / search_similar) reusan los
services existentes (memory_store, embeddings) sin reimplementar nada.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

# El runtime del agente trabaja sobre nombres enmascarados de PII; pero el MCP
# server corre dentro de Stacky y devuelve datos reales del ticket. El contrato
# de masking del runner aplica al prompt, no a las tool calls gobernadas.


def _slugify(text: str, *, maxlen: int = 60) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", (text or "").strip().lower()).strip("-")
    return (s or "rf")[:maxlen]


# ── Tools de lectura ──────────────────────────────────────────────────────────


def get_ticket(*, ado_id: int) -> dict[str, Any]:
    """Devuelve el ticket + comentarios conocidos para un ADO id.

    Retrieval bajo demanda: el agente pide el ticket en vez de recibir todo el
    prompt gigante. Lee de la DB de Stacky (fuente local sincronizada).
    """
    from db import session_scope
    from models import Ticket

    with session_scope() as session:
        ticket = (
            session.query(Ticket).filter(Ticket.ado_id == int(ado_id)).first()
        )
        if ticket is None:
            return {"found": False, "ado_id": int(ado_id)}
        return {
            "found": True,
            "ado_id": ticket.ado_id,
            "title": ticket.title,
            "description": ticket.description,
            "work_item_type": ticket.work_item_type,
            "state": getattr(ticket, "state", None),
            "project": ticket.project,
        }


def search_memory(
    *, project: str | None, query: str, agent_type: str | None = None, k: int = 8
) -> dict[str, Any]:
    """Memoria colaborativa on-demand (complementa la inyección estática, B6)."""
    if not project:
        return {"results": [], "note": "sin proyecto activo"}
    from services import memory_store

    rows = memory_store.search(
        project=project,
        query_text=query or None,
        agent_type=agent_type,
        k=max(1, min(int(k or 8), 20)),
    )
    results = [
        {
            "id": r.get("id"),
            "scope": r.get("scope"),
            "type": r.get("type"),
            "topic_key": r.get("topic_key"),
            "content": (r.get("content") or "")[:1500],
            "score": r.get("_score"),
        }
        for r in rows
    ]
    return {"results": results, "count": len(results)}


def search_similar(
    *, query: str, agent_type: str | None = None, k: int = 5
) -> dict[str, Any]:
    """Ejecuciones pasadas similares (embeddings FA-01)."""
    from services import embeddings

    hits = embeddings.top_k(
        query_text=query or "", agent_type=agent_type, k=max(1, min(int(k or 5), 10))
    )
    results = [h.to_dict() for h in hits]
    for r in results:
        if isinstance(r.get("snippet"), str):
            r["snippet"] = r["snippet"][:800]
    return {"results": results, "count": len(results)}


# ── Tools de escritura (gobernadas: validar → escribir artifact → encolar) ──────


def _outputs_root() -> Path:
    from services.agent_html_output import outputs_dir

    return outputs_dir()


def submit_comment(
    *,
    ado_id: int,
    html: str,
    execution_id: int | None = None,
    ticket_id: int | None = None,
) -> dict[str, Any]:
    """Escribe el comment.html canónico tras validar, y encola la publicación.

    Reemplaza la convención de archivo por una tool call con validación server-
    side: HTML no vacío. Imposible dejar un comment.html vacío en disco.
    Devuelve {ok, path, errors, operation_id?}.
    """
    from services import artifact_validator

    html = html or ""
    if not html.strip():
        return {
            "ok": False,
            "errors": ["el HTML del comentario está vacío; mandá el comentario completo"],
        }

    out_dir = _outputs_root() / str(int(ado_id))
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "comment.html"
    path.write_text(html, encoding="utf-8")

    # Validación server-side (mismo validador que el hook F1.4).
    check = artifact_validator.validate_comment_html_file(path)
    if not check.valid:
        return {"ok": False, "path": str(path), "errors": check.errors}

    op = _enqueue_comment(
        ado_id=int(ado_id),
        path=path,
        html=html,
        execution_id=execution_id,
        ticket_id=ticket_id,
    )
    return {
        "ok": True,
        "path": str(path),
        "warnings": check.warnings,
        "operation_id": op,
        "note": "comment.html escrito y encolado; Stacky lo publica en ADO.",
    }


def submit_task(
    *,
    epic_ado_id: int,
    payload: dict,
    execution_id: int | None = None,
    ticket_id: int | None = None,
) -> dict[str, Any]:
    """Escribe un pending-task.json válido para un Epic, tras validar el schema.

    Validación server-side ANTES de tocar disco: campos requeridos, status
    permitido, epic_id entero, y coherencia epic_id == epic_ado_id (ataca la
    causa raíz "ordinal vs ADO id"). Imposible dejar un JSON inválido en disco.
    """
    from services import artifact_validator

    if not isinstance(payload, dict):
        return {"ok": False, "errors": ["payload debe ser un objeto JSON"]}

    epic_ado_id = int(epic_ado_id)
    # Forzar coherencia del epic_id con el directorio antes de escribir.
    payload = dict(payload)
    payload.setdefault("epic_id", epic_ado_id)
    payload.setdefault("generated_at", datetime.utcnow().isoformat() + "Z")
    payload.setdefault("generated_by", "stacky-mcp")
    payload.setdefault("status", "pending_manual_creation")

    rf_slug = _slugify(str(payload.get("rf_id") or payload.get("title") or "rf"))
    epic_dir = _outputs_root() / f"epic-{epic_ado_id}" / rf_slug
    epic_dir.mkdir(parents=True, exist_ok=True)
    path = epic_dir / "pending-task.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    # Validación server-side (schema + epic_id real vs ordinal).
    check = artifact_validator.validate_pending_task_file(path, check_db=True)
    if not check.valid:
        # Borrar el archivo inválido: el contrato del MCP es "todo lo escrito es
        # válido". Si falla, no dejamos basura que confunda al output_watcher.
        try:
            path.unlink()
        except OSError:
            pass
        return {"ok": False, "path": str(path), "errors": check.errors}

    op = _enqueue_task(
        epic_ado_id=epic_ado_id,
        path=path,
        payload=payload,
        execution_id=execution_id,
        ticket_id=ticket_id,
    )
    return {
        "ok": True,
        "path": str(path),
        "warnings": check.warnings,
        "operation_id": op,
        "note": "pending-task.json válido escrito y encolado; Stacky crea la Task en ADO.",
    }


# ── H4 — Skills tool ──────────────────────────────────────────────────────────


def stacky_get_skill(*, name: str) -> dict[str, Any]:
    """Devuelve el cuerpo completo de una skill por nombre exacto.

    Cuando el agente recibe solo el índice de skills (modo MCP activo), puede
    pedir el cuerpo completo de una skill usando esta tool.
    """
    from services.stacky_skills import get_skill, cap_body

    skill = get_skill(name)
    if skill is None:
        return {"found": False, "name": name, "body": "", "description": ""}
    return {
        "found": True,
        "name": skill.name,
        "description": skill.description,
        "body": cap_body(skill.body),
    }


def _enqueue_comment(
    *, ado_id: int, path: Path, html: str, execution_id, ticket_id
) -> str | None:
    try:
        import hashlib

        from services import ado_write_outbox

        sha = hashlib.sha256(html.encode("utf-8")).hexdigest()
        res = ado_write_outbox.enqueue(
            kind=ado_write_outbox.KIND_POST_COMMENT,
            source="agent_completion",
            idempotency_key=f"mcp:comment:{ado_id}:{sha[:16]}",
            payload={"ado_id": ado_id, "path": str(path)},
            execution_id=execution_id,
            ticket_id=ticket_id,
            target_ado_id=ado_id,
            payload_sha256=sha,
            payload_path=str(path),
        )
        return (res.get("operation") or {}).get("operation_id")
    except Exception:
        return None


def _enqueue_task(
    *, epic_ado_id: int, path: Path, payload: dict, execution_id, ticket_id
) -> str | None:
    try:
        from services import ado_write_outbox

        rf = str(payload.get("rf_id") or payload.get("title") or "")
        res = ado_write_outbox.enqueue(
            kind=ado_write_outbox.KIND_CREATE_TASK,
            source="agent_completion",
            idempotency_key=f"mcp:task:{epic_ado_id}:{_slugify(rf)}",
            payload={"epic_ado_id": epic_ado_id, "path": str(path)},
            execution_id=execution_id,
            ticket_id=ticket_id,
            parent_ado_id=epic_ado_id,
            payload_path=str(path),
        )
        return (res.get("operation") or {}).get("operation_id")
    except Exception:
        return None
