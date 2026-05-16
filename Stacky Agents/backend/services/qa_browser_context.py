"""Context builder for guarded Codex Browser QA UAT runs.

The QA Browser runner must not guess what to test. This service gathers the
ticket description, ADO comments, text attachments, and relevant local Stacky
executions so the plan extractor can build a constrained run specification.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from html.parser import HTMLParser
from typing import Any

from sqlalchemy import desc

from models import AgentExecution, Ticket

_PLAN_KEYWORDS = (
    "plan de prueba",
    "plan de pruebas",
    "caso de prueba",
    "casos de prueba",
    "uat",
    "criterio de aceptacion",
    "criterios de aceptacion",
    "escenario",
    "validar",
    "verificar",
    "p01",
)

_MAX_SOURCE_CHARS = 60_000
_MAX_EXEC_OUTPUT_CHARS = 40_000


@dataclass(frozen=True)
class PlanCandidate:
    kind: str
    title: str
    source_id: str
    text: str
    confidence: float
    reason: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_qa_browser_context(session: Any, ticket: Ticket) -> dict[str, Any]:
    """Build the full ticket context used by the QA Browser run spec."""
    stats: dict[str, Any] = {
        "comments_count": 0,
        "attachments_count": 0,
        "attachments_text_inlined": 0,
        "local_executions_count": 0,
        "errors": [],
    }

    description = (ticket.description or "").strip()
    comments = _fetch_comments(ticket.ado_id, stats)
    attachments = _fetch_attachments(ticket.ado_id, stats)
    local_executions = _load_local_executions(session, ticket.id, stats)

    candidates = _build_plan_candidates(
        description=description,
        comments=comments,
        attachments=attachments,
        local_executions=local_executions,
    )

    return {
        "ticket": {
            "id": ticket.id,
            "ado_id": ticket.ado_id,
            "project": ticket.project,
            "title": ticket.title,
            "state": ticket.ado_state,
            "url": ticket.ado_url,
            "priority": ticket.priority,
            "work_item_type": ticket.work_item_type,
        },
        "description": description,
        "comments": comments,
        "attachments": attachments,
        "local_executions": local_executions,
        "plan_candidates": [c.to_dict() for c in candidates],
        "stats": stats,
    }


def render_context_markdown(context: dict[str, Any]) -> str:
    """Render a compact, readable context bundle for Codex Browser."""
    ticket = context["ticket"]
    parts: list[str] = [
        f"# ADO-{ticket.get('ado_id')} - {ticket.get('title')}",
        "",
        f"Estado: {ticket.get('state') or '-'}",
        f"Tipo: {ticket.get('work_item_type') or '-'}",
        f"URL ADO: {ticket.get('url') or '-'}",
    ]

    if context.get("description"):
        parts.extend(["", "## Descripcion del ticket", _truncate(context["description"], 12_000)])

    if context.get("comments"):
        parts.extend(["", "## Comentarios ADO"])
        for comment in context["comments"][:30]:
            author = comment.get("author") or "?"
            date = comment.get("date") or ""
            text = _truncate(comment.get("text") or "", 8_000)
            parts.append(f"### {author} {date}".strip())
            parts.append(text)

    text_attachments = [
        a for a in context.get("attachments") or []
        if (a.get("text_content") or "").strip()
    ]
    if text_attachments:
        parts.extend(["", "## Adjuntos con texto"])
        for att in text_attachments[:10]:
            parts.append(f"### {att.get('name') or 'adjunto'}")
            parts.append(_truncate(att.get("text_content") or "", 12_000))

    if context.get("local_executions"):
        parts.extend(["", "## Ejecuciones Stacky relevantes"])
        for row in context["local_executions"][:6]:
            parts.append(
                f"### Exec #{row.get('id')} - {row.get('agent_type')} - {row.get('status')}"
            )
            parts.append(_truncate(row.get("output") or "", 8_000))

    return "\n\n".join(part for part in parts if part is not None)


def _fetch_comments(ado_id: int, stats: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        from services.ado_client import AdoClient

        rows = AdoClient().fetch_comments(ado_id, top=50)
    except Exception as exc:  # noqa: BLE001
        stats["errors"].append(f"fetch_comments_failed: {exc}")
        return []

    comments: list[dict[str, Any]] = []
    for idx, row in enumerate(rows, 1):
        raw = row.get("text") or ""
        text = _html_to_text(raw)
        if not text:
            continue
        comments.append(
            {
                "id": row.get("id") or idx,
                "author": row.get("author"),
                "date": row.get("date"),
                "text": _truncate(text, _MAX_SOURCE_CHARS),
                "text_html": _truncate(raw, _MAX_SOURCE_CHARS),
            }
        )
    stats["comments_count"] = len(comments)
    return comments


def _fetch_attachments(ado_id: int, stats: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        from services.ado_client import AdoClient

        rows = AdoClient().fetch_attachments(ado_id, max_text_bytes=131_072)
    except Exception as exc:  # noqa: BLE001
        stats["errors"].append(f"fetch_attachments_failed: {exc}")
        return []

    attachments: list[dict[str, Any]] = []
    for row in rows:
        text = (row.get("text_content") or "").strip()
        attachments.append(
            {
                "name": row.get("name") or "(sin nombre)",
                "url": row.get("url") or "",
                "size": int(row.get("size") or 0),
                "text_content": _truncate(_html_to_text(text), _MAX_SOURCE_CHARS) if text else None,
            }
        )
    stats["attachments_count"] = len(attachments)
    stats["attachments_text_inlined"] = sum(
        1 for item in attachments if item.get("text_content")
    )
    return attachments


def _load_local_executions(
    session: Any,
    ticket_id: int,
    stats: dict[str, Any],
) -> list[dict[str, Any]]:
    rows = (
        session.query(AgentExecution)
        .filter(AgentExecution.ticket_id == ticket_id)
        .filter(AgentExecution.agent_type.in_(["functional", "technical", "developer", "qa"]))
        .order_by(desc(AgentExecution.started_at))
        .limit(12)
        .all()
    )
    out: list[dict[str, Any]] = []
    for row in rows:
        out.append(
            {
                "id": row.id,
                "agent_type": row.agent_type,
                "status": row.status,
                "verdict": row.verdict,
                "started_at": row.started_at.isoformat() if row.started_at else None,
                "completed_at": row.completed_at.isoformat() if row.completed_at else None,
                "output": _truncate(row.output or "", _MAX_EXEC_OUTPUT_CHARS),
                "metadata": row.metadata_dict,
            }
        )
    stats["local_executions_count"] = len(out)
    return out


def _build_plan_candidates(
    *,
    description: str,
    comments: list[dict[str, Any]],
    attachments: list[dict[str, Any]],
    local_executions: list[dict[str, Any]],
) -> list[PlanCandidate]:
    candidates: list[PlanCandidate] = []

    if description:
        candidates.append(
            PlanCandidate(
                kind="ticket_description",
                title="Descripcion del ticket",
                source_id="ticket.description",
                text=description,
                confidence=0.58 if _looks_like_plan(description) else 0.35,
                reason="descripcion con potencial plan de pruebas"
                if _looks_like_plan(description)
                else "descripcion del ticket usada como fallback",
            )
        )

    for comment in comments:
        text = comment.get("text") or ""
        if not text:
            continue
        looks = _looks_like_plan(text)
        candidates.append(
            PlanCandidate(
                kind="ado_comment",
                title=f"Comentario ADO - {comment.get('author') or '?'}",
                source_id=f"comment:{comment.get('id')}",
                text=text,
                confidence=0.82 if looks else 0.45,
                reason="comentario contiene senales de plan de pruebas"
                if looks
                else "comentario disponible como contexto",
                metadata={"author": comment.get("author"), "date": comment.get("date")},
            )
        )

    for attachment in attachments:
        text = attachment.get("text_content") or ""
        if not text:
            continue
        name = attachment.get("name") or "adjunto"
        name_l = name.lower()
        name_hint = any(k in name_l for k in ("plan", "prueba", "uat", "funcional", "qa"))
        looks = _looks_like_plan(text)
        confidence = 0.92 if name_hint or looks else 0.50
        candidates.append(
            PlanCandidate(
                kind="ado_attachment",
                title=f"Adjunto ADO - {name}",
                source_id=f"attachment:{name}",
                text=text,
                confidence=confidence,
                reason="adjunto priorizado por nombre/contenido de pruebas"
                if confidence >= 0.9
                else "adjunto textual disponible como contexto",
                metadata={"name": name, "url": attachment.get("url")},
            )
        )

    for row in local_executions:
        output = row.get("output") or ""
        if not output:
            continue
        agent_type = row.get("agent_type")
        confidence = 0.76 if agent_type == "functional" else 0.52
        if _looks_like_plan(output):
            confidence += 0.1
        candidates.append(
            PlanCandidate(
                kind="stacky_execution",
                title=f"Stacky exec #{row.get('id')} - {agent_type}",
                source_id=f"execution:{row.get('id')}",
                text=output,
                confidence=min(confidence, 0.88),
                reason="output funcional local con plan de pruebas"
                if agent_type == "functional"
                else "output local relevante",
                metadata={"agent_type": agent_type, "status": row.get("status")},
            )
        )

    return _dedupe_candidates(candidates)


def _looks_like_plan(text: str) -> bool:
    lower = (text or "").lower()
    if any(keyword in lower for keyword in _PLAN_KEYWORDS):
        return True
    return bool(re.search(r"\b(P|Caso)\s*\d{1,3}\b", text or "", re.IGNORECASE))


def _dedupe_candidates(candidates: list[PlanCandidate]) -> list[PlanCandidate]:
    seen: set[str] = set()
    out: list[PlanCandidate] = []
    for candidate in sorted(candidates, key=lambda c: c.confidence, reverse=True):
        key = re.sub(r"\s+", " ", candidate.text[:800]).strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(candidate)
    return out


def _truncate(text: str, limit: int) -> str:
    text = text or ""
    if len(text) <= limit:
        return text
    return text[: limit - 80].rstrip() + f"\n\n[truncado: {len(text) - limit + 80} chars omitidos]"


class _HtmlStripper(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data:
            self.parts.append(data)

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() in {"br", "p", "div", "li", "tr", "h1", "h2", "h3", "h4"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"p", "div", "li", "tr", "h1", "h2", "h3", "h4"}:
            self.parts.append("\n")


def _html_to_text(html: str) -> str:
    if not html:
        return ""
    parser = _HtmlStripper()
    try:
        parser.feed(html)
        text = "".join(parser.parts)
    except Exception:
        text = re.sub(r"<[^>]+>", " ", html)
    text = (
        text.replace("&nbsp;", " ")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&amp;", "&")
    )
    lines = [re.sub(r"[ \t]{2,}", " ", line).strip() for line in text.splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(line for line in lines if line)).strip()
