"""Plan 129 — Paleta global: búsqueda profunda multi-fuente.

Servicio puro y determinista sobre 5 fuentes (tickets, ejecuciones, documentos,
servidores DevOps, flags del arnés). Sin IA, sin red externa. Cada fuente está
aislada con try/except: una fuente rota degrada a lista vacía, nunca tumba la
respuesta completa.
"""
from __future__ import annotations

import unicodedata
import urllib.parse
from typing import Any

from services.stacky_logger import logger

MAX_QUERY_LEN = 200
TICKET_CAP = 500
EXECUTION_CAP = 300
DEFAULT_LIMIT = 8
MAX_LIMIT = 20
GROUP_ORDER = ("ticket", "execution", "doc", "server", "flag")


def normalize(text: str) -> str:
    """Minúsculas + sin acentos (NFD, descarta combining marks) + strip."""
    t = unicodedata.normalize("NFD", (text or "").lower().strip())
    return "".join(ch for ch in t if not unicodedata.combining(ch))


def score(query: str, text: str) -> int:
    q = normalize(query)
    t = normalize(text)
    if q == "":
        return 0
    idx = t.find(q)
    if idx >= 0:
        return 100 - min(idx, 50)
    tokens = q.split()
    if len(tokens) > 1 and all(tok in t for tok in tokens):
        return 40
    return 0


def _search_tickets(qn: str, limit: int) -> list[dict[str, Any]]:
    from db import session_scope
    from models import Ticket
    from sqlalchemy import select

    hits: list[dict[str, Any]] = []
    with session_scope() as session:
        rows = session.execute(
            select(Ticket).order_by(Ticket.id.desc()).limit(TICKET_CAP)
        ).scalars().all()
        for t in rows:
            label = f"T-{t.ado_id} — {t.title}"
            s = max(score(qn, label), score(qn, str(t.ado_id)))
            if s <= 0:
                continue
            hits.append({
                "kind": "ticket",
                "id": str(t.id),
                "label": label,
                "hint": t.ado_state or "",
                "nav": f"/tickets?ticket={t.id}",
                "score": s,
            })
    hits.sort(key=lambda h: (-h["score"], h["id"]))
    return hits[:limit]


def _search_executions(qn: str, limit: int) -> list[dict[str, Any]]:
    from db import session_scope
    from models import AgentExecution, Ticket
    from sqlalchemy import select

    hits: list[dict[str, Any]] = []
    with session_scope() as session:
        rows = session.execute(
            select(AgentExecution).order_by(AgentExecution.id.desc()).limit(EXECUTION_CAP)
        ).scalars().all()
        matched = []
        for e in rows:
            label = f"Run #{e.id} · {e.agent_type} · {e.status}"
            s = max(score(qn, label), score(qn, str(e.id)))
            if s <= 0:
                continue
            matched.append((e, label, s))
        if matched:
            ticket_ids = {e.ticket_id for e, _, _ in matched}
            ado_by_ticket_id = dict(
                session.execute(
                    select(Ticket.id, Ticket.ado_id).where(Ticket.id.in_(ticket_ids))
                ).all()
            )
            for e, label, s in matched:
                ado_id = ado_by_ticket_id.get(e.ticket_id)
                hint = f"T-{ado_id}" if ado_id is not None else ""
                hits.append({
                    "kind": "execution",
                    "id": str(e.id),
                    "label": label,
                    "hint": hint,
                    "nav": f"/history?execution={e.id}",
                    "score": s,
                })
    hits.sort(key=lambda h: (-h["score"], h["id"]))
    return hits[:limit]


def _search_docs(qn: str, limit: int) -> list[dict[str, Any]]:
    from services import doc_indexer

    index = doc_indexer.build_index()
    hits: list[dict[str, Any]] = []
    stack: list[dict[str, Any]] = list(index.get("roots", []))
    while stack:
        node = stack.pop()
        children = node.get("children")
        if children:
            stack.extend(children)
        if node.get("kind") != "file":
            continue
        label = node.get("label", "")
        path = node.get("path", "")
        s = score(qn, label)
        if s <= 0:
            continue
        parent = path.rsplit("/", 1)[0] if "/" in path else ""
        hits.append({
            "kind": "doc",
            "id": path,
            "label": label,
            "hint": parent,
            "nav": f"/docs?path={urllib.parse.quote(path, safe='')}",
            "score": s,
        })
    hits.sort(key=lambda h: (-h["score"], h["id"]))
    return hits[:limit]


def _search_servers(qn: str, limit: int) -> list[dict[str, Any]]:
    from services import server_registry

    hits: list[dict[str, Any]] = []
    for s in server_registry.list_servers():
        alias = s.get("alias", "")
        host = s.get("host", "") or ""
        sc = max(score(qn, alias), score(qn, host))
        if sc <= 0:
            continue
        hits.append({
            "kind": "server",
            "id": alias,
            "label": alias,
            "hint": host,
            "nav": f"/devops?server={alias}",
            "score": sc,
        })
    hits.sort(key=lambda h: (-h["score"], h["id"]))
    return hits[:limit]


def _search_flags(qn: str, limit: int) -> list[dict[str, Any]]:
    from services.harness_flags import FLAG_REGISTRY

    hits: list[dict[str, Any]] = []
    for spec in FLAG_REGISTRY:
        sc = max(
            score(qn, spec.key),
            score(qn, spec.label),
            score(qn, spec.description or ""),
        )
        if sc <= 0:
            continue
        hits.append({
            "kind": "flag",
            "id": spec.key,
            "label": spec.label,
            "hint": spec.key,
            "nav": f"/settings?flag={spec.key}",
            "score": sc,
        })
    hits.sort(key=lambda h: (-h["score"], h["id"]))
    return hits[:limit]


_SOURCES = {
    "ticket": _search_tickets,
    "execution": _search_executions,
    "doc": _search_docs,
    "server": _search_servers,
    "flag": _search_flags,
}


def search_all(q: str, limit_per_source: int = DEFAULT_LIMIT) -> dict[str, Any]:
    qn = (q or "").strip()
    limit = max(1, min(MAX_LIMIT, limit_per_source))
    if qn == "":
        return {"ok": True, "query": "", "groups": []}

    groups: list[dict[str, Any]] = []
    for kind in GROUP_ORDER:
        try:
            hits = _SOURCES[kind](qn, limit)
        except Exception as exc:  # noqa: BLE001 — una fuente rota no tumba la respuesta
            logger.warning("global_search", "source_failed", kind=kind, detail=str(exc))
            hits = []
        if not hits:
            continue
        groups.append({
            "kind": kind,
            "hits": [{k: v for k, v in h.items() if k != "score"} for h in hits],
        })
    return {"ok": True, "query": qn, "groups": groups}
